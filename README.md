# Legal Assist AI

A privacy-preserving full-stack platform for automated legal document analysis. Upload contracts, agreements, or case files and get instant risk assessment, clause extraction, and interactive Q&A — all without storing raw documents.

![Architecture](docs/Legal%20Assist%20-%20Backend%20Architecture%20(Compact).png)

---

## Features

- **Zero-Retention Processing** — Documents are processed in-memory. Raw text is never persisted; only PII-anonymized content is stored temporarily.
- **PII Anonymization** — Presidio-powered regex engine detects 25+ Indian & international PII types (Aadhaar, PAN, GSTIN, emails, phone numbers, etc.) before any AI processing.
- **AI-Powered Analysis** — Google Gemini extracts key clauses, identifies risks, obligations, missing clauses, and generates an overall risk score (0-100).
- **Hybrid RAG Chat** — Ask questions about your document. Combines BM25 keyword search + HTOC (Hierarchical Table of Contents) semantic navigation for grounded answers with source citations.
- **OCR Support** — Scanned PDFs are processed via Gemini Vision API for text extraction. Supports 13 Indian languages.
- **PDF Reports** — Download or email full/summary analysis reports as styled PDFs.
- **Real-Time Processing Pipeline** — Live per-stage timers show progress: text extraction, PII anonymization, and AI analysis.

---

## Tech Stack

### Frontend
| Technology | Purpose |
|---|---|
| React 19 + TypeScript | UI framework |
| Tailwind CSS 4 | Styling (Material Design 3 light/dark theme) |
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
| Google Gemini API | Document analysis, chat, OCR |
| Presidio | PII detection (pattern-based, no spaCy model) |
| PyMuPDF | PDF text extraction & rendering |
| MongoDB (Motor) | Async document store for sessions |
| BM25 (rank-bm25) | Keyword search index |
| WeasyPrint | PDF report generation |
| SSE-Starlette | Server-sent events for chat streaming |

---

## Architecture

```
Client (React SPA)
       |
       | HTTPS + JWT
       v
┌──────────────────────────────────────┐
│         FastAPI Gateway              │
│    CORS · Rate Limiting · JWT Auth   │
├──────┬───────┬───────┬───────┬──────┤
│ Auth │Upload │Analyze│ Chat  │Report│
└──┬───┴───┬───┴───┬───┴───┬───┴──┬───┘
   │       │       │       │      │
   v       v       v       v      v
┌──────────────────────────────────────┐
│          Service Layer               │
│  DocumentParser · PIIAnonymizer      │
│  GeminiClient · HTOCBuilder          │
│  BM25Search · SessionService         │
└──────────┬───────────────────────────┘
           │
    ┌──────┼──────┐
    v      v      v
 MongoDB  Gemini  Gemini
 Atlas    API     Vision
```

### Document Processing Flow

```
Upload → PyMuPDF Extract → PII Anonymize → MongoDB (anonymized only)
                                              │
                              ┌────────────────┼────────────────┐
                              v                v                v
                         HTOC Tree        BM25 Index      AI Analysis
                        (background)     (background)     (Gemini API)
                              │                │                │
                              └────────────────┴────────────────┘
                                               │
                                          Chat (Hybrid RAG)
                                     BM25 + HTOC → Gemini → SSE Stream
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- MongoDB (local or [Atlas free tier](https://www.mongodb.com/cloud/atlas))
- [Google Gemini API key](https://aistudio.google.com/apikey)

### 1. Clone

```bash
git clone https://github.com/adityaa2404/legal-assist.git
cd legal-assist
```

### 2. Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create `backend/.env`:

```env
MONGODB_URI=mongodb+srv://<user>:<pass>@cluster.mongodb.net/
MONGO_DB_NAME=legal-assist
GEMINI_API_KEY=your-gemini-api-key
GEMINI_HTOC_API_KEY=your-second-key        # optional, for rate limit isolation
GEMINI_CHAT_API_KEY=your-third-key         # optional, for rate limit isolation
JWT_SECRET=your-secret-key
SESSION_TTL_SECONDS=7200
CORS_ORIGINS=["http://localhost:5173"]
```

Start the backend:

```bash
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend Setup

```bash
cd frontend
npm install
```

Create `frontend/.env`:

```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

Start the frontend:

```bash
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

### 4. Docker (Alternative)

```bash
docker-compose up --build
```

This starts frontend (port 80), backend (port 8000), and MongoDB (port 27017).

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `MONGODB_URI` | Yes | — | MongoDB connection string |
| `MONGO_DB_NAME` | No | `legal-assist` | Database name |
| `GEMINI_API_KEY` | Yes | — | Primary Gemini API key (analysis) |
| `GEMINI_HTOC_API_KEY` | No | Falls back to primary | Separate key for HTOC building |
| `GEMINI_CHAT_API_KEY` | No | Falls back to primary | Separate key for chat |
| `JWT_SECRET` | No | Auto-generated | JWT signing secret |
| `SESSION_TTL_SECONDS` | No | `7200` | Session expiry (seconds) |
| `MAX_FILE_SIZE_MB` | No | `50` | Max upload size |
| `CORS_ORIGINS` | No | `["http://localhost:5173"]` | Allowed frontend origins |
| `SMTP_HOST` | No | — | Email server for report delivery |
| `SMTP_PORT` | No | `587` | SMTP port |
| `SMTP_USER` | No | — | SMTP username |
| `SMTP_PASSWORD` | No | — | SMTP password |
| `RATE_LIMIT_RPM` | No | `300` | API rate limit per minute |

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/auth/signup` | Create account |
| `POST` | `/api/v1/auth/login` | Login, returns JWT |
| `POST` | `/api/v1/upload` | Upload PDF/DOCX for processing |
| `GET` | `/api/v1/htoc-status` | Poll document processing status |
| `GET` | `/api/v1/htoc-tree` | Get document structure tree |
| `POST` | `/api/v1/analyze` | Run AI analysis on document |
| `GET` | `/api/v1/analyze/report` | Download PDF report |
| `POST` | `/api/v1/analyze/email` | Email PDF report |
| `POST` | `/api/v1/chat` | Chat Q&A (non-streaming) |
| `POST` | `/api/v1/chat/stream` | Chat Q&A (SSE streaming) |
| `GET` | `/api/v1/history` | User's analysis history |
| `GET` | `/api/v1/clause-library` | Reference clause library |
| `POST` | `/api/v1/comparison` | Compare two documents |
| `GET` | `/api/v1/health` | Health check |

Full interactive docs available at `/docs` (Swagger UI) when running the backend.

---

## Project Structure

```
legal-assist/
├── frontend/
│   ├── src/
│   │   ├── api/              # Axios API clients
│   │   ├── components/       # React components
│   │   │   ├── ui/           # Radix UI primitives
│   │   │   ├── UploadView    # Document upload + live pipeline
│   │   │   ├── AnalysisDashboard  # Risk score, summary, stats
│   │   │   ├── ChatInterface # Streaming chat with citations
│   │   │   ├── ClausesExplorer    # Clause search & filtering
│   │   │   └── RiskPage      # Risk report with recommendations
│   │   ├── contexts/         # Auth, Session, Theme, Toast providers
│   │   ├── hooks/            # useAuth, useSession, useChat, useTheme
│   │   ├── lib/              # Utilities (cn helper)
│   │   └── types/            # TypeScript interfaces
│   └── vite.config.ts
├── backend/
│   ├── app/
│   │   ├── api/v1/           # Route handlers
│   │   │   ├── documents.py  # Upload + OCR + PII pipeline
│   │   │   ├── analysis.py   # Gemini analysis + caching
│   │   │   ├── chat.py       # Hybrid RAG chat + streaming
│   │   │   └── auth.py       # JWT authentication
│   │   ├── core/             # Config, dependencies, DB
│   │   ├── services/         # Business logic
│   │   │   ├── gemini_client.py    # Gemini API wrapper
│   │   │   ├── pii_anonymizer.py   # Presidio pattern-based PII
│   │   │   ├── htoc_builder.py     # Hierarchical TOC builder
│   │   │   ├── bm25_search.py      # BM25 keyword index
│   │   │   ├── document_parser.py  # PyMuPDF + Gemini Vision OCR
│   │   │   └── session_service.py  # MongoDB session management
│   │   └── models/           # Pydantic schemas
│   └── requirements.txt
├── docs/                     # Architecture diagrams (PlantUML + PNG/SVG)
├── docker-compose.yml
└── README.md
```

---

## Deployment

### Render (Backend) + Vercel (Frontend)

**Backend on Render:**
1. Create a **Web Service**, set root directory to `backend`
2. Build command: `pip install -r requirements.txt`
3. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables in Render dashboard
5. Set up [UptimeRobot](https://uptimerobot.com) to ping `/api/v1/health` every 5 min (prevents free tier sleep)

**Frontend on Vercel:**
1. Import repo, set root directory to `frontend`
2. Add env: `VITE_API_BASE_URL=https://your-backend.onrender.com/api/v1`
3. Deploy

### Docker

```bash
docker-compose up --build -d
```

---

## Evaluation

The project includes an evaluation suite for measuring system performance:

```bash
cd backend
python -m evaluation.measure_all --all --token YOUR_JWT_TOKEN
```

| Metric | What it measures |
|---|---|
| OCR Accuracy | CER & WER against ground truth transcriptions |
| Clause Detection | Precision, Recall, F1 against expert annotations |
| RAG Quality | BERTScore + retrieval hit rate for chat answers |
| Latency | Upload, analysis, and chat response times |

See `evaluation/measure_all.py` for setup instructions and ground truth format.

---

## Privacy & Security

- **Anonymize-first architecture** — PII is detected and replaced with tokens before any text reaches the AI model
- **Zero raw storage** — Original document text is never persisted to disk or database
- **PII mapping isolation** — Token-to-original mappings are stored separately and used only for response deanonymization
- **Session expiry** — All session data (anonymized text, analysis, PII mappings) is auto-deleted after the configured TTL
- **JWT authentication** — All API endpoints require valid JWT tokens
- **Rate limiting** — Configurable per-minute request limits via SlowAPI

---

## License

This project is for educational and research purposes.
