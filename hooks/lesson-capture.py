#!/usr/bin/env python3
"""lesson-capture: UserPromptSubmit + Stop hook for the self-learning loop.

UserPromptSubmit: RU/EN regex prefilter on the owner's prompt; a hit is appended to
  ~/.claude/state/lesson-queue/<session>.jsonl and one `additionalContext` line nudges the agent.
Stop: if this session has unprocessed hits and no lessons/*.md was created/updated since the first one,
  block ONCE (then mark processed); never twice, never in subagents, always fail open.
Input fields (code.claude.com/docs/en/hooks): UserPromptSubmit {session_id, prompt, cwd};
  Stop {session_id, stop_hook_active, last_assistant_message} (no agent_id; subagents fire SubagentStop).
Env overrides (tests): LESSON_QUEUE_DIR, LESSONS_DIR.
"""
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402  (hooks/_paths.py: portable roots)
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LESSONS = os.environ.get("LESSONS_DIR") or os.path.join(os.path.dirname(HERE), "lessons")
QUEUE = os.environ.get("LESSON_QUEUE_DIR") or _paths.data_dir("state", "lesson-queue")
MAX_PROMPT = 2000  # longer = pasted logs/handoffs, not a correction

PATTERN = re.compile(
    r"не нравится|не понравил|опять|снова|я же (?:говорил|просил|писал|сказал)|убери|некрасив|не так\b|"
    r"переделай|хватит|не надо|зачем ты|сколько раз|"
    r"\bi (?:said|told you|asked)\b|stop doing|\bdon'?t\b|\bagain\b",
    re.I,
)

NUDGE = ("Possible owner correction: restate wrong/right; if it is a standing preference record it via the "
         "lesson skill (check-repeat first).")
BLOCK = ("Owner correction(s) from this session are not recorded in ~/.claude/lessons/: run the lesson skill "
         "(check-repeat -> new|repeat) or state in one line why it is not a standing preference.")


def read_input() -> dict:
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def queue_path(session: str) -> str:
    return os.path.join(QUEUE, re.sub(r"[^\w.-]", "_", session or "unknown") + ".jsonl")


def is_hit(prompt: str) -> bool:
    if not prompt or len(prompt) > MAX_PROMPT or prompt.lstrip().startswith(("/", "<")):
        return False
    return bool(PATTERN.search(prompt))


def append(path: str, rec: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def on_prompt(d: dict) -> None:
    prompt = d.get("prompt") or ""
    if not is_hit(prompt):
        return
    m = PATTERN.search(prompt)
    append(queue_path(d.get("session_id", "")), {"kind": "hit", "ts": time.time(), "match": m.group(0).lower(),
                                                 "text": prompt[:500], "cwd": d.get("cwd", "")})
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": NUDGE}},
                     ensure_ascii=False))


def unprocessed_first_ts(path: str):
    first = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("kind") == "processed":
                first = None
            elif r.get("kind") == "hit" and first is None:
                first = r.get("ts")
    return first


def lessons_touched_since(ts: float) -> bool:
    try:
        for n in os.listdir(LESSONS):
            if n.endswith(".md") and n not in ("INDEX.md", "rejected-ui.md"):
                if os.path.getmtime(os.path.join(LESSONS, n)) >= ts:
                    return True
    except OSError:
        pass
    return False


def on_stop(d: dict) -> None:
    if d.get("agent_id") or d.get("stop_hook_active"):
        return
    path = queue_path(d.get("session_id", ""))
    if not os.path.exists(path):
        return
    first = unprocessed_first_ts(path)
    if first is None:
        return
    append(path, {"kind": "processed", "ts": time.time()})  # mark first: guarantees never blocking twice
    if not lessons_touched_since(first):
        print(json.dumps({"decision": "block", "reason": BLOCK}, ensure_ascii=False))


def main() -> int:
    try:
        d = read_input()
        ev = d.get("hook_event_name") or ("Stop" if "stop_hook_active" in d else "UserPromptSubmit")
        (on_stop if ev == "Stop" else on_prompt)(d)
    except Exception as e:  # fail open
        print(f"lesson-capture: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
