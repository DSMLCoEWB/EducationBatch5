FROM python:3.12-slim

WORKDIR /app

# System dependencies (minimal footprint)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install standard CPU PyTorch to avoid massive CUDA dependencies in Docker
RUN pip install --default-timeout=100 --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# Copy requirements first for better caching
COPY requirements.txt .

# Install remaining Python dependencies (this will skip torch since it's already installed)
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create required directories
RUN mkdir -p /app/storage

# Set PYTHONPATH so the container treats src/ as a package root
ENV PYTHONPATH=/app/src

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health', timeout=5)"

# Enterprise Throughput: Use Gunicorn to manage multiple Uvicorn workers.
# Since we migrated to PostgreSQL, we are no longer bound by SQLite concurrent write locks.
CMD ["gunicorn", "app:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--timeout", "120"]
