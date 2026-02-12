from datetime import datetime, timedelta, timezone
import sys

sys.path.insert(0, "services/ids-api/src")

import governance
from operator_interface import OperatorInterfaceService


def _sample_alert(ts: datetime) -> dict:
    return {
        "output": "Falco rule triggered: Unexpected process execution",
        "priority": "High",
        "rule": "Unexpected process",
        "time": ts.isoformat().replace("+00:00", "Z"),
        "output_fields": {
            "container.name": "traffic-camera-001",
            "proc.cmdline": "/bin/bash -c curl example.com",
        },
    }


def _sample_analysis(severity: int = 7, confidence: float = 0.8) -> dict:
    return {
        "summary": "Suspicious process activity detected.",
        "severity": severity,
        "threat_type": "Unauthorized Access",
        "confidence": confidence,
        "key_indicators": ["Unexpected process"],
        "mitigating_factors": [],
        "business_impact": "Potential service compromise.",
        "reasoning": "Behavior deviates from baseline.",
        "recommendations": ["Investigate process tree"],
        "automated_actions": ["alert_team"],
    }


def test_metrics_uses_governance_history_and_trend(monkeypatch):
    service = OperatorInterfaceService()

    now = datetime.now(timezone.utc)
    old = now - timedelta(days=2)

    service.build_incident_for_operator(
        alert_id=1,
        alert_data=_sample_alert(now),
        analysis=_sample_analysis(severity=8, confidence=0.9),
        llm_model_used="openai",
        analysis_duration_ms=500,
        automation_mode="assisted",
        protected_services=[],
    )
    service.build_incident_for_operator(
        alert_id=2,
        alert_data=_sample_alert(old),
        analysis=_sample_analysis(severity=5, confidence=0.6),
        llm_model_used="openai",
        analysis_duration_ms=700,
        automation_mode="assisted",
        protected_services=[],
    )

    monkeypatch.setattr(
        governance.governance,
        "get_action_history",
        lambda limit=1000: [
            {"status": "approved"},
            {"status": "approved"},
            {"status": "rejected"},
            {"status": "auto_executed"},
        ],
    )

    metrics = service.get_metrics()
    assert metrics.approval_rate == 2 / 3
    assert metrics.rejection_rate == 1 / 3
    assert metrics.override_rate == 1 / 4
    assert metrics.incident_volume_trend == "increasing"
