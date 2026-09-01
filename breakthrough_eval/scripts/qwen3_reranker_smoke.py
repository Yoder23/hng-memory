"""Smoke-test the pinned local Qwen3 reranker without benchmark score access."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from breakthrough_eval.reranking import Qwen3Reranker, RerankerConfig


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    args = parser.parse_args()
    reranker = Qwen3Reranker(RerankerConfig(args.model_dir, max_length=512, batch_size=2))
    try:
        query = "Which planet is known as the Red Planet?"
        documents = [
            "Mars is known for its reddish appearance and is called the Red Planet.",
            "Venus has a dense atmosphere and is sometimes called Earth's twin.",
        ]
        scores = reranker.score([(query, document) for document in documents])
        print(json.dumps({"scores": scores, "relevant_first": scores[0] > scores[1]}, indent=2))
        return 0 if scores[0] > scores[1] else 1
    finally:
        reranker.close()


if __name__ == "__main__":
    raise SystemExit(main())
