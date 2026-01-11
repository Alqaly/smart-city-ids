"""Smoke tests for Smart City IDS API."""
import os
import sys
from pathlib import Path

# Ensure service src is importable
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "services" / "ids-api" / "src"
sys.path.insert(0, str(SRC))

os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("GROQ_API_KEY", "test")


def test_imports():
    """Test that core modules can be imported."""
    try:
        import fastapi
        import uvicorn
        assert True
    except ImportError as e:
        assert False, f"Failed to import required modules: {e}"


def test_alert_json_valid():
    """Test that sample alert JSON is valid."""
    payload = {
        "output": "Falco rule triggered",
        "priority": "Critical",
        "rule": "Unexpected process",
        "time": "2025-01-01T00:00:00Z",
        "output_fields": {"container.name": "traffic-camera-1", "proc.cmdline": "/bin/bash"}
    }
    assert isinstance(payload, dict)
    assert "output" in payload
    assert "priority" in payload
    assert "output_fields" in payload
