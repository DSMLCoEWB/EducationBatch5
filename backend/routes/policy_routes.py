from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import shutil
import os

from core.dependencies import get_authenticated_user
from services.policy_service import (
    slugify_policy_id, remove_policy_chunks, resolve_policy_file_path, 
    load_policy_chunks
)
from rag_pipeline.ingest import ingest_policy_document
from services.rag_service import reload_retriever_data
from config import POLICY_DIR

router = APIRouter(prefix="/policies", tags=["Policies"])

class PolicyInfo(BaseModel):
    id: str
    chunk_count: int
    status: str

@router.post("/upload")
async def upload_policy(
    file: UploadFile = File(...),
    user_email: str = Depends(get_authenticated_user)
):
    """Uploads and indexes a new policy document."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDFs allowed.")
        
    policy_id = slugify_policy_id(file.filename)
    path = POLICY_DIR / f"{policy_id}.pdf"
    
    try:
        with open(path, "wb") as f:
             shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Save failed: {e}")
    finally:
        await file.close()

    # Ingest
    remove_policy_chunks(policy_id)
    stats = ingest_policy_document(str(path), policy_id)
    reload_retriever_data()
    
    return {
        "success": True, 
        "message": f"Successfully indexed {file.filename}",
        "policy_id": policy_id, 
        "stats": stats
    }

@router.get("/", response_model=Dict[str, List[PolicyInfo]])
def list_policies(user_email: str = Depends(get_authenticated_user)):
    """Lists all indexed policies."""
    chunks = load_policy_chunks()
    counts = {}
    for c in chunks:
        pid = c.get("policy_id")
        if pid: counts[pid] = counts.get(pid, 0) + 1
        
    policies = []
    for pid, count in counts.items():
        exists = resolve_policy_file_path(pid) is not None
        policies.append(PolicyInfo(
            id=pid, chunk_count=count, 
            status="indexed" if exists else "orphaned"
        ))
    return {"policies": policies}

@router.get("/{policy_id}")
def download_policy(
    policy_id: str,
    user_email: str = Depends(get_authenticated_user)
):
    """Downloads the original PDF for a policy."""
    path = resolve_policy_file_path(policy_id)
    if not path:
        raise HTTPException(status_code=404)
    return FileResponse(str(path), media_type="application/pdf")

@router.delete("/{policy_id}")
def delete_policy(
    policy_id: str,
    user_email: str = Depends(get_authenticated_user)
):
    """Removes a policy and its index entries."""
    path = resolve_policy_file_path(policy_id)
    if path and path.exists():
        path.unlink()
    
    _, removed = remove_policy_chunks(policy_id)
    reload_retriever_data()
    return {"status": "deleted", "removed_chunks": removed}

@router.post("/load-demo")
def load_demo_policies(user_email: str = Depends(get_authenticated_user)):
    """Seeds the RAG index with the production demo PDFs."""
    from config import BASE_DIR, CHUNKS_PATH, INDEX_PATH
    import json
    
    DEMO_DIR = BASE_DIR / "demo_policies"
    
    # Identify PDFs
    pdf_candidates = list(DEMO_DIR.glob("*.pdf")) + list(DEMO_DIR.glob("*.PDF"))
    pdfs = sorted({p.resolve() for p in pdf_candidates})
    
    # 1. Reset state
    CHUNKS_PATH.unlink(missing_ok=True)
    INDEX_PATH.unlink(missing_ok=True)
    
    # 2. Ingest sequentially
    ingested_count = 0
    for p in pdfs:
        try:
            ingest_policy_document(str(p), policy_id=p.stem)
            ingested_count += 1
        except Exception as e:
            print(f"[Policy Sync Error] Failed to ingest {p.name}: {e}")
            
    # 3. Reload Search Engine
    reload_retriever_data()
    
    return {
        "success": True, 
        "message": f"Demo policies indexed: {ingested_count}/{len(pdfs)}",
        "stats": {
            "pdf_count": len(pdfs),
            "indexed_count": ingested_count
        }
    }
