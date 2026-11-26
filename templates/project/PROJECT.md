# <project-name> — one-line purpose

<!-- Human-owned. ≤80 lines. Changes rarely (stage, goal, constraints). Facts only; process lives in ~/.claude. -->

## Stage
<idea | prototype | MVP | prod> since <YYYY-MM-DD>. Environments: <dev URL / prod URL / tenants>.

## Goal
<one measurable sentence: who gets what outcome>

## Non-goals
- <explicitly out of scope for the current stage>

## Users / actors
- <role — what they do in the product>

## Constraints
- Stack: <framework versions, DB, queue, FE>
- Branch flow: <dev → PR; master = prod release (merge commit) | main only>
- Test gate: <exact commands that must be green before a PR>
- Deploy: <mechanics: workflow name / manual runbook / what auto-runs (migrations, horizon restart)>
- Version endpoint(s) for deployed SHA (optional): dev=<URL or "-">, prod=<URL or "-">

## Pointers
- Docs index: <docs/README.md | docs/index.md>
- Specs: docs/project/specs/ · Decisions: docs/project/DECISIONS.md · Milestones: docs/project/MILESTONES.md
- Tracker / dashboards: <URLs or "-">
- Volatile ops facts (prod IP, blockers): auto-memory `~/.claude/projects/<proj>/memory/MEMORY.md`
