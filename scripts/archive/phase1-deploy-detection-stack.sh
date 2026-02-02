#!/bin/bash
# PHASE 1: Deploy Detection Stack (Suricata + Prometheus + Grafana)
# This script deploys the complete monitoring and detection infrastructure

set -e

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  PHASE 1: Deploy Detection Stack                              ║"
echo "║  (Suricata + Prometheus + Grafana)                            ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if K3s is running
echo "[1/6] Checking K3s cluster..."
if ! kubectl cluster-info &> /dev/null; then
    echo -e "${RED}❌ K3s cluster is not running${NC}"
    echo "Please start K3s first: sudo systemctl start k3s"
    exit 1
fi
echo -e "${GREEN}✅ K3s cluster is running${NC}"
echo ""

# Create monitoring namespace
echo "[2/6] Creating monitoring namespace..."
if kubectl get namespace monitoring &> /dev/null; then
    echo "    monitoring namespace already exists"
else
    kubectl create namespace monitoring
fi
echo -e "${GREEN}✅ Monitoring namespace ready${NC}"
echo ""

# Deploy Suricata
echo "[3/6] Deploying Suricata (Network IDS)..."
cat << 'EOF' | kubectl apply -f -
---
# Suricata ConfigMap
apiVersion: v1
kind: ConfigMap
metadata:
  name: suricata-config
  namespace: monitoring
data:
  suricata.yaml: |
    %YAML 1.1
    ---
    
    af-packet:
      - interface: any
        cluster-id: 99
        cluster-type: cluster_flow
        defrag: yes

    outputs:
      - eve-log:
          enabled: yes
          filetype: regular
          filename: /var/log/suricata/eve.json
          types:
            - alert:
                payload: yes
                payload-buffer-size: 4kb
                payload-printable: yes
                packet: yes
                metadata: yes
            - anomaly:
                enabled: yes
            - http:
                extended: yes
            - dns:
                enabled: yes

---
# Suricata Deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: suricata
  namespace: monitoring
  labels:
    app: suricata
spec:
  replicas: 1
  selector:
    matchLabels:
      app: suricata
  template:
    metadata:
      labels:
        app: suricata
    spec:
      hostNetwork: true
      dnsPolicy: ClusterFirstWithHostNet
      containers:
      - name: suricata
        image: jasonish/suricata:6.0.13
        imagePullPolicy: IfNotPresent
        command: ["suricata"]
        args: ["-c", "/etc/suricata/suricata.yaml", "-i", "any"]
        securityContext:
          runAsUser: 0
          capabilities:
            add:
              - NET_ADMIN
              - SYS_NICE
        volumeMounts:
        - name: config
          mountPath: /etc/suricata
        - name: logs
          mountPath: /var/log/suricata
        resources:
          requests:
            cpu: 500m
            memory: 512Mi
          limits:
            cpu: 1000m
            memory: 1Gi
      volumes:
      - name: config
        configMap:
          name: suricata-config
      - name: logs
        emptyDir: {}

---
# Suricata Service
apiVersion: v1
kind: Service
metadata:
  name: suricata
  namespace: monitoring
spec:
  selector:
    app: suricata
  ports:
  - name: syslog
    port: 514
    protocol: UDP
  type: ClusterIP
EOF

echo -e "${GREEN}✅ Suricata deployed${NC}"
echo ""

# Deploy Prometheus
echo "[4/6] Deploying Prometheus (Metrics Collection)..."
cat << 'EOF' | kubectl apply -f -
---
# Prometheus ConfigMap
apiVersion: v1
kind: ConfigMap
metadata:
  name: prometheus-config
  namespace: monitoring
data:
  prometheus.yml: |
    global:
      scrape_interval: 15s
      evaluation_interval: 15s
    
    scrape_configs:
      # Scrape IDS API metrics
      - job_name: 'smart-city-ids'
        static_configs:
          - targets: ['localhost:8000']
        metrics_path: '/api/metrics'
        scrape_interval: 10s

      # Scrape Kubernetes API server
      - job_name: 'kubernetes-apiservers'
        kubernetes_sd_configs:
          - role: endpoints
        scheme: https
        tls_config:
          ca_file: /var/run/secrets/kubernetes.io/serviceaccount/ca.crt
        bearer_token_file: /var/run/secrets/kubernetes.io/serviceaccount/token
        relabel_configs:
          - source_labels: [__meta_kubernetes_namespace, __meta_kubernetes_service_name, __meta_kubernetes_endpoint_port_name]
            action: keep
            regex: default;kubernetes;https

---
# Prometheus Deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: prometheus
  namespace: monitoring
spec:
  replicas: 1
  selector:
    matchLabels:
      app: prometheus
  template:
    metadata:
      labels:
        app: prometheus
    spec:
      serviceAccountName: prometheus
      containers:
      - name: prometheus
        image: prom/prometheus:latest
        imagePullPolicy: IfNotPresent
        args:
          - "--config.file=/etc/prometheus/prometheus.yml"
          - "--storage.tsdb.path=/prometheus"
          - "--web.console.libraries=/usr/share/prometheus/console_libraries"
          - "--web.console.templates=/usr/share/prometheus/consoles"
        ports:
        - containerPort: 9090
        volumeMounts:
        - name: config
          mountPath: /etc/prometheus
        - name: storage
          mountPath: /prometheus
        resources:
          requests:
            cpu: 250m
            memory: 512Mi
          limits:
            cpu: 500m
            memory: 1Gi
      volumes:
      - name: config
        configMap:
          name: prometheus-config
      - name: storage
        emptyDir: {}

---
# Prometheus Service
apiVersion: v1
kind: Service
metadata:
  name: prometheus
  namespace: monitoring
spec:
  selector:
    app: prometheus
  ports:
  - port: 9090
    targetPort: 9090
  type: ClusterIP

---
# Prometheus ServiceAccount
apiVersion: v1
kind: ServiceAccount
metadata:
  name: prometheus
  namespace: monitoring

---
# Prometheus ClusterRole
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: prometheus
rules:
- apiGroups: [""]
  resources:
  - nodes
  - nodes/proxy
  - services
  - endpoints
  - pods
  verbs: ["get", "list", "watch"]
- apiGroups: ["extensions"]
  resources:
  - ingresses
  verbs: ["get", "list", "watch"]

---
# Prometheus ClusterRoleBinding
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: prometheus
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: prometheus
subjects:
- kind: ServiceAccount
  name: prometheus
  namespace: monitoring
EOF

echo -e "${GREEN}✅ Prometheus deployed${NC}"
echo ""

# Deploy Grafana
echo "[5/6] Deploying Grafana (Visualization)..."
cat << 'EOF' | kubectl apply -f -
---
# Grafana ConfigMap - Datasources
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-datasources
  namespace: monitoring
data:
  prometheus.yaml: |
    apiVersion: 1
    datasources:
    - name: Prometheus
      type: prometheus
      access: proxy
      url: http://prometheus:9090
      isDefault: true
      editable: true

---
# Grafana Deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: grafana
  namespace: monitoring
  labels:
    app: grafana
spec:
  replicas: 1
  selector:
    matchLabels:
      app: grafana
  template:
    metadata:
      labels:
        app: grafana
    spec:
      containers:
      - name: grafana
        image: grafana/grafana:latest
        imagePullPolicy: IfNotPresent
        ports:
        - containerPort: 3000
        env:
        - name: GF_SECURITY_ADMIN_PASSWORD
          value: "admin"
        - name: GF_INSTALL_PLUGINS
          value: ""
        volumeMounts:
        - name: datasources
          mountPath: /etc/grafana/provisioning/datasources
        - name: storage
          mountPath: /var/lib/grafana
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 250m
            memory: 512Mi
      volumes:
      - name: datasources
        configMap:
          name: grafana-datasources
      - name: storage
        emptyDir: {}

---
# Grafana Service
apiVersion: v1
kind: Service
metadata:
  name: grafana
  namespace: monitoring
  labels:
    app: grafana
spec:
  type: NodePort
  ports:
  - port: 3000
    targetPort: 3000
    nodePort: 30300
  selector:
    app: grafana
EOF

echo -e "${GREEN}✅ Grafana deployed${NC}"
echo ""

# Verify deployments
echo "[6/6] Verifying all pods are running..."
echo ""
sleep 5

echo "Checking pod status..."
kubectl get pods -n monitoring

echo ""
echo "Waiting for pods to be ready (this may take 1-2 minutes)..."
kubectl wait --for=condition=ready pod -l app=suricata -n monitoring --timeout=120s 2>/dev/null || echo "Suricata still starting..."
kubectl wait --for=condition=ready pod -l app=prometheus -n monitoring --timeout=120s 2>/dev/null || echo "Prometheus still starting..."
kubectl wait --for=condition=ready pod -l app=grafana -n monitoring --timeout=120s 2>/dev/null || echo "Grafana still starting..."

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  ✅ PHASE 1 COMPLETE: Detection Stack Deployed                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "📊 Deployed Services:"
echo "  • Suricata (Network IDS)         - Monitoring network traffic"
echo "  • Prometheus (Metrics)            - Collecting system metrics"
echo "  • Grafana (Dashboard)             - Visualizing metrics"
echo ""
echo "🌐 Access Points:"
echo "  • Grafana Dashboard:    http://localhost:30300  (admin/admin)"
echo "  • Prometheus Console:   http://localhost:9090"
echo "  • Suricata Logs:        kubectl logs -n monitoring -f deployment/suricata"
echo ""
echo "📈 Next Steps:"
echo "  1. Access Grafana at http://localhost:30300"
echo "  2. Add Prometheus datasource (already configured)"
echo "  3. Create dashboards for real-time monitoring"
echo "  4. Start Phase 2: Create Suricata Forwarder"
echo ""
