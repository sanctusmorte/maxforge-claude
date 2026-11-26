---
name: spec
description: Intake + ambiguity-scored spec/plan writer for any non-trivial task (quick or full per the size gate) — scouts the repo, ≤5 decisive questions only if needed, writes the spec (EARS criteria, bug repro plan, waves, verification plan). Use at the start of every quick/full task and when the request is ambiguous.
argument-hint: <request text or issue/PR link> [--quick|--full] [--auto]
---
# /spec — assess the request, then write the spec and the plan

Inputs: `$ARGUMENTS` = request (or issue/PR URL) + flags. `--auto` = unattended (never ask; recommended
defaults, logged as assumptions). Templates: `~/.claude/templates/project/spec.md`.

## 0. Level + size gate — per `rules/task-lifecycle.md` (project → `/project-new`; direct / quick / full), one line
Put `model:` (session model + effort, inherited by every subagent — task-lifecycle) in the spec header.
Put `budget: <N> tokens` there too — defaults quick `60M`, full `600M` (≈p90 of 278 measured sessions: raw input +
cache_creation + cache_read + output of the session and its subagents, 97 % of it cache reads); direct: none; the
owner may name another number. Arm it in the same step: `python3 ~/.claude/hooks/ctx-monitor.py --budget 60M` (session
id from `CLAUDE_CODE_SESSION_ID`; the whole session counts; `--budget <new>` extends, `--budget off` clears).
Direct: no spec file, still reproduce-before-fix + evidence. Quick: inline spec (goal, REQ list, verification plan,
assumptions) reused in the PR body. Full: `docs/project/specs/<slug>.md` (GSD-legacy repos: `.planning/phases/…SPEC.md`),
milestones, waves.

## 1. Scout (read, don't ask)
`docs/project/PROJECT.md` + `STATE.md` (or `.planning/`), `docs/CODEMAP.md`/`docs/domains/README.md` if present,
the subsystem docs, the code paths named (Read symbols, Grep callers). Never ask what the repo answers.
Classify: type (feature | bug | refactor | design), affected domains, existing behaviour with `path::symbol` anchors.

## 2. Assess (internal assessor)
1. Assumptions ledger: `A-n | assumption | evidence path | if wrong → | confidence`.
2. Score Goal / Boundary / Constraints / Acceptance in [0,1]; `ambiguity = 1 − (0.35·G + 0.25·B + 0.20·C + 0.20·A)`.
   No questions when `ambiguity ≤ 0.20` and G ≥ 0.75, B ≥ 0.70, C ≥ 0.65, A ≥ 0.70.
3. Else rank open items by impact × uncertainty; keep only those whose answer changes design, tests or scope;
   ask ≤5 via `AskUserQuestion`, one round, 2–5 options each + recommended default + "why it matters".
4. Bugs: first output = reproduction plan (failing test / Playwright script / screenshot at the reported
   viewport / curl / SQL; env, tenant, role, data). No plan → spec cannot be approved. UI/design bugs are
   proven on the rendered page, not by reading code.

## 3. Spec (WHAT/WHY)
Goal (one measurable sentence) · non-goals · context with `path::symbol` + "existing — do not recreate" ·
acceptance criteria as EARS (`WHEN … THE SYSTEM SHALL …`, `IF … THEN …`) numbered REQ-n, each testable, plus the section `## Requirements status` = `| REQ | status | evidence |` (status `todo|red|green|verified`, initially `todo`; only status/evidence cells change; `verified` is set only by `verifier`; `python3 ~/.claude/tools/req-status.py <spec.md>` counts) ·
UI states (empty/loading/error/success) + viewports · UI tasks: `## Controls` = `| control (screen · text) | effect when
clicked (route / request / visible result) | REQ | e2e test |` for every control the change adds or touches, incl. ones
in every mode/tab and at 390 px — each row gets an e2e asserting that effect (`ui-qa-protocol.md` §E.19) · contracts · NFRs with numbers · assumptions · clarifications
log · definition of done. Right-sized: a small bug gets 3–5 REQs, not 16. Cite code, don't restate it.

## 4. Plan (HOW)
- Milestone 1 = walking skeleton (thinnest end-to-end path), then vertical slices; risks/unknowns first
  (spike before formalising).
- Task = one context window = one PR = 1–3 h: exact files, REQ refs, verify command + expected output,
  "out of scope", owned files. `[P]` only when owned files are disjoint (shared files: one owner). Dependency graph →
  waves; ≥2 subtasks → PRs into the integration branch `task/<slug>` (task-lifecycle; execution: `/task` step 6).
- Heavy/architectural (new subsystem, schema/contract, cross-repo) → independent spec/plan review before code
  (`/task` step 5); record its verdict in the spec.
- Plan is living: Decision Log (why), Surprises, Progress; on divergence revert and re-plan.
- Add a `MILESTONES.md` line when a milestone appears; spec `status: clarified` (or `approved` after the user confirms).

## 5. Hand-off (Russian)
Size gate + assessor verdict (ambiguity score, questions asked or "no questions"), spec path, task list with waves,
and the first executable step.
