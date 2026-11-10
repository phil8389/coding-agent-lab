"""Check workspace boundaries and Docker delegation without running fixtures."""

from pathlib import Path
import subprocess
from unittest.mock import Mock

import pytest

from adapters.sandbox import runner
from adapters.sandbox.repair_tools import RepairTools, safe_path
from core.models import TestResult


def test_read_file(tmp_path):
    (tmp_path / "sample.txt").write_text("café", encoding="utf-8")
    assert RepairTools(tmp_path).read_file("sample.txt") == "café"


@pytest.mark.parametrize("path", ["/secret.txt", "C:/secret.txt", r"C:\secret.txt", r"\\server\share\secret.txt"])
def test_absolute_paths_rejected(tmp_path, path):
    with pytest.raises(ValueError):
        safe_path(tmp_path, path)


def test_native_absolute_path_rejected(tmp_path):
    with pytest.raises(ValueError):
        safe_path(tmp_path, str(tmp_path / "sample.txt"))


def test_traversal_rejected(tmp_path):
    with pytest.raises(ValueError):
        safe_path(tmp_path, "../secret.txt")


def test_edit_file(tmp_path):
    tools = RepairTools(tmp_path)
    tools.edit_file("sample.txt", "répaired")
    assert (tmp_path / "sample.txt").read_text(encoding="utf-8") == "répaired"
    assert tools.changed_files == ["sample.txt"]


def test_repeated_edits_recorded_once(tmp_path):
    tools = RepairTools(tmp_path)
    tools.edit_file("sample.txt", "first")
    tools.edit_file("./sample.txt", "second")
    assert tools.changed_files == ["sample.txt"]


def test_run_tests_delegates(tmp_path, monkeypatch):
    expected = TestResult(True, "passed", 0)
    docker_runner = Mock(return_value=expected)
    monkeypatch.setattr(runner, "run_tests", docker_runner)
    host_process = Mock(side_effect=AssertionError("Host execution forbidden"))
    monkeypatch.setattr(subprocess, "run", host_process)
    assert RepairTools(tmp_path).run_tests() is expected
    docker_runner.assert_called_once_with(tmp_path.resolve())
    host_process.assert_not_called()


def test_runner_invokes_only_docker(tmp_path, monkeypatch):
    process = Mock(return_value=subprocess.CompletedProcess([], 1, "failed", "details"))
    monkeypatch.setattr(subprocess, "run", process)
    result = runner.run_tests(tmp_path)
    command = process.call_args.args[0]
    assert command[:3] == ["docker", "run", "--rm"]
    assert command[command.index("--network") + 1] == "none"
    assert command.count("--mount") == 1
    assert command[command.index("--mount") + 1] == (
        f'type=bind,"source={tmp_path.resolve().as_posix()}",target=/workspace,readonly'
    )
    assert command[-6:] == ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    assert result == TestResult(False, "faileddetails", 1)


def test_workspace_created_under_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    workspace = runner.create_workspace("arithmetic")
    assert workspace.parent == tmp_path / ".cache" / "coding-agent-lab"
    source = Path(runner.__file__).resolve().parents[2] / "evals" / "arithmetic"
    for original in source.iterdir():
        if original.is_file():
            assert (workspace / original.name).read_bytes() == original.read_bytes()


@pytest.mark.parametrize("case", ["..", "../arithmetic", "/arithmetic"])
def test_invalid_case_rejected(case):
    with pytest.raises(ValueError):
        runner.create_workspace(case)
