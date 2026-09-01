#!/usr/bin/env python3
"""Leakage-controlled six-category LoCoMo-Plus local pilot.

The official public data, task instructions, and judge templates are reused. The
reader and judge are the same frozen local 27B model, so results are noncanonical
and cannot be compared directly to the official leaderboard.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "breakthrough_eval"
EXTERNAL = EVAL / "external" / "Locomo-Plus"
DATA = EXTERNAL / "data" / "unified_input_samples_v2.json"
FRAMEWORK = EXTERNAL / "evaluation_framework"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(FRAMEWORK))

from breakthrough_eval.scripts.longmemeval_v2_text_pilot import (  # noqa: E402
    Candidate,
    DEFAULT_DIGEST,
    DEFAULT_MODEL,
    SEED,
    bm25_rank,
    hng_govern,
    ollama_chat,
    select_context,
    stable_hash,
    strong_structured_govern,
)
from task_eval import llm_as_judge as official_judge  # noqa: E402
from task_eval import utils as official_utils  # noqa: E402


SCHEMA_VERSION = 1
CATEGORIES = ("single-hop", "multi-hop", "temporal", "common-sense", "adversarial", "Cognitive")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_jsonl(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(dict(value), sort_keys=True) + "\n")


def select_samples(samples: Sequence[dict[str, Any]], per_category: int) -> list[tuple[int, dict[str, Any]]]:
    grouped: dict[str, list[tuple[int, dict[str, Any]]]] = collections.defaultdict(list)
    for index, sample in enumerate(samples):
        grouped[str(sample["category"])].append((index, sample))
    selected = []
    for category in CATEGORIES:
        rows = grouped.get(category, [])
        rows = sorted(
            rows,
            key=lambda item: stable_hash({
                "seed": SEED,
                "category": category,
                "index": item[0],
                "input_prompt_sha256": stable_hash(item[1]["input_prompt"]),
            }),
        )
        selected.extend(rows[:per_category])
    return sorted(selected, key=lambda item: item[0])


def split_memory_and_query(sample: Mapping[str, Any]) -> tuple[str, str, str]:
    """Return memory text, current query/trigger, and official full input."""
    full = str(sample.get("input_prompt") or "").strip()
    category = str(sample.get("category") or "")
    if category != "Cognitive":
        marker = "\n\nQuestion:"
        if marker not in full:
            raise ValueError("non-Cognitive sample missing Question boundary")
        memory, question = full.rsplit(marker, 1)
        expected = str(sample.get("trigger") or "").strip()
        if question.strip() != expected:
            raise ValueError("question/trigger mismatch")
        return memory.strip(), question.strip(), full

    # The official generator stitches the mapped trigger utterance as the final dialogue line.
    lines = full.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        raise ValueError("empty Cognitive input")
    mapped_trigger = lines.pop().strip()
    raw_trigger = str(sample.get("trigger") or "").strip()
    trigger_text = raw_trigger.split(":", 1)[-1].strip().strip('"')
    if trigger_text and trigger_text.lower() not in mapped_trigger.lower():
        raise ValueError("Cognitive final line does not contain trigger text")
    return "\n".join(lines).strip(), mapped_trigger, full


DATE_RE = re.compile(r"^DATE:\s*(.+)$", re.IGNORECASE)


def dialogue_candidates(sample_index: int, memory: str) -> list[Candidate]:
    current_date = "unknown"
    result = []
    ordinal = 0
    for raw_line in memory.splitlines():
        line = raw_line.strip()
        if not line or line.upper() == "CONVERSATION:":
            continue
        date_match = DATE_RE.match(line)
        if date_match:
            current_date = date_match.group(1).strip()
            continue
        candidate_id = f"locomo-{sample_index:04d}:{ordinal:05d}"
        result.append(Candidate(
            candidate_id=candidate_id,
            source_event_id=candidate_id,
            trajectory_id=f"locomo-{sample_index:04d}",
            state_index=ordinal,
            text=f"DATE: {current_date}\n{line}",
        ))
        ordinal += 1
    return result


def render_retrieved(candidates: Sequence[Candidate], query: str, category: str) -> str:
    memory = "\n".join(item.text for item in candidates)
    if category == "Cognitive":
        return f"RETRIEVED PRIOR CONVERSATION:\n{memory}\n\nCURRENT CONTINUATION:\n{query}"
    return f"RETRIEVED PRIOR CONVERSATION:\n{memory}\n\nQuestion: {query}"


def reader_messages(body: str, category: str) -> list[dict[str, str]]:
    official_input = official_utils._build_model_input(body, category=category)
    return [{"role": "user", "content": official_input}]


def judge_prediction(
    sample: Mapping[str, Any],
    prediction: str,
    *,
    model: str,
    endpoint: str,
    timeout: float,
) -> tuple[float, dict[str, object]]:
    prompt = official_judge.get_judge_prompt(
        str(sample.get("category") or "default"),
        str(sample.get("evidence") or ""),
        prediction,
        str(sample.get("answer") or ""),
    )
    response, metadata = ollama_chat(
        [{"role": "user", "content": prompt}],
        model=model,
        endpoint=endpoint,
        timeout=timeout,
        num_predict=128,
        json_format=True,
    )
    label, reason = official_judge._parse_judge_response(response)
    score = official_judge.label_to_score(label)
    metadata.update({"response": response, "label": label, "reason": reason, "score": score})
    return score, metadata


def prepare(args: argparse.Namespace) -> tuple[list[tuple[int, dict[str, Any]]], dict[int, list[Candidate]], dict[str, object]]:
    samples = json.loads(args.data.read_text(encoding="utf-8"))
    selected = select_samples(samples, args.per_category)
    candidates_by_index = {}
    rows = []
    for index, sample in selected:
        memory, query, _full = split_memory_and_query(sample)
        corpus = dialogue_candidates(index, memory)
        ranked = bm25_rank(query, corpus)
        selected_candidates = select_context(ranked, top_k=args.top_k, char_budget=args.context_chars)
        candidates_by_index[index] = selected_candidates
        rows.append({
            "sample_id": f"locomo-plus-{index:04d}",
            "source_index": index,
            "category": sample["category"],
            "input_prompt_sha256": stable_hash(sample["input_prompt"]),
            "trigger_sha256": stable_hash(sample["trigger"]),
            "memory_without_query_sha256": stable_hash(memory),
            "retrieval_corpus_count": len(corpus),
            "retrieval_corpus_sha256": stable_hash([item.payload() for item in corpus]),
            "selected_candidate_count": len(selected_candidates),
            "selected_candidate_sha256": stable_hash([item.payload() for item in selected_candidates]),
            "selected_context_chars": sum(len(item.text) for item in selected_candidates),
            "candidates": [item.payload() for item in selected_candidates],
        })
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "protocol": "LoCoMo-Plus six-category local pilot; NONCANONICAL",
        "selection": "SHA-256(seed,category,index,input-prompt-hash); answers/evidence excluded",
        "seed": SEED,
        "sample_count": len(selected),
        "parameters": {
            "per_category": args.per_category,
            "top_k": args.top_k,
            "context_chars": args.context_chars,
        },
        "samples": rows,
    }
    write_json(args.output / "PREPARED.json", manifest)
    return selected, candidates_by_index, manifest


def completed_keys(raw_path: Path) -> set[tuple[int, str]]:
    if not raw_path.exists():
        return set()
    result = set()
    with raw_path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                if row.get("event") == "prediction" and not row.get("error"):
                    result.add((int(row["source_index"]), str(row["arm"])))
    return result


def run(
    args: argparse.Namespace,
    selected: Sequence[tuple[int, dict[str, Any]]],
    candidates_by_index: Mapping[int, list[Candidate]],
) -> dict[str, object]:
    raw_path = args.output / "raw" / "events.jsonl"
    completed = completed_keys(raw_path)
    arms = ("full_context", "bm25", "strong_structured", "hng")
    for index, sample in selected:
        memory, query, full = split_memory_and_query(sample)
        category = str(sample["category"])
        base = candidates_by_index[index]
        strong, strong_trace = strong_structured_govern(base)
        hng, hng_trace = hng_govern(base)
        candidate_hash = stable_hash([item.payload() for item in base])
        for arm in arms:
            if (index, arm) in completed:
                continue
            if arm == "full_context":
                body = full
                candidates = []
                trace: Mapping[str, object] = {"mode": "official_full_context"}
                pool_hash = stable_hash([])
            elif arm == "bm25":
                candidates = base
                trace = {"included": [item.candidate_id for item in base], "excluded": []}
                body = render_retrieved(candidates, query, category)
                pool_hash = candidate_hash
            elif arm == "strong_structured":
                candidates, trace = strong, strong_trace
                body = render_retrieved(candidates, query, category)
                pool_hash = candidate_hash
            else:
                candidates, trace = hng, hng_trace
                body = render_retrieved(candidates, query, category)
                pool_hash = candidate_hash
            messages = reader_messages(body, category)
            event: dict[str, object] = {
                "schema_version": SCHEMA_VERSION,
                "event": "prediction",
                "created_at": utc_now(),
                "protocol": "locomo_plus_local_pilot_noncanonical",
                "sample_id": f"locomo-plus-{index:04d}",
                "source_index": index,
                "category": category,
                "arm": arm,
                "model": args.model,
                "model_digest": args.model_digest,
                "candidate_pool_sha256": pool_hash,
                "selected_candidate_ids": [item.candidate_id for item in candidates],
                "governance_trace": trace,
                "prompt_sha256": stable_hash(messages),
            }
            try:
                prediction, reader = ollama_chat(
                    messages,
                    model=args.model,
                    endpoint=args.endpoint,
                    timeout=args.timeout,
                    num_predict=args.num_predict,
                )
                score, judge = judge_prediction(
                    sample,
                    prediction,
                    model=args.model,
                    endpoint=args.endpoint,
                    timeout=args.timeout,
                )
                event.update({
                    "prediction": prediction,
                    "ground_truth": sample.get("answer", ""),
                    "oracle_judge_evidence": sample.get("evidence", ""),
                    "judge_score": score,
                    "reader": reader,
                    "judge": judge,
                })
            except Exception as exc:
                event["error"] = f"{type(exc).__name__}: {exc}"
            append_jsonl(raw_path, event)
    return compile_results(args, selected, raw_path)


def percentile(values: Sequence[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - position) + ordered[high] * (position - low)


def compile_results(
    args: argparse.Namespace,
    selected: Sequence[tuple[int, Mapping[str, Any]]],
    raw_path: Path,
) -> dict[str, object]:
    latest: dict[tuple[int, str], dict[str, Any]] = {}
    failures = []
    with raw_path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("error"):
                failures.append(row)
            else:
                latest[(int(row["source_index"]), str(row["arm"]))] = row
    arms = ("full_context", "bm25", "strong_structured", "hng")
    summaries = {}
    by_category = []
    for arm in arms:
        rows = [row for (index, name), row in latest.items() if name == arm]
        scores = [float(row["judge_score"]) for row in rows]
        latencies = [float(row["reader"]["elapsed_seconds"]) for row in rows]
        summaries[arm] = {
            "count": len(rows),
            "score": sum(scores),
            "average": statistics.mean(scores) if scores else None,
            "prompt_tokens": sum(int(row["reader"].get("prompt_eval_count") or 0) for row in rows),
            "latency_seconds_p50": percentile(latencies, 0.50),
            "latency_seconds_p95": percentile(latencies, 0.95),
        }
        for category in CATEGORIES:
            category_rows = [row for row in rows if row["category"] == category]
            category_scores = [float(row["judge_score"]) for row in category_rows]
            by_category.append({
                "arm": arm,
                "category": category,
                "count": len(category_rows),
                "average": statistics.mean(category_scores) if category_scores else None,
            })
    invariants = []
    for index, _sample in selected:
        rows = [latest.get((index, arm)) for arm in ("bm25", "strong_structured", "hng")]
        rows = [row for row in rows if row is not None]
        if len(rows) == 3:
            invariants.append({
                "source_index": index,
                "candidate_pool_identical": len({row["candidate_pool_sha256"] for row in rows}) == 1,
                "selected_candidates_identical": len({tuple(row["selected_candidate_ids"]) for row in rows}) == 1,
                "prompt_identical": len({row["prompt_sha256"] for row in rows}) == 1,
                "model_digest_identical": len({row["model_digest"] for row in rows}) == 1,
            })
    result = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "protocol": "LoCoMo-Plus six-category local pilot; NONCANONICAL",
        "status": "complete" if all(value["count"] == len(selected) for value in summaries.values()) else "partial",
        "limitations": [
            "six-category stratified subset rather than all 2,387 samples",
            "same local frozen 27B model used as reader and judge",
            "BM25 dialogue-turn retrieval is not an official LoCoMo-Plus baseline",
            "HNG receives only clean public dialogue turns with no trust/tenant/version distinctions",
        ],
        "model": args.model,
        "model_digest": args.model_digest,
        "seed": SEED,
        "sample_count": len(selected),
        "summaries": summaries,
        "by_category": by_category,
        "fixed_candidate_invariants": invariants,
        "all_fixed_candidate_invariants_pass": bool(invariants) and all(
            all(row[key] for key in ("candidate_pool_identical", "selected_candidates_identical", "prompt_identical", "model_digest_identical"))
            for row in invariants
        ),
        "failure_count": len(failures),
        "failures": failures,
        "raw_log": str(raw_path.relative_to(ROOT)).replace("\\", "/"),
    }
    write_json(args.output / "RESULTS.json", result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--output", type=Path, default=EVAL / "public" / "locomo_plus")
    parser.add_argument("--per-category", type=int, default=1)
    parser.add_argument("--top-k", type=int, default=16)
    parser.add_argument("--context-chars", type=int, default=18_000)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--model-digest", default=DEFAULT_DIGEST)
    parser.add_argument("--endpoint", default="http://localhost:11434")
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--num-predict", type=int, default=192)
    parser.add_argument("--prepare-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    selected, candidates, _manifest = prepare(args)
    if args.prepare_only:
        print(json.dumps({"status": "prepared", "samples": len(selected), "output": str(args.output)}))
        return 0
    result = run(args, selected, candidates)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "complete" and result["failure_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
