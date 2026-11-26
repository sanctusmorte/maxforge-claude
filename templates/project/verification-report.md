# Verification Report — <spec slug / issue> — <YYYY-MM-DD> — <commit sha>
Verdict: PASSED | GAPS_FOUND | HUMAN_NEEDED | NOT_VERIFIED
Verifier: <agent + model> · fresh context: yes/no · tools: read-only · wrote the code: no

REQ rows: `python3 ~/.claude/tools/req-status.py <spec.md>` → paste the counts; set `verified` in the spec's `## Requirements status` only for rows proven below.

## Scope
Changed files: <paths> · Impact (callers/flows): <list> · Out of scope: <list>

## Evidence matrix
| REQ / bug | evidence type | command | result (numbers) | artifact |
|---|---|---|---|---|
| REQ-1 | feature test | `php artisan test --filter=X` | 12 passed, 0 failed | artifacts/<slug>/req1.log |
| REQ-3 | screenshot 390/768/1440 | `node qa/shots.mjs` | overflow 0, targets ok, §F verdict OK | artifacts/<slug>/req3-*.png |
| bug | repro script | `npx playwright test repro.spec.ts` | before: FAIL (expected) / after: PASS | artifacts/<slug>/before.png, after.png |

## Root cause (bugs)
observed / expected / mechanism / why tests missed it · regression test: <path::name>

## Gates
lint/format: exit 0 · static analysis: exit 0 · scoped tests: N/N · full suite: N/N (skipped k) · build: exit 0 · UI QA §E/§F: <n screenshots, verdicts> · a11y: 0 serious/critical · docs updated: <paths>

## NOT verified (mandatory, specific)
- <flow / browser / tenant / data shape> — why

## Collateral
git diff limited to: <files> · tests edited/deleted: none · baselines updated: none · risk: low/med/high
