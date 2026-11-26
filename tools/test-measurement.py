#!/usr/bin/env python3
"""Standalone tests for the H3 measurement unit (usage-report, harness-lint, ctx-monitor I9, statusline, wt-prune --report).
Paths come from __file__; everything runs in a temp dir with HOME redirected. Exit 0 = pass."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import warnings

warnings.simplefilter("ignore", ResourceWarning)
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable


def run(args, stdin=None, home=None, cwd=None):
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PLUGIN_DATA"}   # these tests pin the ~/.claude layout
    env["HOME"] = home or os.environ["HOME"]
    return subprocess.run([PY, *args], input=stdin, capture_output=True, text=True, env=env, cwd=cwd, timeout=120)


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat().replace("+00:00", "Z")


def assistant(mid, t, out=10, rd=0, w5=40000, model="claude-opus-5-5"):
    u = {"input_tokens": 5, "output_tokens": out, "cache_read_input_tokens": rd, "cache_creation_input_tokens": w5,
         "cache_creation": {"ephemeral_5m_input_tokens": w5, "ephemeral_1h_input_tokens": 0}}
    return json.dumps({"type": "assistant", "timestamp": iso(t), "message": {"id": mid, "model": model, "usage": u}})


class UsageReport(unittest.TestCase):
    def test_dedupe_json_shape_and_markdown(self):
        with tempfile.TemporaryDirectory() as td:
            proj = os.path.join(td, "projects", "p1")
            os.makedirs(os.path.join(proj, "s1", "subagents"))
            now = time.time()
            with open(os.path.join(proj, "s1.jsonl"), "w") as fh:   # m1 twice (one record per content block)
                fh.write("\n".join([assistant("m1", now - 100, out=5), assistant("m1", now - 100, out=9),
                                    assistant("m2", now - 50)]) + "\n")
            with open(os.path.join(proj, "s1", "subagents", "agent-a1.jsonl"), "w") as fh:
                fh.write(assistant("s1", now - 40, model="claude-sonnet-5-5") + "\n")
            json.dump({"agentType": "verifier"}, open(os.path.join(proj, "s1", "subagents", "agent-a1.meta.json"), "w"))
            logs = os.path.join(td, "logs")
            os.makedirs(logs)
            with open(os.path.join(logs, "token-guard.log"), "w") as fh:
                fh.write(json.dumps({"ts": now, "event": "deny", "reason": "big-read"}) + "\n")
                fh.write(json.dumps({"ts": now, "event": "deny", "reason": "big-read"}) + "\n")
                fh.write(json.dumps({"ts": now, "event": "series"}) + "\n")
            with open(os.path.join(logs, "task-summary.jsonl"), "w") as fh:
                fh.write(json.dumps({"ts": now, "pr": "https://x/pull/7", "repo": "r", "tokens": 1500000, "subagents": 2}) + "\n")
            r = run([os.path.join(ROOT, "tools", "usage-report.py"), "--days", "7", "--root", os.path.join(td, "projects"),
                     "--logs", logs, "--json", os.path.join(td, "o.json"), "--md", os.path.join(td, "sub", "o.md")])
            self.assertEqual(r.returncode, 0, r.stderr)
            o = json.load(open(os.path.join(td, "o.json")))
            self.assertEqual(o["by_kind_model"]["main|claude-opus-5-5"]["calls"], 2)   # deduped by message.id
            self.assertEqual(o["by_kind_model"]["main|claude-opus-5-5"]["out"], 9 + 10)  # larger record wins
            self.assertEqual(o["by_agent"]["verifier"]["n"], 1)
            md = open(os.path.join(td, "sub", "o.md")).read()
            for s in ("Main vs subagent", "Main-session context", "Effort and thinking", "Cold cache rewrites",
                      "Per agent", "| verifier |", "deny", "big-read | 2", "https://x/pull/7"):
                self.assertIn(s, md)


class HarnessLint(unittest.TestCase):
    def build(self, td, bad):
        for d in ("rules", "agents", "hooks", "skills/x"):
            os.makedirs(os.path.join(td, d))
        open(os.path.join(td, "CLAUDE.md"), "w").write("see ~/.claude/rules/a.md\n")
        open(os.path.join(td, "rules", "a.md"), "w").write("Main = Opus 5.5 at medium; cap 12 KB reads\n" if bad else "ok\n")
        open(os.path.join(td, "agents", "w.md"), "w").write("---\nname: w\nmodel: sonnet\n" + ("" if bad else "effort: medium\n") + "---\n")
        open(os.path.join(td, "hooks", "token-guard.py"), "w").write(
            f"READ_MAX = {12000 if bad else 32000}\nREREAD_MIN = 8000\nFENCE_DEFAULT = 260000\n"
            "FENCE_BY_TYPE = {'claude': 200000, 'general-purpose': 220000, 'ui-builder': 300000}\n")
        open(os.path.join(td, "hooks", "orphan.py"), "w").write("")
        open(os.path.join(td, "hooks", "reg.py"), "w").write("")
        open(os.path.join(td, "settings.json"), "w").write('{"x": "hooks/token-guard.py hooks/reg.py' + ('"}' if bad else ' hooks/orphan.py"}'))

    def lint(self, bad):
        with tempfile.TemporaryDirectory() as td:
            self.build(td, bad)
            r = run([os.path.join(ROOT, "tools", "harness-lint.py"), "--root", td, "--json"])
            return r.returncode, {v["check"] for v in json.loads(r.stdout)["violations"]}

    def test_clean_tree_passes(self):
        self.assertEqual(self.lint(False), (0, set()))

    def test_violations_detected(self):
        rc, checks = self.lint(True)
        self.assertEqual(rc, 1)
        self.assertGreaterEqual(checks, {"main-model", "read-cap", "constants", "agent", "hook-registered"})


class Hooks(unittest.TestCase):
    def test_pr_create_summary_and_statusline_hint(self):
        sid = f"h3test{os.getpid()}"
        with tempfile.TemporaryDirectory() as home:
            tr = os.path.join(home, "t.jsonl")
            open(tr, "w").write("")
            payload = {"session_id": sid, "tool_name": "Bash", "cwd": ROOT, "transcript_path": tr,
                       "tool_input": {"command": "gh pr create --fill"},
                       "tool_response": {"stdout": "https://github.com/o/r/pull/12\n"}}
            t0 = time.time()
            r = run([os.path.join(ROOT, "hooks", "ctx-monitor.py")], json.dumps(payload), home)
            self.assertLess(time.time() - t0, 1.0)
            self.assertEqual(r.returncode, 0, r.stderr)
            rows = [json.loads(l) for l in open(os.path.join(home, ".claude", "logs", "task-summary.jsonl"))]
            self.assertEqual(rows[0]["pr"], "https://github.com/o/r/pull/12")
            self.assertEqual(rows[0]["session"], sid)
            # a failed / unrelated command appends nothing
            for p in (dict(payload, tool_response={"stdout": "error"}), dict(payload, tool_input={"command": "git status"})):
                run([os.path.join(ROOT, "hooks", "ctx-monitor.py")], json.dumps(p), home)
            self.assertEqual(len(open(os.path.join(home, ".claude", "logs", "task-summary.jsonl")).readlines()), 1)
            sl = {"session_id": sid, "cwd": home, "transcript_path": tr, "model": {"display_name": "M"}}
            out = run([os.path.join(ROOT, "hooks", "statusline.py")], json.dumps(sl), home).stdout
            self.assertIn("PR открыт — /clear", out)
            with open(tr, "w") as fh:   # next real user prompt clears the hint
                fh.write(json.dumps({"type": "user", "timestamp": iso(time.time() + 5),
                                     "message": {"content": "next task"}}) + "\n")
            out = run([os.path.join(ROOT, "hooks", "statusline.py")], json.dumps(sl), home).stdout
            self.assertNotIn("PR открыт", out)
            for f in (f"/tmp/claude-pr-open-{sid}.json", f"/tmp/claude-ctx-{sid}.json"):
                if os.path.exists(f):
                    os.remove(f)

    def test_hook_err_counts_last_24h(self):
        with tempfile.TemporaryDirectory() as home:
            logs = os.path.join(home, ".claude", "logs")
            os.makedirs(logs)
            old, new = time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() - 3 * 86400)), time.strftime("%Y-%m-%d %H:%M")
            open(os.path.join(logs, "hook-errors.log"), "w").write(f"{old} boom\n{new} a\n{new} b\n")
            sl = {"session_id": f"h3err{os.getpid()}", "cwd": home, "model": {"display_name": "M"}}
            t0 = time.time()
            out = run([os.path.join(ROOT, "hooks", "statusline.py")], json.dumps(sl), home).stdout
            self.assertIn("hook-err 2", out)
            self.assertLess(time.time() - t0, 1.0)
            os.remove(os.path.join(logs, "hook-errors.log"))
            self.assertNotIn("hook-err", run([os.path.join(ROOT, "hooks", "statusline.py")], json.dumps(sl), home).stdout)
            f = f"/tmp/claude-ctx-{sl['session_id']}.json"
            if os.path.exists(f):
                os.remove(f)


class WtPruneReport(unittest.TestCase):
    def test_lists_only_unregistered_dirs_and_deletes_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            repo, root = os.path.join(td, "repo"), os.path.join(td, "worktrees")
            os.makedirs(root)
            g = ["git", "-C", repo, "-c", "user.email=t@t", "-c", "user.name=t"]
            subprocess.run(["git", "init", "-q", repo], check=True)
            subprocess.run([*g, "commit", "-q", "--allow-empty", "-m", "i"], check=True)
            subprocess.run([*g, "worktree", "add", "-q", os.path.join(root, "reg"), "-b", "b"], check=True)
            os.makedirs(os.path.join(root, "orphan"))
            open(os.path.join(root, "orphan", "f"), "w").write("x" * 2048)
            out = os.path.join(td, "o", "cand.md")
            r = run([os.path.join(ROOT, "tools", "wt-prune.py"), "--report", "--root", root, "--out", out, "--repo", repo])
            self.assertEqual(r.returncode, 0, r.stderr)
            md = open(out).read()
            self.assertIn("| orphan |", md)
            self.assertNotIn("| reg |", md)
            self.assertTrue(os.path.isdir(os.path.join(root, "orphan")) and os.path.isdir(os.path.join(root, "reg")))


if __name__ == "__main__":
    unittest.main()
