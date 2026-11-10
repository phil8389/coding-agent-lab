"""Deterministic chat client for offline repair-agent checks."""


class ScriptedClient:
    """Return predefined reply strings in their supplied order."""

    def __init__(self, replies: list[str]) -> None:
        """Copy the replies so caller mutations cannot change the script."""
        self._replies = list(replies)
        self._next_reply = 0

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Return the next reply, or raise RuntimeError when exhausted."""
        if self._next_reply >= len(self._replies):
            raise RuntimeError("ScriptedClient has no predefined replies remaining.")
        reply = self._replies[self._next_reply]
        self._next_reply += 1
        return reply
