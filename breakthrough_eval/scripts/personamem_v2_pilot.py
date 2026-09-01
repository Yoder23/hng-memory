#!/usr/bin/env python3
"""Leakage-controlled PersonaMem-v2 32K MCQ pilot (noncanonical)."""

from __future__ import annotations

import argparse
import ast
import collections
import csv
import hashlib
import json
import math
import random
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "breakthrough_eval"
DEFAULT_DATA_ROOT = Path(r"C:\tmp\pmv2")
sys.path.insert(0, str(ROOT))

from breakthrough_eval.scripts.longmemeval_v2_text_pilot import (  # noqa: E402
    Candidate, DEFAULT_DIGEST, DEFAULT_MODEL, SEED, bm25_rank, hng_govern,
    ollama_chat, select_context, stable_hash, strong_structured_govern,
)

SCHEMA_VERSION = 1
PROMPT_PROTOCOL_REVISION = 2
PREF_TYPES = (
    "anti_stereotypical_pref", "therapy_background", "neutral_preferences",
    "health_and_medical_conditions", "stereotypical_pref", "ask_to_forget",
    "sensitive_info",
)
ARMS = (
    "no_memory", "short_profile", "expanded_profile", "full_history",
    "bm25", "strong_structured", "hng",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_jsonl(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(dict(value), sort_keys=True) + "\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_user_query(value: str) -> str:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        try:
            parsed = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return str(value).strip("\"'")
    return str(parsed.get("content") or "") if isinstance(parsed, dict) else str(parsed)


def selection_key(index: int, row: Mapping[str, str]) -> str:
    """Use pref_type only as a stratum; exclude answers and target/profile/oracle text."""
    return stable_hash({
        "seed": SEED, "index": index, "persona_id": row.get("persona_id", ""),
        "pref_type": row.get("pref_type", ""),
        "history": row.get("chat_history_32k_link", ""),
        "query_sha256": stable_hash(parse_user_query(row.get("user_query", ""))),
    })


def select_rows(rows: Sequence[dict[str, str]], per_type: int) -> list[tuple[int, dict[str, str]]]:
    grouped: dict[str, list[tuple[int, dict[str, str]]]] = collections.defaultdict(list)
    for index, row in enumerate(rows):
        grouped[str(row.get("pref_type") or "")].append((index, row))
    selected = []
    for pref_type in PREF_TYPES:
        ranked = sorted(grouped.get(pref_type, []), key=lambda item: selection_key(*item))
        selected.extend(ranked[:per_type])
    return sorted(selected, key=lambda item: item[0])


def load_history(data_root: Path, row: Mapping[str, str]) -> list[dict[str, str]]:
    payload = json.loads((data_root / str(row["chat_history_32k_link"])).read_text(encoding="utf-8"))
    return [
        {"role": str(msg.get("role") or "user"), "content": str(msg.get("content") or "")}
        for msg in payload["chat_history"]
    ]


def conversation_candidates(index: int, history: Sequence[Mapping[str, str]], *, chunk_size: int, chunk_overlap: int) -> list[Candidate]:
    messages = [message for message in history if message.get("role") != "system"]
    stride = max(1, chunk_size - chunk_overlap)
    result = []
    for ordinal, start in enumerate(range(0, len(messages), stride)):
        chunk = messages[start : start + chunk_size]
        if not chunk:
            continue
        text = "\n".join(f"{msg['role'].upper()}: {msg['content']}" for msg in chunk)
        candidate_id = f"personamem-{index:05d}:{ordinal:04d}"
        result.append(Candidate(
            candidate_id=candidate_id, source_event_id=candidate_id,
            trajectory_id=f"personamem-{index:05d}", state_index=ordinal, text=text,
        ))
    return result


def selected_candidates(index: int, row: Mapping[str, str], history: Sequence[Mapping[str, str]], args: argparse.Namespace) -> list[Candidate]:
    corpus = conversation_candidates(index, history, chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap)
    return select_context(
        bm25_rank(parse_user_query(row["user_query"]), corpus),
        top_k=args.top_k, char_budget=args.context_chars,
    )


def prepare(args: argparse.Namespace) -> tuple[list[tuple[int, dict[str, str]]], dict[int, list[Candidate]]]:
    rows = load_rows(args.benchmark)
    selected = select_rows(rows, args.per_type)
    by_index: dict[int, list[Candidate]] = {}
    manifest_rows = []
    for index, row in selected:
        history = load_history(args.data_root, row)
        corpus = conversation_candidates(index, history, chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap)
        candidates = selected_candidates(index, row, history, args)
        by_index[index] = candidates
        history_path = args.data_root / row["chat_history_32k_link"]
        manifest_rows.append({
            "source_index": index, "persona_id": row["persona_id"],
            "pref_type": row["pref_type"], "updated": row["updated"],
            "history_path": row["chat_history_32k_link"],
            "history_sha256": sha256_file(history_path),
            "query_sha256": stable_hash(parse_user_query(row["user_query"])),
            "selection_key": selection_key(index, row),
            "retrieval_corpus_count": len(corpus),
            "retrieval_corpus_sha256": stable_hash([item.payload() for item in corpus]),
            "selected_candidate_count": len(candidates),
            "selected_candidate_sha256": stable_hash([item.payload() for item in candidates]),
            "selected_context_chars": sum(len(item.text) for item in candidates),
            "candidates": [item.payload() for item in candidates],
        })
    write_json(args.output / "PREPARED.json", {
        "schema_version": SCHEMA_VERSION, "created_at": utc_now(), "status": "prepared",
        "protocol": "PersonaMem-v2 32K seven-stratum MCQ pilot; NONCANONICAL",
        "selection": "one SHA-256-selected row per pref_type; correct/incorrect answers and target/profile/oracle text excluded",
        "seed": SEED, "sample_count": len(selected), "benchmark_rows": len(rows),
        "benchmark_sha256": sha256_file(args.benchmark),
        "parameters": {"per_type": args.per_type, "chunk_size": args.chunk_size,
                       "chunk_overlap": args.chunk_overlap, "top_k": args.top_k,
                       "context_chars": args.context_chars},
        "samples": manifest_rows,
    })
    return selected, by_index


def option_bundle(index: int, row: Mapping[str, str]) -> tuple[str, str, list[str]]:
    incorrect = json.loads(row.get("incorrect_answers") or "[]")
    options = [str(row["correct_answer"]), *[str(item) for item in incorrect]][:4]
    option_seed = int(stable_hash({
        "seed": SEED, "source_index": index,
        "query": parse_user_query(row["user_query"]),
    }), 16)
    random.Random(option_seed).shuffle(options)
    correct_letter = chr(65 + options.index(str(row["correct_answer"])))
    rendered = "\n".join(f"{chr(65 + offset)}. {option}" for offset, option in enumerate(options))
    return rendered, correct_letter, options


def mcq_text(query: str, rendered_options: str) -> str:
    return (
        f"{query} Please recall my related preferences from our conversation history to give personalized responses.\n\n"
        "Please choose the best answer from the following options:\n\n"
        f"{rendered_options}\n\n"
        "Give 'Final Answer: [Letter]' first, then at most one short sentence of reasoning."
    )


def context_messages(label: str, memory: str, question: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "Answer the personalization MCQ using only supplied memory when memory is present."},
        {"role": "user", "content": f"{label}\n{memory or 'No memory supplied.'}\n\nCURRENT QUERY\n{question}"},
    ]


def messages_for_arm(
    arm: str,
    row: Mapping[str, str],
    history: Sequence[Mapping[str, str]],
    candidates: Sequence[Candidate],
    question: str,
) -> list[dict[str, str]]:
    if arm == "full_history":
        return [*history, {"role": "user", "content": question}]
    if arm == "short_profile":
        return context_messages("SHORT PROFILE", str(row.get("short_persona") or ""), question)
    if arm == "expanded_profile":
        return context_messages("EXPANDED PROFILE", str(row.get("expanded_persona") or ""), question)
    if arm == "no_memory":
        return context_messages("MEMORY", "", question)
    memory = "\n\n".join(item.text for item in candidates)
    return context_messages("RETRIEVED CONVERSATION CHUNKS", memory, question)


FINAL_RE = re.compile(r"final\s*answer\s*:\s*\[?\(?([A-D])", re.IGNORECASE)
BOXED_RE = re.compile(r"\\boxed\{\s*([A-D])\s*\}", re.IGNORECASE)


def extract_letter(text: str) -> str:
    for pattern in (FINAL_RE, BOXED_RE):
        match = pattern.search(text)
        if match:
            return match.group(1).upper()
    return ""


def completed_keys(raw_path: Path) -> set[tuple[int, str]]:
    if not raw_path.exists():
        return set()
    result = set()
    with raw_path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                item = json.loads(line)
                done_reason = item.get("reader", {}).get("raw_response", {}).get("done_reason")
                identity_valid = item.get("arm") != "hng" or item.get("source_identity") == "PersonaMem-v2"
                prompt_valid = (
                    item.get("arm") != "full_history"
                    or item.get("prompt_protocol_revision") == PROMPT_PROTOCOL_REVISION
                )
                if (
                    item.get("event") == "prediction"
                    and not item.get("error")
                    and item.get("predicted_letter")
                    and done_reason != "length"
                    and identity_valid
                    and prompt_valid
                ):
                    result.add((int(item["source_index"]), str(item["arm"])))
    return result


def run(
    args: argparse.Namespace,
    selected: Sequence[tuple[int, dict[str, str]]],
    candidates_by_index: Mapping[int, list[Candidate]],
) -> dict[str, object]:
    raw_path = args.output / "raw" / "events.jsonl"
    completed = completed_keys(raw_path)
    for index, row in selected:
        history = load_history(args.data_root, row)
        base = candidates_by_index[index]
        strong, strong_trace = strong_structured_govern(base)
        hng, hng_trace = hng_govern(
            base,
            source_identity="PersonaMem-v2",
            source_id_prefix="personamem-v2",
        )
        rendered_options, correct_letter, options = option_bundle(index, row)
        question = mcq_text(parse_user_query(row["user_query"]), rendered_options)
        pool_hash = stable_hash([item.payload() for item in base])
        for arm in ARMS:
            if (index, arm) in completed:
                continue
            if arm == "strong_structured":
                candidates, trace = strong, strong_trace
            elif arm == "hng":
                candidates, trace = hng, hng_trace
            elif arm == "bm25":
                candidates = base
                trace = {"included": [item.candidate_id for item in base], "excluded": []}
            else:
                candidates, trace = [], {"mode": arm}
            messages = messages_for_arm(arm, row, history, candidates, question)
            event: dict[str, object] = {
                "schema_version": SCHEMA_VERSION,
                "prompt_protocol_revision": PROMPT_PROTOCOL_REVISION,
                "event": "prediction",
                "created_at": utc_now(),
                "protocol": "personamem_v2_32k_seven_stratum_mcq_noncanonical",
                "source_index": index,
                "persona_id": row["persona_id"],
                "pref_type": row["pref_type"],
                "updated": row["updated"],
                "arm": arm,
                "model": args.model,
                "model_digest": args.model_digest,
                "source_identity": "PersonaMem-v2" if arm == "hng" else None,
                "candidate_pool_sha256": pool_hash if arm in {"bm25", "strong_structured", "hng"} else stable_hash([]),
                "selected_candidate_ids": [item.candidate_id for item in candidates],
                "governance_trace": trace,
                "prompt_sha256": stable_hash(messages),
            }
            try:
                prediction, metadata = ollama_chat(
                    messages,
                    model=args.model,
                    endpoint=args.endpoint,
                    timeout=args.timeout,
                    num_predict=args.num_predict,
                    num_ctx=65536 if arm == "full_history" else 32768,
                )
                predicted_letter = extract_letter(prediction)
                event.update({
                    "prediction": prediction,
                    "predicted_letter": predicted_letter,
                    "correct_letter": correct_letter,
                    "correct": predicted_letter == correct_letter,
                    "correct_answer": row["correct_answer"],
                    "options": options,
                    "reader": metadata,
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
    selected: Sequence[tuple[int, Mapping[str, str]]],
    raw_path: Path,
) -> dict[str, object]:
    latest: dict[tuple[int, str], dict[str, Any]] = {}
    failures = []
    excluded_events = []
    with raw_path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            done_reason = row.get("reader", {}).get("raw_response", {}).get("done_reason")
            identity_valid = row.get("arm") != "hng" or row.get("source_identity") == "PersonaMem-v2"
            prompt_valid = (
                row.get("arm") != "full_history"
                or row.get("prompt_protocol_revision") == PROMPT_PROTOCOL_REVISION
            )
            if row.get("error"):
                failures.append(row)
            elif not row.get("predicted_letter") or done_reason == "length" or not identity_valid or not prompt_valid:
                excluded_events.append({
                    "source_index": row.get("source_index"),
                    "arm": row.get("arm"),
                    "created_at": row.get("created_at"),
                    "prompt_sha256": row.get("prompt_sha256"),
                    "reason": (
                        "missing_final_letter_or_output_cap"
                        if not row.get("predicted_letter") or done_reason == "length"
                        else "mislabeled_hng_source_identity"
                        if not identity_valid
                        else "superseded_full_history_prompt"
                    ),
                })
            else:
                latest[(int(row["source_index"]), str(row["arm"]))] = row
    summaries = {}
    by_type = []
    for arm in ARMS:
        arm_rows = [row for (_index, name), row in latest.items() if name == arm]
        elapsed = [float(row["reader"]["elapsed_seconds"]) for row in arm_rows]
        summaries[arm] = {
            "count": len(arm_rows),
            "correct": sum(bool(row["correct"]) for row in arm_rows),
            "accuracy": statistics.mean(bool(row["correct"]) for row in arm_rows) if arm_rows else None,
            "prompt_tokens": sum(int(row["reader"].get("prompt_eval_count") or 0) for row in arm_rows),
            "latency_seconds_p50": percentile(elapsed, 0.50),
            "latency_seconds_p95": percentile(elapsed, 0.95),
        }
        for pref_type in PREF_TYPES:
            typed = [row for row in arm_rows if row["pref_type"] == pref_type]
            by_type.append({
                "arm": arm,
                "pref_type": pref_type,
                "count": len(typed),
                "accuracy": statistics.mean(bool(row["correct"]) for row in typed) if typed else None,
            })
    invariants = []
    for index, _row in selected:
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
        "status": "complete" if all(summary["count"] == len(selected) for summary in summaries.values()) else "partial",
        "protocol": "PersonaMem-v2 32K seven-stratum MCQ pilot; NONCANONICAL",
        "prompt_protocol_revision": PROMPT_PROTOCOL_REVISION,
        "limitations": [
            "seven-row pilot rather than all 5,000 text benchmark rows",
            "local frozen 27B reader rather than official frontier-model configuration",
            "BM25 chunk retrieval rather than the official dense RAG baseline",
            "no dense-memory or agentic-profile baseline executed",
            "clean public histories expose no trust/tenant/version distinction for HNG governance",
        ],
        "model": args.model,
        "model_digest": args.model_digest,
        "seed": SEED,
        "sample_count": len(selected),
        "summaries": summaries,
        "by_pref_type": by_type,
        "fixed_candidate_invariants": invariants,
        "all_fixed_candidate_invariants_pass": bool(invariants) and all(
            all(row[key] for key in (
                "candidate_pool_identical", "selected_candidates_identical",
                "prompt_identical", "model_digest_identical",
            ))
            for row in invariants
        ),
        "failure_count": len(failures),
        "failures": failures,
        "excluded_event_count": len(excluded_events),
        "excluded_events": excluded_events,
        "raw_log": raw_path.relative_to(ROOT).as_posix(),
    }
    write_json(args.output / "RESULTS.json", result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--benchmark", type=Path)
    parser.add_argument("--output", type=Path, default=EVAL / "public" / "personamem_v2")
    parser.add_argument("--per-type", type=int, default=1)
    parser.add_argument("--chunk-size", type=int, default=6)
    parser.add_argument("--chunk-overlap", type=int, default=2)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--context-chars", type=int, default=18_000)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--model-digest", default=DEFAULT_DIGEST)
    parser.add_argument("--endpoint", default="http://localhost:11434")
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--num-predict", type=int, default=128)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    if args.benchmark is None:
        args.benchmark = args.data_root / "benchmark" / "text" / "benchmark.csv"
    return args


def main() -> int:
    args = parse_args()
    selected, candidates = prepare(args)
    if args.prepare_only:
        print(json.dumps({"status": "prepared", "samples": len(selected), "output": str(args.output)}))
        return 0
    result = run(args, selected, candidates)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "complete" and result["failure_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
