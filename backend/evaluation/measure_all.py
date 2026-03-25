"""
Legal Assist — Performance Evaluation Suite
============================================
Measures 4 metrics:
  1. OCR Accuracy (CER, WER)
  2. Clause Detection Precision (P, R, F1)
  3. Response Relevance / RAG Quality (BERTScore, Retrieval Hit Rate)
  4. Latency (upload, analysis, chat)

Usage:
  python -m evaluation.measure_all --all           # run everything
  python -m evaluation.measure_all --ocr           # OCR only
  python -m evaluation.measure_all --clauses       # clause detection only
  python -m evaluation.measure_all --rag           # RAG quality only
  python -m evaluation.measure_all --latency       # latency only
"""

import argparse
import json
import time
import os
import sys

# Add parent dir to path so we can import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ═══════════════════════════════════════════════════════════════
#  METRIC 1: OCR Accuracy
# ═══════════════════════════════════════════════════════════════

def measure_ocr_accuracy(ground_truth_dir: str = "evaluation/data/ocr_ground_truth"):
    """
    Compares OCR output against manually transcribed ground truth.

    Directory structure expected:
      ocr_ground_truth/
        doc1.pdf          ← scanned PDF
        doc1.txt          ← manually transcribed text (ground truth)
        doc2.pdf
        doc2.txt
        ...

    Metrics:
      - CER (Character Error Rate): edit_distance(pred, ref) / len(ref)
      - WER (Word Error Rate): word-level edit distance / word count
    """
    try:
        import Levenshtein
    except ImportError:
        print("Install: pip install python-Levenshtein")
        print("   CER = edit_distance(predicted, reference) / len(reference)")
        print("   WER = word_edit_distance(predicted, reference) / word_count(reference)")
        return

    from app.services.document_parser import DocumentParser
    import asyncio

    if not os.path.isdir(ground_truth_dir):
        print(f"\n[OCR] Create directory: {ground_truth_dir}/")
        print("  Put pairs of files: doc1.pdf (scanned) + doc1.txt (ground truth)")
        _print_ocr_manual_guide()
        return

    pdfs = sorted(f for f in os.listdir(ground_truth_dir) if f.endswith(".pdf"))
    if not pdfs:
        print(f"[OCR] No .pdf files found in {ground_truth_dir}/")
        _print_ocr_manual_guide()
        return

    results = []
    parser = DocumentParser()

    for pdf_file in pdfs:
        txt_file = pdf_file.replace(".pdf", ".txt")
        txt_path = os.path.join(ground_truth_dir, txt_file)
        pdf_path = os.path.join(ground_truth_dir, pdf_file)

        if not os.path.exists(txt_path):
            print(f"  [SKIP] No ground truth for {pdf_file}")
            continue

        with open(txt_path, "r", encoding="utf-8") as f:
            reference = f.read().strip()
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        # Run OCR
        predicted = asyncio.run(
            parser.extract_async(pdf_bytes, "application/pdf", doc_type="scanned")
        ).strip()

        # CER
        cer = Levenshtein.distance(predicted, reference) / max(len(reference), 1)

        # WER
        pred_words = predicted.split()
        ref_words = reference.split()
        wer = Levenshtein.distance(
            " ".join(pred_words), " ".join(ref_words)
        ) / max(len(ref_words), 1)

        results.append({"file": pdf_file, "cer": cer, "wer": wer})
        print(f"  {pdf_file}: CER={cer:.4f}  WER={wer:.4f}")

    if results:
        avg_cer = sum(r["cer"] for r in results) / len(results)
        avg_wer = sum(r["wer"] for r in results) / len(results)
        print(f"\n  [OCR AVERAGE] CER={avg_cer:.4f}  WER={avg_wer:.4f}  (n={len(results)})")
        return {"avg_cer": avg_cer, "avg_wer": avg_wer, "n": len(results), "details": results}


def _print_ocr_manual_guide():
    print("""
  HOW TO PREPARE OCR GROUND TRUTH:
  ─────────────────────────────────
  1. Pick 5-10 scanned legal PDFs
  2. Manually transcribe each page (or use a high-quality commercial OCR as reference)
  3. Save as: evaluation/data/ocr_ground_truth/doc1.pdf + doc1.txt
  4. Run: python -m evaluation.measure_all --ocr

  INTERPRETING RESULTS:
  ─────────────────────
  CER (Character Error Rate):
    < 0.02 = Excellent (98%+ accuracy)
    < 0.05 = Good (95%+)
    < 0.10 = Acceptable (90%+)
    > 0.10 = Poor — check image quality / OCR engine

  WER (Word Error Rate):
    < 0.05 = Excellent
    < 0.10 = Good
    < 0.20 = Acceptable
""")


# ═══════════════════════════════════════════════════════════════
#  METRIC 2: Clause Detection Precision
# ═══════════════════════════════════════════════════════════════

def measure_clause_detection(ground_truth_path: str = "evaluation/data/clause_ground_truth.json"):
    """
    Compares extracted clauses against expert-annotated ground truth.

    Ground truth format (clause_ground_truth.json):
    [
      {
        "document": "lease_agreement_1.pdf",
        "session_id": "...",         ← session ID after uploading this doc
        "expert_clauses": [
          {"title": "Rent Clause", "importance": "critical"},
          {"title": "Security Deposit", "importance": "important"},
          {"title": "Termination", "importance": "critical"},
          ...
        ]
      }
    ]

    Metrics:
      - Precision: correct_detected / total_detected
      - Recall: correct_detected / total_expert
      - F1: harmonic mean
    """
    if not os.path.exists(ground_truth_path):
        print(f"\n[CLAUSES] Create: {ground_truth_path}")
        _print_clause_manual_guide()
        return

    with open(ground_truth_path, "r") as f:
        ground_truth = json.load(f)

    import httpx

    BASE = "http://localhost:8000/api/v1"
    all_precision, all_recall, all_f1 = [], [], []

    for doc in ground_truth:
        sid = doc["session_id"]
        expert_titles = {c["title"].lower().strip() for c in doc["expert_clauses"]}

        # Fetch analysis
        try:
            resp = httpx.post(
                f"{BASE}/analyze",
                headers={"X-Session-ID": sid, "Authorization": f"Bearer {doc.get('token', '')}"},
                params={"analysis_type": "full"},
                timeout=120,
            )
            if resp.status_code != 200:
                print(f"  [SKIP] {doc['document']}: API returned {resp.status_code}")
                continue
            analysis = resp.json()
        except Exception as e:
            print(f"  [SKIP] {doc['document']}: {e}")
            continue

        detected_titles = {c["clause_title"].lower().strip() for c in analysis.get("key_clauses", [])}

        # Fuzzy matching: a clause is "matched" if any expert clause is a substring or vice versa
        matched = 0
        for det in detected_titles:
            for exp in expert_titles:
                if exp in det or det in exp or _jaccard_words(det, exp) > 0.5:
                    matched += 1
                    break

        precision = matched / max(len(detected_titles), 1)
        recall = matched / max(len(expert_titles), 1)
        f1 = 2 * precision * recall / max(precision + recall, 1e-9)

        all_precision.append(precision)
        all_recall.append(recall)
        all_f1.append(f1)

        print(f"  {doc['document']}: P={precision:.3f}  R={recall:.3f}  F1={f1:.3f}  "
              f"(detected={len(detected_titles)}, expert={len(expert_titles)}, matched={matched})")

    if all_f1:
        avg_p = sum(all_precision) / len(all_precision)
        avg_r = sum(all_recall) / len(all_recall)
        avg_f1 = sum(all_f1) / len(all_f1)
        print(f"\n  [CLAUSE AVERAGE] P={avg_p:.3f}  R={avg_r:.3f}  F1={avg_f1:.3f}  (n={len(all_f1)})")
        return {"avg_precision": avg_p, "avg_recall": avg_r, "avg_f1": avg_f1, "n": len(all_f1)}


def _jaccard_words(a: str, b: str) -> float:
    """Word-level Jaccard similarity."""
    wa = set(a.split())
    wb = set(b.split())
    intersection = wa & wb
    union = wa | wb
    return len(intersection) / max(len(union), 1)


def _print_clause_manual_guide():
    print("""
  HOW TO PREPARE CLAUSE GROUND TRUTH:
  ────────────────────────────────────
  1. Upload 5-10 documents to Legal Assist, note the session_id for each
  2. Have a legal expert annotate key clauses in each document
  3. Save as JSON array in evaluation/data/clause_ground_truth.json:
     [
       {
         "document": "lease_agreement_1.pdf",
         "session_id": "abc-123-...",
         "token": "Bearer JWT_TOKEN_HERE",
         "expert_clauses": [
           {"title": "Rent Payment", "importance": "critical"},
           {"title": "Security Deposit", "importance": "important"},
           ...
         ]
       }
     ]
  4. Run: python -m evaluation.measure_all --clauses

  INTERPRETING RESULTS:
  ─────────────────────
  F1 Score:
    > 0.80 = Excellent clause detection
    > 0.60 = Good
    > 0.40 = Moderate — may miss some clauses
    < 0.40 = Poor — check analysis prompt
""")


# ═══════════════════════════════════════════════════════════════
#  METRIC 3: Response Relevance (RAG Quality)
# ═══════════════════════════════════════════════════════════════

def measure_rag_quality(ground_truth_path: str = "evaluation/data/rag_ground_truth.json"):
    """
    Evaluates chat responses against expert reference answers.

    Ground truth format (rag_ground_truth.json):
    [
      {
        "session_id": "...",
        "token": "Bearer ...",
        "questions": [
          {
            "question": "What is the notice period for termination?",
            "reference_answer": "The notice period is 30 days as per Clause 12.",
            "expected_source_section": "Termination Clause"
          }
        ]
      }
    ]

    Metrics:
      - BERTScore (F1): Semantic similarity between generated and reference answer
      - Retrieval Hit Rate: % of queries where the correct source section was retrieved
      - Answer Relevance (LLM-as-judge): Use Gemini to rate answer quality 1-5
    """
    if not os.path.exists(ground_truth_path):
        print(f"\n[RAG] Create: {ground_truth_path}")
        _print_rag_manual_guide()
        return

    with open(ground_truth_path, "r") as f:
        ground_truth = json.load(f)

    import httpx

    # Try to import BERTScore
    try:
        from bert_score import score as bert_score
        has_bertscore = True
    except ImportError:
        print("  [WARN] Install bert-score for semantic similarity: pip install bert-score")
        has_bertscore = False

    BASE = "http://localhost:8000/api/v1"
    all_bertscore = []
    retrieval_hits = 0
    retrieval_total = 0
    all_ratings = []

    for doc in ground_truth:
        sid = doc["session_id"]
        token = doc.get("token", "")

        for qa in doc["questions"]:
            question = qa["question"]
            reference = qa["reference_answer"]
            expected_section = qa.get("expected_source_section", "").lower()

            # Call chat endpoint
            try:
                resp = httpx.post(
                    f"{BASE}/chat",
                    headers={"X-Session-ID": sid, "Authorization": f"Bearer {token}"},
                    json={"message": question, "history": []},
                    timeout=120,
                )
                if resp.status_code != 200:
                    print(f"  [SKIP] {question[:50]}...: status {resp.status_code}")
                    continue
                result = resp.json()
            except Exception as e:
                print(f"  [SKIP] {question[:50]}...: {e}")
                continue

            generated = result.get("response", "")
            sources = result.get("source_sections", [])

            # BERTScore
            if has_bertscore:
                P, R, F1 = bert_score(
                    [generated], [reference],
                    lang="en", verbose=False,
                    model_type="microsoft/deberta-xlarge-mnli"
                )
                bs_f1 = F1.item()
                all_bertscore.append(bs_f1)
            else:
                bs_f1 = None

            # Retrieval hit rate
            retrieval_total += 1
            hit = False
            if expected_section and sources:
                for src in sources:
                    if expected_section in src.get("title", "").lower():
                        hit = True
                        break
            if hit:
                retrieval_hits += 1

            # Simple relevance rating (keyword overlap as proxy if no LLM judge)
            ref_words = set(reference.lower().split())
            gen_words = set(generated.lower().split())
            overlap = len(ref_words & gen_words) / max(len(ref_words), 1)

            print(f"  Q: {question[:60]}...")
            print(f"    BERTScore={bs_f1:.3f if bs_f1 else 'N/A'}  "
                  f"Retrieval={'HIT' if hit else 'MISS'}  "
                  f"WordOverlap={overlap:.3f}")

    # Summary
    print("\n  [RAG QUALITY SUMMARY]")
    if all_bertscore:
        avg_bs = sum(all_bertscore) / len(all_bertscore)
        print(f"    Avg BERTScore F1: {avg_bs:.4f}")
    if retrieval_total:
        hit_rate = retrieval_hits / retrieval_total
        print(f"    Retrieval Hit Rate: {hit_rate:.3f} ({retrieval_hits}/{retrieval_total})")

    return {
        "avg_bertscore": sum(all_bertscore) / len(all_bertscore) if all_bertscore else None,
        "retrieval_hit_rate": retrieval_hits / max(retrieval_total, 1),
        "n_queries": retrieval_total,
    }


def _print_rag_manual_guide():
    print("""
  HOW TO PREPARE RAG GROUND TRUTH:
  ────────────────────────────────
  1. Upload documents and note session_id + JWT token
  2. Prepare 5-10 questions PER DOCUMENT with expert-written reference answers
  3. Note which section of the document contains the answer
  4. Save as evaluation/data/rag_ground_truth.json:
     [
       {
         "session_id": "abc-123",
         "token": "eyJhbG...",
         "questions": [
           {
             "question": "What is the security deposit amount?",
             "reference_answer": "The security deposit is Rs. 2,00,000 as per Clause 4.1 on Page 3.",
             "expected_source_section": "Security Deposit"
           }
         ]
       }
     ]
  5. Run: python -m evaluation.measure_all --rag

  INTERPRETING RESULTS:
  ─────────────────────
  BERTScore F1:
    > 0.90 = Excellent (responses are semantically very similar to reference)
    > 0.80 = Good
    > 0.70 = Acceptable
    < 0.70 = Check retrieval or prompt quality

  Retrieval Hit Rate:
    > 0.80 = Correct sections retrieved most of the time
    > 0.60 = Decent retrieval
    < 0.60 = BM25/HTOC may need tuning
""")


# ═══════════════════════════════════════════════════════════════
#  METRIC 4: Latency
# ═══════════════════════════════════════════════════════════════

def measure_latency(test_pdf: str = "evaluation/data/sample.pdf", token: str = ""):
    """
    Measures end-to-end latency for the 3 main operations.

    Metrics:
      - Upload latency: time to upload + parse + anonymize (excludes background HTOC)
      - Analysis latency: time to generate full analysis
      - Chat latency: time to get a chat response (first token for streaming)

    Just provide a sample PDF and a valid JWT token.
    """
    import httpx

    BASE = "http://localhost:8000/api/v1"

    if not os.path.exists(test_pdf):
        print(f"\n[LATENCY] Put a sample PDF at: {test_pdf}")
        print("  Also pass --token YOUR_JWT_TOKEN")
        _print_latency_guide()
        return

    headers = {"Authorization": f"Bearer {token}"} if token else {}
    results = {}

    # ── 1. Upload Latency ──
    print("\n  [1/3] Measuring UPLOAD latency...")
    with open(test_pdf, "rb") as f:
        pdf_bytes = f.read()

    file_size_mb = len(pdf_bytes) / 1024 / 1024

    t0 = time.perf_counter()
    resp = httpx.post(
        f"{BASE}/documents/upload",
        headers=headers,
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
        data={"doc_type": "digital"},
        timeout=120,
    )
    upload_time = time.perf_counter() - t0

    if resp.status_code != 200:
        print(f"    Upload failed: {resp.status_code} {resp.text[:200]}")
        return

    upload_data = resp.json()
    session_id = upload_data["session_id"]
    page_count = upload_data.get("page_count", "?")
    results["upload_ms"] = round(upload_time * 1000)
    print(f"    Upload: {results['upload_ms']}ms  ({file_size_mb:.1f}MB, {page_count} pages)")

    # Wait for HTOC to be ready
    print("    Waiting for HTOC/BM25 to build...", end="", flush=True)
    for _ in range(60):
        time.sleep(2)
        status_resp = httpx.get(
            f"{BASE}/documents/htoc-status",
            headers={**headers, "X-Session-ID": session_id},
            timeout=10,
        )
        if status_resp.status_code == 200:
            status = status_resp.json()
            if status.get("status") == "ready":
                print(" ready!")
                break
    else:
        print(" timeout (using whatever is available)")

    # ── 2. Analysis Latency ──
    print("  [2/3] Measuring ANALYSIS latency...")
    t0 = time.perf_counter()
    resp = httpx.post(
        f"{BASE}/analyze",
        headers={**headers, "X-Session-ID": session_id},
        params={"analysis_type": "full"},
        timeout=180,
    )
    analysis_time = time.perf_counter() - t0
    results["analysis_ms"] = round(analysis_time * 1000)

    if resp.status_code == 200:
        analysis = resp.json()
        n_clauses = len(analysis.get("key_clauses", []))
        n_risks = len(analysis.get("risks", []))
        print(f"    Analysis: {results['analysis_ms']}ms  "
              f"(clauses={n_clauses}, risks={n_risks}, score={analysis.get('overall_risk_score')})")
    else:
        print(f"    Analysis failed: {resp.status_code}")

    # ── 2b. Cached analysis latency ──
    t0 = time.perf_counter()
    resp2 = httpx.post(
        f"{BASE}/analyze",
        headers={**headers, "X-Session-ID": session_id},
        params={"analysis_type": "full"},
        timeout=30,
    )
    cached_time = time.perf_counter() - t0
    results["analysis_cached_ms"] = round(cached_time * 1000)
    print(f"    Analysis (cached): {results['analysis_cached_ms']}ms")

    # ── 3. Chat Latency ──
    print("  [3/3] Measuring CHAT latency...")
    questions = [
        "What are the key risks in this document?",
        "Who are the parties involved?",
        "What is the termination clause?",
    ]

    chat_times = []
    for q in questions:
        t0 = time.perf_counter()
        resp = httpx.post(
            f"{BASE}/chat",
            headers={**headers, "X-Session-ID": session_id},
            json={"message": q, "history": []},
            timeout=120,
        )
        chat_time = time.perf_counter() - t0
        chat_times.append(round(chat_time * 1000))

        if resp.status_code == 200:
            answer_len = len(resp.json().get("response", ""))
            sources = len(resp.json().get("source_sections", []) or [])
            print(f"    Chat: {chat_times[-1]}ms  Q=\"{q[:40]}...\"  "
                  f"(answer={answer_len} chars, sources={sources})")
        else:
            print(f"    Chat failed: {resp.status_code}")

    results["chat_avg_ms"] = round(sum(chat_times) / len(chat_times)) if chat_times else 0
    results["chat_times_ms"] = chat_times

    # ── Summary ──
    print(f"""
  ┌─────────────────────────────────────────────┐
  │           LATENCY SUMMARY                   │
  ├─────────────────────────────────────────────┤
  │  Upload (parse+PII):    {results['upload_ms']:>6}ms            │
  │  Analysis (fresh):      {results['analysis_ms']:>6}ms            │
  │  Analysis (cached):     {results['analysis_cached_ms']:>6}ms            │
  │  Chat (avg):            {results['chat_avg_ms']:>6}ms            │
  │  Document: {file_size_mb:.1f}MB, {page_count} pages              │
  └─────────────────────────────────────────────┘
""")
    return results


def _print_latency_guide():
    print("""
  HOW TO RUN LATENCY TESTS:
  ─────────────────────────
  1. Start the backend: uvicorn app.main:app --reload
  2. Place a test PDF at evaluation/data/sample.pdf
  3. Get a JWT token by logging in
  4. Run: python -m evaluation.measure_all --latency --token YOUR_TOKEN

  INTERPRETING RESULTS:
  ─────────────────────
  Upload (digital PDF):
    < 2000ms = Good (most time is PII detection)
    < 5000ms = Acceptable for large docs

  Analysis:
    < 15000ms = Good (single Gemini call)
    < 30000ms = Acceptable (complex document)
    Cached should be < 100ms

  Chat:
    < 5000ms = Good (BM25 hit + Gemini)
    < 10000ms = Acceptable (LLM tree search fallback)
    < 2000ms = Excellent (cache hit)
""")


# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Legal Assist Evaluation Suite")
    parser.add_argument("--all", action="store_true", help="Run all metrics")
    parser.add_argument("--ocr", action="store_true", help="OCR accuracy (CER, WER)")
    parser.add_argument("--clauses", action="store_true", help="Clause detection (P, R, F1)")
    parser.add_argument("--rag", action="store_true", help="RAG quality (BERTScore, hit rate)")
    parser.add_argument("--latency", action="store_true", help="Latency benchmarks")
    parser.add_argument("--token", type=str, default="", help="JWT token for API auth")
    parser.add_argument("--pdf", type=str, default="evaluation/data/sample.pdf", help="Test PDF for latency")
    args = parser.parse_args()

    if not any([args.all, args.ocr, args.clauses, args.rag, args.latency]):
        parser.print_help()
        print("\n  Example: python -m evaluation.measure_all --latency --token eyJ...")
        sys.exit(0)

    all_results = {}

    if args.all or args.ocr:
        print("\n" + "=" * 60)
        print("  METRIC 1: OCR Accuracy (CER, WER)")
        print("=" * 60)
        all_results["ocr"] = measure_ocr_accuracy()

    if args.all or args.clauses:
        print("\n" + "=" * 60)
        print("  METRIC 2: Clause Detection Precision")
        print("=" * 60)
        all_results["clauses"] = measure_clause_detection()

    if args.all or args.rag:
        print("\n" + "=" * 60)
        print("  METRIC 3: Response Relevance (RAG Quality)")
        print("=" * 60)
        all_results["rag"] = measure_rag_quality()

    if args.all or args.latency:
        print("\n" + "=" * 60)
        print("  METRIC 4: Latency")
        print("=" * 60)
        all_results["latency"] = measure_latency(test_pdf=args.pdf, token=args.token)

    # Save results
    out_path = "evaluation/results.json"
    os.makedirs("evaluation", exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n  Results saved to {out_path}")
