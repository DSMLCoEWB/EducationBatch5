from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import shutil
import os
import hashlib
from pathlib import Path

from core.dependencies import get_authenticated_user
from services.policy_service import (
    slugify_policy_id, remove_policy_chunks, resolve_policy_file_path, 
    load_policy_chunks
)
from rag_pipeline.ingest import ingest_policy_document
from services.rag_service import reload_retriever_data
from config import POLICY_DIR, DEMO_POLICY_DIR

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
    """Uploads and indexes a new policy document with Intelligent Collision Guard."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDFs allowed.")
        
    # 1. Read content and calculate digital fingerprint (hash)
    content = await file.read()
    new_hash = hashlib.sha256(content).hexdigest()
    
    policy_id = slugify_policy_id(file.filename)
    path = POLICY_DIR / f"{policy_id}.pdf"
    
    is_update = False
    
    # 2. Collision Guard: Check if content is truly new
    if path.exists():
        with open(path, "rb") as f:
            old_hash = hashlib.sha256(f.read()).hexdigest()
            
        if new_hash == old_hash:
            return {
                "success": True,
                "message": "Policy already up to date. No re-indexing required.",
                "stats": {
                    "policy_id": policy_id,
                    "chunks": 0,
                    "is_update": False,
                    "duplicate": True
                }
            }
        is_update = True
    
    # 3. Save physical file
    try:
        with open(path, "wb") as f:
             f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Save failed: {e}")
    finally:
        await file.close()

    # 4. Critical Logic: Purge old memory and teach the AI the new content
    remove_policy_chunks(policy_id)
    stats = ingest_policy_document(str(path), policy_id)
    reload_retriever_data()
    
    return {
        "success": True, 
        "message": f"Policy {'updated' if is_update else 'indexed'} successfully",
        "policy_id": policy_id, 
        "stats": stats
    }

@router.get("/", response_model=Dict[str, List[PolicyInfo]])
def list_policies(user_email: str = Depends(get_authenticated_user)):
    """Lists all discovered policies on disk and their RAG index status."""
    
    chunks = load_policy_chunks()
    counts = {}
    for c in chunks:
        pid = c.get("policy_id")
        if pid: counts[pid] = counts.get(pid, 0) + 1
        
    # Global Filesystem Sweep
    discovered_pids = set()
    for d in [POLICY_DIR, DEMO_POLICY_DIR]:
        if d.exists():
            for f in d.glob("*.pdf"): discovered_pids.add(f.stem)
            for f in d.glob("*.PDF"): discovered_pids.add(f.stem)
            
    # Include both files and existing index entries
    all_pids = discovered_pids.union(set(counts.keys()))
    
    policies = []
    for pid in sorted(list(all_pids)):
        exists = resolve_policy_file_path(pid) is not None
        chunk_count = counts.get(pid, 0)
        
        if exists and chunk_count > 0:
            status = "active"
        elif exists and chunk_count == 0:
            status = "pending"
        else:
            status = "stale"
            
        policies.append(PolicyInfo(
            id=pid, 
            chunk_count=chunk_count, 
            status=status
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

@router.post("/{policy_id}/activate")
def activate_policy(
    policy_id: str,
    user_email: str = Depends(get_authenticated_user)
):
    """Surgically indexes (teaches) a specific policy to the AI."""
    path = resolve_policy_file_path(policy_id)
    if not path:
        raise HTTPException(status_code=404, detail="Physical file missing. Cannot activate.")
        
    remove_policy_chunks(policy_id)
    stats = ingest_policy_document(str(path), policy_id)
    reload_retriever_data()
    
    return {"success": True, "stats": stats}

@router.delete("/{policy_id}")
def delete_policy(
    policy_id: str,
    user_email: str = Depends(get_authenticated_user)
):
    """Removes a policy and its index entries (Atomic Cleanup)."""
    path = resolve_policy_file_path(policy_id)
    if path and path.exists():
        path.unlink()
    
    # Always try to remove chunks, even if file is already gone (Orphan/Stale cleanup)
    _, removed = remove_policy_chunks(policy_id)
    reload_retriever_data()
    return {"status": "success", "removed_chunks": removed}

@router.post("/load-demo")
def load_demo_policies(user_email: str = Depends(get_authenticated_user)):
    """Seeds the RAG index with the production demo PDFs."""
    from services.policy_service import (
        load_policy_chunks, save_policy_chunks, 
        rebuild_index_from_chunks, remove_policy_chunks
    )
    
    DEMO_DIR = DEMO_POLICY_DIR
    pdf_candidates = list(DEMO_DIR.glob("*.pdf")) + list(DEMO_DIR.glob("*.PDF"))
    pdfs = sorted({p.resolve() for p in pdf_candidates})
    demo_ids = [p.stem for p in pdfs]

    # 1. Surgical Purge: Remove only demo chunks to preserve custom guidelines
    chunks = load_policy_chunks()
    retained_chunks = [c for c in chunks if c.get("policy_id") not in demo_ids]
    
    if len(retained_chunks) < len(chunks):
        save_policy_chunks(retained_chunks)
        rebuild_index_from_chunks(retained_chunks)
        print(f"[Policy Sync] Purged {len(chunks) - len(retained_chunks)} demo chunks.")

    # 2. Ingest sequentially (append mode)
    ingested_count = 0
    for p in pdfs:
        try:
            ingest_policy_document(str(p), policy_id=p.stem)
            ingested_count += 1
        except Exception as e:
            print(f"[Policy Sync Error] Failed to ingest {p.name}: {e}")
            
    # 3. Final State Refresh
    reload_retriever_data()
    
    return {
        "success": True, 
        "message": f"Demo policies indexed: {ingested_count}/{len(pdfs)}",
        "stats": {
            "pdf_count": len(pdfs),
            "indexed_count": ingested_count
        }
    }
