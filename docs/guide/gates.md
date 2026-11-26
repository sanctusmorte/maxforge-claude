---
title: "Claude Code quality gates and hooks - what each one blocks"
description: "Every maxforge-claude hook and gate, the exact command or action it denies, the file that implements it, the test that proves it, and its escape hatch."
---

# Quality gates: what each Claude Code hook blocks

Every gate is a Python hook (standard library only) registered in `hooks/hooks.json`. A deny is returned to the model with a one-line reason and a hint. All paths are inside the plugin.

## PreToolUse on Bash

| Gate | Denies | File | Test | Escape hatch |
|---|---|---|---|---|
| Git and destructive commands | push to `master`/`main`/`dev`; force-push to a protected branch; `commit --no-verify`/`-n`; destructive database commands (migrate fresh/reset, db wipe, drop database/table) outside a test database, also over ssh; `rm -rf` outside scratch, build and dependency paths; `git reset --hard`, `git clean -f`, `git checkout -- .` in a main checkout; a PR into `main` while `origin/dev` exists | `hooks/guard-bash.py` | `tools/test-hooks.py` | `CLAUDE_GUARD_OFF=1 <cmd>` |
| Design gate | a non-draft PR touching UI files without a `Verdict: PASS` scorecard newer than the last UI commit, or without a fresh dead-click report (unless the PR body states why it is n/a) | `hooks/guard-bash.py` | `tools/test-designgate.py` | same |
| Geometry gate | the same PR without a `geometry/report.json` newer than the last UI commit and with zero errors (unless the scorecard states `Geometry: n/a - <reason>`); the report comes from overlap, clipping, overflow and alignment checks at 390/768/1440/2560 px with a text-stress mode | `hooks/guard-bash.py` | `tools/test-ui-geometry.mjs` | same |
| Secret scan | a commit whose added lines look like credentials, or that stages `.env`, `*.pem`, `id_rsa`, `*.key`, service-account JSON | `hooks/secret-scan.py` | no dedicated test | `CLAUDE_ALLOW_SECRETS=1 git commit ...` |
| Dump nudge | `cat`/`sed -n`/`head`/`tail`/`less` of a regular file over the line cap inside a git worktree | `hooks/dump-nudge.py` | `tools/test-hooks.py` | none; read a range instead |
| Background router | not a deny: moves builds, installs, test runners and deploys to the background (subagents run tests in the foreground with a 270 s timeout) | `hooks/bg-router.py` | `tools/test-hooks.py` | `CLAUDE_BG_ROUTER_OFF=1` |

## PreToolUse on Edit and Write

| Gate | Denies | File | Test | Escape hatch |
|---|---|---|---|---|
| Rules gate | editing a file matched by a stack rule (`paths:` frontmatter in `rules/*.md`) until the agent has read that rule in its own transcript | `hooks/rules-gate.py` | `tools/test-hooks.py` | `CLAUDE_GUARD_OFF=1` |

## Token guard

`hooks/token-guard.py` applies one-line denies: the context fence for subagents (then `FENCE-HANDOFF`), idle waits (long `sleep`, `gh ... --watch`), whole-file reads above the cap, re-reads of a file already read, unscoped whole-suite test runs, and resuming a cold subagent. Tests: `tools/test-hooks.py`, `tools/test-token-audit.py`. Escape: `CLAUDE_TOKEN_GUARD_OFF=1`. Deny log: `logs/token-guard.log`.

## Session lifecycle

| Hook | Event | Effect | Test |
|---|---|---|---|
| `hooks/stop-guard.py` | Stop | blocks finishing while this session's worktree is dirty or has unpushed commits | `tools/test-hooks.py` |
| `hooks/precompact-handoff.py` | PreCompact | refreshes and commits the task's `progress.md`, pushes it in the background | `tools/test-continuity.py` |
| `hooks/session-restore.py` | SessionStart (compact, resume) | re-injects `progress.md` plus `git status` and the last commits | `tools/test-continuity.py` |
| `hooks/project-sync.py` | SessionStart | short digest of `docs/project/STATE.md` | `tools/test-hooks.py` |
| `hooks/lesson-capture.py` | prompt | flags a likely correction so it can be recorded as a lesson | `tools/test-lessons.py` |
| `hooks/ctx-monitor.py`, `hooks/statusline.py` | PostToolUse, status line | optional task token budget and status line | `tools/test-hooks.py` |
| `hooks/doc-sync-reminder.py` | PostToolUse | reminds to keep docs 1:1 with code | no dedicated test |

## Verification tools

<img src="/readme/art/clicks.webp" width="280" alt="Illustration: a small robot with a magnifying glass presses every button on a control panel; one pressed button stays dark.">

| Tool | What it does | Self-test |
|---|---|---|
| `tools/dead-clicks.mjs` | clicks every control per route, viewport and mode; `NO_EFFECT` or `ERROR` is a blocker | `tools/fixtures/dead-clicks/` |
| `tools/ui-qa.mjs` | UI checks on a production build over a viewport grid | `tools/test-uiqa.mjs` |
| `tools/harness-lint.py` | checks rule numbers, paths, agent model and effort, hook registration | run it directly |

## Running the self-tests

```bash
python3 tools/test-hooks.py
```

It also runs every `tools/test-*.py`. Exit code 0 means no failures.

## Limits

Gates deny known patterns; they do not read intent. Commands the gates do not recognise pass. If a gate is wrong for you, use its escape hatch and state the reason, or [disable it](/guide/faq#how-do-i-disable-one-hook).
