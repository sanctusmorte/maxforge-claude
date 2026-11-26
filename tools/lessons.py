#!/usr/bin/env python3
"""Owner-lesson store: inject / render / check-repeat / stats / expire / new / repeat / memory-index.

Records: lessons/<id>.md = YAML-subset frontmatter (one `key: value` per line, values JSON-style) + short body.
Interfaces: I3 `inject` (hot path, exit 0 always, <300 ms), I4 `render` -> lessons/rejected-ui.md.
Hit counters live in ~/.claude/state/lessons-hits.json (records stay git-quiet).
"""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import glob
import json
import os
import re
import sys
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))
import _paths  # noqa: E402  (hooks/_paths.py)

ROOT = Path(__file__).resolve().parent.parent
LESSONS = Path(os.environ.get("LESSONS_DIR") or ROOT / "lessons")
STATE = Path(os.environ.get("LESSON_STATE_DIR") or _paths.data_dir("state"))
_LOCAL = _paths.private("lessons", {})   # owner-only: project memory dir + title (private/lessons.json); absent = off
_MEM_DIR = os.environ.get("MEMORY_DIR") or (os.path.expanduser(_LOCAL["memory_dir"]) if _LOCAL.get("memory_dir") else "")
MEMORY = Path(_MEM_DIR) if _MEM_DIR else None
SPECIAL = {"INDEX.md", "rejected-ui.md"}
UI_SURFACES = {"landing", "crm-table", "crm-form", "ui", "design", "mockup", "visual-qa"}
ROLE_UI = {"design-judge", "design-critic", "slop-detector", "ui-qa", "product-reviewer", "marketing-reviewer"}
REVIEW_DAYS = 75
MEMORY_LIMIT = 6000
RECENT_DAYS = 14
HOOK_MAX = 100
PINNED = set(_paths.private("lessons", {}).get("pinned_memory", []))   # owner-only (private/lessons.json)


# ---------- records ----------
def _val(raw: str):
    raw = raw.strip()
    if raw[:1] in '"[{' or re.fullmatch(r"-?\d+|true|false|null", raw):
        try:
            return json.loads(raw)
        except ValueError:
            pass
    return raw


def parse(text: str) -> tuple[dict, str]:
    m = re.match(r"---\n(.*?)\n---\n?(.*)", text, re.S)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).split("\n"):
        k, sep, v = line.partition(":")
        if sep and k.strip():
            fm[k.strip()] = _val(v)
    return fm, m.group(2)


def dump(fm: dict, body: str = "") -> str:
    lines = [f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in fm.items()]
    return "---\n" + "\n".join(lines) + "\n---\n" + body.strip() + "\n"


def load_all(active_only: bool = False) -> list[dict]:
    out = []
    for p in sorted(LESSONS.glob("*.md")):
        if p.name in SPECIAL:
            continue
        try:
            fm, body = parse(p.read_text(encoding="utf-8"))
        except OSError:
            continue
        if not fm.get("id"):
            continue
        fm["_path"], fm["_body"] = p, body
        if not active_only or fm.get("status") == "active":
            out.append(fm)
    return out


def save(rec: dict) -> None:
    fm = {k: v for k, v in rec.items() if not k.startswith("_")}
    rec["_path"].write_text(dump(fm, rec.get("_body", "")), encoding="utf-8")


def hits_state() -> dict:
    try:
        return json.loads((STATE / "lessons-hits.json").read_text())
    except (OSError, ValueError):
        return {}


def total_hits(rec: dict, state: dict) -> int:
    return int(rec.get("hits") or 0) + int(state.get(rec["id"], 0))


# ---------- inject (I3) ----------
def repo_name(cwd: str) -> str:
    p = Path(cwd).resolve()
    for d in [p, *p.parents]:
        if (d / ".git").exists():
            return d.name
    return p.name


def matches(rec: dict, agent: str, paths: list[str], repo: str) -> bool:
    sc = rec.get("scope") or {}
    level = str(sc.get("level", "global"))
    if level.startswith("project:") and not repo.startswith(level.split(":", 1)[1]):
        return False
    rec_paths = sc.get("paths") or []
    if paths and rec_paths:
        return any(fnmatch.fnmatch(p, g) for p in paths for g in rec_paths)
    ui_rec = sc.get("surface") in UI_SURFACES
    if agent in ROLE_UI:
        return ui_rec
    if agent == "ui-builder":
        return True
    return not ui_rec


def one_line(rec: dict, with_wrong: bool = True) -> str:
    """`with_wrong=False` for subagent injection: the truncated «не так» tail cost ~1 KB per spawn (2026-11-26)."""
    right = re.sub(r"\s+", " ", str(rec.get("right", "")))[:170]
    wrong = re.sub(r"\s+", " ", str(rec.get("wrong", "")))[:70] if with_wrong else ""
    return f"- [{rec['id']}] {right}" + (f" (не так: {wrong})" if wrong else "")


def cmd_inject(a) -> int:
    try:
        repo = a.repo or repo_name(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
        paths = [p for p in (a.paths or "").split(",") if p]
        recs = [r for r in load_all(True) if matches(r, a.agent_type, paths, repo)]
        recs.sort(key=lambda r: (-int(r.get("rung") or 1), -int(r.get("repeats") or 0), r["id"]))
        recs = recs[: max(a.max_lines - 1, 0)]
        if recs:
            print("Owner lessons (active, highest rung first):")
            print("\n".join(one_line(r, with_wrong=False) for r in recs))
            bump_hits([r["id"] for r in recs])
    except Exception as e:  # inject must never break a spawn
        print(f"lessons inject failed open: {e}", file=sys.stderr)
    return 0


def bump_hits(ids: list[str]) -> None:
    try:
        st = hits_state()
        for i in ids:
            st[i] = int(st.get(i, 0)) + 1
        STATE.mkdir(parents=True, exist_ok=True)
        (STATE / "lessons-hits.json").write_text(json.dumps(st))
    except OSError:
        pass


# ---------- render (INDEX + I4) ----------
def cmd_render(_a) -> int:
    recs = load_all()
    act = [r for r in recs if r.get("status") == "active"]
    lines = ["# Lessons index (generated by tools/lessons.py render — do not edit)", "",
             f"Active: {len(act)} · archived: {len(recs) - len(act)}", "",
             "| id | rung | scope | check | right |", "|---|---|---|---|---|"]
    for r in sorted(act, key=lambda r: (-int(r.get("rung") or 1), r["id"])):
        sc, ck = r.get("scope") or {}, r.get("check") or {}
        lines.append(f"| [{r['id']}]({r['id']}.md) | {r.get('rung')} | {sc.get('level')}/{sc.get('surface')} "
                     f"| {ck.get('type')}{' ✔' if ck.get('proven') else ''} | {one_line(r).split('] ', 1)[1][:110]} |")
    (LESSONS / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    ui = [r for r in act if (r.get("scope") or {}).get("surface") in UI_SURFACES]
    out = ["# Rejected UI (generated — wrong/right pairs with the owner's words)", "",
           "Read by design-judge and slop-detector. Scope matters: landing taste != CRM table taste.", ""]
    for r in ui:
        sc = r.get("scope") or {}
        out += [f"## {r['id']} — {sc.get('level')} / {sc.get('surface')}", f"- Owner: {r.get('quote')}",
                f"- Wrong: {r.get('wrong')}", f"- Right: {r.get('right')}", f"- Why: {r.get('why')}",
                f"- Check: {(r.get('check') or {}).get('type')} ({(r.get('check') or {}).get('ref') or '-'})", ""]
    (LESSONS / "rejected-ui.md").write_text("\n".join(out), encoding="utf-8")
    print(f"INDEX.md: {len(act)} active; rejected-ui.md: {len(ui)} UI lessons")
    return 0


# ---------- check-repeat / stats / expire / new / repeat ----------
def tokens(text: str) -> set[str]:
    return {w[:5] for w in re.findall(r"\w{4,}", text.lower())}


def cmd_check_repeat(a) -> int:
    q, found = tokens(a.text), []
    for r in load_all(True):
        t = tokens(f"{r.get('quote', '')} {r.get('wrong', '')} {r.get('right', '')} {r['id'].replace('-', ' ')}")
        n = len(q & t)
        score = n / max(1, min(len(q), len(t)))
        if n >= 2 and score >= 0.34:
            found.append((score, r))
    for score, r in sorted(found, key=lambda x: -x[0])[:5]:
        print(f"{r['id']}\t{score:.2f}\t{str(r.get('quote', ''))[:80]}")
    return 0


def queue_total() -> int:
    qdir = Path(os.environ.get("LESSON_QUEUE_DIR") or STATE / "lesson-queue")
    n = 0
    for f in glob.glob(str(qdir / "*.jsonl")):
        try:
            n += sum(1 for ln in open(f, encoding="utf-8") if '"kind": "hit"' in ln or '"kind":"hit"' in ln)
        except OSError:
            pass
    return n


def cmd_stats(_a) -> int:
    recs, st = load_all(), hits_state()
    act = [r for r in recs if r.get("status") == "active"]
    reps, corr = sum(int(r.get("repeats") or 0) for r in recs), queue_total()
    rate = f"{reps / corr:.2f}" if corr else "n/a"
    print(f"active={len(act)} archived={len(recs) - len(act)} repeats={reps} corrections_in_queue={corr} "
          f"repeat_rate={rate} hits={sum(total_hits(r, st) for r in recs)}")
    return 0


def is_prose(rec: dict) -> bool:
    ck = rec.get("check") or {}
    return not (ck.get("proven") and ck.get("type") not in (None, "none"))


def cmd_expire(_a) -> int:
    today, st, out = dt.date.today().isoformat(), hits_state(), []
    for r in load_all(True):
        rb = r.get("review_by")
        if is_prose(r) and rb and str(rb) < today and total_hits(r, st) == 0:
            r["status"] = "archived"
            save(r)
            out.append(r["id"])
    print("archived: " + (", ".join(out) if out else "none"))
    return 0


def cmd_new(a) -> int:
    p = LESSONS / f"{a.id}.md"
    if p.exists():
        print(f"exists: {p}", file=sys.stderr)
        return 1
    today = dt.date.today()
    proven = a.check_type != "none" and a.proven
    fm = {"id": a.id, "quote": a.quote, "wrong": a.wrong, "right": a.right, "why": a.why,
          "scope": {"level": a.level, "surface": a.surface, "paths": [x for x in a.paths.split(",") if x]},
          "confidence": a.confidence, "rung": a.rung,
          "check": {"type": a.check_type, "ref": a.check_ref, "proven": proven},
          "status": "active", "supersedes": a.supersedes or None,
          "review_by": None if proven else (today + dt.timedelta(days=REVIEW_DAYS)).isoformat(),
          "hits": 0, "repeats": 0, "created": today.isoformat(), "source": a.source}
    LESSONS.mkdir(parents=True, exist_ok=True)
    p.write_text(dump(fm, a.body), encoding="utf-8")
    print(p)
    return 0


def cmd_repeat(a) -> int:
    for r in load_all():
        if r["id"] == a.id:
            r["repeats"] = int(r.get("repeats") or 0) + 1
            if not is_prose(r):
                r["review_by"] = None
            save(r)
            note = "" if int(r.get("rung") or 1) >= 4 else " -> raise rung to >=4 (detector/kit fix) or write the reason"
            print(f"{a.id}: repeats={r['repeats']} rung={r.get('rung')}{note}")
            return 0
    print(f"unknown lesson: {a.id}", file=sys.stderr)
    return 1


# ---------- memory-index (R6) ----------
ENTRY = re.compile(r"^- \[([^\]]+)\]\(([^)]+)\)(?:\s*[—–-]\s*(.*))?$")


def mem_meta(path: Path) -> dict:
    head = path.read_text(encoding="utf-8", errors="replace")[:3000]
    pick = lambda k: (re.search(rf"^\s*{k}:\s*(.*)$", head, re.M) or [None, ""])[1].strip().strip('"')
    typ = pick("type") or ("handoff" if path.name.startswith("handoff") else "")
    if re.search(r"^superseded_by:", head, re.M):
        typ = "feedback"  # migrated owner-preference file: lives in INDEX-FEEDBACK
    return {"type": typ, "name": pick("name") or path.stem, "desc": pick("description"), "mtime": path.stat().st_mtime}


def index_files(mem: Path) -> list[Path]:
    return [mem / "MEMORY.md", *sorted(mem.glob("INDEX-*.md"))]


def links_of(text: str) -> set[str]:
    out = {m for m in re.findall(r"\]\(([^)#\s]+)\)", text) if not m.startswith(("http", "~", "/"))}
    return out | {m + ".md" for m in re.findall(r"\[\[([^\]]+)\]\]", text)}


def mem_check(mem: Path) -> dict:
    top = {p.name for p in mem.glob("*.md")}
    reach, dangling = set(), []
    for ix in index_files(mem):
        if ix.exists():
            for tgt in links_of(ix.read_text(encoding="utf-8")):
                (reach.add(tgt) if (mem / tgt).exists() else dangling.append(f"{ix.name}->{tgt}"))
    idx = {p.name for p in index_files(mem)}
    mem_links = links_of((mem / "MEMORY.md").read_text(encoding="utf-8"))
    unreachable = sorted(top - reach - idx)
    unlinked_idx = sorted(n for n in idx - {"MEMORY.md"} if n not in mem_links)
    chars = len((mem / "MEMORY.md").read_text(encoding="utf-8"))
    return {"chars": chars, "dangling": dangling, "unreachable": unreachable, "unlinked_index": unlinked_idx,
            "ok": chars <= MEMORY_LIMIT and not dangling and not unreachable and not unlinked_idx}


def split_entries(mem: Path) -> tuple[list[str], list[tuple[str, str, str]]]:
    """Return (header lines, [(file, original line, title)]) of MEMORY.md."""
    ents, head = [], []
    for ln in (mem / "MEMORY.md").read_text(encoding="utf-8").split("\n"):
        m = ENTRY.match(ln)
        if m and (mem / m.group(2)).exists():
            ents.append((m.group(2), ln, m.group(1)))
        elif not ents and ln.strip():
            head.append(ln)
    return head, ents


def short(line: str) -> str:
    m = ENTRY.match(line)
    if not m:
        return line
    hook = m.group(3) or ""
    hook = hook if len(hook) <= HOOK_MAX else hook[: HOOK_MAX - 1].rstrip() + "…"
    return f"- [{m.group(1)}]({m.group(2)})" + (f" — {hook}" if hook else "")


def target_index(meta: dict) -> str:
    return {"feedback": "INDEX-FEEDBACK.md", "reference": "INDEX-REFERENCE.md"}.get(meta["type"], "INDEX-ARCHIVE.md")


def entry_line(mem: Path, name: str, meta: dict) -> str:
    return f"- [{meta['name']}]({name}) — {meta['desc'] or meta['type'] or 'note'}"


def append_section(path: Path, title: str, lines: list[str]) -> None:
    if lines:
        with path.open("a", encoding="utf-8") as f:
            f.write(f"\n## {title}\n" + "\n".join(lines) + "\n")


def mem_apply(mem: Path, today: dt.date) -> dict:
    head, ents = split_entries(mem)
    cutoff = dt.datetime.combine(today - dt.timedelta(days=RECENT_DAYS), dt.time()).timestamp()
    keep, moved = [], {}
    for name, line, _t in ents:
        meta = mem_meta(mem / name)
        stay = meta["type"] == "user" or name in PINNED or (meta["type"] not in ("feedback", "reference", "handoff") and meta["mtime"] >= cutoff)
        if name.startswith("INDEX-"):
            continue
        (keep.append((name, line, meta)) if stay else moved.setdefault(target_index(meta), []).append((name, line)))
    keep = trim_to_budget(mem, head, keep, moved)
    new = [short(ln) for _n, ln, _m in keep]
    write_memory(mem, new)
    for tgt, items in moved.items():
        known = links_of((mem / tgt).read_text(encoding="utf-8")) if (mem / tgt).exists() else set()
        append_section(mem / tgt, f"Moved from MEMORY.md {today.isoformat()}", [ln for n, ln in items if n not in known])
    add_unreachable(mem, today)
    return {"kept": len(keep), "moved": sum(len(v) for v in moved.values())}


def render_memory(mem: Path, entries: list[str]) -> str:
    ptrs = [f"[{p.stem[6:].lower()}]({p.name})" for p in sorted(mem.glob("INDEX-*.md"))]
    head = [f"# MEMORY index — {_LOCAL.get('memory_title', 'project')} (≤6000 chars; generated by `tools/lessons.py memory-index --apply`)",
            "Indexes: " + " · ".join(ptrs),
            "Owner lessons (preferences/rules, replaces feedback memories): ~/.claude/lessons/INDEX.md · rejected UI: ~/.claude/lessons/rejected-ui.md",
            ""]
    return "\n".join(head + entries) + "\n"


def write_memory(mem: Path, entries: list[str]) -> None:
    (mem / "MEMORY.md").write_text(render_memory(mem, entries), encoding="utf-8")


def trim_to_budget(mem: Path, head, keep, moved):
    keep = sorted(keep, key=lambda k: (k[2]["type"] != "user", k[2]["mtime"] * -1))
    while len(render_memory(mem, [short(k[1]) for k in keep])) > MEMORY_LIMIT:
        cand = [k for k in keep if k[2]["type"] != "user" and k[0] not in PINNED]
        if not cand:
            break
        last = min(cand, key=lambda k: k[2]["mtime"])
        keep.remove(last)
        moved.setdefault(target_index(last[2]), []).append((last[0], last[1]))
    return keep


def add_unreachable(mem: Path, today: dt.date) -> None:
    res = mem_check(mem)
    buckets: dict[str, list[str]] = {}
    for name in res["unreachable"]:
        meta = mem_meta(mem / name)
        buckets.setdefault(target_index(meta), []).append(entry_line(mem, name, meta))
    for tgt, lines in buckets.items():
        append_section(mem / tgt, f"Previously unindexed, added {today.isoformat()}", lines)


def cmd_memory_index(a) -> int:
    if not (a.memory_dir or MEMORY):
        print("memory-index: no memory dir (pass --memory-dir, set MEMORY_DIR or private/lessons.json)", file=sys.stderr)
        return 2
    mem = Path(a.memory_dir or MEMORY)
    if a.apply:
        print("applied:", mem_apply(mem, dt.date.today()))
    res = mem_check(mem)
    print(f"MEMORY.md chars={res['chars']} (limit {MEMORY_LIMIT}) dangling={len(res['dangling'])} "
          f"unreachable={len(res['unreachable'])} unlinked_index={len(res['unlinked_index'])}")
    for k in ("dangling", "unreachable", "unlinked_index"):
        for item in res[k][:20]:
            print(f"  {k}: {item}")
    return 0 if res["ok"] else 1


# ---------- CLI ----------
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="lessons.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("inject")
    i.add_argument("--agent-type", default="")
    i.add_argument("--paths", default="")
    i.add_argument("--max-lines", type=int, default=15)
    i.add_argument("--repo", default="")
    i.set_defaults(fn=cmd_inject)
    sub.add_parser("render").set_defaults(fn=cmd_render)
    c = sub.add_parser("check-repeat")
    c.add_argument("text")
    c.set_defaults(fn=cmd_check_repeat)
    sub.add_parser("stats").set_defaults(fn=cmd_stats)
    sub.add_parser("expire").set_defaults(fn=cmd_expire)
    r = sub.add_parser("repeat")
    r.add_argument("id")
    r.set_defaults(fn=cmd_repeat)
    n = sub.add_parser("new")
    n.add_argument("id")
    for f, d in (("quote", ""), ("wrong", ""), ("right", ""), ("why", ""), ("level", "global"), ("surface", "process"),
                 ("paths", ""), ("confidence", "remark"), ("check-type", "none"), ("check-ref", ""),
                 ("supersedes", ""), ("source", "chat"), ("body", "")):
        n.add_argument("--" + f, default=d)
    n.add_argument("--rung", type=int, default=2)
    n.add_argument("--proven", action="store_true")
    n.set_defaults(fn=cmd_new)
    m = sub.add_parser("memory-index")
    m.add_argument("--check", action="store_true")
    m.add_argument("--apply", action="store_true")
    m.add_argument("--memory-dir", default="")
    m.set_defaults(fn=cmd_memory_index)
    return ap


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
