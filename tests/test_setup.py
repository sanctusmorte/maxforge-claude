"""Tests for bin/maxforge and hooks/maxforge-check.py (temp HOME + temp plugin root)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MAXFORGE = REPO / "bin" / "maxforge"
CHECK = REPO / "hooks" / "maxforge-check.py"
WARN = "maxforge-claude: rules not installed or outdated — run /maxforge-claude:setup"


class Env(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.home, self.root, self.data = base / "home", base / "plugin", base / "data"
        self.home.mkdir()
        self.write(self.root / ".claude-plugin" / "plugin.json", json.dumps({"name": "x", "version": "1.2.3"}))
        self.write(self.root / "rules" / "a.md", "rule a\n")
        self.write(self.root / "extras" / "rules" / "core.md", "core\n")
        self.write(self.root / "settings" / "recommended.json", json.dumps(
            {"env": {"A": "1", "B": "2"}, "cleanupPeriodDays": 60, "permissions": {"deny": ["Bash(x)", "Bash(y)"]}}))
        self.write(self.root / "hooks" / "hooks.json", json.dumps(
            {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/stop-guard.py"'}]}]}}))
        self.rules = self.home / ".claude" / "rules" / "maxforge"
        self.settings = self.home / ".claude" / "settings.json"

    @staticmethod
    def write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def env(self) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_")}
        env.update(HOME=str(self.home), CLAUDE_PLUGIN_ROOT=str(self.root), CLAUDE_PLUGIN_DATA=str(self.data))
        return env

    def mf(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(MAXFORGE), *args], capture_output=True, text=True, env=self.env(), timeout=60)

    def backups(self, prefix: str) -> list[Path]:
        root = self.home / ".claude" / "backups"
        return sorted(root.glob(prefix + "-*")) if root.exists() else []


class RulesTests(Env):
    def test_copies_rules_and_stamps_version(self) -> None:
        res = self.mf("setup")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual((self.rules / "a.md").read_text(), "rule a\n")
        self.assertEqual((self.rules / "core.md").read_text(), "core\n")
        self.assertEqual((self.rules / ".maxforge-version").read_text().strip(), "1.2.3")
        self.assertEqual(self.backups("maxforge"), [])

    def test_idempotent_second_run_makes_no_backup(self) -> None:
        self.mf("setup")
        res = self.mf("setup", "--rules")
        self.assertIn("already up to date", res.stdout)
        self.assertEqual(self.backups("maxforge"), [])

    def test_changed_rules_back_up_previous_dir(self) -> None:
        self.mf("setup")
        self.write(self.rules / "local-edit.md", "mine\n")
        res = self.mf("setup")
        self.assertEqual(res.returncode, 0, res.stderr)
        backups = self.backups("maxforge")
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "local-edit.md").read_text(), "mine\n")
        self.assertFalse((self.rules / "local-edit.md").exists())

    def test_dry_run_writes_nothing(self) -> None:
        res = self.mf("setup", "--rules", "--settings", "--dry-run")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("DRY RUN", res.stdout)
        self.assertFalse((self.home / ".claude").exists())

    def test_dry_run_with_existing_rules_makes_no_backup(self) -> None:
        self.mf("setup")
        self.write(self.root / "rules" / "a.md", "changed\n")
        self.mf("setup", "--dry-run")
        self.assertEqual(self.backups("maxforge"), [])
        self.assertEqual((self.rules / "a.md").read_text(), "rule a\n")

    def test_uninstall_backs_up_removes_and_prints_plugin_line(self) -> None:
        self.mf("setup")
        res = self.mf("uninstall")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertFalse(self.rules.exists())
        self.assertEqual(len(self.backups("maxforge-uninstall")), 1)
        self.assertIn("/plugin uninstall maxforge-claude@maxforge-claude", res.stdout)

    def test_version(self) -> None:
        self.assertEqual(self.mf("version").stdout.strip(), "1.2.3")


class SettingsTests(Env):
    def test_creates_settings_when_absent(self) -> None:
        self.assertEqual(self.mf("setup", "--settings").returncode, 0)
        merged = json.loads(self.settings.read_text())
        self.assertEqual(merged["cleanupPeriodDays"], 60)
        self.assertFalse((self.rules).exists(), "--settings alone must not install rules")

    def test_never_overwrites_user_values_and_adds_missing(self) -> None:
        self.write(self.settings, json.dumps({"model": "mine", "env": {"A": "user"}, "permissions": {"deny": ["Bash(x)", "Bash(own)"], "defaultMode": "plan"}}))
        res = self.mf("setup", "--settings")
        self.assertEqual(res.returncode, 0, res.stderr)
        merged = json.loads(self.settings.read_text())
        self.assertEqual(merged["model"], "mine")
        self.assertEqual(merged["env"], {"A": "user", "B": "2"})
        self.assertEqual(merged["permissions"]["defaultMode"], "plan")
        self.assertEqual(merged["permissions"]["deny"], ["Bash(x)", "Bash(own)", "Bash(y)"])
        self.assertIn("+", res.stdout)  # diff shown
        self.assertEqual(len(self.backups("settings")), 1)

    def test_second_run_is_noop(self) -> None:
        self.mf("setup", "--settings")
        res = self.mf("setup", "--settings")
        self.assertIn("nothing to add", res.stdout)

    def test_dry_run_leaves_settings_untouched(self) -> None:
        original = json.dumps({"env": {"A": "user"}})
        self.write(self.settings, original)
        res = self.mf("setup", "--settings", "--dry-run")
        self.assertIn("cleanupPeriodDays", res.stdout)
        self.assertEqual(self.settings.read_text(), original)
        self.assertEqual(self.backups("settings"), [])

    def test_invalid_user_json_aborts_unchanged(self) -> None:
        self.write(self.settings, "{not json")
        res = self.mf("setup", "--settings")
        self.assertEqual(res.returncode, 2)
        self.assertEqual(self.settings.read_text(), "{not json")

    def test_refuses_model_or_bypass_in_recommended(self) -> None:
        self.write(self.root / "settings" / "recommended.json", json.dumps({"model": "opus"}))
        self.assertEqual(self.mf("setup", "--settings").returncode, 2)
        self.write(self.root / "settings" / "recommended.json", json.dumps({"permissions": {"defaultMode": "bypassPermissions"}}))
        self.assertEqual(self.mf("setup", "--settings").returncode, 2)

    def test_shipped_recommended_json_is_generic(self) -> None:
        text = (REPO / "settings" / "recommended.json").read_text()
        data = json.loads(text)
        self.assertNotIn("model", data)
        self.assertNotIn("bypassPermissions", text)
        self.assertNotIn("statusLine", data)


class DoctorTests(Env):
    def test_ok_exit_zero_with_warnings(self) -> None:
        res = self.mf("doctor")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("RESULT: ok", res.stdout)
        self.assertIn("rules installed", res.stdout)

    def test_outdated_rules_warn(self) -> None:
        self.mf("setup")
        self.write(self.rules / ".maxforge-version", "0.0.1\n")
        self.assertIn("outdated", self.mf("doctor").stdout)

    def test_unwritable_data_dir_fails(self) -> None:
        blocker = self.data.parent / "blocker"
        blocker.write_text("file, not dir")
        env = self.env()
        env["CLAUDE_PLUGIN_DATA"] = str(blocker / "sub")
        res = subprocess.run([sys.executable, str(MAXFORGE), "doctor"], capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(res.returncode, 1)
        self.assertIn("FAIL", res.stdout)

    def test_duplicate_hook_wiring_warns_but_exits_zero(self) -> None:
        self.write(self.settings, json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": 'python3 "$HOME/.claude/hooks/stop-guard.py"'}]}]}}))
        res = self.mf("doctor")
        self.assertEqual(res.returncode, 0)
        self.assertRegex(res.stdout, r"WARN\s+no duplicate hook wiring.*stop-guard\.py")


class CheckHookTests(Env):
    def run_hook(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(CHECK)], capture_output=True, text=True, env=self.env(), input="{}", timeout=10)

    def test_warns_when_rules_missing(self) -> None:
        res = self.run_hook()
        self.assertEqual(res.returncode, 0)
        out = json.loads(res.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "SessionStart")
        self.assertEqual(out["additionalContext"], WARN)

    def test_silent_when_current(self) -> None:
        self.mf("setup")
        res = self.run_hook()
        self.assertEqual((res.returncode, res.stdout), (0, ""))

    def test_warns_when_outdated(self) -> None:
        self.mf("setup")
        self.write(self.rules / ".maxforge-version", "0.0.1\n")
        self.assertIn(WARN, self.run_hook().stdout)

    def test_never_fails_on_broken_manifest(self) -> None:
        self.write(self.root / ".claude-plugin" / "plugin.json", "{broken")
        res = self.run_hook()
        self.assertEqual((res.returncode, res.stdout), (0, ""))


class WiringTests(unittest.TestCase):
    def test_plugin_extra_hooks_schema(self) -> None:
        data = json.loads((REPO / "hooks" / "hooks.plugin-extra.json").read_text())
        hook = data["hooks"]["SessionStart"][0]["hooks"][0]
        self.assertEqual(hook["command"], 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/maxforge-check.py"')
        self.assertEqual(hook["timeout"], 5)

    def test_setup_skill_frontmatter(self) -> None:
        text = (REPO / "skills" / "setup" / "SKILL.md").read_text()
        head = text.split("---")[1]
        self.assertIn("name: setup", head)
        self.assertIn("disable-model-invocation: true", head)
        self.assertIn("$ARGUMENTS", text)
        self.assertIn("--dry-run", text)


if __name__ == "__main__":
    unittest.main()
