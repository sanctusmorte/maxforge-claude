#!/usr/bin/env python3
"""PreCompact hook — keep the task's progress.md fresh and tell the compactor what to preserve.

Contract (code.claude.com/docs/en/hooks, PreCompact): exit 0 + plain stdout = instructions for the compaction
summary (stdout cap 10 000 chars; we print <= 2 000). This hook NEVER writes STATE.md or any MEMORY.md (2026-11-25:
pointer lines dirtied the main checkout and blocked main-sync for 5 010 commits).
progress.md (interface I1, <= 60 lines, overwritten): in a linked task worktree of a repo with docs/project/ →
`docs/project/tasks/<slug>/progress.md`, otherwise `~/.claude/state/<repo>/<slug>.md` (slug = branch name without its
prefix). Existing human-filled sections (Goal, Next, Dead ends, Verify) are kept; Git and Status are refreshed.
The session cwd often stays on the main checkout while the task runs in a linked worktree by absolute path: a cwd on
a base branch (dev/main/master) resolves to the worktree of that repo mentioned last in the transcript tail; none
mentioned → nothing is written and no goal is derived (2026-11-25: the checkout's last merge commit and 70 dirty
files were preserved as "the task" and `state/<repo>/dev.md` showed up as an active task).
Up to 2 more task worktrees mentioned in the tail get their progress.md refreshed too (one session, several tasks).
Durability (2026-11-26, owner: "выгружать в гит чтобы всегда была история"): an in-repo progress.md is committed alone
(`git commit --only`) on the task branch and pushed in the background when the branch has an upstream; the refreshed
files are recorded in `state/sessions/<session_id>.json` for hooks/session-restore.py, which re-injects their CONTENT
after compaction (pointer-only reminders are acted on unreliably — github.com/anthropics/claude-code/issues/43733).
Best effort and deterministic (no model call): any failure → exit 0 without output."""
import datetime
import importlib.util
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402  (hooks/_paths.py: portable roots)
import re
import subprocess
import sys
import time

STATE_DIR = os.environ.get("CLAUDE_STATE_DIR") or _paths.data_dir("state")
MAX_CHARS = 2000
MAX_FILES = 12
MAX_OTHER_TASKS = 2
SESSION_KEEP_S = 14 * 86400
CHECKPOINT_MSG = "chore(progress): checkpoint before compaction"
IN_PROGRESS_OPS = ("MERGE_HEAD", "rebase-merge", "rebase-apply", "CHERRY_PICK_HEAD", "REVERT_HEAD")
FAIL_RE = re.compile(r"(FAILED|FAIL\b|\bfailed\b|Traceback|Error:|exit code [1-9]|BAD )")
BASE_BRANCHES = ("dev", "main", "master")
TAIL_BYTES = 4 << 20  # transcripts reach tens of MB; only the tail matters
PATH_END = r"(?![A-Za-z0-9._-])"  # `wt-x` must not match inside `wt-x-2`


def git(args, cwd, timeout=6):
    try:
        r = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def git_ok(args, cwd, timeout=6):
    try:
        return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, timeout=timeout).returncode == 0
    except Exception:
        return False


def load_req_status():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools", "req-status.py")
    try:
        spec = importlib.util.spec_from_file_location("req_status", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def slug_of(branch):
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", branch.split("/", 1)[-1]).strip("-.")
    return s or "task"


def is_linked_worktree(root):
    gd = git(["rev-parse", "--path-format=absolute", "--git-dir"], root)
    cd = git(["rev-parse", "--path-format=absolute", "--git-common-dir"], root)
    return bool(gd and cd and os.path.realpath(gd) != os.path.realpath(cd))


def progress_path(root, slug):
    if is_linked_worktree(root) and os.path.isdir(os.path.join(root, "docs", "project")):
        return os.path.join(root, "docs", "project", "tasks", slug, "progress.md")
    return os.path.join(STATE_DIR, os.path.basename(root), slug + ".md")


def split_sections(text):
    out, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^##\s+(.*?)\s*$", line)
        if m:
            cur = m.group(1)
            out[cur] = []
        elif cur is not None:
            out[cur].append(line)
    return {k: "\n".join(v).strip("\n") for k, v in out.items()}


def tail_lines(path, n):
    """Last n lines of a file without reading a multi-MB transcript whole; [] when unreadable."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - TAIL_BYTES))
            return fh.read().decode("utf-8", "ignore").splitlines()[-n:]
    except Exception:
        return []


def linked_worktrees(root):
    out = git(["worktree", "list", "--porcelain"], root)
    paths = [ln[len("worktree "):] for ln in out.splitlines() if ln.startswith("worktree ")]
    return [p for p in paths if os.path.realpath(p) != os.path.realpath(root) and os.path.isdir(p)]


def mentioned_worktrees(root, transcript_path, limit):
    """Linked worktrees of `root` mentioned in the transcript tail (absolute or `~/` form), most recent first."""
    home = os.path.expanduser("~")
    forms = {}
    for p in linked_worktrees(root):
        forms[p] = p
        if p.startswith(home + os.sep):
            forms["~" + p[len(home):]] = p
    if not forms:
        return []
    rx = re.compile("(" + "|".join(map(re.escape, sorted(forms, key=len, reverse=True))) + ")" + PATH_END)
    found = []
    for line in reversed(tail_lines(transcript_path, 400)):
        for hit in reversed(list(rx.finditer(line))):
            if forms[hit.group(1)] not in found:
                found.append(forms[hit.group(1)])
        if len(found) >= limit:
            break
    return found[:limit]


def mentioned_worktree(root, transcript_path):
    """The linked worktree of `root` mentioned last in the transcript tail, else ''."""
    found = mentioned_worktrees(root, transcript_path, 1)
    return found[0] if found else ""


def other_task_roots(d, primary):
    """Other task worktrees of a base-branch session mentioned in the tail (a session juggling several tasks)."""
    root = git(["rev-parse", "--show-toplevel"], d.get("cwd") or os.getcwd())
    if not root or is_linked_worktree(root):
        return []
    found = mentioned_worktrees(root, d.get("transcript_path") or "", MAX_OTHER_TASKS + 1)
    return [p for p in found if p != primary][:MAX_OTHER_TASKS]


def task_root(d):
    """(root, base_only): the session repo, or the task worktree it works in by path. base_only = a base-branch
    checkout with no task worktree in sight — its last commit and dirty files are not the task."""
    root = git(["rev-parse", "--show-toplevel"], d.get("cwd") or os.getcwd())
    if not root or is_linked_worktree(root):
        return root, False
    if git(["rev-parse", "--abbrev-ref", "HEAD"], root) not in BASE_BRANCHES:
        return root, False
    wt = mentioned_worktree(root, d.get("transcript_path") or "")
    return (wt, False) if wt else (root, True)


def last_failure(transcript_path):
    """First failing line of the most recent tool_result that looks like a failed check, else ''."""
    lines = tail_lines(transcript_path, 300)
    found = ""
    for line in lines:
        try:
            content = (json.loads(line).get("message") or {}).get("content")
        except Exception:
            continue
        if not isinstance(content, list):
            continue
        for c in content:
            if isinstance(c, dict) and c.get("type") == "tool_result":
                rc = c.get("content")
                txt = str(rc if isinstance(rc, str) else json.dumps(rc, ensure_ascii=False))
                hit = next((ln for ln in txt.splitlines() if FAIL_RE.search(ln)), "")
                if hit:
                    found = hit.strip()[:200]
    return found


def find_spec(root, slug):
    cands = [os.path.join(root, "docs", "project", "tasks", slug, "spec.md"),
             os.path.join(root, "docs", "project", "specs", slug + ".md")]
    return next((p for p in cands if os.path.isfile(p)), "")


def open_pr(root, branch):
    try:
        r = subprocess.run(["gh", "pr", "list", "--head", branch, "--state", "open", "--json", "number,url",
                            "--limit", "1"], cwd=root, capture_output=True, text=True, timeout=6)
        rows = json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else []
    except Exception:
        rows = []
    return f"#{rows[0]['number']} {rows[0]['url']}" if rows else ""


def detect_verify(root):
    if os.path.isfile(os.path.join(root, "composer.json")):
        return "composer gate"
    if os.path.isfile(os.path.join(root, "package.json")):
        return "npm run gate"
    if os.path.isfile(os.path.join(root, "pytest.ini")) or os.path.isfile(os.path.join(root, "pyproject.toml")):
        return "pytest -q"
    return "<fill: one command that proves the task works>"


def render_progress(old, f):
    prev = (old.get("Status") or "").strip().split()[:1]
    status = prev[0] if prev and prev[0] in ("blocked", "merged") else ("pr-open" if f["pr"] else "active")
    git_lines = [f"- branch: {f['branch']}", f"- worktree: {f['root']}", f"- PR: {f['pr'] or 'none'}",
                 f"- last pushed sha: {f['pushed'] or 'unpushed'}", f"- head: {f['head']}",
                 f"- updated: {datetime.datetime.now(datetime.timezone.utc):%Y-%m-%dT%H:%MZ} (PreCompact)",
                 f"- last failing check: {f['fail'] or 'none observed'}"]
    if f["files"]:
        git_lines.append("- modified: " + ", ".join(f["files"]))

    def keep(k, default):
        return (old.get(k) or "").strip() or default

    body = [
        f"# progress — {f['slug']}", "",
        "## Goal / done-when", keep("Goal / done-when", f["goal"]), "",
        "## Git", *git_lines, "",
        "## Next", keep("Next", "- <fill: next atomic step with path:line>"), "",
        "## Dead ends", keep("Dead ends", "- none recorded"), "",
        "## Verify", keep("Verify", f["verify"]), "",
        "## Status", status, "",
    ]
    return "\n".join(body[:60]) + "\n"


def changed_files(root):
    porcelain = git(["status", "--porcelain"], root)
    files = [ln[3:].split(" -> ")[-1].strip('"') for ln in porcelain.splitlines()]
    files = [x for x in files if not x.endswith("/progress.md")]
    if files:
        return files
    base = next((b for b in ("origin/dev", "origin/main", "origin/master")
                 if git(["rev-parse", "--verify", "-q", b], root)), "")
    return git(["diff", "--name-only", f"{base}...HEAD"], root).splitlines() if base else []


def open_req_ids(spec):
    req = load_req_status()
    if not (spec and req):
        return []
    try:
        with open(spec, encoding="utf-8") as fh:
            return req.summary(req.parse(fh.read()))["open"]
    except Exception:
        return []


def gather(d):
    root, base_only = task_root(d)
    if not root:
        return None
    if base_only:
        branch = git(["rev-parse", "--abbrev-ref", "HEAD"], root) or "HEAD"
        return {"root": root, "branch": branch, "base_only": True, "fail": last_failure(d.get("transcript_path") or "")}
    return gather_root(root, d.get("transcript_path") or "")


def gather_root(root, transcript):
    """Task facts of one worktree; `transcript` = '' for a secondary task (the last failure belongs to the primary)."""
    branch = git(["rev-parse", "--abbrev-ref", "HEAD"], root) or "HEAD"
    slug = slug_of(branch if branch != "HEAD" else os.path.basename(root))
    files = changed_files(root)
    spec = find_spec(root, slug)
    subject = git(["log", "-1", "--format=%s"], root)
    return {
        "root": root, "branch": branch, "slug": slug, "files": files[:MAX_FILES], "n_files": len(files),
        "pr": open_pr(root, branch), "pushed": git(["rev-parse", "--short", "@{upstream}"], root),
        "head": git(["log", "-1", "--format=%h %s"], root)[:90], "open_reqs": open_req_ids(spec),
        "goal": (f"{subject} (spec: {os.path.relpath(spec, root)})" if spec else subject) or "<fill: goal and done-when>",
        "verify": detect_verify(root), "fail": last_failure(transcript) if transcript else "", "base_only": False,
    }


def base_only_instructions(f):
    return (f"The session cwd is the base-branch checkout {f['root']} ({f['branch']}) and no task worktree of it "
            "appears in the recent transcript, so no task state is derived (its last commit and dirty files are NOT "
            "the task). When summarising, preserve verbatim from the conversation: the task goal, worktree paths, "
            "branch/PR, test commands, open REQ ids and the last failing check "
            f"({f['fail'] or 'none observed'}).")[:MAX_CHARS]


def instructions(f, path, others):
    lines = [
        "When summarising, preserve verbatim:",
        f"- goal: {f['goal'][:160]}",
        f"- modified files ({f['n_files']}): " + (", ".join(f["files"]) or "none"),
        f"- branch/PR: {f['branch']} / {f['pr'] or 'no open PR'}",
        f"- test commands: {f['verify'][:120]}",
        f"- open REQ ids: {', '.join(f['open_reqs']) or 'none'}",
        f"- last failing check: {f['fail'] or 'none observed'}",
    ]
    if others:
        lines.append("- other task files of this session: " + ", ".join(others))
    lines.append(f"After compaction read {path} first, run its ## Verify, then continue; everything else may be summarised.")
    return "\n".join(lines)[:MAX_CHARS]


def write_progress(f):
    path = progress_path(f["root"], f["slug"])
    try:
        old = {}
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                old = split_sections(fh.read())
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(render_progress(old, f))
    except Exception:
        pass
    return path


def push_background(root, branch):
    # Only to the task's own remote branch: wt-new.sh tracks origin/dev until the first `push -u`, and pushing to the
    # upstream name landed a checkpoint straight on dev (2026-11-26).
    up = git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"], root)
    if "/" not in up or up.split("/", 1)[1] != branch or branch in BASE_BRANCHES:
        return
    remote = up.split("/", 1)[0]
    try:
        subprocess.Popen(["git", "push", "-q", remote, f"HEAD:refs/heads/{branch}"], cwd=root, start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def checkpoint(root, path, branch):
    """Commit progress.md ALONE on the task branch (other staged work stays staged), push in the background.
    Skips: file outside the repo, base/detached branch, merge/rebase/cherry-pick in progress, nothing changed."""
    if not path.startswith(root + os.sep) or branch in BASE_BRANCHES + ("HEAD",):
        return False
    if any(os.path.exists(os.path.join(root, git(["rev-parse", "--git-path", op], root) or op)) for op in IN_PROGRESS_OPS):
        return False
    rel = os.path.relpath(path, root)
    if not git_ok(["add", "--", rel], root) or git_ok(["diff", "--cached", "--quiet", "--", rel], root):
        return False
    if not git_ok(["commit", "-q", "--only", "-m", CHECKPOINT_MSG, "--", rel], root, 30):
        return False
    push_background(root, branch)
    return True


def save_task(f):
    path = write_progress(f)
    checkpoint(f["root"], path, f["branch"])
    return {"path": path, "root": f["root"], "branch": f["branch"], "head": git(["rev-parse", "--short", "HEAD"], f["root"])}


def record_session(sid, tasks):
    """state/sessions/<sid>.json → hooks/session-restore.py re-injects these files after compaction/resume."""
    sid = re.sub(r"[^A-Za-z0-9_-]", "", sid or "")
    if not sid:
        return
    d = os.path.join(STATE_DIR, "sessions")
    try:
        os.makedirs(d, exist_ok=True)
        for name in os.listdir(d):
            if time.time() - os.path.getmtime(os.path.join(d, name)) > SESSION_KEEP_S:
                os.remove(os.path.join(d, name))
        with open(os.path.join(d, sid + ".json"), "w", encoding="utf-8") as fh:
            json.dump({"at": int(time.time()), "tasks": tasks}, fh)
    except Exception:
        pass


def main():
    try:
        d = json.load(sys.stdin)
    except Exception:
        return
    if os.environ.get("CLAUDE_HANDOFF_CHILD"):
        return
    f = gather(d)
    if not f:
        return
    if f["base_only"]:
        print(base_only_instructions(f))
        return
    tasks = [save_task(f)] + [save_task(gather_root(r, "")) for r in other_task_roots(d, f["root"])]
    record_session(d.get("session_id"), tasks)
    print(instructions(f, tasks[0]["path"], [t["path"] for t in tasks[1:]]))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
