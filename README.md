# 💬 Converso AI Chat Studio

**A clean, configurable AI chat application built with Python, Streamlit and any OpenAI-compatible LLM API.**

**Converso** lets you talk to a large language model, shape its behaviour with **custom instructions**, tune **model parameters**, and keep a close eye on **token usage and cost**, all from a simple web interface.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-ff4b4b)
![Tests](https://img.shields.io/badge/tests-17%20passing-brightgreen)
![License](https://img.shields.io/badge/license-MIT-green)

---

## 📌 Table of Contents

1. [Features](#-features)
2. [How It Works](#-how-it-works)
3. [Project Structure](#-project-structure)
4. [Quick Start](#-quick-start)
5. [Configuration](#-configuration)
6. [Using the App](#-using-the-app)
7. [Supported Providers](#-supported-providers)
8. [Error Handling](#-error-handling)
9. [Token Usage and Cost Management](#-token-usage-and-cost-management)
10. [Running the Tests](#-running-the-tests)
11. [Deployment](#-deployment)
12. [Security](#-security)
13. [Roadmap](#-roadmap)
14. [License](#-license)

---

## ✨ Features

| Area | What you get |
|------|--------------|
| **LLM connection** | Connects to **Groq, Google Gemini, OpenAI and OpenRouter** through one OpenAI-compatible client |
| **Authentication** | API keys loaded from **environment variables**, Streamlit secrets or typed into the sidebar (session only) |
| **Conversation management** | Full **system / user / assistant** message handling with a persistent chat history |
| **Custom instructions** | Editable **system prompt** plus ready-made personas (Python Mentor, Career Coach, Summarizer and more) |
| **Model parameters** | Live control of **temperature, top-p and max tokens** |
| **Token optimisation** | **Sliding-window memory** and a **context token limit** that drop the oldest messages first |
| **Structured responses** | Optional **JSON mode** returning `answer`, `key_points` and `confidence` |
| **Robust error handling** | Friendly messages and **automatic retries with exponential backoff** |
| **Cost management** | Per-reply and per-session **token and cost tracking** with an optional **budget cap** |
| **Export** | Download any chat as **Markdown** or **JSON** |
| **Quality** | **17 automated tests** that run without a network connection or API key |

---

## 🧠 How It Works

```
 ┌──────────────┐   messages    ┌───────────────┐   HTTPS    ┌──────────────┐
 │ Streamlit UI │ ────────────► │  LLMClient    │ ─────────► │  LLM API     │
 │   (app.py)   │ ◄──────────── │  (llm.py)     │ ◄───────── │ (Groq/Gemini │
 └──────┬───────┘   ChatResult  └───────┬───────┘   response │  /OpenAI...) │
        │                               │                    └──────────────┘
        ▼                               ▼
 ┌──────────────┐               retries · error mapping
 │ Conversation │               token + cost accounting
 │ (history.py) │               JSON-mode parsing
 └──────────────┘
```

1. You type a message, and it is added to the **Conversation**.
2. The conversation builds the exact message list: **system prompt + trimmed history**.
3. **LLMClient** sends it with your chosen parameters, retrying on temporary failures.
4. The reply comes back as a **ChatResult** with content, token usage, latency and cost.
5. Everything is stored in the history and shown in the interface.

---

## 🗂️ Project Structure

```
converso-ai-chat-studio/
├── app.py                  # Streamlit user interface
├── converso/
│   ├── config.py           # Providers, models, pricing, env-var keys
│   ├── llm.py              # API client, retries, errors, JSON mode
│   ├── history.py          # Conversation state, trimming, export
│   ├── tokens.py           # Token estimation and cost helpers
│   └── personas.py         # Ready-made custom instructions
├── tests/
│   └── test_core.py        # Offline unit tests (17)
├── .streamlit/config.toml  # Theme
├── .env.example            # Template for your keys
├── requirements.txt
├── DEPLOYMENT.md
└── LICENSE
```

---

## 🚀 Quick Start

**1. Clone the repository**

```bash
git clone https://github.com/<your-username>/converso-ai-chat-studio.git
cd converso-ai-chat-studio
```

**2. Create a virtual environment and install dependencies**

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**3. Add your API key**

```bash
cp .env.example .env
```

Open `.env` and paste your key, for example `GROQ_API_KEY=...`.
You can get a **free** key from [Groq](https://console.groq.com/keys) or [Google AI Studio](https://aistudio.google.com/app/apikey).

**4. Run the app**

```bash
streamlit run app.py
```

The app opens at **http://localhost:8501**.

---

## 🔧 Configuration

| Variable | Purpose |
|----------|---------|
| `CONVERSO_PROVIDER` | Default provider: `groq`, `gemini`, `openai` or `openrouter` |
| `GROQ_API_KEY` | Key for Groq |
| `GEMINI_API_KEY` | Key for Google Gemini |
| `OPENAI_API_KEY` | Key for OpenAI |
| `OPENROUTER_API_KEY` | Key for OpenRouter |

You only need the key for the provider you actually use.

---

## 🖥️ Using the App

- **Provider and Model**: choose where your requests go.
- **Persona preset**: instantly switch the assistant's personality.
- **System prompt**: write your own **custom instructions** (for example, *"Answer in simple English and always give one example"*).
- **Temperature**: low values give focused answers, high values give creative ones.
- **Top-p**: limits the range of words the model samples from.
- **Max response tokens**: caps the length (and cost) of each reply.
- **Remember last N messages**: controls how much history is sent each time.
- **Structured JSON replies**: ask for machine-readable answers.
- **Clear / Undo / Export**: manage and save your conversation.

---

## 🌐 Supported Providers

| Provider | Default model | Free tier |
|----------|---------------|-----------|
| **Groq** | `llama-3.3-70b-versatile` | Yes |
| **Google Gemini** | `gemini-2.0-flash` | Yes |
| **OpenAI** | `gpt-4o-mini` | No |
| **OpenRouter** | `meta-llama/llama-3.3-70b-instruct:free` | Yes (free models) |

Model names and availability change over time. If a model is retired, edit the list in `converso/config.py`.

---

## 🛡️ Error Handling

Every failure is converted into a clear message instead of a crash:

| Situation | Behaviour |
|-----------|-----------|
| Missing API key | Explains which variable to set |
| Invalid key | **Authentication** message, no retry |
| Rate limit or quota | Retries up to **3 times** with exponential backoff (1s, 2s, 4s), then reports |
| Network problems or timeout | Retries, then shows a connection message |
| Unknown model | Suggests choosing another model |
| Empty or malformed reply | Detected and reported |
| Provider omits usage data | Falls back to an **estimate**, shown with a `~` mark |

---

## 💰 Token Usage and Cost Management

- Exact **prompt and completion tokens** are read from the API response for every reply.
- Cost is calculated from the **approximate** per-million-token prices in `config.py`. Treat it as an **estimate** and verify against your provider's pricing page.
- Set a **session budget** in the sidebar and Converso stops accepting messages once it is reached.
- Reduce spend by lowering **max tokens**, shrinking the **memory window** or choosing a smaller model.

---

## 🧪 Running the Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

The tests use a **fake API client**, so they need **no internet and no API key**. They cover history trimming, retries, error mapping, JSON parsing, token maths and chat export.

---

## ☁️ Deployment

See **[DEPLOYMENT.md](DEPLOYMENT.md)** for step-by-step instructions to publish the app for free on **Streamlit Community Cloud** (or Hugging Face Spaces).

---

## 🔒 Security

- API keys are **never hard-coded** and `.env` is excluded through `.gitignore`.
- Keys typed in the sidebar live only in your **browser session**.
- Never commit real keys. If one leaks, **revoke it immediately** in the provider dashboard.

---

## 🗺️ Roadmap

- [ ] Streaming responses
- [ ] Saved conversations across sessions
- [ ] File upload and document Q&A
- [ ] Exact token counting with `tiktoken`

---

## 📄 License

Released under the **MIT License**. See [LICENSE](LICENSE) for details.

---


