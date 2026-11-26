#!/usr/bin/env python3
"""SubagentStart — put the stack rules (and the active lessons) into a subagent's context before its first prompt.

Documented contract (code.claude.com/docs/en/hooks, SubagentStart): input = common fields + `agent_id` + `agent_type`
(NO prompt, NO paths); output `hookSpecificOutput.additionalContext` is added to the subagent's context at the start of
its conversation; it cannot block. Therefore the rules are chosen by agent type only: ui-builder gets vue-ts,
design-ui-ux and ui-engineering-qa (§A–§D = the whole file); general-purpose / lite-worker get no rules (their file types
are unknown until they edit — rules-gate keeps denying until the rule is Read). Per rule: the current digest
(digests/rules/<name>, sha1 header equal to the source) else the source without frontmatter; a rule that does not fit
the cap is left out (and not recorded), so rules-gate still requires its Read.

Also: `python3 tools/lessons.py inject --agent-type <t>` (interface I3; absent → skipped silently).
Marker (interface I5): <root>/state/injected/<agent_id>.json {"rules": [...injected rule files...]} read by rules-gate.
Cap: CAP chars of additionalContext. Root: $CLAUDE_CONFIG_DIR or ~/.claude. Fails open (prints nothing). Off: CLAUDE_GUARD_OFF=1.
"""
import hashlib
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402  (hooks/_paths.py: portable roots)
import re
import subprocess
import sys
import time

ROOT = os.environ.get("CLAUDE_CONFIG_DIR") or _paths.user_dir()   # rules/digests live in the USER config
CAP = 12_000
RULES_BY_TYPE = {"ui-builder": ["vue-ts.md", "design-ui-ux.md", "ui-engineering-qa.md"]}
DIGEST_HEAD = re.compile(r"^<!-- digest of rules/(\S+) sha1=([0-9a-f]{40}) ")
LESSONS_TIMEOUT_S = 3


def resolve(name: str) -> str:
    """`name` under rules/, else under rules/maxforge/ (public-plugin install); the returned name is rules/-relative."""
    for cand in (name, "maxforge/" + name):
        if os.path.isfile(os.path.join(ROOT, "rules", cand)):
            return cand
    return name


def rule_text(name: str) -> str:
    """Current digest, else the rule source without frontmatter and blank lines; "" when unreadable."""
    try:
        with open(os.path.join(ROOT, "rules", name), "rb") as fh:
            raw = fh.read()
    except OSError:
        return ""
    try:
        with open(os.path.join(ROOT, "digests", "rules", name), encoding="utf-8", errors="ignore") as fh:
            head, body = fh.readline(), fh.read()
        m = DIGEST_HEAD.match(head)
        if m and m.group(1) == name and m.group(2) == hashlib.sha1(raw).hexdigest():
            return body.strip()
    except OSError:
        pass
    text = re.sub(r"\A---\n.*?\n---\n", "", raw.decode("utf-8", "ignore"), flags=re.S)
    return "\n".join(ln for ln in text.splitlines() if ln.strip())


def lessons(agent_type: str) -> str:
    tool = os.path.join(ROOT, "tools", "lessons.py")
    if not os.path.isfile(tool):
        return ""
    try:
        r = subprocess.run([sys.executable, tool, "inject", "--agent-type", agent_type], capture_output=True, text=True,
                           timeout=LESSONS_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def build(agent_type: str) -> tuple:
    """(additionalContext, injected rule names) within CAP."""
    extra = lessons(agent_type)
    parts, injected = [], []
    budget = CAP - len(extra) - 200
    for name in map(resolve, RULES_BY_TYPE.get(agent_type, [])):
        body = rule_text(name)
        block = f"## Stack rule rules/{name} (injected at start — do not Read it again)\n{body}"
        if body and len(block) + 2 <= budget:
            parts.append(block)
            injected.append(name)
            budget -= len(block) + 2
    if extra:
        parts.append(f"## Active lessons\n{extra}")
    return "\n\n".join(parts)[:CAP], injected


def write_marker(agent_id: str, agent_type: str, rules: list) -> None:
    folder = os.path.join(ROOT + "/state" if os.environ.get("CLAUDE_CONFIG_DIR") else _paths.data_dir("state"), "injected")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, f"{agent_id}.json"), "w", encoding="utf-8") as fh:
        json.dump({"rules": rules, "agent_type": agent_type, "ts": int(time.time())}, fh)


def main() -> None:
    if os.environ.get("CLAUDE_GUARD_OFF") == "1":
        return
    try:
        data = json.load(sys.stdin)
        agent_id, agent_type = str(data.get("agent_id") or ""), str(data.get("agent_type") or "")
        if not agent_type or not re.fullmatch(r"[\w.-]+", agent_id):
            return
        context, rules = build(agent_type)
        if rules:
            write_marker(agent_id, agent_type, rules)
        if context:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": context}}))
    except Exception:
        return  # fail open


if __name__ == "__main__":
    main()
