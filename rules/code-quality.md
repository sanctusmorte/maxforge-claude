# Code quality — main-session gates (always loaded; full checklist = skill `code-pack`)

## 1. Who writes code (owner 2026-10-17)
Direct/quick tasks: the main session codes itself in the task worktree — no worker, no respawn, cache stays warm.
Workers (`general-purpose` Sonnet, `ui-builder`) only for full tasks with ≥2 independent subtasks or NEW/VALUE UI
builds (`task-lifecycle.md`). Workers get `worker-core` + role pack from the agent file (`omitClaudeMd: true` — they
do not see this file). Writing or reviewing code yourself → invoke `code-pack` first.

## 2. Design floor (owner 2026-10-17) — the repo's gate decides (`composer gate` / `npm run gate`), prose states intent
- Every Service/Action has a contract in `Contracts/` (`<Class>Contract`), bound in the context's provider; callers
  type-hint the contract; implementations `final`. Polymorphism over type switches: a `match`/`switch` on a
  marketplace/status/type code that appears twice → one strategy class per variant behind the contract.
- Caps for new code: method ≤20 lines, class ≤200, SFC ≤400, cognitive complexity ≤15 per function, ≤4 params.
  DRY = jscpd clean on new code. KISS = no layer without a removed duplication or a real second implementation.
- Boy-scout on legacy: a task touching a file over its cap EXTRACTS the touched method/region (class, Action,
  composable, child component) in the same PR and lowers that file's baseline entry; a capped file never grows.
- Gates are ratchets: PHPStan/Larastan + phpat baseline, ESLint per-file overrides, jscpd threshold, god-file line
  counts, design-lint — CI fails only when debt grows vs origin/dev. Never widen a baseline to pass.
- Golden examples beat prose: the project CLAUDE.md names one reference file per layer; copy its shape.

## 3. Commits and deps
Conventional Commits `type(scope): subject` ≤72, body = why, the `Co-Authored-By` trailer the harness gives for the
CURRENT model (never a hardcoded model name); one logical change. New dep = one-line why; `composer audit` /
`npm audit --audit-level=high` / `pip-audit` in CI.

## 4. Tests and docs 1:1
Every behaviour change ships tests (feature-level first; ≥80 % on new code is a floor; never weaken or delete a test
to pass; isolated per agent) and the matching docs (symbol anchors, verified examples only, stale anchors fixed,
removed flows → "unused candidates", divergence = defect, trade-offs → ADR) in the same PR; detail = `code-pack`
Tests / Docs 1:1.

## Self-review before hand-over (also the acceptance check for a worker's PR)
intent in names · contracts + `final` · invariants · explicit errors · validated boundaries · idempotent · no N+1 /
unbounded queries / missing pagination · secrets & PII · tests incl. edges · docs with real anchors · gate green
(`composer gate` / `npm run gate`, lint, static, touched-class tests, build) · diff = only the task (no drive-by
refactors beyond the boy-scout extraction, no formatting noise, no version bumps).
