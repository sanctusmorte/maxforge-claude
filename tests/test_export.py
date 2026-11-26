from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from _helpers import load

ex = load("export_mod", "export.py")

SETTINGS = {
    "hooks": {
        "PreToolUse": [
            {"matcher": "Bash", "hooks": [
                {"type": "command", "command": 'python3 "$HOME/.claude/hooks/guard.py"', "timeout": 10, "statusMessage": "guard"},
                {"type": "command", "command": 'python3 "$HOME/.claude/hooks/ownerhook.py" || true', "timeout": 5},
            ]},
        ],
        "SessionStart": [
            {"matcher": "startup", "hooks": [{"type": "command", "command": 'python3 "$HOME/.claude/hooks/ownerhook.py"'}]},
        ],
    }
}
MANIFEST = {
    "include": ["hooks/*.py", "skills/**", "rules/*.md"],
    "exclude": ["skills/secret/**", "**/__pycache__/**"],
    "scrub": [{"glob": "**/*.md", "pattern": "GENERICWORD", "replace": "neutral"}],
    "owner_only_hooks": ["ownerhook.py"],
    "third_party_skills": {"ext": {"url": "https://github.com/a/b", "license": "MIT"}},
}


def run(*args: str) -> tuple[int, str]:
    err = io.StringIO()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
        rc = ex.main(list(args))
    return rc, err.getvalue()


class ExportTest(unittest.TestCase):
    def setUp(self) -> None:
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        base = Path(td.name)
        self.src, self.dest = base / "src", base / "dest"
        self.pats, self.priv = base / "pats.txt", base / "priv.json"
        self.pats.write_text("# none\nPRIVATEWORD\n")
        self.priv.write_text(json.dumps({"scrub": [{"glob": "**", "pattern": "OWNERNAME", "replace": "someone"}]}))
        self.put(self.src / "settings.json", json.dumps(SETTINGS))
        self.put(self.src / "hooks/guard.py", "print('guard')\n")
        self.put(self.src / "hooks/ownerhook.py", "print('owner')\n")
        self.put(self.src / "skills/own/SKILL.md", "GENERICWORD and OWNERNAME\n")
        self.put(self.src / "skills/secret/SKILL.md", "never\n")
        self.put(self.src / "rules/a.md", "rule\n")
        self.put(self.src / "skills-src/up/LICENSE", "MIT License\n")
        self.put(self.src / "skills-src/up/SKILL.md", "upstream\n")
        (self.src / "skills/ext").symlink_to(self.src / "skills-src/up", target_is_directory=True)
        (self.src / "rules/linked.md").symlink_to(self.src / "rules/a.md")
        self.put(self.dest / "export-manifest.json", json.dumps(MANIFEST))
        self.put(self.dest / "scripts/leak-allow.txt", "")
        for plugin_only in ("docs/x.md", "README.md", "skills/setup/SKILL.md", "hooks/maxforge-check.py",
                            "extras/rules/core.md", "bin/maxforge", "tests/t.py", "NOTICE"):
            self.put(self.dest / plugin_only, "mine\n")
        self.put(self.dest / "hooks/hooks.plugin-extra.json", json.dumps({"hooks": {"SessionStart": [
            {"hooks": [{"type": "command", "command": 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/maxforge-check.py"'}]}]}}))

    @staticmethod
    def put(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def go(self, *extra: str) -> tuple[int, str]:
        return run("--source", str(self.src), "--dest", str(self.dest), "--patterns", str(self.pats),
                   "--private-scrub", str(self.priv), *extra)

    def test_copy_scrub_and_exclusions(self) -> None:
        rc, _ = self.go()
        self.assertEqual(rc, 0)
        self.assertEqual((self.dest / "skills/own/SKILL.md").read_text(), "neutral and someone\n")
        self.assertTrue((self.dest / "hooks/guard.py").is_file())
        self.assertFalse((self.dest / "hooks/ownerhook.py").exists())
        self.assertFalse((self.dest / "skills/secret").exists())

    def test_symlinks_never_followed(self) -> None:
        self.go()
        self.assertFalse((self.dest / "skills/ext").exists())
        self.assertFalse((self.dest / "rules/linked.md").exists())
        found = ex.third_party(self.src, ["skills/ext"])
        self.assertEqual(found["ext"], {"url": "https://github.com/up/", "license": "MIT"})

    def test_hooks_json_rewritten_and_merged(self) -> None:
        self.go()
        hooks = json.loads((self.dest / "hooks/hooks.json").read_text())["hooks"]
        self.assertEqual(list(hooks), ["PreToolUse", "SessionStart"])
        (group,) = hooks["PreToolUse"]
        self.assertEqual(group["matcher"], "Bash")
        (only,) = group["hooks"]
        self.assertEqual(only, {"type": "command", "command": 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/guard.py"',
                                "timeout": 10, "statusMessage": "guard"})
        (extra,) = hooks["SessionStart"]
        self.assertIn("maxforge-check.py", extra["hooks"][0]["command"])

    def test_lock_based_stale_delete_and_plugin_only_untouched(self) -> None:
        self.go()
        lock = json.loads((self.dest / "export-manifest.lock.json").read_text())["files"]
        self.assertIn("rules/a.md", lock)
        self.assertIn("hooks/hooks.json", lock)
        (self.src / "rules/a.md").unlink()
        self.put(self.dest / "rules/hand-written.md", "not produced by export\n")
        rc, _ = self.go()
        self.assertEqual(rc, 0)
        self.assertFalse((self.dest / "rules/a.md").exists())
        self.assertTrue((self.dest / "rules/hand-written.md").exists())
        for p in ("docs/x.md", "README.md", "skills/setup/SKILL.md", "hooks/maxforge-check.py",
                  "extras/rules/core.md", "bin/maxforge", "tests/t.py", "NOTICE", "hooks/hooks.plugin-extra.json"):
            self.assertEqual((self.dest / p).read_text()[:1] in ("m", "{"), True, p)

    def test_manifest_producing_plugin_only_path_is_an_error(self) -> None:
        self.put(self.src / "skills/setup/SKILL.md", "owner version\n")
        rc, err = self.go()
        self.assertEqual(rc, 2)
        self.assertIn("plugin-only", err)
        self.assertEqual((self.dest / "skills/setup/SKILL.md").read_text(), "mine\n")

    def test_leak_hit_exits_one_and_writes_nothing(self) -> None:
        self.put(self.src / "rules/leaky.md", "mentions PRIVATEWORD here\n")
        rc, err = self.go()
        self.assertEqual(rc, 1)
        self.assertIn("leak hit", err)
        self.assertFalse((self.dest / "rules/leaky.md").exists())
        self.assertFalse((self.dest / "export-manifest.lock.json").exists())

    def test_dry_run_writes_nothing(self) -> None:
        rc, _ = self.go("--dry-run")
        self.assertEqual(rc, 0)
        self.assertFalse((self.dest / "hooks/guard.py").exists())

    def test_glob_semantics(self) -> None:
        self.assertTrue(ex.matches("skills/a/b/c.md", ["skills/**"]))
        self.assertTrue(ex.matches("a/b/__pycache__/x.pyc", ["**/__pycache__/**"]))
        self.assertTrue(ex.matches("hooks/x.py", ["hooks/*.py"]))
        self.assertFalse(ex.matches("hooks/sub/x.py", ["hooks/*.py"]))


if __name__ == "__main__":
    unittest.main()
