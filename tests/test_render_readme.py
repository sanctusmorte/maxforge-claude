"""Tests for scripts/render-readme.mjs on a small fixture README (needs `gh` auth + Playwright)."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "render-readme.mjs"
FIXTURE = ROOT / "tests" / "fixtures" / "readme" / "README.md"
PLAYWRIGHT_DIR = Path.home() / ".claude" / "tools" / "node_modules" / "playwright-core"


def _prerequisites_missing() -> str | None:
    if not shutil.which("node"):
        return "node not installed"
    if not PLAYWRIGHT_DIR.exists():
        return "playwright-core not installed"
    if not shutil.which("gh"):
        return "gh not installed"
    if subprocess.run(["gh", "auth", "status"], capture_output=True).returncode != 0:
        return "gh not authenticated"
    return None


@unittest.skipIf(_prerequisites_missing(), _prerequisites_missing() or "")
class RenderReadmeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        tmp_root = ROOT / ".tmp"
        tmp_root.mkdir(exist_ok=True)
        cls.out = Path(tempfile.mkdtemp(prefix="render-", dir=tmp_root))
        cls.proc = subprocess.run(
            ["node", str(SCRIPT), str(FIXTURE), "--out", str(cls.out), "--widths", "390,1440", "--serve-root", str(ROOT)],
            capture_output=True, text=True, timeout=240,
        )
        report = cls.out / "report.json"
        cls.report = json.loads(report.read_text()) if report.exists() else {}

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.out, ignore_errors=True)

    def test_exits_cleanly_and_writes_screenshots(self) -> None:
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr)
        for theme in ("light", "dark"):
            for width in (390, 1440):
                self.assertGreater((self.out / f"{theme}-{width}.png").stat().st_size, 1000)
                self.assertGreater((self.out / f"{theme}-{width}-first.png").stat().st_size, 1000)

    def test_reports_style_and_class_attributes_as_stripped(self) -> None:
        stripped = {s["markup"] for s in self.report["strippedMarkup"]}
        self.assertIn("<p> style=", stripped)
        self.assertIn("<p> class=", stripped)

    def test_picture_swaps_with_color_scheme(self) -> None:
        images = {i["path"]: i for i in self.report["images"]}
        self.assertEqual(set(images["tests/fixtures/readme/assets/static-dark.svg"]["loadedIn"]), {"dark-390", "dark-1440"})
        self.assertEqual(set(images["tests/fixtures/readme/assets/pulse.svg"]["loadedIn"]), {"light-390", "light-1440"})

    def test_animated_svg_facts_and_frames(self) -> None:
        pulse = next(i for i in self.report["images"] if i["path"].endswith("pulse.svg"))
        self.assertTrue(pulse["isSvg"] and pulse["hasAnimation"] and pulse["hasTitle"] and pulse["exists"])
        self.assertEqual(pulse["naturalSize"], {"width": 320, "height": 120})
        frames = next(iter(self.report["svgFrames"].values()))["light"]
        self.assertAlmostEqual(frames["durationMs"], 4000, delta=50)
        for label in ("t0", "mid", "end"):
            self.assertTrue((self.out / frames["frames"][label]).exists())

    def test_reports_broken_local_link_and_keeps_good_anchor(self) -> None:
        self.assertEqual(self.report["brokenLocalLinks"], ["docs/missing.md"])

    def test_page_height_per_width_and_no_horizontal_overflow(self) -> None:
        self.assertEqual(set(self.report["totalPageHeightByWidth"]), {"390", "1440"})
        for view in self.report["viewports"].values():
            self.assertFalse(view["overflowX"])


if __name__ == "__main__":
    unittest.main()
