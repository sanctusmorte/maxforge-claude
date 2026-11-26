#!/usr/bin/env python3
"""Global PostToolUse hook: after a source-code edit in a repo that has a docs/ directory,
remind the model to keep docs 1:1 with the code (see skill `code-pack` §Docs 1:1, ~/.claude/skills/code-pack/SKILL.md).

Advisory only: reads the hook payload (JSON) on stdin, emits a PostToolUse additionalContext on
stdout when the edited file is source code in a documented repo. Always exits 0, never blocks.
De-duplicated per repo for 10 minutes so a batch of edits yields one reminder."""
import hashlib
import json
import os
import re
import sys
import time

SOURCE_DIRS = r"/(app|routes|database|config|bootstrap|src|resources/js|resources/css|backend|frontend|api|services|lib|packages)/"
NON_SOURCE_DIRS = r"/(scripts|tools|research|notebooks|reports|data|docs|vendor|node_modules|tests?|__tests__|storage|dist|build|\.planning|\.git)/"
SOURCE_EXT = (".php", ".ts", ".tsx", ".js", ".jsx", ".vue", ".py", ".go", ".rs", ".sql", ".blade.php")
CONFIG_EXT = (".json", ".yaml", ".yml", ".env.example")
DEDUP_TTL_SEC = 600


def find_repo_root_with_docs(path: str) -> str:
    """Walk up from the edited file to the git root; return it if it contains docs/, else ''."""
    cur = os.path.dirname(os.path.abspath(path))
    for _ in range(14):
        has_docs = os.path.isdir(os.path.join(cur, "docs"))
        is_git_root = os.path.exists(os.path.join(cur, ".git"))
        if has_docs:
            return cur
        if is_git_root:
            return ""
        parent = os.path.dirname(cur)
        if parent == cur:
            return ""
        cur = parent
    return ""


def recently_reminded(root: str, session_id: str) -> bool:
    key = hashlib.sha1(f"{root}|{session_id}".encode()).hexdigest()[:16]
    marker_dir = os.path.join(os.environ.get("TMPDIR", "/tmp"), "claude-doc-sync")
    try:
        os.makedirs(marker_dir, exist_ok=True)
        marker = os.path.join(marker_dir, key)
        now = time.time()
        if os.path.exists(marker) and now - os.path.getmtime(marker) < DEDUP_TTL_SEC:
            return True
        with open(marker, "w") as fh:
            fh.write(str(now))
    except OSError:
        pass
    return False


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    tool_input = data.get("tool_input") or {}
    tool_response = data.get("tool_response") or {}
    path = tool_input.get("file_path") or tool_response.get("filePath") or ""
    if not path:
        return
    # .claude/ config is not source — but built-in worktrees live in .claude/worktrees/<name>/.
    if re.search(r"/\.claude/(?!worktrees/)", path):
        return
    if re.search(NON_SOURCE_DIRS, path):
        return
    in_source_dir = re.search(SOURCE_DIRS, path) is not None
    if path.endswith(CONFIG_EXT):
        # Config files count only inside explicit source dirs (config/, database/, …), never at repo root.
        if not re.search(r"/(config|database|routes|bootstrap)/", path):
            return
    elif not path.endswith(SOURCE_EXT):
        return
    elif not in_source_dir and not path.endswith(".py"):
        return
    root = find_repo_root_with_docs(path)
    if not root:
        return
    # A project that ships its own doc-sync hook handles the reminder itself.
    if os.path.exists(os.path.join(root, ".claude", "hooks", "doc-sync-reminder.py")):
        return
    if recently_reminded(root, str(data.get("session_id") or "")):
        return
    rel = os.path.relpath(path, root)
    msg = (
        f"Doc-sync: you changed {rel}. If behaviour, a flow, route, schema or config changed, update the "
        f"matching page under {root}/docs/ in THIS change (fix stale anchors, drop dead flows; "
        f"`code-pack` §Docs 1:1)."
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": msg,
        }
    }))


if __name__ == "__main__":
    main()
