from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Form, BackgroundTasks
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
    load_policy_chunks, async_categorize_policy
)
from rag.ingest import ingest_policy_document
from services.rag_service import reload_retriever_data
from config import POLICY_DIR, DEMO_POLICY_DIR

router = APIRouter(prefix="/policies", tags=["Policies"])

class PolicyInfo(BaseModel):
    id: str
    chunk_count: int
    status: str
    extension: str = "pdf"
    is_demo: bool = False
    category: str = "Miscellaneous"

@router.post("/upload")
async def upload_policy(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    force_ocr: bool = Form(False),
    user_email: str = Depends(get_authenticated_user)
):
    """Uploads and indexes a new policy document with Intelligent Collision Guard."""
    allowed_exts = {".pdf", ".docx", ".txt", ".md", ".png", ".jpg", ".jpeg"}
    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in allowed_exts:
        raise HTTPException(status_code=400, detail=f"Unsupported format. Allowed: {', '.join(allowed_exts)}")
        
    # 1. Read content and calculate digital fingerprint (hash)
    content = await file.read()
    new_hash = hashlib.sha256(content).hexdigest()
    
    policy_id = slugify_policy_id(filename)
    
    # User-Specific Path Resolution
    from services.policy_service import get_user_policy_paths
    paths = get_user_policy_paths(user_email)
    path = paths["policy_dir"] / f"{policy_id}{ext}"
    
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
    remove_policy_chunks(policy_id, user_email)
    stats = ingest_policy_document(str(path), user_email, policy_id, force_ocr=force_ocr)
    reload_retriever_data(user_email)
    
    # 5. Background Task: AI Categorization
    background_tasks.add_task(async_categorize_policy, policy_id, user_email)
    
    return {
        "success": True, 
        "message": f"Policy {'updated' if is_update else 'indexed'} successfully",
        "policy_id": policy_id, 
        "stats": stats
    }

@router.get("/", response_model=Dict[str, List[PolicyInfo]])
def list_policies(user_email: str = Depends(get_authenticated_user)):
    """Lists all discovered policies on disk and their RAG index status."""
    
    chunks = load_policy_chunks(user_email)
    counts = {}
    categories = {}
    for c in chunks:
        pid = c.get("policy_id")
        if pid: 
            counts[pid] = counts.get(pid, 0) + 1
            if "category" in c and pid not in categories:
                categories[pid] = c["category"]
        
    # Local Filesystem Sweep
    discovered_pids = set()
    policy_extensions = {}
    from services.policy_service import get_user_policy_paths
    paths = get_user_policy_paths(user_email)
    
    dirs = [paths["policy_dir"], DEMO_POLICY_DIR]
    for d in dirs:
        if d.exists():
            for ext_pattern in [
                "*.pdf", "*.PDF", "*.docx", "*.DOCX", "*.txt", "*.TXT", "*.md", "*.MD",
                "*.png", "*.PNG", "*.jpg", "*.JPG", "*.jpeg", "*.JPEG"
            ]:
                for f in d.glob(ext_pattern):
                    pid = f.stem
                    discovered_pids.add(pid)
                    policy_extensions[pid] = f.suffix.lower().replace(".", "")
            
    # Include both files and existing index entries
    all_pids = discovered_pids.union(set(counts.keys()))
    
    policies = []
    for pid in sorted(list(all_pids)):
        resolved_path = resolve_policy_file_path(pid, user_email)
        exists = resolved_path is not None
        chunk_count = counts.get(pid, 0)
        
        # Determine if it is solely a demo policy (not present in user's isolated directory)
        user_path = paths["policy_dir"] / resolved_path.name if resolved_path else None
        is_demo = not (user_path and user_path.exists())
        
        # Get extension dynamically
        ext = "pdf"
        if resolved_path:
            ext = resolved_path.suffix.lower().replace(".", "")
        elif pid in policy_extensions:
            ext = policy_extensions[pid]
        
        if exists and chunk_count > 0:
            status = "active"
        elif exists and chunk_count == 0:
            status = "pending"
        else:
            status = "stale"
            
        policies.append(PolicyInfo(
            id=pid, 
            chunk_count=chunk_count, 
            status=status,
            extension=ext,
            is_demo=is_demo,
            category=categories.get(pid, "Miscellaneous")
        ))
    return {"policies": policies}

@router.get("/{policy_id}")
def download_policy(
    policy_id: str,
    user_email: str = Depends(get_authenticated_user)
):
    """Downloads the original document for a policy."""
    path = resolve_policy_file_path(policy_id, user_email)
    if not path:
        raise HTTPException(status_code=404)
        
    ext = path.suffix.lower()
    media_types = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg"
    }
    mtype = media_types.get(ext, "application/octet-stream")
    return FileResponse(str(path), media_type=mtype)

@router.post("/activate-all")
def activate_all_policies(user_email: str = Depends(get_authenticated_user)):
    """Indexes/Activates all pending or unindexed guidelines for this user."""
    from services.policy_service import get_user_policy_paths
    paths = get_user_policy_paths(user_email)
    policy_dir = paths["policy_dir"]
    
    # Sweep local directory for all PDFs
    pdf_files = list(policy_dir.glob("*.pdf")) + list(policy_dir.glob("*.PDF"))
    if not pdf_files:
        return {"success": True, "message": "No guidelines found to publish.", "activated_count": 0}
        
    # Find currently active policy ids in user's index chunks
    chunks = load_policy_chunks(user_email)
    active_pids = {c.get("policy_id") for c in chunks if c.get("policy_id")}
    
    to_activate = [p for p in pdf_files if p.stem not in active_pids]
    
    if not to_activate:
        return {"success": True, "message": "All guidelines are already active.", "activated_count": 0}
        
    activated_count = 0
    stats_list = []
    for path in to_activate:
        try:
            # Surgically ingest pending document
            remove_policy_chunks(path.stem, user_email)
            stats = ingest_policy_document(str(path), user_email, path.stem)
            activated_count += 1
            stats_list.append({"policy_id": path.stem, "status": "success", "stats": stats})
        except Exception as e:
            stats_list.append({"policy_id": path.stem, "status": "failed", "error": str(e)})
            
    # Reload retriever index just once at the end for efficiency!
    if activated_count > 0:
        reload_retriever_data(user_email)
        
    return {
        "success": True, 
        "message": f"Successfully published {activated_count} guidelines.", 
        "activated_count": activated_count,
        "details": stats_list
    }


@router.post("/{policy_id}/activate")
def activate_policy(
    policy_id: str,
    background_tasks: BackgroundTasks,
    user_email: str = Depends(get_authenticated_user)
):
    """Surgically indexes (teaches) a specific policy to the AI."""
    path = resolve_policy_file_path(policy_id, user_email)
    if not path:
        raise HTTPException(status_code=404, detail="Physical file missing. Cannot activate.")
        
    remove_policy_chunks(policy_id, user_email)
    stats = ingest_policy_document(str(path), user_email, policy_id)
    reload_retriever_data(user_email)
    
    background_tasks.add_task(async_categorize_policy, policy_id, user_email)
    
    return {"success": True, "stats": stats}

@router.delete("/{policy_id}")
def delete_policy(
    policy_id: str,
    user_email: str = Depends(get_authenticated_user)
):
    """Removes a policy and its index entries (Atomic Cleanup)."""
    path = resolve_policy_file_path(policy_id, user_email)
    
    # Only allow deletion of user-uploaded files, not demo files
    from services.policy_service import get_user_policy_paths
    paths = get_user_policy_paths(user_email)
    if path and path.parent == paths["policy_dir"] and path.exists():
        path.unlink()
    
    # Always try to remove chunks, even if file is already gone (Orphan/Stale cleanup)
    _, removed = remove_policy_chunks(policy_id, user_email)
    reload_retriever_data(user_email)
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
    chunks = load_policy_chunks(user_email)
    retained_chunks = [c for c in chunks if c.get("policy_id") not in demo_ids]
    
    if len(retained_chunks) < len(chunks):
        save_policy_chunks(retained_chunks, user_email)
        rebuild_index_from_chunks(retained_chunks, user_email)
        print(f"[Policy Sync] Purged {len(chunks) - len(retained_chunks)} demo chunks for {user_email}.")

    # 2. Ingest sequentially (append mode)
    ingested_count = 0
    for p in pdfs:
        try:
            ingest_policy_document(str(p), user_email, policy_id=p.stem)
            ingested_count += 1
        except Exception as e:
            print(f"[Policy Sync Error] Failed to ingest {p.name} for {user_email}: {e}")
            
    # 3. Final State Refresh
    reload_retriever_data(user_email)
    
    return {
        "success": True, 
        "message": f"Demo policies indexed: {ingested_count}/{len(pdfs)}",
        "stats": {
            "pdf_count": len(pdfs),
            "indexed_count": ingested_count
        }
    }
