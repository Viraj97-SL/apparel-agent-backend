# Pamorya AI Stylist — Multi-Agent RAG Chatbot for E-Commerce

A **production-deployed, multi-agent AI fashion assistant** built for [Pamorya](https://apparel-agent-frontend.vercel.app), a Sri Lankan clothing brand. The system uses **LangGraph** with a supervisor pattern to orchestrate specialised agents for product discovery, order management, restock alerts, and virtual try-on — all through natural conversation.

> **Live Demo:** [apparel-agent-frontend.vercel.app](https://apparel-agent-frontend.vercel.app)

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    FastAPI Server                         │
│              (Rate-limited, file-validated)               │
├───────────────────────┬──────────────────────────────────┤
│    /chat endpoint      │     Upload handling (VTO)        │
└───────────┬───────────┴──────────────┬───────────────────┘
            │                          │
            ▼                          ▼
┌───────────────────┐        ┌─────────────────────┐
│  LangGraph Agent  │        │  VTO Agent           │
│  (Supervisor)     │        │  (Replicate IDM-VTON)│
└────────┬──────────┘        └─────────────────────┘
         │
         ├── Product Search Agent (MCP Tool → PostgreSQL)
         │     ├── Exact match (SQL ILIKE)
         │     ├── Keyword split fallback
         │     └── Fuzzy match (difflib)
         │
         ├── RAG Agent (FAISS + sentence-transformers)
         │     └── Policy/FAQ retrieval from text docs
         │
         ├── Order Management Agent (SQLAlchemy tools)
         │     ├── Draft order creation
         │     └── Order confirmation (COD)
         │
         └── Category Browser Agent (MCP Tool)
               └── In-stock category listing

┌──────────────────────────────────────────────────────────┐
│                   PostgreSQL (Railway)                    │
│  products │ inventory │ orders │ customers │ returns      │
└──────────────────────────────────────────────────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **LLMs** | Google Gemini 2.5 Flash + Groq (Llama 3.1 8B) |
| **Agent Framework** | LangGraph (supervisor + sub-agent pattern) |
| **Tool Protocol** | MCP (Model Context Protocol) via FastMCP |
| **Vector Store** | FAISS with `all-MiniLM-L6-v2` embeddings |
| **API** | FastAPI + Uvicorn |
| **Database** | PostgreSQL on Railway (SQLAlchemy ORM) |
| **Image CDN** | Cloudinary |
| **Virtual Try-On** | Replicate (IDM-VTON model) |
| **Deployment** | Docker → Railway (backend), Vercel (frontend) |
| **Rate Limiting** | slowapi (50 req/min) |

## Key Features

- **Natural language product search** — handles exact matches, keyword splits, and fuzzy matching with fallback chains
- **Real-time inventory** — size-level stock queries with out-of-stock detection
- **Smart categorisation** — auto-detects product categories from names/descriptions
- **Order flow** — draft orders, item addition, customer details, COD confirmation
- **Restock notifications** — email alert registration for out-of-stock items
- **Virtual Try-On** — upload a photo → AI generates you wearing any product (daily limit: 3)
- **Conversation memory** — LangGraph checkpointer preserves context within threads
- **Multi-image support** — products display up to 3 Cloudinary-hosted images

## Project Structure

```
apparel-agent-backend/
├── app/
│   ├── agent.py              # LangGraph supervisor + routing logic
│   ├── chat_with_rag.py      # RAG chain (FAISS retrieval + LLM)
│   ├── data_query_server.py  # MCP server — product/category tools
│   ├── database.py           # SQLAlchemy engine + session factory
│   ├── db_builder.py         # Excel → PostgreSQL data pipeline
│   ├── models.py             # SQLAlchemy ORM models
│   ├── rag_indexer.py        # FAISS index builder
│   ├── sales_tools.py        # Order management tools
│   └── vto_agent.py          # Virtual try-on (Replicate API)
├── tests/
│   ├── test_api.py
│   ├── test_db_builder.py
│   └── test_vto.py
├── scripts/                  # One-off utilities
│   ├── auto_link_images.py
│   └── migrate_images.py
├── data/                     # Source .txt files for RAG
├── chatbot-ui/               # Frontend (HTML/CSS/JS)
├── .github/workflows/ci.yml  # CI pipeline
├── server.py                 # FastAPI entry point
├── Dockerfile
├── requirements.txt
└── .env.example
```

## Getting Started

### Prerequisites
- Python 3.11+
- PostgreSQL (or Railway Postgres)
- API keys: see `.env.example`

### Local Development

```bash
git clone https://github.com/Viraj97-SL/apparel-agent-backend.git
cd apparel-agent-backend

cp .env.example .env
# Fill in your API keys

pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

### Docker

```bash
docker build -t pamorya-agent .
docker run -p 8000:8000 --env-file .env pamorya-agent
```

### Run Tests

```bash
pip install pytest httpx pytest-asyncio
pytest tests/ -v
```

## API

```bash
# Product search
curl -X POST https://your-domain/chat \
  -F "query=Show me blue dresses under 3000 LKR"

# Virtual try-on
curl -X POST https://your-domain/chat \
  -F "query=Try this dress on me" \
  -F "mode=vto" \
  -F "file=@photo.jpg"
```

## Roadmap

- [ ] LLM observability (LangSmith/LangFuse integration)
- [ ] RAG evaluation pipeline (RAGAS metrics)
- [ ] Streaming responses (SSE)
- [ ] Output guardrails (hallucination prevention)
- [ ] pgvector migration (replace FAISS)
- [ ] Authentication layer

---

**Built by [Viraj](https://github.com/Viraj97-SL)**
