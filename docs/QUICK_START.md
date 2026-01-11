# Quick-start guide (30 min)

Get the IDS API running locally and send a sample alert.

## Prerequisites
- Linux (Ubuntu 20.04+) or macOS
- Python 3.9+
- Node.js 18+ (for docs validation; optional)
- PostgreSQL client (psql) if you want to test migrations
- Groq API key (`GROQ_API_KEY`) or OpenAI key (`OPENAI_API_KEY`) — get one free from [Groq](https://console.groq.com) or [OpenAI](https://platform.openai.com)

## Step 1: Clone & navigate
```bash
cd /home/aka/smart-city-ids
```

## Step 2: Set up LLM key
```bash
export GROQ_API_KEY="gsk_..."  # or export OPENAI_API_KEY="sk_..."
```

## Step 3: Check environment
```bash
make check
```

Expected output: checkmarks for python, node (optional), psql (optional), and confirmation of LLM key set.

## Step 4: Create virtual environment & install IDS API
```bash
make ids-api-venv
# OR manually:
cd services/ids-api/src
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Step 5: Start IDS API
```bash
cd services/ids-api/src
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

Expected output:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

## Step 6: In another terminal, send a sample alert
```bash
curl -X POST http://localhost:8000/api/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "output": "Falco rule triggered: Unexpected process spawned",
    "priority": "Critical",
    "rule": "Unexpected process",
    "time": "2025-01-11T12:00:00Z",
    "output_fields": {
      "container.name": "traffic-camera-1",
      "proc.cmdline": "/bin/bash -i",
      "proc.user": "root"
    }
  }'
```

Expected response (HTTP 200):
```json
{
  "alert_id": "...",
  "status": "processing",
  "analysis": {...}
}
```

## Step 7: Verify the response
- Check `status` field — should be `"processing"` or `"success"`.
- Check `analysis.severity` — should be 1–10 based on LLM assessment.
- Check `analysis.threat_type` — e.g., "Privilege Escalation", "Malware Activity".
- Check `analysis.automated_actions` — may include `["isolate_pod"]` if severity >= 8.

## Step 8: Run smoke tests (optional)
```bash
make smoke-test
```

Expected output: all tests pass (green checkmarks).

## Troubleshooting

### IDS API fails to start
- **Error:** `ModuleNotFoundError: No module named 'fastapi'`
  - Fix: Ensure you're in the venv and ran `pip install -r requirements.txt`.
  - ```bash
    cd services/ids-api/src
    source venv/bin/activate
    pip install -r requirements.txt
    ```

- **Error:** `ConfigError: No LLM API key set`
  - Fix: Export `GROQ_API_KEY` or `OPENAI_API_KEY` before starting.
  - ```bash
    export GROQ_API_KEY="gsk_..."
    ```

### Alert POST returns 500 error
- Check IDS API logs — look for LLM API errors (auth, rate limit, malformed request).
- Ensure `GROQ_API_KEY` / `OPENAI_API_KEY` is valid.
- Verify alert JSON matches expected format (see docs/PROJECT_CONTEXT.md → LLM contract).

### Docs validation fails
- Run `make docs-check` to see which files have lint errors.
- Common fixes: fix markdown headings, remove trailing spaces, ensure valid links.

## Next steps
- **Run the full demo:** see docs/PROJECT_CONTEXT.md → Full demo runbook (requires K3s).
- **Understand the architecture:** see docs/PROJECT_CONTEXT.md → Architecture.
- **Contribute:** see docs/PROJECT_CONTEXT.md → Contributing.

---
**Time to completion:** ~10 min if you already have API keys; ~30 min with signup.
