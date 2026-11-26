---
name: task
description: Orchestrate a quick/full task in an existing repo — triage, spec/plan, parallel waves, integration branch task/<slug>, one review + verifier + e2e, one PR. `--plan-only` stops after the plan.
argument-hint: <request text | issue/PR link> [--plan-only] [--auto]
---
# /task — responsible executor for one task

Gates live in `rules/task-lifecycle.md` (level, size, model, split + waves, review, e2e, security, migrations); this
skill orders the steps and names who does what. Sub-procedures: `/spec`, `/site`, `/ui-task`, `/qa-verify`,
`/project-sync`, `/handoff` — do not restate them. `--plan-only`: run steps 1–5, print the plan block, stop (no
worktree, no code, no PR). `--auto`: unattended, per `/spec --auto`.

## 1. Triage (main session, ≤2k tokens)
Start ritual: `docs/project/tasks/<slug>/progress.md` exists → read it, run its `## Verify` command, only then new work.
Memory L0 (`~/.claude/portfolio.md`, MEMORY.md) + the repo's `docs/project/{PROJECT,STATE}.md`, `git status -sb`.
Narrow before reading: `project-sync.py --landed --domain <d>`, `docs/CODEMAP.json` row (if present, else
`docs/CODEMAP.md`), `grep D-n docs/adr` — then read only the matching section of a domain doc, never whole docs.
Level: new repo / new deployable → stop, run `/project-new`. Else size direct | quick | full; direct → do it per
CLAUDE.md rules 1 + 7, self-check, evidence, done (steps 2–9 do not apply).
**Quick (owner 2026-10-17) → the main session codes it itself:** `tools/wt-new.sh <repo> <slug>` → inline spec
(goal, REQs, verification plan; `/spec` only if ambiguity is real) → tests RED → code (boy-scout on capped files,
`code-quality.md` §2) → `composer gate` / `npm run gate` + touched-class tests → UI gate when visible (`/ui-task`
step 6) → `code-reviewer` only on the security trigger / schema change / owner's «ревью» → PR `--base dev` with the
inline spec + evidence. ≤2 agents in total; no waves, no integration branch, no verifier unless a prod-facing bug.
Steps 2–8 below are the FULL path.

## 2. Research
Wide reads → `researcher` / `Explore` subagents in ONE batch (one per question), conclusions with `path::symbol`. Conclusions that workers need → `docs/project/tasks/<slug>/scout.md` (committed in the task branch); worker prompts point to it.
Question to the owner only at a scope fork (CLAUDE.md rule 2).

## 3. Summary (print it)
```
level: task · size: quick|full · repo: <name> (base <branch>) · model: <session model + effort> · budget: 60M|600M tokens
goal: <one sentence> · risk: low|medium|high (<why>) · triggers: security|migration|selling|UI|none
heavy/architectural: yes|no (<new subsystem | schema/contract | cross-repo>)
```

## 4. Split
Subtasks only where they become independent; each ≥ one 1–3 h PR. For every subtask: slug, kind (backend | frontend
| docs | infra), OWNED files/dirs (disjoint; shared files — routes, lockfiles, migrations index, STATE — belong to one
subtask or to the orchestrator), depends-on. Dependency graph → waves (all independent units at once, CLAUDE.md rule 5). One subtask → no integration
branch, a normal task branch and PR.

## 5. Spec + plan
`/spec` once for the task (it arms the token budget; quick: inline spec for the PR body; full: `docs/project/specs/<slug>.md`), REQs mapped to
subtasks, a task card per subtask (REQ refs, owned files, verify command, out of scope). Heavy/architectural → ONE
independent review of spec + plan before code: `code-reviewer` (or `Plan`) given the spec, the split and the risk
line, asked to refute the design; blockers fixed in the spec. Print the plan block:
```
wave 1: <sub-a> [backend; owns app/X/**, tests/Feature/X*] · <sub-b> [frontend; owns resources/js/x/**]
wave 2: <sub-c> [depends on sub-a; owns …]
integration: task/<slug>-<date> · review: code-reviewer + verifier (+ security-reviewer: trigger) · e2e: <runner | NOT_VERIFIED (no stand)>
```
`--plan-only` ends here.

## 6. Waves
Before each wave: `python3 ~/.claude/tools/ownership-check.py <plan block file>` (exit 1 = a file owned twice → fix the split). A dependent subtask starts when its dependency is pushed (merge that branch), not after the whole wave.
Integration branch: `tools/wt-new.sh <repo> <slug>` → push it. Per subtask: `tools/wt-new.sh <repo> <slug>-<sub>
--base <integration branch>` (own worktree + test DB), one Agent per subtask in ONE message per wave, no `model`
param. Agent prompt = goal · output format (PR link + gate output) · boundaries + owned files · acceptance command · `scout.md` path · task card + spec slice + STATE snapshot + worktree/DB lines · ≤3 lessons from `python3 ~/.claude/tools/lessons.py inject --agent-type <t> --paths <globs>` · "PR into <integration branch>, commit + push after every step".
- Backend subtask: re-read the spec → tests RED → implement (`rules/laravel-php.md` etc.) → green → self-check
  (CLAUDE.md rule 7) → local gate → PR into the integration branch.
- Frontend subtask: worker = `ui-builder` (design-pack preloaded; never `general-purpose` for visual work). Workers
  have no Skill/Agent tools, so the ORCHESTRATOR runs the skill/agent steps: `/site` stages 1–3 (brief, positioning
  with its `researcher` parity check, copy; signed) and `/ui-task` steps 0–4 (context pack + `before/`, references
  `refs/` + LEAD, `plan.md`, component list). Worker prompt = that pack + the build slice + the exact
  `node ~/.claude/tools/ui-qa.mjs … --out artifacts/ui-qa/<slug>/build-<n>` and e2e commands → worker builds in
  rounds, writes e2e specs for the touched flow, local gate → PR, returns artefact paths (absolute). Design panel /
  `ui-qa` agent run in step 8 (`/qa-verify`) on the integrated worktree.
A failed subtask → SendMessage the same agent only ≤5 min after it stopped, else a fresh agent from `progress.md` + the PR state.
Quota 429 → resume after the reset, never downgrade the model.

## 7. Integrate
Merge the subtask PRs into the integration branch in dependency order (`gh pr merge --merge`); conflicts → the
orchestrator resolves in the integration worktree. Run the full local gate there (lint, static, tests of touched
areas, build).
STATE budget in the same gate: `python3 ~/.claude/hooks/project-sync.py --check --strict` (STATE ≤60 lines, Now ≤3).

## 8. Review + verify (on the integrated diff only)
Review packet = diff file + REQ list + touched symbols; reviewer told "against the spec: correctness and requirement gaps only; findings outside the diff are dropped". Done signal = the spec REQ status table all `verified` (`req-status.py`).
`/qa-verify` on the integration branch: ONE `code-reviewer` pass (+ `security-reviewer` on trigger) → fixes → e2e →
UI panel for visible changes → `verifier` refutes. No per-subtask cross-reviews. e2e = the project's runner against
a local production build (example-app: `npm run e2e`), then smoke on the shared stand after merge into `dev` (example-app:
the shared dev stand); no runner/stand → `e2e: NOT_VERIFIED (no stand)`. Verdict ≠ PASSED → fix → re-run failed rows.

## 9. PR + sync
ONE PR `task/<slug>` → base (`gh pr create --base dev`) with spec/REQs, subtask PR list, review + verifier verdicts,
evidence matrix, "NOT verified". `/project-sync` items ride this PR. Merge only on the owner's words (memory:
"смержи в дев"); after merge remove worktrees. PR opened/merged → hint: `/clear`, continue from `progress.md`. Budget exhausted → `/handoff`, then ask
the owner to extend (`ctx-monitor.py --budget <new>`) before the next step.

## Report (Russian)
Verdict + "NOT verified" first → PR link → subtasks × PR × gate → review/verifier verdicts → e2e status.
