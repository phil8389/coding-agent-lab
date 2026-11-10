"""Implementation-independent contracts used by the repair core."""

from typing import Any, Protocol

from core.models import TestResult


class ChatClient(Protocol):
    """Client that returns a text response to chat messages."""

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Return a response for the supplied conversation."""
        ...


class RepairToolsPort(Protocol):
    """File and test operations available in a repair workspace."""

    def read_file(self, path: str) -> str:
        """Read a workspace file as text."""
        ...

    def edit_file(self, path: str, content: str) -> None:
        """Replace a workspace file's text content."""
        ...

    def run_tests(self) -> TestResult:
        """Run workspace tests and return their outcome."""
        ...


class TraceRecorder(Protocol):
    """Recorder for public repair events."""

    def record(self, event: str, payload: dict[str, Any]) -> None:
        """Record a named event and its public payload."""
        ...
