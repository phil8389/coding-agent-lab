"""Message helpers for the model-driven repair workflow."""


def system_message() -> dict[str, str]:
    """Build the repair instructions and allowed action examples."""
    return {
        "role": "system",
        "content": (
            "Repair the selected evaluation case using local source code. "
            "Inspect the relevant local source code and tests. Reproduce a "
            "failing test by running tests before making any edits. Make a "
            "focused edit to repair the observed issue, then verify the repair "
            "by running tests again.\n"
            "Respond with exactly one valid JSON object per reply, without "
            "Markdown or additional prose. Choose one of these allowed actions:\n"
            '{"tool":"read_file","path":"test_calculator.py","summary":"Read the test"}\n'
            '{"tool":"run_tests","summary":"Reproduce the failure"}\n'
            '{"tool":"edit_file","path":"calculator.py","content":"..."}\n'
            "Use relative paths from the supplied file list. The optional "
            "summary is a short public label for the trace, not private reasoning."
        ),
    }


def user_message(case_name: str, file_paths: list[str]) -> dict[str, str]:
    """Build a repair request from a case name and relative file paths."""
    return {
        "role": "user",
        "content": (
            f"Repair evaluation case: {case_name}\n"
            "Available relative file paths:\n"
            + "\n".join(f"- {path}" for path in file_paths)
        ),
    }


def tool_result_message(tool: str, result: str) -> dict[str, str]:
    """Build a message containing a named tool's result."""
    return {"role": "tool", "name": tool, "content": result}
