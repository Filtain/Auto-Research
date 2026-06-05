from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    attempts: int
    estimated_cost_usd: float


class LLMClient:
    """Small optional LLM client with deterministic fallback."""

    def __init__(self, provider: str | None = None, model: str | None = None, max_retries: int = 2) -> None:
        self.provider = provider or os.getenv("AUTO_RESEARCH_LLM_PROVIDER", "deterministic")
        self.model = model or os.getenv("AUTO_RESEARCH_LLM_MODEL", "none")
        self.max_retries = max_retries

    def complete(self, prompt: str, output_dir: Path | str) -> LLMResult:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        attempts = 0
        last_error = ""
        for attempt in range(1, self.max_retries + 2):
            attempts = attempt
            try:
                if self.provider == "deterministic":
                    text = self.deterministic_response(prompt)
                elif self.provider == "openai":
                    text = self.openai_response(prompt)
                else:
                    raise ValueError(f"Unsupported LLM provider: {self.provider}")
                result = LLMResult(text=text, provider=self.provider, model=self.model, attempts=attempts, estimated_cost_usd=0.0)
                self.log(output_path, prompt, result, "")
                return result
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                time.sleep(0.1)
        result = LLMResult(text="", provider=self.provider, model=self.model, attempts=attempts, estimated_cost_usd=0.0)
        self.log(output_path, prompt, result, last_error)
        return result

    @staticmethod
    def deterministic_response(prompt: str) -> str:
        return "Deterministic LLM fallback. Prompt length: " + str(len(prompt))

    def openai_response(self, prompt: str) -> str:
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        payload = json.dumps(
            {
                "model": self.model or "gpt-4.1-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
        return str(data["choices"][0]["message"]["content"])

    @staticmethod
    def log(output_dir: Path, prompt: str, result: LLMResult, error: str) -> None:
        path = output_dir / "llm_calls.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "provider": result.provider,
                        "model": result.model,
                        "attempts": result.attempts,
                        "prompt_chars": len(prompt),
                        "output_chars": len(result.text),
                        "estimated_cost_usd": result.estimated_cost_usd,
                        "error": error,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
