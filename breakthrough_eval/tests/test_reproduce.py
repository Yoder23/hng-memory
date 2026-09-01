from __future__ import annotations

import argparse
from pathlib import Path

from breakthrough_eval.scripts import reproduce


def test_fresh_clone_core_uses_isolated_deterministic_output() -> None:
    commands = reproduce.commands_for(
        argparse.Namespace(command="fresh-clone-core")
    )

    assert [command.name for command in commands] == [
        "breakthrough_tests_dependency_free",
        "adversarial_250_isolated",
        "compile_results",
    ]
    deterministic = commands[1]
    output_index = deterministic.argv.index("--output") + 1
    output = Path(deterministic.argv[output_index])
    assert output == reproduce.ROOT / ".hng-eval-proof" / "fixed_candidate"
    assert output != reproduce.ROOT / "breakthrough_eval" / "fixed_candidate"


def test_fresh_clone_core_keeps_external_exclusions_explicit() -> None:
    command = reproduce.commands_for(
        argparse.Namespace(command="fresh-clone-core")
    )[0]

    ignored = [value for value in command.argv if value.startswith("--ignore=")]
    assert ignored == [
        "--ignore=breakthrough_eval/tests/test_locomo_hybrid_holdout.py",
        "--ignore=breakthrough_eval/tests/test_locomo_plus_pilot.py",
        "--ignore=breakthrough_eval/tests/test_locomo_reranker_holdout.py",
        "--ignore=breakthrough_eval/tests/test_locomo_retrieval_budget_holdout.py",
    ]
