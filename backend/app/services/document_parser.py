import pymupdf  # PyMuPDF — reads electronic PDFs, renders pages to images
import docx
from fastapi import HTTPException
import io
import logging
import asyncio
import numpy as np
from concurrent.futures import ThreadPoolExecutor
import os

logger = logging.getLogger(__name__)

# EasyOCR — fully local, supports 80+ languages including Hindi, Tamil, etc.
# Lazy-loaded to avoid memory spike at startup (~200MB)
_ocr_reader = None

def _get_reader(langs: list[str]):
    """Lazy-load EasyOCR reader on first use."""
    global _ocr_reader
    current_langs = getattr(_ocr_reader, '_langs', None)
    if _ocr_reader is None or current_langs != langs:
        import easyocr
        _ocr_reader = easyocr.Reader(langs, gpu=False)
        _ocr_reader._langs = langs
        logger.info("EasyOCR loaded (langs=%s)", langs)
    return _ocr_reader


# Map frontend language codes to EasyOCR language keys
_LANG_MAP = {
    "en-IN": ["en"],
    "hi-IN": ["hi", "en"],      # Hindi + English (most Indian docs are bilingual)
    "ta-IN": ["ta", "en"],
    "te-IN": ["te", "en"],
    "kn-IN": ["kn", "en"],
    "ml-IN": ["ml", "en"],
    "bn-IN": ["bn", "en"],
    "gu-IN": ["gu", "en"],
    "mr-IN": ["mr", "en"],
    "pa-IN": ["pa", "en"],
    "ur-IN": ["ur", "en"],
    "as-IN": ["as", "en"],      # Assamese
    "ne-IN": ["ne", "en"],      # Nepali
}

# OCR optimization constants
MAX_IMG_WIDTH = 1024        # Cap image width — legal fonts are readable at this size
MIN_PAGE_VARIANCE = 500     # Skip near-blank pages (low pixel variance = mostly white)
DIGITAL_TEXT_THRESHOLD = 50 # If PyMuPDF extracts >50 chars, skip OCR for that page (English only)


class DocumentParser:
    def __init__(self):
        self._page_count = 0
        self._needs_ocr = False
        self._page_texts: list = []

    async def extract_async(self, content: bytes, content_type: str, doc_type: str = "digital", ocr_language: str = "en-IN", ocr_mode: str = "fast", gemini_client=None) -> str:
        """
        Extract text from documents.
        - doc_type="digital": PyMuPDF direct text extraction
        - doc_type="scanned" + ocr_mode="fast": Gemini Vision OCR (API-based, lightweight)
        - doc_type="scanned" + ocr_mode="secure": EasyOCR (local, no API calls, multi-language)
        """
        self._needs_ocr = False
        self._page_texts = []

        if content_type == "application/pdf":
            if doc_type == "scanned":
                if ocr_mode == "fast" and gemini_client:
                    return await self._extract_pdf_gemini_vision(content, ocr_language, gemini_client)
                else:
                    return await self._extract_pdf_scanned(content, ocr_language)
            else:
                return self._extract_pdf_digital(content)
        elif content_type in [
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
        ]:
            return self._extract_docx(content)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type")

    # Language hint mapping for Gemini Vision
    _VISION_LANG_MAP = {
        "en-IN": "English", "hi-IN": "Hindi and English", "mr-IN": "Marathi and English",
        "bn-IN": "Bengali and English", "ta-IN": "Tamil and English", "te-IN": "Telugu and English",
        "gu-IN": "Gujarati and English", "kn-IN": "Kannada and English", "ml-IN": "Malayalam and English",
        "pa-IN": "Punjabi and English", "ur-IN": "Urdu and English", "as-IN": "Assamese and English",
        "ne-IN": "Nepali and English",
    }

    async def _extract_pdf_gemini_vision(self, content: bytes, ocr_language: str, gemini_client) -> str:
        """Extract text from scanned PDF using Gemini Vision API (fast, parallel, API-based)."""
        self._needs_ocr = True
        lang_hint = self._VISION_LANG_MAP.get(ocr_language, "English")

        # Step 1: Render all pages, separate digital vs needs-OCR
        digital_texts = {}   # page_idx -> text
        ocr_tasks = {}       # page_idx -> image_bytes

        with pymupdf.open(stream=content, filetype="pdf") as doc:
            self._page_count = len(doc)
            for i, page in enumerate(doc):
                digital_text = page.get_text().strip()
                if len(digital_text) >= DIGITAL_TEXT_THRESHOLD:
                    digital_texts[i] = digital_text
                    continue
                try:
                    pix = page.get_pixmap(dpi=150)
                    ocr_tasks[i] = pix.tobytes("png")
                except Exception as e:
                    logger.warning("Render failed for page %d: %s", i + 1, e)
                    digital_texts[i] = f"[Render failed for page {i + 1}]"

        # Step 2: OCR all pages in parallel (batch of concurrent Gemini calls)
        ocr_results = {}
        if ocr_tasks:
            BATCH_SIZE = 5  # avoid hammering rate limits

            async def _ocr_one(idx: int, img_bytes: bytes) -> tuple:
                try:
                    text = await gemini_client.ocr_page_image(img_bytes, lang_hint)
                    logger.info("Gemini Vision OCR page %d/%d — %d chars", idx + 1, self._page_count, len(text))
                    return idx, text
                except Exception as e:
                    logger.warning("Gemini Vision OCR failed for page %d: %s", idx + 1, e)
                    return idx, f"[OCR failed for page {idx + 1}]"

            items = list(ocr_tasks.items())
            for batch_start in range(0, len(items), BATCH_SIZE):
                batch = items[batch_start:batch_start + BATCH_SIZE]
                results = await asyncio.gather(*[_ocr_one(idx, img) for idx, img in batch])
                for idx, text in results:
                    ocr_results[idx] = text

        # Step 3: Merge in page order
        page_texts = []
        for i in range(self._page_count):
            if i in digital_texts:
                page_texts.append(digital_texts[i])
            elif i in ocr_results:
                page_texts.append(ocr_results[i])
            else:
                page_texts.append("")

        self._page_texts = page_texts
        full_text = "\n\n".join(t for t in page_texts if t)
        if not full_text.strip():
            raise HTTPException(500, "OCR returned no text. The document may be empty or unreadable.")

        logger.info("Gemini Vision OCR done — %d pages (%d digital, %d OCR'd), %d total chars",
                     self._page_count, len(digital_texts), len(ocr_results), len(full_text))
        return full_text

    def _extract_pdf_digital(self, content: bytes) -> str:
        """Extract text from electronic PDF using PyMuPDF."""
        with pymupdf.open(stream=content, filetype="pdf") as doc:
            self._page_count = len(doc)
            all_text = []
            for page in doc:
                page_text = page.get_text().strip()
                all_text.append(page_text if page_text else "")

        self._page_texts = all_text
        return "\n\n".join(t for t in all_text if t)

    async def _extract_pdf_scanned(self, content: bytes, ocr_language: str = "en-IN") -> str:
        """Extract text from scanned PDF using EasyOCR (fully local).
        Optimizations:
          1. For English-only: try digital text first — skip OCR for pages with extractable text
          2. For non-English: ALWAYS OCR (PyMuPDF extracts garbled text from scanned Indic scripts)
          3. Skip near-blank pages (low pixel variance)
          4. Downscale images to max 1024px width
          5. Parallel OCR across CPU cores
        """
        self._needs_ocr = True

        langs = _LANG_MAP.get(ocr_language, ["en"])
        is_english_only = langs == ["en"]

        # Step 1: Try digital extraction (English only) + render pages that need OCR
        pages_needing_ocr = []
        digital_texts = {}  # page_idx -> text (from PyMuPDF)
        skipped_blank = 0

        with pymupdf.open(stream=content, filetype="pdf") as doc:
            self._page_count = len(doc)
            for i, page in enumerate(doc):
                # For English-only: try digital text extraction first
                # For non-English: SKIP — PyMuPDF extracts garbled text from scanned Indic scripts
                if is_english_only:
                    digital_text = page.get_text().strip()
                    if len(digital_text) >= DIGITAL_TEXT_THRESHOLD:
                        digital_texts[i] = digital_text
                        continue

                # Render to image for OCR
                try:
                    pix = page.get_pixmap(dpi=100, colorspace=pymupdf.csGRAY)
                    img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                        pix.height, pix.width
                    )

                    # Skip near-blank pages
                    if np.var(img_array) < MIN_PAGE_VARIANCE:
                        skipped_blank += 1
                        digital_texts[i] = ""
                        continue

                    # Downscale if wider than MAX_IMG_WIDTH
                    if img_array.shape[1] > MAX_IMG_WIDTH:
                        scale = MAX_IMG_WIDTH / img_array.shape[1]
                        new_h = int(img_array.shape[0] * scale)
                        # Fast nearest-neighbor resize without PIL/cv2
                        row_idx = (np.arange(new_h) / scale).astype(int)
                        col_idx = (np.arange(MAX_IMG_WIDTH) / scale).astype(int)
                        img_array = img_array[row_idx][:, col_idx]

                    pages_needing_ocr.append((i, img_array))
                except Exception as e:
                    logger.warning("Render failed for page %d: %s", i + 1, e)
                    digital_texts[i] = f"[Render failed for page {i + 1}]"

        logger.info(
            "OCR prep — %d pages total, %d digital (skipped), %d blank (skipped), %d need OCR",
            self._page_count, len(digital_texts), skipped_blank, len(pages_needing_ocr)
        )

        # Step 2: OCR only the pages that need it
        ocr_results = {}
        if pages_needing_ocr:
            reader = _get_reader(langs)
            max_workers = min(len(pages_needing_ocr), max(1, os.cpu_count() or 2))

            def _ocr_page(args):
                idx, img = args
                try:
                    kwargs = {"detail": 0, "paragraph": True}
                    # Allowlist for English — fewer candidates = faster recognition
                    if is_english_only:
                        kwargs["allowlist"] = (
                            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
                            "0123456789.,;:!?'\"-()[]{}/@#$%&*+=<> \n₹"
                        )
                    result = reader.readtext(img, **kwargs)
                    text = "\n".join(result) if result else ""
                    return idx, text
                except Exception as e:
                    logger.warning("OCR failed for page %d: %s", idx + 1, e)
                    return idx, f"[OCR failed for page {idx + 1}]"

            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                lambda: list(ThreadPoolExecutor(max_workers=max_workers).map(_ocr_page, pages_needing_ocr))
            )
            for idx, text in results:
                ocr_results[idx] = text

        # Step 3: Merge digital + OCR results in page order
        page_texts = []
        for i in range(self._page_count):
            if i in digital_texts:
                page_texts.append(digital_texts[i])
            elif i in ocr_results:
                page_texts.append(ocr_results[i])
            else:
                page_texts.append("")

        self._page_texts = page_texts

        ocr_count = len(pages_needing_ocr)
        total_chars = sum(len(t) for t in page_texts)
        logger.info("OCR completed — %d pages, %d OCR'd, %d skipped, %d total chars",
                     self._page_count, ocr_count, len(digital_texts), total_chars)

        full_text = "\n\n".join(t for t in page_texts if t)
        if not full_text.strip():
            raise HTTPException(500, "OCR returned no text. The document may be empty or unreadable.")

        return full_text

    def _extract_docx(self, content: bytes) -> str:
        doc = docx.Document(io.BytesIO(content))
        paragraphs = [para.text for para in doc.paragraphs]
        self._page_texts = self._chunk_paragraphs(paragraphs, chars_per_page=3000)
        self._page_count = max(len(self._page_texts), 1)
        return "\n".join(paragraphs)

    def _chunk_paragraphs(self, paragraphs: list, chars_per_page: int = 3000) -> list:
        pages = []
        current_page = []
        current_len = 0
        for para in paragraphs:
            current_page.append(para)
            current_len += len(para) + 1
            if current_len >= chars_per_page:
                pages.append("\n".join(current_page))
                current_page = []
                current_len = 0
        if current_page:
            pages.append("\n".join(current_page))
        return pages if pages else [""]

    @property
    def page_count(self) -> int:
        return self._page_count

    @property
    def needs_ocr(self) -> bool:
        return self._needs_ocr

    @property
    def page_texts(self) -> list:
        return self._page_texts
