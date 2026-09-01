from pathlib import Path

import pytest

from breakthrough_eval.reranking import DEFAULT_INSTRUCTION, RerankerConfig, format_pair


def test_format_pair_is_explicit_and_deterministic() -> None:
    assert format_pair("instruction", "query", "document") == (
        "<Instruct>: instruction\n<Query>: query\n<Document>: document"
    )


def test_frozen_defaults() -> None:
    config = RerankerConfig(Path("model"))
    assert config.max_length == 2048
    assert config.batch_size == 16
    assert config.instruction == DEFAULT_INSTRUCTION
    assert config.device == "cuda"


@pytest.mark.parametrize("max_length,batch_size", [(0, 1), (1, 0)])
def test_invalid_dimensions_are_rejected_before_model_load(
    tmp_path: Path,
    max_length: int,
    batch_size: int,
) -> None:
    from breakthrough_eval.reranking import Qwen3Reranker

    with pytest.raises(ValueError):
        Qwen3Reranker(
            RerankerConfig(tmp_path, max_length=max_length, batch_size=batch_size)
        )
