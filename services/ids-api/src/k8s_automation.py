"""
Kubernetes Automation - REAL Actions
Executes defensive actions on the K8s cluster
"""
import logging
from typing import Optional
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import os

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
            
            # Read automation mode (dry-run | assisted | autopilot)
            self.automation_mode = os.getenv('AUTOMATION_MODE', 'assisted').lower()

            # Initialize API clients
            self.apps_v1 = client.AppsV1Api()
            self.core_v1 = client.CoreV1Api()
            self.networking_v1 = client.NetworkingV1Api()
            
            logger.info("Kubernetes client initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Kubernetes client: {e}")
            raise
    
    def check_connection(self) -> bool:
        """Check if Kubernetes is accessible"""
        try:
            self.core_v1.list_namespace()
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
            
            self.networking_v1.create_namespaced_network_policy(
                namespace=namespace,
                body=network_policy
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
            deployment = self.apps_v1.read_namespaced_deployment(
                name=deployment_name,
                namespace=namespace
            )
            deployment.spec.replicas = replicas
            
            self.apps_v1.patch_namespaced_deployment(
                name=deployment_name,
                namespace=namespace,
                body=deployment
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
            self.core_v1.patch_node(node_name, body)
            logger.info(f"✅ Cordoned node: {node_name}")
        except ApiException as e:
            logger.error(f"Failed to cordon node: {e}")
            raise
    
    async def block_ip(self, ip_address: str, namespace: str = "smart-city"):
        """Block source IP using NetworkPolicy"""
        # Dry-run: log intent but do not execute
        if self.automation_mode == 'dry-run':
            logger.info(f"[DRY-RUN] Would block IP: {ip_address} in {namespace}")
            return

        try:
            policy_name = f"block-{ip_address.replace('.', '-')}"
            network_policy = client.V1NetworkPolicy(
                metadata=client.V1ObjectMeta(
                    name=policy_name,
                    namespace=namespace
                ),
                spec=client.V1NetworkPolicySpec(
                    pod_selector=client.V1LabelSelector(),
                    policy_types=["Ingress"],
                    ingress=[
                        client.V1NetworkPolicyIngressRule(
                            _from=[
                                client.V1NetworkPolicyPeer(
                                    ip_block=client.V1IPBlock(
                                        cidr=f"{ip_address}/32",
                                        _except=[]
                                    )
                                )
                            ]
                        )
                    ]
                )
            )
            
            self.networking_v1.create_namespaced_network_policy(
                namespace=namespace,
                body=network_policy
            )
            
            logger.info(f"✅ Blocked IP: {ip_address}")
            
        except ApiException as e:
            if e.status == 409:
                logger.warning(f"IP block already exists for {ip_address}")
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
            pods = self.core_v1.list_namespaced_pod(
                namespace=namespace,
                label_selector=f"app={service_name}"
            )
            
            for pod in pods.items:
                self.core_v1.delete_namespaced_pod(
                    name=pod.metadata.name,
                    namespace=namespace
                )
            
            logger.info(f"✅ Restarted service: {service_name}")
            
        except ApiException as e:
            logger.error(f"Failed to restart service: {e}")
            raise
    
    async def get_pod_node(self, pod_name: str, namespace: str) -> Optional[str]:
        """Get node name for a pod"""
        try:
            pod = self.core_v1.read_namespaced_pod(pod_name, namespace)
            return pod.spec.node_name
        except ApiException as e:
            logger.error(f"Failed to get pod node: {e}")
            return None
