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

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP ---
    import asyncio
    from core.notifier import SSE_NOTIFIER
    SSE_NOTIFIER.set_main_loop(asyncio.get_running_loop())
    
    logger.info("🚀 Starting backend lifecycle...")
    
    # 0. Initialize Database
    from db.repository import init_db
    init_db()
    
    # 1. Warmup AI models
    try:
        get_embedder()
        reload_retriever_data()
        logger.info("✅ Database initialized and AI models warmed up.")
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

# --- ROUTERS ---
for router in ALL_ROUTERS:
    app.include_router(router)

@app.get("/")
def root():
    return {"status": "Backend running", "environment": os.getenv("APP_ENV", "dev")}

@app.get("/health")
def health():
    return {"status": "healthy"}
