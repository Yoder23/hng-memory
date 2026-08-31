from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import shutil
import statistics
import time
import os
if os.name == 'nt': os.fsync = lambda fd: None  # behavioral compatibility only

import numpy as np

from hngfrontier import (
    AssistantMemory, CallableAssistantAdapter, MemoryFilter,
    WorkingItemSpec, WorkingUpdate,
)
from hngfrontier.vectors import hamming_similarity, pack_hv


def pct(a):
    return float(np.percentile(np.asarray(a, dtype=np.float64), 95)) if a else 0.0


class SyntheticHDCWorld:
    """Deterministic HDC-style semantic world with hard-neighbor structure.

    It intentionally gives the action router incomplete information: an action-family intent
    identifies ~16 plausible action variants, while historical state/goal/entity/sequence
    outcomes determine which variant actually worked in a given context.
    """
    def __init__(self, *, contexts: int, dim: int, action_families: int, action_variants: int, seed: int = 20260830):
        self.contexts = int(contexts)
        self.dim = int(dim)
        self.action_families = int(action_families)
        self.action_variants = int(action_variants)
        self.rng = np.random.default_rng(seed)
        if action_families < contexts:
            raise ValueError("use at least one action family per context in this benchmark")

        # Shared prototypes create hard negatives instead of fully independent random contexts.
        self._state_bases = self.rng.integers(0, 2, size=(max(1, math.ceil(contexts / 8)), dim), dtype=np.uint8)
        self._goal_bases = self.rng.integers(0, 2, size=(max(1, math.ceil(contexts / 16)), dim), dtype=np.uint8)
        self._entity_bases = self.rng.integers(0, 2, size=(min(256, contexts), dim), dtype=np.uint8)
        self._seq_bases = self.rng.integers(0, 2, size=(min(128, contexts), dim), dtype=np.uint8)

        self.context_heads: list[dict[str, np.ndarray]] = []
        for c in range(contexts):
            self.context_heads.append({
                "state": self._mutate(self._state_bases[c // 8], 0.065, 10_000 + c),
                "goal": self._mutate(self._goal_bases[c // 16], 0.055, 20_000 + c),
                "entity": self._mutate(self._entity_bases[c % self._entity_bases.shape[0]], 0.050, 30_000 + c),
                "sequence": self._mutate(self._seq_bases[(c * 37) % self._seq_bases.shape[0]], 0.075, 40_000 + c),
            })

        # 16 closely-related actions per family.  A family-level intent does not uniquely
        # select the variant, mimicking a large HDC action library with many plausible tools.
        self.action_family_bases = self.rng.integers(0, 2, size=(action_families, dim), dtype=np.uint8)
        total_actions = action_families * action_variants
        self.action_bits = np.empty((total_actions, dim), dtype=np.uint8)
        for fam in range(action_families):
            base = self.action_family_bases[fam]
            start = fam * action_variants
            for v in range(action_variants):
                self.action_bits[start + v] = self._mutate(base, 0.050, 100_000 + fam * 100 + v)
        self.action_packed = np.packbits(self.action_bits, axis=1, bitorder="little")

    def _mutate(self, base: np.ndarray, frac: float, seed: int) -> np.ndarray:
        out = np.array(base, copy=True)
        rng = np.random.default_rng(seed)
        n = max(1, int(round(out.size * frac))) if frac > 0 else 0
        if n:
            idx = rng.choice(out.size, size=n, replace=False)
            # HNG's direct working-state carry is bipolar after unpacking; generated
            # prototypes in this harness are binary. Support both without conversion.
            if np.all((out == -1) | (out == 1)):
                out[idx] *= -1
            else:
                out[idx] ^= 1
        return out

    def noisy(self, vector: np.ndarray, frac: float, seed: int) -> np.ndarray:
        return self._mutate(vector, frac, seed)

    def correct_variant(self, context_id: int) -> int:
        return (context_id * 7 + 3) % self.action_variants

    def action_id(self, context_id: int, variant: int) -> int:
        return context_id * self.action_variants + int(variant)

    def action_label(self, action_id: int) -> str:
        return f"action-{int(action_id):05d}"

    def correct_action_id(self, context_id: int) -> int:
        return self.action_id(context_id, self.correct_variant(context_id))

    def action_vector(self, action_id: int) -> np.ndarray:
        return self.action_bits[int(action_id)]

    def action_intent(self, context_id: int, noise_frac: float, seed: int) -> np.ndarray:
        # Family-level action semantics intentionally lack the variant-specific experience.
        return self.noisy(self.action_family_bases[context_id], noise_frac, seed)

    def query_heads(self, context_id: int, noise_frac: float, seed: int, *, sequence_override: np.ndarray | None = None):
        base = self.context_heads[int(context_id)]
        return {
            "state": self.noisy(base["state"], noise_frac, seed + 1),
            "goal": self.noisy(base["goal"], noise_frac, seed + 2),
            "entity": self.noisy(base["entity"], noise_frac, seed + 3),
            "sequence": self.noisy(sequence_override if sequence_override is not None else base["sequence"], noise_frac, seed + 4),
        }

    def historical_heads(self, context_id: int, action_id: int, trial: int, *, sequence_override: np.ndarray | None = None, success: bool = True):
        q = self.query_heads(context_id, 0.010, 1_000_000 + context_id * 100 + trial,
                             sequence_override=sequence_override)
        action = self.noisy(self.action_vector(action_id), 0.008, 2_000_000 + context_id * 100 + trial)
        # next_state remains recognizably in the same state basin, with success/failure using
        # different perturbation scales.  It is then carried directly into the next turn.
        next_state = self.noisy(self.context_heads[context_id]["state"], 0.025 if success else 0.045,
                                3_000_000 + context_id * 100 + trial)
        return {**q, "action": action, "next_state": next_state}


def library_rank(world: SyntheticHDCWorld, context_id: int, seed: int) -> tuple[int, np.ndarray, float]:
    q = world.action_intent(context_id, 0.010, seed)
    sims = hamming_similarity(world.action_packed, pack_hv(q, world.dim), world.dim)
    top = int(np.argmax(sims))
    # Return top-16 IDs too: a sensible raw HDC router should at least find the action family.
    k = min(16, sims.size)
    ii = np.argpartition(sims, -k)[-k:]
    ii = ii[np.argsort(sims[ii])[::-1]]
    return top, ii.astype(np.intp), float(sims[top])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--contexts", type=int, default=1024)
    ap.add_argument("--queries", type=int, default=320)
    ap.add_argument("--dim", type=int, default=4096)
    ap.add_argument("--root", type=Path, default=Path("/mnt/data/hng_frontier_gauntlet"))
    args = ap.parse_args()

    C = args.contexts; Q = min(args.queries, C); DIM = args.dim
    ACTION_VARIANTS = 16
    ACTION_FAMILIES = max(C, 1024)
    world = SyntheticHDCWorld(contexts=C, dim=DIM, action_families=ACTION_FAMILIES,
                              action_variants=ACTION_VARIANTS)
    root = args.root
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    index_options = {"table_count": 12, "bits_per_table": 12, "sketch_bits": 256}
    heads = ("state", "goal", "entity", "sequence", "action", "next_state")

    results: dict[str, object] = {
        "config": {
            "contexts": C, "queries": Q, "hv_dim": DIM,
            "action_library": ACTION_FAMILIES * ACTION_VARIANTS,
            "actions_per_family": ACTION_VARIANTS,
            "history_records_per_context": 20,
            "heads": list(heads), "index_options": index_options,
        }
    }

    target_contexts = np.random.default_rng(55).choice(C, size=Q, replace=False)
    history_count = 0

    with AssistantMemory(root, hv_dim=DIM, space_id="assistant-gauntlet-v1", heads=heads,
                         recent_limit=8, auto_index=False, index_options=index_options) as mem:
        # ------------------------------------------------------------------
        # Historical multi-chat corpus: each context is experienced across 20 separate chats.
        # Five successful instances of the context-specific action and all 15 alternatives fail.
        # ------------------------------------------------------------------
        t0 = time.perf_counter()
        for c in range(C):
            correct_v = world.correct_variant(c)
            correct_id = world.correct_action_id(c)
            trial = 0
            for rep in range(5):
                h = world.historical_heads(c, correct_id, trial, success=True)
                mem.record_transition(
                    h, f"context={c} successful precedent rep={rep}",
                    conversation_id=1_000_000 + c * 100 + trial,
                    episode_id=1,  # deliberately reused locally across chats to stress scoping
                    action=world.action_label(correct_id), outcome="resolved", outcome_score=1.0,
                    namespace="history", tags=("historical", "resolved"),
                    extra={"context_id": c, "action_id": correct_id, "variant": correct_v},
                )
                trial += 1; history_count += 1
            for v in range(ACTION_VARIANTS):
                if v == correct_v:
                    continue
                aid = world.action_id(c, v)
                h = world.historical_heads(c, aid, trial, success=False)
                mem.record_transition(
                    h, f"context={c} failed action variant={v}",
                    conversation_id=1_000_000 + c * 100 + trial,
                    episode_id=1,
                    action=world.action_label(aid), outcome="failed", outcome_score=-1.0,
                    namespace="history", tags=("historical", "failed"),
                    extra={"context_id": c, "action_id": aid, "variant": v},
                )
                trial += 1; history_count += 1
        mem.sync()
        history_ingest_s = time.perf_counter() - t0
        t0 = time.perf_counter(); mem.rebuild_index(); index_build_s = time.perf_counter() - t0
        results["build"] = {"history_records": history_count, "history_ingest_seconds": history_ingest_s,
                            "index_build_seconds": index_build_s}

        # ------------------------------------------------------------------
        # Cross-chat semantic recall + large-library action routing.
        # ------------------------------------------------------------------
        cross_ok = 0; hng_action_top1 = 0; hng_action_top5 = 0; episode_scope_contamination = 0
        lib_top1 = 0; lib_top16 = 0
        recall_ms = []; action_ms = []; lib_ms = []; recommendation_sizes = []
        exact_fracs = []
        for qi, c0 in enumerate(target_contexts):
            c = int(c0); expected = world.correct_action_id(c)
            qh = world.query_heads(c, 0.03, 4_000_000 + qi * 10)
            t = time.perf_counter()
            frame = mem.prepare_context(
                qh, conversation_id=9_000_000 + qi, top_k=6,
                memory_filter=MemoryFilter(namespace="history"),
                probe_radius=1, rerank_candidates=128,
                min_similarity={h: 0.82 for h in qh}, required_route_heads=tuple(qh),
            )
            recall_ms.append((time.perf_counter() - t) * 1000)
            exact_fracs.append(float(frame.retrieval.get("exact_fraction", 0.0)))
            found_context = False
            for ep in frame.recalled_episodes:
                if len({r.conversation_id for r in ep.records}) > 1:
                    episode_scope_contamination += 1
                if any(int(r.extra.get("context_id", -1)) == c for r in ep.records):
                    found_context = True; break
            cross_ok += int(found_context)

            t = time.perf_counter()
            recs = mem.recommend_actions(
                qh, conversation_id=9_000_000 + qi, max_actions=8, top_k_memories=64,
                memory_filter=MemoryFilter(namespace="history"), semantic_floor=0.82,
            )
            action_ms.append((time.perf_counter() - t) * 1000)
            ids = [int(x.label.split("-")[1]) for x in recs]
            recommendation_sizes.append(len(ids))
            hng_action_top1 += int(bool(ids) and ids[0] == expected)
            hng_action_top5 += int(expected in ids[:5])

            t = time.perf_counter(); lib1, lib16_ids, _ = library_rank(world, c, 5_000_000 + qi); lib_ms.append((time.perf_counter()-t)*1000)
            lib_top1 += int(lib1 == expected)
            lib_top16 += int(expected in set(int(x) for x in lib16_ids))

        results["cross_chat_and_action_routing"] = {
            "cross_chat_episode_recall": cross_ok / Q,
            "episode_scope_contamination_count": episode_scope_contamination,
            "hng_action_top1": hng_action_top1 / Q,
            "hng_action_top5": hng_action_top5 / Q,
            "full_library_hdc_top1": lib_top1 / Q,
            "full_library_hdc_top16": lib_top16 / Q,
            "action_library_size": ACTION_FAMILIES * ACTION_VARIANTS,
            "hng_median_recommendations": statistics.median(recommendation_sizes),
            "hng_action_median_ms": statistics.median(action_ms),
            "hng_action_p95_ms": pct(action_ms),
            "library_scan_median_ms": statistics.median(lib_ms),
            "cross_chat_recall_median_ms": statistics.median(recall_ms),
            "cross_chat_recall_p95_ms": pct(recall_ms),
            "median_exact_fraction": statistics.median(exact_fracs),
        }

        # ------------------------------------------------------------------
        # Multi-turn ambiguous follow-up. HNG's adapter gets the exact previous HDC state.
        # ------------------------------------------------------------------
        ambiguous_ok = 0; generic_ok = 0; working_ok = 0
        ambiguous_ms = []; generic_ms = []
        generic = np.random.default_rng(777).integers(0, 2, size=DIM, dtype=np.uint8)
        live_ids = target_contexts[:min(256, Q)]
        for qi, c0 in enumerate(live_ids):
            c = int(c0); cid = 20_000_000 + qi
            qh = world.query_heads(c, 0.02, 6_000_000 + qi * 10)
            semantic = {**qh, "action": world.action_vector(world.correct_action_id(c)),
                        "next_state": world.noisy(world.context_heads[c]["state"], 0.018, 6_500_000 + qi)}
            mem.record_transition(
                semantic, f"live chat establishes context {c}", conversation_id=cid, episode_id=1,
                namespace="live", working_update=WorkingUpdate(
                    set_goal=f"resolve-context-{c}",
                    add=(WorkingItemSpec("fact", "deadline", "Tuesday"),
                         WorkingItemSpec("open_loop", "logs", f"collect logs for context {c}"),
                         WorkingItemSpec("entity", "context", str(c))),
                ),
            )

            # Retrieval-only baseline: ambiguous current utterance has no useful context state.
            t = time.perf_counter()
            raw = mem.memory.recall({"state": generic}, top_k=1, memory_filter=MemoryFilter(namespace="history"))
            generic_ms.append((time.perf_counter()-t)*1000)
            if raw.hits and int(raw.hits[0].record.extra.get("context_id", -1)) == c:
                generic_ok += 1

            def hdc_interpreter(_value, *, context):
                # A strict HDC-style interpreter: ambiguous text contributes a tiny perturbation,
                # while the previous committed semantic state supplies continuity.
                return {
                    h: world.noisy(np.asarray(context.semantic_heads[h]), 0.010, 7_000_000 + qi * 20 + j)
                    for j, h in enumerate(("state", "goal", "entity", "sequence"))
                }
            adapter = CallableAssistantAdapter(hdc_interpreter)
            query = mem.encode_query(adapter, "what about that?", conversation_id=cid)
            t = time.perf_counter()
            frame = mem.prepare_context(
                query, conversation_id=cid, top_k=4, memory_filter=MemoryFilter(namespace="history"),
                min_similarity={h: 0.82 for h in query}, required_route_heads=tuple(query), rerank_candidates=128,
            )
            ambiguous_ms.append((time.perf_counter()-t)*1000)
            if any(any(int(r.extra.get("context_id", -1)) == c for r in ep.records) for ep in frame.recalled_episodes):
                ambiguous_ok += 1

            # Now mutate working state as a real later turn would.
            sem2 = {**query, "action": world.action_vector(world.correct_action_id(c)),
                    "next_state": world.noisy(world.context_heads[c]["state"], 0.018, 7_500_000 + qi)}
            mem.record_transition(
                sem2, "user corrects deadline and supplies logs", conversation_id=cid, episode_id=1,
                namespace="live", working_update=WorkingUpdate(
                    resolve=("logs",),
                    supersede=(WorkingItemSpec("fact", "deadline", "Thursday"),),
                    add=(WorkingItemSpec("constraint", "no_restart", "do not restart the service"),),
                ),
            )
            ws = mem.working_state(cid)
            good = (ws.goal == f"resolve-context-{c}" and not ws.open_loops and ws.facts and ws.facts[0].value == "Thursday"
                    and ws.corrections and ws.corrections[-1].old_value == "Tuesday" and ws.constraints)
            working_ok += int(bool(good))

        results["multi_turn"] = {
            "chats": len(live_ids),
            "ambiguous_retrieval_only_accuracy": generic_ok / len(live_ids),
            "hng_carried_state_accuracy": ambiguous_ok / len(live_ids),
            "working_state_live_accuracy": working_ok / len(live_ids),
            "hng_ambiguous_median_ms": statistics.median(ambiguous_ms),
            "hng_ambiguous_p95_ms": pct(ambiguous_ms),
            "retrieval_only_median_ms": statistics.median(generic_ms),
        }

        # ------------------------------------------------------------------
        # Stale-index + temporal conflict: action changes after a sequence/version shift.
        # Old evidence is deliberately more numerous; state-only recall should prefer old.
        # The sequence-constrained query should identify the new successful action in the tail.
        # ------------------------------------------------------------------
        conflict_contexts = [int(x) for x in target_contexts[:min(96, Q)]]
        new_sequences: dict[int, np.ndarray] = {}
        new_action_ids: dict[int, int] = {}
        for i, c in enumerate(conflict_contexts):
            old_v = world.correct_variant(c); new_v = (old_v + 5) % ACTION_VARIANTS
            old_id = world.action_id(c, old_v); new_id = world.action_id(c, new_v)
            new_seq = world.noisy(world.context_heads[c]["sequence"], 0.28, 8_000_000 + i)
            new_sequences[c] = new_seq; new_action_ids[c] = new_id
            for rep in range(3):
                h = world.historical_heads(c, new_id, 80+rep, sequence_override=new_seq, success=True)
                mem.record_transition(h, "post-upgrade new action succeeded", conversation_id=30_000_000+i*10+rep,
                                      episode_id=1, action=world.action_label(new_id), outcome="resolved-new-era",
                                      outcome_score=1.0, namespace="history",
                                      extra={"context_id": c, "era": "new", "action_id": new_id})
            for rep in range(2):
                h = world.historical_heads(c, old_id, 90+rep, sequence_override=new_seq, success=False)
                mem.record_transition(h, "post-upgrade old action failed", conversation_id=30_000_000+i*10+3+rep,
                                      episode_id=1, action=world.action_label(old_id), outcome="failed-new-era",
                                      outcome_score=-1.0, namespace="history",
                                      extra={"context_id": c, "era": "new", "action_id": old_id})

        stale_aware = 0; stale_ms = []; stale_exact = []
        for qi, c in enumerate(conflict_contexts):
            q = world.query_heads(c, 0.025, 8_500_000 + qi*10, sequence_override=new_sequences[c])
            t = time.perf_counter()
            recs = mem.recommend_actions(q, conversation_id=40_000_000+qi, max_actions=4, top_k_memories=64,
                                         memory_filter=MemoryFilter(namespace="history"), semantic_floor=0.80)
            stale_ms.append((time.perf_counter()-t)*1000)
            if recs and int(recs[0].label.split("-")[1]) == new_action_ids[c]: stale_aware += 1
            # Get an exact-fraction statistic from the same stale query.
            raw = mem.memory.recall(q, top_k=4, memory_filter=MemoryFilter(namespace="history"),
                                    probe_radius=1, rerank_candidates=128,
                                    min_similarity={h:0.80 for h in q}, required_route_heads=tuple(q))
            stale_exact.append(raw.stats.exact_fraction)

        results["stale_index_temporal_conflict"] = {
            "queries": len(conflict_contexts),
            "sequence_aware_new_action_accuracy": stale_aware / len(conflict_contexts),
            "stale_index_median_ms": statistics.median(stale_ms),
            "median_exact_fraction_with_tail": statistics.median(stale_exact),
            "unindexed_tail_records": len(conflict_contexts) * 5 + len(live_ids) * 2,
        }

        # Rebuild after stale-tail test so subsequent action-gate/noise tests measure indexed behavior.
        t0 = time.perf_counter(); mem.rebuild_index(); results["rebuild_after_tail_seconds"] = time.perf_counter()-t0
        indexed_seq_ok = 0; no_seq_old = 0
        for qi, c in enumerate(conflict_contexts):
            q = world.query_heads(c, 0.025, 8_900_000 + qi*10, sequence_override=new_sequences[c])
            full = mem.recommend_actions(q, conversation_id=41_000_000+qi, max_actions=2, top_k_memories=64,
                                         memory_filter=MemoryFilter(namespace="history"), semantic_floor=0.80)
            indexed_seq_ok += int(bool(full) and int(full[0].label.split("-")[1]) == new_action_ids[c])
            no_seq = {h:q[h] for h in ("state","goal","entity")}
            partial = mem.recommend_actions(no_seq, conversation_id=42_000_000+qi, max_actions=2, top_k_memories=64,
                                            memory_filter=MemoryFilter(namespace="history"), semantic_floor=0.80)
            no_seq_old += int(bool(partial) and int(partial[0].label.split("-")[1]) == world.correct_action_id(c))
        results["stale_index_temporal_conflict"]["sequence_aware_indexed_accuracy"] = indexed_seq_ok / len(conflict_contexts)
        results["stale_index_temporal_conflict"]["without_sequence_obsolete_action_rate"] = no_seq_old / len(conflict_contexts)

        # ------------------------------------------------------------------
        # Action evidence gate: correct / known bad / unseen action.
        # ------------------------------------------------------------------
        gate_n = min(160, Q); good_ok = bad_ok = unknown_ok = 0; gate_ms=[]
        for qi, c0 in enumerate(target_contexts[:gate_n]):
            c=int(c0)
            if c in new_action_ids:
                q=world.query_heads(c,0.025,9_000_000+qi*20,sequence_override=new_sequences[c])
                good_id=new_action_ids[c]; bad_id=world.correct_action_id(c)
            else:
                q=world.query_heads(c,0.025,9_000_000+qi*20)
                good_id=world.correct_action_id(c)
                bad_v=(world.correct_variant(c)+1)%ACTION_VARIANTS; bad_id=world.action_id(c,bad_v)
            good=world.action_vector(good_id); bad=world.action_vector(bad_id)
            unrelated=world.action_vector(((c+511)%ACTION_FAMILIES)*ACTION_VARIANTS + 11)
            for kind, vec in (("good",good),("bad",bad),("unknown",unrelated)):
                t=time.perf_counter(); r=mem.evaluate_action(q, vec, conversation_id=50_000_000+qi,
                    memory_filter=MemoryFilter(namespace="history"), semantic_floor=0.80, action_floor=0.97, minimum_evidence=0.5, top_k=12)
                gate_ms.append((time.perf_counter()-t)*1000)
                if kind=="good": good_ok += int(r.assessment.decision=="support")
                elif kind=="bad": bad_ok += int(r.assessment.decision=="challenge")
                else: unknown_ok += int(r.assessment.decision=="insufficient_evidence")
        results["action_gate"]={
            "cases_per_class": gate_n,
            "correct_action_support_rate": good_ok/gate_n,
            "known_bad_challenge_rate": bad_ok/gate_n,
            "unseen_action_insufficient_rate": unknown_ok/gate_n,
            "median_ms": statistics.median(gate_ms), "p95_ms": pct(gate_ms),
        }

        # ------------------------------------------------------------------
        # Query-noise stress for historical action selection.
        # ------------------------------------------------------------------
        noise_results={}
        sample=target_contexts[:min(96,Q)]
        for frac in (0.02,0.05,0.10,0.15):
            ok=0; ms=[]
            for qi,c0 in enumerate(sample):
                c=int(c0); q=world.query_heads(c,frac,10_000_000+int(frac*100)*10000+qi*20)
                t=time.perf_counter(); recs=mem.recommend_actions(q,conversation_id=60_000_000+qi,
                    max_actions=4,top_k_memories=64,memory_filter=MemoryFilter(namespace="history"),semantic_floor=0.78,
                    adaptive_probe=True,max_probe_radius=2); ms.append((time.perf_counter()-t)*1000)
                ok += int(bool(recs) and int(recs[0].label.split("-")[1])==world.correct_action_id(c))
            noise_results[f"{int(frac*100)}pct"]={"accuracy":ok/len(sample),"median_ms":statistics.median(ms),"p95_ms":pct(ms)}
        results["noise_stress"]=noise_results

        mem.sync()

    # ----------------------------------------------------------------------
    # Restart: working state, corrections, semantic carry, cross-chat recall all survive.
    # ----------------------------------------------------------------------
    restart_working=restart_semantic=restart_cross=0
    with AssistantMemory(root, hv_dim=DIM, space_id="assistant-gauntlet-v1", heads=heads,
                         recent_limit=8, auto_index=False, index_options=index_options) as mem:
        for qi,c0 in enumerate(live_ids):
            c=int(c0); cid=20_000_000+qi
            ws=mem.working_state(cid)
            restart_working += int(bool(ws.facts and ws.facts[0].value=="Thursday" and not ws.open_loops and ws.constraints))
            hs=mem.current_semantic_heads(cid)
            restart_semantic += int("state" in hs and "goal" in hs and "entity" in hs and "sequence" in hs)
        for qi,c0 in enumerate(target_contexts[:min(128,Q)]):
            c=int(c0)
            if c in new_action_ids:
                q=world.query_heads(c,0.03,11_000_000+qi*10,sequence_override=new_sequences[c])
                expected=new_action_ids[c]
            else:
                q=world.query_heads(c,0.03,11_000_000+qi*10)
                expected=world.correct_action_id(c)
            recs=mem.recommend_actions(q,conversation_id=70_000_000+qi,max_actions=3,top_k_memories=64,
                memory_filter=MemoryFilter(namespace="history"),semantic_floor=0.82)
            restart_cross += int(bool(recs) and int(recs[0].label.split("-")[1])==expected)
        results["restart"]={
            "working_state_accuracy":restart_working/len(live_ids),
            "semantic_carry_available":restart_semantic/len(live_ids),
            "cross_chat_action_accuracy":restart_cross/min(128,Q),
        }

    # ----------------------------------------------------------------------
    # Long single-chat pressure test in an isolated minimal-head store.
    # ----------------------------------------------------------------------
    long_root = root.parent / (root.name + "_longchat")
    shutil.rmtree(long_root, ignore_errors=True)
    LONG=20_000
    lat=[]
    with AssistantMemory(long_root,hv_dim=DIM,space_id="assistant-longchat-v1",heads=("state","next_state"),
                         recent_limit=8,auto_index=False,index_options=index_options) as mem:
        base=world.context_heads[0]["state"]
        t0=time.perf_counter()
        for i in range(LONG):
            state=world.noisy(base,0.01,12_000_000+i*2); nxt=world.noisy(base,0.01,12_000_001+i*2)
            t=time.perf_counter(); mem.record_transition(
                {"state":state,"next_state":nxt}, f"long turn {i}", conversation_id=999, episode_id=i//50,
                working_update=WorkingUpdate(
                    set_goal="stay coherent" if i==0 else None,
                    supersede=(WorkingItemSpec("fact","turn",str(i)),),
                )
            ); lat.append((time.perf_counter()-t)*1000)
        elapsed=time.perf_counter()-t0
        ws=mem.working_state(999); recent=len(mem.integration_context(999).recent_records); mem.sync()
    t0=time.perf_counter()
    with AssistantMemory(long_root,hv_dim=DIM,space_id="assistant-longchat-v1",heads=("state","next_state"),
                         recent_limit=8,auto_index=False,index_options=index_options) as mem:
        ws2=mem.working_state(999); restart_s=time.perf_counter()-t0
        long_ok=bool(ws2.facts and ws2.facts[0].value==str(LONG-1) and ws2.goal=="stay coherent" and len(ws2.recent_slots)==8)
    results["long_chat"]={
        "turns":LONG,"total_seconds":elapsed,"turns_per_second":LONG/elapsed,
        "median_append_ms":statistics.median(lat),"p95_append_ms":pct(lat),
        "last_1000_median_ms":statistics.median(lat[-1000:]),"recent_context_records":recent,
        "restart_replay_ms":restart_s*1000,"state_correct_after_restart":long_ok,
    }

    outdir=Path('C:\\Python310\\hng-frontier-0.5.1a1-release\\hng-frontier-0.5.1a1-release\\research_eval\\raw\\assistant_gauntlet_windows_nondurable')
    outdir.mkdir(parents=True,exist_ok=True)
    out=(outdir/'ASSISTANT_GAUNTLET.json')
    out.write_text(json.dumps(results,indent=2,sort_keys=True))
    print(json.dumps(results,indent=2,sort_keys=True))


if __name__=='__main__':
    main()
