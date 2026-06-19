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
    """Background task to resume sync and intelligence processing for all users on startup."""
    from db.repository import get_all_active_users, has_enrichment_work
    from core.coordination import trigger_intelligence_suite
    import asyncio
    
    # Small delay to ensure DB and SSE systems are fully ready
    await asyncio.sleep(5)
    
    try:
        # --- STEP 1: (REMOVED) ---
        # We previously wiped Redis locks here. However, since Celery is a distributed queue
        # and locks have auto-expiring TTLs (ex=300), wiping them on backend restart accidentally
        # destroys the locks of healthy, currently-running Celery workers, causing duplicates.
        # We now rely purely on Redis TTLs for cleanup.

        # --- STEP 2: Resume sync and intelligence for all active users ---
        # get_all_active_users() already filters to non-revoked (logged-in) users using the DB.
        # This relies on robust database revocation tracking across restarts.
        users = []
        retries = 0
        while retries < 5:
            try:
                users = get_all_active_users()
                break
            except Exception as db_e:
                retries += 1
                logger.warning(f"⚠️ [Startup] Database not ready. Retrying {retries}/5 in 3s... ({db_e})")
                await asyncio.sleep(3)
        else:
            logger.error("❌ [Startup] Failed to connect to database after 5 retries. Sync loops will not automatically resume.")
            return

        logger.info(f"📋 [Startup] Found {len(users)} active users to resume sync for.")
        
        for user_email in users:
            # Restart the sync loop for active users
            from db.repository import get_user_sync_history
            from core.coordination import run_background_sync_loop
            history = get_user_sync_history(user_email)
            if history:
                logger.info(f"🔄 [Startup] Restarting sync worker for {user_email}.")
                from core.context import worker_manager
                worker_manager.start_sync_worker(user_email, lambda e=user_email: run_background_sync_loop(e))
            
            # Also resume any pending intelligence backlog
            if has_enrichment_work(user_email):
                logger.info(f"💡 [Startup] Pending intelligence work found for {user_email}. Resuming...")
                trigger_intelligence_suite(user_email)
            else:
                logger.debug(f"⏭️ [Startup] No pending intelligence work for {user_email}.")
    except Exception as e:
        logger.error(f"⚠️ [Startup] Resumer failed: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP ---
    import asyncio
    from core.notifier import SSE_NOTIFIER
    SSE_NOTIFIER.set_main_loop(asyncio.get_running_loop())
    
    logger.info("🚀 Starting backend lifecycle...")
    
    # 0. Database initialization
    # To prevent deadlocks in distributed clusters, Docker sets AUTO_INIT_DB=false and relies on run_migrations.py.
    # Native execution (default) safely auto-initializes the DB for both SQLite and local Postgres!
    if os.getenv("AUTO_INIT_DB", "true").lower() == "true":
        from db.repository import init_db
        init_db()
        logger.info(f"✅ {os.getenv('DATABASE_TYPE', 'sqlite').upper()} Database auto-initialized for local development.")
    
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
    root_path=os.getenv("FASTAPI_ROOT_PATH", ""),
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
