# Project state & continuity (always loaded — the contract; procedure in `/project-sync`, `/handoff`)

- Every repo: `docs/project/` = `PROJECT.md` (human-owned constitution) · `STATE.md` (GENERATED, ≤60 lines,
  provenance frontmatter) · `DECISIONS.md` / `MILESTONES.md` / `specs/` ledgers · `DESIGN.md` (UI source of truth,
  implement 1:1). GSD-legacy repos (`.planning/`) keep their artifacts. No `docs/project/` → `/project-sync --init`
  (facts only, `<confirm with user>` where docs are silent).
- Derive, don't narrate: git/GitHub facts come from `hooks/project-sync.py`; STATE lines cite PR#/run/sha; GitHub
  wins on contradiction; stale after 7 days / 30 commits. STATE is generated (`project-sync.py --write`, inside a
  worktree, never by a hook or in the main checkout); budgets: `--check`.
- Continuity = ONE file per task: `docs/project/tasks/<slug>/progress.md` (≤60 lines, overwritten: Goal · Git ·
  Next · Dead ends · Verify · Status), committed in the task branch; no docs/project → `~/.claude/state/<repo>/<slug>.md`.
  Written by `/handoff` and the PreCompact hook (never touches STATE/MEMORY; commits progress.md ALONE on the task
  branch + pushes; SessionStart `compact|resume` re-injects it — `hooks/session-restore.py`). `tasks/<slug>/` =
  working state (progress, briefs); specs stay in the `specs/` ledger. Raw transcripts are never committed
  (secrets). Dated `handoff-*.md` and `~/.claude/handoffs` are legacy (read-only). Start ritual: read progress.md →
  run `## Verify` → new work.
  Spec `## Requirements status` rows ≠ verified block Stop once (`tools/req-status.py`).
- Session start: the hook prints a STATE digest + ≤3 active tasks (read-only); read PROJECT.md, `git status -sb`,
  red CI first, surface ≤3 risks, take the task from the user or progress.md `## Next`.
- Compact instructions (when compaction happens): preserve the task goal, modified files, PR/branch,
  test commands, open REQ ids and the last failing check — everything else can be summarised.
