import fitz  # PyMuPDF
import docx
from fastapi import HTTPException
import io

class DocumentParser:
    def __init__(self):
        self._page_count = 0

    def extract(self, content: bytes, content_type: str) -> str:
        if content_type == "application/pdf":
            return self._extract_pdf(content)
        elif content_type in ["application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/msword"]:
            return self._extract_docx(content)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type")

    def _extract_pdf(self, content: bytes) -> str:
        with fitz.open(stream=content, filetype="pdf") as doc:
            self._page_count = len(doc)
            text = ""
            for page in doc:
                text += page.get_text()
            return text

    def _extract_docx(self, content: bytes) -> str:
        doc = docx.Document(io.BytesIO(content))
        # DOCX doesn't have strict pages, but we can estimate or just set to 1 if needed.
        # Or count paragraphs/sections.
        # For now, let's just count paragraphs as a proxy or set to 1.
        self._page_count = len(doc.paragraphs) # rough proxy
        text = "\n".join([para.text for para in doc.paragraphs])
        return text

    @property
    def page_count(self) -> int:
        return self._page_count
