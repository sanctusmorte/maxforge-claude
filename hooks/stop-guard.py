#!/usr/bin/env python3
"""Stop hook — one reminder per agent worktree per day when work is left unfinished.

Blocks the stop (decision=block) if a recent agent worktree (/tmp/claude-<uid>/wt-*, ~/worktrees/*
with a .git entry, or <repo>/.claude/worktrees/*) is dirty or has a branch with commits not on any remote, so the
model finishes: commit + push + PR, or records a handoff in docs/project/STATE.md (Now/Blockers).
Only THIS session's worktrees count (2026-09-24: every headless run got an extra turn over another session's dirty
~/worktrees/wt-<executor>-*). Ownership is recorded at creation, never guessed: tools/wt-new.sh writes the creating
session's id (CLAUDE_CODE_SESSION_ID; subagents share the parent's) to `<worktree git dir>/claude-owner`. A worktree is
ours when that marker equals stdin `session_id`, or when the hook's cwd is inside it and no other session's marker is
there (EnterWorktree / `isolation: worktree` worktrees get no marker; EnterWorktree moves the session cwd into them).
No marker and cwd elsewhere → not ours, silent (external-executor worktrees, isolation worktrees handed back to the
parent, worktrees made before 2026-09-24).
Never loops: respects `stop_hook_active`, and marks each worktree as reported for 24 h.
REQ gate (interface I2, 2026-11-25): when the session's cwd is inside a linked worktree whose spec
(`docs/project/specs/<slug>.md`, `docs/project/tasks/<slug>/spec.md`, or a spec this branch touches) has a
`## Requirements status` table with rows ≠ verified, the stop is blocked ONCE per session (marker
`~/.claude/state/stop-req-<session>`); never without a spec/table, never a second time.
"""
import glob
import hashlib
import importlib.util
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402  (hooks/_paths.py: portable roots)
import subprocess
import sys
import time

RECENT_SEC = 6 * 3600
ACTIVE_SEC = 15 * 60  # dirty files touched this recently = a live agent is still writing there, not an abandoned tree
MARK_DIR = os.path.join(os.environ.get("TMPDIR", "/tmp"), "claude-stop-guard")
STATE_DIR = os.environ.get("CLAUDE_STATE_DIR") or _paths.data_dir("state")
OWNER_FILE = "claude-owner"  # written by tools/wt-new.sh into `git rev-parse --git-dir`


def git(args, cwd, timeout=8):
    try:
        r = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def candidates(cwd):
    own = own_worktree()
    if own is not None:  # an executor session: only ITS worktree is its business (2026-09-18 —
        return [own] if own else []  # чужие worktree обрывали ход исполнителя вопросом «а это чьё?»
    paths = glob.glob(f"/tmp/claude-{os.getuid()}/wt-*") + glob.glob(os.path.expanduser("~/worktrees/*"))
    root = git(["rev-parse", "--show-toplevel"], cwd) or cwd
    paths += glob.glob(os.path.join(root, ".claude", "worktrees", "*"))
    out = []
    now = time.time()
    for p in paths:
        if not os.path.isdir(p) or not os.path.exists(os.path.join(p, ".git")):
            continue
        try:
            if now - os.path.getmtime(p) > RECENT_SEC:
                continue
        except OSError:
            continue
        out.append(p)
    return out


def being_written(p, porcelain):
    now = time.time()
    for line in porcelain.splitlines():
        rel = line[3:].split(" -> ")[-1].strip('"')
        try:
            if now - os.path.getmtime(os.path.join(p, rel)) < ACTIVE_SEC:
                return True
        except OSError:
            continue
    return False


def problem(p):
    dirty = git(["status", "--porcelain"], p)
    if dirty and being_written(p, dirty):
        return None
    if dirty:
        return f"uncommitted changes ({len(dirty.splitlines())} files)"
    branch = git(["rev-parse", "--abbrev-ref", "HEAD"], p) or "?"
    if branch == "HEAD":
        return None
    if not git(["remote"], p):  # a repo with no remote at all (executor): every commit looks unpushed for ever
        return None
    unpushed = git(["log", "--oneline", f"{branch}", "--not", "--remotes"], p)
    if unpushed:
        return f"branch {branch} has {len(unpushed.splitlines())} commit(s) not on any remote"
    return None


def already_reported(p):
    os.makedirs(MARK_DIR, exist_ok=True)
    key = hashlib.sha1(p.encode()).hexdigest()[:12]
    marker = os.path.join(MARK_DIR, key)
    if os.path.exists(marker) and time.time() - os.path.getmtime(marker) < 24 * 3600:
        return True
    open(marker, "w").write(p)
    return False


# Owner-only: an external task executor tags its sessions with an env var (private/executor.json; absent = off).
EXECUTOR = _paths.private("executor", {})


def executor_task_id():
    """Task id of the executor session this hook runs in, or None (also when no executor is configured)."""
    name = EXECUTOR.get("task_env")
    return os.environ.get(name) if name else None


def own_worktree():
    """The worktree of the executor task this session runs for, or None when we are not inside such a session.

    A session started by the executor carries its task-id env var; its worktree is recorded in the task state
    (`<executor home>/tasks/<id>/state.json` → run.worktree). Returning a list of one keeps the guard useful
    (undelivered work is still caught) without ever asking the executor about somebody else's worktree.
    Empty string = we know the session but not its worktree: then the guard has nothing to say."""
    task_id = executor_task_id()
    if not task_id:
        return None
    home = os.environ.get(EXECUTOR.get("home_env", "")) or EXECUTOR.get("home_default", "")
    state = os.path.join(home, "tasks", task_id, "state.json")
    try:
        with open(state, encoding="utf-8") as fh:
            return ((json.load(fh).get("run") or {}).get("worktree") or "")
    except Exception:
        return ""


def owner(p):
    """Session id recorded by wt-new.sh in the worktree's git dir, or "" when there is none."""
    dotgit = os.path.join(p, ".git")
    gitdir = dotgit
    if os.path.isfile(dotgit):  # linked worktree: `.git` is a file "gitdir: <repo>/.git/worktrees/<name>"
        try:
            with open(dotgit, encoding="utf-8") as fh:
                line = fh.readline().strip()
        except OSError:
            return ""
        if not line.startswith("gitdir:"):
            return ""
        gitdir = os.path.join(p, line[len("gitdir:"):].strip())
    try:
        with open(os.path.join(gitdir, OWNER_FILE), encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def owned(paths, cwd, session_id):
    """Subset of `paths` this session owns: marker == session_id, or cwd inside it with no foreign marker."""
    real_cwd = os.path.realpath(cwd)
    mine = []
    for p in paths:
        mark = owner(p)
        real = os.path.realpath(p)
        inside = real_cwd == real or real_cwd.startswith(real + os.sep)
        if (session_id and mark == session_id) or (inside and (not mark or mark == session_id)):
            mine.append(p)
    return mine


def agents_live(transcript_path, session_id, window=600):
    """Background subagents of this session wrote their transcript in the last `window` s → their worktrees are
    work in progress, not abandoned (a worker can run a test suite for >15 min without touching files)."""
    if not transcript_path or not session_id:
        return False
    now = time.time()
    for f in glob.glob(os.path.join(os.path.dirname(transcript_path), session_id, "subagents", "*.jsonl")):
        try:
            if now - os.path.getmtime(f) < window:
                return True
        except OSError:
            continue
    return False


def req_status_module():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools", "req-status.py")
    try:
        spec = importlib.util.spec_from_file_location("req_status", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def spec_candidates(root, branch):
    slug = branch.split("/", 1)[-1]
    found = [os.path.join(root, "docs", "project", "tasks", slug, "spec.md"),
             os.path.join(root, "docs", "project", "specs", slug + ".md")]
    touched = [ln[3:] for ln in (git(["status", "--porcelain"], root) or "").splitlines()]
    touched += (git(["log", "--name-only", "--format=", branch, "--not", "--remotes"], root) or "").splitlines()
    for rel in touched:
        rel = rel.strip().strip('"')
        if rel.startswith("docs/project/") and rel.endswith(".md") and ("/specs/" in rel or rel.endswith("/spec.md")):
            found.append(os.path.join(root, rel))
    return [p for p in dict.fromkeys(found) if os.path.isfile(p)]


def open_reqs(cwd):
    """(spec path, open REQ ids) of the session's linked worktree, or None when there is no spec table / worktree."""
    root = git(["rev-parse", "--show-toplevel"], cwd)
    gd, cd = git(["rev-parse", "--path-format=absolute", "--git-dir"], cwd), git(["rev-parse", "--path-format=absolute", "--git-common-dir"], cwd)
    if not root or not gd or not cd or os.path.realpath(gd) == os.path.realpath(cd):
        return None
    mod = req_status_module()
    if mod is None:
        return None
    branch = git(["rev-parse", "--abbrev-ref", "HEAD"], root) or ""
    for spec in spec_candidates(root, branch):
        try:
            with open(spec, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        if "status: shipped" in text[:400]:
            continue
        rows = mod.parse(text)
        open_ids = mod.summary(rows)["open"] if rows else []
        if open_ids:
            return spec, open_ids
    return None


def req_reason(cwd, session_id):
    """One-line reason, once per session (marker file); '' when nothing to say or already said."""
    if not session_id:
        return ""
    marker = os.path.join(STATE_DIR, f"stop-req-{session_id[:36]}")
    if os.path.exists(marker):
        return ""
    found = open_reqs(cwd)
    if not found:
        return ""
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        open(marker, "w").write(found[0])
    except OSError:
        return ""
    spec, ids = found
    return (f"stop-guard: {len(ids)} REQ not verified in {os.path.basename(spec)} ({', '.join(ids[:6])}) — "
            "finish or run verifier before declaring done (shown once).")


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    if data.get("stop_hook_active"):
        return
    if agents_live(data.get("transcript_path") or "", data.get("session_id") or ""):
        return
    cwd = data.get("cwd") or os.getcwd()
    issues = []
    paths = candidates(cwd)
    if executor_task_id() is None:  # executor session: candidates() already narrowed to its own worktree
        paths = owned(paths, cwd, data.get("session_id") or "")
    for p in paths:
        why = problem(p)
        if why and not already_reported(p):
            issues.append(f"{p}: {why}")
    req = req_reason(cwd, data.get("session_id") or "")
    if not issues and not req:
        return
    reason = ""
    if issues:
        reason = ("stop-guard: unfinished agent worktree(s):\n  " + "\n  ".join(issues[:5]) +
                  "\nFinish per core rule 1 (commit → push → PR) or refresh the task's progress.md "
                  "(## Next with path:line, ## Status), commit it, then stop.")
    print(json.dumps({"decision": "block", "reason": (reason + "\n" if reason and req else reason) + req}))


if __name__ == "__main__":
    main()
