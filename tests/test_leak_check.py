from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from _helpers import load

lc = load("leak_check", "leak-check.py")

GH = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
AWS = "AKIA" + "ABCDEFGHIJKLMNOP"


def run(*args: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        rc = lc.main(list(args))
    return rc, out.getvalue()


class LeakCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.root = Path(self._td.name)

    def write(self, name: str, text: str) -> Path:
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def test_clean_tree_exits_zero(self) -> None:
        self.write("a.md", "hello 127.0.0.1 and 10.0.0.5 and 192.0.2.7 noreply@anthropic.com a@example.com\n")
        rc, out = run(str(self.root), "--generic-only")
        self.assertEqual((rc, out), (0, ""))

    def test_generic_detectors_report_file_line_id(self) -> None:
        cases = {
            "github-token": GH,
            "aws-key": AWS,
            "anthropic-key": "sk-ant-" + "x" * 20,
            "private-key": "-----BEGIN RSA PRIVATE" + " KEY-----",
            "email": "mail me: someone@corp" + ".org",
            "ipv4": "host 8.8" + ".4.4 here",
            "secret-literal": "password = \"hunter2" + "hunter2\"",
            "slack-token": "xox" + "b-" + "1" * 12,
            "jwt": "eyJhbGciOiJI" + ".eyJzdWIiOiIx.abcdefghij",
        }
        for det, line in cases.items():
            with self.subTest(det):
                p = self.write(f"{det}.txt", f"ok\n{line}\n")
                rc, out = run(str(p), "--generic-only")
                self.assertEqual(rc, 1)
                self.assertIn(f"{p}:2:{det}", out)

    def test_private_pattern_prints_line_number_not_text(self) -> None:
        pats = self.write("pats.txt", "# comment\n\nsupersecretclient\n")
        p = self.write("x.md", "talk about SuperSecretClient here\n")
        rc, out = run(str(p), "--patterns", str(pats))
        self.assertEqual(rc, 1)
        self.assertIn(f"{p}:1:private-pattern#3", out)
        self.assertNotIn("supersecretclient", out.lower())

    def test_missing_patterns_file_warns_and_runs_generic(self) -> None:
        p = self.write("x.md", f"{GH}\n")
        rc, _ = run(str(p), "--patterns", str(self.root / "absent.txt"))
        self.assertEqual(rc, 1)

    def test_allowlist_removes_public_strings(self) -> None:
        allow = self.write("allow.txt", "# c\n8.8" + ".4.4\n")
        p = self.write("x.md", "dns 8.8" + ".4.4\n")
        self.assertEqual(run(str(p), "--generic-only", "--allow", str(allow))[0], 0)

    def test_skips_git_node_modules_and_symlinks(self) -> None:
        self.write(".git/config", GH)
        self.write("node_modules/p/i.js", GH)
        target = self.write("outside/t.txt", GH)
        (self.root / "link.txt").symlink_to(target)
        rc, out = run(str(self.root / "node_modules"), "--generic-only")
        self.assertEqual(rc, 1)  # explicit path is scanned...
        rc, out = run(str(self.root), "--generic-only")
        self.assertNotIn(".git/config", out)
        self.assertNotIn("node_modules", out)
        self.assertNotIn("link.txt", out)


if __name__ == "__main__":
    unittest.main()
