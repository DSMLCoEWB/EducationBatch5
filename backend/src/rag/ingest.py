import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import faiss
import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from services.rag_service import get_embedder

from config import INDEX_PATH, CHUNKS_PATH

# Chunking parameters
CHUNK_SIZE_TOKENS = 500
OVERLAP_TOKENS = 50



def split_text_into_chunks(text: str, chunk_size: int = CHUNK_SIZE_TOKENS, overlap: int = OVERLAP_TOKENS) -> List[str]:
    """
    Split text into chunks of approximately chunk_size tokens with overlap.
    Preserves Markdown tables as single blocks and injects headers across split tables.
    """
    if not text or not text.strip():
        return []
    
    chunks = []
    current_chunk_items = []  # List of tuples: (type, text)
    current_tokens = 0
    
    blocks = re.split(r"\n\n+", text.strip())
    
    def finalize_chunk():
        nonlocal current_chunk_items, current_tokens, chunks
        if current_chunk_items:
            chunk_str = ""
            for item_type, item_text in current_chunk_items:
                if item_type == "table":
                    if chunk_str and not chunk_str.endswith("\n"):
                        chunk_str += "\n\n"
                    chunk_str += item_text + "\n"
                else:
                    if chunk_str and not chunk_str.endswith("\n") and not chunk_str.endswith(" "):
                        chunk_str += " "
                    chunk_str += item_text
                    
            chunk_str = chunk_str.strip()
            if chunk_str:
                chunks.append(chunk_str)
            current_chunk_items = []
            current_tokens = 0
 
    for block in blocks:
        block = block.strip()
        if not block:
            continue
            
        is_markdown_table = block.startswith("|") and "|---" in block
        
        if is_markdown_table:
            lines = [line.strip() for line in block.split("\n") if line.strip()]
            if len(lines) > 2:
                header_lines = lines[:2]
                data_lines = lines[2:]
                
                header_text = "\n".join(header_lines)
                header_tokens = len(header_text.split())
                
                if current_tokens > 0 and current_tokens + header_tokens > chunk_size:
                    finalize_chunk()
                
                current_chunk_items.append(("table", header_text))
                current_tokens += header_tokens
                
                for data_line in data_lines:
                    line_tokens = len(data_line.split())
                    if current_tokens + line_tokens > chunk_size and current_tokens > header_tokens:
                        finalize_chunk()
                        current_chunk_items.append(("table", header_text))
                        current_tokens += header_tokens
                        
                    current_chunk_items.append(("table", data_line))
                    current_tokens += line_tokens
                
                continue

        # Normal text handling
        clean_block = block.replace("\n", " ")
        sentences = re.split(r"(?<=[.!?])\s+", clean_block)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        for sentence in sentences:
            sentence_tokens = len(sentence.split())
            if current_tokens + sentence_tokens > chunk_size and current_chunk_items:
                overlap_items = []
                overlap_tokens = 0
                for item_type, item_text in reversed(current_chunk_items):
                    if item_type == "sentence":
                        s_tokens = len(item_text.split())
                        if overlap_tokens + s_tokens <= overlap:
                            overlap_items.insert(0, ("sentence", item_text))
                            overlap_tokens += s_tokens
                        else:
                            break
                    else:
                        break
                        
                finalize_chunk()
                current_chunk_items = overlap_items + [("sentence", sentence)]
                current_tokens = overlap_tokens + sentence_tokens
            else:
                current_chunk_items.append(("sentence", sentence))
                current_tokens += sentence_tokens
                
    finalize_chunk()
    return chunks


# (Marker-delimited chunking functions removed as obsolete)


def split_numbered_clause_chunks(text: str) -> List[Dict[str, str]]:
    """Split text into chunks when clauses are prefixed as `Clause N:` and capture the tag code."""
    # Capture the specific clause code (e.g. EXM-01) in regex group 1
    pattern = re.compile(r"(?:^|\n)\s*Clause\s+([A-Za-z0-9_-]+)\s*:\s*", re.IGNORECASE)
    matches = list(pattern.finditer(text))
    if not matches:
        return []

    chunks: List[Dict[str, str]] = []
    for idx, match in enumerate(matches):
        tag = match.group(1).strip()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        normalized = " ".join(text[start:end].split()).strip()
        if normalized:
            chunks.append({
                "tag": tag,
                "text": normalized
            })

    return chunks


def update_faiss_index(new_embeddings: np.ndarray, user_email: str) -> None:
    """
    Update user-specific FAISS index by appending new embeddings.
    """
    if new_embeddings.size == 0:
        return
    
    from services.policy_service import get_user_policy_paths
    paths = get_user_policy_paths(user_email)
    index_path = paths["index_path"]
    
    new_embeddings = np.asarray(new_embeddings).astype("float32")
    
    if index_path.exists():
        index = faiss.read_index(str(index_path))
        index.add(new_embeddings)
    else:
        dim = new_embeddings.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(new_embeddings)
    
    faiss.write_index(index, str(index_path))


def ingest_policy_document(
    file_path: str, 
    user_email: str,
    policy_id: Optional[str] = None, 
    section_title: str = "General",
    force_ocr: bool = False
) -> Dict[str, Any]:
    """
    Ingest a policy document into a USER'S private RAG index.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Policy document not found: {file_path}")
    
    text = ""
    
    # Check if we should bypass traditional parser and force Visual AI OCR
    if force_ocr:
        try:
            from services.ocr_service import extract_text_from_attachment_ai
            ocr_text = extract_text_from_attachment_ai(str(file_path))
            if ocr_text:
                text = ocr_text
        except Exception as e:
            import logging
            logging.getLogger("rag.ingest").warning(f"Forced OCR failed: {e}")
            
    # Extract text from document using traditional parser if not forced or OCR failed
    if not text and file_path.suffix.lower() == ".pdf":
        try:
            import pdfplumber

            with pdfplumber.open(file_path) as pdf:
                pages_text = []
                last_table_headers = None
                
                for page in pdf.pages:
                    tables = page.find_tables()
                    if not tables:
                        pages_text.append(page.extract_text() or "")
                        continue
                        
                    # Filter out tables inside other tables
                    top_level_tables = []
                    for t in tables:
                        is_inside = False
                        for other in tables:
                            if t is other: continue
                            if t.bbox[0] >= other.bbox[0] and t.bbox[1] >= other.bbox[1] and t.bbox[2] <= other.bbox[2] and t.bbox[3] <= other.bbox[3]:
                                is_inside = True
                                break
                        if not is_inside:
                            top_level_tables.append(t)
                            
                    tables = sorted(top_level_tables, key=lambda t: t.bbox[1])
                    bboxes = [table.bbox for table in tables]
                    
                    def not_within_bboxes(obj, bboxes):
                        def obj_in_bbox(_obj, bbox):
                            v_mid = (_obj.get("top", 0) + _obj.get("bottom", 0)) / 2
                            h_mid = (_obj.get("x0", 0) + _obj.get("x1", 0)) / 2
                            x0, top, x1, bottom = bbox
                            return (h_mid >= x0) and (h_mid < x1) and (v_mid >= top) and (v_mid < bottom)
                        return not any(obj_in_bbox(obj, bbox) for bbox in bboxes)

                    current_y = 0
                    page_elements = []
                    
                    for table_idx, table in enumerate(tables):
                        x0, top, x1, bottom = table.bbox
                        
                        # Extract text above the table
                        if top > current_y + 1:
                            crop_box = (0, current_y, page.width, top)
                            if crop_box[3] > crop_box[1]:
                                cropped = page.crop(crop_box)
                                filtered_cropped = cropped.filter(lambda obj: not_within_bboxes(obj, bboxes))
                                text_above = filtered_cropped.extract_text()
                                if text_above and text_above.strip():
                                    page_elements.append(text_above.strip())
                        
                        extracted = table.extract()
                        if not extracted:
                            current_y = bottom
                            continue
                        
                        num_cols = len(extracted[0])
                        
                        # Clean all rows upfront and escape any pipe characters to protect markdown structures
                        clean_rows = []
                        for row in extracted:
                            clean = [str(cell).replace("\n", " ").replace("|", "\\|").strip() if cell else "" for cell in row]
                            clean_rows.append(clean)
                        
                        # Detect if this table is a continuation from the previous page
                        is_continuation = False
                        if table_idx == 0 and last_table_headers and len(last_table_headers) == num_cols and top < 300:
                            is_continuation = True
                        
                        # Find where headers end and data begins.
                        # A data row typically has digits (amounts, percentages) AND most columns filled.
                        # Everything before the first data row is considered header material.
                        first_data_idx = 0
                        if not is_continuation:
                            for ri, cr in enumerate(clean_rows):
                                filled = sum(1 for c in cr if c)
                                row_text = " ".join(cr)
                                # A row is "data" if it has numeric content AND enough filled columns
                                has_numbers = bool(re.search(r'\d', row_text))
                                has_enough_cols = filled >= max(2, num_cols * 0.4)
                                if has_numbers and has_enough_cols:
                                    first_data_idx = ri
                                    break
                            # If first_data_idx is still 0 (first row is data OR no data found)
                            if first_data_idx == 0:
                                # Check if row 0 looks like data (has digits)
                                row0_text = " ".join(clean_rows[0])
                                row0_has_numbers = bool(re.search(r'\d', row0_text))
                                row0_filled = sum(1 for c in clean_rows[0] if c)
                                if row0_has_numbers and row0_filled >= 2:
                                    # Row 0 IS data — this table is likely a continuation
                                    # from the previous page with different column parsing.
                                    # Use last_table_headers if available, otherwise no header.
                                    if last_table_headers:
                                        is_continuation = True
                                    else:
                                        first_data_idx = 0  # No header, all data
                                else:
                                    first_data_idx = 1  # Row 0 is the header
                        
                        # Build merged header from rows 0..first_data_idx-1
                        md_table = []
                        if is_continuation:
                            # Adapt header to current column count if different
                            adapted_headers = list(last_table_headers)
                            if len(adapted_headers) > num_cols:
                                adapted_headers = adapted_headers[:num_cols]
                            elif len(adapted_headers) < num_cols:
                                adapted_headers.extend([""] * (num_cols - len(adapted_headers)))
                            md_table.append("| " + " | ".join(adapted_headers) + " |")
                            md_table.append("|" + "|".join(["---"] * num_cols) + "|")
                        else:
                            # Merge all header rows column-by-column
                            merged_header = [""] * num_cols
                            for ri in range(first_data_idx):
                                for ci, cell in enumerate(clean_rows[ri]):
                                    if cell:
                                        if merged_header[ci]:
                                            merged_header[ci] += " " + cell
                                        else:
                                            merged_header[ci] = cell
                            
                            # If merged header is entirely empty, use first non-empty row
                            if not any(merged_header):
                                for ri, cr in enumerate(clean_rows):
                                    if any(cr):
                                        merged_header = cr
                                        first_data_idx = ri + 1
                                        break
                            
                            last_table_headers = merged_header
                            md_table.append("| " + " | ".join(merged_header) + " |")
                            md_table.append("|" + "|".join(["---"] * num_cols) + "|")
                        
                        # Collect data rows
                        start_idx = first_data_idx if not is_continuation else 0
                        data_rows_clean = []
                        for ri in range(start_idx, len(clean_rows)):
                             cr = clean_rows[ri]
                             if any(cr):
                                 data_rows_clean.append(cr)
                        
                        # --- Post-process: fix merged-cell column misalignment ---
                        # Get the current header (either merged or inherited)
                        if is_continuation:
                            current_header = list(adapted_headers)
                        else:
                            current_header = list(last_table_headers)
                        
                        # Shift orphaned headers: if col N has header but no data,
                        # and col N-1 has data but no header, move header left.
                        for ci in range(num_cols - 1, 0, -1):
                            col_has_data = any(dr[ci] for dr in data_rows_clean) if data_rows_clean else False
                            col_has_header = bool(current_header[ci])
                            prev_has_data = any(dr[ci - 1] for dr in data_rows_clean) if data_rows_clean else False
                            prev_has_header = bool(current_header[ci - 1])
                            if col_has_header and not col_has_data and prev_has_data and not prev_has_header:
                                current_header[ci - 1] = current_header[ci]
                                current_header[ci] = ""
                        
                        # Drop columns that are empty in BOTH header and all data rows
                        keep_cols = []
                        for ci in range(num_cols):
                            col_has_data = any(dr[ci] for dr in data_rows_clean) if data_rows_clean else False
                            if current_header[ci] or col_has_data:
                                keep_cols.append(ci)
                        
                        if keep_cols and len(keep_cols) < num_cols:
                            current_header = [current_header[ci] for ci in keep_cols]
                            data_rows_clean = [[dr[ci] for ci in keep_cols] for dr in data_rows_clean]
                            # Update last_table_headers with cleaned version
                            if not is_continuation:
                                last_table_headers = current_header
                        
                        # Rebuild md_table with cleaned columns
                        final_ncols = len(current_header)
                        md_table = []
                        md_table.append("| " + " | ".join(current_header) + " |")
                        md_table.append("|" + "|".join(["---"] * final_ncols) + "|")
                        for dr in data_rows_clean:
                            # Flawless table formation: pad or truncate row cells to match header columns exactly
                            row_cells = list(dr)
                            if len(row_cells) < final_ncols:
                                row_cells.extend([""] * (final_ncols - len(row_cells)))
                            elif len(row_cells) > final_ncols:
                                row_cells = row_cells[:final_ncols]
                            md_table.append("| " + " | ".join(row_cells) + " |")
                                
                        page_elements.append("\n\n" + "\n".join(md_table) + "\n\n")
                        current_y = bottom
                        
                    # Extract text below the last table
                    if current_y < page.height - 1:
                        crop_box = (0, current_y, page.width, page.height)
                        if crop_box[3] > crop_box[1]:
                            cropped = page.crop(crop_box)
                            filtered_cropped = cropped.filter(lambda obj: not_within_bboxes(obj, bboxes))
                            text_below = filtered_cropped.extract_text()
                            if text_below and text_below.strip():
                                page_elements.append(text_below.strip())
                                
                    pages_text.append("\n".join(page_elements))
                    
                text = "\n".join(pages_text)
        except Exception:
            # Fallback for PDFs that parse better with PyMuPDF.
            try:
                import fitz  # type: ignore

                doc = fitz.open(file_path)
                text = "\n".join(page.get_text() for page in doc)
            except ImportError:
                pass  # Handled by OCR fallback below
                
        # Scanned PDF Fallback (if text extraction yielded very little or nothing)
        if len(text.strip()) < 50:
            try:
                from services.ocr_service import extract_text_from_attachment_ai
                ocr_text = extract_text_from_attachment_ai(str(file_path))
                if ocr_text:
                    text = ocr_text
            except Exception as e:
                import logging
                logging.getLogger("rag.ingest").warning(f"OCR fallback failed: {e}")
                
    elif file_path.suffix.lower() in [".txt", ".md"]:
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
    elif file_path.suffix.lower() == ".docx":
        try:
            from docx import Document
            doc = Document(file_path)
            text = "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception as e:
            raise ValueError(f"Failed to parse Word document: {e}")
    elif file_path.suffix.lower() in [".png", ".jpg", ".jpeg"]:
        try:
            from services.ocr_service import extract_text_from_attachment_ai
            ocr_text = extract_text_from_attachment_ai(str(file_path))
            if ocr_text:
                text = ocr_text
        except Exception as e:
            raise ValueError(f"Failed to parse image via AI OCR: {e}")
    elif file_path.suffix.lower() == ".pdf":
        # Text already extracted via forced AI OCR
        pass
    else:
        raise ValueError(f"Unsupported file format: {file_path.suffix}")
    
    if not text or not text.strip():
        raise ValueError(f"No text extracted from: {file_path}")
    
    # Determine policy_id
    if policy_id is None:
        policy_id = file_path.stem

    # Determine section title dynamically if left as default "General"
    if section_title == "General" and file_path:
        # Strip leading numbers (e.g. "03_semester_examination" -> "semester_examination")
        stem_clean = re.sub(r'^\d+_+', '', file_path.stem)
        # Convert underscores and hyphens to spaces, then Title Case
        section_title = stem_clean.replace('_', ' ').replace('-', ' ').title()
    
    # Split into chunks. If structured clauses are present, parse them exactly.
    structured_chunks = split_numbered_clause_chunks(text)
    
    # Load or initialize user-specific policy_chunks.json
    from services.policy_service import get_user_policy_paths
    paths = get_user_policy_paths(user_email)
    index_path = paths["index_path"]
    chunks_path = paths["chunks_path"]

    if chunks_path.exists():
        with open(chunks_path, "r", encoding="utf-8") as f:
            existing_chunks = json.load(f)
    else:
        existing_chunks = []

    max_chunk_id = 0
    if existing_chunks:
        # Avoid throwing on custom string clause_ids by getting maximum integer chunk_id
        max_chunk_id = max(int(c.get("chunk_id", 0)) for c in existing_chunks if str(c.get("chunk_id", "0")).isdigit())

    new_chunks = []
    if structured_chunks:
        # 1. Structured clauses found: map tags (e.g. EXM-01) to clause_id
        for idx, sc in enumerate(structured_chunks, start=1):
            chunk_id = max_chunk_id + idx
            new_chunks.append(
                {
                    "chunk_id": chunk_id,
                    "text": f"Clause {sc['tag']}: {sc['text']}",
                    "policy_id": policy_id,
                    "section_title": section_title,
                    "clause_id": sc["tag"],  # <--- Registers the actual EXM-01 structural code!
                    "source_file": str(file_path),
                }
            )
    else:
        # 2. Standard unstructured fallback
        raw_chunks = split_text_into_chunks(text, chunk_size=CHUNK_SIZE_TOKENS, overlap=OVERLAP_TOKENS)
        if not raw_chunks:
            raise ValueError(f"No chunks generated from: {file_path}")
            
        for idx, chunk_text in enumerate(raw_chunks, start=1):
            chunk_id = max_chunk_id + idx
            new_chunks.append(
                {
                    "chunk_id": chunk_id,
                    "text": chunk_text,
                    "policy_id": policy_id,
                    "section_title": section_title,
                    "clause_id": str(chunk_id),
                    "source_file": str(file_path),
                }
            )
    
    # Generate embeddings for new chunks using singleton
    embedder = get_embedder()
    
    texts_to_embed = [chunk["text"] for chunk in new_chunks]
    embeddings = embedder.encode(
        texts_to_embed,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    embeddings = np.asarray(embeddings).astype("float32")
    
    # Update FAISS index
    update_faiss_index(embeddings, user_email)
    
    # Append new chunks to policy_chunks.json
    all_chunks = existing_chunks + new_chunks
    chunks_path.parent.mkdir(parents=True, exist_ok=True)
    with open(chunks_path, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, indent=2, ensure_ascii=False)
    
    return {
        "success": True,
        "policy_id": policy_id,
        "chunks_added": len(new_chunks),
        "total_chunks": len(all_chunks),
        "embeddings_generated": embeddings.shape[0],
        "index_path": str(index_path),
        "chunks_path": str(chunks_path),
    }


def main() -> None:
    if not CHUNKS_PATH.exists():
        raise FileNotFoundError(f"Missing chunks file: {CHUNKS_PATH}")

    with open(CHUNKS_PATH, "r", encoding="utf-8") as f:
        policy_chunks = json.load(f)

    if not policy_chunks:
        raise ValueError("policy_chunks.json is empty")

    texts = [chunk.get("text", "") for chunk in policy_chunks if chunk.get("text")]
    if not texts:
        raise ValueError("No valid text fields found in policy chunks")

    embedder = get_embedder()

    embeddings = embedder.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    embeddings = np.asarray(embeddings).astype("float32")

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    faiss.write_index(index, str(INDEX_PATH))

    print("Ingestion complete")
    print(f"Chunks indexed: {len(texts)}")
    print(f"Embedding dim: {dim}")
    print(f"Index saved at: {INDEX_PATH}")



if __name__ == "__main__":
    main()
