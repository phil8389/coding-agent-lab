"""Restricted UTF-8 file operations and Docker test delegation."""

from pathlib import Path, PureWindowsPath

from adapters.sandbox import runner
from core.models import TestResult
from core.ports import RepairToolsPort


def safe_path(workspace: Path, requested_path: str) -> Path:
    """Reject absolute paths and paths resolving outside the workspace."""
    relative = Path(requested_path)
    windows = PureWindowsPath(requested_path)
    if relative.is_absolute() or windows.drive or windows.root:
        raise ValueError("Absolute paths are not permitted")
    root = Path(workspace).resolve()
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Path escapes the workspace")
    return resolved


class RepairTools(RepairToolsPort):
    """Expose only workspace reads, edits, and sandboxed tests."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = Path(workspace).resolve(strict=True)
        self.changed_files: list[str] = []

    def read_file(self, path: str) -> str:
        """Read a workspace file as UTF-8 text."""
        return safe_path(self.workspace, path).read_text(encoding="utf-8")

    def edit_file(self, path: str, content: str) -> None:
        """Save UTF-8 text and record each changed relative path once."""
        target = safe_path(self.workspace, path)
        target.write_text(content, encoding="utf-8")
        relative = target.relative_to(self.workspace).as_posix()
        if relative not in self.changed_files:
            self.changed_files.append(relative)

    def run_tests(self) -> TestResult:
        """Delegate test execution to the Docker runner."""
        return runner.run_tests(self.workspace)
