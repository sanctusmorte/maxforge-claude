# Design Scorecard — <slug> — <YYYY-MM-DD> — <commit sha>
Verdict: PASS | FIX | REDESIGN
<!-- First line after the title is exactly `Verdict: PASS` / `Verdict: FIX` / `Verdict: REDESIGN` (the PR guard reads it).
     PASS floors: 0 blockers + 0 majors (minors uncapped); NEW/VALUE: craft ≥8, uniqueness ≥7 (selling ≥8), worse-than-LEAD
     ≤1 axis and never on object; SMALL EDIT: LEAD = before/, no axis worse than before, uniqueness n/a; app: conversion n/a -->
Judge: design-judge (opus) · reviewers: design-critic, slop-detector, marketing-reviewer,
product-reviewer (sonnet, parallel) · ui-qa: <artifacts/ui-qa/<slug>/report.md>

## Scorecard
| axis | score | owner | evidence |
|---|---|---|---|
| pairs | <anchor, screen-first / anchor-first: s\|a\|t each> | design-judge | pairwise placement against the two nearest owner anchors |
| craft | <0-10> | design-critic | <screenshot path> |
| uniqueness | <0-10> | design-critic | <screenshot path> |
| anchors | <anchor file each score was compared with> | design-critic + judge spot-check | `~/.claude/skills/qa-verify/design-anchors.md` |
| vs LEAD reference | worse on <n>/6 axes (<list>) | design-critic | <refs/lead.png> vs <screenshot> |
| position consistency | <n>/6 axes AB = BA (<4/6 → VS_LEAD weak evidence) | design-critic | VS_LEAD_AB / VS_LEAD_BA lines |
| round | <n> of ≤5 (best so far: <n>) | design-judge | `rounds.md` |
| slop | SLOP \| CLEAN (<n>/<total>) | slop-detector | <screenshot path> |
| conversion_readiness | <0-10> | marketing-reviewer | <screenshot path> |
| completeness | <0-10> | product-reviewer | <screenshot path> |
| layout / a11y | pass \| fail (<n> axe critical/serious) | ui-qa | <report path> |

## State matrix
<!-- I11. Every row needs a screenshot path OR an `n/a reason`; the PR guard (hooks/guard-bash.py) treats an empty row as not PASS
     for scorecards dated 2026-11-25 or later. Capture each state with the repo's forceState helper (e2e/ fixtures, `/__kit` route) when
     it has one, else by hand; judge reads the crops/screenshots, not the code. -->
| state | screenshot | verdict | n/a reason |
|---|---|---|---|
| loading | <path> | pass \| fail | <reason> |
| first-use empty | <path> | pass \| fail | <reason> |
| no results | <path> | pass \| fail | <reason> |
| error | <path> | pass \| fail | <reason> |
| partial data | <path> | pass \| fail | <reason> |
| no permission | <path> | pass \| fail | <reason> |
| disabled+reason | <path> | pass \| fail | <reason> |
| long text | <path> | pass \| fail | <reason> |
| 1000 rows | <path> | pass \| fail | <reason> |

## Interaction
<!-- Every PASS scorecard: the PR guard needs `artifacts/ui-qa/<slug>/dead-clicks/report.json` (tools/dead-clicks.mjs,
     ui-qa-protocol.md §E.19) newer than the last UI commit, ≥1 control, 0 NO_EFFECT/ERROR rows that are not allowlisted. A
     screen without controls (copy, colours only): replace the table with the line `Interaction: n/a — <reason>`. -->
| controls probed | live | dead (NO_EFFECT) | error | allowlisted (reason) | skipped destructive | report |
|---|---|---|---|---|---|---|
| <n> | <n> | 0 | 0 | <n — reasons> | <n> | `dead-clicks/report.md` |

Spec `## Controls` rows (control → effect → e2e test) without a green e2e: <none | list> — each is a major.

## Geometry
<!-- Every PASS scorecard: the PR guard needs `artifacts/ui-qa/<slug>/geometry/report.json` (tools/ui-geometry.mjs,
     ui-qa-protocol.md §E.20) newer than the last UI commit with `summary.errors == 0`. No rendered UI change (copy in a
     non-rendered file, config, docs): replace the block with the line `Geometry: n/a — <reason>` (reason required). -->
Report: `geometry/report.json` — errors: <0> · warnings: <n — the ones you fixed / accepted and why> · stress pass: <yes | no>

## Checklists by screen type (yes / no — no scores; one `no` on a starred item = major)
Fill only the blocks that match the screen; every answer cites a screenshot. Detector `defects[]` (ui-qa report.json) are facts, not items.
- **table**: header row present* · sortable or filterable column marked · no column is all "—" · numbers right-aligned · row action visible without hover* · empty/loading rows handled
- **form**: every field has a visible label* · required marked · error text sits at the field* · disabled submit says why* · primary action labelled with its result
- **filters**: active filters visible and clearable* · result count shown · "no results" offers a reset · filter state survives reload
- **dashboard**: one primary number/chart reads first* · no equal-weight card soup · every number has unit + period · drill-down target obvious
- **modal**: one primary action* · closable (×, Esc, backdrop) · content not cut at 390 px* · focus lands inside, returns on close

## Fix list (≤8, ordered blocker → major → minor)
| # | severity | owner reviewer | screenshot | viewport | issue | fix |
|---|---|---|---|---|---|---|
| 1 | blocker\|major\|minor | <reviewer> | <path> | <WxH> | <what's wrong> | <concrete change> |

## Reviewers' disagreements
- <reviewer A> vs <reviewer B> on <screenshot path>: <what they disagreed on> → resolution
  <what the judge decided> — priority reason: <DESIGN.md contract | PROJECT.md goal metric |
  accessibility | marketing | taste>
- <or "none — all four reports agreed">

## Evidence paths
- Screenshots: `artifacts/ui-qa/<slug>/*.png` · ui-qa report: `artifacts/ui-qa/<slug>/report.md`
- Reviewer reports (raw output, pasted or linked): design-critic, slop-detector, marketing-reviewer,
  product-reviewer
- `docs/project/DESIGN.md` · `docs/project/PROJECT.md` · diff: `git diff --stat <base>...HEAD`

## Re-run scope (on FIX)
- Fixes applied: <list, or "-"> · reviewers re-run: <subset that found the fixed issues, or "all">
- design-judge re-run: yes (always, to confirm no regression and issue new verdict)

## Notes for REDESIGN
- Contract broken: <DESIGN.md section / direction sentence violated>
- Back to `/spec`: <what must be re-decided before another design pass>
