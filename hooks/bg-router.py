#!/usr/bin/env python3
"""PreToolUse(Bash) — route long-running commands to the background (owner 2026-10-17).

Short commands (git status, ls, grep) stay synchronous: a backgrounded call costs one extra turn to read its output.
A command whose COMMAND POSITION (start, after `;`/`&&`/`||`/`|`/`(`, env prefixes allowed) is a build, install,
test runner, static analyser, deploy, worktree bootstrap, du/rsync/docker gets `run_in_background: true` through
`updatedInput`, unless the call already sets `run_in_background` or an explicit `timeout`. Quoted strings are blanked
before matching (a commit message naming `npm run build` is text); `grep … phpunit` is not a run.
Subagents (payload carries `agent_id`, 2026-11-25): a backgrounded test/build leaves the worker idle while its 5-min
prompt cache expires (122 cache rewrites, 16 M tokens in 14 days), so test runners and builds run in the FOREGROUND with
`timeout: 270000` (token-guard allows ≤280 s) instead; servers, deploys, bootstraps and du/rsync/docker stay background.
`updatedInput` + `permissionDecision: allow` is the documented pairing (a hook returning updatedInput WITHOUT a decision
can be denied by auto mode); another PreToolUse hook's deny wins (precedence deny > defer > ask > allow).
Complement: `env.BASH_DEFAULT_TIMEOUT_MS=20000` in settings.json — anything else that runs past 20 s is moved to
the background by the harness itself. Off: CLAUDE_BG_ROUTER_OFF=1. Fails open. Self-test: `--self-test`.
"""
import json
import os
import re
import sys

START = r"(?:^|[;&|(]\s*)(?:\w+=\S*\s+)*(?:sudo\s+|nice\s+|time\s+|timeout\s+\S+\s+)?(?:\S*/)?"
LONG = re.compile(START + r"""(?:
        npm\s+(?:run\s+(?:build|e2e(?::\w+)?|test(?::\w+)?|lint|gate|tokens:build|build:icons)|ci|install|i)\b
      | npx\s+(?:playwright|vitest|vite\s+build|impeccable|jscpd)\b
      | composer\s+(?:install|update|require|remove|gate|codemap|components-md|design-lint)\b
      | (?:phpunit|pest|paratest|phpstan|pint|rector|phpmd|deptrac)\b
      | php\s+artisan\s+(?:test|migrate|db:seed|horizon|queue:work|schedule:run)\b
      | q\s+\S
      | pytest\b | pip3?\s+install\b | cargo\s+(?:build|test)\b | make\b
      | docker(?:\s+compose)?\s+(?:build|up|pull|run)\b
      | (?:bash\s+|sh\s+)?\S*(?:deploy-release\.sh|wt-new\.sh|mysql-to-s3\.sh)
      | python3?\s+\S*(?:design-lint|generate-codemap|wt-prune)\.py
      | du\s+-[a-zA-Z]*s | du\s+--summarize | rsync\b | git\s+(?:clone|gc)\b
      | playwright\s+(?:test|install)\b | vitest\b
    )""", re.X)
QUOTED = re.compile(r'"[^"\n]*"|\'[^\'\n]*\'')
HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?\n.*?\n\s*\1\b", re.S)   # a PR body / file content is text, not commands
# test runners and builds a subagent waits for anyway: foreground, 270 s cap
FOREGROUND = re.compile(START + r"""(?:
        npm\s+(?:run\s+(?:build|e2e(?::\w+)?|test(?::\w+)?|lint|gate|tokens:build|build:icons)|ci|install|i)\b
      | npx\s+(?:playwright|vitest|vite\s+build|jscpd)\b
      | composer\s+(?:install|update|require|remove|gate|design-lint)\b
      | (?:phpunit|pest|paratest|phpstan|pint|rector|phpmd|deptrac)\b
      | php\s+artisan\s+(?:test|migrate)\b
      | q\s+\S | pytest\b | cargo\s+(?:build|test)\b | make\b
      | playwright\s+test\b | vitest\b
    )""", re.X)
SUBAGENT_TIMEOUT_MS = 270_000
SKIP = ("--help", "--version")


def route(ti: dict, subagent: bool = False) -> dict | None:
    cmd = ti.get("command") or ""
    if not cmd or ti.get("run_in_background") is not None or ti.get("timeout") is not None:
        return None
    if any(s in cmd for s in SKIP):
        return None
    text = QUOTED.sub('""', HEREDOC.sub("<<X\nX", cmd))
    if not LONG.search(text):
        return None
    if subagent and FOREGROUND.search(text):
        return {**ti, "timeout": SUBAGENT_TIMEOUT_MS}
    return {**ti, "run_in_background": True}


def self_test() -> int:
    cases = [
        ("npm run build", True), ("CI=true npm run build 2>&1 | tail -3", True), ("composer install -q", True),
        ("vendor/bin/phpunit --filter=Foo", True), ("~/.claude/tools/q php artisan test --filter=X", True),
        ("php artisan migrate --force", True), ("du -sh ~/worktrees", True), ("bash deploy/deploy-release.sh dev", True),
        ("cd /x && composer install", True), ("python3 scripts/design-lint.py", True),
        ("npx impeccable detect resources/js", True), ("timeout 240 npx impeccable@latest detect a b", True),
        ("git status -sb", False), ("ls -la", False), ("git commit -m 'fix npm run build on CI'", False),
        ("npm run build --help", False), ("grep -rn phpunit tests | head", False), ("echo make", False),
        ("cat composer.json | grep require", False), ("git log --oneline -3", False),
        ("gh pr create --body \"$(cat <<'EOF'\n- vendor/bin/pint --test on dev: 1 file red\nEOF\n)\"", False),
        ("cat > x.sh <<'EOF'\nnpm run build\nEOF\nchmod +x x.sh", False),
    ]
    bad = [(c, want) for c, want in cases if (route({"command": c}) is not None) != want]
    for c, want in bad:
        print(f"FAIL: {c!r} expected background={want}")
    sub = [("npm run test:unit", "timeout"), ("q php artisan test --filter=X", "timeout"), ("vendor/bin/phpstan", "timeout"),
           ("php artisan horizon", "run_in_background"), ("bash deploy/deploy-release.sh dev", "run_in_background"),
           ("git status", None)]
    for c, key in sub:
        got = route({"command": c}, subagent=True)
        want_ok = (got is None) if key is None else (got is not None and key in got and (
            got.get("timeout") == SUBAGENT_TIMEOUT_MS if key == "timeout" else got.get("run_in_background") is True))
        if not want_ok or (key == "timeout" and "run_in_background" in got):
            bad.append((c, key))
            print(f"FAIL (subagent): {c!r} expected {key}")
    cases += sub
    print(f"bg-router self-test: {len(cases) - len(bad)}/{len(cases)} ok")
    return 1 if bad else 0


def main() -> None:
    if os.environ.get("CLAUDE_BG_ROUTER_OFF") == "1":
        return
    try:
        data = json.load(sys.stdin)
        if data.get("tool_name") != "Bash":
            return
        updated = route(data.get("tool_input") or {}, subagent=bool(data.get("agent_id")))
        if updated is None:
            return
        reason = ("bg-router: test/build runs in the foreground (timeout 270 s) — a subagent waiting on a background job "
                  "lets its prompt cache expire." if updated.get("timeout") == SUBAGENT_TIMEOUT_MS else
                  "bg-router: long-running command runs in the background — continue with other work and read its "
                  "output file when the completion notification arrives.")
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": reason,
            "updatedInput": updated,
        }}))
    except Exception:
        return  # fail open


if __name__ == "__main__":
    sys.exit(self_test()) if "--self-test" in sys.argv else main()
