# Smoke tests & validation

Local and CI smoke tests to verify core functionality.

## Local smoke tests (manual)

### 1. Validate environment & tools

```bash
```bash

### 2. Validate docs

```bash
```bash

### 3. Try database migrations (optional, requires PostgreSQL)

```bash
export DATABASE_URL="postgres://user:pass@localhost:5432/smartcity_test"

make db-migrate
```bash

### 4. Run IDS API locally

```bash
cd services/ids-api/src

python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export GROQ_API_KEY="gsk_..." # or OPENAI_API_KEY
uvicorn main:app --host 0.0.0.0 --port 8000
```bash

### 5. Send a sample alert

In another terminal:

```bash
curl -X POST <http://localhost:8000/api/alerts> \

  -H "Content-Type: application/json" \
  -d '{
    "output": "Falco rule triggered: Unexpected process spawned",
    "priority": "Critical",
    "rule": "Unexpected process",
    "time": "2025-01-11T12:00:00Z",
    "output_fields": {
      "container.name": "traffic-camera-1",
      "proc.cmdline": "/bin/bash",
      "proc.user": "root"
    }
  }'
```bash

```json
{

  "alert_id": "...",
  "status": "processing",
  "analysis": {
    "summary": "...",
    "severity": 7,
    "threat_type": "...",
    "recommendations": [...],
    "automated_actions": [...]
  }
}
```bash

- `status` is `"processing"` or `"success"`.
- `analysis.severity` is 1–10.
- `analysis.threat_type` is populated.
- If severity >= 8, `automated_actions` includes `["isolate_pod"]`.

### 6. Run pytest smoke tests

```bash
```bash

Actual test runs:
- `test_post_alert_basic_flow()` — sends sample alert, checks HTTP 200 + valid JSON response.

### 7. Debug if needed

If a test fails, check:
- IDS API logs (in terminal where you started uvicorn).
- LLM API key is set and valid: `echo $GROQ_API_KEY` or `echo $OPENAI_API_KEY`.
- Alert JSON is valid: use a JSON validator or check IDS API startup logs.

## CI smoke tests (automatic)

Runs on every push and PR. Files:
- `.github/workflows/smoke-tests.yml` — runs pytest on `tests/smoke/test_smoke_api.py`.
- `.github/workflows/docs.yml` — runs `make docs-check`.

### What's tested

- Markdown linting (no style errors).
- Broken links (all links valid).
- API smoke test: alert ingestion + LLM analysis + valid response.

### To check CI status

- Go to [GitHub Actions](https://github.com/yourusername/smart-city-ids/actions).
- Check the latest workflows for smoke-tests and docs.
- If a workflow fails, click it to see error details.

## Smoke test results interpretation

| Result | Meaning | Action |
|--------|---------|--------|
| ✅ All tests pass | Core functionality works. | Ready to merge / demo. |
| ❌ Docs check fails | Markdown lint or broken link error. | Fix lint errors, verify links. |
| ❌ Smoke test fails | Alert processing or LLM integration issue. | Check IDS API logs, verify API key. |
| ⚠️ Partial failures | Some tests pass, some fail. | Review failed test output, fix specific issue. |

## Debugging failed tests

### If `make docs-check` fails

```bash

npx markdownlint-cli README.md docs/*.md
# Fix style issues (usually heading format, trailing spaces)

# Then re-run

make docs-check
```bash

```bash

pytest -vv tests/smoke/test_smoke_api.py
# Check IDS API logs (in terminal where uvicorn runs)

# Verify LLM API key: echo $GROQ_API_KEY

# Try running IDS API manually and posting an alert (step 5 above)

```bash

```bash

curl <http://localhost:8000/health>
# Check alert JSON is valid (use jq or a JSON validator)

# Check LLM API key is set

env | grep -E "GROQ|OPENAI"
# Check IDS API logs for parsing errors

```bash

- **make check** — ~2 sec
- **make docs-check** — ~5 sec
- **make smoke-test** — ~10 sec
- **curl alert POST** — ~2 sec (depends on LLM API latency, usually 1–3 sec)
- **Full local validation** — ~20 sec

## Next steps after smoke tests pass

- If running locally: ready for PR / code review.
- If running in CI: ready for merge (if all reviews pass).
- Before demo: run full demo with K3s (`./scripts/start-everything.sh`), see docs/PROJECT_CONTEXT.md.

---
**Last updated:** 2026-01-11
