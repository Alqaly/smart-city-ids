"""
Unified LLM Engine - Auto-detects available API
Tries: xAI Grok-4 > OpenAI > Claude
"""
import os
from dotenv import load_dotenv

load_dotenv()

class LLMSecurityAnalyzer:
    def __init__(self):
        self.engine = None
        self.provider = None
        
        # Try xAI Grok-4 first (primary)
        if os.getenv("XAI_API_KEY"):
            try:
                from llm_engine_xai import XAIAnalyzer
                self.engine = XAIAnalyzer()
                self.provider = "xAI Grok-4"
                print("✅ Using xAI Grok-4")
                return
            except Exception as e:
                print(f"⚠️ xAI failed: {e}")
        
        # Try OpenAI (fallback)
        if os.getenv("OPENAI_API_KEY"):
            try:
                from llm_engine_openai import LLMSecurityAnalyzer as OpenAIAnalyzer
                self.engine = OpenAIAnalyzer()
                self.provider = "OpenAI"
                print("✅ Using OpenAI")
                return
            except Exception as e:
                print(f"⚠️ OpenAI failed: {e}")
        
        # Try Claude (tertiary)
        if os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY"):
            try:
                from llm_engine_claude import LLMSecurityAnalyzer as ClaudeAnalyzer
                self.engine = ClaudeAnalyzer()
                self.provider = "Claude"
                print("✅ Using Claude AI")
                return
            except Exception as e:
                print(f"⚠️ Claude failed: {e}")
        
        raise ValueError("❌ No LLM API key found! Set XAI_API_KEY, OPENAI_API_KEY, or CLAUDE_API_KEY in .env")
    
    def analyze_alert(self, alert_data):
        """Forward to the active engine"""
        if not self.engine:
            raise ValueError("No LLM engine available")
        return self.engine.analyze_alert(alert_data)
