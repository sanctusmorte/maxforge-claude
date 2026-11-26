#!/usr/bin/env python3
"""PreToolUse(Edit|Write|MultiEdit|NotebookEdit) gate — the stack rule must be in context before the first edit.

Path-scoped rules (`~/.claude/rules/*.md` with `paths:`) auto-load only for files inside the session's project dir;
workers edit `~/worktrees/*` and other repos, where they never load (2026-09-26: 1 of 164 UI workers had them; after
an instruction-only fix still 3 of 6 workers edited PHP/Python without reading their rule). This hook denies an edit
of a file matched by a rule's `paths:` until that rule's path appears in the agent's own transcript (a Read of it, or
the harness's auto-load attachment). Fails OPEN on anything unexpected. Escape: CLAUDE_GUARD_OFF=1 in the env.

Only a `file_path`/`path` value counts (a Read or an attachment) — a mere mention of the rule in a prompt or in this
hook's own deny text does not. A Read of the digest `digests/rules/<name>` (tools/rules-digest.py) counts instead of
the rule ONLY while the digest's recorded sha1 equals the current source sha1; a stale digest → the rule is required.
Root for rules/ and digests/: $CLAUDE_CONFIG_DIR or ~/.claude.

2026-11-25: a rule counts only if it was Read AFTER the transcript's last compaction boundary (an earlier Read was
summarised away) or was injected by hooks/subagent-start.py, which writes <root>/state/injected/<agent_id>.json
{"rules": ["vue-ts.md", ...]} (interface I5). The scan is mmap-based: the last boundary is found with one rfind.
"""
import hashlib
import json
import mmap
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402  (hooks/_paths.py: portable roots)
import re
import sys

ROOT = os.environ.get("CLAUDE_CONFIG_DIR") or _paths.user_dir()   # rules/digests live in the USER config
RULES_DIR = os.path.join(ROOT, "rules")
DIGEST_DIR = os.path.join(ROOT, "digests", "rules")
DIGEST_HEAD = re.compile(r"^<!-- digest of rules/(\S+) sha1=([0-9a-f]{40}) ")
PATH_VALUE = re.compile(r'\\?"(?:file_path|path)\\?"\s*:\s*\\?"([^"\\]+)')
INJECTED_DIR = os.path.join(ROOT + "/state" if os.environ.get("CLAUDE_CONFIG_DIR") else _paths.data_dir("state"), "injected")
COMPACT_MARKS = (b'"subtype":"compact_boundary"', b'"isCompactSummary":true')
EXEMPT = ("/.claude/", "/tmp/", "/scratchpad/", "/artifacts/", "/node_modules/", "/vendor/", "/.git/")


def expand_braces(pat: str):
    m = re.search(r"\{([^{}]*)\}", pat)
    if not m:
        return [pat]
    out = []
    for alt in m.group(1).split(","):
        out += expand_braces(pat[:m.start()] + alt + pat[m.end():])
    return out


def glob_re(pat: str):
    rx, i = "", 0
    while i < len(pat):
        if pat.startswith("**/", i):
            rx, i = rx + "(?:.*/)?", i + 3
        elif pat.startswith("**", i):
            rx, i = rx + ".*", i + 2
        elif pat[i] == "*":
            rx, i = rx + "[^/]*", i + 1
        elif pat[i] == "?":
            rx, i = rx + "[^/]", i + 1
        else:
            rx, i = rx + re.escape(pat[i]), i + 1
    return re.compile("^" + rx + "$")   # patterns start with **/ → match the absolute path


def rule_files():
    """Rule names relative to rules/ — recursive (Claude Code scans ~/.claude/rules/ recursively; the public plugin
    installs its copies under rules/maxforge/, name `maxforge/<file>.md`)."""
    out = []
    for dirpath, dirs, files in os.walk(RULES_DIR):
        dirs.sort()
        out += [os.path.relpath(os.path.join(dirpath, f), RULES_DIR) for f in sorted(files) if f.endswith(".md")]
    return sorted(out)


def rule_paths():
    rules = {}
    for name in rule_files():
        text = open(os.path.join(RULES_DIR, name), encoding="utf-8", errors="ignore").read(3000)
        fm = re.match(r"---\n(.*?)\n---", text, re.S)
        if not fm:
            continue
        pats = re.findall(r'^\s*-\s*"([^"]+)"', fm.group(1), re.M)
        if pats:
            rules[name] = [glob_re(p) for pat in pats for p in expand_braces(pat)]
    return rules


def digest_current(rule: str) -> bool:
    try:
        with open(os.path.join(DIGEST_DIR, rule), encoding="utf-8", errors="ignore") as fh:
            m = DIGEST_HEAD.match(fh.readline())
        with open(os.path.join(RULES_DIR, rule), "rb") as fh:
            return bool(m) and m.group(1) == rule and m.group(2) == hashlib.sha1(fh.read()).hexdigest()
    except OSError:
        return False


def satisfied(rule: str, paths: set) -> bool:
    if any(p.endswith(f"/rules/{rule}") and not p.endswith(f"/digests/rules/{rule}") for p in paths):
        return True
    return digest_current(rule) and any(p.endswith(f"/digests/rules/{rule}") for p in paths)


def agent_transcript(data: dict) -> str:
    tp = data.get("transcript_path") or ""
    aid = data.get("agent_id")
    if aid:
        cand = os.path.join(os.path.dirname(tp), data.get("session_id", ""), "subagents", f"agent-{aid}.jsonl")
        return cand if os.path.isfile(cand) else ""   # never judge a subagent by the parent's transcript
    return tp if os.path.isfile(tp) else ""


def injected_rules(agent_id) -> set:
    """Rule names the SubagentStart hook put into this agent's context (I5); empty when none / unreadable."""
    if not agent_id or not re.fullmatch(r"[\w.-]+", agent_id):
        return set()
    try:
        with open(os.path.join(INJECTED_DIR, f"{agent_id}.json"), encoding="utf-8") as fh:
            return {r if r.endswith(".md") else r + ".md" for r in json.load(fh).get("rules") or []}
    except (OSError, ValueError, AttributeError, TypeError):
        return set()


def rule_paths_read(tp: str, need: list) -> set:
    """Rule paths (`…/rules/<need>`) Read/attached after the last compaction boundary, stopping once all are satisfied."""
    ends, seen = tuple(f"/rules/{r}" for r in need), set()
    with open(tp, "rb") as fh:
        try:
            mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        except ValueError:   # empty file
            return seen
        with mm:
            cut = max(mm.rfind(m) for m in COMPACT_MARKS)
            pos = 0 if cut < 0 else (mm.find(b"\n", cut) + 1 or len(mm))   # the boundary/summary line itself is skipped
            while True:
                i = mm.find(b"rules/", pos)
                if i < 0:
                    return seen
                end = mm.find(b"\n", i)
                end = len(mm) if end < 0 else end
                line = mm[mm.rfind(b"\n", 0, i) + 1:end].decode("utf-8", "ignore")
                pos = end + 1
                new = {p for p in PATH_VALUE.findall(line) if p.endswith(ends)} - seen
                if new:
                    seen |= new
                    if all(satisfied(r, seen) for r in need):
                        return seen


def main() -> None:
    if os.environ.get("CLAUDE_GUARD_OFF") == "1":
        return
    try:
        data = json.load(sys.stdin)
        inp = data.get("tool_input") or {}
        path = inp.get("file_path") or inp.get("notebook_path") or ""
        if not path or any(x in path for x in EXEMPT):
            return
        need = [r for r, rxs in rule_paths().items() if any(rx.match(path) for rx in rxs)]
        if not need:
            return
        need = [r for r in need if r not in injected_rules(data.get("agent_id"))]
        if not need:
            return
        tp = agent_transcript(data)
        if not tp:
            return
        seen = rule_paths_read(tp, need)
        missing = [r for r in need if not satisfied(r, seen)]
        if not missing:
            return
        reads = " and ".join(
            f"`Read ~/.claude/digests/rules/{r}` (current digest, smaller; or the full ~/.claude/rules/{r})"
            if digest_current(r) else f"`Read ~/.claude/rules/{r}`" for r in missing)
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"rules-gate: {os.path.basename(path)} is covered by {', '.join(missing)} "
                                        f"which is not in your context (path-scoped rules do not auto-load outside "
                                        f"the session's project dir) — {reads} first, follow it, then retry this edit.",
        }}))
    except Exception:
        return  # fail open


if __name__ == "__main__":
    main()
