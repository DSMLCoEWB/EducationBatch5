import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aicoe-backend")

def get_logger(name: str):
    return logging.getLogger(f"aicoe-backend.{name}")
