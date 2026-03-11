FROM python:3.9-slim

WORKDIR /app

RUN pip install --no-cache-dir flask==3.0.0 paho-mqtt==2.1.0

COPY app.py .

EXPOSE 5002

CMD ["python", "app.py"]
