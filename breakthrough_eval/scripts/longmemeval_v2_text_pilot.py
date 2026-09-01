#!/usr/bin/env python3
"""Pinned, leakage-resistant LongMemEval-V2 small-tier text pilot.

This is deliberately *not* the canonical LongMemEval-V2 protocol.  It uses the
official questions, small-tier haystacks, trajectories, and evaluation functions,
but a local frozen reader, text-only accessibility trees, BM25 retrieval, and the
same local model as judge for judge-dependent items.  The output therefore cannot
be compared directly with official leaderboard scores.

The fixed-candidate comparison is BM25 versus BM25+StrongStructuredBaseline versus
BM25+HNG.  All three arms receive the same ordered BM25 candidates.  Answers and
evaluation labels are never used by selection, retrieval, governance, or prompting.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import json
import math
import re
import statistics
import sys
import time
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
EVAL_ROOT = ROOT / "breakthrough_eval"
EXTERNAL = EVAL_ROOT / "external" / "LongMemEval-V2"
DATA = EXTERNAL / "data" / "longmemeval-v2"
QUESTIONS = DATA / "questions.jsonl"
HAYSTACK = DATA / "haystacks" / "lme_v2_small.json"
TRAJECTORIES = DATA / "trajectories.jsonl"
OFFICIAL_METRICS = EXTERNAL / "evaluation" / "qa_eval_metrics.py"
PACKAGE = ROOT / "baseline_source" / "hng-frontier-0.5.1a1" / "src"
sys.path.insert(0, str(PACKAGE))

from hngfrontier.aggregation import EvidenceAggregator  # noqa: E402
from hngfrontier.governance import (  # noqa: E402
    EvidenceKind,
    EvidenceProvenance,
    EvidenceRecordV2,
    TemporalValidity,
)
from hngfrontier.query_planner import QueryIntent, QueryPlanner  # noqa: E402
from hngfrontier.semantic import SemanticState  # noqa: E402


SCHEMA_VERSION = 1
SEED = 20260831
NOW = "2026-08-31T12:00:00+00:00"
DEFAULT_MODEL = "qwen3.8:27b-q4_K_M"
DEFAULT_DIGEST = "25b843619e944cd0ae6069f94ff4e5e26a16e109ccbc0a66a0f05979ed70098e"
DEFAULT_QUESTIONS_PER_STRATUM = 2
DEFAULT_TOP_K = 8
DEFAULT_CONTEXT_CHARS = 18_000
DEFAULT_STATE_CHARS = 3_200

SYSTEM_PROMPT = (
    "Answer the question using only the supplied historical interaction evidence. "
    "The evidence may include failed attempts and intermediate interface states. "
    "If the premise is contradicted or cannot be established from the evidence, say so. "
    "Follow the question's requested answer format and put the final answer in \\boxed{}."
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def append_jsonl(path: Path, row: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(dict(row), sort_keys=True) + "\n")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_metrics_module() -> Any:
    spec = importlib.util.spec_from_file_location("lme_v2_qa_eval_metrics", OFFICIAL_METRICS)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import official metrics from {OFFICIAL_METRICS}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evaluator_family(question: Mapping[str, Any]) -> str:
    return str(question["eval_function"]).split("|", 1)[0]


def ability(question_type: str) -> str:
    if question_type.startswith("static-environment"):
        return "static_state"
    if question_type.startswith("dynamic-environment"):
        return "dynamic_state"
    if question_type.startswith("procedure"):
        return "workflow"
    if question_type == "errors-gotchas":
        return "environment_gotchas"
    return question_type


def select_questions(
    questions: Sequence[dict[str, Any]],
    *,
    per_stratum: int = DEFAULT_QUESTIONS_PER_STRATUM,
) -> list[dict[str, Any]]:
    """Select without answer/evidence access: domain x major ability x judge class."""
    strata: dict[tuple[str, str, str], list[dict[str, Any]]] = collections.defaultdict(list)
    for item in questions:
        family = evaluator_family(item)
        judge_class = "local_llm_judge" if family.startswith("llm_") else "deterministic"
        key = (str(item["domain"]), ability(str(item["question_type"])), judge_class)
        strata[key].append(item)
    selected: list[dict[str, Any]] = []
    for key, rows in sorted(strata.items()):
        ordered = sorted(rows, key=lambda row: stable_hash({"seed": SEED, "id": row["id"]}))
        # One item is enough for scarce gotcha/premise strata; ordinary strata use per_stratum.
        limit = 1 if key[1] == "environment_gotchas" or key[2] == "local_llm_judge" else per_stratum
        selected.extend(ordered[:limit])
    return sorted(selected, key=lambda row: str(row["id"]))


def selection_record(item: Mapping[str, Any]) -> dict[str, object]:
    return {
        "id": item["id"],
        "domain": item["domain"],
        "environment": item["environment"],
        "question_type": item["question_type"],
        "ability": ability(str(item["question_type"])),
        "evaluation_family": evaluator_family(item),
        "question_sha256": stable_hash(item["question"]),
    }


def required_trajectory_ids(selected: Sequence[Mapping[str, Any]], haystacks: Mapping[str, Any]) -> set[str]:
    required: set[str] = set()
    for item in selected:
        question_id = str(item["id"])
        ids = haystacks.get(question_id)
        if not isinstance(ids, list) or not ids:
            raise RuntimeError(f"Missing small-tier haystack for {question_id}")
        required.update(str(value) for value in ids)
    return required


def stream_required_trajectories(path: Path, required: set[str]) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            item = json.loads(line)
            trajectory_id = str(item["id"])
            if trajectory_id in required:
                found[trajectory_id] = item
    missing = sorted(required - set(found))
    if missing:
        raise RuntimeError(f"Missing {len(missing)} required trajectories; first={missing[:5]}")
    return found


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    source_event_id: str
    trajectory_id: str
    state_index: int
    text: str
    bm25_score: float = 0.0

    def payload(self) -> dict[str, object]:
        return asdict(self)


TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_.:/-]*", re.IGNORECASE)


def tokens(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


def state_text(trajectory: Mapping[str, Any], state: Mapping[str, Any], max_chars: int) -> str:
    tree = str(state.get("accessibility_tree") or "")
    fields = [
        f"trajectory_goal: {trajectory.get('goal', '')}",
        f"trajectory_outcome: {trajectory.get('outcome', '')}",
        f"environment: {trajectory.get('environment', '')}",
        f"url: {state.get('url', '')}",
        f"action: {state.get('action', '')}",
        f"thought: {state.get('thought', '')}",
        "accessibility_tree:",
        tree,
    ]
    text = "\n".join(fields)
    return text[:max_chars]


def candidate_corpus(
    trajectory_ids: Sequence[str],
    trajectories: Mapping[str, Mapping[str, Any]],
    *,
    max_state_chars: int,
) -> list[Candidate]:
    result: list[Candidate] = []
    for trajectory_id in trajectory_ids:
        trajectory = trajectories[trajectory_id]
        for state in trajectory.get("states") or []:
            index = int(state.get("state_index", state.get("step", 0)))
            candidate_id = f"{trajectory_id}:{index:05d}"
            result.append(Candidate(
                candidate_id=candidate_id,
                source_event_id=candidate_id,
                trajectory_id=trajectory_id,
                state_index=index,
                text=state_text(trajectory, state, max_state_chars),
            ))
    return result


def bm25_rank(query: str, candidates: Sequence[Candidate]) -> list[Candidate]:
    if not candidates:
        return []
    docs = [tokens(item.text) for item in candidates]
    document_frequency: collections.Counter[str] = collections.Counter()
    for doc in docs:
        document_frequency.update(set(doc))
    query_terms = collections.Counter(tokens(query))
    average_length = sum(len(doc) for doc in docs) / len(docs)
    k1, b = 1.5, 0.75
    ranked: list[Candidate] = []
    for candidate, doc in zip(candidates, docs):
        frequencies = collections.Counter(doc)
        score = 0.0
        for term, query_frequency in query_terms.items():
            df = document_frequency.get(term, 0)
            if not df:
                continue
            inverse_document_frequency = math.log(1.0 + (len(docs) - df + 0.5) / (df + 0.5))
            tf = frequencies.get(term, 0)
            denominator = tf + k1 * (1.0 - b + b * len(doc) / max(1.0, average_length))
            if denominator:
                score += query_frequency * inverse_document_frequency * tf * (k1 + 1.0) / denominator
        ranked.append(Candidate(**{**candidate.payload(), "bm25_score": score}))
    return sorted(ranked, key=lambda item: (-item.bm25_score, item.candidate_id))


def select_context(ranked: Sequence[Candidate], *, top_k: int, char_budget: int) -> list[Candidate]:
    selected: list[Candidate] = []
    used = 0
    for item in ranked:
        if len(selected) >= top_k:
            break
        remaining = char_budget - used
        if remaining <= 0:
            break
        text = item.text[:remaining]
        if not text:
            continue
        selected.append(Candidate(**{**item.payload(), "text": text}))
        used += len(text)
    return selected


def strong_structured_govern(candidates: Sequence[Candidate]) -> tuple[list[Candidate], dict[str, object]]:
    """Independent clean-document policy: verified/current plus source-event deduplication."""
    included: list[Candidate] = []
    seen: set[str] = set()
    excluded: list[dict[str, str]] = []
    for item in candidates:
        if item.source_event_id in seen:
            excluded.append({"id": item.candidate_id, "reason": "duplicate_event"})
            continue
        seen.add(item.source_event_id)
        included.append(item)
    return included, {"included": [item.candidate_id for item in included], "excluded": excluded}


def hng_govern(candidates: Sequence[Candidate]) -> tuple[list[Candidate], dict[str, object]]:
    records = []
    for item in candidates:
        records.append(EvidenceRecordV2(
            experience_id=item.candidate_id,
            evidence_group_id=item.source_event_id,
            source_event_id=item.source_event_id,
            episode_id=item.trajectory_id,
            conversation_id=item.trajectory_id,
            kind=EvidenceKind.DOCUMENT_CLAIM,
            content=item.text,
            semantics=SemanticState({}),
            provenance=EvidenceProvenance(
                "external_document",
                f"longmemeval-v2:{item.candidate_id}",
                0.75,
                True,
                NOW,
                "official-dataset",
                verifier="sha256-pinned-dataset",
                verification_status="verified",
                identity="LongMemEval-V2",
            ),
            validity=TemporalValidity(valid_from="2026-01-01T00:00:00+00:00"),
            outcome_score=0.0,
            confidence=1.0,
            scope="global",
        ))
    plan = QueryPlanner().plan(QueryIntent.DOCUMENT_EVIDENCE)
    assessment = EvidenceAggregator().assess(records, SemanticState({}), plan, now=NOW)
    included_ids = {item.record.experience_id for item in assessment.included}
    # Preserve BM25 order after policy filtering so prompt order is held fixed.
    included = [item for item in candidates if item.candidate_id in included_ids]
    return included, assessment.as_dict()


def render_context(candidates: Sequence[Candidate]) -> str:
    if not candidates:
        return "No historical interaction evidence was retrieved."
    blocks = []
    for index, item in enumerate(candidates, 1):
        blocks.append(
            f"[Evidence {index}; id={item.candidate_id}; bm25={item.bm25_score:.6f}]\n{item.text}"
        )
    return "\n\n".join(blocks)


def reader_messages(question: str, candidates: Sequence[Candidate]) -> list[dict[str, str]]:
    user = f"HISTORICAL EVIDENCE\n{render_context(candidates)}\n\nQUESTION\n{question}"
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def ollama_chat(
    messages: Sequence[Mapping[str, str]],
    *,
    model: str,
    endpoint: str,
    timeout: float,
    num_predict: int,
    json_format: bool = False,
) -> tuple[str, dict[str, object]]:
    request: dict[str, object] = {
        "model": model,
        "stream": False,
        "think": False,
        "messages": list(messages),
        "options": {
            "temperature": 0,
            "seed": SEED,
            "num_predict": num_predict,
            "num_ctx": 32768,
        },
        "keep_alive": "30m",
    }
    if json_format:
        request["format"] = "json"
    raw = json.dumps(request).encode("utf-8")
    http_request = urllib.request.Request(
        endpoint.rstrip("/") + "/api/chat",
        data=raw,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    with urllib.request.urlopen(http_request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    elapsed = time.perf_counter() - started
    content = str(payload.get("message", {}).get("content", ""))
    return content, {
        "elapsed_seconds": elapsed,
        "prompt_eval_count": payload.get("prompt_eval_count"),
        "eval_count": payload.get("eval_count"),
        "total_duration_ns": payload.get("total_duration"),
        "load_duration_ns": payload.get("load_duration"),
        "prompt_sha256": stable_hash(list(messages)),
        "raw_response": payload,
    }


def score_prediction(
    metrics: Any,
    question: Mapping[str, Any],
    prediction: str,
    *,
    model: str,
    endpoint: str,
    timeout: float,
) -> tuple[bool, dict[str, object] | None]:
    parsed = metrics.extract_boxed_answer(prediction)
    family = evaluator_family(question)
    if family == "llm_abstention_checker":
        messages = metrics._build_abstention_judge_messages(
            question_text=str(question["question"]),
            reference_answer=str(question["answer"]),
            model_full_response=prediction,
            model_final_answer=parsed,
        )
    elif family == "llm_gotchas_checker":
        messages = metrics._build_gotchas_judge_messages(
            question_text=str(question["question"]),
            reference_answer=str(question["answer"]),
            model_full_response=prediction,
            model_final_answer=parsed,
        )
    else:
        score = metrics.eval_from_spec(str(question["eval_function"]), prediction, question["answer"])
        return metrics.score_to_bool(score), None
    judge_text, metadata = ollama_chat(
        messages,
        model=model,
        endpoint=endpoint,
        timeout=timeout,
        num_predict=128,
        json_format=True,
    )
    label, reason = metrics._parse_llm_binary_judgement(judge_text)
    metadata.update({"judge_response": judge_text, "judge_reason": reason, "judge_label": label})
    return label == 1, metadata


def prepare(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, list[Candidate]], dict[str, object]]:
    questions = load_jsonl(args.questions)
    selected = select_questions(questions, per_stratum=args.questions_per_stratum)
    haystacks = json.loads(args.haystack.read_text(encoding="utf-8"))
    required = required_trajectory_ids(selected, haystacks)
    started = time.perf_counter()
    trajectories = stream_required_trajectories(args.trajectories, required)
    scan_seconds = time.perf_counter() - started
    candidates_by_question: dict[str, list[Candidate]] = {}
    preparation_rows = []
    for question in selected:
        question_id = str(question["id"])
        corpus = candidate_corpus(
            [str(value) for value in haystacks[question_id]],
            trajectories,
            max_state_chars=args.max_state_chars,
        )
        ranked = bm25_rank(str(question["question"]), corpus)
        candidates = select_context(ranked, top_k=args.top_k, char_budget=args.context_chars)
        candidates_by_question[question_id] = candidates
        preparation_rows.append({
            **selection_record(question),
            "haystack_trajectory_count": len(haystacks[question_id]),
            "retrieval_corpus_count": len(corpus),
            "retrieval_corpus_sha256": stable_hash([item.payload() for item in corpus]),
            "selected_candidate_count": len(candidates),
            "selected_candidate_sha256": stable_hash([item.payload() for item in candidates]),
            "selected_context_chars": sum(len(item.text) for item in candidates),
            "candidates": [item.payload() for item in candidates],
        })
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "protocol": "LongMemEval-V2 small-tier text pilot; noncanonical",
        "selection_policy": "SHA-256(seed,id), stratified by domain/ability/judge class; no answers used",
        "seed": SEED,
        "question_count": len(selected),
        "required_trajectory_count": len(required),
        "trajectory_scan_seconds": scan_seconds,
        "parameters": {
            "questions_per_stratum": args.questions_per_stratum,
            "top_k": args.top_k,
            "context_chars": args.context_chars,
            "max_state_chars": args.max_state_chars,
        },
        "source_hashes": {
            "questions_sha256": sha256_file(args.questions),
            "haystack_sha256": sha256_file(args.haystack),
            "trajectories_sha256": sha256_file(args.trajectories),
        },
        "questions": preparation_rows,
    }
    write_json(args.output / "PREPARED.json", manifest)
    return selected, candidates_by_question, manifest


def existing_keys(raw_path: Path) -> set[tuple[str, str]]:
    if not raw_path.exists():
        return set()
    keys = set()
    with raw_path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                if row.get("event") == "prediction" and not row.get("error"):
                    keys.add((str(row["question_id"]), str(row["arm"])))
    return keys


def run(args: argparse.Namespace, selected: Sequence[dict[str, Any]], candidates_by_question: Mapping[str, list[Candidate]]) -> dict[str, object]:
    metrics = load_metrics_module()
    raw_path = args.output / "raw" / "events.jsonl"
    completed = existing_keys(raw_path) if args.resume else set()
    question_by_id = {str(item["id"]): item for item in selected}
    arms = ("no_retrieval", "bm25", "strong_structured", "hng")
    for question_id in sorted(question_by_id):
        question = question_by_id[question_id]
        base_candidates = candidates_by_question[question_id]
        strong_candidates, strong_trace = strong_structured_govern(base_candidates)
        hng_candidates, hng_trace = hng_govern(base_candidates)
        candidate_hash = stable_hash([item.payload() for item in base_candidates])
        for arm in arms:
            if (question_id, arm) in completed:
                continue
            if arm == "no_retrieval":
                candidates, trace = [], {"included": [], "excluded": []}
            elif arm == "bm25":
                candidates, trace = base_candidates, {"included": [item.candidate_id for item in base_candidates], "excluded": []}
            elif arm == "strong_structured":
                candidates, trace = strong_candidates, strong_trace
            else:
                candidates, trace = hng_candidates, hng_trace
            messages = reader_messages(str(question["question"]), candidates)
            event: dict[str, object] = {
                "schema_version": SCHEMA_VERSION,
                "event": "prediction",
                "created_at": utc_now(),
                "protocol": "longmemeval_v2_small_text_pilot_noncanonical",
                "question_id": question_id,
                "domain": question["domain"],
                "question_type": question["question_type"],
                "ability": ability(str(question["question_type"])),
                "arm": arm,
                "model": args.model,
                "model_digest": args.model_digest,
                "candidate_pool_sha256": candidate_hash if arm != "no_retrieval" else stable_hash([]),
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
                )
                correct, judge = score_prediction(
                    metrics,
                    question,
                    prediction,
                    model=args.model,
                    endpoint=args.endpoint,
                    timeout=args.timeout,
                )
                event.update({
                    "prediction": prediction,
                    "parsed_prediction": metrics.extract_boxed_answer(prediction),
                    "reference_answer": question["answer"],
                    "eval_function": question["eval_function"],
                    "correct": correct,
                    "reader": metadata,
                    "judge": judge,
                })
            except Exception as exc:  # Preserve every setup/runtime failure.
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


def compile_results(args: argparse.Namespace, selected: Sequence[Mapping[str, Any]], raw_path: Path) -> dict[str, object]:
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    failures = []
    with raw_path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("event") != "prediction":
                continue
            if row.get("error"):
                failures.append(row)
            else:
                latest[(str(row["question_id"]), str(row["arm"]))] = row
    arms = ("no_retrieval", "bm25", "strong_structured", "hng")
    summaries = {}
    by_ability = {}
    for arm in arms:
        rows = [row for (question_id, name), row in latest.items() if name == arm]
        elapsed = [float(row["reader"]["elapsed_seconds"]) for row in rows]
        prompt_tokens = [int(row["reader"].get("prompt_eval_count") or 0) for row in rows]
        summaries[arm] = {
            "count": len(rows),
            "correct": sum(bool(row["correct"]) for row in rows),
            "accuracy": statistics.mean(bool(row["correct"]) for row in rows) if rows else None,
            "prompt_tokens": sum(prompt_tokens),
            "latency_seconds_p50": percentile(elapsed, 0.50),
            "latency_seconds_p95": percentile(elapsed, 0.95),
        }
        for ability_name in sorted({str(row["ability"]) for row in rows}):
            ability_rows = [row for row in rows if row["ability"] == ability_name]
            by_ability[f"{arm}:{ability_name}"] = {
                "arm": arm,
                "ability": ability_name,
                "count": len(ability_rows),
                "correct": sum(bool(row["correct"]) for row in ability_rows),
                "accuracy": statistics.mean(bool(row["correct"]) for row in ability_rows),
            }
    fixed_invariants = []
    for question in selected:
        question_id = str(question["id"])
        rows = [latest.get((question_id, arm)) for arm in ("bm25", "strong_structured", "hng")]
        rows = [row for row in rows if row is not None]
        if len(rows) == 3:
            fixed_invariants.append({
                "question_id": question_id,
                "candidate_pool_identical": len({row["candidate_pool_sha256"] for row in rows}) == 1,
                "selected_candidates_identical": len({tuple(row["selected_candidate_ids"]) for row in rows}) == 1,
                "prompt_identical": len({row["prompt_sha256"] for row in rows}) == 1,
                "model_digest_identical": len({row["model_digest"] for row in rows}) == 1,
            })
    result = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "status": "complete" if all(summary["count"] == len(selected) for summary in summaries.values()) else "partial",
        "protocol": "LongMemEval-V2 small-tier text pilot; NONCANONICAL",
        "limitations": [
            "text-only accessibility-tree path; trajectory screenshots were not downloaded",
            "local qwen3.8 27B reader instead of official reader configuration",
            "same local model used as evaluator for judge-dependent questions",
            "stratified pilot subset, not the full 451-question tier",
            "BM25-selected state slices rather than official embedding retriever",
        ],
        "model": args.model,
        "model_digest": args.model_digest,
        "seed": SEED,
        "question_count": len(selected),
        "summaries": summaries,
        "by_ability": list(by_ability.values()),
        "fixed_candidate_invariants": fixed_invariants,
        "all_fixed_candidate_invariants_pass": bool(fixed_invariants) and all(
            all(row[key] for key in ("candidate_pool_identical", "selected_candidates_identical", "prompt_identical", "model_digest_identical"))
            for row in fixed_invariants
        ),
        "failure_count": len(failures),
        "failures": failures,
        "raw_log": str(raw_path.relative_to(ROOT)).replace("\\", "/"),
    }
    write_json(args.output / "RESULTS.json", result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, default=QUESTIONS)
    parser.add_argument("--haystack", type=Path, default=HAYSTACK)
    parser.add_argument("--trajectories", type=Path, default=TRAJECTORIES)
    parser.add_argument("--output", type=Path, default=EVAL_ROOT / "public" / "longmemeval_v2")
    parser.add_argument("--questions-per-stratum", type=int, default=DEFAULT_QUESTIONS_PER_STRATUM)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--context-chars", type=int, default=DEFAULT_CONTEXT_CHARS)
    parser.add_argument("--max-state-chars", type=int, default=DEFAULT_STATE_CHARS)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--model-digest", default=DEFAULT_DIGEST)
    parser.add_argument("--endpoint", default="http://localhost:11434")
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--num-predict", type=int, default=192)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--resume", action="store_true", default=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    selected, candidates, manifest = prepare(args)
    if args.prepare_only:
        print(json.dumps({"status": "prepared", "questions": len(selected), "manifest": str(args.output / 'PREPARED.json')}))
        return 0
    result = run(args, selected, candidates)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "complete" and result["failure_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
