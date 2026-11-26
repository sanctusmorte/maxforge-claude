#!/usr/bin/env python3
"""Token-efficiency audit of Claude Code sessions from their transcripts (no estimates where usage exists).

  ctx-audit.py                      → newest transcript of the current repo (cwd)
  ctx-audit.py <repo-path> [-n 3]   → newest N transcripts of that repo
  ctx-audit.py --file <x.jsonl>     → one transcript
  ctx-audit.py --baseline 58484     → compare start with a baseline (default: 2026-09-15 pre-cleanup measurement)

Prints: start context (first assistant usage: input + cache_creation + cache_read), layer breakdown from the
attachment records (chars, ≈tokens), cache-read share, peak context, tool mix, Agent calls + models, hook events,
docs/ reads without limit. Read-only."""
import argparse
import collections
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
import _paths  # noqa: E402  (hooks/_paths.py)

BASELINE = 58484


def est(s):
    cy = len(re.findall(r"[Ѐ-ӿ]", s))
    return int(cy / 2.3 + (len(s) - cy) / 3.8)


def project_dir(repo):
    root = os.path.realpath(repo)
    return _paths.user_dir("projects", "-" + re.sub(r"[^A-Za-z0-9]", "-", root.strip("/")))   # USER transcripts dir


def analyze(path):
    first = None
    tot = collections.Counter()
    tools = collections.Counter()
    agents = collections.Counter()
    hooks = collections.Counter()
    sub_models = collections.Counter()
    layers = []
    docs_reads = []
    peak = 0
    ids = {}
    with open(path, errors="replace") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except Exception:
                continue
            t = d.get("type")
            m = d.get("message") or {}
            if t == "assistant" and d.get("isSidechain"):
                sub_models[m.get("model", "?")] += 1
                continue
            if t == "assistant":
                u = m.get("usage") or {}
                ctx = u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0)
                if first is None and ctx:
                    first = ctx
                peak = max(peak, ctx)
                tot["in"] += u.get("input_tokens", 0)
                tot["cc"] += u.get("cache_creation_input_tokens", 0)
                tot["cr"] += u.get("cache_read_input_tokens", 0)
                tot["out"] += u.get("output_tokens", 0)
                tot["turns"] += 1
                for c in m.get("content") or []:
                    if isinstance(c, dict) and c.get("type") == "tool_use":
                        tools[c["name"]] += 1
                        ids[c["id"]] = c["name"]
                        inp = c.get("input", {})
                        if c["name"] == "Agent":
                            agents[f"{inp.get('subagent_type', '?')}/{inp.get('model', 'inherit')}"] += 1
                        if c["name"] == "Read" and "/docs/" in str(inp.get("file_path", "")) and not inp.get("limit"):
                            docs_reads.append(inp["file_path"].split("/docs/")[-1])
            elif t == "attachment" and first is None:
                a = d.get("attachment", {})
                at = a.get("type")
                if at == "instructions":
                    for f in a.get("files", []):
                        c = f.get("content") or ""
                        layers.append((f"instructions: {os.path.basename(os.path.dirname(f['path']))}/{os.path.basename(f['path'])}", len(c), est(c)))
                elif at == "skill_listing":
                    c = a.get("content", "")
                    layers.append(("skill_listing", len(c), est(c)))
                elif at == "agent_listing_delta":
                    c = "\n".join(a.get("addedLines", []))
                    layers.append(("agent_listing", len(c), est(c)))
                elif at == "hook_additional_context":
                    c = "\n".join(a.get("content", []))
                    layers.append((f"hook_additional_context ({a.get('hookName', '')})", len(c), est(c)))
                elif at == "hook_system_message":
                    c = a.get("content", "")
                    layers.append((f"hook_system_message ({a.get('hookName', '')})", len(c), est(c)))
                elif at == "prompt_snapshot":
                    sp = a.get("systemPrompt") or []
                    c = "\n".join(x if isinstance(x, str) else json.dumps(x) for x in sp)
                    layers.append(("system prompt (dynamic blocks)", len(c), est(c)))
                    for tl in a.get("tools") or []:
                        s = json.dumps(tl)
                        layers.append((f"tool schema: {tl.get('name')}", len(s), est(s)))
                elif at in ("session_context", "environment", "deferred_tools_delta", "mcp_instructions_delta"):
                    s = json.dumps(a, ensure_ascii=False)
                    layers.append((at, len(s), est(s)))
            elif t == "attachment":
                a = d.get("attachment", {})
                if a.get("hookName"):
                    hooks[a["hookName"].split(":")[0]] += 1
    for sf in glob.glob(os.path.join(path[:-6], "subagents", "*.jsonl")):
        with open(sf, errors="replace") as fh:
            for line in fh:
                if '"type":"assistant"' in line or '"type": "assistant"' in line:
                    mm = re.search(r'"model":\s*"([^"]+)"', line)
                    if mm:
                        sub_models[mm.group(1)] += 1
    return dict(file=os.path.basename(path), first=first, peak=peak, turns=tot["turns"],
                cache_share=round(tot["cr"] / max(1, tot["in"] + tot["cc"] + tot["cr"]) * 100, 1),
                out=tot["out"], tools=tools, agents=agents, hooks=hooks, layers=layers, docs_reads=docs_reads, sub_models=sub_models)


def report(r, baseline):
    print(f"\n=== {r['file']}")
    if r["first"] is None:
        print("no assistant usage yet (send one message first)")
        return
    diff = r["first"] - baseline
    print(f"start context: {r['first']:,} tokens | baseline {baseline:,} → {diff:+,} ({diff / baseline * 100:+.1f} %)")
    print(f"turns {r['turns']} | peak context {r['peak']:,} | cache-read share {r['cache_share']} % | output {r['out']:,}")
    if r["layers"]:
        print("layers before first reply (chars → ≈tokens):")
        known = 0
        for name, n, e in sorted(r["layers"], key=lambda x: -x[2]):
            print(f"  {e:6d}  {n:7d}  {name}")
            known += e
        print(f"  {known:6d}          measured layers total; remainder ≈ {r['first'] - known:,} = tool schemas + static harness prompt")
    print("tools:", dict(r["tools"].most_common(8)))
    print("agents (type/model):", dict(r["agents"]) or "none")
    print("subagent turns by model:", dict(r["sub_models"]) or "none")
    print("hook events:", dict(r["hooks"]) or "none")
    if r["docs_reads"]:
        print(f"docs/ reads WITHOUT limit ({len(r['docs_reads'])}):", r["docs_reads"][:6])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", nargs="?", default=os.getcwd())
    ap.add_argument("-n", type=int, default=1)
    ap.add_argument("--file")
    ap.add_argument("--baseline", type=int, default=BASELINE)
    a = ap.parse_args()
    if a.file:
        files = [a.file]
    else:
        pd = project_dir(a.repo)
        files = sorted(glob.glob(os.path.join(pd, "*.jsonl")), key=os.path.getmtime, reverse=True)[: a.n]
        if not files:
            sys.exit(f"no transcripts in {pd}")
    for f in files:
        report(analyze(f), a.baseline)


if __name__ == "__main__":
    main()
