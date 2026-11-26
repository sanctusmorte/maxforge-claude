#!/usr/bin/env python3
"""Synthetic, isolated regression tests for token-audit.py."""

from __future__ import annotations

import base64
import importlib.util
import json
import subprocess
import sys
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).with_name("token-audit.py")
SPEC = importlib.util.spec_from_file_location("token_audit", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
AS_OF = "2026-10-10T12:00:00+00:00"


def png(width: int, height: int) -> str:
    data = b"\x89PNG\r\n\x1a\n" + b"\0" * 8 + struct.pack(">II", width, height) + b"\0" * 16
    return base64.b64encode(data).decode()


def write_transcript(root: Path, name: str, entries: list[dict]) -> None:
    transcript = root / "fixture-project" / f"{name}.jsonl"
    transcript.parent.mkdir(parents=True, exist_ok=True)
    transcript.write_text("\n".join(json.dumps(item) for item in entries) + "\n", encoding="utf-8")


def call_entry(model: str, usage: dict, call_id: str = "call", timestamp: str = AS_OF, stop_reason: str = "end_turn") -> dict:
    return {"type": "assistant", "timestamp": timestamp, "message": {"id": call_id, "model": model,
        "usage": usage, "stop_reason": stop_reason, "content": []}}


class TokenAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="token-audit-test-")
        self.root = Path(self.temp.name) / "projects"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def report(self, weighted: bool = False, days: int = 7) -> dict:
        return MODULE.audit(str(self.root), days, AS_OF, weighted)

    def test_import_is_safe_and_empty_root_has_zero_totals(self) -> None:
        with patch.object(MODULE.glob, "glob", side_effect=AssertionError("import scanned transcripts")):
            spec = importlib.util.spec_from_file_location("token_audit_import_check", SCRIPT)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        result = self.report()
        self.assertEqual(result["ncalls"], 0)
        self.assertEqual(result["W_total"], 0)
        self.assertEqual(result["cache_hit"], 0)
        self.assertEqual(result["totals"], {})
        self.assertIs(result["measurement"]["subscription_quota"], False)

    def test_sums_each_image_and_preserves_text_and_empty_results(self) -> None:
        timestamp = AS_OF
        entries = [
            {"type": "assistant", "timestamp": timestamp, "message": {"id": "a", "model": "claude-opus-5-5",
                "usage": {"input_tokens": 1, "output_tokens": 1}, "content": [
                    {"type": "tool_use", "id": "images", "name": "Read", "input": {}},
                    {"type": "tool_use", "id": "text", "name": "Read", "input": {}},
                    {"type": "tool_use", "id": "empty", "name": "Read", "input": {}}]}},
            {"type": "user", "timestamp": timestamp, "message": {"content": [
                {"type": "tool_result", "tool_use_id": "images", "content":[
                    {"type": "image", "source": {"data": png(100, 100)}},
                    {"type": "image", "source": {"data": png(200, 100)}}]},
                {"type": "tool_result", "tool_use_id": "text", "content":[
                    {"type": "text", "text": "abcdefghij"},
                    {"type": "image", "source": {"data": png(100, 100)}}]},
                {"type": "tool_result", "tool_use_id": "empty", "content": []}]}}]
        write_transcript(self.root, "images", entries)
        result = self.report()
        small, large = int(100 * 100 / 750), int(200 * 100 / 750)
        self.assertEqual(result["images"], [3, small * 2 + large])
        self.assertEqual(result["toolres"], [["Read(image)", 10, 2], ["Read", 0, 1]])

    def test_exact_and_dated_model_ids_and_rejects_future_unknowns(self) -> None:
        expected = {
            "claude-opus-5-5": "opus-5.5", "claude-opus-5-5-20261010": "opus-5.5",
            "CLAUDE-SONNET-5-5-20261010": "sonnet-5.5", "claude-opus-4.8": "opus-4.8",
            "claude-sonnet-4-6-20250929": "sonnet-4.6", "claude-sonnet-5": "sonnet-5",
        }
        for model, key in expected.items():
            with self.subTest(model=model):
                self.assertEqual(MODULE.parse_model(model), key)
        for model in ("claude-opus-6-0", "claude-sonnet-5-6", "claude-haiku-4-5", "fable", "claude-opus-5-5-future"):
            with self.subTest(model=model):
                self.assertIsNone(MODULE.parse_model(model))

    def test_known_and_unknown_prices_are_separate_and_totals_are_partial(self) -> None:
        known = call_entry("claude-opus-5-5", {"input_tokens": 1_000_000, "output_tokens": 0}, "known")
        unknown = call_entry("claude-opus-6-0", {"input_tokens": 500_000, "output_tokens": 9}, "unknown")
        write_transcript(self.root, "models", [known, unknown])
        result = self.report()
        self.assertEqual(result["W_total"], 4.0)
        self.assertEqual(result["measurement"]["unknown_model_calls"], 1)
        self.assertEqual(result["measurement"]["unknown_models"], {"claude-opus-6-0": 1})
        self.assertTrue(result["measurement"]["cost_totals_partial"])
        self.assertEqual(result["by_model"]["claude-opus-6-0"]["i"], 500_000)
        self.assertEqual(result["by_model"]["claude-opus-6-0"]["w"], 0)

    def test_cost_shares_are_normalized_for_sub_dollar_totals(self) -> None:
        write_transcript(self.root, "small", [call_entry("claude-opus-5-5", {
            "input_tokens": 1_000, "output_tokens": 0})])
        result = self.report()
        self.assertAlmostEqual(result["W_total"], 0.004)
        self.assertEqual(result["totals"]["all"]["share"], 100.0)
        self.assertEqual(result["by_day"]["2026-10-10"]["share"], 100.0)

    def test_older_verified_prices_and_mixed_cache_ttl(self) -> None:
        entries = [
            call_entry("claude-opus-4-6-20250514", {"input_tokens": 1_000_000, "output_tokens": 0,
                "cache_creation_input_tokens": 2_000_000,
                "cache_creation": {"ephemeral_5m_input_tokens": 1_000_000, "ephemeral_1h_input_tokens": 1_000_000}}, "old-opus"),
            call_entry("claude-sonnet-4-5", {"input_tokens": 1_000_000, "output_tokens": 0,
                "cache_creation_input_tokens": 2_000_000,
                "cache_creation": {"ephemeral_5m_input_tokens": 1_000_000, "ephemeral_1h_input_tokens": 1_000_000}}, "old-sonnet"),
        ]
        write_transcript(self.root, "ttl", entries)
        result = self.report()
        self.assertAlmostEqual(result["W_total"], 34.0)
        self.assertEqual(result["cw_1h_share"], 0.5)
        self.assertEqual(result["measurement"]["ttl_assumptions"], {})

    def test_missing_ttl_uses_legacy_five_minute_assumption_and_weighted_mode(self) -> None:
        write_transcript(self.root, "missing-ttl", [call_entry("claude-opus-5-5", {
            "input_tokens": 1_000_000, "output_tokens": 0, "cache_creation_input_tokens": 2_000_000})])
        result = self.report(weighted=True)
        self.assertEqual(result["W_total"], 17_500_000)
        self.assertEqual(result["measurement"]["kind"], "heuristic-weight-units")
        self.assertEqual(result["measurement"]["ttl_assumptions"], {
            "ttl_missing_assumed_5m_calls": 1,
            "ttl_missing_assumed_5m_tokens": 2_000_000,
        })

    def test_cache_ttl_partial_remainder_is_counted_and_inconsistent_breakdown_is_visible(self) -> None:
        write_transcript(self.root, "ttl-mismatch", [
            call_entry("claude-opus-5-5", {"input_tokens": 0, "output_tokens": 0,
                "cache_creation_input_tokens": 2_000_000,
                "cache_creation": {"ephemeral_5m_input_tokens": 500_000, "ephemeral_1h_input_tokens": 500_000}}, "partial"),
            call_entry("claude-opus-5-5", {"input_tokens": 0, "output_tokens": 0,
                "cache_creation_input_tokens": 1_500_000,
                "cache_creation": {"ephemeral_5m_input_tokens": 1_000_000, "ephemeral_1h_input_tokens": 1_000_000}}, "excess"),
            call_entry("claude-opus-5-5", {"input_tokens": 1, "output_tokens": 0,
                "cache_creation_input_tokens": 0}, "zero"),
        ])
        result = self.report()
        self.assertAlmostEqual(result["W_total"], 24.500004)
        self.assertEqual(result["measurement"]["ttl_assumptions"], {
            "ttl_partial_remainder_assumed_5m_calls": 1,
            "ttl_partial_remainder_assumed_5m_tokens": 1_000_000,
            "ttl_breakdown_exceeds_total_calls": 1,
            "ttl_breakdown_exceeds_total_tokens": 500_000,
        })

    def test_days_and_as_of_filter_use_utc_boundaries_and_exclude_future_calls(self) -> None:
        cutoff = "2026-10-09T12:00:00Z"
        write_transcript(self.root, "dated", [
            call_entry("claude-opus-5-5", {"input_tokens": 10, "output_tokens": 1}, "boundary", cutoff),
            call_entry("claude-opus-5-5", {"input_tokens": 10, "output_tokens": 1}, "as-of", AS_OF),
            call_entry("claude-opus-5-5", {"input_tokens": 10, "output_tokens": 1}, "offset", "2026-10-10T14:00:00+02:00"),
            call_entry("claude-opus-5-5", {"input_tokens": 100, "output_tokens": 1}, "future", "2026-10-10T12:00:00.000001Z"),
            call_entry("claude-opus-5-5", {"input_tokens": 100, "output_tokens": 1}, "malformed", "not-a-date"),
        ])
        result = self.report(days=1)
        self.assertEqual(result["ncalls"], 3)
        self.assertEqual(set(result["by_day"]), {"2026-10-09", "2026-10-10"})
        self.assertEqual(result["measurement"]["invalid_timestamp_entries"], 1)

    def test_cli_reports_malformed_as_of_as_argument_error(self) -> None:
        output = Path(self.temp.name) / "invalid.json"
        command = [sys.executable, "-B", str(SCRIPT), str(output), "--root", str(self.root),
            "--as-of", "not-a-date"]
        completed = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 2)
        self.assertIn("invalid ISO 8601 timestamp", completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)

    def test_weighted_legacy_imputed_fields_keep_million_unit_scale(self) -> None:
        write_transcript(self.root, "weighted", [call_entry("claude-opus-5-5", {
            "input_tokens": 1_000_000, "output_tokens": 0,
            "cache_creation_input_tokens": 2_000_000})])
        result = self.report(weighted=True)
        self.assertEqual(result["imputed"]["usd_main"], 17.5)
        self.assertEqual(result["measurement"]["kind"], "heuristic-weight-units")

    def test_rebuild_filter_keeps_legacy_call_index_semantics(self) -> None:
        usage = {"input_tokens": 0, "output_tokens": 1,
            "cache_creation_input_tokens": 30_000,
            "cache_creation": {"ephemeral_5m_input_tokens": 30_000}}
        write_transcript(self.root, "rebuild", [
            call_entry("claude-opus-5-5", usage, "first"),
            call_entry("claude-opus-5-5", usage, "second"),
        ])
        result = self.report()
        self.assertEqual(sum(group["n"] for group in result["rebuilds"].values()), 1)

    def test_cli_uses_only_the_explicit_synthetic_root(self) -> None:
        output = Path(self.temp.name) / "report.json"
        command = [sys.executable, "-B", str(SCRIPT), str(output), "--root", str(self.root),
            "--days", "1", "--as-of", AS_OF]
        completed = subprocess.run(command, capture_output=True, text=True, check=True)
        self.assertEqual(completed.stdout.strip(), "ok 0 0")
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["W_total"], 0)


if __name__ == "__main__":
    unittest.main()
