from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import threading
import time
import uuid
from typing import Iterable, Mapping

from .aggregation import EvidenceAggregator, TrustPolicy
from .governance import (
    CandidateTrace, Decision, EvidenceKind, EvidenceProvenance, EvidenceRecordV2, GovernedMemoryFrame, TemporalValidity,
)
from .profiles import EffectiveProfile, GovernedProfile, GovernedProfileStore, ProfileOverride
from .query_planner import QueryIntent, QueryPlanV2, QueryPlanner
from .retrieval import BM25Retriever, DenseRetriever, FaissBinaryRetriever, ReferenceBinaryRetriever, RetrievalHit, USearchBinaryRetriever
from .document_stack import DocumentChunk, HybridDocumentRetriever
from .beliefs import BeliefStore
from .consolidation_v2 import PersistedConsolidator, RetentionPolicy
from .profiling import ComponentProfiler
from .provenance import CallerAssertionVerifier, ProvenanceVerifier, verified_provenance
from .working_v2 import Commitment, DeterministicWorkingState, ExactTurn, WorkingCorrection
from .semantic import SemanticKind, SemanticState, SemanticValue
from .storage_v2 import SQLiteEvidenceStore


class HNGMemory:
    """Evidence-governed memory/control plane.

    Retrieval is replaceable candidate generation. SQLite records, access policy,
    temporal validity, trust, independence, and exact semantic verification determine
    what may influence an assistant.
    """

    def __init__(self, root: str | Path, *, semantic_backend: str = "faiss-auto",
                 trust_policy: TrustPolicy | None = None, planner: QueryPlanner | None = None,
                 allow_reference_fallback: bool = True, provenance_verifier: ProvenanceVerifier | None = None,
                 profiler: ComponentProfiler | None = None, document_retriever: HybridDocumentRetriever | None = None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = SQLiteEvidenceStore(self.root / "evidence.sqlite")
        self.profiles = GovernedProfileStore(self.store.con)
        self.beliefs = BeliefStore(self.store.con)
        self.consolidation = PersistedConsolidator(self.store.con)
        self.provenance_verifier = provenance_verifier or CallerAssertionVerifier()
        self.profiler = profiler or ComponentProfiler()
        self.documents = document_retriever or HybridDocumentRetriever()
        self.semantic_backend = semantic_backend
        self.allow_reference_fallback = bool(allow_reference_fallback)
        self.planner = planner or QueryPlanner()
        self.aggregator = EvidenceAggregator(trust_policy)
        self._lock = threading.RLock()
        self._providers: dict[str, object] = {}
        self._lexical = BM25Retriever()
        self._access_cache: dict[tuple[str, str, bool, str, str], set[str]] = {}
        self._backend_fallback_reason = ""
        for record in self.store.all():
            self._index_record(record)
            self._restore_document_record(record)
        self.rebuild_retrieval()
        self.documents.rebuild()
        self._provider_generation = self.store.generation()

    def _binary_provider(self):
        if self.semantic_backend in {"reference-hng", "reference", "exact"}:
            return ReferenceBinaryRetriever()
        if self.semantic_backend in {"usearch", "usearch-hamming"}:
            try:
                return USearchBinaryRetriever()
            except ImportError as exc:
                if not self.allow_reference_fallback: raise
                self._backend_fallback_reason = str(exc)
                return ReferenceBinaryRetriever(name="reference-hng-fallback")
        mode = {
            "faiss": "auto", "faiss-auto": "auto", "faiss-flat": "faiss-flat",
            "faiss-ivf": "faiss-ivf", "faiss-hnsw": "faiss-hnsw",
            "faiss-multihash": "faiss-multihash",
        }.get(self.semantic_backend)
        if mode is None:
            raise ValueError(f"unknown semantic backend: {self.semantic_backend}")
        try:
            return FaissBinaryRetriever(mode=mode)
        except ImportError as exc:
            if not self.allow_reference_fallback:
                raise
            self._backend_fallback_reason = str(exc)
            return ReferenceBinaryRetriever(name="reference-hng-fallback")

    def _provider(self, head: str, value: SemanticValue):
        provider = self._providers.get(head)
        if provider is None:
            if value.kind == SemanticKind.HDC_BINARY:
                provider = self._binary_provider()
            elif value.kind == SemanticKind.DENSE:
                provider = DenseRetriever()
            else:
                return None
            self._providers[head] = provider
        return provider

    def _index_record(self, record: EvidenceRecordV2) -> None:
        self._lexical.add(record.experience_id, record.content)
        for head, value in record.semantics.fields.items():
            provider = self._provider(head, value)
            if provider is not None:
                provider.add(record.experience_id, value)

    def rebuild_retrieval(self) -> None:
        with self._lock:
            for provider in self._providers.values():
                provider.rebuild()

    def _restore_document_record(self, record: EvidenceRecordV2) -> None:
        if record.kind is not EvidenceKind.DOCUMENT_CLAIM:
            return
        metadata = dict(record.metadata)
        chunk_id = str(metadata.get("chunk_id") or "")
        document_id = str(metadata.get("document_id") or "")
        if not chunk_id or not document_id:
            return
        semantic = next((record.semantics.fields[name] for name in ("topic", "claim", "entity")
                         if name in record.semantics.fields), None)
        excluded = {"chunk_id", "document_id", "source_uri"}
        chunk_metadata = {key: value for key, value in metadata.items() if key not in excluded}
        self.documents.ingest(DocumentChunk(chunk_id, document_id, record.content,
                              str(metadata.get("source_uri") or record.provenance.source_id),
                              semantic, chunk_metadata))

    def set_profile(self, profile: GovernedProfile) -> GovernedProfile:
        with self._lock:
            result = self.profiles.set_profile(profile)
            self._access_cache.clear()
            return result

    def activate_profile(self, conversation_id: str, user_id: str,
                         override: ProfileOverride | None = None) -> EffectiveProfile:
        with self._lock:
            result = self.profiles.activate(str(conversation_id), user_id, override)
            self._access_cache.clear()
            return result

    def effective_profile(self, conversation_id: str) -> EffectiveProfile | None:
        return self.profiles.effective(str(conversation_id))

    def update_state(self, conversation_id: str, state: SemanticState | Mapping[str, SemanticValue], *,
                     open_loops: Iterable[str] = (), constraints: Iterable[str] = ()) -> SemanticState:
        with self._lock:
            previous, _, _ = self.store.working_state(str(conversation_id))
            if isinstance(state, SemanticState):
                next_state = SemanticState(dict(state.fields), max(previous.revision + 1, state.revision))
            else:
                next_state = previous.merged(dict(state))
            self.store.put_working_state(str(conversation_id), next_state,
                                         open_loops=tuple(open_loops), constraints=tuple(constraints))
            detailed = self.store.deterministic_working(str(conversation_id))
            self.store.put_deterministic_working(replace(
                detailed, prior_semantic_state=next_state, open_loops=tuple(open_loops),
                constraints=tuple(constraints), revision=detailed.revision + 1))
            return next_state

    def working_state(self, conversation_id: str) -> DeterministicWorkingState:
        return self.store.deterministic_working(str(conversation_id))

    def update_working_state(self, conversation_id: str, *, active_episode: str | None = None,
                             current_goal: SemanticValue | None = None,
                             current_facts: Iterable[str] | None = None,
                             open_loops: Iterable[str] | None = None,
                             constraints: Iterable[str] | None = None) -> DeterministicWorkingState:
        with self._lock:
            current = self.store.deterministic_working(str(conversation_id))
            updated = replace(current,
                active_episode=current.active_episode if active_episode is None else str(active_episode),
                current_goal=current.current_goal if current_goal is None else current_goal,
                current_facts=current.current_facts if current_facts is None else tuple(map(str,current_facts)),
                open_loops=current.open_loops if open_loops is None else tuple(map(str,open_loops)),
                constraints=current.constraints if constraints is None else tuple(map(str,constraints)),
                revision=current.revision + 1)
            self.store.put_deterministic_working(updated)
            self.store.put_working_state(str(conversation_id), updated.prior_semantic_state,
                                         open_loops=updated.open_loops, constraints=updated.constraints)
            return updated

    def record_turn(self, conversation_id: str, *, turn_id: str, speaker: str, content: str,
                    semantics: SemanticState, recent_limit: int = 32) -> DeterministicWorkingState:
        with self._lock:
            current = self.store.deterministic_working(str(conversation_id))
            updated = current.with_turn(ExactTurn(str(turn_id),str(speaker),str(content),semantics), limit=recent_limit)
            self.store.put_deterministic_working(updated)
            self.store.put_working_state(str(conversation_id), semantics,
                                         open_loops=updated.open_loops, constraints=updated.constraints)
            return updated

    def add_correction(self, conversation_id: str, correction: WorkingCorrection) -> DeterministicWorkingState:
        with self._lock:
            current = self.store.deterministic_working(str(conversation_id))
            updated = replace(current, corrections=current.corrections + (correction,), revision=current.revision + 1)
            self.store.put_deterministic_working(updated); return updated

    def add_commitment(self, conversation_id: str, commitment: Commitment) -> DeterministicWorkingState:
        with self._lock:
            current = self.store.deterministic_working(str(conversation_id))
            updated = replace(current, commitments=current.commitments + (commitment,), revision=current.revision + 1)
            self.store.put_deterministic_working(updated); return updated

    def current_state(self, conversation_id: str) -> SemanticState:
        return self.store.working_state(str(conversation_id))[0]

    def ingest_evidence(self, *, content: str, semantics: SemanticState | Mapping[str, SemanticValue],
                        provenance: EvidenceProvenance, kind: EvidenceKind | str = EvidenceKind.OBSERVATION,
                        outcome_score: float = 0.0, confidence: float = 1.0,
                        experience_id: str | None = None, evidence_group_id: str | None = None,
                        source_event_id: str | None = None, episode_id: str = "", conversation_id: str = "",
                        tenant_id: str = "", user_id: str = "", scope: str = "global", role: str = "",
                        authority_level: int | None = None, abstraction_level: int | None = None,
                        profile_revision: int | None = None, validity: TemporalValidity | None = None,
                        supersedes: Iterable[str] = (), metadata: Mapping[str, object] | None = None) -> EvidenceRecordV2:
        kind = EvidenceKind(kind)
        if provenance.source_type == "model_inference" and kind is EvidenceKind.FACT:
            raise ValueError("model-generated inference cannot be ingested as authoritative FACT")
        verification = self.provenance_verifier.verify(provenance, content=str(content), metadata=dict(metadata or {}))
        provenance = verified_provenance(provenance, verification)
        metadata_payload = dict(metadata or {})
        effective = self.effective_profile(str(conversation_id)) if conversation_id else None
        if effective is not None:
            profile_revision = effective.profile_revision if profile_revision is None else profile_revision
            metadata_payload.setdefault("profile_snapshot", {
                name: (field.value.as_storage() if isinstance(field.value, SemanticValue) else field.value)
                for name, field in effective.fields.items()
            })
        source_event_id = source_event_id or f"event:{uuid.uuid4()}"
        record = EvidenceRecordV2(
            experience_id=experience_id or str(uuid.uuid4()),
            evidence_group_id=evidence_group_id or source_event_id,
            source_event_id=source_event_id,
            episode_id=str(episode_id), conversation_id=str(conversation_id), kind=kind,
            content=str(content), semantics=semantics if isinstance(semantics, SemanticState) else SemanticState(dict(semantics)),
            provenance=provenance, validity=validity or TemporalValidity(), outcome_score=float(outcome_score),
            confidence=float(confidence), tenant_id=str(tenant_id), user_id=str(user_id), scope=scope,
            role=str(role), authority_level=authority_level, abstraction_level=abstraction_level,
            profile_revision=profile_revision, supersedes=tuple(str(value) for value in supersedes),
            metadata=metadata_payload,
        )
        with self._lock:
            self.store.append(record)
            self._access_cache.clear()
            self._index_record(record)
            self._provider_generation = self.store.generation()
        return record

    def observe(self, content: str, semantics: SemanticState | Mapping[str, SemanticValue], *,
                provenance: EvidenceProvenance, **kwargs) -> EvidenceRecordV2:
        return self.ingest_evidence(content=content, semantics=semantics, provenance=provenance,
                                    kind=EvidenceKind.OBSERVATION, **kwargs)

    def remember_transition(self, *, conversation_id: str, state: SemanticState | Mapping[str, SemanticValue],
                            action: SemanticValue, next_state: SemanticValue | SemanticState,
                            outcome: str, outcome_score: float, provenance: EvidenceProvenance,
                            goal: SemanticValue | None = None, sequence: SemanticValue | None = None,
                            content: str = "", **kwargs) -> EvidenceRecordV2:
        base = state if isinstance(state, SemanticState) else SemanticState(dict(state))
        fields = dict(base.fields)
        fields["action"] = action
        if goal is not None:
            fields["goal"] = goal
        if sequence is not None:
            fields["sequence"] = sequence
        transition = self.ingest_evidence(
            content=content or outcome, semantics=SemanticState(fields), provenance=provenance,
            kind=EvidenceKind.OUTCOME, outcome_score=outcome_score, conversation_id=str(conversation_id),
            metadata={"outcome": outcome, **dict(kwargs.pop("metadata", {}) or {})}, **kwargs,
        )
        if isinstance(next_state, SemanticState):
            carried = next_state
        else:
            current = dict(base.fields)
            current["state"] = next_state
            current["next_state"] = next_state
            carried = SemanticState(current)
        self.update_state(str(conversation_id), carried)
        return transition

    def supersede(self, old_ids: Iterable[str], new_id: str) -> None:
        with self._lock:
            self.store.supersede(old_ids, new_id)
            self._access_cache.clear()

    def invalidate(self, experience_id: str) -> None:
        with self._lock:
            self.store.invalidate(experience_id)
            self._access_cache.clear()

    def _access(self, conversation_id: str, *, include_inactive: bool = True) -> tuple[tuple[EvidenceRecordV2, ...], EffectiveProfile | None]:
        profile = self.effective_profile(str(conversation_id))
        tenant_id = "" if profile is None else profile.tenant_id
        user_id = "" if profile is None else profile.user_id
        records = self.store.query_structured(tenant_id=tenant_id, user_id=user_id, include_inactive=include_inactive)
        return records, profile

    def _access_ids(self, conversation_id: str, *, include_inactive: bool = True,
                    query: SemanticState | None = None) -> tuple[set[str], EffectiveProfile | None, set[str]]:
        profile = self.effective_profile(str(conversation_id))
        tenant_id = "" if profile is None else profile.tenant_id
        user_id = "" if profile is None else profile.user_id
        environment = "" if query is None or "environment_version" not in query.fields else str(query.fields["environment_version"].value)
        policy_version = "" if query is None or "policy_version" not in query.fields else str(query.fields["policy_version"].value)
        all_key = (tenant_id, user_id, bool(include_inactive), "", "")
        all_access = self._access_cache.get(all_key)
        if all_access is None:
            all_access = self.store.eligible_ids(tenant_id=tenant_id, user_id=user_id, include_inactive=include_inactive)
            self._access_cache[all_key] = all_access
        key = (tenant_id, user_id, bool(include_inactive), environment, policy_version)
        allowed = self._access_cache.get(key)
        if allowed is None:
            allowed = self.store.eligible_ids(tenant_id=tenant_id, user_id=user_id, include_inactive=include_inactive,
                                              environment_version=environment, policy_version=policy_version)
            self._access_cache[key] = allowed
        return allowed, profile, all_access - allowed

    @staticmethod
    def _with_prefilter_exclusions(assessment, prefiltered: set[str], query: SemanticState):
        if not prefiltered:
            return assessment
        from .governance import ExcludedEvidence
        if "environment_version" in query.fields:
            reason = "environment_version_mismatch"
        elif "policy_version" in query.fields:
            reason = "policy_version_mismatch"
        else:
            reason = "structured_applicability_prefilter"
        excluded = assessment.excluded + tuple(ExcludedEvidence(value, reason) for value in sorted(prefiltered))
        reasons = assessment.reasons + (f"prefiltered {len(prefiltered)} records before ANN: {reason}",)
        return replace(assessment, excluded=excluded, reasons=reasons)

    def _retrieve(self, query: SemanticState, records: tuple[EvidenceRecordV2, ...], *, candidate_k: int,
                  lexical_query: str = "") -> tuple[tuple[EvidenceRecordV2, ...], tuple[RetrievalHit, ...]]:
        allowed = {record.experience_id for record in records}
        hits: dict[str, RetrievalHit] = {}
        for head, value in query.fields.items():
            provider = self._providers.get(head)
            if provider is None:
                continue
            for hit in provider.search(value, top_k=candidate_k, allowed_ids=allowed):
                previous = hits.get(hit.evidence_id)
                if previous is None or hit.score > previous.score:
                    hits[hit.evidence_id] = hit
        if lexical_query:
            for hit in self._lexical.search(lexical_query, top_k=candidate_k, allowed_ids=allowed):
                previous = hits.get(hit.evidence_id)
                if previous is None or hit.score > previous.score:
                    hits[hit.evidence_id] = hit
        ranked = tuple(sorted(hits.values(), key=lambda item: (-item.score, item.evidence_id))[:candidate_k])
        by_id = {record.experience_id: record for record in records}
        selected = tuple(by_id[hit.evidence_id] for hit in ranked if hit.evidence_id in by_id)
        return selected, ranked

    def _retrieve_ids(self, query: SemanticState, allowed: set[str], *, candidate_k: int,
                      lexical_query: str = "", priority_ids: tuple[str, ...] = ()) -> tuple[tuple[EvidenceRecordV2, ...], tuple[RetrievalHit, ...]]:
        """Fuse provider ranks with RRF; candidate scores never become final semantic truth."""
        rrf_k = 60
        scores: dict[str, float] = {}
        channels: dict[str, set[str]] = {}
        for head, value in query.fields.items():
            provider = self._providers.get(head)
            if provider is None:
                continue
            provider_hits = provider.search(value, top_k=candidate_k, allowed_ids=allowed)
            for rank, hit in enumerate(provider_hits, start=1):
                scores[hit.evidence_id] = scores.get(hit.evidence_id, 0.0) + 1.0 / (rrf_k + rank)
                channels.setdefault(hit.evidence_id, set()).add(f"{head}:{hit.provider}")
        if lexical_query:
            for rank, hit in enumerate(self._lexical.search(lexical_query, top_k=candidate_k, allowed_ids=allowed), start=1):
                scores[hit.evidence_id] = scores.get(hit.evidence_id, 0.0) + 1.0 / (rrf_k + rank)
                channels.setdefault(hit.evidence_id, set()).add("lexical:bm25")
        ranked_ids = sorted(scores, key=lambda key: (-scores[key], key))[:candidate_k]
        ranked_list = [RetrievalHit(key, scores[key], "hybrid-rrf:" + ",".join(sorted(channels[key])))
                       for key in ranked_ids]
        seen = set(ranked_ids)
        ranked_list.extend(RetrievalHit(value, 0.0, "governance-priority")
                           for value in priority_ids if value in allowed and value not in seen)
        ranked = tuple(ranked_list)
        return self.store.get_many(hit.evidence_id for hit in ranked), ranked

    def _ensure_provider_generation(self) -> None:
        generation = self.store.generation()
        if generation == self._provider_generation:
            return
        for _ in range(3):
            before = self.store.generation()
            self._providers = {}
            self._lexical = BM25Retriever()
            for record in self.store.all():
                self._index_record(record)
            self.rebuild_retrieval()
            after = self.store.generation()
            if before == after:
                self._provider_generation = after
                return
        raise RuntimeError("evidence generation changed repeatedly during provider rebuild")

    @staticmethod
    def _profile_query(query: SemanticState, profile: EffectiveProfile | None) -> SemanticState:
        if profile is None:
            return query
        additions = {}
        for name in ("expertise", "priority"):
            field = profile.field(name)
            if field is not None and name not in query.fields:
                additions[name] = field.value if isinstance(field.value, SemanticValue) else SemanticValue.structured(field.value)
        return query if not additions else query.merged(additions, revision=query.revision)

    def _governed_frame(self, *, conversation_id: str, query: SemanticState, plan: QueryPlanV2,
                        lexical_query: str = "") -> GovernedMemoryFrame:
        for attempt in range(3):
            self._ensure_provider_generation()
            generation = self.store.generation()
            data_version = self.store.data_version()
            started = time.perf_counter()
            phase = time.perf_counter()
            allowed, profile, prefiltered = self._access_ids(conversation_id, query=query)
            eligibility_ms = (time.perf_counter() - phase) * 1000
            query = self._profile_query(query, profile)
            phase = time.perf_counter()
            selected, hits = self._retrieve_ids(
                query, allowed, candidate_k=plan.candidate_k, lexical_query=lexical_query,
                priority_ids=self._priority_ids(conversation_id, query, limit=plan.candidate_k))
            retrieval_ms = (time.perf_counter() - phase) * 1000
            phase = time.perf_counter()
            assessment = self.aggregator.assess(selected, query, plan, profile=profile)
            governance_ms = (time.perf_counter() - phase) * 1000
            assessment = self._with_prefilter_exclusions(assessment, prefiltered, query)
            detailed = self.store.deterministic_working(conversation_id)
            current, open_loops, constraints = self.store.working_state(conversation_id)
            if generation != self.store.generation() or data_version != self.store.data_version():
                self._access_cache.clear()
                continue
            component = dict(assessment.component_ms)
            component.update({"structured_eligibility": eligibility_ms, "retrieval": retrieval_ms,
                              "storage_access": max(0.0, (time.perf_counter()-started)*1000-retrieval_ms-governance_ms)})
            assessment = replace(assessment,
                original_candidates=tuple(CandidateTrace(hit.evidence_id,hit.provider,hit.score) for hit in hits),
                component_ms=component)
            for name, milliseconds in component.items():
                self.profiler.record(name, milliseconds)
            return GovernedMemoryFrame(4, plan.intent.value, conversation_id, current, assessment,
                                       {} if profile is None else profile.as_dict(), open_loops, constraints,
                                       len(hits), detailed.as_dict())
        raise RuntimeError("evidence generation changed repeatedly during query; retry")

    def _priority_ids(self, conversation_id: str, query: SemanticState, *, limit: int) -> tuple[str, ...]:
        profile = self.effective_profile(str(conversation_id))
        environment = "" if "environment_version" not in query.fields else str(query.fields["environment_version"].value)
        policy_version = "" if "policy_version" not in query.fields else str(query.fields["policy_version"].value)
        return self.store.governance_priority_ids(
            tenant_id="" if profile is None else profile.tenant_id,
            user_id="" if profile is None else profile.user_id,
            environment_version=environment, policy_version=policy_version, limit=limit,
        )

    def context(self, conversation_id: str, *, query: SemanticState | None = None,
                intent: QueryIntent | str = QueryIntent.RECALL, lexical_query: str = "") -> GovernedMemoryFrame:
        with self._lock:
            state = self.store.deterministic_working(str(conversation_id)).prior_semantic_state
            query = query or state
            return self._governed_frame(conversation_id=str(conversation_id), query=query,
                                        plan=self.planner.plan(intent), lexical_query=lexical_query)

    def recall(self, query: SemanticState, *, conversation_id: str, lexical_query: str = "") -> GovernedMemoryFrame:
        return self.context(conversation_id, query=query, intent=QueryIntent.RECALL, lexical_query=lexical_query)

    def evaluate_action(self, state: SemanticState | Mapping[str, SemanticValue], action: SemanticValue, *,
                        conversation_id: str, plan: QueryPlanV2 | None = None,
                        lexical_query: str = "") -> GovernedMemoryFrame:
        with self._lock:
            query = state if isinstance(state, SemanticState) else SemanticState(dict(state))
            query = query.merged({"action": action}, revision=query.revision)
            return self._governed_frame(conversation_id=str(conversation_id), query=query,
                                        plan=plan or self.planner.plan(QueryIntent.ACTION_EVALUATION),
                                        lexical_query=lexical_query)

    def recommend_actions(self, state: SemanticState, *, conversation_id: str) -> tuple[tuple[str, float], ...]:
        records, profile = self._access(str(conversation_id), include_inactive=False)
        actions: dict[str, float] = {}
        for record in records:
            action = record.semantics.fields.get("action")
            label = str(record.metadata.get("action_label") or "")
            if action is None or not label:
                continue
            frame = self.evaluate_action(state, action, conversation_id=str(conversation_id))
            score = frame.assessment.support_score - frame.assessment.challenge_score
            actions[label] = max(actions.get(label, float("-inf")), score)
        return tuple(sorted(actions.items(), key=lambda item: (-item[1], item[0])))

    def consolidate(self) -> tuple[str, ...]:
        with self._lock:
            return self.consolidation.consolidate(self.store.all())

    def evaluate_retention(self) -> dict[str, str]:
        with self._lock:
            return self.consolidation.evaluate_retention(self.store.all())

    def ingest_document_chunk(self, chunk: DocumentChunk, *, semantics: SemanticState,
                              provenance: EvidenceProvenance, validity: TemporalValidity | None = None,
                              conversation_id: str = "", tenant_id: str = "", user_id: str = "",
                              scope: str = "global") -> EvidenceRecordV2:
        record = self.ingest_evidence(
            experience_id=f"chunk:{chunk.chunk_id}", source_event_id=f"document:{chunk.document_id}:{chunk.chunk_id}",
            evidence_group_id=f"document:{chunk.document_id}", content=chunk.text, semantics=semantics,
            provenance=provenance, kind=EvidenceKind.DOCUMENT_CLAIM, validity=validity,
            conversation_id=conversation_id, tenant_id=tenant_id, user_id=user_id, scope=scope,
            metadata={"document_id": chunk.document_id, "chunk_id": chunk.chunk_id,
                      "source_uri": chunk.source_uri, **dict(chunk.metadata)})
        self.documents.ingest(chunk)
        return record

    def search_documents(self, query: str, *, semantic: SemanticValue | None = None, top_k: int = 10,
                         filters: Mapping[str, object] | None = None):
        with self.profiler.measure("document_hybrid_retrieval"):
            return self.documents.search(query, semantic=semantic, top_k=top_k, filters=filters)

    def profile_history(self, user_id: str):
        return self.profiles.history(user_id)

    def stats(self) -> Mapping[str, object]:
        return {
            "semantic_backend": self.semantic_backend,
            "fallback_reason": self._backend_fallback_reason,
            "records": len(self.store.all()),
            "providers": {head: provider.stats() for head, provider in self._providers.items()},
            "lexical": self._lexical.stats(),
            "generation": self.store.generation(),
            "profile": self.profiler.summary(),
        }

    def close(self) -> None:
        self.store.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
