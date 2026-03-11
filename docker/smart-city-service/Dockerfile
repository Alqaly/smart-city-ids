# Smart City Service - Shared Emulator Runtime Image
# Generic base image for smart-city protocol emulators mounted via ConfigMap.
# Services may intentionally expose insecure protocol paths for IDS evaluation.

FROM python:3.11-slim

LABEL maintainer="Smart City IDS Team"
LABEL description="Shared Smart City emulator runtime image"
LABEL version="1.0.0"

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install runtime dependencies shared by the emulator services
RUN pip install --no-cache-dir \
    flask==3.0.0 \
    paho-mqtt==2.1.0 \
    opcua==0.98.13

# Application code will be mounted via ConfigMap
# This allows updating without rebuilding the image

# Create non-root user (note: some attacks need root, so keeping root for research evaluation)
# In production, you would: RUN useradd -m appuser && USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${APP_PORT:-5000}/health || exit 1

# Default port (overridden per service)
EXPOSE 5000

# Run the application
CMD ["python", "/app/app.py"]
