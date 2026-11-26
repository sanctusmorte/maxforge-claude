#!/usr/bin/env python3
"""Self-test for hooks/rules-gate.py digest handling and tools/rules-digest.py. Temp CLAUDE_CONFIG_DIR; prints FAILS: N."""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.join(os.path.dirname(HERE), "hooks", "rules-gate.py")
TOOL = os.path.join(HERE, "rules-digest.py")
fails = 0

root = tempfile.mkdtemp(prefix="rdt-")   # not under /.claude/ or /tmp/-exempt paths: the gate only exempts edited files
os.makedirs(os.path.join(root, "rules"))
os.makedirs(os.path.join(root, "digests", "rules"))
SRC = os.path.join(root, "rules", "python.md")
DIG = os.path.join(root, "digests", "rules", "python.md")
open(SRC, "w").write('---\npaths:\n  - "**/*.py"\n---\n# Python rules\n- never float for money\n')
ENV = dict(os.environ, CLAUDE_CONFIG_DIR=root)
ENV.pop("CLAUDE_GUARD_OFF", None)


def write_digest(sha: str) -> None:
    open(DIG, "w").write(f"<!-- digest of rules/python.md sha1={sha} — stale? python3 "
                         f"~/.claude/tools/rules-digest.py --check -->\nnever float for money\n")


def src_sha() -> str:
    return hashlib.sha1(open(SRC, "rb").read()).hexdigest()


def gate(read_paths: list) -> str:
    tp = os.path.join(root, "t.jsonl")
    with open(tp, "w") as fh:
        fh.write('{"type":"user","message":{"content":"Read rules/python.md and digests/rules/python.md first"}}\n')
        for p in read_paths:
            fh.write(json.dumps({"message": {"content": [{"type": "tool_use", "name": "Read",
                                                          "input": {"file_path": p}}]}}) + "\n")
    d = {"session_id": "s", "transcript_path": tp, "tool_name": "Edit",
         "tool_input": {"file_path": "/home/user/worktrees/wt/app/main.py"}}
    return subprocess.run(["python3", GATE], input=json.dumps(d), capture_output=True, text=True, env=ENV).stdout


def check(label: str, ok: bool) -> None:
    global fails
    fails += 0 if ok else 1
    print(f"{'OK ' if ok else 'BAD'} {label}")


def tool(*args: str) -> int:
    return subprocess.run(["python3", TOOL, *args], capture_output=True, text=True, env=ENV).returncode


try:
    # no digest → source required; a mere mention in the prompt does not count
    out = gate([])
    check("no digest, nothing read → deny", '"deny"' in out)
    check("no digest → deny names only the source", "rules/python.md" in out and "digests/rules" not in out)
    check("no digest, source Read → allow", gate([SRC]) == "")

    write_digest(src_sha())
    out = gate([])
    check("current digest, nothing read → deny names digest first",
          '"deny"' in out and 0 <= out.find("digests/rules/python.md") < out.find("/.claude/rules/python.md"))
    check("current digest Read → allow", gate([DIG]) == "")
    check("source Read still accepted with a digest present", gate([SRC]) == "")
    check("--check exit 0 when current", tool("--check") == 0)

    open(SRC, "a").write("- new norm\n")   # source changed → digest stale
    check("stale digest Read → deny", '"deny"' in gate([DIG]))
    out = gate([])
    check("stale digest → deny text names only the source", "digests/rules" not in out and "rules/python.md" in out)
    check("stale digest, source Read → allow", gate([SRC]) == "")
    check("--check exit 1 when stale", tool("--check") == 1)
    check("--stamp then --check exit 0", tool("--stamp", "python.md") == 0 and tool("--check") == 0)

    os.remove(SRC)
    check("--check exit 1 when source gone", tool("--check") == 1)
    check("--paths exit 0", tool("--paths") == 0)
    env_off = dict(ENV, CLAUDE_GUARD_OFF="1")
    open(SRC, "w").write('---\npaths:\n  - "**/*.py"\n---\nx\n')
    d = {"session_id": "s", "transcript_path": os.path.join(root, "t.jsonl"), "tool_name": "Edit",
         "tool_input": {"file_path": "/home/user/worktrees/wt/app/main.py"}}
    out = subprocess.run(["python3", GATE], input=json.dumps(d), capture_output=True, text=True, env=env_off).stdout
    check("CLAUDE_GUARD_OFF=1 escape → allow", out == "")
    out = subprocess.run(["python3", GATE], input="not json", capture_output=True, text=True, env=ENV)
    check("garbage input → fail open", out.stdout == "" and out.returncode == 0)
finally:
    shutil.rmtree(root, ignore_errors=True)

print(f"FAILS: {fails}")
raise SystemExit(1 if fails else 0)
