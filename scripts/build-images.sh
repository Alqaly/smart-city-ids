#!/bin/bash
# =============================================================================
# Smart City IDS - Docker Image Builder
# Professional-grade container image building with registry support
# Usage: bash scripts/build-images.sh [--push] [--registry REGISTRY] [--help]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/script-utils.sh"

init_script "$0" "Docker Image Builder"

PUSH_IMAGES=0
NO_CACHE=""
REGISTRY="${DOCKER_REGISTRY:-localhost}"

while [[ $# -gt 0 ]]; do
    case $1 in
        --push)       PUSH_IMAGES=1; shift ;;
        --no-cache)   NO_CACHE="--no-cache"; shift ;;
        --registry)   REGISTRY="$2"; shift 2 ;;
        --help)       print_help "build-images.sh [--push] [--registry REGISTRY]"; exit 0 ;;
        *)            die "Unknown option: $1" ;;
    esac
done

ensure_commands docker

PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DOCKER_DIR="${PROJECT_ROOT}/docker"

log_section "BUILD CONFIGURATION"
log_info "Docker Context: $DOCKER_DIR"
log_info "Registry: $REGISTRY"
if [[ $PUSH_IMAGES -eq 1 ]]; then
    log_warn "Images will be pushed after building"
fi
echo ""

# Define images
declare -a IMAGES=(
    "ids-api:IDS API Service"
    "forwarder:Alert Forwarder"
    "smart-city-service:Smart City Services"
)

log_section "BUILDING IMAGES"

BUILD_SUCCESS=0
BUILD_FAILED=0

for image_spec in "${IMAGES[@]}"; do
    IFS=':' read -r image_name image_desc <<< "$image_spec"

    log_subsection "$image_desc"
    DOCKERFILE="${DOCKER_DIR}/${image_name}/Dockerfile"
    IMAGE_TAG="${REGISTRY}/smart-city-ids/${image_name}:latest"

    if [[ ! -f "$DOCKERFILE" ]]; then
        log_error "Dockerfile not found: $DOCKERFILE"
        ((BUILD_FAILED+=1))
        continue
    fi

    log_info "Building: $IMAGE_TAG"

    if docker build \
        --file "$DOCKERFILE" \
        --tag "$IMAGE_TAG" $NO_CACHE \
        "${DOCKER_DIR}/${image_name}" >/dev/null 2>&1
    then
        log_info "Built: $IMAGE_TAG"
        ((BUILD_SUCCESS+=1))

        if [[ $PUSH_IMAGES -eq 1 ]]; then
            log_info "Pushing to registry..."
            docker push "$IMAGE_TAG" || {
                log_error "Push failed: $IMAGE_TAG"
                ((BUILD_FAILED+=1))
            }
        fi
    else
        log_error "Build failed: $IMAGE_TAG"
        ((BUILD_FAILED+=1))
    fi
    echo ""
done

log_section "BUILD SUMMARY"
echo "Successful: $BUILD_SUCCESS"
echo "Failed: $BUILD_FAILED"
echo ""

if [[ $BUILD_FAILED -eq 0 ]]; then
    log_info "All images built successfully"
    exit 0
else
    die "Some builds failed"
fi
