"""Compose the scripted client, safe tools, agent, and repair service."""

import json
from pathlib import Path

from adapters.models.scripted import ScriptedClient
from adapters.sandbox.repair_tools import RepairTools
from adapters.sandbox.runner import create_workspace
from core.repair_agent import RepairAgent
from core.repair_service import RepairService


# Each answer card describes a focused correction to the supplied source.
SCRIPTED_REPAIRS = {
    "arithmetic": (
        "calculator.py", "test_calculator.py",
        "return left - right", "return left + right",
    ),
    "balanced_brackets": (
        "brackets.py", "test_brackets.py",
        "            stack.pop()",
        "            if stack.pop() != pairs[character]:\n                return False",
    ),
    "median": (
        "statistics_tools.py", "test_statistics_tools.py",
        "    return ordered[middle]",
        "    if len(ordered) % 2 == 0:\n"
        "        return (ordered[middle - 1] + ordered[middle]) / 2\n"
        "    return ordered[middle]",
    ),
    "multi_function": (
        "text_tools.py", "test_text_tools.py",
        "normalize_name(name).upper()", "normalize_name(name).title()",
    ),
    "unique_words": (
        "word_tools.py", "test_word_tools.py",
        "sorted(set(text.lower().split()))",
        "list(dict.fromkeys(text.lower().split()))",
    ),
}


def scripted_replies(case: str, workspace: Path) -> list[str]:
    """Build five ordered actions from the selected disposable source."""
    source, tests, before, after = SCRIPTED_REPAIRS[case]
    content = (workspace / source).read_text(encoding="utf-8")
    if content.count(before) != 1:
        raise ValueError(f"Script does not match the supplied {case} fixture")
    actions = [
        {"tool": "read_file", "path": source, "summary": "Inspect source"},
        {"tool": "read_file", "path": tests, "summary": "Inspect expected behavior"},
        {"tool": "run_tests", "summary": "Reproduce the initial failure"},
        {"tool": "edit_file", "path": source,
         "content": content.replace(before, after, 1),
         "summary": "Apply the focused correction"},
        {"tool": "run_tests", "summary": "Verify the repair"},
    ]
    return [json.dumps(action) for action in actions]


def build_repair_service(provider: str = "scripted") -> RepairService:
    """Wire a fresh client and Docker-backed tools for each repair."""
    if provider != "scripted":
        raise ValueError(f"Unsupported provider: {provider}")

    def create_agent(case: str, workspace: Path) -> RepairAgent:
        """Bind this attempt's script and tools to its workspace."""
        tools = RepairTools(workspace)
        client = ScriptedClient(scripted_replies(case, workspace))
        return RepairAgent(client, tools)

    return RepairService(create_workspace, create_agent)
