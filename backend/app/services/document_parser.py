import pymupdf  # PyMuPDF — reads electronic PDFs in any language natively
import docx
from fastapi import HTTPException
from app.core.config import settings
import io
import os
import tempfile
import zipfile
import logging
import asyncio

logger = logging.getLogger(__name__)


class DocumentParser:
    def __init__(self):
        self._page_count = 0
        self._needs_ocr = False
        self._page_texts: list = []

    async def extract_async(self, content: bytes, content_type: str, doc_type: str = "digital", ocr_language: str = "en-IN") -> str:
        """
        Extract text from documents.
        - doc_type="digital": PyMuPDF (fast, any language)
        - doc_type="scanned": Sarvam AI Vision (22 Indian languages + English)
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
        """Extract text from scanned PDF using Sarvam AI — 22 Indian languages + English."""
        self._needs_ocr = True

        if not settings.SARVAM_AI_API_KEY:
            raise HTTPException(500, "Sarvam AI API key not configured for scanned document processing")

        # Get page count from PyMuPDF
        with pymupdf.open(stream=content, filetype="pdf") as doc:
            self._page_count = len(doc)

        logger.info("Scanned PDF — sending %d pages to Sarvam AI for OCR", self._page_count)

        page_texts = await self._ocr_with_sarvam(content, ocr_language)

        if not page_texts:
            raise HTTPException(500, "Sarvam AI OCR returned no text. Please check the document.")

        self._page_texts = page_texts
        self._page_count = len(page_texts)
        return "\n\n".join(t for t in page_texts if t)

    async def _ocr_with_sarvam(self, pdf_bytes: bytes, ocr_language: str = "en-IN") -> list:
        """Use Sarvam AI Document Intelligence to OCR a scanned PDF."""
        from sarvamai import SarvamAI

        try:
            client = SarvamAI(api_subscription_key=settings.SARVAM_AI_API_KEY)

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(pdf_bytes)
                tmp_path = tmp.name

            try:
                page_texts = await asyncio.to_thread(
                    self._run_sarvam_job, client, tmp_path, ocr_language
                )
                return page_texts
            finally:
                os.unlink(tmp_path)

        except Exception as e:
            logger.error("Sarvam AI OCR failed: %s", e)
            raise HTTPException(500, "Sarvam AI OCR failed: {}".format(str(e)))

    def _run_sarvam_job(self, client, pdf_path: str, ocr_language: str = "en-IN") -> list:
        """Run Sarvam Document Intelligence job (blocking — called via to_thread)."""
        job = client.document_intelligence.create_job(
            language=ocr_language,
            output_format="md",
        )
        logger.info("Sarvam job created: %s", job.job_id)

        job.upload_file(pdf_path)
        job.start()
        logger.info("Sarvam job started, waiting for completion...")

        status = job.wait_until_complete()
        logger.info("Sarvam job completed: %s", status.job_state)

        if status.job_state.lower() != "completed":
            raise Exception("Sarvam job failed with state: {}".format(status.job_state))

        with tempfile.TemporaryDirectory() as tmpdir:
            output_zip = os.path.join(tmpdir, "output.zip")
            job.download_output(output_zip)

            page_texts = []
            with zipfile.ZipFile(output_zip, "r") as zf:
                md_files = sorted(
                    [f for f in zf.namelist() if f.endswith(".md")]
                )
                # Sarvam may return one .md with --- page breaks,
                # or multiple .md files (one per page)
                all_text = []
                for md_file in md_files:
                    text = zf.read(md_file).decode("utf-8", errors="replace").strip()
                    all_text.append(text)

                combined = "\n\n".join(all_text)

                if len(md_files) > 1:
                    # Multiple files = one per page
                    page_texts = [t.strip() for t in all_text if t.strip()]
                else:
                    # Single file — split on markdown horizontal rule (page break)
                    # Sarvam uses \n---\n between pages
                    import re
                    parts = re.split(r'\n---\n', combined)
                    page_texts = [p.strip() for p in parts if p.strip()]

            logger.info("Sarvam extracted %d pages of text", len(page_texts))
            return page_texts

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
