import pymupdf  # PyMuPDF — reads electronic PDFs in any language natively
import pytesseract
from PIL import Image
import docx
from fastapi import HTTPException
import io
import logging
import asyncio

logger = logging.getLogger(__name__)

# Tesseract language map (Indian languages)
_LANG_MAP = {
    "en-IN": "eng", "hi-IN": "hin", "ta-IN": "tam", "te-IN": "tel",
    "kn-IN": "kan", "ml-IN": "mal", "bn-IN": "ben", "gu-IN": "guj",
    "mr-IN": "mar", "pa-IN": "pan", "ur-IN": "urd",
}


class DocumentParser:
    def __init__(self):
        self._page_count = 0
        self._needs_ocr = False
        self._page_texts: list = []

    async def extract_async(self, content: bytes, content_type: str, doc_type: str = "digital", ocr_language: str = "en-IN") -> str:
        """
        Extract text from documents.
        - doc_type="digital": PyMuPDF (fast, any language)
        - doc_type="scanned": Tesseract OCR (local, no API calls)
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
        """Extract text from scanned PDF using Tesseract OCR (fully local)."""
        self._needs_ocr = True
        tess_lang = _LANG_MAP.get(ocr_language, "eng")

        with pymupdf.open(stream=content, filetype="pdf") as doc:
            self._page_count = len(doc)
            page_texts = []

            for i, page in enumerate(doc):
                try:
                    # Render page to image at 300 DPI for better OCR accuracy
                    pix = page.get_pixmap(dpi=300)
                    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

                    # Run Tesseract in thread to not block event loop
                    text = await asyncio.to_thread(
                        pytesseract.image_to_string, img, lang=tess_lang
                    )
                    page_texts.append(text.strip())
                except Exception as e:
                    logger.warning("OCR failed for page %d: %s", i + 1, e)
                    page_texts.append(f"[OCR failed for page {i + 1}]")

        self._page_texts = page_texts
        logger.info("Tesseract OCR completed — %d pages", len(page_texts))

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
