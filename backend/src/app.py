import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import IS_PRODUCTION
from core.context import worker_manager
from core.logging import get_logger
from routes import ALL_ROUTERS
from services.rag_service import get_embedder, reload_retriever_data

logger = get_logger("app")

async def startup_resumer():
    """Background task to resume intelligence processing for all users on startup."""
    from db.repository import get_all_active_users, has_enrichment_work
    from core.coordination import trigger_intelligence_suite
    import asyncio
    
    # Small delay to ensure DB and SSE systems are fully ready
    await asyncio.sleep(5)
    
    try:
        users = get_all_active_users()
        logger.info(f"📋 [Startup] Found {len(users)} users to scan for pending work.")
        
        for user_email in users:
            if has_enrichment_work(user_email):
                logger.info(f"💡 [Startup] Pending intelligence work found for {user_email}. Resuming...")
                trigger_intelligence_suite(user_email)
            else:
                logger.debug(f"⏭️ [Startup] No pending work for {user_email}.")
    except Exception as e:
        logger.error(f"⚠️ [Startup] Resumer failed: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP ---
    import asyncio
    from core.notifier import SSE_NOTIFIER
    SSE_NOTIFIER.set_main_loop(asyncio.get_running_loop())
    
    logger.info("🚀 Starting backend lifecycle...")
    
    # 0. Database should be initialized externally via run_migrations.py
    # We no longer call init_db() here to prevent deadlocks in distributed clusters.
    
    # 1. Warmup AI models
    try:
        get_embedder()
        # Note: retriever data is now loaded per-user on demand
        logger.info("✅ Database initialized and AI embedder warmed up.")
        
        # 2. Resume background intelligence work
        asyncio.create_task(startup_resumer())
        
        # 3. Start Redis listener for SSE broadcasts (IPC from Celery)
        asyncio.create_task(SSE_NOTIFIER.listen_for_redis_broadcasts())
        
    except Exception as e:
        logger.error(f"⚠️ Startup warmup failed: {e}")
        
    yield
    
    # --- SHUTDOWN ---
    logger.info("🏁 Stopping background workers...")
    worker_manager.stop_all()

# --- APP INITIALIZATION ---
app = FastAPI(
    title="Education Grievance AI Backend",
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    lifespan=lifespan
)

# --- MIDDLEWARE ---
cors_origins = [
    o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi import Request
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# --- ROUTERS ---
for router in ALL_ROUTERS:
    app.include_router(router)

@app.get("/")
def root():
    return {"status": "Backend running", "environment": os.getenv("APP_ENV", "dev")}

@app.get("/health")
def health():
    from db.session import get_db_conn
    try:
        with get_db_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Database connection failed")
