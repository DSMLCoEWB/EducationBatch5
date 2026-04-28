from fastapi import APIRouter, Depends, HTTPException, Body
from typing import List, Dict, Any
from core.dependencies import get_authenticated_user
from db.repository import (
    get_active_categories,
    get_all_categories,
    add_category,
    update_category,
    delete_category
)
from core.coordination import trigger_intelligence_suite

router = APIRouter(prefix="/settings", tags=["Settings"])

@router.get("/categories")
def fetch_active_categories(user_email: str = Depends(get_authenticated_user)):
    """Fetches all active categories."""
    try:
        categories = get_active_categories(user_email)
        return {"categories": categories}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/categories/all")
def fetch_all_categories(user_email: str = Depends(get_authenticated_user)):
    """Fetches all categories (including inactive)."""
    try:
        categories = get_all_categories(user_email)
        return {"categories": categories}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/categories")
def create_category(
    payload: Dict[str, Any] = Body(...),
    user_email: str = Depends(get_authenticated_user)
):
    """Adds a new custom category."""
    name = payload.get("name")
    color = payload.get("color", "#3b82f6")
    icon = payload.get("icon", "Hash")
    
    if not name:
        raise HTTPException(status_code=400, detail="Category name is required.")
        
    try:
        cat_id = add_category(user_email, name, color, icon)
        return {"status": "success", "id": cat_id, "name": name, "color": color, "icon": icon}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/categories/{cat_id}")
def edit_category(
    cat_id: str,
    payload: Dict[str, Any] = Body(...),
    user_email: str = Depends(get_authenticated_user)
):
    """Updates an existing category."""
    name = payload.get("name")
    color = payload.get("color")
    icon = payload.get("icon", "Hash")
    
    if not name or not color:
        raise HTTPException(status_code=400, detail="Name and color are required.")
        
    try:
        update_category(user_email, cat_id, name, color, icon)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/categories/{cat_id}")
def remove_category(
    cat_id: str,
    user_email: str = Depends(get_authenticated_user)
):
    """Deactivates a category and triggers self-healing re-categorization."""
    try:
        delete_category(user_email, cat_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/categories/apply")
def apply_categories(user_email: str = Depends(get_authenticated_user)):
    """Triggers the AI intelligence worker to re-evaluate the inbox."""
    try:
        from core.notifier import SSE_NOTIFIER
        SSE_NOTIFIER.notify(user_email, "sync_started")
        trigger_intelligence_suite(user_email)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
