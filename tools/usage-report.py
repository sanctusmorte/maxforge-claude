#!/usr/bin/env python3
"""Token usage report from Claude Code transcripts (read-only; no content leaves the machine).

usage-report.py [--days 7] [--root ~/.claude/projects] [--json out.json] [--md out.md]
Aggregation = docs/harness-review-2026-11-25/usage.py (dedupe by message.id, same input-equivalent weights), so the
JSON has the usage14.json shape. The markdown adds: main/sub shares by model, main-session context buckets,
effort/thinking share, cold cache rewrites by reason, per-agent table, token-guard deny counts by reason
(~/.claude/logs/token-guard.log, records with a `reason` field) and tokens per PR (~/.claude/logs/task-summary.jsonl).
"""
import argparse
import glob
import json
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
import _paths  # noqa: E402  (hooks/_paths.py)

LOGS = _paths.data_dir("logs")

# list price per 1M tokens: input, output, write5m, write1h, read (None = unpriced)
PRICE = {
    'claude-opus-5-5': (4, 20, 5, 8, 0.20),
    'claude-sonnet-5-5': (2, 10, 2.5, 4, 0.10),
}
# input-equivalent weights (same ratios for every model): out 5x, w5m 1.25x, w1h 2x, read 0.05x
W = (1, 5, 1.25, 2, 0.05)




def collect(days, root):
    now = datetime.now(timezone.utc)
    cut_ts = (now - timedelta(days=days)).timestamp()
    def ts(s):
        try:
            return datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp()
        except Exception:
            return None


    def parse(path):
        """-> list of calls sorted by time, n_compactions"""
        calls = {}
        compacts = 0
        try:
            fh = open(path, errors='replace')
        except OSError:
            return [], 0
        with fh:
            for line in fh:
                if '"compact_boundary"' in line or '"isCompactSummary":true' in line:
                    compacts += 1
                if '"usage"' not in line or '"assistant"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get('type') != 'assistant':
                    continue
                m = d.get('message') or {}
                u = m.get('usage')
                mid = m.get('id')
                if not u or not mid or m.get('model') in (None, '<synthetic>'):
                    continue
                t = ts(d.get('timestamp', ''))
                if t is None or t < cut_ts:
                    continue
                cc = u.get('cache_creation') or {}
                w1h = cc.get('ephemeral_1h_input_tokens', 0) or 0
                w5m = cc.get('ephemeral_5m_input_tokens', 0) or 0
                tot_cc = u.get('cache_creation_input_tokens', 0) or 0
                if w1h + w5m < tot_cc:
                    w5m += tot_cc - w1h - w5m
                rec = dict(t=t, model=m.get('model'), effort=d.get('effort'),
                           ttl=d.get('promptCacheRequested'), inp=u.get('input_tokens', 0) or 0,
                           out=u.get('output_tokens', 0) or 0, w5m=w5m, w1h=w1h,
                           rd=u.get('cache_read_input_tokens', 0) or 0,
                           think=((u.get('output_tokens_details') or {}).get('thinking_tokens', 0) or 0))
                old = calls.get(mid)
                if old is None or rec['out'] >= old['out']:
                    if old is not None:
                        rec['t'] = min(rec['t'], old['t'])
                    calls[mid] = rec
        return sorted(calls.values(), key=lambda r: r['t']), compacts


    def blank():
        return dict(calls=0, inp=0, out=0, w5m=0, w1h=0, rd=0)


    def add(acc, r):
        acc['calls'] += 1
        for k in ('inp', 'out', 'w5m', 'w1h', 'rd'):
            acc[k] += r[k]


    def ieq(x):
        return x['inp'] * W[0] + x['out'] * W[1] + x['w5m'] * W[2] + x['w1h'] * W[3] + x['rd'] * W[4]


    def usd(model, x):
        p = PRICE.get(model)
        if not p:
            return None
        return (x['inp'] * p[0] + x['out'] * p[1] + x['w5m'] * p[2] + x['w1h'] * p[3] + x['rd'] * p[4]) / 1e6


    by_kind_model = defaultdict(blank)      # (main|sub, model)
    by_agent = defaultdict(blank)           # agentType
    agent_stats = defaultdict(list)         # agentType -> [dict(peak, calls, ieq, first_hit, dur)]
    by_day = defaultdict(lambda: defaultdict(float))  # day -> main/sub ieq
    effort_main = defaultdict(int)          # (model, effort) -> calls
    ttl_seen = defaultdict(int)             # (kind, ttl)
    miss = defaultdict(lambda: dict(events=0, rewritten=0))  # (kind, reason)
    main_ctx = []                           # prompt size per main call
    main_ctx_tok = defaultdict(float)       # bucket -> ieq
    sess = []                               # per main session
    intervals = []                          # (start, end) of subagents for concurrency
    compactions = 0
    files = 0
    eff = defaultdict(lambda: dict(calls=0, out=0, think=0))  # (kind, model, effort)
    sub_ctx_tok = defaultdict(lambda: defaultdict(float))    # agent -> bucket -> ieq
    sess_conc = []
    expired_by_agent = defaultdict(lambda: dict(events=0, rewritten=0))


    def walk(calls, kind, agent=None):
        prev = None
        peak = 0
        tot = blank()
        first_hit = None
        for i, r in enumerate(calls):
            p = r['inp'] + r['w5m'] + r['w1h'] + r['rd']
            peak = max(peak, p)
            add(tot, r)
            add(by_kind_model[(kind, r['model'])], r)
            day = datetime.fromtimestamp(r['t'], timezone.utc).strftime('%Y-%m-%d')
            by_day[day][kind] += ieq(dict(r, calls=1))
            ttl_seen[(kind, r['ttl'])] += 1
            e2 = eff[(kind, r['model'], r['effort'])]
            e2['calls'] += 1; e2['out'] += r['out']; e2['think'] += r['think']
            if kind == 'sub':
                b2 = '<100k' if p < 100e3 else '100-150k' if p < 150e3 else '150-200k' if p < 200e3 else '200k+'
                sub_ctx_tok[agent][b2] += ieq(dict(r, calls=1))
            if kind == 'main':
                effort_main[(r['model'], r['effort'])] += 1
                main_ctx.append(p)
                b = '<100k' if p < 100e3 else '100-200k' if p < 200e3 else '200-300k' if p < 300e3 else '300k+'
                main_ctx_tok[b] += ieq(dict(r, calls=1))
            else:
                add(by_agent[agent], r)
            if i == 0:
                first_hit = (r['rd'] / p) if p else 0
            if p >= 30000 and r['rd'] / p < 0.5:
                if i == 0:
                    reason = 'first-call'
                else:
                    gap = r['t'] - prev['t']
                    lim = 3600 if (prev['ttl'] == '1h') else 300
                    if prev['model'] != r['model']:
                        reason = 'model-switch'
                    elif gap > lim:
                        reason = 'ttl-expired'
                    else:
                        reason = 'invalidated-within-ttl'
                if kind == 'sub' and reason == 'ttl-expired':
                    x = expired_by_agent[agent]; x['events'] += 1; x['rewritten'] += r['w5m'] + r['w1h'] + r['inp']
                e = miss[(kind, reason)]
                e['events'] += 1
                e['rewritten'] += r['w5m'] + r['w1h'] + r['inp']
            prev = r
        return peak, tot, first_hit


    for proj in glob.glob(os.path.join(root, '*')):
        for f in glob.glob(os.path.join(proj, '*.jsonl')):
            try:
                if os.path.getmtime(f) < cut_ts:
                    continue
            except OSError:
                continue
            files += 1
            calls, comp = parse(f)
            compactions += comp
            sid = os.path.basename(f)[:-6]
            subs = glob.glob(os.path.join(proj, sid, 'subagents', 'agent-*.jsonl'))
            if not calls and not subs:
                continue
            peak, tot, _ = walk(calls, 'main') if calls else (0, blank(), None)
            s_tot = blank()
            n_sub = 0
            loc_iv = []
            for sf in subs:
                try:
                    if os.path.getmtime(sf) < cut_ts:
                        continue
                except OSError:
                    continue
                sc, _c = parse(sf)
                if not sc:
                    continue
                meta = {}
                try:
                    meta = json.load(open(sf[:-6] + '.meta.json'))
                except Exception:
                    pass
                at = meta.get('agentType') or 'unknown'
                pk, st, fh = walk(sc, 'sub', at)
                n_sub += 1
                for k in s_tot:
                    s_tot[k] += st[k]
                agent_stats[at].append(dict(peak=pk, calls=st['calls'], ieq=ieq(st), first_hit=fh,
                                            dur=sc[-1]['t'] - sc[0]['t']))
                intervals.append((sc[0]['t'], sc[-1]['t']))
                loc_iv.append((sc[0]['t'], sc[-1]['t']))
            ev2 = sorted([(x, 1) for x, _ in loc_iv] + [(y, -1) for _, y in loc_iv]); c2 = m2 = 0
            for _, dd in ev2:
                c2 += dd; m2 = max(m2, c2)
            sess.append(dict(max_conc=m2, project=os.path.basename(proj), sid=sid[:8], main_calls=tot['calls'], main_peak=peak,
                             main_ieq=ieq(tot), sub_ieq=ieq(s_tot), n_sub=n_sub, compactions=comp,
                             hours=((calls[-1]['t'] - calls[0]['t']) / 3600 if calls else 0)))

    # max concurrency of subagents
    ev = sorted([(s, 1) for s, e in intervals] + [(e, -1) for s, e in intervals])
    cur = mx = 0
    for _, d in ev:
        cur += d
        mx = max(mx, cur)


    def pct(xs, q):
        if not xs:
            return 0
        xs = sorted(xs)
        return xs[min(len(xs) - 1, int(len(xs) * q))]


    out = dict(
        window_days=days, as_of=now.isoformat(), files=files, sessions=len(sess), compaction_markers=compactions,
        max_parallel_subagents=mx, subagents=len(intervals),
        by_kind_model={f'{k[0]}|{k[1]}': dict(v, ieq=ieq(v), usd=usd(k[1], v),
                                              hit=(v['rd'] / max(1, v['inp'] + v['w5m'] + v['w1h'] + v['rd'])))
                       for k, v in by_kind_model.items()},
        by_agent={k: dict(v, ieq=ieq(v), n=len(agent_stats[k]),
                          hit=(v['rd'] / max(1, v['inp'] + v['w5m'] + v['w1h'] + v['rd'])),
                          peak_p50=pct([x['peak'] for x in agent_stats[k]], .5),
                          peak_p90=pct([x['peak'] for x in agent_stats[k]], .9),
                          peak_max=max([x['peak'] for x in agent_stats[k]] or [0]),
                          calls_p50=pct([x['calls'] for x in agent_stats[k]], .5),
                          ieq_p50=pct([x['ieq'] for x in agent_stats[k]], .5),
                          first_hit_avg=statistics.mean([x['first_hit'] or 0 for x in agent_stats[k]]) if agent_stats[k] else 0,
                          dur_min_p50=pct([x['dur'] for x in agent_stats[k]], .5) / 60,
                          over_200k=sum(1 for x in agent_stats[k] if x['peak'] >= 200e3))
                  for k, v in by_agent.items()},
        by_day={d: dict(v) for d, v in sorted(by_day.items())},
        effort_main={f'{k[0]}|{k[1]}': v for k, v in effort_main.items()},
        ttl_seen={f'{k[0]}|{k[1]}': v for k, v in ttl_seen.items()},
        cache_miss={f'{k[0]}|{k[1]}': v for k, v in miss.items()},
        main_ctx=dict(p50=pct(main_ctx, .5), p90=pct(main_ctx, .9), p99=pct(main_ctx, .99), max=max(main_ctx or [0]),
                      ieq_by_bucket=dict(main_ctx_tok)),
        effort={f'{k[0]}|{k[1]}|{k[2]}': v for k, v in eff.items()},
        sub_ctx_ieq={k: dict(v) for k, v in sub_ctx_tok.items()},
        expired_by_agent={k: v for k, v in expired_by_agent.items()},
        top_sessions=sorted(sess, key=lambda s: -(s['main_ieq'] + s['sub_ieq']))[:15],
        sess_summary=dict(
            n=len(sess), with_subs=sum(1 for s in sess if s['n_sub']),
            main_ieq=sum(s['main_ieq'] for s in sess), sub_ieq=sum(s['sub_ieq'] for s in sess),
            subs_per_session_p50=pct([s['n_sub'] for s in sess if s['n_sub']], .5),
            subs_per_session_max=max([s['n_sub'] for s in sess] or [0]),
            main_peak_p50=pct([s['main_peak'] for s in sess if s['main_calls']], .5),
            main_peak_p90=pct([s['main_peak'] for s in sess if s['main_calls']], .9),
            compacted_sessions=sum(1 for s in sess if s['compactions'])),
    )
    return out


def read_jsonl(path, since_ts):
    out = []
    try:
        with open(path, errors="replace") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if isinstance(r, dict) and (r.get("ts") or since_ts) >= since_ts:
                    out.append(r)
    except OSError:
        pass
    return out


def deny_counts(log, since_ts):
    c = defaultdict(int)
    for r in read_jsonl(log, since_ts):
        if r.get("reason"):
            c[f"{r.get('event', '?')} / {r['reason']}"] += 1
    return dict(c)


def pr_tokens(path, since_ts):
    rows = []
    for r in read_jsonl(path, since_ts):
        if r.get("pr") or r.get("pr_url"):
            rows.append(r)
    return rows


def table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return out


def k(n):
    return f"{n / 1e6:.2f}M" if n >= 1e6 else f"{n / 1e3:.0f}k"


def render_md(o, denies, prs):
    lines = [f"# Usage report — last {o['window_days']} days (as of {o['as_of'][:16]})", "",
             f"{o['sessions']} sessions, {o['subagents']} subagents, max parallel subagents {o['max_parallel_subagents']}, "
             f"compaction markers {o['compaction_markers']}.", "",
             "## Main vs subagent share by model (input-equivalent tokens)", ""]
    total = sum(v["ieq"] for v in o["by_kind_model"].values()) or 1
    rows = [(kk.replace("|", " / "), v["calls"], k(v["ieq"]), f"{100 * v['ieq'] / total:.1f}%", f"{100 * v['hit']:.0f}%")
            for kk, v in sorted(o["by_kind_model"].items(), key=lambda x: -x[1]["ieq"])]
    lines += table(["kind / model", "calls", "ieq", "share", "cache hit"], rows)
    mc = o["main_ctx"]
    lines += ["", "## Main-session context", "",
              f"prompt size p50 {k(mc['p50'])}, p90 {k(mc['p90'])}, p99 {k(mc['p99'])}, max {k(mc['max'])}", ""]
    bt = sum(mc["ieq_by_bucket"].values()) or 1
    lines += table(["bucket", "ieq", "share"], [(b, k(v), f"{100 * v / bt:.1f}%") for b, v in sorted(mc["ieq_by_bucket"].items())])
    lines += ["", "## Effort and thinking (calls, output, thinking share)", ""]
    rows = []
    for kk, v in sorted(o["effort"].items(), key=lambda x: -x[1]["calls"]):
        rows.append((kk.replace("|", " / "), v["calls"], k(v["out"]), f"{100 * v['think'] / max(1, v['out']):.0f}%"))
    lines += table(["kind / model / effort", "calls", "output", "thinking"], rows)
    lines += ["", "## Cold cache rewrites by reason (prompt >=30k, read share <50%)", ""]
    rows = [(kk.replace("|", " / "), v["events"], k(v["rewritten"]))
            for kk, v in sorted(o["cache_miss"].items(), key=lambda x: -x[1]["rewritten"])]
    lines += table(["kind / reason", "events", "rewritten tokens"], rows)
    lines += ["", "## Per agent", ""]
    sub_total = sum(v["ieq"] for v in o["by_agent"].values()) or 1
    rows = [(a, v["n"], k(v["peak_p50"]), v["calls_p50"], f"{100 * v['ieq'] / sub_total:.1f}%")
            for a, v in sorted(o["by_agent"].items(), key=lambda x: -x[1]["ieq"])]
    lines += table(["agent", "runs", "p50 peak", "p50 calls", "share"], rows)
    lines += ["", "## token-guard denies by reason", ""]
    lines += table(["event / reason", "count"], sorted(denies.items(), key=lambda x: -x[1])) if denies else \
        ["no records with a `reason` field in the window"]
    lines += ["", "## Tokens per PR (task-summary.jsonl)", ""]
    if prs:
        lines += table(["pr", "repo", "tokens", "subagents"],
                       [(r.get("pr") or r.get("pr_url"), r.get("repo", ""), k(r.get("tokens", 0) or 0), r.get("subagents", ""))
                        for r in prs])
    else:
        lines.append("no task-summary.jsonl records in the window")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--root", default=_paths.user_dir("projects"))   # USER transcripts
    ap.add_argument("--logs", default=LOGS)
    ap.add_argument("--json")
    ap.add_argument("--md")
    a = ap.parse_args()
    out = collect(a.days, a.root)
    since = datetime.now(timezone.utc).timestamp() - a.days * 86400
    if a.json:
        json.dump(out, open(a.json, "w"), indent=1)
    md = render_md(out, deny_counts(os.path.join(a.logs, "token-guard.log"), since),
                   pr_tokens(os.path.join(a.logs, "task-summary.jsonl"), since))
    if a.md:
        os.makedirs(os.path.dirname(os.path.abspath(a.md)), exist_ok=True)
        open(a.md, "w").write(md)
    print(f"ok files {out['files']} sessions {out['sessions']} subagents {out['subagents']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
