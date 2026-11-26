---
name: lesson
description: Record an owner correction or standing preference as a lesson (wrong/right/why/scope/check), raise its rung on repeats. Use on the lesson-capture hook's "Possible owner correction", on «не так / опять / я же говорил / убери / некрасиво», or «запомни».
argument-hint: [owner words]
---
# /lesson — capture → record → ladder → check

Store: `~/.claude/lessons/<id>.md`; tool: `python3 ~/.claude/tools/lessons.py` (`check-repeat`, `new`, `repeat`, `render`, `stats`, `expire`).

1. **Restate** in one line: wrong (what I did) → right (what he wants). Keep his words verbatim (RU) as `quote`.
   Not a standing preference (one-off task detail) → say so in one line and stop; no record.
2. **Dedupe**: `lessons.py check-repeat "<his words + wrong/right>"`.
   - Candidate id → it is a **repeat**: `lessons.py repeat <id>`. Second identical correction → rung ≥4 (detector/hook/kit fix)
     now, or write in the reply why a detector is impossible. Never answer a repeat with another memory line.
   - No candidate → `lessons.py new <id> --quote … --wrong … --right … --why … --level … --surface … --rung … --check-type …`.
3. **Scope** (`level` global|project:<repo>, `surface` landing|crm-table|crm-form|ui|mockup|code|process|ops|deploy|test|content,
   `--paths` globs). Ask the owner ONE question only when global vs a single surface is genuinely ambiguous
   (landing taste ≠ CRM table taste); otherwise decide and state it in the reply.
4. **Rung** (1 note 30 d · 2 memory · 3 rule/pack line · 4 detector · 5 kit fix). Convert UI complaints:
   - measurable (gap, size, contrast, clipping, distance) → request a design-lint / ui-qa rule with a bad+good fixture (`check.type: ui-qa|design-lint`);
   - component defect → kit fix + baseline snapshot (rung 5);
   - taste → before/after pair into the TRAIN anchors only (never the held-out calibration set);
   - process → a hook that checks the artefact (`check.type: hook`) or an ESLint/PHPStan rule.
   `check.proven: true` only after the detector FAILS on the wrong fixture and PASSES on the right one; then `review_by` = none.
5. **Apply the rule edit immediately** (rule/pack line, detector request) and show the diff in the same reply (git = rollback).
6. `lessons.py render` (refreshes `lessons/INDEX.md` + `rejected-ui.md`), commit the record with the edit.
7. **Reply line**: `Записал урок <id> (ступень N, <scope>) — проверка: <check type/ref или «нет, проза до <review_by>».` + the diff.

Memory vs lessons: preferences/rules go here, never into `MEMORY.md`; facts (servers, projects, recipes) stay in memory.
