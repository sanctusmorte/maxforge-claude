---
name: site
description: Build or rebuild a SELLING web surface (landing, product, pricing, signup) via the 8-stage pipeline with signer gates (positioning, copy first, competitor references, style tiles, first screen judged by the design panel). Use for any new/redesigned selling page, «сделай сайт / лендинг / первый экран», or when the page is unclear, not selling or not beautiful.
argument-hint: [project path] [stage to start from, 1-8]
---
# /site — selling surface, meaning before form

Rules (Read at start; not auto-loaded): `~/.claude/skills/site/design-rules.md` (§0 pipeline, §1 scales,
§2 references, §3 object, §6–§11 craft, §12 selling mechanics), `~/.claude/skills/site/lead-capture-events.md`
(§G forms + events), `~/.claude/skills/qa-verify/ui-qa-protocol.md` (§E tiers, §E.15 measurement, §F inspection); path-scoped
core `rules/design-ui-ux.md` (§4 truth, §5 ban list). Do not restate them here.
Artefacts live in the project: `docs/project/site/` (one file per stage) + `docs/project/references/`.
Signer decisions → one line each in `docs/project/DECISIONS.md`. NEVER ask the signer for inputs (§0.1).

## Start
Read what exists: `docs/project/site/*`, PROJECT.md, DESIGN.md, specs, pricing constants, claims register.
A stage whose artefact exists AND carries a signer line in DECISIONS.md is done — start at the first
unsigned stage. State in one line: "starting at stage N because …".

## Stages (deliverable → exit)
1. **Brief** → `site/brief.md`: product, price, buyer, traffic source, awareness stage, buying cycle, real
   assets (product UI? photos? numbers?), constraints. Research it from the repo, specs and the web.
   Exit: no contradiction with specs/pricing.
2. **Positioning** → `site/positioning.md`: Dunford's 5 steps. PARITY CHECK via a `researcher` agent: for each
   alternative, read its own pricing/feature pages TODAY, quote what it ships, strike every "differentiator"
   it already has. Exit: `SIGN`.
3. **Copy** → `site/copy.md`: the four first-screen answers; 3–5 headlines; anxiety removers; text for every
   block; claims register rows. Run `marketing-reviewer` in text mode on the first-screen copy (5-second
   test: what / for whom / why this and not the alternative). Exit: reviewer passes + `SIGN`.
4. **Architecture** → `site/architecture.md` + grey wireframes 390/768/1440 (ASCII or grey HTML): block
   order from the awareness stage, two-screen rule marked. Exit: every block has copy from stage 3.
5. **Character + references** → `site/character.md` (five scales with one-line reasons) and
   `references/` : competitor list, strong/weak ranking table with dated public signals (§2), 3–5
   screenshots at 390 + 1440 of the strong ones, and a SPEC per reference (sizes, weights, colour roles,
   whitespace, object type, motion). One reference named as the lead. Runs in parallel with 3–4.
6. **Style tiles** → 2–3 tiles (bold / moderate / restrained) as live HTML, one width (1440), each in its own
   worktree + port, each with the REAL headline and one figure. Tiles must DIVERGE: different concept (object,
   composition, type), not one layout in three skins — same hero split / CTA pair twice = redo one. No polish
   rounds on anything the signer has not picked. Each tile names its palette: the brand palette, or a Wada
   combination id (`node ~/.claude/tools/palette-from-wada.mjs --search <hue|name>` → `<id> [--dark]` → CSS
   tokens + WCAG table); the picked tile's source goes to DESIGN.md as `palette-source: brand | wada:<id>`. Cheap divergence option: 3–4 wireframe directions via Claude
   Design (`/design`, rules `~/.claude/skills/site/claude-design.md`) in the product's work project, then tiles. Measure with §E.15. Show the signer a labelled
   index page (one link per tile, what it is, what it costs). Exit: signer picks → tokens in DESIGN.md.
7. **First screen** → built at 390 / 768 / 1440 on the picked tile and the signed copy; hero object marked
   `data-figure`; object priority §3 (real product first). Judge loop, ≥2 iterations before the signer:
   `node ~/.claude/tools/first-screen-measure.mjs` → `slop-detector` + `marketing-reviewer` + `design-critic`
   in parallel (each gets `references/` with the LEAD + the picked tile) → `design-judge` → fix → repeat until
   PASS, ≤5 rounds, keep the best. Built by `ui-builder`, whose prompt carries the signed copy, `character.md`,
   `references/` + LEAD spec, the picked tile and the owner's last verdict verbatim. Then show the signer the
   labelled index. Exit: `SIGN`.
8. **Rest of the page → release** — section by section on the same tokens, each section screenshotted and
   §F-inspected; §G events; release-tier §E; `ui-qa` agent; `/qa-verify`. Post-launch: read the funnel after
   14 days (DECISIONS.md line).

## Showing work to the signer
One labelled index page per round (what it is · width · scenario · what was set by hand · strong · weak ·
the orchestrator's verdict) + live links. Say what was NOT verified in the first sentence. Never present a
candidate the panel failed without saying so.

## Anti-patterns this skill exists to prevent (all happened 16–23.09.2026)
Design before copy · candidates with zero references · objects drawn in CSS while the real product existed ·
differentiators the competitor already ships · the maker judging its own work · building 3 full first
screens where 3 style tiles would have decided the direction · asking the signer for materials ·
(26.09 audit) zero runs of this skill in two weeks — six prototypes in one template, references left in a
scratchpad, executors given prose instead of PNGs, waves of polish on a direction nobody signed.
