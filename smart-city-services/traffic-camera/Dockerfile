FROM python:3.9-slim
WORKDIR /app
RUN pip install --no-cache-dir flask==3.0.0
COPY app.py .
EXPOSE 5000
# Intentionally runs as root for demo vulnerability
CMD ["python", "app.py"]
