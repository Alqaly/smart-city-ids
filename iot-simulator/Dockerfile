FROM python:3.12-alpine
WORKDIR /app
COPY mqtt_device.py .
RUN pip install --no-cache-dir flask requests paho-mqtt
CMD ["python", "mqtt_device.py"]
