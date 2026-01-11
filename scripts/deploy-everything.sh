#!/bin/bash

set -e

PROJECT_DIR="$HOME/smart-city-ids"
cd "$PROJECT_DIR"

echo "🚀 Deploying Smart City IDS - Complete System"
echo "=============================================="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Check API keys
echo -e "${YELLOW}📋 Checking configuration...${NC}"

if [ -z "$OPENAI_API_KEY" ] && [ -z "$GROQ_API_KEY" ]; then
    echo -e "${RED}❌ Error: No API keys found!${NC}"
    echo "Please set at least one:"
    echo "  export OPENAI_API_KEY='your-key'"
    echo "  export GROQ_API_KEY='your-key'"
    exit 1
fi

if [ -n "$OPENAI_API_KEY" ]; then
    echo -e "${GREEN}✅ OpenAI API key found${NC}"
fi

if [ -n "$GROQ_API_KEY" ]; then
    echo -e "${GREEN}✅ Groq API key found${NC}"
fi

echo ""

# Check if src files exist
if [ ! -f "src/main.py" ]; then
    echo -e "${RED}❌ Error: src/main.py not found${NC}"
    echo "Please create the IDS application files first"
    exit 1
fi

# Create ConfigMaps for IDS app code
echo -e "${YELLOW}📦 Creating ConfigMaps for IDS application...${NC}"

kubectl create configmap ids-app-code \
  --from-file=src/main.py \
  --from-file=src/config.py \
  --from-file=src/security_monitor.py \
  --from-file=src/llm_engine_openai.py \
  --from-file=src/llm_engine_groq.py \
  --from-file=src/k8s_automation.py \
  --from-file=requirements.txt \
  -n smart-city \
  --dry-run=client -o yaml | kubectl apply -f -

echo -e "${GREEN}✅ ConfigMaps created${NC}"
echo ""

# Update secrets with API keys
echo -e "${YELLOW}🔐 Updating secrets...${NC}"

kubectl create secret generic ids-secrets \
  --from-literal=openai-api-key="${OPENAI_API_KEY:-none}" \
  --from-literal=groq-api-key="${GROQ_API_KEY:-none}" \
  -n smart-city \
  --dry-run=client -o yaml | kubectl apply -f -

echo -e "${GREEN}✅ Secrets updated${NC}"
echo ""

# Check if Suricata manifests exist
if [ -f "k8s-manifests/04-suricata.yaml" ]; then
    echo -e "${YELLOW}🛡️  Deploying Suricata IDS...${NC}"
    kubectl apply -f k8s-manifests/04-suricata.yaml
    echo -e "${GREEN}✅ Suricata deployed${NC}"
    echo ""
else
    echo -e "${YELLOW}⚠️  Suricata manifest not found, skipping...${NC}"
fi

if [ -f "k8s-manifests/05-suricata-forwarder.yaml" ]; then
    echo -e "${YELLOW}📡 Deploying Suricata forwarder...${NC}"
    kubectl apply -f k8s-manifests/05-suricata-forwarder.yaml
    echo -e "${GREEN}✅ Forwarder deployed${NC}"
    echo ""
else
    echo -e "${YELLOW}⚠️  Suricata forwarder manifest not found, skipping...${NC}"
fi

# Deploy IDS application
if [ -f "k8s-manifests/03-ids-app.yaml" ]; then
    echo -e "${YELLOW}🤖 Deploying IDS application...${NC}"
    kubectl apply -f k8s-manifests/03-ids-app.yaml
    echo -e "${GREEN}✅ IDS application deployed${NC}"
    echo ""
else
    echo -e "${YELLOW}⚠️  IDS app manifest not found, skipping...${NC}"
fi

# Wait for pods
echo -e "${YELLOW}⏳ Waiting for pods to be ready...${NC}"
sleep 5

echo ""
echo -e "${GREEN}📊 Deployment Status:${NC}"
echo ""
kubectl get pods -n smart-city
echo ""

echo -e "${GREEN}✅ Deployment complete!${NC}"
echo ""
echo "Next steps:"
echo "  1. Check IDS health: kubectl port-forward -n smart-city svc/ids-api-service 8000:8000"
echo "     Then: curl http://localhost:8000/health"
echo ""
echo "  2. Run demo: bash demo_script.sh"
echo ""
