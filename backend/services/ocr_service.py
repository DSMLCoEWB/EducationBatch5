import os
import pdfplumber
import pandas as pd
from docx import Document
from google.genai import Client, types
from ai_utils import generate_content_with_fallback
from config import ATTACHMENTS_DIR
from core.logging import get_logger

logger = get_logger("services.ocr")

def extract_text_from_attachment_ai(path: str) -> str:
    """Uses Gemini Vision to extract text from images and scanned PDFs via fallback-safe generation."""
    try:
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            return ""

        client = Client(api_key=api_key)
        
        with open(path, "rb") as f:
            file_data = f.read()

        mime_type = "image/jpeg"
        if path.lower().endswith(".pdf"):
            mime_type = "application/pdf"
        elif path.lower().endswith(".png"):
            mime_type = "image/png"

        contents = [
            types.Part.from_bytes(data=file_data, mime_type=mime_type),
            "Extract all legible text from this document for archival purposes. "
            "If it is an official document, preserve core facts like names, dates, and status."
        ]

        response = generate_content_with_fallback(
            client=client,
            contents=contents,
            label="OCR Service"
        )

        if response and response.text:
            return f"\n--- [Extracted from Attachment: {os.path.basename(path)}] ---\n{response.text}\n"
    except Exception as e:
        logger.error(f"⚠️ AI OCR failed for {path}: {e}")
    return ""

def extract_attachment_text(path: str) -> str:
    """Entry point for text extraction. Routes by file type with AI fallback for visuals."""
    if not os.path.exists(path):
        return ""
        
    try:
        ext = path.lower()
        if ext.endswith(".pdf"):
            try:
                with pdfplumber.open(path) as pdf:
                    # Increase depth to 20 pages for policy context and multi-page attachments
                    text = " ".join((page.extract_text() or "") for page in pdf.pages[:20]).strip()
                    if text:
                        return text
            except Exception as e:
                logger.debug(f"pdfplumber failed for {path}: {e}")
            # Fallback to AI OCR for scanned PDFs
            return extract_text_from_attachment_ai(path)

        if ext.endswith(".docx"):
            try:
                doc = Document(path)
                return " ".join(p.text for p in doc.paragraphs)
            except Exception:
                return ""

        if ext.endswith(".xlsx"):
            try:
                df = pd.read_excel(path)
                return df.astype(str).head(10).to_string()
            except Exception:
                return ""

        if ext.endswith(".txt"):
            try:
                with open(path, "r", errors="ignore") as f:
                    return f.read()
            except Exception:
                return ""

        # Image direct AI OCR
        if ext.endswith((".png", ".jpg", ".jpeg")):
            return extract_text_from_attachment_ai(path)

    except Exception as e:
        logger.error(f"⚠️ Failed to extract attachment: {path} - {e}")

    return ""
