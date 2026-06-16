import os
import pdfplumber
import pandas as pd
from docx import Document
from google.genai import types
from services.ai_utils import generate_content_with_fallback, get_genai_client
from config import ATTACHMENTS_DIR
from core.logging import get_logger

logger = get_logger("services.ocr")

def extract_text_from_attachment_ai(path: str) -> str:
    """Uses Gemini Vision to extract text from images and scanned PDFs via fallback-safe generation."""
    try:
        from config import GEMINI_API_KEY
        client = get_genai_client(api_key=GEMINI_API_KEY)
        if not client:
            return ""
        
        with open(path, "rb") as f:
            file_data = f.read()

        contents = []
        mime_type = "image/jpeg"
        if path.lower().endswith(".pdf"):
            mime_type = "application/pdf"
            
            # Ollama Vision models cannot ingest PDFs natively. Convert to images.
            from config import AI_PREFER_LOCAL
            if AI_PREFER_LOCAL:
                try:
                    import pdfplumber
                    import io
                    with pdfplumber.open(path) as pdf:
                        # Process up to 5 pages (to prevent OOM on local GPUs)
                        for page in pdf.pages[:5]:
                            img = page.to_image(resolution=150).original
                            img_byte_arr = io.BytesIO()
                            img.save(img_byte_arr, format='JPEG', quality=85)
                            contents.append(types.Part.from_bytes(data=img_byte_arr.getvalue(), mime_type="image/jpeg"))
                        # We've already added the pages, skip the default single-file addition
                        file_data = None
                except Exception as e:
                    logger.warning(f"⚠️ Failed to convert PDF to images for local OCR: {e}")
                    
        elif path.lower().endswith(".png"):
            mime_type = "image/png"

        if file_data is not None:
            contents.append(types.Part.from_bytes(data=file_data, mime_type=mime_type))
            
        contents.append(
            "Extract all legible text from this document for archival purposes. "
            "If it is an official document, preserve core facts like names, dates, and status."
        )

        from services.ai_utils import generate_content_with_fallback, VISION_FALLBACK_LIST
        
        response = generate_content_with_fallback(
            client=client,
            contents=contents,
            label="OCR Service",
            model_list=VISION_FALLBACK_LIST
        )

        if response:
            try:
                text = response.text
                if text is not None:
                    return text.strip()
            except Exception as e:
                logger.warning(f"⚠️ Response text extraction failed for {path}: {e}")
                
            try:
                parts = []
                if hasattr(response, "candidates") and response.candidates:
                    for cand in response.candidates:
                        if cand.content and cand.content.parts:
                            for part in cand.content.parts:
                                if part.text:
                                    parts.append(part.text)
                if parts:
                    return "".join(parts).strip()
            except Exception as inner_e:
                logger.warning(f"Failed to extract partial text from candidates: {inner_e}")
            return ""
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
