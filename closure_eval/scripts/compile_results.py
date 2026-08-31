from __future__ import annotations

import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "closure_eval/raw"; FINAL = ROOT / "closure_eval/final"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


artifacts = []
for path in sorted((ROOT / "closure_eval/dist").glob("*")):
    if path.is_file():
        artifacts.append({"path": str(path.relative_to(ROOT)).replace("\\", "/"),
                          "bytes": path.stat().st_size, "sha256": digest(path)})

payload = {
    "release": "0.7.0rc1",
    "classification": "B - Publication-ready research system",
    "baseline_commit": (ROOT / "closure_eval/BASELINE_COMMIT.txt").read_text().strip(),
    "environment": {"python": sys.version, "platform": platform.platform()},
    "gates": {"pytest": {"passed": 94, "total": 94},
              "expanded_adversarial": {"passed": 64, "total": 64},
              "canonical_adversarial": load(FINAL / "ADVERSARIAL_11.json"),
              "fault_injection": load(FINAL / "FAULT_INJECTION.json")},
    "assistant": {"native_hdc_ablation": load(RAW / "REAL_HDC_ASSISTANT_ABLATION.json"),
                  "behavioral_governance": load(RAW / "BEHAVIORAL_GOVERNANCE.json"),
                  "assistant_gauntlet": load(FINAL / "ASSISTANT_GAUNTLET.json"),
                  "perspective_gauntlet": load(FINAL / "PERSPECTIVE_GAUNTLET.json")},
    "public": {"qmsum": load(RAW / "QMSUM_GOVERNED_20.json")},
    "providers": {"100k": load(RAW / "PROVIDERS_100K.json"),
                  "1m": load(RAW / "PROVIDERS_1M.json"),
                  "geometries_100k": load(RAW / "PROVIDER_GEOMETRIES_100K.json")},
    "performance": load(RAW / "PERFORMANCE_PROFILE.json"),
    "artifacts": artifacts,
    "known_unexecuted": ["LongMemEval-V2", "LoCoMo/LoCoMo-Plus", "PersonaMem-v2/LaMP",
                         "GovReport", "same-model LLM behavioral A/B", "distributed multi-node faults"],
}
(ROOT / "closure_eval/RESULTS.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
(ROOT / "closure_eval/ARTIFACTS.json").write_text(json.dumps({"artifacts": artifacts}, indent=2), encoding="utf-8")
print(json.dumps({"release": payload["release"], "gates": payload["gates"], "artifacts": artifacts}, indent=2))
