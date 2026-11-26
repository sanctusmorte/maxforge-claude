#!/usr/bin/env python3
"""Standalone tests for tools/lessons.py and hooks/lesson-capture.py (exit 0 = pass)."""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL, HOOK = ROOT / "tools" / "lessons.py", ROOT / "hooks" / "lesson-capture.py"

HITS = ["мне не нравится этот отступ", "опять кнопка далеко от текста", "снова сломал таблицу", "я же говорил про шрифты",
        "я же просил не трогать список", "убери эту плашку", "выглядит некрасиво", "это не так, как я просил",
        "переделай карточку", "хватит спрашивать", "не надо так делать", "зачем ты удалил файл", "сколько раз повторять",
        "I said no modals", "stop doing that please", "don't add a footer", "you broke it again"]
MISSES = ["добавь поле email в форму", "запусти тесты по подсистеме", "what does this function return",
          "сделай PR в dev", "покажи diff", "thanks, looks good"]


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(cmd: list[str], env: dict, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *cmd], input=stdin, capture_output=True, text=True, env={**os.environ, **env})


def record(i: str, **kw) -> str:
    fm = {"id": i, "quote": kw.get("quote", "q"), "wrong": kw.get("wrong", "w"), "right": kw.get("right", "r"), "why": "y",
          "scope": {"level": kw.get("level", "global"), "surface": kw.get("surface", "process"), "paths": kw.get("paths", [])},
          "confidence": "standing", "rung": kw.get("rung", 2), "check": kw.get("check", {"type": "none", "ref": "", "proven": False}),
          "status": kw.get("status", "active"), "supersedes": None, "review_by": kw.get("review_by", "2099-01-01"),
          "hits": kw.get("hits", 0), "repeats": kw.get("repeats", 0), "created": "2026-11-25", "source": "t"}
    return "---\n" + "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in fm.items()) + "\n---\nbody\n"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.les, self.q, self.st, self.mem = t / "lessons", t / "queue", t / "state", t / "mem"
        for d in (self.les, self.q, self.st, self.mem):
            d.mkdir()
        self.env = {"LESSONS_DIR": str(self.les), "LESSON_QUEUE_DIR": str(self.q), "LESSON_STATE_DIR": str(self.st),
                    "MEMORY_DIR": str(self.mem)}

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, i: str, **kw):
        (self.les / f"{i}.md").write_text(record(i, **kw), encoding="utf-8")

    def lessons(self, *args):
        return run([str(TOOL), *args], self.env)

    def hook(self, payload: dict):
        return run([str(HOOK)], self.env, json.dumps(payload))


class PrefilterAndHook(Base):
    def test_prefilter_samples(self):
        mod = load(HOOK, "lc")
        for s in HITS:
            self.assertTrue(mod.is_hit(s), s)
        for s in MISSES:
            self.assertFalse(mod.is_hit(s), s)
        self.assertGreaterEqual(len(HITS) + len(MISSES), 20)

    def test_prompt_hit_queues_and_nudges(self):
        r = self.hook({"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "опять кнопка далеко"})
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "UserPromptSubmit")
        self.assertIn("Possible owner correction", out["additionalContext"])
        self.assertEqual(len((self.q / "s1.jsonl").read_text().splitlines()), 1)

    def test_prompt_miss_silent(self):
        r = self.hook({"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "добавь поле"})
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertFalse((self.q / "s1.jsonl").exists())

    def test_stop_blocks_once_only(self):
        self.hook({"hook_event_name": "UserPromptSubmit", "session_id": "s2", "prompt": "я же говорил"})
        stop = {"hook_event_name": "Stop", "session_id": "s2"}
        first = self.hook(stop)
        self.assertEqual(json.loads(first.stdout)["decision"], "block")
        self.assertEqual(self.hook(stop).stdout, "")
        self.assertEqual(self.hook({**stop, "stop_hook_active": True}).stdout, "")

    def test_stop_no_block_when_lesson_written_or_subagent(self):
        self.hook({"hook_event_name": "UserPromptSubmit", "session_id": "s3", "prompt": "убери это"})
        self.assertEqual(self.hook({"hook_event_name": "Stop", "session_id": "s3", "agent_id": "a1"}).stdout, "")
        time.sleep(0.05)
        self.put("x")
        self.assertEqual(self.hook({"hook_event_name": "Stop", "session_id": "s3"}).stdout, "")

    def test_stop_without_queue_and_bad_input_fail_open(self):
        self.assertEqual(self.hook({"hook_event_name": "Stop", "session_id": "none"}).stdout, "")
        r = run([str(HOOK)], self.env, "not json")
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_hook_fast(self):
        t = time.time()
        self.hook({"hook_event_name": "UserPromptSubmit", "session_id": "s9", "prompt": "опять"})
        self.assertLess(time.time() - t, 0.5)  # includes interpreter start; in-process cost is ~1 ms


class Tool(Base):
    def test_inject_scope_rung_and_cap(self):
        self.put("code-low", surface="code", rung=2, right="low")
        self.put("code-high", surface="code", rung=4, right="high")
        self.put("ui-one", surface="landing", rung=3, right="ui rule")
        self.put("other-repo", level="project:zzz", surface="code", rung=5)
        self.put("archived", status="archived", surface="code", rung=5)
        self.put("path-only", surface="code", paths=["app/Http/*"], rung=3, right="path rule")
        out = self.lessons("inject", "--agent-type", "general-purpose", "--repo", "demo-app")
        self.assertEqual(out.returncode, 0)
        lines = out.stdout.splitlines()
        self.assertLess(lines.index(next(l for l in lines if "code-high" in l)), lines.index(next(l for l in lines if "code-low" in l)))
        for bad in ("ui-one", "other-repo", "archived"):
            self.assertNotIn(bad, out.stdout)
        self.assertIn("path-only", self.lessons("inject", "--agent-type", "general-purpose", "--paths", "app/Http/X.php").stdout)
        self.assertNotIn("path-only", self.lessons("inject", "--agent-type", "general-purpose", "--paths", "src/a.ts").stdout)
        ui = self.lessons("inject", "--agent-type", "design-judge").stdout
        self.assertIn("ui-one", ui)
        self.assertNotIn("code-high", ui)
        self.assertLessEqual(len(self.lessons("inject", "--agent-type", "general-purpose", "--max-lines", "2").stdout.splitlines()), 2)

    def test_inject_omits_wrong_tail(self):
        self.put("with-wrong", surface="code", rung=3, right="do this", wrong="did that")
        out = self.lessons("inject", "--agent-type", "general-purpose", "--repo", "demo-app").stdout
        self.assertIn("do this", out)
        self.assertNotIn("не так", out)

    def test_inject_always_exit_0_and_empty(self):
        env = {**self.env, "LESSONS_DIR": str(self.les / "missing")}
        r = run([str(TOOL), "inject", "--agent-type", "x"], env)
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        (self.les / "bad.md").write_text("---\nid: \"b\"\nrung: [oops\n---\n")
        self.assertEqual(self.lessons("inject", "--agent-type", "x").returncode, 0)

    def test_inject_fast_on_real_records(self):
        t = time.time()
        r = run([str(TOOL), "inject", "--agent-type", "general-purpose"], {"LESSON_STATE_DIR": self.st.as_posix()})
        self.assertEqual(r.returncode, 0)
        self.assertLess(time.time() - t, 0.3)

    def test_check_repeat(self):
        self.put("btn-far", surface="ui", quote="кнопка опять далеко от текста", wrong="кнопка в 120 px от подписи", right="кнопка рядом с подписью")
        self.put("other", quote="убери экранный диктор", wrong="screen reader", right="skip")
        r = self.lessons("check-repeat", "кнопка снова далеко от подписи").stdout
        self.assertTrue(r.startswith("btn-far"))
        self.assertNotIn("other", r)
        self.assertEqual(self.lessons("check-repeat", "совсем другое про базу").stdout, "")

    def test_render_outputs(self):
        self.put("ui-x", surface="crm-table", quote="Q-UI", wrong="W-UI", right="R-UI")
        self.put("code-x", surface="code")
        self.lessons("render")
        self.assertIn("ui-x", (self.les / "INDEX.md").read_text())
        rejected = (self.les / "rejected-ui.md").read_text()
        self.assertIn("Q-UI", rejected)
        self.assertIn("W-UI", rejected)
        self.assertNotIn("code-x", rejected)

    def test_stats_and_repeat(self):
        self.put("a", repeats=1)
        (self.q / "s.jsonl").write_text('{"kind": "hit", "ts": 1}\n{"kind": "hit", "ts": 2}\n{"kind": "processed", "ts": 3}\n')
        self.assertIn("repeat_rate=0.50", self.lessons("stats").stdout)
        self.assertIn("raise rung", self.lessons("repeat", "a").stdout)
        self.assertIn("repeats=2", self.lessons("stats").stdout)

    def test_expire_only_prose_unhit_past_due(self):
        self.put("old-prose", review_by="2020-01-01")
        self.put("old-hit", review_by="2020-01-01", hits=2)
        self.put("old-proven", review_by="2020-01-01", check={"type": "ui-qa", "ref": "r", "proven": True})
        self.put("future", review_by="2099-01-01")
        out = self.lessons("expire").stdout
        self.assertIn("old-prose", out)
        for keep in ("old-hit", "old-proven", "future"):
            self.assertNotIn(keep, out)
        self.assertIn('"archived"', (self.les / "old-prose.md").read_text())
        self.assertTrue((self.les / "old-prose.md").exists())

    def test_new_scaffold_and_no_overwrite(self):
        r = self.lessons("new", "t-1", "--quote", "q", "--wrong", "w", "--right", "r", "--why", "y", "--surface", "ui")
        self.assertEqual(r.returncode, 0)
        text = (self.les / "t-1.md").read_text()
        review = dt.date.today() + dt.timedelta(days=75)
        self.assertIn(review.isoformat(), text)
        self.assertEqual(self.lessons("new", "t-1").returncode, 1)
        self.lessons("new", "t-2", "--check-type", "ui-qa", "--proven")
        self.assertIn("review_by: null", (self.les / "t-2.md").read_text())


class MemoryIndex(Base):
    def make(self, n_old: int = 30):
        old = time.time() - 60 * 86400
        (self.mem / "MEMORY.md").write_text("# idx\n\n- [User](user.md) — u\n" + "".join(
            f"- [Old {i}](project_old_{i}.md) — {'x' * 150}\n" for i in range(n_old)) +
            "- [Fresh](project_fresh.md) — new project\n- [Feed](feedback_a.md) — pref\n- [Ref](reference_r.md) — recipe\n")
        for name, typ in [("user.md", "user"), ("project_fresh.md", "project"), ("feedback_a.md", "feedback"), ("reference_r.md", "reference"),
                          ("handoff-1.md", "handoff"), ("project_orphan.md", "project")]:
            (self.mem / name).write_text(f"---\nname: {name}\ndescription: d {name}\nmetadata:\n  type: {typ}\n---\nbody\n")
        for i in range(n_old):
            p = self.mem / f"project_old_{i}.md"
            p.write_text(f"---\nname: old{i}\ndescription: d\nmetadata:\n  type: project\n---\nbody\n")
            os.utime(p, (old, old))
        for n in ("INDEX-ARCHIVE.md", "INDEX-REFERENCE.md", "INDEX-FEEDBACK.md"):
            (self.mem / n).write_text(f"# {n}\n")

    def test_check_fails_then_apply_passes_and_is_idempotent(self):
        self.make()
        before = self.lessons("memory-index", "--check")
        self.assertEqual(before.returncode, 1)
        self.assertIn("unlinked_index=3", before.stdout)
        self.assertEqual(self.lessons("memory-index", "--apply").returncode, 0)
        after = self.lessons("memory-index", "--check")
        self.assertEqual(after.returncode, 0, after.stdout)
        self.assertIn("dangling=0 unreachable=0", after.stdout)
        text = (self.mem / "MEMORY.md").read_text()
        self.assertLessEqual(len(text), 6000)
        self.assertIn("project_fresh.md", text)
        self.assertIn("user.md", text)
        self.assertNotIn("project_old_3.md", text)
        self.assertIn("project_old_3.md", (self.mem / "INDEX-ARCHIVE.md").read_text())
        self.assertIn("feedback_a.md", (self.mem / "INDEX-FEEDBACK.md").read_text())
        self.assertIn("reference_r.md", (self.mem / "INDEX-REFERENCE.md").read_text())
        self.assertIn("project_orphan.md", (self.mem / "INDEX-ARCHIVE.md").read_text())
        snap = {p.name: p.read_text() for p in self.mem.glob("*.md")}
        self.lessons("memory-index", "--apply")
        self.assertEqual(snap, {p.name: p.read_text() for p in self.mem.glob("*.md")})
        self.assertEqual(len(list(self.mem.glob("project_old_*.md"))), 30)  # no file deleted

    def test_dangling_detected(self):
        self.make(2)
        self.lessons("memory-index", "--apply")
        with (self.mem / "INDEX-ARCHIVE.md").open("a") as f:
            f.write("- [gone](missing.md) — x\n")
        r = self.lessons("memory-index", "--check")
        self.assertEqual(r.returncode, 1)
        self.assertIn("dangling=1", r.stdout)


class RealRecords(unittest.TestCase):
    def test_records_valid(self):
        mod = load(TOOL, "lessons")
        if not mod.LESSONS.is_dir():   # public plugin tree: the owner's lessons/ is never exported
            self.skipTest(f"no lessons directory at {mod.LESSONS}")
        recs = mod.load_all()
        self.assertGreaterEqual(len(recs), 1)
        need = {"id", "quote", "wrong", "right", "why", "scope", "confidence", "rung", "check", "status", "review_by", "hits",
                "repeats", "created", "source"}
        for r in recs:
            self.assertFalse(need - set(r), r["id"])
            self.assertEqual(r["_path"].stem, r["id"])
            self.assertIn(r["rung"], (1, 2, 3, 4, 5))
            self.assertIn(r["status"], ("active", "archived"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
