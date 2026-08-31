from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "next_eval" / "raw"


def load(path): return json.loads((RAW / path).read_text(encoding="utf-8"))


rows = []
def add(benchmark, method, metric, value, unit=""):
    rows.append({"tier": "A", "benchmark": benchmark, "method": method, "metric": metric, "value": value, "unit": unit})


adv = load("ADVERSARIAL_11.json")
add("canonical_adversarial", "HNG_0.6.0rc1", "passed", adv["passed"], "count")
add("canonical_adversarial", "HNG_0.6.0rc1", "total", adv["total"], "count")
for case in adv["cases"]: add("canonical_adversarial", "HNG_0.6.0rc1", case["case"], int(case["passed"]), "pass_bool")

behavior = load("BEHAVIORAL.json")
for method, values in (("raw_topk_majority", behavior["raw_topk_majority"]), ("HNG_governed", behavior["hng_governed"])):
    for metric, value in values.items(): add("synthetic_poisoned_action_policy", method, metric, value, "fraction" if "ms" not in metric else "ms")

provider = load("PROVIDER_100K.json")
for metric in ("exact_top1_agreement", "median_ms", "p95_ms", "p99_ms"):
    add("100K_4096bit_independent", "HNG_FAISS_provider", metric, provider[metric], "fraction" if metric == "exact_top1_agreement" else "ms")

gauntlet = load("compat/assistant_gauntlet/ASSISTANT_GAUNTLET.json")
add("compat_assistant_gauntlet", "HNG_0.6.0rc1", "cross_chat_recall", gauntlet["cross_chat_and_action_routing"]["cross_chat_episode_recall"], "fraction")
add("compat_assistant_gauntlet", "HNG_0.6.0rc1", "action_top1", gauntlet["cross_chat_and_action_routing"]["hng_action_top1"], "fraction")
add("compat_assistant_gauntlet", "HNG_0.6.0rc1", "carried_state_accuracy", gauntlet["multi_turn"]["hng_carried_state_accuracy"], "fraction")
add("compat_assistant_gauntlet", "HNG_0.6.0rc1", "noise_15pct_accuracy", gauntlet["noise_stress"]["15pct"]["accuracy"], "fraction")
add("compat_assistant_gauntlet", "HNG_0.6.0rc1", "restart_accuracy", gauntlet["restart"]["working_state_accuracy"], "fraction")

result = {"version": "0.6.0rc1", "evidence_tier": "A - executed locally", "rows": rows}
(ROOT / "next_eval" / "RESULTS.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
with (ROOT / "next_eval" / "RESULTS.csv").open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
    writer.writeheader(); writer.writerows(rows)
print(f"wrote {len(rows)} rows")
