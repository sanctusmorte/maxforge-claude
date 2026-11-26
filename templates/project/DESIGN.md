# <project> — design system (source of truth for UI work)
<!-- Human/lead-owned. ≤120 lines. If this file exists, UI is implemented 1:1 against it — no new palettes,
     fonts or radii without a DECISIONS.md line. Global craft rules: ~/.claude/rules/design-ui-ux.md. -->

## Direction (one sentence)
<e.g. "Quiet, dense B2B tool: warm neutrals, one orange accent, hairline borders, tabular numbers.">
Reference sites / mockups: <paths under design/ or mockups/, URLs>

## Claude Design
- Design-system project: `<Brand> / <Product> — <app|marketing|generated>` · packet `docs/project/design-system/packet.md`
  (+ `screens/`) · last import <YYYY-MM-DD> · rules `~/.claude/skills/site/claude-design.md`

## Style signature (3-5 items)
<3-5 recognisable, repeatable decisions that make a screen unmistakably this product — e.g. type
pairing, grid/rhythm, one signature motion, one non-default device (colour-block headers,
numbered sections). Every new screen must show them; see `~/.claude/skills/ui-task/SKILL.md` step 3.>
1. <…>
2. <…>
3. <…>

## Tokens (where they live)
- File: <src/assets/styles/main.css | resources/css/app.css @theme | packages/ui/src/styles/tokens.css>
- Colours (semantic roles → token): canvas `--bg-main`, surface `--bg-card`, ink `--text-white`, ink-soft
  `--text-muted`, border `--border-color`, accent `--orange`, accent-ink `…`, status: success/warning/error `…`
- Dark theme: <yes: token layer `…` | no: `color-scheme: light` only>
- Radius by role: control <px>, card <px>, sheet <px> · Elevation: <how (border / tinted shadow)>, ≤3 steps
- Spacing scale: 4/8-pt tokens `--space-1..12` · Container widths: <content max, admin max>

## Typography
- Families: display <name (source)>, body <name>, mono <name> — fallback stacks `<…>`
- Scale: <clamp() steps or Tailwind names>, body 16–18px lh 1.5, headings tracking <…>, `tabular-nums` for data

## Components (canonical implementations to copy, never re-invent)
- Button: <path> (variants) · Input/Select: <path> · Table: <path> (density toggle?) · Modal/Drawer: <path>
- Toast: <path> · Empty/Loading/Error states: <path> · Icons: <set, size, stroke>

## Component registry
- Full generated registry (name → path → props/slots → usages): `docs/project/COMPONENTS.md`.
- Generator: <command that (re)builds COMPONENTS.md, e.g. a project script or GitNexus query>.
- Rule: reuse first — every UI task reads this registry before writing a new component; a gap
  justifies a new one only with a `docs/project/DECISIONS.md` line. See `~/.claude/rules/design-ui-ux.md`
  §0.0 and `~/.claude/skills/ui-task/SKILL.md`.

## Motion
- Durations/easings tokens: <--duration-fast 150ms, --ease-out …> · What animates: <list> · Reduced motion: <how>

## Layout patterns
- Marketing hero / sections: <patterns in use> · App shell: <sidebar/rail/bottom-nav rules> · Breakpoints: <list>

## Do / Don't (project-specific)
- Do: <…>
- Don't: <e.g. raw hex in components, new fonts, glass effects, purple gradients, emoji icons>

## QA
- Viewports to screenshot: <390/768/1440 + …> · Mockup compare: <where> · Device target: <e.g. 440×956 DPR3>

## Character scales (skills/site/design-rules.md §1)
serious ↔ playful: <pos> — <why> · luxury ↔ accessible: <pos> — <why> · traditional ↔ innovative: <pos> — <why>
warm ↔ strict: <pos> — <why> · quiet ↔ loud: <pos> — <why> (sets motion level and display weight)

## Lead reference
<competitor or site> — what we take (structure/discipline), what we do not copy · board: docs/project/references/
