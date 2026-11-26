#!/usr/bin/env python3
"""Size budget for ~/.claude instruction files (Codex `project_doc_max_bytes` analogue), tokens ≈ chars/4.

  instr-budget.py [--root DIR]   (default ~/.claude)

Always-loaded = CLAUDE.md + rules/*.md without a `paths:` frontmatter key → total ≤ ALWAYS_MAX_TOKENS.
Path-scoped   = rules/*.md with `paths:` → each ≤ SCOPED_MAX_TOKENS (they load together when a matching file is Read).
Prints every file's size; exit 1 on any violation (FAIL lines), 0 otherwise. Read-only."""
import argparse
import glob
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
import _paths  # noqa: E402  (hooks/_paths.py)

ALWAYS_MAX_TOKENS = 7500
SCOPED_MAX_TOKENS = 4000


def tokens(text):
    return len(text) // 4


def is_path_scoped(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    return bool(m and re.search(r"^paths\s*:", m.group(1), re.M))


def measure(root):
    """[(relative path, tokens, scoped)] for CLAUDE.md and rules/*.md under root."""
    rows = []
    files = [os.path.join(root, "CLAUDE.md")] + sorted(glob.glob(os.path.join(root, "rules", "*.md")))
    for path in files:
        if not os.path.isfile(path):
            continue
        text = open(path, encoding="utf-8", errors="ignore").read()
        rows.append((os.path.relpath(path, root), tokens(text), is_path_scoped(text)))
    return rows


def violations(rows):
    always = sum(t for _, t, scoped in rows if not scoped)
    out = []
    if always > ALWAYS_MAX_TOKENS:
        out.append(f"always-loaded {always} tok > {ALWAYS_MAX_TOKENS}")
    out += [f"{name} {t} tok > {SCOPED_MAX_TOKENS} (path-scoped)" for name, t, scoped in rows
            if scoped and t > SCOPED_MAX_TOKENS]
    return always, out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=_paths.harness_dir())
    rows = measure(ap.parse_args().root)
    always, problems = violations(rows)
    for name, t, scoped in rows:
        print(f"  {name:<32} {t:>6} tok  {'path-scoped' if scoped else 'always-loaded'}")
    print(f"always-loaded total {always} tok (budget {ALWAYS_MAX_TOKENS}); path-scoped budget {SCOPED_MAX_TOKENS} per rule")
    for p in problems:
        print("FAIL " + p)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
