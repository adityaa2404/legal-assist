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
}


class DocumentParser:
    def __init__(self):
        self._page_count = 0
        self._needs_ocr = False
        self._page_texts: list = []

    async def extract_async(self, content: bytes, content_type: str, doc_type: str = "digital", ocr_language: str = "en-IN") -> str:
        """
        Extract text from documents.
        - doc_type="digital": PyMuPDF direct text extraction
        - doc_type="scanned": EasyOCR (local, no API calls, multi-language)
        """
        self._needs_ocr = False
        self._page_texts = []

        if content_type == "application/pdf":
            if doc_type == "scanned":
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
        Optimized: 150 DPI grayscale + parallel page OCR across CPU cores."""
        self._needs_ocr = True

        langs = _LANG_MAP.get(ocr_language, ["en"])
        reader = _get_reader(langs)

        # Step 1: Render all pages to grayscale images (fast, ~50ms/page)
        page_images = []
        with pymupdf.open(stream=content, filetype="pdf") as doc:
            self._page_count = len(doc)
            for i, page in enumerate(doc):
                try:
                    pix = page.get_pixmap(dpi=150, colorspace=pymupdf.csGRAY)
                    img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                        pix.height, pix.width
                    )
                    page_images.append((i, img_array))
                except Exception as e:
                    logger.warning("Render failed for page %d: %s", i + 1, e)
                    page_images.append((i, None))

        # Step 2: OCR all pages in parallel using thread pool
        max_workers = min(len(page_images), max(1, os.cpu_count() or 2))

        def _ocr_page(args):
            idx, img = args
            if img is None:
                return idx, f"[Render failed for page {idx + 1}]"
            try:
                result = reader.readtext(img, detail=0, paragraph=True)
                text = "\n".join(result) if result else ""
                logger.debug("Page %d: %d chars extracted", idx + 1, len(text))
                return idx, text
            except Exception as e:
                logger.warning("OCR failed for page %d: %s", idx + 1, e)
                return idx, f"[OCR failed for page {idx + 1}]"

        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            lambda: list(ThreadPoolExecutor(max_workers=max_workers).map(_ocr_page, page_images))
        )

        # Sort by page index and collect texts
        results.sort(key=lambda x: x[0])
        page_texts = [text for _, text in results]

        self._page_texts = page_texts
        logger.info("EasyOCR completed — %d pages, %d total chars, %d workers",
                     len(page_texts), sum(len(t) for t in page_texts), max_workers)

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
