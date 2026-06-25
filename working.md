# Legal Assist — Complete Working Document
**Scope: Digital PDF + Gemini provider, end-to-end**

---

## Table of Contents
1. [System Overview](#1-system-overview)
2. [Phase 1 — File Upload & Validation](#2-phase-1--file-upload--validation)
3. [Phase 2 — Text Extraction (PyMuPDF)](#3-phase-2--text-extraction-pymupdf)
4. [Phase 3 — PII Anonymization](#4-phase-3--pii-anonymization)
5. [Phase 4 — Session Creation](#5-phase-4--session-creation)
6. [Phase 5 — HTOC Tree Building](#6-phase-5--htoc-tree-building)
7. [Phase 6 — BM25 Index Building](#7-phase-6--bm25-index-building)
8. [Phase 7 — Document Analysis](#8-phase-7--document-analysis)
9. [Phase 8 — Chat (RAG)](#9-phase-8--chat-rag)
10. [Data Flow Summary](#10-data-flow-summary)
11. [Key Constants & Limits](#11-key-constants--limits)

---

## 1. System Overview

```
Frontend (React + Vite)
        ↕ REST + SSE
Backend (FastAPI + Python)
        ↕
MongoDB Atlas          ← sessions, users, history, analysis cache
        ↕
Gemini 2.5 Flash API   ← HTOC build, analysis, chat
Presidio (local)       ← PII anonymization (no external API)
PyMuPDF (local)        ← digital text extraction
BM25Okapi (local)      ← keyword search index
```

**AI Keys used (Gemini provider):**
- `GEMINI_API_KEY` — analysis
- `GEMINI_HTOC_API_KEY` — HTOC build + tree search
- `GEMINI_CHAT_API_KEY` — chat responses

Three separate keys = three independent rate limit buckets. No task starves another.

---

## 2. Phase 1 — File Upload & Validation

**Endpoint:** `POST /api/v1/upload`
**File:** `backend/app/api/v1/documents.py`

### What the frontend sends
```
multipart/form-data:
  file        → the PDF file (binary)
  doc_type    → "general" | "lease" | "employment" | "loan" | ...
  ocr_mode    → "fast" | "secure"
  ocr_language → "English" | "Hindi" | ...
  ai_provider → "gemini" | "groq" | "openai" | "claude"
```

### Validation
```python
# Extension check
ext = filename.rsplit(".", 1)[-1].lower()
if ext not in ["pdf", "docx"]:
    raise HTTPException(400, "Only PDF and DOCX files are supported")

# Size check
content = await file.read()
size_mb = len(content) / (1024 * 1024)
if size_mb > settings.MAX_FILE_SIZE_MB:   # 50 MB
    raise HTTPException(413, "File too large")
```

### Path decision
After validation, the backend decides which of three paths to take:

```
Is it a scanned PDF?
  → needs_ocr = True  (PyMuPDF returned empty text)
  → SCANNED PATH: everything in background, return session_id immediately

Is it a large digital PDF? (>500K chars OR >100 pages)
  → LARGE DIGITAL PATH: PII in background too

Is it a small digital PDF? (<500K chars AND ≤100 pages)
  → SMALL DIGITAL PATH: PII done synchronously, only HTOC in background
```

**For digital PDFs (our focus):** PyMuPDF extraction runs first synchronously to detect the path.

---

## 3. Phase 2 — Text Extraction (PyMuPDF)

**File:** `backend/app/services/document_parser.py`
**Method:** `DocumentParser._extract_pdf_digital()`

### How it works
```python
doc = fitz.open(stream=file_content, filetype="pdf")
page_texts = []

for page in doc:
    text = page.get_text()          # extract raw text from PDF layer
    if len(text.strip()) < 50:
        # Page has almost no text → it's a scanned image page
        needs_ocr = True
        page_texts.append("")
    else:
        page_texts.append(text)
```

### Output
```python
page_texts = [
    "GENERAL ALLEGATIONS\n1. Plaintiff, Ann Altman...",   # page 0
    "7. From approximately 1997 to 1999...",               # page 1
    "COUNT I: BATTERY\n20. Plaintiff re-alleges...",       # page 2
    ...
]
# len(page_texts) == total pages in PDF
```

Also produces:
- `full_text` = `"\n\n".join(page_texts)` — used as fallback for analysis
- `needs_ocr` = True/False flag
- `page_count` = number of pages

### Digital detection rule
If **any** page returns < 50 chars → `needs_ocr = True` → switches to OCR path.
For a clean digital PDF, all pages have real text → stays on digital path.

---

## 4. Phase 3 — PII Anonymization

**File:** `backend/app/services/pii_anonymizer.py`
**Library:** Microsoft Presidio (runs fully locally, no API)

### What it detects
15 pattern recognizers for Indian-specific PII:

| Entity | Example | Token |
|--------|---------|-------|
| Person names | Ann Altman | `[PERSON_1]` |
| Organizations | XYZ Corp Ltd | `[ORG_1]` |
| Email | ann@gmail.com | `[EMAIL_1]` |
| Phone | +91 98765 43210 | `[PHONE_1]` |
| Aadhaar | 1234 5678 9012 | `[AADHAAR_1]` |
| PAN | ABCDE1234F | `[PAN_1]` |
| GSTIN | 27AAPFU0939F1ZV | `[GSTIN_1]` |
| Passport | A1234567 | `[PASSPORT_1]` |
| Driving License | MH01 20110012345 | `[DL_1]` |
| IFSC | SBIN0001234 | `[IFSC_1]` |
| Credit Card | 4111 1111 1111 1111 | `[CREDIT_CARD_1]` |
| IP Address | 192.168.1.1 | `[IP_1]` |
| PIN Code | 400001 | `[PIN_1]` |
| Voter ID | ABC1234567 | `[VOTER_ID_1]` |
| Vehicle Reg | MH 01 AB 1234 | `[VEHICLE_1]` |

### Process
```python
async def anonymize(text: str) -> (anonymized_text, pii_mapping):
    # 1. Run all 15 pattern recognizers in parallel
    results = analyzer.analyze(text, language="en")

    # 2. Resolve overlapping detections (keep highest confidence)
    results = _resolve_overlaps(results)

    # 3. Sort by position (right to left to preserve offsets)
    results.sort(key=lambda r: r.start, reverse=True)

    # 4. Replace each match with a token
    for result in results:
        entity_type = result.entity_type    # "PERSON"
        counter[entity_type] += 1
        token = f"[{entity_type}_{counter[entity_type]}]"   # "[PERSON_1]"
        text = text[:result.start] + token + text[result.end:]
        pii_mapping[token] = original_value

    return anonymized_text, pii_mapping
```

### Output
```python
anonymized_text = "GENERAL ALLEGATIONS\n1. Plaintiff, [PERSON_1]..."
pii_mapping = {
    "[PERSON_1]": "Ann Altman",
    "[PERSON_2]": "Samuel Altman",
    "[ORG_1]": "XYZ LLC",
    ...
}
```

The `pii_mapping` is stored in MongoDB and used to **de-anonymize** responses before they reach the user.

### De-anonymization
```python
def deanonymize(text: str, pii_mapping: dict) -> str:
    for token, real_value in pii_mapping.items():
        text = text.replace(token, real_value)
    return text
```
Applied to every LLM response before it's returned to the frontend.

---

## 5. Phase 4 — Session Creation

**File:** `backend/app/services/session_service.py`
**DB:** MongoDB Atlas, `sessions` collection

### What gets stored
```python
session_data = {
    "session_id":        "da504324-d060-455b-...",   # UUID
    "user_email":        "user@example.com",
    "created_at":        datetime(2026, 4, 23, ...),
    "expires_at":        created_at + 2 hours,
    "pii_mapping":       {"[PERSON_1]": "Ann Altman", ...},
    "anonymized_text":   "full anonymized text joined",
    "page_texts":        ["page 0 text...", "page 1 text...", ...],
    "htoc_tree":         None,          # filled in later
    "bm25_data":         None,          # filled in later
    "htoc_status":       "pending",     # → "building" → "ready"
    "ai_provider":       "gemini",
    "document_metadata": {
        "filename":    "complaint.pdf",
        "page_count":  10,
        "size_bytes":  524288,
        "needs_ocr":   False,
        "doc_type":    "general",
    }
}
```

### Response to frontend
```json
{
  "session_id": "da504324-d060-455b-a9c0-c82362274769",
  "page_count": 10,
  "needs_ocr": false,
  "htoc_status": "pending"
}
```

**Returns immediately** — the frontend gets this in ~500ms-1s and can render the upload success screen. HTOC+BM25 build continues in background.

### asyncio.create_task
```python
asyncio.create_task(
    _build_htoc_and_bm25(session_id, page_texts, ai_provider)
)
# ↑ fires and forgets — does NOT await
return UploadResponse(session_id=session_id, ...)
```

---

## 6. Phase 5 — HTOC Tree Building

**File:** `backend/app/services/htoc_builder.py`
**Triggered by:** `asyncio.create_task` after session creation
**Gemini key used:** `GEMINI_HTOC_API_KEY`

### What is HTOC?
Hierarchical Table of Contents — a JSON tree that maps the document's logical structure to page ranges. Enables structured retrieval without vector embeddings.

### Step 1 — Page previews
```python
MAX_CHARS_PER_PAGE_PREVIEW = 600   # Gemini
# (200 for Groq — smaller context window)

for i, text in enumerate(page_texts):
    preview = text[:600].strip()
    previews.append(f"--- Page {i} ---\n{preview}")

page_previews = "\n\n".join(previews)
```

### Step 2 — Chunk decision
```
≤ 3 pages    → skip LLM, build simple tree (title = first line of each page)
≤ 100 pages  → single LLM call with all page previews
> 100 pages  → chunked: 100 pages per chunk, parallel calls, then merge
```

For a 10-page document: single call. For a 320-page document: 4 chunks of 80 pages, 4 parallel Gemini calls, then 1 merge call.

### Step 3 — Gemini prompt
```
You are a legal document structure analyzer. Analyze the following document
pages and build a hierarchical table of contents (HTOC).

DOCUMENT PAGES:
--- Page 0 ---
GENERAL ALLEGATIONS
1. Plaintiff, [PERSON_1], a resident and citizen of Hawaii...
--- Page 1 ---
7. From approximately 1997 to 1999, when [PERSON_1] was between...
...

Return a JSON object:
{
  "title": "Document title",
  "node_id": "root",
  "start_page": 0,
  "end_page": 9,
  "summary": "Brief overall summary",
  "children": [
    {
      "title": "Section name",
      "node_id": "0001",
      "start_page": 0,
      "end_page": 3,
      "summary": "What this section covers",
      "children": [...]
    }
  ]
}

RULES:
- Every page must be covered by at least one node
- node_id must be unique 4-digit strings
- Identify: preamble, definitions, clauses, schedules, signatures
- RETURN ONLY VALID JSON
```

### Step 4 — Gemini response (example)
```json
{
  "title": "Complaint — [PERSON_1] v. [PERSON_2]",
  "node_id": "root",
  "start_page": 0,
  "end_page": 9,
  "summary": "Civil complaint alleging childhood sexual abuse by sibling",
  "children": [
    {
      "title": "Parties and Jurisdiction",
      "node_id": "0001",
      "start_page": 0,
      "end_page": 0,
      "summary": "Identifies plaintiff and defendant, establishes jurisdiction",
      "children": []
    },
    {
      "title": "General Allegations",
      "node_id": "0002",
      "start_page": 0,
      "end_page": 3,
      "summary": "16 numbered allegations of sexual abuse 1997-2006",
      "children": []
    },
    {
      "title": "Count I: Battery",
      "node_id": "0003",
      "start_page": 4,
      "end_page": 5,
      "summary": "Civil battery claim",
      "children": []
    }
  ]
}
```

### Step 5 — Validation & fallback
```python
def _validate_tree(tree, num_pages):
    tree.setdefault("title", "Document")
    tree.setdefault("node_id", "root")
    tree.setdefault("children", [])
    # ensure all children have required fields
    _fix_children(tree)
    return tree

# If LLM fails entirely:
def _fallback_tree(page_texts):
    # one node per page: {"title": "Page 1", "start_page": 0, ...}
```

### Step 6 — Session updated
```python
await session_service.update(session_id, SessionUpdate(
    htoc_tree=tree,
    htoc_status="ready",   # ← frontend polling detects this
))
```

**Frontend polls `/api/v1/htoc-status` every 2 seconds** until `"ready"`.

---

## 7. Phase 6 — BM25 Index Building

**File:** `backend/app/services/bm25_search.py`
**Runs:** immediately after HTOC is built, in the same background task
**Library:** `rank_bm25.BM25Okapi`

### What is BM25?
Best Match 25 — statistical keyword ranking. No AI, no API. Ranks pages by word relevance to a query.

### Step 1 — Tokenize all pages
```python
def _tokenize(text: str) -> List[str]:
    text = text.lower()
    text = re.sub(r'[^\w\s₹]', ' ', text)   # keep alphanumeric + ₹
    tokens = text.split()
    return [t for t in tokens if len(t) > 2]  # drop short words

page_tokens = [_tokenize(text) for text in page_texts]
# [["general", "allegations", "plaintiff", ...],   # page 0 tokens
#  ["approximately", "1997", "1999", ...],           # page 1 tokens
#  ...]
```

### Step 2 — Build BM25 index
```python
index = BM25Okapi(page_tokens)
# Internally builds: IDF scores for every word across all pages
# ~10-50ms for 300 pages
```

### Step 3 — Extract HTOC nodes for boost
Flattens the HTOC tree into a list:
```python
[
  {"node_id": "0002", "title": "General Allegations",
   "summary": "16 allegations of abuse 1997-2006",
   "start_page": 0, "end_page": 3},
  {"node_id": "0003", "title": "Count I: Battery",
   "summary": "Civil battery claim",
   "start_page": 4, "end_page": 5},
  ...
]
```

Also builds `page_to_nodes` map: `{0: [node_0002], 1: [node_0002], ...}`

### Step 4 — Serialized and stored in MongoDB
```python
bm25_data = {
    "htoc_nodes": [...],         # flat node list
    "page_tokens": [...],        # tokenized pages
    "num_pages": 10
}
await session_service.update(session_id, SessionUpdate(bm25_data=bm25_data))
```

Index is reconstructed from `page_tokens` on load — `BM25Okapi` is not serializable so it's rebuilt in memory each time.

---

## 8. Phase 7 — Document Analysis

**Endpoint:** `POST /api/v1/analyze?analysis_type=full`
**File:** `backend/app/api/v1/analysis.py`
**Gemini key used:** `GEMINI_API_KEY`

### Step 1 — Build structured context
```python
# Uses HTOC tree to build organized context (not raw full text)
structured_context = await tree_search.search_for_analysis(
    tree=session.htoc_tree,
    page_texts=session.page_texts,
    gemini_client=gemini,
)
```

`search_for_analysis` does **recursive DFS** through the tree:
```
## General Allegations (Pages 1-4)
Summary: 16 allegations of childhood sexual abuse

[Page 1 text...]
[Page 2 text...]
[Page 3 text...]

## Count I: Battery (Pages 5-6)
Summary: Civil battery claim
[Page 5 text...]
```

Capped at `MAX_ANALYSIS_CHARS = 80,000` characters.

### Step 2 — Analysis prompt (full)
Sent to `gemini-2.5-flash` with `response_mime_type="application/json"`:

```
You are legal-assist AI, an expert legal document analyst.
Analyze the following legal document and return a strictly valid JSON object.

REQUIRED JSON STRUCTURE:
{
  "summary": "Plain-language summary (3-5 paragraphs)",
  "document_type": "Classification (lease, NDA, employment, etc.)",
  "parties": [{"role": "Plaintiff", "name": "[PERSON_1]"}],
  "key_clauses": [{
    "clause_title": "Name",
    "clause_text": "Exact text",
    "plain_english": "Simplified explanation",
    "importance": "critical | important | standard",
    "risk_rank": 1
  }],
  "risks": [{
    "risk_title": "Brief description",
    "severity": "high | medium | low",
    "description": "What could go wrong",
    "recommendation": "What user should do"
  }],
  "obligations": [{"type": "...", "description": "..."}],
  "missing_clauses": ["Standard clauses that are absent"],
  "overall_risk_score": 0
}

RISK SCORE FORMULA:
  A = min(40, high*6 + medium*3 + low*1)      ← Risk severity
  B = min(25, critical_missing*5 + important_missing*2)  ← Missing clauses
  C = rating * 5   (0=balanced, 4=unconscionable)        ← One-sidedness
  D = min(15, protections_present * 2)                    ← Protective credit
  FINAL = max(5, min(95, A + B + C - D))

Document:
[structured context — up to 80,000 chars]
```

### Step 3 — Backend clamps the score
Even if LLM returns a bad score, backend corrects it:
```python
min_floor = min(95, high_count * 6 + medium_count * 3 + missing_count * 2)
if score < 5 or (score < min_floor and min_floor > 10):
    score = max(score, min_floor)
result["overall_risk_score"] = max(5, min(95, score))
```

### Step 4 — De-anonymize
```python
result = pii_service.deanonymize_dict(raw_result, session.pii_mapping)
# "[PERSON_1]" → "Ann Altman" in all string fields
```

### Step 5 — Cache and return
```python
await session_service.save_analysis(session_id, "full", result)
return AnalysisResponse(**result)
```

Cached in MongoDB. Subsequent calls return instantly from cache.
Use `?force=true` to bypass cache and re-run.

---

## 9. Phase 8 — Chat (RAG)

**Endpoint:** `POST /api/v1/chat/stream`
**File:** `backend/app/api/v1/chat.py`
**Returns:** Server-Sent Events (SSE)

### Full streaming pipeline

```
User message → anonymize → build search query → BM25 search
                                                    ↓
                                          confidence high/medium?
                                                Yes → use BM25 result
                                                No  → LLM tree search
                                                    ↓
                                          extract page text context
                                                    ↓
                                          stream LLM response (SSE)
                                                    ↓
                                          de-anonymize chunks
                                                    ↓
                                          send to frontend
```

### Step 1 — Anonymize the question
```python
anonymized_question, _ = await pii_service.anonymize(request.message)
# "What did Samuel Altman do?" → "What did [PERSON_2] do?"
```

### Step 2 — Build context-aware search query
```python
def _build_search_query(question, history):
    # Appends last 2 exchanges for follow-up awareness
    return "Conversation context:\nUser: ...\nAssistant: ...\n\nCurrent question: ..."
```

### Step 3 — BM25 search (primary, <5ms)
```python
bm25 = BM25SearchService()
bm25.load_from_data(session.bm25_data)   # rebuild index from stored tokens
search_result = bm25.search(search_query, session.page_texts)
confidence = search_result["confidence"]  # "high" | "medium" | "low"
```

**BM25 scoring:**
```python
bm25_scores = index.get_scores(query_tokens)
# boost by HTOC title/summary overlap
boosted_scores[page] += title_overlap * 3.0 + summary_overlap * 1.5
# top pages selected, full sections expanded
```

**Confidence levels:**
- `max_score > 2.0` → high (exact keyword match found)
- `max_score > 0.5` → medium (partial match)
- `max_score ≤ 0.5` → low (semantic query, no keywords matched)

**Exhaustive query detection:**
```python
# "list all", "all allegations", "enumerate", "complete list" → top_k=15
if any(p in query_lower for p in exhaustive_patterns):
    top_k = max(top_k, 15)
```

### Step 4 — LLM tree search fallback (only if BM25 low confidence)
```python
if confidence == "low" and session.htoc_tree:
    result = await tree_search.search(
        tree=session.htoc_tree,
        query=search_query,
        page_texts=session.page_texts,
        gemini_client=gemini,
        provider=ai_provider,   # uses same provider as session
    )
```

Tree search strips the tree to summaries only → sends to Gemini:
```
Given this query and HTOC tree, which node_ids contain the answer?
→ {"selected_nodes": ["0002"], "confidence": "high"}
```
Then extracts page text for those node IDs via O(1) hash lookup.

### Step 5 — Stream LLM response
```python
stream = gemini.chat_with_context_stream(
    question=anonymized_question,
    context=context,              # extracted pages
    chat_history=trimmed_history,
    source_info="General Allegations (p.1-4), ...",
    provider="gemini",
)

async for chunk in stream:
    # buffer partial PII tokens (e.g. "[PERS" split across chunks)
    buffer += chunk
    partial = _PARTIAL_TOKEN_RE.search(buffer)  # regex: \[[A-Z_0-9]*$
    if partial:
        emit = buffer[:partial.start()]
        buffer = buffer[partial.start():]
    else:
        emit = buffer
        buffer = ""

    if emit:
        clean_chunk = pii_service.deanonymize(emit, session.pii_mapping)
        yield f"event: token\ndata: {json.dumps({'text': clean_chunk})}\n\n"
```

### Step 6 — SSE events sent to frontend
```
event: sources
data: {"source_sections": [{"title": "General Allegations", "pages": "1-4"}]}

event: token
data: {"text": "Here are all 16 General Allegations:\n\n"}

event: token
data: {"text": "1. Ann Altman is a resident of Hawaii..."}

... (more token events as Gemini streams)

event: done
data: {}
```

### History trimming (long conversations)
```python
MAX_HISTORY_MESSAGES = 8   # last 4 exchanges sent to LLM
SUMMARIZE_AFTER = 8        # older messages summarized to 1 context line

# If history > 8 messages:
old_messages → "Earlier we discussed: [topic1]; [topic2]"
recent_messages → last 8 as-is
```

### Response caching
```python
query_hash = md5(f"{session_id}:{normalized_question}")
cached = await session_service.get_cached_chat(session_id, query_hash)
if cached:
    # return cached response as single token event, skip LLM entirely
```

---

## 10. Data Flow Summary

```
PDF file
  ↓
PyMuPDF → page_texts[]           (local, sync, ~200ms)
  ↓
Presidio → anonymized_texts[]    (local, sync, ~300ms)
         + pii_mapping{}
  ↓
MongoDB ← session created        (async write, ~100ms)
  ↓  ← session_id returned to frontend here (~600ms total)
asyncio.create_task:
  ↓
Gemini HTOC API → htoc_tree{}    (API call, ~5-15s)
  ↓
BM25Okapi → bm25_data{}          (local, <50ms)
  ↓
MongoDB ← session updated, htoc_status="ready"
  ↓  ← frontend polling detects "ready"
  ↓
[User triggers analyze]
  ↓
tree_search.search_for_analysis → structured_context  (local DFS, <1ms)
  ↓
Gemini Analysis API → raw_result{}  (API call, ~10-30s)
  ↓
pii_service.deanonymize_dict()   (local regex, <1ms)
  ↓
MongoDB ← analysis cached
  ↓  ← AnalysisResponse returned to frontend
  ↓
[User sends chat message]
  ↓
Presidio anonymize question      (local, <50ms)
  ↓
BM25 search → top pages + confidence  (local, <5ms)
  ↓  (if low confidence)
Gemini HTOC tree search → node_ids    (API call, ~1-3s)
  ↓
Gemini Chat API → stream chunks  (API call, streaming)
  ↓
PII deanonymize each chunk       (local, <1ms per chunk)
  ↓
SSE token events → frontend
```

---

## 11. Key Constants & Limits

| Constant | Value | Location |
|----------|-------|----------|
| Max file size | 50 MB | `config.py` |
| Session TTL | 2 hours | `config.py` |
| HTOC max pages per prompt | 100 (Gemini), 40 (Groq) | `htoc_builder.py` |
| HTOC chars per page preview | 600 (Gemini), 200 (Groq) | `htoc_builder.py` |
| BM25 default top_k | 8 pages | `bm25_search.py` |
| BM25 exhaustive top_k | 15 pages | `bm25_search.py` |
| Max context for analysis | 80,000 chars | `tree_search.py` |
| Max context for chat | 50,000 chars | `tree_search.py` |
| Max full-text chat context | 200,000 chars | `gemini_client.py` |
| Chat history window | 8 messages | `chat.py` |
| Gemini timeout | 90s (180s for analysis) | `config.py` |
| Gemini retry attempts | 3 with backoff | `gemini_client.py` |
| Risk score range | 5–95 | `analysis.py` |
| Claude max tokens (analysis) | 16,000 | `gemini_client.py` |
| Claude max tokens (HTOC) | 8,192 | `gemini_client.py` |

---

*Document covers: digital PDF path, Gemini provider, production configuration as of 2026-04-23*
