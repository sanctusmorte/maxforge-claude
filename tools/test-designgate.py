#!/usr/bin/env python3
"""Design gate (hooks/guard-bash.py): State matrix rule for scorecards dated >= 2026-11-25 (I11); older ones keep the
old behaviour. Standalone, paths relative to this repo root; exit 0 = pass."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, "hooks", "guard-bash.py")
STATES = ["loading", "first-use empty", "no results", "error", "partial data", "no permission",
          "disabled+reason", "long text", "1000 rows"]


def matrix(empty=(), rows=STATES):
    out = ["## State matrix", "| state | screenshot | verdict | n/a reason |", "|---|---|---|---|"]
    for s in rows:
        if s in empty:
            out.append(f"| {s} | <path> | pass \\| fail | <reason> |")  # untouched template row
        elif s == "error":
            out.append(f"| {s} | | n/a | no error path on this screen |")
        else:
            out.append(f"| {s} | states/{s.replace(' ', '-')}.png | pass | |")
    return "\n".join(out) + "\n"


def card(date, body=""):
    return f"# Design Scorecard — x — {date} — abc1234\nVerdict: PASS\n\n## Scorecard\n| a | b |\n\n{body}\n## Fix list\n"


fx = tempfile.mkdtemp(prefix="dg-")


def g(*a):
    subprocess.run(["git", *a], cwd=fx, check=True, capture_output=True)


g("init", "-q", "-b", "dev"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
open(os.path.join(fx, "a.php"), "w").write("<?php\n"); g("add", "."); g("commit", "-qm", "base")
g("update-ref", "refs/remotes/origin/dev", "HEAD"); g("checkout", "-qb", "feat")
os.makedirs(os.path.join(fx, "src")); open(os.path.join(fx, "src", "X.vue"), "w").write("<template/>\n")
g("add", "."); g("commit", "-qm", "ui")
sc_dir = os.path.join(fx, "artifacts", "ui-qa", "x"); os.makedirs(sc_dir)
sc = os.path.join(sc_dir, "scorecard.md")


def clicks(rows):
    rep_dir = os.path.join(sc_dir, "dead-clicks")
    shutil.rmtree(rep_dir, ignore_errors=True)
    if rows is not None:
        os.makedirs(rep_dir)
        json.dump(rows, open(os.path.join(rep_dir, "report.json"), "w"))


def geometry(report, age=0):
    rep_dir = os.path.join(sc_dir, "geometry")
    shutil.rmtree(rep_dir, ignore_errors=True)
    if report is not None:
        os.makedirs(rep_dir)
        path = os.path.join(rep_dir, "report.json")
        json.dump(report, open(path, "w"))
        t = time.time() - age
        os.utime(path, (t, t))


CLEAN_GEO = {"version": 1, "summary": {"errors": 0, "warnings": 3}}
BAD_GEO = {"version": 1, "summary": {"errors": 2, "warnings": 0}}
LIVE = [{"verdict": "NAVIGATED", "text": "Open"}, {"verdict": "OVERLAY", "text": "Menu"}]
DEAD = LIVE + [{"verdict": "NO_EFFECT", "text": "Экспорт"}]
ALLOWED = LIVE + [{"verdict": "NO_EFFECT", "text": "Logo", "allowed": "decorative"}]


def gate(text, rows=LIVE, geo="clean", geo_age=0):
    clicks(rows)
    geometry(CLEAN_GEO if geo == "clean" else (BAD_GEO if geo == "bad" else None), geo_age)
    open(sc, "w").write(text)
    r = subprocess.run(["python3", HOOK], input=json.dumps({"cwd": fx, "tool_input": {
        "command": "gh pr create --base dev --title x --body y"}}), capture_output=True, text=True, timeout=30)
    out = r.stdout.strip()
    return ('"deny"' in out), (json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"] if out else "")


CASES = [  # label, scorecard, expect_deny, substrings the message must contain
    ("old scorecard (2026-10-01), no matrix", card("2026-10-01"), False, []),
    ("undated legacy scorecard, no matrix", "# S\nVerdict: PASS\n", False, []),
    ("new scorecard, full matrix (n/a reason counts)", card("2026-11-25", matrix()), False, []),
    ("new scorecard, no matrix at all", card("2026-11-26"), True, ["loading", "1000 rows"]),
    ("new scorecard, two template rows", card("2026-11-25", matrix(empty=("loading", "long text"))), True,
     ["loading", "long text", "State matrix"]),
    ("new scorecard, a row missing", card("2026-12-01", matrix(rows=STATES[:-1])), True, ["1000 rows"]),
    ("new FIX scorecard is still FIX", card("2026-11-25", matrix()).replace("PASS", "FIX"), True, ["Verdict"]),
    # interaction rule (every PASS scorecard): dead-clicks/report.json next to the scorecard
    ("scorecard dated 11-26, no report → gated too", card("2026-11-26", matrix()), True, ["no dead-clicks"], None),
    ("legacy undated scorecard, no report → gated too", "# S\nVerdict: PASS\n", True, ["no dead-clicks"], None),
    ("interaction: live controls only", card("2026-11-27", matrix()), False, [], LIVE),
    ("interaction: dead control allowlisted", card("2026-11-27", matrix()), False, [], ALLOWED),
    ("interaction: no report", card("2026-11-27", matrix()), True, ["no dead-clicks/report.json"], None),
    ("interaction: one NO_EFFECT", card("2026-11-27", matrix()), True, ["1 control", "Экспорт"], DEAD),
    ("interaction: report with 0 controls", card("2026-11-27", matrix()), True, ["0 controls"], []),
    ("interaction: n/a with reason", card("2026-11-28", matrix() + "Interaction: n/a — copy-only change\n"),
     False, [], None),
    ("interaction: n/a without reason", card("2026-11-28", matrix() + "Interaction: n/a\n"), True,
     ["no dead-clicks"], None),
    # geometry rule (every PASS scorecard): geometry/report.json fresh with 0 errors, or `Geometry: n/a — reason`
    ("geometry: fresh clean report", card("2026-11-28", matrix()), False, [], LIVE, "clean"),
    ("geometry: report missing", card("2026-11-28", matrix()), True, ["no geometry/report.json"], LIVE, "none"),
    ("geometry: report stale", card("2026-11-28", matrix()), True, ["geometry/report.json is older"], LIVE, "clean", 86400 * 30),
    ("geometry: errors > 0", card("2026-11-28", matrix()), True, ["geometry: 2 error(s)"], LIVE, "bad"),
    ("geometry: n/a with reason", card("2026-11-28", matrix() + "Geometry: n/a — no rendered UI change\n"),
     False, [], LIVE, "none"),
    ("geometry: n/a without reason", card("2026-11-28", matrix() + "Geometry: n/a\n"), True,
     ["no geometry/report.json"], LIVE, "none"),
]
fails = 0
for label, text, expect, needles, *rows in CASES:
    denied, msg = gate(text, *rows)
    ok = denied == expect and all(n in msg for n in needles)
    # message for a missing matrix must NOT list rows that are filled
    if label.startswith("new scorecard, two template") and ("no results" in msg.split("empty rows:")[-1].split("—")[0]):
        ok = False
    fails += 0 if ok else 1
    print(f"{'OK ' if ok else 'BAD'} {label:<48} → {'deny' if denied else 'allow'}" + ("" if ok else f"  [{msg[:160]}]"))
shutil.rmtree(fx, ignore_errors=True)
sys.exit(1 if fails else 0)
