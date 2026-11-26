---
paths:
  - "**/Ai/**"
  - "**/ai/**"
  - "**/AI/**"
  - "**/Llm/**"
  - "**/llm/**"
  - "**/prompts/**"
  - "**/*Agent*.php"
  - "**/*Assistant*.{php,ts,vue}"
---
# LLM-powered features — engineering rules (Sept 2026)

Applies to AI agents, assistants, generators and moderation pipelines inside products. Model ids and pricing: load the `claude-api` skill before choosing.

1. **Prompts are code.** Live in the repo (`resources/prompts/*.md` or `app/Ai/Prompts/`), versioned,
   reviewed in PRs, referenced by name + version in logs. No prompt strings inline in controllers.
2. **Driver abstraction.** One interface (`AiDriver`/`LlmClient`) with `api` + `fake` implementations;
   tests use the fake with scripted responses; a `subscription`/dev-only driver never ships to prod.
3. **Structured outputs.** Ask for JSON with a schema; validate with a DTO (spatie/laravel-data, zod);
   reject and retry once on schema failure; never trust free text for state changes.
4. **Budget guards.** Per-run and per-tenant limits (tokens, cost, wall time, tool calls); record usage
   per run (`ai_runs` table: model, prompt version, tokens in/out, cost, latency, outcome); alert on
   anomalies. Cache deterministic calls (embeddings, classifications) by content hash.
5. **Tool use = least privilege.** Tools declare scope; the run carries the tenant/user; every tool call is
   authorised like an HTTP request and logged; destructive actions require a moderation/approval gate.
6. **Moderation & safety.** Input and output pass moderation where user-generated content is involved;
   publish flows need an explicit human-approved state; keep an audit trail (who/what/when/prompt).
7. **Evals before ship.** A small versioned eval set (≥20 cases per feature) with expected outputs or
   rubric; run on prompt/model changes; store scores next to the prompt version; regression = block.
8. **Idempotent runs.** Every run has an id and a status machine (queued → running → done/failed/
   cancelled); retries are safe; concurrency guarded per resource (`WithoutOverlapping`).
9. **Observability.** Log prompt version, model, latency, tokens, tool calls, moderation verdicts with a
   correlation id; redact PII/secrets from logs; expose counters (Pulse/metrics).
10. **Fallbacks.** Model unavailable/timeout → degrade gracefully (cached/previous result, clear UI state),
    never hang a request; user-facing errors say what to do next.
11. **Docs.** Each AI feature has a doc page: purpose, prompt versions, tools + scopes, budgets, eval set
    location, failure modes — updated in the same PR.
