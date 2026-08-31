from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
import threading
from typing import Mapping

from .governance import Decision, GovernedMemoryFrame, utc_now_iso


class DeploymentMode(str, Enum):
    SHADOW = "shadow"
    CONTEXT_AUGMENTATION = "context_augmentation"
    ADVISORY_CHALLENGE = "advisory_challenge"
    HARD_GATE = "hard_gate"


@dataclass(frozen=True, slots=True)
class DeploymentDecision:
    mode: DeploymentMode
    would_block: bool
    blocks: bool
    decision: Decision
    reason: str


class GovernedShadowEvaluator:
    """Append-only rollout log. Hard blocking is opt-in and never the default."""

    def __init__(self, path: str | Path, *, mode: DeploymentMode = DeploymentMode.SHADOW,
                 allow_hard_gate: bool = False):
        if mode is DeploymentMode.HARD_GATE and not allow_hard_gate:
            raise ValueError("hard gate requires explicit allow_hard_gate=True")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.mode = mode
        self.allow_hard_gate = allow_hard_gate
        self._lock = threading.Lock()

    def decide(self, frame: GovernedMemoryFrame) -> DeploymentDecision:
        would_block = frame.assessment.decision in {
            Decision.CHALLENGE, Decision.INSUFFICIENT_STATE, Decision.UNTRUSTED_EVIDENCE, Decision.PROFILE_UNCERTAIN,
        }
        blocks = self.mode is DeploymentMode.HARD_GATE and self.allow_hard_gate and would_block
        return DeploymentDecision(self.mode, would_block, blocks, frame.assessment.decision,
                                  frame.assessment.reasons[0] if frame.assessment.reasons else "")

    def log(self, frame: GovernedMemoryFrame, *, assistant_action: str = "",
            outcome: Mapping[str, object] | None = None) -> DeploymentDecision:
        decision = self.decide(frame)
        payload = {
            "timestamp": utc_now_iso(), "mode": self.mode.value, "assistant_action": assistant_action,
            "would_block": decision.would_block, "blocks": decision.blocks,
            "hng": frame.as_dict(), "observed_outcome": dict(outcome or {}),
        }
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
        return decision

    def summarize(self) -> dict[str, object]:
        counts: dict[str, int] = {}
        records = blocks = would_block = 0
        if not self.path.exists():
            return {"records": 0, "decisions": {}, "would_block": 0, "blocks": 0}
        for line in self.path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            records += 1
            decision = row["hng"]["assessment"]["decision"]
            counts[decision] = counts.get(decision, 0) + 1
            would_block += int(row["would_block"])
            blocks += int(row["blocks"])
        return {"records": records, "decisions": counts, "would_block": would_block, "blocks": blocks}

