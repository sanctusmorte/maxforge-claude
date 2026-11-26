#!/usr/bin/env python3
"""Leak check for the maxforge-claude tree.

Usage: leak-check.py [paths] [--patterns FILE] [--generic-only] [--allow FILE]

Generic detectors (tokens, keys, emails, public IPv4) plus private regexes from
~/.claude/state/maxforge/leak-patterns.txt (one regex per line, `#` = comment).
Private hits print the pattern LINE NUMBER, never the pattern text.
Exit 1 on any hit (file:line:detector-id), else 0.
"""
from __future__ import annotations

import argparse
import ipaddress
import re
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATTERNS = Path.home() / ".claude" / "state" / "maxforge" / "leak-patterns.txt"
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".tmp"}
ALLOWED_EMAIL_DOMAINS = {"example.com", "example.org", "example.net", "anthropic.com", "users.noreply.github.com"}
ALLOWED_EMAILS = {"noreply@anthropic.com"}
IPV4 = re.compile(r"(?<![\w.])(\d{1,3}(?:\.\d{1,3}){3})(?![\w.]*\d)")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")

GENERIC: list[tuple[str, re.Pattern[str]]] = [
    ("github-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{10,}")),
    ("openai-key", re.compile(r"\bsk-(?!ant-)[A-Za-z0-9_-]{20,}")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("aws-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
    (
        "secret-literal",
        re.compile(
            r"""(?i)\b(?:password|passwd|secret|token|api[_-]?key)\b["']?\s*[:=]\s*["'][^"'\s$<>{}()\[\]]{8,}["']"""
        ),
    ),
]


@dataclass(frozen=True)
class Hit:
    path: str
    line: int
    detector: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}:{self.detector}"


def load_allow(path: Path | None) -> list[str]:
    if path is None or not path.is_file():
        return []
    out = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = raw.strip()
        if s and not s.startswith("#"):
            out.append(s)
    return out


def load_private(path: Path) -> list[tuple[int, re.Pattern[str]]]:
    out = []
    for n, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        try:
            out.append((n, re.compile(s, re.IGNORECASE)))
        except re.error as exc:
            raise SystemExit(f"leak-check: invalid regex at {path}:{n}: {exc}")
    return out


def _public_ip(text: str) -> bool:
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return False
    if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
        return False
    # documentation ranges (TEST-NET-1/2/3) are is_private in the stdlib; 100.64/10 is shared space
    return ip.is_global


def scan_line(line: str, allow: list[str], private: list[tuple[int, re.Pattern[str]]], generic: bool) -> list[str]:
    for a in allow:
        line = line.replace(a, "")
    found: list[str] = []
    if generic:
        for det, rx in GENERIC:
            if rx.search(line):
                found.append(det)
        for m in EMAIL.finditer(line):
            domain = m.group(1).lower()
            if m.group(0).lower() in ALLOWED_EMAILS or domain in ALLOWED_EMAIL_DOMAINS or domain.rsplit(".", 1)[-1].isdigit():
                continue  # allowlisted, or `user:pw@1.2.3.4` (host part; IPv4 is checked separately)
            found.append("email")
            break
        for m in IPV4.finditer(line):
            if _public_ip(m.group(1)):
                found.append("ipv4")
                break
    for n, rx in private:
        if rx.search(line):
            found.append(f"private-pattern#{n}")
    return found


def iter_files(paths: list[Path]):
    for root in paths:
        if root.is_file():
            yield root
            continue
        for p in sorted(root.rglob("*")):
            if any(part in SKIP_DIRS for part in p.relative_to(root).parts):
                continue
            if p.is_symlink() or not p.is_file():
                continue
            yield p


def scan_paths(paths: list[Path], allow: list[str], private, generic: bool = True) -> list[Hit]:
    hits: list[Hit] = []
    for f in iter_files(paths):
        try:
            data = f.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:4096]:
            continue
        text = data.decode("utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            for det in scan_line(line, allow, private, generic):
                hits.append(Hit(str(f), i, det))
    return hits


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", default=["."])
    ap.add_argument("--patterns", type=Path, default=DEFAULT_PATTERNS)
    ap.add_argument("--generic-only", action="store_true")
    ap.add_argument("--allow", type=Path, default=Path(__file__).with_name("leak-allow.txt"))
    args = ap.parse_args(argv)

    private: list[tuple[int, re.Pattern[str]]] = []
    if not args.generic_only:
        if args.patterns.is_file():
            private = load_private(args.patterns)
        else:
            print(f"leak-check: warning: no private patterns at {args.patterns}; generic detectors only", file=sys.stderr)
    hits = scan_paths([Path(p) for p in args.paths], load_allow(args.allow), private)
    for h in hits:
        print(h)
    if hits:
        print(f"leak-check: {len(hits)} hit(s)", file=sys.stderr)
        return 1
    print("leak-check: clean", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
