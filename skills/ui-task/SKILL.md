---
name: ui-task
description: Add, change or redesign a screen inside an existing product (app/CRM, not selling pages) — design system first, references + plan for new/value screens, `ui-builder` in screenshot rounds, design panel until PASS, before/after on 3 viewports. Use for "add a button/field/screen", "переделай экран", "некрасиво" in an app.
argument-hint: [route or screen] [element to add/change]
---
# /ui-task — reuse-first UI change

Selling surfaces (landing, product, pricing, signup) go through `/site`; app screens, redesigns included,
stay here.

This skill only orders the steps. Core rules load by `paths:` only inside the session's project dir (not in
worktrees — `ui-builder` preloads them via design-pack): `rules/design-ui-ux.md` (§0.0, §4, §5), `rules/ui-engineering-qa.md` (§A–§D). On demand:
craft §6–§11 in `~/.claude/skills/site/design-rules.md` (new component or visual decision), QA §E/§F in
`~/.claude/skills/qa-verify/ui-qa-protocol.md`, forms/events §G in `~/.claude/skills/site/lead-capture-events.md`.
Do not restate them here.

0. **Size gate** (`rules/task-lifecycle.md`): one-sentence diff → direct; else `/spec` first. Kind: NEW/VALUE
   screen (new screen, editor, gallery, dashboard, onboarding, empty/first-run, redesign) → all steps, builder =
   `ui-builder` (Opus default); small edit of an existing screen → skip 2–3; SMALL EDIT mode (owner 2026-10-17):
   the main session edits directly (or `ui-builder` with `model: sonnet` when it is a bounded build), one round,
   gate = detector + `ui-qa` + `design-judge` (LEAD = `before/`, floor = no regression; `qa-verify` UI gate).
   Existing product: house style 1:1, uniqueness n/a (`design-ui-ux.md` §0.0).
1. **Context pack** (`rules/design-ui-ux.md` §0.0) — read, in order:
   - `docs/project/DESIGN.md` (direction, tokens, style signature).
   - `docs/project/COMPONENTS.md` (registry: name → path → props/slots → usages). No registry file
     yet → generate/update it per the command DESIGN.md points to, or note the gap and grep instead.
   - `grep`/list 2-3 existing screens closest by route or domain to the target screen; open them.
   - Current screenshot of the target screen: `node ~/.claude/tools/ui-qa.mjs --url <base_url> --routes <route>
     --out artifacts/ui-qa/<slug>/before` (default viewports are already 390/768/1440/2560). Look at it.
2. **References** (NEW/VALUE) — 2–3 best-in-class screens doing the same job (category leaders, not our other
   screens), captured to `artifacts/ui-qa/<slug>/refs/` via `first-screen-measure.mjs --url <public url>`
   (or public product screenshots) + `refs/spec.md`: per reference what to take; one marked LEAD. Via a
   `researcher` agent when the category is unfamiliar. Never ask the owner for them.
3. **Plan** (NEW/VALUE) — `artifacts/ui-qa/<slug>/plan.md` per `design-ui-ux.md` §0.A 3: subject + job, token
   roles used, type levels, ASCII wireframe 390/1440, the ONE bold place, the generic test and what it changed.
   Optional concepts: 2–3 divergent Design Artifacts via `/design` on the product's packet
   (`~/.claude/skills/site/claude-design.md`) — candidates for the plan, never a substitute for the panel.
4. **Components** — list every component you will reuse with its registry path. A gap in the registry
   justifies a new component only with a `docs/project/DECISIONS.md` line. No silent new component.
5. **Build via `ui-builder`** (never `general-purpose` for visual work). The prompt carries: worktree + branch,
   route, subject/job, DESIGN.md path, `refs/` + LEAD, `plan.md`, states to cover, the owner's last verdict on
   this area verbatim if any, and "≥3 rounds per design-pack, report best round". Tokens only; states: loading,
   empty, error, disabled, long text.
6. **Panel loop** — `/qa-verify` UI gate on the best round (`ui-qa` + 4 reviewers + `design-judge`, reviewers
   get `refs/` and `plan.md`). FIX → back to `ui-builder` with the fix list, re-check = delta round (`qa-verify`
   UI gate: pixel-diff baseline, only flagged reviewers, only changed screens); ≤5 rounds total; REDESIGN or round
   5 → show the owner the best round with the scorecard. Before the panel: fill the scorecard's `## State matrix`
   (screenshot per state via the repo's `forceState` helper if it has one, else by hand; `n/a reason` where a state cannot
   exist), run `npx impeccable detect <rendered URL>`, run `dead-clicks.mjs` per route × mode × 1440/390 (protocol §E.19;
   NO_EFFECT/ERROR fixed first, every spec `## Controls` row has a green e2e), run `ui-geometry.mjs --stress` per changed route (§E.20; errors fixed first,
   `--out artifacts/ui-qa/<slug>/geometry`), and hand the judge `report.json` `defects[]` + crops. The judge
   scores by yes/no checklists and pairwise placement against owner anchors. Not done without a PASS scorecard at
   `artifacts/ui-qa/<slug>/scorecard.md` — `gh pr create` is blocked without it (guard-bash).
7. **Hand off** — one labelled before/after index (screen · width · state · what was set by hand) + the verdict;
   "NOT verified" in the first sentence.
