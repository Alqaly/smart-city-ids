import os
import sys
from pathlib import Path

# Ensure service src is importable
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "services" / "ids-api" / "src"
sys.path.insert(0, str(SRC))

os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("GROQ_API_KEY", "test")

from fastapi.testclient import TestClient
import main as ids_main

def test_post_alert_basic_flow():
    client = TestClient(ids_main.app)
    payload = {
        "output": "Falco rule triggered",
        "priority": "Critical",
        "rule": "Unexpected process",
        "time": "2025-01-01T00:00:00Z",
        "output_fields": {"container.name": "traffic-camera-1", "proc.cmdline": "/bin/bash"}
    }
    resp = client.post("/api/alerts", json=payload)
    assert resp.status_code < 300, resp.text
    assert isinstance(resp.json(), dict)
