# Smart City IDS Operator

Kubernetes operator that automates security threat response, using Kopf and a custom ThreatResponse CRD.

## Features
- Watches for ThreatResponse resources (CRD)
- Validates LLM recommendations and target pods
- Executes security actions (e.g., pod isolation)
- Updates status and conditions
- Designed for K3s/Kubernetes 1.28+

## Quickstart

1. **Install CRD and RBAC:**
   ```sh
   kubectl apply -f ../../k8s-manifests/threat-response-crd.yaml
   kubectl apply -f ../../k8s-manifests/operator-rbac.yaml
   ```
2. **Build and run the operator:**
   ```sh
   cd services/ids-operator
   docker build -t ids-operator:dev .
   docker run --rm -it --network host \
     -v ~/.kube/config:/root/.kube/config:ro \
     ids-operator:dev
   ```
3. **Test with a ThreatResponse resource:**
   ```sh
   kubectl apply -f sample-threatresponse.yaml
   ```

## Project Structure
- `src/handlers.py` — Kopf event handlers
- `requirements.txt` — Python dependencies
- `Dockerfile` — Operator container
- `tests/unit/` — Unit tests
- `tests/integration/` — Integration tests
