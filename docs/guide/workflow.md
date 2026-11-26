---
title: "Claude Code workflow - worktree per task, parallel subagents, one PR"
description: "How a task flows through maxforge-claude - triage, spec, parallel subagents split by file ownership, review, verifier, and one pull request."
---

# Workflow: worktree per task, parallel subagents, one PR

The default path for a non-trivial task is `/maxforge-claude:task` (`skills/task/SKILL.md`).

1. **Triage.** New project (`skills/project-new`) or task in an existing repository; quick or full by size.
2. **Spec.** `skills/spec` scouts the repository, records assumptions, asks only decisive questions and writes a plan.
3. **Split by file ownership.** A shared contract file and placeholders are written first. One agent per independent unit, each in its own worktree, branch, temp directory and test database. Overlapping files mean one agent.
4. **Parallel waves.** Units start together; a dependent unit starts once its dependency is pushed. Claude Code's own concurrency cap is `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`; `settings/recommended.json` sets it to 10.
5. **Integration branch.** Unit PRs merge into `task/<slug>`.
6. **Review and verify.** One independent `code-reviewer` pass (plus `security-reviewer` when the diff touches auth, uploads, billing, webhooks or secrets), then the `verifier` agent tries to refute the result.
7. **One PR** into the integration branch. Merging into `main` is a separate release decision.

## Screens and selling pages

- App screens: `/maxforge-claude:ui-task` (`skills/ui-task/SKILL.md`): design system first, references and a plan for new screens, build, `ui-qa`, `dead-clicks`, one `design-judge` verdict.
- Landing, pricing, signup: `/maxforge-claude:site` (`skills/site/SKILL.md`): brief, positioning, copy, architecture, then visuals, with a sign-off at each stage.

## Continuity

Each task keeps a `progress.md` (`skills/handoff`). The PreCompact hook refreshes and commits it; the SessionStart hook re-injects it after compaction or resume. A subagent that reaches its context fence writes a handoff and returns `FENCE-HANDOFF <path>` so the caller continues with a fresh agent.

## Lessons

When you correct the agent, `hooks/lesson-capture.py` flags it and `skills/lesson` records what was wrong, what is right, and a check, so the same mistake is caught next time.

The generic form of these process rules is in `extras/rules/core.md`.
