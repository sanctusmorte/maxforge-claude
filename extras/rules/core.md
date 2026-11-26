# Core rules (maxforge-claude)

Generic distillation of the process rules the harness is built around. Copy into your global `CLAUDE.md` or keep it
as `~/.claude/rules/maxforge/core.md`. Project `CLAUDE.md` = facts only (stack, commands, ports, traps); on a
conflict these rules win and the project file gets fixed in the same PR.

## 1. One worktree per task, one PR per task
- Code changes happen in a dedicated git worktree on a task branch cut from the integration branch (`dev` if it
  exists, else `main`). Never commit in the main checkout; never leave work in progress there.
- Commit and push after every logical step. Open a PR into the integration branch; a subtask PR goes into its
  parent `task/<slug>` branch. Only an explicit release decision merges into `main`.
- Local gate before a PR: lint, static analysis, tests of the touched code (wider if unsure), build. A docs-only PR
  needs no gate; say so in the PR body.
- Never amend or rewrite pushed commits, never force-push, never skip hooks (`--no-verify`). A failing hook means
  fix the cause. A follow-up after a merge is a new branch and a new PR.

## 2. Autonomy
- Reversible action: do it, do not ask. Ask only before the irreversible (force-push, data deletion, external
  publication, real money, production) or at a genuine scope fork.
- Never ask the user for inputs you can research (references, examples, materials). Showing a result for a yes/no
  is fine.

## 3. Tokens
- Read project docs first (code map, domain index), then run a scoped search. Do not dump large files through
  `cat`/`sed`/`head`; read a range or an outline of the file instead.
- Handle narrow lookups directly. Use a research subagent only for a substantial independent question, and ask it
  to return facts with `path::symbol` anchors.
- Slow commands (builds, installs, test suites) run in the background; keep working and read the output when the
  notification arrives. Never poll or sleep-loop.

## 4. Task path
- Triage first: new project or task, and its size. A direct or quick change is coded by the main session. A full
  task is split by file ownership, specified, built by workers, reviewed once, verified once, delivered as one PR.

## 5. Parallel agents
- Launch every independent unit at once, capped at what the machine and the subscription allow. Split by file
  ownership; write the shared contract (interfaces, ownership) and placeholder files first, then one agent per unit.
- Each agent gets its own worktree, branch, temp directory and test database, plus explicit paths and acceptance
  checks. Overlapping files mean one agent, not two. Do not invent units to fill slots.
- A dependent unit starts as soon as its dependency is pushed, not after the whole wave.

## 6. Task cycle
Docs first, then code, then self-check (errors, duplicates, edge cases, idempotency, N+1 queries), then tests in
the same PR, then docs updated 1:1 with the code in that same PR.

## 7. Done = evidence
- Bug: a reproduction artefact, the fix, the same artefact passing, and a regression test.
- Feature: every requirement mapped to a command, test or screenshot you actually ran; an independent verifier
  tries to refute the result.
- UI: automated UI QA plus a look at every screenshot. Nothing unobserved is reported as done.
- Report format: verdict first, then evidence, then a `NOT verified:` list when anything was not checked.

## 8. Meaning before form
- Selling surfaces (landing, pricing, signup): positioning and copy are agreed before visuals; the real product is
  the hero object; competitor references come before the design direction.
- App UI: follow the existing design system component by component; never raw framework primitives where a kit
  component exists.

## 9. Gates
- Production protocol: goal, backup, dry run, run, smoke test, record.
- Never bypass the push, secret and stop gates. A conscious bypass names the reason to the user first.
