# Scripts Audit & Issues Report

## Executive Summary

Found **5 critical issues** and **3 areas of improvement** in the scripts folder. Main problems:
1. **Docker image naming mismatch** between `build-images.sh` and K8s manifests
2. **Missing Docker build step** in deploy.sh flow
3. **Duplication** between deploy.sh and start-everything.sh
4. **Weak error handling** in K3s restart logic
5. **Unmanaged demo scripts** should be clearly separated from production workflow

---

## Issues Found

### 🔴 CRITICAL: Image Name Mismatch
- **File**: `scripts/build-images.sh` (lines 24-26)
- **Problem**: Builds images with wrong names
  - Builds: `smart-city-ids-api:latest`
  - K8s expects: `smart-city-ids/ids-api:latest`
  - Builds: `smart-city-service:latest`
  - K8s expects: `smart-city-ids/smart-city-service:latest`
- **Impact**: K8s pod creation fails with "image not found" or falls back to Docker Hub
- **Fix**: Update IMAGES array in build-images.sh to match K8s manifests

### 🔴 CRITICAL: Missing Docker Build Step
- **File**: `deploy.sh` (line 213-233)
- **Problem**: 
  ```bash
  build_images() {
      if $SKIP_BUILD; then
          log_info "Skipping image build (--skip-build)"
          return
      fi
      
      # ❌ PROBLEM: Only calls build-images.sh if docker is available
      if ! command -v docker &> /dev/null; then
          log_warn "Docker not found..."
          # Falls back to nerdctl or warns user
      else
          bash "${PROJECT_ROOT}/scripts/build-images.sh"
      fi
  }
  ```
- **Impact**: If user doesn't have Docker but has K3s with nerdctl, build still may not execute
- **Fix**: Always call build-images.sh with better error handling

### 🟠 HIGH: Duplication Between Scripts
- **Files**: 
  - `deploy.sh` (441 lines, full orchestration)
  - `scripts/start-everything.sh` (115 lines, K3s restart)
- **Overlapping functionality**:
  - Both configure KUBECONFIG
  - Both kill/restart K3s
  - Both apply K8s manifests
  - Both wait for pods to be ready
- **Impact**: Confusion about which script to run; risk of inconsistent behavior
- **Solution**: deploy.sh should call start-everything.sh instead of duplicating logic, or consolidate into one

### 🟠 HIGH: Weak K3s Restart Error Handling
- **File**: `scripts/start-everything.sh` (lines 30-60)
- **Problem**: 
  ```bash
  # Kills K3s with pkill - may leave processes hanging
  pkill -f "k3s server" || true
  sleep 2
  
  # Then starts new process without checking old one fully stopped
  k3s server --write-kubeconfig-mode=644 ...
  ```
- **Impact**: Orphaned processes, port conflicts (6443 already in use), race conditions
- **Fix**: Use `systemctl` instead of pkill, add proper wait checks

### 🟡 MEDIUM: Inconsistent Error Handling
- **Files**: Multiple scripts
- **Problem**:
  - `build-images.sh`: Uses `set -e` (exit on error)
  - `check-setup.sh`: No error handling, just warns
  - `cleanup.sh`: Uses `2>/dev/null || true` to suppress all errors
- **Impact**: Inconsistent debugging, silent failures
- **Fix**: Standardize on consistent error handling pattern

### 🟡 MEDIUM: Demo Scripts Not Separated
- **Problem**: 
  - `capstone1-demo.sh`
  - `capstone1-live-view.sh`
  - `phase4-run-smart-city-attacks.sh`
  - `supervisor-demo.sh`
  - These are in root scripts/ folder but are specialized demo scenarios
- **Impact**: Users confused about which script to run for normal deployment
- **Fix**: Move to `scripts/demos/` subdirectory, create `scripts/README.md` to guide users

### 🟡 MEDIUM: Unused/Duplicate Logic
- **Files**: 
  - `check-setup.sh` (49 lines, checks prereqs)
  - `deploy.sh` has its own `check_prerequisites()` (lines 79-120)
  - `check-system.sh` (150 lines, health checks)
- **Problem**: Overlapping functionality, unclear which to use
- **Solution**: Keep deploy.sh self-contained, make check-system.sh just a quick health check

---

## Script Purposes & Dependencies

| Script | Purpose | Called By | Status |
|--------|---------|-----------|--------|
| **deploy.sh** | Main one-click deployment (K3s + images + manifests) | User runs directly | ✅ Production |
| **scripts/build-images.sh** | Build Docker images from Dockerfiles | deploy.sh (Step 4) | ✅ Production (has bugs) |
| **scripts/start-everything.sh** | Restart K3s + deploy manifests | Standalone or by deploy.sh? | ⚠️ Duplicates deploy.sh |
| **scripts/cleanup.sh** | Tear down all K8s resources | User runs to cleanup | ✅ Production |
| **scripts/check-setup.sh** | Verify prerequisites before deployment | Could be called by deploy.sh | ⚠️ Redundant with deploy.sh |
| **scripts/check-system.sh** | Health check (show pod status, URLs) | User runs after deployment | ✅ Production |
| **scripts/load-dashboards.sh** | Load Grafana dashboards | deploy.sh (Step 6) | ✅ Production |
| **scripts/demo.sh** | Run attack proof demo | User runs for demo | 🎓 Demo |
| **scripts/capstone1-demo.sh** | Capstone 1 specific demo | User runs for capstone | 🎓 Demo (archived?) |
| **scripts/capstone1-live-view.sh** | Live dashboard view for capstone | User runs for capstone | 🎓 Demo (archived?) |
| **scripts/phase4-run-smart-city-attacks.sh** | Run Phase 4 attacks | User runs for testing | 🎓 Demo |
| **scripts/supervisor-demo.sh** | Supervisor mode demo | User runs for demo | 🎓 Demo |
| **scripts/scalability-test.sh** | Test horizontal scaling | User runs for testing | 🧪 Test |
| **scripts/k3s-dynamic-ip.sh** | Handle dynamic K3s IP changes | Unknown usage | ❓ Unclear |
| **scripts/archive/** | Old/unused scripts | Archive | 📦 Archived |
| **scripts/db/** | Database setup scripts | Unknown | ❓ Unclear |

---

## Recommended Actions

### Priority 1: Fix Critical Image Naming Bug
**Task**: Fix Docker image names in build-images.sh to match K8s manifests
```bash
# BEFORE (scripts/build-images.sh line 24)
IMAGES=(
    "smart-city-ids-api:latest|ids-api"
    "smart-city-service:latest|smart-city-service"
    "smart-city-forwarder:latest|forwarder"
)

# AFTER: Should match K8s image references
IMAGES=(
    "smart-city-ids/ids-api:latest|ids-api"
    "smart-city-ids/smart-city-service:latest|smart-city-service"
    "smart-city-ids/forwarder:latest|forwarder"
)
```

### Priority 2: Improve Docker Build in deploy.sh
**Task**: Ensure build-images.sh always runs with proper error checking
```bash
# CURRENT: Falls back to base images if docker not found
# BETTER: Always build, fail explicitly if no runtime
build_images() {
    if $SKIP_BUILD; then
        log_info "Skipping image build (--skip-build)"
        return
    fi
    
    log_info "Building Docker images..."
    bash "${PROJECT_ROOT}/scripts/build-images.sh" || {
        log_error "Docker image build failed"
        exit 1
    }
}
```

### Priority 3: Fix K3s Restart Logic
**Task**: Replace pkill with proper systemctl management
```bash
# CURRENT: scripts/start-everything.sh uses pkill
pkill -f "k3s server" || true

# BETTER: Use k3s-killall.sh provided by K3s
/usr/local/bin/k3s-killall.sh || true
sleep 5

# Then restart via systemctl (if installed) or direct command
if systemctl is-active --quiet k3s; then
    sudo systemctl restart k3s
else
    k3s server --write-kubeconfig-mode=644 ... &
fi
```

### Priority 4: Consolidate Duplicate Scripts
**Task**: Have deploy.sh call build-images.sh and cleanup duplicated K3s logic
- Keep `deploy.sh` as main entry point
- Remove K3s restart from `start-everything.sh` (or make it just call deploy.sh)
- Use `start-everything.sh` only for interactive K3s startup (no cleanup)

### Priority 5: Organize Demo Scripts
**Task**: Move demo scripts to separate folder
```bash
mkdir -p scripts/demos
mv scripts/capstone1-demo.sh scripts/demos/
mv scripts/capstone1-live-view.sh scripts/demos/
mv scripts/phase4-run-smart-city-attacks.sh scripts/demos/
mv scripts/supervisor-demo.sh scripts/demos/
```
Create `scripts/README.md`:
```
## Production Deployment Scripts
- deploy.sh - One-click deployment (main entry point)
- cleanup.sh - Tear down deployment
- check-system.sh - Health check and URLs

## Demo & Testing Scripts
See scripts/demos/ for various demonstration scenarios
```

---

## Testing Strategy

After fixes:
```bash
# Test 1: Verify image names
./scripts/build-images.sh
docker images | grep smart-city-ids

# Test 2: Full deployment
./deploy.sh --clean

# Test 3: Check pod startup time
time kubectl get pods -n smart-city -o jsonpath='{.items[*].metadata.creationTimestamp}'

# Test 4: Verify all services healthy
./scripts/check-system.sh
```

---

## Summary of Changes Needed

| File | Changes | Priority |
|------|---------|----------|
| **scripts/build-images.sh** | Fix image names to match K8s | 🔴 P1 |
| **deploy.sh** | Improve Docker build error handling | 🔴 P1 |
| **scripts/start-everything.sh** | Replace pkill with systemctl | 🟠 P2 |
| **scripts/start-everything.sh** | Remove duplicate K3s logic | 🟠 P2 |
| **scripts/demos/** | Create folder, move demo scripts | 🟡 P3 |
| **scripts/README.md** | Create navigation guide | 🟡 P3 |
| All scripts | Add consistent error handling | 🟡 P3 |

