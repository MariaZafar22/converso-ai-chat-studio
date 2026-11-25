"""Thin, well-behaved wrapper around any OpenAI-compatible chat completions API.

Features: authentication via env vars, tunable parameters, retries with
exponential backoff, friendly error messages, token usage + cost tracking and
a structured (JSON) response mode.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

from .config import Provider, get_api_key
from .tokens import estimate_cost, estimate_messages_tokens, estimate_tokens


# --------------------------------------------------------------------- errors
class ConversoError(Exception):
    """Base error. ``user_message`` is always safe to show in the UI."""

    def __init__(self, user_message: str, *, retryable: bool = False) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.retryable = retryable


class MissingAPIKeyError(ConversoError):
    pass


def translate_error(exc: Exception) -> ConversoError:
    """Map SDK exceptions (matched by class name, so the SDK stays optional) to friendly errors."""
    name = type(exc).__name__
    if name == "AuthenticationError" or name == "PermissionDeniedError":
        return ConversoError("Authentication failed. Check that your API key is correct and active.")
    if name == "RateLimitError":
        return ConversoError(
            "Rate limit or quota reached. Wait a moment, switch model, or check your plan.",
            retryable=True,
        )
    if name in {"APIConnectionError", "APITimeoutError", "Timeout", "ConnectionError"}:
        return ConversoError("Could not reach the provider. Check your internet connection.", retryable=True)
    if name == "NotFoundError":
        return ConversoError("Model or endpoint not found. Pick a different model for this provider.")
    if name == "BadRequestError":
        return ConversoError(f"The provider rejected the request: {_short(exc)}")
    if name == "InternalServerError":
        return ConversoError("The provider had a server error. Please try again.", retryable=True)
    return ConversoError(f"Unexpected error ({name}): {_short(exc)}")


def _short(exc: Exception, limit: int = 220) -> str:
    text = str(exc).replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


# -------------------------------------------------------------------- results
@dataclass
class ChatResult:
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_s: float
    cost_usd: float
    finish_reason: str | None = None
    usage_estimated: bool = False
    parsed: dict[str, Any] | None = None

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def meta(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "latency_s": round(self.latency_s, 2),
            "cost_usd": self.cost_usd,
            "finish_reason": self.finish_reason,
            "usage_estimated": self.usage_estimated,
        }


# ----------------------------------------------------------------- JSON mode
STRUCTURED_INSTRUCTION = (
    "Respond ONLY with a valid JSON object using exactly these keys: "
    '"answer" (string), "key_points" (array of short strings), '
    '"confidence" (one of "low", "medium", "high"). No text outside the JSON.'
)

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def parse_json_response(text: str) -> dict[str, Any] | None:
    """Best-effort extraction of a JSON object from a model reply."""
    if not text:
        return None
    candidates = [text.strip()]
    fenced = _FENCE.search(text)
    if fenced:
        candidates.insert(0, fenced.group(1).strip())
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for cand in candidates:
        try:
            value = json.loads(cand)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(value, dict):
            return value
    return None


# --------------------------------------------------------------------- client
class LLMClient:
    """Chat client for one provider. Inject ``client`` to test without a network."""

    def __init__(
        self,
        provider: Provider,
        api_key: str | None = None,
        *,
        client: Any | None = None,
        max_retries: int = 3,
        timeout: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.provider = provider
        self.max_retries = max_retries
        self._sleep = sleep

        if client is not None:
            self._client = client
            return

        key = get_api_key(provider, api_key)
        if not key:
            raise MissingAPIKeyError(
                f"No API key found. Set {provider.api_key_env} in your environment/.env "
                "or paste a key in the sidebar."
            )
        try:
            from openai import OpenAI  # imported lazily so tests need no SDK
        except ImportError as exc:  # pragma: no cover
            raise ConversoError("The 'openai' package is not installed. Run: pip install -r requirements.txt") from exc
        self._client = OpenAI(api_key=key, base_url=provider.base_url, timeout=timeout, max_retries=0)

    # ------------------------------------------------------------------- chat
    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        top_p: float = 1.0,
        json_mode: bool = False,
    ) -> ChatResult:
        if not messages:
            raise ConversoError("There are no messages to send.")
        model = model or self.provider.default_model

        msgs = [dict(m) for m in messages]
        if json_mode:
            msgs.append({"role": "system", "content": STRUCTURED_INSTRUCTION})

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": msgs,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
        }

        started = time.perf_counter()
        response = self._with_retries(lambda: self._client.chat.completions.create(**kwargs))
        latency = time.perf_counter() - started

        try:
            choice = response.choices[0]
            content = (choice.message.content or "").strip()
            finish = getattr(choice, "finish_reason", None)
        except (AttributeError, IndexError) as exc:
            raise ConversoError("The provider returned an unexpected response format.") from exc

        usage = getattr(response, "usage", None)
        estimated = False
        if usage is not None and getattr(usage, "prompt_tokens", None) is not None:
            prompt_tokens = int(usage.prompt_tokens)
            completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        else:  # some providers omit usage; fall back to an estimate and say so
            prompt_tokens = estimate_messages_tokens(msgs)
            completion_tokens = estimate_tokens(content)
            estimated = True

        cost = estimate_cost(prompt_tokens, completion_tokens, self.provider.pricing.get(model))
        return ChatResult(
            content=content,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_s=latency,
            cost_usd=cost,
            finish_reason=finish,
            usage_estimated=estimated,
            parsed=parse_json_response(content) if json_mode else None,
        )

    # ---------------------------------------------------------------- helpers
    def _with_retries(self, call: Callable[[], Any]) -> Any:
        last: ConversoError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return call()
            except ConversoError:
                raise
            except Exception as exc:  # noqa: BLE001 - translated below
                err = translate_error(exc)
                last = err
                if not err.retryable or attempt == self.max_retries:
                    raise err from exc
                self._sleep(min(2**attempt, 8))  # 1s, 2s, 4s ... capped
        raise last or ConversoError("Request failed.")  # pragma: no cover
