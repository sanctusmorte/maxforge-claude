# UI QA protocol — `ui-engineering-qa.md` §E (QA tiers) and §F (visual inspection) (moved 2026-09-24, IDs unchanged)

Loaded on demand, not by `paths:`. Read it before declaring UI done: the `ui-qa` agent, `/qa-verify`, `/ui-task`
step 5, `/site` (prototype tier §E.0 + §E.15 measurement) and `verifier` run it. "UI done" means §E ran green.
Floors it checks: `~/.claude/rules/ui-engineering-qa.md` §A–§D, `~/.claude/rules/design-ui-ux.md` §5;
events for §E.14: `~/.claude/skills/site/lead-capture-events.md` §G7.

## E. QA protocol — run before declaring UI done
0. **Tiers.** PROTOTYPE (a direction candidate, style tile or first-screen candidate): 390×844 / 768×1024 /
   1440×900 + one reduced-motion capture, §E.15 measurements, §F inspection of every PNG, lint clean — nothing
   more; say "prototype tier" in the report instead of listing skipped checks. RELEASE (anything shipped to
   users): the full protocol below.
1. Production build (the project's production build command as named in its CLAUDE.md — on some projects the
   plain `npm run build` is deliberately failing or destructive), serve it, Playwright with Chromium + WebKit projects
   (`mcp playwright` tools or a script in the scratchpad). Never QA the dev server only.
2. For each route/state — list, detail, form (pristine + invalid), modal/drawer open, empty,
   loading, bulk-selected — at 360×800, 390×844, 430×932, 768×1024, 1024×768, 1280×800, 1440×900,
   1920×1080, 844×390 (landscape), 640×800 (=200 % zoom) and 320×568: full-page screenshot to
   `qa/<route>/<w>x<h>.png`; repeat with `reducedMotion: 'reduce'` and `forcedColors: 'active'`;
   the `emulateMedia` dark pass only when the project ships a dark theme (light-only → state
   "dark: n/a" in the report). Live states for review: `ui-qa.mjs --states` → `states/*-cta-strip.png`
   (rest | hover | focus-visible), `states/*-form-strip.png` (pristine | invalid), `anim/*-anim<i>-strip.png`
   (N frames across each `[data-anim]` element, `--frames`, default 6) + `*-reduced.png`. Minimum for small changes: 390 / 768 / 1440. Captures meant for reading: viewport-only
   or element crops ≤1280 px wide, unless a full-page shot is itself the evidence (tokens; §F).
3. DOM assertions per viewport (fail on any):
   `scrollWidth > clientWidth` (list offenders with `rect.right > innerWidth + 1`) · visible
   standalone controls with rect <24px, excluding inline `a` inside text (<44 primary on ≤430) ·
   inputs with computed font-size <16px on ≤430 ·
   `img` without width/height and without CSS aspect-ratio · above-fold `loading="lazy"` · LCP
   image without `fetchpriority="high"` · ≠1 `h1`, skipped heading levels, missing `main`/`nav` ·
   inputs without label/aria-label · fixed+sticky heights >30 % on ≤430 · white `body` under dark
   scheme (dark-theme projects only) · under reduced motion, any animation or transition with
   duration >250 ms, translate >8 px, scale, parallax, `infinite` iteration or autoplay — a short
   fade is compliant (design-ui-ux.md §5) and is not a failure.
4. Focus walk: Tab ×60 recording `activeElement`; each has a visible indicator, lies in the
   viewport, `elementFromPoint(center)` resolves to it (not a sticky bar). Each dialog: focus
   inside, Esc closes, focus returns, background not focusable.
5. Route change: `activeElement` is the new `h1`/`main`, `document.title` changed.
6. axe (`@axe-core/playwright`, tags wcag2a/2aa/21a/21aa/22aa) per route incl. modal-open and
   error states: zero critical/serious.
7. Web vitals (budgets: web.dev/articles/vitals): `ui-qa.mjs` writes `vitals` per route × viewport to
   `report.json` — LCP + CLS from PerformanceObserver on load, INP from scripted interactions (one form field,
   then the primary CTA; writes blocked, navigation cancelled): LCP ≤2500 ms, CLS ≤0.1, INP ≤200 ms, over
   budget = finding `E7`. Unthrottled local lab numbers — a floor, not field data. Lighthouse CI (3 runs; mobile
   preset marketing, desktop admin): a11y 1.0; perf ≥0.9 marketing / ≥0.8 admin; best-practices ≥0.9; TBT ≤200.
8. Layout-shift observer 5s idle (no recent input) <0.1; console: zero errors, zero failed requests.
9. Content stress: 50-char unbroken strings, 0 / 1 / 1000 rows, +30 % longer labels, `dir=rtl`
   if i18n, 200 % zoom — re-run 3–4.
10. Manual: keyboard-only through the core flow (sort, filter, select, bulk, open row, submit
    invalid form → focus lands on first error) + a screen-reader smoke of that flow (VoiceOver
    or NVDA: route announced, table headers read, toast announced); if the project has a mockup,
    side-by-side compare at 1440 and 390 for 1:1 fidelity.
11. Text smells via `page.evaluate` on visible text: `undefined`, `NaN`, `null`, `[object Object]`,
    `{{`, `lorem`, `TODO`, raw i18n keys (`^[a-z]+(\.[a-z_]+)+$`), `document.fonts.status !==
    'loaded'`, body `font-family` resolving to Times/serif when a webfont is expected, `img` with
    `naturalWidth === 0`, visible elements with `rect.width === 0`. Any hit = fail.
12. Every screenshot goes through the §F visual inspection — the automated checks do not see
    "the layout broke". Done = screenshots taken, §F verdicts written, assertions green, axe
    clean, LHCI green, manual pass logged and reported with evidence (paths, numbers).
    Otherwise fix and re-run from 2.
13. Visual regression: `--baseline <dir>` on `ui-qa.mjs` diffs each PNG against the same-named
    baseline PNG (pixelmatch; `--diff-threshold` = max FRACTION of changed pixels = Playwright
    `maxDiffPixelRatio`, default 0.005, allowed 0.001–0.01 — the former 0.1 meant 10 % of the screen and
    hid every real regression); over threshold fails with a `<name>.diff.png`. Dynamic regions (clock,
    avatars, charts, ads) are masked with `--mask <css,css>` or the attribute `data-qa-mask`; animations
    are disabled in every capture. `--update-baseline <dir>` refreshes the baseline after an intended
    change. Convention: `artifacts/ui-qa/baseline/<slug>/`. Playwright specs: `toHaveScreenshot({
    maxDiffPixelRatio: 0.005, animations: 'disabled', mask: [...] })`, never a ratio above 0.01.
14. Conversion pass (selling surfaces), at 360 / 390 / 768 / 1440: primary CTA present in the first
    viewport · exactly one primary-weight button per viewport · every CTA resolves to a real route ·
    the lead form completes end-to-end against a stub API with pristine / invalid / loading / success
    / failure each screenshotted and §F-inspected · zero placeholder strings in the render · every §G7
    event observed during the walkthrough.

15. **One measurement method for first screens** (so candidates are comparable — every agent used to count
    differently). Per viewport, at rest (after motion ends): `copy` = visible text leaves OUTSIDE any element
    marked `data-figure` (threshold ≤10 in the first viewport); `figure_labels` = text leaves INSIDE `data-figure`
    elements (reported, own cap ≤24); `dead_ground` = share of the viewport covered by neither copy boxes nor
    `data-figure`/`img`/`picture`/`video`/`canvas` boxes, 4×4 px grid (≤35 %); `ratio` = computed H1 font-size ÷
    body font-size (≥4 first screen); `filled_ctas` = buttons/links with background alpha ≥0.5 different from the
    page (=1); `small_sizes` = distinct copy font-sizes <20px (≤2); `families` = font families actually fetched
    over the network. Tool: `node ~/.claude/tools/first-screen-measure.mjs --url <u> --out <dir>`. Mark the
    hero object with `data-figure` in the markup — that is the declaration.

16. **Layout detectors (deterministic, run BEFORE the judge).** `ui-qa.mjs` computes `defects[]` per route ×
    viewport (default on, `--no-detect` skips) → `report.json` `defects[]` = `{type, selector, rect:{x,y,w,h}
    (document px), severity, crop, route, viewport}` and `crops/<type>-<n>.png` (native device scale, 16 px
    margin). VLM judges flag 18–62 % of clean screenshots and find 47–72 % of text-layout faults (arXiv
    2611.10234): a detector hit is a fact, the judge only classifies the crop and checks what the detectors
    cannot see. Reported ≤10 per type per viewport (`report.defectCounts` keeps the totals; ≤10 crops per type). Any defect = finding with its severity (−5 clipped-text, overlap, foreign-overlay; −3
    edge-bleed, action-far-from-label, small-target) and fails the run.
    - `clipped-text`: text rect cut by the element's own `overflow:hidden|clip` box or an overflow-clipping
      ancestor, without intended `text-overflow: ellipsis` / `-webkit-line-clamp` on it or the clipper.
    - `edge-bleed`: non-text box partly outside the viewport or past the padding box of an `overflow:hidden|clip`
      ancestor; `overflow:auto|scroll` containers (scrolling tables) are exempt.
    - `overlap`: two text-bearing or interactive boxes intersect (per text line / control rect: >2 px both axes, ≥25 % of the smaller rect; leaf elements only, a control owns its text);
      ancestor/descendant pairs, anything not rendered (closed `<details>`, `checkVisibility()` false), open dialog/menu/listbox/tooltip content and `sticky`/`fixed` chrome are skipped.
    - `foreign-overlay`: `elementFromPoint` at 3 points of an interactive/text box returns a `fixed`/`absolute`
      layer that does not contain it and is not an open dialog/menu/tooltip (cookie bars, promos, click-catchers).
    - `action-far-from-label`: a `button`/`[role=button]`/submit input inside a `form`, `fieldset`, `[role=group|row|search]`, `tr` or `li`
      is compared with what it acts on — `aria-labelledby`/`aria-describedby` targets first, else the nearest
      preceding sibling (walking up ≤4 levels inside the container) that has visible text or is a field. Same
      row (≥50 % vertical overlap): horizontal gap >160 px; otherwise vertical gap >48 px. Hero CTAs outside
      such containers are not judged.
    - `small-target`: interactive box <24×24 CSS px, except inline links inside a sentence and targets that meet
      the WCAG 2.5.8 spacing exemption (a 24 px circle on the box centre touches no other target nor the circle
      of another undersized target).
    Fixtures and regression test: `node ~/.claude/tools/test-uiqa.mjs` (`tools/fixtures/ui-qa/<type>-bad|good.html`
    + ellipsis-table and sticky-header negatives). Pass `defects[]` and the crops to the judge; do not re-derive them by eye.
17. **Token conformance (`style-audit.mjs`).** `node ~/.claude/tools/style-audit.mjs --url <u> --tokens
    <tokens.css|tokens.dtcg.json> --out artifacts/ui-qa/style-audit` collects computed font-size, line-height,
    margin/padding/gap, border-radius and colours of visible elements and reports off-scale values with counts
    and top selectors (`style-audit.json` + `.md`). Off-scale = design finding (token drift), not a render
    failure; `--max-off-scale N` makes it a gate. Ignores 0, auto, %, ≥999 px radius.
18. **impeccable on the rendered page.** The CLI supports URLs (`npx impeccable detect --json --viewport WxH
    <url>`, verified 2026-11-25; exit 2 = findings). `ui-qa.mjs --impeccable artifacts/ui-qa/impeccable-baseline.json`
    runs it once per route at the first viewport and fails only on findings missing from that committed baseline
    (key = antipattern|path|selector|snippet); `--update-impeccable` adds the current findings to the baseline
    after the owner accepted them. Source-level `npx impeccable detect <dir>` stays in `npm run gate`.
19. **Every control does something (`dead-clicks.mjs`).** Screenshots and the judge never press a button (2026-11-26:
    a dashboard passed ui-qa + judge 9/10 + 60 author-written e2e with half its buttons dead). On the stand of the
    task (own test DB — clicks write), for every changed route: `node ~/.claude/tools/dead-clicks.mjs --url <u> [--url …]
    --viewport 1440x900 --viewport 390x844 --storage-state <auth.json> --project <repo> [--setup <mode.mjs>]
    [--allow <allow.json>] --out artifacts/ui-qa/<slug>/dead-clicks`. One `--setup` module per mode/tab the route has
    (PRO/basic switch, report tab, open drawer) so controls behind it are reached. Verdicts: NAVIGATED | REQUEST | OVERLAY |
    STATE_CHANGED | DOM_CHANGED = live; NO_EFFECT | ERROR (console/page error, 4xx/5xx caused by the click) = blocker.
    Allowlist only inert-by-design controls, each with a reason (`[{"text":"^Логотип$","reason":"decorative"}]`); a
    control disabled by data must render `disabled` + say why (§A), never look enabled. Destructive texts are SKIPPED —
    their effect is covered by the spec's e2e. Self-test: `node ~/.claude/tools/fixtures/dead-clicks/test-dead-clicks.mjs`.
    DOM_CHANGED only proves something moved: for every row of the spec's `## Controls` table an e2e asserts the
    expected effect (route, request payload, visible result), not just "no error".
20. **Geometry oracle (`ui-geometry.mjs`).** The judge agrees with humans ~60 % pairwise (research 2026-11-26), so
    mechanical geometry gates and the judge only advises. For every changed route:
    `node ~/.claude/tools/ui-geometry.mjs --url <u> [--url …] [--urls-file f] [--storage-state <auth.json>] --project <repo>
    [--widths 390,768,1440,2560] [--allow "<css>, <css>"] --stress --out artifacts/ui-qa/<slug>/geometry` → `report.json` +
    `<url>-<width>[-stress].png` with offenders outlined (red error, orange warning). Errors (exit 1, blocker): `overlap`
    of interactive elements (non-ancestor, >1 px, per fixed/sticky layer), `page-overflow` (horizontal scroll),
    `clipped-text` (overflow hidden/clip, no ellipsis/line-clamp), `outside-viewport` (interactive, horizontally, not in a
    scroller). Warnings: `edge-misalign` (sibling edges 1–3 px apart), `gap-off-scale` (4–64 px gap not a multiple of 4),
    `unequal-heights` (same-type siblings in a row, >4 px), `first-screen` (1440 only: submit/H1 below the fold; mark the
    hero with `[data-primary]`). `--stress` re-runs everything after pseudo-localisation (text ×1.4 + accents + a 40-char
    unbroken word per text node): errors there are real layout bugs (add `overflow-wrap:anywhere`/`min-width:0`/wrapping).
    Intentional exceptions: `[data-geometry-ignore]` on the element or `--allow`; each needs a reason in the scorecard.
    Text-box overlap/clipping detectors and small targets stay in §E.16 / ui-qa; this adds the interactive + stress rules.
    `Geometry: n/a — <reason>` is allowed only when no rendered UI changed (guard-bash: PASS needs a fresh
    `geometry/report.json` with `summary.errors == 0`, or that line; no date grace). Self-test: `node ~/.claude/tools/test-ui-geometry.mjs`.

## F. Visual inspection — look at every screenshot like a human reviewer
Automated checks miss most visible breakage. Assume each screenshot is broken until every
question below has an explicit answer. Never write "looks good" without the list of checks.
Image budget: capture viewport-only or element crops ≤1280 px wide unless a full-page shot is the evidence; never
Read more screenshots than the verdict needs — but every screenshot that is taken is looked at (below).
1. **View at native scale.** `Read` the PNG itself; a full-page capture is inspected in
   viewport-height crops (top → bottom), never as one downscaled tall image. Zoom (2× crop)
   into any region that raises doubt. Compare side by side with the mockup/wireframe/previous
   version when one exists.
2. **Whole-frame pass (3 seconds):** what draws the eye first, and is that intended? Is there
   one composition or a pile of parts? Any region that is visibly emptier or denser than the
   rest for no reason? Anything obviously not styled (browser default serif, blue underlined
   links, default buttons, visible list bullets) — means CSS did not load or a class is missing.
3. **Region pass in reading order** (header → hero/title → each section or table → footer);
   for each region answer:
   - Alignment: do left/right edges line up on the grid? Are icons vertically centred with
     their text? Do rows share a baseline? Anything off by a few px reads as sloppy.
   - Clipping/overlap: text cut off, ellipsis where full content is expected, elements sticking
     out of cards, dropdown/tooltip hidden behind other content, sticky header covering content,
     images cropping faces/product.
   - Spacing: equal gaps between siblings; symmetric padding; no collapsed 0-gap or giant empty
     gap; section rhythm consistent; footer not floating mid-page with blank space below.
   - Text: orphan word on the last line of a heading; a single word per line (0-width
     container); mid-word wraps; unintended line breaks inside buttons/labels/badges; line length
     over ~90 characters; body text smaller than ~13px; text touching container edges.
   - Images/media: stretched or squashed (wrong aspect), upscaled/pixelated, broken-image
     icon, lazy placeholder still visible, empty boxes, giant SVG (icon rendered at 100 % width).
   - Controls: same role → same size/style; labels fit; disabled state distinguishable;
     focus ring visible in the focused capture; toggles/checkboxes aligned with labels.
   - Colour/contrast: text readable on its background and over media; accent used
     consistently; no random default colours; dark-theme capture has no white islands.
   - Layout integrity: grid orphan (one card alone on the last row), cards of unequal height
     where equal is intended, columns squeezed to unreadable widths, sidebar overlapping
     content, elements beyond the right edge, wrong stacking order, duplicated header/nav.
4. **Mobile captures additionally:** nav collapsed into a menu; hero type stepped down; no
   side-by-side columns narrower than ~150px; tables scroll instead of squish; buttons full
   width or properly grouped; nothing relies on hover; no horizontal scrollbar; bottom bar not
   covering the last row; input font ≥16px.
5. **State captures:** skeleton the same shape as the loaded content; empty state has a CTA;
   error visible without scrolling; modal centred with backdrop and no page scroll behind;
   toast in its slot; bulk bar not hiding the row it acts on.
6. **Cross-screenshot consistency:** header/footer identical on every page and width; same
   fonts, radius, shadows, accent everywhere; no page that renders in another font.
7. **Verdict per screenshot, written down:** `OK` or a list of `[region] problem → expected`,
   with the crop/coordinates. Fix everything found, re-capture, re-inspect. A finding that a
   human would spot at a glance (broken grid, overlap, unstyled page) blocks "done" regardless
   of green automated checks.

