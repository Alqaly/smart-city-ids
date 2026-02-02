# Falco Forwarder - Pre-built Docker Image
# Forwards Falco security alerts to IDS API

FROM python:3.11-slim

LABEL maintainer="Smart City IDS Team"
LABEL description="Falco alert forwarder for Smart City IDS"
LABEL version="1.0.0"

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir flask==3.0.0 requests==2.31.0

# Copy application
COPY services/forwarders/falco/src/ ./

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

EXPOSE 5000

CMD ["python", "main.py"]
