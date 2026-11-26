---
title: "Uninstall maxforge-claude"
description: "How to remove the maxforge-claude Claude Code plugin, its copied rules and optional settings merge, and what stays on disk."
---

# Uninstall

```text
maxforge uninstall
/plugin uninstall maxforge-claude@maxforge-claude
```

## What gets removed or kept

| Item | After uninstall |
|---|---|
| Plugin files (hooks, skills, agents, tools) | removed by `/plugin uninstall` |
| `~/.claude/rules/maxforge/` | removed by `maxforge uninstall`; the setup backup stays |
| Settings merged with `--settings` | restore from the backup that setup made |
| Playwright in the plugin data directory (`--node`) | stays until you delete `$CLAUDE_PLUGIN_DATA` |
| Logs and state (`~/.claude/state`, `~/.claude/logs`) | stay; delete by hand if you do not want them |
| `progress.md` files committed in your task branches | stay; they are normal git history |

Run `maxforge doctor` afterwards to confirm nothing still points at the plugin. To pause instead of remove, disable the plugin in `/plugin` or use a single [escape hatch](/guide/faq#how-do-i-disable-one-hook).
