#!/usr/bin/env python3
"""Static scan for the mechanical rules of tools/web-guidelines/guidelines.md.

Usage: scan.py [--diff BASE] [--fail-on ID,ID] [paths...]
Output: JSON {"findings": [{rule,file,line,snippet}], "summary": {...}}. Exit 0 unless --fail-on matches.
Regex/AST-lite: findings are leads for review, not proofs. Vue 3 + Vuetify 3 aware.
"""
from __future__ import annotations

import argparse
import bisect
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

EXTS = {".vue", ".html", ".css", ".scss", ".ts", ".tsx", ".jsx"}
SKIP_DIRS = {"node_modules", "vendor", "dist", "build", ".git", "storage", "coverage", ".nuxt", ".output"}

# rule id -> guidelines.md id (ZOOM-1 is scanner-only, from the Anti-patterns list)
RULES = {
    "A11Y-1": "icon-only button without accessible name",
    "A11Y-2": "form control without label / aria-label",
    "A11Y-5": "<img>/<v-img> without alt",
    "FOCUS-2": "outline removed without focus replacement",
    "FORM-1": "text input without autocomplete",
    "FORM-3": "paste blocked",
    "ANIM-3": "transition: all",
    "IMG-1": "<img> without width/height",
    "TOUCH-7": "autofocus misuse",
    "ZOOM-1": "viewport blocks zoom",
}

ATTR_CHUNK = r'(?:=>|"[^"]*"|\'[^\']*\'|[^>"\'])*'
TAG_RE = re.compile(r"<([A-Za-z][\w.-]*)\b(" + ATTR_CHUNK + r")>")
ICON_MARK = re.compile(r"<(?:v-icon|VIcon|svg|i\b|img|Icon\b|[A-Z]\w*Icon\b|mdi-|font-awesome)", re.I)
NATIVE_FIELDS = {"input", "textarea", "select"}
VUETIFY_FIELDS = {
    "v-text-field", "v-textarea", "v-select", "v-autocomplete", "v-combobox", "v-checkbox",
    "v-switch", "v-file-input", "v-radio", "v-slider", "v-otp-input",
}
NO_LABEL_TYPES = {"hidden", "submit", "button", "reset", "image"}
AUTOCOMPLETE_TYPES = {"email", "tel", "password", "url"}
AUTOCOMPLETE_HINT = re.compile(r"name|e-?mail|phone|login|user|address|city|zip|postal", re.I)


def blank_comments(text: str) -> str:
    """Replace comments with spaces, keeping offsets and newlines."""
    def sp(m: re.Match) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))
    text = re.sub(r"<!--.*?-->", sp, text, flags=re.S)
    return re.sub(r"/\*.*?\*/", sp, text, flags=re.S)


def kebab(name: str) -> str:
    """VTextField -> v-text-field; plain tags just lower-cased."""
    if name[:1].isupper() and not name.isupper():
        return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()
    return name.lower()


def has_attr(attrs: str, *names: str) -> bool:
    for n in names:
        if re.search(r"(?<![\w-])(?:v-bind:|:)?" + re.escape(n) + r"(?![\w-])", attrs):
            return True
    return False


def attr_value(attrs: str, name: str) -> str | None:
    m = re.search(r"(?<![\w-])(?:v-bind:|:)?" + re.escape(name) + r"\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|\{([^}]*)\})", attrs)
    if not m:
        return None
    return next(g for g in m.groups() if g is not None)


def has_spread(attrs: str) -> bool:
    return bool(re.search(r"v-bind=|\{\s*\.\.\.", attrs))


class Scan:
    def __init__(self, path: str, text: str):
        self.path = path
        self.raw = text
        self.text = blank_comments(text)
        self.starts = [0] + [m.end() for m in re.finditer(r"\n", text)]
        self.lines = text.split("\n")
        self.findings: list[dict] = []

    def add(self, rule: str, offset: int) -> None:
        line = bisect.bisect_right(self.starts, offset)
        snippet = self.lines[line - 1].strip()[:160]
        key = (rule, line)
        if any((f["rule"], f["line"]) == key for f in self.findings):
            return
        self.findings.append({"rule": rule, "file": self.path, "line": line, "snippet": snippet})

    # --- tag based rules -------------------------------------------------
    def run(self) -> list[dict]:
        self.tags()
        self.css_outline()
        self.regex_rules()
        self.paste()
        self.autofocus_count()
        return sorted(self.findings, key=lambda f: (f["line"], f["rule"]))

    def tags(self) -> None:
        for m in TAG_RE.finditer(self.text):
            name, attrs = m.group(1), m.group(2)
            low = kebab(name)
            if low in ("button", "v-btn"):
                self.button(m, low, attrs)
            if low in NATIVE_FIELDS or low in VUETIFY_FIELDS:
                self.field(m, low, attrs)
            if low in ("img", "v-img"):
                self.image(m, low, attrs)
            if has_attr(attrs, "autofocus") and name.islower() and low not in NATIVE_FIELDS:
                self.add("TOUCH-7", m.start())

    def inner(self, m: re.Match, tag: str) -> str | None:
        if m.group(0).endswith("/>"):
            return ""
        end = re.search(r"</" + re.escape(tag) + r"\s*>", self.text[m.end():], re.I)
        return self.text[m.end(): m.end() + end.start()] if end else None

    def button(self, m: re.Match, low: str, attrs: str) -> None:
        if has_attr(attrs, "aria-label", "aria-labelledby", "title") or has_spread(attrs):
            return
        content = self.inner(m, m.group(1))
        if content is None:
            return
        if low == "v-btn":
            if re.search(r"(?<![\w-])(?::)?icon(?![\w-])", attrs) and not self.has_text(content):
                self.add("A11Y-1", m.start())
            return
        if ICON_MARK.search(content) and not self.has_text(content):
            self.add("A11Y-1", m.start())

    @staticmethod
    def has_text(content: str) -> bool:
        stripped = re.sub(r"<(v-icon|VIcon|svg|i)\b[^>]*>.*?</\1\s*>", "", content, flags=re.S | re.I)
        stripped = re.sub(r"<[^>]*>", "", stripped)
        return bool(stripped.strip()) or "<slot" in content

    def field(self, m: re.Match, low: str, attrs: str) -> None:
        ftype = (attr_value(attrs, "type") or "text").lower()
        if has_spread(attrs):
            return
        if low in NATIVE_FIELDS:
            if ftype in NO_LABEL_TYPES:
                return
            if not (has_attr(attrs, "aria-label", "aria-labelledby") or self.labelled_native(m, attrs)):
                self.add("A11Y-2", m.start())
        elif not has_attr(attrs, "label", "aria-label", "aria-labelledby"):
            self.add("A11Y-2", m.start())
        if low in ("input", "v-text-field") and not has_attr(attrs, "autocomplete"):
            ident = " ".join(filter(None, (attr_value(attrs, n) or attr_value(attrs, n.replace("-", "")) for n in ("name", "id"))))
            ident += " " + (re.search(r"v-model(?::\w+)?(?:\.\w+)*\s*=\s*\"([^\"]*)\"", attrs) or [None, ""])[1]
            if ftype in AUTOCOMPLETE_TYPES or (ftype == "text" and AUTOCOMPLETE_HINT.search(ident)):
                self.add("FORM-1", m.start())

    def labelled_native(self, m: re.Match, attrs: str) -> bool:
        before = self.text[: m.start()]
        if before.lower().rfind("<label") > before.lower().rfind("</label"):
            return True
        fid = attr_value(attrs, "id")
        return bool(fid and re.search(r"<label\b[^>]*(?:for|htmlFor)\s*=\s*[\"'{]\s*" + re.escape(fid), self.text))

    def image(self, m: re.Match, low: str, attrs: str) -> None:
        if has_spread(attrs):
            return
        if not has_attr(attrs, "alt"):
            self.add("A11Y-5", m.start())
        if low == "img" and not (has_attr(attrs, "width") and has_attr(attrs, "height")):
            self.add("IMG-1", m.start())

    # --- text rules --------------------------------------------------------
    def regex_rules(self) -> None:
        for m in re.finditer(r"user-scalable\s*=\s*(?:no|0)|maximum-scale\s*=\s*1(?:\.0+)?(?![\d.])", self.text, re.I):
            self.add("ZOOM-1", m.start())
        for m in re.finditer(r"(?<![\w-])transition(?:-property)?\s*:\s*[^;{}]*?\ball(?![\w-])|(?<![\w:-])transition-all\b", self.text):
            self.add("ANIM-3", m.start())

    def paste(self) -> None:
        for m in re.finditer(r"@paste(?:\.[\w.]*prevent[\w.]*)\b|\bonpaste\s*=\s*[\"']\s*return\s+false", self.text, re.I):
            self.add("FORM-3", m.start())
        for m in re.finditer(r"@paste\s*=\s*\"[^\"]*preventDefault|onPaste\s*=\s*\{[^}]*preventDefault", self.text):
            self.add("FORM-3", m.start())
        for m in re.finditer(r"addEventListener\(\s*['\"]paste['\"]", self.text):
            if "preventDefault" in self.text[m.end(): m.end() + 300]:
                self.add("FORM-3", m.start())

    def autofocus_count(self) -> None:
        hits = [m.start() for m in TAG_RE.finditer(self.text) if has_attr(m.group(2), "autofocus")]
        for off in hits[1:]:  # more than one autofocus per file is misuse
            self.add("TOUCH-7", off)

    # --- css outline ---------------------------------------------------------
    def css_outline(self) -> None:
        for m in re.finditer(r"(?<![\w-])outline\s*:\s*(?:none|0)\b(?!\.)", self.text):
            sel, body = self.rule_block(m.start())
            if body is None:
                continue
            if re.search(r"box-shadow|border(?:-color)?\s*:|outline-(?:color|style)\s*:|text-decoration\s*:|background(?:-color)?\s*:", body):
                continue
            if re.search(r"(?<![\w-])h[1-6]\b|title|heading|__h[1-6]", sel) and ":focus" not in sel:
                continue  # programmatically focused headings (tabindex=-1) legitimately drop the ring
            if re.search(r":focus(?:-visible|-within)?[^,{]*[+~>]|:focus(?:-visible)?\)?\s+\S", sel):
                continue  # ring is drawn on another element (sibling/descendant)
            if self.sibling_focus_visible(sel):
                continue
            self.add("FOCUS-2", m.start())
        for m in re.finditer(r"class\s*=\s*\"([^\"]*)\"|:?class\s*=\s*'([^']*)'|className\s*=\s*[\"{`']([^\"`'}]*)", self.text):
            classes = next(g for g in m.groups() if g is not None)
            if re.search(r"(?<![\w:-])outline-none\b|(?<![\w-])focus:outline-none\b", classes) and not re.search(
                r"focus(?:-visible)?:(?:ring|outline|border|shadow)", classes
            ):
                self.add("FOCUS-2", m.start())

    def rule_block(self, pos: int) -> tuple[str, str | None]:
        open_i = self.text.rfind("{", 0, pos)
        close_prev = self.text.rfind("}", 0, pos)
        if open_i < 0 or close_prev > open_i:
            return "", None
        close_i = self.text.find("}", pos)
        sel_start = max(self.text.rfind("}", 0, open_i), self.text.rfind(";", 0, open_i), self.text.rfind("{", 0, open_i)) + 1
        return self.text[sel_start:open_i].strip(), self.text[open_i + 1: close_i if close_i > 0 else len(self.text)]

    def sibling_focus_visible(self, sel: str) -> bool:
        base = re.split(r":focus|:active|:hover", sel)[0].strip().split(",")[-1].strip()
        if not base:
            return False
        for m in re.finditer(r"([^{}]*:focus-(?:visible|within)[^{}]*)\{([^}]*)\}", self.text):
            if base in m.group(1) and re.search(r"outline\s*:(?!\s*(?:none|0\b))|box-shadow|border", m.group(2)):
                return True
        return False


def scan_text(path: str, text: str) -> list[dict]:
    return Scan(path, text).run()


def iter_files(paths: list[str]):
    for p in map(Path, paths):
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.suffix in EXTS and f.is_file() and not (set(f.parts) & SKIP_DIRS):
                    yield f
        elif p.is_file() and p.suffix in EXTS:
            yield p


def diff_files(base: str) -> list[str]:
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True).stdout.strip()
    for spec in (f"{base}...HEAD", base):
        r = subprocess.run(["git", "diff", "--name-only", "--diff-filter=ACMR", spec], capture_output=True, text=True, cwd=top)
        if r.returncode == 0:
            return [str(Path(top) / n) for n in r.stdout.split("\n") if n]
    raise SystemExit(f"git diff against {base} failed")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--diff", metavar="BASE")
    ap.add_argument("--fail-on", default="", help="comma-separated rule ids; exit 1 if any is found")
    args = ap.parse_args(argv)
    paths = list(args.paths) + (diff_files(args.diff) if args.diff else [])
    findings: list[dict] = []
    files = 0
    for f in iter_files(paths):
        files += 1
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        findings += scan_text(str(f), text)
    counts = Counter(f["rule"] for f in findings)
    out = {"findings": findings, "summary": {"files": files, "total": len(findings), "by_rule": dict(sorted(counts.items()))}}
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1)
    sys.stdout.write("\n")
    fail = {r.strip() for r in args.fail_on.split(",") if r.strip()}
    return 1 if fail & set(counts) else 0


if __name__ == "__main__":
    sys.exit(main())
