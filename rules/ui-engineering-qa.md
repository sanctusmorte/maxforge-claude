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
  - "**/e2e/**"
  - "**/playwright*"
---
# UI engineering, app UX, a11y, perf — core floor (path-scoped; split 2026-09-24, section IDs unchanged)

Companion to `design-ui-ux.md`. Everything here is a hard floor; "UI done" means §E ran green.
On demand, same IDs: §E QA protocol (tiers E.0, E.1–E.18) + §F visual inspection →
`~/.claude/skills/qa-verify/ui-qa-protocol.md` (run by the `ui-qa` agent / `/qa-verify`; E.16 layout detectors → `defects[]` + crops, E.17 `style-audit.mjs`, E.18 impeccable on the rendered URL); §G lead capture +
instrumentation (G1–G10) → `~/.claude/skills/site/lead-capture-events.md`.

## A. Responsive mechanics
1. Shell = viewport-first (`min-width` media queries only for nav / column count). Components =
   container-first (`container-type: inline-size`, `@container`, `cqi`) so they work in
   sidebars, panes and modals alike.
2. Widths that matter: 360 (1 col, 16px gutters) · 390–430 (iPhone) · 600/768 (2 col, nav rail,
   filters in side sheet) · 840/1024 (persistent sidebar, list-detail) · 1280 (admin baseline) ·
   1440 (cap marketing content at 1200–1320px) · 1920 (add panes, never stretch; ≤75ch) · 2560 (the owner's monitor:
   centred max-width, nothing pinned left, no stretched cards — shot on every UI gate).
3. Fluid type/space via `clamp(min-rem, rem + cqi|vw, max-rem)`; never bare `vw` (kills zoom).
4. Pointer targets ≥24×24 CSS px for standalone controls (WCAG 2.5.8; inline text links and
   targets with ≥24px spacing are exempt), ≥44pt/48dp for primary touch controls; grow the hit
   area with padding/`::before`, not the visual size; 8px between targets.
5. Hover-only affordances are forbidden: gate hover under `@media (hover:hover) and
   (pointer:fine)`; on coarse pointers row actions are always visible or in an explicit menu;
   every hover reveal must also appear on `:focus-visible`.
6. Full-height: `100svh` for guaranteed fit, `100dvh` only for resize-tolerant elements (sheets,
   chat input), never `100vh` on mobile. `viewport-fit=cover` + `max(16px, env(safe-area-inset-*))`
   on fixed bars. Sticky chrome ≤64px on mobile, top+bottom ≤30 % of viewport;
   `html { scroll-padding-top: var(--header-h) }` so anchors/focus are never hidden.
7. Overflow: fix causes, never mask — `min-width: 0` on flex/grid children, `minmax(0,1fr)`,
   `overflow-wrap: anywhere` on user strings, `max-width:100%; height:auto` on media, never
   `width:100vw`, `scrollbar-gutter: stable`. `overflow-x: clip` on body only as last resort.
8. Images: `width`+`height` attrs (or `aspect-ratio`) always; `srcset`+`sizes` matching the slot;
   `loading="lazy"` only below the fold; LCP image `fetchpriority="high"` + preload, never lazy;
   `<picture>` AVIF → WebP → JPEG.
9. Tables on mobile — choose by task: comparison → horizontal scroll region (`role="region"`,
   `aria-labelledby`, `tabindex="0"`, sticky first column + header, scroll shadow); independent
   records → card stack (`thead` visually-hidden, not `display:none`; `data-label` per cell); many
   columns → column priority (hide low-priority <1024 + "Columns" toggle). Re-add
   `role="table|row|cell"` whenever `display` changes.
10. Mobile forms: computed input font-size ≥16px (iOS zoom), never `maximum-scale=1` /
    `user-scalable=no`, per-field `type`/`inputmode`/`autocomplete`/`autocapitalize`, one column,
    labels above, never split one entity (phone) into several inputs.
11. Overlays: native `<dialog>.showModal()` (top layer, inert background, Esc, focus trap);
    light dismiss via `closedby="any"` PLUS a click-outside fallback (Safari has no `closedby`);
    Popover API for menus/tooltips; anchor positioning with fallback. <768px modals become bottom sheets / full screen; desktop details & filters live in
    non-modal side drawers; sheets have a visible Close and never stack.
12. Navigation: <600 bottom bar (3–5) or drawer · 600–840 rail · ≥840 sidebar collapsible to a
    64–72px icon rail with persisted state. Page title + breadcrumb visible at every width.
13. Z-index: `isolation: isolate` per component root; ≤5 named layers (`--z-dropdown / sticky /
    modal / toast / tooltip`); prefer top-layer primitives over manual z-index.

## B. App UX (SaaS / CRM)
1. Density: compact rows 32–40px with a Compact/Comfortable toggle; table text ≥13px,
   `tabular-nums`, numbers right-aligned, text left, consistent units/decimals per column.
2. Tables serve four tasks (NN/g): find (visible filters with active state, human-readable id in
   column 1), compare (frozen header + first column, hover highlight, hide/reorder columns),
   view/edit one row (non-modal side panel > modal; inline edit for narrow tables), act (row
   overflow menu, checkbox bulk). Explicit default sort + indicator; stable column widths
   across loading and pagination (no reflow skeleton → data).
3. Empty states ×3: first-use (what / why / primary CTA / sample data), no-results (name the
   filters, one-click "Clear filters"), error (retry). Never a blank pane.
4. Loading: <1s nothing; 1–10s skeleton shaped like the final layout (spinner only for one module
   or a blocking submit); >10s progress + estimate. Optimistic UI for reversible low-risk actions
   (toggle, star, reorder) with rollback + toast on failure.
5. Validation on blur (never on keystroke before first blur); a shown error clears on keystroke the
   moment the value becomes valid, never at the next blur (Baymard); on submit focus the first
   invalid field + summary linking to fields; messages say how to fix.
6. Destructive: undo beats confirm — toast with Undo (5–10s) + Ctrl+Z for reversible; dialog
   only for irreversible / high-cost, naming object and count ("Delete 12 contacts" / "Keep"), no
   dangerous default, type-to-confirm for catastrophic; separate destructive buttons spatially.
7. Keyboard: everything reachable by Tab; APG grid pattern only when cells are interactive;
   `/` search, `?` shortcuts, Esc closes; no `tabindex > 0`.
8. Toasts: `role="status"`, bottom corner (above bottom nav on mobile), 5–6s success, errors
   persist, pause on hover, ≤3 stacked, never the only place a required action lives.
   Form-blocking errors go inline, not in toasts.
9. Progressive disclosure: ≤7 primary options, "Advanced" behind a toggle, ≤2 levels, wizards
   show step count, required fields are never hidden.
10. Filters: batch "Apply" on mobile/slow queries, live on desktop/fast; applied filters as
    removable chips + "Clear all"; state in URL (shareable, back button works); show result count.
11. Bulk: bar appears on first selection ("N selected"), "Select page" vs "Select all N", sticky
    bar ≤5 actions + overflow, non-applicable actions disabled with a reason.
12. Dirty state: warn on navigation with unsaved changes, visible "Saved" status, autosave drafts
    of long forms, prefill previously entered data in the same flow (WCAG 3.3.7).

## C. Accessibility floor — WCAG 2.2 AA
1. Contrast: text 4.5:1 (3:1 for ≥24px / ≥18.66px bold); UI borders, icons, focus rings, chart
   marks 3:1; placeholders 4.5:1; check both themes. APCA is advisory only (not normative 2026).
2. Focus: never `outline: none` without replacement; `:focus-visible` ring ≥2px, 3:1 vs adjacent,
   offset; focused element never under sticky bars (2.4.11).
3. WCAG 2.2 duties: every drag has a click/keyboard path (2.5.7); help sits in the same place on
   every page (3.2.6); no cognitive CAPTCHA, allow paste, `autocomplete="current-password" /
   "one-time-code"` (3.3.8); don't ask twice (3.3.7).
4. Semantic HTML before ARIA: `button`, `a[href]`, `nav/main`, `table`, `dialog`, `details`,
   native `select`/date unless UX truly demands custom; exactly one `h1`; no `div onclick`.
5. Icon-only controls get `aria-label`; `.sr-only` for captions / "opens in new tab"; live regions
   exist at load and receive text on async results; `role="alert"` for errors only.
6. Overlays: initial focus on first field/heading, focus returns to the opener, background
   `inert`. SPA route change: focus the new `h1[tabindex=-1]`, update `document.title`, announce
   politely; after delete focus the next row/heading, never `body`.
7. Forms: visible `<label for>` (placeholder ≠ label), `fieldset/legend` for groups, required in
   text, `aria-describedby` + `aria-invalid` on errors, `autocomplete` tokens, `:user-invalid`.
8. Media queries honoured: `prefers-reduced-motion`, `prefers-contrast: more` (thicker borders),
   `forced-colors: active` (borders replace shadows, system colours).
9. Works at 320 CSS px without 2D scrolling (except tables/maps), survives text-spacing
   overrides and 200 % zoom; keyboard-only completes every flow.

## D. Performance as UX (p75 targets)
- LCP ≤2.5s, INP ≤200ms, CLS ≤0.1. Marketing initial JS ≈150–200 KB gz / CSS ≤30 KB;
  admin routes split per screen (≤300 KB / 50 KB).
- LCP: SSR above-fold, critical CSS inline, `preconnect` font/CDN, no render-blocking JS.
- INP: tasks <50ms; `await scheduler.yield()` (fallback `setTimeout(0)`); paint the response
  first, then heavy work; batch DOM reads/writes; debounce inputs; skeleton on click for soft
  navigations; never re-render a whole table for one cell.
- Virtualise lists >~100 rows; `content-visibility: auto` + `contain-intrinsic-size` for
  off-screen sections; code-split routes, prefetch on hover/viewport.
- CLS: reserve space (`min-height`/`aspect-ratio`), never insert above the viewport, skeleton
  same size as content, animate only transform/opacity.
- Fonts: WOFF2, ≤2 families / ≤4 files, `font-display: swap` + metric-matched fallback
  (`size-adjust`, `ascent/descent/line-gap-override`), `unicode-range` subsets, preload one
  above-fold face. Third parties after idle; iframes lazy.

