#!/bin/bash
# =============================================================================
# Smart City IDS - Docker Image Builder
# Builds all required images with dependencies pre-installed
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DOCKER_DIR="${PROJECT_ROOT}/docker"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Image configuration
IMAGES=(
    "smart-city-ids-api:latest|ids-api"
    "smart-city-service:latest|smart-city-service"
    "smart-city-forwarder:latest|forwarder"
)

# Check for container runtime
detect_runtime() {
    if command -v nerdctl &> /dev/null; then
        RUNTIME="nerdctl"
        RUNTIME_OPTS="--namespace k8s.io"
    elif command -v docker &> /dev/null; then
        RUNTIME="docker"
        RUNTIME_OPTS=""
    else
        log_error "No container runtime found. Install Docker or use k3s with nerdctl."
        exit 1
    fi
    log_info "Using container runtime: $RUNTIME"
}

# Build a single image
build_image() {
    local image_name=$1
    local docker_subdir=$2
    local dockerfile="${DOCKER_DIR}/${docker_subdir}/Dockerfile"
    
    if [[ ! -f "$dockerfile" ]]; then
        log_error "Dockerfile not found: $dockerfile"
        return 1
    fi
    
    log_info "Building image: $image_name"
    cd "$PROJECT_ROOT"
    
    $RUNTIME build $RUNTIME_OPTS \
        -t "$image_name" \
        -f "$dockerfile" \
        .
    
    log_info "Successfully built: $image_name"
}

# Import image to k3s containerd (if using k3s)
import_to_k3s() {
    local image_name=$1
    
    if command -v k3s &> /dev/null; then
        log_info "Importing $image_name to k3s containerd..."
        
        if [[ "$RUNTIME" == "docker" ]]; then
            # Export from docker and import to k3s
            docker save "$image_name" | sudo k3s ctr images import -
        elif [[ "$RUNTIME" == "nerdctl" ]]; then
            # Already in k3s.io namespace
            log_info "Image already available in k3s namespace"
        fi
    fi
}

# Main build process
main() {
    log_info "=========================================="
    log_info "Smart City IDS - Image Builder"
    log_info "=========================================="
    
    detect_runtime
    
    local failed=0
    
    for image_spec in "${IMAGES[@]}"; do
        IFS='|' read -r image_name docker_subdir <<< "$image_spec"
        
        if build_image "$image_name" "$docker_subdir"; then
            import_to_k3s "$image_name"
        else
            ((failed++))
        fi
    done
    
    echo ""
    log_info "=========================================="
    if [[ $failed -eq 0 ]]; then
        log_info "All images built successfully!"
        log_info ""
        log_info "Images created:"
        for image_spec in "${IMAGES[@]}"; do
            IFS='|' read -r image_name _ <<< "$image_spec"
            echo "  - $image_name"
        done
    else
        log_error "$failed image(s) failed to build"
        exit 1
    fi
}

# Run if executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
