from workers.manager import WorkerManager

# --- SINGLETON ---
# This instance will be used across all modules.
# In a modular system, initializing this here ensures it's available 
# to both services and routers without creating circular dependencies.
worker_manager = WorkerManager()
