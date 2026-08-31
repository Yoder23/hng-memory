"""Run shipped HNG examples/benchmarks with path-only Windows adapters.

The release scripts hard-code POSIX-rooted /tmp and /mnt/data locations.  This
runner preserves their computation and seeds, changes only filesystem targets,
captures stdout/stderr, and writes the exact adapted source for audit.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "baseline_source" / "hng-frontier-0.5.1a1"
RAW = ROOT / "research_eval" / "raw"
ADAPTED = ROOT / "research_eval" / "scripts" / "adapted_shipped"
RUNS = ROOT / "research_eval" / "run_data"


def py_path(path: Path) -> str:
    return "Path(" + repr(str(path.resolve())) + ")"


def adapt(name: str, relpath: str, replacements: dict[str, str], argv: list[str] | None = None) -> dict:
    source_path = SOURCE / relpath
    text = source_path.read_text(encoding="utf-8")
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError(f"adapter token missing in {relpath}: {old}")
        text = text.replace(old, new)
    adapted_path = ADAPTED / relpath
    adapted_path.parent.mkdir(parents=True, exist_ok=True)
    adapted_path.write_text(text, encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(SOURCE / "src")
    cmd = [sys.executable, str(adapted_path), *(argv or [])]
    started = time.time()
    proc = subprocess.run(cmd, cwd=SOURCE, env=env, text=True, capture_output=True)
    elapsed = time.time() - started
    (RAW / f"{name}.stdout.txt").write_text(proc.stdout, encoding="utf-8")
    (RAW / f"{name}.stderr.txt").write_text(proc.stderr, encoding="utf-8")
    result = {
        "name": name,
        "source": str(source_path.relative_to(ROOT)),
        "adapted_source": str(adapted_path.relative_to(ROOT)),
        "replacements": replacements,
        "argv": argv or [],
        "command": cmd,
        "exit_code": proc.returncode,
        "elapsed_seconds": elapsed,
    }
    (RAW / f"{name}.run.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"{name}: exit={proc.returncode} elapsed={elapsed:.3f}s")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="skip the large assistant gauntlet")
    args = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    ADAPTED.mkdir(parents=True, exist_ok=True)
    RUNS.mkdir(parents=True, exist_ok=True)

    specs: list[tuple[str, str, dict[str, str], list[str]]] = [
        ("example_multichat", "examples/synthetic_multichat_demo.py", {
            'Path("/tmp/hng-frontier-multichat-demo")': py_path(RUNS / "example_multichat"),
        }, []),
        ("example_document", "examples/synthetic_document_demo.py", {
            'Path("/tmp/hng-frontier-document-demo")': py_path(RUNS / "example_document"),
        }, []),
        ("example_perspective", "examples/perspective_digital_twin_demo.py", {
            "Path('/tmp/hng-perspective-demo')": py_path(RUNS / "example_perspective"),
        }, []),
        ("perspective_gauntlet", "benchmarks/perspective_gauntlet.py", {
            "Path('/tmp/hng-perspective-gauntlet')": py_path(RUNS / "perspective_gauntlet"),
            "Path(__file__).with_name('PERSPECTIVE_GAUNTLET.json')": py_path(RAW / "perspective_gauntlet.results.json"),
        }, []),
        ("document_breakthrough", "benchmarks/document_breakthrough.py", {}, [
            "--root", str(RUNS / "document_breakthrough"),
            "--out", str(RAW / "document_breakthrough.results.json"),
        ]),
        ("assistant_ablation", "benchmarks/assistant_breakthrough_ablation.py", {
            "Path('/mnt/data/hng_assistant_ablation_04')": py_path(RUNS / "assistant_ablation"),
            "Path('/mnt/data/hng-frontier-0.4.0a1/benchmarks/ASSISTANT_ABLATION.json')": py_path(RAW / "assistant_ablation.results.json"),
        }, []),
        ("assistant_readiness", "benchmarks/assistant_readiness.py", {
            "Path('/mnt/data/hng_frontier_03_bench')": py_path(RUNS / "assistant_readiness"),
            "Path('/mnt/data/hng-frontier-0.3.0a1/benchmarks/ASSISTANT_READINESS.json')": py_path(RAW / "assistant_readiness.results.json"),
        }, []),
        ("turn_stream", "benchmarks/turn_stream.py", {
            "Path('/mnt/data/hng_frontier_03_stream')": py_path(RUNS / "turn_stream"),
            "Path('/mnt/data/hng-frontier-0.3.0a1/benchmarks/TURN_STREAM.json')": py_path(RAW / "turn_stream.results.json"),
        }, []),
        ("document_noise", "benchmarks/document_noise_stress.py", {
            "Path('/mnt/data/hng_doc_breakthrough_full_v3')": py_path(RUNS / "document_breakthrough"),
            "Path('/mnt/data/hng-frontier-0.4.0a1/benchmarks/DOCUMENT_NOISE.json')": py_path(RAW / "document_noise.results.json"),
        }, []),
        ("document_scale", "benchmarks/document_scale.py", {
            "Path('/mnt/data/hng_doc_scale')": py_path(RUNS / "document_scale"),
            "Path('/mnt/data/hng-frontier-0.4.0a1/benchmarks/DOCUMENT_SCALE.json')": py_path(RAW / "document_scale.results.json"),
        }, []),
    ]
    if not args.quick:
        specs.append(("assistant_gauntlet", "benchmarks/assistant_gauntlet.py", {
            "Path('/mnt/data/hng-frontier-0.4.0a1/benchmarks')": py_path(RAW),
        }, ["--root", str(RUNS / "assistant_gauntlet")]))

    results = []
    for name, relpath, replacements, argv in specs:
        results.append(adapt(name, relpath, replacements, argv))
    manifest = {"runner_python": sys.version, "results": results}
    (RAW / "shipped_runs.manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return 0 if all(x["exit_code"] == 0 for x in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
