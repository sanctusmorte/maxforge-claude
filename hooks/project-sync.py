#!/usr/bin/env python3
"""Living project state — derived from git/GitHub, never narrated.

Modes:
  (no args, stdin = Claude Code SessionStart payload) → additionalContext digest ≤ HOOK_MAX_TOKENS: frontmatter
              essentials + one-line ## Now headlines (resolved ~~…~~ skipped) + one derived line + ≤3 active tasks
              (progress.md, status ≠ merged: slug, status, first `## Next` line) + open PR count; STRICTLY read-only
              (no tracked file is touched; legacy handoff list only when no progress.md exists); the full STATE stays in the file (matcher startup|compact|clear — resume keeps its own transcript)
  --print   → print the full snapshot to stdout (for /project-sync)
  --write   → manual, inside a linked worktree only: regenerate docs/project/STATE.md `## Now` (≤3 lines, open PRs +
              active progress.md) + the derived section + frontmatter (never Next/Blockers/Do-not)
              + regenerate docs/project/specs/README.md (see --specs-index)
  --check [--strict] → memory budgets (L1): STATE ≤60 lines / ≤2.5k tok, Now ≤3 / Next ≤5 bullets, DECISIONS
              ledger lines ≤300 chars, STATE not edited >24 h after its last_sync, domain docs ≤15k tok (L3 ratchet),
              plus ~/.claude instruction budget (tools/instr-budget.py: always-loaded ≤7.5k tok, path-scoped rule
              ≤4k tok). Prints violations; exit 1 only with --strict (warning-only until the repo's baseline is clean).
  --landed [--since 14d|YYYY-MM-DD] [--domain D] [--path P] [--limit N] → L4 navigator: merged PRs into base,
              one line each `#PR date title · domains · +/- · task doc`. Domains = longest path prefix from
              docs/CODEMAP.json (origin/<base> first, then working tree); unmatched code paths → `other`.
              Merged PRs are immutable → cached per PR in <git-common-dir>/project-sync-cache.json.
  --specs-index [--since 60d] → L6: regenerate docs/project/specs/README.md (title, status, size, merged PRs
              touching/citing each spec, from the --landed cache)
  --domain-baseline → L3: record docs/domains/*.md over 15k tokens in docs/domains/budget-baseline.json; --check
              then fails a listed doc only when it GROWS (ratchet), an unlisted one when it is over budget
  --base X  → override the base branch (default: origin/dev if it exists, else origin/HEAD)
  --cwd P   → repo path (default: CLAUDE_PROJECT_DIR or cwd)

Hook mode (stdin JSON with hook_event_name) also refreshes the L0 block of ~/.claude/portfolio.md
(tools/portfolio.sh --prs --write, detached) when its GEN:state stamp is older than PORTFOLIO_REFRESH_HOURS.
Unknown flags → usage on stderr, exit 2; --help → usage, exit 0.
Silent (exit 0, no output) when the repo has no docs/project/STATE.md and no .planning/STATE.md.
A GSD-only .planning/STATE.md older than STALE_PLANNING_DAYS prints ≤5 head lines + a stale warning.
Network calls (git fetch, gh) are bounded by short timeouts; failures degrade to "(unavailable)".
"""
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402  (hooks/_paths.py: portable roots)
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone

MAX_COMMITS = 10
MAX_PRS = 6
HOOK_MAX_TOKENS = 600  # SessionStart digest budget (tokens() = chars/3.5); tools/test-hooks.py enforces it
HOOK_NOW_HEADLINES = 5  # ## Now items shown as one-line headlines; the rest → "+N more in STATE.md"
HOOK_HEADLINE_CHARS = 140
HOOK_FM_KEYS = ("last_sync", "base_branch", "deployed", "status")   # frontmatter essentials in the digest
HOOK_MAX_TASKS = 3        # active progress.md tasks in the digest
TASK_FRESH_DAYS = 14      # a progress.md untouched this long is abandoned, not active
HOOK_OWN_HANDOFF_LINES = 25   # compact/clear continuity: head of this session's own handoff, rest in the file
STALE_PLANNING_DAYS = 30   # .planning/STATE.md (GSD) older than this → 5 lines + warning


def run(cmd, cwd, timeout=12):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def repo_root(start):
    root = run(["git", "rev-parse", "--show-toplevel"], start)
    if not root:
        return ""
    # Inside a worktree under <main>/.claude/worktrees/<x> the project docs live in the worktree itself.
    return root


def state_path(root):
    for p in ("docs/project/STATE.md", ".planning/STATE.md"):
        full = os.path.join(root, p)
        if os.path.isfile(full):
            return full
    return ""


def parse_frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    fm = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip()
    return fm, (m.end() if m else 0)


def base_branch(root, override):
    if override:
        return override
    if run(["git", "rev-parse", "--verify", "-q", "origin/dev"], root):
        return "dev"
    head = run(["git", "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD"], root)
    if head:
        return head.split("/", 1)[-1]
    for b in ("master", "main"):
        if run(["git", "rev-parse", "--verify", "-q", f"origin/{b}"], root):
            return b
    return run(["git", "rev-parse", "--abbrev-ref", "HEAD"], root) or "master"


def gh_json(args, root, timeout=8):
    out = run(["gh"] + args, root, timeout)
    try:
        return json.loads(out) if out else None
    except Exception:
        return None


def deployed_shas(root):
    """Read optional version endpoints from docs/project/PROJECT.md: 'dev=<url>, prod=<url>'.
    An endpoint that is missing or unreachable (e.g. dev behind basic-auth) falls back to the
    headSha of the latest successful "Deploy <env>" workflow run, marked with the run id."""
    p = os.path.join(root, "docs/project/PROJECT.md")
    if not os.path.isfile(p):
        return {}
    text = open(p, encoding="utf-8", errors="ignore").read()
    m = re.search(r"deployed SHA.*?:\s*(.*)", text, re.I)
    if not m:
        return {}
    result = {}
    envs = re.findall(r"(dev|prod|staging)\s*=\s*(\S+)", m.group(1))
    for env, url in envs:
        if not url.startswith("http"):
            continue
        url = url.rstrip(",)")
        try:
            with urllib.request.urlopen(url, timeout=4) as resp:
                body = resp.read(4000).decode("utf-8", "ignore")
            sha = None
            try:
                data = json.loads(body)
                sha = data.get("sha") or data.get("commit") or data.get("version")
            except Exception:
                mm = re.search(r"\b[0-9a-f]{7,40}\b", body)
                sha = mm.group(0) if mm else None
            result[env] = (sha or "?")[:12]
        except Exception:
            result[env] = "unavailable"
    for env, _ in envs:
        if result.get(env, "unavailable") != "unavailable":
            continue
        runs = gh_json(["run", "list", "--workflow", f"Deploy {env}", "--status", "success", "--limit", "1",
                        "--json", "headSha,databaseId"], root) or []
        if runs and runs[0].get("headSha"):
            result[env] = f"{runs[0]['headSha'][:7]} (Deploy {env} run {runs[0].get('databaseId')})"
        elif env in result:
            result[env] = "unavailable"
    return result


def snapshot(root, base):
    fm, body_start = {}, 0
    sp = state_path(root)
    text = open(sp, encoding="utf-8", errors="ignore").read() if sp else ""
    if text:
        fm, body_start = parse_frontmatter(text)
    run(["git", "fetch", "-q", "--prune", "origin"], root, timeout=12)
    base_ref = f"origin/{base}"
    base_sha = run(["git", "rev-parse", base_ref], root)
    last = fm.get("last_sync_sha", "").strip('"') or ""
    if last and run(["git", "rev-parse", "--verify", "-q", last], root):
        commits = run(["git", "log", "--oneline", "--no-merges", f"{last}..{base_ref}"], root)
    else:
        commits = run(["git", "log", "--oneline", "--no-merges", "-n", str(MAX_COMMITS), base_ref], root)
    commit_lines = commits.splitlines()
    behind = len(commit_lines)
    merged = gh_json(["pr", "list", "--state", "merged", "--base", base, "--limit", str(MAX_PRS),
                      "--json", "number,title,mergedAt,mergeCommit"], root) or []
    open_prs = gh_json(["pr", "list", "--state", "open", "--limit", str(MAX_PRS),
                        "--json", "number,title,baseRefName,headRefName,isDraft,mergeable,statusCheckRollup"], root) or []
    runs = gh_json(["run", "list", "--branch", base, "--limit", "3",
                    "--json", "name,status,conclusion,headSha,url"], root) or []
    deployed = deployed_shas(root)
    stale = ""
    ls = fm.get("last_sync", "")
    try:
        dt = datetime.fromisoformat(ls.replace("Z", "+00:00"))
        if (datetime.now(timezone.utc) - dt).days > 7:
            stale = f"stale: last_sync {ls} is older than 7 days"
    except Exception:
        stale = "stale: no valid last_sync" if sp else ""
    if behind > 30:
        stale = (stale + "; " if stale else "stale: ") + f"{behind} commits landed since last sync"
    return {
        "state_path": sp, "text": text, "fm": fm, "body_start": body_start, "base": base,
        "base_sha": base_sha, "commits": commit_lines[:MAX_COMMITS], "behind": behind,
        "merged": merged, "open": open_prs, "runs": runs, "deployed": deployed, "stale": stale,
    }


def fmt_pr(pr):
    ci = ""
    for c in pr.get("statusCheckRollup") or []:
        concl = c.get("conclusion") or c.get("state") or ""
        if concl:
            ci = concl
            break
    return f"#{pr['number']} {pr['title'][:50]} → {pr.get('baseRefName','')} " \
           f"{'draft ' if pr.get('isDraft') else ''}{pr.get('mergeable','')} ci={ci or 'none'}"


def planning_stale(sp):
    """'YYYY-MM-DD' mtime of a GSD-only .planning/STATE.md older than STALE_PLANNING_DAYS, else ''."""
    if not sp.endswith(os.path.join(".planning", "STATE.md")):
        return ""
    try:
        mtime = os.path.getmtime(sp)
    except OSError:
        return ""
    if datetime.now(timezone.utc).timestamp() - mtime <= STALE_PLANNING_DAYS * 86400:
        return ""
    return datetime.fromtimestamp(mtime, timezone.utc).strftime("%Y-%m-%d")


def now_headlines(text):
    """First line of each open top-level '## Now' bullet; resolved '~~…~~' items are skipped."""
    m = re.search(r"^## Now[^\n]*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    heads = []
    for line in (m.group(1).splitlines() if m else []):
        if not line.startswith("- "):
            continue
        item = line[2:].strip()
        if item.startswith("~~"):
            continue
        item = item.replace("**", "")
        heads.append(item if len(item) <= HOOK_HEADLINE_CHARS else item[:HOOK_HEADLINE_CHARS - 1].rstrip() + "…")
    return heads


def render_digest(s):
    """SessionStart digest (≤ HOOK_MAX_TOKENS): frontmatter essentials + ## Now headlines + one derived line.
    Full STATE detail stays in the file; the session opens it when an item matters."""
    out = []
    rel_state = os.path.relpath(s["state_path"], state_root(s["state_path"])) if s["state_path"] else ""
    if s["text"]:
        out.append(f"## Project state — digest; full detail in {rel_state}")
        fm = s.get("fm") or parse_frontmatter(s["text"])[0]
        ess = [f"{k} {fm[k]}" for k in HOOK_FM_KEYS if fm.get(k)]
        if ess:
            out.append(" · ".join(ess))
        heads = now_headlines(s["text"])
        if heads:
            out.append("Now:")
            out += [f"  • {h}" for h in heads[:HOOK_NOW_HEADLINES]]
            if len(heads) > HOOK_NOW_HEADLINES:
                out.append(f"  (+{len(heads) - HOOK_NOW_HEADLINES} more in {rel_state})")
        else:   # GSD .planning/STATE.md or no ## Now section → a few head lines only
            body = s["text"][s.get("body_start", 0):].strip().splitlines()[:5]
            out += [l[:HOOK_HEADLINE_CHARS] for l in body]
        stale_date = planning_stale(s["state_path"])
        if stale_date:
            out.append(f"STATE stale ({stale_date}) — run /project-sync --init")
    ci = "; ".join(f"{r['name']} {r.get('conclusion') or r.get('status')} @{(r.get('headSha') or '')[:7]}"
                   for r in s["runs"][:2])
    out.append(f"Derived: origin/{s['base']} @ {s['base_sha'][:7]} · {s['behind']} commits since last sync · "
               f"{len(s['merged'])} merged / {len(s['open'])} open PRs"
               + (f" · CI {s['base']}: {ci}" if ci else "")
               + (f" · {s['stale']}" if s["stale"] else "")
               + " — lists: project-sync.py --print")
    return out


def progress_dirs(root):
    """progress.md locations (I1): docs/project/tasks/*/ of this checkout and every linked worktree, plus
    ~/.claude/state/<repo>/ for repos without docs/project."""
    roots = [root]
    for ln in run(["git", "worktree", "list", "--porcelain"], root).splitlines():
        if ln.startswith("worktree ") and ln[9:] not in roots:
            roots.append(ln[9:])
    files = []
    for r in roots:
        base = os.path.join(r, "docs", "project", "tasks")
        if os.path.isdir(base):
            files += [os.path.join(base, d, "progress.md") for d in os.listdir(base)]
    sdir = os.path.join(os.environ.get("CLAUDE_STATE_DIR") or _paths.data_dir("state"),
                        os.path.basename(root))
    if os.path.isdir(sdir):
        files += [os.path.join(sdir, f) for f in os.listdir(sdir) if f.endswith(".md")]
    return [f for f in files if os.path.isfile(f)]


def parse_progress(path):
    """{slug, status, next, goal, branch, pr, mtime} of a progress.md, or None when unreadable."""
    try:
        text = open(path, encoding="utf-8", errors="ignore").read()
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    secs, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^##\s+(.*?)\s*$", line)
        if m:
            cur = m.group(1)
            secs[cur] = []
        elif cur:
            secs[cur].append(line.strip())
    first = lambda k: next((l for l in secs.get(k, []) if l), "")
    git_txt = "\n".join(secs.get("Git", []))
    branch = re.search(r"branch:\s*(\S+)", git_txt)
    pr = re.search(r"PR:\s*#(\d+)", git_txt)
    slug = os.path.basename(os.path.dirname(path)) if path.endswith("/progress.md") else os.path.basename(path)[:-3]
    return {"slug": slug, "status": (first("Status").split() or ["active"])[0], "next": first("Next").lstrip("-* ").strip(),
            "goal": first("Goal / done-when").lstrip("-* ").strip(), "branch": branch.group(1) if branch else "",
            "pr": pr.group(1) if pr else "", "mtime": mtime}


def active_tasks(root, limit=HOOK_MAX_TASKS):
    """Newest progress.md tasks with status ≠ merged, touched within TASK_FRESH_DAYS."""
    now_ts = datetime.now(timezone.utc).timestamp()
    tasks = [t for t in (parse_progress(f) for f in progress_dirs(root)) if t and t["status"] != "merged"
             and now_ts - t["mtime"] < TASK_FRESH_DAYS * 86400]
    return sorted(tasks, key=lambda t: -t["mtime"])[:limit]


def render_tasks(tasks, n_open):
    out = [f"Active tasks (progress.md) · {n_open} open PR(s):"]
    for t in tasks:
        out.append(f"  • {t['slug']} [{t['status']}] next: {(t['next'] or '—')[:HOOK_HEADLINE_CHARS - 40]}")
    return out


def state_root(sp):
    """Repo root of docs/project/STATE.md or .planning/STATE.md."""
    up = 3 if sp.endswith(os.path.join("docs", "project", "STATE.md")) else 2
    for _ in range(up):
        sp = os.path.dirname(sp)
    return sp


def render(s, head_lines=40, sid="", hook=False):
    out = []
    if hook:
        out = render_digest(s)
    elif s["text"]:
        stale_date = planning_stale(s["state_path"])
        if stale_date:
            head_lines = min(head_lines, 5)
        out.append(f"## Project state ({os.path.relpath(s['state_path'])})")
        out.append("\n".join(s["text"].splitlines()[:head_lines]))
        if stale_date:
            out.append(f"STATE stale ({stale_date}) — run /project-sync --init")
    if not hook:
        out += render_derived(s)
    return out_with_handoffs(out, s, sid, hook)


def render_derived(s):
    out = []
    out.append(f"\n## Derived {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')} — base origin/{s['base']} @ {s['base_sha'][:7]}"
               + (f" — {s['stale']}" if s["stale"] else ""))
    if s["commits"] and not s["merged"]:
        out.append(f"Landed on {s['base']} since last sync ({s['behind']} commits, showing {len(s['commits'])}):")
        out += [f"  • {c}" for c in s["commits"]]
    elif s["commits"]:
        out.append(f"Landed on {s['base']} since last sync: {s['behind']} commits (merged PRs below).")
    else:
        out.append(f"Landed on {s['base']} since last sync: nothing")
    if s["merged"]:
        out.append("Merged PRs (latest):")
        out += [f"  • #{p['number']} {p['title'][:50]} ({(p.get('mergedAt') or '')[:10]})" for p in s["merged"]]
    if s["open"]:
        out.append("Open PRs:")
        out += [f"  • {fmt_pr(p)}" for p in s["open"]]
    if s["runs"]:
        out.append(f"CI on {s['base']}: " + "; ".join(
            f"{r['name']} {r.get('conclusion') or r.get('status')} @{(r.get('headSha') or '')[:7]}" for r in s["runs"]))
    if s["deployed"]:
        out.append("Deployed: " + ", ".join(f"{k}={v}" for k, v in s["deployed"].items())
                   + f" — base {s['base_sha'][:7]}")
    return out


def out_with_handoffs(out, s, sid, hook):
    root = state_root(s["state_path"])
    tasks = active_tasks(root) if hook else []
    if tasks:   # progress.md replaces the handoff list (2026-11-25); legacy dated handoffs are a fallback only
        out += render_tasks(tasks, len(s["open"]))
        return "\n".join(out)
    # newest handoff (<24h) from docs/project/tasks or the project's auto-memory → continue, don't restart
    cands = []
    for d in (os.path.join(root, "docs", "project", "tasks"),
              _paths.user_dir("projects", "-" + re.sub(r"[^A-Za-z0-9]", "-", root.strip("/")), "memory")):
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.startswith("handoff-") and f.endswith(".md"):
                    p = os.path.join(d, f)
                    cands.append((os.path.getmtime(p), p))
    # Own session (resume/compact) → the body, that is the continuity case. Other sessions → a list only: in a
    # busy repo the newest handoff usually belongs to a DIFFERENT concurrent session and 45 lines of it were
    # injected into every new session (found 2026-09-24).
    now_ts = datetime.now(timezone.utc).timestamp()
    recent = sorted((c for c in cands if now_ts - c[0] < 24 * 3600), reverse=True)
    rel = lambda p: os.path.relpath(p, root) if p.startswith(root) else p
    own = [p for _, p in recent if sid and sid[:8] in os.path.basename(p)]
    if own:
        try:
            body = open(own[0], encoding="utf-8", errors="ignore").read().splitlines()[:HOOK_OWN_HANDOFF_LINES if hook else 45]
            out.append(f"\n## Your handoff ({rel(own[0])}) — continue from here")
            out.extend(body)
        except OSError:
            pass
    others = [p for _, p in recent if p not in own][:3]
    if others:
        out.append("\nRecent handoffs of other sessions (open only if your task matches):")
        for p in others:
            try:
                title = next((l.lstrip("# ").strip() for l in open(p, encoding="utf-8", errors="ignore") if l.startswith("#")), "")
            except OSError:
                title = ""
            out.append(f"  • {rel(p)} — {title[:90]}")
    return "\n".join(out)


def now_lines(s, tasks):
    """≤3 generated `## Now` bullets: active progress.md tasks first, then open PRs no task claims."""
    lines, claimed = [], set()
    for t in tasks:
        pr = t["pr"] or next((str(p["number"]) for p in s["open"] if p.get("headRefName") and p["headRefName"] == t["branch"]), "")
        if pr:
            claimed.add(pr)
        lines.append(f"- {t['slug']} — branch `{t['branch'] or '?'}` — PR {'#' + pr if pr else '—'} — "
                     f"{(t['goal'] or '—')[:90]} — status {t['status']}")
    for p in s["open"]:
        if str(p["number"]) not in claimed:
            lines.append(f"- PR #{p['number']} — {p['title'][:60]} → {p.get('baseRefName', '')} — status in review")
    return lines[:NOW_MAX_BULLETS_GEN]


def is_linked_worktree(root):
    gd = run(["git", "rev-parse", "--path-format=absolute", "--git-dir"], root)
    cd = run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], root)
    return bool(gd and cd and os.path.realpath(gd) != os.path.realpath(cd))


def write_state(s, tasks=()):
    if not s["state_path"] or not s["state_path"].endswith("docs/project/STATE.md"):
        return False
    text = s["text"]
    fm, body_start = s["fm"], s["body_start"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    if fm.get("last_sync"):
        fm["prev_sync"] = fm["last_sync"]
    fm["last_sync"] = now
    fm["last_sync_sha"] = s["base_sha"]
    fm["base_branch"] = s["base"]
    if s["deployed"]:
        fm["deployed"] = "{ " + ", ".join(f"{k}: {v}" for k, v in s["deployed"].items()) + " }"
    fm.setdefault("status", "active")
    front = "---\n" + "\n".join(f"{k}: {v}" for k, v in fm.items()) + "\n---\n"
    body = text[body_start:] if body_start else text
    now_block = "## Now (≤3)\n\n" + "\n".join(now_lines(s, tasks) or ["- nothing active"]) + "\n"
    now_pat = re.compile(r"^## Now[^\n]*\n.*?(?=^## |\Z)", re.S | re.M)
    if now_pat.search(body):
        body = now_pat.sub(lambda _: now_block + "\n", body, count=1)
    else:
        body = body.rstrip("\n") + "\n\n" + now_block
    # markdown-lint friendly: blank line after the heading and before the next section
    derived = ["## Landed since last sync (derived)", ""]
    root = os.path.dirname(os.path.dirname(os.path.dirname(s["state_path"])))
    prev = (s["fm"].get("prev_sync") or "")[:10]
    rows, total, _, online = landed(root, s["base"], prev or parse_since("14d"), limit=MAX_COMMITS) if s["base"] else ([], 0, False, False)
    if rows:
        derived.append(f"{total} PRs merged into {s['base']} since {prev or '14 days'}; top {len(rows)} "
                       f"(`project-sync.py --landed` for the rest):")
        derived += render_landed(rows, bullet="- ")
    elif online:
        derived.append("- nothing merged since last sync")
    else:
        derived += [f"- {c}" for c in s["commits"]] or ["- nothing since last sync"]
    if s["deployed"]:
        derived.append("- deployed: " + ", ".join(f"{k}={v}" for k, v in s["deployed"].items()))
    derived_block = "\n".join(derived) + "\n"
    pattern = re.compile(r"## Landed since last sync \(derived\)\n.*?(?=\n## |\Z)", re.S)
    if pattern.search(body):
        body = pattern.sub(derived_block, body)
    else:
        body = body.rstrip("\n") + "\n\n" + derived_block
    body = re.sub(r"\n{3,}", "\n\n", body)
    with open(s["state_path"], "w", encoding="utf-8") as fh:
        fh.write(front + body.lstrip("\n"))
    return True


# ---------------------------------------------------------------- L1 budgets (--check)
STATE_MAX_LINES = 60
NOW_MAX_BULLETS_GEN = 3
STATE_MAX_TOKENS = 2500
NOW_MAX_BULLETS = 3
NEXT_MAX_BULLETS = 5
DECISION_MAX_CHARS = 300
RESYNC_GRACE_HOURS = 24
LEDGER_LINE = re.compile(r"^\d{4}-\d{2}-\d{2} \| D-\d+")


def tokens(text):
    return round(len(text) / 3.5)   # design E1: tokens ≈ chars/3.5 (UTF-8 chars)


def section_bullets(text, heading_prefix):
    """Top-level bullets ('- ' or 'N. ') of the first '## <heading_prefix>…' section."""
    m = re.search(rf"^## {re.escape(heading_prefix)}[^\n]*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    return [l for l in (m.group(1).splitlines() if m else []) if re.match(r"^(- |\d+\. )", l)]


def check_budgets(root):
    problems = []
    sp = os.path.join(root, "docs/project/STATE.md")
    if os.path.isfile(sp):
        text = open(sp, encoding="utf-8", errors="ignore").read()
        n, t = len(text.splitlines()), tokens(text)
        if n > STATE_MAX_LINES:
            problems.append(f"STATE.md: {n} lines > {STATE_MAX_LINES}")
        if t > STATE_MAX_TOKENS:
            problems.append(f"STATE.md: ~{t} tokens > {STATE_MAX_TOKENS}")
        for head, cap in (("Now", NOW_MAX_BULLETS), ("Next", NEXT_MAX_BULLETS)):
            b = len(section_bullets(text, head))
            if b > cap:
                problems.append(f"STATE.md: ## {head} has {b} bullets > {cap}")
        if len(re.findall(r"^## Now", text, re.M)) > 1:
            problems.append("STATE.md: more than one ## Now section")
        fm, _ = parse_frontmatter(text)
        try:
            synced = datetime.fromisoformat(fm.get("last_sync", "").replace("Z", "+00:00"))
            committed = run(["git", "log", "-1", "--format=%cI", "--", "docs/project/STATE.md"], root)
            if committed:
                lag = (datetime.fromisoformat(committed) - synced).total_seconds() / 3600
                if lag > RESYNC_GRACE_HOURS:
                    problems.append(f"STATE.md: last commit {committed[:16]} is {lag:.0f} h after last_sync "
                                    f"{fm['last_sync']} — run --write")
        except ValueError:
            problems.append("STATE.md: no valid last_sync in frontmatter")
    problems += check_domain_docs(root)
    problems += check_instruction_budget()
    dp = os.path.join(root, "docs/project/DECISIONS.md")
    if os.path.isfile(dp):
        long_ids = [re.match(r"^\S+ \| (D-\d+)", l).group(1)
                    for l in open(dp, encoding="utf-8", errors="ignore").read().splitlines()
                    if LEDGER_LINE.match(l) and len(l) > DECISION_MAX_CHARS]
        if long_ids:
            problems.append(f"DECISIONS.md: {len(long_ids)} ledger lines > {DECISION_MAX_CHARS} chars "
                            f"({', '.join(long_ids[:8])}{' …' if len(long_ids) > 8 else ''}) — detail → docs/adr/D-n-*.md")
    return problems


def check_instruction_budget():
    """~/.claude instruction files over budget (tools/instr-budget.py FAIL lines); [] when the tool is absent."""
    tool = _paths.harness_dir("tools", "instr-budget.py")
    if not os.path.isfile(tool):
        return []
    try:
        r = subprocess.run([sys.executable, tool], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return ["instr-budget.py: could not run"]
    return ["~/.claude instructions: " + l[5:] for l in r.stdout.splitlines() if l.startswith("FAIL ")]


DOMAIN_DOC_MAX_TOKENS = 15000
DOMAIN_BASELINE = "docs/domains/budget-baseline.json"   # {"<doc>.md": tokens} — oversize docs that may only shrink


def check_domain_docs(root):
    """L3 ratchet: docs/domains/*.md ≤ 15k tokens, or listed in the baseline and not larger than recorded there."""
    ddir = os.path.join(root, "docs/domains")
    if not os.path.isdir(ddir):
        return []
    try:
        baseline = json.load(open(os.path.join(root, DOMAIN_BASELINE), encoding="utf-8"))
    except (OSError, ValueError):
        baseline = None
    over, grew = [], []
    for f in sorted(os.listdir(ddir)):
        if not f.endswith(".md") or f.endswith(".history.md"):
            continue
        t = tokens(open(os.path.join(ddir, f), encoding="utf-8", errors="ignore").read())
        if t <= DOMAIN_DOC_MAX_TOKENS:
            continue
        if baseline is not None and f in baseline:
            if t > baseline[f]:
                grew.append(f"{f} {baseline[f]}→{t}")
        else:
            over.append(f"{f} ~{t // 1000}k")
    out = []
    if over:
        out.append(f"docs/domains: {len(over)} docs > {DOMAIN_DOC_MAX_TOKENS // 1000}k tokens"
                   + (" not in baseline" if baseline is not None else f" (no {DOMAIN_BASELINE})")
                   + f": {', '.join(over[:6])}{' …' if len(over) > 6 else ''} — split, history → <d>.history.md")
    if grew:
        out.append(f"docs/domains: baseline docs grew (ratchet): {', '.join(grew)}")
    return out


def write_domain_baseline(root):
    ddir = os.path.join(root, "docs/domains")
    data = {}
    for f in sorted(os.listdir(ddir)):
        if f.endswith(".md") and not f.endswith(".history.md"):
            t = tokens(open(os.path.join(ddir, f), encoding="utf-8", errors="ignore").read())
            if t > DOMAIN_DOC_MAX_TOKENS:
                data[f] = t
    with open(os.path.join(root, DOMAIN_BASELINE), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    return len(data)


# ---------------------------------------------------------------- L4 navigator (--landed)
LANDED_MAX_LINES = 30
TASK_DOC = re.compile(r"docs/(?:project/specs|superpowers/specs|project/tasks)/[\w./-]+?\.md")


def git_show(root, ref, path):
    try:
        r = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=root, capture_output=True, text=True, timeout=10)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def domain_prefixes(root, base):
    """[(prefix, domain)] longest first, from docs/CODEMAP.json {"domains": {d: {"doc", "paths": [...]}}}."""
    raw = git_show(root, f"origin/{base}", "docs/CODEMAP.json")
    wt = os.path.join(root, "docs/CODEMAP.json")
    if not raw and os.path.isfile(wt):
        raw = open(wt, encoding="utf-8").read()
    try:
        domains = json.loads(raw).get("domains", {}) if raw else {}
    except ValueError:
        domains = {}
    pairs = []
    for d, spec in domains.items():
        for p in spec.get("paths", []) + ([spec["doc"]] if spec.get("doc") else []):
            pairs.append((p.rstrip("/"), d))
    return sorted(pairs, key=lambda x: -len(x[0]))


def classify(files, prefixes):
    found, unmatched = set(), False
    for f in files:
        m = re.match(r"docs/domains/([a-z][\w-]*?)(?:\.history)?\.md$", f)
        hit = next((d for p, d in prefixes if f == p or f.startswith(p + "/") or f.startswith(p + ".")), None)
        if m and m.group(1) != "README":
            found.add(m.group(1))
        elif hit:
            found.add(hit)
        elif f.startswith(("app/", "resources/js/", "routes/", "database/")):
            unmatched = True
    return sorted(found) or (["other"] if unmatched else [])


def parse_since(value):
    m = re.fullmatch(r"(\d+)([dw])", value or "14d")
    if m:
        days = int(m.group(1)) * (7 if m.group(2) == "w" else 1)
        return datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() - days * 86400, timezone.utc).strftime("%Y-%m-%d")
    datetime.strptime(value, "%Y-%m-%d")   # raises on garbage → explicit error, not a silent default
    return value


def cache_path(root):
    common = run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], root)
    return os.path.join(common or os.path.join(root, ".git"), "project-sync-cache.json")


def landed(root, base, since, domain="", path="", limit=LANDED_MAX_LINES):
    """Merged PRs into base since `since` (YYYY-MM-DD), newest first, filtered; cached per PR number."""
    cp = cache_path(root)
    try:
        cache = json.load(open(cp, encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    prs = cache.setdefault(base, {})
    query = ["pr", "list", "--state", "merged", "--base", base, "--search", f"merged:>={since}", "--limit", "300"]
    light = gh_json(query + ["--json", "number"], root, timeout=20)
    if light is not None and any(str(p["number"]) not in prs for p in light):
        heavy = gh_json(query + ["--json", "number,title,mergedAt,additions,deletions,files,body"], root, timeout=60) or []
        for p in heavy:
            body = p.get("body") or ""
            files = [f["path"] for f in p.get("files") or []]
            docs = TASK_DOC.findall(body) or [f for f in files if TASK_DOC.fullmatch(f)]
            prs[str(p["number"])] = {"title": p["title"], "mergedAt": p.get("mergedAt") or "",
                                     "add": p.get("additions", 0), "del": p.get("deletions", 0),
                                     "files": files, "doc": docs[0] if docs else ""}
        tmp = cp + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, ensure_ascii=False)
        os.replace(tmp, cp)
    wanted = {str(p["number"]) for p in light} if light is not None else set(prs)
    prefixes = domain_prefixes(root, base)
    rows = []
    for num in wanted:
        p = prs.get(num)
        if not p or p["mergedAt"][:10] < since:
            continue
        doms = classify(p["files"], prefixes)
        if domain and domain not in doms:
            continue
        if path and not any(f.startswith(path) for f in p["files"]):
            continue
        rows.append((p["mergedAt"], num, p, doms))
    rows.sort(reverse=True)
    return rows[:limit], len(rows), bool(prefixes), light is not None


def render_landed(rows, bullet="", title_max=70):
    out = []
    for merged_at, num, p, doms in rows:
        title = p["title"] if len(p["title"]) <= title_max else p["title"][:title_max - 1] + "…"
        tail = f" · {p['doc']}" if p["doc"] else ""
        out.append(f"{bullet}#{num} {merged_at[:10]} {title} · {','.join(doms) or '-'} · +{p['add']}/-{p['del']}{tail}")
    return out


# ---------------------------------------------------------------- L6 specs index (--specs-index)
SPECS_DIR = "docs/project/specs"
STATUS_LINE = re.compile(r"^(?:\*\*)?(?:status|статус)(?:\*\*)?\s*:\s*(.+)$", re.I | re.M)


def spec_meta(path):
    text = open(path, encoding="utf-8", errors="ignore").read()
    fm, _ = parse_frontmatter(text)
    title = next((l[2:].strip() for l in text.splitlines() if l.startswith("# ")), os.path.basename(path))
    m = STATUS_LINE.search(text[:3000])
    status = (fm.get("status") or (m.group(1) if m else "") or "—").strip().strip("*")
    return title, status, tokens(text)


def write_specs_index(root, base, since):
    """docs/project/specs/README.md — one line per spec: title, status, size, merged PRs that touch or cite it."""
    sdir = os.path.join(root, SPECS_DIR)
    if not os.path.isdir(sdir):
        return 0
    landed(root, base, since, limit=10**6)   # fills the per-PR cache for the window
    try:
        prs = json.load(open(cache_path(root), encoding="utf-8")).get(base, {})
    except (OSError, ValueError):
        prs = {}
    specs = sorted(f for f in os.listdir(sdir) if f.endswith(".md") and f != "README.md")
    rows = ["# Specs — index (generated)", "",
            f"<!-- GENERATED by ~/.claude/hooks/project-sync.py --specs-index (PRs merged into {base} since {since} that "
            "touch or cite the spec); never edit by hand. Status = frontmatter `status:` or the first `Status:` line. -->", "",
            "| Spec | Title | Status | ~tok | PRs |", "|---|---|---|---|---|"]
    for f in specs:
        rel = f"{SPECS_DIR}/{f}"
        title, status, tok = spec_meta(os.path.join(sdir, f))
        nums = sorted((int(n) for n, p in prs.items() if p.get("doc") == rel or rel in p.get("files", [])), reverse=True)
        cell = lambda t, n: (t if len(t) <= n else t[:n - 1] + "…").replace("|", "/")
        rows.append(f"| [{f}]({f}) | {cell(title.lstrip('# '), 70)} | {cell(status, 50)} | {tok // 1000}k | "
                    + (", ".join(f"#{n}" for n in nums[:6]) + (" …" if len(nums) > 6 else "") if nums else "—") + " |")
    with open(os.path.join(sdir, "README.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(rows) + "\n")
    return len(specs)


# ---------------------------------------------------------------- L0 refresh (hook mode)
PORTFOLIO = _paths.data_dir("portfolio.md")   # owner-only; absent in a plugin install
PORTFOLIO_TOOL = _paths.harness_dir("tools", "portfolio.sh")
PORTFOLIO_REFRESH_HOURS = 6
PORTFOLIO_REFRESH_MARKER_TTL = 600   # s; portfolio.md.refreshing younger than this = sweep already spawned


def refresh_portfolio_if_stale():
    """Detached `portfolio.sh --prs --write` when the GEN:state stamp is older than PORTFOLIO_REFRESH_HOURS.
    Never blocks the SessionStart hook. Two guards against duplicate sweeps from concurrent sessions: the
    portfolio.md.refreshing marker (TTL PORTFOLIO_REFRESH_MARKER_TTL) here, and `flock -n` inside portfolio.sh."""
    try:
        text = open(PORTFOLIO, encoding="utf-8").read()
    except OSError:
        return
    m = re.search(r"<!-- GEN:state (\S+)", text)
    try:
        age_h = (datetime.now(timezone.utc) - datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))).total_seconds() / 3600
    except (AttributeError, ValueError):
        age_h = PORTFOLIO_REFRESH_HOURS + 1
    if age_h < PORTFOLIO_REFRESH_HOURS or not os.path.isfile(PORTFOLIO_TOOL):
        return
    marker = PORTFOLIO + ".refreshing"   # another session spawned a sweep < TTL ago → do not spawn a duplicate
    try:
        if datetime.now().timestamp() - os.path.getmtime(marker) < PORTFOLIO_REFRESH_MARKER_TTL:
            return
    except OSError:
        pass
    try:
        with open(marker, "w") as fh:
            fh.write(str(os.getpid()))
    except OSError:
        return
    log = _paths.data_dir("logs", "portfolio-gen.log")
    os.makedirs(os.path.dirname(log), exist_ok=True)
    try:
        with open(log, "a") as fh:
            subprocess.Popen(["bash", PORTFOLIO_TOOL, "--prs", "--write"], stdout=fh, stderr=fh,
                             stdin=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        pass


USAGE = ("usage: project-sync.py [--print | --write | --check [--strict] | --landed [--since 14d|YYYY-MM-DD]"
         " [--domain D] [--path P] [--limit N] | --specs-index [--since 60d] | --domain-baseline]"
         " [--base BRANCH] [--cwd PATH] [--help]\n"
         "       no mode flag = SessionStart hook mode (payload JSON on stdin); see the module docstring")
MODES = ("--print", "--write", "--check", "--landed", "--specs-index", "--domain-baseline")


def main():
    args = sys.argv[1:]
    mode = "hook"
    opts = {"base": "", "cwd": "", "since": "", "domain": "", "path": "", "limit": str(LANDED_MAX_LINES)}
    strict = False
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--help", "-h"):
            print(USAGE)
            return
        if a in MODES:
            mode = a[2:]
        elif a == "--strict":
            strict = True
        elif a.startswith("--") and a[2:] in opts and i + 1 < len(args):
            opts[a[2:]] = args[i + 1]; i += 1
        else:
            print(f"project-sync.py: unknown or incomplete argument '{a}'\n{USAGE}", file=sys.stderr)
            sys.exit(2)
        i += 1
    payload = {}
    if mode == "hook" and not sys.stdin.isatty():
        try:
            payload = json.load(sys.stdin)
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
    if mode == "hook" and payload.get("hook_event_name"):   # real hook call only, not a bare manual run
        refresh_portfolio_if_stale()
    cwd = opts["cwd"] or payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    root = repo_root(cwd)
    if mode == "landed":
        if not root:
            sys.exit("not a git repository: " + cwd)
        base = base_branch(root, opts["base"])
        since = parse_since(opts["since"] or "14d")
        rows, total, mapped, online = landed(root, base, since, opts["domain"], opts["path"], int(opts["limit"]))
        filt = "".join(f" {k}={opts[k]}" for k in ("domain", "path") if opts[k])
        print(f"# merged into {base} since {since}{filt}: {total} PRs"
              + (f", showing {len(rows)}" if total > len(rows) else "")
              + ("" if mapped else " (no docs/CODEMAP.json — domains only from docs/domains/*.md)")
              + ("" if online else " (gh unavailable — cache only)"))
        print("\n".join(render_landed(rows)))
        return
    if mode == "specs-index":
        if not root:
            sys.exit("not a git repository: " + cwd)
        n = write_specs_index(root, base_branch(root, opts["base"]), parse_since(opts["since"] or "60d"))
        print(f"{SPECS_DIR}/README.md: {n} specs")
        return
    if mode == "domain-baseline":
        if not root:
            sys.exit("not a git repository: " + cwd)
        print(f"{DOMAIN_BASELINE}: {write_domain_baseline(root)} oversize docs recorded (may only shrink)")
        return
    if mode == "check":
        if not root:
            sys.exit("not a git repository: " + cwd)
        problems = check_budgets(root)
        for p in problems:
            print(("FAIL " if strict else "WARN ") + p)
        print(f"memory budgets: {len(problems)} violation(s)" if problems else "memory budgets: ok")
        sys.exit(1 if strict and problems else 0)
    if not root or not state_path(root):
        return
    base = base_branch(root, opts["base"])
    s = snapshot(root, base)
    hook = mode == "hook"
    text = render(s, head_lines=60, sid=payload.get("session_id") or "", hook=hook)
    if mode == "write":
        if not is_linked_worktree(root) and not os.environ.get("PROJECT_SYNC_ALLOW_MAIN"):
            sys.exit("project-sync --write: run it inside a task worktree (a write in the main checkout blocks "
                     "main-sync); PROJECT_SYNC_ALLOW_MAIN=1 overrides")
        ok = write_state(s, active_tasks(root))
        if ok and os.path.isdir(os.path.join(root, SPECS_DIR)):
            write_specs_index(root, base, parse_since("60d"))
        n = len(open(s["state_path"], encoding="utf-8").read().splitlines()) if ok else 0
        print("STATE.md `## Now` + derived section " + (f"rewritten ({n} lines)" if ok else "NOT written (GSD or missing docs/project/STATE.md)"))
        print("\n".join(render_tasks(active_tasks(root), len(s["open"]))))
    elif mode == "print":
        print(text)
    else:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))


if __name__ == "__main__":
    main()
