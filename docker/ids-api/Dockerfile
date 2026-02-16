# Smart City IDS API - Pre-built Docker Image
# Eliminates runtime dependency installation for reproducible deployments

FROM python:3.11-slim

LABEL maintainer="Smart City IDS Team"
LABEL description="LLM-driven Intrusion Detection System API"
LABEL version="2.0.0"

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install Python dependencies first (layer caching)
COPY services/ids-api/src/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code (all packages)
COPY services/ids-api/src/ ./

# Copy static frontend (HTML, CSS, JS modules)
COPY services/ids-api/static/ ./static/

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose API port
EXPOSE 8000

# Run the application
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
