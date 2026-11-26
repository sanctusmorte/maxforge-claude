# <Feature or bug title>
<!-- One spec per feature/bug in flight. Status: draft → clarified → approved → in progress → verified → shipped. WHAT/WHY here; HOW goes to ## Plan. Keep each REQ testable. -->
status: draft · owner: <human> · created: <YYYY-MM-DD> · type: feature | bug | refactor · size: quick | full · model: <session model + effort; subagents inherit> · budget: <60M quick | 600M full> tokens
links: issue <#|-> · PR <#|-> · milestone <M-n|->

## Goal
<one measurable sentence>

## Non-goals / out of scope
- <…>

## Context (existing behaviour, code, docs)
- <path/File.php::method> — <what it does today>; docs: <docs/domains/x.md#section>
- Existing — DO NOT recreate: <list>

## Reproduction (bugs only — must exist before any fix)
- Env/tenant/role/viewport/data: <…>
- Artifact proving the bug: <failing test path::name | Playwright script | screenshot path | curl + response | SQL + rows>
- Root cause: observed / expected / mechanism / why tests missed it

## User stories (features)
- US1 (P1) As a <role> I want <capability> so that <outcome>

## Acceptance criteria (EARS; every REQ maps to evidence in verification)
- REQ-1 WHEN <trigger> THE SYSTEM SHALL <response>
- REQ-2 IF <failure> THEN THE SYSTEM SHALL <handling>
- REQ-3 (UI) <state: empty/loading/error/success> SHALL <…>; responsive at 390/768/1440

## Requirements status
<!-- Only the status/evidence cells change. todo → red → green by the implementer; `verified` ONLY by the verifier agent. `python3 ~/.claude/tools/req-status.py <spec.md>`; Stop is blocked once while a row ≠ verified. -->
| REQ | status | evidence |
|-----|--------|----------|
| REQ-1 | todo | |
| REQ-2 | todo | |

## Contracts
- Data: <tables/columns/enums> · API: <method path → payload/response> · Events/jobs: <…>

## NFRs
- <latency/volume/security/i18n/a11y with numbers>

## Assumptions ledger
- A-1 <assumption> | evidence: <path/link> | if wrong: <consequence> | confidence: <high/med/low>

## Clarifications
### Session <YYYY-MM-DD>
- Q: <…> → A: <…>

## Plan (HOW) — milestones and tasks
- M1 (walking skeleton): <exit criterion>
- [ ] T1 [wave 1] <what> in <files> — refs REQ-1 — verify: `<cmd>` → <expected>
- [ ] T2 [wave 1] [P] <what> in <files> — refs REQ-2 — verify: `<cmd>` → <expected>
- [ ] T3 [wave 2] depends T1 — …

## Verification plan (evidence per REQ)
| REQ | evidence type (test / e2e / screenshot / SQL / UAT) | command / script | artifact path |
|-----|-----|-----|-----|

## Definition of done
- All REQ rows have passing evidence · regression test for bugs · local gate green · docs updated in the same PR · every `## Requirements status` row `verified` · verification report attached to PR · DECISIONS updated
