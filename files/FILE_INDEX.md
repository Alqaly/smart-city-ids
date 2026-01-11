# 📑 Smart City IDS - Complete File Index & Navigation

## 🗺️ Quick Navigation Guide

### For First-Time Users
1. Start here: **`QUICKSTART.md`** (5-minute setup)
2. Then read: **`README.md`** (comprehensive guide)
3. For demo: **`docs/demo-guide.md`** (presentation script)

### For Developers
1. Architecture: **`README.md`** (section 2)
2. Code: **`src/main.py`**, **`smart-city-services/*`**
3. Deployment: **`k8s-manifests/`**
4. Scripts: **`scripts/`**

### For Presenters
1. Guide: **`docs/demo-guide.md`** (complete 15-min script)
2. Status: **`PROJECT_STATUS.md`** (metrics & highlights)
3. Demo: **`scripts/run-all-attacks.sh`** (interactive menu)

---

## 📄 Documentation Files (4 files)

### 1. **README.md** (15KB, 200+ lines)
**Purpose**: Complete project reference  
**Contains**:
- Project overview & problem statement
- Architecture explanation
- File structure breakdown
- Service descriptions (Traffic Camera, Healthcare, Parking)
- Kubernetes setup guide
- kubectl commands explained
- Common issues & troubleshooting
- Learning resources

**When to Use**: For comprehensive understanding of the system

---

### 2. **QUICKSTART.md** (3KB, 70+ lines)
**Purpose**: Get started in 5 minutes  
**Contains**:
- Installation (1 minute)
- Verification (1 minute)
- Service testing (1 minute)
- Attack demo (2 minutes)
- Useful commands
- Quick troubleshooting

**When to Use**: When you want to try it immediately

---

### 3. **docs/demo-guide.md** (20KB, 500+ lines)
**Purpose**: Complete presentation guide  
**Contains**:
- End-to-end demo flow (15 minutes)
- Step-by-step walkthrough
- Talking points for different audiences
- Demo variations (5, 10, 15 minute versions)
- Key metrics to show
- Troubleshooting during demo
- Q&A preparation
- Pro tips for presenters

**When to Use**: Before giving a presentation

---

### 4. **PROJECT_STATUS.md** (10KB, 250+ lines)
**Purpose**: Project status & file summary  
**Contains**:
- Completion status (100%)
- File listings with descriptions
- Code statistics
- Learning outcomes
- Future enhancements
- Success criteria (all met)

**When to Use**: To understand what's been delivered

---

### 5. **DELIVERY_SUMMARY.md** (14KB, 350+ lines)
**Purpose**: Executive summary & highlights  
**Contains**:
- Executive summary
- Project metrics (3,125 lines of code)
- What you get (checklist)
- Getting started (3 steps)
- File manifest
- Key achievements
- Educational value
- System architecture
- Performance metrics
- Demo scenarios
- Innovation highlights
- Use cases
- Next steps

**When to Use**: For a quick overview

---

## 🐍 Python Code Files (8 files)

### Core Application

#### **src/main.py** (250+ lines)
**Purpose**: Main IDS application  
**Language**: Python (FastAPI/Flask)  
**Features**:
- Alert collection & storage
- LLM integration (Groq API)
- Mock mode for testing
- 7 REST API endpoints
- Real-time dashboard
- Simulation tools

**Endpoints**:
```
GET  /health               - Service status
POST /api/alerts           - Create alert
GET  /api/alerts           - List all alerts
POST /api/analyze/<id>     - Analyze alert with LLM
GET  /api/analyses         - Get all analyses
GET  /api/dashboard        - Summary dashboard
POST /api/simulate-alert   - Create simulated alert
GET  /api/config           - System configuration
```

**Dependencies**: flask, groq, python-dotenv

**Run**: `python3 src/main.py`  
**Port**: 5003

---

### Smart City Services (3 files)

#### **smart-city-services/traffic-camera/app.py** (150+ lines)
**Purpose**: Traffic monitoring service (intentionally vulnerable)  
**Language**: Python (Flask)  
**Features**:
- Camera management
- Traffic analytics
- Admin configuration
- No authentication (VULNERABLE)
- No rate limiting (VULNERABLE)

**Endpoints**:
```
GET  /health               - Service status
GET  /api/cameras          - Camera list (NO AUTH!)
GET  /api/camera/<id>/stream - Stream URL
GET  /api/analytics        - Traffic analytics (NO AUTH!)
POST /admin/config         - Config modification (NO AUTH! 🚨)
GET  /api/status          - System status
```

**Run**: `python3 smart-city-services/traffic-camera/app.py`  
**Port**: 5000  
**Vulnerabilities**: No auth, exposed data, modifiable config

---

#### **smart-city-services/healthcare-api/app.py** (150+ lines)
**Purpose**: Healthcare data management (intentionally vulnerable)  
**Language**: Python (Flask)  
**Features**:
- Patient data management
- Prescription handling
- Admin logs
- HIPAA violations (VULNERABLE)
- No input validation (VULNERABLE)

**Endpoints**:
```
GET  /health              - Service status
GET  /api/patients        - Patient list (HIPAA VIOLATION!)
GET  /api/patient/<id>    - Individual patient (NO AUTH!)
POST /api/prescriptions/<id> - Add prescription (NO VALIDATION!)
GET  /api/prescriptions/<id> - Get prescriptions
GET  /admin/logs          - Admin logs (EXPOSED!)
```

**Run**: `python3 smart-city-services/healthcare-api/app.py`  
**Port**: 5001  
**Vulnerabilities**: No auth, exposed PII, data leaks

---

#### **smart-city-services/parking-system/app.py** (150+ lines)
**Purpose**: Parking lot management (intentionally vulnerable)  
**Language**: Python (Flask)  
**Features**:
- Parking lot management
- Payment processing
- Transaction tracking
- Credit card logging (PCI-DSS VIOLATION!)
- No authentication (VULNERABLE)

**Endpoints**:
```
GET  /health              - Service status
GET  /api/lots            - Available lots
POST /api/lot/<id>/reserve - Reserve spot
POST /api/payment         - Process payment (LOGS CARD DATA!)
GET  /api/transactions    - View all transactions (NO AUTH!)
GET  /admin/system-status - Admin panel (NO AUTH!)
```

**Run**: `python3 smart-city-services/parking-system/app.py`  
**Port**: 5002  
**Vulnerabilities**: Card data logging, exposed payments, no auth

---

### Attack Simulation Tools (2 files)

#### **attack-simulator/ddos_simulator.py** (200+ lines)
**Purpose**: DDoS attack generator  
**Language**: Python  
**Features**:
- Configurable threads (1-100+)
- Configurable duration
- Real-time RPS monitoring
- Success/failure tracking
- Professional reporting

**Usage**:
```bash
python3 attack-simulator/ddos_simulator.py <url> [threads] [duration]

Examples:
python3 attack-simulator/ddos_simulator.py http://localhost:8001/api/cameras 20 30
python3 attack-simulator/ddos_simulator.py http://localhost:8001/health 50 60
```

**Output**: Attack metrics, RPS, success rate

**Dependencies**: requests, threading, concurrent.futures

---

#### **attack-simulator/data_exfiltration.py** (200+ lines)
**Purpose**: Data theft & unauthorized access simulator  
**Language**: Python  
**Features**:
- Camera data extraction
- Admin config modification
- Patient data theft (HIPAA violation)
- Payment data exfiltration
- Automated attack scenarios

**Usage**:
```bash
python3 attack-simulator/data_exfiltration.py <service_url>

Examples:
python3 attack-simulator/data_exfiltration.py http://localhost:8001
python3 attack-simulator/data_exfiltration.py http://localhost:8002
```

**Attacks Performed**:
1. Camera data extraction
2. Analytics retrieval
3. Admin config modification
4. Patient data theft
5. Payment data access

**Dependencies**: requests, json, logging

---

## ☸️ Kubernetes Configuration Files (2 files)

### **k8s-manifests/namespace.yaml**
**Purpose**: Create isolated namespace  
**Type**: Kubernetes Namespace  
**Contains**:
- Namespace definition: `smart-city`
- Labels for organization
- Metadata

**Apply**: `kubectl apply -f k8s-manifests/namespace.yaml`

---

### **k8s-manifests/services-no-build.yaml** (350+ lines)
**Purpose**: Deploy all services  
**Type**: Kubernetes Deployments & Services  
**Contains**:

#### 3 Deployments:
1. **traffic-camera**
   - 2 replicas
   - Image: python:3.9-slim
   - Port: 5000
   - 256MB memory limit

2. **healthcare-api**
   - 2 replicas
   - Image: python:3.9-slim
   - Port: 5001
   - 256MB memory limit

3. **parking-system**
   - 2 replicas
   - Image: python:3.9-slim
   - Port: 5002
   - 256MB memory limit

#### 3 Services:
1. **traffic-camera-service** (ClusterIP)
2. **healthcare-api-service** (ClusterIP)
3. **parking-system-service** (ClusterIP)

**Apply**: `kubectl apply -f k8s-manifests/services-no-build.yaml`

---

## 🛠️ Automation Scripts (3 files)

### **scripts/start-everything.sh** (200+ lines)
**Purpose**: Automated cluster startup  
**Type**: Bash script  
**Features**:
- Auto-detects K3s
- Installs if needed (no manual steps)
- Starts Kubernetes cluster
- Creates namespace
- Creates ConfigMaps
- Deploys services
- Waits for readiness
- Shows final status

**Usage**:
```bash
./scripts/start-everything.sh
```

**Time**: ~2 minutes  
**Output**: Cluster status, pod list, service info

**What it Does**:
1. Checks for K3s (installs if missing)
2. Kills any existing K3s processes
3. Starts K3s server
4. Waits for cluster ready (max 60s)
5. Creates namespace
6. Creates ConfigMaps (code)
7. Deploys services
8. Waits for pods ready
9. Shows status summary

---

### **scripts/run-all-attacks.sh** (400+ lines)
**Purpose**: Interactive attack simulation runner  
**Type**: Bash script  
**Features**:
- Interactive menu
- 6 different attack scenarios
- Automatic port-forwarding
- Colored output
- Detailed reporting
- Easy flow

**Usage**:
```bash
./scripts/run-all-attacks.sh          # Interactive menu
./scripts/run-all-attacks.sh 1        # Traffic camera attacks
./scripts/run-all-attacks.sh 2        # Healthcare attacks
./scripts/run-all-attacks.sh 3        # Parking attacks
./scripts/run-all-attacks.sh 4        # DDoS attack
./scripts/run-all-attacks.sh 5        # Data exfiltration
./scripts/run-all-attacks.sh 6        # All attacks
```

**Menu Options**:
1. Traffic Camera Attacks
2. Healthcare Data Breach
3. Payment System Breach
4. DDoS Attack Simulation
5. Automated Data Exfiltration
6. Run ALL attacks
0. Exit

---

### **scripts/cleanup.sh**
**Purpose**: Clean up and shutdown  
**Type**: Bash script  
**Features**:
- Kills port forwards
- Deletes Kubernetes resources
- Stops K3s
- Optional data cleanup

**Usage**:
```bash
./scripts/cleanup.sh
```

**What it Does**:
1. Kills port forwards
2. Deletes smart-city namespace
3. Stops K3s server
4. Optionally removes K3s data

---

## ⚙️ Configuration Files (2 files)

### **.env.example** (30+ lines)
**Purpose**: Configuration template  
**Type**: Environment variables  
**Contains**:
- MOCK_MODE (true/false)
- GROQ_API_KEY
- K8S_NAMESPACE
- Service URLs
- Monitoring URLs
- Alert configuration
- Attack simulation config

**Usage**:
```bash
cp .env.example .env
# Edit .env with your settings
```

---

### **.gitignore** (40+ lines)
**Purpose**: Git ignore patterns  
**Type**: Git configuration  
**Contains**:
- Environment files
- Python cache
- Virtual environments
- IDE files
- Logs
- OS files
- K3s data

---

### **requirements.txt** (8 lines)
**Purpose**: Python dependencies  
**Type**: pip requirements  
**Contains**:
```
flask==3.0.0
requests==2.31.0
python-dotenv==1.0.0
groq==0.4.1
kubernetes==28.1.0
prometheus-client==0.18.0
pyyaml==6.0
colorama==0.4.6
```

---

## 📂 Directory Structure

```
smart-city-ids/                    (Root)
│
├── Documentation (4 files)
│   ├── README.md                  (15KB)
│   ├── QUICKSTART.md              (3KB)
│   ├── PROJECT_STATUS.md          (10KB)
│   └── DELIVERY_SUMMARY.md        (14KB)
│
├── src/                           (Application)
│   └── main.py                    (IDS - 250 lines)
│
├── smart-city-services/           (Services)
│   ├── traffic-camera/app.py      (150 lines)
│   ├── healthcare-api/app.py      (150 lines)
│   └── parking-system/app.py      (150 lines)
│
├── attack-simulator/              (Tools)
│   ├── ddos_simulator.py          (200 lines)
│   └── data_exfiltration.py       (200 lines)
│
├── k8s-manifests/                 (Kubernetes)
│   ├── namespace.yaml
│   └── services-no-build.yaml     (350 lines)
│
├── scripts/                       (Automation)
│   ├── start-everything.sh        (200 lines)
│   ├── run-all-attacks.sh         (400 lines)
│   └── cleanup.sh
│
├── docs/                          (Extra docs)
│   └── demo-guide.md              (500 lines)
│
├── Configuration
│   ├── .env.example
│   ├── requirements.txt
│   └── .gitignore
│
└── Placeholders (for future)
    ├── monitoring/
    ├── deployment/
    └── tests/
```

---

## 📊 File Statistics

| Category | Files | Size | Lines |
|----------|-------|------|-------|
| Documentation | 4 | 42KB | 1500+ |
| Python Code | 8 | 20KB | 1000+ |
| Kubernetes | 2 | 15KB | 350+ |
| Scripts | 3 | 10KB | 600+ |
| Config | 3 | 3KB | 100+ |
| **TOTAL** | **20** | **90KB** | **3550+** |

---

## 🎯 Usage Scenarios

### Scenario 1: Learning Kubernetes
→ Read: README.md (section 2-3)  
→ Code: k8s-manifests/services-no-build.yaml  
→ Run: ./scripts/start-everything.sh  
→ Explore: kubectl commands from README

### Scenario 2: Demo for Presentation
→ Read: docs/demo-guide.md  
→ Setup: ./scripts/start-everything.sh  
→ Run: ./scripts/run-all-attacks.sh  
→ Show: Metrics & analysis results

### Scenario 3: Capstone Project
→ Study: All documentation  
→ Modify: Services & IDS code  
→ Deploy: With Kubernetes manifests  
→ Present: Following demo-guide.md

### Scenario 4: Security Research
→ Extend: Attack simulators  
→ Analyze: Vulnerability patterns  
→ Integrate: Real Falco/Prometheus  
→ Measure: Detection effectiveness

---

## 🔍 Code Browsing Guide

### For Reading Code in Order:
1. **src/main.py** - Entry point, understand IDS flow
2. **smart-city-services/*.py** - Understand vulnerable services
3. **attack-simulator/*.py** - See how attacks work
4. **k8s-manifests/services-no-build.yaml** - Deployment config
5. **scripts/start-everything.sh** - Orchestration logic

### For Learning Kubernetes:
1. k8s-manifests/namespace.yaml
2. k8s-manifests/services-no-build.yaml
3. README.md section on kubectl commands

### For Learning Python/Flask:
1. smart-city-services/traffic-camera/app.py
2. smart-city-services/healthcare-api/app.py
3. src/main.py (more advanced)

---

## 📞 Quick Reference

### Most Important Files
1. **QUICKSTART.md** - If you have 5 minutes
2. **README.md** - If you have 30 minutes
3. **docs/demo-guide.md** - If you're presenting

### Most Common Commands
```bash
./scripts/start-everything.sh      # Start system
./scripts/run-all-attacks.sh       # Run attacks
kubectl get pods -n smart-city     # Check pods
kubectl logs -f <pod> -n smart-city # View logs
./scripts/cleanup.sh               # Stop system
```

### Key Endpoints
- Traffic Camera: localhost:8001 (after port-forward)
- Healthcare API: localhost:8002
- Parking System: localhost:8003
- IDS Application: localhost:8004

---

**Happy exploring! 🚀**

For any questions, refer to README.md or docs/demo-guide.md
