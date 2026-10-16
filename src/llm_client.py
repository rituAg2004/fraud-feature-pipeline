"""LLM access behind one interface. The rest of the project only calls get_client()."""
import logging
import os
import time

import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class LLMUnavailable(Exception):
    """Raised when the LLM cannot give an answer (disabled, down, bad key, timeout)."""


class LLMClient:
    """Base class: every provider has a name and a generate() method."""

    name = "base"

    def generate(self, prompt: str, timeout: int = 20) -> str:
        """Take a prompt, return the model's text, or raise LLMUnavailable."""
        raise NotImplementedError


class NullClient(LLMClient):
    """Provider 'none': always unavailable, so the template fallback is used."""

    name = "none"

    def generate(self, prompt: str, timeout: int = 20) -> str:
        """Always raise LLMUnavailable, because this provider is switched off."""
        raise LLMUnavailable("LLM disabled")


class GeminiClient(LLMClient):
    """Provider 'gemini': calls Google's generateContent endpoint over HTTP."""

    def __init__(self):
        """Read the API key and model name from environment variables (never from code)."""
        self.api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        self.model = os.environ.get("GEMINI_MODEL", "").strip()
        self.name = self.model or "gemini"

    def generate(self, prompt: str, timeout: int = 20) -> str:
        """Send the prompt, return text. Any problem becomes LLMUnavailable."""
        if not self.api_key or not self.model:
            raise LLMUnavailable("Gemini key or model not set")

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0},
        }

        last_error = "unknown error"
        for attempt in (1, 2):
            try:
                resp = requests.post(url, headers=headers, json=body, timeout=timeout)
                if resp.status_code != 200:
                    last_error = f"HTTP {resp.status_code}"
                else:
                    parts = resp.json()["candidates"][0]["content"]["parts"]
                    text = "".join(p.get("text", "") for p in parts).strip()
                    if text:
                        return text
                    last_error = "empty answer"
            except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
                last_error = type(exc).__name__
            logger.warning("Gemini attempt %d failed: %s", attempt, last_error)
            if attempt == 1:
                time.sleep(1)
        raise LLMUnavailable(f"Gemini failed: {last_error}")


def get_client() -> LLMClient:
    """Read LLM_PROVIDER from the environment and return the matching client."""
    load_dotenv()
    provider = os.environ.get("LLM_PROVIDER", "none").strip().lower()
    if provider == "none":
        return NullClient()
    if provider == "gemini":
        return GeminiClient()
    raise ValueError(f"Unknown LLM_PROVIDER: {provider}")