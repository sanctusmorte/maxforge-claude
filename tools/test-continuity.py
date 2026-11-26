#!/usr/bin/env python3
"""Tests for H1 continuity: precompact-handoff.py (R1), project-sync.py digest/--write (R2), req-status.py +
stop-guard REQ gate (R5). Standalone; paths relative to this repo root; exit 0 = pass."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H = os.path.join(ROOT, "hooks")
REQ = os.path.join(ROOT, "tools", "req-status.py")
fails = 0
SCRATCH = os.path.join(ROOT, "tmp")
os.makedirs(SCRATCH, exist_ok=True)
TMP = tempfile.mkdtemp(prefix="continuity-", dir=SCRATCH)
STATE_HOME = os.path.join(TMP, "state")
ENV = {**os.environ, "CLAUDE_STATE_DIR": STATE_HOME, "TMPDIR": TMP, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t", "PATH": os.environ["PATH"]}


def check(name, cond):
    global fails
    fails += 0 if cond else 1
    print(f"{'OK ' if cond else 'BAD'} {name}")


def sh(args, cwd=None, inp=None):
    return subprocess.run(args, cwd=cwd, env=ENV, input=inp, capture_output=True, text=True, timeout=60)


def digest(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


SPEC = ("# Spec\n\n## Requirements status\n| REQ | status | evidence |\n|-----|--------|----------|\n"
        "| REQ-1 | verified | test a |\n| REQ-2 | red | |\n| REQ-3 | todo | |\n\n## Contracts\nx\n")


def make_repo(name):
    repo = os.path.join(TMP, name)
    os.makedirs(os.path.join(repo, "docs/project/specs"))
    sh(["git", "init", "-q", "-b", "main", repo])
    with open(os.path.join(repo, "docs/project/STATE.md"), "w") as fh:
        fh.write("---\nlast_sync: 2026-11-20T10:00Z\nbase_branch: main\nstatus: active\n---\n\n## Now (≤3)\n- old\n\n"
                 "## Next (≤5)\n1. x\n\n## Landed since last sync (derived)\n- nothing\n")
    with open(os.path.join(repo, "docs/project/specs/feat-x.md"), "w") as fh:
        fh.write(SPEC)
    sh(["git", "add", "-A"], repo)
    sh(["git", "commit", "-qm", "init"], repo)
    wt = os.path.join(TMP, name + "-wt")
    sh(["git", "worktree", "add", "-q", "-b", "task/feat-x", wt], repo)
    return repo, wt


# ---------------------------------------------------------------- req-status (I2)
spec_path = os.path.join(TMP, "spec.md")
open(spec_path, "w").write(SPEC)
r = sh(["python3", REQ, spec_path, "--json"])
data = json.loads(r.stdout)
check("req-status: exit 1 with non-verified rows", r.returncode == 1)
check("req-status --json counts + open ids", data["counts"]["verified"] == 1 and data["open"] == ["REQ-2", "REQ-3"])
open(spec_path, "w").write(SPEC.replace("red", "verified").replace("todo", "verified"))
check("req-status: exit 0 when all verified", sh(["python3", REQ, spec_path]).returncode == 0)
open(spec_path, "w").write("# no table\n")
check("req-status: exit 2 without a table", sh(["python3", REQ, spec_path]).returncode == 2)
check("req-status: exit 2 for a missing file", sh(["python3", REQ, os.path.join(TMP, "nope.md")]).returncode == 2)

# ---------------------------------------------------------------- R1 precompact-handoff
repo, wt = make_repo("r1")
state = os.path.join(repo, "docs/project/STATE.md")
state_wt = os.path.join(wt, "docs/project/STATE.md")
mem = os.path.join(TMP, "memory")
os.makedirs(mem)
open(os.path.join(mem, "MEMORY.md"), "w").write("# memory\n")
before = (digest(state), digest(state_wt), digest(os.path.join(mem, "MEMORY.md")))
open(os.path.join(wt, "work.py"), "w").write("x = 1\n")
tr = os.path.join(TMP, "tr.jsonl")
with open(tr, "w") as fh:
    fh.write(json.dumps({"message": {"role": "user", "content": [{"type": "tool_result", "content":
             "FAILED tests/test_x.py::test_y - assert 1 == 2"}]}}) + "\n")
payload = json.dumps({"cwd": wt, "session_id": "abcdef123456", "transcript_path": tr, "hook_event_name": "PreCompact"})
r = sh(["python3", os.path.join(H, "precompact-handoff.py")], inp=payload)
check("precompact: exit 0", r.returncode == 0)
check("precompact: STATE.md byte-identical (main + worktree), MEMORY.md untouched",
      before == (digest(state), digest(state_wt), digest(os.path.join(mem, "MEMORY.md"))))
prog = os.path.join(wt, "docs/project/tasks/feat-x/progress.md")
check("precompact: progress.md written at I1 path", os.path.isfile(prog))
text = open(prog).read() if os.path.isfile(prog) else ""
check("precompact: progress.md has the 6 sections, <=60 lines",
      all(f"## {s}" in text for s in ("Goal / done-when", "Git", "Next", "Dead ends", "Verify", "Status"))
      and len(text.splitlines()) <= 60)
out = r.stdout
for label, needle in (("goal", "- goal:"), ("modified files", "work.py"), ("PR/branch", "task/feat-x"),
                      ("test commands", "- test commands:"), ("open REQ ids", "REQ-2, REQ-3"),
                      ("last failing check", "FAILED tests/test_x.py")):
    check(f"precompact stdout: {label}", needle in out)
check("precompact stdout <= 2000 chars", 0 < len(out) <= 2000)
check("precompact: no dated handoff file", not any(f.startswith("handoff-") for f in os.listdir(os.path.dirname(prog))))
# human-filled sections survive a second run
edited = text.replace("- <fill: next atomic step with path:line>", "- edit work.py:1 then run tests").replace(
    "- none recorded", "- tried X, failed")
open(prog, "w").write(edited)
sh(["python3", os.path.join(H, "precompact-handoff.py")], inp=payload)
again = open(prog).read()
check("precompact: Next/Dead ends kept on overwrite", "edit work.py:1 then run tests" in again and "tried X, failed" in again)
# base-branch checkout, no task worktree in the transcript → nothing written, no last-commit "goal"
r = sh(["python3", os.path.join(H, "precompact-handoff.py")], inp=json.dumps({"cwd": repo, "session_id": "s"}))
check("precompact: base-branch checkout without a task worktree → no state file, repo clean",
      not os.path.exists(os.path.join(STATE_HOME, "r1")) and sh(["git", "status", "--porcelain"], repo).stdout == "")
check("precompact: base-branch checkout → says no task worktree, no derived goal",
      "no task worktree" in r.stdout and "- goal:" not in r.stdout)
# session cwd stays on the main checkout while the task runs in a worktree by absolute path → that worktree
wt2 = wt + "-2"
sh(["git", "worktree", "add", "-q", "-b", "task/feat-y", wt2], repo)
open(os.path.join(repo, "junk.png"), "w").write("x")


def precompact_with_mention(path):
    trm = os.path.join(TMP, "tr-mention.jsonl")
    with open(trm, "w") as fh:
        fh.write(json.dumps({"message": {"role": "assistant", "content": [
            {"type": "tool_use", "input": {"command": f"cd {path} && make test"}}]}}) + "\n")
        fh.write(json.dumps({"message": {"role": "user", "content": "ok"}}) + "\n")
    return sh(["python3", os.path.join(H, "precompact-handoff.py")],
              inp=json.dumps({"cwd": repo, "session_id": "s", "transcript_path": trm}))


os.remove(prog)
r = precompact_with_mention(wt)
check("precompact: main checkout + worktree in transcript → that worktree's progress.md", os.path.isfile(prog))
check("precompact: main checkout + worktree in transcript → its branch, not the checkout's dirty files",
      "task/feat-x" in r.stdout and "junk.png" not in r.stdout)
r = precompact_with_mention(wt2)
check("precompact: worktree path that extends another one's → the longer (task/feat-y)",
      "task/feat-y" in r.stdout and "task/feat-x" not in r.stdout)
# checkpoint push: never onto the base branch the task branch tracks (landed on dev, 2026-11-26)
bare = os.path.join(TMP, "r1-origin.git")
sh(["git", "init", "-q", "--bare", bare])
sh(["git", "remote", "add", "origin", bare], repo)
sh(["git", "push", "-q", "origin", "main"], repo)
wtp = wt + "-push"
sh(["git", "worktree", "add", "-q", "-b", "task/feat-push", "--track", wtp, "origin/main"], repo)
main_before = sh(["git", "rev-parse", "main"], bare).stdout
open(os.path.join(wtp, "z.py"), "w").write("z = 1\n")
precompact_with_mention(wtp)
time.sleep(2)
check("precompact: task branch tracking origin/main → checkpoint committed, origin/main untouched",
      "checkpoint" in sh(["git", "log", "-1", "--format=%s"], wtp).stdout and sh(["git", "rev-parse", "main"], bare).stdout == main_before)
sh(["git", "push", "-q", "-u", "origin", "HEAD:refs/heads/task/feat-push"], wtp)
pushed_head = sh(["git", "rev-parse", "HEAD"], wtp).stdout
open(os.path.join(wtp, "z2.py"), "w").write("z = 2\n")  # changes the progress "modified" line → a new checkpoint
precompact_with_mention(wtp)
time.sleep(2)
headp = sh(["git", "rev-parse", "HEAD"], wtp).stdout
check("precompact: task branch tracking its own remote branch → checkpoint pushed there",
      headp != pushed_head and sh(["git", "rev-parse", "task/feat-push"], bare).stdout == headp)
sh(["git", "worktree", "remove", "--force", wtp], repo)
sh(["git", "remote", "remove", "origin"], repo)
sh(["git", "branch", "-q", "-D", "task/feat-push"], repo)
os.remove(os.path.join(repo, "junk.png"))
sh(["git", "worktree", "remove", "--force", wt2], repo)
open(prog, "w").write(again)  # R2 below reads the human-filled Next line

# ---------------------------------------------------------------- durability: checkpoint commit + session-restore
PC, SR = os.path.join(H, "precompact-handoff.py"), os.path.join(H, "session-restore.py")
rel_prog = os.path.relpath(prog, wt)
sh(["python3", PC], inp=payload)
check("precompact: progress.md committed ALONE on the task branch (untracked work.py stays out)",
      sh(["git", "log", "-1", "--format=%s"], wt).stdout.strip() == "chore(progress): checkpoint before compaction"
      and sh(["git", "show", "--name-only", "--format=", "HEAD"], wt).stdout.split() == [rel_prog]
      and "work.py" in sh(["git", "status", "--porcelain"], wt).stdout)
check("precompact: progress.md records updated + last failing check",
      "- updated: " in open(prog).read() and "- last failing check: FAILED tests/test_x.py" in open(prog).read())
rec = os.path.join(STATE_HOME, "sessions", "abcdef123456.json")
check("precompact: session record lists the progress file",
      os.path.isfile(rec) and json.load(open(rec))["tasks"][0]["path"] == prog)
r = sh(["python3", SR], inp=json.dumps({"session_id": "abcdef123456", "source": "compact"}))
check("session-restore: prints progress CONTENT + git status, <=6000 chars",
      "## Goal / done-when" in r.stdout and "edit work.py:1" in r.stdout and "git status -sb" in r.stdout
      and "HEAD moved" not in r.stdout and len(r.stdout) <= 6000)
check("session-restore: unknown session → silent", sh(["python3", SR], inp=json.dumps({"session_id": "nope"})).stdout == "")
sh(["git", "commit", "-q", "--allow-empty", "-m", "later"], wt)
check("session-restore: HEAD moved since the record → flagged",
      "HEAD moved" in sh(["python3", SR], inp=json.dumps({"session_id": "abcdef123456", "source": "resume"})).stdout)
wt3 = os.path.join(TMP, "r1-wt3")
sh(["git", "worktree", "add", "-q", "-b", "task/feat-z", wt3], repo)
trm = os.path.join(TMP, "tr-multi.jsonl")
with open(trm, "w") as fh:
    for p in (wt3, wt):  # wt mentioned last → primary
        fh.write(json.dumps({"message": {"role": "assistant", "content": [
            {"type": "tool_use", "input": {"command": f"cd {p} && make test"}}]}}) + "\n")
r = sh(["python3", PC], inp=json.dumps({"cwd": repo, "session_id": "multi", "transcript_path": trm}))
prog3 = os.path.join(wt3, "docs/project/tasks/feat-z/progress.md")
check("precompact: second task worktree of the session → its progress.md too, listed after the primary",
      os.path.isfile(prog3) and "task/feat-x" in r.stdout and "other task files" in r.stdout and prog3 in r.stdout
      and [t["path"] for t in json.load(open(os.path.join(STATE_HOME, "sessions", "multi.json")))["tasks"]] == [prog, prog3])
sh(["git", "worktree", "remove", "--force", wt3], repo)

# ---------------------------------------------------------------- R2 project-sync
sync = os.path.join(H, "project-sync.py")
sh(["git", "add", "-A"], wt)
sh(["git", "commit", "-qm", "progress"], wt)
clean_before = sh(["git", "status", "--porcelain"], wt).stdout
hook_in = json.dumps({"cwd": wt, "session_id": "zzzzzzzz", "hook_event_name": "SessionStart"})
r = sh(["python3", sync], cwd=wt, inp=hook_in)
ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout.strip() else ""
check("digest: git status clean after SessionStart run", sh(["git", "status", "--porcelain"], wt).stdout == clean_before == "")
check("digest: active task with first Next line + open PR count",
      "feat-x" in ctx and "edit work.py:1 then run tests" in ctx and "open PR" in ctx)
for i in range(4):
    d = os.path.join(wt, f"docs/project/tasks/t{i}")
    os.makedirs(d)
    open(os.path.join(d, "progress.md"), "w").write(f"# p\n## Next\n- step{i}\n## Status\n{'merged' if i == 0 else 'active'}\n")
r = sh(["python3", sync], cwd=wt, inp=hook_in)
ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
check("digest: <=3 tasks, merged excluded", "step0" not in ctx
      and sum(1 for ln in ctx.splitlines() if "[active]" in ln or "[pr-open]" in ln) == 3)
for i in range(4):
    shutil.rmtree(os.path.join(wt, f"docs/project/tasks/t{i}"))
r = sh(["python3", sync, "--write"], cwd=repo)
check("--write refuses in the main checkout", r.returncode != 0 and sh(["git", "status", "--porcelain"], repo).stdout == "")
r = sh(["python3", sync, "--write"], cwd=wt)
lines = open(state_wt).read().splitlines()
now = open(state_wt).read().split("## Now")[1].split("\n## ")[0]
check(f"--write: exit 0, STATE <=60 lines ({len(lines)}), output <=60 lines",
      r.returncode == 0 and len(lines) <= 60 and len(r.stdout.splitlines()) <= 60)
check("--write: ## Now <=3 bullets from progress.md", 1 <= sum(1 for l in now.splitlines() if l.startswith("- ")) <= 3
      and "feat-x" in now and "- old" not in now)
check("--write: Next section kept", "## Next (≤5)\n1. x" in open(state_wt).read())
r = sh(["python3", sync, "--check", "--strict"], cwd=wt)
check("--check --strict still runs (budgets)", r.returncode in (0, 1) and "memory budgets" in r.stdout)

# ---------------------------------------------------------------- R5 stop-guard
guard = os.path.join(H, "stop-guard.py")
repo5, wt5 = make_repo("r5")
sh(["git", "commit", "-qm", "noop", "--allow-empty"], wt5)


def stop(cwd, sid, **kw):
    r = sh(["python3", guard], inp=json.dumps({"cwd": cwd, "session_id": sid, **kw}))
    return r.stdout


o1 = stop(wt5, "sess-aaaa")
check("stop-guard: blocks once with a REQ reason", '"block"' in o1 and "REQ-2" in o1 and "REQ-3" in o1)
check("stop-guard: reason names one line for REQ", o1.count("not verified") == 1)
check("stop-guard: never twice in the same session", "not verified" not in stop(wt5, "sess-aaaa"))
check("stop-guard: another session is blocked once", "not verified" in stop(wt5, "sess-bbbb"))
check("stop-guard: stop_hook_active → silent", stop(wt5, "sess-cccc", stop_hook_active=True) == "")
check("stop-guard: main checkout (no linked worktree) → no REQ block", "not verified" not in stop(repo5, "sess-dddd"))
os.remove(os.path.join(wt5, "docs/project/specs/feat-x.md"))
check("stop-guard: no spec → no REQ block", "not verified" not in stop(wt5, "sess-eeee"))
open(os.path.join(wt5, "docs/project/specs/feat-x.md"), "w").write("# Spec without a table\n")
check("stop-guard: spec without a table → no REQ block", "not verified" not in stop(wt5, "sess-ffff"))
open(os.path.join(wt5, "docs/project/specs/feat-x.md"), "w").write(SPEC.replace("red", "verified").replace("todo", "verified"))
check("stop-guard: all verified → no REQ block", "not verified" not in stop(wt5, "sess-gggg"))

if not os.environ.get("KEEP"):
    shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failure(s)")
sys.exit(1 if fails else 0)
