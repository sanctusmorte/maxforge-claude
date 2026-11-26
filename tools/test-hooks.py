#!/usr/bin/env python3
"""Self-test for ~/.claude/hooks guard-bash.py / ctx-monitor.py / statusline.py / stop-guard.py /
project-sync.py SessionStart digest, and tools/instr-budget.py."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import time

HARNESS = os.environ.get("CLAUDE_HARNESS_DIR") or os.path.expanduser("~/.claude")   # CLAUDE_HARNESS_DIR = test a worktree
if os.environ.get("CLAUDE_HARNESS_DIR"):
    os.environ["CLAUDE_CONFIG_DIR"] = HARNESS   # rules-gate / rules-digest read rules + digests from there
H = os.path.join(HARNESS, "hooks")
HD = "\"$(cat <<'EOF'\nsummary; a | b\nEOF\n)\""
HD_GH = "\"$(cat <<'EOF'\ngh pr create --base master\nEOF\n)\""
# Hermetic fixtures: PROJ has origin/dev, SITE/PORTAL do not; a gh shim answers the `branches/dev` API lookup offline.
# Not under /tmp, a worktree or a cache dir: guard-bash treats those as safe scratch (rm / reset allowed there).
_FX = tempfile.mkdtemp(prefix=".hooks-fx-", dir=os.path.expanduser("~"))
import atexit
atexit.register(shutil.rmtree, _FX, ignore_errors=True)
def _mkrepo(name, dev):
    d = os.path.join(_FX, name)
    os.makedirs(d)
    for a in (["init", "-q"], ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "i"]):
        subprocess.run(["git", *a], cwd=d, check=True)
    if dev:
        subprocess.run(["git", "update-ref", "refs/remotes/origin/dev", "HEAD"], cwd=d, check=True)
    return d
PROJ, SITE, PORTAL = _mkrepo("demo-app", True), _mkrepo("site-io", False), _mkrepo("portal-spa", False)
UID_TMP = f"/tmp/claude-{os.getuid()}"
GH_SHIM = os.path.join(_FX, "bin")
os.makedirs(GH_SHIM)
open(os.path.join(GH_SHIM, "gh"), "w").write('#!/bin/sh\ncase "$*" in *repos/acme-org/demo-app/branches/dev*) exit 0;; *) exit 1;; esac\n')
os.chmod(os.path.join(GH_SHIM, "gh"), 0o755)
CASES = [  # (command, cwd, expect_deny)
    ("git push origin master", PROJ, True),
    ("git push -u origin feat/x", PROJ, False),
    ("git push --force origin feat/x", PROJ, False),
    ("git push --force origin dev", PROJ, True),
    ("git push -f", PROJ, True),
    ("gh pr create --base master --title x", PROJ, True),
    ("gh pr create --base master --head dev --title release", PROJ, False),
    ("gh pr create --base dev --title x", PROJ, False),
    ("git commit " + "-n -m x", PROJ, True),
    ("grep -n foo file && git commit -m x", PROJ, False),
    ("php artisan migrate:fresh --force", PROJ, True),
    ("DB_DATABASE=app_testing_x php artisan migrate:fresh", PROJ, False),
    ("rm -rf " + PROJ + "/storage/framework/cache", PROJ, False),
    ("rm -rf node_modules && npm ci", PROJ, False),
    ("rm -rf " + PROJ + "/app", PROJ, True),
    ("git reset --hard HEAD~1", PROJ, True),
    ("git reset --hard origin/dev", UID_TMP + "/wt-x", False),
    ("ssh root@1.2.3.4 'php artisan migrate:fresh --force'", PROJ, True),
    ("CLAUDE_GUARD_OFF=1 git push origin master", PROJ, False),
    # effective cwd: the segment runs after `cd` into a repo without dev → allow even if session cwd has dev
    ("cd " + SITE + " && gh pr create --base main --title x", PROJ, False),
    ("cd " + PORTAL + " && gh pr create --base master --title x", PROJ, False),
    ("cd " + UID_TMP + "/wt-demo-app-x && gh pr create --base master --title x", PROJ, True),
    ("gh pr create --repo acme-org/site-io --base main --title x", PROJ, False),
    ("gh pr create --repo acme-org/demo-app --base master --title x", PROJ, True),
    ("(cd " + PORTAL + " && gh pr create --base master --title x)", PROJ, False),
    ("pushd " + SITE + " && gh pr create --base main --title x", PROJ, False),
    ("(cd " + PROJ + " && gh pr create --base master --title x)", PROJ, True),
    # review 2 (2026-09-26): shell-aware parsing — short flags, late flags after heredoc bodies, text is not a command
    ("gh pr create -B master -t x -b y", PROJ, True),
    ("gh pr create --title x --body " + HD + " --base master", PROJ, True),
    ("gh pr edit 12 --base master", PROJ, True),
    ("cat > notes.md <<'EOF'\ngh pr create --base master\nEOF", PROJ, False),
    ("python3 -c \"print('gh pr create --base master')\"", PROJ, False),
    ("git commit -m " + HD_GH, PROJ, False),
    ("cat > /tmp/b.md <<'EOF'\nx\nEOF\ncd " + SITE + " && gh pr create --base main --title x", PROJ, False),
]


def run(script, payload):
    env = {**os.environ, "PATH": GH_SHIM + os.pathsep + os.environ.get("PATH", "")} if script == "guard-bash.py" else None
    r = subprocess.run(["python3", os.path.join(H, script)], input=json.dumps(payload), capture_output=True, text=True, timeout=30, env=env)
    return r.stdout.strip()


fails = 0
for cmd, cwd, expect in CASES:
    out = run("guard-bash.py", {"cwd": cwd, "tool_input": {"command": cmd}})
    denied = '"deny"' in out
    ok = denied == expect
    fails += 0 if ok else 1
    reason = json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"][:60] if denied else "allow"
    print(f"{'OK ' if ok else 'BAD'} {cmd[:60]:<60} → {reason}")

# --- forge-moved gate: driven by the private overlay; synthetic names, absent overlay = silent
_ov = os.path.join(_FX, "ov-on")
os.makedirs(_ov)
json.dump({"repos": ["widget"], "github_org": "acme-org", "forge_host": "git.example.test", "forge_org": "acme",
           "forge_name": "Forge", "moved_on": "2026-01-01"}, open(os.path.join(_ov, "forge-moved.json"), "w"))
_off = os.path.join(_FX, "ov-off")
os.makedirs(_off)
for _cmd, _ov_dir, _expect in [
    ("gh pr create -R acme-org/widget --base dev --title x", _ov, True),
    ("git push https://github.com/acme-org/widget.git dev", _ov, True),
    ("gh api repos/acme-org/widget/issues -f title=x", _ov, True),
    ("gh pr create -R acme-org/other --base dev --title x", _ov, False),
    ("gh repo view acme-org/widget", _ov, False),
    ("gh pr create -R acme-org/widget --base dev --title x", _off, False),
]:
    _env = {**os.environ, "CLAUDE_PRIVATE_DIR": _ov_dir, "PATH": GH_SHIM + os.pathsep + os.environ.get("PATH", "")}
    _r = subprocess.run(["python3", os.path.join(H, "guard-bash.py")], input=json.dumps({"cwd": PROJ, "tool_input": {"command": _cmd}}),
                        capture_output=True, text=True, timeout=30, env=_env)
    _ok = ('"deny"' in _r.stdout) == _expect
    fails += 0 if _ok else 1
    print(f"{'OK ' if _ok else 'BAD'} forge-moved: {_cmd[:58]} [{'overlay' if _ov_dir == _ov else 'no overlay'}]")

# --- design gate (guard-bash): fixture repo with origin/dev and a feature branch touching a .vue file ---
import shutil
import tempfile
fx = tempfile.mkdtemp(prefix="dg-", dir="/tmp")
def g(*a):
    subprocess.run(["git", *a], cwd=fx, check=True, capture_output=True)
g("init", "-q", "-b", "dev"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
open(os.path.join(fx, "a.php"), "w").write("<?php\n"); g("add", "."); g("commit", "-qm", "base")
g("update-ref", "refs/remotes/origin/dev", "HEAD"); g("checkout", "-qb", "feat")
os.makedirs(os.path.join(fx, "src"), exist_ok=True)
open(os.path.join(fx, "src", "X.vue"), "w").write("<template/>\n"); g("add", "."); g("commit", "-qm", "ui")
sc_dir = os.path.join(fx, "artifacts", "ui-qa", "x"); os.makedirs(sc_dir)
sc = os.path.join(sc_dir, "scorecard.md")
def gate(cmd, scorecard=None, age=0):
    if os.path.exists(sc):
        os.remove(sc)
    if scorecard:
        open(sc, "w").write(scorecard)
        t = time.time() - age
        os.utime(sc, (t, t))
    return '"deny"' in run("guard-bash.py", {"cwd": fx, "tool_input": {"command": cmd}})
body_file = os.path.join(fx, "body.md"); open(body_file, "w").write("x\ndesign-panel: n/a — copy only\n")
DG = [  # (label, command, scorecard, age_s, expect_deny)
    ("ui diff, no scorecard", "gh pr create --base dev --title x --body y", None, 0, True),
    ("ui diff, PASS fresh", "gh pr create --base dev --title x --body y",
     "# S\nVerdict: PASS\nInteraction: n/a — fixture screen without controls\nGeometry: n/a — fixture without rendered UI\n", 0, False),
    ("ui diff, PASS fresh, no dead-clicks", "gh pr create --base dev --title x --body y", "# S\nVerdict: PASS\n", 0, True),
    ("ui diff, FIX", "gh pr create --base dev --title x --body y", "# S\nVerdict: FIX\n", 0, True),
    ("ui diff, PASS stale", "gh pr create --base dev --title x --body y", "# S\nVerdict: PASS\n", 86400 * 30, True),
    ("n/a in --body", "gh pr create --base dev --title x --body 'design-panel: n/a — text only'", None, 0, False),
    ("n/a in --body-file", f"gh pr create --base dev --title x --body-file {body_file}", None, 0, False),
    ("draft", "gh pr create --draft --base dev --title x --body y", None, 0, False),
    ("subtask base", "gh pr create --base task/foo --title x --body y", None, 0, False),
    ("default base (origin/dev)", "gh pr create --title x --body y", None, 0, True),
    ("gh pr ready (no GitHub → fail open)", "gh pr ready 12", None, 0, False),
    ("-B task/foo short flag", "gh pr create -B task/foo -t x -b y", None, 0, False),
    ("-F body file with n/a", f"gh pr create -B dev -t x -F {body_file}", None, 0, False),
    ("-H dev release", "gh pr create -B master -H dev -t x -b y", None, 0, False),
    ("title contains -d", "gh pr create --base dev --title 'fix -d flag' --body y", None, 0, True),
    ("--draft=false", "gh pr create --draft=false --base dev --title x --body y", None, 0, True),
    ("template verdict line", "gh pr create --base dev --title x --body y", "# S\nVerdict: PASS | FIX | REDESIGN\n", 0, True),
    ("heredoc body, n/a inside", "gh pr create --base dev --title x --body \"$(cat <<'EOF'\nsummary\ndesign-panel: n/a — docs\nEOF\n)\"", None, 0, False),
    ("heredoc body, no n/a", "gh pr create --base dev --title x --body \"$(cat <<'EOF'\nsummary\nEOF\n)\"", None, 0, True),
    ("--head other branch from dev checkout", "gh pr create --base dev --head feat --title x --body y", None, 0, True),
    ("heredoc body, then --base task/foo", "gh pr create --title x --body " + HD + " --base task/foo", None, 0, False),
    ("heredoc body, then --draft", "gh pr create --base dev --title x --body " + HD + " --draft", None, 0, False),
    ("body with ; and |, then --base task/foo", "gh pr create --title x --body 'a; b | c' --base task/foo", None, 0, False),
    ("gh pr create only inside heredoc text", "cat > notes.md <<'EOF'\ngh pr create --base dev\nEOF", None, 0, False),
    ("attached short flag -Btask/foo", "gh pr create -Btask/foo -t x -b y", None, 0, False),
    ("--dry-run", "gh pr create --dry-run --base dev --title x --body y", None, 0, False),
    ("unresolvable --head → fail open", "gh pr create --base dev --head nope --title x --body y", None, 0, False),
    ("subshell (cd fx && … --base dev)", f"(cd {fx} && gh pr create --base dev --title x --body y)", None, 0, True),
    ("guard off", "CLAUDE_GUARD_OFF=1 gh pr create --base dev --title x", None, 0, False),
]
for label, cmd, card, age, expect in DG:
    denied = gate(cmd, card, age)
    ok = denied == expect
    fails += 0 if ok else 1
    print(f"{'OK ' if ok else 'BAD'} design gate: {label:<48} → {'deny' if denied else 'allow'}")
g("checkout", "-q", "dev"); g("checkout", "-qb", "feat-php")
open(os.path.join(fx, "b.php"), "w").write("<?php\n"); g("add", "b.php"); g("commit", "-qm", "php")
denied = gate("gh pr create --base dev --title x --body y")
fails += 0 if not denied else 1
print(f"{'OK ' if not denied else 'BAD'} design gate: {'php-only diff':<48} → {'deny' if denied else 'allow'}")
g("checkout", "-q", "dev")
denied = gate("gh pr create --base dev --head feat --title x --body y")
fails += 0 if denied else 1
print(f"{'OK ' if denied else 'BAD'} design gate: {'--head feat run from dev checkout':<48} → {'deny' if denied else 'allow'}")
g("remote", "add", "origin", "https://example.invalid/me/x.git"); g("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/dev")
g("checkout", "-q", "feat")
denied = gate("gh pr create --title x --body y")
fails += 0 if denied else 1
print(f"{'OK ' if denied else 'BAD'} design gate: {'default base from origin/HEAD':<48} → {'deny' if denied else 'allow'}")
for label, cmd_, expect in [("-R matching origin is gated", "gh pr create -R me/x --base dev --title x --body y", True),
                            ("-R other repo → not gated", "gh pr create -R other/y --base dev --title x --body y", False)]:
    denied = gate(cmd_); ok = denied == expect; fails += 0 if ok else 1
    print(f"{'OK ' if ok else 'BAD'} design gate: {label:<48} → {'deny' if denied else 'allow'}")
shutil.rmtree(fx, ignore_errors=True)

# --- rules-gate: an edit of a rule-covered file needs the rule in the agent's own transcript ---
rg_dir = tempfile.mkdtemp(prefix="rg-", dir="/tmp")
main_tp = os.path.join(rg_dir, "sess.jsonl"); open(main_tp, "w").write('{"type":"user"}\n')
sub_dir = os.path.join(rg_dir, "sess", "subagents"); os.makedirs(sub_dir)
sub_tp = os.path.join(sub_dir, "agent-a1.jsonl"); open(sub_tp, "w").write('{"type":"user"}\n')
def rgate(path, agent=None, tp=main_tp):
    d = {"session_id": "sess", "transcript_path": tp, "tool_name": "Edit", "tool_input": {"file_path": path}}
    if agent:
        d["agent_id"] = agent
    return '"deny"' in run("rules-gate.py", d)
W = "/home/user/worktrees/wt-app/"
RG = [
    ("php in worktree, rule not read", lambda: rgate(W + "app/A.php"), True),
    ("markdown file", lambda: rgate(W + "README.md"), False),
    ("~/.claude file exempt", lambda: rgate("/home/user/.claude/hooks/a.py"), False),
    ("artifacts exempt", lambda: rgate(W + "artifacts/ui-qa/x/seed.php"), False),
    ("subagent, rule not read", lambda: rgate(W + "app/A.php", "a1"), True),
    ("subagent transcript missing → fail open", lambda: rgate(W + "app/A.php", "zz"), False),
    ("main transcript missing → fail open", lambda: rgate(W + "app/A.php", tp="/nonexistent.jsonl"), False),
]
for label, fn, expect in RG:
    got = fn(); ok = got == expect; fails += 0 if ok else 1
    print(f"{'OK ' if ok else 'BAD'} rules-gate: {label:<46} → {'deny' if got else 'allow'}")
open(sub_tp, "a").write('{"message":{"content":[{"type":"tool_use","name":"Read","input":{"file_path":"/home/user/.claude/rules/laravel-php.md"}}]}}\n')
got = rgate(W + "app/A.php", "a1"); fails += 0 if not got else 1
print(f"{'OK ' if not got else 'BAD'} rules-gate: {'subagent after Read of the rule':<46} → {'deny' if got else 'allow'}")
got = rgate(W + "resources/js/pages/a.vue", "a1"); fails += 0 if got else 1
print(f"{'OK ' if got else 'BAD'} rules-gate: {'vue needs vue-ts + design + ui-eng rules':<46} → {'deny' if got else 'allow'}")
open(main_tp, "a").write('{"attachment":{"type":"nested_memory","path":"/home/user/.claude/rules/laravel-php.md"}}\n')
got = rgate(W + "app/A.php"); fails += 0 if not got else 1
print(f"{'OK ' if not got else 'BAD'} rules-gate: {'main session, rule auto-loaded':<46} → {'deny' if got else 'allow'}")
shutil.rmtree(rg_dir, ignore_errors=True)

sid = "testsess"
json.dump({"used": 52, "ts": time.time()}, open(f"/tmp/claude-ctx-{sid}.json", "w"))
try:
    os.remove(f"/tmp/claude-ctx-{sid}.band")
except OSError:
    pass
o1 = run("ctx-monitor.py", {"session_id": sid})
o2 = run("ctx-monitor.py", {"session_id": sid})
print("ctx-monitor first:", ("REMIND" if o1 else "silent"), "| second (same band):", ("REMIND" if o2 else "silent"))
print("statusline:", run("statusline.py", {"session_id": sid, "model": {"display_name": "Fable 5.1"},
                                          "workspace": {"current_dir": PROJ},
                                          "context_window": {"used_percentage": 47, "remaining_percentage": 53}}))
print("stop-guard:", run("stop-guard.py", {"cwd": PROJ, "stop_hook_active": False})[:100] or "silent")
# --- project-sync SessionStart digest (≤ ~600 tokens: frontmatter essentials + ## Now headlines + handoff list)
import importlib.util
import shutil
import tempfile


def check(name, cond):
    global fails
    fails += 0 if cond else 1
    print(f"{'OK ' if cond else 'BAD'} {name}")


# --- stop-guard ownership: only worktrees whose owner marker (<git-dir>/claude-owner, written by wt-new.sh) equals the
# stopping session's session_id, or that hold the session's cwd, may block. Fixtures live under /tmp/claude-<uid>/wt-*
# (one of the guard's scan roots); TMPDIR per call keeps the 24 h "already reported" markers out of the way.
def sh(args, cwd=None, env=None):
    return subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=60)


def stop_guard(payload):
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CODE_SESSION_ID")}
    env["TMPDIR"] = tempfile.mkdtemp(dir=SG_TMP)
    r = subprocess.run(["python3", os.path.join(H, "stop-guard.py")], input=json.dumps(payload), capture_output=True,
                       text=True, timeout=30, env=env)
    return r.stdout.strip()


SG_TMP = tempfile.mkdtemp(prefix="stopguard-test-")
SG_ROOT = f"/tmp/claude-{os.getuid()}"
SG_TAG = f"sgtest{os.getpid()}"
os.makedirs(SG_ROOT, exist_ok=True)
origin = os.path.join(SG_TMP, "origin.git")
seed = os.path.join(SG_TMP, "seed")
sh(["git", "init", "-q", "--bare", "-b", "dev", origin])
sh(["git", "clone", "-q", origin, seed])
sh(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "init"], cwd=seed)
sh(["git", "push", "-q", "origin", "HEAD:dev"], cwd=seed)
sh(["git", "fetch", "-q", "origin"], cwd=seed)
sg_wts = {}
for kind in ("nomark", "other", "own"):
    p = os.path.join(SG_ROOT, f"wt-{SG_TAG}-{kind}")
    sh(["git", "worktree", "add", "-q", "-b", f"t/{SG_TAG}-{kind}", p, "origin/dev"], cwd=seed)
    open(os.path.join(p, "dirty.txt"), "w").write("x")
    os.utime(os.path.join(p, "dirty.txt"), (time.time() - 3600,) * 2)  # abandoned an hour ago (ACTIVE_SEC = 15 min)
    sg_wts[kind] = p
gd = lambda p: sh(["git", "rev-parse", "--absolute-git-dir"], cwd=p).stdout.strip()
open(os.path.join(gd(sg_wts["other"]), "claude-owner"), "w").write("sess-OTHER\n")
open(os.path.join(gd(sg_wts["own"]), "claude-owner"), "w").write("sess-ME\n")
transcript = os.path.join(SG_TMP, "sess-ME.jsonl")  # mentions the foreign worktrees (the old heuristic's false trigger)
open(transcript, "w").write(json.dumps({"cmd": f"git -C {sg_wts['nomark']} status; ls {sg_wts['other']}"}) + "\n")
base = {"session_id": "sess-ME", "transcript_path": transcript, "cwd": PROJ,
        "stop_hook_active": False}
out = stop_guard(base)
check("stop-guard: blocks on own-marker dirty worktree", '"block"' in out and sg_wts["own"] in out)
check("stop-guard: unmarked dirty worktree mentioned in transcript → not blocking", sg_wts["nomark"] not in out)
check("stop-guard: another session's marker → not blocking", sg_wts["other"] not in out)
out = stop_guard(dict(base, session_id="sess-THIRD", transcript_path=""))
check("stop-guard: session owning nothing → silent", out == "")
out = stop_guard(dict(base, session_id="sess-THIRD", cwd=sg_wts["nomark"]))
check("stop-guard: cwd inside an unmarked dirty worktree (EnterWorktree) → blocks",
      '"block"' in out and sg_wts["nomark"] in out and sg_wts["own"] not in out)
out = stop_guard(dict(base, session_id="sess-THIRD", cwd=sg_wts["other"]))
check("stop-guard: cwd inside another session's marked worktree → not blocking", out == "")
os.utime(os.path.join(sg_wts["own"], "dirty.txt"))  # a live agent just wrote there
check("stop-guard: own dirty worktree touched <15 min ago (agent still writing) → not blocking",
      sg_wts["own"] not in stop_guard(base))
os.utime(os.path.join(sg_wts["own"], "dirty.txt"), (time.time() - 3600,) * 2)
sub_dir = os.path.join(SG_TMP, "sess-ME", "subagents"); os.makedirs(sub_dir, exist_ok=True)
open(os.path.join(sub_dir, "agent-x.jsonl"), "w").write("{}\n")  # a background worker of this session is live
check("stop-guard: live subagent transcript (<10 min) → not blocking", sg_wts["own"] not in stop_guard(base))
os.utime(os.path.join(sub_dir, "agent-x.jsonl"), (time.time() - 3600,) * 2)
check("stop-guard: stale subagent transcript → blocks again", sg_wts["own"] in stop_guard(base))
check("stop-guard: stop_hook_active → silent", stop_guard(dict(base, stop_hook_active=True)) == "")
# wt-new.sh records the owner at creation, inside the git dir (never shows in `git status`)
wt_env = dict(os.environ, CLAUDE_CODE_SESSION_ID="sess-WTNEW", WORKTREES_DIR=SG_ROOT)
r = sh([os.path.join(HARNESS, "tools", "wt-new.sh"), seed, f"{SG_TAG}-new", "--no-deps", "--no-db"], env=wt_env)
wt_new = os.path.join(SG_ROOT, f"wt-seed-{SG_TAG}-new")
marker = os.path.join(gd(wt_new), "claude-owner") if os.path.isdir(wt_new) else ""
check(f"wt-new: exit 0 (rc={r.returncode} {r.stderr.strip()[:80]})", r.returncode == 0)
check("wt-new: owner marker = CLAUDE_CODE_SESSION_ID",
      bool(marker) and os.path.exists(marker) and open(marker).read().strip() == "sess-WTNEW")
check("wt-new: marker invisible to git status", os.path.isdir(wt_new) and sh(["git", "status", "--porcelain"], cwd=wt_new).stdout == "")
if os.path.isdir(wt_new):
    open(os.path.join(wt_new, "dirty.txt"), "w").write("x")
    os.utime(os.path.join(wt_new, "dirty.txt"), (time.time() - 3600,) * 2)
out = stop_guard(dict(base, session_id="sess-WTNEW", transcript_path=""))
check("stop-guard + wt-new: the creating session is blocked on its dirty worktree", '"block"' in out and wt_new in out)
for p in list(sg_wts.values()) + [wt_new]:
    sh(["git", "worktree", "remove", "--force", p], cwd=seed)
shutil.rmtree(SG_TMP, ignore_errors=True)

spec = importlib.util.spec_from_file_location("project_sync", os.path.join(H, "project-sync.py"))
ps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ps)


with tempfile.TemporaryDirectory() as repo:
    os.makedirs(os.path.join(repo, "docs/project/tasks"))
    now_items = "".join(
        f"- **Item {i} headline.** " + "h" * 200 + f"\n  detail line {i} that must stay in the file only " + "x" * 300 + "\n"
        for i in range(8))
    state = ("---\nlast_sync: 2026-09-15T09:45Z\nlast_sync_sha: fd55ff0edc3a\nbase_branch: dev\n"
             "deployed: { dev: fd55ff0, prod: d002b71 }\nstatus: active\nnotes: drop-me\n---\n<!-- comment -->\n\n"
             "## Now (≤3)\n- ~~**Resolved item.**~~\n  old detail\n" + now_items +
             "\n## Next\n- next thing that is not in the digest\n")
    sp = os.path.join(repo, "docs/project/STATE.md")
    open(sp, "w").write(state)
    for i in range(5):
        open(os.path.join(repo, f"docs/project/tasks/handoff-2026-09-24-other{i}.md"), "w").write(f"# Handoff {i}\nbody\n")
    snap = {"state_path": sp, "text": state, "base": "dev", "base_sha": "abcdef1234", "stale": "",
            "commits": [f"c{i} commit subject " + "y" * 60 for i in range(10)], "behind": 40,
            "merged": [{"number": 100 + i, "title": "t" * 50, "mergedAt": "2026-09-24"} for i in range(6)],
            "open": [{"number": 200 + i, "title": "o" * 50, "baseRefName": "dev"} for i in range(6)],
            "runs": [{"name": "CI", "conclusion": "failure", "headSha": "abcdef1"}], "deployed": {}}
    out = ps.render(snap, sid="nosuchsession", hook=True)
    check("digest: ≤ HOOK_MAX_TOKENS (%d tok, %d chars)" % (ps.tokens(out), len(out)), ps.tokens(out) <= ps.HOOK_MAX_TOKENS)
    check("digest: frontmatter essentials kept", "last_sync 2026-09-15T09:45Z" in out and "prod: d002b71" in out)
    check("digest: non-essential frontmatter dropped", "drop-me" not in out and "last_sync_sha" not in out)
    check("digest: Now headlines only", "Item 0 headline" in out and "detail line" not in out)
    check("digest: resolved ~~items~~ dropped", "Resolved item" not in out)
    check("digest: Now capped with a pointer to the file", "Item 7" not in out and "more in docs/project/STATE.md" in out)
    check("digest: other sections stay in the file", "next thing" not in out)
    check("digest: handoff list kept (3)", out.count("handoff-2026-09-24-other") == 3)
    check("digest: CI failure still surfaced", "CI dev: CI failure" in out)
    full = ps.render(snap, head_lines=60)
    check("--print keeps the full STATE", "detail line 3" in full and "next thing" in full)

# --- instruction size budget (tools/instr-budget.py)
IB = os.path.join(HARNESS, "tools", "instr-budget.py")


def budget(files):
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "rules"))
        for name, body in files.items():
            open(os.path.join(d, name), "w").write(body)
        r = subprocess.run(["python3", IB, "--root", d], capture_output=True, text=True, timeout=30)
        return r.returncode, r.stdout


scoped = "---\npaths:\n  - \"**/*.php\"\n---\n"
rc, out = budget({"CLAUDE.md": "a" * 4000, "rules/x.md": "b" * 4000, "rules/y.md": scoped + "c" * 15000})
check("instr-budget: within budget → exit 0", rc == 0 and "always-loaded" in out)
rc, out = budget({"CLAUDE.md": "a" * 20000, "rules/x.md": "b" * 11000})
check("instr-budget: always-loaded > 7.5k tok → exit 1", rc == 1 and "FAIL always-loaded" in out)
rc, out = budget({"CLAUDE.md": "a" * 100, "rules/y.md": scoped + "c" * 17000})
check("instr-budget: path-scoped rule > 4k tok → exit 1", rc == 1 and "FAIL rules/y.md" in out)
rc, out = budget({"CLAUDE.md": "a" * 100, "rules/z.md": "---\ndescription: no paths\n---\n" + "d" * 31000})
check("instr-budget: frontmatter without paths counts as always-loaded", rc == 1 and "FAIL always-loaded" in out)

# --- per-task token budget (ctx-monitor.py --budget + PostToolUse reminder every 10 %, statusline part)
CM = os.path.join(H, "ctx-monitor.py")


def turn(mid, cr, fresh=1000):
    u = {"input_tokens": fresh, "cache_creation_input_tokens": 0, "cache_read_input_tokens": cr, "output_tokens": 0}
    return json.dumps({"type": "assistant", "message": {"id": mid, "model": "claude-opus-5-5", "usage": u}}) + "\n"


def set_budget(sid, limit, tp=None):
    args = ["python3", CM, "--budget", limit, "--session", sid] + (["--transcript", tp] if tp else [])
    return subprocess.run(args, capture_output=True, text=True, timeout=30)


with tempfile.TemporaryDirectory() as proj:
    bsid = "budgettest-%d" % os.getpid()
    tp = os.path.join(proj, bsid + ".jsonl")
    os.makedirs(os.path.join(proj, bsid, "subagents"))
    sub = os.path.join(proj, bsid, "subagents", "agent-x.jsonl")
    # main: m1 written twice (one record per content block) → counted once; 9k + 1k fresh = 10k per turn
    open(tp, "w").write(turn("m1", 9000) + turn("m1", 9000) + turn("m2", 9000))
    open(sub, "w").write(turn("s1", 9000))
    for f in (f"/tmp/claude-budget-{bsid}.json", f"/tmp/claude-ctx-{bsid}.json"):
        try:
            os.remove(f)
        except OSError:
            pass
    hook = {"session_id": bsid, "transcript_path": tp, "cwd": proj}
    check("budget: no budget set → silent", run("ctx-monitor.py", hook) == "")
    r = set_budget(bsid, "300k", tp)
    check("budget: --budget 300k → exit 0 + status line", r.returncode == 0 and "10%" in r.stdout)
    st = json.load(open(f"/tmp/claude-budget-{bsid}.json"))
    check("budget: dedupe by message.id incl. subagents (30k)", st.get("limit") == 300000 and st.get("used") == 30000)
    check("budget: set inside band 1 → no immediate reminder", run("ctx-monitor.py", hook) == "")
    open(sub, "a").write(turn("s2", 29000) + turn("s2", 29000))            # +30k → 60k = 20 %
    out = run("ctx-monitor.py", {**hook, "agent_id": "ax", "agent_type": "general-purpose"})
    check("budget: subagent hook call → silent, band not consumed", out == "")
    out = run("ctx-monitor.py", hook)
    ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else ""
    check("budget: 20 % → one line with fresh / cache-read split", "budget 20%" in ctx and "cache-read" in ctx
          and ctx.count("\n") == 0)
    check("budget: same band → silent", run("ctx-monitor.py", hook) == "")
    print("statusline budget:", run("statusline.py", {"session_id": bsid, "model": {"display_name": "M"},
                                                       "workspace": {"current_dir": proj}}))
    check("statusline: shows budget %", "budget 20%" in run("statusline.py", {"session_id": bsid, "model": {},
                                                                              "workspace": {"current_dir": proj}}))
    open(tp, "a").write("".join(turn(f"m{i}", 29000) for i in range(3, 11)))  # +240k → 300k = 100 %
    out = run("ctx-monitor.py", hook)
    ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else ""
    check("budget: 100 % → exhausted: finish atomic step, handoff, ask owner to extend",
          "exhausted" in ctx and "atomic step" in ctx and "handoff" in ctx and "extend" in ctx)
    open(tp, "a").write('{"type": "assistant", "message": {"id": "partial", "usa')   # half-written line
    run("ctx-monitor.py", hook)
    open(tp, "a").write('ge": {"input_tokens": 5000}}}\n')
    run("ctx-monitor.py", hook)
    check("budget: half-written tail line counted once when complete",
          json.load(open(f"/tmp/claude-budget-{bsid}.json")).get("used") == 305000)
    r = set_budget(bsid, "off")
    check("budget: --budget off removes the state", r.returncode == 0 and not os.path.exists(f"/tmp/claude-budget-{bsid}.json"))
    check("budget: bad value → exit 2", set_budget(bsid, "lots").returncode == 2)

# --- dump-nudge.py (PreToolUse Bash): no cat/sed -n/head/tail/less dumps of a >150-line file inside a git worktree
# fixture outside any git checkout ($TMPDIR may sit inside a worktree, where `plain` would count as tracked)
with tempfile.TemporaryDirectory(dir="/dev/shm" if os.path.isdir("/dev/shm") else None) as dn:
    repo, plain = os.path.join(dn, "repo"), os.path.join(dn, "plain")
    os.makedirs(os.path.join(repo, "app")); os.makedirs(plain)
    sh(["git", "init", "-q", repo])
    for rel, n in (("app/Big.php", 400), ("app/Small.php", 150), ("storage.log", 400)):
        open(os.path.join(repo, rel), "w").write("".join(f"line {i}\n" for i in range(n)))
    open(os.path.join(plain, "big.txt"), "w").write("x\n" * 400)
    big = os.path.join(repo, "app/Big.php")
    dump_cases = [  # (command, cwd, expect_deny)
        ("cat app/Big.php", repo, True),
        ("sed -n '1,400p' app/Big.php", repo, True),
        ("sed -n '100,$p' app/Big.php", repo, True),
        ("sed -n '5p;300,500p' app/Big.php", repo, True),
        ("head -n 400 app/Big.php", repo, True),
        ("tail -n +5 app/Big.php", repo, True),
        ("head -c 50000 app/Big.php", repo, True),
        ("less app/Big.php", repo, True),
        (f"cat {big}", "/", True),
        # bounded slices (≤ MAX_LINES lines) are not dumps — spend audit 2026-10-09: 654 of 826 denials were these
        ("head -n 80 app/Big.php", repo, False),
        ("tail -100 app/Big.php", repo, False),
        ("head app/Big.php", repo, False),
        (f"cd {repo} && sed -n 20,60p app/Big.php", "/", False),
        ("sed -n '100,249p' app/Big.php", repo, False),
        ("sed -n '5p;10,20p' app/Big.php", repo, False),
        ("sed -n -e '1,40p' app/Big.php", repo, False),
        ("cat app/Small.php app/Big.php", repo, True),
        ("cat app/Big.php | grep -n foo", repo, False),
        ("cat app/Big.php | wc -l", repo, False),
        ("sed -n '/function/p' app/Big.php", repo, False),
        ("sed -i 's/a/b/' app/Big.php", repo, False),
        ("cat app/Small.php", repo, False),
        ("tail -n 50 storage.log", repo, False),
        ("cat storage.log", repo, False),
        (f"cat {plain}/big.txt", repo, False),
        ("cat > app/New.php <<'EOF'\nx\nEOF", repo, False),
        ("cat app/Big.php > /tmp/copy.php", repo, False),
        ("grep -n foo app/Big.php", repo, False),
        ("git status", repo, False),
    ]
    for cmd, cwd, expect in dump_cases:
        out = run("dump-nudge.py", {"cwd": cwd, "tool_input": {"command": cmd}})
        denied = '"deny"' in out
        reason = json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"] if denied else ""
        check(f"dump-nudge: {cmd.splitlines()[0][:50]:<50} → {'deny' if expect else 'allow'}",
              denied == expect and (not denied or ("Read" in reason and "\n" not in reason)))

# --- C6 STATE budget gate: project-sync.py --check --strict fails on STATE > 60 lines or ## Now > 3 bullets
PS = os.path.join(H, "project-sync.py")


def strict_check(state_text):
    with tempfile.TemporaryDirectory() as d:
        sh(["git", "init", "-q", d])
        os.makedirs(os.path.join(d, "docs/project"))
        open(os.path.join(d, "docs/project/STATE.md"), "w").write(state_text)
        r = subprocess.run(["python3", PS, "--check", "--strict"], cwd=d, capture_output=True, text=True, timeout=60)
        return r.returncode, r.stdout


fm = "---\nlast_sync: 2026-09-24T09:00Z\n---\n"
rc, out = strict_check(fm + "## Now\n- a\n- b\n\n## Next\n- c\n")
check(f"project-sync --check --strict: small STATE → exit 0 (rc={rc})", rc == 0)
rc, out = strict_check(fm + "## Now\n- a\n" + "filler\n" * 70)
check("project-sync --check --strict: STATE > 60 lines → exit 1", rc == 1 and "lines > 60" in out)
rc, out = strict_check(fm + "## Now\n- a\n- b\n- c\n- d\n")
check("project-sync --check --strict: ## Now > 3 bullets → exit 1", rc == 1 and "## Now has 4 bullets > 3" in out)

# --- token-guard: context fence + idle waits (subagents), big reads + rewrite-by-Write (all sessions)
TG_HO = tempfile.mkdtemp(prefix="tg-handoffs-")   # fence skeletons never land in the real ~/.claude/handoffs


def tg_out(payload, env=None):
    r = subprocess.run(["python3", os.path.join(H, "token-guard.py")], input=json.dumps(payload), capture_output=True,
                       text=True, timeout=30, env={**os.environ, "CLAUDE_TOKEN_GUARD_LOG": os.devnull,
                                                   "CLAUDE_HANDOFF_DIR": TG_HO, **(env or {})})
    return r.stdout


def tg(payload, env=None):
    return '"deny"' in tg_out(payload, env)


with tempfile.TemporaryDirectory() as td:
    sid = "sess0001-test"
    main_tp = os.path.join(td, f"{sid}.jsonl")
    open(main_tp, "w").write("")
    sub = os.path.join(td, sid, "subagents")
    os.makedirs(sub)

    def agent(aid, ctx):
        rec = {"type": "assistant", "message": {"id": "m1", "usage": {
            "input_tokens": 1, "cache_creation_input_tokens": 1000, "cache_read_input_tokens": ctx - 1001}}}
        open(os.path.join(sub, f"agent-{aid}.jsonl"), "w").write(json.dumps(rec) + "\n")
        return {"session_id": sid, "transcript_path": main_tp, "agent_id": aid}

    small = os.path.join(td, "small.txt"); open(small, "w").write("x\n" * 10)
    big = os.path.join(td, "big.txt"); open(big, "w").write("line\n" * 20000)
    saved = os.path.join(td, "tool-results", "r.txt"); os.makedirs(os.path.dirname(saved))
    open(saved, "w").write("y" * 60000)
    src = os.path.join(td, "src.php"); open(src, "w").write("".join(f"line {i}\n" for i in range(300)))
    hi, lo = agent("hi", 300_000), agent("lo", 50_000)
    TG = [  # (label, payload, env, expect_deny)
        ("fence: Read at 300k", {**hi, "tool_name": "Read", "tool_input": {"file_path": small}}, None, True),
        ("fence: Bash ls at 300k", {**hi, "tool_name": "Bash", "tool_input": {"command": "ls"}}, None, True),
        ("fence: Write handoff at 300k", {**hi, "tool_name": "Write", "tool_input": {"file_path": "/x/a-handoff.md", "content": "h"}}, None, False),
        ("fence: git commit+push at 300k", {**hi, "tool_name": "Bash", "tool_input": {"command": "cd /x && git add -A && git commit -m wip && git push"}}, None, False),
        ("fence: multi-line quoted commit msg", {**hi, "tool_name": "Bash", "tool_input": {"command": "git add -A && git commit -m \"wip: x\n\nbody; with semicolon\" && git push"}}, None, False),
        ("fence: heredoc commit msg", {**hi, "tool_name": "Bash", "tool_input": {"command": "git commit -F - <<'EOF'\nwip; x\n\nmore && text\nEOF\ngit push"}}, None, False),
        ("fence: $(cat heredoc) commit msg", {**hi, "tool_name": "Bash", "tool_input": {"command": "git commit -m \"$(cat <<'EOF'\nwip\n\nsemi; x\nEOF\n)\" && git push"}}, None, False),
        ("fence: commit then rm", {**hi, "tool_name": "Bash", "tool_input": {"command": "git commit -m 'x; y'; rm -rf foo"}}, None, True),
        ("fence: SubagentHandback at 300k", {**hi, "tool_name": "SubagentHandback", "tool_input": {}}, None, False),
        ("fence: mcp tool at 300k", {**hi, "tool_name": "mcp__x__y", "tool_input": {}}, None, True),
        ("fence: Read at 50k", {**lo, "tool_name": "Read", "tool_input": {"file_path": small}}, None, False),
        ("fence off via env", {**hi, "tool_name": "Read", "tool_input": {"file_path": small}}, {"CLAUDE_CTX_FENCE": "0"}, False),
        ("guard off via env", {**hi, "tool_name": "Read", "tool_input": {"file_path": small}}, {"CLAUDE_TOKEN_GUARD_OFF": "1"}, False),
        ("main session never fenced", {"session_id": sid, "transcript_path": main_tp, "tool_name": "Bash", "tool_input": {"command": "sleep 600"}}, None, False),
        ("wait: sleep 300", {**lo, "tool_name": "Bash", "tool_input": {"command": "sleep 300 && gh run view 1"}}, None, True),
        ("wait: sleep 2m", {**lo, "tool_name": "Bash", "tool_input": {"command": "sleep 2m"}}, None, True),
        ("wait: sleep 5", {**lo, "tool_name": "Bash", "tool_input": {"command": "sleep 5; curl -s localhost"}}, None, False),
        ("wait: until loop", {**lo, "tool_name": "Bash", "tool_input": {"command": "until curl -s x; do sleep 10; done"}}, None, True),
        ("wait: loop in timeout 200", {**lo, "tool_name": "Bash", "tool_input": {"command": "timeout 200 bash -c 'until curl -s x; do sleep 5; done'"}}, None, False),
        ("wait: Bash timeout 600 s", {**lo, "tool_name": "Bash", "tool_input": {"command": "php artisan test", "timeout": 600000}}, None, True),
        ("wait: background sleep", {**lo, "tool_name": "Bash", "tool_input": {"command": "sleep 900", "run_in_background": True}}, None, False),
        ("wait: gh run watch", {**lo, "tool_name": "Bash", "tool_input": {"command": "gh run watch 123"}}, None, True),
        ("wait: gh pr checks --watch", {**lo, "tool_name": "Bash", "tool_input": {"command": "gh pr checks 5 --watch"}}, None, True),
        ("wait: commit msg mentions sleep 300", {**lo, "tool_name": "Bash", "tool_input": {"command": "git commit -m \"drop sleep 300 from the job\""}}, None, False),
        ("wait: text heredoc mentions sleep 673", {**lo, "tool_name": "Bash", "tool_input": {"command": "cat > n.md <<'EOF'\nsleep 673 calls\nEOF"}}, None, False),
        ("wait: executed heredoc bash <<X sleep 600", {**lo, "tool_name": "Bash", "tool_input": {"command": "bash <<'X'\nsleep 600\nX"}}, None, True),
        ("wait: heredoc piped into sh, sleep 600", {**lo, "tool_name": "Bash", "tool_input": {"command": "cat <<'X' | sh\nsleep 600\nX"}}, None, True),
        ("read: big file no limit", {"tool_name": "Read", "tool_input": {"file_path": big}}, None, True),
        ("read: big file with limit", {"tool_name": "Read", "tool_input": {"file_path": big, "offset": 1, "limit": 200}}, None, False),
        ("read: small file", {"tool_name": "Read", "tool_input": {"file_path": small}}, None, False),
        ("read: saved tool-result 60 KB", {"tool_name": "Read", "tool_input": {"file_path": saved}}, None, True),
        ("read: png", {"tool_name": "Read", "tool_input": {"file_path": os.path.join(td, "x.png")}}, None, False),
        ("write: rewrite 300-line file, 1 line changed", {"tool_name": "Write", "tool_input": {"file_path": src, "content": open(src).read().replace("line 7\n", "line seven\n")}}, None, True),
        ("write: replace with new content", {"tool_name": "Write", "tool_input": {"file_path": src, "content": "new\n" * 50}}, None, False),
        ("write: new file", {"tool_name": "Write", "tool_input": {"file_path": os.path.join(td, "n.md"), "content": "a"}}, None, False),
    ]
    for c, expect in [("php artisan test", True), ("php artisan test --parallel", True),
                      ("cd /x && php artisan test --filter=OrderSync | tail -5", False),
                      ("php artisan test tests/Feature/FooTest.php | tail -5", False), ("vendor/bin/phpunit -c phpunit.ci.xml", True),
                      ("FULL_SUITE=1 php artisan test | tail -5", False), ("npx playwright test", True),
                      ("npx playwright test e2e/list.spec.ts | tail -5", False), ("npx playwright test --grep @smoke | tail -5", False),
                      ("grep -rn 'php artisan test' docs", False), ("composer test", True)]:
        TG.append((f"suite: {c}", {"tool_name": "Bash", "tool_input": {"command": c}}, None, expect))
    for c, expect in [("npx playwright test e2e/a.spec.ts", True), ("npx playwright test e2e/a.spec.ts 2>&1", True),
                      ("~/.claude/tools/q npx playwright test e2e/a.spec.ts", False),
                      ("cd /x && q php artisan test --filter=Foo", False),
                      ("php artisan test --filter=Foo > /tmp/t.log 2>&1", False),
                      ("npx playwright test e2e/a.spec.ts --reporter=dot", False),
                      ("php artisan test --filter=Foo | tail -20", False), ("npx vitest run src/a.test.ts", True)]:
        TG.append((f"testout: {c}", {"tool_name": "Bash", "tool_input": {"command": c}}, None, expect))
    rr_tp = os.path.join(td, "rr.jsonl")
    src_big = os.path.join(td, "big2.txt"); open(src_big, "w").write("z\n" * 5000)
    open(rr_tp, "w").write(json.dumps({"type": "assistant", "message": {"id": "x", "content": [
        {"type": "tool_use", "id": "r0", "name": "Read", "input": {"file_path": src_big}}]}}) + "\n" +
        json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "r0", "content": "z"}]}}) + "\n")
    art_log = os.path.join(td, "artifacts", "run.log"); os.makedirs(os.path.dirname(art_log), exist_ok=True)
    open(art_log, "w").write("l\n" * 20000)
    mid = os.path.join(td, "mid.php"); open(mid, "w").write("x" * 60000)
    TG += [("read: 40 KB log → saved-output cap", {"tool_name": "Read", "tool_input": {"file_path": art_log}}, None, True),
           ("read: 60 KB source no limit", {"tool_name": "Read", "tool_input": {"file_path": mid}}, None, True)]
    TG += [("reread: same 10 KB file whole again", {"transcript_path": rr_tp, "tool_name": "Read", "tool_input": {"file_path": src_big}}, None, True),
           ("reread: ranged re-read", {"transcript_path": rr_tp, "tool_name": "Read", "tool_input": {"file_path": src_big, "offset": 1, "limit": 50}}, None, False),
           ("reread: other file", {"transcript_path": rr_tp, "tool_name": "Read", "tool_input": {"file_path": src}}, None, False),
           ("testout: heredoc body is not a run", {"tool_name": "Bash", "tool_input": {"command": "cat > x.py <<'EOF'\nrun('npx playwright test')\nEOF"}}, None, False)]
    # resume gate: SendMessage targets in <td>/<sid>/subagents (same layout as fence fixtures)
    def agent_at(aid, ctx, idle_s=0, atype=None):
        rec = {"type": "assistant", "message": {"id": "m1", "usage": {
            "input_tokens": 1, "cache_creation_input_tokens": 1000, "cache_read_input_tokens": ctx - 1001}}}
        p = os.path.join(sub, f"agent-{aid}.jsonl")
        open(p, "w").write(json.dumps(rec) + "\n")
        if atype:
            open(p[:-6] + ".meta.json", "w").write(json.dumps({"agentType": atype}))
        t = time.time() - idle_s
        os.utime(p, (t, t))
    agent_at("abig0000000000001", 300_000)
    agent_at("amidcold000000002", 120_000, idle_s=900)
    agent_at("amidwarm000000003", 120_000, idle_s=30)
    agent_at("asmallcold0000004", 50_000, idle_s=3600)
    agent_at("acoord00000000005", 210_000, idle_s=30, atype="claude")
    main_p = {"session_id": sid, "transcript_path": main_tp, "tool_name": "SendMessage"}
    out_path = "/tmp/x/tasks/a" + "8f530a2e97e35402" + ".output"   # split so the literal is not a live path
    TG += [("resume: 300k agent", {**main_p, "tool_input": {"to": "abig0000000000001", "message": "x"}}, None, True),
           ("resume: 120k idle 15 min", {**main_p, "tool_input": {"to": "amidcold000000002", "message": "x"}}, None, True),
           ("resume: 120k warm", {**main_p, "tool_input": {"to": "amidwarm000000003", "message": "x"}}, None, False),
           ("resume: 50k idle 1 h", {**main_p, "tool_input": {"to": "asmallcold0000004", "message": "x"}}, None, False),
           ("resume: claude coordinator 210k (fence 200k)", {**main_p, "tool_input": {"to": "acoord00000000005", "message": "x"}}, None, True),
           ("resume: unknown name/teammate", {**main_p, "tool_input": {"to": "researcher-bob", "message": "x"}}, None, False),
           ("agentout: Read agent JSONL", {"tool_name": "Read", "tool_input": {"file_path": out_path}}, None, True),
           ("agentout: tail agent JSONL", {"tool_name": "Bash", "tool_input": {"command": "tail -5 " + out_path}}, None, True),
           ("agentout: path inside heredoc text", {"tool_name": "Bash", "tool_input": {"command": "cat > n.md <<'EOF'\n" + out_path + "\nEOF"}}, None, False),
           ("agentout: background bash output ok", {"tool_name": "Read", "tool_input": {"file_path": "/tmp/x/tasks/blbatpwi3.output"}}, None, False)]
    # per-type fences (experiment 2026-10-09) + READ_MAX 32 KB (2026-10-17, was 12 KB)
    gp, uib = agent("agp", 230_000), agent("aui", 280_000)
    src15 = os.path.join(td, "src15.php"); open(src15, "w").write("x" * 40000)
    src11 = os.path.join(td, "src11.php"); open(src11, "w").write("x" * 30000)
    TG += [("fence: general-purpose at 230k (fence 220k)", {**gp, "agent_type": "general-purpose", "tool_name": "Read", "tool_input": {"file_path": small}}, None, True),
           ("fence: ui-builder at 280k (fence 300k)", {**uib, "agent_type": "ui-builder", "tool_name": "Read", "tool_input": {"file_path": small}}, None, False),
           ("fence: other type at 230k (default 260k)", {**gp, "agent_type": "backend-builder", "tool_name": "Read", "tool_input": {"file_path": small}}, None, False),
           ("fence: Read of the handoff at 300k", {**hi, "tool_name": "Read", "tool_input": {"file_path": "/x/a-handoff.md"}}, None, False),
           ("read: 40 KB source no limit (cap 32 KB)", {"tool_name": "Read", "tool_input": {"file_path": src15}}, None, True),
           ("wait: 'sleep 673' inside heredoc text", {**lo, "tool_name": "Bash", "tool_input": {"command": "python3 - <<'EOF'\n# loops sleep 673 calls\nEOF"}}, None, False),
           ("read: 11 KB source no limit",{"tool_name": "Read", "tool_input": {"file_path": src11}}, None, False)]

    # polling gate: 3rd wait-like Bash in a row (subagents only)
    def poll_agent(aid, prev_cmds, inflight=()):
        """One completed turn (tool_use + its tool_result) per prev_cmds item; `inflight` = earlier siblings of the
        current message, no results yet."""
        p = os.path.join(sub, f"agent-{aid}.jsonl")
        with open(p, "w") as fh:
            fh.write(json.dumps({"type": "assistant", "message": {"id": "u0", "usage": {"input_tokens": 1000}}}) + "\n")
            for i, c in enumerate(prev_cmds):
                tool, inp = ("Bash", {"command": c}) if c != "READ" else ("Read", {"file_path": small})
                fh.write(json.dumps({"type": "assistant", "message": {"id": f"p{i}", "content": [
                    {"type": "tool_use", "id": f"t{i}", "name": tool, "input": inp}]}}) + "\n")
                fh.write(json.dumps({"type": "user", "message": {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": f"t{i}", "content": "ok"}]}}) + "\n")
            for j, c in enumerate(inflight):
                fh.write(json.dumps({"type": "assistant", "message": {"id": "pcur", "content": [
                    {"type": "tool_use", "id": f"s{j}", "name": "Bash", "input": {"command": c}}]}}) + "\n")
        return {"session_id": sid, "transcript_path": main_tp, "agent_id": aid}
    waits = ["sleep 60; gh run view 42", "tail -20 /tmp/x/tasks/bxyz.output"]
    p2 = poll_agent("apoll2", waits)
    p_mixed = poll_agent("apollmix", [waits[0], "READ"])
    p_loop = poll_agent("apolloop", ["sleep 20", "tail -5 build.log"])
    p_par = poll_agent("apollpar", ["READ"], inflight=["tail -n1 /s/th1.log", "tail -n1 /s/th2.log"])
    p_par2 = poll_agent("apollpar2", ["sleep 30", "sleep 30"], inflight=["sleep 5"])
    p_dbg = poll_agent("apolldbg", ["tail -50 storage/logs/a.log", "tail -50 storage/logs/b.log"])
    p_probe = poll_agent("apollprobe", ["tail -20 /tmp/x/tasks/bq1.output", "tail -5 /tmp/x/tasks/bq1.output"])
    p_ci = poll_agent("apollci", ["gh run view 42", "gh run view 42 --log-failed | tail -80"])
    p_gs = poll_agent("apollgs", ["grep -rn sleep app/", "php artisan queue:work --once --sleep=0"])
    p_quoted = poll_agent("apollq", ["git commit -m 'sleep later'", "echo \"while x; do sleep 1; done\""])
    p_self = poll_agent("apollself", ["READ", waits[0], "sleep 30"])   # current call already in the transcript (id t2)
    loop_cmd = "git diff --name-only | while read f; do php -l \"$f\"; done"
    p_proc = poll_agent("apollproc", [loop_cmd, loop_cmd])
    bash_c = "timeout 200 bash -c 'until gh run view 42 --json status | grep -q completed; do sleep 20; done'"
    p_bashc = poll_agent("apollbc", [bash_c, bash_c])
    TG += [("poll: 3rd wait in a row (sleep)", {**p2, "tool_name": "Bash", "tool_input": {"command": "sleep 30 && gh run view 42"}}, None, True),
           ("poll: 3rd wait in a row (tail *.log)", {**p_loop, "tool_name": "Bash", "tool_input": {"command": "tail -5 build.log"}}, None, True),
           ("poll: wait after a non-wait call", {**p_mixed, "tool_name": "Bash", "tool_input": {"command": "sleep 30"}}, None, False),
           ("poll: non-wait after two waits", {**p2, "tool_name": "Bash", "tool_input": {"command": "git status"}}, None, False),
           ("poll: background after two waits", {**p2, "tool_name": "Bash", "tool_input": {"command": "sleep 30", "run_in_background": True}}, None, False),
           ("poll: quoted 'sleep' text is not a wait", {**p_quoted, "tool_name": "Bash", "tool_input": {"command": "sleep 10"}}, None, False),
           ("poll: current call in transcript not counted", {**p_self, "tool_use_id": "t2", "tool_name": "Bash", "tool_input": {"command": "sleep 30"}}, None, False),
           ("poll: `while read` processing loops ×3", {**p_proc, "tool_name": "Bash", "tool_input": {"command": loop_cmd}}, None, False),
           ("poll: 3rd quoted `bash -c` sleep loop", {**p_bashc, "tool_name": "Bash", "tool_input": {"command": bash_c}}, None, True),
           ("poll: parallel siblings of one message = 1 turn", {**p_par, "tool_name": "Bash", "tool_input": {"command": "tail -n1 /s/th3.log"}}, None, False),
           ("poll: 3rd wait turn, siblings in flight", {**p_par2, "tool_name": "Bash", "tool_input": {"command": "sleep 5"}}, None, True),
           ("poll: 3 different log tails (debugging)", {**p_dbg, "tool_name": "Bash", "tool_input": {"command": "tail -50 storage/logs/c.log"}}, None, False),
           ("poll: same probe re-checked 3×", {**p_probe, "tool_name": "Bash", "tool_input": {"command": "tail -20 /tmp/x/tasks/bq1.output"}}, None, True),
           ("poll: gh run view --log/--job investigation", {**p_ci, "tool_name": "Bash", "tool_input": {"command": "gh run view --job 99 --log | grep Error"}}, None, False),
           ("poll: grep sleep / --sleep=0 are not waits", {**p_gs, "tool_name": "Bash", "tool_input": {"command": "grep -rn \"sleep 1\" app/"}}, None, False),
           ("poll: main session never", {"session_id": sid, "transcript_path": main_tp, "tool_name": "Bash", "tool_input": {"command": "sleep 30"}}, None, False)]
    # main session with the same history in its own transcript
    main_poll = os.path.join(td, "main-poll.jsonl")
    open(main_poll, "w").write(open(os.path.join(sub, "agent-apoll2.jsonl")).read())
    TG.append(("poll: main session with 2 waits before", {"session_id": sid, "transcript_path": main_poll, "tool_name": "Bash", "tool_input": {"command": "sleep 30"}}, None, False))
    for label, payload, env, expect in TG:
        check(f"token-guard: {label:<45} → {'deny' if expect else 'allow'}", tg(payload, env) == expect)
    pr = tg_out({**p2, "tool_name": "Bash", "tool_input": {"command": "sleep 30"}})
    check("token-guard: poll deny names `pending:`", "pending:" in pr and "polling" in pr)

    # fence handoff skeleton from the agent's own transcript
    sk_aid = "askel0000000001"
    sk_tp = os.path.join(sub, f"agent-{sk_aid}.jsonl")
    secret = "sk-" + "abcDEF1234567890xyz"
    leaks = ["hunter2pass", "dbpw12345", "ghtok12345", "oak12345678", "pgpw9876", "ghp_" + "A" * 36, "myRootPw9",
             "abc.def-123", "tokval98765", "sk-straddl"]
    sk_head = ("Fix the widget. key " + secret + " password=hunter2pass DB_PASSWORD=dbpw12345 GITHUB_TOKEN=ghtok12345 "
               "OPENAI_API_KEY=oak12345678 postgres://app:pgpw9876@127.0.0.1/db ghp_" + "A" * 36 + " ")
    sk_prompt = sk_head + "P" * (1489 - len(sk_head)) + " sk-straddle12345678 " + "P" * 3000   # key crosses the 1500 cut
    recs = [{"type": "user", "cwd": "/w/repo", "gitBranch": "feat/x", "message": {"role": "user", "content": sk_prompt}},
            {"type": "assistant", "cwd": "/w/repo", "gitBranch": "feat/x", "message": {"id": "s1", "content": [
                {"type": "tool_use", "id": "r1", "name": "Read", "input": {"file_path": "/w/repo/a.php", "offset": 10, "limit": 20}},
                {"type": "tool_use", "id": "r2", "name": "Read", "input": {"file_path": "/w/repo/b.php"}}]}},
            {"type": "assistant", "message": {"id": "s2", "content": [
                {"type": "tool_use", "id": "r3", "name": "Read", "input": {"file_path": "/w/repo/a.php", "offset": 10, "limit": 20}},
                {"type": "tool_use", "id": "e1", "name": "Edit", "input": {"file_path": "/w/repo/c.php", "old_string": "a", "new_string": "b"}},
                {"type": "tool_use", "id": "b1", "name": "Bash", "input": {"command": "ls -la /w/repo"}},
                {"type": "tool_use", "id": "b2", "name": "Bash", "input": {"command": "git commit -m wip -m 'Authorization: Bearer abc.def-123'"}},
                {"type": "tool_use", "id": "b3", "name": "Bash", "input": {"command": "q php artisan test --filter=Widget"}},
                {"type": "tool_use", "id": "b4", "name": "Bash", "input": {"command": "mysql -uroot -pmyRootPw9 app_testing < s.sql && q php artisan test"}},
                {"type": "tool_use", "id": "b5", "name": "Bash", "input": {"command": "curl -H 'Authorization: token tokval98765' x && gh pr view 1"}},
                {"type": "tool_use", "id": "r4", "name": "Read", "input": {"file_path": "/w/repo/docs/task-lifecycle.md"}}]}},
            {"type": "assistant", "message": {"id": "s3", "usage": {"input_tokens": 1, "cache_read_input_tokens": 299_000}}}]
    open(sk_tp, "w").write("".join(json.dumps(r) + "\n" for r in recs))
    sk_p = {"session_id": sid, "transcript_path": main_tp, "agent_id": sk_aid, "agent_type": "backend-builder"}
    out = tg_out({**sk_p, "tool_name": "Read", "tool_input": {"file_path": small}})
    ho = os.path.join(TG_HO, f"{sid[:8]}-{sk_aid}-handoff.md")
    body = open(ho).read() if os.path.exists(ho) else ""
    check("token-guard: fence writes a handoff skeleton", bool(body) and '"deny"' in out)
    check("token-guard: fence deny names skeleton + FENCE-HANDOFF", ho in out and "FENCE-HANDOFF" in out and "TODO" in out)
    check("token-guard: skeleton header (type, branch, cwd)", "backend-builder" in body and "feat/x" in body and "/w/repo" in body)
    check("token-guard: skeleton prompt ≤1500 chars", "Fix the widget" in body and "P" * 1500 not in body)
    check("token-guard: skeleton redacts secrets", secret not in body and not [s for s in leaks if s in body])
    check("token-guard: skeleton keeps paths like task-lifecycle.md", "/w/repo/docs/task-lifecycle.md" in body)
    rs = body.split("## Read so far")[-1].split("##")[0]
    check("token-guard: skeleton Read list unique, ranged, recent last",
          rs.count("/w/repo/a.php:10+20") == 1 and rs.index("/w/repo/b.php") < rs.index("/w/repo/a.php:10+20"))
    check("token-guard: skeleton Edited lists c.php", "/w/repo/c.php" in body.split("## Edited/Written")[-1].split("##")[0])
    cm = body.split("## Last git/test commands")[-1].split("##")[0]
    check("token-guard: skeleton commands = git/test only", "git commit" in cm and "artisan test" in cm and "ls -la" not in cm)
    check("token-guard: skeleton TODO sections", all(s in body for s in ("Goal", "Done", "Next atomic step", "path:line", "Dead ends", "Open questions")))
    open(ho, "w").write("agent filled\n")
    tg_out({**sk_p, "tool_name": "Read", "tool_input": {"file_path": small}})
    check("token-guard: skeleton never overwrites", open(ho).read() == "agent filled\n")
    bad_dir = os.path.join(td, "notadir"); open(bad_dir, "w").write("f")
    check("token-guard: skeleton failure → still deny", tg({**sk_p, "agent_id": "askel0000000001", "tool_name": "Read",
          "tool_input": {"file_path": small}}, {"CLAUDE_HANDOFF_DIR": bad_dir}))

    # digest hint + series nudge
    r = subprocess.run(["python3", os.path.join(H, "token-guard.py")], input=json.dumps(
        {"tool_name": "Read", "tool_input": {"file_path": mid}}), capture_output=True, text=True,
        env={**os.environ, "CLAUDE_TOKEN_GUARD_LOG": os.devnull})
    check("token-guard: big Read names a digest path + outline", "/digests/mid.php-" in r.stdout and "tools/outline" in r.stdout)

    def series(n, tool="Bash"):
        tp = os.path.join(td, f"series-{n}.jsonl")
        with open(tp, "w") as fh:
            fh.write(json.dumps({"type": "assistant", "message": {"id": "r0", "content": [
                {"type": "tool_use", "name": "Read", "input": {}}]}}) + "\n")
            for i in range(n):
                fh.write(json.dumps({"type": "assistant", "message": {"id": f"m{i}", "content": [
                    {"type": "tool_use", "name": tool, "input": {}}]}}) + "\n")
        r = subprocess.run(["python3", os.path.join(H, "token-guard.py")], input=json.dumps(
            {"hook_event_name": "PostToolUse", "tool_name": tool, "transcript_path": tp}), capture_output=True,
            text=True, env={**os.environ, "CLAUDE_TOKEN_GUARD_LOG": os.devnull})
        return "in a row" in r.stdout
    check("token-guard: series of 8 Bash → nudge", series(8))
    check("token-guard: series of 7 Bash → silent", not series(7))
    check("token-guard: series of 8 Write → silent (not a series tool)", not series(8, "Write"))
shutil.rmtree(TG_HO, ignore_errors=True)

# --- main-sync (SessionStart): fast-forward a clean main checkout on its base branch, warn otherwise
def ms(cwd):
    r = subprocess.run(["python3", os.path.join(H, "main-sync.py")], input=json.dumps({"cwd": cwd}),
                       capture_output=True, text=True, timeout=60)
    return r.stdout.strip()


if not os.path.exists(os.path.join(H, "main-sync.py")):   # owner-only hook, not in the public plugin export
    print("SKIP main-sync: hooks/main-sync.py not present in this tree")
else:
    with tempfile.TemporaryDirectory() as td:
        origin, main_co, other = (os.path.join(td, n) for n in ("origin.git", "main", "other"))
        sh(["git", "init", "-q", "--bare", "-b", "dev", origin])
        sh(["git", "clone", "-q", origin, other])
        sh(["git", "-C", other, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "c1"])
        sh(["git", "-C", other, "push", "-q", "origin", "HEAD:dev"])
        sh(["git", "clone", "-q", "-b", "dev", origin, main_co])

        def advance(msg, path=None):
            if path:
                os.makedirs(os.path.dirname(os.path.join(other, path)) or other, exist_ok=True)
                open(os.path.join(other, path), "w").write(msg)
                sh(["git", "-C", other, "add", "-A"])
            sh(["git", "-C", other, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", msg])
            sh(["git", "-C", other, "push", "-q", "origin", "HEAD:dev"])

        check("main-sync: current checkout → silent", ms(main_co) == "")
        advance("c2", "database/migrations/2026_x.php")
        out = ms(main_co)
        check("main-sync: clean + behind → fast-forwarded, migration hint",
              "fast-forwarded" in out and "migrate" in out and
              subprocess.run(["git", "-C", main_co, "rev-list", "--count", "HEAD..origin/dev"], capture_output=True,
                             text=True).stdout.strip() == "0")
        advance("c3", "README.md")
        open(os.path.join(main_co, "README.md"), "w").write("local edit")
        sh(["git", "-C", main_co, "add", "README.md"])
        out = ms(main_co)
        check("main-sync: dirty + behind → warning, not updated", "not updated" in out and "uncommitted" in out)
        sh(["git", "-C", main_co, "reset", "-q", "--hard"])
        sh(["git", "-C", main_co, "checkout", "-q", "-b", "feat/x"])
        check("main-sync: other branch → warning", "is on `feat/x`" in ms(main_co))
        sh(["git", "-C", main_co, "checkout", "-q", "dev"])
        wt = os.path.join(td, "wt")
        sh(["git", "-C", main_co, "worktree", "add", "-q", "-b", "task/y", wt])
        check("main-sync: linked worktree → silent", ms(wt) == "")

# --- 2026-11-25 hook speed (H2): re-read gate, rules-gate compaction + injection, subagent-start, bg-router, deny text
def jl(*recs):
    return "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in recs)


def tu(i, path, **inp):
    return {"type": "assistant", "message": {"id": "m" + i, "content": [
        {"type": "tool_use", "id": i, "name": "Read", "input": {"file_path": path, **inp}}]}}


def tr(i, text="ok", err=False):
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": i, "content": text,
                                                     **({"is_error": True} if err else {})}]}}


BOUNDARY = {"type": "system", "subtype": "compact_boundary", "compactMetadata": {"trigger": "auto"}}
SUMMARY = {"type": "user", "isCompactSummary": True, "message": {"content": "summary"}}
with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as td:
    big_f = os.path.join(td, "README.md"); open(big_f, "w").write("line\n" * 3000)
    log = os.path.join(td, "tg.log")

    def reread(*recs, cur="cur"):
        tp = os.path.join(td, "t.jsonl"); open(tp, "w").write(jl(*recs))
        return tg({"transcript_path": tp, "tool_use_id": cur, "tool_name": "Read", "tool_input": {"file_path": big_f}})
    check("reread: FIRST Read (own tool_use already in transcript, no result) is not denied",
          not reread(tu("cur", big_f)))
    check("reread: earlier whole Read with a result → denied",
          reread(tu("r1", big_f), tr("r1"), tu("cur", big_f)))
    check("reread: earlier Read that was denied (is_error) does not count",
          not reread(tu("r1", big_f), tr("r1", "token-guard: x", err=True), tu("cur", big_f)))
    check("reread: earlier Read whose result is a hook deny text does not count",
          not reread(tu("r1", big_f), tr("r1", "token-guard: big"), tu("cur", big_f)))
    check("reread: Read before the compaction boundary does not count",
          not reread(tu("r1", big_f), tr("r1"), BOUNDARY, SUMMARY, tu("cur", big_f)))
    check("reread: Read after the compaction boundary counts",
          reread(BOUNDARY, SUMMARY, tu("r1", big_f), tr("r1"), tu("cur", big_f)))

    # rules-gate: compaction + injected marker (own CLAUDE_CONFIG_DIR = rules symlink + state dir)
    root = os.path.join(td, "root"); os.makedirs(os.path.join(root, "state", "injected"))
    os.symlink(os.path.join(HARNESS, "rules"), os.path.join(root, "rules"))
    sess = os.path.join(td, "s"); os.makedirs(os.path.join(sess, "sess9", "subagents"))
    main_t, sub_t = os.path.join(sess, "sess9.jsonl"), os.path.join(sess, "sess9", "subagents", "agent-ag9.jsonl")
    rule_read = tu("g1", os.path.join(root, "rules", "laravel-php.md"))

    def rgate2(*recs, agent=None):
        open(sub_t if agent else main_t, "w").write(jl(*recs))
        d = {"session_id": "sess9", "transcript_path": main_t, "tool_name": "Edit",
             "tool_input": {"file_path": "/home/user/worktrees/w/app/A.php"}, **({"agent_id": agent} if agent else {})}
        r = subprocess.run(["python3", os.path.join(H, "rules-gate.py")], input=json.dumps(d), capture_output=True,
                           text=True, timeout=30, env={**os.environ, "CLAUDE_CONFIG_DIR": root})
        return '"deny"' in r.stdout
    check("rules-gate: rule Read after the boundary → allow", not rgate2(BOUNDARY, SUMMARY, rule_read))
    check("rules-gate: rule Read BEFORE the compaction boundary → deny", rgate2(rule_read, BOUNDARY, SUMMARY))
    check("rules-gate: rule Read before boundary but again after → allow", not rgate2(rule_read, BOUNDARY, SUMMARY, rule_read))
    check("rules-gate: no marker → deny", rgate2({"type": "user"}, agent="ag9"))
    json.dump({"rules": ["laravel-php.md"]}, open(os.path.join(root, "state", "injected", "ag9.json"), "w"))
    check("rules-gate: rule injected per I5 marker → allow", not rgate2({"type": "user"}, agent="ag9"))
    check("rules-gate: injected marker survives a compaction boundary in the transcript",
          not rgate2(BOUNDARY, SUMMARY, agent="ag9"))

    # subagent-start (SubagentStart: agent_id + agent_type only; additionalContext; I5 marker; I3 lessons)
    os.makedirs(os.path.join(root, "tools"))

    def sstart(agent_type, aid="ag7", env=None):
        r = subprocess.run(["python3", os.path.join(H, "subagent-start.py")], capture_output=True, text=True, timeout=30,
                           input=json.dumps({"hook_event_name": "SubagentStart", "agent_id": aid, "agent_type": agent_type,
                                             "session_id": "sess9"}), env={**os.environ, "CLAUDE_CONFIG_DIR": root, **(env or {})})
        return json.loads(r.stdout)["hookSpecificOutput"] if r.stdout.strip() else None
    out = sstart("ui-builder")
    ctx = (out or {}).get("additionalContext", "")
    marker = json.load(open(os.path.join(root, "state", "injected", "ag7.json")))
    check("subagent-start: ui-builder gets stack rule context, event name SubagentStart",
          bool(out) and out["hookEventName"] == "SubagentStart" and "vue-ts.md" in ctx and len(ctx) <= 12000)
    check("subagent-start: I5 marker lists exactly the injected rules", marker["rules"] == ["vue-ts.md"] or
          all(f"rules/{r}" in ctx for r in marker["rules"]) and "vue-ts.md" in marker["rules"])
    check("subagent-start: general-purpose → nothing, no marker", sstart("general-purpose", "ag8") is None
          and not os.path.exists(os.path.join(root, "state", "injected", "ag8.json")))
    open(os.path.join(root, "tools", "lessons.py"), "w").write(
        "import sys\nassert sys.argv[1:3] == ['inject', '--agent-type']\nprint('- lesson for ' + sys.argv[3])\n")
    check("subagent-start: lessons tool output (I3) appended, any agent type",
          "- lesson for lite-worker" in (sstart("lite-worker", "ag6") or {}).get("additionalContext", ""))
    open(os.path.join(root, "tools", "lessons.py"), "w").write("print('x' * 20000)\n")
    check("subagent-start: total capped at 12000 chars",
          len((sstart("ui-builder", "ag5") or {}).get("additionalContext", "")) <= 12000)
    os.remove(os.path.join(root, "tools", "lessons.py"))
    check("subagent-start: missing lessons tool → silent for lite-worker", sstart("lite-worker", "ag4") is None)

    # rules under rules/maxforge/ (public plugin install; Claude Code scans ~/.claude/rules/ recursively)
    mroot = os.path.join(td, "mroot"); os.makedirs(os.path.join(mroot, "rules", "maxforge")); os.makedirs(os.path.join(mroot, "state", "injected"))
    for nm, pat in (("laravel-php.md", "**/*.php"), ("vue-ts.md", "**/*.vue"), ("design-ui-ux.md", "**/*.vue"),
                    ("ui-engineering-qa.md", "**/*.vue")):
        open(os.path.join(mroot, "rules", "maxforge", nm), "w").write(f'---\npaths:\n  - "{pat}"\n---\n# {nm}\nbody {nm}\n')
    msess = os.path.join(td, "ms"); os.makedirs(msess)
    mtp = os.path.join(msess, "sess9.jsonl")

    def mgate(path, *recs):
        open(mtp, "w").write(jl({"type": "user"}, *recs))
        d = {"session_id": "sess9", "transcript_path": mtp, "tool_name": "Edit", "tool_input": {"file_path": path}}
        r = subprocess.run(["python3", os.path.join(H, "rules-gate.py")], input=json.dumps(d), capture_output=True,
                           text=True, timeout=30, env={**os.environ, "CLAUDE_CONFIG_DIR": mroot})
        return r.stdout
    out = mgate("/home/user/worktrees/w/app/A.php")
    check("rules-gate: rule under rules/maxforge/ is found → deny naming it", '"deny"' in out and "maxforge/laravel-php.md" in out)
    check("rules-gate: Read of rules/maxforge/<rule> → allow",
          '"deny"' not in mgate("/home/user/worktrees/w/app/A.php", tu("m1", os.path.join(mroot, "rules", "maxforge", "laravel-php.md"))))
    r = subprocess.run(["python3", os.path.join(H, "subagent-start.py")], capture_output=True, text=True, timeout=30,
                       input=json.dumps({"hook_event_name": "SubagentStart", "agent_id": "mg1", "agent_type": "ui-builder", "session_id": "sess9"}),
                       env={**os.environ, "CLAUDE_CONFIG_DIR": mroot})
    mctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout.strip() else ""
    check("subagent-start: ui-builder rules resolved from rules/maxforge/", "body vue-ts.md" in mctx)
    mmark = os.path.join(mroot, "state", "injected", "mg1.json")
    os.makedirs(os.path.join(msess, "sess9", "subagents"), exist_ok=True)
    open(os.path.join(msess, "sess9", "subagents", "agent-mg1.jsonl"), "w").write('{"type":"user"}\n')
    check("subagent-start: marker names maxforge/ rules; rules-gate then allows the .vue edit",
          os.path.exists(mmark) and "maxforge/vue-ts.md" in json.load(open(mmark))["rules"]
          and '"deny"' not in subprocess.run(["python3", os.path.join(H, "rules-gate.py")], capture_output=True, text=True, timeout=30,
              input=json.dumps({"session_id": "sess9", "transcript_path": mtp, "agent_id": "mg1", "tool_name": "Edit",
                                "tool_input": {"file_path": "/home/user/worktrees/w/a.vue"}}), env={**os.environ, "CLAUDE_CONFIG_DIR": mroot}).stdout)

    # bg-router: subagent → foreground + timeout 270000; main session unchanged; token-guard allows the 270 s call
    def bgr(cmd, agent=None, **extra):
        r = subprocess.run(["python3", os.path.join(H, "bg-router.py")], capture_output=True, text=True, timeout=30,
                           input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd, **extra},
                                             **({"agent_id": agent} if agent else {})}))
        return json.loads(r.stdout)["hookSpecificOutput"] if r.stdout.strip() else None
    o = bgr("npm run test:unit", agent="a1")
    check("bg-router: subagent test run → foreground, timeout 270000, allow",
          o and o["updatedInput"].get("timeout") == 270000 and "run_in_background" not in o["updatedInput"]
          and o["permissionDecision"] == "allow")
    o = bgr("npm run test:unit")
    check("bg-router: main session test run → background (unchanged)",
          o and o["updatedInput"].get("run_in_background") is True and "timeout" not in o["updatedInput"])
    o = bgr("php artisan horizon", agent="a1")
    check("bg-router: subagent server stays in the background", o and o["updatedInput"].get("run_in_background") is True)
    check("bg-router: subagent call with explicit timeout untouched", bgr("npm run build", agent="a1", timeout=60000) is None)
    sid_ = "sess0002"; tp_ = os.path.join(td, f"{sid_}.jsonl"); open(tp_, "w").write("")
    check("token-guard: the rewritten 270 s foreground call is not denied",
          not tg({"session_id": sid_, "transcript_path": tp_, "agent_id": "zz", "tool_name": "Bash",
                  "tool_input": {"command": "npm run test:unit", "timeout": 270000}}))
    check("token-guard: a 300 s foreground call in a subagent is still denied",
          tg({"session_id": sid_, "transcript_path": tp_, "agent_id": "zz", "tool_name": "Bash",
              "tool_input": {"command": "npm run test:unit", "timeout": 300000}}))
    gb = run("guard-bash.py", {"cwd": PROJ, "agent_id": "a1",
                               "tool_input": {"command": "npm run build && git push origin master"}})
    check("bg-router + guard-bash: a long command that also pushes master is still denied by guard-bash",
          '"deny"' in gb and bgr("npm run build && git push origin master", agent="a1") is not None)

    # deny text: exactly one concrete `Next:` step at the end; log line has reason/path|cmd/session/agent_type
    sub_ = os.path.join(td, sid_, "subagents"); os.makedirs(sub_)
    sub_rec = {"type": "assistant", "message": {"id": "m1", "usage": {"input_tokens": 1, "cache_creation_input_tokens": 1,
                                                                      "cache_read_input_tokens": 10}}}
    open(os.path.join(sub_, "agent-zz.jsonl"), "w").write(json.dumps(sub_rec) + "\n")
    mid_f = os.path.join(td, "mid.php"); open(mid_f, "w").write("x" * 60000)
    base = {"session_id": sid_, "transcript_path": tp_, "agent_id": "zz", "agent_type": "general-purpose"}
    KINDS = {
        "read": {"tool_name": "Read", "tool_input": {"file_path": mid_f}},
        "suite": {"tool_name": "Bash", "tool_input": {"command": "php artisan test"}},
        "testout": {"tool_name": "Bash", "tool_input": {"command": "npx vitest run src/a.test.ts"}},
        "wait": {"tool_name": "Bash", "tool_input": {"command": "sleep 200"}},
        "rewrite": {"tool_name": "Write", "tool_input": {"file_path": big_f, "content": "line\n" * 3000}},
    }
    for kind, pl in KINDS.items():
        r = subprocess.run(["python3", os.path.join(H, "token-guard.py")], input=json.dumps({**base, **pl}),
                           capture_output=True, text=True, timeout=30,
                           env={**os.environ, "CLAUDE_TOKEN_GUARD_LOG": log, "CLAUDE_HANDOFF_DIR": TG_HO})
        txt = json.loads(r.stdout)["hookSpecificOutput"]["permissionDecisionReason"] if r.stdout.strip() else ""
        nxt = txt.rsplit(" Next: ", 1)[-1]
        check(f"deny text [{kind}]: ends with exactly one `Next:` step", txt.count(" Next: ") == 1 and len(nxt) > 8 and
              not nxt.rstrip().endswith("?"))
    lines = [json.loads(l) for l in open(log)]
    check("token-guard.log: 5 denies with event/reason/session/agent_type + path or cmd",
          len(lines) == 5 and all(l["reason"] and l["session"] == sid_ and l["agent_type"] == "general-purpose"
                                  and (l.get("path") or l.get("cmd")) for l in lines))
    check("token-guard.log: command target capped at 120 chars",
          all(len(l.get("cmd", "")) <= 120 for l in lines))
    dn = run("dump-nudge.py", {"cwd": td, "tool_input": {"command": f"cat {big_f}"}})
    check("dump-nudge: deny ends with one `Next:` Read step (only in a git worktree → skipped outside)",
          dn == "" or json.loads(dn)["hookSpecificOutput"]["permissionDecisionReason"].count(" Next: Read ") == 1)

# --- rule digests + rules-gate digest path (own suite)
r = subprocess.run(["python3", os.path.join(HARNESS, "tools", "test-rules-digest.py")], capture_output=True, text=True,
                   timeout=120)
check("rules-digest: tools/test-rules-digest.py FAILS 0", r.returncode == 0)

# --- every other self-test shipped in the same tools/ dir (each unit adds tools/test-<unit>.py, interface I8)
SELF = os.path.abspath(__file__)
tools_dir = os.path.join(HARNESS, "tools")
for name in sorted(os.listdir(tools_dir)):
    full = os.path.join(tools_dir, name)
    if not re.fullmatch(r"test-[\w.-]+\.(py|mjs)", name) or os.path.abspath(full) == SELF or name == "test-rules-digest.py":
        continue
    r = subprocess.run(["python3" if name.endswith(".py") else "node", full], capture_output=True, text=True, timeout=600,
                       cwd=HARNESS, env={**os.environ, "CLAUDE_HARNESS_DIR": HARNESS})
    check(f"{name}: exit 0", r.returncode == 0)
    if r.returncode:
        print((r.stdout + r.stderr)[-800:])

print("FAILS:", fails)
raise SystemExit(1 if fails else 0)
