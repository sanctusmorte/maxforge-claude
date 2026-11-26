---
layout: home
title: "maxforge-claude - Claude Code for big tasks and whole projects"
description: "A Claude Code plugin: a spec before code, parallel subagents in separate worktrees, a verifier that tries to refute the result, one pull request. Hooks deny the shortcuts. Costs about 1.49 times the tokens."
hero:
  name: maxforge-claude
  text: "Claude Code for big tasks and whole projects: a plan first, parallel agents, proof before every pull request."
  tagline: "A Claude Code plugin: a spec before code, parallel subagents in separate worktrees, a verifier that tries to refute the result, one pull request. Hooks deny the shortcuts, from a push to main to a UI pull request nobody clicked."
  image:
    src: /readme/art/hero.webp
    alt: "Illustration: a robot foreman cuts a big blueprint into task cards; six robots build parts in parallel, each in its own glass booth; the parts pass an amber checkpoint gate and stack into one tower."
  actions:
    - theme: brand
      text: "Install: 3 commands"
      link: /guide/install
    - theme: alt
      text: How a task flows
      link: /guide/workflow
    - theme: alt
      text: GitHub
      link: https://github.com/sanctusmorte/maxforge-claude
features:
  - icon: { src: /readme/art/parallel.webp, width: 160, height: 107 }
    title: One big task, start to finish
    details: Triage, a spec with requirements and waves, one subagent per unit in its own worktree and branch, an integration branch, one review, a verifier, one pull request.
    link: /guide/workflow
  - icon: { src: /readme/art/project.webp, width: 160, height: 107 }
    title: A whole project
    details: "/maxforge-claude:project-new: research, PROJECT.md and ADRs that a reviewer tries to refute, bootstrap with CI and a test stand, milestones that become tasks. STATE.md is generated from git and GitHub."
  - icon: { src: /readme/art/relay.webp, width: 160, height: 107 }
    title: Long sessions without losing the thread
    details: progress.md per task is committed before compaction and put back after it; a subagent at its context fence hands over with FENCE-HANDOFF.
  - icon: { src: /readme/art/verifier.webp, width: 107, height: 107 }
    title: Proof before "done"
    details: A verifier that did not write the code tries to refute it; a stop with unverified spec requirements is blocked. A UI pull request needs a dead-click report and a layout report.
    link: /guide/gates
  - icon: { src: /readme/art/gate.webp, width: 107, height: 107 }
    title: Gates in every repo
    details: Push to main, force-push, --no-verify, rm -rf ~, destructive DB commands and secrets in a commit are denied by hooks, and each deny names the reason.
    link: /guide/gates
  - icon: { src: /readme/art/lessons.webp, width: 107, height: 107 }
    title: Corrections become checks
    details: When you correct the agent, lesson-capture flags it and the lesson skill records what was wrong, what is right and a check; every new subagent gets the active lessons.
---

## Install

```text
/plugin marketplace add sanctusmorte/maxforge-claude
/plugin install maxforge-claude@maxforge-claude
/maxforge-claude:setup
```

`setup` shows a dry run first, then copies the rules to `~/.claude/rules/maxforge/` (old copy backed up) and runs `maxforge doctor`. Start a new session afterwards so the rules load.

::: info Cost
It spends more tokens, not fewer: about 1.49 times the tokens of plain Claude Code at equal quality (author's A/B run, 2026-10-13). The plugin never edits your `CLAUDE.md`.
:::

## What a deny looks like

![Terminal replay of four real hook outputs: guard-bash denies git push origin main and rm -rf ~, secret-scan denies a commit with an AWS-style key, stop-guard blocks Done. with 3 requirements not verified.](/readme/terminal-light.svg)

The design gate on the self-test fixture, verbatim from `hooks/guard-bash.py`:

```text
guard-bash: design gate: a PASS scorecard exists but is not complete — dashboard/scorecard.md: dead-clicks: 2 control(s) without effect or with an error: NO_EFFECT «Dead button», ERROR «Throwing button» — every State matrix row needs a screenshot or an 'n/a reason'; every control needs an effect in dead-clicks/report.json (allowlist only with a reason) or the scorecard says 'Interaction: n/a — <reason>'; geometry/report.json (tools/ui-geometry.mjs) with 0 errors or 'Geometry: n/a — <reason>' (templates/project/design-scorecard.md § State matrix, § Interaction, § Geometry)
```

Every gate with its trigger and escape hatch: [Gates](/guide/gates).

## Compared with

Other packs warn, advise or gate on review text; here the hook denies the tool call and names the missing report. The cited table: [README, Compared with](https://github.com/sanctusmorte/maxforge-claude#compared-with-what-you-might-already-use).

Requirements: Python 3.10+ and git. Optional: `gh`, Node 18+ and Playwright for the UI tools. License: MIT. No telemetry.
