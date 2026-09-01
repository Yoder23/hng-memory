from __future__ import annotations

from breakthrough_eval.scripts import policy_differential_search as search


def test_development_grid_is_complete_and_unique() -> None:
    cases = search.generate_cases()

    expected = len(search.EvidenceKind) * len(search.TRUST_SOURCE) * 2 * 2 * 2
    assert len(cases) == expected
    assert len({scenario.case_id for scenario, _inputs in cases}) == expected


def test_report_remains_unlabeled_development_evidence() -> None:
    report = search.build_report()

    assert report["status"] == "DEVELOPMENT_ONLY_COMPLETE"
    assert report["summary"]["case_count"] == len(search.generate_cases())
    assert report["summary"]["hng_decisive_strong_nondecisive_count"] == 0
    assert "no outcome labels" in report["claim_boundary"]
    assert all(
        scenario.expected == "UNLABELED_DEVELOPMENT"
        for scenario, _inputs in search.generate_cases()
    )
