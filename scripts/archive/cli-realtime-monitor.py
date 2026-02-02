#!/usr/bin/env python3
"""
Smart City IDS Real-Time CLI Monitor

Displays live attack alerts, LLM analysis, and K8s automation actions
in a beautiful, real-time terminal UI.

Usage:
    python monitor.py                    # Monitor local IDS API
    python monitor.py --host 10.0.0.5    # Monitor remote IDS API
    python monitor.py --port 9000        # Custom port
"""

import asyncio
import json
import sys
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from collections import deque

import httpx
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.layout import Layout

# Configuration
IDS_API_URL = "http://localhost:8000"
METRICS_ENDPOINT = "/api/metrics"
MAX_ALERTS_DISPLAY = 10
REFRESH_INTERVAL = 2  # seconds

# Rich Console for pretty output
console = Console()


@dataclass
class Alert:
    """IDS Alert"""
    timestamp: str
    rule: str
    priority: str
    source: str  # "falco" or "suricata"
    severity_score: int  # 1-10


@dataclass
class AutomationAction:
    """K8s Automation Action"""
    timestamp: str
    action_type: str  # "isolate_pod", "scale_service", etc.
    target: str
    status: str  # "success", "failed", "pending"


class RealTimeMonitor:
    """Monitors IDS API and displays real-time metrics"""
    
    def __init__(self, api_url: str = IDS_API_URL):
        self.api_url = api_url
        self.alerts = deque(maxlen=MAX_ALERTS_DISPLAY)
        self.automation_actions = deque(maxlen=MAX_ALERTS_DISPLAY)
        self.metrics = {}
        self.start_time = datetime.now()
        
    async def fetch_metrics(self) -> Dict[str, Any]:
        """Fetch current metrics from IDS API"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.api_url}{METRICS_ENDPOINT}")
                if response.status_code == 200:
                    return response.json()
        except Exception as e:
            console.print(f"[red]Error fetching metrics: {e}[/red]")
        return {}
    
    async def fetch_recent_alerts(self) -> List[Dict[str, Any]]:
        """Fetch recent alerts (would need API extension)"""
        # For now, return empty - in production, add /api/alerts/recent endpoint
        return []
    
    def generate_alert_table(self) -> Table:
        """Generate table of recent alerts"""
        table = Table(title="🚨 Recent Alerts (Real-Time)", show_header=True, header_style="bold magenta")
        table.add_column("Time", style="cyan")
        table.add_column("Source", style="blue")
        table.add_column("Priority", style="red")
        table.add_column("Rule", style="white", max_width=40)
        table.add_column("Severity", style="yellow")
        
        for alert in list(self.alerts)[-MAX_ALERTS_DISPLAY:]:
            table.add_row(
                alert.timestamp.split("T")[1][:8],
                f"[blue]{alert.source.upper()}[/blue]",
                self._priority_color(alert.priority),
                alert.rule[:40],
                f"[yellow]{alert.severity_score}/10[/yellow]"
            )
        
        if not self.alerts:
            table.add_row("[dim]No alerts yet - waiting for attacks...[/dim]", "", "", "", "")
        
        return table
    
    def generate_automation_table(self) -> Table:
        """Generate table of automation actions"""
        table = Table(title="⚙️ Automated K8s Actions", show_header=True, header_style="bold green")
        table.add_column("Time", style="cyan")
        table.add_column("Action", style="green")
        table.add_column("Target", style="white")
        table.add_column("Status", style="yellow")
        
        for action in list(self.automation_actions)[-MAX_ALERTS_DISPLAY:]:
            status_color = "[green]✓[/green]" if action.status == "success" else "[red]✗[/red]"
            table.add_row(
                action.timestamp.split("T")[1][:8],
                action.action_type,
                action.target[:30],
                f"{status_color} {action.status}"
            )
        
        if not self.automation_actions:
            table.add_row("[dim]No actions yet - waiting for alerts...[/dim]", "", "", "")
        
        return table
    
    def generate_metrics_panel(self) -> Panel:
        """Generate panel with key metrics"""
        metrics_text = Text()
        
        metrics_data = [
            ("📊 Total Alerts", self.metrics.get("total_alerts", 0), ""),
            ("🔴 Critical", self.metrics.get("critical_alerts", 0), "[red]"),
            ("🟠 Error", self.metrics.get("error_alerts", 0), "[yellow]"),
            ("🟡 Warning", self.metrics.get("warning_alerts", 0), "[yellow]"),
            ("⚙️ Actions Executed", self.metrics.get("automation_actions", 0), "[green]"),
            ("✅ Success Rate", f"{self.metrics.get('success_rate', 0):.1%}", "[green]"),
            ("⏱️ Avg Latency", f"{self.metrics.get('avg_latency_ms', 0):.0f}ms", "[cyan]"),
        ]
        
        for i, (label, value, color) in enumerate(metrics_data):
            if i > 0:
                metrics_text.append("\n")
            metrics_text.append(f"{label:<20} ", style="white")
            metrics_text.append(f"{value}", style=color or "white")
        
        return Panel(metrics_text, title="📈 Key Metrics", border_style="blue")
    
    def _priority_color(self, priority: str) -> str:
        """Color code priority level"""
        colors = {
            "Critical": "[red]🔴 CRITICAL[/red]",
            "Error": "[orange]🟠 ERROR[/orange]",
            "Warning": "[yellow]🟡 WARNING[/yellow]",
            "Notice": "[green]🟢 NOTICE[/green]",
        }
        return colors.get(priority, f"[white]{priority}[/white]")
    
    async def update(self):
        """Update metrics and alerts"""
        self.metrics = await self.fetch_metrics()
        recent_alerts = await self.fetch_recent_alerts()
        
        # Simulate recent alerts for demo (in production, fetch from API)
        # This would be replaced with real API data
    
    def render(self) -> Layout:
        """Render complete dashboard layout"""
        layout = Layout()
        
        # Header
        header = Text()
        header.append("🛡️ Smart City IDS - Real-Time Monitor", style="bold cyan")
        header.append(" | ", style="dim")
        uptime = (datetime.now() - self.start_time).total_seconds()
        header.append(f"Uptime: {int(uptime)}s", style="dim")
        
        layout.add_panel(Panel(header, border_style="cyan"))
        
        # Metrics and alerts
        layout.split_column(
            Layout(self.generate_metrics_panel(), name="metrics", size=8),
            Layout(self.generate_alert_table(), name="alerts", size=14),
            Layout(self.generate_automation_table(), name="actions", size=10),
            Layout(Text("[dim]Press Ctrl+C to exit[/dim]", justify="center"), size=2)
        )
        
        return layout


async def main():
    """Main monitoring loop"""
    monitor = RealTimeMonitor()
    
    console.print("\n[cyan]Starting Real-Time Monitor...[/cyan]")
    console.print(f"[dim]Connecting to IDS API at {IDS_API_URL}[/dim]\n")
    
    try:
        with Live(monitor.render(), refresh_per_second=1, console=console) as live:
            while True:
                await monitor.update()
                live.update(monitor.render())
                await asyncio.sleep(REFRESH_INTERVAL)
    except KeyboardInterrupt:
        console.print("\n[yellow]Monitor stopped[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Smart City IDS Real-Time CLI Monitor")
    parser.add_argument("--host", default="localhost", help="IDS API host")
    parser.add_argument("--port", type=int, default=8000, help="IDS API port")
    
    args = parser.parse_args()
    IDS_API_URL = f"http://{args.host}:{args.port}"
    
    try:
        asyncio.run(main())
    except ImportError:
        console.print("[red]Error: Missing dependencies. Install with:[/red]")
        console.print("[yellow]pip install httpx rich[/yellow]")
        sys.exit(1)
