"""Select supplied evaluations and coordinate disposable repair attempts."""

from collections.abc import Callable
from pathlib import Path, PureWindowsPath

from core.models import RepairResult
from core.repair_agent import RepairAgent


class RepairService:
    """Run an injected agent only against a fresh evaluation copy."""

    PROJECTS = frozenset({
        "arithmetic", "balanced_brackets", "median", "multi_function",
        "unique_words",
    })

    def __init__(
        self,
        create_workspace: Callable[[str], Path],
        create_agent: Callable[[str, Path], RepairAgent],
    ) -> None:
        self.create_workspace = create_workspace
        self.create_agent = create_agent

    def run(self, selected_project: str) -> RepairResult:
        """Validate an evals path, copy it, and return the agent's result."""
        requested = str(selected_project)
        windows = PureWindowsPath(requested)
        parts = requested.replace("\\", "/").split("/")
        if (
            Path(requested).is_absolute() or windows.drive or windows.root
            or ".." in parts
            or len(parts) != 2 or parts[0] != "evals"
            or parts[1] not in self.PROJECTS
        ):
            raise ValueError("Select a supplied project using evals/<project>")
        case = parts[1]
        evals = Path(__file__).resolve().parents[1] / "evals"
        source = evals / case
        if (
            not source.is_dir() or source.is_symlink()
            or not source.resolve().is_relative_to(evals.resolve())
        ):
            raise ValueError("Unknown or unsafe evaluation project")
        workspace = Path(self.create_workspace(case))
        file_paths = sorted(
            path.relative_to(workspace).as_posix()
            for path in workspace.rglob("*") if path.is_file()
        )
        agent = self.create_agent(case, workspace)
        return agent.run(case, file_paths, workspace)
