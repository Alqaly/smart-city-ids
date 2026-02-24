#!/usr/bin/env bash
# Fix and Redeploy Script for Smart City IDS
# This script fixes common issues and redeploys the system

set -e

echo "=========================================="
echo "Smart City IDS - Fix and Redeploy"
echo "=========================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running from project root
if [ ! -f ".env" ]; then
    echo -e "${RED}ERROR: .env file not found. Run this script from the project root.${NC}"
    exit 1
fi

echo -e "${YELLOW}Step 1: Checking .env file for API keys...${NC}"
API_KEYS_FOUND=0
for key in XAI_API_KEY OPENAI_API_KEY ANTHROPIC_API_KEY GEMINI_API_KEY KIMI_API_KEY; do
    if grep -q "^${key}=" .env && ! grep -q "^${key}=$" .env && ! grep -q "^${key}=placeholder" .env; then
        value=$(grep "^${key}=" .env | cut -d'=' -f2 | head -c 10)
        echo "  ✓ $key is set (${value}...)"
        API_KEYS_FOUND=$((API_KEYS_FOUND + 1))
    else
        echo "  ✗ $key is missing or empty"
    fi
done

if [ $API_KEYS_FOUND -eq 0 ]; then
    echo -e "${RED}WARNING: No API keys found in .env file!${NC}"
    echo "  Add your API keys to .env file before continuing."
    echo "  Example: XAI_API_KEY=xai-your-key-here"
    exit 1
fi

echo ""
echo -e "${YELLOW}Step 2: Syncing API keys to Kubernetes...${NC}"
if kubectl get namespace smart-city >/dev/null 2>&1; then
    bash scripts/apply-llm-env-to-k8s-secret.sh .env
else
    echo "  Namespace 'smart-city' not found. Skipping K8s secret sync."
    echo "  (The API will use .env file directly when running locally)"
fi

echo ""
echo -e "${YELLOW}Step 3: Checking IoT device emulation...${NC}"
if kubectl get namespace smart-city >/dev/null 2>&1; then
    IOT_PODS=$(kubectl get pods -n smart-city -l app=iot-device 2>/dev/null | grep -c "Running" || echo "0")
    echo "  Running IoT device pods: $IOT_PODS"
    
    if [ "$IOT_PODS" -lt 5 ]; then
        echo "  Redeploying IoT devices..."
        kubectl apply -f k8s-manifests/iot-devices/ 2>/dev/null || echo "  (IoT manifests not found or already applied)"
    fi
else
    echo "  K8s not available - IoT emulation will run locally if configured"
fi

echo ""
echo -e "${YELLOW}Step 4: Restarting IDS API to pick up changes...${NC}"
if kubectl get deployment ids-api -n smart-city >/dev/null 2>&1; then
    kubectl rollout restart deployment/ids-api -n smart-city
    kubectl rollout status deployment/ids-api -n smart-city --timeout=120s
else
    echo "  K8s deployment not found. If running locally, restart the API manually:"
    echo "  pkill -f 'python.*main.py' && python services/ids-api/src/main.py"
fi

echo ""
echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}Fix and redeploy complete!${NC}"
echo -e "${GREEN}==========================================${NC}"
echo ""
echo "Next steps:"
echo "  1. Wait 30 seconds for services to stabilize"
echo "  2. Run: python scripts/demo-complete.py"
echo "  3. Open dashboard: http://localhost:8000/ui/"
echo ""
