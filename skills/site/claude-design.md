# Claude Design — operating rules (on demand; researched 2026-09-26, sources at the end)

Read before any `/design`, Design Artifact, or claude.ai/design work. Pipelines `/site` (stage 6 tiles) and
`/ui-task` (step 3 concepts) may use it; the implementation still goes through `ui-builder` + the panel.

## What it is (Sep 2026)
- claude.ai/design (Labs, since 2026-04-17) + in Claude Code: `/design "<brief>"` → a Design Artifact canvas of
  `.dc.html` artboards (research preview, CLI ≥2.1.265; needs the Artifact tool: `~/.claude/tools/artifact.sh on`,
  next session). The design skill reads the project's design system (CLAUDE.md token notes, theme file);
  priority = prompt > design system > its own choices.
- Usage is SHARED with chat + Claude Code (no separate allowance since 2026-06-17) — heavy design eats code capacity.
- `/design-sync` + `DesignSync` sync a React dist/Storybook into a claude.ai design-system project. **Vue is not
  supported** — our SPAs (Vue/Vuetify) use the packet route below. `/design-login` is interactive-only.
- No folders or nesting in claude.ai: hierarchy lives in NAMES (below). No version history: export snapshots.

## Separation and hierarchy (one design system per product surface; names are the hierarchy)
- Design-system project: `<Brand> / <Product> — <app|marketing|generated>`, e.g. `Acme / CRM — app`.
  A shared brand core only when products truly share tokens (verified in code): `<Brand> / Core`.
- Work projects (screens, flows, tiles): `<Brand> / <Product> / <screen or flow> — <YYYY-MM>`, always linked to
  that product's design system; never mix products in one project or chat.
- Source of truth = the repo, never the claude.ai copy. Per repo: `docs/project/design-system/packet.md` (+
  `screens/`), registry of names and status in `~/.claude/portfolio.md` §Design systems.

## The packet (what is uploaded / imported; regenerate after any theme change)
`packet.md`: product + surface, one-sentence direction, tokens by role WITH values (from the theme/tokens file,
not memory), type scale, radius/elevation/spacing, components by their framework names (VBtn, VDataTable…) with
paths, states (empty/loading/error/disabled), CURRENT vs FORBIDDEN (legacy screens, admin-template leftovers, §5
bans), 2–3 external references (LEAD), the claude.ai DS name + last import date. `screens/`: 6–10 clean,
anonymised viewport PNGs of the best current screens (no demo data, no placeholders).

## Economy (what burns shared usage)
- Decide before prompting: brief + packet + references ready; start with 3–4 divergent wireframe directions,
  pick one, only then high fidelity. Regenerations and long derailed threads are the main cost.
- One chat per screen/flow; a direction change → a fresh chat. Small tweaks on the canvas (manual edits cost no
  tokens); batch the rest in one message with explicit "keep" constraints.
- Upload viewport crops, not full-page screenshots or whole decks. Never paste the codebase.

## Quality
- Design system first; name components by framework names; ask for empty/error/loading states explicitly.
- Divergence: 3–4 directions that differ in concept (object, composition, type), not skins; combine the best.
- Label assets current vs outdated (old uploads leak into new work); give specific feedback (px, token names).
- Weak spots: generic SaaS look, drift from the system across sessions, data/product judgment — the panel
  (design-critic vs LEAD, anchors) still judges every artefact; a Claude Design output is a candidate, not a PASS.
- Handoff to code: the bundle/artboards go to `ui-builder` with "implement with existing components/tokens, no
  new CSS values"; decisions (type scale, colour roles) are written back to DESIGN.md, not left in chats.

Sources: anthropic.com/news/claude-design-anthropic-labs (04-17) · claude.com/blog/claude-design-stays-on-brand-
for-daily-work (06-17) · support.claude.com articles 14604416, 14604397, 14604406, 12138966 (release notes 09-16) ·
code.claude.com/docs/en/artifacts · code.claude.com/docs/en/whats-new/2026-w34 · claude.com/blog/how-the-product-
designer-who-built-claude-design-uses-it… (07-24) · wmedia.es (design-sync React-only) · aiuxplayground.com (tokens).
