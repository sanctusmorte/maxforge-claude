---
name: project-sync
description: Regenerate docs/project/STATE.md from git/GitHub facts and progress.md files, curate Next/Blockers, append decisions; `--init` bootstraps docs/project/ + auto-memory. Use when SessionStart printed no digest, after merging PRs, before a release or declaring done, and on «что по проекту / где мы».
argument-hint: [--init] [--base <branch>] [--write]
---
# /project-sync — derive the state, then curate it

Script: `~/.claude/hooks/project-sync.py` (same as the SessionStart hook). Templates: `~/.claude/templates/project/`.
Truth split: **constitution** `PROJECT.md` (human-owned, rarely changes) · **state** `STATE.md` (regenerated, ≤60 lines)
· **ledgers** `DECISIONS.md`, `MILESTONES.md`, `specs/<slug>.md`, optional `CHANGELOG.md` (append-only, one line per
entry with unique ids `D-n`/`M-n` so parallel branches auto-merge). GSD repos (`.planning/` exists) keep their artifacts;
use `gsd-progress` / `gsd-spec-phase` / `gsd-verify-work` there instead of duplicating.

## Rules
1. Derive, don't narrate: anything computable from git/gh/deploy endpoints comes from the script — never typed.
2. Agents write only typed fields (Next / Blockers / Do-not, decision lines, spec status); humans own Stage,
   Goal, Constraints. Every line cites evidence (PR#, run URL, sha). `## Now` is generated, never hand-edited.
3. Provenance in STATE frontmatter (`last_sync`, `last_sync_sha`, `base_branch`, `deployed`); >7 days or >30 commits
   behind → stale → re-derive before relying. GitHub wins over STATE on any contradiction.
4. STATE.md is GENERATED and rewritten only by `--write` run by the orchestrator inside a task worktree (a hook or a
   write in the main checkout dirtied it and froze main-sync, 2026-11-25). Per-task continuity = ONE
   `docs/project/tasks/<slug>/progress.md` (interface I1: Goal / Git / Next / Dead ends / Verify / Status, ≤60 lines,
   overwritten, committed in the task branch; no docs/project → `~/.claude/state/<repo>/<slug>.md`). Dated
   `handoff-*.md` and `~/.claude/handoffs` are legacy: read-only, nothing deleted. STATE ≤60 lines, PROJECT ≤80; finished specs get `status: shipped` and stay as history — never a diary.
5. Project docs live in git (visible to every agent/tool); auto-memory holds only personal preferences and volatile
   ops facts (`reference_prod.md`: prod pointers, live blockers).

## Modes
- `python3 ~/.claude/hooks/project-sync.py --print` (default, read-only snapshot).
- SessionStart hook (no flag) = strictly read-only digest: STATE essentials + `## Now` headlines + ≤3 active tasks
  (progress.md, status ≠ merged, touched <14 d: slug, status, first `## Next` line) + open PR count.
- `--write` (inside a linked worktree only; refuses in the main checkout) → regenerates `## Now` (≤3 lines from open PRs +
  active progress.md), the derived section (Landed top 10 from `--landed`), frontmatter, and the specs index
  `docs/project/specs/README.md`; never touches Next/Blockers/Do-not.
- `--check [--strict]` → budgets: STATE lines/tokens, Now/Next counts, resync lag, DECISIONS lines ≤300 chars (detail →
  `docs/adr/D-n-*.md`), domain-doc size ratchet. Run before closing a sync.
- `--landed [--since 14d] [--domain d] [--path p]` → L4 navigator of merged PRs (stdout, cached); `--specs-index` alone.
- `--init` → create `docs/project/{PROJECT.md,STATE.md,DECISIONS.md,MILESTONES.md,DESIGN.md?,specs/}` from templates,
  filled ONLY from verifiable sources (project CLAUDE.md, README, docs index, composer/package.json, workflows, deploy
  scripts); leave `<confirm with user>` where docs are silent — never invent goals. Also create the repo's auto-memory
  `MEMORY.md` + `reference_prod.md`. DESIGN.md only from real tokens/fonts/components. GSD repo → do not init.

## Session start (≤2k tokens; the hook prints the digest when STATE exists)
0. Ritual: read the task's progress.md → run its `## Verify` → only then new work.
1. PROJECT.md + STATE lines 1–40. 2. `git status -sb`, `git log --oneline -5`.
3. Landed since `last_sync_sha`, open PRs + CI — red first. 4. Deployed vs `origin/master` → "undeployed changes".
5. Cross-check STATE claims; surface ≤3 risks (red CI, stale STATE, conflicting PRs, prod ≠ master).
6. Take the task from the user's message or `Next`; confirm branch base (core rule 1).

## Sync at the end of a task (same PR, before "done")
Docs 1:1 · spec `## Requirements status` rows verified (by `verifier`; `tools/req-status.py`), then `status: shipped` · `DECISIONS.md` one line per decision (`YYYY-MM-DD | D-n | decision | why | PR#`)
· progress.md `## Status` → merged · STATE Next/Blockers (evidence) · CHANGELOG `[Unreleased]` line if the project keeps one · `--write` to refresh
derived data. Inside a task worktree these files ride the task PR; otherwise open a doc-only PR
(`chore(project): sync STATE`) — never push to the base directly. Reply in Russian ≤10 lines: stage, landed since last
sync, open PRs + CI, deployed vs base, risks, Now/Next.
