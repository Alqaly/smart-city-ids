# Smart City IDS - Validation Checklist

Use this checklist to verify a successful deployment.

---

## Pre-Deployment Checks

- [ ] **OS Requirements**
  ```bash
  cat /etc/os-release | grep -E "^(NAME|VERSION)="
  # Should show Ubuntu 20.04+ or similar
  ```

- [ ] **Memory Available**
  ```bash
  free -h | grep Mem
  # Should show at least 4GB total
  ```

- [ ] **Disk Space**
  ```bash
  df -h / | awk 'NR==2{print $4}'
  # Should show at least 20GB free
  ```

- [ ] **API Keys Configured**
  ```bash
  # Check .env exists and has keys
  grep -E "^(XAI_API_KEY|OPENAI_API_KEY)=" .env 2>/dev/null | wc -l
  # Should be at least 1
  ```

---

## Post-Deployment Checks

### Kubernetes Cluster

- [ ] **K3s Running**
  ```bash
  sudo systemctl status k3s | grep Active
  # Should show: active (running)
  ```

- [ ] **Nodes Ready**
  ```bash
  kubectl get nodes
  # All nodes should show Ready
  ```

- [ ] **Namespaces Created**
  ```bash
  kubectl get namespaces | grep -E "(smart-city|monitoring)"
  # Should show both namespaces
  ```

### Core Services

- [ ] **All Pods Running**
  ```bash
  kubectl get pods -n smart-city
  # All pods should show Running (1/1)
  ```

- [ ] **IDS API Health**
  ```bash
  NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
  curl -s http://${NODE_IP}:30800/health | jq .status
  # Should return "healthy"
  ```

- [ ] **PostgreSQL Connected**
  ```bash
  kubectl exec -n smart-city -l app=postgres -- psql -U idsuser -d idsdb -c "SELECT COUNT(*) FROM alerts;" 2>/dev/null
  # Should return a number
  ```

### Monitoring Stack

- [ ] **Prometheus Running**
  ```bash
  kubectl get pods -n monitoring -l app=prometheus
  # Should show Running
  ```

- [ ] **Grafana Accessible**
  ```bash
  curl -s http://${NODE_IP}:30300/api/health | jq .database
  # Should return "ok"
  ```

- [ ] **Metrics Scraping**
  ```bash
  curl -s http://${NODE_IP}:31701/api/v1/targets | jq '.data.activeTargets | length'
  # Should return number > 0
  ```

### LLM Integration

- [ ] **LLM Connection Test**
  ```bash
  curl -s http://${NODE_IP}:30800/health | jq '.components'
  # Should show xai_grok4 or openai as "connected"
  ```

---

## Functional Tests

### Alert Processing

- [ ] **Submit Test Alert**
  ```bash
  curl -X POST http://${NODE_IP}:30800/api/alerts \
    -H "Content-Type: application/json" \
    -d '{
      "source": "validation-test",
      "rule": "Validation Test Alert",
      "priority": "Warning",
      "output": "This is a validation test alert",
      "output_fields": {"container.name": "test"}
    }'
  # Should return success with analysis
  ```

- [ ] **View Stored Alerts**
  ```bash
  curl -s http://${NODE_IP}:30800/api/alerts?limit=5 | jq '.[0].rule'
  # Should show "Validation Test Alert"
  ```

### Attack Simulation

- [ ] **DDoS Simulation (Optional)**
  ```bash
  python attack-simulator/ddos_simulator.py http://${NODE_IP}:30800 2 5
  # Should complete without errors
  ```

---

## Dashboard Verification

- [ ] **Access Grafana**
  - Open: http://NODE_IP:30300
  - Login: admin / admin
  
- [ ] **Dashboards Loaded**
  - Navigate to Dashboards
  - Verify "Smart City IDS" dashboard exists
  
- [ ] **Data Displaying**
  - Check alerts panel shows data
  - Check metrics are updating

---

## Cleanup Verification (If Needed)

- [ ] **Clean Uninstall**
  ```bash
  ./scripts/cleanup.sh
  kubectl get namespaces | grep -E "(smart-city|monitoring)"
  # Should return nothing
  ```

---

## Common Issues & Fixes

| Issue | Check | Fix |
|-------|-------|-----|
| Pods pending | `kubectl describe pod <name> -n smart-city` | Check node resources |
| API key error | `kubectl get secret ids-api-secrets -n smart-city` | Recreate secret |
| LLM timeout | Check xAI/OpenAI status | Wait or use fallback |
| Metrics missing | `kubectl logs -n smart-city -l app=ids-api` | Check for errors |

---

## Validation Complete

If all checks pass:

✅ **System is ready for demonstration**

Record deployment details:
```bash
echo "Deployed: $(date)"
echo "K3s Version: $(k3s --version)"
echo "Node IP: ${NODE_IP}"
echo "IDS API: http://${NODE_IP}:30800"
echo "Grafana: http://${NODE_IP}:30300"
```

---

*For troubleshooting, see [docs/OPERATIONS.md](docs/OPERATIONS.md)*
