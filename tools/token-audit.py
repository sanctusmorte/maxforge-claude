#!/usr/bin/env python3
"""Estimate API list-price cost and token usage from Claude Code JSONL transcripts."""

from __future__ import annotations

import argparse
import base64
import bisect
import collections
import datetime as dt
import glob
import json
import os
import re
import statistics
import struct
import sys

PRICING_SOURCE = "https://platform.claude.com/docs/en/about-claude/pricing"
PRICING_DATE = "2026-10-10"
QUOTA_SOURCE = "https://code.claude.com/docs/en/costs"
PRICES = {
    "opus-5.5": (4, 20, 5, 8, 0.20),
    "sonnet-5.5": (2, 10, 2.5, 4, 0.10),
    "opus-5": (5, 25, 6.25, 10, 0.50),
    "opus-4.5": (5, 25, 6.25, 10, 0.50),
    "opus-4.6": (5, 25, 6.25, 10, 0.50),
    "opus-4.7": (5, 25, 6.25, 10, 0.50),
    "opus-4.8": (5, 25, 6.25, 10, 0.50),
    "sonnet-5": (2, 10, 2.5, 4, 0.20),
    "sonnet-4.5": (3, 15, 3.75, 6, 0.30),
    "sonnet-4.6": (3, 15, 3.75, 6, 0.30),
}
MODEL_ID = re.compile(r"^claude-(opus|sonnet)-(\d+)-(\d+)(?:-(\d{8}))?$")
SINGLE_VERSION_ID = re.compile(r"^claude-(opus|sonnet)-(5)(?:-(\d{8}))?$")
CPT = 2.2


def parse_model(model: str) -> str | None:
    """Return an exact supported model key; dated IDs use that model's published price."""
    normalized = model.strip().lower().replace(".", "-")
    single = SINGLE_VERSION_ID.fullmatch(normalized)
    if single:
        family, major, _date = single.groups()
        key = f"{family}-{major}"
        return key if key in PRICES else None
    match = MODEL_ID.fullmatch(normalized)
    if not match:
        return None
    family, major, minor, _date = match.groups()
    key = f"{family}-{major}.{minor}"
    return key if key in PRICES else None


def parse_aware_datetime(value: str) -> dt.datetime:
    """Parse an ISO 8601 timestamp and return UTC, rejecting timezone-naive values."""
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO 8601 string")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"invalid ISO 8601 timestamp: {value!r}") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


def audit(root: str, days: int, as_of: str, weighted: bool) -> dict:
    """Read transcripts under root and return a JSON-serializable report."""
    root = os.path.abspath(os.path.expanduser(root))
    now = parse_aware_datetime(as_of)
    cut_dt = now - dt.timedelta(days=days)
    CUT = cut_dt.isoformat().replace("+00:00", "Z")

    def mf(model: str) -> int:
        return 3 if "sonnet" in model.lower() else 1 if "haiku" in model.lower() else 5

    def rates(model: str, ctx: int = 0) -> tuple[float, float, float, float, float]:
        if weighted:
            factor = mf(model)
            return (factor, 5 * factor, 1.25 * factor, 2 * factor, 0.1 * factor)
        key = parse_model(model)
        return PRICES[key] if key else (0, 0, 0, 0, 0)

    def wcost(usage: dict, model: str) -> tuple[float, int, int, dict[str, int]]:
        cache = usage.get("cache_creation") or {}
        raw_5m = cache.get("ephemeral_5m_input_tokens")
        raw_1h = cache.get("ephemeral_1h_input_tokens")
        has_breakdown = raw_5m is not None or raw_1h is not None
        c5, c1 = raw_5m or 0, raw_1h or 0
        ttl_info: dict[str, int] = {}
        has_total = "cache_creation_input_tokens" in usage
        total_cache = usage.get("cache_creation_input_tokens", 0) or 0
        if not has_breakdown:
            c5, c1 = total_cache, 0
            if total_cache > 0:
                ttl_info["ttl_missing_assumed_5m_calls"] = 1
                ttl_info["ttl_missing_assumed_5m_tokens"] = total_cache
        elif has_total and c5 + c1 < total_cache:
            remainder = total_cache - c5 - c1
            c5 += remainder
            ttl_info["ttl_partial_remainder_assumed_5m_calls"] = 1
            ttl_info["ttl_partial_remainder_assumed_5m_tokens"] = remainder
        elif has_total and c5 + c1 > total_cache:
            ttl_info["ttl_breakdown_exceeds_total_calls"] = 1
            ttl_info["ttl_breakdown_exceeds_total_tokens"] = c5 + c1 - total_cache
        c5, c1 = c5 or 0, c1 or 0
        input_tokens = usage.get("input_tokens", 0) or 0
        cache_read = usage.get("cache_read_input_tokens", 0) or 0
        price = rates(model, input_tokens + cache_read + c5 + c1)
        divisor = 1 if weighted else 1_000_000
        output_tokens = usage.get("output_tokens", 0) or 0
        cost = (price[0] * input_tokens + price[2] * c5 + price[3] * c1
                + price[4] * cache_read + price[1] * output_tokens) / divisor
        return cost, c5, c1, ttl_info

    def pctl(values: list, percentile: float):
        if not values:
            return 0
        values = sorted(values)
        return values[min(len(values) - 1, int(percentile * len(values)))]

    files = []
    for file_path in glob.glob(root + "/*/*.jsonl"):
        files.append((file_path, False))
    for file_path in glob.glob(root + "/*/*/subagents/*.jsonl"):
        files.append((file_path, True))
    files = sorted(files)

    calls = []
    seen_messages, seen_tool_uses, duplicates = set(), set(), collections.Counter()
    transcripts = []
    tool_results = collections.defaultdict(lambda: [0, 0])
    biggest = []
    reread, reread_chars = collections.Counter(), collections.Counter()
    images = [0, 0]
    agent_spawn_types = collections.Counter()
    carry = collections.defaultdict(lambda: collections.Counter())
    img_by, img_tok_by, bash_by = collections.Counter(), collections.Counter(), collections.Counter()
    ttl_assumptions = collections.Counter()
    unknown_models = collections.Counter()
    invalid_timestamp_entries = 0

    def image_tokens(block: dict) -> int:
        try:
            raw = base64.b64decode(block["source"]["data"][:64])
            if raw[:4] == b"\x89PNG":
                width, height = struct.unpack(">II", raw[16:24])
            else:
                return 1600
            scale = min(1.0, (1568 * 1568 / (width * height)) ** .5, 1568 / max(width, height)) if width * height else 1
            return int(width * scale * height * scale / 750)
        except (KeyError, TypeError, ValueError, struct.error):
            return 1600

    thinking_chars = text_chars = tooluse_chars = 0

    for file_path, is_subagent in files:
        project = file_path[len(root) + 1:].split("/")[0]
        metadata = {}
        if is_subagent:
            try:
                with open(file_path[:-6] + ".meta.json", encoding="utf-8") as metadata_file:
                    metadata = json.load(metadata_file)
            except (OSError, json.JSONDecodeError):
                pass
        agent_type = metadata.get("agentType", "unknown-sub") if is_subagent else "main"
        session = file_path.split("/")[-3] if is_subagent else os.path.basename(file_path)[:-6]
        messages = collections.OrderedDict()
        tool_uses = {}
        reads, read_sizes, pending = collections.Counter(), collections.Counter(), []
        try:
            transcript_file = open(file_path, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with transcript_file:
            for line in transcript_file:
                if '"assistant"' not in line and '"tool_result"' not in line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                timestamp = entry.get("timestamp", "")
                try:
                    timestamp_dt = parse_aware_datetime(timestamp)
                except ValueError:
                    invalid_timestamp_entries += 1
                    continue
                if timestamp_dt < cut_dt or timestamp_dt > now:
                    continue
                timestamp = timestamp_dt.isoformat().replace("+00:00", "Z")
                message = entry.get("message")
                if not isinstance(message, dict):
                    continue
                entry_type = entry.get("type")
                if entry_type == "assistant":
                    if not is_subagent and entry.get("isSidechain"):
                        continue
                    if agent_type.startswith("unknown") and entry.get("attributionAgent"):
                        agent_type = entry["attributionAgent"]
                    message_id = message.get("id") or entry.get("requestId") or entry.get("uuid")
                    usage = message.get("usage") or {}
                    model = message.get("model", "")
                    if model == "<synthetic>" or not usage:
                        pass
                    elif message_id in seen_messages and message_id not in messages:
                        duplicates["msg"] += 1
                    elif message_id not in messages:
                        seen_messages.add(message_id)
                        messages[message_id] = dict(u=usage, m=model, ts=timestamp,
                            out=usage.get("output_tokens", 0) or 0, sr=message.get("stop_reason"),
                            eff=entry.get("effort"), txt=0, tuc=0, ntu=0, nth=0, tt=None)
                    else:
                        messages[message_id]["out"] = max(messages[message_id]["out"], usage.get("output_tokens", 0) or 0)
                        messages[message_id]["u"] = usage
                        messages[message_id]["sr"] = message.get("stop_reason") or messages[message_id]["sr"]
                    current = messages.get(message_id)
                    if current is not None:
                        thinking = (usage.get("output_tokens_details") or {}).get("thinking_tokens")
                        if thinking is not None:
                            current["tt"] = thinking
                    for block in message.get("content") or []:
                        if not isinstance(block, dict):
                            continue
                        block_type = block.get("type")
                        if block_type == "thinking":
                            thinking_chars += len(block.get("thinking", ""))
                            if current is not None:
                                current["nth"] += 1
                        elif block_type == "text":
                            text_chars += len(block.get("text", ""))
                            if current is not None:
                                current["txt"] += len(block.get("text", ""))
                        elif block_type == "tool_use":
                            tool_input = block.get("input") or {}
                            serialized = json.dumps(tool_input, ensure_ascii=False)
                            tooluse_chars += len(serialized)
                            if current is not None:
                                current["tuc"] += len(serialized)
                                current["ntu"] += 1
                            tool_name = block.get("name", "?")
                            argument = (tool_input.get("file_path") or tool_input.get("command") or tool_input.get("url")
                                        or tool_input.get("pattern") or tool_input.get("description") or tool_input.get("query") or "")
                            tool_uses[block.get("id")] = (tool_name, str(argument)[:120], tool_input)
                            if tool_name in ("Agent", "Task"):
                                agent_spawn_types[tool_input.get("subagent_type", "general-purpose")] += 1
                elif entry_type == "user":
                    content = message.get("content")
                    if not isinstance(content, list):
                        continue
                    for block in content:
                        if not isinstance(block, dict) or block.get("type") != "tool_result":
                            continue
                        tool_use_id = block.get("tool_use_id")
                        if tool_use_id in seen_tool_uses:
                            duplicates["tr"] += 1
                            continue
                        seen_tool_uses.add(tool_use_id)
                        tool_name, argument, tool_input = tool_uses.get(tool_use_id, ("?", "", {}))
                        result = block.get("content")
                        char_count = 0
                        image_count = image_total = 0
                        if isinstance(result, str):
                            char_count = len(result)
                        elif isinstance(result, list):
                            for item in result:
                                if isinstance(item, dict):
                                    if item.get("type") == "text":
                                        char_count += len(item.get("text", ""))
                                    elif item.get("type") == "image":
                                        image_count += 1
                                        image_total += image_tokens(item)
                        label = tool_name
                        if tool_name.startswith("mcp__"):
                            label = "mcp:" + tool_name.split("__")[1]
                        token_estimate = char_count / CPT
                        if image_count:
                            images[0] += image_count
                            images[1] += image_total
                            label = tool_name + "(image)"
                            token_estimate += image_total
                            img_by[(agent_type, os.path.dirname(argument)[-50:])] += image_count
                            img_tok_by[agent_type] += image_total
                        pending.append((timestamp, label, token_estimate, agent_type))
                        if tool_name == "Bash":
                            bash_by[(argument.split()[0] if argument.split() else "")[:30]] += char_count
                        tool_results[label][0] += char_count
                        tool_results[label][1] += 1
                        if char_count > 20000:
                            biggest.append((char_count, tool_name, argument, agent_type, session[:8], project[-25:]))
                        if tool_name == "Read":
                            file_name = tool_input.get("file_path", "")
                            key = (file_name, tool_input.get("offset"), tool_input.get("limit"))
                            reads[key] += 1
                            read_sizes[key] += char_count
        for key, count in reads.items():
            if count > 1:
                reread[(key[0], agent_type, session[:8])] += count - 1
                reread_chars[(key[0], agent_type, session[:8])] += read_sizes[key] * (count - 1) / count
        if not messages:
            continue
        previous_time = previous_model = None
        sequence = []
        for index, (message_id, message_data) in enumerate(messages.items()):
            usage = dict(message_data["u"])
            usage["output_tokens"] = message_data["out"]
            cost, cache_5m, cache_1h, ttl_info = wcost(usage, message_data["m"])
            ttl_assumptions.update(ttl_info)
            model_key = parse_model(message_data["m"])
            if not weighted and model_key is None:
                unknown_models[message_data["m"] or "(missing)"] += 1
            input_tokens = usage.get("input_tokens", 0) or 0
            cache_read = usage.get("cache_read_input_tokens", 0) or 0
            cache_created = usage.get("cache_creation_input_tokens", 0) or 0
            context = input_tokens + cache_read + cache_created
            timestamp_dt = dt.datetime.fromisoformat(message_data["ts"].replace("Z", "+00:00"))
            gap = (timestamp_dt - previous_time).total_seconds() if previous_time else None
            record = dict(day=message_data["ts"][:10], sub=is_subagent, at=agent_type, proj=project,
                sess=session, f=os.path.basename(file_path), m=message_data["m"], i=input_tokens,
                c5=cache_5m, c1=cache_1h, cr=cache_read, o=message_data["out"], w=cost,
                ctx=context, n=index, gap=gap, msw=(previous_model is not None and previous_model != message_data["m"]),
                cmpl=message_data["sr"] is not None, eff=message_data["eff"], txt=message_data["txt"],
                tuc=message_data["tuc"], ntu=message_data["ntu"], nth=message_data["nth"], tt=message_data["tt"])
            calls.append(record)
            sequence.append(record)
            previous_time, previous_model = timestamp_dt, message_data["m"]
        timestamps = sorted(message["ts"] for message in messages.values())
        transcript_rates = rates(sequence[-1]["m"], sequence[-1]["ctx"])
        divisor = 1 if weighted else 1_000_000
        for pending_time, label, tokens, parent_agent in pending:
            remaining = len(timestamps) - bisect.bisect_right(timestamps, pending_time)
            carry_cost = tokens * (transcript_rates[2] + transcript_rates[4] * max(remaining - 1, 0)) / divisor if remaining else 0
            carry[label]["tok"] += tokens
            carry[label]["w"] += carry_cost
            carry[label]["n"] += 1
            carry["by:" + parent_agent]["w"] += carry_cost
        transcripts.append(dict(sub=is_subagent, at=agent_type, sess=session, f=os.path.basename(file_path),
            proj=project, turns=len(sequence), w=sum(record["w"] for record in sequence),
            tok=sum(record["i"] + record["c5"] + record["c1"] + record["cr"] + record["o"] for record in sequence),
            start=sequence[0]["ctx"], start_cc=sequence[0]["c5"] + sequence[0]["c1"],
            start_cr=sequence[0]["cr"], peak=max(record["ctx"] for record in sequence), full=(sequence[0]["n"] == 0)))

    W = sum(call["w"] for call in calls)
    SHARE_W = W if W > 0 else 1
    out = {}

    def agg(key_fn, items=calls):
        grouped = collections.defaultdict(collections.Counter)
        for call in items:
            key = key_fn(call)
            grouped[key]["w"] += call["w"]
            grouped[key]["n"] += 1
            for token_type in ("i", "c5", "c1", "cr", "o"):
                grouped[key][token_type] += call[token_type]
        return {str(key): dict(values, share=round(100 * values["w"] / SHARE_W, 1))
                for key, values in sorted(grouped.items(), key=lambda item: -item[1]["w"])}

    out["pricing"] = "weighted-mf" if weighted else "api-list-price-estimate-partial" if unknown_models else "api-list-price-estimate"
    out["dups"] = dict(duplicates)
    out["W_total"] = W
    out["ncalls"] = len(calls)
    out["ntranscripts"] = len(transcripts)
    out["cut"] = CUT
    out["measurement"] = {
        "kind": "heuristic-weight-units" if weighted else "api-cost-estimate-usd",
        "subscription_quota": False,
        "pricing_source": PRICING_SOURCE,
        "pricing_date": PRICING_DATE,
        "quota_reference": QUOTA_SOURCE,
        "unknown_model_calls": sum(unknown_models.values()),
        "unknown_models": dict(sorted(unknown_models.items())),
        "cost_totals_partial": bool(unknown_models) and not weighted,
        "invalid_timestamp_entries": invalid_timestamp_entries,
        "ttl_assumptions": dict(ttl_assumptions),
        "carry_attribution": "heuristic, not observed API billing",
        "carry_assumptions": ["full survival without compaction", "tool-result text at 2.2 chars/token",
            "image tokens approximated from dimensions", "cache write/read rates inferred from the transcript's final model"],
    }

    # Missing completion usage is imputed from visible content; carry is a separate transcript-based heuristic.
    thinking_groups = collections.defaultdict(lambda: [0.0, 0])
    group_keys = lambda call: ((call["at"], call["eff"], call["m"]), (call["eff"], call["m"]), (call["m"],))
    for call in calls:
        if call["cmpl"] and call["nth"]:
            estimated_thinking = call["tt"] if call["tt"] is not None else max(0.0, call["o"] - 40 * (1 + call["ntu"]) - (call["txt"] + call["tuc"]) / 2.3)
            for key in group_keys(call):
                thinking_groups[key][0] += estimated_thinking
                thinking_groups[key][1] += 1
    imputed_models = collections.Counter()
    for call in calls:
        call["wi"] = call["w"]
        if call["cmpl"]:
            continue
        imputed_models[call["m"]] += 1
        thinking = next((thinking_groups[key][0] / thinking_groups[key][1] for key in group_keys(call)
            if call["nth"] and thinking_groups[key][1] >= 20), 0.0)
        divisor = 1 if weighted else 1_000_000
        call["wi"] = call["w"] + rates(call["m"], call["ctx"])[1] / divisor * max(
            0.0, 40 * (1 + call["ntu"]) + (call["txt"] + call["tuc"]) / 2.3 + thinking - call["o"])
    WI = sum(call["wi"] for call in calls)
    out["imputed"] = dict(incomplete_share=round(sum(not call["cmpl"] for call in calls) / max(1, len(calls)), 3),
        W_total_imputed=WI, added_pct=round(100 * (WI / W - 1), 1) if W else 0,
        usd_main=round(sum(call["wi"] for call in calls if not call["sub"]), 6) if not weighted else round(sum(call["wi"] for call in calls if not call["sub"]) / 1_000_000, 1),
        usd_sub=round(sum(call["wi"] for call in calls if call["sub"]), 6) if not weighted else round(sum(call["wi"] for call in calls if call["sub"]) / 1_000_000, 1),
        unpriced_incomplete_calls=sum(imputed_models[model] for model in unknown_models))
    out["effort_mix"] = collections.Counter(str(call["eff"]) for call in calls).most_common()
    out["totals"] = agg(lambda call: "all")
    out["by_day"] = agg(lambda call: call["day"])
    out["main_vs_sub"] = agg(lambda call: "sub" if call["sub"] else "main")
    out["by_model"] = agg(lambda call: call["m"])
    out["by_proj"] = dict(list(agg(lambda call: call["proj"]).items())[:10])
    out["by_agent"] = agg(lambda call: call["at"])
    agent_transcripts = collections.defaultdict(list)
    for transcript in transcripts:
        if transcript["sub"]:
            agent_transcripts[transcript["at"]].append(transcript)
    out["agent_types"] = {key: dict(spawns=len(value), med_tok=statistics.median([item["tok"] for item in value]),
        p90_tok=pctl([item["tok"] for item in value], .9), med_w=statistics.median([item["w"] for item in value]),
        share=round(100 * sum(item["w"] for item in value) / SHARE_W, 1),
        med_turns=statistics.median([item["turns"] for item in value]),
        med_start=statistics.median([item["start"] for item in value if item["full"]] or [0]),
        med_start_cc=statistics.median([item["start_cc"] for item in value if item["full"]] or [0]),
        med_peak=statistics.median([item["peak"] for item in value]))
        for key, value in sorted(agent_transcripts.items(), key=lambda pair: -sum(item["w"] for item in pair[1]))}
    mains = [item for item in transcripts if not item["sub"] and item["full"]]
    out["main_start"] = dict(n=len(mains), med_start=statistics.median([item["start"] for item in mains] or [0]),
        med_start_cc=statistics.median([item["start_cc"] for item in mains] or [0]))
    out["spawn_types_from_parent"] = agent_spawn_types.most_common(20)

    def bucket(value):
        return "<50k" if value < 50e3 else "50-100k" if value < 100e3 else "100-200k" if value < 200e3 else "200-400k" if value < 400e3 else ">400k"

    out["ctx_buckets"] = agg(lambda call: bucket(call["ctx"]))
    out["ctx_buckets_main_sub"] = agg(lambda call: (bucket(call["ctx"]), "sub" if call["sub"] else "main"))
    big_calls = [call for call in calls if call["ctx"] >= 200e3]
    out["gt200_by_transcript"] = dict(list(agg(lambda call: (call["at"], call["sess"][:8], call["f"][:22], call["proj"][-22:]), big_calls).items())[:12])
    out["gt200_by_agent"] = dict(list(agg(lambda call: call["at"], big_calls).items())[:8])
    cache_read = sum(call["cr"] for call in calls)
    cache_created = sum(call["c5"] + call["c1"] for call in calls)
    input_total = sum(call["i"] for call in calls)
    out["cache_hit"] = round(cache_read / (cache_read + cache_created + input_total), 4) if cache_read + cache_created + input_total else 0
    rebuilds = [call for call in calls if call["n"] > 0 and (call["c5"] + call["c1"]) > 20000 and (call["c5"] + call["c1"]) > 0.5 * call["ctx"]]

    def rebuild_class(call):
        if call["msw"]:
            return "model_switch"
        if call["gap"] is not None and call["gap"] > 3600:
            return "gap>1h"
        if call["gap"] is not None and call["gap"] > 300:
            return "gap5m-1h"
        return "no_gap(compact/edit/other)"

    out["rebuilds"] = agg(rebuild_class, rebuilds)
    out["rebuild_w_by_agent"] = dict(list(agg(lambda call: call["at"], rebuilds).items())[:8])
    out["rebuild_by_sess"] = dict(list(agg(lambda call: (call["at"], call["sess"][:8], call["proj"][-20:]), rebuilds).items())[:8])
    out["cw_1h_share"] = round(sum(call["c1"] for call in calls) / max(cache_created, 1), 3)
    divisor = 1 if weighted else 1_000_000
    out["cache_write_w_share"] = round(100 * sum(rates(call["m"], call["ctx"])[2] * call["c5"] + rates(call["m"], call["ctx"])[3] * call["c1"] for call in calls) / divisor / SHARE_W, 1)
    out["cache_read_w_share"] = round(100 * sum(rates(call["m"], call["ctx"])[4] * call["cr"] for call in calls) / divisor / SHARE_W, 1)
    out["output_w_share"] = round(100 * sum(rates(call["m"], call["ctx"])[1] * call["o"] for call in calls) / divisor / SHARE_W, 1)
    out["input_w_share"] = round(100 * sum(rates(call["m"], call["ctx"])[0] * call["i"] for call in calls) / divisor / SHARE_W, 1)
    out["thinking_char_share_of_output"] = round(thinking_chars / max(1, thinking_chars + text_chars + tooluse_chars), 3)
    out["out_chars"] = dict(thinking=thinking_chars, text=text_chars, tool_use=tooluse_chars)
    out["toolres"] = sorted(([key, value[0], value[1]] for key, value in tool_results.items()), key=lambda row: -row[1])[:25]
    out["images"] = images
    out["biggest"] = sorted(biggest, reverse=True)[:15]
    out["reread_top"] = [[key, reread[key], int(reread_chars[key])] for key, _ in reread_chars.most_common(12)]
    out["reread_total"] = [sum(reread.values()), int(sum(reread_chars.values()))]
    out["top_transcripts"] = [[item["at"], item["sess"][:8], item["f"][:24], item["proj"][-22:], item["turns"],
        round(100 * item["w"] / SHARE_W, 2), item["peak"]] for item in sorted(transcripts, key=lambda item: -item["w"])[:15]]
    sessions = collections.Counter()
    for transcript in transcripts:
        sessions[(transcript["sess"][:8], transcript["proj"][-22:])] += transcript["w"]
    out["top_sessions"] = [[key, round(100 * value / SHARE_W, 1)] for key, value in sessions.most_common(10)]
    out["carry"] = sorted(([key, int(value["tok"]), round(100 * value["w"] / SHARE_W, 1), value["n"]]
        for key, value in carry.items()), key=lambda row: -row[2])[:30]
    out["img_by"] = [[list(key), value] for key, value in img_by.most_common(10)]
    out["img_tok_by"] = img_tok_by.most_common(10)
    out["bash_by"] = bash_by.most_common(12)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", help="JSON report path (legacy positional argument)")
    parser.add_argument("--root", default="~/.claude/projects", help="transcript root (default: ~/.claude/projects)")
    parser.add_argument("--days", type=int, default=7, help="lookback window in days (default: 7)")
    parser.add_argument("--as-of", help="inclusive window end, ISO8601 with timezone; defaults to current UTC time")
    parser.add_argument("--weighted", action="store_true", help="use heuristic MF units instead of API price estimates")
    args = parser.parse_args(argv)
    if args.days < 0:
        parser.error("--days must be non-negative")
    as_of = args.as_of or dt.datetime.now(dt.timezone.utc).isoformat()
    try:
        report = audit(args.root, args.days, as_of, args.weighted)
    except ValueError as error:
        parser.error(str(error))
    with open(args.output, "w", encoding="utf-8") as report_file:
        json.dump(report, report_file, indent=1, default=str)
    print("ok", report["ncalls"], report["ntranscripts"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
