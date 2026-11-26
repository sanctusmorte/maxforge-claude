---
paths:
  - "**/*.php"
  - "**/composer.json"
  - "**/phpunit*.xml"
  - "**/phpstan*.neon"
  - "**/pint.json"
---
# Laravel / PHP — senior code rules (Sept 2026)

World state (Nov 2026): Laravel 13 current (PHP 8.3–8.5), Larastan 3 / PHPStan 2, Pest 5 exists (many repos pin 4 or
PHPUnit), Pint, Rector 2, Inertia 3, Laravel Boost 2; PHP 8.4+ features only when the project runs ≥8.4. **Version-gate everything:** use only what the project's
`composer.json` pins (check `php`, `laravel/framework`, test runner, static analyser first).
Never upgrade a framework/package as a side effect of a task; propose it as its own PR.

## 1. Architecture (multi-tenant SaaS, modular monolith)
1. Business logic lives in **Actions** — `final readonly class CreateOrderAction { public function
   handle(CreateOrderData $data): Order }` — one public method, constructor-injected deps,
   composable. A `Service` only for stateful collaborators (gateway clients, calculators).
2. Controllers are transport only: FormRequest → Data DTO → Action → `JsonResource` / Inertia.
   ≤10 lines per action method, no queries, no `if` beyond routing decisions. Never
   `->toArray()` a model to the client.
3. Bounded contexts as folders (`app/Domains/<Ctx>/{Actions,Data,Models,Events,Listeners,Jobs,
   Policies,Enums,Exceptions,Queries,Http}` or the project's existing `Services/V2/...` layout —
   follow what the project documents). Cross-context access only via `Contracts/` (interfaces,
   DTOs, events); never import another context's Models/Builders/Actions. Enforce with phpat via
   PHPStan (any runner) or Pest `arch()->expect('App\Domains\A')->not->toUse('App\Domains\B')` where Pest exists.
4. DTOs: `spatie/laravel-data` where installed, else `final readonly class` with promoted
   props. No associative arrays across layer boundaries. Value objects (`Money`, `Sku`,
   `TenantId`) validate invariants in the constructor (property hooks on PHP ≥8.4).
   Money = integer minor units (`_kopecks`/`_cents`), never float.
5. Backed enums with behaviour (`label()`, `transitionsTo()`), cast on models; no string constants.
6. Failures are domain exceptions (`OrderCannotBeCancelled`), never `false`/`null`.
7. `DB::transaction()` around multi-write Actions; events `ShouldDispatchAfterCommit`; jobs and
   listeners idempotent (unique keys, upserts, `ShouldBeUnique`, `WithoutOverlapping` keyed by
   tenant). Every queued job needs a running worker for that tenant — check before dispatching.
8. Tenant isolation, one DB per tenant (default here): scalar tenant id in the job payload (never a model), a job
   middleware asserting/switching the tenant connection before `handle`, cache/lock/`WithoutOverlapping` keys
   prefixed by DB name. Global scope / `#[ScopedBy]` + `Context` only for row-level tenancy. Never rely on the
   controller to filter by tenant. `Route::scopeBindings()` for nested resources.
9. Contracts (owner 2026-10-17): EVERY Service and Action has an interface `<Ctx>/Contracts/<Class>Contract`
   bound in the context's service provider (`$this->app->bind(FooServiceContract::class, FooService::class)`);
   callers, jobs and controllers type-hint the contract, never the class. External systems (marketplaces,
   payments, mail, LLMs) additionally get an adapter behind the contract. Facades are fine in
   controllers/console/tests, not in domain code. phpat checks it (`composer gate`).
10. Polymorphism over type switches: a `match`/`switch` on a marketplace/status/type code that appears in two
    places → one strategy class per variant implementing the contract, resolved through a map in the provider.
    Pipelines (`Pipeline::send()->through([...])`) for ordered optional steps instead of nested conditionals.
11. Don't over-abstract beyond that: no repository over Eloquent, no CQRS buses, no `Infrastructure/Application`
    cosplay. Add any further layer only when it removes real duplication, coupling or risk. Work *with* the
    framework. Boy-scout on legacy files over the caps: `rules/code-quality.md` §2.

## 2. Use the framework, don't hand-roll
- N+1: `Model::shouldBeStrict()` in non-prod (`AppServiceProvider::boot`),
  `Model::automaticallyEagerLoadRelationships()` (≥12.8) or explicit `with()`, `chaperone()`
  on hasMany, `cursor()`/`chunkById()` for exports. Custom Eloquent builders / query objects
  for complex reads; one filter = global scope OR named scope, never both.
- Primitives before custom code: `once()`, `Context`, `defer()`, `Concurrency::run()`, `Sleep`
  (fakeable), `Lottery`, `Number`, `Bus::chain/batch`, `Cache::flexible`, `Http::pool`, `Str`.
- Laravel ≥13: model/job/controller attributes (`#[Fillable] #[ScopedBy] #[UsePolicy] #[Tries]
  #[Backoff] #[Queue] #[Middleware] #[Authorize]`), `Queue::route`, passkeys, `#[UnitTest]`.
  One style per class (attributes XOR properties).
- PHP ≥8.4: property hooks, asymmetric visibility `public private(set)`, `new Foo()->m()`,
  `#[\Deprecated]`, `array_find/any/all`; PHP 8.5: `clone($o, [...])`, `|>` for pure chains,
  `array_first/last`, `#[\NoDiscard]`. PHP ≥8.3: `#[\Override]` on every overridden method.
- Auth: Sanctum (SPA/API), Fortify, Precognition for live validation, Horizon for Redis
  queues, Reverb for broadcasting, Scout for search, Pulse for metrics.

## 3. Conventions
- `declare(strict_types=1)` in every file; native types on every param/return/property
  (`void`, `never`, `static`); no implicit nullable; no `mixed`.
- Untyped arrays are forbidden at boundaries: DTOs/collections or PHPDoc generics
  (`@param array<int, Order>`, `@return Collection<int, Order>`, `HasMany<Post, $this>`,
  `@phpstan-type`).
- `final` by default for Actions/DTOs/VOs/Listeners/Jobs/Services; `readonly` for DTOs/VOs;
  constructor promotion; not final for Models or anything mocked/extended.
- Early returns and guard clauses, happy path last, no `else` after return/throw, always braces,
  interpolation over concatenation. Method ≤20 lines, class ≤200 lines, nesting ≤3.
- Names: jobs are verbs (`SyncMarketplaceStock`), events past tense (`OrderShipped`), Actions
  `XxxAction`, Data `XxxData`, enums singular, kebab-case URLs, camelCase route names, tuple
  route syntax `[Controller::class, 'method']`, migrations `YYYY_MM_DD_HHMMSS_verb_noun`.
- Comments explain *why*, invariants, contracts; never restate code. Docblocks only for
  generics, `@throws`, or what the type system can't express. `env()` only inside `config/`.
- Security specifics beyond the obvious OWASP floor: never `Model::unguard()`; `{!! !!}` needs a
  comment justifying it; rate-limit auth by ip AND lower-cased email; uploads validated by mime +
  size and stored on a non-public disk; `composer audit` in CI; signed URLs for time-limited links.

## 4. Testing
- Feature-first through real HTTP routes with factories + named states; unit tests only for VOs /
  pure calculators. Use the project's runner (Pest 4 where present, PHPUnit otherwise); never
  mix styles in one directory.
- Per-process DB: `php artisan test --parallel` (`db_test_{token}`; add `--recreate-databases`
  after migration changes) on the worktree's own MySQL container (`~/.claude/tools/wt-mysql.sh up <wt>`, CLAUDE.md rule 1);
  never the shared host mysqld / dev DB; never `migrate:fresh` on anything but a test DB.
- Fake everything external: `Queue/Bus/Event/Notification/Mail/Storage/Http::fake()` (scoped
  where possible), `Http::preventStrayRequests()`, `Sleep::fake()`, `Carbon::setTestNow()`.
  Pin the clock before seeding time-dependent data.
- Arch tests (phpat via PHPStan, or Pest `arch()`): strict types, `final` Actions/Data, suffixes, no `dd/dump/ray/env` outside
  config, context boundaries. Mutation on core domains: Pest `--mutate --min=70`, or Infection `--git-diff-lines --min-covered-msi=70` on PHPUnit repos.
- Gate = `composer gate` (cheapest first): `composer validate` → `pint --test` on changed files →
  `phpstan` (Larastan; legacy repos level 5 + baseline ratchet, new repos ≥8; phpat + cognitive-complexity
  inside it) → `composer audit --locked` → quarantine ratchet (baseline counts, jscpd, god-file lines vs
  origin/<base>: fail only on growth) → affected tests (`--filter`, wider on doubt); build where the project has one. `rector --dry-run` where
  adopted. CI runs the same gate; `--parallel` locally only with a per-agent DB. Golden examples per layer:
  the project CLAUDE.md names them — copy their shape before writing a new Action/Service/contract.

## 5. Docs-as-code — Laravel specifics (general rule: `code-pack` §Docs 1:1)
- Changes under `app/ routes/ database/ config/ bootstrap/` → matching `docs/domains/<ctx>.md`
  (or the project's documented location) in the same commit.
- Generated over hand-written: route tables from `route:list --json`, resource shapes from Data
  classes; VitePress `<<< @/../path#region` snippet imports for code examples where available.
  Dead code → its section moves to `docs/domains/_unused-candidates.md` in the same PR.
