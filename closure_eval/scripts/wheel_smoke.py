from pathlib import Path
import tempfile

import numpy as np

import hngfrontier
from hngfrontier import EvidenceProvenance, HNGMemory, SemanticState, SemanticValue

assert hngfrontier.__version__ == "0.7.0rc1"
vector = SemanticValue.hdc(np.ones(256, dtype=np.int8), dimension=256)
state = SemanticState({"state": vector, "goal": vector, "sequence": vector})
with tempfile.TemporaryDirectory(prefix="hng-wheel-smoke-") as directory:
    with HNGMemory(Path(directory), semantic_backend="reference-hng") as memory:
        memory.observe("installed wheel evidence", state,
                       provenance=EvidenceProvenance("system_telemetry", "wheel-smoke", 1, True))
        assert memory.stats()["records"] == 1
print("wheel smoke passed", hngfrontier.__version__)
