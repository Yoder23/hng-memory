from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "baseline_source" / "hng-frontier-0.5.1a1"
sys.path.insert(0, str(SOURCE / "src"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("benchmark", choices=("assistant_gauntlet", "perspective_gauntlet", "turn_stream", "assistant_readiness"))
    args = parser.parse_args()
    source = SOURCE / "benchmarks" / f"{args.benchmark}.py"
    output = ROOT / "next_eval" / "raw" / "compat" / args.benchmark
    output.mkdir(parents=True, exist_ok=True)
    code = source.read_text(encoding="utf-8")
    # Only output/run directories are adapted; benchmark logic remains byte-for-byte otherwise.
    replacements = {
        "/mnt/data/hng-frontier-0.4.0a1/benchmarks": str(output).replace("\\", "/"),
        "/mnt/data/hng_frontier_03_gauntlet": str((ROOT / "next_eval" / "run_data" / "compat_gauntlet")).replace("\\", "/"),
        "/mnt/data/hng_frontier_03_gauntlet_longchat": str((ROOT / "next_eval" / "run_data" / "compat_gauntlet_longchat")).replace("\\", "/"),
        "/mnt/data/hng_frontier_03_stream": str((ROOT / "next_eval" / "run_data" / "compat_stream")).replace("\\", "/"),
        "/mnt/data/hng-frontier-0.3.0a1/benchmarks": str(output).replace("\\", "/"),
        "/mnt/data/hng_frontier_05_perspective": str((ROOT / "next_eval" / "run_data" / "compat_perspective")).replace("\\", "/"),
        "/mnt/data/hng-frontier-0.5.0a1/benchmarks": str(output).replace("\\", "/"),
        "/mnt/data/hng_frontier_04_readiness": str((ROOT / "next_eval" / "run_data" / "compat_readiness")).replace("\\", "/"),
        "/mnt/data/hng_frontier_03_bench": str((ROOT / "next_eval" / "run_data" / "compat_readiness")).replace("\\", "/"),
        "/mnt/data/hng-frontier-0.3.0a1/benchmarks/ASSISTANT_READINESS.json": str((output / "ASSISTANT_READINESS.json")).replace("\\", "/"),
        "/mnt/data/hng_frontier_gauntlet": str((ROOT / "next_eval" / "run_data" / "compat_gauntlet")).replace("\\", "/"),
        "/tmp/hng-perspective-gauntlet": str((ROOT / "next_eval" / "run_data" / "compat_perspective")).replace("\\", "/"),
    }
    for old, new in replacements.items(): code = code.replace(old, new)
    if args.benchmark == "perspective_gauntlet":
        target = str((output / "PERSPECTIVE_GAUNTLET.json")).replace("\\", "/")
        code = code.replace("OUT=Path(__file__).with_name('PERSPECTIVE_GAUNTLET.json')", f"OUT=Path(r'{target}')")
    namespace = {"__name__": "__main__", "__file__": str(source)}
    sys.argv = [str(source)]
    exec(compile(code, str(source), "exec"), namespace)


if __name__ == "__main__": main()
