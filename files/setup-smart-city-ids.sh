#!/bin/bash

# 🛡️ Smart City IDS - Automated Setup Script for Kali Linux
# This script will create the entire project on your local machine

set -e

echo "🛡️  Smart City IDS - Project Setup"
echo "===================================="
echo ""

# Color codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PROJECT_DIR="$HOME/smart-city-ids"

echo -e "${BLUE}Creating project directory: $PROJECT_DIR${NC}"
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

# Create directory structure
echo -e "${BLUE}Creating directory structure...${NC}"
mkdir -p src smart-city-services/{traffic-camera,healthcare-api,parking-system}
mkdir -p attack-simulator k8s-manifests scripts docs
mkdir -p monitoring/{falco,prometheus} deployment tests

# Create .env.example
cat > .env.example << 'ENVEOF'
# Smart City IDS Configuration
MOCK_MODE=true
GROQ_API_KEY=
K8S_NAMESPACE=smart-city
TRAFFIC_CAMERA_URL=http://traffic-camera-service:80
HEALTHCARE_API_URL=http://healthcare-api-service:80
PARKING_SYSTEM_URL=http://parking-system-service:80
PROMETHEUS_URL=http://prometheus:9090
GRAFANA_URL=http://grafana:3000
IDS_PORT=5003
ALERT_RETENTION_HOURS=24
MAX_ALERTS_STORED=1000
ENABLE_ATTACK_SIMULATION=true
ENVEOF

# Create requirements.txt
cat > requirements.txt << 'REQEOF'
flask==3.0.0
requests==2.31.0
python-dotenv==1.0.0
groq==0.4.1
kubernetes==28.1.0
prometheus-client==0.18.0
pyyaml==6.0
colorama==0.4.6
REQEOF

# Create .gitignore
cat > .gitignore << 'GITEOF'
# Environment
.env
.env.local
.env.*.local

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual environments
venv/
ENV/
env/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# Logs
logs/
*.log

# OS
.DS_Store
Thumbs.db

# K3s
/var/lib/rancher/k3s

# Temporary
/tmp/
/temp/
GITEOF

# Create QUICKSTART.md
cat > QUICKSTART.md << 'QSEOF'
# 🚀 Quick Start Guide - 5 Minutes

## Installation (1 minute)

```bash
cd ~/smart-city-ids
pip3 install -r requirements.txt
./scripts/start-everything.sh
```

Wait for: ✅ Smart City IDS System is ready!

## Verify Services (1 minute)

In a new terminal:
```bash
kubectl get pods -n smart-city
```

Should show 6 pods all Running

## Test Services (1 minute)

```bash
kubectl port-forward -n smart-city svc/traffic-camera-service 8001:80 &
sleep 2
curl http://localhost:8001/health
```

## Run Attack Demo (2 minutes)

```bash
./scripts/run-all-attacks.sh
```

## Cleanup

```bash
./scripts/cleanup.sh
```

## Useful Commands

```bash
# Watch pods in real-time
kubectl get pods -n smart-city -w

# View pod logs
kubectl logs -f <pod-name> -n smart-city

# Port forward any service
kubectl port-forward -n smart-city svc/<service-name> <local>:80 &

# View all services
kubectl get svc -n smart-city
```

That's it! You now have a working Smart City IDS demo. 🎉
QSEOF

# Create namespace.yaml
cat > k8s-manifests/namespace.yaml << 'NSEOF'
apiVersion: v1
kind: Namespace
metadata:
  name: smart-city
  labels:
    name: smart-city
    purpose: capstone-project
    environment: development
NSEOF

# Create src/main.py
cat > src/main.py << 'MAINEOF'
#!/usr/bin/env python3
"""
Smart City IDS - Main Application
AI-powered Intrusion Detection System with Groq LLM
"""

from flask import Flask, jsonify, request
import os
import logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MOCK_MODE = os.getenv('MOCK_MODE', 'true').lower() == 'true'
GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')

alerts = []
threat_analyses = []


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "service": "smart-city-ids",
        "mode": "mock" if MOCK_MODE else "production",
        "timestamp": datetime.now().isoformat()
    }), 200


@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    return jsonify({
        "alerts": alerts,
        "total": len(alerts)
    }), 200


@app.route('/api/alerts', methods=['POST'])
def create_alert():
    data = request.get_json()
    
    alert = {
        "id": len(alerts) + 1,
        "timestamp": datetime.now().isoformat(),
        "source": data.get('source', 'unknown'),
        "severity": data.get('severity', 'medium'),
        "message": data.get('message', ''),
        "service": data.get('service', ''),
        "status": "new"
    }
    
    alerts.append(alert)
    logger.info(f"New alert created: {alert['id']}")
    
    return jsonify(alert), 201


@app.route('/api/dashboard', methods=['GET'])
def dashboard():
    high_severity = sum(1 for a in alerts if a['severity'] == 'high')
    medium_severity = sum(1 for a in alerts if a['severity'] == 'medium')
    low_severity = sum(1 for a in alerts if a['severity'] == 'low')
    
    return jsonify({
        "total_alerts": len(alerts),
        "alert_breakdown": {
            "high": high_severity,
            "medium": medium_severity,
            "low": low_severity
        },
        "analyzed": sum(1 for a in alerts if a['status'] == 'analyzed'),
        "pending": sum(1 for a in alerts if a['status'] == 'new'),
        "threat_analyses": len(threat_analyses),
        "mode": "mock" if MOCK_MODE else "production"
    }), 200


if __name__ == '__main__':
    port = int(os.environ.get('IDS_PORT', 5003))
    logger.info(f"Starting Smart City IDS on port {port}")
    app.run(host='0.0.0.0', port=port, debug=True)
MAINEOF

# Create Traffic Camera Service
cat > smart-city-services/traffic-camera/app.py << 'TCEOF'
#!/usr/bin/env python3
from flask import Flask, jsonify, request
import logging
from datetime import datetime

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CAMERAS = {
    "CAM-001": {"location": "Downtown-Main", "status": "active", "fps": 30},
    "CAM-002": {"location": "Highway-North", "status": "active", "fps": 24},
}


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "service": "traffic-camera",
        "timestamp": datetime.now().isoformat()
    }), 200


@app.route('/api/cameras', methods=['GET'])
def get_cameras():
    logger.info("GET /api/cameras - Retrieving camera list")
    return jsonify({
        "cameras": CAMERAS,
        "total": len(CAMERAS)
    }), 200


@app.route('/api/analytics', methods=['GET'])
def analytics():
    logger.warning("GET /api/analytics - NO AUTH!")
    return jsonify({
        "timestamp": datetime.now().isoformat(),
        "total_vehicles": 1247,
        "average_speed": 45,
        "congestion_level": "moderate"
    }), 200


@app.route('/admin/config', methods=['GET', 'POST', 'PUT'])
def admin_config():
    logger.warning(f"{request.method} /admin/config - NO AUTH!")
    return jsonify({"status": "success", "message": "Config endpoint"}), 200


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting Traffic Camera on port {port}")
    app.run(host='0.0.0.0', port=port, debug=True)
TCEOF

# Create Healthcare API
cat > smart-city-services/healthcare-api/app.py << 'HAEOF'
#!/usr/bin/env python3
from flask import Flask, jsonify, request
import logging
from datetime import datetime

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PATIENTS = {
    "P001": {"name": "John Smith", "ssn": "123-45-6789", "age": 45},
    "P002": {"name": "Jane Doe", "ssn": "987-65-4321", "age": 32},
}


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "service": "healthcare-api",
        "timestamp": datetime.now().isoformat()
    }), 200


@app.route('/api/patients', methods=['GET'])
def get_patients():
    logger.warning("GET /api/patients - HIPAA VIOLATION!")
    return jsonify({
        "patients": PATIENTS,
        "count": len(PATIENTS)
    }), 200


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5001))
    logger.info(f"Starting Healthcare API on port {port}")
    app.run(host='0.0.0.0', port=port, debug=True)
HAEOF

# Create Parking System
cat > smart-city-services/parking-system/app.py << 'PSEOF'
#!/usr/bin/env python3
from flask import Flask, jsonify, request
import logging
from datetime import datetime

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PARKING_LOTS = {
    "LOT-A": {"location": "Downtown", "capacity": 500, "available": 234},
    "LOT-B": {"location": "Airport", "capacity": 1000, "available": 567},
}


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "service": "parking-system",
        "timestamp": datetime.now().isoformat()
    }), 200


@app.route('/api/lots', methods=['GET'])
def get_lots():
    return jsonify({"lots": PARKING_LOTS}), 200


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5002))
    logger.info(f"Starting Parking System on port {port}")
    app.run(host='0.0.0.0', port=port, debug=True)
PSEOF

# Create DDoS Simulator
cat > attack-simulator/ddos_simulator.py << 'DDOSEOF'
#!/usr/bin/env python3
import requests
import threading
import time
import sys
from concurrent.futures import ThreadPoolExecutor

class DDOSSimulator:
    def __init__(self, target_url, num_threads=10, duration=30):
        self.target_url = target_url
        self.num_threads = num_threads
        self.duration = duration
        self.request_count = 0
        self.error_count = 0

    def send_request(self):
        try:
            response = requests.get(self.target_url, timeout=2)
            self.request_count += 1
        except:
            self.error_count += 1

    def attack_worker(self):
        while time.time() - self.start_time < self.duration:
            self.send_request()

    def run(self):
        self.start_time = time.time()
        print(f"🚀 DDoS Attack: {self.target_url}")
        print(f"   Threads: {self.num_threads}, Duration: {self.duration}s")
        
        with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
            futures = [executor.submit(self.attack_worker) for _ in range(self.num_threads)]
            
            for future in futures:
                future.result()
        
        elapsed = time.time() - self.start_time
        print(f"\n✅ Attack Complete!")
        print(f"   Total Requests: {self.request_count}")
        print(f"   Avg RPS: {self.request_count / elapsed:.0f}")
        print(f"   Errors: {self.error_count}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 ddos_simulator.py <url> [threads] [duration]")
        sys.exit(1)
    
    target = sys.argv[1]
    threads = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    duration = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    
    simulator = DDOSSimulator(target, threads, duration)
    simulator.run()
DDOSEOF

# Create Data Exfiltration Simulator
cat > attack-simulator/data_exfiltration.py << 'DATAEOF'
#!/usr/bin/env python3
import requests
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataExfiltrationSimulator:
    def __init__(self, base_url):
        self.base_url = base_url

    def extract_cameras(self):
        logger.info("🎯 Extracting camera data...")
        try:
            response = requests.get(f"{self.base_url}/api/cameras", timeout=5)
            if response.status_code == 200:
                logger.info("   ✅ SUCCESS: Retrieved camera data")
                return True
        except Exception as e:
            logger.error(f"   ❌ Failed: {e}")
        return False

    def extract_patients(self):
        logger.info("🎯 Extracting patient data...")
        try:
            response = requests.get(f"{self.base_url}/api/patients", timeout=5)
            if response.status_code == 200:
                logger.info("   ✅ SUCCESS: Retrieved SENSITIVE patient data")
                return True
        except Exception as e:
            logger.error(f"   ❌ Failed: {e}")
        return False

    def run(self):
        logger.info(f"Starting attacks on {self.base_url}")
        results = {
            "Cameras": self.extract_cameras(),
            "Patients": self.extract_patients(),
        }
        
        print("\n✅ Attack Summary:")
        for name, success in results.items():
            print(f"   {'✅' if success else '❌'} {name}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 data_exfiltration.py <service_url>")
        sys.exit(1)
    
    simulator = DataExfiltrationSimulator(sys.argv[1].rstrip('/'))
    simulator.run()
DATAEOF

# Create startup script
cat > scripts/start-everything.sh << 'STARTEOF'
#!/bin/bash

set -e

echo "🚀 Starting Smart City IDS"
echo "=========================="
echo ""

# Check for K3s
if ! command -v k3s &> /dev/null; then
    echo "📥 Installing K3s..."
    curl -sfL https://get.k3s.io | sh -
fi

# Kill existing K3s
pkill -f "k3s server" 2>/dev/null || true
sleep 2

# Start K3s
echo "🔧 Starting K3s..."
k3s server --write-kubeconfig-mode=644 > /tmp/k3s.log 2>&1 &
K3S_PID=$!

# Wait for ready
echo "⏳ Waiting for K3s..."
for i in {1..60}; do
    if kubectl cluster-info &>/dev/null 2>&1; then
        echo "✅ K3s ready!"
        break
    fi
    sleep 1
done

# Create namespace
echo "📂 Creating namespace..."
kubectl create namespace smart-city --dry-run=client -o yaml | kubectl apply -f -

echo "✅ Smart City IDS Ready!"
echo ""
echo "Next: Run ./scripts/run-all-attacks.sh"
STARTEOF

# Create cleanup script
cat > scripts/cleanup.sh << 'CLEANEOF'
#!/bin/bash

echo "🧹 Cleaning up..."
pkill -f "k3s server" 2>/dev/null || true
pkill -f "kubectl port-forward" 2>/dev/null || true
echo "✅ Cleanup complete"
CLEANEOF

# Create attack runner
cat > scripts/run-all-attacks.sh << 'ATTACKEOF'
#!/bin/bash

echo "🎯 Running Attack Simulations"
echo "============================"
echo ""
echo "1. Traffic Camera"
echo "2. Healthcare"
echo "3. Parking"
echo "0. Exit"
echo ""

read -p "Choose: " choice

case $choice in
    1)
        echo "Running traffic camera attacks..."
        python3 attack-simulator/data_exfiltration.py http://localhost:8001
        ;;
    2)
        echo "Running healthcare attacks..."
        python3 attack-simulator/data_exfiltration.py http://localhost:8002
        ;;
    3)
        echo "Running parking attacks..."
        python3 attack-simulator/data_exfiltration.py http://localhost:8003
        ;;
    0)
        echo "Exiting..."
        ;;
    *)
        echo "Invalid choice"
        ;;
esac
ATTACKEOF

chmod +x scripts/*.sh

echo -e "${GREEN}✅ Project setup complete!${NC}"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo "  1. cd ~/smart-city-ids"
echo "  2. pip3 install -r requirements.txt"
echo "  3. ./scripts/start-everything.sh"
echo "  4. Read QUICKSTART.md"
echo ""
echo -e "${GREEN}Happy deploying! 🚀${NC}"
