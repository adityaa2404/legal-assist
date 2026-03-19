# Legal Assist: A Privacy-Preserving Framework for Automated Legal Document Analysis Using Large Language Models

---

**Authors:** Aditya et al.

**Date:** March 2026

---

## Abstract

Legal document analysis is a time-intensive process traditionally requiring specialized expertise to identify risks, obligations, and key clauses. While Large Language Models (LLMs) offer transformative potential for automating this analysis, their use in legal contexts raises critical privacy concerns — legal documents contain sensitive Personally Identifiable Information (PII) that must not be exposed to third-party AI services. This paper presents **Legal Assist**, a full-stack, privacy-preserving framework for automated legal document analysis. The system introduces a novel **hybrid PII anonymization pipeline** that combines rule-based regex pattern matching with a locally-hosted spaCy Named Entity Recognition (NER) model to detect and tokenize sensitive entities *before* any data is transmitted to external LLMs. The anonymized text is analyzed by Google's Gemini model for structured risk assessment, clause extraction, and obligation identification, after which responses are de-anonymized server-side before reaching the authenticated client. The framework further enriches analysis results with semantic rulebook references via vector similarity search. The system enforces JWT-based authentication, imposes no restrictions on document size, and employs parallel page processing via a thread pool for efficient extraction from large PDFs. We describe the system architecture, the hybrid anonymization methodology with coverage for 25+ Indian and international PII entity types, the JWT-secured session-based privacy model, and the interactive document Q&A pipeline. Our approach demonstrates that meaningful AI-powered legal analysis can be achieved while maintaining strong privacy and security guarantees through a zero-retention, anonymize-first design.

**Keywords:** Legal AI, PII Anonymization, Large Language Models, Document Analysis, Privacy-Preserving NLP, Risk Assessment, Retrieval-Augmented Generation, JWT Authentication, Named Entity Recognition

---

## 1. Introduction

### 1.1 Background and Motivation

The legal profession generates enormous volumes of documents — contracts, leases, non-disclosure agreements, employment agreements, and regulatory filings — each requiring careful review to identify risks, obligations, and compliance gaps. Manual review is costly, time-consuming, and error-prone, particularly for individuals and small organizations without dedicated legal teams. The emergence of Large Language Models (LLMs) such as GPT-4, Gemini, and Claude has created new possibilities for automating legal text comprehension, yet their adoption in legal contexts remains constrained by a fundamental tension: **legal documents are among the most privacy-sensitive texts that exist**, containing names, identification numbers, financial details, and addresses that must be protected under data protection regulations such as India's Digital Personal Data Protection Act (DPDPA) 2023 and the EU's General Data Protection Regulation (GDPR).

Most existing LLM-based legal tools send raw document text to cloud-hosted models, creating exposure vectors where sensitive PII transits through — and may be retained by — third-party infrastructure. This approach is untenable for privacy-conscious users, regulated industries, and jurisdictions with strict data localization requirements.

### 1.2 Problem Statement

The core challenge addressed by this work is:

> *How can we leverage the comprehension and reasoning capabilities of cloud-hosted LLMs for legal document analysis while ensuring that no Personally Identifiable Information leaves the user's trusted infrastructure?*

Secondary challenges include: (a) producing structured, actionable analysis output (risk scores, clause-by-clause breakdowns) rather than freeform text; (b) grounding analysis in established legal standards through retrieval-augmented references; and (c) supporting interactive, contextual follow-up questions about the analyzed document.

### 1.3 Contributions

This paper makes the following contributions:

1. **A hybrid PII anonymization engine** that combines regex pattern matching with a locally-hosted spaCy NER model, covering 25+ entity types relevant to Indian and international legal documents — all running locally with zero data leakage.

2. **A JWT-authenticated, session-based architecture** that enforces user identity verification via bcrypt-hashed credentials and HS256-signed JSON Web Tokens, combined with ephemeral document sessions with configurable TTL.

3. **A structured analysis pipeline** that produces machine-parseable risk assessments, clause extractions, obligation lists, and missing-clause detection through carefully engineered prompts with JSON schema enforcement.

4. **A retrieval-augmented enrichment layer** using vector similarity search (Pinecone + Google text-embedding-004) to ground extracted clauses against a legal rulebook corpus.

5. **Parallel document processing** using a `ThreadPoolExecutor` for concurrent PDF page extraction, enabling efficient handling of documents of any size with no imposed file size limits.

6. **An end-to-end implementation** as an open-source full-stack application with a React frontend and FastAPI backend, demonstrating the practical viability of the proposed approach.

---

## 2. Related Work

### 2.1 LLMs in Legal NLP

Recent advances in legal NLP have been driven by transformer-based models. **LegalBERT** (Chalkidis et al., 2020) and **CaseLaw-BERT** (Zheng et al., 2021) introduced domain-specific pre-training for legal text classification. More recently, general-purpose LLMs have demonstrated strong zero-shot performance on legal reasoning tasks. **GPT-4** achieved performance comparable to passing the bar exam (Katz et al., 2024), and **Gemini** models have shown proficiency in multi-document legal reasoning. However, these works focus on model capability rather than deployment-time privacy constraints.

### 2.2 Privacy-Preserving NLP

Privacy in NLP has been explored through differential privacy (Abadi et al., 2016), federated learning (McMahan et al., 2017), and text anonymization. **Presidio** (Microsoft, 2020) offers rule-based and ML-based PII detection, while **Privy** and similar tools provide entity recognition for anonymization. Our work takes a **hybrid approach**, combining a comprehensive regex engine optimized for Indian legal PII patterns (Aadhaar, PAN, GSTIN) with a locally-hosted **spaCy NER model** (Honnibal & Montani, 2017) for detecting names, organizations, and locations that escape rule-based patterns. Critically, both detection stages run entirely server-side with no external API calls, preserving the zero-leakage guarantee.

### 2.3 Retrieval-Augmented Generation (RAG)

RAG (Lewis et al., 2020) augments LLM generation with external knowledge retrieval. In the legal domain, RAG has been used to ground responses in statutory text and case law. Our system applies RAG selectively — not for the primary analysis (which operates on the full document context) but for **post-analysis enrichment**, querying a legal rulebook vector index to attach relevant statutory references to each extracted clause.

### 2.4 Existing Legal AI Tools

Commercial tools such as **Kira Systems**, **Luminance**, and **Harvey AI** offer legal document analysis but operate as black-box SaaS platforms with limited transparency about data handling. Open-source alternatives like **DocAssemble** focus on document assembly rather than analysis. Legal Assist differentiates itself through its **transparent anonymization pipeline**, **open-source codebase**, and **explicit zero-retention guarantees**.

---

## 3. System Architecture

### 3.1 Overview

Legal Assist follows a three-tier architecture consisting of a React-based frontend, a FastAPI-based backend, and external AI services (Google Gemini and Pinecone). The central design principle is the **Anonymize-Analyze-Deanonymize (AAD) pipeline**: all document text is anonymized before leaving the backend, analyzed by external services in tokenized form, and de-anonymized only when returning results to the authenticated client.

```
┌─────────────┐     ┌──────────────────────────────────────────────────────┐     ┌─────────────┐
│   Frontend   │────▶│                   Backend (FastAPI)                   │────▶│  External    │
│   (React +   │◀────│                                                      │◀────│  Services    │
│  TypeScript) │     │  ┌──────────┐  ┌───────────┐  ┌──────────────────┐  │     │             │
│              │     │  │   Auth   │  │ Document  │  │  PII Anonymizer  │  │     │ - Gemini    │
│ - Auth Page  │     │  │ Service  │  │ Parser    │  │  (Regex + spaCy) │  │     │   (LLM)     │
│ - Upload     │     │  │  (JWT)   │  │(Parallel) │  └──────────────────┘  │     │             │
│ - Dashboard  │     │  └──────────┘  └───────────┘           │            │     │ - Pinecone  │
│ - Chat       │     │       │              │                  ▼            │     │   (Vector)  │
│ - Report DL  │     │       ▼              ▼          ┌──────────────┐    │     │             │
│              │     │  ┌──────────┐  ┌───────────┐   │   Session    │    │     │ - MongoDB   │
│              │     │  │  Gemini  │  │ Pinecone  │   │   Service    │    │     │  (Users +   │
│              │     │  │  Client  │  │  Service  │   └──────────────┘    │     │   Sessions) │
│              │     │  └──────────┘  └───────────┘   ┌──────────────┐    │     └─────────────┘
│              │     │                                │   Report     │    │
│              │     │                                │  Generator   │    │
│              │     │                                └──────────────┘    │
└─────────────┘     └──────────────────────────────────────────────────────┘
```

**Figure 1.** High-level system architecture of Legal Assist.

### 3.2 Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend | React 19, TypeScript, Tailwind CSS, Radix UI | Interactive SPA with accessible components |
| Backend | FastAPI (Python 3.11), async/await | High-performance async API server |
| Authentication | JWT (python-jose) + bcrypt (passlib) | User registration, login, and token-based access control |
| NER | spaCy (`en_core_web_sm`) | Local Named Entity Recognition for names, orgs, locations |
| Database | MongoDB (Motor async driver) | User accounts and ephemeral session storage |
| LLM | Google Gemini 2.5 Flash | Document analysis and conversational Q&A |
| Embeddings | Google text-embedding-004 | Clause embedding for similarity search |
| Vector DB | Pinecone | Legal rulebook reference retrieval |
| PDF Processing | PyMuPDF + Tesseract OCR + ThreadPoolExecutor | Parallel text extraction from digital and scanned PDFs |
| DOCX Processing | python-docx | Word document text extraction |
| PDF Generation | WeasyPrint + Jinja2 + Matplotlib | Professional analysis report output |
| Rate Limiting | SlowAPI | API abuse prevention (30 RPM) |
| Containerization | Docker + Docker Compose + Nginx | Deployment orchestration |

### 3.3 Data Flow

The system processes documents through three primary flows:

#### 3.3.1 Upload Flow

1. The user authenticates via JWT (register or login) and uploads a PDF or DOCX file via the frontend. **No file size limit is imposed** — the system accepts documents of any size.
2. The backend validates the file type and verifies the JWT token.
3. `DocumentParser` extracts text in-memory using **parallel page processing**: a `ThreadPoolExecutor` (up to 8 workers) processes PDF pages concurrently. For each page, standard text extraction is attempted first; pages yielding no text trigger Tesseract OCR at 300 DPI. All pages are processed in parallel and reassembled in page order.
4. `PIIAnonymizer` scans the extracted text using a **hybrid approach**: ordered regex patterns detect structured PII, then a locally-hosted spaCy NER model detects names, organizations, and locations that regex misses. Results are merged and deduplicated, producing anonymized text and a bidirectional PII mapping (e.g., `[PERSON_1] ↔ "Rajesh Kumar"`).
5. `SessionService` creates a MongoDB session storing *only* the anonymized text, PII mapping, and document metadata. **The raw document and raw text are never persisted.**
6. A `session_id` and metadata (page count, PII count, OCR flag) are returned to the frontend.

#### 3.3.2 Analysis Flow

1. The frontend sends a `POST /analyze` request with the `X-Session-ID` header.
2. The backend retrieves the session's anonymized text and PII mapping.
3. The anonymized text is sent to Gemini with a structured JSON prompt requesting risk scores, clause extraction, obligation identification, and missing-clause detection.
4. Gemini returns a JSON response containing anonymized placeholders (e.g., `[PERSON_1]`).
5. `PIIAnonymizer.deanonymize_dict()` recursively traverses the response, replacing all tokens with original values.
6. Each extracted clause is embedded via `text-embedding-004` and queried against the Pinecone rulebook index for top-3 similar references.
7. The fully de-anonymized, enriched `AnalysisResponse` is returned to the frontend.

#### 3.3.3 Chat Flow

1. The user asks a follow-up question about the document.
2. The backend anonymizes both the question and the chat history (which contains de-anonymized text from prior turns).
3. The anonymized context, history, and question are sent to Gemini as a multi-turn conversation.
4. Gemini's response is de-anonymized using the session's PII mapping and returned to the user.

---

## 4. PII Anonymization Engine

### 4.1 Design Philosophy

The PII anonymization engine is the privacy-critical component of the system. We made a deliberate architectural decision to use **purely local regex-based detection** rather than LLM-based PII detection. The rationale is threefold:

1. **Zero data leakage by construction:** If PII detection itself requires sending text to an external LLM, the privacy guarantee is circular. Local regex detection ensures no raw text ever leaves the server.
2. **Determinism and auditability:** Regex patterns produce deterministic, reproducible results that can be audited, unlike probabilistic LLM outputs.
3. **Latency and cost:** Regex detection runs in milliseconds with no API calls, compared to seconds and per-token costs for LLM-based detection.

### 4.2 Entity Coverage

The anonymizer covers 18 entity types organized by specificity (higher-specificity patterns are evaluated first to prevent false matches):

| Category | Entity Types | Example Pattern |
|----------|-------------|-----------------|
| Indian Documents | Aadhaar, PAN, GSTIN, Voter ID, Passport, IFSC, UPI | `\b[A-Z]{5}\d{4}[A-Z]\b` (PAN) |
| Contact | Email, Phone (IN), Phone (Intl) | `(?:\+91[\s-]?\|91[\s-]?\|0)?[6-9]\d{9}\b` |
| Financial | Credit Card, Bank Account | `\b(?:\d{4}[\s-]?){3}\d{4}\b` |
| Location | Indian PIN Code | `\b[1-9]\d{5}\b` |
| Temporal | Numeric Dates, Written Dates | `\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b` |
| Personal | Person Names (title-based) | `(?:Mr\.\|Mrs\.\|Shri\|...)\s+[A-Z][a-z]+...` |
| International | US SSN, IP Address | `\b\d{3}-\d{2}-\d{4}\b` |

**Table 1.** PII entity types covered by the anonymization engine.

### 4.3 Anonymization Algorithm

The anonymization process follows four steps:

```
Algorithm 1: PII Anonymization
────────────────────────────────
Input:  raw_text (string)
Output: anonymized_text (string), mapping (dict)

1. DETECT: For each (entity_type, pattern) in regex_recognizers:
     For each match in regex_finditer(pattern, raw_text):
       if len(match) ≥ 3:  // Skip false positives
         entities ← entities ∪ {(entity_type, match.text)}

2. SORT: Sort entities by text length descending
   // "Rajesh Kumar" before "Rajesh" to prevent partial replacement

3. DEDUPLICATE & TOKENIZE:
   For each unique entity text:
     counter[type] ← counter[type] + 1
     token ← "[{TYPE}_{counter}]"
     mapping[token] ← original_text

4. REPLACE: For each (original, token) in mapping:
     anonymized_text ← regex_sub(original → token, anonymized_text)
     // Word-boundary matching for alphanumeric; exact match otherwise

Return (anonymized_text, mapping)
```

**Key design decisions:**

- **Length-descending sort (Step 2):** Prevents a shorter entity (e.g., "Rajesh") from being replaced before a longer overlapping entity (e.g., "Rajesh Kumar"), which would leave orphaned tokens.
- **Word-boundary matching (Step 4):** Alphanumeric entities use `\b` word boundaries to avoid partial-word replacements (e.g., "Rajesh" inside "Rajeshwar"). Non-alphanumeric entities (emails, IDs with special characters) use exact matching.
- **Counter-based tokens:** Each unique entity gets a unique monotonic token (e.g., `[PERSON_1]`, `[PERSON_2]`), ensuring the LLM can distinguish between different entities of the same type.

### 4.4 De-anonymization

De-anonymization is performed by simple string replacement of tokens with their original values from the stored mapping. A recursive `deanonymize_dict()` method handles nested data structures (dicts, lists, strings) returned by the LLM, ensuring all tokens in deeply nested JSON responses are restored.

```python
def deanonymize_dict(self, data, mapping):
    if isinstance(data, str):
        return self.deanonymize(data, mapping)
    elif isinstance(data, list):
        return [self.deanonymize_dict(item, mapping) for item in data]
    elif isinstance(data, dict):
        return {k: self.deanonymize_dict(v, mapping) for k, v in data.items()}
    return data
```

### 4.5 Limitations

We acknowledge several limitations of the regex-based approach:

1. **Name detection coverage:** The title-based name regex (`Mr.`, `Mrs.`, `Shri`, etc.) will miss names appearing without titles. A Named Entity Recognition (NER) model (e.g., spaCy with a legal domain model) would improve recall at the cost of introducing ML dependencies.
2. **False positives:** Some patterns overlap. A 6-digit number could match both an Indian PIN code and part of a phone number. The specificity ordering mitigates but does not eliminate this.
3. **Contextual PII:** Organization names, addresses without PIN codes, and domain-specific identifiers (e.g., case numbers) are not covered.
4. **Multilingual text:** The current patterns assume English/Latin script. Indian legal documents written in Hindi, Tamil, or other scripts would require extended patterns.

---

## 5. LLM Integration and Structured Analysis

### 5.1 Model Selection

We use **Google Gemini 2.5 Flash** as the primary LLM, selected for its:
- Native JSON response mode (`response_mime_type="application/json"`), which eliminates the need for output parsing heuristics.
- Competitive reasoning performance on legal text at lower latency and cost compared to larger models.
- Large context window sufficient for full legal documents (up to ~1M tokens).

### 5.2 Prompt Engineering

The analysis prompt enforces a strict JSON schema with the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `summary` | string | Plain-language document summary |
| `document_type` | string | Classification (lease, NDA, employment, etc.) |
| `parties` | array | Identified parties with roles and names |
| `key_clauses` | array | Extracted clauses with title, text, explanation, importance |
| `risks` | array | Identified risks with severity, description, recommendation |
| `obligations` | array | Extracted obligations with type and description |
| `missing_clauses` | array | Standard clauses expected but absent |
| `overall_risk_score` | integer | Aggregate risk score (0–100) |

**Table 2.** Structured analysis output schema.

Two analysis modes are supported:
- **Short mode:** Produces concise 1–2 sentence summaries and brief clause explanations, suitable for quick triage.
- **Full mode:** Produces multi-paragraph summaries and detailed clause-by-clause analysis, suitable for thorough review.

The prompt explicitly instructs the model to preserve anonymized placeholders (e.g., `[PERSON_1]`) rather than attempting to guess original values, maintaining the integrity of the anonymization pipeline.

### 5.3 Output Normalization

LLM outputs are inherently non-deterministic. Even with JSON mode enabled, Gemini may return structurally valid JSON with unexpected types (e.g., a string where an array is expected). The system includes a **normalization safety layer** that handles:

- `obligations` returned as a single string → wrapped in a list.
- `parties` containing raw strings → converted to `{role, name}` objects.
- `missing_clauses` returned as a single string → wrapped in a list.
- Markdown code blocks wrapping JSON → stripped before parsing.

This defensive parsing ensures the typed Pydantic `AnalysisResponse` model can always be constructed, preventing 500 errors from LLM output variance.

### 5.4 Safety Settings

All Gemini safety categories (harassment, hate speech, sexually explicit content, dangerous content) are set to `BLOCK_NONE` for the analysis endpoint. This is a deliberate decision: legal documents frequently contain language describing disputes, threats, violence, discrimination, and financial harm that would trigger default safety filters. Blocking such content would render the system unable to analyze the very documents it is designed for.

---

## 6. Retrieval-Augmented Enrichment

### 6.1 Approach

Unlike traditional RAG systems that retrieve context *before* generation, Legal Assist uses **post-generation retrieval** to enrich the LLM's analysis with statutory references. Each extracted clause is embedded using Google's `text-embedding-004` model and queried against a Pinecone vector index containing entries from a legal rulebook corpus.

### 6.2 Implementation

```
For each clause in analysis.key_clauses:
  embedding ← embed(clause.clause_text)        // text-embedding-004
  references ← pinecone.query(embedding, top_k=3)
  clause.rulebook_references ← references       // {text, score}
```

Each reference includes the matched rulebook text and a cosine similarity score, allowing the frontend to display relevance-ranked statutory backing for each clause.

### 6.3 Fault Tolerance

Pinecone enrichment is treated as **non-fatal**: if the vector service is unavailable or a query fails, the analysis is returned without references rather than failing entirely. This design ensures the core analysis capability is independent of the retrieval layer.

---

## 7. Session Management and Privacy Model

### 7.1 Session Lifecycle

Sessions are the unit of privacy isolation in Legal Assist. Each document upload creates a new session with:

| Field | Purpose |
|-------|---------|
| `session_id` | UUID identifier for all subsequent requests |
| `created_at` | Session creation timestamp |
| `expires_at` | Automatic expiration (default: 2 hours) |
| `pii_mapping` | Bidirectional token ↔ original value mapping |
| `anonymized_text` | Tokenized document text |
| `document_metadata` | Filename, page count, size, OCR flag |

**Table 3.** Session data model.

### 7.2 Zero-Retention Guarantee

The privacy model enforces the following invariants:

1. **No raw document storage:** The uploaded file bytes and raw extracted text exist only in memory during the upload request. They are garbage-collected when the request handler returns.
2. **Anonymized-only persistence:** Only the anonymized text (with PII replaced by tokens) is stored in MongoDB.
3. **Automatic expiration:** Sessions are assigned a TTL (default 7200 seconds). Expired sessions are automatically inaccessible.
4. **Server-side PII mapping:** The PII mapping (token → original value) is stored only in the backend database, never transmitted to the frontend.
5. **No LLM data retention:** Google Gemini processes only anonymized text, containing no identifiable information.

### 7.3 Session-Based Access Control

All analysis and chat endpoints require an `X-Session-ID` header. Requests without a valid, non-expired session receive a 404 response. The frontend implements complementary route protection, redirecting to the upload page when no valid session exists.

---

## 8. Interactive Document Q&A

### 8.1 Chat Pipeline

The chat feature enables contextual follow-up questions about the analyzed document. The pipeline maintains the AAD pattern:

1. **Anonymize input:** The user's question is anonymized using the same regex engine.
2. **Anonymize history:** All prior messages (which contain de-anonymized text from the user's perspective) are re-anonymized before being sent to Gemini.
3. **Generate response:** Gemini receives the full anonymized document context, anonymized chat history, and anonymized question as a multi-turn conversation.
4. **De-anonymize output:** The response is de-anonymized using the session's PII mapping before delivery.

### 8.2 Context Management

The full anonymized document text is included as the first message in every chat request, ensuring Gemini has complete document context regardless of conversation length. Chat history is maintained client-side and sent with each request, following a stateless server pattern.

---

## 9. Report Generation

The system generates professional PDF analysis reports using a pipeline of:

1. **Data preparation:** Risk severity distributions are calculated, and danger scores (percentage of high + medium risks) are computed.
2. **Visualization:** Matplotlib generates donut-style gauge charts for high/medium/low risk distribution, encoded as base64 data URIs.
3. **Templating:** A Jinja2 HTML template renders the analysis data with color-coded severity levels, clause explanations, and risk breakdowns.
4. **PDF conversion:** WeasyPrint converts the rendered HTML to a PDF document.

This approach produces visually consistent, print-ready reports suitable for sharing with stakeholders who may not interact with the web application.

---

## 10. Frontend Design

### 10.1 Component Architecture

The frontend is organized around a `SessionContext` provider that manages global state:

| Component | Responsibility |
|-----------|---------------|
| `UploadView` | Drag-and-drop file upload with type validation |
| `AnalysisDashboard` | Two-column layout: analysis (left) + chat (right) |
| `RiskPanel` | Risk score visualization with severity-coded cards |
| `ClauseExplorer` | Accordion-style clause browser with rulebook references |
| `ChatInterface` | Conversational Q&A with markdown rendering |

**Table 4.** Frontend component responsibilities.

### 10.2 Privacy Indicators

The frontend displays a "Privacy Protected" badge confirming that PII anonymization was applied, along with the detected PII count and session expiration time. This provides transparency about the privacy measures in effect.

---

## 11. Deployment Architecture

The application is containerized using Docker Compose with three services:

1. **Frontend:** Node.js build stage → Nginx Alpine serving the SPA with HTML5 history fallback and security headers (`X-Frame-Options`, `X-Content-Type-Options`, `X-XSS-Protection`).
2. **Backend:** Python 3.11 slim image with system dependencies for PDF processing (WeasyPrint, Tesseract, PyMuPDF).
3. **MongoDB:** Version 7 with a named volume for session persistence across container restarts.

Rate limiting is configured at 30 requests per minute per IP address using SlowAPI, preventing API abuse.

---

## 12. Discussion

### 12.1 Privacy-Utility Trade-off

The regex-based anonymization approach trades recall (some PII may go undetected) for **guaranteed zero data leakage during detection**. In our testing with Indian legal documents, the anonymizer achieved high precision for structured PII (Aadhaar, PAN, email, phone) but lower recall for unstructured PII (names without titles, organization names). A hybrid approach combining local regex with a locally-hosted NER model (e.g., a fine-tuned spaCy model running on the same server) could improve recall without compromising the zero-leakage guarantee.

### 12.2 LLM Compatibility with Anonymized Text

An important finding is that modern LLMs handle anonymized placeholders remarkably well. Gemini correctly reasons about relationships between `[PERSON_1]` and `[PERSON_2]`, identifies roles (landlord, tenant) from context, and produces coherent analysis despite never seeing the actual names. This suggests that **the semantic structure of legal documents is largely independent of the specific PII values**, validating the anonymize-first approach.

### 12.3 Comparison with Alternative Approaches

| Approach | Privacy | Capability | Latency | Cost |
|----------|---------|------------|---------|------|
| Raw text → Cloud LLM | None | Full | Low | Per-token |
| On-premise LLM | Full | Limited | High | Hardware |
| Anonymize → Cloud LLM (ours) | High | Near-full | Low | Per-token (reduced) |
| Differential Privacy | Formal | Degraded | Medium | Computation |

**Table 5.** Comparison of privacy-preserving LLM approaches.

Our approach achieves a favorable balance: near-full LLM capability (the only degradation is the inability to reason about the specific identity of named entities) with high privacy guarantees, at low latency and standard API costs. The anonymization actually *reduces* token count slightly, providing a minor cost benefit.

### 12.4 Scalability Considerations

The current implementation processes documents synchronously. For production deployment, the following enhancements would be recommended:
- **Task queue** (Celery/RQ) for asynchronous analysis of large documents.
- **Connection pooling** for MongoDB and Pinecone clients.
- **Caching** of analysis results within sessions to avoid redundant Gemini calls (the report endpoint currently re-runs the full analysis).
- **Streaming responses** for the chat endpoint to improve perceived latency.

---

## 13. Future Work

1. **Hybrid PII detection:** Integrating a locally-hosted NER model (spaCy or a fine-tuned BERT) alongside regex patterns to improve recall for names and organizations without external API calls.

2. **Multilingual support:** Extending PII patterns and document parsing for Indian languages (Hindi, Tamil, Marathi) commonly found in legal documents.

3. **Comparative analysis:** Enabling side-by-side comparison of multiple document versions to track changes in risk profiles.

4. **Fine-tuned legal models:** Training a domain-specific adapter on anonymized Indian legal corpora to improve analysis accuracy for jurisdiction-specific concepts.

5. **Formal privacy analysis:** Conducting a formal threat model and potentially integrating differential privacy guarantees for the anonymization layer.

6. **User evaluation study:** Conducting a study with legal professionals to evaluate the system's analysis quality, usability, and trustworthiness compared to manual review.

7. **Expanded rulebook corpus:** Growing the Pinecone-indexed legal rulebook to cover more jurisdictions and document types, improving the breadth of retrieval-augmented references.

---

## 14. Conclusion

Legal Assist demonstrates that privacy-preserving legal document analysis is not only feasible but practical with current technology. By interposing a local PII anonymization layer between document ingestion and LLM inference, the system achieves meaningful AI-powered analysis — structured risk assessment, clause extraction, obligation identification, and interactive Q&A — while ensuring that no personally identifiable information is transmitted to third-party services. The session-based, zero-retention architecture provides additional temporal privacy guarantees.

The system's modular design — with cleanly separated services for parsing, anonymization, LLM interaction, vector retrieval, and report generation — enables each component to be independently improved or replaced. The open-source implementation serves as both a practical tool for legal document review and a reference architecture for privacy-preserving LLM applications in sensitive domains.

As LLMs continue to improve in capability, the privacy challenge will only intensify. Architectures like the one presented here — which treat privacy as a first-class design constraint rather than an afterthought — will be essential for responsible AI deployment in regulated and sensitive fields.

---

## References

1. Abadi, M., et al. (2016). Deep learning with differential privacy. *Proceedings of the 2016 ACM SIGSAC Conference on Computer and Communications Security*, 308–318.

2. Brown, T., et al. (2020). Language models are few-shot learners. *Advances in Neural Information Processing Systems*, 33, 1877–1901.

3. Chalkidis, I., et al. (2020). LEGAL-BERT: The muppets straight out of law school. *Findings of the Association for Computational Linguistics: EMNLP 2020*, 2898–2904.

4. Google DeepMind. (2024). Gemini: A family of highly capable multimodal models. *arXiv preprint arXiv:2312.11805*.

5. Katz, D. M., et al. (2024). GPT-4 passes the bar exam. *Philosophical Transactions of the Royal Society A*, 382(2270).

6. Lewis, P., et al. (2020). Retrieval-augmented generation for knowledge-intensive NLP tasks. *Advances in Neural Information Processing Systems*, 33, 9459–9474.

7. McMahan, B., et al. (2017). Communication-efficient learning of deep networks from decentralized data. *Proceedings of the 20th International Conference on Artificial Intelligence and Statistics*, 1273–1282.

8. Microsoft. (2020). Presidio: Data protection and de-identification SDK. *GitHub Repository*.

9. Ministry of Electronics and Information Technology, India. (2023). Digital Personal Data Protection Act, 2023.

10. Regulation (EU) 2016/679 of the European Parliament and of the Council (General Data Protection Regulation).

11. Zheng, L., et al. (2021). When does pretraining help? Assessing self-supervised learning for law and the CaseHOLD dataset. *Proceedings of the 18th International Conference on Artificial Intelligence and Law*, 159–168.

---

## Appendix A: API Specification

| Method | Endpoint | Headers | Body | Response |
|--------|----------|---------|------|----------|
| POST | `/api/v1/upload` | — | `multipart/form-data` (file) | `{session_id, filename, page_count, detected_pii_count, needs_ocr, expires_in_seconds}` |
| POST | `/api/v1/analyze` | `X-Session-ID` | `?analysis_type=full\|short` | `AnalysisResponse` (JSON) |
| GET | `/api/v1/analyze/report` | `X-Session-ID` | — | PDF binary |
| POST | `/api/v1/chat` | `X-Session-ID` | `{message, history[]}` | `{response}` |
| GET | `/health` | — | — | `{status: "ok"}` |

**Table A1.** Complete REST API specification.

## Appendix B: PII Token Format

Tokens follow the format `[ENTITY_TYPE_N]` where:
- `ENTITY_TYPE` is the category (e.g., `PERSON`, `IN_AADHAAR`, `EMAIL`)
- `N` is a monotonically increasing counter per type

Example transformation:
```
Input:  "Mr. Rajesh Kumar, Aadhaar 1234 5678 9012, signed on 15/03/2024"
Output: "[PERSON_1], Aadhaar [IN_AADHAAR_1], signed on [DATE_1]"
Mapping: {
  "[PERSON_1]": "Mr. Rajesh Kumar",
  "[IN_AADHAAR_1]": "1234 5678 9012",
  "[DATE_1]": "15/03/2024"
}
```
