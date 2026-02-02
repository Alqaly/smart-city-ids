# Smart City Demo Service - Pre-built Docker Image
# Generic base image for all smart city demo services (traffic-camera, healthcare-api, parking-system)
# These are INTENTIONALLY VULNERABLE for demonstration purposes

FROM python:3.11-slim

LABEL maintainer="Smart City IDS Team"
LABEL description="Smart City Demo Service (intentionally vulnerable)"
LABEL version="1.0.0"

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Flask with pinned version
RUN pip install --no-cache-dir flask==3.0.0

# Application code will be mounted via ConfigMap
# This allows updating without rebuilding the image

# Create non-root user (note: some attacks need root, so keeping root for demo)
# In production, you would: RUN useradd -m appuser && USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${APP_PORT:-5000}/health || exit 1

# Default port (overridden per service)
EXPOSE 5000

# Run the application
CMD ["python", "/app/app.py"]
