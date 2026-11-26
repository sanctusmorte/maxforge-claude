# Web interface guidelines (vendored)

Source: https://github.com/vercel-labs/web-interface-guidelines, `command.md`, commit
`434b7f91364665f2f733b310ec54809bf8f37937` (MIT, see `LICENSE`, `ATTRIBUTION.md`). Rule text is verbatim;
ids and `mechanical:` flags are ours. `mechanical: yes` = checked by `scan.py` (rule ids there are listed in
its `RULES` table); everything else is read by the ui-qa agent on the changed screens. Rules are React/Next-flavoured
in places; map to Vue 3 + Vuetify 3 (`htmlFor` = `for`, `onClick` = `@click`, `autoFocus` = `autofocus`).
Additional scanner-only rules not in the source list: `ZOOM-1` (viewport blocks zoom, from the Anti-patterns list).

## Accessibility

- `A11Y-1` Icon-only buttons need `aria-label` — mechanical: yes
- `A11Y-2` Form controls need `<label>` or `aria-label` — mechanical: yes
- `A11Y-3` Interactive elements need keyboard handlers (`onKeyDown`/`onKeyUp`) — mechanical: no
- `A11Y-4` `<button>` for actions, `<a>`/`<Link>` for navigation (not `<div onClick>`) — mechanical: no
- `A11Y-5` Images need `alt` (or `alt=""` if decorative) — mechanical: yes
- `A11Y-6` Decorative icons need `aria-hidden="true"` — mechanical: no
- `A11Y-7` Async updates (toasts, validation) need `aria-live="polite"` — mechanical: no
- `A11Y-8` Use semantic HTML (`<button>`, `<a>`, `<label>`, `<table>`) before ARIA — mechanical: no
- `A11Y-9` Headings hierarchical `<h1>`–`<h6>`; include skip link for main content — mechanical: no
- `A11Y-10` `scroll-margin-top` on heading anchors — mechanical: no
- `A11Y-11` Meaningful media needs captions, transcripts, or descriptions as applicable — mechanical: no
- `A11Y-12` Media controls need keyboard support; decorative media needs assistive-tech hiding — mechanical: no

## Focus States

- `FOCUS-1` Interactive elements need visible focus: `focus-visible:ring-*` or equivalent — mechanical: no
- `FOCUS-2` Never `outline-none` / `outline: none` without focus replacement — mechanical: yes
- `FOCUS-3` Use `:focus-visible` over `:focus` (avoid focus ring on click) — mechanical: no
- `FOCUS-4` Group focus with `:focus-within` for compound controls — mechanical: no
- `FOCUS-5` Sticky headers/footers/overlays must not cover the focused element — mechanical: no

## Forms

- `FORM-1` Inputs need `autocomplete` and meaningful `name` — mechanical: yes
- `FORM-2` Use correct `type` (`email`, `tel`, `url`, `number`) and `inputmode` — mechanical: no
- `FORM-3` Never block paste (`onPaste` + `preventDefault`) — mechanical: yes
- `FORM-4` Labels clickable (`htmlFor` or wrapping control) — mechanical: no
- `FORM-5` Disable spellcheck on emails, codes, usernames (`spellCheck={false}`) — mechanical: no
- `FORM-6` Checkboxes/radios: label + control share single hit target (no dead zones) — mechanical: no
- `FORM-7` Submit button stays enabled until request starts; spinner during request — mechanical: no
- `FORM-8` Errors inline next to fields; focus first error on submit — mechanical: no
- `FORM-9` Placeholders end with `…` and show example pattern — mechanical: no
- `FORM-10` `autocomplete="off"` on non-auth fields to avoid password manager triggers — mechanical: no
- `FORM-11` Warn before navigation with unsaved changes (`beforeunload` or router guard) — mechanical: no

## Animation

- `ANIM-1` Honor `prefers-reduced-motion` (provide reduced variant or disable) — mechanical: no
- `ANIM-2` Animate `transform`/`opacity` only (compositor-friendly) — mechanical: no
- `ANIM-3` Never `transition: all`—list properties explicitly — mechanical: yes
- `ANIM-4` Set correct `transform-origin` — mechanical: no
- `ANIM-5` SVG: transforms on `<g>` wrapper with `transform-box: fill-box; transform-origin: center` — mechanical: no
- `ANIM-6` Animations interruptible—respond to user input mid-animation — mechanical: no
- `ANIM-7` Autoplay motion >5 seconds alongside other content needs pause, stop, or hide controls — mechanical: no
- `ANIM-8` Muted decorative loops must stop under `prefers-reduced-motion` — mechanical: no

## Typography

- `TYPO-1` `…` not `...` — mechanical: no
- `TYPO-2` Curly quotes `“` `”` not straight `"` — mechanical: no
- `TYPO-3` Non-breaking spaces: `10&nbsp;MB`, `⌘&nbsp;K`, brand names — mechanical: no
- `TYPO-4` Loading states end with `…`: `"Loading…"`, `"Saving…"` — mechanical: no
- `TYPO-5` `font-variant-numeric: tabular-nums` for number columns/comparisons — mechanical: no
- `TYPO-6` Use `text-wrap: balance` or `text-pretty` on headings (prevents widows) — mechanical: no

## Content Handling

- `CONTENT-1` Text containers handle long content: `truncate`, `line-clamp-*`, or `break-words` — mechanical: no
- `CONTENT-2` Flex children need `min-w-0` to allow text truncation — mechanical: no
- `CONTENT-3` Handle empty states—don't render broken UI for empty strings/arrays — mechanical: no
- `CONTENT-4` User-generated content: anticipate short, average, and very long inputs — mechanical: no

## Images

- `IMG-1` `<img>` needs explicit `width` and `height` (prevents CLS) — mechanical: yes
- `IMG-2` Below-fold images: `loading="lazy"` — mechanical: no
- `IMG-3` Above-fold critical images: `priority` or `fetchpriority="high"` — mechanical: no

## Performance

- `PERF-1` Large lists (>50 items): virtualize (`virtua`, `content-visibility: auto`) — mechanical: no
- `PERF-2` No layout reads in render (`getBoundingClientRect`, `offsetHeight`, `offsetWidth`, `scrollTop`) — mechanical: no
- `PERF-3` Batch DOM reads/writes; avoid interleaving — mechanical: no
- `PERF-4` Prefer uncontrolled inputs; controlled inputs must be cheap per keystroke — mechanical: no
- `PERF-5` Add `<link rel="preconnect">` for CDN/asset domains — mechanical: no
- `PERF-6` Critical fonts: `<link rel="preload" as="font">` with `font-display: swap` — mechanical: no
- `PERF-7` Prefer `<video autoplay muted loop playsinline>` over animated GIF; provide a still alternative — mechanical: no
- `PERF-8` Short non-essential loops: Safari H.264 MP4 `<picture>` source, `prefers-reduced-motion` media condition, and still fallback — mechanical: no

## Navigation & State

- `NAV-1` URL reflects state—filters, tabs, pagination, expanded panels in query params — mechanical: no
- `NAV-2` Links use `<a>`/`<Link>` (Cmd/Ctrl+click, middle-click support) — mechanical: no
- `NAV-3` Deep-link all stateful UI (if uses `useState`, consider URL sync via nuqs or similar) — mechanical: no
- `NAV-4` Destructive actions need confirmation modal or undo window—never immediate — mechanical: no

## Touch & Interaction

- `TOUCH-1` `touch-action: manipulation` (prevents double-tap zoom delay) — mechanical: no
- `TOUCH-2` `-webkit-tap-highlight-color` set intentionally — mechanical: no
- `TOUCH-3` `overscroll-behavior: contain` in modals/drawers/sheets — mechanical: no
- `TOUCH-4` Page rubber-band suppression: `overscroll-behavior: none` on `<html>` inside `@media (pointer: fine)`; keep coarse-pointer page defaults for pull-to-refresh. Test hybrid touch devices: `pointer` describes the primary input, and `none` also disables scroll chaining and native swipe navigation — mechanical: no
- `TOUCH-5` During drag: disable text selection, `inert` on dragged elements — mechanical: no
- `TOUCH-6` Drag/swipe/pinch/path gestures need tap/click and keyboard alternatives unless essential — mechanical: no
- `TOUCH-7` `autoFocus` sparingly—desktop only, single primary input; avoid on mobile — mechanical: yes

## Safe Areas & Layout

- `LAYOUT-1` Full-bleed layouts need `env(safe-area-inset-*)` for notches — mechanical: no
- `LAYOUT-2` Avoid unwanted scrollbars: `overflow-x-hidden` on containers, fix content overflow — mechanical: no
- `LAYOUT-3` Flex/grid over JS measurement for layout — mechanical: no

## Dark Mode & Theming

- `THEME-1` `color-scheme: dark` on `<html>` for dark themes (fixes scrollbar, inputs) — mechanical: no
- `THEME-2` `<meta name="theme-color">` matches page background — mechanical: no
- `THEME-3` Native `<select>`: explicit `background-color` and `color` (Windows dark mode) — mechanical: no

## Locale & i18n

- `I18N-1` Dates/times: use `Intl.DateTimeFormat` not hardcoded formats — mechanical: no
- `I18N-2` Numbers/currency: use `Intl.NumberFormat` not hardcoded formats — mechanical: no
- `I18N-3` Detect language via `Accept-Language` / `navigator.languages`, not IP — mechanical: no
- `I18N-4` Brand names, code tokens, identifiers: wrap with `translate="no"` to prevent garbled auto-translation — mechanical: no

## Hydration Safety

- `HYDR-1` Inputs with `value` need `onChange` (or use `defaultValue` for uncontrolled) — mechanical: no
- `HYDR-2` Date/time rendering: guard against hydration mismatch (server vs client) — mechanical: no
- `HYDR-3` `suppressHydrationWarning` only where truly needed — mechanical: no

## Hover & Interactive States

- `HOVER-1` Buttons/links need `hover:` state (visual feedback) — mechanical: no
- `HOVER-2` Interactive states increase contrast: hover/active/focus more prominent than rest — mechanical: no

## Content & Copy

- `COPY-1` Active voice: "Install the CLI" not "The CLI will be installed" — mechanical: no
- `COPY-2` Title Case for headings/buttons (Chicago style) — mechanical: no
- `COPY-3` Numerals for counts: "8 deployments" not "eight" — mechanical: no
- `COPY-4` Specific button labels: "Save API Key" not "Continue" — mechanical: no
- `COPY-5` Error messages include fix/next step, not just problem — mechanical: no
- `COPY-6` Second person; avoid first person — mechanical: no
- `COPY-7` `&` over "and" where space-constrained — mechanical: no
