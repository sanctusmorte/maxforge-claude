---
name: qa-verify
description: Evidence-based verification of a task against its spec — Protocol A (Bug→Proof→Fix→Proof) or B (Feature→Acceptance matrix→Evidence), goal-backward checks, UI QA, independent `verifier`, verification report. Use before declaring a task done, marking a PR ready, or on "is it really fixed".
argument-hint: <spec path | PR # | issue | "current diff"> [--no-verifier]
---
# /qa-verify — prove it, don't believe it

Inputs: spec path (`docs/project/specs/<slug>.md`, `.planning/...SPEC.md`, PR body) or "current diff".
Output: `artifacts/<slug>/verification-report.md` (template `templates/project/verification-report.md`),
pasted into the PR + Russian summary. Principles: evidence not assertion (command + exit code +
artifact); writer ≠ judge; deterministic sensors gate, LLM reading only advises; "NOT verified"
mandatory; never edit/delete tests to go green.

## 0. Scope
`git diff --stat <base>...HEAD`; changed files, impacted callers (Grep). No REQ ids → derive them
from the spec's acceptance section first.

## Protocol A — bug
1. Repro artifact BEFORE the fix (failing test/Playwright script/`before.png`/curl/SQL).
   Missing → reproduce on base now (worktree); not reproducible → NOT_VERIFIED+attempts.
2. Identical repro on the fix passes; `after.*` next to `before.*` (1440×900+390×844, no animation).
3. Regression test, named for the scenario, RED on base / GREEN on fix (run both).
4. Blast radius: tests of callers/related flows; full suite if shared code changed; exit codes.
5. Real-app pass on a production build for user-visible behaviour.
6. Collateral: diff limited to intended files; no tests edited/deleted; no silent baseline updates.

## Protocol B — feature
1. Evidence matrix: REQ → evidence type → command → result → artifact path.
2. Execute each row (tests, e2e, screenshots 390/768/1440/2560, SQL, contract). UI rows: `ui-qa.mjs` (§E)
   + §F visual inspection (`~/.claude/skills/qa-verify/ui-qa-protocol.md`, Read on demand) — or the `ui-qa` agent.
3. Goal-backward per REQ: exists → substantive (no stubs/placeholders) → wired (real path) → data
   flows (not hardcoded). Grep `TODO|FIXME|lorem|placeholder|return \[\]`.
4. Cross-cutting gates: lint/format, static analysis, scoped + full tests, build, docs updated.
   STATE budget: `python3 ~/.claude/hooks/project-sync.py --check --strict` exits 0 (STATE ≤60 lines, Now ≤3).
5. Rows needing a human → HUMAN_NEEDED with the exact UAT script.

## UI gate — detector + ui-qa + ONE judge (after ui-qa, before the verifier; owner 2026-10-17)
Any user-visible change, app screens (default): (1) deterministic detectors — `npx impeccable detect <changed
dirs>` (regex mode on `.vue`; add `{ "ext": ".vue", "engine": "html" }` in `.impeccable/config.json` for element
rules) + the repo's `design-lint` / `npm run gate`, AND `npx impeccable detect <rendered URL of the dev/stand
page>` (rendered-page rules — contrast, tiny text — never run in source mode; flags/exit codes: `ui-qa-protocol.md`, H5a);
findings are fixed before the judge; (2) `ui-qa` (§E/§F) screenshots + report at 390/768/1440/2560 — `report.json` `defects[]` +
`crops/<type>-<n>.png` (I10) go to the judge as facts; (2b) **state matrix** — one screenshot per state of the scorecard's
`## State matrix` (loading, first-use empty, no results, error, partial data, no permission, disabled+reason, long text,
1000 rows), via the repo's `forceState` helper when it has one (e2e fixtures / `/__kit`), else by hand; a row that cannot
apply gets an `n/a reason`, never a blank (guard-bash: empty row = not PASS for scorecards dated 2026-11-25+); (2c) **interaction**
— `dead-clicks.mjs` on every changed route × mode × 1440/390 (`ui-qa-protocol.md` §E.19) + every spec `## Controls` row has a
green e2e asserting its effect; NO_EFFECT/ERROR = blocker, fixed before the judge (guard-bash: every PASS scorecard
needs a fresh clean `dead-clicks/report.json` or `Interaction: n/a — <reason>`); (2d) **geometry** — `ui-geometry.mjs --stress` per changed route, 390/768/1440/2560
(`ui-qa-protocol.md` §E.20); errors = blocker, fixed before the judge (guard-bash: a fresh `geometry/report.json` with 0 errors or
`Geometry: n/a — <reason>`); (2e) **guidelines** — `ui-qa` step 1d runs `python3 ~/.claude/tools/web-guidelines/scan.py
--diff origin/dev`; BLOCKING `A11Y-1`, `FOCUS-2`, `ZOOM-1`, `FORM-3` fixed before the judge, the rest advisory; (3) ONE `design-judge` (Opus) in SOLO mode, given `artifacts/ui-qa/<slug>/`,
the detector output, `before/` (SMALL EDIT, LEAD) or `refs/` + `plan.md` (NEW/VALUE), `docs/project/DESIGN.md`,
the diff, the task goal; it scores by binary checklists per axis + screen-type checklist and places `overall` by PAIRWISE
comparison with the two nearest owner anchors in both orders (`design-judge.md` SCORING; your own calibration check must exit 0 — a
changed judge input without a recorded re-run = stop). Existing product: floors = 0 blockers/majors, consistency with DESIGN.md, craft ≥ before,
no raw primitives; uniqueness n/a. The judge writes `<worktree>/artifacts/ui-qa/<slug>/scorecard.md` — absolute
path of the worktree the PR is opened from (template `design-scorecard.md`), first line `Verdict: PASS|FIX|REDESIGN`.
PASS is required before "done" and before `gh pr create` (guard-bash checks a PASS scorecard newer than the last UI
commit). FIX → fixes, then a DELTA round: `ui-qa --baseline <previous round dir>` (only changed screenshots re-read)
+ the judge with its previous fix list. ≤3 rounds; REDESIGN / round 3 → stop, show the owner the best round.
Full panel (`design-critic`, `slop-detector`, `product-reviewer`, + `marketing-reviewer`) ONLY for selling surfaces
and new-product hero/first screens (`/site`): one parallel batch with mode, `refs/` (LEAD marked), `plan.md`; no
references → uniqueness capped at 5, no PASS; the judge reconciles the 4 reports + ui-qa; delta rounds re-run only
reviewers that raised a blocker/major; ≤5 rounds. The orchestrator never edits a scorecard or re-labels a verdict.

## Integrated review (quick/full, before the verifier)
ONE independent `code-reviewer` pass on the whole task diff (`<base>...task/<slug>`), never per subtask
(`task-lifecycle.md` Review); + `security-reviewer` on the security trigger. Blockers fixed before the verifier.

## Independent verifier (skip only for "direct" size, `--no-verifier`)
Spawn `verifier`: base ref+worktree, spec/REQ list or bug artifact, draft report. It re-runs the
commands, tries to refute, returns a verdict. Unresolved gaps → GAPS_FOUND.

## Test closure — whole area, not just the diff (before "done")
Gates + UI panel pass → the ENTIRE scope (feature/bug area, not only changed lines) gets end-to-end
coverage in the same PR: backend feature tests via the real entry point (HTTP/job/command), unit
tests for pure logic, and for anything visible a Playwright e2e spec
(`tests/e2e/specs/<domain>/<slug>.spec.ts`, project fixtures) at 390/1440px incl. empty/error states, RUN on the
project's e2e runner / stand; no stand yet → report row `e2e: NOT_VERIFIED (no stand)`, never silent.
Coverage matrix REQ → test name in the report. Missing tests: write now, never defer.

## Report
Verdict first (PASSED|GAPS_FOUND|HUMAN_NEEDED|NOT_VERIFIED) → evidence matrix → root cause
(bugs: observed/expected/mechanism/why tests missed it, regression test path) → gates with numbers →
review + UI scorecard verdicts → test coverage matrix (+ e2e status) → NOT verified (specific) → collateral. Save under
`artifacts/<slug>/` (gitignored), paste into PR. Then: spec `status: verified`, `DECISIONS.md` lines,
STATE Now/Next via `/project-sync`. Reply in Russian: verdict, evidence, NOT-verified.
