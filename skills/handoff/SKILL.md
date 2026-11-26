---
name: handoff
description: Write the task's progress.md (goal, git, next step, dead ends, verify, status) and commit it in the task branch so a new session or post-/compact continues. Use before closing mid-task, before /compact, or on «запиши где остановились».
argument-hint: [short task slug]
---
# /handoff — overwrite progress.md, commit it

1. Repo root + slug (`$ARGUMENTS`, else the branch name without its prefix).
2. Path (interface I1): inside a task worktree of a repo with `docs/project/` → `docs/project/tasks/<slug>/progress.md`;
   otherwise `~/.claude/state/<repo>/<slug>.md`. OVERWRITE (never append, never a dated file), ≤60 lines, Russian
   prose, identifiers verbatim, sections exactly:
   - `## Goal / done-when` (spec path if any) · `## Git` (branch, worktree, PRs, last pushed sha)
   - `## Next` — first line = the next atomic step with `path:line`; then the ordered rest
   - `## Dead ends` (tried, why it failed) · `## Verify` (ONE command) · `## Status` (`active|blocked|pr-open|merged`)
   If the file exists, keep the human-filled content and refresh what changed; never wipe Next or Dead ends.
3. Do NOT touch `docs/project/STATE.md` or any MEMORY.md — STATE is generated (`/project-sync`), no pointer lines.
4. In a task worktree commit the file with the task branch (doc-only commit, `docs(<slug>): progress`) and push; elsewhere
   it is already outside the repo.
5. Reply in one line: path + first `## Next` line. Next session: read progress.md → run `## Verify` → new work.
   The PreCompact hook refreshes the same file automatically (Git/Status only).

Legacy: dated `docs/project/tasks/handoff-*.md` and `~/.claude/handoffs/` (fence skeletons) are no longer written by
this skill; they stay readable, nothing is deleted.
