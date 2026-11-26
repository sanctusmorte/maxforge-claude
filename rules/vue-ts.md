---
paths:
  - "**/*.{vue,ts,tsx,js,jsx,mjs,cjs}"
  - "**/package.json"
  - "**/tsconfig*.json"
  - "**/vite.config.*"
  - "**/eslint.config.*"
---
# Vue 3 / TypeScript / Vite / Tailwind — senior code rules (Sept 2026)

World state: Vue 3.5 (3.6 Vapor is RC — not for prod), TypeScript 7 (native Go `tsc`), Vite 8
(Rolldown), Tailwind 4.3 (CSS-first; needs Safari 16.4+ / Chrome 111+ / Firefox 128+), Inertia 3,
ESLint flat config only. **Version-gate:** use only what the project's `package.json` pins
(check it first; JS-only projects get JSDoc types, Tailwind 3 projects keep their config).
Never bump majors as a side effect of a task. Repos with `.ts` files (example-app: Vue 3.4 + Vuetify 3 + Pinia, mostly `.js` SFCs): JS + JSDoc, gradual `lang="ts"` per new file; the same shape, size and kit rules apply with JSDoc types; the TanStack / Inertia / Tailwind lines
apply only where `package.json` has them.

## 0. Kit-only screens (owner 2026-10-17)
Screens compose the project's kit (example-app: `resources/js/components/ui/`, `shared/ui/`; registry
`docs/project/COMPONENTS.md`) — never raw framework primitives (`<v-btn>`, `<v-card>`, `<v-text-field>`, raw
`<button>`) or raw colours/px outside tokens on a page. A missing kit piece → add it to the kit (DECISIONS.md line),
then use it. `design-lint` + `npm run gate` enforce; a new project builds the kit (tokens + 8–12 base components)
before its first screen (`design-ui-ux.md` §0.0). Caps: SFC ≤400 lines (new code), legacy frozen per file in the
ESLint overrides, boy-scout extraction on touch (`code-quality.md` §2): template region → child component, logic
→ `composables/use<X>.js`, data access → `api/`.

## 1. Components
- `<script setup lang="ts">` only (JS projects: `<script setup>` + JSDoc types). Multi-word
  PascalCase names; `Base*` for design-system atoms, `The*` for singletons; one component per file.
- Props: `defineProps<Props>()` with reactive destructure defaults (3.5) or `withDefaults` on
  3.4; `defineEmits<{ change: [id: number] }>()`; `defineModel<T>()` for v-model; generic
  components via `generic="T"`. ≤5 props before switching to an object/slot API.
- SFC ≤400 lines (`code-quality.md` §1); extract composables/child components past that. No `v-if` + `v-for` on one
  element; always keyed `v-for`; scoped styles or Tailwind only; no inline style objects for theming.
- Accessibility inside components: native elements first, `useId()` for label/aria wiring,
  focus management in dialogs, `aria-live` for async status, keyboard paths tested.
- Performance: route-level `defineAsyncComponent` (+ `hydrateOnVisible` on SSR), `v-memo` for
  large static rows, virtual lists >100 rows (ui-engineering-qa §D), `shallowRef` for big
  immutable payloads.

## 2. State & data
- Server state → TanStack Vue Query (or Pinia Colada) with per-feature keys, `staleTime`,
  invalidation in mutations. Pinia setup stores hold client state only (auth, prefs, filters).
  Never cache server data in Pinia; never duplicate server state into refs.
- URL is state for filters, sort, pagination, active tab, search. Form state via `useForm`
  (Inertia + Precognition) or a typed form composable.
- Composables `useX()` are single-purpose, return refs/computed (not reactive objects), accept
  `MaybeRefOrGetter`, clean up with `onWatcherCleanup`/`effectScope`; check VueUse before writing one.
- API layer is typed and generated where possible: Wayfinder for Inertia routes/forms;
  SPA → types from the backend (`spatie/laravel-typescript-transformer` or `openapi-typescript`)
  + `zod` parsing at the edge. Never hand-write URL strings in components.
- Inertia ≥2: `Deferred` props + `<WhenVisible>` for slow panels, prefetch on hover, `usePoll`
  instead of `setInterval`, `once` props for lookups, encrypted history for tenant data.

## 3. TypeScript
- `strict: true`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`,
  `verbatimModuleSyntax`; `vue-tsc --noEmit` in CI. Zero `any` (`no-explicit-any: error`);
  `unknown` + narrowing at boundaries; string-literal unions over `enum`.
- Explicit types on exported/public APIs, inferred locals. `interface` for extendable object
  shapes, `type` for unions/tuples/mapped types. `Readonly<T>` + spread for immutability.
- Errors: `getErrorMessage(error: unknown)` narrowing helper; never swallow; no `console.log` in
  production code.
- ESLint flat config: `vue/flat/recommended` + `vueTsConfigs.recommendedTypeChecked`,
  `vue/require-explicit-emits`, `vue/no-unused-properties`, `vue/block-order`,
  `eslint-plugin-vuejs-accessibility`; Prettier + `prettier-plugin-tailwindcss`.

## 4. Structure
- Feature-based: `features/<name>/{components,composables,api,stores,types,__tests__}`,
  `shared/ui`, `shared/lib`. Many small files beat few large ones (≤400 lines typical, 800 max).
- Tailwind 4: tokens in `@theme`, custom utilities `@utility`, variants `@custom-variant`,
  `@tailwindcss/vite`, no `tailwind.config.js`; `bg-linear-to-*`, logical `ps-/pe-`; variants via
  `cva`/`tailwind-variants` + `tailwind-merge`. Tailwind 3 projects: keep their config, same
  token discipline via `theme.extend`.
- i18n: `vue-i18n` typed messages, keys mirrored from Laravel lang files; no literal user-facing
  strings in components; dates/numbers via `Intl`.

## 5. Testing & gates
- Vitest + Vue Test Utils for logic-heavy components; Vitest browser mode
  (`vitest-browser-vue`, Vitest ≥4 only) for interaction; Playwright E2E for critical journeys; MSW for API
  mocking; no snapshot tests of large DOM trees.
- Pre-PR gate = `npm run gate`: eslint on changed files (no `--fix`; size/complexity caps, legacy per-file overrides that only
  shrink) → `vitest related` → jscpd threshold, `design-lint`, `npx impeccable detect` on changed dirs, `tokens:check`, `vue-tsc --noEmit` where TS,
  unit tests, `npm run build`. UI changes additionally run `~/.claude/skills/qa-verify/ui-qa-protocol.md` §E and
  the ONE-judge gate (`task-lifecycle.md` UI gate).
- Never run `npm run dev` from an agent unless the project explicitly documents it; build and
  serve the production bundle for QA.
