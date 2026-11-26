---
title: "FAQ - cost, CLAUDE.md conflicts, Windows, disabling hooks, telemetry"
description: "Answers about maxforge-claude token cost, coexisting with your CLAUDE.md, Windows and macOS support, disabling a single Claude Code hook, and telemetry."
---

# FAQ

## Does it save tokens?

No. It costs more: about 1.49 times the tokens in the author's A/B run at equal quality. The harness buys enforcement and verification. Some hooks remove waste inside it, but the net is higher.

## Does it conflict with my own CLAUDE.md?

The plugin never edits it. Rules go to `~/.claude/rules/maxforge/`. If your `CLAUDE.md` says something different from a rule, the model sees both and may follow either; hooks enforce regardless of text. Keep project `CLAUDE.md` to facts (stack, commands, ports) and let the rules carry process.

## Windows and macOS?

Hooks are Python 3.10+ stdlib. The author develops on Linux, and some tools are bash scripts (`tools/wt-new.sh`, `tools/q`). macOS is expected to work but has no test matrix here; on Windows use WSL. Report platform problems as issues.

## How do I disable one hook?

Per-run escape hatches, each meant to be used knowingly with the reason stated to the user:

| Variable | Disables |
|---|---|
| `CLAUDE_GUARD_OFF=1` | git and destructive-command gate, design gate, rules gate |
| `CLAUDE_ALLOW_SECRETS=1` | secret scan on one commit |
| `CLAUDE_TOKEN_GUARD_OFF=1` | token guard |
| `CLAUDE_BG_ROUTER_OFF=1` | background routing |

To remove a hook for good, disable the plugin in `/plugin`.

## Telemetry?

None. The plugin sends no usage data, and logs stay on your machine. One thing to know: `hooks/project-sync.py` can make an HTTP GET to the deployed-SHA URLs you list in your own `docs/project/PROJECT.md`, to show what is live.

## Do I need gh and Node?

No. Without `gh` you open PRs by hand. Without Node the UI tools (`ui-qa`, `dead-clicks`) are unavailable, so the design gate cannot be satisfied for a UI PR except with an explicit n/a reason.

## Can I use only part of it?

Yes. Hooks run without invoking any skill. Skills and agents cost nothing until used.

## What is the licence?

MIT. Third-party notes are in `NOTICE`.
