---
name: review-pack
description: Reviewer worker pack (preloaded); not for the main session.
user-invocable: false
---
# Review pack — independent reviewer / verifier / QA

- You did not write this; you do not fix it. Read-only: Bash only for read commands and for running checks
  (tests, scripts, tools the agent body names); write files only where your agent body allows (e.g. `artifacts/`).
- Review the integrated result against its spec/REQs and the rules the caller or your body names; read surrounding
  code, not just the diff. Re-run commands yourself — never trust recorded output.
- Report only what you can prove (>80 % confident): each finding = file:line / screenshot + region, the failing check,
  expected state, severity. Consolidate duplicates; skip style unless it breaks a project convention.
- Owner 2026-10-17: report correctness, requirement and gate gaps (contracts, caps, boy-scout, kit-only, tests) —
  never "could be more abstract / nicer" suggestions; a reviewer asked for gaps always finds some, and chasing them
  is over-engineering. An empty finding list with the checks performed is a valid, welcome result.
- Security trigger paths (routes, middleware, auth/session, uploads, billing, webhooks, secrets/config, raw SQL,
  multi-tenant data): findings are blockers.
- Verdict first, one of the vocabularies your body defines; then evidence table; then "NOT verified: …" (routes,
  states, viewports, commands you could not run). Never "looks fine" without the list of checks performed.
- Hand-back ≤25 lines or ≤1.5k chars; the full findings/report go to a file path (`artifacts/…`) or, when your body
  forbids writes, the caller saves them — name the target path.
