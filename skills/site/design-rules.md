# Design rules — on-demand part of `rules/design-ui-ux.md` (moved 2026-09-24, section IDs unchanged)

Loaded on demand, not by `paths:`. Read it for any selling surface (`/site` runs §0), a new visual direction,
a new component, or a typography / colour / composition / motion decision. The path-scoped core
`~/.claude/rules/design-ui-ux.md` keeps §0.0 reuse-first, §4 truth and §5 ban list; the engineering floor is
`~/.claude/rules/ui-engineering-qa.md` §A–§D; QA §E/§F: `~/.claude/skills/qa-verify/ui-qa-protocol.md`;
lead capture + events §G: `~/.claude/skills/site/lead-capture-events.md`.

Goal: pages that SELL — the offer is understood in 5 seconds, the design is beautiful and current, and the
whole thing is honest. Works for any business: style changes with the business, selling architecture does not.
Procedure for a selling surface: skill `/site`. Draft basis + evidence:
`~/.claude/drafts/selling-web-design-concept-2026-09-24.md`.

Why this file changed (2026-09-24): the old version was mostly Anthropic's `frontend-design` skill — it only
fights generic output and says nothing about selling. Five directions for one site were rejected in a week,
none for craft, all for meaning/taste. Root causes: design before copy; zero references; objects drawn in CSS
instead of the real product; "differentiators" the competitor already ships; the maker judged its own work.
Anti-generic is necessary, not sufficient.


## 0. Pipeline — meaning before form (every selling surface: landing, product, pricing, signup)
Each stage has a deliverable; `SIGN` = the signer (owner today, client in the product) looks and says yes/no.
1. **Brief** — business, price, audience, traffic source, awareness stage (Schwartz: unaware → most aware),
   buying cycle, real assets on hand. Researched, not asked (§0.1).
2. **Positioning** (Dunford) — competitive alternatives incl. "do it myself / do nothing" → unique attributes
   → value → who cares most → category. Every attribute passes the PARITY CHECK: read what the alternative
   already ships (its own pricing/feature pages, dated); anything they ship is not a differentiator. `SIGN`.
3. **Copy first** — first screen answers four questions in words: who it is for · what it does · what you
   receive · why us rather than the named alternative. 3–5 headline candidates (clear beats clever; value
   clarity outweighs everything but visitor motivation — MECLABS C=4m+3v+2(i−f)−2a); anxiety removed next to
   the CTA (risk, guarantee, what is NOT included); copy for every block; claims register (§4).
   5-second test on the TEXT by `marketing-reviewer` before any pixels. `SIGN`.
4. **Architecture** — block order from the awareness stage (default problem → solution → proof → objections
   → price → action; a heuristic, not a law); TWO-SCREEN RULE: offer + proof + primary action inside the first
   two screens (NN/g: 57 % of viewing time above the fold, 74 % in the first two). Grey wireframe 390/768/1440.
5. **Character + references** — place the business on the scales (§1); research competitors and pick 3–5
   REAL references from the strong ones (§2); deconstruct each into a spec (sizes, weights, colour roles,
   whitespace, object type, motion) — a spec, not a description.
6. **Style tiles** (Samantha Warren) — 2–3 variants bold / moderate / restrained as live HTML at one width:
   type, palette, buttons, one block, one figure style, the real headline. Cheap by design. `SIGN` (pick).
7. **First screen, high fidelity** — approved copy + picked tile, art-directed separately at 390 / 768 /
   1440. Object priority §3. Judged by the design panel (slop-detector + marketing-reviewer + design-critic →
   design-judge), ≥2 fix iterations BEFORE the signer sees it; the maker never judges its own work. `SIGN`.
8. **Rest → build → QA tier → events → improvement loop** — section by section on the same tokens;
   `ui-qa-protocol.md` §E tiers; `lead-capture-events.md` §G events ship with the surface; <5 000 sessions/month → no A/B, only
   qualitative fixes; a release nobody measured is unfinished.
App/CRM screens (not selling) skip 1–6: reuse-first path, `rules/design-ui-ux.md` §0.0.

### 0.1 Inputs are researched, never requested (owner rule 2026-09-24)
Never ask the signer for references, photos, brand assets or materials — default is that none exist. Find
them: competitors for references (§2), licensed or generated imagery for pictures (§3). Showing results at a
gate is welcome; asking for inputs is not. Use what the signer volunteers.

### 0.2 Portability
These rules are also loaded by an app factory (executor sessions read the same `~/.claude`). Write
project facts in the project's docs, never here; keep "signer" as a role.

## 1. Character scales → decisions (what legitimately changes per business)
Place every business on five scales before any visual choice; record them in DESIGN.md:
serious ↔ playful · luxury ↔ accessible · traditional ↔ innovative · warm ↔ strict · quiet ↔ loud.
Derive from sphere, price level and audience, not taste. They drive:
- **Type**: quiet/luxury → light display (w200–400), size carries hierarchy; loud → heavy display
  (w700–900) allowed. Contrast by extremes either way (≥3× size jumps, weights far apart), never 400 vs 600.
- **Palette**: luxury/serious → achromatic base, one restrained accent; playful → higher chroma, still one
  accent hue.
- **Density & whitespace**: luxury → air around few objects; accessible/local → denser, faster to action.
- **Motion level (owner decision 2026-09-24)**: premium, finance, serious → quiet (motion only where it
  explains a mechanism); enthusiast/consumer/playful → louder (a live, animated or interactive moment on the
  first screen). Never the §5 slop patterns at either end.
- **Copy voice**: formal "вы" and full sentences at the serious end; conversational at the playful end.
- **Proof type**: B2B/complex → real product + mechanism + numbers; premium service → specificity and
  guarantees; local → reviews, address, fast contact.
Default reading of sphere (examples, not law): B2B SaaS → product screenshots, several CTAs by role;
premium/luxury → cinematic, neutral palette, emotion; local/professional → trust and the shortest path to a
request; fintech → conservative colour, product UI as proof.

## 2. References come from competitors
1. List direct and closest competitors (same job for the same buyer, incl. adjacent substitutes).
2. Rank strong vs weak by public signals, each labelled as an estimate with its date: traffic (SimilarWeb
   free estimate), brand demand (Yandex Wordstat / Google Trends), revenue for Russian legal entities
   (bo.nalog.ru — public statements; the hardest signal available), reviews (Yandex Maps, 2GIS, sector
   sites), scale (hh.ru vacancies), ad presence (public ad libraries where they exist).
3. Strong ones → 3–5 references, captured as screenshots at 390 and 1440 and deconstructed into a spec.
   Weak ones → the "do not" list. Add 1–2 cross-sphere references from Awwwards / Godly / Land-book / Mobbin
   when the sphere's own leaders are visually weak.
4. Anchor ONE reference as the lead for the first screen; borrow structure and discipline, never copy
   layout, copy or assets. Save the board to `docs/project/references/` (images + spec + ranking table).

## 3. The object in the first screen
A marketing first screen needs an object (§6 ban: type alone on flat colour). Priority:
1. **The real product** — its actual UI, captured and anonymised (no names, ids, timestamps). NN/g: users
   study images that carry information and ignore decorative ones. Best-in-class sites (Linear, Cursor,
   Arc, Mercury) lead with their real product.
2. **Real photography** of the real thing (place, work, people who actually work there).
3. **Licensed stock or generated imagery** — the agent chooses it (Unsplash / Pexels licences allow
   commercial use; generation only when a tool is available). Never passed off as "our team / our office /
   our clients" — that is an invented trust cue.
4. **Pre-rendered still** (AVIF ≤200 kB, one key light) when a 3-D object is truly needed.
5. **Drawn CSS/SVG illustration** — last resort; agent-drawn objects have been rejected repeatedly as
   crude. A diagram is welcome when it carries information (a mechanism, a comparison), not as decoration.
Never an image without a licence; never a competitor's asset.

## 6. Typography
- 1 family, or 2 clearly distinct (serif + grotesk, display + mono). Cyrillic required for Russian sites;
  self-host; real fallback stack with metric overrides. Log families per project in auto-memory
  `design-fonts.md`. A family is BURNED only if another project uses it or the signer rejected it AS A TYPEFACE
  — appearing in a rejected candidate does not burn it.
- Distinctive picks (★ Cyrillic): grotesk — Bricolage Grotesque, Manrope★, Onest★, Golos Text★, Geologica★,
  IBM Plex Sans★, Source Sans 3★, Wix Madefor★, Commissioner★, Satoshi, General Sans, Cabinet Grotesk;
  serif — Fraunces, Newsreader, Literata★, Spectral★, Source Serif 4★, Petrona★, Piazzolla★, Vollkorn★,
  Cormorant Garamond★; display — Unbounded★, Syne, Clash Display; mono — IBM Plex Mono★, JetBrains Mono★.
- Modular scale 1.2 mobile → 1.25–1.333 desktop, 5–7 steps, fluid `clamp()`. Display ≥3.5× body on
  marketing (≥4× first screen) as the default; hierarchy through weight, colour and tracking, not size alone.
  Tracking −0.035…−0.065em at ≥64px; +0.10…+0.14em on labels ≤13px. ≤2 distinct sizes below 20px per
  viewport, counting page copy only (labels inside a declared figure are the figure's own scale).
- Body 16–18px, lh 1.4–1.6, measure 45–75ch; display lh 1.0–1.15; `text-wrap: balance` h1–h3, `pretty` on
  body; `tabular-nums` for data; everything in rem/em.

## 7. Colour
- OKLCH tokens; 4–6 named roles (canvas, surface, ink, ink-soft, accent, accent-ink) + semantic colours
  ≠ accent. Achromatic-leaning base + ONE accent used sparingly (the best product sites all do this).
  Neutrals hue-biased by choice; may carry more than one bias. No pure `#000` on light / `#fff` on dark.
- Contrast measured on the render: body ≥4.5:1, large text/UI/icons/focus/chart marks ≥3:1.
- Light-only → declare `color-scheme: light`. A dark theme is designed (tinted surfaces, lighter-surface
  elevation, desaturated accents), never `filter: invert`.
- Shadows: one light source, layered, tinted toward the canvas, ≤3 elevation steps, almost invisible.

## 8. Composition
- First viewport = one composition: wordmark + headline + one sentence + primary CTA + the object (§3).
  Left-anchored or asymmetric beats centred-everything. No cards and no badges on the hero object.
- One job per section; the page is understood by scanning headlines only. Structure (borders, numbers,
  dividers, labels) only where it encodes information.
- Not everything is a card: vary size and treatment; mix list / table / prose / rails; zigzag ≤2.
- 4/8-pt spacing scale, `gap` not margins, proximity encodes grouping, more space above a heading than below.
- Containers: `container-type: inline-size` for components; media queries only for the shell; `@layer`;
  logical properties.
- Mobile (390) and tablet (768) are art-directed separately — re-crop the object, reorder layers, step the
  display down — never a shrunk desktop or a stretched phone.
- Spend boldness in ONE place; remove one element that carries no information before shipping (Chanel).
  "Expensive, not empty": whitespace is only premium when a real, precise detail stands in it.

## 9. Motion (level set by §1)
- CSS/WAAPI first; GSAP for timelines; Motion for component/gesture; never two for one job. Animate only
  transform, opacity, clip-path, filter. ≤300 ms for UI response (180 ms reads faster than 400).
- Easing: enter/exit `cubic-bezier(0.23,1,0.32,1)`; move `cubic-bezier(0.77,0,0.175,1)`; never `ease-in`.
- One orchestrated moment beats scattered effects; motion that answers a user action is welcome.
  Everything readable at rest; nothing parked at `opacity:0`; reduced motion = fewer and gentler, and the
  page still conveys every fact.
- Loud end of §1 may add: kinetic type (mask reveal once), cursor-reactive light (fine pointers, ≤4px,
  spring return), pinned storytelling (one per page, pin ≤2 viewports, native scroll rate, skip link, static
  fallback, off <768px), section colour transitions, card-stack fan-out for tiers (desktop). Scroll-jacking stays banned.
- Hover only under `@media (hover:hover) and (pointer:fine)`.

## 10. 3D / WebGL
Only when the object IS the product (configurator, world). Otherwise a pre-rendered still. Two agent-built
three.js heroes were rejected on sight (2026-09-17). If ever used: WebGPU → WebGL2 → poster ladder, ≤1 MB
mobile, render on demand, dispose on unmount, poster under reduced motion / saveData / low memory.

## 11. Copy
Buyer's words, not the system's. Active voice, sentence case, plain verbs, no filler. Clear beats clever
(Wynter). Numbers beat adjectives; never invent claims. CTA = verb + the thing received, true to what
happens; the action keeps its name through the flow. Errors say what happened and how to fix it.
Simple text converts better (Unbounce 2024: 5th–7th-grade reading level 11.1 % vs professional 5.3 %).

## 12. Selling mechanics (with §0)
1. One conversion goal per page, one primary CTA label; secondaries visually subordinate.
2. First screen answers who / what / receive / next, visible without scrolling at 360×640 and 390×844.
3. CTA label = verb + what the user actually gets; banned: «Начать», «Подробнее», «Узнать больше»,
   "Get started", "Learn more". If the step costs commitment, the label says so.
4. Repeat the primary CTA at most once per two screens and never twice in one viewport; each repeat
   carries a new reason.
5. Page length follows the awareness stage and decision style, not price alone (CXL: short pages beat long
   ones in documented cases) — treat length as a hypothesis.
6. FAQ = real objections in the buyer's words; an honest "no / not yet" is the first sentence; ≤8 on a landing.
7. Price is public: tiers, a comparison, an explicit "what is not included"; anchor against the alternative
   the buyer already knows. Do not build a grid around a decoy tier — the effect failed replication
   (Frederick 2014; Yang & Lynn 2014: 11 of 91 attempts).
8. Trust without testimonials (ship ≥3): real artefact from a real run · self-serve demo · public dated
   changelog · methodology page · explicit failure path and "what we do not do" · real legal identity with
   a human channel.
9. Zero-commitment path on every selling page; an unfilled contact placeholder fails the release gate.
10. Done = `lead-capture-events.md` §G events live and the funnel read once.

## 13. Optional tools (not rules)
Anthropic `frontend-design` skill (rev. 2026-09-03 — its persona, subject-first and two-pass plan are core
§0.A) · Vuetify MCP (configured) for correct Vuetify 3 APIs · Refero / Mobbin MCP for references and a
generation MCP (fal) for imagery — only after the owner approves the paid trial · `impeccable` (pbakaus)
command vocabulary (bolder / quieter / polish / critique) — ideas only, never its installer (adds hooks).

Claude Design (`/design`, claude.ai/design): operating rules, hierarchy and economy — `claude-design.md` (same dir).

## 14. Why §0.A exists (diagnosis 2026-09-26, evidence `~/.claude/drafts/design-diagnosis-2026-09-26.md`)
Across several products (selling site, AI-cards, prototypes) the panel, references and
style tiles never ran — zero scorecards; six prototypes were one template in six skins; objects drawn in CSS;
✨ placeholders where the product's output belongs; polish rounds spent on a direction nobody had approved.
Rules were mostly bans, loaded on demand where the worker writing the UI never read them; app screens were
exempt from references; the judge passed any screen without defects, however generic. Fixes: §0.A in the
path-scoped core, the `ui-builder` worker with `design-pack`, a judge that needs a reference comparison and
score floors to PASS, calibration anchors, and the PR guard that blocks UI PRs without a PASS scorecard.
