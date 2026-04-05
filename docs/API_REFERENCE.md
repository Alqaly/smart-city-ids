# API Reference

Current high-level API reference for the Smart City IDS.

This document covers the main active endpoints. For exact route inventory, verify against the live API and current `services/ids-api/src/api/*.py` files.

## Base URLs

Direct local NodePort:
- `http://localhost:30800`

Stable forwarded access:
- `http://localhost:8000`

## Health and metrics

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | overall service health, storage mode, component state |
| `GET` | `/api/metrics` | application metrics in JSON form |
| `GET` | `/metrics` | Prometheus text metrics |
| `GET` | `/api/pipeline-overview` | overview counters used by the dashboard |

## Alerts

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/alerts` | list processed alerts |
| `GET` | `/api/alerts/live` | server-sent event stream for live alerts |
| `POST` | `/api/alerts` | authenticated alert ingestion path |
| `POST` | `/api/alerts/internal` | internal forwarder ingestion path |
| `POST` | `/api/alerts/{id}/reanalyze` | rerun analysis for a stored alert |

Notes:
- `/api/alerts/internal` is for internal detector/forwarder traffic
- alert history may hide legacy broken rows by default

## Authentication

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/auth/login` | obtain bearer token |

Common local default:
- `admin / admin`

## Governance

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/governance/status` | current mode and governance metrics |
| `POST` | `/api/governance/mode` | set `manual`, `assisted`, or `autonomous` |
| `GET` | `/api/governance/pending` | list pending actions |
| `POST` | `/api/governance/approve/{id}` | approve a pending action |
| `POST` | `/api/governance/reject/{id}` | reject a pending action |
| `GET` | `/api/governance/history` | governance action history |

## LLM

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/llm/diagnostics` | current provider status and summary |
| `GET` | `/api/llm/status` | authenticated LLM status view |
| `POST` | `/api/llm/test/{provider}` | provider test/probe |
| `POST` | `/api/llm/retry-all` | reset provider runtime failure state |
| `POST` | `/api/llm/reset-cooldown` | clear cooldown state |
| `GET` | `/api/llm/providers/comparison` | provider comparison view |
| `GET` | `/api/metrics/llm-usage?window=today` | DB-backed provider usage and cost |

Important:
- strict provider diagnostics use `?strict=true`
- DB-backed usage counts real alert-analysis calls only
- manual provider tests do not increment those usage totals

## IoT

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/iot/devices` | hybrid device inventory |
| `GET` | `/api/iot/telemetry` | telemetry snapshot |
| `POST` | `/api/iot/sensor` | telemetry ingest |
| `POST` | `/api/iot/devices/register` | logical device registration |
| `POST` | `/api/iot/devices/heartbeat` | logical device heartbeat |
| `GET` | `/api/iot/events` | recent IoT events |

## Audit and operator views

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/audit/trace/{trace_id}` | correlated trace for a specific alert or action |
| `GET` | `/api/operator/dashboard` | dashboard summary data |
| `GET` | `/api/operator/incidents` | incident list |

## AI analyst chat

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/analyst/session` | start a new chat session |
| `POST` | `/api/analyst/chat` | send message to AI analyst (rate-limited, supports provider selection) |
| `GET` | `/api/analyst/tools` | list available analyst actions |
| `POST` | `/api/analyst/action/submit` | execute analyst-approved action |
| `POST` | `/api/analyst/action/pending-decision` | respond to pending governance approval |
| `POST` | `/api/analyst/quick-analyze` | one-off alert analysis without session |

## Live checks

```bash
curl -s http://localhost:30800/health | jq .
curl -s http://localhost:30800/api/alerts?limit=5 | jq .
curl -s http://localhost:30800/api/iot/devices | jq .
curl -s http://localhost:30800/api/llm/diagnostics | jq .
```

## Truth boundary

- This document is a maintained operational reference, not a frozen exhaustive route ledger.
- For a full point-in-time route inventory, inspect the current API modules in the source tree.
