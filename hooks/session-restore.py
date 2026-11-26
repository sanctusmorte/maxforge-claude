#!/usr/bin/env python3
"""SessionStart(compact|resume) — put the task state back into context as CONTENT, not a pointer.

precompact-handoff.py records the progress files it refreshed in `state/sessions/<session_id>.json`. After compaction
(or `--resume`) this hook prints each file (the primary in full up to 3 000 chars, up to 2 others capped), the
worktree's `git status -sb` + last 3 commits, and flags a HEAD that moved since the record. Why content: pointer-only
reminders ("read progress.md") are acted on unreliably (github.com/anthropics/claude-code/issues/43733); the hooks guide
recommends SessionStart `compact` re-injection (code.claude.com/docs/en/hooks-guide). Read-only, best effort,
stdout <= 6 000 chars (hook cap 10 000)."""
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402  (hooks/_paths.py: portable roots)
import re
import subprocess
import sys

STATE_DIR = os.environ.get("CLAUDE_STATE_DIR") or _paths.data_dir("state")
MAX_TOTAL = 6000
PRIMARY_CAP = 3000
OTHER_CAP = 900
MAX_TASKS = 3


def git(args, cwd):
    try:
        r = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def recorded_tasks(sid):
    sid = re.sub(r"[^A-Za-z0-9_-]", "", sid or "")
    try:
        with open(os.path.join(STATE_DIR, "sessions", sid + ".json"), encoding="utf-8") as fh:
            tasks = json.load(fh).get("tasks") or []
    except Exception:
        return []
    return [t for t in tasks if isinstance(t, dict) and os.path.isfile(t.get("path", ""))][:MAX_TASKS]


def task_block(t, cap):
    with open(t["path"], encoding="utf-8", errors="ignore") as fh:
        body = fh.read().strip()
    if len(body) > cap:
        body = body[:cap] + f"\n…(cut at {cap} chars — full file: {t['path']})"
    root, rec = t.get("root") or os.path.dirname(t["path"]), (t.get("head") or "")[:7]
    head = git(["rev-parse", "--short", "HEAD"], root)
    drift = f" — HEAD moved {rec} → {head} since this was written: trust git over the file" if rec and head[:7] != rec else ""
    status = "\n".join(git(["status", "-sb"], root).splitlines()[:6])
    log = git(["log", "-3", "--format=%h %s"], root)
    return f"### {t['path']}{drift}\n{body}\n\n`git status -sb`:\n{status}\nlast commits:\n{log}\n"


def main():
    try:
        d = json.load(sys.stdin)
    except Exception:
        return
    tasks = recorded_tasks(d.get("session_id"))
    if not tasks:
        return
    src = d.get("source") or "compact"
    parts = [f"## Task state restored after {src} (session-restore hook; written by PreCompact, committed on the task branch)"]
    parts += [task_block(t, PRIMARY_CAP if i == 0 else OTHER_CAP) for i, t in enumerate(tasks)]
    parts.append("Before new work: run the first file's ## Verify; where the summary and git disagree, git wins.")
    print("\n".join(parts)[:MAX_TOTAL])


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
