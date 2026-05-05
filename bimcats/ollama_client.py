from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


OLLAMA_BASE_URL = "http://127.0.0.1:11434"
EMBEDDING_MODEL = "embeddinggemma"
CHAT_MODEL = "qwen3.6:27b-32k"


class OllamaError(RuntimeError):
    pass


@dataclass(frozen=True)
class OllamaClient:
    base_url: str = OLLAMA_BASE_URL
    timeout: int = 120

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise OllamaError(f"Ollama request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise OllamaError("Ollama returned invalid JSON") from exc

    def _get(self, path: str) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(f"{self.base_url}{path}", timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise OllamaError(f"Ollama is unavailable: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise OllamaError("Ollama returned invalid JSON") from exc

    def is_available(self) -> bool:
        try:
            self._get("/api/tags")
            return True
        except OllamaError:
            return False

    def model_names(self) -> set[str]:
        payload = self._get("/api/tags")
        return {model.get("name", "") for model in payload.get("models", [])}

    def ensure_model(self, model: str) -> None:
        names = self.model_names()
        if model in names or f"{model}:latest" in names:
            return
        self._post("/api/pull", {"name": model, "stream": False})

    def stop_model(self, model: str) -> None:
        try:
            subprocess.run(
                ["ollama", "stop", model],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass

    def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        payload = self._post("/api/embed", {"model": model, "input": texts})
        embeddings = payload.get("embeddings")
        if not isinstance(embeddings, list):
            raise OllamaError("Ollama embedding response did not include embeddings")
        return embeddings

    def chat_json(self, model: str, system: str, user: str) -> dict[str, Any]:
        payload = self._post(
            "/api/chat",
            {
                "model": model,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        content = payload.get("message", {}).get("content", "")
        if not content:
            raise OllamaError("Ollama chat response was empty")
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise OllamaError("Ollama chat response was not valid JSON") from exc
