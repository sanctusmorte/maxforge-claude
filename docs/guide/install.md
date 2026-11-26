---
title: "Install the maxforge-claude Claude Code plugin"
description: "Install maxforge-claude in 60 seconds with the Claude Code plugin marketplace, run setup to copy rules, and verify with maxforge doctor."
---

# Install the Claude Code plugin in 60 seconds

## Steps

Run inside Claude Code:

```text
/plugin marketplace add sanctusmorte/maxforge-claude
/plugin install maxforge-claude@maxforge-claude
/maxforge-claude:setup
```

Then ask Claude to run the check (`bin/` is on the PATH of Claude Code's Bash tool, not of your own shell):

```bash
maxforge doctor
```

## What setup does

Claude Code does not load rules from a plugin automatically, so `/maxforge-claude:setup` copies `rules/*.md` and the generic core rules into `~/.claude/rules/maxforge/`. It keeps a backup of anything it replaces and writes a version stamp (`.maxforge-version`). A SessionStart hook warns when the copy is missing or older than the plugin.

| Flag | Effect |
|---|---|
| (none) | copy rules |
| `--settings` | optional: merge recommended settings into your `settings.json`, backup first |
| `--node` | install Playwright and axe for the UI tools (`ui-qa`, `dead-clicks`) |
| `--dry-run` | show what would change |

## Requirements

- Required: Python 3.10+ (hooks use the standard library only) and git.
- Optional: `gh` for the PR flow; Node 18+ and Playwright for UI QA and dead-click checks.

## Verify

`maxforge doctor` reports each requirement, the rules copy and its version. If a hook seems silent, doctor is the first stop.

## Optional extras

`extras/output-styles/dense-en.md` is a short-answer output style (verdict first, no filler). `extras/rules/core.md` is a generic version of the process rules. Both are plain files; copy them where you want them.

Uninstall: [uninstall](/guide/uninstall). What each gate does: [gates](/guide/gates).
