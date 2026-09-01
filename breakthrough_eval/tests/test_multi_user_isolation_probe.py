from argparse import Namespace
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from breakthrough_eval.scripts.multi_user_isolation_probe import run


def test_scoped_isolation_concurrency_and_backup(tmp_path):
    result = run(
        Namespace(
            records=120,
            tenants=12,
            restart_every=40,
            lifecycle_records=2,
            concurrent_read_checks=48,
            reader_workers=4,
            concurrent_writes=24,
            writer_workers=4,
            database=tmp_path / "isolation.sqlite",
            backup=tmp_path / "isolation-backup.sqlite",
        )
    )

    assert result["status"] == "PASS_WITH_BOUNDARY"
    assert result["config"]["synthetic_user_principals"] == 120
    assert result["config"]["semantic_state"] == "identical across all private records"
    assert result["scoped_zero_leakage"] is True
    assert result["exhaustive_scoped_queries"]["authorized_misses"] == 0
    assert result["exhaustive_scoped_queries"]["cross_tenant_leaks"] == 0
    assert result["exhaustive_scoped_queries"]["cross_user_leaks"] == 0
    assert result["actor_policy"]["role_leaks"] == 0
    assert result["actor_policy"]["authority_leaks"] == 0
    assert result["concurrent_read_queries"]["cross_tenant_leaks"] == 0
    assert result["concurrent_read_queries"]["cross_user_leaks"] == 0
    assert result["concurrent_global_writes"]["completed"] == 24
    assert result["ledger"]["identical"] is True
    assert result["privileged_raw_access"]["get_is_access_controlled"] is False
    assert result["privileged_raw_access"]["direct_get_returns_private_record_by_id"] is True
