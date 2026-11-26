# Recommended settings

`maxforge setup --settings` adds these keys to `~/.claude/settings.json` only when missing (list values gain missing entries; your values are never overwritten; a backup and a diff are shown first). It never sets `model` or `bypassPermissions`.

- `env.CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` = `10`: the worktree-per-task workflow runs several subagents in parallel; the default cap is lower.
- `cleanupPeriodDays` = `60`: keeps session transcripts long enough for handoffs and lesson capture to find them.
- `permissions.deny` force-push to `main`/`master` (4 patterns): protected branches change only through merged PRs.
- `permissions.deny` `git filter-repo*`, `git filter-branch*`: history rewrites are irreversible; do them by hand.
- `permissions.deny` `rm -rf /*`, `rm -rf ~*`: blocks the most destructive shell mistakes.
