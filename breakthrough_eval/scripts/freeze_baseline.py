from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import hashlib
import importlib.metadata as metadata
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Iterable


BASELINE_COMMIT = "e57db1b1e92329e9b8f2b173be9a506d2b898da8"
THREAD_ENVIRONMENT = {
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def command_output(args: list[str], *, cwd: Path, environment: dict[str, str]) -> dict[str, object]:
    started = utc_now()
    clock = time.perf_counter()
    try:
        run = subprocess.run(args, cwd=cwd, env=environment, text=True, capture_output=True, errors="replace")
        return {
            "started_at": started,
            "finished_at": utc_now(),
            "duration_seconds": time.perf_counter() - clock,
            "command": args,
            "returncode": run.returncode,
            "stdout": run.stdout,
            "stderr": run.stderr,
        }
    except Exception as exc:
        return {
            "started_at": started,
            "finished_at": utc_now(),
            "duration_seconds": time.perf_counter() - clock,
            "command": args,
            "returncode": None,
            "stdout": "",
            "stderr": f"{type(exc).__name__}: {exc}",
        }


def environment_manifest(root: Path, environment: dict[str, str]) -> dict[str, object]:
    packages = {}
    for name in (
        "numpy", "pytest", "build", "faiss-cpu", "usearch", "psutil", "scipy",
        "scikit-learn", "pandas",
    ):
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            packages[name] = None

    memory: dict[str, object] = {}
    try:
        import psutil
        memory = {
            "physical_cores": psutil.cpu_count(logical=False),
            "logical_processors": psutil.cpu_count(logical=True),
            "ram_bytes": psutil.virtual_memory().total,
        }
    except Exception as exc:
        memory = {"error": f"{type(exc).__name__}: {exc}"}

    numpy_configuration: object
    try:
        import numpy as np
        try:
            numpy_configuration = np.show_config(mode="dicts")
        except TypeError:
            capture = io.StringIO()
            with redirect_stdout(capture):
                np.show_config()
            numpy_configuration = capture.getvalue()
    except Exception as exc:
        numpy_configuration = {"error": f"{type(exc).__name__}: {exc}"}

    faiss_configuration: dict[str, object] = {}
    try:
        import faiss
        faiss_configuration = {
            "version": getattr(faiss, "__version__", None),
            "compile_options": getattr(faiss, "get_compile_options", lambda: None)(),
            "max_threads": getattr(faiss, "omp_get_max_threads", lambda: None)(),
        }
    except Exception as exc:
        faiss_configuration = {"error": f"{type(exc).__name__}: {exc}"}

    nvidia = command_output(
        ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
        cwd=root,
        environment=environment,
    )
    pip_freeze = command_output(
        [sys.executable, "-m", "pip", "freeze", "--all"], cwd=root, environment=environment
    )
    return {
        "captured_at": utc_now(),
        "baseline_commit": BASELINE_COMMIT,
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "compiler": platform.python_compiler(),
        **memory,
        "packages": packages,
        "thread_environment": {name: environment.get(name) for name in THREAD_ENVIRONMENT},
        "numpy_blas_openmp": numpy_configuration,
        "faiss": faiss_configuration,
        "gpu_probe": {key: nvidia[key] for key in ("returncode", "stdout", "stderr")},
        "pip_freeze_returncode": pip_freeze["returncode"],
        "pip_freeze": pip_freeze["stdout"],
    }


def copy_shipped_evidence(baseline: Path, output: Path) -> list[dict[str, object]]:
    destination = output / "shipped_evidence"
    copied: list[dict[str, object]] = []
    sources = (
        baseline / "closure_eval" / "final",
        baseline / "closure_eval" / "raw",
        baseline / "closure_eval" / "dist",
        baseline / "closure_eval" / "RESULTS.json",
        baseline / "closure_eval" / "ARTIFACTS.json",
        baseline / "next_eval" / "raw",
    )
    if destination.exists():
        return json.loads((output / "SHIPPED_EVIDENCE_MANIFEST.json").read_text(encoding="utf-8"))["files"]
    for source in sources:
        if not source.exists():
            continue
        relative = source.relative_to(baseline)
        target = destination / relative
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    for path in sorted(destination.rglob("*")):
        if path.is_file():
            copied.append({
                "path": path.relative_to(output).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            })
    json_write(output / "SHIPPED_EVIDENCE_MANIFEST.json", {"baseline_commit": BASELINE_COMMIT, "files": copied})
    return copied


def artifact_snapshot(paths: Iterable[Path], *, base: Path) -> list[dict[str, object]]:
    result = []
    for path in paths:
        if path.exists() and path.is_file():
            result.append({
                "path": path.relative_to(base).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            })
    return result


class Runner:
    def __init__(self, baseline: Path, output: Path, environment: dict[str, str]):
        self.baseline = baseline
        self.output = output
        self.environment = environment
        self.raw = output / "raw"
        self.raw.mkdir(parents=True, exist_ok=True)

    def run(self, name: str, args: list[str], *, cwd: Path | None = None) -> dict[str, object]:
        record_path = self.raw / f"{name}.run.json"
        existing_paths = sorted(self.raw.glob(f"{name}*.run.json"))
        for existing_path in reversed(existing_paths):
            existing = json.loads(existing_path.read_text(encoding="utf-8"))
            if existing.get("returncode") == 0:
                print(f"SKIP {name}: preserved successful result from {existing_path.name}")
                return existing
        if record_path.exists():
            revision = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            record_path = self.raw / f"{name}.{revision}.run.json"
        print(f"RUN  {name}")
        record = command_output(args, cwd=cwd or self.baseline, environment=self.environment)
        stdout = str(record.pop("stdout"))
        stderr = str(record.pop("stderr"))
        stdout_path = record_path.with_suffix(".stdout.txt")
        stderr_path = record_path.with_suffix(".stderr.txt")
        stdout_path.write_text(stdout, encoding="utf-8")
        stderr_path.write_text(stderr, encoding="utf-8")
        record["stdout_path"] = stdout_path.relative_to(self.output).as_posix()
        record["stderr_path"] = stderr_path.relative_to(self.output).as_posix()
        json_write(record_path, record)
        print(f"DONE {name}: returncode={record['returncode']} duration={record['duration_seconds']:.3f}s")
        return record


def exact_commit(baseline: Path, environment: dict[str, str]) -> str:
    result = command_output(
        ["git", "-c", f"safe.directory={baseline.as_posix()}", "rev-parse", "HEAD"],
        cwd=baseline,
        environment=environment,
    )
    if result["returncode"] != 0:
        raise RuntimeError(f"cannot read baseline commit: {result['stderr']}")
    return str(result["stdout"]).strip()


def run_core(runner: Runner, python: str) -> None:
    source = runner.baseline / "baseline_source" / "hng-frontier-0.5.1a1"
    runner.run("pytest_94", [
        python, "-m", "pytest", "-q", "-p", "no:cacheprovider",
        str(source / "tests"), "--rootdir", str(source),
        "--junitxml", str(runner.raw / "PYTEST_94.xml"),
    ])
    expanded = [
        source / "tests" / "test_governed_memory.py",
        source / "tests" / "test_closure.py",
        source / "tests" / "test_profile_closure_explicit.py",
        source / "tests" / "test_document_closure_restart.py",
    ]
    runner.run("expanded_adversarial_64", [
        python, "-m", "pytest", "-q", "-p", "no:cacheprovider",
        *(str(path) for path in expanded),
        "--junitxml", str(runner.raw / "EXPANDED_ADVERSARIAL_64.xml"),
    ])
    runner.run("canonical_adversarial_11", [python, str(runner.baseline / "next_eval" / "scripts" / "governed_adversarial.py")])
    generated = runner.baseline / "next_eval" / "raw" / "ADVERSARIAL_11.json"
    if generated.exists():
        shutil.copy2(generated, runner.raw / "ADVERSARIAL_11.json")
    runner.run("fault_concurrency_10", [
        python, str(runner.baseline / "closure_eval" / "scripts" / "fault_injection.py"),
        "--output", str(runner.raw / "FAULT_INJECTION_10.json"),
    ])

    wheel = runner.baseline / "closure_eval" / "dist" / "hng_frontier-0.7.0rc1-py3-none-any.whl"
    with tempfile.TemporaryDirectory(prefix="hng-baseline-wheel-") as directory:
        venv = Path(directory)
        runner.run("wheel_venv", [python, "-m", "venv", "--system-site-packages", str(venv)])
        vpython = venv / "Scripts" / "python.exe" if os.name == "nt" else venv / "bin" / "python"
        runner.run("wheel_install", [str(vpython), "-m", "pip", "install", "--no-deps", str(wheel)])
        runner.run("wheel_smoke", [str(vpython), str(runner.baseline / "closure_eval" / "scripts" / "wheel_smoke.py")])


def run_gauntlets(runner: Runner, python: str) -> None:
    script = runner.baseline / "next_eval" / "scripts" / "run_compat_gauntlet.py"
    for benchmark in ("assistant_readiness", "perspective_gauntlet", "turn_stream", "assistant_gauntlet"):
        runner.run(f"compat_{benchmark}", [python, str(script), benchmark])
        generated = runner.baseline / "next_eval" / "raw" / "compat" / benchmark
        target = runner.raw / "compat" / benchmark
        if generated.exists() and not target.exists():
            shutil.copytree(generated, target)


def run_public(runner: Runner, python: str, qmsum_jsonl: Path | None) -> None:
    runner.run("performance_profile", [
        python, str(runner.baseline / "closure_eval" / "scripts" / "performance_profile.py"),
        "--records", "1000", "--queries", "300", "--dim", "2048",
        "--output", str(runner.raw / "PERFORMANCE_PROFILE.json"),
    ])
    if qmsum_jsonl is None:
        json_write(runner.raw / "qmsum_governed_20.run.json", {
            "returncode": None,
            "status": "BLOCKED_EXTERNAL",
            "reason": "--qmsum-jsonl was not supplied",
        })
        print("BLOCKED qmsum_governed_20: --qmsum-jsonl absent")
        return
    runner.run("qmsum_governed_20", [
        python, str(runner.baseline / "closure_eval" / "scripts" / "qmsum_governed_eval.py"),
        str(qmsum_jsonl), "--limit", "20", "--dim", "4096", "--top-k", "5",
        "--output", str(runner.raw / "QMSUM_GOVERNED_20.json"),
    ])


def run_providers(runner: Runner, python: str) -> None:
    closure = runner.baseline / "closure_eval" / "scripts"
    runner.run("providers_100k", [
        python, str(closure / "provider_closure_benchmark.py"),
        "--n", "100000", "--dim", "4096", "--queries", "80",
        "--modes", "faiss-flat", "faiss-ivf", "faiss-hnsw", "faiss-multihash", "usearch",
        "--output", str(runner.raw / "PROVIDERS_100K.json"),
    ])
    runner.run("provider_geometries_100k", [
        python, str(closure / "provider_geometry_benchmark.py"),
        "--n", "100000", "--dim", "4096", "--queries", "80",
        "--output", str(runner.raw / "PROVIDER_GEOMETRIES_100K.json"),
    ])
    runner.run("providers_1m", [
        python, str(closure / "provider_closure_benchmark.py"),
        "--n", "1000000", "--dim", "4096", "--queries", "30",
        "--modes", "faiss-flat", "faiss-ivf", "faiss-multihash",
        "--output", str(runner.raw / "PROVIDERS_1M.json"),
    ])


def run_10m(runner: Runner, python: str) -> None:
    runner.run("inherited_retrieval_10m", [
        python, str(runner.baseline / "research_eval" / "scripts" / "retrieval_10m_attempt.py")
    ])
    generated = runner.baseline / "research_eval" / "raw" / "retrieval_kernel_10m.results.json"
    if generated.exists():
        shutil.copy2(generated, runner.raw / "RETRIEVAL_10M.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--batch", choices=("core", "gauntlets", "public", "providers", "10m"), required=True)
    parser.add_argument("--qmsum-jsonl", type=Path)
    args = parser.parse_args()
    baseline = args.baseline_root.resolve()
    output = args.output_root.resolve()
    output.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.update(THREAD_ENVIRONMENT)
    program_root = Path(__file__).resolve().parents[2]
    vendor_root = program_root / "research_eval" / "vendor"
    if vendor_root.exists():
        existing_pythonpath = environment.get("PYTHONPATH", "")
        environment["PYTHONPATH"] = str(vendor_root) + (
            os.pathsep + existing_pythonpath if existing_pythonpath else ""
        )
    commit = exact_commit(baseline, environment)
    if commit != BASELINE_COMMIT:
        raise SystemExit(f"refusing mutable baseline: expected {BASELINE_COMMIT}, found {commit}")

    (output / "BASELINE_COMMIT.txt").write_text(BASELINE_COMMIT + "\n", encoding="utf-8")
    manifest_path = output / "ENVIRONMENT.json"
    if not manifest_path.exists():
        manifest = environment_manifest(baseline, environment)
        manifest["external_vendor_root"] = str(vendor_root) if vendor_root.exists() else None
        json_write(manifest_path, manifest)
        (output / "DEPENDENCIES.lock.txt").write_text(str(manifest["pip_freeze"]), encoding="utf-8")
    copied = copy_shipped_evidence(baseline, output)
    if vendor_root.exists() and not (output / "VENDOR_MANIFEST.json").exists():
        vendor_files = artifact_snapshot(vendor_root.rglob("*"), base=vendor_root)
        json_write(output / "VENDOR_MANIFEST.json", {
            "source": str(vendor_root),
            "faiss_cpu": "1.15.0",
            "usearch": "2.26.1",
            "files": vendor_files,
        })
        json_write(output / "EXECUTION_DEPENDENCIES.json", {
            "pythonpath_vendor": str(vendor_root),
            "faiss_cpu": "1.15.0",
            "usearch": "2.26.1",
            "reason": "binary dependencies are intentionally untracked and absent from the detached Git worktree",
        })
    runner = Runner(baseline, output, environment)
    if args.batch == "core":
        run_core(runner, sys.executable)
    elif args.batch == "gauntlets":
        run_gauntlets(runner, sys.executable)
    elif args.batch == "public":
        run_public(runner, sys.executable, None if args.qmsum_jsonl is None else args.qmsum_jsonl.resolve())
    elif args.batch == "providers":
        run_providers(runner, sys.executable)
    else:
        run_10m(runner, sys.executable)

    files = [
        item
        for item in artifact_snapshot(output.rglob("*"), base=output)
        if item["path"] != "BASELINE_MANIFEST.json"
    ]
    json_write(output / "BASELINE_MANIFEST.json", {
        "baseline_commit": BASELINE_COMMIT,
        "generated_at": utc_now(),
        "last_batch": args.batch,
        "shipped_evidence_files": len(copied),
        "files": files,
    })
    attempts: dict[str, list[dict[str, object]]] = {}
    for path in sorted((output / "raw").glob("*.run.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        logical_name = path.name.split(".", 1)[0]
        attempts.setdefault(logical_name, []).append({
            "path": path.relative_to(output).as_posix(),
            "returncode": record.get("returncode"),
            "status": record.get("status", "PASSED" if record.get("returncode") == 0 else "FAILED"),
        })
    failures = [
        values[-1]
        for values in attempts.values()
        if not any(value.get("returncode") == 0 for value in values)
    ]
    json_write(output / "BASELINE_STATUS.json", {
        "baseline_commit": BASELINE_COMMIT,
        "updated_at": utc_now(),
        "last_batch": args.batch,
        "attempts": attempts,
        "failures_or_blocks": failures,
    })
    print(json.dumps({"baseline_commit": BASELINE_COMMIT, "batch": args.batch,
                      "failures_or_blocks": failures}, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
