"""Create disposable evaluation copies and execute tests only in Docker."""

from pathlib import Path
import shutil
import subprocess
import tempfile

from core.models import TestResult


def create_workspace(case: str) -> Path:
    """Copy one named evaluation case into a fresh directory under home."""
    evals = Path(__file__).resolve().parents[2] / "evals"
    if not case or Path(case).name != case or case in {".", ".."}:
        raise ValueError("Expected an evaluation case name")
    source = evals / case
    if not source.is_dir() or source.is_symlink():
        raise ValueError("Unknown evaluation case")
    if any(path.is_symlink() for path in source.rglob("*")):
        raise ValueError("Evaluation cases must not contain symbolic links")
    cache = Path.home() / ".cache" / "coding-agent-lab"
    cache.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix=f"{case}-", dir=cache))
    try:
        shutil.copytree(source, workspace, dirs_exist_ok=True)
    except Exception:
        shutil.rmtree(workspace)
        raise
    return workspace


def run_tests(workspace: Path, image: str = "coding-agent-lab-runner") -> TestResult:
    """Run pytest in a network-disabled container with one read-only mount."""
    workspace = Path(workspace).resolve(strict=True)
    if not workspace.is_dir():
        raise ValueError("Workspace must be a directory")
    # --mount avoids the drive-letter colon ambiguity of -v on Windows.
    mount = f'type=bind,"source={workspace.as_posix()}",target=/workspace,readonly'
    command = [
        "docker", "run", "--rm", "--network", "none",
        "--mount", mount, "--workdir", "/workspace",
        "--env", "PYTHONDONTWRITEBYTECODE=1", image,
        "python", "-m", "pytest", "-q", "-p", "no:cacheprovider",
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8",
            errors="replace", check=False,
        )
    except OSError as exc:
        return TestResult(passed=False, output=str(exc), returncode=127)
    return TestResult(
        passed=result.returncode == 0,
        output=result.stdout + result.stderr,
        returncode=result.returncode,
    )
