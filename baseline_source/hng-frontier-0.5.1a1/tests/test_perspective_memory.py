from __future__ import annotations

from pathlib import Path
import numpy as np

from hngfrontier import (
    AssistantMemory, CallableAssistantAdapter, MemoryFilter,
    PerspectiveOverride, PerspectivePolicy, PerspectiveProfile,
)

DIM = 2048

def hv(seed: int):
    return np.random.default_rng(seed).choice(np.array([-1, 1], dtype=np.int8), size=DIM)

def heads(seed: int, *, action=None, perspective=None, expertise=None, priority=None):
    out = {
        "state": hv(seed+1), "goal": hv(seed+2), "entity": hv(seed+3), "sequence": hv(seed+4),
        "action": hv(seed+5) if action is None else action, "next_state": hv(seed+6),
    }
    if perspective is not None: out["perspective"] = perspective
    if expertise is not None: out["expertise"] = expertise
    if priority is not None: out["priority"] = priority
    return out


def profile(user: str, role: str, authority: int, abstraction: int, *, priority="reliability"):
    return PerspectiveProfile(
        user_id=user, tenant_id="acme", role=role, authority_level=authority,
        abstraction_level=abstraction, expertise={"engineering": .9},
        responsibilities=("software delivery",), priorities=(priority,),
    )


def test_profile_and_active_role_override_survive_restart(tmp_path: Path):
    root = tmp_path / "mem"
    with AssistantMemory(root, hv_dim=DIM, space_id="p", auto_index=False) as mem:
        p = mem.set_user_profile(profile("u1", "individual-contributor", 1, 1))
        assert p.revision == 1
        eff = mem.activate_perspective(77, "u1", PerspectiveOverride(
            role="engineering-manager", authority_level=2, abstraction_level=2,
            priorities=("team-delivery",),
        ))
        assert eff.role == "engineering-manager" and eff.active_override
    with AssistantMemory(root, hv_dim=DIM, space_id="p", auto_index=False) as mem:
        eff = mem.perspective(77)
        assert eff is not None
        assert eff.user_id == "u1" and eff.role == "engineering-manager"
        assert eff.authority_level == 2 and eff.priorities == ("team-delivery",)


def test_adapter_receives_effective_perspective(tmp_path: Path):
    root = tmp_path / "mem"
    seen = {}
    with AssistantMemory(root, hv_dim=DIM, space_id="p", auto_index=False) as mem:
        mem.set_user_profile(profile("u1", "staff-engineer", 2, 2, priority="correctness"))
        mem.activate_perspective(9, "u1")
        adapter = CallableAssistantAdapter(lambda value, *, context: (
            seen.update(context.perspective.as_dict() if context.perspective else {}),
            {"state": hv(4)}
        )[1])
        mem.encode_query(adapter, "same words", conversation_id=9)
        assert seen["role"] == "staff-engineer"
        assert seen["priorities"] == ["correctness"]
        assert seen["expertise"]["engineering"] == .9


def test_private_memory_never_crosses_user_boundary(tmp_path: Path):
    root = tmp_path / "mem"
    state = hv(100); action_a = hv(200); action_b = hv(300)
    with AssistantMemory(root, hv_dim=DIM, space_id="p", auto_index=False,
                         index_options={"table_count":12,"bits_per_table":10,"sketch_bits":128}) as mem:
        mem.set_user_profile(profile("alice", "engineer", 1, 1))
        mem.set_user_profile(profile("bob", "engineer", 1, 1))
        # Same semantic state and role, opposite private experiences.
        mem.activate_perspective(1, "alice")
        mem.record_transition({"state":state,"goal":hv(101),"entity":hv(102),"sequence":hv(103),"action":action_a},
                              "alice private success", conversation_id=1, episode_id=1,
                              action="alice-action", outcome="worked", outcome_score=1.0)
        mem.activate_perspective(2, "bob")
        mem.record_transition({"state":state,"goal":hv(101),"entity":hv(102),"sequence":hv(103),"action":action_b},
                              "bob private success", conversation_id=2, episode_id=1,
                              action="bob-action", outcome="worked", outcome_score=1.0)
        mem.rebuild_index()
        q={"state":state,"goal":hv(101),"entity":hv(102),"sequence":hv(103)}
        a=mem.recommend_actions(q, conversation_id=1, max_actions=5, semantic_floor=.8)
        b=mem.recommend_actions(q, conversation_id=2, max_actions=5, semantic_floor=.8)
        assert [x.label for x in a] == ["alice-action"]
        assert [x.label for x in b] == ["bob-action"]


def test_role_authority_gating_beats_semantics_only(tmp_path: Path):
    root = tmp_path / "mem"
    context={"state":hv(500),"goal":hv(501),"entity":hv(502),"sequence":hv(503)}
    ic_action=hv(600); exec_action=hv(601)
    with AssistantMemory(root, hv_dim=DIM, space_id="p", auto_index=False,
                         index_options={"table_count":16,"bits_per_table":10,"sketch_bits":128}) as mem:
        mem.set_user_profile(profile("ic-user", "ic", 1, 1))
        mem.set_user_profile(profile("exec-user", "executive", 5, 4))
        # Shared tenant evidence; exec has more precedents, so semantics-only follows the wrong level for IC.
        mem.activate_perspective(10, "ic-user")
        for i in range(2):
            h=dict(context); h["action"]=ic_action
            mem.record_transition(h, f"ic {i}", conversation_id=10, episode_id=i+1,
                                  action="profile-query-plan", outcome="worked", outcome_score=1.0,
                                  memory_scope="tenant")
        mem.activate_perspective(20, "exec-user")
        for i in range(6):
            h=dict(context); h["action"]=exec_action
            mem.record_transition(h, f"exec {i}", conversation_id=20, episode_id=i+1,
                                  action="reorganize-platform-ownership", outcome="worked", outcome_score=1.0,
                                  memory_scope="tenant")
        mem.rebuild_index()
        mem.activate_perspective(99, "ic-user")
        raw=mem.recommend_actions(context, conversation_id=99, max_actions=2, semantic_floor=.8,
                                  perspective_policy=PerspectivePolicy.disabled())
        gated=mem.recommend_actions(context, conversation_id=99, max_actions=2, semantic_floor=.8)
        assert raw[0].label == "reorganize-platform-ownership"
        assert gated[0].label == "profile-query-plan"
        assert all(x.label != "reorganize-platform-ownership" for x in gated)


def test_perspective_semantic_heads_disambiguate_same_role(tmp_path: Path):
    root = tmp_path / "mem"
    base={"state":hv(700),"goal":hv(701),"entity":hv(702),"sequence":hv(703)}
    phead=hv(710); novice=hv(711); expert=hv(712); speed=hv(713); safety=hv(714)
    fast_action=hv(720); safe_action=hv(721)
    with AssistantMemory(root, hv_dim=DIM, space_id="p", auto_index=False,
                         index_options={"table_count":16,"bits_per_table":10,"sketch_bits":128}) as mem:
        mem.set_user_profile(profile("speed-user", "ic", 1, 1, priority="speed"))
        mem.set_user_profile(profile("safety-user", "ic", 1, 1, priority="safety"))
        mem.activate_perspective(1, "speed-user")
        for i in range(3):
            h={**base,"perspective":phead,"expertise":expert,"priority":speed,"action":fast_action}
            mem.record_transition(h, f"speed {i}", conversation_id=1, episode_id=i+1,
                                  action="fast-local-fix", outcome="worked", outcome_score=1.0,
                                  memory_scope="tenant")
        mem.activate_perspective(2, "safety-user")
        for i in range(3):
            h={**base,"perspective":phead,"expertise":expert,"priority":safety,"action":safe_action}
            mem.record_transition(h, f"safety {i}", conversation_id=2, episode_id=i+1,
                                  action="validated-safe-fix", outcome="worked", outcome_score=1.0,
                                  memory_scope="tenant")
        mem.rebuild_index()
        mem.activate_perspective(99, "safety-user")
        q={**base,"perspective":phead,"expertise":expert,"priority":safety}
        out=mem.recommend_actions(q, conversation_id=99, max_actions=4, semantic_floor=.8)
        assert out[0].label == "validated-safe-fix"
        assert all(x.label != "fast-local-fix" for x in out)

def test_tenant_scope_is_hard_isolation_but_global_is_visible(tmp_path: Path):
    root=tmp_path/'mem'
    state=hv(880); action=hv(881)
    with AssistantMemory(root,hv_dim=DIM,space_id='p',auto_index=False) as mem:
        mem.set_user_profile(PerspectiveProfile('a','tenant-a','ic',1,1))
        mem.set_user_profile(PerspectiveProfile('b','tenant-b','ic',1,1))
        mem.activate_perspective(1,'a')
        h={'state':state,'goal':hv(882),'entity':hv(883),'sequence':hv(884),'action':action}
        mem.record_transition(h,'tenant-a-only',conversation_id=1,episode_id=1,action='tenant-a-action',outcome='worked',outcome_score=1,memory_scope='tenant')
        mem.record_transition(h,'global',conversation_id=1,episode_id=2,action='global-action',outcome='worked',outcome_score=1,memory_scope='global')
        mem.activate_perspective(2,'b')
        mem.rebuild_index()
        q={k:h[k] for k in ('state','goal','entity','sequence')}
        out=mem.recommend_actions(q,conversation_id=2,max_actions=8,semantic_floor=.8)
        labels={x.label for x in out}
        assert 'tenant-a-action' not in labels
        assert 'global-action' in labels


def test_experience_keeps_perspective_revision_snapshot(tmp_path: Path):
    root=tmp_path/'mem'
    with AssistantMemory(root,hv_dim=DIM,space_id='p',auto_index=False) as mem:
        first=mem.set_user_profile(profile('u1','ic',1,1,priority='speed'))
        mem.activate_perspective(1,'u1')
        slot1=mem.record_transition(heads(9100),'old',conversation_id=1,episode_id=1).slot
        second=mem.set_user_profile(profile('u1','ic',1,1,priority='safety'))
        slot2=mem.record_transition(heads(9200),'new',conversation_id=1,episode_id=2).slot
        r1=mem.memory.db.get(slot1); r2=mem.memory.db.get(slot2)
        assert r1 is not None and r2 is not None
        assert r1.perspective_version==first.revision
        assert r2.perspective_version==second.revision
        assert r2.perspective_version>r1.perspective_version

def test_v04_experience_store_schema_migrates_before_actor_indexes(tmp_path: Path):
    import sqlite3, json
    from hngfrontier.store import ExperienceStore
    db=tmp_path/'old.sqlite'
    con=sqlite3.connect(db)
    con.executescript('''
    CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE memories(
      slot INTEGER PRIMARY KEY,timestamp_ns INTEGER NOT NULL,conversation_id INTEGER NOT NULL DEFAULT 0,
      episode_id INTEGER NOT NULL DEFAULT 0,role TEXT NOT NULL DEFAULT '',record_type TEXT NOT NULL DEFAULT '',
      namespace TEXT NOT NULL DEFAULT '',namespace_hash BLOB NOT NULL,importance REAL NOT NULL DEFAULT 0.0,
      deleted INTEGER NOT NULL DEFAULT 0,head_mask INTEGER NOT NULL DEFAULT 0,source TEXT NOT NULL,
      action TEXT NOT NULL DEFAULT '',outcome TEXT NOT NULL DEFAULT '',outcome_score REAL NOT NULL DEFAULT 0.0,
      extra_json TEXT NOT NULL DEFAULT '{}');
    CREATE TABLE tags(slot INTEGER NOT NULL,tag TEXT NOT NULL,PRIMARY KEY(slot,tag)) WITHOUT ROWID;
    CREATE TABLE relations(src_slot INTEGER NOT NULL,relation TEXT NOT NULL,dst_slot INTEGER NOT NULL,weight REAL NOT NULL DEFAULT 1.0,PRIMARY KEY(src_slot,relation,dst_slot)) WITHOUT ROWID;
    ''')
    heads=('state','goal')
    vals={'schema_version':'2','hv_dim':str(DIM),'space_id':'old','heads':json.dumps(heads,separators=(',',':')),'committed_count':'0','metadata_epoch':'0'}
    con.executemany('INSERT INTO meta(key,value) VALUES(?,?)',vals.items());con.commit();con.close()
    store=ExperienceStore(db,hv_dim=DIM,heads=heads,space_id='old')
    cols={r[1] for r in store.con.execute('PRAGMA table_info(memories)')}
    assert {'tenant_id','actor_user_id','actor_role','authority_level','abstraction_level','memory_scope','perspective_version'} <= cols
    assert store.con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0]=='3'
    store.close()
