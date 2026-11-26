#!/usr/bin/env python3
"""SessionStart hook: warn once when the maxforge rules are missing or outdated.

Silent when everything is fine. Never fails (always exit 0), stdlib only.
additionalContext format:
https://code.claude.com/docs/en/hooks (hookSpecificOutput.additionalContext)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

MESSAGE = "maxforge-claude: rules not installed or outdated — run /maxforge-claude:setup"


def plugin_version(root: Path) -> str | None:
    try:
        return str(json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"])
    except (OSError, ValueError, KeyError):
        return None


def installed_version(home: Path) -> str | None:
    try:
        return (home / ".claude" / "rules" / "maxforge" / ".maxforge-version").read_text(encoding="utf-8").strip()
    except OSError:
        return None


def needs_setup() -> bool:
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    root = Path(env) if env else Path(__file__).resolve().parent.parent
    want = plugin_version(root)
    if want is None:  # cannot tell: stay silent rather than nag
        return False
    home = Path(os.environ.get("HOME") or Path.home())
    return installed_version(home) != want


def main() -> int:
    try:
        if needs_setup():
            out = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": MESSAGE}}
            sys.stdout.write(json.dumps(out, ensure_ascii=False))
    except Exception:  # a hook must never break the session start
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
