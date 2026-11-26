#!/usr/bin/env python3
"""Rule digests: ~/.claude/digests/rules/<name>.md = lossless-in-norms compression of ~/.claude/rules/<name>.md.

Each digest's first line records the sha1 of the source bytes it was written from:
  <!-- digest of rules/<name> sha1=<40 hex> — stale? python3 ~/.claude/tools/rules-digest.py --check -->
hooks/rules-gate.py accepts a Read of a digest in place of its rule ONLY while that sha1 matches the source.

  --check        list digests whose source changed or is gone (or header is broken); exit 1 if any
  --paths        print source -> digest with status
  --stamp NAME   rewrite NAME's header with the current source sha1 — only after the digest body and
                 digests/rules/CHECKLIST.md were re-verified against the changed source
Root: $CLAUDE_CONFIG_DIR or ~/.claude.
"""
import hashlib
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
import _paths  # noqa: E402  (hooks/_paths.py)

ROOT = os.environ.get("CLAUDE_CONFIG_DIR") or _paths.user_dir()   # rules/digests live in the USER config
RULES = os.path.join(ROOT, "rules")
DIGESTS = os.path.join(ROOT, "digests", "rules")
HEADER_RE = re.compile(r"^<!-- digest of rules/(\S+) sha1=([0-9a-f]{40}) ")
HEADER = "<!-- digest of rules/{name} sha1={sha} — stale? python3 ~/.claude/tools/rules-digest.py --check -->"


def source_sha1(name: str) -> str | None:
    try:
        with open(os.path.join(RULES, name), "rb") as fh:
            return hashlib.sha1(fh.read()).hexdigest()
    except OSError:
        return None


def digests() -> list[str]:
    if not os.path.isdir(DIGESTS):
        return []
    return sorted(n for n in os.listdir(DIGESTS) if n.endswith(".md") and n != "CHECKLIST.md")


def status(name: str) -> str:
    with open(os.path.join(DIGESTS, name), encoding="utf-8", errors="replace") as fh:
        m = HEADER_RE.match(fh.readline())
    if not m or m.group(1) != name:
        return "bad-header"
    current = source_sha1(name)
    if current is None:
        return "source-gone"
    return "current" if current == m.group(2) else "stale"


def stamp(name: str) -> int:
    path, sha = os.path.join(DIGESTS, name), source_sha1(name)
    if sha is None or not os.path.isfile(path):
        print(f"no source or digest for {name}", file=sys.stderr)
        return 1
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    head = HEADER.format(name=name, sha=sha)
    lines = [head] + lines[1:] if HEADER_RE.match(lines[0]) else [head] + lines
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"stamped {name} sha1={sha}")
    return 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["--check"]:
        bad = [(n, s) for n in digests() if (s := status(n)) != "current"]
        for n, s in bad:
            print(f"{s}: digests/rules/{n} (source rules/{n})")
        if not bad:
            print(f"ok: {len(digests())} digest(s) current")
        return 1 if bad else 0
    if argv[:1] == ["--paths"]:
        for n in digests():
            print(f"rules/{n} -> digests/rules/{n} [{status(n)}]")
        return 0
    if argv[:1] == ["--stamp"] and len(argv) == 2:
        return stamp(argv[1])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
