import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from scan import scan_text  # noqa: E402


def rules(src: str, name: str = "x.vue") -> list[str]:
    return [f["rule"] for f in scan_text(name, src)]


class ScanRules(unittest.TestCase):
    def test_icon_button(self):
        self.assertIn("A11Y-1", rules('<v-btn icon="mdi-close" @click="x"></v-btn>'))
        self.assertIn("A11Y-1", rules("<v-btn icon><v-icon>mdi-x</v-icon></v-btn>"))
        self.assertIn("A11Y-1", rules('<button class="b"><svg></svg></button>'))
        self.assertNotIn("A11Y-1", rules('<v-btn icon="mdi-x" aria-label="Close" />'))
        self.assertNotIn("A11Y-1", rules('<v-btn prepend-icon="mdi-x">Save</v-btn>'))
        self.assertNotIn("A11Y-1", rules('<button><v-icon>mdi-x</v-icon> Save</button>'))
        self.assertNotIn("A11Y-1", rules('<button aria-label="Go"><svg/></button>'))

    def test_label(self):
        self.assertIn("A11Y-2", rules('<input type="text">'))
        self.assertIn("A11Y-2", rules("<v-text-field v-model=\"a\"></v-text-field>"))
        self.assertNotIn("A11Y-2", rules('<label>Name <input type="text"></label>'))
        self.assertNotIn("A11Y-2", rules('<label for="n">Name</label><input id="n">'))
        self.assertNotIn("A11Y-2", rules('<v-text-field label="Name" />'))
        self.assertNotIn("A11Y-2", rules('<input type="hidden">'))
        self.assertNotIn("A11Y-2", rules('<input aria-label="q">'))

    def test_alt_and_size(self):
        r = rules('<img src="a.png">')
        self.assertIn("A11Y-5", r)
        self.assertIn("IMG-1", r)
        self.assertNotIn("A11Y-5", rules('<img src="a" alt="" width="1" height="1">'))
        self.assertNotIn("IMG-1", rules('<img src="a" alt="" width="1" height="1">'))
        self.assertIn("A11Y-5", rules('<v-img src="a" />'))
        self.assertNotIn("IMG-1", rules('<v-img src="a" alt="x" />'))

    def test_outline(self):
        self.assertIn("FOCUS-2", rules("button:focus { outline: none; }", "a.css"))
        self.assertIn("FOCUS-2", rules(".a:focus-visible { outline: 0 }", "a.css"))
        self.assertNotIn("FOCUS-2", rules("a:focus { outline: none; box-shadow: 0 0 0 2px red }", "a.css"))
        self.assertNotIn("FOCUS-2", rules(".b{outline:none}.b:focus-visible{outline:2px solid blue}", "a.css"))
        self.assertNotIn("FOCUS-2", rules("a { outline: 0.5px solid red }", "a.css"))
        self.assertNotIn("FOCUS-2", rules(".i:focus-visible + .ring { outline: none }", "a.css"))
        self.assertNotIn("FOCUS-2", rules(".i:focus-visible { outline: none; background: red }", "a.css"))
        self.assertIn("FOCUS-2", rules('<div class="p-1 outline-none">'))
        self.assertNotIn("FOCUS-2", rules('<div class="outline-none focus-visible:ring-2">'))
        self.assertNotIn("FOCUS-2", rules("/* a { outline: none } */", "a.css"))

    def test_zoom(self):
        self.assertIn("ZOOM-1", rules('<meta name="viewport" content="width=device-width, user-scalable=no">', "i.html"))
        self.assertIn("ZOOM-1", rules('<meta name="viewport" content="maximum-scale=1">', "i.html"))
        self.assertNotIn("ZOOM-1", rules('<meta name="viewport" content="width=device-width, initial-scale=1">', "i.html"))
        self.assertNotIn("ZOOM-1", rules('<meta name="viewport" content="maximum-scale=1.5">', "i.html"))

    def test_paste(self):
        self.assertIn("FORM-3", rules('<input aria-label="a" @paste.prevent>'))
        self.assertIn("FORM-3", rules('<input aria-label="a" @paste="e => e.preventDefault()">'))
        self.assertIn("FORM-3", rules("el.addEventListener('paste', e => { e.preventDefault() })", "a.ts"))
        self.assertNotIn("FORM-3", rules("el.addEventListener('paste', e => { log(e) })", "a.ts"))
        self.assertNotIn("FORM-3", rules('<input aria-label="a" @paste="onPaste">'))

    def test_transition_all(self):
        self.assertIn("ANIM-3", rules(".a { transition: all .2s ease; }", "a.css"))
        self.assertIn("ANIM-3", rules('<div class="transition-all">'))
        self.assertNotIn("ANIM-3", rules(".a { transition: opacity .2s; }", "a.css"))
        self.assertNotIn("ANIM-3", rules(".a { transition: color .2s, all-x 1s; }", "a.css"))

    def test_autofocus(self):
        two = '<input aria-label="a" autofocus><input aria-label="b" autofocus>'
        self.assertEqual(rules(two).count("TOUCH-7"), 1)
        self.assertIn("TOUCH-7", rules("<div autofocus></div>"))
        self.assertNotIn("TOUCH-7", rules('<input aria-label="a" autofocus>'))

    def test_autocomplete(self):
        self.assertIn("FORM-1", rules('<input type="email" aria-label="e">'))
        self.assertNotIn("FORM-1", rules('<input type="email" aria-label="e" autocomplete="email">'))
        self.assertNotIn("FORM-1", rules('<input type="checkbox" aria-label="e">'))

    def test_line_numbers(self):
        f = scan_text("x.vue", "<div>\n\n<img src=a>\n</div>")
        self.assertEqual({x["line"] for x in f}, {3})
        self.assertEqual(f[0]["snippet"], "<img src=a>")


class Cli(unittest.TestCase):
    def run_cli(self, *args: str):
        return subprocess.run([sys.executable, str(Path(__file__).parent / "scan.py"), *args], capture_output=True, text=True)

    def test_json_and_fail_on(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.html").write_text("<img src=a>")
            r = self.run_cli(d)
            self.assertEqual(r.returncode, 0)
            out = json.loads(r.stdout)
            self.assertEqual(out["summary"]["by_rule"], {"A11Y-5": 1, "IMG-1": 1})
            self.assertEqual(self.run_cli("--fail-on", "IMG-1", d).returncode, 1)
            self.assertEqual(self.run_cli("--fail-on", "ZOOM-1", d).returncode, 0)


if __name__ == "__main__":
    unittest.main()
