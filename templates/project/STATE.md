---
last_sync: <YYYY-MM-DDTHH:MMZ>
last_sync_sha: <origin/<base> full sha at last sync>
base_branch: <dev | master | main>
deployed: { dev: <sha|->, prod: <sha|-> }
status: active
---
<!-- GENERATED snapshot, ≤60 lines — `project-sync.py --write` (inside a task worktree) rewrites `## Now` (≤3 lines: open PRs + active progress.md) and `## Landed`. Per-task detail lives in docs/project/tasks/<slug>/progress.md, never here; no handoff pointer lines. Every claim carries evidence (PR#, run URL, sha). -->

## Now (≤3)
- <slug> — branch `<name>` — PR #<n> — <goal, first line of progress.md> — status <active|blocked|pr-open>   <!-- generated -->

## Next (≤5, ordered, each executable)
1. <task> — spec: docs/project/specs/<slug>.md
2. <task>

## Blockers
- <what> — evidence: <run URL / issue / PR#> — owner <who>

## Landed since last sync (derived)
- <auto: merged PRs, commits on base, deploys>

## Do-not (dead ends already tried)
- <approach> — why it failed — <date>
