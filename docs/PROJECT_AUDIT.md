# Smart City IDS - Project Audit Report

**Audit Date:** February 2, 2026  
**Last Updated:** February 2, 2026  
**Purpose:** Full codebase assessment for one-click deployment and GitHub publication  
**Auditor:** Automated CI/CD Preparation Agent

---

## Executive Summary

The Smart City IDS project is a functional LLM-driven intrusion detection system running on K3s with PostgreSQL persistence.

### Audit Results

| Issue Category | Original | Fixed | Status |
|----------------|----------|-------|--------|
| Runtime dependency installs in pods | 4 | 0* | ✅ Dockerfiles created |
| Secrets committed to repo | 1 | 0 | ✅ Never committed |
| Duplicate/obsolete directories | 6 | 0 | ✅ Removed |
| Missing documentation | 5 | 0 | ✅ Created |
| Non-idempotent scripts | 3 | 0 | ✅ Fixed |
| Virtual envs in repo | 2 | 0 | ✅ Gitignored |

*Dockerfiles created but not yet deployed to cluster - pods still use runtime install.

---

## 1. Active vs Obsolete Components

### ✅ Active & Required

| Path | Purpose | Status |
|------|---------|--------|
| `services/ids-api/src/` | Main IDS API (FastAPI) | ✅ Active |
| `services/ids-operator/src/` | Kubernetes operator | ✅ Active |
| `services/forwarders/falco/` | Falco alert forwarder | ✅ Active |
| `smart-city-services/` | Demo IoT services (intentionally vulnerable) | ✅ Active |
| `k8s-manifests/` | Kubernetes deployments | ✅ Active |
| `infrastructure/monitoring/` | Prometheus/Grafana | ✅ Active |
| `infrastructure/database/migrations/` | PostgreSQL schema | ✅ Active |
| `attack-simulator/` | Attack simulation tools | ✅ Active (demo) |

### ~~⚠️ Duplicate/Obsolete~~ ✅ REMOVED

| Path | Issue | Status |
|------|-------|--------|
| `clean-app/` | Duplicate of `services/ids-api/src/` | ✅ Removed |
| `src/ids-api/` | Empty/outdated structure | ✅ Removed |
| `grok-cli/` | Unused TypeScript CLI | ✅ Removed |
| `iot-simulator/` | Duplicate of `services/iot-simulator/` | 📦 Kept (has unique configs) |
| `k8s-manifests/ids-api-LEGENDARY.yaml` | Superseded by FINAL | ✅ Removed |
| `k8s-manifests/*.yaml.1` | Backup files | ✅ Removed |
| `docs/_archive/` | Old documentation | 📦 Kept for reference |

### ~~🔴 Committed Secrets (CRITICAL)~~ ✅ VERIFIED SAFE

**File:** `.env`  
**Status:** ✅ Never committed to git  
**Verification:**
- `.env` is in `.gitignore`
- `git log -- .env` returns 0 commits
- GitHub repo verified clean

---

## 2. Runtime Dependency Issues

### 🔴 Critical: Pods Installing Dependencies at Runtime

**services-no-build.yaml** (lines 23-25):
```yaml
args:
  - "pip install --no-cache-dir flask==3.0.0 && python /app/app.py"
```

**ids-api-FINAL.yaml** (lines 24-28):
```yaml
args:
  - |
    apt update >/dev/null 2>&1
    apt install -y curl >/dev/null 2>&1
    pip install --no-cache-dir -r requirements.txt
```

**Impact:**
- ~60 second startup delay per pod
- Network dependency at runtime
- Non-reproducible builds
- Fails without internet access

**Solution Required:**
- Build proper Docker images with dependencies pre-installed
- Push to local registry or use k3s image import
- Reference pre-built images in manifests

---

## 3. Repository Structure Analysis

### Current Structure (Messy)
```
smart-city-ids/
├── clean-app/              # DUPLICATE - remove
├── grok-cli/               # UNUSED - archive
├── iot-simulator/          # DUPLICATE
├── k8s-manifests/          # Mixed active/obsolete
├── services/               # Main services
│   ├── ids-api/
│   ├── ids-operator/
│   ├── forwarders/
│   └── iot-simulator/
├── smart-city-services/    # Demo services
├── src/                    # EMPTY - remove
├── venv/                   # Should not be tracked
└── ...
```

### Recommended Structure (Clean)
```
smart-city-ids/
├── deploy.sh               # One-click deployment
├── docker/                 # All Dockerfiles
│   ├── ids-api/
│   ├── smart-city-service/
│   └── forwarder/
├── k8s/                    # All K8s manifests
│   ├── namespaces/
│   ├── services/
│   └── monitoring/
├── services/               # Application code only
│   ├── ids-api/
│   ├── ids-operator/
│   └── forwarders/
├── demo-services/          # Intentionally vulnerable
├── scripts/                # Utility scripts
│   ├── install-k3s.sh
│   ├── build-images.sh
│   └── load-dashboards.sh
├── docs/
│   ├── README.md
│   ├── ARCHITECTURE.md
│   ├── SETUP.md
│   └── OPERATIONS.md
└── tests/
```

---

## 4. Kubernetes Manifest Audit

### Active Manifests (Keep)
| File | Purpose |
|------|---------|
| `namespace.yaml` | Namespace definitions |
| `services-no-build.yaml` | Demo services (needs Docker fix) |
| `ids-api-FINAL.yaml` | IDS API (needs Docker fix) |
| `prometheus-deployment.yaml` | Prometheus stack |
| `grafana-deployment.yaml` | Grafana with dashboards |
| `rbac.yaml` | RBAC for IDS |
| `falco-forwarder.yaml` | Falco integration |

### Obsolete/Duplicate (Remove)
| File | Reason |
|------|--------|
| `ids-api-LEGENDARY.yaml` | Superseded |
| `k8s.yaml.1`, `mqtt-broker.yaml.1` | Backup files |
| `simple-services.yaml` | Superseded by services-no-build |
| `suricata-working.yaml` | Development artifact |

---

## 5. Missing Documentation

| Document | Status | Required For |
|----------|--------|--------------|
| `docs/SETUP.md` | ❌ Missing | New laptop migration |
| `docs/ARCHITECTURE.md` | ❌ Missing | IEEE review |
| `docs/OPERATIONS.md` | ❌ Missing | Demo procedures |
| `docs/CHANGELOG.md` | ❌ Missing | Capstone I→II evolution |
| `README.md` (root) | ⚠️ Outdated | Quick start |

---

## 6. Environment & Configuration

### Current State
| Variable | Source | Issue |
|----------|--------|-------|
| `XAI_API_KEY` | `.env` (committed!) | 🔴 Secret exposed |
| `OPENAI_API_KEY` | `.env` (committed!) | 🔴 Secret exposed |
| `KUBECONFIG` | `.env` | Hardcoded path |
| `K8S_NAMESPACE` | Config | OK |

### `.env.example` Status
Current `.env.example` is outdated:
- References `GROQ_API_KEY` (not used in current code)
- Missing `XAI_API_KEY`
- Missing `POSTGRES_*` variables

---

## 7. Current Cluster State (Working)

```
Namespaces:
  - smart-city (main workloads)
  - monitoring (Prometheus/Grafana)
  - falco-system (Falco runtime security)
  - suricata-system (Network IDS)

Services Running:
  - ids-api (NodePort 30800) ✅
  - ids-operator ✅
  - postgres ✅
  - grafana (NodePort 30300) ✅
  - prometheus (NodePort 31701) ✅
  - traffic-camera, healthcare-api, parking-system ✅
  - mqtt-broker, iot-devices ✅

Data Persisted:
  - PostgreSQL: 157 alerts stored
  - Prometheus: Metrics restored from DB on restart
```

---

## 8. Required Actions (Priority Order)

### 🔴 P0: Critical (Before GitHub)
1. **Remove secrets from git history**
   - `.env` contains real API keys
   - Use `git filter-branch` or BFG Repo Cleaner
   
2. **Build proper Docker images**
   - Create Dockerfiles that pre-install dependencies
   - Eliminate runtime `pip install`
   - Build and load into k3s containerd

3. **Update `.env.example`**
   - Add all required variables with placeholders
   - Document each variable's purpose

### 🟡 P1: Medium (One-Click Deployment)
4. **Create `deploy.sh`**
   - Check prerequisites (docker, k3s)
   - Build all images
   - Load images into k3s
   - Apply all manifests in order
   - Load Grafana dashboards
   - Verify health endpoints

5. **Consolidate directory structure**
   - Remove duplicates (clean-app, src/ids-api)
   - Organize manifests by category
   - Archive unused components

6. **Create missing documentation**
   - SETUP.md (migration guide)
   - ARCHITECTURE.md (system design)
   - OPERATIONS.md (demo playbook)

### 🟢 P2: Polish (Academic Quality)
7. **Improve Grafana dashboards**
   - Auto-provision on deployment
   - Add annotation explaining panels
   
8. **Add health verification**
   - Post-deployment smoke tests
   - Metric validation

9. **Create CHANGELOG.md**
   - Document Capstone I vs II differences
   - Feature evolution timeline

---

## 9. Files to Create

| File | Purpose |
|------|---------|
| `deploy.sh` | One-click deployment |
| `scripts/build-images.sh` | Build all Docker images |
| `scripts/load-dashboards.sh` | Import Grafana dashboards |
| `docker/ids-api/Dockerfile` | Pre-built IDS API image |
| `docker/smart-city-service/Dockerfile` | Pre-built demo service |
| `.env.example` | Updated template |
| `docs/SETUP.md` | New laptop guide |
| `docs/ARCHITECTURE.md` | System design |
| `docs/OPERATIONS.md` | Demo procedures |

---

## 10. Estimated Effort

| Task | Time |
|------|------|
| Docker image creation | 2 hours |
| deploy.sh script | 2 hours |
| Directory cleanup | 1 hour |
| Documentation | 3 hours |
| Testing & validation | 2 hours |
| **Total** | **~10 hours** |

---

## Appendix: Current Service Ports

| Service | Internal Port | External Access |
|---------|--------------|-----------------|
| IDS API | 8000 | NodePort 30800 |
| Grafana | 3000 | NodePort 30300 |
| Prometheus | 9090 | NodePort 31701 |
| PostgreSQL | 5432 | ClusterIP only |
| Traffic Camera | 5000 | ClusterIP only |
| Healthcare API | 5001 | ClusterIP only |
| Parking System | 5002 | ClusterIP only |

---

*Audit completed. Proceed with P0 actions immediately.*
