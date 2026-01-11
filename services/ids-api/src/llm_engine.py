"""
Unified LLM Engine - Auto-detects available API
Tries: Claude > Groq > OpenAI
"""
import os
from dotenv import load_dotenv

load_dotenv()

class LLMSecurityAnalyzer:
    def __init__(self):
        self.engine = None
        self.provider = None
        
        # Try Claude first
        if os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY"):
            try:
                from llm_engine_claude import LLMSecurityAnalyzer as ClaudeAnalyzer
                self.engine = ClaudeAnalyzer()
                self.provider = "Claude"
                print("✅ Using Claude AI")
                return
            except Exception as e:
                print(f"⚠️ Claude failed: {e}")
        
        # Try Groq
        if os.getenv("GROQ_API_KEY"):
            try:
                from llm_engine_groq import LLMSecurityAnalyzer as GroqAnalyzer
                self.engine = GroqAnalyzer()
                self.provider = "Groq"
                print("✅ Using Groq AI")
                return
            except Exception as e:
                print(f"⚠️ Groq failed: {e}")
        
        # Try OpenAI
        if os.getenv("OPENAI_API_KEY"):
            try:
                from llm_engine_openai import LLMSecurityAnalyzer as OpenAIAnalyzer
                self.engine = OpenAIAnalyzer()
                self.provider = "OpenAI"
                print("✅ Using OpenAI")
                return
            except Exception as e:
                print(f"⚠️ OpenAI failed: {e}")
        
        raise ValueError("❌ No LLM API key found! Set CLAUDE_API_KEY, GROQ_API_KEY, or OPENAI_API_KEY in .env")
    
    def analyze_alert(self, alert_data):
        """Forward to the active engine"""
        if not self.engine:
            raise ValueError("No LLM engine available")
        return self.engine.analyze_alert(alert_data)
