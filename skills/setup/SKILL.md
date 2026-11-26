---
name: setup
description: Install the maxforge-claude rules into ~/.claude/rules/maxforge/ (plus optional settings merge and Playwright). Run once after installing the plugin and after each plugin update.
disable-model-invocation: true
argument-hint: "[--rules] [--settings] [--node]"
---

# maxforge-claude setup

Plugin rules are not loaded automatically by Claude Code, so this skill copies them to
`~/.claude/rules/maxforge/` (existing copy is backed up first). Arguments: `$ARGUMENTS`
(no arguments = `--rules`; `--settings` merges recommended settings without overwriting
yours; `--node` installs Playwright + axe-core for the UI QA tools).

`${CLAUDE_PLUGIN_ROOT}` and `${CLAUDE_PLUGIN_DATA}` are substituted by Claude Code inside
plugin skills but are not environment variables of the Bash tool, so pass them explicitly.

Do exactly this:

1. Dry run and show the user the printed plan (files, backups, settings diff, commands):

   ```bash
   CLAUDE_PLUGIN_DATA="${CLAUDE_PLUGIN_DATA}" CLAUDE_PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}" python3 "${CLAUDE_PLUGIN_ROOT}/bin/maxforge" setup $ARGUMENTS --dry-run
   ```

2. If the dry run failed, report the error and stop. Otherwise run the same command without
   `--dry-run`:

   ```bash
   CLAUDE_PLUGIN_DATA="${CLAUDE_PLUGIN_DATA}" CLAUDE_PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}" python3 "${CLAUDE_PLUGIN_ROOT}/bin/maxforge" setup $ARGUMENTS
   ```

3. Run `python3 "${CLAUDE_PLUGIN_ROOT}/bin/maxforge" doctor` and summarise WARN/FAIL rows in
   two lines. Tell the user to start a new session so the rules load.

Never edit the user's files by hand; only `bin/maxforge` writes.
