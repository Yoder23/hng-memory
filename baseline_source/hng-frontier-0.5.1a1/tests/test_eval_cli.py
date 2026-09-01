from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from hngfrontier import eval_cli


def make_checkout(root: Path) -> Path:
    runner = root / eval_cli.RELATIVE_RUNNER
    runner.parent.mkdir(parents=True)
    runner.write_text("raise SystemExit(0)\n", encoding="utf-8")
    return root


def test_resolve_explicit_and_parent_search(tmp_path, monkeypatch):
    root = make_checkout(tmp_path / "repo")
    nested = root / "a" / "b"
    nested.mkdir(parents=True)
    assert eval_cli.resolve_repo_root(root) == root.resolve()
    monkeypatch.chdir(nested)
    assert eval_cli.resolve_repo_root(None) == root.resolve()


def test_missing_checkout_fails_closed(tmp_path):
    with pytest.raises(FileNotFoundError, match="--repo-root"):
        eval_cli.resolve_repo_root(tmp_path)


def test_command_uses_current_interpreter_and_no_shell(tmp_path):
    root = make_checkout(tmp_path)
    command = eval_cli.command_for(root, ["--dry-run", "core"])
    assert command == [eval_cli.sys.executable, str(root / eval_cli.RELATIVE_RUNNER), "--dry-run", "core"]


def test_main_forwards_and_returns_runner_status(tmp_path, monkeypatch):
    root = make_checkout(tmp_path)
    observed = {}

    def fake_run(command, *, cwd, check):
        observed.update(command=command, cwd=cwd, check=check)
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(eval_cli.subprocess, "run", fake_run)
    assert eval_cli.main(["--repo-root", str(root), "--dry-run", "core"]) == 7
    assert observed["command"][-2:] == ["--dry-run", "core"]
    assert observed["cwd"] == root.resolve()
    assert observed["check"] is False
