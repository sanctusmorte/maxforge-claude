#!/usr/bin/env python3
"""Export the owner's harness (~/.claude) into this plugin tree.

Usage: export.py [--source DIR] [--dest DIR] [--dry-run] [--patterns FILE] [--private-scrub FILE]

Source default: $MAXFORGE_SOURCE or ~/.claude. Produces: files matched by export-manifest.json
(include minus exclude, symlinks never followed), scrubbed with the manifest rules plus the private
rules file, `hooks/hooks.json` generated from the source settings.json, and `export-manifest.lock.json`.
Everything is staged first and leak-checked; a hit exits 1 and writes nothing.
Plugin-only paths are never written or deleted.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK_NAME = "export-manifest.lock.json"
HOOK_FILE = re.compile(r"hooks/([A-Za-z0-9_.-]+\.py)")
# Never touched or deleted by export (CONTRACT.md "Plugin-only files").
PLUGIN_ONLY = [
    ".claude-plugin/**", "docs/**", "README*.md", "bin/**", "skills/setup/**", "extras/**", "scripts/**",
    "tests/**", ".github/**", "NOTICE", "LICENSE", "settings/**", "hooks/hooks.plugin-extra.json",
    "hooks/maxforge-check.py", "export-manifest.json", LOCK_NAME, ".gitignore", ".git", ".tmp/**",
]
DEFAULT_PRIVATE_SCRUB = Path.home() / ".claude" / "state" / "maxforge" / "scrub-private.json"
DEFAULT_PATTERNS = Path.home() / ".claude" / "state" / "maxforge" / "leak-patterns.txt"


class ExportError(RuntimeError):
    pass


def glob_to_regex(glob: str) -> re.Pattern[str]:
    """`**` crosses directories, `*` and `?` do not; a trailing `/**` also matches the directory itself."""
    out, i = "", 0
    while i < len(glob):
        c = glob[i]
        if glob.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif glob.startswith("**", i):
            out += ".*"
            i += 2
        elif c == "*":
            out += "[^/]*"
            i += 1
        elif c == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(c)
            i += 1
    return re.compile(out + r"\Z")


def matches(rel: str, globs: list[str]) -> bool:
    return any(glob_to_regex(g).match(rel) for g in globs)


def load_json(path: Path, default: dict | None = None) -> dict:
    if not path.is_file():
        if default is not None:
            return default
        raise ExportError(f"missing file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def walk_source(source: Path):
    """Yield (rel, abs, is_symlink); symlinks are reported, never descended into."""
    for dirpath, dirnames, filenames in os.walk(source, followlinks=False):
        d = Path(dirpath)
        for name in list(dirnames):
            if (d / name).is_symlink():
                dirnames.remove(name)
                yield (d / name).relative_to(source).as_posix(), d / name, True
        for name in filenames:
            p = d / name
            yield p.relative_to(source).as_posix(), p, p.is_symlink()


def select_files(source: Path, manifest: dict) -> tuple[dict[str, Path], list[str]]:
    include, exclude = manifest["include"], manifest["exclude"]
    chosen: dict[str, Path] = {}
    skipped_links: list[str] = []
    for rel, p, is_link in walk_source(source):
        if not matches(rel, include) or matches(rel, exclude):
            continue
        if is_link:
            skipped_links.append(rel)
            continue
        if matches(rel, PLUGIN_ONLY):
            raise ExportError(f"manifest would produce plugin-only path: {rel}")
        chosen[rel] = p
    return chosen, sorted(skipped_links)


def compile_rules(rules: list[dict]) -> list[tuple[re.Pattern[str], re.Pattern[str], str]]:
    return [(glob_to_regex(r["glob"]), re.compile(r["pattern"], re.MULTILINE), r["replace"]) for r in rules]


def scrub_text(rel: str, text: str, rules) -> str:
    for gx, px, repl in rules:
        if gx.match(rel):
            text = px.sub(repl, text)
    return text


def stage_files(chosen: dict[str, Path], stage: Path, rules) -> dict[str, str]:
    produced: dict[str, str] = {}
    for rel, src in sorted(chosen.items()):
        dst = stage / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        raw = src.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            dst.write_bytes(raw)
        else:
            dst.write_text(scrub_text(rel, text, rules), encoding="utf-8")
        shutil.copymode(src, dst)
        produced[rel] = hashlib.sha256(dst.read_bytes()).hexdigest()
    return produced


def build_hooks(settings: dict, shipped: set[str], extra: dict | None) -> dict:
    """Rewire the owner's hook groups to ${CLAUDE_PLUGIN_ROOT}; keep events, matchers, timeouts."""
    events: dict[str, list] = {}
    for event, groups in (settings.get("hooks") or {}).items():
        for group in groups:
            kept = []
            for h in group.get("hooks", []):
                m = HOOK_FILE.search(h.get("command", ""))
                if h.get("type") != "command" or not m or m.group(1) not in shipped:
                    continue
                new = {"type": "command", "command": f'python3 "${{CLAUDE_PLUGIN_ROOT}}/hooks/{m.group(1)}"',
                       **{k: v for k, v in h.items() if k not in ("type", "command")}}
                kept.append(new)
            if kept:
                events.setdefault(event, []).append({**{k: v for k, v in group.items() if k != "hooks"}, "hooks": kept})
    for event, groups in ((extra or {}).get("hooks") or {}).items():
        events.setdefault(event, []).extend(groups)
    return {"hooks": events}


def third_party(source: Path, skipped_links: list[str]) -> dict[str, dict]:
    """Name -> upstream URL + license for symlinked skills, read from skills-src/*."""
    found: dict[str, dict] = {}
    for rel in skipped_links:
        if not rel.startswith("skills/") or rel.count("/") != 1:
            continue
        target = Path(os.path.realpath(source / rel))
        try:
            top = target.relative_to(source / "skills-src").parts[0]
        except ValueError:
            continue
        owner, _, repo = top.partition("_")
        license_name = "none (no LICENSE file)"
        for lf in sorted((source / "skills-src" / top).glob("LICENSE*")):
            head = lf.read_text(encoding="utf-8", errors="replace")[:400].lower()
            license_name = "MIT" if "mit license" in head else "Apache-2.0" if "apache license" in head else lf.name
            break
        found[rel.split("/", 1)[1]] = {"url": f"https://github.com/{owner}/{repo}", "license": license_name}
    return found


def load_leak_check():
    spec = importlib.util.spec_from_file_location("leak_check", Path(__file__).with_name("leak-check.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["leak_check"] = mod
    spec.loader.exec_module(mod)
    return mod


def run_leak_check(paths: list[Path], patterns: Path, allow: Path) -> list:
    lc = load_leak_check()
    private = lc.load_private(patterns) if patterns.is_file() else []
    if not private:
        print(f"export: warning: no private leak patterns at {patterns}", file=sys.stderr)
    return lc.scan_paths(paths, lc.load_allow(allow), private)


def sync_tree(stage: Path, dest: Path, produced: dict[str, str], old_lock: dict) -> tuple[int, list[str]]:
    for rel in produced:
        dst = dest / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(stage / rel, dst)
    stale = sorted(set(old_lock.get("files", {})) - set(produced))
    removed = []
    for rel in stale:
        if matches(rel, PLUGIN_ONLY):
            continue
        p = dest / rel
        if p.is_file():
            p.unlink()
            removed.append(rel)
            parent = p.parent
            while parent != dest and parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent
    return len(produced), removed


def export(source: Path, dest: Path, dry_run: bool, patterns: Path, private_scrub: Path) -> int:
    manifest = load_json(dest / "export-manifest.json")
    source_settings = load_json(source / "settings.json", {})
    rules = compile_rules(manifest.get("scrub", []) + load_json(private_scrub, {"scrub": []}).get("scrub", []))
    chosen, skipped_links = select_files(source, manifest)
    owner_only = set(manifest.get("owner_only_hooks", []))
    chosen = {r: p for r, p in chosen.items() if not (r.startswith("hooks/") and Path(r).name in owner_only)}

    declared = manifest.get("third_party_skills", {})
    found = third_party(source, skipped_links)
    if set(found) != set(declared):
        print(f"export: warning: third_party_skills drift (manifest {len(declared)}, source {len(found)}): "
              f"{sorted(set(found) ^ set(declared))}", file=sys.stderr)

    with tempfile.TemporaryDirectory(prefix="maxforge-stage-") as td:
        stage = Path(td)
        produced = stage_files(chosen, stage, rules)
        shipped = {Path(r).name for r in produced if r.startswith("hooks/") and r.endswith(".py")}
        extra_path = dest / "hooks" / "hooks.plugin-extra.json"
        extra = load_json(extra_path) if extra_path.is_file() else None
        hooks_json = json.dumps(build_hooks(source_settings, shipped, extra), indent=2, ensure_ascii=False) + "\n"
        (stage / "hooks").mkdir(exist_ok=True)
        (stage / "hooks" / "hooks.json").write_text(hooks_json, encoding="utf-8")
        produced["hooks/hooks.json"] = hashlib.sha256(hooks_json.encode()).hexdigest()

        hits = run_leak_check([stage], patterns, dest / "scripts" / "leak-allow.txt")
        if hits:
            for h in hits:
                print(str(h).replace(str(stage) + os.sep, ""))
            print(f"export: {len(hits)} leak hit(s) in staged tree; nothing written", file=sys.stderr)
            return 1

        old_lock = load_json(dest / LOCK_NAME, {"files": {}})
        if dry_run:
            stale = sorted(set(old_lock.get("files", {})) - set(produced))
            print(f"export: dry-run: {len(produced)} files, {len(stale)} stale, {len(skipped_links)} symlinks skipped, "
                  f"{len(found)} third-party skills")
            return 0
        count, removed = sync_tree(stage, dest, produced, old_lock)

    lock = {"files": dict(sorted(produced.items()))}
    (dest / LOCK_NAME).write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    print(f"export: wrote {count} files, removed {len(removed)} stale, skipped {len(skipped_links)} symlinks")
    final = run_leak_check([dest / r for r in produced], patterns, dest / "scripts" / "leak-allow.txt")
    if final:
        for h in final:
            print(h)
        print(f"export: {len(final)} leak hit(s) in final tree; do not commit", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", type=Path, default=Path(os.environ.get("MAXFORGE_SOURCE") or Path.home() / ".claude"))
    ap.add_argument("--dest", type=Path, default=ROOT)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--patterns", type=Path, default=DEFAULT_PATTERNS)
    ap.add_argument("--private-scrub", type=Path, default=DEFAULT_PRIVATE_SCRUB)
    a = ap.parse_args(argv)
    try:
        return export(a.source.resolve(), a.dest.resolve(), a.dry_run, a.patterns, a.private_scrub)
    except ExportError as exc:
        print(f"export: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
