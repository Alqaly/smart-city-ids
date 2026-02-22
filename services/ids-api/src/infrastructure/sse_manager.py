"""
Enhanced SSE (Server-Sent Events) Manager with error deduplication,
connection resilience, and health tracking.
"""

import asyncio
import json
import logging
import time
from typing import Dict, Set, Optional, Callable, Any
from collections import deque
from datetime import datetime

logger = logging.getLogger(__name__)


class SSEMessageDeduplicator:
    """
    Deduplicates SSE messages to prevent log spam.
    
    Similar messages within a time window are collapsed into a single
    message with a count indicator.
    """
    
    def __init__(self, window_seconds: int = 30):
        self.window_seconds = window_seconds
        self.message_history: deque = deque(maxlen=100)
        self.dedup_counter: Dict[str, int] = {}
        
    def should_emit(self, message_type: str, content: str) -> tuple[bool, Optional[str]]:
        """
        Check if message should be emitted or deduplicated.
        
        Returns:
            (should_emit, modified_content)
        """
        key = f"{message_type}:{content}"
        now = time.time()
        
        # Clean old entries
        cutoff = now - self.window_seconds
        while self.message_history and self.message_history[0][0] < cutoff:
            old_key = self.message_history.popleft()[1]
            if old_key in self.dedup_counter:
                del self.dedup_counter[old_key]
        
        # Check for duplicate
        if key in self.dedup_counter:
            self.dedup_counter[key] += 1
            count = self.dedup_counter[key]
            return True, f"{content} (x{count})"
        
        # New message
        self.message_history.append((now, key))
        self.dedup_counter[key] = 1
        return True, None


class SSEClient:
    """Represents a single SSE client connection."""
    
    def __init__(self, client_id: str, queue: asyncio.Queue):
        self.client_id = client_id
        self.queue = queue
        self.connected_at = time.time()
        self.last_activity = time.time()
        self.message_count = 0
        
    async def send(self, event: dict) -> bool:
        """Send an event to this client. Returns False if queue is full."""
        try:
            self.queue.put_nowait(event)
            self.last_activity = time.time()
            self.message_count += 1
            return True
        except asyncio.QueueFull:
            logger.warning(f"SSE client {self.client_id} queue full, dropping event")
            return False


class SSEManager:
    """
    Enhanced SSE manager with health tracking, deduplication, and resilience.
    
    Features:
    - Message deduplication to prevent spam
    - Client health tracking
    - Automatic cleanup of stale connections
    - Connection metrics and monitoring
    """
    
    def __init__(self, max_queue_size: int = 100):
        self.clients: Dict[str, SSEClient] = {}
        self.deduplicator = SSEMessageDeduplicator(window_seconds=30)
        self.max_queue_size = max_queue_size
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        
        # Metrics
        self.total_connections = 0
        self.total_messages_sent = 0
        self.messages_dropped = 0
        
    async def start(self):
        """Start the SSE manager background tasks."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("SSE manager started")
    
    async def stop(self):
        """Stop the SSE manager and cleanup."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Close all client connections
        async with self._lock:
            self.clients.clear()
        
        logger.info("SSE manager stopped")
    
    async def register_client(self, client_id: Optional[str] = None) -> tuple[str, asyncio.Queue]:
        """
        Register a new SSE client.
        
        Returns:
            (client_id, queue) - Use queue to receive events
        """
        if client_id is None:
            client_id = f"client_{time.time()}_{id(asyncio.current_task())}"
        
        queue = asyncio.Queue(maxsize=self.max_queue_size)
        client = SSEClient(client_id, queue)
        
        async with self._lock:
            # Remove existing client with same ID (reconnect)
            if client_id in self.clients:
                logger.debug(f"Replacing existing SSE client: {client_id}")
            
            self.clients[client_id] = client
            self.total_connections += 1
        
        logger.info(f"SSE client registered: {client_id} (total: {len(self.clients)})")
        
        # Send connection confirmation
        await client.send({
            "type": "connected",
            "timestamp": datetime.now().isoformat(),
            "client_id": client_id,
            "message": "Connected to live event stream"
        })
        
        return client_id, queue
    
    async def unregister_client(self, client_id: str):
        """Unregister a client (e.g., on disconnect)."""
        async with self._lock:
            if client_id in self.clients:
                del self.clients[client_id]
                logger.info(f"SSE client unregistered: {client_id} (remaining: {len(self.clients)})")
    
    async def broadcast(self, event: dict, deduplicate: bool = True) -> int:
        """
        Broadcast an event to all connected clients.
        
        Args:
            event: The event to broadcast
            deduplicate: Whether to apply deduplication
            
        Returns:
            Number of clients that received the event
        """
        if deduplicate:
            msg_type = event.get("type", "unknown")
            content = json.dumps(event, sort_keys=True, default=str)
            should_emit, modified_content = self.deduplicator.should_emit(msg_type, content)
            
            if not should_emit:
                return 0
            
            if modified_content:
                # Message was modified to include count
                event = {**event, "_dedup_note": modified_content}
        
        sent_count = 0
        dead_clients = []
        
        async with self._lock:
            for client_id, client in list(self.clients.items()):
                success = await client.send(event)
                if success:
                    sent_count += 1
                    self.total_messages_sent += 1
                else:
                    # Queue full - mark for removal
                    dead_clients.append(client_id)
                    self.messages_dropped += 1
            
            # Remove dead clients
            for client_id in dead_clients:
                if client_id in self.clients:
                    del self.clients[client_id]
        
        return sent_count
    
    async def send_to_client(self, client_id: str, event: dict) -> bool:
        """Send an event to a specific client."""
        async with self._lock:
            client = self.clients.get(client_id)
            if not client:
                return False
            return await client.send(event)
    
    async def _cleanup_loop(self):
        """Background task to cleanup stale connections."""
        while True:
            try:
                await asyncio.sleep(60)  # Cleanup every minute
                await self._cleanup_stale_connections()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in SSE cleanup loop: {e}")
    
    async def _cleanup_stale_connections(self):
        """Remove connections that haven't been active for 5 minutes."""
        cutoff = time.time() - 300  # 5 minutes
        stale_clients = []
        
        async with self._lock:
            for client_id, client in self.clients.items():
                if client.last_activity < cutoff:
                    stale_clients.append(client_id)
            
            for client_id in stale_clients:
                del self.clients[client_id]
        
        if stale_clients:
            logger.info(f"Cleaned up {len(stale_clients)} stale SSE connections")
    
    def get_stats(self) -> dict:
        """Get SSE manager statistics."""
        return {
            "active_connections": len(self.clients),
            "total_connections": self.total_connections,
            "total_messages_sent": self.total_messages_sent,
            "messages_dropped": self.messages_dropped,
            "clients": [
                {
                    "id": c.client_id,
                    "connected_at": datetime.fromtimestamp(c.connected_at).isoformat(),
                    "last_activity_ago_seconds": int(time.time() - c.last_activity),
                    "message_count": c.message_count,
                }
                for c in self.clients.values()
            ]
        }
    
    async def emit_keepalive(self):
        """Send keepalive ping to all clients."""
        await self.broadcast({
            "type": "keepalive",
            "timestamp": datetime.now().isoformat(),
        }, deduplicate=False)


# Global SSE manager instance
sse_manager = SSEManager()


async def broadcast_alert(alert_data: dict):
    """Broadcast an alert event to all connected clients."""
    await sse_manager.broadcast({
        "type": "alert",
        "timestamp": datetime.now().isoformat(),
        "data": alert_data,
    })


async def broadcast_provider_status(provider: str, status: str, details: Optional[dict] = None):
    """Broadcast a provider status change."""
    await sse_manager.broadcast({
        "type": "provider_status",
        "timestamp": datetime.now().isoformat(),
        "provider": provider,
        "status": status,
        "details": details or {},
    })


async def broadcast_system_event(event_type: str, message: str, severity: str = "info"):
    """Broadcast a system event (e.g., routing change, error)."""
    await sse_manager.broadcast({
        "type": "system",
        "timestamp": datetime.now().isoformat(),
        "event_type": event_type,
        "message": message,
        "severity": severity,
    })
