# Pamorya AI Stylist - Multi-Agent RAG Chatbot for E-Commerce

A **production-deployed, multi-agent AI fashion assistant** built for [Pamorya](https://apparel-agent-frontend.vercel.app), a Sri Lankan clothing brand. The system uses **LangGraph v0.3** with a supervisor pattern to orchestrate specialised agents for product discovery, order management, virtual try-on, trend research, and style advice — all through natural conversation.

> **Live Demo:** [apparel-agent-frontend.vercel.app](https://apparel-agent-frontend.vercel.app)

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    FastAPI Server (Railway)                    │
│              (Rate-limited, file-validated)                    │
├───────────────────────┬──────────────────────────────────────┤
│    /chat endpoint      │  /vto/start + /vto/status endpoints  │
└───────────┬───────────┴──────────────┬───────────────────────┘
            │                          │
            ▼                          ▼
┌─────────────────────────────┐  ┌─────────────────────────┐
│  LangGraph v0.3 Agent Graph │  │  VTO Agent (async jobs)  │
│  ┌──────────────────────┐   │  │  Primary:  Fashn.ai      │
│  │  memory_injector     │   │  │  Fallback: Replicate     │
│  │  supervisor (Gemini) │   │  │  Cache:    Redis (30d)   │
│  │  planner             │   │  └─────────────────────────┘
│  │  rag_agent           │   │
│  │  data_query_agent    │   │
│  │  sales_agent         │   │
│  │  web_search_agent    │   │
│  │  style_advisor       │   │
│  │  reflection          │   │
│  │  memory_writer       │   │
│  └──────────────────────┘   │
└─────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                     3-Layer Memory                            │
│  L1: trim_messages (working window, 8k tokens)               │
│  L2: Redis (episodic — session cart, viewed products, 24h)   │
│  L3: MongoDB Atlas (semantic — size prefs, style, history)   │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                  PostgreSQL (Railway)                          │
│  products │ inventory │ orders │ customers │ vto_sessions     │
└──────────────────────────────────────────────────────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **LLMs** | Google Gemini 2.5 Flash (workers) + Gemini 2.5 Pro (supervisor) |
| **Agent Framework** | LangGraph v0.3 — Plan-and-Execute + Reflexion patterns |
| **Tool Protocol** | MCP (Model Context Protocol) via FastMCP |
| **Embeddings** | HuggingFace `all-MiniLM-L6-v2` (local, no API key) |
| **Vector Store** | FAISS (built at container start from `data/` docs) |
| **Web Search** | Tavily (`langchain-tavily`) — results formatted as markdown |
| **API** | FastAPI + Uvicorn |
| **Database** | PostgreSQL on Railway (SQLAlchemy ORM + startup migrations) |
| **Memory L2** | Redis (Railway plugin — episodic session cache) |
| **Memory L3** | MongoDB Atlas M0 free — semantic long-term user facts |
| **Image CDN** | Cloudinary |
| **Virtual Try-On** | Fashn.ai (primary, async + retry) → Replicate IDM-VTON (fallback) |
| **Frontend** | Next.js 15 — 9 sections, Framer Motion, GSAP + ScrollTrigger |
| **Admin Panel** | Refine.dev + Ant Design v5 + Vite (React 18, TypeScript) |
| **Deployment** | Docker → Railway (backend), Vercel (frontend) |
| **Rate Limiting** | slowapi (50 req/min) |
| **Observability** | LangSmith (optional — set `LANGSMITH_API_KEY`) |

## Key Features

### AI Agent
- **Multi-agent supervisor** — 9-node LangGraph graph routes queries to the right specialist: RAG, data query, sales, web search, style advisor, reflection
- **Plan-and-Execute** — complex queries are decomposed into steps before execution
- **Reflexion** — self-critique loop retries low-quality responses before sending to user
- **3-layer memory** — working window + Redis session cache + MongoDB long-term facts
- **Full sales funnel** — draft orders → cart management → COD confirmation with delivery date estimate, order number, and WhatsApp dispatch notification
- **Order tracking** — `get_order_status` tool lets users check any order by number or thread
- **Natural language product search** — exact match → keyword split → fuzzy fallback
- **Real-time inventory** — size-level stock queries with out-of-stock detection
- **Restock notifications** — email alert registration for out-of-stock items
- **Virtual Try-On (async)** — upload photo → Fashn.ai generates try-on → fallback to Replicate; 30-day result cache; retry with exponential backoff on 5xx
- **Trending products** — `/api/trending` endpoint returns live product list with Cloudinary image URLs
- **Web search** — Tavily results formatted as clean markdown (title + content + source)
- **Conversation memory** — LangGraph PostgreSQL checkpointer preserves context across sessions

### Frontend (Next.js 15)
- **9 premium sections** — Hero, Featured Collections, AI Stylist, VTO, Trending, Brand Story, Brand Stats, Partners, Testimonials
- **Embedded chat widget** — button actions wired directly to the LangGraph agent via `lib/chatEvents.js`
- **GSAP + ScrollTrigger** — hero parallax and section reveal animations
- **Framer Motion** — component-level transitions and layout animations
- **Real product images** — FeaturedCollections and TrendingSection pull live data from `/api/trending`
- **Mobile-responsive** — fluid grid layouts with `clamp()`-based spacing and typography

### Admin Panel (Refine.dev)
- **Product management** — create, edit, list products with Cloudinary image upload
- **Order management** — full order list with status tracking
- **Customer management** — customer list and detail view
- **Dashboard** — analytics with Ant Design Plots + Recharts
- **Auth-gated** — key-based auth provider protecting all admin routes

## Project Structure

```
NewChatbot/
├── app/
│   ├── agent.py              # LangGraph supervisor graph + all node logic
│   ├── chat_with_rag.py      # RAG chain (FAISS + HuggingFace embeddings)
│   ├── data_query_server.py  # MCP server — product/category tools
│   ├── database.py           # SQLAlchemy engine (SQLite-safe pool config)
│   ├── db_builder.py         # Excel → PostgreSQL sync + startup migrations
│   ├── models.py             # SQLAlchemy ORM models
│   ├── observability.py      # LangSmith tracing setup
│   ├── rag_indexer.py        # FAISS index builder
│   ├── sales_tools.py        # Order tools (draft, confirm, cart, status)
│   ├── vto_agent.py          # VTO (Fashn.ai + Replicate fallback, async)
│   └── memory/
│       ├── episodic.py       # Layer 2 — Redis session cache
│       └── semantic.py       # Layer 3 — MongoDB Atlas long-term memory
├── tests/
│   ├── conftest.py           # Shared fixtures + app.agent pre-import bootstrap
│   ├── test_routing.py       # Supervisor routing logic (26 tests, all passing)
│   ├── test_vto.py           # VTO pipeline: cache, retry, fallback, job store
│   ├── test_memory.py        # Memory layers: Redis graceful degradation, Mongo
│   ├── test_api.py
│   └── test_db_builder.py
├── chatbot-ui/               # Next.js 15 frontend (Vercel)
│   ├── components/
│   │   ├── sections/
│   │   │   ├── HeroSection.jsx          # GSAP split-text hero + parallax
│   │   │   ├── FeaturedCollections.jsx  # 12 real products + filter tabs
│   │   │   ├── AIStylistSection.jsx     # Chat widget integration
│   │   │   ├── VTOSection.jsx           # Virtual try-on UI
│   │   │   ├── TrendingSection.jsx      # Fetches /api/trending, real images
│   │   │   ├── BrandStorySection.jsx    # Brand pillars + feature tiles
│   │   │   ├── BrandStatsSection.jsx    # Animated KPI counters
│   │   │   ├── PartnersSection.jsx      # Partner logos
│   │   │   └── TestimonialsSection.jsx  # Customer reviews carousel
│   │   └── chat/
│   │       ├── ChatWidget.jsx           # Embedded chat UI
│   │       └── lib/chatEvents.js        # Agent event bus (button → agent)
│   └── ...
├── pamorya-admin/            # Refine.dev admin panel (Vite + TypeScript)
│   └── src/
│       ├── pages/
│       │   ├── dashboard/    # Analytics + KPI charts
│       │   ├── products/     # list, create, edit
│       │   ├── orders/       # Order list + status
│       │   ├── customers/    # Customer list
│       │   └── login.tsx     # Auth-gated entry
│       ├── components/
│       │   └── CloudinaryUpload.tsx  # Unsigned Cloudinary image upload
│       └── providers/
│           ├── authProvider.ts   # Key-based auth
│           └── dataProvider.ts   # FastAPI /admin/* REST adapter
├── data/                     # Source .txt files for RAG index
├── server.py                 # FastAPI entry point + /api/trending + /admin/* endpoints
├── start.sh                  # Container startup: build FAISS if missing, then uvicorn
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

# Build the FAISS index first
python app/rag_indexer.py

uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
cd chatbot-ui
npm install
npm run dev
```

### Admin Panel

```bash
cd pamorya-admin
npm install
# Copy .env.example to .env and fill in your values
cp .env.example .env
npm run dev
```

### Docker

```bash
docker build -t pamorya-agent .
docker run -p 8000:8000 --env-file .env pamorya-agent
# FAISS index is built automatically at container start via start.sh
```

### Run Tests

```bash
pip install -r requirements.txt
pytest tests/test_routing.py tests/test_vto.py tests/test_memory.py -v
# Expected: 26 passed
```

## Environment Variables

### Backend (`.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_API_KEY` | Yes | Gemini 2.5 Flash/Pro |
| `DATABASE_URL` | Yes | Railway PostgreSQL connection string |
| `TAVILY_API_KEY` | Yes | Web search |
| `CLOUDINARY_*` | Yes | Image CDN (3 vars) |
| `REPLICATE_API_TOKEN` | Yes | VTO fallback |
| `FASHN_API_KEY` | Yes | VTO primary |
| `REDIS_URL` | Recommended | Layer 2 episodic memory (Railway Redis plugin) |
| `MONGODB_URI` | Recommended | Layer 3 semantic memory (MongoDB Atlas M0 free) |
| `LANGSMITH_API_KEY` | Optional | LangSmith tracing |
| `HF_TOKEN` | Optional | Faster HuggingFace model downloads |

### Admin Panel (`pamorya-admin/.env`)

| Variable | Description |
|----------|-------------|
| `VITE_API_URL` | Backend URL (e.g. `http://localhost:8000`) |
| `VITE_ADMIN_KEY` | Must match `ADMIN_SECRET_KEY` on the backend |
| `VITE_CLOUDINARY_CLOUD_NAME` | Your Cloudinary cloud name |
| `VITE_CLOUDINARY_UPLOAD_PRESET` | Unsigned upload preset from Cloudinary dashboard |

## API

```bash
# Chat
curl -X POST https://your-domain/chat \
  -F "query=Show me blue dresses under 3000 LKR" \
  -F "thread_id=my-session-123"

# Start VTO job
curl -X POST https://your-domain/vto/start \
  -F "thread_id=my-session-123" \
  -F "product_name=Wild Bloom Whisper" \
  -F "file=@photo.jpg"

# Poll VTO status
curl https://your-domain/vto/status/{job_id}

# Trending products (used by frontend TrendingSection)
curl https://your-domain/api/trending
```

## Changelog

### 2026-05-24 — Admin Panel + Frontend Polish
- **Admin panel**: Full Refine.dev + Ant Design v5 panel at `pamorya-admin/` — product CRUD with Cloudinary upload, order list, customer list, dashboard with charts
- **Chat widget wired to agent**: Button actions in `ChatWidget.jsx` now dispatch events via `lib/chatEvents.js` directly to the LangGraph agent
- **CORS hardened**: Replaced static origin list with a Vercel + localhost regex — no more per-deployment CORS updates
- **Brand Story section**: Updated feature tiles (AI-Powered, Virtual Try-On, WhatsApp Native, Remembers You) with lucide-react icons
- **9 frontend sections live**: Hero, Featured Collections, AI Stylist, VTO, Trending, Brand Story, Brand Stats, Partners, Testimonials

### 2026-05-21 — Deep-Dive Sprint
- **Sales agent overhaul**: delivery date estimation (next N business days skipping weekends), COD receipt with order number, WhatsApp dispatch notification message, `get_order_status` tool
- **All sub-agent prompts rewritten**: handles partial customer info, mind changes, cart queries, price-after-add-to-cart
- **Tavily upgrade**: migrated from deprecated `langchain_community.TavilySearchResults` to `langchain-tavily` package; web search results now formatted as clean markdown
- **VTO hardening**: Fashn.ai retry with exponential backoff on 5xx, Replicate fallback chain, provider tracking, human-readable progress messages, `estimated_seconds_remaining` in status response
- **TrendingSection**: real Cloudinary product images via new `/api/trending` endpoint
- **3-layer memory infrastructure**: semantic memory supports both `MONGODB_URI` and `MONGODB_URL`; episodic memory ready for Railway Redis plugin
- **Database migration**: `_apply_column_migrations()` runs `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` at startup — fixes `order_number` missing column on existing Railway deployments
- **SQLite-safe pool config**: `database.py` excludes `max_overflow`/`pool_use_lifo` for SQLite (enables local testing with `sqlite:///:memory:`)
- **Test suite**: 26 tests passing across `test_routing.py`, `test_vto.py`, `test_memory.py`

---

**Built by [Viraj Bulugahapitiya - AI Engineer](https://github.com/Viraj97-SL)**
