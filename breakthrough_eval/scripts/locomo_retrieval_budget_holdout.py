#!/usr/bin/env python3
"""Disjoint LoCoMo-Plus retrieval-budget holdout after the observed top-16 loss.

This is a failure-driven retrieval dependency experiment, not an HNG feature change.
The observed n=30 slice is treated as development evidence. This runner freezes the
next SHA-ranked samples in each category and compares 16/32/64 retrieved turns with
full context. HNG and Strong are evaluated only at the 64-turn operating point.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from breakthrough_eval.scripts import locomo_plus_pilot as pilot  # noqa: E402


SCHEMA_VERSION = 1
BUDGETS = {
    "bm25_k16": (16, 18_000),
    "bm25_k32": (32, 36_000),
    "bm25_k64": (64, 72_000),
}
ARMS = ("full_context", *BUDGETS, "strong_k64", "hng_k64")
DEFAULT_OUTPUT = pilot.EVAL / "public" / "locomo_retrieval_budget_holdout"
DEVELOPMENT_PREPARED = pilot.EVAL / "public" / "locomo_plus_n30" / "PREPARED.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_head() -> str:
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    ).strip()


def select_samples_window(
    samples: Sequence[dict[str, Any]],
    *,
    per_category: int,
    offset: int,
) -> list[tuple[int, dict[str, Any]]]:
    if per_category < 1 or offset < 0:
        raise ValueError("per_category must be positive and offset non-negative")
    grouped: dict[str, list[tuple[int, dict[str, Any]]]] = collections.defaultdict(list)
    for index, sample in enumerate(samples):
        grouped[str(sample["category"])].append((index, sample))
    selected = []
    for category in pilot.CATEGORIES:
        rows = sorted(
            grouped.get(category, []),
            key=lambda item: pilot.stable_hash({
                "seed": pilot.SEED,
                "category": category,
                "index": item[0],
                "input_prompt_sha256": pilot.stable_hash(item[1]["input_prompt"]),
            }),
        )
        window = rows[offset:offset + per_category]
        if len(window) != per_category:
            raise ValueError(f"insufficient samples for category {category}")
        selected.extend(window)
    return sorted(selected, key=lambda item: item[0])


def manifest_identity(value: Mapping[str, Any]) -> str:
    keys = ("protocol", "selection", "seed", "sample_count", "parameters", "development_indices", "samples")
    return pilot.stable_hash({key: value.get(key) for key in keys})


def prepare(args: argparse.Namespace) -> tuple[list[tuple[int, dict[str, Any]]], dict[tuple[int, str], list[pilot.Candidate]], dict[str, Any]]:
    samples = json.loads(args.data.read_text(encoding="utf-8"))
    selected = select_samples_window(samples, per_category=args.per_category, offset=args.selection_offset)
    development = json.loads(args.development_prepared.read_text(encoding="utf-8"))
    development_indices = sorted(int(row["source_index"]) for row in development["samples"])
    selected_indices = [index for index, _sample in selected]
    overlap = sorted(set(development_indices) & set(selected_indices))
    if overlap:
        raise RuntimeError(f"holdout overlaps observed development slice: {overlap}")

    candidates: dict[tuple[int, str], list[pilot.Candidate]] = {}
    prepared_rows = []
    for index, sample in selected:
        memory, query, _full = pilot.split_memory_and_query(sample)
        corpus = pilot.dialogue_candidates(index, memory)
        ranked = pilot.bm25_rank(query, corpus)
        budget_rows = {}
        prior_ids: set[str] = set()
        monotonic = True
        for arm, (top_k, char_budget) in BUDGETS.items():
            chosen = pilot.select_context(ranked, top_k=top_k, char_budget=char_budget)
            candidates[(index, arm)] = chosen
            ids = [item.candidate_id for item in chosen]
            current_ids = set(ids)
            if prior_ids and not prior_ids.issubset(current_ids):
                monotonic = False
            prior_ids = current_ids
            budget_rows[arm] = {
                "top_k": top_k,
                "char_budget": char_budget,
                "selected_count": len(chosen),
                "selected_chars": sum(len(item.text) for item in chosen),
                "selected_candidate_ids": ids,
                "selected_candidate_sha256": pilot.stable_hash([item.payload() for item in chosen]),
            }
        prepared_rows.append({
            "sample_id": f"locomo-plus-{index:04d}",
            "source_index": index,
            "category": sample["category"],
            "input_prompt_sha256": pilot.stable_hash(sample["input_prompt"]),
            "trigger_sha256": pilot.stable_hash(sample["trigger"]),
            "memory_without_query_sha256": pilot.stable_hash(memory),
            "retrieval_corpus_count": len(corpus),
            "retrieval_corpus_sha256": pilot.stable_hash([item.payload() for item in corpus]),
            "candidate_sets_monotonic": monotonic,
            "budgets": budget_rows,
        })
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "protocol": "LoCoMo-Plus disjoint retrieval-budget holdout; NONCANONICAL",
        "selection": "next SHA-256-ranked window per category after observed n=30 development slice; answers/evidence excluded",
        "seed": pilot.SEED,
        "sample_count": len(selected),
        "parameters": {
            "per_category": args.per_category,
            "selection_offset": args.selection_offset,
            "budgets": {name: {"top_k": spec[0], "char_budget": spec[1]} for name, spec in BUDGETS.items()},
        },
        "development_manifest": args.development_prepared.resolve().relative_to(ROOT).as_posix(),
        "development_manifest_sha256": file_sha256(args.development_prepared),
        "development_indices": development_indices,
        "holdout_indices": selected_indices,
        "development_overlap": overlap,
        "samples": prepared_rows,
    }
    prepared_path = args.output / "PREPARED.json"
    if prepared_path.exists():
        existing = json.loads(prepared_path.read_text(encoding="utf-8"))
        if manifest_identity(existing) != manifest_identity(manifest):
            raise RuntimeError(f"refusing to overwrite incompatible prepared manifest: {prepared_path}")
        manifest = existing
    else:
        pilot.write_json(prepared_path, manifest)
    return selected, candidates, manifest


def inference_config_hash(args: argparse.Namespace) -> str:
    return pilot.stable_hash({
        "model": args.model,
        "model_digest": args.model_digest,
        "temperature": 0,
        "seed": pilot.SEED,
        "num_predict": args.num_predict,
        "judge_num_predict": 128,
        "num_ctx": 32768,
        "reader": "official_LoCoMo-Plus_build_model_input",
        "judge": "official_LoCoMo-Plus_prompt_and_parser",
    })


def reusable_events(raw_path: Path) -> dict[tuple[int, str, str], dict[str, Any]]:
    result = {}
    if not raw_path.exists():
        return result
    for line in raw_path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        required = ("prediction", "judge_score", "reader", "judge", "inference_config_sha256")
        if row.get("error") or not all(key in row for key in required):
            continue
        key = (int(row["source_index"]), str(row["prompt_sha256"]), str(row["inference_config_sha256"]))
        result.setdefault(key, row)
    return result


def completed_keys(raw_path: Path) -> set[tuple[int, str]]:
    """Return only complete, identity-valid prediction events."""
    if not raw_path.exists():
        return set()
    result = set()
    for line in raw_path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        identity_valid = row.get("arm") != "hng_k64" or row.get("source_identity") == "LoCoMo-Plus"
        if row.get("event") == "prediction" and not row.get("error") and identity_valid:
            result.add((int(row["source_index"]), str(row["arm"])))
    return result


def run(
    args: argparse.Namespace,
    selected: Sequence[tuple[int, dict[str, Any]]],
    candidates: Mapping[tuple[int, str], list[pilot.Candidate]],
) -> dict[str, Any]:
    raw_path = args.output / "raw" / "events.jsonl"
    completed = completed_keys(raw_path)
    reusable = reusable_events(raw_path)
    config_hash = inference_config_hash(args)
    preregistered_commit = git_head()
    for index, sample in selected:
        _memory, query, full = pilot.split_memory_and_query(sample)
        category = str(sample["category"])
        k64 = candidates[(index, "bm25_k64")]
        strong, strong_trace = pilot.strong_structured_govern(k64)
        hng, hng_trace = pilot.hng_govern(k64, source_identity="LoCoMo-Plus", source_id_prefix="locomo-plus")
        for arm in ARMS:
            if (index, arm) in completed:
                continue
            if arm == "full_context":
                chosen: Sequence[pilot.Candidate] = []
                body = full
                trace: Mapping[str, object] = {"mode": "official_full_context"}
                top_k = None
                char_budget = None
            elif arm in BUDGETS:
                chosen = candidates[(index, arm)]
                body = pilot.render_retrieved(chosen, query, category)
                trace = {"included": [item.candidate_id for item in chosen], "excluded": []}
                top_k, char_budget = BUDGETS[arm]
            elif arm == "strong_k64":
                chosen = strong
                body = pilot.render_retrieved(chosen, query, category)
                trace = strong_trace
                top_k, char_budget = BUDGETS["bm25_k64"]
            else:
                chosen = hng
                body = pilot.render_retrieved(chosen, query, category)
                trace = hng_trace
                top_k, char_budget = BUDGETS["bm25_k64"]
            messages = pilot.reader_messages(body, category)
            event: dict[str, Any] = {
                "schema_version": SCHEMA_VERSION,
                "event": "prediction",
                "created_at": utc_now(),
                "protocol": "locomo_plus_disjoint_retrieval_budget_holdout_noncanonical",
                "sample_id": f"locomo-plus-{index:04d}",
                "source_index": index,
                "category": category,
                "arm": arm,
                "top_k": top_k,
                "char_budget": char_budget,
                "model": args.model,
                "model_digest": args.model_digest,
                "preregistered_commit": preregistered_commit,
                "inference_config_sha256": config_hash,
                "source_identity": "LoCoMo-Plus" if arm == "hng_k64" else None,
                "candidate_pool_sha256": pilot.stable_hash([item.payload() for item in chosen]),
                "selected_candidate_ids": [item.candidate_id for item in chosen],
                "selected_context_chars": len(full) if arm == "full_context" else sum(len(item.text) for item in chosen),
                "governance_trace": trace,
                "prompt_sha256": pilot.stable_hash(messages),
            }
            reuse_key = (index, event["prompt_sha256"], config_hash)
            cached = reusable.get(reuse_key)
            if cached is not None:
                event.update({
                    "prediction": cached["prediction"],
                    "ground_truth": cached["ground_truth"],
                    "oracle_judge_evidence": cached["oracle_judge_evidence"],
                    "judge_score": cached["judge_score"],
                    "reader": cached["reader"],
                    "judge": cached["judge"],
                    "evaluation_reused": True,
                    "reused_from_arm": cached["arm"],
                    "reuse_reason": "same sample, prompt SHA-256, and full inference-configuration SHA-256",
                })
                pilot.append_jsonl(raw_path, event)
                continue
            try:
                prediction, reader = pilot.ollama_chat(
                    messages,
                    model=args.model,
                    endpoint=args.endpoint,
                    timeout=args.timeout,
                    num_predict=args.num_predict,
                )
                score, judge = pilot.judge_prediction(
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
                    "evaluation_reused": False,
                })
            except Exception as exc:
                event["error"] = f"{type(exc).__name__}: {exc}"
            pilot.append_jsonl(raw_path, event)
            if not event.get("error"):
                reusable.setdefault(reuse_key, dict(event))
    return compile_results(args, selected, raw_path.resolve())


def comparison(latest: Mapping[tuple[int, str], Mapping[str, Any]], left: str, right: str) -> dict[str, Any] | None:
    common = sorted(index for index, arm in latest if arm == left and (index, right) in latest)
    if not common:
        return None
    left_scores = [float(latest[(index, left)]["judge_score"]) for index in common]
    right_scores = [float(latest[(index, right)]["judge_score"]) for index in common]
    return {
        "paired_cases": len(common),
        "paired_bootstrap_mean_score": pilot.paired_bootstrap_delta(left_scores, right_scores),
        "mcnemar_judge_positive": pilot.mcnemar(
            [score > 0.5 for score in left_scores],
            [score > 0.5 for score in right_scores],
        ),
        "positive_threshold": "official judge score > 0.5",
    }


def compile_results(
    args: argparse.Namespace,
    selected: Sequence[tuple[int, Mapping[str, Any]]],
    raw_path: Path,
) -> dict[str, Any]:
    latest: dict[tuple[int, str], dict[str, Any]] = {}
    failures = []
    for line in raw_path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        if row.get("error"):
            failures.append(row)
        else:
            latest[(int(row["source_index"]), str(row["arm"]))] = row
    summaries = {}
    for arm in ARMS:
        rows = [latest[(index, arm)] for index, _sample in selected if (index, arm) in latest]
        scores = [float(row["judge_score"]) for row in rows]
        prompt_tokens = sum(int(row["reader"].get("prompt_eval_count") or 0) for row in rows)
        summaries[arm] = {
            "count": len(rows),
            "score": sum(scores),
            "average": statistics.mean(scores) if scores else None,
            "prompt_tokens": prompt_tokens,
            "mean_prompt_tokens_per_sample": prompt_tokens / len(rows) if rows else None,
            "score_per_1000_prompt_tokens": (sum(scores) * 1000 / prompt_tokens) if prompt_tokens else None,
            "mean_selected_context_chars": statistics.mean(float(row["selected_context_chars"]) for row in rows) if rows else None,
            "by_category": {
                category: {
                    "count": len(category_rows),
                    "score": sum(float(row["judge_score"]) for row in category_rows),
                    "average": statistics.mean(float(row["judge_score"]) for row in category_rows) if category_rows else None,
                }
                for category in pilot.CATEGORIES
                for category_rows in [[row for row in rows if row["category"] == category]]
            },
        }
    invariants = []
    for index, _sample in selected:
        rows = [latest.get((index, arm)) for arm in ("bm25_k64", "strong_k64", "hng_k64")]
        if all(row is not None for row in rows):
            invariants.append({
                "source_index": index,
                "candidate_pool_identical": len({row["candidate_pool_sha256"] for row in rows}) == 1,
                "selected_candidates_identical": len({tuple(row["selected_candidate_ids"]) for row in rows}) == 1,
                "prompt_identical": len({row["prompt_sha256"] for row in rows}) == 1,
                "model_and_config_identical": len({(row["model_digest"], row["inference_config_sha256"]) for row in rows}) == 1,
            })
    comparisons = {
        "hng_k64_vs_bm25_k64": comparison(latest, "hng_k64", "bm25_k64"),
        "hng_k64_vs_strong_k64": comparison(latest, "hng_k64", "strong_k64"),
        "bm25_k16_vs_full_context": comparison(latest, "bm25_k16", "full_context"),
        "bm25_k32_vs_full_context": comparison(latest, "bm25_k32", "full_context"),
        "bm25_k64_vs_full_context": comparison(latest, "bm25_k64", "full_context"),
        "bm25_k32_vs_bm25_k16": comparison(latest, "bm25_k32", "bm25_k16"),
        "bm25_k64_vs_bm25_k32": comparison(latest, "bm25_k64", "bm25_k32"),
        "bm25_k64_vs_bm25_k16_primary": comparison(latest, "bm25_k64", "bm25_k16"),
    }
    result = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "status": "complete" if all(value["count"] == len(selected) for value in summaries.values()) else "partial",
        "protocol": "LoCoMo-Plus disjoint retrieval-budget holdout; NONCANONICAL",
        "claim_boundary": (
            "Official public data/templates with a disjoint local holdout, but local reader/judge and BM25 turn retrieval; "
            "budget arms change candidates and isolate retrieval context, not governance."
        ),
        "model": args.model,
        "model_digest": args.model_digest,
        "preregistered_commit": next(
            (row.get("preregistered_commit") for row in latest.values() if row.get("preregistered_commit")),
            None,
        ),
        "sample_count": len(selected),
        "selection_offset_per_category": args.selection_offset,
        "summaries": summaries,
        "paired_statistics": comparisons,
        "fixed_candidate_k64_invariants": invariants,
        "all_fixed_candidate_k64_invariants_pass": bool(invariants) and all(
            all(row[key] for key in ("candidate_pool_identical", "selected_candidates_identical", "prompt_identical", "model_and_config_identical"))
            for row in invariants
        ),
        "inference_reuse": {
            "actual_inference_events": sum(not bool(row.get("evaluation_reused")) for row in latest.values()),
            "exact_prompt_reuse_events": sum(bool(row.get("evaluation_reused")) for row in latest.values()),
        },
        "failure_count": len(failures),
        "failures": failures,
        "raw_log": raw_path.relative_to(ROOT).as_posix(),
        "limitations": [
            "30-sample holdout rather than all 2,387 samples",
            "same frozen local 27B model is reader and judge",
            "BM25 dialogue-turn retrieval is not an official LoCoMo-Plus baseline",
            "retrieval budgets were chosen after observing the separate top-16 development loss",
        ],
    }
    pilot.write_json(args.output / "RESULTS.json", result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=pilot.DATA)
    parser.add_argument("--development-prepared", type=Path, default=DEVELOPMENT_PREPARED)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--per-category", type=int, default=5)
    parser.add_argument("--selection-offset", type=int, default=5)
    parser.add_argument("--model", default=pilot.DEFAULT_MODEL)
    parser.add_argument("--model-digest", default=pilot.DEFAULT_DIGEST)
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
