"""Conversation state: system / user / assistant messages, trimming and export."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .tokens import estimate_messages_tokens, estimate_tokens

VALID_ROLES = {"system", "user", "assistant"}


@dataclass
class Turn:
    role: str
    content: str
    meta: dict[str, Any] = field(default_factory=dict)  # tokens, latency, cost ...
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def __post_init__(self) -> None:
        if self.role not in VALID_ROLES:
            raise ValueError(f"Invalid role '{self.role}'. Expected one of {sorted(VALID_ROLES)}")


class Conversation:
    """Holds the chat history and builds the exact message list sent to the API."""

    def __init__(self, system_prompt: str = "") -> None:
        self.system_prompt = system_prompt.strip()
        self.turns: list[Turn] = []

    # ------------------------------------------------------------------ mutate
    def add_user(self, content: str) -> Turn:
        content = content.strip()
        if not content:
            raise ValueError("Cannot add an empty user message.")
        turn = Turn("user", content)
        self.turns.append(turn)
        return turn

    def add_assistant(self, content: str, **meta: Any) -> Turn:
        turn = Turn("assistant", content, meta=meta)
        self.turns.append(turn)
        return turn

    def pop_last(self) -> Turn | None:
        return self.turns.pop() if self.turns else None

    def clear(self) -> None:
        self.turns.clear()

    def set_system_prompt(self, prompt: str) -> None:
        self.system_prompt = prompt.strip()

    # -------------------------------------------------------------------- read
    def api_messages(
        self,
        max_turns: int | None = None,
        max_context_tokens: int | None = None,
    ) -> list[dict[str, str]]:
        """Return messages for the API, trimming the OLDEST turns first.

        * ``max_turns`` keeps only the last N turns.
        * ``max_context_tokens`` drops old turns until the estimate fits.
        The system prompt and the newest message are always kept.
        """
        turns = self.turns[-max_turns:] if max_turns else list(self.turns)
        body = [{"role": t.role, "content": t.content} for t in turns]
        system: list[dict[str, str]] = (
            [{"role": "system", "content": self.system_prompt}] if self.system_prompt else []
        )

        if max_context_tokens:
            budget = max_context_tokens - estimate_messages_tokens(system)
            while len(body) > 1 and estimate_messages_tokens(body) > budget:
                body.pop(0)
            # never start the history with an assistant reply
            while len(body) > 1 and body[0]["role"] == "assistant":
                body.pop(0)
        return system + body

    def __len__(self) -> int:
        return len(self.turns)

    # ------------------------------------------------------------------ usage
    def totals(self) -> dict[str, float]:
        prompt = sum(t.meta.get("prompt_tokens", 0) for t in self.turns)
        completion = sum(t.meta.get("completion_tokens", 0) for t in self.turns)
        cost = sum(t.meta.get("cost_usd", 0.0) for t in self.turns)
        replies = sum(1 for t in self.turns if t.role == "assistant")
        return {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
            "cost_usd": cost,
            "replies": replies,
        }

    # ----------------------------------------------------------------- export
    def to_json(self) -> str:
        return json.dumps(
            {
                "system_prompt": self.system_prompt,
                "turns": [t.__dict__ for t in self.turns],
            },
            indent=2,
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, raw: str) -> "Conversation":
        data = json.loads(raw)
        convo = cls(data.get("system_prompt", ""))
        for item in data.get("turns", []):
            convo.turns.append(
                Turn(
                    role=item["role"],
                    content=item["content"],
                    meta=item.get("meta", {}),
                    timestamp=item.get("timestamp", ""),
                )
            )
        return convo

    def to_markdown(self) -> str:
        lines = ["# Converso chat export", ""]
        if self.system_prompt:
            lines += ["**System instructions**", "", f"> {self.system_prompt}", ""]
        for t in self.turns:
            who = "You" if t.role == "user" else "Converso"
            lines += [f"**{who}:**", "", t.content, ""]
        t = self.totals()
        lines.append(
            f"---\n*{int(t['total_tokens'])} tokens used, estimated cost ${t['cost_usd']:.5f}*"
        )
        return "\n".join(lines)

    def estimated_context_tokens(self) -> int:
        return estimate_messages_tokens(self.api_messages()) + estimate_tokens("")
