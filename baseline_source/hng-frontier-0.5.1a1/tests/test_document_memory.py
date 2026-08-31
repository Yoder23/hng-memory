import numpy as np

from hngfrontier import HDCDocumentMemory


def hv(rng, d):
    return rng.choice(np.array([-1, 1], dtype=np.int8), size=d)


def noisy(v, rng, p=0.03):
    out = v.copy(); mask = rng.random(v.size) < p; out[mask] *= -1; return out


def test_document_summary_coverage_and_priority(tmp_path):
    rng = np.random.default_rng(1); d = 512
    with HDCDocumentMemory(tmp_path / 'doc', hv_dim=d, space_id='t', index_options={'table_count':8,'bits_per_table':10,'sketch_bits':128}) as mem:
        ordinal = 0; key_slots=[]; priority_slots=[]
        for sec in range(5):
            base = hv(rng,d)
            for j in range(6):
                kind = 'key_claim' if j == 0 else 'body'
                imp = .95 if j == 0 else .2
                if sec == 2 and j == 5:
                    kind='caveat'; imp=.99
                slot = mem.add_unit(1, f's{sec} u{j}', {'topic':noisy(base,rng,.03),'claim':noisy(base,rng,.05),'entity':noisy(base,rng,.08),'evidence':noisy(base,rng,.08)}, ordinal=ordinal, section_id=sec, kind=kind, importance=imp)
                if j == 0: key_slots.append(slot)
                if kind == 'caveat': priority_slots.append(slot)
                ordinal += 1
        frame = mem.summarize_document(1, budget_units=8)
        assert len(frame.segments) == 5
        assert set(key_slots).issubset(set(frame.selected_slots))
        assert set(priority_slots).issubset(set(frame.selected_slots))
        assert frame.document_heads['topic'].shape == (d,)


def test_document_discovered_structure(tmp_path):
    rng = np.random.default_rng(2); d=512
    with HDCDocumentMemory(tmp_path / 'doc', hv_dim=d, space_id='t', index_options={'table_count':8,'bits_per_table':10,'sketch_bits':128}) as mem:
        ordinal=0
        for sec in range(4):
            base=hv(rng,d)
            for j in range(8):
                mem.add_unit(7, f'{sec}:{j}', {'topic':noisy(base,rng,.02),'claim':noisy(base,rng,.04),'entity':noisy(base,rng,.05),'evidence':noisy(base,rng,.06)}, ordinal=ordinal, section_id=sec, importance=.9 if j==0 else .2)
                ordinal += 1
        f=mem.summarize_document(7,budget_units=8,discover_structure=True)
        assert len(f.segments)==4
        assert f.boundary_threshold is not None


def test_document_query_is_scoped(tmp_path):
    rng=np.random.default_rng(3); d=512; base=hv(rng,d); other=hv(rng,d)
    with HDCDocumentMemory(tmp_path/'doc',hv_dim=d,space_id='t',index_options={'table_count':8,'bits_per_table':10,'sketch_bits':128}) as mem:
        s1=mem.add_unit(1,'doc1 target',{'topic':base,'claim':base,'entity':base,'evidence':base},ordinal=0,section_id=0,importance=1)
        mem.add_unit(2,'doc2 similar',{'topic':noisy(base,rng,.01),'claim':noisy(base,rng,.01),'entity':other,'evidence':other},ordinal=0,section_id=0,importance=1)
        mem.rebuild_index()
        r=mem.query_document(1, noisy(base,rng,.02), top_k=3) if False else mem.query_document(1, {'topic':noisy(base,rng,.02)},top_k=3)
        assert r.hits and r.hits[0].slot==s1
        assert all(h.record.conversation_id==1 for h in r.hits)


def test_document_priority_can_be_selected_by_hdc_role_not_metadata(tmp_path):
    from hngfrontier import CallableDocumentAdapter, DocumentUnitEncoding
    rng=np.random.default_rng(9); d=512
    topic=hv(rng,d); role_body=hv(rng,d); role_warn=hv(rng,d)
    def encoder(text, *, context):
        warning='WARN' in text
        return DocumentUnitEncoding(
            heads={'topic':noisy(topic,rng,.03),'claim':noisy(topic,rng,.05),'entity':noisy(topic,rng,.06),'evidence':noisy(topic,rng,.07),'role':noisy(role_warn if warning else role_body,rng,.02)},
            # Deliberately lie in metadata: the HDC role query must find the warning anyway.
            kind='body', importance=.5,
        )
    with HDCDocumentMemory(tmp_path/'doc',hv_dim=d,space_id='roles',auto_index=False) as mem:
        mem.ingest(3,[(f'body {i}',0) for i in range(5)]+[('WARN rare limitation',0)],CallableDocumentAdapter(encoder))
        frame=mem.summarize_document(3,budget_units=2,priority_role_queries={'warning':role_warn},priority_similarity=.85)
        assert any('WARN' in r.source for r in frame.priority_records)
        hdc=frame.to_hdc_context(); assert 'document_heads' in hdc and len(hdc['segments'])==1


def test_corpus_query_preserves_document_provenance(tmp_path):
    dim = 512
    rng = np.random.default_rng(812)
    target = rng.choice(np.array([-1, 1], np.int8), size=dim)
    other = rng.choice(np.array([-1, 1], np.int8), size=dim)
    role = rng.choice(np.array([-1, 1], np.int8), size=dim)
    with HDCDocumentMemory(tmp_path / "corpus", hv_dim=dim, space_id="corpus-test", auto_index=False,
                           index_options={"table_count": 8, "bits_per_table": 8, "sketch_bits": 64}) as docs:
        for doc_id, base in ((101, target), (202, other)):
            for i in range(4):
                v = np.array(base, copy=True)
                flip = np.random.default_rng(doc_id + i).choice(dim, size=8, replace=False)
                v[flip] *= -1
                docs.add_unit(doc_id, f"doc {doc_id} unit {i}",
                              {"topic": v, "claim": v, "entity": v, "evidence": v, "role": role},
                              ordinal=i, section_id=1, kind="body")
        docs.rebuild_index()
        q = docs.query_corpus({"topic": target, "entity": target}, top_k=3,
                              min_similarity={"topic": .80, "entity": .80},
                              required_route_heads=("topic", "entity"), probe_radius=1)
        assert q.hits
        assert q.hits[0].record.conversation_id == 101
        assert all(h.record.namespace == "hng.document" for h in q.hits)
