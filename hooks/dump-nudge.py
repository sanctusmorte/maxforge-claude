#!/usr/bin/env python3
"""PreToolUse(Bash) nudge — no file dumps through Bash (rules-audit A2/C3, 2026-09-24).

Denies `cat` / `sed -n <line address>` / `head` / `tail` / `less` when an operand is a regular file of more than
MAX_LINES lines inside a git worktree. Such dumps cost context and skip Read, so the path-scoped stack rules never
load. Stays allowed: output piped into grep/rg/wc, stdout redirected to a file, pattern-only `sed -n '/re/p'`,
bounded slices of ≤ MAX_LINES lines (`sed -n 'N,Mp'`, `head`/`tail -n K`, `-c` ≤ MAX_BYTES; spend audit 2026-10-09:
654 of 826 denials were such slices, each a wasted call), files ≤ MAX_LINES, logs (*.log, *.log.N), paths outside a
git worktree. Separators inside quotes/heredocs are text. Deny reason = one line with the Read hint.
"""
import json
import os
import re
import shlex
import sys

MAX_LINES = 150
MAX_BYTES = 12000  # head/tail -c bound
FILTERS = {"grep", "egrep", "fgrep", "rg", "wc"}
SED_PRINT = re.compile(r"^\s*(\d+)\s*(?:,\s*(\+?)(\d+)\s*)?p\s*$")
SED_QUIT = re.compile(r"^\s*\d*\s*q\s*$")
LOG = re.compile(r"\.log(\.\d+)?$")
ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
REDIRECT = re.compile(r"^(\d*>>?|&>|<<?<?|\d*<)")


def deny(path: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": f"dump-nudge: {path} has >{MAX_LINES} lines — a shell dump of it stays in "
                                    f"context and skips the stack rules a Read loads. Next: Read {path} with "
                                    f"offset=1 limit={MAX_LINES}",
    }}))
    sys.exit(0)


def words(stage: str) -> list:
    try:
        toks = shlex.split(stage)
    except ValueError:
        toks = stage.split()
    while toks and ENV_ASSIGN.match(toks[0]):
        toks = toks[1:]
    return toks


def split_redirects(toks: list):
    """(args without redirections, True when stdout goes to a file or stdin is a heredoc/file)."""
    args, redirected, skip = [], False, False
    for t in toks:
        if skip:
            skip = False
            continue
        m = REDIRECT.match(t)
        if not m:
            args.append(t)
            continue
        op = m.group(1)
        if op in (">", ">>", "1>", "1>>", "&>") or op.startswith("<"):
            redirected = True
        skip = t == op   # operator and target are separate words
    return args, redirected


def strip_heredocs(cmd: str) -> str:
    """Command text without heredoc bodies (script text is not a command run)."""
    out, lines, i = [], cmd.split("\n"), 0
    while i < len(lines):
        out.append(lines[i])
        m = re.search(r"<<-?\s*['\"]?(\w+)['\"]?", lines[i])
        i += 1
        if m:
            while i < len(lines) and lines[i].strip() != m.group(1):
                i += 1
            i += 1
    return "\n".join(out)


def split_top(cmd: str, pipes: bool = False) -> list:
    """Split on && || ; newline (pipes=True: on a single |) outside quotes — `sed -n '5p;9p'` stays one stage."""
    parts, buf, quote, i = [], [], None, 0
    while i < len(cmd):
        ch = cmd[i]
        if quote:
            buf.append(ch)
            if ch == "\\" and quote == '"' and i + 1 < len(cmd):
                buf.append(cmd[i + 1]); i += 2; continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
        elif ch == "\\" and i + 1 < len(cmd):
            buf.append(ch + cmd[i + 1]); i += 2; continue
        elif pipes and ch == "|":
            parts.append("".join(buf)); buf = []; i += 1; continue
        elif not pipes and (cmd[i:i + 2] in ("&&", "||") or ch in ";\n"):
            step = 2 if cmd[i:i + 2] in ("&&", "||") else 1
            parts.append("".join(buf)); buf = []; i += step; continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return parts


def sed_lines(scripts: list):
    """Lines printed by numeric-address `sed -n` scripts (`N p`, `N,M p`, `N,+K p`, `q`); None if unbounded or other."""
    total = 0
    for script in scripts:
        for part in script.split(";"):
            if not part.strip() or SED_QUIT.match(part):
                continue
            m = SED_PRINT.match(part)
            if not m:
                return None
            start = int(m.group(1))
            if m.group(3) is None:
                total += 1
            elif m.group(2):
                total += int(m.group(3)) + 1
            else:
                total += max(0, int(m.group(3)) - start) + 1
    return total


def head_tail_bounded(args: list) -> bool:
    """True when head/tail prints ≤ MAX_LINES lines or ≤ MAX_BYTES bytes (`-n K`, `-K`, `--lines=K`, default 10)."""
    kind, count, i = "n", "10", 0
    while i < len(args):
        a = args[i]
        if a in ("-f", "-F") or a.startswith("--follow"):
            return False
        if a in ("-n", "-c", "--lines", "--bytes"):
            kind, count = ("c" if a in ("-c", "--bytes") else "n"), (args[i + 1] if i + 1 < len(args) else "")
            i += 2
            continue
        m = re.match(r"^(?:--(lines|bytes)=|-(n|c))(.+)$", a)
        if m:
            kind, count = ("c" if m.group(1) == "bytes" or m.group(2) == "c" else "n"), m.group(3)
        elif re.match(r"^-\d+$", a):
            kind, count = "n", a[1:]
        i += 1
    return count.isdigit() and int(count) <= (MAX_BYTES if kind == "c" else MAX_LINES)


def operands(cmd: str, args: list) -> list:
    """File operands of a dump command, [] when the invocation is not a dump (bounded slices ≤ MAX_LINES are not)."""
    if cmd in ("cat", "less"):
        return [a for a in args if not a.startswith("-")]
    if cmd in ("head", "tail"):
        if head_tail_bounded(args):
            return []
        out, skip = [], False
        for a in args:
            if skip:
                skip = False
            elif a in ("-n", "-c", "--lines", "--bytes"):
                skip = True
            elif not a.startswith("-") and not (a.startswith("+") and a[1:].isdigit()):
                out.append(a)
        return out
    if cmd == "sed":
        flags = [a for a in args if a.startswith("-")]
        if any(f == "-i" or f.startswith("-i") or f.startswith("--in-place") for f in flags):
            return []
        if not any(f in ("--quiet", "--silent") or (not f.startswith("--") and "n" in f[1:]) for f in flags):
            return []
        rest, scripts, skip = [], [], False
        for a in args:
            if skip:
                scripts.append(a); skip = False
            elif a in ("-e", "--expression"):
                skip = True
            elif not a.startswith("-"):
                rest.append(a)
        if not scripts and rest:
            scripts, rest = [rest[0]], rest[1:]
        if not any(re.match(r"^\s*(\d+|\$)", s) for s in scripts):
            return []
        n = sed_lines(scripts)
        return [] if n is not None and n <= MAX_LINES else rest
    return []


def in_git_worktree(path: str) -> bool:
    d = os.path.dirname(path)
    while True:
        if os.path.exists(os.path.join(d, ".git")):
            return True
        parent = os.path.dirname(d)
        if parent == d:
            return False
        d = parent


def line_count(path: str, cap: int) -> int:
    """Lines in the file, counting stops once past cap."""
    n, last = 0, b"\n"
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            n += chunk.count(b"\n")
            last = chunk[-1:]
            if n > cap:
                return n
    return n + (0 if last == b"\n" else 1)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if not re.search(r"\b(cat|sed|head|tail|less)\b", cmd):
        return
    cwd = data.get("cwd") or os.getcwd()
    for seq in split_top(strip_heredocs(cmd)):
        stages = [s.strip() for s in split_top(seq, pipes=True) if s.strip()]
        for i, stage in enumerate(stages):
            toks = words(stage)
            if not toks:
                continue
            name = os.path.basename(toks[0])
            if name in ("cd", "pushd") and len(toks) > 1:
                target = os.path.expanduser(toks[1])
                cwd = os.path.normpath(os.path.join(cwd, target))
                continue
            nxt = words(stages[i + 1]) if i + 1 < len(stages) else []
            if nxt and os.path.basename(nxt[0]) in FILTERS:
                continue
            args, redirected = split_redirects(toks[1:])
            if redirected:
                continue
            for op in operands(name, args):
                path = os.path.normpath(os.path.join(cwd, os.path.expanduser(op)))
                if not os.path.isfile(path) or LOG.search(path) or not in_git_worktree(path):
                    continue
                try:
                    n = line_count(path, MAX_LINES)
                except OSError:
                    continue
                if n > MAX_LINES:
                    deny(op)


if __name__ == "__main__":
    main()
