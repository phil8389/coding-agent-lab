"""Chat adapter for the local Ollama HTTP API."""

import json
import math
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OllamaClient:
    """Return model reply text while leaving action validation to the agent."""

    def __init__(self, model: str | None = None, temperature: float = 0.0,
                 timeout: float = 120.0) -> None:
        """Configure the model, sampling temperature, and HTTP timeout."""
        self.model = model if model is not None else os.environ.get(
            "OLLAMA_MODEL", "qwen2.5-coder:7b")
        if not self.model.strip():
            raise ValueError("Ollama model name must not be empty")
        if not math.isfinite(temperature) or temperature < 0:
            raise ValueError("Ollama temperature must be finite and non-negative")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Ollama timeout must be finite and positive")
        self.temperature = temperature
        self.timeout = timeout

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Send a non-streaming JSON-mode chat request to local Ollama."""
        payload = {
            "model": self.model,
            "messages": messages,
            "format": "json",
            "stream": False,
            "options": {"temperature": self.temperature},
        }
        request = Request(
            "http://localhost:11434/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                body = response.read()
        except HTTPError as exc:
            raise RuntimeError(
                f"Ollama HTTP error {exc.code}: {exc.reason}; "
                f"check that model {self.model!r} is installed"
            ) from exc
        except TimeoutError as exc:
            raise TimeoutError(
                f"Ollama request timed out after {self.timeout} seconds"
            ) from exc
        except URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise TimeoutError(
                    f"Ollama request timed out after {self.timeout} seconds"
                ) from exc
            raise ConnectionError(
                f"Cannot connect to local Ollama at localhost:11434: {exc.reason}"
            ) from exc
        except OSError as exc:
            raise ConnectionError(f"Ollama connection failed: {exc}") from exc

        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValueError("Malformed Ollama response: expected a JSON object") from exc
        if not isinstance(data, dict):
            raise ValueError("Malformed Ollama response: expected a JSON object")
        if "error" in data:
            raise RuntimeError(f"Ollama server error: {data['error']}")
        message = data.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise ValueError("Malformed Ollama response: expected message.content text")
        return message["content"]
