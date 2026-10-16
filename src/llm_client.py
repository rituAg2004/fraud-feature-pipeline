"""LLM access behind one interface. The rest of the project only calls get_client()."""
import logging
import os

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
        raise LLMUnavailable("LLM disabled")


def get_client() -> LLMClient:
    """Read LLM_PROVIDER from the environment and return the matching client."""
    load_dotenv()
    provider = os.environ.get("LLM_PROVIDER", "none").strip().lower()
    if provider == "none":
        return NullClient()
    raise ValueError(f"Unknown LLM_PROVIDER: {provider}")