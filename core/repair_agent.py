"""Validate model actions and coordinate a bounded repair attempt."""

import json
from dataclasses import asdict
from pathlib import Path

from core.models import ModelAction, RepairResult
from core.ports import ChatClient, RepairToolsPort
from core.prompts import system_message, tool_result_message, user_message


def _unique_object(pairs: list[tuple]) -> dict:
    """Decode an object without silently accepting duplicate keys."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _parse_action(reply: str) -> ModelAction:
    """Accept exactly one object matching a permitted action schema."""
    data = json.loads(reply, object_pairs_hook=_unique_object)
    if not isinstance(data, dict):
        raise ValueError("Expected one JSON object")
    tool = data.get("tool")
    schemas = {
        "read_file": {"path"},
        "run_tests": set(),
        "edit_file": {"path", "content"},
    }
    if not isinstance(tool, str) or tool not in schemas:
        raise ValueError("Unsupported tool")
    required = schemas[tool] | {"tool"}
    if not required <= data.keys() or data.keys() - (required | {"summary"}):
        raise ValueError("Missing or unexpected action fields")
    if any(not isinstance(value, str) for value in data.values()):
        raise ValueError("Action fields must be strings")
    return ModelAction(tool, {key: data[key] for key in schemas[tool]}, data.get("summary"))


class RepairAgent:
    """Run up to eight model decisions through the restricted tools port."""

    def __init__(self, client: ChatClient, tools: RepairToolsPort) -> None:
        self.client = client
        self.tools = tools

    def run(self, case_name: str, file_paths: list[str], workspace: Path) -> RepairResult:
        """Attempt a repair and return its outcome and public observations."""
        messages = [system_message(), user_message(case_name, file_paths)]
        trace = [{"event": "repair_started", "case_name": case_name}]
        changed_files = []
        last_test = None
        has_read = has_failure = has_edit = False

        def finish(passed: bool, reason: str) -> RepairResult:
            trace.append({"event": "repair_finished", "passed": passed, "reason": reason})
            return RepairResult(passed, trace, changed_files, Path(workspace), last_test)

        for _ in range(8):
            try:
                reply = self.client.chat(messages)
            except Exception as exc:
                return finish(False, f"Client error: {exc}")
            try:
                action = _parse_action(reply)
            except (ValueError, TypeError, RecursionError) as exc:
                trace.append({"event": "model_response", "error": f"Invalid model response: {exc}"})
                return finish(False, f"Invalid model response: {exc}")

            trace.append({"event": "model_response", **asdict(action)})
            messages.append({"role": "assistant", "content": reply})
            observation = {}
            test_completed = False
            if action.tool == "edit_file" and not (has_read and has_failure):
                observation = {"error": "Policy error: edit_file requires a successful read_file and a failing run_tests observation"}
            else:
                try:
                    if action.tool == "read_file":
                        observation = {"content": self.tools.read_file(**action.arguments)}
                        has_read = True
                    elif action.tool == "edit_file":
                        self.tools.edit_file(**action.arguments)
                        has_edit = True
                        path = action.arguments["path"]
                        if path not in changed_files:
                            changed_files.append(path)
                        observation = {"edited": path}
                    else:
                        result = self.tools.run_tests()
                        observation = asdict(result)
                        last_test = result
                        has_failure = has_failure or not result.passed
                        test_completed = True
                except Exception as exc:
                    observation = {"error": f"Tool error: {exc}"}

            trace.append({"event": "tool_result", "tool": action.tool, **observation})
            message = tool_result_message(action.tool, json.dumps(observation))
            messages.append({"role": "user", "content": f"{action.tool}: {message['content']}"})
            if test_completed and last_test.passed:
                if has_edit and has_failure:
                    return finish(True, "Tests passed after repair")
                return finish(False, "No reproducible failure was observed before an edit")

        return finish(False, "Eight-decision budget exhausted")
