"""
Conversational Security Analyst API with Tool Calling
Enables natural language interaction with the IDS system
"""

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any, Callable
import json
import asyncio
import inspect
import threading
import logging
import time
from datetime import datetime
from enum import Enum
from uuid import uuid4

# Use absolute imports if this file is in services/ids-api/src/api/
from llm_manager_enhanced import EnhancedLLMManager
from llm_credit_checker import check_all_credits
from config import Config

# Define status constants to replace missing Enum
class ProviderStatus:
    HEALTHY = "ok"
    LOW_CREDIT = "warning"
    CRITICAL = "critical"
    EXHAUSTED = "exhausted"
    ERROR = "error"

# Create a local instance of the enhanced manager for analyst operations
# This ensures we have access to analyze_security_alert and other enhanced features
analyst_llm = EnhancedLLMManager()


class PerUserTokenBucket:
    """Simple per-user/session token bucket limiter for analyst chat."""

    def __init__(self, requests_per_minute: int, burst_size: int):
        self.requests_per_minute = max(1, int(requests_per_minute))
        self.burst_size = max(1, int(burst_size))
        self._state: Dict[str, Dict[str, float]] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, user_key: str) -> tuple[bool, str]:
        key = str(user_key or "anonymous").strip().lower() or "anonymous"
        now = time.time()
        async with self._lock:
            row = self._state.get(key)
            if not row:
                row = {"tokens": float(self.burst_size), "last_refill": now}
                self._state[key] = row

            elapsed = now - float(row.get("last_refill", now))
            refill = elapsed * (self.requests_per_minute / 60.0)
            row["tokens"] = min(float(self.burst_size), float(row.get("tokens", 0.0)) + refill)
            row["last_refill"] = now

            if row["tokens"] >= 1.0:
                row["tokens"] -= 1.0
                return True, "OK"

            return False, (
                f"Chat rate limit exceeded for {key}. "
                f"Max {self.requests_per_minute}/min, burst {self.burst_size}."
            )


chat_rate_limiter = PerUserTokenBucket(
    Config.ANALYST_CHAT_RATE_LIMIT_PER_MINUTE,
    Config.ANALYST_CHAT_RATE_LIMIT_BURST,
)

async def analyze_alert(alert_data: Dict) -> Dict:
    """Wrapper for alert analysis"""
    enriched_data = {
        "rule": "Manual Analysis",
        "priority": "High",
        "output": f"Manual analysis request for alert {alert_data.get('id')}",
        "output_fields": {},
        **alert_data
    }
    return await analyst_llm.analyze(enriched_data)

logger = logging.getLogger(__name__)
# Router prefix is /api/analyst, so endpoints like /chat become /api/analyst/chat
router = APIRouter(prefix="/api/analyst", tags=["AI Analyst"])

# Tool definitions for the LLM
AVAILABLE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_recent_alerts",
            "description": "Get recent security alerts from the IDS",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Number of alerts to retrieve", "default": 10},
                    "severity": {"type": "string", "description": "Filter by severity (low, medium, high, critical)"},
                    "source": {"type": "string", "description": "Filter by source (falco, suricata, manual)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_alert_details",
            "description": "Get detailed information about a specific alert",
            "parameters": {
                "type": "object",
                "properties": {
                    "alert_id": {"type": "string", "description": "The unique alert ID"}
                },
                "required": ["alert_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "isolate_pod",
            "description": "Isolate a compromised Kubernetes pod from the network",
            "parameters": {
                "type": "object",
                "properties": {
                    "pod_name": {"type": "string", "description": "Name of the pod to isolate"},
                    "namespace": {"type": "string", "description": "Kubernetes namespace", "default": "smart-city"},
                    "reason": {"type": "string", "description": "Reason for isolation"}
                },
                "required": ["pod_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scale_service",
            "description": "Scale a Kubernetes service up or down",
            "parameters": {
                "type": "object",
                "properties": {
                    "service_name": {"type": "string", "description": "Name of the service"},
                    "namespace": {"type": "string", "description": "Kubernetes namespace", "default": "smart-city"},
                    "replicas": {"type": "integer", "description": "Number of replicas"}
                },
                "required": ["service_name", "replicas"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "block_ip",
            "description": "Block an IP address at the network level",
            "parameters": {
                "type": "object",
                "properties": {
                    "ip_address": {"type": "string", "description": "IP address to block"},
                    "duration_minutes": {"type": "integer", "description": "Block duration", "default": 60},
                    "reason": {"type": "string", "description": "Reason for blocking"}
                },
                "required": ["ip_address"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_status",
            "description": "Get overall system health and status",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_llm_credits",
            "description": "Check remaining LLM API credits across all providers",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_threat",
            "description": "Perform deep analysis on a potential threat using AI",
            "parameters": {
                "type": "object",
                "properties": {
                    "alert_id": {"type": "string", "description": "Alert ID to analyze"},
                    "context": {"type": "string", "description": "Additional context"}
                },
                "required": ["alert_id"]
            }
        }
    }
]

# System prompt for the conversational analyst
SECURITY_ANALYST_SYSTEM_PROMPT = """You are **Kimi Sentinel**, an advanced AI Security Analyst for the Smart City IDS (Intrusion Detection System).

## Your Capabilities
You have real-time access to the entire security infrastructure through specialized tools:
- **Alert Management**: View, filter, and analyze security alerts
- **Incident Response**: Isolate pods, block IPs, scale services
- **Threat Intelligence**: Deep AI-powered threat analysis
- **System Monitoring**: Check health, credits, and performance

## Your Personality
- Professional yet approachable
- Concise but thorough
- Proactive in suggesting actions
- Security-focused with a hint of paranoia (healthy for security!)

## Response Guidelines
1. **Always validate** before taking actions - ask for confirmation on destructive operations
2. **Provide context** - explain WHY you're suggesting something
3. **Use tools** when needed - don't guess, fetch real data
4. **Format clearly** - use markdown, code blocks, and emojis for readability
5. **Credit aware** - monitor LLM usage and suggest cost-effective alternatives when appropriate

## Tool Usage
When you need to perform an action, respond with a tool call in this format:
```tool
{"name": "tool_name", "arguments": {"key": "value"}}
```

You can make multiple tool calls in sequence. Wait for results before proceeding.

## Current Context
- Time: {current_time}
- Session: {session_id}
- Available Providers: {providers}

Remember: You are the guardian of a smart city. Lives and critical infrastructure depend on your vigilance."""

class ChatMessage(BaseModel):
    role: str = Field(..., description="Role: system, user, assistant, or tool")
    content: str = Field(..., description="Message content")
    tool_calls: Optional[List[Dict]] = Field(None, description="Tool calls if any")
    tool_call_id: Optional[str] = Field(None, description="ID of tool call being responded to")

class ConversationRequest(BaseModel):
    messages: List[ChatMessage]
    session_id: Optional[str] = None
    use_tools: bool = True
    stream: bool = False

class ConversationResponse(BaseModel):
    message: ChatMessage
    tool_results: Optional[List[Dict]] = None
    credits_used: Optional[float] = None
    provider_used: str = "unknown"
    intent: Optional[str] = None
    trace_id: Optional[str] = None
    action_selector: Optional[List[Dict[str, Any]]] = None
    confirmation_required: bool = False


class SessionBootstrapResponse(BaseModel):
    session_id: str
    available_tools: List[str]
    available_providers: List[str]
    timestamp: str


class AnalystActionRequest(BaseModel):
    session_id: str
    action_type: str
    target: str
    severity: int = 7
    reason: Optional[str] = None
    confirm: bool = False


class AnalystPendingDecisionRequest(BaseModel):
    action_id: str
    decision: str
    operator: str = "operator"
    comment: Optional[str] = None


def _extract_action_selector(analysis: Any, user_prompt: str) -> List[Dict[str, Any]]:
    """Build actionable suggestions for chat Action-Selector UI."""
    if not isinstance(analysis, dict):
        return []

    suggested = []
    automated_actions = analysis.get("automated_actions") or []
    output_fields = analysis.get("output_fields") or {}
    prompt_text = (user_prompt or "").strip()

    def add_action(action_type: str, target: str, reason: str, severity: int):
        if not target:
            return
        suggested.append({
            "action_type": action_type,
            "target": target,
            "reason": reason,
            "severity": max(1, min(10, int(severity or 7))),
        })

    primary_target = (
        output_fields.get("container.name")
        or output_fields.get("k8s.pod.name")
        or output_fields.get("k8s.pod")
        or analysis.get("target")
    )

    severity = int(analysis.get("severity", 7) or 7)
    summary = str(analysis.get("summary") or "Analyst recommendation")

    for action in automated_actions:
        action_name = str(action or "").strip().lower()
        if action_name == "isolate_pod":
            add_action("isolate_pod", primary_target or "unknown-pod", summary, severity)
        elif action_name == "scale_up":
            add_action("scale_up", primary_target or "unknown-service", summary, severity)
        elif action_name == "block_ip":
            ip_target = output_fields.get("fd.sip") or output_fields.get("src.ip")
            add_action("block_ip", ip_target or "unknown-ip", summary, severity)

    if not suggested and prompt_text:
        lower = prompt_text.lower()
        if "isolate" in lower:
            add_action("isolate_pod", primary_target or "unknown-pod", "User requested isolation", severity)
        if "scale" in lower:
            add_action("scale_up", primary_target or "unknown-service", "User requested scaling", severity)
        if "block" in lower and "ip" in lower:
            add_action("block_ip", output_fields.get("fd.sip") or "unknown-ip", "User requested IP block", severity)

    deduped: List[Dict[str, Any]] = []
    seen = set()
    for item in suggested:
        key = (item["action_type"], item["target"])
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped[:5]


def _execute_security_action(action_type: str, target: str):
    """Execute a selected security action via k8s automation when available."""
    from api._state import k8s_automation

    def normalize_result(result):
        if inspect.isawaitable(result):
            box = {"value": None, "error": None}

            def _runner(awaitable):
                try:
                    box["value"] = asyncio.run(awaitable)
                except Exception as exc:
                    box["error"] = str(exc)

            worker = threading.Thread(target=_runner, args=(result,), daemon=True)
            worker.start()
            worker.join(timeout=20)

            if worker.is_alive():
                return {"success": False, "error": "async action execution timeout"}
            if box["error"] is not None:
                return {"success": False, "error": box["error"]}
            return box["value"]
        return result

    if action_type == "isolate_pod":
        if k8s_automation and hasattr(k8s_automation, "isolate_pod"):
            try:
                return normalize_result(k8s_automation.isolate_pod(target))
            except TypeError:
                return normalize_result(k8s_automation.isolate_pod(target, "smart-city"))
        return {"success": False, "error": "k8s isolate_pod unavailable"}

    if action_type == "scale_up":
        if k8s_automation and hasattr(k8s_automation, "scale_deployment"):
            try:
                return normalize_result(k8s_automation.scale_deployment(target, "smart-city", 3))
            except TypeError:
                return normalize_result(k8s_automation.scale_deployment(target, 3))
        return {"success": False, "error": "k8s scale_deployment unavailable"}

    if action_type == "block_ip":
        return {"success": False, "error": "block_ip execution backend not configured"}

    return {"success": False, "error": f"unsupported action_type: {action_type}"}


def classify_intent(text: str) -> str:
    """Lightweight intent classification for chat UX routing hints."""
    txt = (text or "").lower()
    if any(k in txt for k in ["isolate", "block", "scale", "quarantine", "contain", "evict"]):
        return "action"
    if any(k in txt for k in ["why", "explain", "summary", "analyze", "analysis", "root cause"]):
        return "analysis"
    if any(k in txt for k in ["status", "health", "uptime", "credits", "provider", "metrics"]):
        return "status"
    return "general"

class ToolExecutor:
    """Executes tools on behalf of the AI analyst"""
    
    def __init__(self):
        self.tools: Dict[str, Callable] = {
            "get_recent_alerts": self._get_recent_alerts,
            "get_alert_details": self._get_alert_details,
            "isolate_pod": self._isolate_pod,
            "scale_service": self._scale_service,
            "block_ip": self._block_ip,
            "get_system_status": self._get_system_status,
            "get_llm_credits": self._get_llm_credits,
            "analyze_threat": self._analyze_threat
        }
    
    async def execute(self, tool_name: str, arguments: Dict) -> Dict:
        """Execute a tool by name"""
        if tool_name not in self.tools:
            return {"error": f"Unknown tool: {tool_name}"}
        
        try:
            result = await self.tools[tool_name](**arguments)
            return {"tool": tool_name, "result": result, "success": True}
        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return {"tool": tool_name, "error": str(e), "success": False}
    
    async def _get_recent_alerts(self, limit: int = 10, severity: Optional[str] = None, source: Optional[str] = None) -> List[Dict]:
        """Fetch recent alerts from database"""
        try:
            from api._state import db
            # Assuming db has a method like get_recent_alerts_full or similar, otherwise fallback to stats
            # For now returning mock structure as in original code
            return {
                "alerts": [],
                "message": "This would fetch from your alerts database (implementation pending db method)",
                "filters": {"limit": limit, "severity": severity, "source": source}
            }
        except Exception as e:
             return {"error": f"DB access error: {str(e)}"}
    
    async def _get_alert_details(self, alert_id: str) -> Dict:
        """Get specific alert details"""
        return {"alert_id": alert_id, "details": "Fetch from database"}
    
    async def _isolate_pod(self, pod_name: str, namespace: str = "smart-city", reason: str = "Security isolation") -> Dict:
        """Isolate a pod using k8s automation"""
        # Import your existing k8s automation
        try:
            from k8s_automation import K8sAutomation
            # K8sAutomation is a class, but widely used as k8s_automation instance in _state
            from api._state import k8s_automation
            if k8s_automation:
                 # Check available methods on k8s_automation
                 # Assuming isolate_pod exists or similar
                 # For safety in this insertion, we'll wrap in try-except
                 if hasattr(k8s_automation, 'isolate_pod'):
                     result = k8s_automation.isolate_pod(pod_name, namespace)
                     return {"action": "isolate", "pod": pod_name, "result": result}
                 else:
                     # Check if it has different name (e.g. isolate_workload)
                     # Or check if we should instantiate it locally if _state is None
                     pass
                     return {"error": "Method isolate_pod not found on k8s_automation object"}
            return {"error": "K8s automation not initialized"}
        except Exception as e:
            return {"error": str(e)}
    
    async def _scale_service(self, service_name: str, replicas: int, namespace: str = "smart-city") -> Dict:
        """Scale a service"""
        try:
            from api._state import k8s_automation
            if k8s_automation:
                # Assuming method name is scale_deployment or similar
                if hasattr(k8s_automation, 'scale_deployment'):
                    result = k8s_automation.scale_deployment(service_name, namespace, replicas)
                    return {"action": "scale", "service": service_name, "replicas": replicas, "result": result}
            return {"error": "Method scale_service not found or k8s not initialized"}
        except Exception as e:
            return {"error": str(e)}
    
    async def _block_ip(self, ip_address: str, duration_minutes: int = 60, reason: str = "Threat mitigation") -> Dict:
        """Block an IP address"""
        # Integrate with your network policies
        return {"action": "block_ip", "ip": ip_address, "duration": duration_minutes, "status": "pending"}
    
    async def _get_system_status(self) -> Dict:
        """Get overall system status"""
        credits = await check_all_credits()
        healthy_providers = [p for p, c in credits.items() if c.status == ProviderStatus.HEALTHY]
        
        return {
            "status": "operational",
            "healthy_providers": healthy_providers,
            "llm_credits_status": "healthy" if len(healthy_providers) > 0 else "critical",
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def _get_llm_credits(self) -> Dict:
        """Get LLM credit status"""
        credits = await check_all_credits()
        return {
            provider: {
                "status": info.status,
                "remaining": info.credits,
                "currency": info.currency
            }
            for provider, info in credits.items()
        }
    
    async def _analyze_threat(self, alert_id: str, context: Optional[str] = None) -> Dict:
        """Perform AI threat analysis"""
        # Fetch alert and analyze
        alert_data = {"id": alert_id, "context": context}  # Fetch from DB
        analysis = await analyze_alert(alert_data)
        return analysis

# Initialize tool executor
tool_executor = ToolExecutor()


@router.post("/session", response_model=SessionBootstrapResponse)
async def start_chat_session():
    """Bootstrap a new analyst chat session with tool/provider visibility."""
    session_id = f"chat_{uuid4().hex[:12]}"
    providers: List[str] = []
    try:
        credits = await check_all_credits()
        providers = [
            p for p, c in credits.items()
            if c.status in [ProviderStatus.HEALTHY, ProviderStatus.LOW_CREDIT]
        ]
    except Exception:
        providers = ["xai", "openai", "gemini", "kimi"]

    return SessionBootstrapResponse(
        session_id=session_id,
        available_tools=list(tool_executor.tools.keys()),
        available_providers=providers,
        timestamp=datetime.utcnow().isoformat(),
    )

@router.post("/chat", response_model=ConversationResponse)
async def chat_with_analyst(request: ConversationRequest, http_request: Request):
    """
    Have a conversation with the AI security analyst.
    
    The analyst can:
    - Answer questions about security alerts
    - Perform actions (isolate pods, block IPs)
    - Analyze threats in depth
    - Check system status and credits
    """
    try:
        session_key = (request.session_id or "").strip()
        client_host = (http_request.client.host if http_request and http_request.client else "anonymous") or "anonymous"
        user_key = session_key or f"ip:{client_host}"

        allowed, limit_reason = await chat_rate_limiter.acquire(user_key)
        if not allowed:
            try:
                from api._state import add_audit_event
                add_audit_event(
                    "CHAT_RATE_LIMITED",
                    trace_id=f"chat-{session_key or client_host}",
                    user=user_key,
                    status="blocked",
                    payload={"reason": limit_reason},
                )
            except Exception:
                pass
            raise HTTPException(status_code=429, detail=limit_reason)

        started = datetime.utcnow()
        # Build system prompt with current context
        try:
            credits = await check_all_credits()
            # Filter providers by status string
            providers = [p for p, c in credits.items() if c.status in [ProviderStatus.HEALTHY, ProviderStatus.LOW_CREDIT]]
        except Exception as e:
            logger.warning(f"Credit check failed: {e}")
            providers = ["xai", "openai"] # Fallback
        
        system_prompt = (
            SECURITY_ANALYST_SYSTEM_PROMPT
            .replace("{current_time}", datetime.utcnow().isoformat())
            .replace("{session_id}", request.session_id or "anonymous")
            .replace("{providers}", ", ".join(providers) if providers else "none available")
        )
        
        # Prepare messages for LLM
        messages = [{"role": "system", "content": system_prompt}]
        
        for msg in request.messages:
            msg_dict = {"role": msg.role, "content": msg.content}
            if msg.tool_calls:
                msg_dict["tool_calls"] = msg.tool_calls
            if msg.tool_call_id:
                msg_dict["tool_call_id"] = msg.tool_call_id
            messages.append(msg_dict)
        
        # Call LLM with tool support
        # This uses the enhanced manager but with tool-enabled models
        response = await analyst_llm.analyze_security_alert(
            alert_data={"conversation": messages, "tools_available": request.use_tools},
            system_prompt=system_prompt,
            force_provider=None  # Auto-select based on credits
        )
        
        # Parse response for tool calls
        analysis = response.get("analysis")
        content = ""
        if isinstance(analysis, dict):
            content = (
                str(
                    analysis.get("raw_analysis")
                    or analysis.get("summary")
                    or analysis.get("message")
                    or ""
                ).strip()
            )
            if not content:
                severity = analysis.get("severity")
                threat_type = analysis.get("threat_type") or "Unknown"
                recommendations = analysis.get("recommendations") or []
                rec_line = ""
                if isinstance(recommendations, list) and recommendations:
                    rec_line = f" Recommended actions: {', '.join(map(str, recommendations[:3]))}."
                sev_line = f" Severity: {severity}/10." if severity is not None else ""
                content = f"Threat analysis complete. Type: {threat_type}.{sev_line}{rec_line}".strip()
        elif isinstance(analysis, str):
            content = analysis.strip()

        if not content:
            content = str(
                response.get("message")
                or response.get("summary")
                or response.get("detail")
                or ""
            ).strip()

        if not content:
            content = (
                "Analysis service returned an empty response. "
                "Please retry. If this persists, verify provider status and API keys."
            )
        
        # Check for tool calls in response (if model supports it)
        tool_results = []
        if request.use_tools and "```tool" in content:
            # Extract and execute tool calls
            import re
            tool_pattern = r'```tool\\n(.*?)\\n```'
            matches = re.findall(tool_pattern, content, re.DOTALL)
            
            for match in matches:
                try:
                    tool_call = json.loads(match)
                    result = await tool_executor.execute(
                        tool_call.get('name'),
                        tool_call.get('arguments', {})
                    )
                    tool_results.append(result)
                    
                    # Append tool result to conversation
                    messages.append({
                        "role": "tool",
                        "content": json.dumps(result),
                        "tool_call_id": tool_call.get('id', 'unknown')
                    })
                    
                except json.JSONDecodeError:
                    tool_results.append({"error": "Invalid tool call format", "raw": match})
        
        user_intent = classify_intent(request.messages[-1].content if request.messages else "")
        trace_id = f"chat-{request.session_id or uuid4().hex[:8]}"
        action_selector = _extract_action_selector(
            analysis if isinstance(analysis, dict) else {},
            request.messages[-1].content if request.messages else "",
        )

        try:
            from api._state import add_audit_event
            add_audit_event(
                "CHAT_ANALYSIS",
                trace_id=trace_id,
                severity=(analysis or {}).get("severity") if isinstance(analysis, dict) else None,
                user="analyst-chat",
                status="ok",
                payload={
                    "intent": user_intent,
                    "provider": response.get("provider", "unknown"),
                    "session_id": request.session_id,
                    "action_suggestions": action_selector,
                },
            )
        except Exception as audit_error:
            logger.debug(f"Skipped chat audit event: {audit_error}")

        response_obj = ConversationResponse(
            message=ChatMessage(
                role="assistant",
                content=content,
                tool_calls=None
            ),
            tool_results=tool_results if tool_results else None,
            credits_used=response.get('credit_info', {}).get('estimated_cost_usd'),
            provider_used=response.get('provider', 'unknown'),
            intent=user_intent,
            trace_id=trace_id,
            action_selector=action_selector if action_selector else None,
            confirmation_required=bool(action_selector),
        )

        try:
            from api._state import record_llm_usage, set_llm_last_provider_used
            provider = response_obj.provider_used or "unknown"
            latency_s = max(0.0, (datetime.utcnow() - started).total_seconds())
            ok = response.get("status") in ("success", "fallback")
            record_llm_usage(
                provider,
                latency_s=latency_s,
                success=ok,
                prompt_payload=messages,
                completion_payload=content,
                usage=response.get("usage"),
                purpose="analyst_chat",
                model=response.get("model"),
            )
            set_llm_last_provider_used(provider)
        except Exception as metrics_error:
            logger.debug(f"Skipped chat metrics tracking: {metrics_error}")

        return response_obj
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.websocket("/ws")
async def analyst_websocket(websocket: WebSocket):
    """WebSocket for real-time analyst chat"""
    await websocket.accept()
    session_id = f"ws_{datetime.utcnow().timestamp()}"
    
    try:
        while True:
            # Receive message
            data = await websocket.receive_text()
            request = json.loads(data)
            
            # Process through chat endpoint logic
            conversation_request = ConversationRequest(
                messages=[ChatMessage(role="user", content=request.get('message'))],
                session_id=session_id,
                use_tools=request.get('use_tools', True)
            )
            
            # Get response (simplified for WebSocket)
            credits = await check_all_credits()
            providers = [p for p, c in credits.items() if c.status == ProviderStatus.HEALTHY]
            
            response_data = {
                "type": "message",
                "content": f"Received: {request.get('message')}",
                "session_id": session_id,
                "available_providers": providers,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            await websocket.send_json(response_data)
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.close()
        except:
            pass

@router.get("/tools")
async def list_available_tools():
    """List all available tools the analyst can use"""
    return {"tools": AVAILABLE_TOOLS}


@router.post("/action/submit")
async def submit_analyst_action(payload: AnalystActionRequest):
    """Submit a selected chat action with an explicit HITL confirmation gate."""
    from governance import request_automated_action
    from api._state import add_audit_event

    trace_id = f"chat-{payload.session_id}"

    if not payload.confirm:
        add_audit_event(
            "HITL_CONFIRMATION_REQUIRED",
            trace_id=trace_id,
            severity=payload.severity,
            user="analyst-chat",
            status="pending",
            payload={
                "action_type": payload.action_type,
                "target": payload.target,
                "reason": payload.reason,
            },
        )
        return {
            "status": "confirmation_required",
            "trace_id": trace_id,
            "action": payload.model_dump(),
            "message": "Confirm this action to submit it through governance controls.",
        }

    governance_result = request_automated_action(
        action_type=payload.action_type,
        target=payload.target,
        severity=payload.severity,
        reason=payload.reason or "Requested by analyst chat action-selector",
        execute_fn=lambda: _execute_security_action(payload.action_type, payload.target),
    )

    add_audit_event(
        "GOVERNANCE_DECISION",
        trace_id=trace_id,
        severity=payload.severity,
        user="analyst-chat",
        status="ok" if governance_result.get("status") in ("executed", "approved_and_executed") else "pending",
        payload={
            "decision": governance_result.get("status"),
            "action": payload.action_type,
            "target": payload.target,
            "governance_action": (governance_result.get("action") or {}).get("id"),
            "reason": payload.reason,
        },
    )

    return {
        "status": governance_result.get("status"),
        "trace_id": trace_id,
        "governance": governance_result,
    }


@router.post("/action/pending-decision")
async def decide_pending_action(payload: AnalystPendingDecisionRequest):
    """Approve or reject a governance-pending action from chat UI."""
    from governance import approve_pending_action, reject_pending_action, governance
    from api._state import add_audit_event

    decision = (payload.decision or "").strip().lower()
    if decision not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="decision must be 'approve' or 'reject'")

    if decision == "approve":
        pending = governance._pending_actions.get(payload.action_id)
        execute_fn = None
        if pending:
            execute_fn = lambda: _execute_security_action(pending.action_type, pending.target)
        result = approve_pending_action(
            payload.action_id,
            operator=payload.operator,
            execute_fn=execute_fn,
            operator_comment=payload.comment,
        )
    else:
        result = reject_pending_action(
            payload.action_id,
            operator=payload.operator,
            reason=payload.comment,
        )

    action = result.get("action") or {}
    trace_id = f"chat-{action.get('alert_id') or payload.action_id}"
    add_audit_event(
        "HITL_DECISION",
        trace_id=trace_id,
        severity=action.get("severity"),
        user=payload.operator,
        status="ok" if result.get("status") in ("approved_and_executed", "rejected") else "error",
        payload={
            "decision": decision,
            "action_id": payload.action_id,
            "result": result.get("status"),
            "comment": payload.comment,
        },
    )

    return {"status": result.get("status"), "result": result, "trace_id": trace_id}

@router.post("/quick-analyze")
async def quick_analyze_alert(alert_id: str):
    """Quick analysis of a specific alert"""
    try:
        # Fetch alert from database
        alert_data = {"id": alert_id, "source": "database"}  # Replace with actual DB fetch
        
        analysis = await analyze_alert(alert_data)
        
        return {
            "alert_id": alert_id,
            "analysis": analysis.get('analysis'),
            "provider": analysis.get('provider'),
            "cost": analysis.get('credit_info', {}).get('estimated_cost_usd')
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
