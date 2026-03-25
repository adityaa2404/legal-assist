import pymupdf  # PyMuPDF — reads electronic PDFs in any language natively
import docx
from fastapi import HTTPException
import io
import logging
import asyncio
import numpy as np

logger = logging.getLogger(__name__)

# PaddleOCR — fully local, no API calls
# Lazy-loaded to avoid 400MB memory spike at startup
_ocr_engine = None

def _get_ocr(lang: str = "en"):
    """Lazy-load PaddleOCR engine on first use."""
    global _ocr_engine
    if _ocr_engine is None or getattr(_ocr_engine, '_lang', 'en') != lang:
        try:
            import os
            os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
            from paddleocr import PaddleOCR
            _ocr_engine = PaddleOCR(use_angle_cls=True, lang=lang)
            _ocr_engine._lang = lang  # track current lang
            logger.info("PaddleOCR loaded (lang=%s)", lang)
        except ImportError:
            raise RuntimeError("PaddleOCR not installed. Run: pip install paddleocr paddlepaddle")
    return _ocr_engine


class DocumentParser:
    def __init__(self):
        self._page_count = 0
        self._needs_ocr = False
        self._page_texts: list = []

    async def extract_async(self, content: bytes, content_type: str, doc_type: str = "digital", ocr_language: str = "en-IN") -> str:
        """
        Extract text from documents.
        - doc_type="digital": PyMuPDF (fast, any language)
        - doc_type="scanned": PaddleOCR (local, no API calls)
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
        """Extract text from electronic PDF using PyMuPDF — works for any language."""
        with pymupdf.open(stream=content, filetype="pdf") as doc:
            self._page_count = len(doc)
            all_text = []
            for page in doc:
                page_text = page.get_text().strip()
                all_text.append(page_text if page_text else "")

        self._page_texts = all_text
        return "\n\n".join(t for t in all_text if t)

    async def _extract_pdf_scanned(self, content: bytes, ocr_language: str = "en-IN") -> str:
        """Extract text from scanned PDF using PaddleOCR (fully local, no API calls)."""
        if not _ocr_engine:
            raise HTTPException(500, "PaddleOCR not installed. Run: pip install paddleocr paddlepaddle")

        self._needs_ocr = True

        # Map language codes to PaddleOCR lang keys
        lang_map = {
            "en-IN": "en", "hi-IN": "hi", "ta-IN": "ta", "te-IN": "te",
            "kn-IN": "kn", "ml-IN": "ml", "bn-IN": "bn", "gu-IN": "gu",
            "mr-IN": "mr", "pa-IN": "pa", "ur-IN": "ur",
        }
        paddle_lang = lang_map.get(ocr_language, "en")

        # Reload OCR engine if language changed from default
        ocr = _ocr_engine
        if paddle_lang != "en":
            try:
                ocr = PaddleOCR(use_angle_cls=True, lang=paddle_lang, show_log=False)
            except Exception:
                ocr = _ocr_engine  # fall back to English

        # Render pages to images and OCR
        with pymupdf.open(stream=content, filetype="pdf") as doc:
            self._page_count = len(doc)
            page_texts = []

            for i, page in enumerate(doc):
                try:
                    pix = page.get_pixmap(dpi=200)
                    img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                        pix.height, pix.width, pix.n
                    )
                    # RGB only (drop alpha if present)
                    if pix.n == 4:
                        img_array = img_array[:, :, :3]

                    # Run OCR on numpy array
                    result = await asyncio.to_thread(ocr.ocr, img_array, cls=True)

                    # Extract text lines sorted by vertical position
                    lines = []
                    if result and result[0]:
                        for line in result[0]:
                            text = line[1][0] if line[1] else ""
                            if text.strip():
                                lines.append(text.strip())

                    page_text = "\n".join(lines)
                    page_texts.append(page_text)
                except Exception as e:
                    logger.warning("OCR failed for page %d: %s", i + 1, e)
                    page_texts.append(f"[OCR failed for page {i + 1}]")

        self._page_texts = page_texts
        logger.info("PaddleOCR completed — %d pages", len(page_texts))

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
