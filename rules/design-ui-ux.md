---
paths:
  - "**/*.{vue,tsx,jsx,svelte,astro,html}"
  - "**/*.blade.php"
  - "**/*.{css,scss,postcss}"
  - "**/resources/js/**"
  - "**/resources/css/**"
  - "**/src/{components,pages,views,layouts,features,styles,assets,ui}/**"
  - "**/design/**"
  - "**/mockups/**"
---
# Design / UI / UX — core (path-scoped; split 2026-09-24, section IDs unchanged)

Goal: pages that SELL and screens that work — honest, current, never generic. This core loads on every UI file.
On demand, same IDs — `~/.claude/skills/site/design-rules.md`: §0 pipeline (§0.1 inputs researched, §0.2
portability), §1 character scales, §2 references, §3 first-screen object, §6 typography, §7 colour,
§8 composition, §9 motion, §10 3D, §11 copy, §12 selling mechanics, §13 optional tools. Read it for any selling
surface (`/site`), a new direction or component, or a type/colour/composition/motion decision.
Engineering floor: `ui-engineering-qa.md` §A–§D (QA §E/§F and events §G: its header).

## 0.A Direction before code — the positive core (2026-09-26; why: `skills/site/design-rules.md` §14)
Act as the design lead of a studio whose client already rejected templated work. Bans (§5) only stop the
worst; quality comes from these five steps, on every new screen, redesign or selling surface:
1. **Subject first** — name the subject, the user, the screen's one job. Distinct choices come from the
   subject's own world (materials, vernacular, the artefact the user makes) — the hero/object is the most
   characteristic thing of that world, shown for real: the product's actual output, never a placeholder.
2. **References, not memory** — 2–3 real best-in-class screens for the same job (competitors or category
   leaders; app UI too), captured as PNGs + a per-element spec: what to take from each. One is the LEAD.
3. **Plan, then the generic test** — `plan.md` before code: 4–6 named colours (existing tokens for app
   UI), type roles + scale, ASCII wireframe, ONE bold place, 3 principles. Then ask: "would a similar
   prompt for any other product land here?" — revise every part that would; write what changed.
4. **Build in rounds** — screenshot → Read every PNG next to the lead reference → name the 3 worst gaps
   → fix. ≥3 rounds; keep the best round, not the last. The maker never passes its own work.
5. **Independent judge** (`qa-verify` UI gate, owner 2026-10-17): detectors (`npx impeccable detect`,
   `design-lint`) + `ui-qa` + ONE `design-judge` (Opus) at 390/768/1440; the 4-reviewer panel only for selling
   surfaces and new-product hero screens. New product: generic-but-clean is FIX, not PASS. Existing product:
   consistent-and-clean is PASS (§0.0).

## 0.0 Reuse first — app/CRM screens
App/CRM screens (not selling) skip pipeline stages 1–6 of `/site`: reuse-first via `/ui-task` (DESIGN.md →
COMPONENTS.md → 2–3 closest screens; a new component only with a DECISIONS.md line). Reuse applies to
components and tokens, NOT to quality: a new screen or a value screen (editor, gallery, dashboard,
onboarding, first-run/empty) still runs §0.A 1–5; small edits to an existing screen run §0.A 4–5.
**Existing product (owner 2026-10-17): the house style wins** — DESIGN.md + kit components 1:1 (`vue-ts.md` §0),
uniqueness is n/a, the judge's floors are consistency with DESIGN.md, craft, defects, no raw primitives.
**New product:** kit-first — tokens + 8–12 base components (`shared/ui/`) land before the first screen; direction =
3 concrete concepts (named references, palette, type, the ONE bold place), the owner or the judge picks ONE before
build; then §0.A in full, with the "wow" bar set by the character scale (`design-rules.md` §1).

## 4. Truth — non-negotiable
Every claim is one of: a number from one source constant (with a test that the rendered text equals it) ·
a mechanism stated in verbs · a named artefact the buyer receives. Claims register per site (claim → source
→ status). No invented reviews, logos, user counts, percentages, savings. Planned looks different from
working (dashed/outline) AND is labelled in words («скоро»). Show the real failure path as a trust signal.
**Target state, not dev state** (owner 2026-09-29): "planned" = NOT in the release. Work in flight (backend built
in parallel, pending payment/legal/env/domain) is not planned — UI is built as it will be at release (real CTA,
real flow, real price). Never add waitlist / «скоро» / «продажи откроются» copy, closed modes or availability
flags for it; whether an unfinished flow goes live is a release decision (don't deploy), not UI copy. An interim
state only on the owner's explicit request.
Parity check (`design-rules.md` §0, stage 2) before anything is called a differentiator.

## 5. Anti-generic — the ban list (necessary, not sufficient)
Source: Anthropic `frontend-design` skill + our own rejections. Do NOT produce unless the brief asks. A ban alone pushes the
model to the next common choice, so every bullet ends with **Instead**. Tags: **D** = a detector can check it (CSS/DOM/regex),
**J** = needs the judge's eye, **P** = prose/taste guidance only.
- **D** Purple/indigo→blue/cyan gradients; gradient text; aurora blobs; radial halos; neon glows. Instead: one flat accent from
  the DESIGN.md palette, depth from value contrast and borders.
- **D** Inter / Roboto / Arial / system-ui / Open Sans / Lato / Poppins / Montserrat as "the" font; the safe 2026 clusters Space
  Grotesk, Geist, DM Sans, Instrument Serif by default. Instead: the pairing named in DESIGN.md; none → pick by the product's voice
  and write it down.
- **J** 2026 clusters: cream `#F4F1EA` + italic serif + terracotta `#D97757` (Anthropic's accent — a tell); near-black + lone
  acid-green/vermilion; broadsheet hairlines + zero radius everywhere. Instead: a palette derived from a named source (last bullet).
- **J** SaaS-card kit: 3/6 identical icon-heading-text cards, icon-in-rounded-tile, nested cards, one radius everywhere, the same
  `rgba(0,0,0,.1)` shadow, coloured left accent bars, hairline-everything. Instead: vary the unit by content (a table, a diagram,
  one wide row) and one shadow level per elevation.
- **D** Template chrome: tracked ALL-CAPS eyebrow above every heading; decorative badge above H1 (ONE allowed if it states a
  buying fact); `01/02/03` on non-sequences; `A · B · C` meta strings; `→` appended to links; mono for small labels; one accented
  word in a headline; "scroll to explore"; marquees; spaced em-dash labels. Instead: the heading alone, labels in the body font.
- **J** Centred hero + floating CTA over gradient; big-number hero tile + fake stat strip; emoji as icons; ✨ on AI; stock "team at
  laptop"; plastic AI illustrations; AI-painted backgrounds. Instead: the product's real output as the hero object, CTA beside the
  text it acts on.
- **D** Glassmorphism as decoration. Instead: an opaque surface; blur only on nav bars/modals where content truly overlaps.
- **D** Motion slop: fade-up on every section, hover transition on every card, content parked at `opacity:0`, bounce/elastic easing,
  `ease-in`, `transition: all`, pulsing dots, hover-zoom images. Instead: one purposeful transition per screen (state change,
  100–200 ms ease-out), `prefers-reduced-motion` honoured.
- **D** Copy slop: "Unlock the power of…", "Build faster. Ship smarter.", "all-in-one platform", buzzwords (seamless, robust,
  elevate, harness, leverage, empower, cutting-edge, streamline, game-changer, unleash, delve), em-dash in every line, "Submit"/"OK".
  Instead: a verb + object naming what happens ("Отправить письмо клиенту"), one concrete number or noun per claim.
- **D** Lorem ipsum, placeholder images. Instead: real or realistic domain data from the fixtures. **J** Only happy-path screens,
  unasked dark mode. Instead: the state matrix (design-scorecard.md) covered, one theme.
- **J** Content slop: a glyph (✨, icon, grey box) where the product's real output belongs; template demo data (John Doe,
  Vuexy/admin-kit names and avatars); letters as icons; the same how-to text twice; internal vocabulary (schema names) as headings;
  timestamps with seconds; test tokens in copy. Instead: the real record/output in that slot, user-language headings, relative time.
- **D** Dead half-frame: >35 % of the first viewport empty (counting method `ui-qa-protocol.md` §E.15). **J** Flat page value (all
  sections within ~8 % luminance); ledger-itis (only small-text lists and tables). Instead: fill the viewport with the product's own
  content; give one section a different value/density.
- **D** Accent inflation: the accent on >5 elements in one viewport; a glowing middle pricing tier. **J** the coloured last line of
  the H1 on every page; demo widgets built from unstyled state fragments. Instead: accent only on the one primary action and the
  active state; widgets built from the kit components.
- **P** Invented palette: no brand colour → derive it from a named source (`node ~/.claude/tools/palette-from-wada.mjs <id>`, Wada
  combination; DESIGN.md `palette-source`), never hex from memory (claude.com/blog/improving-frontend-design-through-skills).
  Instead: write the source id into DESIGN.md first.
