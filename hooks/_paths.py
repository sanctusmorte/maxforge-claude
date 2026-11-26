"""Portable path resolution shared by hooks and tools (stdlib only, import-light: hot-path hooks pay for this import).

Same files run (a) from ~/.claude (owner layout) and (b) from a plugin dir ($CLAUDE_PLUGIN_ROOT) with mutable
data in $CLAUDE_PLUGIN_DATA. Static assets are found via this file's location; mutable state/logs go to
data_dir(). Paths that mean the USER's own Claude config (settings.json, projects/ transcripts, rules/) are NOT
plugin-relative: user_dir() stays ~/.claude based.

String API (no pathlib import, used by hooks): harness_dir, data_dir, user_dir, tilde, private.
Path API (lazy pathlib): HARNESS_ROOT, data_root(), state_dir(), logs_dir(), user_config().
"""
from __future__ import annotations

import os

_HARNESS = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
_HOME_CLAUDE = os.path.join(os.path.expanduser("~"), ".claude")


def __getattr__(name):   # PEP 562: HARNESS_ROOT = Path(__file__).resolve().parents[1], built on first use only
    if name == "HARNESS_ROOT":
        from pathlib import Path
        return Path(_HARNESS)
    raise AttributeError(name)


def harness_dir(*parts: str) -> str:
    """Static assets of this harness/plugin (tools/, rules/, ...), found via this file's location."""
    return os.path.join(_HARNESS, *parts)


def _data_base() -> str:
    return os.environ.get("CLAUDE_PLUGIN_DATA") or _HOME_CLAUDE


def data_dir(*parts: str) -> str:
    """Mutable data: $CLAUDE_PLUGIN_DATA/<parts> if set (parent dir created), else ~/.claude/<parts> (owner layout)."""
    path = os.path.join(_data_base(), *parts)
    if os.environ.get("CLAUDE_PLUGIN_DATA") and parts:
        os.makedirs(os.path.dirname(path) if "." in parts[-1] else path, exist_ok=True)
    return path


def user_dir(*parts: str) -> str:
    """The USER's Claude config (settings.json, projects/ transcripts+memory): always ~/.claude, never plugin-relative."""
    return os.path.join(_HOME_CLAUDE, *parts)


def data_root():
    from pathlib import Path
    return Path(_data_base())


def state_dir():
    d = data_root() / "state"
    d.mkdir(parents=True, exist_ok=True)
    return d


def logs_dir():
    d = data_root() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def user_config():
    from pathlib import Path
    return Path(_HOME_CLAUDE)


def tilde(p) -> str:
    """Display form: ~/... for paths under the home dir (messages stay short and identical for the owner)."""
    s, home = str(p), os.path.expanduser("~")
    return "~" + s[len(home):] if s == home or s.startswith(home + os.sep) else s


def private(name: str, default=None):
    """Owner-only overlay: <harness>/private/<name>.json (= ~/.claude/private for the owner) if present, else `default`
    (feature silently off). $CLAUDE_PRIVATE_DIR overrides the lookup dir (tests: fixture dir or an empty one)."""
    import json   # lazy: hot-path hooks that never read an overlay must not pay for it
    override = os.environ.get("CLAUDE_PRIVATE_DIR")
    for d in ([override] if override is not None else [os.path.join(_HARNESS, "private"), os.path.join(_HOME_CLAUDE, "private")]):
        try:
            with open(os.path.join(d, name + ".json"), encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            continue
    return default
