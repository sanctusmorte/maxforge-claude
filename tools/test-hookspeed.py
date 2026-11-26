#!/usr/bin/env python3
"""Hook latency: wall time of the whole PreToolUse + PostToolUse chain for one Bash, one Read and one Edit call, with the
session transcript at HOOKSPEED_MB (default 160) MB. Compares BEFORE (live harness, default ~/.claude or
CLAUDE_HOOKSPEED_BEFORE) with AFTER (the repo this file lives in). Exit 1 when AFTER is slower than BEFORE by more than
BUDGET_MS per call (best of RUNS runs per hook; the hooks run one after another, the harness runs them in parallel,
so this is an upper bound). Chain = hooks registered in settings.json for the tool, in the shipped file names.
Synthetic transcript lives in $TMPDIR (else <repo>/tmp) and is deleted at the end. Disk: needs ~HOOKSPEED_MB free.
"""
import json
import os
import subprocess
import sys
import tempfile
import time

AFTER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BEFORE = os.environ.get("CLAUDE_HOOKSPEED_BEFORE") or os.path.expanduser("~/.claude")
MB = int(os.environ.get("HOOKSPEED_MB", "160"))
RUNS, BUDGET_MS = 9, 10.0
CHAIN = {  # tool → (PreToolUse hooks, PostToolUse hooks)
    "Bash": (["guard-bash.py", "dump-nudge.py", "secret-scan.py", "bg-router.py", "token-guard.py"],
             ["ctx-monitor.py", "token-guard.py"]),
    "Read": (["token-guard.py"], ["ctx-monitor.py", "token-guard.py"]),
    "Edit": (["rules-gate.py", "token-guard.py"], ["doc-sync-reminder.py", "ctx-monitor.py", "token-guard.py"]),
}


def make_transcript(path: str, big_file: str) -> None:
    def rec(kind, i):
        if kind == "use":
            return {"type": "assistant", "uuid": f"u{i}", "message": {"id": f"m{i}", "usage": {
                "input_tokens": 3, "cache_creation_input_tokens": 900, "cache_read_input_tokens": 120000 + i % 1000},
                "content": [{"type": "tool_use", "id": f"t{i}", "name": "Read",
                             "input": {"file_path": f"/home/user/proj/src/file{i % 500}.ts"}}]}}
        return {"type": "user", "uuid": f"r{i}", "message": {"content": [
            {"type": "tool_result", "tool_use_id": f"t{i}", "content": ("export const x = 1;\n" * 90)}]}}
    block = b"".join((json.dumps(rec(k, i)) + "\n").encode() for i in range(400) for k in ("use", "res"))
    mention = (json.dumps({"attachment": {"type": "nested_memory", "path": "/home/user/.claude/rules/python.md"}}) + "\n").encode()
    first = (json.dumps({"type": "assistant", "message": {"id": "m0", "content": [
        {"type": "tool_use", "id": "t0", "name": "Read", "input": {"file_path": big_file}}]}}) + "\n").encode()
    with open(path, "wb") as fh:
        fh.write(first)
        for _ in range(MB * 1_000_000 // len(block) + 1):
            fh.write(block + mention)


def payloads(tp: str, big_file: str, root: str) -> dict:
    base = {"session_id": "hookspeed-test", "transcript_path": tp, "cwd": root, "tool_use_id": "tcur"}
    return {
        "Bash": {**base, "tool_name": "Bash", "tool_input": {"command": "git status -sb"}},
        "Read": {**base, "tool_name": "Read", "tool_input": {"file_path": big_file}},
        "Edit": {**base, "tool_name": "Edit", "tool_input": {"file_path": "/home/user/worktrees/w/app/Models/A.php"}},
    }


def run_hook(harness: str, name: str, event: str, payload: dict) -> float:
    path = os.path.join(harness, "hooks", name)
    if not os.path.isfile(path):
        return 0.0
    env = {**os.environ, "CLAUDE_TOKEN_GUARD_LOG": os.devnull, "CLAUDE_CONFIG_DIR": harness}
    t0 = time.perf_counter()
    subprocess.run([sys.executable, path], input=json.dumps({**payload, "hook_event_name": event}), env=env,
                   capture_output=True, text=True, timeout=60)
    return (time.perf_counter() - t0) * 1000


def chain_ms(harness: str, tool: str, payload: dict) -> float:
    pre, post = CHAIN[tool]
    total = 0.0
    for event, names in (("PreToolUse", pre), ("PostToolUse", post)):
        for name in names:
            total += min(run_hook(harness, name, event, payload) for _ in range(RUNS))
    return total


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="hookspeed-", dir=os.environ.get("TMPDIR") or os.path.join(AFTER, "tmp")
                           if os.path.isdir(os.environ.get("TMPDIR") or os.path.join(AFTER, "tmp")) else None)
    try:
        big_file = os.path.join(tmp, "README.md")
        open(big_file, "w").write("line of text\n" * 3000)
        tp = os.path.join(tmp, "session.jsonl")
        make_transcript(tp, big_file)
        print(f"transcript {os.path.getsize(tp) // 1_000_000} MB; BEFORE={BEFORE} AFTER={AFTER}")
        if not os.path.isdir(os.path.join(BEFORE, "hooks")):   # plugin tree / fresh HOME: nothing to compare against
            print(f"SKIP: no BEFORE harness at {BEFORE} (set CLAUDE_HOOKSPEED_BEFORE)")
            return 0
        same = os.path.realpath(BEFORE) == os.path.realpath(AFTER)
        bad = 0
        for tool, payload in payloads(tp, big_file, AFTER).items():
            for _ in range(3):   # a loaded machine (e.g. inside test-hooks.py) skews one measurement: best of 3 attempts
                after = chain_ms(AFTER, tool, payload)
                before = after if same else chain_ms(BEFORE, tool, payload)
                if after - before <= BUDGET_MS:
                    break
            ok = after - before <= BUDGET_MS
            bad += 0 if ok else 1
            print(f"{'OK ' if ok else 'BAD'} {tool:<5} chain before {before:7.1f} ms  after {after:7.1f} ms  "
                  f"delta {after - before:+6.1f} ms (budget +{BUDGET_MS:.0f})")
        return 1 if bad else 0
    finally:
        subprocess.run(["rm", "-rf", tmp])


if __name__ == "__main__":
    sys.exit(main())
