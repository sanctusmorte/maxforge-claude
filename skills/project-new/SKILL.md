---
name: project-new
description: Start a NEW project (new repo or deployable) — intake + research, positioning, PROJECT.md + ADRs with plan review, bootstrap (dev branch, CI, stand + e2e, docs/project, portfolio); milestones run as `/task`.
argument-hint: <idea / request text> [--auto]
---
# /project-new — project path above the task path

Level gate (`rules/task-lifecycle.md`): new repo or new deployable → here; a big initiative inside an existing repo
is a full task → `/task`. Never ask the owner for inputs — research them (CLAUDE.md rule 2); questions only at a
scope fork. Each step ends with a line in `docs/project/DECISIONS.md` once the repo exists (before that: in the
draft under `~/.claude/drafts/<slug>-intake.md`).

## 1. Intake + research
Problem, user, outcome, constraints, budget/timeline. `researcher` agents in ONE batch: competitors and references
(pricing/feature pages read today, dated), existing internal assets (`~/.claude/portfolio.md`, sibling repos,
auto-memory) to reuse. Output: intake draft with sources.

## 2. Meaning
Sells to someone → `/site` stages 1–3 (brief, positioning with parity check, copy) — signed before any stack work.
Internal tool / service → goal + one success metric + non-goals.

## 3. Constitution + architecture
`docs/project/PROJECT.md` (template `~/.claude/templates/project/PROJECT.md`) + ADRs for stack, hosting, data,
auth, deploy (`docs/adr/D-n-*.md`: context, options, outcome, consequences). Reuse the portfolio's proven stack
unless an ADR says why not. Independent plan review (task-lifecycle Review gate): `code-reviewer` (or `Plan`) tries
to refute PROJECT.md + ADRs; blockers fixed before bootstrap. Owner sign-off here if the stack, hosting or spend is
new (scope fork).

## 4. Bootstrap (one PR, reversible steps only)
- Repo: local `git init` from the closest sibling repo's skeleton (lint/format/test config, `.github/workflows`,
  CLAUDE.md facts-only header) — creating a remote (GitHub) is external publication → owner "go" first.
- Branches: `master`/`main` + default `dev`; CI gate (lint, static, tests, build) and `guard-master`-style rule.
- Stand + e2e runner from day one (owner decision 3): a non-prod stand (pattern: example-app `deploy-release.sh dev`,
  `~/.claude/drafts/d-stands-inventory-2026-09-24.md`) and a Playwright (or stack-native) smoke spec in CI. DNS/TLS/
  OAuth consoles are owner-only → record as Blockers, stand stays NOT_VERIFIED until they land.
- `/project-sync --init` (docs/project/*, auto-memory MEMORY.md + reference_prod.md), a row in
  `~/.claude/portfolio.md` (repo, base branch, deploy, stand URL).

## 5. Milestones → tasks
`docs/project/MILESTONES.md`: M1 = walking skeleton deployed to the stand, then vertical slices. Each milestone →
tasks; each task → `/task` (its own triage, split, waves, integration branch, one PR into `dev`). Independent tasks
of one milestone may run as parallel `/task` runs (≤5 agents in total, disjoint file ownership).

## 6. Project done
Milestone acceptance on the stand (e2e green or explicit NOT_VERIFIED rows), `verifier` against PROJECT.md goals,
prod release only on the owner's explicit "go" (prod protocol, CLAUDE.md rule 10). `/project-sync`, `/handoff` at
the context threshold.

## Report (Russian)
Verdict + "NOT verified" first → repo/stand URLs → signed decisions → milestone table (task × PR × status) →
owner-only blockers.
