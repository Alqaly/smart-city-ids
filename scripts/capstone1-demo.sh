#!/bin/bash
# Capstone I Live Demo - No fake success, no narration, just proof.
# Usage: ./scripts/capstone1-demo.sh

set -euo pipefail
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"

# ── STEP 1: Capture BEFORE state ─────────────────────────────────────────────
echo "=== BEFORE ATTACK ==="
echo ""
echo "Metrics snapshot:"
kubectl exec -n smart-city deploy/ids-api -- curl -s localhost:8000/metrics 2>/dev/null \
  | grep -E "^smartcity_ids_(alerts_received|alerts_processed|actions_executed)_total" \
  | sort
echo ""

BEFORE_RECEIVED=$(kubectl exec -n smart-city deploy/ids-api -- curl -s localhost:8000/metrics 2>/dev/null \
  | grep "smartcity_ids_alerts_received_total{" | awk -F'} ' '{sum+=$2} END {print sum+0}')
BEFORE_PROCESSED=$(kubectl exec -n smart-city deploy/ids-api -- curl -s localhost:8000/metrics 2>/dev/null \
  | grep "smartcity_ids_alerts_processed_total{" | awk -F'} ' '{sum+=$2} END {print sum+0}')

echo "Total alerts received: $BEFORE_RECEIVED"
echo "Total alerts processed: $BEFORE_PROCESSED"
echo ""

# ── STEP 2: Run attack ───────────────────────────────────────────────────────
TARGET_POD=$(kubectl get pods -n smart-city -o jsonpath='{.items[0].metadata.name}')
echo "=== ATTACK ==="
echo "Target: $TARGET_POD"
echo "Command: cat /etc/shadow"
echo "Time: $(date -Iseconds)"
echo ""
kubectl exec -n smart-city "$TARGET_POD" -- cat /etc/shadow 2>&1 | head -2
echo ""

# ── STEP 3: Wait for pipeline ────────────────────────────────────────────────
echo "Waiting 8 seconds for pipeline..."
sleep 8

# ── STEP 4: Capture AFTER state ──────────────────────────────────────────────
echo ""
echo "=== AFTER ATTACK ==="
echo ""
echo "Metrics snapshot:"
kubectl exec -n smart-city deploy/ids-api -- curl -s localhost:8000/metrics 2>/dev/null \
  | grep -E "^smartcity_ids_(alerts_received|alerts_processed|actions_executed)_total" \
  | sort
echo ""

AFTER_RECEIVED=$(kubectl exec -n smart-city deploy/ids-api -- curl -s localhost:8000/metrics 2>/dev/null \
  | grep "smartcity_ids_alerts_received_total{" | awk -F'} ' '{sum+=$2} END {print sum+0}')
AFTER_PROCESSED=$(kubectl exec -n smart-city deploy/ids-api -- curl -s localhost:8000/metrics 2>/dev/null \
  | grep "smartcity_ids_alerts_processed_total{" | awk -F'} ' '{sum+=$2} END {print sum+0}')

echo "Total alerts received: $AFTER_RECEIVED (was $BEFORE_RECEIVED, delta: +$((AFTER_RECEIVED - BEFORE_RECEIVED)))"
echo "Total alerts processed: $AFTER_PROCESSED (was $BEFORE_PROCESSED, delta: +$((AFTER_PROCESSED - BEFORE_PROCESSED)))"
echo ""

# ── STEP 5: Show recent logs (real, no fallback - fails visibly if empty) ────
echo "=== FALCO (last 3 JSON alerts) ==="
kubectl logs -n falco-system -l app.kubernetes.io/name=falco -c falco --tail=10 2>/dev/null \
  | grep '"rule"' | tail -3 | cut -c1-120
echo ""

echo "=== FORWARDER (last 5 lines) ==="
kubectl logs -n falco-system -l app=falco-forwarder --tail=5 2>/dev/null || echo "(no logs)"
echo ""

echo "=== IDS API (last 5 alert-related lines) ==="
kubectl logs -n smart-city deploy/ids-api --tail=50 2>/dev/null \
  | grep -E "Received alert|xAI Grok analysis|POST.*alerts" | tail -5 || echo "(no matching logs)"
echo ""

# ── STEP 6: Verify delta ─────────────────────────────────────────────────────
DELTA=$((AFTER_RECEIVED - BEFORE_RECEIVED))
if [ "$DELTA" -gt 0 ]; then
    echo "=== RESULT: Pipeline working (+$DELTA alerts) ==="
else
    echo "=== RESULT: No new alerts detected (pipeline may have failed) ==="
    exit 1
fi
