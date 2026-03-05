"""Manual OpenAI integration smoke script.

This file is intentionally excluded from automated pytest runs and should be
executed directly only when OpenAI dependencies and credentials are present.
"""

if __name__ != "__main__":
    import pytest
    pytest.skip("Manual integration script (run directly, not via pytest)", allow_module_level=True)

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Allow running from repository root without environment tweaks.
sys.path.insert(0, str(Path("services/ids-api/src").resolve()))
from llm_engine_openai import LLMSecurityAnalyzer


def main() -> int:
    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY not found")
        return 1
    print(f"API key loaded: {api_key[:20]}...")

    analyzer = LLMSecurityAnalyzer()
    test_alert = {
        "type": "DDoS Attack",
        "source": "traffic-camera-service",
        "timestamp": "2025-11-05T16:00:00Z",
        "details": "High request rate: 500 req/s from 192.168.1.100",
    }

    print("Testing OpenAI integration...")
    result = analyzer.analyze_alert(test_alert)

    print("Analysis Result")
    print("=" * 60)
    print(f"Summary: {result.get('summary')}")
    print(f"Severity: {result.get('severity')}/10")
    print(f"Threat Type: {result.get('threat_type')}")
    print(f"Recommendations: {result.get('recommendations')}")
    print(f"Automated Actions: {result.get('automated_actions')}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
