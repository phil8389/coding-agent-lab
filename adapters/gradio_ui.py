"""Present the existing repair service through a local Gradio page."""

import json
from pathlib import Path, PureWindowsPath
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile

import gradio as gr

from adapters.sandbox.repair_tools import safe_path
from bootstrap import build_repair_service


PROJECTS = [
    "arithmetic", "balanced_brackets", "median", "multi_function", "unique_words",
]


def _workspace_path(workspace: Path, relative: str) -> Path:
    """Validate a relative file path before reading workspace content."""
    if not relative or ".." in PureWindowsPath(relative).parts:
        raise ValueError("Invalid relative workspace path")
    return safe_path(workspace, relative)


def _archive_workspace(workspace: Path) -> str:
    """Archive regular workspace files without following symbolic links."""
    files = []
    for path in sorted(workspace.rglob("*")):
        if path.is_symlink() or path.is_junction():
            raise ValueError("Workspace archive cannot contain links")
        relative = path.relative_to(workspace).as_posix()
        target = _workspace_path(workspace, relative)
        if target.is_file():
            files.append((target, relative))
    archive = Path(tempfile.mkdtemp(prefix="repair-download-")) / "repaired-workspace.zip"
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as output:
        for path, relative in files:
            output.write(path, arcname=relative)
    return str(archive)


def _run_repair(project: str) -> tuple[str, str, str, str | None]:
    """Run one supplied case and format its public result and artifacts."""
    try:
        if project not in PROJECTS:
            raise ValueError("Select one of the five supplied projects")
        result = build_repair_service().run(f"evals/{project}")
    except Exception as exc:
        return "", "", f"Repair failed: {exc}", None

    trace = "\n".join(json.dumps(event, ensure_ascii=False) for event in result.trace)
    status = f"Repair {'succeeded' if result.passed else 'failed'}."
    if result.last_test is None:
        status += "\nTests did not complete."
    else:
        test = result.last_test
        status += (f"\nFinal sandboxed tests: {'PASS' if test.passed else 'FAIL'} "
                   f"(exit code {test.returncode})\n{test.output}")

    changed = []
    try:
        workspace = Path(result.workspace).resolve(strict=True)
        evals = (Path(__file__).resolve().parents[1] / "evals").resolve()
        if (not workspace.is_dir() or workspace.is_relative_to(evals)
                or evals.is_relative_to(workspace)):
            raise ValueError("Expected a disposable workspace outside evals")
        for relative in result.changed_files:
            content = _workspace_path(workspace, relative).read_text(encoding="utf-8")
            changed.append(f"=== {relative} ===\n{content}")
        archive = _archive_workspace(workspace)
    except Exception as exc:
        return (trace, "\n\n".join(changed),
                f"UI result preparation failed: {exc}\n{status}", None)
    return trace, "\n\n".join(changed) or "No changed files.", status, archive


def create_demo() -> gr.Blocks:
    """Build the project selector and repair evidence displays."""
    with gr.Blocks(title="Coding Agent Lab") as demo:
        gr.Markdown("# Coding Agent Lab\nRepair a disposable copy of a supplied project.")
        project = gr.Dropdown(choices=PROJECTS, value=PROJECTS[0], label="Project")
        start = gr.Button("Start repair", variant="primary")
        trace = gr.Textbox(label="Public repair trace", lines=12, interactive=False)
        changed = gr.Textbox(label="Changed relative files and contents", lines=12,
                             interactive=False)
        final = gr.Textbox(label="Repair status and final sandboxed test output",
                           lines=8, interactive=False)
        archive = gr.File(label="Repaired workspace ZIP", interactive=False)
        start.click(_run_repair, inputs=project, outputs=[trace, changed, final, archive])
    return demo
