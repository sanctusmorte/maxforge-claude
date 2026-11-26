# Parity check: what visitors compare us with (2026-11-26)

Method: for each alternative, `gh api repos/<o>/<r>` (stars, pushed_at, license) and `gh api repos/<o>/<r>/readme`
read on 2026-11-26; then a shallow clone of the five closest ones (`git clone --depth 1`, HEAD of 2026-11-26) searched
with `grep -rIil` for the terms `dead click`, `getBoundingClientRect` (geometry oracles), `unpushed`, `lesson`.
Stars are a public signal, not quality. "README says" = quoted from the README; "tree" = found in the cloned tree.
Limit: absence in a README or grep is not proof of absence in a 300-skill repo; every "none" below means "not found
by README read + grep on that date".

## 1. Alternatives

| Project | Stars | Last push | License | What it is (README) |
|---|---|---|---|---|
| [affaan-m/everything-claude-code](https://github.com/affaan-m/everything-claude-code) (now `affaan-m/ECC`) | 310,988 | 2026-11-23 | MIT | "agent harness operating system": 72 agents, 328 skills, 99 command shims, hooks, rules, memory, continuous learning, AgentShield scanner |
| [obra/superpowers](https://github.com/obra/superpowers) | 327,035 | 2026-11-26 | MIT | "complete software development methodology for your coding agents" (skills library; 16 harnesses listed) |
| [anthropics/claude-code](https://github.com/anthropics/claude-code) | 157,157 | 2026-11-26 | none (proprietary) | the tool itself; README = install + `/plugin` pointer |
| [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official) | 48,266 | 2026-11-26 | Apache-2.0 | "Anthropic's own plugins" + the `claude-plugins-official` marketplace |
| [gsd-build/get-shit-done](https://github.com/gsd-build/get-shit-done) | 64,121 | 2026-05-31 | MIT | ARCHIVED; README = redirect "GSD Has Moved" to open-gsd/gsd-core |
| [open-gsd/gsd-core](https://github.com/open-gsd/gsd-core) | 11,855 | 2026-11-26 | MIT | "meta-prompting, context engineering, and spec-driven development system": discuss, plan, execute, verify, ship |
| [wshobson/agents](https://github.com/wshobson/agents) | 42,914 | 2026-11-24 | MIT | catalogue of agents/skills/commands as plugins for several harnesses; paid "Verified" layer announced |
| [davila7/claude-code-templates](https://github.com/davila7/claude-code-templates) | 34,218 | 2026-11-26 | MIT | "more than 1,980" components (63 hooks, 50 mods...) browsable at aitmpl.com, `npx` install |
| [SuperClaude-Org/SuperClaude_Framework](https://github.com/SuperClaude-Org/SuperClaude_Framework) | 23,949 | 2026-09-27 | MIT | "Transform Claude Code into a Structured Development Platform": commands, agents, modes, optional MCPs |
| [Chachamaru127/claude-code-harness](https://github.com/Chachamaru127/claude-code-harness) | 3,226 | 2026-11-16 | see LICENSE.md | "The AI writes the code. You still manage the work": plan / work / review / sync / release, Go guardrail engine, hooks |
| [parcadei/Continuous-Claude-v3](https://github.com/parcadei/Continuous-Claude-v3) | 3,954 | 2026-11-16 | not read | continuity system: YAML handoffs, memory, hooks |
| [disler/claude-code-hooks-mastery](https://github.com/disler/claude-code-hooks-mastery) | 3,993 | 2026-03-04 | not read | tutorial repo for every hook event (stale 8+ months) |
| [karanb192/claude-code-hooks](https://github.com/karanb192/claude-code-hooks) | 588 | 2026-11-26 | not read | hooks collection (>500 stars; README not read in depth) |
| [hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code) | 58,841 | 2026-11-26 | NOASSERTION | a LIST, not a competitor: the place we get listed (draft entry in `docs/project/launch-copy.md`) |

Harness/hooks packs above 500 stars found with `gh search repos` ("claude code hooks", "claude code harness",
"everything claude code"): ECC, Chachamaru127/claude-code-harness, Continuous-Claude-v3, claude-code-hooks-mastery,
claude-code-hooks-multi-agent-observability (1,577, observability, not gates), karanb192/claude-code-hooks.

## 2. What each ships (README quotes, 2026-11-26)

| Project | Hooks that BLOCK | Verification before done | UI QA | Worktrees | Continuity | Lessons |
|---|---|---|---|---|---|---|
| ECC | yes: README "Blocks git hook bypasses and dev servers outside tmux (exit 2)", ".env/.key/.pem reads", `context-gate.js` "advisory by default", `enforce` opt-in | `/verify`, `verification-loop`, `/quality-gate` (commands/skills) | `e2e-runner` Playwright agent; no dead-click/geometry in tree | "worktree lifecycle service" | `pre-compact.js`, `session-start.js`, "Memory Vault ... handoffs" | `/learn`, "instincts ... confidence scores", `continuous-learning-v2` |
| obra/superpowers | none (SessionStart bootstrap hook only) | skill `verification-before-completion`; "Critical issues block progress" (review skill) | none | skill `using-git-worktrees` | bootstrap "injected at session startup and again after compaction" | none (skill `diagnosing-superpowers` reads transcripts) |
| claude-code-harness | yes: "direct pushes to the shared main branch, forced pushes", "secret reads", "protected files"; "no global off switch" for the runtime floor | `/harness-review`: "Serious findings block completion"; test-first demo of failing test | none | worker isolation in a worktree (hosts.toml, 27 hook event types in `hooks/hooks.json`) | `/harness-work --resume latest`; optional harness-mem | none |
| davila7 templates | catalogue entries: "blocking direct pushes", `secret-redactor`, protected paths (opt-in `npx` installs) | none | none | none | none | none |
| wshobson/agents | plugin-specific hooks only | "Verified" paid scorecards (judge scores workflows) | skill `responsive-design`, `interaction-design` (guidance only) | none | none | none |
| SuperClaude | none in README | none | Playwright MCP mention | none | Serena MCP "session persistence & memory" | ReflexionMemory ("error learning") |
| gsd-core | none in README | "Verify: walk through what was built; diagnose and fix before declaring done" (prompted) | none | none | fresh 200k context per executor ("context rot") | none |
| anthropics official | `security-guidance` (warns on ~25 patterns; LLM diff review on turn end and agentic review on `git commit`), `hookify` (user-written rules from conversations) | `code-review` (parallel agents, confidence scoring), `pr-review-toolkit` | `frontend-design` (skill), `playground` | none found | none | `hookify`: "analyzing conversation patterns" to create hooks |
| Continuous-Claude-v3 | few | "verif" mentions, no gate | none | none | yes: "create_handoff / resume_handoff", ledger | none |
| claude-code-hooks-mastery | tutorial: `pre_tool_use.py` blocks `rm -rf`/`.env`; Stop-hook example "decision: block" if tests fail | example only | none | none | none | none |
| awesome-claude-code | list | list | list | list | list | list |

Tree grep (HEAD 2026-11-26), count of files: `dead.click` = 0 in ECC, superpowers, claude-code-harness, agents,
claude-code-templates, Continuous-Claude-v3. `unpushed` = 0 in superpowers, agents, Continuous-Claude-v3; 4 in ECC
(`commands/pr.md` = prompt text, not a hook); 0 hook hits in claude-code-harness (only CHANGELOG/notify text);
14 in claude-code-templates (not inspected). `getBoundingClientRect` appears only in app code of ECC/templates
dashboards and one guidance skill in agents, not in a QA runner.

## 3. Candidate differentiators (strikethrough = an alternative already ships it)

| # | Candidate | Verdict | Evidence |
|---|---|---|---|
| 1 | ~~Hooks deny direct push to `main`, force-push, `--no-verify`~~ | struck | claude-code-harness README "direct pushes to the shared main branch, forced pushes"; ECC "Blocks git hook bypasses"; davila7 "blocking direct pushes" |
| 2 | ~~Secret / `.env` commit and read gate~~ | struck | claude-code-harness "secret reads"; ECC ".env/.key/.pem reads", AgentShield; davila7 `secret-redactor`; official `security-guidance` |
| 3 | ~~Verifier / reviewer agents, "no done without evidence" skills~~ | struck | superpowers `verification-before-completion`; claude-code-harness `/harness-review`; official `code-review`; ECC `/verify` |
| 4 | ~~Worktree per task + PR per task~~ | struck as a feature (kept only as workflow) | superpowers `using-git-worktrees`; ECC worktree lifecycle; claude-code-harness worker worktrees |
| 5 | ~~Task state survives compaction~~ | struck | ECC `pre-compact.js` + Memory Vault; Continuous-Claude-v3 handoffs; superpowers re-injects bootstrap after compaction |
| 6 | ~~Corrections become lessons / rules~~ | struck | official `hookify` (hooks from conversation patterns); ECC `/learn`, instincts; SuperClaude ReflexionMemory |
| 7 | ~~Spec, plan, build workflow skills~~ | struck | superpowers brainstorming/writing-plans; gsd-core discuss/plan/execute; claude-code-harness `/harness-plan` |
| 8 | ~~Python stdlib hooks, MIT, plugin marketplace install~~ | struck as a differentiator | every alternative is MIT/Apache and installable; stdlib-only is an install detail, not a buyer reason |
| 9 | **UI QA oracles as gates: `tools/dead-clicks.mjs` (every control per route and viewport, `NO_EFFECT`/`ERROR` = blocker) and `tools/ui-geometry.mjs` (overlap/clipping/overflow at 390/768/1440/2560)** | KEPT | no `dead.click` file in 6 cloned trees; no geometry QA runner; ECC ships only an `e2e-runner` Playwright agent and wshobson only guidance skills. Self-tests: `tools/fixtures/dead-clicks/`, `tools/test-ui-geometry.mjs` |
| 10 | **Artefact-gated PR: `hooks/guard-bash.py` denies a non-draft UI PR without a passing design scorecard and fresh dead-click + geometry reports** | KEPT | alternatives gate on review prose ("Serious findings block completion", claude-code-harness) or warn after the fact (official `security-guidance`); none denies `gh pr create` on missing machine reports. `tools/test-designgate.py` |
| 11 | **Stop-guard: stop is blocked while the session worktree is dirty or has unpushed commits (`hooks/stop-guard.py`)** | KEPT (narrow) | 0 hook hits for `unpushed` in the six trees; hooks-mastery shows a generic Stop-block example for failing tests only |
| 12 | **Context discipline that denies, not advises: whole-file read cap, `cat` dumps, `sleep` polling, subagent context fence with `FENCE-HANDOFF` (`hooks/token-guard.py`, `dump-nudge.py`)** | KEPT (narrow) | ECC `context-gate.js` is "advisory by default" and opt-in at 90% context; no alternative README mentions a read cap or fence |
| 13 | **Every claim in the README = file + test; cost stated up front (about 1.49x tokens at equal quality, owner A/B 2026-10-13)** | KEPT as positioning | SuperClaude README claims "30-50% fewer tokens"; ECC and superpowers state no cost; claude-code-harness has a "Cost and project data" section but no measured ratio |

## 4. Surviving differentiators (use these, in this order)

1. **UI QA that clicks every control and measures geometry, as a hard gate**: dead-click oracle plus geometry oracle
   at 4 viewports (`tools/dead-clicks.mjs`, `tools/ui-geometry.mjs`). No alternative ships either (grep, 6 trees).
2. **A PR cannot be opened without machine-readable proof**: `hooks/guard-bash.py` denies a UI PR without scorecard +
   fresh dead-click and geometry reports; others gate on prose review.
3. **Enforcement of session hygiene, not advice**: stop blocked on dirty/unpushed worktree (`hooks/stop-guard.py`),
   context-discipline denies and subagent fence (`hooks/token-guard.py`); ECC's nearest hook is advisory by default.
4. **Verifiable claims and honest cost**: each README claim names its file and test; costs ~1.49x tokens, stated.

Positioning consequence: do NOT lead with "blocks pushes to main / secrets / done without evidence" (items 1-3
above: claude-code-harness, ECC and official plugins say the same). Lead with the proof-of-UI angle (1, 2) and let
the shared gates appear as table stakes. The existing README comparison table (`README.md`, "Compared with ...")
omits ECC (311k stars), claude-code-harness (closest in wording) and the official marketplace; add them.

## NOT verified

- Source of ECC/templates/harness was grepped, not read; hooks in `hooks/hooks.json` of ECC (hundreds of lines) and
  harness (27 event types) were not audited line by line. A dead-click or geometry gate hiding under another name
  would not be found by these greps.
- claude-code-templates: 14 `unpushed` files not inspected; karanb192/claude-code-hooks, Continuous-Claude-v3
  and hooks-mastery licenses not read.
- GitHub code search was rate-limited (HTTP 403) mid-run; the `dead click` 27-hit count from it was a loose match
  and the tree grep (0 files) supersedes it.
- Star counts are as of 2026-11-26 11:00-12:00 UTC and move daily.
