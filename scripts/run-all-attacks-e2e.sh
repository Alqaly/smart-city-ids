#!/usr/bin/env bash
set -euo pipefail

echo "ERROR: scripts/run-all-attacks-e2e.sh was removed (it ran synthetic scenarios via /api/attacks/*)." >&2
echo "Use live attacks only:" >&2
echo "  bash scripts/run-live-attacks.sh --duration 60" >&2
exit 2
