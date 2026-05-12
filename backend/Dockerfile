FROM python:3.10-slim

WORKDIR /app

# System dependencies (minimal footprint)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies (no cache to reduce layer size)
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create required directories
RUN mkdir -p /app/data /app/files /app/policies /app/demo_policies /app/attachments

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health', timeout=5)"

# Use Uvicorn directly (single worker) for SQLite + SSE compatibility.
# Gunicorn multi-worker mode breaks SQLite concurrent writes and SSE streams.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "120"]
