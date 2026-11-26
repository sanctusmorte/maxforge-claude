#!/usr/bin/env python3
"""Harness consistency lint: canonical numbers (docs/harness-review-2026-11-25/CONTRACT.md) must agree across
CLAUDE.md, rules/*.md, skills/*/SKILL.md, README.md, agents/*.md and hooks/token-guard.py constants; every quoted
`~/.claude/...` path exists; every agent has `model` + `effort`; every hooks/* file is registered in settings.json
or listed in ALLOWLIST. Usage: harness-lint.py [--root DIR] [--json]. Exit 1 on any violation.
"""
import argparse
import ast
import glob
import json
import os
import re
import sys

CANON = {"READ_MAX": 32000, "REREAD_MIN": 8000, "FENCE_DEFAULT": 260000,
         "FENCE_BY_TYPE": {"claude": 200000, "general-purpose": 220000, "ui-builder": 300000}}
FENCE_K = {200, 220, 260, 300}
ALLOWLIST: set[str] = set()   # hook files intentionally not in settings.json (none: auto-pr-on-stop.sh is reported)
RUNTIME_DIRS = {"logs", "state", "projects", "cache", "tmp", "sessions", "shell-snapshots", "todos", "plans"}
PATH_RE = re.compile(r"~/\.claude/([A-Za-z0-9_./-]+)")

# (id, regex, predicate(match) -> True when the text is a violation, message)
TEXT_RULES = [
    ("main-model", re.compile(r"Opus 5\.5\s+(?:at|на|,|\()?\s*(medium|low|xhigh|max)\b", re.I),
     lambda m: True, "main session must be Opus 5.5 high"),
    ("worker-model", re.compile(r"Sonnet (\d+(?:\.\d+)?)"), lambda m: m.group(1) != "5.5", "workers are Sonnet 5.5"),
    ("agent-cap", re.compile(r"MAX_CONCURRENT_SUBAGENTS\s*[=:]\s*(\d+)"), lambda m: m.group(1) != "10", "agent cap is 10"),
    ("agent-cap", re.compile(r"(?:cap|лимит|максимум|max)\D{0,12}(\d+)\s+(?:parallel|concurrent|subagents|агент|субагент)", re.I),
     lambda m: m.group(1) != "10", "agent cap is 10"),
    ("read-cap", re.compile(r"\b12 ?(?:KB|k\b|000)", re.I), lambda m: True, "Read cap is 32000 chars (READ_MAX), not 12 KB"),
    ("fence", re.compile(r"(?:fence|фенс)[^\n|]{0,80}?\b(\d{2,3})k", re.I),
     lambda m: int(m.group(1)) not in FENCE_K, "fences: default 260k, claude 200k, general-purpose 220k, ui-builder 300k"),
    ("cache-ttl", re.compile(r"SendMessage[^\n]{0,60}?(\d+)\s*(?:min|мин)", re.I),
     lambda m: m.group(1) != "5", "SendMessage resume only within 5 min"),
    ("fg-limit", re.compile(r"foreground[^\n]{0,60}?\b(\d{3})\s*(?:s|sec|с)\b", re.I),
     lambda m: m.group(1) != "270", "subagent foreground test/build limit 270 s"),
]


def read(path):
    try:
        return open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


def doc_files(root):
    pats = ["CLAUDE.md", "README.md", "rules/*.md", "skills/*/SKILL.md", "agents/*.md"]
    return sorted({f for p in pats for f in glob.glob(os.path.join(root, p))})


def check_numbers(root, files, out):
    for f in files:
        rel = os.path.relpath(f, root)
        for n, line in enumerate(read(f).splitlines(), 1):
            for rid, rx, bad, msg in TEXT_RULES:
                m = rx.search(line)
                if m and bad(m):
                    out.append({"check": rid, "file": rel, "line": n, "msg": f"{msg}: «{m.group(0)}»"})


def check_constants(root, out):
    path = os.path.join(root, "hooks", "token-guard.py")
    try:
        tree = ast.parse(read(path))
    except SyntaxError as e:
        out.append({"check": "constants", "file": "hooks/token-guard.py", "line": e.lineno or 0, "msg": "unparsable"})
        return
    found = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in CANON:
            try:
                found[node.targets[0].id] = (ast.literal_eval(node.value), node.lineno)
            except ValueError:
                pass
    for name, want in CANON.items():
        got, line = found.get(name, (None, 0))
        if got != want:
            out.append({"check": "constants", "file": "hooks/token-guard.py", "line": line,
                        "msg": f"{name} = {got!r}, canonical {want!r}"})


def check_paths(root, files, out):
    for f in files:
        rel = os.path.relpath(f, root)
        for n, line in enumerate(read(f).splitlines(), 1):
            for m in PATH_RE.finditer(line):
                p = m.group(1).rstrip(".,;:)")
                tail = line[m.end():m.end() + 1]
                if not p or p.split("/")[0] in RUNTIME_DIRS or (tail and tail in "*<{$"):
                    continue
                if not os.path.exists(os.path.join(root, p.rstrip("/"))):
                    out.append({"check": "path", "file": rel, "line": n, "msg": f"~/.claude/{p} does not exist"})


def frontmatter(text):
    m = re.match(r"---\n(.*?)\n---", text, re.S)
    return dict(l.split(":", 1) for l in m.group(1).splitlines() if ":" in l and not l.startswith(" ")) if m else {}


def check_agents(root, out):
    for f in sorted(glob.glob(os.path.join(root, "agents", "*.md"))):
        fm = {k.strip(): v.strip() for k, v in frontmatter(read(f)).items()}
        for key in ("model", "effort"):
            if not fm.get(key):
                out.append({"check": "agent", "file": os.path.relpath(f, root), "line": 1, "msg": f"missing `{key}`"})


def check_hooks(root, out):
    settings = read(os.path.join(root, "settings.json"))
    registered = set(re.findall(r"hooks/([\w.-]+\.(?:py|sh))", settings))
    for f in sorted(glob.glob(os.path.join(root, "hooks", "*"))):
        name = os.path.basename(f)
        if name.endswith((".py", ".sh")) and name not in registered and name not in ALLOWLIST:
            out.append({"check": "hook-registered", "file": f"hooks/{name}", "line": 0, "msg": "unregistered in settings.json"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    out: list[dict] = []
    files = doc_files(a.root)
    check_numbers(a.root, files, out)
    check_constants(a.root, out)
    check_paths(a.root, files, out)
    check_agents(a.root, out)
    check_hooks(a.root, out)
    if a.json:
        print(json.dumps({"violations": out, "count": len(out)}, ensure_ascii=False, indent=1))
    else:
        for v in out:
            print(f"{v['file']}:{v['line']}: [{v['check']}] {v['msg']}")
        print(f"harness-lint: {len(out)} violation(s)")
    return 1 if out else 0


if __name__ == "__main__":
    sys.exit(main())
