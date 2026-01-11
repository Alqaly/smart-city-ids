#!/bin/bash
set -e

# CRITICAL: Set KUBECONFIG at the very top
export KUBECONFIG=/home/aka/.kube/config

echo "╔════════════════════════════════════════════════════════╗"
echo "║   SMART CITY IDS - COMPLETE DEPLOYMENT                ║"
echo "╚════════════════════════════════════════════════════════╝"

# Verify KUBECONFIG=/home/aka/.kube/config kubectl works
echo "Testing KUBECONFIG=/home/aka/.kube/config kubectl connection..."
if ! KUBECONFIG=/home/aka/.kube/config kubectl get nodes >/dev/null 2>&1; then
    echo "❌ KUBECONFIG=/home/aka/.kube/config kubectl cannot connect!"
    echo "Current KUBECONFIG: $KUBECONFIG"
    exit 1
fi
echo "✅ KUBECONFIG=/home/aka/.kube/config kubectl connected to cluster"
KUBECONFIG=/home/aka/.kube/config kubectl get nodes

# Load environment variables
if [ -f .env ]; then
    source .env
    echo "✅ Loaded .env file"
else
    echo "❌ .env file not found!"
    exit 1
fi

# 1. CREATE NAMESPACES
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1. Creating Namespaces"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

KUBECONFIG=/home/aka/.kube/config kubectl create namespace smart-city 2>/dev/null || echo "  ↳ smart-city already exists"
KUBECONFIG=/home/aka/.kube/config kubectl create namespace falco-system 2>/dev/null || echo "  ↳ falco-system already exists"
KUBECONFIG=/home/aka/.kube/config kubectl create namespace suricata-system 2>/dev/null || echo "  ↳ suricata-system already exists"
KUBECONFIG=/home/aka/.kube/config kubectl create namespace monitoring 2>/dev/null || echo "  ↳ monitoring already exists"

echo "✅ All namespaces ready"

# 2. CREATE SECRETS
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2. Creating Secrets"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

KUBECONFIG=/home/aka/.kube/config kubectl delete secret ids-secrets -n smart-city 2>/dev/null || true
KUBECONFIG=/home/aka/.kube/config kubectl create secret generic ids-secrets \
  --from-literal=groq-api-key="${GROQ_API_KEY}" \
  --from-literal=openai-api-key="${OPENAI_API_KEY}" \
  --namespace=smart-city

echo "✅ Secrets created"

# 3. CREATE CONFIG MAP FOR IDS CONFIG
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3. Creating IDS Configuration"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

KUBECONFIG=/home/aka/.kube/config kubectl delete configmap ids-config -n smart-city 2>/dev/null || true
KUBECONFIG=/home/aka/.kube/config kubectl create configmap ids-config \
  --from-literal=GROQ_MODEL="${GROQ_MODEL}" \
  --from-literal=OPENAI_MODEL="${OPENAI_MODEL}" \
  --from-literal=K8S_NAMESPACE="${K8S_NAMESPACE}" \
  --from-literal=FALCO_ENABLED="${FALCO_ENABLED}" \
  --from-literal=LOG_LEVEL="${LOG_LEVEL}" \
  --namespace=smart-city

echo "✅ IDS config created"

# 4. CREATE IDS APP CODE CONFIGMAP
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4. Creating IDS Application Code"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

KUBECONFIG=/home/aka/.kube/config kubectl delete configmap ids-app-code -n smart-city 2>/dev/null || true
KUBECONFIG=/home/aka/.kube/config kubectl create configmap ids-app-code \
  --from-file=main.py=services/ids-api/src/main.py \
  --from-file=config.py=services/ids-api/src/config.py \
  --from-file=llm_engine_groq.py=services/ids-api/src/llm_engine_groq.py \
  --from-file=k8s_automation.py=services/ids-api/src/k8s_automation.py \
  --from-file=requirements.txt=services/ids-api/src/requirements.txt \
  --namespace=smart-city

echo "✅ IDS application code created"

# 5. CREATE SERVICE ACCOUNT FOR IDS
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5. Creating RBAC for IDS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

KUBECONFIG=/home/aka/.kube/config kubectl apply -f - <<EOF
apiVersion: v1
kind: ServiceAccount
metadata:
  name: ids-service-account
  namespace: smart-city
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: ids-cluster-role
rules:
- apiGroups: [""]
  resources: ["pods", "services", "nodes", "namespaces"]
  verbs: ["get", "list", "watch", "delete"]
- apiGroups: ["apps"]
  resources: ["deployments", "replicasets"]
  verbs: ["get", "list", "watch", "patch", "update"]
- apiGroups: ["networking.k8s.io"]
  resources: ["networkpolicies"]
  verbs: ["get", "list", "create", "delete"]
- apiGroups: [""]
  resources: ["nodes"]
  verbs: ["patch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: ids-cluster-role-binding
subjects:
- kind: ServiceAccount
  name: ids-service-account
  namespace: smart-city
roleRef:
  kind: ClusterRole
  name: ids-cluster-role
  apiGroup: rbac.authorization.k8s.io
EOF

echo "✅ RBAC created"

# 6. DEPLOY IOT SIMULATOR
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "6. Deploying IoT Devices"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

KUBECONFIG=/home/aka/.kube/config kubectl apply -f iot-simulator/iot-configmap.yaml

echo "✅ IoT devices deployed"

# 7. DEPLOY MONITORING STACK
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "7. Deploying Monitoring Stack"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

KUBECONFIG=/home/aka/.kube/config kubectl apply -f k8s-manifests/prometheus-stack.yaml

echo "✅ Prometheus and Grafana deployed"

# 8. DEPLOY MQTT BROKER
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "8. Deploying MQTT Broker"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

KUBECONFIG=/home/aka/.kube/config kubectl apply -f k8s-manifests/mqtt-broker.yaml

echo "✅ MQTT broker deployed"

# 9. INSTALL FALCO VIA HELM
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "9. Installing Falco"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Add Falco Helm repo
KUBECONFIG=/home/aka/.kube/config helm repo add falcosecurity https://falcosecurity.github.io/charts 2>/dev/null || true
KUBECONFIG=/home/aka/.kube/config helm repo update

# Install Falco
KUBECONFIG=/home/aka/.kube/config helm upgrade --install falco falcosecurity/falco \
  --namespace falco-system \
  --set driver.kind=modern_ebpf \
  --set falco.json_output=true \
  --set falco.json_include_output_property=true \
  --wait

echo "✅ Falco installed"

# 10. DEPLOY FALCO FORWARDER
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "10. Deploying Falco Forwarder"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

KUBECONFIG=/home/aka/.kube/config kubectl apply -f k8s-manifests/falco-forwarder.yaml

echo "✅ Falco forwarder deployed"

# 11. DEPLOY SURICATA
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "11. Deploying Suricata"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

KUBECONFIG=/home/aka/.kube/config kubectl apply -f k8s-manifests/suricata-working.yaml
KUBECONFIG=/home/aka/.kube/config kubectl apply -f k8s-manifests/05-suricata-forwarder.yaml

echo "✅ Suricata deployed"

# 12. DEPLOY IDS API
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "12. Deploying IDS API"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

KUBECONFIG=/home/aka/.kube/config kubectl apply -f k8s-manifests/ids-api-LEGENDARY.yaml

echo "✅ IDS API deployed"

# 13. WAIT FOR PODS
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "13. Waiting for Pods to be Ready"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "Waiting for MQTT broker..."
KUBECONFIG=/home/aka/.kube/config kubectl wait --for=condition=ready pod -l app=mqtt-broker -n smart-city --timeout=120s || echo "  ↳ Timeout, but continuing..."

echo "Waiting for IoT devices..."
KUBECONFIG=/home/aka/.kube/config kubectl wait --for=condition=ready pod -l app=iot-device -n smart-city --timeout=120s || echo "  ↳ Timeout, but continuing..."

echo "Waiting for IDS API..."
KUBECONFIG=/home/aka/.kube/config kubectl wait --for=condition=ready pod -l app=ids-api -n smart-city --timeout=300s || echo "  ↳ Timeout, but continuing..."

echo "Waiting for monitoring stack..."
KUBECONFIG=/home/aka/.kube/config kubectl wait --for=condition=ready pod -l app=prometheus -n monitoring --timeout=120s || echo "  ↳ Timeout, but continuing..."
KUBECONFIG=/home/aka/.kube/config kubectl wait --for=condition=ready pod -l app=grafana -n monitoring --timeout=120s || echo "  ↳ Timeout, but continuing..."

echo ""
echo "╔════════════════════════════════════════════════════════╗"
echo "║              ✅ DEPLOYMENT COMPLETE!                   ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""
echo "📊 System Status:"
KUBECONFIG=/home/aka/.kube/config kubectl get pods -n smart-city
echo ""
KUBECONFIG=/home/aka/.kube/config kubectl get pods -n falco-system
echo ""
KUBECONFIG=/home/aka/.kube/config kubectl get pods -n suricata-system
echo ""
KUBECONFIG=/home/aka/.kube/config kubectl get pods -n monitoring
echo ""
echo "🌐 Access URLs:"
echo "   IDS API: http://localhost:8000"
echo "   Grafana: http://localhost:30030 (admin/admin123)"
echo "   Prometheus: http://localhost:30090"
echo ""
echo "🚀 Run './SHOW-EVERYTHING.sh' to verify everything is working!"
