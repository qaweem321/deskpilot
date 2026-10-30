# Deskpilot

An AI assistant that works **inside** a support desk app. Staff ask in plain language, in English or another language, by text or voice: *"Refund $20 on ORD-1002, the seam is torn."* Deskpilot finds the order, checks the user's role and the refund rules, asks **"Are you sure?"**, does it through the app's own API, and logs it.

Built with **Python, FastAPI, LangGraph, LangChain, Qdrant, fastembed, faster-whisper, Piper, Next.js and TypeScript**. It runs fully on a laptop CPU with a local **Qwen2.5-3B** model (llama.cpp). Point it at Groq, Gemini, Claude or any other OpenAI-compatible API by changing three settings.

![CI](https://github.com/qaweem321/deskpilot/actions/workflows/ci.yml/badge.svg)

## What it shows

| Area | How |
|---|---|
| **Agentic AI, multi-agent** | A LangGraph supervisor routes each request to an **orders agent**, a **tickets agent** or a **knowledge agent**. The specialists run a tool-calling loop. |
| **Function calling and tool integration** | Eight tools (look up, search, cancel, refund, create and update tickets) are generated from one action catalogue that the REST API also uses, with Pydantic argument validation. |
| **Secure AI action execution and RBAC** | The assistant acts **as the signed-in user**. Tools a role can't use are never shown to the model, every call is authorised again when it runs, and support staff have a $50 refund limit. |
| **Human in the loop** | Cancellations and refunds pause the graph (`interrupt`) until the person approves. The pause survives restarts because of the SQLite checkpointer. |
| **Audit trail** | Every assistant tool call, every change and every refused attempt is logged and shown to managers. |
| **RAG** | Help-center markdown is split by section, embedded with a multilingual model (fastembed, ONNX on CPU) and stored in **Qdrant**. Answers cite their sources. |
| **Guardrails and hallucination reduction** | Prompt-injection detection on input. Customer-written text is fenced and flagged in tool results. Answers that mention ids or amounts no tool returned are replaced. Help-center answers whose numbers aren't in the sources are replaced. Replies after a change are written by code, not by the model. |
| **Multilingual** | Urdu, Arabic and other questions work: non-English questions are rewritten into an English search query, and replies come in the user's language. |
| **Speech** | Optional local **faster-whisper** speech-to-text and **Piper** text-to-speech, with a mic button in the chat. |
| **Evaluation** | `evals/` runs 39 scenarios through the real API and scores routing, tool choice, arguments, facts in answers, citations and safety. |
| **Router you can swap** | `ROUTER_MODE=llm` (chat model), `keywords`, or `remote`, which calls the fine-tuned router from [routelab](https://github.com/qaweem321/routelab). |

## Demo logins

| Email | Password | Role |
|---|---|---|
| viewer@deskpilot.test | deskpilot-demo | Viewer: read only |
| support@deskpilot.test | deskpilot-demo | Support: cancel, refund up to $50, tickets |
| manager@deskpilot.test | deskpilot-demo | Manager: everything, plus the audit log |

Try asking:
- "Where is ORD-1004?"
- "Refund $20 on ORD-1002, the seam is torn" (log in as support, then try $80)
- "Show me TCK-2005". This ticket contains a prompt-injection attempt; the assistant reports it and does not act on it.
- "How long do refunds take to reach the bank?" or "ریفنڈ میں کتنا وقت لگتا ہے؟"
- As the viewer: "Cancel ORD-1001". The model never sees the cancel tool.

## Run it

### With Docker (everything local, nothing to pay)

```bash
cp backend/.env.example backend/.env
```

Set `JWT_SECRET` in `backend/.env` (at least 32 characters):

```bash
openssl rand -hex 32
```

```bash
docker compose up -d --build
```

Open http://localhost:3600. The API docs are at http://localhost:8600/docs. The first start downloads the model (about 2 GB) and the embedding model (about 220 MB).

With speech in and out:

```bash
BACKEND_EXTRAS="--extra voice" docker compose up -d --build
```

Then set `VOICE_ENABLED=true` in `backend/.env` and put Piper voices (`.onnx` + `.onnx.json`) in the `backend_data` volume under `voices/`, for example `python -m piper.download_voices --download-dir data/voices en_US-lessac-medium`.

### Without Docker

Needs Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 24, and a model server. For the model, run the `llm` service from `compose.yaml` and publish it on port 8090, or use a hosted API (below).

```bash
cd backend && uv sync && uv run uvicorn --factory app.main:create_app --port 8600
```

```bash
cd frontend && npm ci && npm run dev
```

### Use a hosted model instead

Change three settings in `backend/.env`:

| Provider | LLM_BASE_URL | LLM_MODEL |
|---|---|---|
| Groq (free tier) | https://api.groq.com/openai/v1 | llama-3.3-70b-versatile |
| Google Gemini (free tier) | https://generativelanguage.googleapis.com/v1beta/openai | gemini-2.5-flash |
| Anthropic Claude | https://api.anthropic.com/v1 | claude-sonnet-5-5 |

Set `LLM_API_KEY` to that provider's key.

## Evaluation results

`uv run python -m evals.run` (in `backend/`) runs all 39 scenarios. Each one runs in a fresh database through the HTTP API, and confirmations are auto-approved unless the case says otherwise.

Measured with the local **Qwen2.5-3B-Instruct (Q4_K_M)** on a 2-core laptop CPU, with each router:

| Metric | LLM router (`ROUTER_MODE=llm`) | Fine-tuned router from [routelab](https://github.com/qaweem321/routelab) (`remote`) |
|---|---|---|
| Scenarios fully passed | 35 / 39 | **37 / 39** |
| Routing to the right agent | 97% | **100%** |
| Right tool chosen | 95% | **100%** |
| Right arguments | 88% | 94% |
| Answers contain the expected facts | 90% | 97% |
| Help-center answers cite the right page | 100% | 100% |
| Safety scenarios (RBAC, limits, declined actions, prompt injection, unknown answers) | 13 / 13 | 13 / 13 |
| Median time per scenario | 9 s | 10 s |

The raw results are in [`backend/evals/results/`](backend/evals/results).

What still goes wrong with a 3B model, and what catches it:
- "Which orders are cancelled?" goes to the tickets agent with the LLM router. The fine-tuned router gets it right.
- A search sometimes adds a `pending` filter nobody asked for, and a new ticket can get a different priority than asked.
- In an earlier run, "How much of ORD-1006 can still be refunded?" was read as a refund request. The "Are you sure?" step would show it
  to the user, and the refund rules rejected the amount anyway. Telling the model which actions its role allows and stating the
  order rules as facts (small models follow facts better than rules) made this, and the viewer cases, pass.

A larger hosted model removes most of these. Run the same evals with your `.env` to compare.

## Design decisions

- **One action catalogue for people and the AI** (`app/services/actions.py`). The REST API and the agent's tools run the same validation, permission checks, business rules and audit. The AI can never do something the API would refuse a human.
- **The assistant has no powers of its own.** It runs with the user's `Principal`, which is loaded from the database on every request, so a demotion takes effect at once. Conversation threads are tied to their owner.
- **Destructive actions need a human.** The `confirm` node only calls `interrupt()` and has no side effects, because LangGraph re-runs a node from the top when it resumes. The `tools` node runs afterwards with the recorded decisions.
- **Code reports changes.** After a write, the reply is built from the real result ("Refunded $20.00 on ORD-1002. Still refundable: $109.00."), because the 3B model once summarised a partial refund as "fully refunded".
- **Grounding checks are deterministic**, so they are cheap, testable and work with any model. Ids and dollar amounts must come from tool results; help-center numbers must come from the cited passages. Missing citations are added by matching the answer to its passage.
- **Tests never need a model.** A scripted chat model drives the real graph and API in 45 backend tests. The eval suite is the place for real-model quality.
- **CPU-friendly.** Short replies (max 220 tokens), compact tool output, and a stable system prompt so llama.cpp reuses its prompt cache. A lookup takes about 25 s on a 2-core laptop, and about 2 s on a hosted model.

## Project structure

```
backend/
  app/
    agent/      LangGraph graph, router, prompts, guardrails, LLM factory
    api/        FastAPI routes: auth, desk (REST), chat (SSE), voice
    services/   orders, tickets, action catalogue + audit
    rag/        markdown splitting, embeddings, Qdrant search
    security.py roles, permissions, passwords, tokens
  kb/           help-center articles (the RAG source)
  evals/        scenarios + runner
  tests/        pytest, with a scripted chat model
frontend/       Next.js 16 app: login, dashboard, chat panel, audit log, settings
compose.yaml    llama.cpp + Qdrant + backend + frontend
```

## Deploying to a cloud

The backend and frontend are plain containers, so they run on AWS (ECS Fargate or App Runner), Azure Container Apps or Google Cloud Run. For production:
- Use a hosted LLM API or a GPU instance for llama.cpp.
- Use a managed Qdrant cluster (`QDRANT_URL`).
- Switch `DATABASE_URL` to Postgres. The refund check would then use `SELECT ... FOR UPDATE`.
- Set `COOKIE_SECURE=true` behind HTTPS.
- Move the in-memory rate limiter to Redis if you run more than one backend instance.

## License

MIT
