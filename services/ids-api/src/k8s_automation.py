"""Kubernetes Automation - REAL Actions.

Executes defensive actions on the K8s cluster.

Important: The official Kubernetes Python client is synchronous.
This module is used from FastAPI async request handlers; therefore any
Kubernetes API calls must be executed off the event loop to avoid
stalling HTTP responsiveness (which can trip readiness/liveness probes).
"""

import asyncio
import logging
from typing import Optional
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import os
import time

logger = logging.getLogger(__name__)

class K8sAutomation:
    """Kubernetes automation for defensive actions"""
    
    def __init__(self):
        try:
            # Try in-cluster config first (for running inside K8s)
            try:
                config.load_incluster_config()
                logger.info("Loaded in-cluster Kubernetes config")
            except:
                # Fall back to kubeconfig file (for local development)
                config.load_kube_config()
                logger.info("Loaded kubeconfig file")
            
            # Read automation mode (manual | assisted | autonomous | emergency)
            self.automation_mode = os.getenv('AUTOMATION_MODE', 'assisted').lower()

            # Initialize API clients
            self.apps_v1 = client.AppsV1Api()
            self.core_v1 = client.CoreV1Api()
            self.networking_v1 = client.NetworkingV1Api()
            self.custom_objects = client.CustomObjectsApi()
            
            logger.info("Kubernetes client initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Kubernetes client: {e}")
            raise

    async def _call_k8s(self, fn, *args, timeout_s: float = 3.0, **kwargs):
        """Run a synchronous Kubernetes client call off the event loop.

        Args:
            fn: Callable (bound method) from kubernetes.client.*Api.
            timeout_s: Hard timeout for the *overall* call.
        """
        return await asyncio.wait_for(asyncio.to_thread(fn, *args, **kwargs), timeout=timeout_s)

    async def create_threat_response(
        self,
        *,
        alert_id: str,
        target_resource: str,
        severity: int,
        actions: list,
        namespace: str = "smart-city",
        trace_id: Optional[str] = None,
    ) -> dict:
        """Create a ThreatResponse CRD resource for operator-driven reconciliation."""
        if self.automation_mode == 'dry-run':
            logger.info(
                "[DRY-RUN] Would create ThreatResponse (alert_id=%s, target=%s, severity=%s, actions=%s)",
                alert_id,
                target_resource,
                severity,
                actions,
            )
            return {"success": True, "status": "dry-run"}

        if os.getenv("K8S_USE_THREATRESPONSE_CRD", "true").lower() != "true":
            return {"success": False, "status": "disabled", "reason": "K8S_USE_THREATRESPONSE_CRD=false"}

        crd_name = f"tr-{str(alert_id).lower().replace('_', '-')}-{int(time.time())}"
        crd_name = ''.join(ch if (ch.isalnum() or ch == '-') else '-' for ch in crd_name)[:63].strip('-') or f"tr-{int(time.time())}"

        body = {
            "apiVersion": "ids.smartcity.local/v1alpha1",
            "kind": "ThreatResponse",
            "metadata": {
                "name": crd_name,
                "namespace": namespace,
                "labels": {
                    "app.kubernetes.io/managed-by": "smart-city-ids-api",
                    "ids.smartcity.local/trace-id": (trace_id or "none")[:63],
                },
            },
            "spec": {
                "alertId": str(target_resource or alert_id),
                "severity": int(severity),
                "actions": [str(a) for a in (actions or [])],
            },
        }

        try:
            created = await self._call_k8s(
                self.custom_objects.create_namespaced_custom_object,
                group="ids.smartcity.local",
                version="v1alpha1",
                namespace=namespace,
                plural="threatresponses",
                body=body,
                timeout_s=5.0,
            )
            logger.info("✅ ThreatResponse created: %s", crd_name)
            return {
                "success": True,
                "name": created.get("metadata", {}).get("name", crd_name),
                "namespace": namespace,
            }
        except ApiException as e:
            if e.status == 409:
                logger.warning("ThreatResponse already exists: %s", crd_name)
                return {"success": True, "name": crd_name, "namespace": namespace, "status": "exists"}
            logger.error(f"Failed to create ThreatResponse: {e}")
            return {"success": False, "error": str(e)}
    
    def check_connection(self) -> bool:
        """Check if Kubernetes is accessible"""
        try:
            self.core_v1.list_namespace(_request_timeout=(1, 2))
            return True
        except:
            return False
    
    async def isolate_pod(self, pod_name: str, namespace: str):
        """Isolate compromised pod using NetworkPolicy"""
        # Dry-run: log intent but do not execute
        if self.automation_mode == 'dry-run':
            logger.info(f"[DRY-RUN] Would isolate pod: {pod_name} in {namespace}")
            return

        try:
            policy_name = f"isolate-{pod_name}"
            network_policy = client.V1NetworkPolicy(
                metadata=client.V1ObjectMeta(
                    name=policy_name,
                    namespace=namespace
                ),
                spec=client.V1NetworkPolicySpec(
                    pod_selector=client.V1LabelSelector(
                        match_labels={"pod-name": pod_name}
                    ),
                    policy_types=["Ingress", "Egress"],
                    ingress=[],
                    egress=[]
                )
            )

            await self._call_k8s(
                self.networking_v1.create_namespaced_network_policy,
                namespace=namespace,
                body=network_policy,
                timeout_s=5.0,
            )
            
            logger.info(f"✅ Isolated pod: {pod_name} in {namespace}")
            
        except ApiException as e:
            if e.status == 409:
                logger.warning(f"NetworkPolicy already exists for {pod_name}")
            else:
                logger.error(f"Failed to isolate pod: {e}")
                raise
    
    async def scale_deployment(self, service_name: str, replicas: int = 5, namespace: str = "smart-city"):
        """Scale deployment to handle increased load"""
        # Dry-run: log intent but do not execute
        if self.automation_mode == 'dry-run':
            logger.info(f"[DRY-RUN] Would scale {service_name} to {replicas} replicas in {namespace}")
            return

        try:
            deployment_name = f"{service_name}-deployment"
            deployment = await self._call_k8s(
                self.apps_v1.read_namespaced_deployment,
                name=deployment_name,
                namespace=namespace,
                timeout_s=5.0,
            )
            deployment.spec.replicas = replicas

            await self._call_k8s(
                self.apps_v1.patch_namespaced_deployment,
                name=deployment_name,
                namespace=namespace,
                body=deployment,
                timeout_s=5.0,
            )
            
            logger.info(f"✅ Scaled {service_name} to {replicas} replicas")
            
        except ApiException as e:
            logger.error(f"Failed to scale deployment: {e}")
            raise
    
    async def cordon_node(self, node_name: str):
        """Cordon node to prevent new pods"""
        # Dry-run: log intent but do not execute
        if self.automation_mode == 'dry-run':
            logger.info(f"[DRY-RUN] Would cordon node: {node_name}")
            return

        try:
            body = {"spec": {"unschedulable": True}}
            await self._call_k8s(self.core_v1.patch_node, node_name, body, timeout_s=5.0)
            logger.info(f"✅ Cordoned node: {node_name}")
        except ApiException as e:
            logger.error(f"Failed to cordon node: {e}")
            raise
    
    async def block_ip(self, ip_address: str, namespace: str = "smart-city", target_workload: Optional[str] = None):
        """Block source IP for a specific workload using a scoped egress NetworkPolicy.

        Safety:
        - Never uses `podSelector: {}` to avoid namespace-wide lockouts.
        - Requires `target_workload` so only affected pods are constrained.
        """
        # Dry-run: log intent but do not execute
        if self.automation_mode == 'dry-run':
            logger.info(
                f"[DRY-RUN] Would block IP: {ip_address} in {namespace} "
                f"(target_workload={target_workload})"
            )
            return

        try:
            if not target_workload:
                raise ValueError("target_workload is required for safe IP blocking")

            policy_name = f"block-{ip_address.replace('.', '-')}"
            network_policy = client.V1NetworkPolicy(
                metadata=client.V1ObjectMeta(
                    name=policy_name,
                    namespace=namespace
                ),
                spec=client.V1NetworkPolicySpec(
                    pod_selector=client.V1LabelSelector(match_labels={"app": target_workload}),
                    policy_types=["Egress"],
                    egress=[
                        client.V1NetworkPolicyEgressRule(
                            to=[
                                client.V1NetworkPolicyPeer(
                                    ip_block=client.V1IPBlock(
                                        cidr="0.0.0.0/0",
                                        _except=[f"{ip_address}/32"]
                                    )
                                )
                            ]
                        )
                    ]
                )
            )

            await self._call_k8s(
                self.networking_v1.create_namespaced_network_policy,
                namespace=namespace,
                body=network_policy,
                timeout_s=5.0,
            )
            
            logger.info(f"✅ Scoped IP block applied: {ip_address} (workload={target_workload})")
            
        except ApiException as e:
            if e.status == 409:
                logger.warning(f"IP block already exists for {ip_address} (workload={target_workload})")
            else:
                logger.error(f"Failed to block IP: {e}")
                raise
    
    async def restart_service(self, service_name: str, namespace: str = "smart-city"):
        """Rolling restart of service"""
        # Dry-run: log intent but do not execute
        if self.automation_mode == 'dry-run':
            logger.info(f"[DRY-RUN] Would restart service: {service_name} in {namespace}")
            return

        try:
            pods = await self._call_k8s(
                self.core_v1.list_namespaced_pod,
                namespace=namespace,
                label_selector=f"app={service_name}",
                timeout_s=5.0,
            )
            
            for pod in pods.items:
                await self._call_k8s(
                    self.core_v1.delete_namespaced_pod,
                    name=pod.metadata.name,
                    namespace=namespace,
                    timeout_s=5.0,
                )
            
            logger.info(f"✅ Restarted service: {service_name}")
            
        except ApiException as e:
            logger.error(f"Failed to restart service: {e}")
            raise
    
    async def get_pod_node(self, pod_name: str, namespace: str) -> Optional[str]:
        """Get node name for a pod"""
        try:
            pod = await self._call_k8s(
                self.core_v1.read_namespaced_pod,
                pod_name,
                namespace,
                timeout_s=3.0,
            )
            return pod.spec.node_name
        except ApiException as e:
            logger.error(f"Failed to get pod node: {e}")
            return None
