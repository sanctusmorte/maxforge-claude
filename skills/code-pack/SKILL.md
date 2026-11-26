---
name: code-pack
description: Senior code checklist — invoke before writing or reviewing code in the main session; preloaded in coding workers.
user-invocable: false
---
# Code pack — senior checklist (stack specifics: path-scoped rules, loaded on Read)

## Design
- Deep modules, small public surface; encapsulate invariants (validate in constructors); composition over
  inheritance. Owner 2026-10-17: every Service/Action sits behind a `Contracts/<Class>Contract` (callers type-hint
  it); polymorphism (one strategy class per variant) replaces a type switch that appears twice; any FURTHER layer
  only where it removes duplication or a second implementation exists. Caps: method ≤20 lines, class ≤200,
  SFC ≤400, complexity ≤15, ≤4 params; boy-scout extraction when touching an over-cap file; the repo gate
  (`composer gate` / `npm run gate`) is the arbiter.
- Immutable by default (`readonly`/`final`/`const`); side effects at the edges (controllers, jobs, CLI).
- Errors explicit: typed/domain exceptions, never `false`/`null`/magic codes, never swallowed; log once with
  context at the boundary. Validate at boundaries (HTTP, queue, CLI, external APIs); trust typed data inside.
- Idempotent where re-run is possible (jobs, webhooks, retries); locks/unique keys for shared state.
- No premature abstraction: three similar lines beat one wrong layer; no "just in case" options.
- Money = integer minor units; time = UTC aware; ids typed.

## Shape
- Functions ≤ ~20–50 lines, one abstraction level, ≤3 nesting, early returns; files ≤ ~400 (800 max).
- Names say intent (verbs for actions/jobs, past tense for events); no `helper`/`util`/`manager`, no boolean params.
- Native static types everywhere (no `any`/`mixed`), typed collections, named constants; no dead or
  commented-out code; TODO only with an issue/ADR reference. Comments explain *why*, never *what*.
- The project's formatter/linter runs before review (names in the stack rules); never hand-format.
- Deps: `composer audit` / `npm audit --audit-level=high` / `pip-audit` in CI; new dep = one-line why.

## Tests
- Every behaviour change ships tests in the same PR: feature-level through the real entry point first, unit for
  pure logic; named by behaviour, AAA, one reason to fail, deterministic (fake time/random/network/queues).
- Coverage ≥80 % on new code is a floor; meaningful assertions/mutation score are the signal. Never weaken or
  delete a test to pass — fix code or the wrong assumption and say which. Isolated per agent (own DB/tmp).

## Docs 1:1
- Docs describe the code as it is: symbol anchors (`path/File.php::method`; `file:line` only where the project
  style demands) and only real, verified examples (snippet imports over pasted copies).
- Same PR: code change → doc change → stale anchors fixed → removed flows removed/moved to "unused candidates".
  Read docs first; verify a claim against code before relying on it; divergence = defect, fix and report.
- Decisions with trade-offs → ADR (context, options, outcome, consequences) linked from the code.
- User-facing claims and selling-surface events: `design-ui-ux.md` §4 (path-scoped); `skills/site/design-rules.md` §12 and `skills/site/lead-capture-events.md` §G (on demand).

## Migrations and security (main-session source: `rules/task-lifecycle.md`)
- Migrations: additive first → backfill job → switch code → drop later; tested `down()`; destructive migration =
  backup step in the PR body; per-tenant failures reported, never ignored.
- Diff touches routes/middleware/auth/session/uploads/billing/webhooks/secrets/config/raw SQL/multi-tenant →
  write "security trigger: <paths>" in the hand-back so the orchestrator runs `security-reviewer`.

## Self-review before hand-over
intent in names · invariants · explicit errors · validated boundaries · idempotent · no N+1 / unbounded queries /
missing pagination · secrets & PII · tests incl. edges · docs with real anchors · lint/static/tests/build green ·
diff = only the task (no drive-by refactors, formatting noise, version bumps).
Hand-back ≤25 lines or ≤1.5k chars (worker-core target ≤15 lines); details go to a file path you name.
