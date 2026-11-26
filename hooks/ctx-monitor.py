#!/usr/bin/env python3
"""PostToolUse context monitor. Reads /tmp/claude-ctx-<session_id>.json (statusline.py); when missing/stale
(VSCode runs no statusline) usage = last assistant transcript record's (input + cache_creation + cache_read
tokens) / window; window = 1M by default, 200k for haiku or a settings.json "model" pinned without "[1m]".
Context-% reminders are DISABLED (owner 2026-10-03): the assumed 1M window is wrong for larger-window
sessions (a 15M session got "91 % — stop" at ~6 % real use). `ctx_msg()` is kept but not called; only the
task token budget below is active. Auto handoff before compaction stays (hooks/precompact-handoff.py).
Task token budget (rules/task-lifecycle.md): `ctx-monitor.py --budget 60M` (set by /spec; `off` removes it) writes
/tmp/claude-budget-<session_id>.json; every PostToolUse then adds the new transcript bytes of the session AND its
subagents (<transcript dir>/<sid>/subagents/*.jsonl), usage deduped by message.id, raw input + cache_creation +
cache_read + output. One line per crossed 10 % band (main thread only), firm line from 100 %; no hard stop.
Task summary (I9): a successful `gh pr create` / `tea pr create` appends one JSON line to ~/.claude/logs/task-summary.jsonl
(session, repo, branch, pr, tokens since the budget was armed, subagents) and drops /tmp/claude-pr-open-<sid>.json, which
statusline.py turns into the «PR открыт — /clear» hint until the next user prompt. Hint only, never a stop."""
import glob
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402  (hooks/_paths.py: portable roots)
import re
import subprocess
import sys
import time

WARN, STOP = 45, 70
CTX_1M, CTX_200K = 1_000_000, 200_000
TAIL_BYTES = 4_000_000   # last assistant usage record is always within the transcript tail
CTX_KEYS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
ALL_KEYS = CTX_KEYS + ("output_tokens",)
RECENT_IDS = 64   # same-id records (one per content block) are adjacent; a short window dedupes them


def used_from_file(f):
    try:
        u = json.load(open(f))
    except Exception:
        return None
    if u.get("used") is None or time.time() - (u.get("ts") or 0) > 900:
        return None
    return int(u["used"])


def used_from_transcript(tp):
    try:
        with open(tp, "rb") as fh:
            fh.seek(max(0, os.path.getsize(tp) - TAIL_BYTES))
            lines = fh.read().decode("utf-8", "ignore").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            rec = json.loads(line) if '"usage"' in line else {}
        except Exception:
            continue
        m = rec.get("message") or {}
        u = m.get("usage") if rec.get("type") == "assistant" else None
        if not isinstance(u, dict):
            continue
        try:
            # settings.json is the USER config: stays home-based, not plugin-relative
            cfg = str(json.load(open(_paths.user_dir("settings.json"))).get("model") or "")
        except Exception:
            cfg = ""
        total = sum(int(u.get(k) or 0) for k in CTX_KEYS)
        # The transcript model id NEVER carries "[1m]" and settings.json usually has no "model", so the old
        # "200k unless proven 1M" rule fired 45 % / 70 % at ~90k / ~140k on 1M sessions (found 2026-09-24:
        # a forced handoff at ~9 % real use). Default is now 1M; 200k only when settings pins a model without
        # "[1m]" or the model is a known 200k family (haiku).
        mid = str(m.get("model") or "")
        small = "haiku" in mid or (cfg and "[1m]" not in cfg)
        window = CTX_200K if small and total <= CTX_200K else CTX_1M
        return round(100 * total / window)
    return None


def handoff_path(cwd, date, sid8):
    try:
        root = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd, capture_output=True,
                              text=True, timeout=5).stdout.strip() or cwd
    except Exception:
        root = cwd
    if os.path.isdir(os.path.join(root, "docs", "project")):
        return os.path.join(root, "docs", "project", "tasks", f"handoff-{date}-{sid8}.md"), True
    proj = "-" + re.sub(r"[^A-Za-z0-9]", "-", root.strip("/"))
    return _paths.user_dir("projects", proj, "memory", f"handoff-{date}-{sid8}.md"), False


def budget_file(sid):
    return f"/tmp/claude-budget-{sid}.json"


def parse_tokens(v):
    """'60M' / '300k' / '2000000' → int tokens; ValueError otherwise."""
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([kKmM]?)\s*(?:tokens)?\s*", v or "")
    if not m:
        raise ValueError(f"budget must look like 300k / 60M / 2000000, got {v!r}")
    n = float(m.group(1)) * {"": 1, "k": 1_000, "m": 1_000_000}[m.group(2).lower()]
    if n <= 0:
        raise ValueError("budget must be > 0")
    return int(n)


def fmt(n):
    return f"{n / 1e6:.1f}M" if n >= 1_000_000 else f"{round(n / 1e3)}k"


def scan_new(path, seen):
    """Usage sums of complete lines appended since seen['off']; updates seen in place."""
    sums = dict.fromkeys(ALL_KEYS, 0)
    try:
        with open(path, "rb") as fh:
            fh.seek(seen.get("off", 0))
            chunk = fh.read()
    except OSError:
        return sums
    end = chunk.rfind(b"\n") + 1                       # a half-written tail line waits for the next run
    ids = seen.get("ids", [])
    for line in chunk[:end].decode("utf-8", "ignore").splitlines():
        if '"usage"' not in line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        m = rec.get("message")
        if rec.get("type") != "assistant" or not isinstance(m, dict) or not isinstance(m.get("usage"), dict):
            continue
        mid = m.get("id")
        if mid and mid in ids:
            continue
        ids = (ids + [mid])[-RECENT_IDS:] if mid else ids
        for k in ALL_KEYS:
            sums[k] += int(m["usage"].get(k) or 0)
    seen["off"], seen["ids"] = seen.get("off", 0) + end, ids
    return sums


def refresh_budget(st):
    """Add tokens written since the last run (session + subagents) to st['used'] / st['cache_read']."""
    tp = st.get("transcript") or ""
    files = [tp] + sorted(glob.glob(os.path.join(tp[:-6], "subagents", "*.jsonl"))) if tp.endswith(".jsonl") else []
    for f in files:
        sums = scan_new(f, st.setdefault("files", {}).setdefault(f, {}))
        st["used"] = st.get("used", 0) + sum(sums.values())
        st["cache_read"] = st.get("cache_read", 0) + sums["cache_read_input_tokens"]
    return st


def save(path, st):
    tmp = f"{path}.{os.getpid()}"
    with open(tmp, "w") as fh:
        json.dump(st, fh)
    os.replace(tmp, path)                       # sums and offsets land together: a lost race only re-reads bytes


def budget_line(st):
    used, limit, cr = st["used"], st["limit"], st.get("cache_read", 0)
    pct = 100 * used // limit
    split = f"{fmt(used)} / {fmt(limit)} tokens: fresh {fmt(used - cr)}, cache-read {fmt(cr)} (~0.1x price)"
    if pct >= 100:
        return (f"Task budget exhausted — budget {pct}% ({split}). Finish the current atomic step, write the handoff "
                f"(/handoff), then ask the owner to extend (ctx-monitor.py --budget <new>); no new steps until then.")
    return f"Task budget {pct}% ({split}) — keep to the spec scope."


def budget_msg(d):
    """One line when a new 10 % band of the task budget is crossed; None otherwise. Subagent calls only count."""
    path = budget_file(d.get("session_id"))
    try:
        st = json.load(open(path))
    except Exception:
        return None
    st["transcript"] = st.get("transcript") or d.get("transcript_path") or ""   # setter may run before the file exists
    refresh_budget(st)
    band = 10 * st["used"] // st["limit"]
    msg = None
    if band > st.get("band", 0) and not d.get("agent_id"):
        st["band"], msg = band, budget_line(st)
    st["ts"] = time.time()
    save(path, st)
    return msg


def set_budget(argv):
    """CLI: ctx-monitor.py --budget <300k|60M|off> [--session SID] [--transcript PATH]."""
    opts = dict(zip(argv[::2], argv[1::2]))
    sid = opts.get("--session") or os.environ.get("CLAUDE_CODE_SESSION_ID") or ""
    if not sid:
        sys.exit("no session id: pass --session or run inside Claude Code (CLAUDE_CODE_SESSION_ID)")
    path = budget_file(sid)
    if opts.get("--budget") == "off":
        if os.path.exists(path):
            os.remove(path)
        print(f"task budget off for {sid[:8]}")
        return
    try:
        limit = parse_tokens(opts.get("--budget"))
    except ValueError as e:
        print(e, file=sys.stderr)
        sys.exit(2)
    try:
        st = json.load(open(path))
    except Exception:
        found = glob.glob(_paths.user_dir("projects", "*", f"{sid}.jsonl"))
        st = {"transcript": opts.get("--transcript") or (found[0] if found else "")}
    st["limit"] = limit
    refresh_budget(st)
    st["band"], st["ts"] = 10 * st.get("used", 0) // limit, time.time()   # next reminder at the next 10 % band
    save(path, st)
    print(budget_line(st) if st["transcript"] else f"budget {fmt(limit)} set; transcript not found yet")


PR_CMD = re.compile(r"\b(?:gh|tea)\s+(?:pr|pulls?)\s+create\b")
PR_URL = re.compile(r"https?://\S+/pulls?/\d+")


def task_summary_path():
    return _paths.data_dir("logs", "task-summary.jsonl")


def record_pr(d, sid):
    """I9: append the task summary after a successful PR creation; silent on anything else."""
    ti = d.get("tool_input") or {}
    cmd = ti.get("command") or ""
    if d.get("tool_name") != "Bash" or not PR_CMD.search(cmd):
        return
    tr = d.get("tool_response")
    out = tr.get("stdout", "") if isinstance(tr, dict) else str(tr or "")
    m = PR_URL.search(out or "")
    if not m or (isinstance(tr, dict) and tr.get("interrupted")):
        return
    cwd = d.get("cwd") or os.getcwd()
    _, repo = run_git(cwd, "rev-parse", "--show-toplevel")
    _, branch = run_git(cwd, "rev-parse", "--abbrev-ref", "HEAD")
    tokens, subs = None, 0
    try:
        st = json.load(open(budget_file(sid)))
        tokens = refresh_budget(st).get("used")
        subs = len(glob.glob(os.path.join((st.get("transcript") or "")[:-6], "subagents", "*.jsonl")))
    except Exception:
        pass
    rec = {"ts": int(time.time()), "session": sid, "repo": os.path.basename(repo) or repo, "branch": branch,
           "pr": m.group(0), "tokens": tokens, "subagents": subs, "review_rounds": None}
    try:
        os.makedirs(os.path.dirname(task_summary_path()), exist_ok=True)
        with open(task_summary_path(), "a") as fh:
            fh.write(json.dumps(rec) + "\n")
        with open(f"/tmp/claude-pr-open-{sid}.json", "w") as fh:
            json.dump({"ts": time.time(), "pr": rec["pr"]}, fh)
    except OSError:
        pass


def run_git(cwd, *args):
    try:
        p = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=3)
        return p.returncode, p.stdout.strip()
    except Exception:
        return 1, ""


def ctx_msg(d, sid):
    used = used_from_file(f"/tmp/claude-ctx-{sid}.json")
    used = used_from_transcript(d.get("transcript_path") or "") if used is None else used
    if used is None or used < WARN:
        return None
    band, marker = used // 10, f"/tmp/claude-ctx-{sid}.band"
    try:
        last = int(open(marker).read().strip()) if os.path.exists(marker) else -1
    except Exception:
        last = -1
    if band <= last:
        return None
    try:
        open(marker, "w").write(str(band))
    except OSError:
        pass
    path, has_docs = handoff_path(d.get("cwd") or os.getcwd(), time.strftime("%Y-%m-%d"), sid[:8])
    state = ("и обнови docs/project/STATE.md «## Now» (ветка/worktree, PR, сделано, следующий шаг)" if has_docs
             else "и добавь строку-ссылку на него в MEMORY.md той же папки")
    if used >= STOP:
        return (f"КОНТЕКСТ {used}% — порог остановки. Заверши текущий атомарный шаг (не начинай новых). "
                f"ЗАПИШИ handoff в файл {path} (цель задачи, сделано, следующий шаг, открытые вопросы, "
                f"ветка/worktree/PR, команды для проверки) {state}. Затем скажи пользователю в одну строку: "
                f"«handoff записан, продолжить в новой сессии или /compact». Новая сессия подхватит STATE и handoff через SessionStart-хук.")
    return (f"Контекст {used}%. Запиши handoff сейчас (не позже следующего шага) в {path} "
            f"(цель, сделано, следующий шаг, открытые вопросы, ветка/worktree/PR, команды) {state}. "
            f"Продолжай работу; обновляй handoff после каждого крупного шага. Ресёрч и широкие поиски — субагентам.")


def main():
    if len(sys.argv) > 1:
        set_budget(sys.argv[1:])
        return
    try:
        d = json.load(sys.stdin)
    except Exception:
        return
    sid = d.get("session_id") or ""
    if not sid:
        return
    record_pr(d, sid)
    msgs = [m for m in (budget_msg(d),) if m]   # ctx_msg disabled, see docstring
    if msgs:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "\n".join(msgs)}}))


if __name__ == "__main__":
    main()
