---
title: "Why an agent harness for Claude Code"
description: "Why maxforge-claude adds hooks, subagents and quality gates to Claude Code, what failure modes it targets, and the honest cost - more tokens, not fewer."
---

# Why an agent harness for Claude Code

A Claude Code agent writes code fast and is wrong in repeatable ways. A harness does not make the model smarter. It makes the repeatable mistakes expensive to commit or impossible to hide.

## The failure modes

| Failure | What happens | What maxforge-claude does |
|---|---|---|
| "Done" without evidence | The agent reports success with no test output or screenshot | `qa-verify` requires a reproduction or a requirement-to-evidence matrix; the `verifier` agent tries to refute the claim |
| Skipped or bent tests | A failing test is deleted or loosened | Worker rules forbid weakening a test; reviewers and the verifier check the diff |
| Push to `main` | A direct push, a force-push, `--no-verify` | `hooks/guard-bash.py` denies the command |
| Dead buttons | UI passes screenshot review, half the controls do nothing | `tools/dead-clicks.mjs` presses every control; the PR guard needs its report |
| Lost context | After compaction the goal, branch and next step are gone | `hooks/precompact-handoff.py` and `hooks/session-restore.py` |
| Context waste | Large dumps, re-reads, sleep loops | `hooks/token-guard.py`, `hooks/dump-nudge.py`, `hooks/bg-router.py` |

## Instructions versus hooks

A rule in `CLAUDE.md` is a request. A hook is code that runs on the tool call and can return a denial, so a rule that must hold lives in a hook. The harness still ships instructions (`rules/*.md`, skills) for everything that cannot be checked mechanically, such as how to review or how to write a spec.

## The honest cost

The harness spends more tokens than plain Claude Code. In the author's own A/B run, the same tasks used about 1.49 times the tokens at equal quality. Extra spend comes from independent review, a verifier pass, UI QA runs, handoff files and rule reads. The project makes no savings claim.

Some hooks reduce waste inside that budget (blocking whole-file dumps, re-reads, idle waits), and each one is documented with its measurement in the harness changelog. The net is still higher.

Use it when a wrong "done" costs more than extra tokens: shared repositories, production code, UI work that must actually work, work you will not watch line by line. For a throwaway script, plain Claude Code is cheaper and fine.

## What it is not

- Not a model upgrade: it does not change how well Claude writes code.
- Not a sandbox: hooks deny known-bad commands; they do not make arbitrary commands safe.
- Not tied to one stack: Laravel/PHP, Vue/TypeScript and Python rules are included, the gates are stack-neutral.

Next: [install](/guide/install).
