#!/usr/bin/env python3
"""Status line: model | dir (branch) | ctx NN% | budget NN% (only when a task budget is set) | Now: <first STATE task>.
Shows «PR открыт — /clear» after a PR was opened (marker from ctx-monitor.py) until the next user prompt, and
`hook-err N` = lines of logs/hook-errors.log written in the last 24 h. Also writes /tmp/claude-ctx-<session_id>.json {used, remaining, ts} for ctx-monitor.py."""
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402  (hooks/_paths.py: portable roots)
import re
import subprocess
import sys
import time
from datetime import datetime


def run(cmd, cwd):
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=2).stdout.strip()
    except Exception:
        return ""


HOOK_ERR_LOG = _paths.data_dir("logs", "hook-errors.log")
TS_RE = re.compile(r"^\[?(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}(?::\d{2})?)")


def hook_errors(now=None, path=HOOK_ERR_LOG):
    """Lines from the last 24 h; a line without a timestamp inherits the previous one (else the file mtime)."""
    now = now or time.time()
    try:
        mtime = os.path.getmtime(path)
        if now - mtime > 86400:
            return 0
        with open(path, "rb") as fh:
            fh.seek(max(0, os.path.getsize(path) - 262144))
            lines = fh.read().decode("utf-8", "ignore").splitlines()
    except OSError:
        return 0
    n, cur = 0, mtime
    for l in lines:
        m = TS_RE.match(l)
        if m:
            try:
                cur = time.mktime(time.strptime(f"{m.group(1)} {m.group(2)[:5]}", "%Y-%m-%d %H:%M"))
            except ValueError:
                pass
        if l.strip() and now - cur <= 86400:
            n += 1
    return n


def user_prompt_after(transcript, ts):
    """True when a real user prompt (not a tool result) newer than ts is in the transcript tail."""
    try:
        with open(transcript, "rb") as fh:
            fh.seek(max(0, os.path.getsize(transcript) - 65536))
            lines = fh.read().decode("utf-8", "ignore").splitlines()
    except OSError:
        return False
    for l in reversed(lines):
        if '"user"' not in l or "tool_result" in l:
            continue
        try:
            r = json.loads(l)
            c = (r.get("message") or {}).get("content")
            t = datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00")).timestamp()
        except Exception:
            continue
        if r.get("type") == "user" and not r.get("isSidechain") and (isinstance(c, str) or any(
                isinstance(b, dict) and b.get("type") == "text" for b in c or [])):
            return t > ts
    return False


def pr_hint(sid, transcript):
    marker = f"/tmp/claude-pr-open-{sid}.json"
    try:
        ts = json.load(open(marker)).get("ts") or 0
    except Exception:
        return ""
    if transcript and user_prompt_after(transcript, ts):
        try:
            os.remove(marker)
        except OSError:
            pass
        return ""
    return "PR открыт — /clear"


def main():
    try:
        d = json.load(sys.stdin)
    except Exception:
        return
    cwd = (d.get("workspace") or {}).get("current_dir") or d.get("cwd") or os.getcwd()
    model = (d.get("model") or {}).get("display_name") or (d.get("model") or {}).get("id") or "?"
    cw = d.get("context_window") or {}
    used = cw.get("used_percentage")
    if used is None and cw.get("context_window_size"):
        used = round(100 * (cw.get("total_input_tokens") or 0) / cw["context_window_size"])
    sid = d.get("session_id") or "unknown"
    try:
        with open(f"/tmp/claude-ctx-{sid}.json", "w") as fh:
            json.dump({"used": used, "remaining": cw.get("remaining_percentage"), "ts": time.time(),
                       "size": cw.get("context_window_size")}, fh)
    except OSError:
        pass
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd)
    now = ""
    for p in ("docs/project/STATE.md", ".planning/STATE.md"):
        f = os.path.join(cwd, p)
        if os.path.isfile(f):
            try:
                lines = open(f, encoding="utf-8", errors="ignore").read().splitlines()
                for i, l in enumerate(lines):
                    if l.startswith("## Now") or l.startswith("## Current Position"):
                        for l2 in lines[i + 1:i + 6]:
                            if l2.strip().startswith(("-", "Phase", "Status")):
                                now = l2.strip("- ").strip()[:60]
                                break
                        break
            except OSError:
                pass
            break
    ctx = f"ctx {used}%" if used is not None else "ctx ?"
    if used is not None and used >= 70:
        ctx += " ⚠ handoff"
    elif used is not None and used >= 45:
        ctx += " ↑"
    parts = [model, f"{os.path.basename(cwd)}" + (f" ({branch})" if branch else ""), ctx]
    try:  # task budget, as last counted by ctx-monitor.py (the status line never scans transcripts)
        b = json.load(open(f"/tmp/claude-budget-{sid}.json"))
        pct = 100 * b.get("used", 0) // b["limit"]
        parts.append(f"budget {pct}%" + (" ⚠ extend?" if pct >= 100 else ""))
    except Exception:
        pass
    hint = pr_hint(sid, d.get("transcript_path") or "")
    if hint:
        parts.append(hint)
    errs = hook_errors()
    if errs:
        parts.append(f"hook-err {errs}")
    if now:
        parts.append("Now: " + now)
    print(" | ".join(parts))


if __name__ == "__main__":
    main()
