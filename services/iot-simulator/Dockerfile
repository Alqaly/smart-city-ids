FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install paho-mqtt flask requests prometheus-client

# Copy the enhanced IoT device code
COPY mqtt_device_enhanced.py .

# Create non-root user for security
RUN useradd -m -u 1000 iotuser && chown -R iotuser:iotuser /app
USER iotuser

# Expose the REST API port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:5000/status || exit 1

# Run the enhanced IoT simulator
CMD ["python", "mqtt_device_enhanced.py"]
