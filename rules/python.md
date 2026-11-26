---
paths:
  - "**/*.py"
  - "**/pyproject.toml"
  - "**/requirements*.txt"
  - "**/pytest.ini"
---
# Python — senior code rules (Sept 2026; trading/ML/research repos)

Version-gate by `pyproject.toml` / `.python-version` (3.10–3.12 in this workspace). Never change the
interpreter or add heavy deps as a side effect.

## Tooling
- `uv` for envs/locks where the repo uses it; otherwise the repo's `.venv` + `requirements*.txt`
  (never install into system Python). One lockfile, committed.
- `ruff` (lint + format, `ruff check --fix` / `ruff format`), `mypy --strict` (or the repo's level;
  never lower it), `pytest` with `-q`, `pytest-xdist` for parallel, `hypothesis` for pure logic.
  Pre-PR gate: `ruff check`, `ruff format --check`, `mypy`, `pytest` on affected modules (wider on
  doubt), and the repo's own `make`/`tox` targets if present.

## Code
- Type hints everywhere (`from __future__ import annotations`), `dataclass(frozen=True, slots=True)`
  or `pydantic` models for data crossing boundaries; no bare `dict` payloads across modules.
- Small pure functions for logic; I/O at the edges; explicit exceptions (custom classes, never
  `except Exception: pass`); `logging` with structured context, no `print` in library code.
- Money/prices as `Decimal` (or integer minor units), timezone-aware UTC datetimes, explicit
  rounding modes. Never float for money.
- Deterministic by construction: seed randomness, inject clocks, freeze time in tests
  (`freezegun`), fixture data versioned and small.
- Scripts are entry points only (`if __name__ == "__main__": main()`), logic lives in the package;
  CLI via `argparse`/`typer`; config via env/`pydantic-settings`, never hard-coded credentials.
- Data pipelines: idempotent, resumable (checkpoints/bookkeeping tables), rate-limited against
  external sources (source limits ≠ parallelism ban), raw data immutable + derived data
  reproducible; every empirical claim in docs carries the verification date.

## Tests
- `tests/` mirrors package layout; unit for pure logic, integration for DB/API with fakes for the
  network (`responses`/`respx`/VCR cassettes), property tests for parsers/pricing/rounding.
- Coverage floor 80 % on new code; one reason to fail per test; no sleeps; parallel-safe (own temp
  dirs/DB names via `TEST_DB=<project>_test_<task>`).
- ML/research: pin dataset snapshots + seeds; assert metric ranges, not exact floats; keep
  backtests reproducible (config file committed, results with commit sha).
