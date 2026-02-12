# Legacy Project Context Summary

This file consolidates older project context/status documentation for historical reference.

## Historical Snapshot

- Project scope: LLM-driven IDS for smart city emulation on K3s.
- Core pipeline: Falco/Suricata alerts -> IDS API -> LLM analysis -> K8s actions.
- Early gaps documented: missing metrics, missing Suricata integration, Prometheus/Grafana not wired (later fixed).
- Emulation framing: controlled IIoT emulation, not full city simulation.

## Key Historical Notes

- Early docs referenced Groq as the primary LLM; later migrated to xAI Grok-4.
- Initial deployment used in-memory storage before PostgreSQL persistence was added.
- Prometheus and Grafana integration matured after infrastructure fixes.

## Superseded Files

- docs/_archive/specs/PROJECT_CONTEXT.md
- docs/_archive/specs/PROJECT_DOCUMENTATION.md
- docs/_archive/specs/PROJECT_STATUS.md
