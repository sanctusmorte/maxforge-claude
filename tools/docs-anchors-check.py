#!/usr/bin/env python3
"""docs-anchors-check.py — verify that code anchors cited in docs still exist.

Scans markdown under --docs (default docs/) for `path/to/file.ext:LINE[-LINE]` and
`path/to/file.ext::Symbol` anchors, and checks: file exists; line ≤ file length; for `::Symbol`
the symbol name appears in the file; for `:LINE` with a symbol hint on the same doc line
(`FooService::bar`, `function bar`, `class Foo`) the hint appears within ±5 lines of LINE.
Exit 1 with a listing when anything is stale. Usage: docs-anchors-check.py [--docs docs] [--root .]
[--changed-only] (only anchors pointing at files changed vs origin/dev|master) [--max 200]
[--exclude docs/a,docs/b] (skip docs under these prefixes — historical specs/plans/handoffs)."""
import argparse
import os
import re
import subprocess
import sys

ANCHOR = re.compile(r"(?<![\w/])((?:[A-Za-z0-9_.\-]+/)+[A-Za-z0-9_.\-]+\.(?:php|ts|tsx|js|jsx|vue|py|go|rs|sql|blade\.php|yml|yaml|json|sh|mjs|cjs))(?:::([A-Za-z_][A-Za-z0-9_]*(?:::[A-Za-z_][A-Za-z0-9_]*)?)|:(\d+)(?:-(\d+))?)")


def declared(name: str, src: list) -> bool:
    """True only if `name` is DECLARED in src (class/interface/trait/enum/function/const/property/def/export),
    not merely called or mentioned in a docblock."""
    pat = re.compile(
        r"(?:\b(?:abstract\s+|final\s+|readonly\s+)*(?:class|interface|trait|enum)\s+" + re.escape(name) + r"\b"
        r"|\bfunction\s+&?" + re.escape(name) + r"\s*\("
        r"|\bconst\s+" + re.escape(name) + r"\b"
        r"|\b(?:public|protected|private|var)\s+(?:static\s+)?(?:readonly\s+)?(?:[\w?|\\\[\]]+\s+)?\$" + re.escape(name) + r"\b"
        r"|\bdef\s+" + re.escape(name) + r"\s*\("
        r"|\b(?:export\s+)?(?:async\s+)?function\s+" + re.escape(name) + r"\b"
        r"|\b(?:export\s+)?(?:const|let|var|type|interface|class|enum)\s+" + re.escape(name) + r"\b"
        r"|^\s*(?:async\s+)?" + re.escape(name) + r"\s*\([^)]*\)\s*(?::\s*[\w<>\[\]|\s]+)?\s*\{"   # TS/JS class method
        r"|^\s*" + re.escape(name) + r"\s*:\s*(?:function|\(|async)"                                 # object method
        r")")
    return any(pat.search(s) for s in src)
HINT = re.compile(r"([A-Z][A-Za-z0-9_]+(?:::|@)[a-zA-Z_][A-Za-z0-9_]*|function\s+[a-zA-Z_][A-Za-z0-9_]*|class\s+[A-Z][A-Za-z0-9_]*|def\s+[a-z_][a-z0-9_]*)")


def changed_files(root):
    for base in ("origin/dev", "origin/master", "origin/main"):
        r = subprocess.run(["git", "diff", "--name-only", f"{base}...HEAD"], cwd=root, capture_output=True, text=True)
        if r.returncode == 0:
            return set(r.stdout.split())
    return set()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", default="docs"); ap.add_argument("--root", default=".")
    ap.add_argument("--changed-only", action="store_true"); ap.add_argument("--max", type=int, default=200)
    ap.add_argument("--exclude", default="", help="comma-separated doc path prefixes to skip (relative to --root)")
    a = ap.parse_args()
    excluded = tuple(e.strip().strip("/") + "/" for e in a.exclude.split(",") if e.strip())
    root = os.path.abspath(a.root)
    changed = changed_files(root) if a.changed_only else None
    stale, checked = [], 0
    cache = {}
    for dp, _, files in os.walk(os.path.join(root, a.docs)):
        if "node_modules" in dp or ".vitepress/cache" in dp:
            continue
        for fn in files:
            if not fn.endswith(".md"):
                continue
            doc = os.path.join(dp, fn)
            rel_doc = os.path.relpath(doc, root)
            if excluded and rel_doc.startswith(excluded):
                continue
            try:
                lines = open(doc, encoding="utf-8", errors="ignore").read().splitlines()
            except OSError:
                continue
            for ln, text in enumerate(lines, 1):
                for m in ANCHOR.finditer(text):
                    path, sym, l1, l2 = m.group(1), m.group(2), m.group(3), m.group(4)
                    if path.startswith(("http", "docs/")) or "/node_modules/" in path:
                        continue
                    if changed is not None and path not in changed:
                        continue
                    checked += 1
                    full = os.path.realpath(os.path.join(root, path))
                    if not full.startswith(root + os.sep):
                        stale.append(f"{rel_doc}:{ln}: anchor escapes repo root: {path}")
                        continue
                    if not os.path.isfile(full):
                        stale.append(f"{rel_doc}:{ln}: missing file {path}")
                        continue
                    if path not in cache:
                        cache[path] = open(full, encoding="utf-8", errors="ignore").read().splitlines()
                    src = cache[path]
                    if sym:
                        # `path::Symbol` or `path::Class::member` — every part must be DECLARED in the file
                        missing = [part for part in sym.split("::") if not declared(part, src)]
                        if missing:
                            stale.append(f"{rel_doc}:{ln}: {'/'.join(missing)} not declared in {path} (anchor {sym})")
                        continue
                    line = int(l1)
                    if line > len(src):
                        stale.append(f"{rel_doc}:{ln}: {path}:{line} beyond EOF ({len(src)} lines)")
                        continue
                    # A doc line often names several symbols (`Foo::bar` … `Baz::all()`); the anchor is
                    # fine if ANY of them sits within ±5 lines of the cited line.
                    hints = [re.split(r"::|@", m.group(1))[-1].split()[-1] for m in HINT.finditer(text)]
                    if hints:
                        lo, hi = max(0, line - 6), min(len(src), line + 5)
                        window = src[lo:hi]
                        if not any(any(h in s for s in window) for h in hints):
                            stale.append(f"{rel_doc}:{ln}: {path}:{line} — none of {hints} within ±5 lines (moved?)")
    print(f"anchors checked: {checked}; stale: {len(stale)}")
    for s in stale[:a.max]:
        print("  " + s)
    sys.exit(1 if stale else 0)


if __name__ == "__main__":
    main()
