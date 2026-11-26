# Task lifecycle (always loaded — the gates; procedures live in skills)

Flow: **triage → `/spec` → build → `/qa-verify` → `/project-sync`** (`/task` runs it; `/project-new` above it).
- **Level gate first:** new repo or new deployable (product, service, site) → **project** → `/project-new`; anything
  else is a **task** (a big initiative inside an existing repo = full task).
- Size gate, stated in one line: **direct** (one-sentence diff, ≤2 files, no spec file) · **quick**
  (one session/PR, inline spec in the PR body) · **full** (multi-session/agent, new subsystem, UI redesign →
  `docs/project/specs/<slug>.md`). Quick/full → run `/spec` before code; ambiguity is scored there, ≤5 questions.
- **Models (owner 2026-10-17):** main session = Opus 5.5 at `high` (owner 2026-11-25; `xhigh` only per hard turn);
  Fable only for research on the owner's explicit request. `general-purpose` and `lite-worker` pin Sonnet 5.5 + medium; `verifier` Opus high.
  `ui-builder` = Opus for NEW/VALUE screens (agent default); the caller passes `model: sonnet` for SMALL EDITs inside
  the kit. Code/security reviewers and `design-judge` = Opus. Worker ambiguity (architecture, security/data loss,
  material design) or two failed fixes → evidence + decision to the caller, not more blind attempts. `ui-builder`
  requires an approved plan. Spec header `model:` records the actual model + effort.
- **Executor (owner 2026-10-17):** direct/quick = the main session codes itself (`code-quality.md` §1); agents per
  task: quick ≤2 (reviewer on trigger, one UI judge), full = every independent unit at once, up to the CLAUDE.md rule 5
  cap + UI gate. Only forks (`subagent_type: "fork"`) share the parent's prompt cache → use one for context-heavy side
  work that needs the current context; a fresh subagent re-pays a ~10k prefix → delegate only when its expected
  throwaway reads are ≥20–30k tokens and ≥5–10 turns remain; one session per task. SendMessage resume only ≤5 min after
  the agent stopped (cache TTL); later = fresh agent from `progress.md`.
- **Spend:** direct narrow reads/small steps; delegate one bounded result with paths, acceptance checks and
  context needed to act. A scout is useful only for substantial discovery, not before every worker. Choose
  `lite-worker` for specified mechanical edits; `general-purpose`/`ui-builder` for prepared implementation;
  built-in `claude` only for work that actually needs orchestration. Judge cost per completed task including
  reloads, retries and quality (aggregate input grows superlinearly; cache and compaction change it): two fresh
  agents are not always cheaper.
- **Continuity:** token-guard keeps the owner's +100k fences per agent type (values: README «Context fences»,
  `hooks/token-guard.py` FENCE_BY_TYPE). The last observed usage triggers a tool fence and handoff skeleton; the
  worker fills it and returns `FENCE-HANDOFF <path>`, the caller starts a fresh same-type agent from those paths.
  Subagent test/build runs foreground ≤270 s; longer → hand back `pending: <run id>`. The hook itself neither stops
  nor spawns agents; a fenced/cold-resume denial is not bypassed. No artificial keep-alive polling: long jobs return
  `pending: <run id>` or a completion notification (the wait parser and repeated-poll gate cover specific patterns,
  not all waits over 240 seconds). Max main-context TTL defaults to 1h; local subagent TTL remains 5m — neither is a
  universal idle rule. Tests stay scoped (`FULL_SUITE=1` remains deliberate).
- **Budget:** spec header `budget:` (quick 60M · full 600M tokens, session + subagents; direct none); hook line every
  10 %; at 100 % finish the atomic step, `/handoff`, ask the owner to extend — no hard stop.
- **Selling surfaces:** run `/site` (signed positioning + copy before pixels). The spec header carries conversion
  goal · primary CTA label · `skills/site/lead-capture-events.md` §G7 events · honest-availability sentence (release state, not dev state — `design-ui-ux.md` §4); "done" includes the
  events firing in prod and the funnel read 14 days after release (DECISIONS.md line).
- Bugs: artifact BEFORE the fix (failing test / Playwright / screenshot at the reported viewport / curl / SQL;
  UI bugs proven on the rendered page); regression test RED first, minimal fix, the same artefact passes after.
- **Split + waves:** subtasks only where they become independent (each ≥ one 1–3 h PR), split by file ownership;
  independent → one parallel batch, dependent → next wave. ≥2 subtasks → integration branch `task/<slug>`, subtask
  PRs into it, ONE PR into base.
- **Review (owner 2026-10-17):** quick = the repo gate (`composer gate` / `npm run gate`) + touched-class tests;
  ONE `code-reviewer` only on the security trigger, a schema/contract change, or the owner's «ревью» — told to
  report correctness and requirement gaps only (Anthropic: a reviewer asked for gaps always finds some). Full =
  subtask self-check; integrated diff = ONE `code-reviewer` + `verifier`. `verifier` on quick only for prod-facing
  bugs. Heavy/architectural (new subsystem, schema/contract, cross-repo) → independent plan review first.
- **UI gate (owner 2026-10-17):** app screens = detectors (`npx impeccable detect`, `design-lint`) + `ui-qa` + `dead-clicks` (every control has an effect) + `ui-geometry --stress`
  (mechanical layout oracle, 0 errors; `Geometry: n/a — <reason>` only without a rendered UI change) + ONE
  `design-judge` (Opus, SOLO) at 390/768/1440/2560, ≤3 rounds; the 4-reviewer panel only for selling surfaces and
  new-product hero screens (`/site`). Existing product: house style 1:1, uniqueness n/a (`design-ui-ux.md` §0.0).
- **e2e:** UI-touching work adds e2e and runs it on the stand; no stand → `e2e: NOT_VERIFIED (no stand)`, never silent.
- Build per CLAUDE.md rule 1. Tests from REQs, RED before code.
- **Security trigger:** `routes/`, middleware, auth/session, uploads, billing, webhooks, secrets/config, raw
  SQL, anything multi-tenant → `security-reviewer` on the integrated diff (`/qa-verify`) before the PR into base;
  findings are blockers.
- **Red base:** lint/tests/CI already red on origin/dev → separate `fix/<gate>-green` PR + STATE Blockers with
  the run URL; never merge on top of a red base silently.
- **Migrations:** additive first → backfill job → switch code → drop later; tested `down()`; destructive
  migration needs a backup step in the PR body; per-tenant failures reported, not ignored.
- Verify with `/qa-verify` (Protocol A/B, goal-backward, `verifier` for quick/full and prod-facing bugs);
  report verdict PASSED | GAPS_FOUND | HUMAN_NEEDED | NOT_VERIFIED with evidence paths and "NOT verified".
- Sync in the same PR: spec status, `DECISIONS.md` line, STATE Now/Next (`/project-sync`).
- **Context:** no context-% thresholds and never stop/offer a new session because of context (owner 2026-10-03:
  the monitor miscounted the window). Handoff before compaction is automatic (PreCompact) or on request. After a PR is opened/merged: `/clear` + continue from `progress.md` (hint only; format in `/task`).
