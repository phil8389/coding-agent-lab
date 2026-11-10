"""Exercise the repair loop with scripted replies and in-memory tools."""

import json

import pytest

from adapters.models.scripted import ScriptedClient
from core.models import RepairResult, TestResult
from core.prompts import system_message, user_message
from core.repair_agent import RepairAgent


class FakeTools:
    """Record calls without executing a project or accessing files."""

    def __init__(self, results=()):
        self.results = iter(results)
        self.calls = []

    def read_file(self, path):
        self.calls.append(("read_file", path))
        if path == "missing.py":
            raise FileNotFoundError(path)
        return "source"

    def edit_file(self, path, content):
        self.calls.append(("edit_file", path, content))

    def run_tests(self):
        self.calls.append(("run_tests",))
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        return result


class RecordingClient(ScriptedClient):
    """Capture conversations at each model decision."""

    def __init__(self, replies):
        super().__init__(replies)
        self.histories = []

    def chat(self, messages):
        self.histories.append([dict(message) for message in messages])
        return super().chat(messages)


READ = '{"tool":"read_file","path":"calculator.py","summary":"Read source"}'
TEST = '{"tool":"run_tests"}'
EDIT = '{"tool":"edit_file","path":"calculator.py","content":"fixed"}'
FAIL = TestResult(False, "failure", 1)
PASS = TestResult(True, "passed", 0)


def attempt(tmp_path, replies, results=()):
    tools = FakeTools(results)
    client = RecordingClient(replies)
    result = RepairAgent(client, tools).run("arithmetic", ["calculator.py"], tmp_path)
    assert isinstance(result, RepairResult)
    assert result.trace[0]["event"] == "repair_started"
    assert result.trace[-1]["event"] == "repair_finished"
    return result, tools, client


def test_success(tmp_path):
    result, tools, client = attempt(tmp_path, [READ, TEST, EDIT, TEST], [FAIL, PASS])
    assert result.passed
    assert result.last_test == PASS
    assert result.workspace == tmp_path
    assert result.changed_files == ["calculator.py"]
    assert [call[0] for call in tools.calls] == ["read_file", "run_tests", "edit_file", "run_tests"]
    assert client.histories[0] == [system_message(), user_message("arithmetic", ["calculator.py"])]
    assert client.histories[1][2] == {"role": "assistant", "content": READ}
    assert client.histories[1][3]["role"] == "user"
    assert len(client.histories) == 4
    assert [event["event"] for event in result.trace] == ["repair_started"] + ["model_response", "tool_result"] * 4 + ["repair_finished"]


@pytest.mark.parametrize("reply", [
    "invalid", "```json\n" + READ + "\n```", "Action: " + READ,
    "[]", READ + READ, '{"tool":"run_tests","tool":"read_file"}',
    '{"tool":"shell"}', '{"tool":"read_file"}',
    '{"tool":"run_tests","path":"calculator.py"}',
    '{"tool":"read_file","path":1}', '{"tool":"run_tests","summary":null}',
    '{"tool":[]}', '{"tool":"edit_file","path":"calculator.py"}',
    '{"tool":"edit_file","path":"calculator.py","content":false}',
])
def test_invalid_response(tmp_path, reply):
    result, tools, _ = attempt(tmp_path, [reply])
    assert not result.passed
    assert not tools.calls
    assert "Invalid model response" in result.trace[-1]["reason"]


@pytest.mark.parametrize("replies,results", [
    ([READ, EDIT, TEST, EDIT, TEST], [FAIL, PASS]),
    ([TEST, EDIT, READ, EDIT, TEST], [FAIL, PASS]),
])
def test_early_edit_rejected_and_recoverable(tmp_path, replies, results):
    result, tools, client = attempt(tmp_path, replies, results)
    assert result.passed
    assert sum(call[0] == "edit_file" for call in tools.calls) == 1
    assert any("Policy error" in event.get("error", "") for event in result.trace)
    assert any("Policy error" in message["content"] for message in client.histories[3] if message["role"] == "user")


def test_budget_exhaustion(tmp_path):
    result, tools, client = attempt(tmp_path, [READ] * 9)
    assert not result.passed
    assert len(client.histories) == len(tools.calls) == 8
    assert "budget exhausted" in result.trace[-1]["reason"]


def test_passing_baseline(tmp_path):
    result, tools, _ = attempt(tmp_path, [TEST, EDIT], [PASS])
    assert not result.passed
    assert result.last_test == PASS
    assert tools.calls == [("run_tests",)]
    assert "No reproducible failure" in result.trace[-1]["reason"]


def test_client_exception(tmp_path):
    result, tools, _ = attempt(tmp_path, [])
    assert not result.passed
    assert not tools.calls
    assert "Client error" in result.trace[-1]["reason"]


def test_tool_exception_recovery(tmp_path):
    missing = json.dumps({"tool": "read_file", "path": "missing.py"})
    result, _, client = attempt(tmp_path, [missing, READ, TEST, TEST, EDIT, TEST], [RuntimeError("unavailable"), FAIL, PASS])
    assert result.passed
    assert sum("Tool error" in event.get("error", "") for event in result.trace) == 2
    assert "missing.py" in client.histories[1][-1]["content"]


def test_failed_read_does_not_authorize_edit(tmp_path):
    result, tools, _ = attempt(tmp_path, ['{"tool":"read_file","path":"missing.py"}', TEST, EDIT], [FAIL])
    assert not result.passed
    assert not result.changed_files
    assert all(call[0] != "edit_file" for call in tools.calls)


def test_edit_exception_does_not_count_as_repair(tmp_path):
    class FailedEditTools(FakeTools):
        """Simulate a rejected write."""

        def edit_file(self, path, content):
            raise PermissionError("write rejected")

    tools = FailedEditTools([FAIL, PASS])
    client = RecordingClient([READ, TEST, EDIT, TEST])
    result = RepairAgent(client, tools).run("arithmetic", [], tmp_path)
    assert not result.passed
    assert result.changed_files == []
    assert "write rejected" in client.histories[-1][-1]["content"]


def test_evidence_resets_between_attempts(tmp_path):
    tools = FakeTools([FAIL, PASS])
    agent = RepairAgent(ScriptedClient([READ, TEST, EDIT, TEST]), tools)
    assert agent.run("arithmetic", [], tmp_path).passed
    tools.calls.clear()
    agent.client = ScriptedClient([EDIT])
    result = agent.run("arithmetic", [], tmp_path)
    assert not result.passed
    assert not tools.calls
    assert not result.changed_files
    assert result.last_test is None
