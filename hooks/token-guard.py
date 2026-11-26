#!/usr/bin/env python3
"""PreToolUse (+ PostToolUse series nudge) token guard. Measured 2026-10-09 (7 days, 55.9k calls, scratchpad token_audit.py): subagents 91.6 % of
weighted cost, calls with >200k context 71.6 %, cache rebuilds after >5 min idle 15 %, Read results 15.4 %. A call
costs ~0.1 × its whole context, so anything in context costs size × remaining calls. Gates, one deny line each:

1. Context fence (subagents only): the agent's last call used ≥ FENCE context tokens → every tool is denied except
   Write/Edit of a file named *handoff* and git bookkeeping. The agent writes the handoff and hands back
   `FENCE-HANDOFF <path>`; the caller continues with a FRESH agent (rules/task-lifecycle.md §Spend).
2. No idle waits (subagents only): Bash `timeout` > 280 s, `sleep` ≥ 120 s in total, sleep inside an until/while loop
   (unless wrapped in `timeout ≤240`), `gh … --watch` / `gh run watch`. Subagent cache TTL is 5 min: one gap
   re-writes the whole context. Waiting is the caller's job.
3. Big reads (all sessions): Read without `limit` of a text file > READ_MAX bytes, or > DUMP_MAX for saved output
   (SAVED_OUTPUT: tool-results, scratchpad, logs, text/json under artifacts|/tmp). Deny names `tools/outline`.
4. Rewrite by Write (all sessions): Write over an existing file of > REWRITE_LINES lines that keeps ≥ 60 % of its
   lines → Edit (Write content is billed as output, 5× price, and stays in context).

5. Full local suites (all sessions): `php artisan test` / phpunit / pest / paratest / `composer test` / `playwright test`
   without a scope (--filter, --testsuite, --group, --grep, a test path) → the full suite is CI's job on push.
   `FULL_SUITE=1` in the command = deliberate full run.
6. Re-read (all sessions): a whole-file Read (no limit) of a file > REREAD_MIN bytes this agent already read whole →
   ranged Read / Grep (it is in context; after your own Edit the Edit result shows the change).
7. Raw test output (all sessions): playwright / vitest / jest / artisan test / phpunit / pest not wrapped in `q`,
   not redirected to a file, not piped to tail/grep, no dot/line reporter → wrap in ~/.claude/tools/q.
8. Resume (all sessions): SendMessage to an agent of this session at ≥ fence context, or ≥ RESUME_COLD_MAX and idle
   > 5 min (cache gone) → spawn a fresh agent from its handoff/report (orch audit: resumes at median 270k = $2k/week).
9. Agent output (all sessions): Read/Bash of `/tasks/a<16 hex>.output` (a subagent's JSONL) → wait for the notification.
10. Polling (subagents only): a 3rd wait turn in a row (parallel calls of one message = one turn) → hand back
   `pending: …`. Wait = `sleep N` / --watch (also in `bash -c '…'` or a heredoc fed to a shell), or a re-check of the
   same target (gh run view <id> without --log/--job, gh pr checks, tail/cat of one /tasks/…output or *.log).
Fence skeleton: the first fence deny writes HANDOFF_DIR/<sid8>-<agent>-handoff.md from the agent's transcript (prompt,
reads, edits, git/test commands, TODO sections; secrets redacted); the agent fills the TODOs with Edit.
Per-type fence: FENCE_BY_TYPE (`claude` coordinators 200k; general-purpose 220k, ui-builder 300k; owner 2026-10-10: +100k each).
Digests: a denied big Read names ~/.claude/digests/<name>-<hash>.md — current digest → read it first; none → the
reader writes one (≤60 lines, symbols with line numbers) so the next agent does not re-read the whole file.
PostToolUse (same script): a series of SERIES_STEP consecutive calls of the same tool (Bash/Read/Grep/Glob/Edit)
gets a one-line nudge to batch — every call re-sends the whole context.

Env: CLAUDE_CTX_FENCE (tokens, default 260000, 0 = fence off), CLAUDE_TOKEN_GUARD_OFF=1 (all gates off).
"""
import hashlib
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402  (hooks/_paths.py: portable roots)
import re
import sys
import time

FENCE_DEFAULT = 260_000  # owner 2026-10-10: every fence +100k (was 160k; claude 100k, gp 120k, ui-builder 200k)
# coordinators: 32k start, 76 % of their cost was ≥160k (orch audit 2026-10-09)
# experiment 2026-10-09 (one week, owner-approved): general-purpose 120k, ui-builder 200k (screenshots need room)
FENCE_BY_TYPE = {"claude": 200_000, "general-purpose": 220_000, "ui-builder": 300_000}
RESUME_COLD_MAX = 100_000             # SendMessage into an idle agent at ≥ this context → fresh agent instead
CACHE_TTL_S = 300
AGENT_OUTPUT = re.compile(r"/tasks/a[0-9a-f]{16}\.output\b")   # a subagent's full JSONL transcript
TAIL_BYTES = 2_000_000
CTX_KEYS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
READ_MAX = 32_000   # 2026-10-17: 12 KB denied 9 of 29 calls in one session (each deny = a lost turn); the native
DUMP_MAX = 32_000   # cap CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS=12000 already truncates — deny only clearly big files
REWRITE_LINES = 150
REWRITE_KEEP = 0.6
MAX_BASH_TIMEOUT_MS = 280_000
MAX_SLEEP_S = 120
LOOP_TIMEOUT_S = 240
WORK_TOOLS = {"Read", "Grep", "Glob", "NotebookEdit", "Agent", "Task", "WebFetch", "WebSearch", "Skill", "Monitor",
              "LSP"}
BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".ipynb"}
HANDOFF_DIR = os.environ.get("CLAUDE_HANDOFF_DIR") or _paths.data_dir("handoffs")
PAYLOAD = {}   # the hook input, for the deny log
LOG = os.environ.get("CLAUDE_TOKEN_GUARD_LOG") or _paths.data_dir("logs", "token-guard.log")   # one line per deny / unresolved agent transcript
TOOLS = _paths.tilde(_paths.harness_dir("tools"))   # display form; ~/.claude/tools for the owner
DIGEST_DIR = _paths.data_dir("digests")
SUITE = re.compile(r"\b(php\s+artisan\s+test|vendor/bin/(phpunit|pest|paratest)|composer\s+test|playwright\s+test)\b")
SUITE_SCOPE = re.compile(r"--filter\b|--testsuite\b|--group\b|--grep\b|\s-g\s|::|(^|\s)\S*tests?/\S+|\S+\.(php|spec\.[jt]s|test\.[jt]s)\b")
REREAD_MIN = 8_000
SAVED_OUTPUT = re.compile(r"/tool-results/|\.output$|/scratchpad/|\.log(\.\d+)?$|"
                          r"(/artifacts/|^/tmp/|/\.claude/tmp/).*\.(txt|json|jsonl|log|html|xml|csv)$")
TEST_RUN = re.compile(r"\b(playwright\s+test|vitest|jest|php\s+artisan\s+test|vendor/bin/(phpunit|pest|paratest))\b")
TEST_QUIET = re.compile(r"(^|[\s;&|(])(\S*/)?q\s|>\s*[^&\s]|\|\s*(tail|grep|head)\b|--reporter[= ](dot|line)|--quiet\b|-q\b")
TEXT_CMDS = {"grep", "rg", "echo", "printf", "git", "cat", "sed", "awk"}   # the suite command is text, not a run
SERIES_TOOLS = {"Bash", "Read", "Grep", "Glob", "Edit"}
SERIES_STEP = 8
GIT_SEGMENT = re.compile(r"^\s*(\(?\s*cd\s+\S+|git\s|gh\s+pr\s+(view|create|edit|comment)\b|mkdir\s)")
QUOTED = re.compile(r"'[^']*'|\"(?:\\.|[^\"\\])*\"")  # bash quoting: no escapes inside '…'
# audit 2026-10-09: subagent polling = until/while+sleep loops 673 calls $310, sleep+tail 447 $148, tail .output 201 $93,
# gh pr checks/run view 178 $38 → the 3rd wait turn in a row is denied. Review 2026-10-09: a wait = a real sleep or
# --watch, or a re-check of the SAME target (run id, PR, output/log file); different logs = debugging, `--log`/`--job`
# = reading a failure, `grep sleep` / `--sleep=0` / a `while read` loop = not a wait; parallel calls = one turn.
SLEEP_CMD = re.compile(r"(?<![\w-])sleep\s+\d")
WATCH_CMD = re.compile(r"\bgh\s+run\s+watch\b|\bgh\b[^\n|;&]*--watch\b")
PROBE = re.compile(r"\bgh\s+run\s+view\s+(\d+)(?![^\n|;&]*--(?:log|job))|\bgh\s+pr\s+checks\b\s*(\d*)|"
                   r"\b(?:tail|cat)\b[^|;&\n]*?(\S*/tasks/\S*output|\S+\.log)\b")
BASH_C = re.compile(r"\b(?:bash|sh|zsh)\s+(?:-\w+\s+)*-\w*c\s+(?:'([^']*)'|\"((?:\\.|[^\"\\])*)\")")
SHELL_HEREDOC = re.compile(r"\b(?:bash|sh|zsh|ssh)\b[^<\n]*<<|<<.*\|\s*(?:bash|sh|zsh)\b")   # a shell runs the body
POLL_RUN = 2           # previous wait turns that make the next wait a poll
SKEL_PROMPT = 1_500
SKEL_LIST = 40
SKEL_CMDS, SKEL_CMD_LEN = 10, 160
SKEL_CMD = re.compile(r"\b(git|gh)\s|\b(test|tests|pytest|phpunit|pest|paratest|vitest|jest|playwright|build|tsc|lint|"
                      r"phpstan|affected-tests)\b|test-hooks\.py")
# review 2026-10-09: `DB_PASSWORD=`, `*_TOKEN=`, `*_API_KEY=`, `scheme://u:pw@`, ghp_/glpat-, `-pPASS`, `--password X`
# slipped through (17 of 599 real skeletons); prefixes as in secret-scan.py
SECRETS = [(re.compile(r"(?<![A-Za-z0-9])(?:sk-[A-Za-z0-9_-]{8,}|[sr]k_(?:live|test)_[A-Za-z0-9]{8,}|"
                       r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_-]{10,}|"
                       r"xox[abprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,}|\d{8,10}:[A-Za-z0-9_-]{35})"),
            "[REDACTED]"),
           (re.compile(r"(://[^\s/:@]+:)[^\s@]+@"), r"\1[REDACTED]@"),
           (re.compile(r"(\bBearer\s+|\bAuthorization:\s*(?:token|basic|bearer)?\s*)[A-Za-z0-9._~+/=-]{6,}", re.I),
            r"\1[REDACTED]"),
           (re.compile(r"(\b[\w.-]*(?:pass(?:word|wd)?|secret|token|api_?key|credential|private_?key)\w*['\"]?\s*[=:]\s*)"
                       r"['\"]?[^\s'\"&;,]+", re.I), r"\1[REDACTED]"),
           (re.compile(r"(--(?:password|pass|token|secret|api-?key)[= ]\s*)['\"]?[^\s'\"]+", re.I), r"\1[REDACTED]"),
           (re.compile(r"(\b(?:mysql|mysqldump|mariadb|mysqladmin)\b[^\n|;&]*?\s-p)(?=[^\s-])\S+"), r"\1[REDACTED]")]
REDACT_MARGIN = 200    # redact before cutting (a secret across the cut must not survive half-masked), bounded input


def log(event, d, reason=""):
    """One JSON line per deny: event (gate), reason (deny text, 200 chars), path or first 120 chars of the command
    (secrets redacted), session, agent_type — enough to tell a repeat from a new event without the transcript."""
    ti = d.get("tool_input") or {}
    target = {"path": ti["file_path"]} if ti.get("file_path") else (
        {"cmd": redact((ti.get("command") or "")[:120 + REDACT_MARGIN])[:120]} if ti.get("command") else {})
    try:
        with open(LOG, "a") as fh:
            fh.write(json.dumps({"ts": int(time.time()), "event": event, "tool": d.get("tool_name"),
                                 "agent": d.get("agent_type") or d.get("agent_id") or "main", "reason": reason[:200],
                                 **target, "session": d.get("session_id") or "",
                                 "agent_type": d.get("agent_type") or ""}) + "\n")
    except OSError:
        pass


def deny(gate, reason, nxt):
    """The deny text always ends with exactly one concrete next step (each deny costs the model a turn)."""
    text = f"{reason} Next: {nxt}"
    log(gate, PAYLOAD, text)
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": "token-guard: " + text,
    }}))
    sys.exit(0)


def agent_transcript(d):
    """The subagent's own transcript: <dir>/<session_id>/subagents/agent-<agent_id>.jsonl."""
    if d.get("agent_transcript_path"):
        return d["agent_transcript_path"]
    tp, sid, aid = d.get("transcript_path") or "", d.get("session_id") or "", d.get("agent_id") or ""
    if os.path.basename(tp) == f"agent-{aid}.jsonl":
        return tp
    return os.path.join(os.path.dirname(tp), sid, "subagents", f"agent-{aid}.jsonl")


def last_context(path):
    """Context tokens of the last assistant call in the transcript, None when unknown."""
    try:
        with open(path, "rb") as fh:
            fh.seek(max(0, os.path.getsize(path) - TAIL_BYTES))
            lines = fh.read().decode("utf-8", "ignore").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        if '"usage"' not in line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        u = (rec.get("message") or {}).get("usage") if rec.get("type") == "assistant" else None
        if isinstance(u, dict):
            return sum(int(u.get(k) or 0) for k in CTX_KEYS)
    return None


def fence_limit(agent_type=""):
    """CLAUDE_CTX_FENCE overrides everything; else the per-type fence; else FENCE_DEFAULT."""
    try:
        return int(os.environ["CLAUDE_CTX_FENCE"])
    except (KeyError, ValueError):
        return FENCE_BY_TYPE.get(agent_type or "", FENCE_DEFAULT)


def fence_allows(tool, ti):
    """Fenced agents keep bookkeeping (hand-back, messages, todos, handoff file, git); work tools are denied."""
    if tool in ("Write", "Edit", "MultiEdit", "Read"):   # Read: Edit of the skeleton needs a prior Read
        return "handoff" in os.path.basename(ti.get("file_path") or "").lower()
    if tool == "Bash":
        # separators inside a quoted / heredoc commit message are text, not commands (audit 2026-10-09: WIP commits denied)
        cmd = QUOTED.sub("''", strip_heredocs(ti.get("command") or ""))
        segs = [s for s in re.split(r"&&|\|\||;|\n", cmd) if s.strip()]
        return bool(segs) and all(GIT_SEGMENT.match(s) for s in segs)
    return tool not in WORK_TOOLS and not tool.startswith("mcp__")


def check_fence(d, tool, ti):
    limit = fence_limit(d.get("agent_type"))
    if limit <= 0:
        return
    path = agent_transcript(d)
    if not os.path.exists(path):
        log("fence-unresolved", {**d, "tool_name": f"{d.get('tool_name')} {path}"})
    ctx = last_context(path)
    if ctx is None or ctx < limit or fence_allows(tool, ti):
        return
    handoff = os.path.join(HANDOFF_DIR, f"{(d.get('session_id') or 'x')[:8]}-{d.get('agent_id')}-handoff.md")
    if write_handoff_skeleton(d, path, handoff):
        deny("fence", f"context fence — this agent is at {ctx // 1000}k context (limit {limit // 1000}k); every further "
             f"call re-sends all of it. Stop working now. A handoff skeleton (prompt, files read/edited, last git/test "
             f"commands) exists at {handoff}; fill its TODO lines with Edit (no rewrite: next atomic step + exact "
             f"path:line ranges, done with evidence, dead ends), commit + push WIP (git only), then hand back with "
             f"first line `FENCE-HANDOFF {handoff}` — a fresh agent continues from it.",
             f"Read {handoff} once, then Edit its TODO lines")
    deny("fence", f"context fence — this agent is at {ctx // 1000}k context (limit {limit // 1000}k); every further call "
         f"re-sends all of it. Stop working now: commit + push WIP (git only), Write the handoff to {handoff} (goal, done "
         f"with evidence, next atomic step + the exact path:line ranges it needs — the fresh agent reads only those, "
         f"branch/worktree/PR, commands, dead ends, open questions), then hand "
         f"back with first line `FENCE-HANDOFF {handoff}` — a fresh agent continues from it.",
         f"Write {handoff} with the handoff text")


def redact(text):
    for rx, sub in SECRETS:
        text = rx.sub(sub, text)
    return text


def remember(seen, key):
    """Ordered unique list, most recent last."""
    seen.pop(key, None)
    seen[key] = True


def message_text(content):
    if isinstance(content, str):
        return content
    return "\n".join(c.get("text") or "" for c in content or [] if isinstance(c, dict) and c.get("type") == "text")


def scan_transcript(path):
    """One pass over the agent transcript → prompt, cwd, branch, reads, edits, git/test commands."""
    info = {"prompt": None, "cwd": "", "branch": "", "reads": {}, "edits": {}, "cmds": []}
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            info["cwd"] = rec.get("cwd") or info["cwd"]
            info["branch"] = rec.get("gitBranch") or info["branch"]
            msg = rec.get("message") or {}
            if rec.get("type") == "user" and info["prompt"] is None and message_text(msg.get("content")).strip():
                info["prompt"] = message_text(msg.get("content"))
            if rec.get("type") != "assistant":
                continue
            for c in msg.get("content") or []:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    note_tool_use(info, c.get("name"), c.get("input") or {})
    return info


def note_tool_use(info, name, inp):
    if name == "Read" and inp.get("file_path"):
        rng = f":{inp.get('offset') or 1}+{inp['limit']}" if inp.get("limit") else ""
        remember(info["reads"], inp["file_path"] + rng)
    elif name in ("Edit", "Write", "MultiEdit") and inp.get("file_path"):
        remember(info["edits"], inp["file_path"])
    elif name == "Bash":
        cmd = strip_heredocs(inp.get("command") or "").strip()
        if cmd and SKEL_CMD.search(QUOTED.sub("''", cmd)):
            info["cmds"].append(redact(" ".join(cmd.split())[:SKEL_CMD_LEN + REDACT_MARGIN])[:SKEL_CMD_LEN])


def write_handoff_skeleton(d, transcript, handoff):
    """Pre-filled handoff at the first fence deny (audit 2026-10-09: continuations spent 53 % of their $ before the
    first edit). Never overwrites; any failure → False (fail open: the plain fence deny still applies)."""
    if os.path.exists(handoff):
        return True
    try:
        info = scan_transcript(transcript)
        def listing(items):
            return "\n".join(f"- {x}" for x in items) or "- (none)"
        text = "\n".join([
            f"# FENCE handoff — {d.get('agent_type') or 'agent'}",
            f"session {d.get('session_id') or '?'} · agent {d.get('agent_id')} · "
            f"{time.strftime('%Y-%m-%dT%H:%MZ', time.gmtime())}",
            f"cwd: {info['cwd'] or '?'} · branch: {info['branch'] or '?'}", "",
            "## Delegation prompt", redact((info["prompt"] or "(not found)")[:SKEL_PROMPT + REDACT_MARGIN])[:SKEL_PROMPT], "",
            "## Read so far", listing(list(info["reads"])[-SKEL_LIST:]), "",
            "## Edited/Written", listing(list(info["edits"])[-SKEL_LIST:]), "",
            "## Last git/test commands", listing(info["cmds"][-SKEL_CMDS:]), "",
            "## Goal", "TODO", "",
            "## Done (with evidence)", "TODO", "",
            "## Next atomic step", "TODO", "",
            "## Exact path:line ranges the next step needs", "TODO", "",
            "## Dead ends", "TODO", "",
            "## Open questions", "TODO", ""])
        os.makedirs(HANDOFF_DIR, exist_ok=True)
        with open(handoff, "x", encoding="utf-8") as fh:
            fh.write(redact(text))
        return True
    except Exception:   # fail open: a broken skeleton must never block the fence deny
        return False


def sleep_seconds(cmd):
    total = 0.0
    for n, unit in re.findall(r"(?<![\w-])sleep\s+(\d+(?:\.\d+)?)([smh]?)\b", cmd):
        total += float(n) * {"": 1, "s": 1, "m": 60, "h": 3600}[unit]
    return total


def check_wait(tool, ti):
    if tool != "Bash" or ti.get("run_in_background"):
        return
    cmd = exec_text(ti.get("command") or "")   # text is not a wait (a heredoc or commit message mentioning "sleep 673")
    why = None
    if int(ti.get("timeout") or 0) > MAX_BASH_TIMEOUT_MS:
        why = f"Bash timeout {int(ti['timeout']) // 1000}s"
    elif WATCH_CMD.search(cmd):
        why = "a --watch wait"
    elif sleep_seconds(cmd) >= MAX_SLEEP_S:
        why = f"sleep {int(sleep_seconds(cmd))}s"
    elif re.search(r"\b(until|while)\b", cmd) and SLEEP_CMD.search(cmd):
        capped = [int(n) for n in re.findall(r"\btimeout\s+(\d+)s?\b", cmd)]
        if not capped or max(capped) > LOOP_TIMEOUT_S:
            why = f"a sleep poll loop without `timeout ≤{LOOP_TIMEOUT_S}`"
    if why:
        deny("wait", f"{why} in a subagent — its prompt cache lives 5 min, a longer idle gap re-pays the whole context. "
             f"Waiting is the caller's job (split work to ≤240 s per call, run_in_background for servers).",
             "end your turn with the hand-back `pending: <run id / command to check>`")


def exec_text(cmd):
    """What the shell runs: quoted text and text heredocs dropped, `bash -c '…'` bodies and heredocs fed to a shell
    kept (review 2026-10-09: `git commit -m "drop sleep 300"` counted as a wait, `bash <<X` + sleep 600 did not)."""
    cmd = strip_heredocs(cmd, keep_shell=True)
    return "\n".join([QUOTED.sub("''", cmd)] + [a or b for a, b in BASH_C.findall(cmd)])


def wait_kind(tool, ti):
    """None, "sleep" (a real wait) or "probe:<targets>" (a status check — a poll only when the target repeats)."""
    if tool != "Bash" or ti.get("run_in_background"):
        return None
    text = exec_text(ti.get("command") or "")
    if SLEEP_CMD.search(text) or WATCH_CMD.search(text):
        return "sleep"
    targets = sorted({"|".join(g or "" for g in m.groups()) for m in PROBE.finditer(text)})
    return "probe:" + ",".join(targets) if targets else None


def previous_turns(d, n):
    """The agent's last n finished turns before the current one, each = the (name, input) calls of one assistant
    message. The current message (holds tool_use_id, or calls without a result yet) is not a previous turn."""
    path = agent_transcript(d)
    try:
        with open(path, "rb") as fh:
            fh.seek(max(0, os.path.getsize(path) - 400_000))
            lines = fh.read().decode("utf-8", "ignore").splitlines()
    except OSError:
        return []
    turns, answered = {}, set()   # message id → its tool uses, in transcript order
    for line in lines:
        if '"tool_use"' not in line and '"tool_result"' not in line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        content = (rec.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        if rec.get("type") == "assistant":
            uses = [c for c in content if isinstance(c, dict) and c.get("type") == "tool_use"]
            if uses:
                turns.setdefault((rec.get("message") or {}).get("id") or rec.get("uuid"), []).extend(uses)
        elif rec.get("type") == "user":
            answered.update(c.get("tool_use_id") for c in content if isinstance(c, dict) and c.get("type") == "tool_result")
    order = list(turns.values())
    current = [i for i, uses in enumerate(order) if d.get("tool_use_id") in {u.get("id") for u in uses}]
    if current:
        order = order[:current[0]]
    elif order and any(u.get("id") not in answered for u in order[-1]):
        order = order[:-1]   # in flight: earlier siblings of the current call
    return [[(u.get("name") or "", u.get("input") or {}) for u in uses] for uses in order[-n:]]


def check_poll(d, tool, ti):
    kind = wait_kind(tool, ti)
    if not kind:
        return

    def waited(turn):   # waits only, and a probe counts only next to a sleep or a re-check of the same target
        kinds = [wait_kind(name, inp) for name, inp in turn]
        return all(kinds) and (kind == "sleep" or "sleep" in kinds or kind in kinds)
    turns = previous_turns(d, POLL_RUN)
    if len(turns) == POLL_RUN and all(waited(t) for t in turns):
        deny("poll", "polling — this is the 3rd wait in a row; every check re-sends your whole context; the main session "
             "watches the job.", "end your turn with the hand-back `pending: <job/run id + what to check>`")


def digest_path(path):
    real = os.path.realpath(path)
    return os.path.join(DIGEST_DIR, f"{os.path.basename(real)}-{hashlib.sha1(real.encode()).hexdigest()[:10]}.md")


def check_read(ti):
    path = ti.get("file_path") or ""
    if ti.get("limit") or os.path.splitext(path)[1].lower() in BINARY_EXT:
        return
    try:
        size = os.path.getsize(path)
    except OSError:
        return
    saved = bool(SAVED_OUTPUT.search(path))
    cap = DUMP_MAX if saved else READ_MAX
    if size <= cap:
        return
    kind = "saved output" if saved else "file"
    hint = ""
    if not saved:
        dg = digest_path(path)
        current = os.path.exists(dg) and os.path.getmtime(dg) >= os.path.getmtime(path)
        hint = (f" Current digest: Read {dg} first." if current else
                f" No digest yet: once you know the file, Write a ≤60-line digest (purpose, key symbols with line "
                f"numbers) to {dg} for the next agent.")
    deny("read", f"{kind} {path} is {size // 1000} KB; a whole-file Read stays in context for every later call. "
         f"Map it first: {TOOLS}/outline {path} (symbols/headings with line numbers; one symbol: --sym <name>), "
         f"or Grep -n; Read slices of ≤300 lines.{hint}", f"{TOOLS}/outline {path}")


COMPACT_MARKS = (b'"subtype":"compact_boundary"', b'"isCompactSummary":true')   # transcript lines the harness writes


def after_last_compaction(raw):
    """Bytes from the last compaction boundary on (a Read before it is no longer in context); all when none."""
    cut = max(raw.rfind(m) for m in COMPACT_MARKS)
    return raw[cut:] if cut >= 0 else raw


def read_results(rec):
    """tool_use_id → ok for the tool_results of one user record (denied / errored Reads are not in context)."""
    out = {}
    for c in (rec.get("message") or {}).get("content") or []:
        if isinstance(c, dict) and c.get("type") == "tool_result":
            out[c.get("tool_use_id")] = not c.get("is_error") and not message_text(c.get("content")).startswith(
                ("token-guard:", "rules-gate:", "dump-nudge:"))
    return out


def already_read_whole(d, path):
    """True when an EARLIER whole-file Read of path got a successful result after the last compaction boundary. The
    current call (its tool_use is already in the transcript when the hook runs) and denied/errored Reads do not count
    (2026-11-25: the first Read of README.md was denied as "already Read whole")."""
    tp = agent_transcript(d) if d.get("agent_id") else d.get("transcript_path") or ""
    needle = json.dumps(path)[1:-1].encode()
    try:
        with open(tp, "rb") as fh:
            fh.seek(max(0, os.path.getsize(tp) - 8_000_000))
            raw = after_last_compaction(fh.read())
    except OSError:
        return False
    if needle not in raw:
        return False
    current, reads, ok = d.get("tool_use_id"), set(), set()
    for line in raw.decode("utf-8", "ignore").splitlines():
        if '"tool_use' not in line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("type") == "user":
            ok.update(i for i, good in read_results(rec).items() if good)
            continue
        for c in (rec.get("message") or {}).get("content") or []:
            if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") == "Read":
                inp = c.get("input") or {}
                if inp.get("file_path") == path and not inp.get("limit") and c.get("id") != current:
                    reads.add(c.get("id"))
    return bool(reads & ok)


def check_reread(d, ti):
    path = ti.get("file_path") or ""
    if ti.get("limit") or os.path.splitext(path)[1].lower() in BINARY_EXT:
        return
    try:
        if os.path.getsize(path) <= REREAD_MIN:
            return
    except OSError:
        return
    if already_read_whole(d, path):
        deny("reread", f"{path} was already Read whole in this agent (after the last compaction) — it is still in "
             f"context; your own Edit results show the changes.", f"Read {path} with offset=<line> limit=120")


def strip_heredocs(cmd, keep_shell=False):
    """Command text without heredoc bodies (script text is not a command run); keep_shell keeps a body a shell runs
    (`bash <<X`, `ssh host <<X`, `cat <<X | sh`)."""
    out, lines, i = [], cmd.split("\n"), 0
    while i < len(lines):
        out.append(lines[i])
        m = re.search(r"<<-?\s*['\"]?(\w+)['\"]?", lines[i])
        runs = bool(m) and keep_shell and bool(SHELL_HEREDOC.search(lines[i]))
        i += 1
        if m:
            while i < len(lines) and lines[i].strip() != m.group(1):
                if runs:
                    out.append(lines[i])
                i += 1
            i += 1
    return "\n".join(out)


def check_test_output(ti):
    cmd = strip_heredocs(ti.get("command") or "")
    for seg in re.split(r"&&|\|\||;|\n", cmd):
        if seg.split()[:1] and seg.split()[0] in TEXT_CMDS:
            continue
        m = TEST_RUN.search(seg)
        if m and not TEST_QUIET.search(seg):
            deny("testout", f"`{m.group(0)}` output would land in context raw (e2e runs average thousands of chars). "
                 f"Wrapped in q it returns the verdict + failures only, full log in a file.",
                 f"{TOOLS}/q {seg.strip()[:80]}")


def sibling_agent_transcript(d, target):
    """Transcript of agent <target> in this session (main or nested caller), None for names/teammates."""
    tp = d.get("transcript_path") or ""
    base = os.path.dirname(tp)
    folder = base if os.path.basename(base) == "subagents" else os.path.join(base, d.get("session_id") or "", "subagents")
    path = os.path.join(folder, f"agent-{target}.jsonl")
    return path if re.fullmatch(r"[A-Za-z0-9_-]{6,40}", target or "") and os.path.exists(path) else None


def check_resume(d, ti):
    target = str(ti.get("to") or "")
    path = sibling_agent_transcript(d, target)
    if not path:
        return
    ctx = last_context(path)
    if ctx is None:
        return
    idle = time.time() - os.path.getmtime(path)
    fresh = ("Agent(same type, prompt `continue from <its FENCE-HANDOFF path or last report> + the new instruction`) "
             "(a fresh agent starts at ~10k)")
    try:
        target_type = json.load(open(path[:-6] + ".meta.json")).get("agentType") or ""
    except (OSError, ValueError):
        target_type = ""
    if ctx >= fence_limit(target_type):
        deny("resume", f"agent {target} is at {ctx // 1000}k context — at/over the fence: a resume re-sends all of it "
             f"and is fenced at once.", fresh)
    if ctx >= RESUME_COLD_MAX and idle > CACHE_TTL_S:
        deny("resume", f"agent {target} is at {ctx // 1000}k context and idle {int(idle) // 60} min — its 5-min cache "
             f"expired, a resume re-writes all {ctx // 1000}k at 1.25×.", fresh)


def check_agent_output(tool, ti):
    target = ti.get("file_path") if tool == "Read" else strip_heredocs(ti.get("command") or "") if tool == "Bash" else ""
    if target and AGENT_OUTPUT.search(target):
        deny("agentout", "that file is a running/finished subagent's full JSONL transcript — reading or polling it floods "
             "your context; its report arrives as a message.", "end your turn and wait for the task notification")


def check_suite(ti):
    cmd = strip_heredocs(ti.get("command") or "")
    if "FULL_SUITE=1" in cmd:
        return
    for seg in re.split(r"&&|\|\||;|\n|\|", cmd):
        if seg.split()[:1] and seg.split()[0] in TEXT_CMDS:
            continue
        m = SUITE.search(seg)
        if m and not SUITE_SCOPE.search(seg[m.end():]):
            deny("suite", f"`{m.group(0)}` without a scope runs the whole suite — that is CI's job on push (minutes of "
                 f"idle context, big output). Deliberate full run: prefix FULL_SUITE=1 and run_in_background.",
                 f"{TOOLS}/q $({TOOLS}/affected-tests --cmd)")


def series_nudge(d):
    """PostToolUse: trailing run of API calls that each used only one same tool → one line at every SERIES_STEP."""
    tool = d.get("tool_name") or ""
    if tool not in SERIES_TOOLS:
        return
    path = agent_transcript(d) if d.get("agent_id") else d.get("transcript_path") or ""
    try:
        with open(path, "rb") as fh:
            fh.seek(max(0, os.path.getsize(path) - 400_000))
            lines = fh.read().decode("utf-8", "ignore").splitlines()
    except OSError:
        return
    calls = {}   # message id → set of tool names, in order
    for line in lines:
        if '"tool_use"' not in line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        m = rec.get("message") or {}
        if rec.get("type") != "assistant":
            continue
        names = {c.get("name") for c in m.get("content") or [] if isinstance(c, dict) and c.get("type") == "tool_use"}
        if names:
            calls.setdefault(m.get("id") or id(rec), set()).update(names)
    run = 0
    for names in reversed(list(calls.values())):
        if names != {tool}:
            break
        run += 1
    if run and run % SERIES_STEP == 0:
        log("series", d)
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext":
              f"token-guard: {run} {tool} calls in a row — each re-sends the whole context. Batch independent steps: "
              f"one script (`a; b; c`, loop) or several tool calls in ONE message."}}))


def check_rewrite(ti):
    path, new = ti.get("file_path") or "", ti.get("content") or ""
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            old = [ln.strip() for ln in fh if ln.strip()]
    except OSError:
        return
    if len(old) <= REWRITE_LINES:
        return
    kept = set(ln.strip() for ln in new.splitlines() if ln.strip())
    share = sum(1 for ln in old if ln in kept) / len(old)
    if share >= REWRITE_KEEP:
        deny("rewrite", f"Write would re-emit {path} ({len(old)} lines, {round(100 * share)} % unchanged) — use Edit for the "
             f"changed parts (Write content is output tokens and stays in context).",
             f"Edit {path} with old_string/new_string for the changed parts only")


def main():
    if os.environ.get("CLAUDE_TOKEN_GUARD_OFF") == "1":
        return
    try:
        d = json.load(sys.stdin)
    except ValueError:
        return
    PAYLOAD.update(d)
    if d.get("hook_event_name") == "PostToolUse":
        series_nudge(d)
        return
    tool, ti = d.get("tool_name") or "", d.get("tool_input") or {}
    if d.get("agent_id"):
        check_fence(d, tool, ti)
        check_wait(tool, ti)
        check_poll(d, tool, ti)
    if tool == "SendMessage":
        check_resume(d, ti)
    check_agent_output(tool, ti)
    if tool == "Bash":
        check_suite(ti)
        check_test_output(ti)
    elif tool == "Read":
        check_read(ti)
        check_reread(d, ti)
    elif tool == "Write":
        check_rewrite(ti)


if __name__ == "__main__":
    main()
