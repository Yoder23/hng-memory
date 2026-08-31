from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "baseline_source" / "hng-frontier-0.5.1a1"
sys.path.insert(0, str(SOURCE / "src"))

import numpy as np
from hngfrontier import (
    EvidenceProvenance, GovernedProfile, HNGMemory, PerspectiveField,
    SemanticState, SemanticValue,
)


def hv(seed: int, dim: int = 256):
    return SemanticValue.hdc(np.random.default_rng(seed).choice([-1, 1], size=dim), dimension=dim)


def state(seed: int = 1):
    return SemanticState({"state": hv(seed), "goal": hv(seed + 1), "sequence": hv(seed + 2)})


def trusted(source="system"):
    return EvidenceProvenance("system_telemetry", source, 1.0, True)


def worker(mode: str, target: Path, index: int = 0):
    if mode == "before_commit":
        con = sqlite3.connect(target / "evidence.sqlite")
        con.execute("BEGIN IMMEDIATE"); con.execute("INSERT INTO fault_probe VALUES(?)", ("uncommitted",)); os._exit(17)
    if mode == "vector_only":
        from hngfrontier import ReferenceBinaryRetriever
        provider = ReferenceBinaryRetriever(); provider.add("orphan", hv(1)); os._exit(18)
    if mode == "after_commit":
        mem = HNGMemory(target, semantic_backend="reference-hng")
        mem.observe("committed", SemanticState({"state": hv(1)}), provenance=trusted(), experience_id="committed")
        os._exit(19)
    if mode == "rebuild":
        mem = HNGMemory(target, semantic_backend="reference-hng")
        while True: mem.rebuild_retrieval()
    if mode == "writer":
        with HNGMemory(target, semantic_backend="reference-hng") as mem:
            for value in range(20):
                key = f"w{index}-{value}"
                mem.observe(key, SemanticState({"state": hv(index * 100 + value)}), provenance=trusted(key), experience_id=key)
        return
    if mode == "reader":
        with HNGMemory(target, semantic_backend="reference-hng") as mem:
            assert len(mem.store.all()) >= 1
        return


def child(mode: str, target: Path, index: int = 0, *, wait: bool = True):
    command = [sys.executable, str(Path(__file__).resolve()), "--worker", mode, str(target), str(index)]
    process = subprocess.Popen(command, env={**os.environ, "PYTHONPATH": str(SOURCE / "src")})
    if wait: process.wait(timeout=60)
    return process


def concurrent_mutation_case(target: Path, mutation: str) -> bool:
    with HNGMemory(target, semantic_backend="reference-hng") as mem:
        mem.set_profile(GovernedProfile("u", "t", {
            "role": PerspectiveField("ic", 1, "user-confirmed", True),
            "authority_level": PerspectiveField(1, 1, "user-confirmed", True)}))
        mem.activate_profile("c", "u")
        query, action = state(), hv(10)
        record = mem.remember_transition(conversation_id="c", state=query, action=action, next_state=hv(20),
                                         outcome="ok", outcome_score=1, provenance=trusted(), tenant_id="t",
                                         scope="tenant", role="ic", experience_id="precedent")
        entered = threading.Event(); original = mem.aggregator.assess
        def slow(*args, **kwargs):
            entered.set(); time.sleep(.08); return original(*args, **kwargs)
        mem.aggregator.assess = slow
        result = []
        thread = threading.Thread(target=lambda: result.append(mem.evaluate_action(query, action, conversation_id="c")))
        thread.start(); entered.wait(5)
        with HNGMemory(target, semantic_backend="reference-hng") as other:
            if mutation == "profile":
                other.set_profile(GovernedProfile("u", "t", {
                    "role": PerspectiveField("manager", 1, "user-confirmed", True),
                    "authority_level": PerspectiveField(3, 1, "user-confirmed", True)}))
            elif mutation == "supersede":
                newer = other.observe("new", SemanticState({"state": hv(99)}), provenance=trusted(), experience_id="new")
                other.supersede((record.experience_id,), newer.experience_id)
            elif mutation == "invalidate": other.invalidate(record.experience_id)
        thread.join(10)
        return bool(result) and not thread.is_alive()


def run(output: Path):
    cases = {}
    with tempfile.TemporaryDirectory(prefix="hng-closure-fault-") as raw:
        base = Path(raw)
        before = base / "before"; before.mkdir();
        with HNGMemory(before, semantic_backend="reference-hng") as mem:
            mem.store.con.execute("CREATE TABLE fault_probe(value TEXT)"); mem.store.con.commit()
        child("before_commit", before)
        con = sqlite3.connect(before / "evidence.sqlite")
        cases["process_kill_before_commit"] = con.execute("SELECT COUNT(*) FROM fault_probe").fetchone()[0] == 0; con.close()

        vector = base / "vector"; vector.mkdir(); child("vector_only", vector)
        with HNGMemory(vector, semantic_backend="reference-hng") as mem:
            cases["kill_after_semantic_vector_write"] = len(mem.store.all()) == 0

        committed = base / "committed"; committed.mkdir(); child("after_commit", committed)
        with HNGMemory(committed, semantic_backend="reference-hng") as mem:
            cases["kill_after_evidence_commit"] = mem.store.get("committed") is not None

        rebuild = base / "rebuild"; rebuild.mkdir()
        with HNGMemory(rebuild, semantic_backend="reference-hng") as mem:
            for i in range(100): mem.observe(str(i), SemanticState({"state": hv(i)}), provenance=trusted(str(i)))
        process = child("rebuild", rebuild, wait=False); time.sleep(.05); process.kill(); process.wait()
        with HNGMemory(rebuild, semantic_backend="reference-hng") as mem:
            cases["kill_during_index_rebuild"] = len(mem.store.all()) == 100

        concurrent = base / "concurrent"; concurrent.mkdir()
        writers = [child("writer", concurrent, i, wait=False) for i in range(4)]
        writer_codes = [process.wait(timeout=60) for process in writers]
        with HNGMemory(concurrent, semantic_backend="reference-hng") as mem:
            cases["competing_writer_processes"] = writer_codes == [0, 0, 0, 0] and len(mem.store.all()) == 80
        readers = [child("reader", concurrent, i, wait=False) for i in range(4)]
        cases["multiple_reader_processes"] = [process.wait(timeout=60) for process in readers] == [0, 0, 0, 0]

        cases["profile_revision_during_query"] = concurrent_mutation_case(base / "profile", "profile")
        cases["supersession_during_query"] = concurrent_mutation_case(base / "supersede", "supersede")
        cases["invalidation_during_query"] = concurrent_mutation_case(base / "invalidate", "invalidate")

        index = base / "index"; index.mkdir()
        with HNGMemory(index, semantic_backend="reference-hng") as mem:
            mem.observe("one", SemanticState({"state": hv(1)}), provenance=trusted())
            query = threading.Thread(target=lambda: mem.recall(SemanticState({"state": hv(1)}), conversation_id="c"))
            replacement = threading.Thread(target=mem.rebuild_retrieval)
            query.start(); replacement.start(); query.join(10); replacement.join(10)
            cases["index_replacement_during_query"] = not query.is_alive() and not replacement.is_alive()

    payload = {"passed": sum(cases.values()), "total": len(cases), "cases": cases}
    output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2)); return 0 if all(cases.values()) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--worker", action="store_true")
    parser.add_argument("mode", nargs="?"); parser.add_argument("target", nargs="?"); parser.add_argument("index", nargs="?", default="0")
    parser.add_argument("--output", default=str(ROOT / "closure_eval" / "raw" / "FAULT_INJECTION.json"))
    args = parser.parse_args()
    if args.worker: worker(args.mode, Path(args.target), int(args.index))
    else: raise SystemExit(run(Path(args.output)))
