#!/usr/bin/env python3
"""Preregisterable disjoint LoCoMo-Plus neural-reranker holdout."""

from __future__ import annotations

import argparse
import collections
import json
import math
import statistics
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from breakthrough_eval import reranking  # noqa: E402
from breakthrough_eval.scripts import locomo_plus_pilot as pilot  # noqa: E402
from breakthrough_eval.scripts import locomo_retrieval_budget_holdout as budget  # noqa: E402

SCHEMA_VERSION = 1
ARMS = (
    "full_context", "bm25_k64", "dense_k64", "hybrid_k64", "reranked_k64",
    "strong_reranked_k64", "hng_reranked_k64",
)
TOP_K = 64
FIRST_STAGE_K = 128
CHAR_BUDGET = 72_000
RRF_K = 60
DEFAULT_EMBED_MODEL = "qwen3-embedding:0.6b"
DEFAULT_EMBED_DIGEST = "ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d"
DEFAULT_RERANKER_MODEL = "Qwen/Qwen3-Reranker-0.6B"
DEFAULT_RERANKER_REVISION = "e61197ed45024b0ed8a2d74b80b4d909f1255473"
DEFAULT_RERANKER_DIGEST = "27cd75a405b9c1b46b59abfd88aaa209e6fed2a1972cde9b70e7659537c5e65b"
DEFAULT_RERANKER_DIR = Path("C:/tmp/hng-qwen3-reranker-0.6b-e61197e")
DEFAULT_OUTPUT = pilot.EVAL / "public" / "locomo_reranker_holdout"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def git_head() -> str:
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
        cwd=ROOT, text=True, encoding="utf-8",
    ).strip()


def embed_texts(endpoint: str, model: str, texts: Sequence[str], timeout: float, batch_size: int = 64) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        payload = json.dumps({"model": model, "input": list(texts[start:start + batch_size]), "truncate": False}).encode()
        request = urllib.request.Request(
            endpoint.rstrip("/") + "/api/embed", data=payload,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        rows = body.get("embeddings")
        if not isinstance(rows, list) or len(rows) != len(texts[start:start + batch_size]):
            raise RuntimeError("embedding response row count mismatch")
        vectors.extend([[float(value) for value in row] for row in rows])
    if vectors and len({len(row) for row in vectors}) != 1:
        raise RuntimeError("embedding dimensions differ")
    return vectors


def query_text(query: str) -> str:
    return "Instruct: Retrieve prior dialogue turns needed to answer the memory question.\nQuery: " + query


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def rank_dense(candidates: Sequence[pilot.Candidate], query_vector: Sequence[float], document_vectors: Sequence[Sequence[float]]) -> list[pilot.Candidate]:
    if len(candidates) != len(document_vectors):
        raise ValueError("candidate/vector count mismatch")
    scored = [
        pilot.Candidate(**{**candidate.payload(), "bm25_score": cosine(query_vector, vector)})
        for candidate, vector in zip(candidates, document_vectors)
    ]
    return sorted(scored, key=lambda item: (-item.bm25_score, item.candidate_id))


def reciprocal_rank_fusion(
    candidates: Sequence[pilot.Candidate],
    bm25_ranked: Sequence[pilot.Candidate],
    dense_ranked: Sequence[pilot.Candidate],
    *,
    rrf_k: int = RRF_K,
) -> list[pilot.Candidate]:
    by_id = {item.candidate_id: item for item in candidates}
    scores: collections.defaultdict[str, float] = collections.defaultdict(float)
    for ranking in (bm25_ranked, dense_ranked):
        for rank, item in enumerate(ranking, 1):
            scores[item.candidate_id] += 1.0 / (rrf_k + rank)
    return [
        pilot.Candidate(**{**by_id[candidate_id].payload(), "bm25_score": score})
        for candidate_id, score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    ]


def rerank_union(
    corpus: Sequence[pilot.Candidate],
    bm25_ranked: Sequence[pilot.Candidate],
    dense_ranked: Sequence[pilot.Candidate],
    query: str,
    neural: Any,
    *,
    first_stage_k: int = FIRST_STAGE_K,
) -> tuple[list[pilot.Candidate], list[pilot.Candidate]]:
    """Cross-encode the deterministic union of two first-stage rankings."""

    by_id = {item.candidate_id: item for item in corpus}
    first_stage_ids = {
        item.candidate_id
        for item in [*bm25_ranked[:first_stage_k], *dense_ranked[:first_stage_k]]
    }
    first_stage = [by_id[candidate_id] for candidate_id in sorted(first_stage_ids)]
    scores = neural.score([(query, item.text) for item in first_stage])
    if len(scores) != len(first_stage):
        raise RuntimeError("reranker score count mismatch")
    reranked = sorted(
        [
            pilot.Candidate(**{**item.payload(), "bm25_score": score})
            for item, score in zip(first_stage, scores)
        ],
        key=lambda item: (-item.bm25_score, item.candidate_id),
    )
    return first_stage, reranked


def manifest_identity(value: Mapping[str, Any]) -> str:
    keys = ("protocol", "selection", "seed", "sample_count", "parameters", "excluded_indices", "samples")
    return pilot.stable_hash({key: value.get(key) for key in keys})


def completed_keys(raw_path: Path) -> set[tuple[int, str]]:
    if not raw_path.exists():
        return set()
    result = set()
    for line in raw_path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        identity_valid = row.get("arm") != "hng_reranked_k64" or row.get("source_identity") == "LoCoMo-Plus"
        if row.get("event") == "prediction" and not row.get("error") and identity_valid:
            result.add((int(row["source_index"]), str(row["arm"])))
    return result


def prepare(args: argparse.Namespace) -> tuple[list[tuple[int, dict[str, Any]]], dict[tuple[int, str], list[pilot.Candidate]], dict[str, Any]]:
    samples = json.loads(args.data.read_text(encoding="utf-8"))
    selected = budget.select_samples_window(samples, per_category=args.per_category, offset=args.selection_offset)
    excluded = budget.select_samples_window(samples, per_category=args.selection_offset, offset=0)
    excluded_indices = sorted(index for index, _sample in excluded)
    selected_indices = sorted(index for index, _sample in selected)
    if set(excluded_indices) & set(selected_indices):
        raise RuntimeError("reranker holdout overlaps earlier SHA-ranked windows")

    candidates: dict[tuple[int, str], list[pilot.Candidate]] = {}
    path = args.output / "PREPARED.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("holdout_indices") != selected_indices:
            raise RuntimeError(f"prepared holdout indices changed: {path}")
        for row in existing["samples"]:
            index = int(row["source_index"])
            for arm in ("bm25_k64", "dense_k64", "hybrid_k64", "reranked_k64"):
                candidates[(index, arm)] = [pilot.Candidate(**item) for item in row["arms"][arm]["candidates"]]
        return selected, candidates, existing

    weight_path = args.reranker_model_dir / "model.safetensors"
    if budget.file_sha256(weight_path) != args.reranker_digest:
        raise RuntimeError(f"reranker weight digest mismatch: {weight_path}")
    neural = reranking.Qwen3Reranker(reranking.RerankerConfig(
        args.reranker_model_dir,
        max_length=args.reranker_max_length,
        batch_size=args.reranker_batch_size,
        instruction=args.reranker_instruction,
    ))
    prepared_rows = []
    for ordinal, (index, sample) in enumerate(selected, 1):
        memory, query, _full = pilot.split_memory_and_query(sample)
        corpus = pilot.dialogue_candidates(index, memory)
        vectors = embed_texts(
            args.endpoint, args.embedding_model,
            [query_text(query), *[item.text for item in corpus]], args.timeout,
        )
        if not vectors or len(vectors[0]) != args.embedding_dimensions:
            raise RuntimeError(f"embedding dimension mismatch for sample {index}")
        bm25_ranked = pilot.bm25_rank(query, corpus)
        dense_ranked = rank_dense(corpus, vectors[0], vectors[1:])
        hybrid_ranked = reciprocal_rank_fusion(corpus, bm25_ranked, dense_ranked)
        first_stage, reranked_ranked = rerank_union(
            corpus, bm25_ranked, dense_ranked, query, neural
        )
        rankings = {
            "bm25_k64": bm25_ranked,
            "dense_k64": dense_ranked,
            "hybrid_k64": hybrid_ranked,
            "reranked_k64": reranked_ranked,
        }
        arms = {}
        for arm, ranked in rankings.items():
            chosen = pilot.select_context(ranked, top_k=TOP_K, char_budget=CHAR_BUDGET)
            candidates[(index, arm)] = chosen
            arms[arm] = {
                "selected_count": len(chosen),
                "selected_chars": sum(len(item.text) for item in chosen),
                "selected_candidate_ids": [item.candidate_id for item in chosen],
                "selected_candidate_sha256": pilot.stable_hash([item.payload() for item in chosen]),
                "top_scores": [round(float(item.bm25_score), 12) for item in chosen],
                "candidates": [item.payload() for item in chosen],
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
            "embedding_dimensions": len(vectors[0]),
            "reranker_first_stage_count": len(first_stage),
            "reranker_first_stage_sha256": pilot.stable_hash([item.payload() for item in first_stage]),
            "arms": arms,
        })
        print(json.dumps({"prepared": ordinal, "total": len(selected), "source_index": index}), flush=True)
    neural.close()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "protocol": "LoCoMo-Plus disjoint neural-reranker retrieval holdout; NONCANONICAL",
        "selection": "SHA-ranked positions 16-20 per category; positions 1-15 excluded; answers/evidence excluded from retrieval and reranking",
        "seed": pilot.SEED,
        "sample_count": len(selected),
        "parameters": {
            "selection_offset": args.selection_offset, "per_category": args.per_category,
            "top_k": TOP_K, "first_stage_k_per_retriever": FIRST_STAGE_K,
            "char_budget": CHAR_BUDGET, "rrf_k": RRF_K,
            "embedding_model": args.embedding_model, "embedding_model_digest": args.embedding_digest,
            "embedding_dimensions": args.embedding_dimensions,
            "embedding_query_instruction": query_text("{query}"),
            "reranker_model": args.reranker_model,
            "reranker_revision": args.reranker_revision,
            "reranker_weight_sha256": args.reranker_digest,
            "reranker_max_length": args.reranker_max_length,
            "reranker_batch_size": args.reranker_batch_size,
            "reranker_instruction": args.reranker_instruction,
        },
        "excluded_indices": excluded_indices,
        "holdout_indices": selected_indices,
        "development_overlap": [],
        "samples": prepared_rows,
    }
    pilot.write_json(path, manifest)
    return selected, candidates, manifest


def inference_config_hash(args: argparse.Namespace) -> str:
    return pilot.stable_hash({
        "reader_model": args.model, "reader_model_digest": args.model_digest,
        "embedding_model": args.embedding_model, "embedding_model_digest": args.embedding_digest,
        "reranker_model": args.reranker_model, "reranker_revision": args.reranker_revision,
        "reranker_weight_sha256": args.reranker_digest,
        "temperature": 0, "seed": pilot.SEED, "num_predict": args.num_predict,
        "judge_num_predict": 128, "num_ctx": 32768,
        "reader": "official_LoCoMo-Plus_build_model_input",
        "judge": "official_LoCoMo-Plus_prompt_and_parser",
    })


def run(args: argparse.Namespace, selected: Sequence[tuple[int, dict[str, Any]]], candidates: Mapping[tuple[int, str], list[pilot.Candidate]]) -> dict[str, Any]:
    raw_path = args.output / "raw" / "events.jsonl"
    completed = completed_keys(raw_path)
    reusable = budget.reusable_events(raw_path)
    config_hash = inference_config_hash(args)
    preregistered_commit = git_head()
    for index, sample in selected:
        _memory, query, full = pilot.split_memory_and_query(sample)
        category = str(sample["category"])
        reranked = candidates[(index, "reranked_k64")]
        strong, strong_trace = pilot.strong_structured_govern(reranked)
        hng, hng_trace = pilot.hng_govern(reranked, source_identity="LoCoMo-Plus", source_id_prefix="locomo-plus")
        for arm in ARMS:
            if (index, arm) in completed:
                continue
            if arm == "full_context":
                chosen: Sequence[pilot.Candidate] = []
                body, trace = full, {"mode": "official_full_context"}
            elif arm in ("bm25_k64", "dense_k64", "hybrid_k64", "reranked_k64"):
                chosen = candidates[(index, arm)]
                body, trace = pilot.render_retrieved(chosen, query, category), {"included": [item.candidate_id for item in chosen], "excluded": []}
            elif arm == "strong_reranked_k64":
                chosen, trace = strong, strong_trace
                body = pilot.render_retrieved(chosen, query, category)
            else:
                chosen, trace = hng, hng_trace
                body = pilot.render_retrieved(chosen, query, category)
            messages = pilot.reader_messages(body, category)
            event: dict[str, Any] = {
                "schema_version": SCHEMA_VERSION, "event": "prediction", "created_at": utc_now(),
                "protocol": "locomo_plus_disjoint_neural_reranker_holdout_noncanonical",
                "sample_id": f"locomo-plus-{index:04d}", "source_index": index,
                "category": category, "arm": arm, "top_k": None if arm == "full_context" else TOP_K,
                "char_budget": None if arm == "full_context" else CHAR_BUDGET,
                "model": args.model, "model_digest": args.model_digest,
                "embedding_model": args.embedding_model, "embedding_model_digest": args.embedding_digest,
                "reranker_model": args.reranker_model, "reranker_revision": args.reranker_revision,
                "reranker_weight_sha256": args.reranker_digest,
                "preregistered_commit": preregistered_commit, "inference_config_sha256": config_hash,
                "source_identity": "LoCoMo-Plus" if arm == "hng_reranked_k64" else None,
                "candidate_pool_sha256": pilot.stable_hash([item.payload() for item in chosen]),
                "selected_candidate_ids": [item.candidate_id for item in chosen],
                "selected_context_chars": len(full) if arm == "full_context" else sum(len(item.text) for item in chosen),
                "governance_trace": trace, "prompt_sha256": pilot.stable_hash(messages),
            }
            reuse_key = (index, event["prompt_sha256"], config_hash)
            cached = reusable.get(reuse_key)
            if cached is not None:
                event.update({key: cached[key] for key in ("prediction", "ground_truth", "oracle_judge_evidence", "judge_score", "reader", "judge")})
                event.update({"evaluation_reused": True, "reused_from_arm": cached["arm"], "reuse_reason": "same sample, prompt SHA-256, and full inference-configuration SHA-256"})
                pilot.append_jsonl(raw_path, event)
                continue
            try:
                prediction, reader = pilot.ollama_chat(messages, model=args.model, endpoint=args.endpoint, timeout=args.timeout, num_predict=args.num_predict)
                score, judge = pilot.judge_prediction(sample, prediction, model=args.model, endpoint=args.endpoint, timeout=args.timeout)
                event.update({"prediction": prediction, "ground_truth": sample.get("answer", ""), "oracle_judge_evidence": sample.get("evidence", ""), "judge_score": score, "reader": reader, "judge": judge, "evaluation_reused": False})
            except Exception as exc:
                event["error"] = f"{type(exc).__name__}: {exc}"
            pilot.append_jsonl(raw_path, event)
            if not event.get("error"):
                reusable.setdefault(reuse_key, dict(event))
    return compile_results(args, selected, raw_path.resolve())


def compile_results(args: argparse.Namespace, selected: Sequence[tuple[int, Mapping[str, Any]]], raw_path: Path) -> dict[str, Any]:
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
        tokens = sum(int(row["reader"].get("prompt_eval_count") or 0) for row in rows)
        summaries[arm] = {
            "count": len(rows), "score": sum(scores), "average": statistics.mean(scores) if scores else None,
            "prompt_tokens": tokens, "mean_prompt_tokens_per_sample": tokens / len(rows) if rows else None,
            "mean_selected_context_chars": statistics.mean(float(row["selected_context_chars"]) for row in rows) if rows else None,
        }
    comparisons = {
        "dense_k64_vs_bm25_k64": budget.comparison(latest, "dense_k64", "bm25_k64"),
        "hybrid_k64_vs_bm25_k64": budget.comparison(latest, "hybrid_k64", "bm25_k64"),
        "reranked_k64_vs_hybrid_k64_primary": budget.comparison(latest, "reranked_k64", "hybrid_k64"),
        "reranked_k64_vs_dense_k64": budget.comparison(latest, "reranked_k64", "dense_k64"),
        "reranked_k64_vs_bm25_k64": budget.comparison(latest, "reranked_k64", "bm25_k64"),
        "reranked_k64_vs_full_context": budget.comparison(latest, "reranked_k64", "full_context"),
        "hng_reranked_k64_vs_reranked_k64": budget.comparison(latest, "hng_reranked_k64", "reranked_k64"),
        "hng_reranked_k64_vs_strong_reranked_k64": budget.comparison(latest, "hng_reranked_k64", "strong_reranked_k64"),
    }
    invariants = []
    for index, _sample in selected:
        rows = [latest.get((index, arm)) for arm in ("reranked_k64", "strong_reranked_k64", "hng_reranked_k64")]
        if all(row is not None for row in rows):
            invariants.append({
                "source_index": index,
                "candidate_pool_identical": len({row["candidate_pool_sha256"] for row in rows}) == 1,
                "selected_candidates_identical": len({tuple(row["selected_candidate_ids"]) for row in rows}) == 1,
                "prompt_identical": len({row["prompt_sha256"] for row in rows}) == 1,
                "model_and_config_identical": len({(row["model_digest"], row["inference_config_sha256"]) for row in rows}) == 1,
            })
    result = {
        "schema_version": SCHEMA_VERSION, "created_at": utc_now(),
        "status": "complete" if all(value["count"] == len(selected) for value in summaries.values()) else "partial",
        "protocol": "LoCoMo-Plus disjoint neural-reranker retrieval holdout; NONCANONICAL",
        "claim_boundary": "Official public data/templates with local BM25/dense/RRF retrieval, a pinned Qwen3 cross-encoder reranker, and local reader/judge; not an official leaderboard protocol.",
        "model": args.model, "model_digest": args.model_digest,
        "embedding_model": args.embedding_model, "embedding_model_digest": args.embedding_digest,
        "reranker_model": args.reranker_model, "reranker_revision": args.reranker_revision,
        "reranker_weight_sha256": args.reranker_digest,
        "preregistered_commit": next((row.get("preregistered_commit") for row in latest.values() if row.get("preregistered_commit")), None),
        "sample_count": len(selected), "selection_offset_per_category": args.selection_offset,
        "summaries": summaries, "paired_statistics": comparisons,
        "fixed_candidate_reranked_invariants": invariants,
        "all_fixed_candidate_reranked_invariants_pass": bool(invariants) and all(all(row[key] for key in ("candidate_pool_identical", "selected_candidates_identical", "prompt_identical", "model_and_config_identical")) for row in invariants),
        "inference_reuse": {"actual_inference_events": sum(not bool(row.get("evaluation_reused")) for row in latest.values()), "exact_prompt_reuse_events": sum(bool(row.get("evaluation_reused")) for row in latest.values())},
        "failure_count": len(failures), "failures": failures, "raw_log": raw_path.relative_to(ROOT).as_posix(),
        "limitations": ["30-sample holdout rather than all 2,387 samples", "same frozen local 27B model is reader and judge", "reranker and embedding model share the Qwen3 family", "retrieval approaches change candidates; only reranked/Strong/HNG isolates governance"],
    }
    pilot.write_json(args.output / "RESULTS.json", result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=pilot.DATA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--per-category", type=int, default=5)
    parser.add_argument("--selection-offset", type=int, default=15)
    parser.add_argument("--model", default=pilot.DEFAULT_MODEL)
    parser.add_argument("--model-digest", default=pilot.DEFAULT_DIGEST)
    parser.add_argument("--embedding-model", default=DEFAULT_EMBED_MODEL)
    parser.add_argument("--embedding-digest", default=DEFAULT_EMBED_DIGEST)
    parser.add_argument("--embedding-dimensions", type=int, default=1024)
    parser.add_argument("--reranker-model", default=DEFAULT_RERANKER_MODEL)
    parser.add_argument("--reranker-revision", default=DEFAULT_RERANKER_REVISION)
    parser.add_argument("--reranker-digest", default=DEFAULT_RERANKER_DIGEST)
    parser.add_argument("--reranker-model-dir", type=Path, default=DEFAULT_RERANKER_DIR)
    parser.add_argument("--reranker-max-length", type=int, default=512)
    parser.add_argument("--reranker-batch-size", type=int, default=16)
    parser.add_argument("--reranker-instruction", default=reranking.DEFAULT_INSTRUCTION)
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

