"""Pinned local neural reranking primitives for breakthrough evaluations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


DEFAULT_INSTRUCTION = (
    "Given a long-term memory question, retrieve dialogue turns that contain evidence needed "
    "to answer the question."
)


def format_pair(instruction: str, query: str, document: str) -> str:
    """Format a query/document pair using the official Qwen3 reranker interface."""

    return (
        f"<Instruct>: {instruction}\n"
        f"<Query>: {query}\n"
        f"<Document>: {document}"
    )


@dataclass(frozen=True)
class RerankerConfig:
    model_dir: Path
    max_length: int = 2048
    batch_size: int = 16
    instruction: str = DEFAULT_INSTRUCTION
    device: str = "cuda"


class Qwen3Reranker:
    """Minimal deterministic wrapper around Qwen3-Reranker's yes/no logits."""

    prefix = (
        '<|im_start|>system\nJudge whether the Document meets the requirements based on the '
        'Query and the Instruct provided. Note that the answer can only be "yes" or "no".'
        '<|im_end|>\n<|im_start|>user\n'
    )
    suffix = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"

    def __init__(self, config: RerankerConfig) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        if config.max_length <= 0 or config.batch_size <= 0:
            raise ValueError("max_length and batch_size must be positive")
        if not config.model_dir.is_dir():
            raise FileNotFoundError(config.model_dir)
        if config.device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA is required by the frozen reranker configuration")

        self.config = config
        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(
            str(config.model_dir),
            padding_side="left",
            local_files_only=True,
        )
        self.model = AutoModelForCausalLM.from_pretrained(
            str(config.model_dir),
            dtype=torch.float16,
            attn_implementation="sdpa",
            local_files_only=True,
        ).to(config.device).eval()
        self.false_id = self.tokenizer.convert_tokens_to_ids("no")
        self.true_id = self.tokenizer.convert_tokens_to_ids("yes")
        self.prefix_tokens = self.tokenizer.encode(self.prefix, add_special_tokens=False)
        self.suffix_tokens = self.tokenizer.encode(self.suffix, add_special_tokens=False)
        if self.false_id == self.true_id:
            raise RuntimeError("reranker yes/no token ids are not distinct")
        if config.max_length <= len(self.prefix_tokens) + len(self.suffix_tokens):
            raise ValueError("max_length cannot fit the frozen reranker prefix and suffix")

    def _inputs(self, pairs: Sequence[tuple[str, str]]):
        formatted = [
            format_pair(self.config.instruction, query, document)
            for query, document in pairs
        ]
        encoded = self.tokenizer(
            formatted,
            padding=False,
            truncation="longest_first",
            return_attention_mask=False,
            max_length=(
                self.config.max_length
                - len(self.prefix_tokens)
                - len(self.suffix_tokens)
            ),
        )
        encoded["input_ids"] = [
            self.prefix_tokens + item + self.suffix_tokens
            for item in encoded["input_ids"]
        ]
        padded = self.tokenizer.pad(
            encoded,
            padding=True,
            return_tensors="pt",
        )
        return {key: value.to(self.config.device) for key, value in padded.items()}

    def score(self, pairs: Sequence[tuple[str, str]]) -> list[float]:
        if not pairs:
            return []
        scores: list[float] = []
        with self.torch.inference_mode():
            for start in range(0, len(pairs), self.config.batch_size):
                inputs = self._inputs(pairs[start : start + self.config.batch_size])
                logits = self.model(**inputs).logits[:, -1, :]
                binary = logits[:, [self.false_id, self.true_id]]
                relevant = self.torch.softmax(binary, dim=1)[:, 1]
                scores.extend(float(value) for value in relevant.cpu().tolist())
        return scores

    def close(self) -> None:
        del self.model
        if self.config.device == "cuda":
            self.torch.cuda.empty_cache()
