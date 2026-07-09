# Legal Assist AI

A privacy-preserving legal document analysis platform. Upload a contract, agreement, or case file and get an AI-generated risk assessment, clause-by-clause breakdown, and an interactive chat interface grounded in the document — all personal information is anonymized before it ever reaches an LLM.

![Architecture](docs/architecture.png)

![User Flow](docs/user-flow.png)

---

## Features

- **PII Anonymization** — Presidio-powered regex engine with 16 custom Indian recognizers (Aadhaar, PAN, GSTIN, Voter ID, Passport, IFSC, etc.) — **100% detection rate on Indian document IDs**. Every LLM call sees anonymized text; responses are de-anonymized before reaching the user.
- **AI-Powered Clause Extraction** — Gemini 2.5 Flash extracts 40+ clauses from loan/legal documents, ranked by real-world danger: property seizure > monetary penalties > criminal liability > privacy risks. **F1 = 0.82, 87.5% recall on critical clauses.**
- **Indian Legal Domain Knowledge** — Prompt-engineered for Indian property law: Transfer of Property Act, SARFAESI, NI Act, DPDPA. Document-specific checks for Sale Deed, Lease, Mortgage, POA, Gift Deed, and Loan agreements.
- **Vectorless RAG Chat** — Ask questions about your document. Hybrid BM25 + HTOC (Hierarchical Table of Contents) retrieval achieves **90% hit rate at <5ms latency** with zero embedding cost and no vector database.
- **Multi-Provider HTOC Building** — Gemini by default; docs over 50 pages auto-route to Groq (faster, cheaper for large prompts); Gemini failures retry once before falling back to Groq automatically.
- **Dual OCR Modes** — Fast (Gemini Vision API, 100+ languages) and Secure (EasyOCR, fully local, no data leaves the server, 13+ Indian languages).
- **Image Capture** — No PDF? Take photos of your document (up to 15 pages), compressed client-side, stitched to a PDF server-side, then run through the same OCR pipeline.
- **PDF Reports** — Download or email a styled analysis report.
- **Session-Scoped, Auto-Deleted Storage** — Documents and extracted text are stored only for the session lifetime (2 hours), enforced by a MongoDB TTL index — not a UI promise, the database deletes it.

---

## How It Works

1. **Upload and validate** — The frontend sends a PDF, DOCX, or image-capture job to the backend upload endpoint.
2. **Extract text** — PyMuPDF handles digital PDFs directly; scanned pages or image captures go through OCR (Gemini Vision or local EasyOCR).
3. **Anonymize PII** — Presidio and regex-based recognizers replace sensitive values with tokens before any AI call.
4. **Create session state** — The backend stores anonymized text, page text, and metadata in MongoDB with TTL cleanup.
5. **Build retrieval indexes** — HTOC (hierarchical table of contents) and BM25 artifacts are built in the background so chat and analysis can reuse the document's structure without re-reading the whole thing every time.
6. **Process in background** — OCR, PII, and index-building run through a Celery worker so the API returns immediately while the heavy work continues.
7. **Run analysis and chat** — Gemini is used by default, with Groq/OpenAI/Claude fallbacks where configured; responses are de-anonymized before returning to the UI.
8. **Return reports** — The frontend renders analysis, chat, history, clause views, and PDF/email reports from the stored session data.

For the detailed phase-by-phase walkthrough of each step, see [working.md](working.md).

---

## System Architecture

The system is split into three independently deployable services: a static frontend, a FastAPI backend that serves HTTP traffic, and a Celery worker that does the heavy background processing (OCR, PII, HTOC/BM25 index building). They communicate through Redis (job queue) and MongoDB (shared state).

### Processing Pipeline

```
                    ┌─────────────────────────────┐
                    │      React 19 Frontend       │
                    │  Upload │ Dashboard │ Chat   │
                    └────────────┬────────────────┘
                                 │ HTTPS + JWT
                                 ▼
                    ┌─────────────────────────────┐
                    │      FastAPI Backend        │
                    │  Auth │ CORS │ Rate Limit   │
                    └────────────┬────────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                   ▼
        ┌──────────┐     ┌────────────┐      ┌──────────┐
        │ OCR Engine│     │   Privacy   │      │ Retrieval│
        │          │     │   Layer     │      │  + AI    │
        │ PyMuPDF  │     │             │      │          │
        │ Gemini   │────▶│ PII Anon.  │─────▶│ HTOC Tree│
        │ Vision   │     │ Presidio    │      │ BM25 Idx │
        │ EasyOCR  │     │ + regex     │      │ Chat SSE │
        └──────────┘     └────────────┘      └─────┬────┘
                                                    │
                           ┌────────────────────────┼────────────────────────┐
                           ▼                        ▼                        ▼
                      MongoDB                 Gemini / Groq /              Redis
                    (sessions, TTL)            OpenAI / Claude           (queue/broker)
```

Uploads that need OCR or heavy PII work are queued as Celery tasks: the API writes the raw file to MongoDB, enqueues a job with just the `session_id`, and returns immediately. The worker (a separate process/container) picks the job up, fetches the file by ID, runs OCR → PII → HTOC → BM25, and updates the session — the frontend polls `/htoc-status` until it flips to `ready`.

### Three OCR Modes

| Mode | Engine | API Calls | Privacy | Latency | Languages |
|------|--------|-----------|---------|---------|-----------|
| **Digital** | PyMuPDF | None | Text never leaves server | Instant | N/A |
| **Fast** | Gemini Vision | Yes (batched) | Images sent to Gemini | ~9s/page | 100+ |
| **Secure** | EasyOCR | None | Nothing leaves server | ~3.5s/page | 80+ (13 Indian) |

### Vectorless RAG: How Chat Works

```
User Question
      │
      ▼
┌─ BM25 Search (<5ms) ────────────────────────┐
│  Keyword match against HTOC-boosted index    │
│  90% hit rate, zero API calls                │
└──────────┬───────────────────────────────────┘
           │ Low confidence?
           ▼
┌─ LLM Tree Search (~3-5s) ───────────────────┐
│  Gemini navigates HTOC tree structure        │
│  Selects most relevant sections              │
└──────────┬───────────────────────────────────┘
           │
           ▼
┌─ Gemini Generate ────────────────────────────┐
│  Answer grounded in retrieved sections       │
│  Source citations + page references          │
│  Streamed via SSE to frontend                │
└──────────────────────────────────────────────┘
```

No embeddings, no vector DB — the HTOC tree gives structural navigation, BM25 gives keyword retrieval, and the two combined outperform plain vector search on this benchmark (see [Performance Benchmarks](#performance-benchmarks)).

---

## Tech Stack

### Frontend
| Technology | Purpose |
|---|---|
| React 19 + TypeScript | UI framework |
| Tailwind CSS 4 | Styling (Material Design 3 theme) |
| Radix UI | Accessible component primitives |
| React Router v7 | Client-side routing |
| Axios | API client with JWT auth |
| Framer Motion | Animations |
| React PDF | In-browser document viewer |
| Vite 6 | Build tool |

### Backend
| Technology | Purpose |
|---|---|
| FastAPI | Async API framework |
| Google Gemini 2.5 Flash | Document analysis, chat, OCR |
| Groq / OpenAI / Claude | Optional fallback providers |
| Presidio | PII detection (16 custom Indian patterns) |
| PyMuPDF | PDF text extraction & rendering |
| EasyOCR | Local OCR (13+ Indian languages) |
| MongoDB (Motor) | Async session store with TTL |
| Celery + Redis | Background processing queue |
| BM25 (rank-bm25) | Keyword search with HTOC boost |
| WeasyPrint | PDF report generation |
| SSE-Starlette | Server-sent events for chat streaming |

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- MongoDB (local, or [Atlas free tier](https://www.mongodb.com/cloud/atlas))
- Redis (a free [Upstash](https://upstash.com/) instance is the simplest — no local Redis install needed, and it matches production)
- [Google Gemini API key](https://aistudio.google.com/apikey)

```bash
git clone https://github.com/adityaa2404/legal-assist.git
cd legal-assist
```

### Running Locally (no Docker)

The API and the worker are two separate long-running processes — the API queues jobs, the worker consumes them. Both need to be running for uploads to complete.

**1. Backend environment**

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```

Create `backend/.env`:

```env
MONGODB_URI=mongodb+srv://<user>:<pass>@cluster.mongodb.net/
MONGO_DB_NAME=legal-assist
GEMINI_API_KEY=your-gemini-api-key
GEMINI_HTOC_API_KEY=your-second-key        # optional, for rate limit isolation
GEMINI_CHAT_API_KEY=your-third-key         # optional, for rate limit isolation
GROQ_API_KEY=your-groq-key                 # optional, HTOC fallback + large-doc routing
JWT_SECRET=your-secret-key
SESSION_SECRET=your-session-secret
SESSION_TTL_SECONDS=7200
GEMINI_TIMEOUT=180
MAX_FILE_SIZE_MB=15                        # MongoDB's BSON document cap is 16MB
CORS_ORIGINS=["http://localhost:5173"]
REDIS_URL=rediss://default:<password>@<your-instance>.upstash.io:6379/0
```

`JWT_SECRET` and `SESSION_SECRET` auto-generate if omitted, but every restart then invalidates all issued tokens/sessions — set them explicitly for anything beyond a one-off smoke test.

**2. Start the API** (terminal 1)

```bash
cd backend
venv\Scripts\activate
uvicorn app.main:app --reload --port 8000
```

**3. Start the worker** (terminal 2)

```bash
cd backend
venv\Scripts\activate
python app/worker_entry.py
```

This starts Celery (`--pool=solo` automatically on Windows) plus a heartbeat thread that writes to Redis so the API's `/health` can tell the worker is alive. Watch for `celery@<hostname> ready.` in the log.

Only one worker process can run at a time against a given checkout — `worker_entry.py` holds a PID lock (`app/.worker.lock`) and refuses to start a second instance while one is already running, printing the PID to kill instead. A worker that crashes leaves a stale lock behind; the next one you start detects the dead PID and reclaims it automatically.

**4. Verify**

```bash
curl http://localhost:8000/api/v1/health
# {"status":"ok","api_status":"ok","worker_status":"healthy"}
```

**5. Frontend** (terminal 3)

```bash
cd frontend
npm install
```

Create `frontend/.env`:

```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

```bash
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

### Docker (Alternative)

```bash
docker-compose up --build
```

Starts the full local stack: frontend (port 80), API (port 8000), worker, MongoDB (port 27017), and Redis (port 6379). The `backend` service builds `backend/Dockerfile`; the `worker` service builds `backend/Dockerfile.worker`.

---

## Committing and Pushing

The repo has two branches that matter for deployment:

- **`main`** — the real backend + frontend. Its `backend/Dockerfile` builds the API. This is the only branch pushed to GitHub, and what the API's Hugging Face Space deploys from.
- **`worker`** — a **local-only** branch dedicated to the worker Space; it is never pushed to GitHub. Its `backend/Dockerfile` is a different file (the worker build — installs `requirements-worker.txt`, runs `worker_entry.py` instead of `uvicorn`) and its `backend/README.md` carries the worker Space's title/frontmatter. Everything else in `backend/app/` is identical to `main` — this branch exists purely so each Space's `Dockerfile` can have the same filename (`Dockerfile`, the only name Hugging Face Docker Spaces will build) while pointing at different content.

Hugging Face itself has no concept of "branches" shared with this repo — `la-space` and `la-space-worker` are each an independent git repo with their own single `main`. `git subtree push ... worker:main` just means "push my local `worker` branch's content *as* that remote's `main`" — the name `worker` is local convenience only, not something HF sees or needs.

If the `worker` branch is ever lost (e.g. a fresh clone on a new machine), recreate it once: branch off `main`, swap in the worker `Dockerfile`/`README.md` content, commit. See [Deploying to Hugging Face](#deploying-to-hugging-face-two-spaces) below for what that content should be.

Normal day-to-day workflow — commit on `main`, push to GitHub:

```bash
git add -A
git commit -m "your message"
git push origin main
```

This alone does **not** touch either Hugging Face Space — pushing to GitHub and deploying to Hugging Face are separate steps (below).

---

## Deploying to Hugging Face (two Spaces)

The API and the worker run as **two separate Hugging Face Spaces**, each built from this same repo via `git subtree push` of the `backend/` folder — the API Space from the `main` branch, the worker Space from the `worker` branch.

### One-time setup

1. Create two HF Spaces (Docker SDK): one for the API, one for the worker.
2. Add both as git remotes:
   ```bash
   git remote add hf-space-remote https://huggingface.co/spaces/<user>/<api-space>
   git remote add hf-worker-remote https://huggingface.co/spaces/<user>/<worker-space>
   ```
3. Create the `worker` branch once, with its own `backend/Dockerfile` and `backend/README.md` (see [`worker` branch](#committing-and-pushing) above for what differs). After that, keep it in sync with `main` by merging as needed — everything under `backend/app/` should stay identical between the two branches; only `backend/Dockerfile` and `backend/README.md` are meant to differ permanently.
4. Set environment variables/secrets on **both** Spaces — `MONGODB_URI`, `MONGO_DB_NAME`, `GEMINI_API_KEY` (+ optional `GEMINI_HTOC_API_KEY`, `GEMINI_CHAT_API_KEY`, `GROQ_API_KEY`), `JWT_SECRET`, `SESSION_SECRET`, and `REDIS_URL`. **`REDIS_URL` must be byte-for-byte identical on both Spaces** — it's the shared queue between them.
5. On the **API Space only**, additionally set:
   - `WORKER_URL` — the worker Space's public URL (e.g. `https://<user>-<worker-space>.hf.space`) — see [Worker wake coordination](#worker-wake-coordination) below.
   - `CORS_ORIGINS` — your deployed frontend's origin, JSON array string, e.g. `["https://your-frontend.vercel.app"]`.

### Pushing each Space

```bash
# API Space — push from main
git checkout main
git subtree push --prefix=backend hf-space-remote main

# Worker Space — push from worker
git checkout worker
git merge main                       # bring in any app/ changes made on main
git subtree push --prefix=backend hf-worker-remote worker:main

git checkout main                    # back to the default branch when done
```

`subtree push` requires linear history with the remote; if a push is rejected as non-fast-forward and you're certain the Space's current state isn't something you need, split and force-push instead:

```bash
git subtree split --prefix=backend -b tmp-split
git push hf-worker-remote tmp-split:main --force
git branch -D tmp-split
```

Only push the worker Space when something under `backend/app/worker/`, `backend/app/worker_entry.py`, `backend/requirements-worker.txt`, or a service the worker's task chain reaches (`app/api/v1/documents.py`'s `_process_document_inner` / `_build_htoc_and_bm25` and everything they call) actually changed — most day-to-day API-route changes only need the API Space redeployed.

### Sanity-check after deploying

```bash
curl https://<user>-<api-space>.hf.space/api/v1/health
# worker_status should read "healthy" once both Spaces are awake

curl https://<user>-<worker-space>.hf.space
# "Celery worker is running"
```

### Worker wake coordination

Hugging Face Spaces on free tier sleep when idle, and a request that wakes the **API** Space does not wake the **worker** Space — they're separate containers with separate idle timers, and a Space only wakes on traffic to its own URL.

`GET /api/v1/health` (already polled by the frontend every 15s) fires a background ping at the worker Space's own URL whenever the worker's Redis heartbeat looks stale:

```
Frontend polls /health every 15s
        │
        ▼
API checks worker:heartbeat key in Redis
        │
        ├─ fresh (< 45s old) → status: healthy
        │
        └─ stale/missing → status: starting
                 │
                 ▼
          API fires GET <WORKER_URL> in the background
          (does not block the /health response)
                 │
                 ▼
          Worker Space wakes, starts Celery + heartbeat thread
                 │
                 ▼
          Next /health poll (≤15s later) sees a fresh heartbeat → healthy
```

This needs `WORKER_URL` set on the API Space (see setup above); without it the ping is skipped as a safe no-op. The frontend blocks the whole app behind `worker_status: healthy` — intentional, so uploads don't appear to succeed and then silently never finish while the worker is still asleep.

For near-zero cold starts, add an external uptime monitor (e.g. UptimeRobot free tier) hitting the API's `/api/v1/health` on a few-minute interval — the wake-ping means that alone is enough to keep both Spaces warm.

---

## Performance Benchmarks

### Clause Detection (7-page Loan Application)

| Metric | Score |
|--------|-------|
| Precision | 87.2% |
| Recall | 77.4% |
| F1 Score | **0.820 (Excellent)** |
| Critical Clause Recall | 87.5% |
| Clauses Extracted | 47 / 53 expected |

### Search/Retrieval Strategy Comparison

| Strategy | Hit Rate | Latency | API Calls |
|----------|----------|---------|-----------|
| **BM25+HTOC (production)** | **90%** | **2.3ms** | **0** |
| BM25 plain | 90% | 19.9ms | 0 |
| TF-IDF cosine | 80% | 709ms | 0 |
| Tree DFS | 60% | 0.1ms | 0 |
| Tree BFS | 60% | 0.1ms | 0 |

### PII Detection

| Entity Category | Presidio (spaCy) | Regex Only | Hybrid |
|----------------|-----------------|------------|--------|
| Indian Doc IDs | 57.1% | **100.0%** | **100.0%** |
| Locations | 46.2% | 53.8% | **92.3%** |
| Overall Recall | 44.8% | 51.7% | **75.9%** |
| F1 Score | 0.333 | 0.500 | 0.407 |

### OCR Accuracy (Scanned Legal Document)

| Metric | EasyOCR | Tesseract | Gemini Vision |
|--------|---------|-----------|---------------|
| CER (%) | 32.29 | **13.27** | **13.10** |
| Latency (s/page) | 23.58 | **1.19** | 9.17 |
| Cost (100 pages) | $0.00 | $0.00 | ~$1.20 |
| Local Processing | Yes | Yes | No |

### Storage: Vector RAG vs HTOC

| Metric | Vector RAG | HTOC (Ours) |
|--------|-----------|-------------|
| Storage per document | ~47 KB | **~5 KB** |
| Retrieval latency | ~105ms | **<5ms** |
| Embedding model needed | Yes | **No** |
| Vector DB needed | Yes ($25-70/mo) | **No** |
| GPU/RAM overhead | ~500MB | **~0MB** |
| Works offline | No | **Yes (BM25)** |

### End-to-End Latency (7-page Digital PDF)

| Operation | Latency |
|-----------|---------|
| Upload + PII Anonymization | 6.7s |
| HTOC + BM25 Build | 5.1s |
| Analysis (fresh) | 94.7s |
| Analysis (cached) | 4.1s |
| Chat (avg of 5 questions) | 14.7s |

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `MONGODB_URI` | Yes | — | MongoDB connection string |
| `MONGO_DB_NAME` | No | `legal-assist` | Database name |
| `GEMINI_API_KEY` | Yes | — | Primary Gemini API key (analysis) |
| `GEMINI_HTOC_API_KEY` | No | Falls back to primary | Separate key for HTOC building |
| `GEMINI_CHAT_API_KEY` | No | Falls back to primary | Separate key for chat |
| `GEMINI_TIMEOUT` | No | `90` | Max wait per Gemini call (seconds) |
| `JWT_SECRET` | No | Auto-generated | JWT signing secret (set explicitly for production) |
| `SESSION_TTL_SECONDS` | No | `7200` | Session expiry (seconds) |
| `MAX_FILE_SIZE_MB` | No | `15` | Max upload size. Capped below MongoDB's 16MB BSON document limit — raw file bytes are stored in `document_files` for the worker to fetch |
| `CORS_ORIGINS` | No | `["http://localhost:5173"]` | Allowed frontend origins (JSON array string recommended in env) |
| `REDIS_URL` | Yes | — | Redis broker/backend URL — must match exactly between the API and worker |
| `WORKER_URL` | No (API only) | — | Worker's public URL. When set, `/health` pings it whenever the worker's heartbeat looks stale, waking it alongside the API |
| `SMTP_HOST` | No | — | Email server for report delivery |
| `RATE_LIMIT_RPM` | No | `300` | API rate limit per minute |

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/auth/register` | Create account |
| `POST` | `/api/v1/auth/login` | Login, returns JWT |
| `POST` | `/api/v1/upload` | Upload PDF/DOCX for processing |
| `POST` | `/api/v1/upload/images` | Upload images, stitch to PDF, process |
| `GET` | `/api/v1/htoc-status` | Poll document processing status |
| `GET` | `/api/v1/htoc-tree` | Get document structure tree |
| `POST` | `/api/v1/analyze` | Run AI analysis on document |
| `GET` | `/api/v1/analyze/report` | Download PDF report |
| `POST` | `/api/v1/analyze/email` | Email PDF report |
| `POST` | `/api/v1/chat` | Chat Q&A (non-streaming) |
| `POST` | `/api/v1/chat/stream` | Chat Q&A (SSE streaming) |
| `GET` | `/api/v1/document/pdf` | Download stitched PDF (image captures) |
| `GET` | `/api/v1/history` | User's analysis history |
| `POST` | `/api/v1/history/restore` | Restore past analysis for chat |
| `GET/POST/DELETE` | `/api/v1/clause-library` | Manage saved clauses |
| `POST` | `/api/v1/compare` | Compare two document analyses |
| `GET` | `/api/v1/health` | Health check (also drives the worker wake-ping) |

---

## Project Structure

```
legal-assist/
├── frontend/
│   ├── src/
│   │   ├── api/                   # Axios API clients
│   │   ├── components/
│   │   │   ├── ui/                # Radix UI primitives
│   │   │   ├── UploadView.tsx     # Document upload + live pipeline + cancel
│   │   │   ├── ImageCapturePage.tsx # Photo capture → PDF stitching
│   │   │   ├── AnalysisDashboard.tsx # Risk score, parties, summary
│   │   │   ├── ClauseExplorer.tsx # Risk-ranked clause viewer
│   │   │   ├── ChatInterface.tsx  # Streaming chat with citations
│   │   │   ├── DocumentViewer.tsx # In-browser PDF viewer
│   │   │   └── RiskPage.tsx       # Risk report
│   │   ├── contexts/              # Auth, Session, Theme, Toast
│   │   ├── hooks/                 # useSession, useChat, useServerHealth
│   │   └── types/                 # TypeScript interfaces
│   └── vite.config.ts
├── backend/
│   ├── app/
│   │   ├── api/v1/                # Route handlers
│   │   │   ├── documents.py       # Upload + OCR + PII + image capture
│   │   │   ├── analysis.py        # Gemini analysis + caching
│   │   │   ├── chat.py            # Hybrid RAG chat + streaming
│   │   │   ├── auth.py            # JWT auth + rate limiting
│   │   │   └── health.py          # /health — worker heartbeat check + wake-ping
│   │   ├── core/                  # Config, dependencies, DB, Redis client
│   │   ├── services/
│   │   │   ├── gemini_client.py   # Gemini API (3 clients, retry on 429/503)
│   │   │   ├── pii_anonymizer.py  # 16 Presidio regex patterns, single-pass O(n)
│   │   │   ├── htoc_builder.py    # Hierarchical TOC via Gemini
│   │   │   ├── bm25_search.py     # BM25 + HTOC-boosted retrieval
│   │   │   ├── tree_search.py     # LLM-guided HTOC tree navigation
│   │   │   ├── document_parser.py # PyMuPDF + Gemini Vision + EasyOCR
│   │   │   └── session_service.py # MongoDB sessions + ownership
│   │   ├── worker/
│   │   │   ├── celery_app.py      # Celery app + broker retry/keepalive config
│   │   │   └── tasks.py           # process_document, build_htoc_bm25
│   │   ├── worker_entry.py        # Worker process entrypoint (dummy health server + heartbeat + Celery)
│   │   └── models/                # Pydantic schemas
│   ├── evaluation/                # Benchmark suite
│   │   ├── run_eval.py            # Full pipeline evaluation
│   │   ├── ocr_benchmark.py       # EasyOCR vs Tesseract vs Gemini Vision
│   │   ├── pii_benchmark.py       # Presidio vs Regex vs Hybrid
│   │   ├── clause_benchmark.py    # Clause detection P/R/F1
│   │   ├── search_benchmark.py    # BM25 vs TF-IDF vs Tree DFS/BFS
│   │   └── storage_benchmark.py   # Vector RAG vs HTOC storage
│   ├── Dockerfile                 # main branch: API image. worker branch: worker image (different content, same filename)
│   ├── Dockerfile.worker          # main branch only — used by docker-compose's worker service for local testing
│   ├── README.md                  # main branch: API Space frontmatter. worker branch: worker Space frontmatter
│   ├── requirements.txt           # Full API dependency set
│   └── requirements-worker.txt    # Trimmed worker-only dependency set
├── docs/
│   ├── architecture.puml          # Combined architecture (PlantUML)
│   ├── architecture.png           # Rendered diagram
│   ├── user-flow.puml             # User journey diagram
│   ├── user-flow.png              # Rendered user flow
│   └── project_report.md          # Full research report
├── docker-compose.yml
└── README.md
```

---

## Evaluation Suite

Six benchmark scripts, no external datasets needed:

```bash
cd backend

# Full pipeline (upload → analysis → chat) on test PDFs
python -m evaluation.run_eval --email you@example.com --password pass

# OCR accuracy (EasyOCR vs Tesseract vs Gemini Vision)
python -m evaluation.ocr_benchmark --pdf evaluation/docs/digital.pdf

# PII detection (Presidio spaCy vs Regex vs Hybrid)
python -m evaluation.pii_benchmark --text evaluation/docs/scanned_ground_truth.txt

# Clause detection (F1, precision, recall)
python -m evaluation.clause_benchmark --analysis-json evaluation/docs/analysis_result.json

# Search retrieval (BM25 vs TF-IDF vs Tree DFS/BFS) — no API needed
python -m evaluation.search_benchmark --pdf evaluation/docs/sliceSFBLoanApplicationForm.pdf

# Storage comparison (Vector RAG vs HTOC)
python -m evaluation.storage_benchmark --pdf evaluation/docs/sliceSFBLoanApplicationForm.pdf
```

---

## Privacy & Security

- **Anonymize-first** — PII detected and replaced with tokens (`[PERSON_1]`, `[IN_AADHAAR_1]`) before any text reaches Gemini
- **Anonymized-at-rest** — Extracted text is PII-anonymized before storage; raw file bytes are kept only to support OCR/re-processing and are deleted with the session
- **Session ownership** — Each session tied to user email; cross-user access blocked
- **Auto-expiry** — MongoDB TTL index auto-deletes all session data after 2 hours
- **Error sanitization** — Internal errors logged but never exposed to clients
- **Auth rate limiting** — 15/min on login, 10/min on register (brute-force protection)
- **Streaming safety** — SSE deanonymization buffered to prevent partial PII token leakage
- **Stuck session recovery** — Sessions in "processing" for >30 minutes auto-marked as failed on startup

---

## License

This project is for educational and research purposes.
