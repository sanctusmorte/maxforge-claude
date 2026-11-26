#!/usr/bin/env python3
"""REQ status of a spec (interface I2): parses `## Requirements status` = `| REQ | status | evidence |`.

usage: req-status.py <spec.md> [--json]
status in todo|red|green|verified; `verified` is set only by the verifier agent.
exit 0 = every row verified, 1 = at least one row not verified, 2 = no table / unreadable file.
Importable: `parse(text)` -> rows, `summary(rows)` -> dict (used by stop-guard and precompact-handoff)."""
import json
import re
import sys

STATUSES = ("todo", "red", "green", "verified")
SECTION = re.compile(r"^##\s+Requirements status\s*$\n(.*?)(?=^##\s|\Z)", re.S | re.M)


def parse(text):
    """Rows [{req, status, evidence}] of the table, [] when the section or its rows are missing."""
    m = SECTION.search(text)
    if not m:
        return []
    rows = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2 or cells[0].lower() == "req" or set(cells[0]) <= set("-: "):
            continue
        status = cells[1].strip("`*_ ").lower()
        rows.append({"req": cells[0], "status": status if status in STATUSES else "todo",
                     "evidence": cells[2] if len(cells) > 2 else ""})
    return rows


def summary(rows):
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in STATUSES}
    return {"total": len(rows), "counts": counts, "open": [r["req"] for r in rows if r["status"] != "verified"]}


def main(argv):
    args = [a for a in argv if a != "--json"]
    if len(args) != 1:
        print("usage: req-status.py <spec.md> [--json]", file=sys.stderr)
        return 2
    try:
        with open(args[0], encoding="utf-8") as fh:
            rows = parse(fh.read())
    except OSError as exc:
        print(f"req-status: {exc}", file=sys.stderr)
        return 2
    if not rows:
        print(f"req-status: no `## Requirements status` table with rows in {args[0]}", file=sys.stderr)
        return 2
    s = summary(rows)
    if "--json" in argv:
        print(json.dumps({**s, "rows": rows}, ensure_ascii=False))
    else:
        c = s["counts"]
        print(f"{c['verified']}/{s['total']} verified · " + " · ".join(f"{k} {c[k]}" for k in STATUSES[:3])
              + (f" · open: {', '.join(s['open'])}" if s["open"] else ""))
    return 1 if s["open"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
