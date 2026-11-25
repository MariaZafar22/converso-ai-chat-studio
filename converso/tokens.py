"""Token estimation and cost helpers."""

from __future__ import annotations

from typing import Iterable, Mapping

# ~4 characters per token is a widely used rule of thumb for English text.
_CHARS_PER_TOKEN = 4
# Small fixed overhead per chat message (role markers, separators).
_MESSAGE_OVERHEAD = 4


def estimate_tokens(text: str) -> int:
    """Cheap, dependency-free token estimate (never returns less than 1 for text)."""
    if not text:
        return 0
    return max(1, round(len(text) / _CHARS_PER_TOKEN))


def estimate_messages_tokens(messages: Iterable[Mapping[str, str]]) -> int:
    return sum(estimate_tokens(m.get("content", "")) + _MESSAGE_OVERHEAD for m in messages)


def estimate_cost(
    prompt_tokens: int,
    completion_tokens: int,
    pricing: tuple[float, float] | None,
) -> float:
    """Cost in USD given (input_price, output_price) per 1M tokens."""
    if not pricing:
        return 0.0
    in_price, out_price = pricing
    return (prompt_tokens * in_price + completion_tokens * out_price) / 1_000_000
