"""Provider registry and environment-variable based configuration.

API keys are NEVER hard-coded. They are read from environment variables
(``.env`` locally, platform secrets when deployed) or typed into the UI for the
current browser session only.

Prices are APPROXIMATE USD per 1M tokens and are only used for the cost
estimate shown in the UI. Always verify against your provider's pricing page.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Provider:
    key: str
    label: str
    base_url: str
    api_key_env: str
    models: tuple[str, ...]
    # model -> (input_price, output_price) per 1M tokens, approximate
    pricing: dict[str, tuple[float, float]] = field(default_factory=dict)

    @property
    def default_model(self) -> str:
        return self.models[0]


PROVIDERS: dict[str, Provider] = {
    "groq": Provider(
        key="groq",
        label="Groq (free tier available)",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        models=("llama-3.3-70b-versatile", "llama-3.1-8b-instant"),
        pricing={
            "llama-3.3-70b-versatile": (0.59, 0.79),
            "llama-3.1-8b-instant": (0.05, 0.08),
        },
    ),
    "gemini": Provider(
        key="gemini",
        label="Google Gemini (free tier available)",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        api_key_env="GEMINI_API_KEY",
        models=("gemini-2.0-flash", "gemini-1.5-flash"),
        pricing={
            "gemini-2.0-flash": (0.10, 0.40),
            "gemini-1.5-flash": (0.075, 0.30),
        },
    ),
    "openai": Provider(
        key="openai",
        label="OpenAI",
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        models=("gpt-4o-mini", "gpt-4o"),
        pricing={
            "gpt-4o-mini": (0.15, 0.60),
            "gpt-4o": (2.50, 10.00),
        },
    ),
    "openrouter": Provider(
        key="openrouter",
        label="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        models=("meta-llama/llama-3.3-70b-instruct:free", "openai/gpt-4o-mini"),
        pricing={
            "meta-llama/llama-3.3-70b-instruct:free": (0.0, 0.0),
            "openai/gpt-4o-mini": (0.15, 0.60),
        },
    ),
}

DEFAULT_PROVIDER = os.getenv("CONVERSO_PROVIDER", "groq")


def get_provider(key: str) -> Provider:
    try:
        return PROVIDERS[key]
    except KeyError as exc:
        raise ValueError(
            f"Unknown provider '{key}'. Choose one of: {', '.join(PROVIDERS)}"
        ) from exc


def get_api_key(provider: Provider, override: str | None = None) -> str | None:
    """Return the API key: UI override first, then environment variable."""
    if override and override.strip():
        return override.strip()
    value = os.getenv(provider.api_key_env)
    return value.strip() if value else None
