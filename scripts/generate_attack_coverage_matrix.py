#!/usr/bin/env python3
"""Generate machine-readable ATT&CK coverage matrix for thesis appendix.

Outputs:
- docs/ATTACK_COVERAGE_MATRIX.json
- docs/ATTACK_COVERAGE_MATRIX.csv

Data source: attack-simulator/scenario_registry.py (SCENARIOS + CAMPAIGNS)

This is intentionally deterministic and has no external dependencies.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def _load_registry() -> dict[str, Any]:
    import sys

    sys.path.insert(0, str(ROOT / "attack-simulator"))
    from scenario_registry import export_all_json  # type: ignore

    return export_all_json()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def main() -> int:
    reg = _load_registry()
    scenarios = reg.get("scenarios", {}) or {}
    campaigns = reg.get("campaigns", {}) or {}
    categories = reg.get("categories", {}) or {}

    rows: list[dict[str, Any]] = []
    for sid, sc in sorted(scenarios.items(), key=lambda kv: str(kv[0])):
        rows.append(
            {
                "id": sc.get("id", sid),
                "name": sc.get("name"),
                "category": sc.get("category"),
                "category_name": (categories.get(sc.get("category")) or {}).get("name"),
                "target": sc.get("target"),
                "source": sc.get("source"),
                "severity": sc.get("severity"),
                "mitre_id": sc.get("mitre_id"),
                "mitre_name": sc.get("mitre_name"),
                "tactic": sc.get("tactic"),
                "kill_chain": sc.get("kill_chain"),
                "volume": sc.get("volume"),
                "rule": sc.get("rule"),
                "description": sc.get("description"),
            }
        )

    # Also export campaigns as a separate section (stage list is important academically)
    campaign_rows: list[dict[str, Any]] = []
    for cid, c in sorted(campaigns.items(), key=lambda kv: str(kv[0])):
        campaign_rows.append(
            {
                "id": c.get("id", cid),
                "name": c.get("name"),
                "category": c.get("category", "campaign"),
                "target": c.get("target"),
                "severity": c.get("severity"),
                "mitre_id": c.get("mitre_id"),
                "mitre_name": c.get("mitre_name"),
                "tactic": c.get("tactic"),
                "kill_chain": c.get("kill_chain"),
                "stages": c.get("stages") or [],
                "description": c.get("description"),
            }
        )

    out = {
        "generated_at": _now_iso(),
        "source": "attack-simulator/scenario_registry.py",
        "totals": {
            "scenarios": len(rows),
            "campaigns": len(campaign_rows),
        },
        "categories": categories,
        "scenarios": rows,
        "campaigns": campaign_rows,
    }

    DOCS.mkdir(parents=True, exist_ok=True)
    json_path = DOCS / "ATTACK_COVERAGE_MATRIX.json"
    csv_path = DOCS / "ATTACK_COVERAGE_MATRIX.csv"

    json_path.write_text(json.dumps(out, indent=2, sort_keys=False) + "\n", encoding="utf-8")

    # CSV for appendix tables
    csv_fields = [
        "id",
        "name",
        "category",
        "category_name",
        "target",
        "source",
        "severity",
        "mitre_id",
        "mitre_name",
        "tactic",
        "kill_chain",
        "volume",
        "rule",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=csv_fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in csv_fields})

    print(f"Wrote: {json_path}")
    print(f"Wrote: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
