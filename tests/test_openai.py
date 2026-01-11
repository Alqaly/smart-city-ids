import sys
sys.path.append('src')

from llm_engine_openai import LLMSecurityAnalyzer
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Check if API key is loaded
api_key = os.getenv("OPENAI_API_KEY")
if api_key:
    print(f"✅ API Key loaded: {api_key[:20]}...")
else:
    print("❌ API Key not found!")
    exit(1)

# Initialize analyzer
analyzer = LLMSecurityAnalyzer()

# Test alert
test_alert = {
    "type": "DDoS Attack",
    "source": "traffic-camera-service",
    "timestamp": "2025-11-05T16:00:00Z",
    "details": "High request rate: 500 req/s from 192.168.1.100"
}

print("\n🔍 Testing OpenAI integration...")
print("Sending alert to OpenAI for analysis...\n")

result = analyzer.analyze_alert(test_alert)

print("✅ Analysis Result:")
print("=" * 60)
print(f"Summary: {result.get('summary')}")
print(f"Severity: {result.get('severity')}/10")
print(f"Threat Type: {result.get('threat_type')}")
print(f"Recommendations: {result.get('recommendations')}")
print(f"Automated Actions: {result.get('automated_actions')}")
print("=" * 60)
