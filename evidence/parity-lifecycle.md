# Parity check, lifecycle angle: "full kit for big tasks / a huge project" (2026-11-26)

Complements `parity.md` (hooks, verifiers, worktrees, compaction, lessons, UI QA), which is not repeated here.
Method: `gh api repos/<r>` for stars and last push; shallow clones (HEAD 2026-11-26) of 7 repos, read by targeted grep plus
skill/command files. For gsd-core the clone failed, so I used `gh api` on branch `next` (README, hooks/, docs/features/).
Tokens: maxforge costs about 1.49x tokens at equal quality (owner A/B 2026-10-13). Nothing below claims a saving.

## 1. Alternatives (stars and last push on 2026-11-26)
| Project | Stars | Last push | Studied via |
|---|---|---|---|
| [obra/superpowers](https://github.com/obra/superpowers) | 327,151 | 2026-11-26 | clone |
| [affaan-m/ECC](https://github.com/affaan-m/ECC) (was everything-claude-code) | 311,078 | 2026-11-23 | clone |
| [github/spec-kit](https://github.com/github/spec-kit) | 151,463 | 2026-11-25 | clone |
| [ruvnet/ruflo](https://github.com/ruvnet/ruflo) (was claude-flow) | 82,463 | 2026-11-26 | clone |
| [bmad-code-org/BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD) (v7 alpha on main; v6.12 stable is on another branch) | 55,779 | 2026-11-26 | clone |
| [Yeachan-Heo/oh-my-claudecode](https://github.com/Yeachan-Heo/oh-my-claudecode) | 41,080 | 2026-11-26 | README |
| [SuperClaude_Framework](https://github.com/SuperClaude-Org/SuperClaude_Framework) | 23,949 | 2026-09-27 | clone |
| [open-gsd/gsd-core](https://github.com/open-gsd/gsd-core) | 11,861 | 2026-11-26 | `gh api`, branch `next` |
| [Chachamaru127/claude-code-harness](https://github.com/Chachamaru127/claude-code-harness) | 3,225 | 2026-11-16 | clone |
| [rohitg00/pro-workflow](https://github.com/rohitg00/pro-workflow) | 2,972 | 2026-09-29 | README only |
| [the-open-engine/zeroshot](https://github.com/the-open-engine/zeroshot) | 2,230 | 2026-11-26 | README only |
Found by `gh search repos` but not studied: Maestro, openrig, Continuous-Claude-v3 (see `parity.md`). Stale, not CC-specific or not a lifecycle kit: gsd-build/get-shit-done (archived), Pimzino/claude-code-spec-workflow (last push 2025-09), gemini-cli-extensions/conductor (Gemini CLI).

## 2. What maxforge ships (checkout HEAD 0b59903, 2026-11-26) and how it is enforced
| Piece | Where | Enforcement |
|---|---|---|
| New project: intake, ADRs with plan review, bootstrap, milestones to tasks | `skills/project-new/SKILL.md` steps 1-5 | skill text only |
| STATE/DECISIONS/MILESTONES, SessionStart digest, budgets STATE <=60 lines | `hooks/project-sync.py` (`--check --strict`), `skills/project-sync` | digest = context injection; `--check` is called by the skill, warning-only unless `--strict` |
| Triage direct/quick/full, waves, split by file ownership, one PR | `skills/task/SKILL.md` steps 1, 4-9; `skills/spec/SKILL.md` | skill text only |
| Ownership clash check | `tools/ownership-check.py` (exit 1 when a file is owned twice) | a tool the skill calls; no hook references it (`grep hooks/*.py`: 0) |
| Worktree + branch + env + deps + test DB per task/agent | `tools/wt-new.sh`, `tools/wt-mysql.sh` | script; falls back to the SHARED host mysql if `wt-mysql` fails (`wt-new.sh:81`); no hook forces an agent into a worktree |
| Up to 10 parallel agents | `rules/task-lifecycle.md:16`, CLAUDE.md rule 5 | text only (no cap hook found). `skills/project-new/SKILL.md:41` says <=5, `task` says 10: inconsistent |
| Budget in spec header | `skills/spec/SKILL.md` 0; `hooks/ctx-monitor.py:306` | advisory: emits `additionalContext` per 10% band, no deny |
| Context fence + `FENCE-HANDOFF` per agent type | `hooks/token-guard.py::check_fence`, `FENCE_BY_TYPE` (:53) | DENY |
| Unverified REQ at stop | `hooks/stop-guard.py::req_reason` (:233) | block ONCE per session (marker file), then allowed: a nudge |
| Dirty/unpushed worktree at stop | `hooks/stop-guard.py` (docstring :1-16) | block once per worktree per 24 h |
| Push to master/main/dev, PR into master while dev exists, non-draft UI PR without scorecard | `hooks/guard-bash.py` (:5-13, :418-426) | DENY |
| Stack rule read before edit | `hooks/rules-gate.py` | DENY |
| `progress.md` per task, handoff, restore | `hooks/precompact-handoff.py` (writes <=60-line `progress.md`, checkpoint commit), `hooks/session-restore.py` | hook-written, not denying |
| One `code-reviewer` + `security-reviewer` on trigger + `verifier` | `agents/{code-reviewer,security-reviewer,verifier}.md` (read-only: `disallowedTools: Edit, Write`); order in `/task` step 8 | agents are read-only by config; invocation order is skill text |

## 3. Capability matrix (Y = shipped, P = partial/prompt-only, N = not found, ? = not verified; all 2026-11-26)
| # | Capability | maxforge | gsd-core | claude-code-harness | ECC | superpowers | BMAD v7 | spec-kit | ruflo | SuperClaude |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Project layer (bootstrap, milestones, state file) | Y | Y | P | P | N | P | P | P | ? |
| 2 | Triage by size | Y | Y | Y | P | N | Y | N | ? | ? |
| 3 | Spec/plan before code | Y | Y | Y | Y | Y | Y | Y | Y | ? |
| 4a | Per-agent worktree | Y (script, not forced) | Y (hook-forced) | Y (`isolation: worktree`) | P | P | N | N (community ext.) | Y | N |
| 4b | Per-agent branch | Y | Y | Y | P | P | N | P | ? | N |
| 4c | Per-agent test DB | Y (shared-DB fallback) | ? | N (grep) | ? | ? | N | N | ? | N |
| 4d | Split by file ownership | Y (+script) | P (`files_modified`) | P (prose) | P (prose) | N | N | P (`[P]`) | ? | N |
| 4e | Concurrency cap | P (text, 10) | ? | P (`--parallel N`; CC cap 20) | ? | N | N | N | ? | N |
| 5 | Integration branch + one PR | Y | P | N | P | N | N | N | ? | N |
| 6 | Independent review + verifier | Y | Y | Y | Y | Y | Y | N | P | ? |
| 7 | Continuity | Y | Y | Y | Y | P | P | N | ? | P (Serena MCP) |
| 8 | Token/budget control | P (advisory) | P | ? | P (tracking) | N | N | N | P | N |
| 9 | Hook-ENFORCED (deny) | 4a-ish, context, PR gates | isolation, path, STATE write | guardrails, `stop-evaluator` (not audited) | block-no-verify, gateguard | none | none | none | ? | none |

Evidence (quote, URL):
- gsd-core 1: README "`/gsd-new-project` greenfield", `commands/gsd/new-milestone.md` "Start a new milestone cycle" ([tree](https://github.com/open-gsd/gsd-core/tree/next/commands/gsd)). 2: `docs/features/quick-mode.md` "Ad-hoc task execution with GSD guarantees but a faster path". 4: `commands/gsd/execute-phase.md` "dependency-aware wave parallelization"; `agents/gsd-planner.md` frontmatter `wave: N`, `files_modified: []`. 7: `commands/gsd/pause-work.md` "Create context handoff when pausing work mid-phase". 8: `docs/features/agent-size-budget-enforcement.md` limits agent prompt FILE size in CI, not run tokens. 9: [`hooks/gsd-agent-isolation-guard.js`](https://github.com/open-gsd/gsd-core/blob/next/hooks/gsd-agent-isolation-guard.js) "enforces the invariant at the tooling layer instead: HARD-BLOCKING" (an executor dispatch without `isolation="worktree"` is denied); [`hooks/gsd-worktree-path-guard.js`](https://github.com/open-gsd/gsd-core/blob/next/hooks/gsd-worktree-path-guard.js) "BLOCK (exit 2) if file_path is absolute and outside the worktree root"; [`hooks/gsd-write-guard.js`](https://github.com/open-gsd/gsd-core/blob/next/hooks/gsd-write-guard.js) hard-blocks a Write that shrinks ROADMAP.md/STATE.md; `gsd-workflow-guard.js` is "a SOFT guard". `docs/features/statemd-consistency-gates.md` "Detect and repair drift between STATE.md and the actual filesystem".
- harness: `skills/harness-work/SKILL.md` table "1 件 Solo / 2〜3 件 Parallel / 4 件以上 Breezing"; [`agents/worker.md:18`](https://github.com/Chachamaru127/claude-code-harness/blob/main/agents/worker.md) `isolation: worktree`; `skills/breezing/SKILL.md` Phase D "Integrated Review Gate (default ON)": fresh-context reviewer + codex second opinion, iterate to APPROVE, max 3, "gate 未通過のまま run を「完了」として報告してはならない" (prompt text); `hooks/hooks.json` has 27 event types incl. PreCompact, PostCompact, WorktreeCreate, TaskCompleted, Stop `stop-evaluator`. `--parallel N` "CC は同時実行中の subagent を既定 20 に制限する".
- ECC: skills `blueprint` ("multi-session, multi-agent engineering projects: one-PR-sized steps ... dependency graph with parallel-step detection, adversarial review gate"), `ralphinho-rfc-pipeline` ("merge through a queue with re-based branches"; "Always rebase unit branches on latest integration branch"), `team-agent-orchestration` ("branch isolation ... merge gates"; anti-pattern "Overlapping writes: parallel agents edit the same files without worktrees"), `orch-build-mvp` (thin vertical slices, 2 gates), `epic-*` commands (GitHub issue coordination), `model-route` (complexity/risk/budget), `cost-tracker.js`; hook `gateguard-fact-force.js` denies edits until facts are given. All lifecycle pieces are skills/commands.
- superpowers: `subagent-driven-development` "fresh implementer subagent per task, a task review ... and a broad whole-branch review"; tasks run in sequence; `dispatching-parallel-agents` is for unrelated failures; `hooks/hooks.json` = SessionStart only (matcher includes `compact`).
- BMAD README: "Right-sized process — Go directly to implementation for clear changes or add deeper planning for larger initiatives"; `bmad-code-review` "several independent reviewers in parallel". No hooks dir, no worktree text.
- spec-kit: `templates/tasks-template.md` "[P]: Can run in parallel (different files, no dependencies)"; worktree only via community extensions (`docs/community/extensions.md:231-232`); no review/verifier step.
- ruflo: `plugins/ruflo-swarm/README.md` "Each agent works in its own git worktree to avoid conflicts"; `ruflo-cost-tracker` "hard stop at 100%" (a slash command exit 1, not a verified deny hook); plugins `ruflo-adr`, `ruflo-sparc` ("quality gate that must pass before advancing").
- OMC README: team pipeline "team-plan -> team-prd -> team-exec -> team-verify -> team-fix"; worktrees "being added behind an opt-in/config gate". zeroshot README: "a graph the engine enforces ... independent reviews, end-to-end testing, and CI must pass before merge" (own engine, not Claude hooks).

## 4. Candidate lifecycle differentiators (strikethrough = an alternative ships it)
| # | Candidate | Verdict / evidence |
|---|---|---|
| 1 | ~~Project-level layer: bootstrap, milestones, state file, ledgers~~ | struck: gsd-core `new-project`, `new-milestone`, STATE/ROADMAP with consistency gates; ECC `orch-build-mvp`; ruflo `ruflo-adr` |
| 2 | ~~Triage direct/quick/full~~ | struck: gsd-core `/gsd-quick`; harness solo/parallel/breezing by task count; BMAD "Right-sized process" |
| 3 | ~~Ambiguity-scored spec, plan, waves~~ | struck as a category (spec-kit, gsd-core waves, harness Plans.md, superpowers). The numeric formula `ambiguity = 1 - (0.35G+0.25B+0.20C+0.20A)` was not found elsewhere (no grep) |
| 4 | ~~Worktree/branch per parallel agent~~ | struck: harness `isolation: worktree`, ruflo, gsd-core |
| 5 | ~~Hook-enforced worktree isolation of agents~~ | struck AND a maxforge gap: gsd-core denies it; maxforge only offers `wt-new.sh` |
| 6 | ~~Independent reviewer + verifier before done~~ | struck (parity.md #3; harness Phase D, BMAD, gsd-core verifier) |
| 7 | ~~Continuity across compaction~~ | struck (parity.md #5; harness PreCompact/PostCompact; ECC `pre-compact.js`; gsd-core pause/resume) |
| 8 | ~~Token/cost budget~~ | struck as unique: ECC `cost-tracker.js`, ruflo cost-tracker with a stop ladder; maxforge's own budget is advisory too |
| 9 | ~~Integration branch + merge order + rebase~~ | partly struck: ECC `ralphinho-rfc-pipeline` (prompted). No alternative found with `task/<slug>` + subtask PRs + ONE PR + a PR-base deny |
| 10 | Pre-wave file-ownership script that exits 1 on a shared file (`tools/ownership-check.py`) | survives (narrow): others only state ownership in prose or frontmatter (gsd-core `files_modified`, spec-kit `[P]`, ECC anti-pattern text). maxforge itself does not hook it |
| 11 | Per-agent test DB (`tools/wt-mysql.sh`, `DB_DATABASE=<project>_testing_<task>`) | survives tentatively: harness tree has no hit; the other trees were NOT grepped for it. maxforge itself falls back to a shared DB |
| 12 | Deny-level end-of-lifecycle gates: `gh pr create` denied without machine UI reports; PR into master denied while dev exists; context fence | survives (from parity.md #9-12). harness `stop-evaluator` and Go guardrails not audited |
| 13 | REQ table with `verified` set only by `verifier`, checked at stop | weak: the stop check blocks once per session; gsd-core "Nyquist rule" and harness sprint-contract are similar ideas |

## 5. Surviving differentiators (priority order)
1. Deny-level PR gates tied to UI evidence (dead-click + geometry + scorecard), the end of the task lifecycle (`guard-bash.py`; parity.md #9-10). No alternative checked has it.
2. Whole-task chain in one kit: spec with REQ table, split by ownership with a checkable script, `task/<slug>` integration branch with subtask PRs and one PR, and one reviewer plus a refuting verifier on the integrated diff. Each link exists elsewhere (ECC, harness, gsd-core); the chain with PR-base denies was not found. Claim only "this chain", not "first lifecycle".
3. Context discipline that denies (fence + `FENCE-HANDOFF`, read caps); gsd-core's context monitor and ECC's `context-gate` are advisory.
4. Per-agent test DB, if the unverified greps hold (see NOT verified).
5. Stated cost (about 1.49x tokens) and a README that names a file and test per claim.

Positioning consequence: "a full kit for big tasks and huge projects" is NOT a differentiator by itself. gsd-core (project, milestones, waves, quick mode, hard-blocking worktree hooks) and ECC (blueprint, orch-build-mvp, epic-*) cover the same ground. "Big tasks with proof at the PR gate" holds. Gaps to close or avoid claiming: hook-forced worktree isolation (gsd-core), an enforced agent cap (none; docs say <=5 vs 10), a hard budget stop (advisory only), and a REQ gate that is a one-time nudge.

## NOT verified
- gsd-core was not cloned (clone stalled, 0 files): only README, `docs/features/*`, 4 hook headers, 3 command descriptions were read. Per-agent test DB, cap, integration branch there are unknown.
- harness Go guardrail rules (R01-R13) and the `stop-evaluator` / `TaskCompleted` hook bodies were not read; whether Phase D is hook-enforced is unknown.
- ruflo (8.8k files), ECC (4.9k files), SuperClaude and OMC: read via descriptions and targeted greps; hooks in ECC `hooks.json` and ruflo's 27 hooks were not audited; ruflo "hard stop" is unconfirmed as a deny.
- Per-agent test DB, concurrency cap, and integration branch were grepped in harness, superpowers, BMAD, spec-kit, SuperClaude only (or not at all for ECC/ruflo/gsd-core).
- pro-workflow, zeroshot, OMC: README only. Maestro, openrig, Continuous-Claude-v3 were not studied.
- Capability 8 for harness/SuperClaude/ruflo-beyond-cost-tracker and capability 2 for ruflo/SuperClaude: `?`.
- Matrix cells are from README/skill text; claims about "N" mean not found by grep and README read, not proven absent.
- maxforge `/task` was not run end to end; enforcement was read from hook source, not exercised. Star counts move daily.
