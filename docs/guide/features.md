---
title: "Features - Claude Code skills, subagents, rules and tools"
description: "What is inside the maxforge-claude Claude Code plugin - skills, subagents with pinned models, rules, templates, tools and the optional add-ons it recommends but does not ship."
---

# Features: skills, subagents, rules and tools

## Skills (`skills/*/SKILL.md`)

| Skill | Use |
|---|---|
| `task` | orchestrate a quick or full task: triage, split, waves, one PR |
| `spec` | intake, assumptions ledger, spec and plan |
| `project-new` | start a new project: positioning, ADRs, bootstrap |
| `qa-verify` | evidence-based verification of a bug fix or feature |
| `ui-task` | add or change an app screen with design system and QA gates |
| `site` | selling pages through an 8-stage signed pipeline |
| `handoff` | write the per-task `progress.md` |
| `project-sync` | regenerate `docs/project/STATE.md` from git and GitHub |
| `lesson` | record a correction with a check |
| `grilling` | stress-test a plan by questioning |
| `laravel-best-practices` | Laravel best practices (third party, MIT) |
| `worker-core`, `code-pack`, `design-pack`, `research-pack`, `review-pack` | preloaded into workers, not for the main session |

## Subagents (`agents/*.md`)

Model and effort are pinned in each file's frontmatter.

| Agent | Role | Model, effort |
|---|---|---|
| `verifier` | tries to refute that a finished task works | opus, high |
| `code-reviewer` | one independent review of the integrated diff | opus, high |
| `security-reviewer` | diffs touching auth, uploads, billing, webhooks, secrets | opus, high |
| `design-judge` | the single UI judge | opus, high |
| `ui-builder` | builds new or value screens | opus, medium |
| `ui-qa` | runs the UI QA tool on a served build and a static web-interface guidelines scan (Vercel rules, MIT) with a blocking list | sonnet, medium |
| `researcher` | read-only codebase and web research | sonnet, medium |
| `lite-worker` | mechanical edits, renames, docs | sonnet, medium |
| `design-critic`, `product-reviewer`, `marketing-reviewer`, `slop-detector` | design-panel reviewers | sonnet, medium |

## Rules (`rules/*.md`)

Always on: `code-quality`, `task-lifecycle`, `project-state`. Path-scoped and enforced by the rules gate: `design-ui-ux`, `ui-engineering-qa`, `laravel-php`, `vue-ts`, `python`, `llm-features`.

## Templates and tools

`templates/project/` holds per-repository files (`PROJECT.md`, `STATE.md`, `DESIGN.md`, spec, verification report, design scorecard). `tools/` holds worktree bootstrap (`wt-new.sh`), test selection (`affected-tests`, `q`), file outline (`outline`), the UI runners, and usage reports (`usage-report.py`, `token-audit.py`).

## Plugin-only extras

- `extras/output-styles/dense-en.md`: short answers, verdict first.
- `extras/rules/core.md`: generic core process rules, 80 lines or fewer.

## Recommended add-ons (not shipped)

The author also uses skills written by other people. They are not part of this plugin; install them from their authors and check each licence yourself.

| Skills | Upstream |
|---|---|
| marketing skills (copywriting, cro, content-strategy, customer-research, product-marketing, marketing-psychology, competitor-profiling) | github.com/coreyhaines31/marketingskills |
| context engineering (context-compression, context-fundamentals, context-optimization, harness-engineering, multi-agent-patterns) | github.com/muratcankoylan/Agent-Skills-for-Context-Engineering |
| taste-skill, redesign-skill | github.com/leonxlnx/taste-skill |
| stop-slop | github.com/hardikpandya/stop-slop |
| council-review | github.com/ngmeyer/council-review |
| emil-design-eng | github.com/emilkowalski/skill |

The plugin works without them; the design and marketing skills simply have fewer references to draw on.
