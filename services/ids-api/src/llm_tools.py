"""
LLM Tools System — Smart City IDS
===================================

Provides function calling capabilities for LLM security analysts.
Allows the LLM to query system state and execute defensive actions.

Tools are exposed to LLMs in OpenAI-style function format and can be:
- Queried for system information (read-only)
- Executed for defensive actions (write operations)

Usage:
    from llm_tools import ToolRegistry, execute_tool_call
    
    # LLM calls a function
    result = await execute_tool_call("isolate_pod", {"pod_name": "camera-123"})
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum
import json
import functools

# Import system components
try:
    from llm_credit_checker import credit_checker
    from governance import GovernanceController
    from k8s_automation import K8sAutomation
    from database import db
except ImportError:
    credit_checker = None
    GovernanceController = None
    K8sAutomation = None
    db = None

logger = logging.getLogger(__name__)


class ToolCategory(Enum):
    """Tool categories for organization"""
    QUERY = "query"           # Read-only operations
    ACTION = "action"         # Write operations
    GOVERNANCE = "governance" # Human-in-the-loop operations


@dataclass
class ToolParameter:
    """Parameter definition for a tool"""
    name: str
    type: str
    description: str
    required: bool = True
    enum: Optional[List[str]] = None
    default: Any = None


@dataclass
class Tool:
    """Tool definition"""
    name: str
    description: str
    category: ToolCategory
    parameters: List[ToolParameter]
    handler: Callable[..., Awaitable[Any]]
    requires_approval: bool = False
    allowed_in_mode: List[str] = field(default_factory=lambda: ["autopilot", "assisted", "manual"])
    
    def to_openai_schema(self) -> Dict[str, Any]:
        """Convert to OpenAI function schema"""
        properties = {}
        required = []
        
        for param in self.parameters:
            prop = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            properties[param.name] = prop
            
            if param.required:
                required.append(param.name)
        
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        }


class ToolRegistry:
    """Registry of available LLM tools"""
    
    _instance = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        self._tools: Dict[str, Tool] = {}
        self._register_default_tools()
    
    def register(self, tool: Tool):
        """Register a tool"""
        self._tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")
    
    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name"""
        return self._tools.get(name)
    
    def list_tools(self, category: Optional[ToolCategory] = None) -> List[Tool]:
        """List all tools, optionally filtered by category"""
        if category:
            return [t for t in self._tools.values() if t.category == category]
        return list(self._tools.values())
    
    def get_openai_schemas(self) -> List[Dict[str, Any]]:
        """Get all tools in OpenAI function schema format"""
        return [t.to_openai_schema() for t in self._tools.values()]
    
    def _register_default_tools(self):
        """Register the default set of tools"""
        
        # ==================== QUERY TOOLS ====================
        
        self.register(Tool(
            name="get_system_health",
            description="Get overall system health status including LLM providers, Kubernetes cluster, and database",
            category=ToolCategory.QUERY,
            parameters=[],
            handler=self._get_system_health
        ))
        
        self.register(Tool(
            name="get_credit_status",
            description="Get LLM provider credit balances and status",
            category=ToolCategory.QUERY,
            parameters=[
                ToolParameter("force_refresh", "boolean", "Force fresh credit check", required=False, default=False)
            ],
            handler=self._get_credit_status
        ))
        
        self.register(Tool(
            name="get_active_alerts",
            description="Get recent security alerts with optional filtering",
            category=ToolCategory.QUERY,
            parameters=[
                ToolParameter("limit", "integer", "Maximum number of alerts to return", required=False, default=10),
                ToolParameter("severity_min", "integer", "Minimum severity filter (1-10)", required=False, default=0),
                ToolParameter("source", "string", "Filter by source (falco, suricata, iot)", required=False)
            ],
            handler=self._get_active_alerts
        ))
        
        self.register(Tool(
            name="get_pod_status",
            description="Get Kubernetes pod status for a namespace",
            category=ToolCategory.QUERY,
            parameters=[
                ToolParameter("namespace", "string", "Kubernetes namespace", required=False, default="smart-city")
            ],
            handler=self._get_pod_status
        ))
        
        self.register(Tool(
            name="get_network_policies",
            description="Get active network isolation policies",
            category=ToolCategory.QUERY,
            parameters=[
                ToolParameter("namespace", "string", "Kubernetes namespace", required=False, default="smart-city")
            ],
            handler=self._get_network_policies
        ))
        
        self.register(Tool(
            name="get_iot_devices",
            description="Get registered IoT device inventory",
            category=ToolCategory.QUERY,
            parameters=[],
            handler=self._get_iot_devices
        ))
        
        self.register(Tool(
            name="get_governance_queue",
            description="Get pending governance actions awaiting approval",
            category=ToolCategory.QUERY,
            parameters=[],
            handler=self._get_governance_queue
        ))
        
        self.register(Tool(
            name="get_alert_details",
            description="Get detailed information about a specific alert",
            category=ToolCategory.QUERY,
            parameters=[
                ToolParameter("alert_id", "integer", "Alert ID to retrieve")
            ],
            handler=self._get_alert_details
        ))
        
        # ==================== ACTION TOOLS ====================
        
        self.register(Tool(
            name="isolate_pod",
            description="Isolate a compromised pod by creating a deny-all NetworkPolicy. Use for confirmed threats.",
            category=ToolCategory.ACTION,
            parameters=[
                ToolParameter("pod_name", "string", "Name of the pod to isolate"),
                ToolParameter("namespace", "string", "Kubernetes namespace", required=False, default="smart-city"),
                ToolParameter("reason", "string", "Reason for isolation", required=False)
            ],
            handler=self._isolate_pod,
            requires_approval=True,
            allowed_in_mode=["autopilot", "assisted"]
        ))
        
        self.register(Tool(
            name="scale_service",
            description="Scale a service to handle increased load. Use for DDoS mitigation or capacity issues.",
            category=ToolCategory.ACTION,
            parameters=[
                ToolParameter("service_name", "string", "Name of the service to scale"),
                ToolParameter("replicas", "integer", "Target number of replicas"),
                ToolParameter("namespace", "string", "Kubernetes namespace", required=False, default="smart-city")
            ],
            handler=self._scale_service,
            requires_approval=False,
            allowed_in_mode=["autopilot", "assisted", "manual"]
        ))
        
        self.register(Tool(
            name="block_ip",
            description="Block a malicious IP address at the network level",
            category=ToolCategory.ACTION,
            parameters=[
                ToolParameter("ip_address", "string", "IP address to block"),
                ToolParameter("namespace", "string", "Kubernetes namespace", required=False, default="smart-city"),
                ToolParameter("duration_minutes", "integer", "Block duration (0 = permanent)", required=False, default=0)
            ],
            handler=self._block_ip,
            requires_approval=True,
            allowed_in_mode=["autopilot", "assisted"]
        ))
        
        self.register(Tool(
            name="restart_service",
            description="Perform a rolling restart of a service",
            category=ToolCategory.ACTION,
            parameters=[
                ToolParameter("service_name", "string", "Name of the service to restart"),
                ToolParameter("namespace", "string", "Kubernetes namespace", required=False, default="smart-city")
            ],
            handler=self._restart_service,
            requires_approval=True,
            allowed_in_mode=["autopilot", "assisted"]
        ))
        
        # ==================== GOVERNANCE TOOLS ====================
        
        self.register(Tool(
            name="approve_action",
            description="Approve a pending governance action",
            category=ToolCategory.GOVERNANCE,
            parameters=[
                ToolParameter("action_id", "string", "ID of the action to approve"),
                ToolParameter("operator", "string", "Name/ID of the approving operator"),
                ToolParameter("comment", "string", "Approval comment", required=False, default="")
            ],
            handler=self._approve_action,
            allowed_in_mode=["assisted", "manual"]
        ))
        
        self.register(Tool(
            name="reject_action",
            description="Reject a pending governance action",
            category=ToolCategory.GOVERNANCE,
            parameters=[
                ToolParameter("action_id", "string", "ID of the action to reject"),
                ToolParameter("operator", "string", "Name/ID of the rejecting operator"),
                ToolParameter("reason", "string", "Rejection reason")
            ],
            handler=self._reject_action,
            allowed_in_mode=["assisted", "manual"]
        ))
        
        self.register(Tool(
            name="set_governance_mode",
            description="Change the automation governance mode",
            category=ToolCategory.GOVERNANCE,
            parameters=[
                ToolParameter("mode", "string", "New governance mode", enum=["autopilot", "assisted", "manual"])
            ],
            handler=self._set_governance_mode,
            allowed_in_mode=["autopilot", "assisted", "manual"]
        ))
    
    # ==================== TOOL HANDLERS ====================
    
    async def _get_system_health(self) -> Dict[str, Any]:
        """Get overall system health"""
        health = {
            "timestamp": datetime.now().isoformat(),
            "llm_providers": credit_checker.get_health_summary() if credit_checker else {"status": "unknown"},
            "kubernetes": {"status": "unknown"},
            "database": {"status": "unknown"},
            "falco": {"status": "unknown"},
            "suricata": {"status": "unknown"},
        }
        
        # Check K8s
        try:
            if K8sAutomation:
                k8s = K8sAutomation()
                health["kubernetes"]["status"] = "healthy" if k8s.check_connection() else "unhealthy"
        except Exception as e:
            health["kubernetes"]["error"] = str(e)
        
        # Check DB
        try:
            if db:
                health["database"]["status"] = "connected" if not db.use_memory else "memory_fallback"
        except Exception as e:
            health["database"]["error"] = str(e)
        
        return health
    
    async def _get_credit_status(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Get LLM credit status"""
        if not credit_checker:
            return {"status": "error", "message": "Credit checker not available"}
        
        try:
            credits = await credit_checker.check_all_providers(force_refresh)
            return {
                "status": "success",
                "providers": {name: info.to_dict() for name, info in credits.items()}
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def _get_active_alerts(self, limit: int = 10, severity_min: int = 0, source: Optional[str] = None) -> Dict[str, Any]:
        """Get recent alerts"""
        if not db:
            return {"status": "error", "message": "Database not available"}
        
        try:
            alerts = db.get_alerts(limit=limit)
            # Filter by severity and source if provided
            filtered = []
            for alert in alerts:
                if severity_min > 0 and alert.get("severity", 0) < severity_min:
                    continue
                if source and alert.get("source") != source:
                    continue
                filtered.append(alert)
            
            return {
                "status": "success",
                "count": len(filtered),
                "alerts": filtered
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def _get_pod_status(self, namespace: str = "smart-city") -> Dict[str, Any]:
        """Get pod status"""
        try:
            from kubernetes import client, config
            config.load_kube_config()
            v1 = client.CoreV1Api()
            
            pods = v1.list_namespaced_pod(namespace=namespace)
            pod_list = []
            
            for pod in pods.items:
                pod_list.append({
                    "name": pod.metadata.name,
                    "status": pod.status.phase,
                    "ready": pod.status.container_statuses[0].ready if pod.status.container_statuses else False,
                    "restarts": pod.status.container_statuses[0].restart_count if pod.status.container_statuses else 0,
                    "ip": pod.status.pod_ip,
                    "node": pod.spec.node_name
                })
            
            return {
                "status": "success",
                "namespace": namespace,
                "pods": pod_list,
                "total": len(pod_list)
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def _get_network_policies(self, namespace: str = "smart-city") -> Dict[str, Any]:
        """Get network policies"""
        try:
            from kubernetes import client, config
            config.load_kube_config()
            networking = client.NetworkingV1Api()
            
            policies = networking.list_namespaced_network_policy(namespace=namespace)
            policy_list = []
            
            for policy in policies.items:
                policy_list.append({
                    "name": policy.metadata.name,
                    "pod_selector": policy.spec.pod_selector.match_labels,
                    "policy_types": policy.spec.policy_types
                })
            
            return {
                "status": "success",
                "namespace": namespace,
                "policies": policy_list,
                "total": len(policy_list)
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def _get_iot_devices(self) -> Dict[str, Any]:
        """Get IoT devices"""
        if not db:
            return {"status": "error", "message": "Database not available"}
        
        try:
            devices = db.get_iot_devices()
            return {
                "status": "success",
                "count": len(devices),
                "devices": devices
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def _get_governance_queue(self) -> Dict[str, Any]:
        """Get governance queue"""
        try:
            if GovernanceController:
                gov = GovernanceController()
                pending = gov.get_pending_actions()
                return {
                    "status": "success",
                    "mode": gov.get_mode().value,
                    "pending_count": len(pending),
                    "pending_actions": [p.to_dict() for p in pending]
                }
            return {"status": "error", "message": "Governance not available"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def _get_alert_details(self, alert_id: int) -> Dict[str, Any]:
        """Get alert details"""
        if not db:
            return {"status": "error", "message": "Database not available"}
        
        try:
            alert = db.get_alert(alert_id)
            if alert:
                return {"status": "success", "alert": alert}
            return {"status": "error", "message": f"Alert {alert_id} not found"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def _isolate_pod(self, pod_name: str, namespace: str = "smart-city", reason: Optional[str] = None) -> Dict[str, Any]:
        """Isolate a pod"""
        try:
            if K8sAutomation:
                k8s = K8sAutomation()
                await k8s.isolate_pod(pod_name, namespace)
                return {
                    "status": "success",
                    "message": f"Pod {pod_name} isolated",
                    "network_policy": f"isolate-{pod_name}"
                }
            return {"status": "error", "message": "K8s automation not available"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def _scale_service(self, service_name: str, replicas: int, namespace: str = "smart-city") -> Dict[str, Any]:
        """Scale a service"""
        try:
            if K8sAutomation:
                k8s = K8sAutomation()
                await k8s.scale_deployment(service_name, replicas, namespace)
                return {
                    "status": "success",
                    "message": f"Scaled {service_name} to {replicas} replicas"
                }
            return {"status": "error", "message": "K8s automation not available"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def _block_ip(self, ip_address: str, namespace: str = "smart-city", duration_minutes: int = 0) -> Dict[str, Any]:
        """Block an IP"""
        try:
            if K8sAutomation:
                k8s = K8sAutomation()
                await k8s.block_ip(ip_address, namespace)
                return {
                    "status": "success",
                    "message": f"IP {ip_address} blocked",
                    "duration": "permanent" if duration_minutes == 0 else f"{duration_minutes} minutes"
                }
            return {"status": "error", "message": "K8s automation not available"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def _restart_service(self, service_name: str, namespace: str = "smart-city") -> Dict[str, Any]:
        """Restart a service"""
        try:
            if K8sAutomation:
                k8s = K8sAutomation()
                await k8s.restart_service(service_name, namespace)
                return {
                    "status": "success",
                    "message": f"Service {service_name} restarted"
                }
            return {"status": "error", "message": "K8s automation not available"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def _approve_action(self, action_id: str, operator: str, comment: str = "") -> Dict[str, Any]:
        """Approve a governance action"""
        try:
            if GovernanceController:
                gov = GovernanceController()
                result = gov.approve_action(action_id, operator, comment)
                return {
                    "status": "success",
                    "message": f"Action {action_id} approved",
                    "result": result
                }
            return {"status": "error", "message": "Governance not available"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def _reject_action(self, action_id: str, operator: str, reason: str) -> Dict[str, Any]:
        """Reject a governance action"""
        try:
            if GovernanceController:
                gov = GovernanceController()
                result = gov.reject_action(action_id, operator, reason)
                return {
                    "status": "success",
                    "message": f"Action {action_id} rejected",
                    "result": result
                }
            return {"status": "error", "message": "Governance not available"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def _set_governance_mode(self, mode: str) -> Dict[str, Any]:
        """Set governance mode"""
        try:
            if GovernanceController:
                gov = GovernanceController()
                gov.set_mode(mode)
                return {
                    "status": "success",
                    "message": f"Governance mode set to {mode}"
                }
            return {"status": "error", "message": "Governance not available"}
        except Exception as e:
            return {"status": "error", "message": str(e)}


# Singleton instance
tool_registry = ToolRegistry()


async def execute_tool_call(name: str, arguments: Dict[str, Any], governance_mode: str = "assisted") -> Dict[str, Any]:
    """
    Execute a tool call with governance checks.
    
    Args:
        name: Tool name
        arguments: Tool arguments
        governance_mode: Current governance mode
        
    Returns:
        Tool execution result
    """
    tool = tool_registry.get(name)
    if not tool:
        return {"status": "error", "message": f"Unknown tool: {name}"}
    
    # Check if tool is allowed in current mode
    if governance_mode not in tool.allowed_in_mode:
        return {
            "status": "blocked",
            "message": f"Tool '{name}' not allowed in {governance_mode} mode"
        }
    
    # Check if approval is required
    if tool.requires_approval and governance_mode == "assisted":
        # Queue for approval
        try:
            if GovernanceController:
                gov = GovernanceController()
                action_id = gov.propose_action(
                    action_type=name,
                    target=arguments.get("pod_name") or arguments.get("service_name") or arguments.get("ip_address"),
                    severity=8,  # Tool actions are typically high severity
                    reason=f"LLM requested: {name}({json.dumps(arguments)})",
                    recommended_by="llm_analyst"
                )
                return {
                    "status": "pending_approval",
                    "message": f"Action queued for approval (ID: {action_id})",
                    "action_id": action_id
                }
        except Exception as e:
            logger.error(f"Failed to queue action: {e}")
    
    # Execute the tool
    try:
        result = await tool.handler(**arguments)
        return result
    except Exception as e:
        logger.error(f"Tool execution failed: {e}")
        return {"status": "error", "message": str(e)}


# Export
__all__ = [
    "ToolRegistry",
    "Tool",
    "ToolCategory",
    "ToolParameter",
    "tool_registry",
    "execute_tool_call",
]


# Add missing import
from datetime import datetime
