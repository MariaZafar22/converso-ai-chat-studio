"""Converso - Streamlit chat UI.  Run with:  streamlit run app.py"""

from __future__ import annotations

import streamlit as st

from converso.config import DEFAULT_PROVIDER, PROVIDERS, get_api_key
from converso.history import Conversation
from converso.llm import ConversoError, LLMClient
from converso.personas import DEFAULT_PERSONA, PERSONAS

st.set_page_config(page_title="Converso AI Chat Studio", page_icon="💬", layout="wide")

st.markdown(
    """
    <style>
      .block-container {padding-top: 2rem; max-width: 980px;}
      .converso-title {font-size: 2rem; font-weight: 800; margin-bottom: 0;}
      .converso-sub {color: #6b7280; margin-top: 0;}
      .meta {color: #8b8f98; font-size: 0.78rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


# ------------------------------------------------------------------ state
def init_state() -> None:
    if "convo" not in st.session_state:
        st.session_state.convo = Conversation(PERSONAS[DEFAULT_PERSONA])
    st.session_state.setdefault("budget_hit", False)


def secret_key(provider_env: str) -> str | None:
    """Read a key from Streamlit secrets (deployment) without crashing if none exist."""
    try:
        return st.secrets.get(provider_env)
    except Exception:  # noqa: BLE001
        return None


init_state()
convo: Conversation = st.session_state.convo

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("⚙️ Settings")

    provider_keys = list(PROVIDERS)
    provider_key = st.selectbox(
        "Provider",
        provider_keys,
        index=provider_keys.index(DEFAULT_PROVIDER) if DEFAULT_PROVIDER in provider_keys else 0,
        format_func=lambda k: PROVIDERS[k].label,
    )
    provider = PROVIDERS[provider_key]
    model = st.selectbox("Model", provider.models)

    typed_key = st.text_input(
        f"{provider.api_key_env}",
        type="password",
        placeholder="Optional if set in environment / secrets",
        help="Kept only in this browser session. Never stored or logged.",
    )
    api_key = typed_key or secret_key(provider.api_key_env) or get_api_key(provider)

    st.subheader("🎭 Custom instructions")
    persona = st.selectbox("Persona preset", list(PERSONAS), index=list(PERSONAS).index(DEFAULT_PERSONA))
    system_prompt = st.text_area(
        "System prompt",
        value=PERSONAS[persona],
        height=140,
        key=f"system_prompt_{persona}",
        help="Tells the model how to behave. Edit freely or pick 'Custom'.",
    )
    convo.set_system_prompt(system_prompt)

    st.subheader("🎛️ Model parameters")
    temperature = st.slider("Temperature", 0.0, 2.0, 0.7, 0.05, help="Higher = more creative, lower = more focused.")
    top_p = st.slider("Top-p", 0.1, 1.0, 1.0, 0.05)
    max_tokens = st.slider("Max response tokens", 64, 4096, 1024, 64)

    st.subheader("🧠 Memory & cost control")
    max_turns = st.slider("Remember last N messages", 2, 40, 12, 2, help="Older messages are dropped to save tokens.")
    max_ctx = st.number_input("Max context tokens (estimate)", 500, 32000, 6000, 500)
    budget = st.number_input("Session budget (USD, 0 = off)", 0.0, 100.0, 0.0, 0.01, format="%.2f")
    json_mode = st.toggle("Structured JSON replies", help="Model answers as {answer, key_points, confidence}.")

    st.divider()
    c1, c2 = st.columns(2)
    if c1.button("🗑️ Clear", use_container_width=True):
        convo.clear()
        st.session_state.budget_hit = False
        st.rerun()
    if c2.button("↩️ Undo", use_container_width=True, disabled=len(convo) == 0):
        convo.pop_last()
        st.rerun()

    if len(convo):
        st.download_button("⬇️ Export Markdown", convo.to_markdown(), "converso_chat.md", use_container_width=True)
        st.download_button("⬇️ Export JSON", convo.to_json(), "converso_chat.json", use_container_width=True)

# ------------------------------------------------------------------- main
st.markdown('<p class="converso-title">💬 Converso AI Chat Studio</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="converso-sub">Chat with an LLM, shape its behaviour with custom instructions, and watch your token usage.</p>',
    unsafe_allow_html=True,
)

totals = convo.totals()
m1, m2, m3, m4 = st.columns(4)
m1.metric("Replies", int(totals["replies"]))
m2.metric("Prompt tokens", f"{int(totals['prompt_tokens']):,}")
m3.metric("Completion tokens", f"{int(totals['completion_tokens']):,}")
m4.metric("Est. cost", f"${totals['cost_usd']:.5f}")

if not len(convo):
    st.info("👋 Say hello below. Tip: change the persona in the sidebar to see how custom instructions change the answers.")

for turn in convo.turns:
    with st.chat_message(turn.role):
        parsed = turn.meta.get("parsed")
        if parsed:
            st.markdown(f"**{parsed.get('answer', '')}**")
            for point in parsed.get("key_points", []) or []:
                st.markdown(f"- {point}")
            st.caption(f"Confidence: {parsed.get('confidence', 'n/a')}")
        else:
            st.markdown(turn.content)
        if turn.role == "assistant" and turn.meta:
            approx = "~" if turn.meta.get("usage_estimated") else ""
            st.markdown(
                f"<span class='meta'>{turn.meta.get('model', '')} · "
                f"{approx}{turn.meta.get('prompt_tokens', 0)}+{approx}{turn.meta.get('completion_tokens', 0)} tokens · "
                f"{turn.meta.get('latency_s', 0)}s · ${turn.meta.get('cost_usd', 0):.5f}</span>",
                unsafe_allow_html=True,
            )

over_budget = bool(budget) and totals["cost_usd"] >= budget
if over_budget:
    st.warning("Session budget reached. Raise the budget or clear the chat to continue.")

prompt = st.chat_input("Type your message…", disabled=over_budget)

if prompt:
    try:
        convo.add_user(prompt)
    except ValueError:
        st.stop()

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        try:
            client = LLMClient(provider, api_key)
            messages = convo.api_messages(max_turns=max_turns, max_context_tokens=int(max_ctx))
            with st.spinner("Thinking…"):
                result = client.chat(
                    messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=top_p,
                    json_mode=json_mode,
                )
            if not result.content:
                raise ConversoError("The model returned an empty reply. Try rephrasing.")
            meta = result.meta()
            if result.parsed:
                meta["parsed"] = result.parsed
            convo.add_assistant(result.content, **meta)
        except ConversoError as err:
            convo.pop_last()  # keep history valid: remove the unanswered user turn
            st.error(err.user_message)
            st.stop()
    st.rerun()
