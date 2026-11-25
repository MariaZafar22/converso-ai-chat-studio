from types import SimpleNamespace

import pytest

from converso.config import PROVIDERS, get_api_key, get_provider
from converso.history import Conversation
from converso.llm import (
    ConversoError,
    LLMClient,
    MissingAPIKeyError,
    parse_json_response,
    translate_error,
)
from converso.tokens import estimate_cost, estimate_tokens


# ------------------------------------------------------------------ fakes
def make_response(text="Hello!", prompt=10, completion=5, usage=True):
    msg = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=msg, finish_reason="stop")
    u = SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion) if usage else None
    return SimpleNamespace(choices=[choice], usage=u)


class FakeClient:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


class RateLimitError(Exception):
    pass


class AuthenticationError(Exception):
    pass


def client_with(outcomes):
    fake = FakeClient(outcomes)
    sleeps = []
    llm = LLMClient(PROVIDERS["groq"], client=fake, sleep=sleeps.append)
    return llm, fake, sleeps


# ----------------------------------------------------------------- tokens
def test_estimate_tokens():
    assert estimate_tokens("") == 0
    assert estimate_tokens("a") == 1
    assert estimate_tokens("x" * 40) == 10


def test_estimate_cost():
    assert estimate_cost(1_000_000, 1_000_000, (1.0, 2.0)) == pytest.approx(3.0)
    assert estimate_cost(100, 100, None) == 0.0


# ----------------------------------------------------------------- config
def test_get_provider_and_key(monkeypatch):
    with pytest.raises(ValueError):
        get_provider("nope")
    p = get_provider("groq")
    monkeypatch.setenv("GROQ_API_KEY", "  env-key ")
    assert get_api_key(p) == "env-key"
    assert get_api_key(p, "ui-key") == "ui-key"
    monkeypatch.delenv("GROQ_API_KEY")
    assert get_api_key(p) is None


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(MissingAPIKeyError):
        LLMClient(PROVIDERS["groq"])


# ---------------------------------------------------------------- history
def test_roles_and_empty_message():
    c = Conversation("be nice")
    with pytest.raises(ValueError):
        c.add_user("   ")
    c.add_user("hi")
    c.add_assistant("hello", prompt_tokens=3, completion_tokens=2, cost_usd=0.001)
    msgs = c.api_messages()
    assert [m["role"] for m in msgs] == ["system", "user", "assistant"]
    assert c.totals()["total_tokens"] == 5


def test_trim_by_turns_keeps_system():
    c = Conversation("sys")
    for i in range(5):
        c.add_user(f"q{i}")
        c.add_assistant(f"a{i}")
    msgs = c.api_messages(max_turns=4)
    assert msgs[0]["role"] == "system"
    assert len(msgs) == 5
    assert msgs[1]["content"] == "q3"


def test_trim_by_tokens_keeps_newest_and_starts_with_user():
    c = Conversation("sys")
    for i in range(6):
        c.add_user("word " * 100)
        c.add_assistant("reply " * 100)
    c.add_user("latest question")
    msgs = c.api_messages(max_context_tokens=400)
    assert msgs[-1]["content"] == "latest question"
    assert msgs[1]["role"] == "user"
    assert len(msgs) < 14


def test_export_roundtrip():
    c = Conversation("sys")
    c.add_user("hi")
    c.add_assistant("yo", prompt_tokens=1, completion_tokens=1, cost_usd=0.0)
    again = Conversation.from_json(c.to_json())
    assert again.system_prompt == "sys"
    assert [t.content for t in again.turns] == ["hi", "yo"]
    assert "**You:**" in c.to_markdown()


# -------------------------------------------------------------------- llm
def test_chat_success_and_params():
    llm, fake, _ = client_with([make_response("Hi there", 20, 8)])
    res = llm.chat([{"role": "user", "content": "hey"}], temperature=0.2, max_tokens=50, top_p=0.9)
    assert res.content == "Hi there"
    assert res.total_tokens == 28
    assert res.cost_usd > 0
    call = fake.calls[0]
    assert call["temperature"] == 0.2 and call["max_tokens"] == 50 and call["top_p"] == 0.9


def test_usage_fallback_estimated():
    llm, _, _ = client_with([make_response("abcd" * 10, usage=False)])
    res = llm.chat([{"role": "user", "content": "hey"}])
    assert res.usage_estimated and res.completion_tokens == 10


def test_retry_then_success():
    llm, fake, sleeps = client_with([RateLimitError("429"), RateLimitError("429"), make_response()])
    res = llm.chat([{"role": "user", "content": "x"}])
    assert res.content == "Hello!"
    assert len(fake.calls) == 3
    assert sleeps == [1, 2]


def test_retries_exhausted():
    llm, fake, _ = client_with([RateLimitError("429")] * 4)
    with pytest.raises(ConversoError) as ei:
        llm.chat([{"role": "user", "content": "x"}])
    assert "Rate limit" in ei.value.user_message
    assert len(fake.calls) == 4


def test_auth_error_not_retried():
    llm, fake, sleeps = client_with([AuthenticationError("bad key")])
    with pytest.raises(ConversoError) as ei:
        llm.chat([{"role": "user", "content": "x"}])
    assert "Authentication" in ei.value.user_message
    assert len(fake.calls) == 1 and sleeps == []


def test_unknown_error_translation():
    assert "Unexpected" in translate_error(RuntimeError("boom")).user_message


def test_empty_messages_rejected():
    llm, _, _ = client_with([])
    with pytest.raises(ConversoError):
        llm.chat([])


# --------------------------------------------------------------- json mode
def test_parse_json_variants():
    assert parse_json_response('{"a": 1}') == {"a": 1}
    assert parse_json_response('Sure!\n```json\n{"a": 2}\n```') == {"a": 2}
    assert parse_json_response('text before {"a": 3} text after') == {"a": 3}
    assert parse_json_response("not json") is None
    assert parse_json_response("[1,2]") is None


def test_json_mode_adds_instruction_and_parses():
    reply = '{"answer": "42", "key_points": ["x"], "confidence": "high"}'
    llm, fake, _ = client_with([make_response(reply)])
    res = llm.chat([{"role": "user", "content": "meaning of life"}], json_mode=True)
    assert res.parsed["answer"] == "42"
    assert fake.calls[0]["messages"][-1]["role"] == "system"
