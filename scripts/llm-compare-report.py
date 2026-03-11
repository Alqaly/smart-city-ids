#!/usr/bin/env python3
"""Export paper-ready LLM comparison CSV templates from live IDS API data.

This script is intentionally lightweight: it reads current provider metrics and
recent alerts, then writes CSVs that analysts can score against ground truth.
It does not claim accuracy scores by itself.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import urllib.request
from urllib.error import HTTPError
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PSEUDO_PROVIDERS = {"", "none", "unknown", "cache", "cached", "rule", "rule_based", "rule-based"}
LLM_COST_PER_1K_TOKENS = {
    "xai": 0.012,
    "openai": 0.010,
    "anthropic": 0.016,
    "gemini": 0.002,
    "kimi": 0.006,
}


def http_json(url: str, token: str | None = None) -> dict[str, Any]:
    req = urllib.request.Request(url, method="GET")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def post_json(url: str, payload: dict[str, Any] | None = None, token: str | None = None) -> dict[str, Any]:
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"detail": body}
        raise RuntimeError(f"HTTP {exc.code}: {json.dumps(parsed)}") from exc


def login(api_url: str, username: str, password: str) -> str:
    data = json.dumps({"username": username, "password": password}).encode("utf-8")
    req = urllib.request.Request(
        f"{api_url}/api/auth/login",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        token = body.get("access_token")
        if not token:
            raise RuntimeError("login failed: no access_token")
        return token


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def normalize_text(v: Any) -> str:
    return str(v or "").strip().lower()


def is_real_provider(name: Any) -> bool:
    return normalize_text(name) not in PSEUDO_PROVIDERS


def estimate_cost_from_tokens(engine: str, prompt_tokens: Any, completion_tokens: Any) -> float:
    total_tokens = max(0, int(to_int(prompt_tokens) or 0)) + max(0, int(to_int(completion_tokens) or 0))
    if total_tokens <= 0:
        return 0.0
    return round((total_tokens / 1000.0) * float(LLM_COST_PER_1K_TOKENS.get(normalize_text(engine), 0.0)), 8)


def to_float(v: Any) -> float | None:
    try:
        return float(v)
    except Exception:
        return None


def to_int(v: Any) -> int | None:
    try:
        return int(float(v))
    except Exception:
        return None


def classify_action_class(action_text: str) -> str:
    s = normalize_text(action_text)
    if not s:
        return "none"
    if any(k in s for k in ["isolate", "evict", "quarantine"]):
        return "isolate_or_evict"
    if any(k in s for k in ["block", "rate", "throttle"]):
        return "rate_limit_or_contain_source"
    if any(k in s for k in ["collect", "log", "capture"]):
        return "collect_forensics"
    if "allowlist" in s:
        return "investigate_or_allowlist"
    if "investigate" in s or "review" in s:
        return "investigate"
    if "contain" in s:
        return "investigate_and_contain"
    return "other"


def action_matches_expected(pred_action: str, expected: str) -> bool:
    p = classify_action_class(pred_action)
    e = normalize_text(expected)
    if not e:
        return False
    if e == p:
        return True
    # Allow broader compatibility buckets for first-pass scoring.
    aliases = {
        "investigate_and_contain": {"investigate", "rate_limit_or_contain_source", "isolate_or_evict", "other"},
        "investigate_or_allowlist": {"investigate", "investigate_or_allowlist"},
        "investigate_and_isolate_if_confirmed": {"investigate", "isolate_or_evict"},
        "rate_limit_or_contain_source": {"rate_limit_or_contain_source", "investigate", "isolate_or_evict"},
    }
    return p in aliases.get(e, set())


def threat_matches(pred: str, expected: str) -> bool:
    p = normalize_text(pred)
    e = normalize_text(expected)
    if not p or not e:
        return False
    synonyms = {
        "dos": {"ddos", "denial of service", "network dos"},
        "injection": {"sql injection", "sqli"},
        "runtime abuse": {"reconnaissance", "execution", "command execution"},
        "credential access": {"credential theft"},
        "lateral movement": {"reconnaissance"},
    }
    if e in p or p in e:
        return True
    return any(x in p for x in synonyms.get(e, set()))


def load_ground_truth_mappings(path: Path | None) -> list[dict[str, str]]:
    if not path or not path.exists():
        return []
    rows = read_csv_rows(path)
    # precompile regex for rule_pattern
    for r in rows:
        pat = r.get("rule_pattern", "").strip()
        r["_regex"] = re.compile(pat, re.IGNORECASE)
    return rows


def match_ground_truth(alert_row: dict[str, Any], mappings: list[dict[str, str]]) -> dict[str, str] | None:
    rule = str(alert_row.get("rule") or "")
    source = normalize_text(alert_row.get("source"))
    for m in mappings:
        m_source = normalize_text(m.get("source"))
        if m_source and source and m_source != source:
            continue
        rx = m.get("_regex")
        if rx and rx.search(rule):
            return m
    return None


def derive_effective_provider(alert: dict[str, Any], analysis: dict[str, Any]) -> tuple[str, bool]:
    """Return (effective_provider, cache_hit)."""
    reported = normalize_text(alert.get("llm_engine"))
    analysis_source = normalize_text(analysis.get("_analysis_source"))
    trace_provider = normalize_text((analysis.get("_llm_trace") or {}).get("provider"))
    analysis_engine = normalize_text(analysis.get("_llm_engine"))

    cache_hit = reported == "cached" or analysis_source == "cached" or analysis_engine == "cached"
    if cache_hit:
        # Cache rows should not be counted as direct-provider quality observations.
        # Preserve a recoverable provider when trace metadata exists for optional reporting.
        return (trace_provider or "cached"), True
    return (reported or trace_provider or analysis_engine or "unknown"), False


def build_eval_prompt_from_alert(alert: dict[str, Any]) -> str:
    """Stable text snapshot for strict provider evaluation logs/debug."""
    analysis = alert.get("analysis") or {}
    parts = [
        f"Alert source: {alert.get('source') or 'unknown'}",
        f"Rule: {alert.get('rule') or 'unknown'}",
        f"Priority: {alert.get('priority') or 'unknown'}",
        f"Severity hint: {alert.get('severity') or 'unknown'}",
        f"Observed output: {(alert.get('raw_alert') or {}).get('output') or alert.get('summary') or analysis.get('summary') or ''}",
    ]
    raw_fields = (alert.get("raw_alert") or {}).get("output_fields") or {}
    if raw_fields:
        parts.append(f"Output fields: {json.dumps(raw_fields, sort_keys=True)}")
    return "\n".join(parts)


def run_strict_evaluation(
    api_url: str,
    token: str,
    source_alerts: list[dict[str, Any]],
    mappings: list[dict[str, str]],
    providers: list[str],
    runs: int,
    max_per_family: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    strict_rows: list[dict[str, Any]] = []
    alert_rows: list[dict[str, Any]] = []
    matched_alerts = [a for a in source_alerts if match_ground_truth(a, mappings)]
    if max_per_family > 0:
        family_buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for alert in matched_alerts:
            gt = match_ground_truth(alert, mappings)
            family = normalize_text((gt or {}).get("scenario_family")) or "unmapped"
            if len(family_buckets[family]) < max_per_family:
                family_buckets[family].append(alert)
        matched_alerts = []
        for family in sorted(family_buckets):
            matched_alerts.extend(family_buckets[family])
    for alert in matched_alerts:
        alert_id = alert.get("id") or alert.get("alert_id")
        if not alert_id:
            continue
        gt = match_ground_truth(alert, mappings)
        prompt_snapshot = build_eval_prompt_from_alert(alert)
        for provider in providers:
            for run_idx in range(1, runs + 1):
                try:
                    result = post_json(
                        f"{api_url}/api/alerts/{alert_id}/reanalyze?engine={provider}&strict=true&persist=false",
                        {},
                        token=token,
                    )
                    status = result.get("status", "success")
                    error_text = result.get("error", "")
                except Exception as exc:
                    result = {}
                    status = "error"
                    error_text = str(exc)
                analysis = result.get("analysis") or {}
                usage = result.get("usage") or {}
                strict_rows.append({
                    "alert_id": alert_id,
                    "provider": provider,
                    "run_index": run_idx,
                    "status": status,
                    "strict_requested": result.get("strict_requested", True),
                    "strict_satisfied": result.get("strict_satisfied", status == "success"),
                    "engine_used": result.get("engine_used", provider),
                    "latency_s": result.get("latency_s", ""),
                    "prompt_tokens": usage.get("prompt_tokens", ""),
                    "completion_tokens": usage.get("completion_tokens", ""),
                    "total_tokens": usage.get("total_tokens", ""),
                    "estimated_cost_usd": estimate_cost_from_tokens(provider, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)),
                    "summary": analysis.get("summary", ""),
                    "severity": analysis.get("severity", ""),
                    "threat_type": analysis.get("threat_type", ""),
                    "action_text": "; ".join(str(x) for x in (analysis.get("automated_actions") or analysis.get("recommendations") or [])[:5]),
                    "error": error_text,
                })
                if status != "success" or not result.get("strict_satisfied", status == "success"):
                    continue
                row = {
                    "alert_id": alert_id,
                    "time": alert.get("timestamp") or alert.get("time") or "",
                    "rule": alert.get("rule") or "",
                    "source": alert.get("source") or "",
                    "provider_reported": provider,
                    "provider": provider,
                    "cache_hit_0_1": 0,
                    "analysis_source": "strict_reanalysis",
                    "severity_pred": analysis.get("severity", ""),
                    "threat_type_pred": analysis.get("threat_type", ""),
                    "summary_pred": analysis.get("summary", ""),
                    "action_pred_class": "; ".join(str(x) for x in (analysis.get("automated_actions") or analysis.get("recommendations") or [])[:5]),
                    "scenario_family": gt.get("scenario_family", ""),
                    "safety_profile": gt.get("safety_profile", ""),
                    "under_escalation_weight": gt.get("under_escalation_weight", ""),
                    "expected_severity_min": gt.get("expected_severity_min", ""),
                    "expected_severity_max": gt.get("expected_severity_max", ""),
                    "expected_threat_type": gt.get("expected_threat_type", ""),
                    "expected_safe_action_class": gt.get("expected_safe_action_class", ""),
                    "severity_in_range_score_0_1": "",
                    "threat_type_match_score_0_1": "",
                    "action_relevance_score_1_to_5": "",
                    "explanation_usefulness_score_1_to_5": "",
                    "false_high_severity_0_1": "",
                    "false_low_severity_0_1": "",
                    "weighted_false_low_penalty": "",
                    "ot_or_controlplane_sensitive_0_1": "",
                    "unsafe_action_recommendation_0_1": "",
                    "notes": f"run={run_idx}; prompt_snapshot={prompt_snapshot[:220].replace(chr(10), ' | ')}",
                }
                try:
                    sev = int(row.get("severity_pred") or 0)
                    smin = int(gt.get("expected_severity_min") or 0)
                    smax = int(gt.get("expected_severity_max") or 0)
                    row["severity_in_range_score_0_1"] = 1 if smin <= sev <= smax else 0
                    row["false_high_severity_0_1"] = 1 if sev > smax else 0
                    row["false_low_severity_0_1"] = 1 if sev < smin else 0
                except Exception:
                    pass
                weight = to_float(gt.get("under_escalation_weight"))
                if weight is None:
                    weight = 1.0
                row["under_escalation_weight"] = weight
                false_low = to_float(row.get("false_low_severity_0_1"))
                if false_low is not None:
                    row["weighted_false_low_penalty"] = round(false_low * weight, 4)
                safety_profile = normalize_text(gt.get("safety_profile"))
                row["ot_or_controlplane_sensitive_0_1"] = 1 if any(
                    k in safety_profile for k in ["ot_", "controlplane", "availability_critical"]
                ) else 0
                row["threat_type_match_score_0_1"] = 1 if threat_matches(row.get("threat_type_pred"), gt.get("expected_threat_type")) else 0
                row["action_relevance_score_1_to_5"] = 4 if action_matches_expected(row.get("action_pred_class", ""), gt.get("expected_safe_action_class", "")) else 2
                row["unsafe_action_recommendation_0_1"] = 1 if ("isolate" in normalize_text(row.get("action_pred_class")) and "allowlist" in normalize_text(gt.get("expected_safe_action_class"))) else 0
                alert_rows.append(row)
    return strict_rows, alert_rows


def consistency_score_pct(rows: list[dict[str, Any]]) -> float | str:
    """Compute a repeat-alert consistency score for a provider (0-100).

    This is a first-pass proxy, not a full semantic consistency metric:
    - groups repeated alerts by source/rule/scenario_family
    - compares severity spread, threat label stability, and action class stability
    """
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        key = "|".join([
            normalize_text(r.get("source")),
            normalize_text(r.get("rule")),
            normalize_text(r.get("scenario_family")),
        ])
        grouped[key].append(r)

    group_scores: list[float] = []
    for _, grows in grouped.items():
        if len(grows) < 2:
            continue
        subscores: list[float] = []

        severities = []
        for g in grows:
            try:
                severities.append(float(g.get("severity_pred")))
            except Exception:
                continue
        if len(severities) >= 2:
            span = max(severities) - min(severities)
            subscores.append(max(0.0, 1.0 - (span / 10.0)))

        threats = [normalize_text(g.get("threat_type_pred")) for g in grows if normalize_text(g.get("threat_type_pred"))]
        if len(threats) >= 2:
            most_common = Counter(threats).most_common(1)[0][1]
            subscores.append(most_common / len(threats))

        actions = [classify_action_class(str(g.get("action_pred_class") or "")) for g in grows]
        actions = [a for a in actions if a and a != "none"]
        if len(actions) >= 2:
            most_common = Counter(actions).most_common(1)[0][1]
            subscores.append(most_common / len(actions))

        if subscores:
            group_scores.append(sum(subscores) / len(subscores))

    if not group_scores:
        return ""
    return round(sum(group_scores) / len(group_scores) * 100.0, 2)


def _rank_values(rows: list[dict[str, Any]], value_key: str, rank_key: str, higher_is_better: bool, min_gate_fn) -> None:
    ranked: list[tuple[int, float]] = []
    for idx, r in enumerate(rows):
        if not min_gate_fn(r):
            r[rank_key] = ""
            continue
        try:
            ranked.append((idx, float(r.get(value_key))))
        except Exception:
            r[rank_key] = ""
    ranked.sort(key=lambda t: t[1], reverse=higher_is_better)
    last_val = None
    last_rank = 0
    for pos, (idx, val) in enumerate(ranked, start=1):
        if last_val is None or val != last_val:
            last_rank = pos
            last_val = val
        rows[idx][rank_key] = last_rank


def build_provider_scorecard(scored_provider_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for r in scored_provider_rows:
        provider = normalize_text(r.get("provider"))
        scored_n = to_int(r.get("scored_alerts_n")) or 0
        calls = to_int(r.get("calls")) or 0
        runtime_attempts = to_int(r.get("runtime_attempts")) or 0
        avg_latency_s = to_float(r.get("avg_latency_s"))
        latency_ms = round(avg_latency_s * 1000.0, 2) if avg_latency_s is not None and avg_latency_s > 0 and runtime_attempts > 0 else ""
        success_runtime = to_float(r.get("success_rate_runtime"))
        # Treat runtime success as unavailable when the current runtime snapshot has no attempts.
        success_runtime = round(success_runtime, 2) if success_runtime is not None and runtime_attempts > 0 else ""

        score_row = {
            "provider": provider,
            "model": r.get("model", ""),
            "scored_alerts_n_direct": scored_n,
            "scored_alerts_n_total_including_cache": to_int(r.get("scored_total_alerts_n")) or 0,
            "cache_hit_share_pct_of_scored": r.get("cache_hit_share_pct_of_scored", ""),
            "quality_composite_score_pct": r.get("quality_composite_score_pct", ""),
            "severity_accuracy_pct": r.get("severity_accuracy_pct", ""),
            "threat_type_accuracy_pct": r.get("threat_type_accuracy_pct", ""),
            "action_relevance_score_1_to_5": r.get("action_relevance_score_1_to_5", ""),
            "estimated_cost_usd_per_1m_tokens": r.get("estimated_cost_usd_per_1m_tokens", ""),
            "avg_latency_ms": latency_ms,
            "reliability_runtime_success_pct": success_runtime,
            "safety_calibration_score_proxy_pct": r.get("safety_calibration_score_proxy_pct", ""),
            "ot_under_escalation_rate_pct": r.get("ot_under_escalation_rate_pct", ""),
            "consistency_score_pct": r.get("consistency_score_pct", ""),
            "rank_quality": "",
            "rank_cost": "",
            "rank_latency": "",
            "rank_reliability_runtime": "",
            "rank_safety_proxy": "",
            "overall_rank_proxy": "",
            "scorecard_note": "",
        }
        notes = []
        if scored_n < 5:
            notes.append("low_direct_scored_sample")
        if runtime_attempts == 0:
            notes.append("no_runtime_attempts_for_latency_reliability")
        elif calls == 0:
            notes.append("runtime_attempts_present_but_db_calls_zero")
        score_row["scorecard_note"] = ";".join(notes)
        rows.append(score_row)

    _rank_values(rows, "quality_composite_score_pct", "rank_quality", True, lambda r: (to_int(r.get("scored_alerts_n_direct")) or 0) >= 5)
    _rank_values(rows, "estimated_cost_usd_per_1m_tokens", "rank_cost", False, lambda r: to_float(r.get("estimated_cost_usd_per_1m_tokens")) is not None)
    _rank_values(rows, "avg_latency_ms", "rank_latency", False, lambda r: to_float(r.get("avg_latency_ms")) is not None)
    _rank_values(rows, "reliability_runtime_success_pct", "rank_reliability_runtime", True, lambda r: to_float(r.get("reliability_runtime_success_pct")) is not None)
    _rank_values(rows, "safety_calibration_score_proxy_pct", "rank_safety_proxy", True, lambda r: (to_int(r.get("scored_alerts_n_direct")) or 0) >= 5)

    # Overall proxy rank = average of available rank positions across the five dimensions.
    overall_values: list[tuple[int, float]] = []
    for idx, r in enumerate(rows):
        rank_vals = []
        for k in ["rank_quality", "rank_cost", "rank_latency", "rank_reliability_runtime", "rank_safety_proxy"]:
            try:
                rank_vals.append(float(r.get(k)))
            except Exception:
                continue
        if len(rank_vals) >= 3:
            avg_rank = sum(rank_vals) / len(rank_vals)
            r["_overall_rank_avg"] = round(avg_rank, 3)
            overall_values.append((idx, avg_rank))
        else:
            r["_overall_rank_avg"] = ""
            r["overall_rank_proxy"] = ""
    overall_values.sort(key=lambda t: t[1])
    last_val = None
    last_rank = 0
    for pos, (idx, val) in enumerate(overall_values, start=1):
        if last_val is None or val != last_val:
            last_rank = pos
            last_val = val
        rows[idx]["overall_rank_proxy"] = last_rank

    for r in rows:
        r.pop("_overall_rank_avg", None)
    return rows


def maybe_write_charts(
    out_dir: Path,
    provider_rows: list[dict[str, Any]],
    scored_provider_rows: list[dict[str, Any]],
    family_rollups: list[dict[str, Any]],
) -> list[str]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return []

    charts_dir = out_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    generated: list[str] = []

    scored_map = {normalize_text(r.get("provider")): r for r in scored_provider_rows}
    merged_rows = []
    for p in provider_rows:
        merged_rows.append({**p, **scored_map.get(normalize_text(p.get("provider")), {})})

    def plot_bar(filename: str, title: str, rows: list[dict[str, Any]], value_key: str, ylabel: str, include_fn=None) -> None:
        xs, ys = [], []
        for r in rows:
            if include_fn and not include_fn(r):
                continue
            try:
                y = float(r.get(value_key))
            except Exception:
                continue
            xs.append(str(r.get("provider", "")).upper())
            ys.append(y)
        if not xs:
            return
        fig, ax = plt.subplots(figsize=(8, 4.5))
        bars = ax.bar(xs, ys)
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", alpha=0.25)
        for b, y in zip(bars, ys):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(), f"{y:.2f}", ha="center", va="bottom", fontsize=8)
        fig.tight_layout()
        path = charts_dir / filename
        fig.savefig(path, dpi=160)
        plt.close(fig)
        generated.append(str(path))

    # Runtime/provider metrics
    runtime_rows_gate = lambda r: (to_int(r.get("runtime_attempts")) or 0) > 0
    plot_bar("avg_latency_by_provider.png", "Avg LLM Latency by Provider", merged_rows, "avg_latency_s", "Seconds", include_fn=runtime_rows_gate)
    plot_bar("cost_per_1m_tokens_by_provider.png", "Estimated Cost per 1M Tokens", merged_rows, "estimated_cost_usd_per_1m_tokens", "USD")
    plot_bar("success_rate_runtime_by_provider.png", "Runtime Success Rate by Provider", merged_rows, "success_rate_runtime", "Percent", include_fn=runtime_rows_gate)
    # Scored quality/safety metrics (direct-provider rows only)
    plot_bar("severity_accuracy_by_provider.png", "Severity Range Accuracy (Ground Truth Matched)", merged_rows, "severity_accuracy_pct", "Percent")
    plot_bar("threat_accuracy_by_provider.png", "Threat-Type Accuracy (Ground Truth Matched)", merged_rows, "threat_type_accuracy_pct", "Percent")

    # Cost vs latency scatter (use providers with both metrics)
    scatter_points = []
    for r in merged_rows:
        if (to_int(r.get("runtime_attempts")) or 0) <= 0:
            continue
        try:
            x = float(r.get("avg_latency_s"))
            y = float(r.get("estimated_cost_usd_per_1m_tokens"))
        except Exception:
            continue
        scatter_points.append((x, y, str(r.get("provider", "")).upper()))
    if scatter_points:
        fig, ax = plt.subplots(figsize=(6.5, 5))
        for x, y, label in scatter_points:
            ax.scatter(x, y, s=60)
            ax.text(x, y, label, fontsize=8, ha="left", va="bottom")
        ax.set_title("Cost vs Latency (Provider Tradeoff)")
        ax.set_xlabel("Avg Latency (s)")
        ax.set_ylabel("Estimated USD per 1M Tokens")
        ax.grid(alpha=0.25)
        fig.tight_layout()
        path = charts_dir / "cost_vs_latency_scatter.png"
        fig.savefig(path, dpi=160)
        plt.close(fig)
        generated.append(str(path))

    # Scenario-family charts (all providers aggregate rows only)
    fam_all = [r for r in family_rollups if normalize_text(r.get("provider")) == "all_providers"]
    if fam_all:
        def plot_family_bar(filename: str, title: str, value_key: str, ylabel: str) -> None:
            xs, ys = [], []
            for r in sorted(fam_all, key=lambda rr: normalize_text(rr.get("scenario_family"))):
                try:
                    y = float(r.get(value_key))
                except Exception:
                    continue
                xs.append(str(r.get("scenario_family", "")))
                ys.append(y)
            if not xs:
                return
            fig, ax = plt.subplots(figsize=(8.5, 4.8))
            ax.bar(xs, ys)
            ax.set_title(title)
            ax.set_ylabel(ylabel)
            ax.tick_params(axis="x", rotation=20)
            ax.grid(axis="y", alpha=0.25)
            fig.tight_layout()
            path = charts_dir / filename
            fig.savefig(path, dpi=160)
            plt.close(fig)
            generated.append(str(path))

        plot_family_bar("scenario_family_severity_accuracy.png", "Scenario Family Severity Accuracy (All Providers)", "severity_accuracy_pct", "Percent")
        plot_family_bar("scenario_family_threat_accuracy.png", "Scenario Family Threat Accuracy (All Providers)", "threat_type_accuracy_pct", "Percent")
        plot_family_bar("scenario_family_cache_share.png", "Scenario Family Cache-Hit Share (All Providers)", "cache_hit_share_pct_of_scored", "Percent")
        plot_family_bar("scenario_family_safety_proxy.png", "Scenario Family Safety Calibration Proxy (All Providers)", "safety_calibration_score_proxy_pct", "Percent")

    return generated


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build LLM evaluation CSVs and charts from the live Smart City IDS.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "What this command does:\n"
            "  1. Logs into the IDS API\n"
            "  2. Reads recent alerts from /api/alerts\n"
            "  3. Matches alerts against the ground-truth CSV\n"
            "  4. Optionally re-runs the same alerts against specific providers in strict mode\n"
            "  5. Writes scored CSVs and PNG charts into the output directory\n\n"
            "Normal export example:\n"
            "  python3 scripts/llm-compare-report.py \\\n"
            "    --api-url http://localhost:30800 \\\n"
            "    --ground-truth docs/reference/LLM_EVAL_GROUND_TRUTH_CORE.csv \\\n"
            "    --out-dir artifacts/llm-eval/latest\n\n"
            "Strict comparison example:\n"
            "  python3 scripts/llm-compare-report.py \\\n"
            "    --api-url http://localhost:30800 \\\n"
            "    --ground-truth docs/reference/LLM_EVAL_GROUND_TRUTH_CORE.csv \\\n"
            "    --strict-eval \\\n"
            "    --providers kimi,openai,xai \\\n"
            "    --runs 1 \\\n"
            "    --max-per-family 2 \\\n"
            "    --out-dir artifacts/llm-eval/strict-real-01\n"
        ),
    )
    ap.add_argument("--api-url", default="http://localhost:30800", help="Base URL of the IDS API.")
    ap.add_argument("--username", default="admin", help="IDS API username.")
    ap.add_argument("--password", default="admin", help="IDS API password.")
    ap.add_argument("--alerts-limit", type=int, default=200, help="How many recent alerts to read from /api/alerts.")
    ap.add_argument("--out-dir", default="artifacts/llm-eval/latest", help="Directory where CSV and PNG outputs will be written.")
    ap.add_argument("--ground-truth", default="", help="CSV file with rule_pattern/source/expected_* columns.")
    ap.add_argument("--no-charts", action="store_true", help="Skip PNG chart generation.")
    ap.add_argument("--strict-eval", action="store_true", help="Re-run the same stored alerts against the requested providers with strict=true and persist=false.")
    ap.add_argument("--providers", default="", help="Comma-separated providers for strict evaluation, for example: kimi,openai,xai")
    ap.add_argument("--runs", type=int, default=1, help="How many times to repeat each alert per provider during strict evaluation.")
    ap.add_argument("--max-per-family", type=int, default=0, help="Maximum matched alerts to keep per scenario family during strict evaluation.")
    args = ap.parse_args()

    api_url = args.api_url.rstrip("/")
    out_dir = Path(args.out_dir)

    token = login(api_url, args.username, args.password)
    usage = http_json(f"{api_url}/api/metrics/llm-usage?window=today", token=token)
    comparison = http_json(f"{api_url}/api/llm/providers/comparison")
    alerts = http_json(f"{api_url}/api/alerts?limit={args.alerts_limit}")
    mappings = load_ground_truth_mappings(Path(args.ground_truth) if args.ground_truth else None)

    # Provider summary template (paper-ready columns, no fake scoring)
    provider_rows = []
    providers = {str(r.get("provider", "")).lower(): r for r in comparison.get("providers", []) or [] if is_real_provider(r.get("provider", ""))}
    usage_rows = {str(r.get("provider", "")).lower(): r for r in usage.get("providers", []) or [] if is_real_provider(r.get("provider", ""))}
    for name in sorted(n for n in (set(providers) | set(usage_rows)) if is_real_provider(n)):
        c = providers.get(name, {})
        u = usage_rows.get(name, {})
        tokens_total = int(u.get("tokens") or c.get("tokens_total") or 0)
        est_cost_usd = float(u.get("estimated_cost_usd") or c.get("total_estimated_cost_usd") or 0.0)
        est_cost_per_1m = (est_cost_usd / tokens_total * 1_000_000) if tokens_total > 0 else ""
        provider_rows.append({
            "provider": name,
            "model": c.get("model", ""),
            "status": c.get("status", ""),
            "status_category": c.get("status_category", ""),
            "last_error_category": c.get("last_error_category", ""),
            "circuit_breaker_state": c.get("circuit_breaker_state", ""),
            "runtime_attempts": c.get("attempts", 0),
            "runtime_successes": c.get("successes", 0),
            "runtime_failures": c.get("failures", 0),
            "calls": c.get("calls", u.get("calls", 0)),
            "tokens_total": tokens_total,
            "avg_latency_s": c.get("avg_latency_s", ""),
            "p95_latency_s": c.get("p95_latency_s", ""),
            "success_rate_runtime": c.get("success_rate", ""),
            "estimated_cost_usd_total": round(est_cost_usd, 6),
            "estimated_cost_usd_per_1m_tokens": round(est_cost_per_1m, 6) if est_cost_per_1m != "" else "",
            "pricing_unit_label": "USD_per_1M_tokens",
            # Paper scoring fields (to be filled after ground-truth scoring)
            "severity_accuracy_pct": "",
            "threat_type_accuracy_pct": "",
            "action_relevance_score_1_to_5": "",
            "false_high_severity_rate_pct": "",
            "false_low_severity_rate_pct": "",
            "ot_under_escalation_rate_pct": "",
            "weighted_under_escalation_penalty_avg": "",
            "unsafe_action_recommendation_rate_pct": "",
            "quality_composite_score_pct": "",
            "safety_calibration_score_proxy_pct": "",
            "consistency_score_pct": "",
            "notes": "",
        })

    provider_fields = [
        "provider", "model", "status", "status_category", "last_error_category",
        "circuit_breaker_state", "runtime_attempts", "runtime_successes", "runtime_failures",
        "calls", "tokens_total", "avg_latency_s", "p95_latency_s",
        "success_rate_runtime", "estimated_cost_usd_total", "estimated_cost_usd_per_1m_tokens",
        "pricing_unit_label", "severity_accuracy_pct", "threat_type_accuracy_pct",
        "action_relevance_score_1_to_5", "false_high_severity_rate_pct",
        "false_low_severity_rate_pct", "ot_under_escalation_rate_pct", "weighted_under_escalation_penalty_avg",
        "unsafe_action_recommendation_rate_pct", "quality_composite_score_pct", "safety_calibration_score_proxy_pct",
        "consistency_score_pct", "notes"
    ]
    write_csv(out_dir / "provider_summary_template.csv", provider_rows, provider_fields)

    strict_eval_rows: list[dict[str, Any]] = []
    # Scenario/alert scoring template
    alert_rows = []
    source_alerts = alerts.get("alerts") or []
    if args.strict_eval:
        provider_list = [normalize_text(p) for p in args.providers.split(",") if normalize_text(p)]
        if not provider_list:
            provider_list = [p for p in sorted(providers) if p not in {"anthropic"}]
        strict_eval_rows, alert_rows = run_strict_evaluation(
            api_url=api_url,
            token=token,
            source_alerts=source_alerts,
            mappings=mappings,
            providers=provider_list,
            runs=max(1, args.runs),
            max_per_family=max(0, args.max_per_family),
        )
    else:
        for a in source_alerts:
            analysis = a.get("analysis") or {}
            effective_provider, cache_hit = derive_effective_provider(a, analysis)
            if not is_real_provider(effective_provider):
                continue
            recs = analysis.get("recommendations") or []
            actions = analysis.get("automated_actions") or []
            action_text = "; ".join(str(x) for x in actions[:5]) or "; ".join(str(x) for x in recs[:5])
            row = {
                "alert_id": a.get("id") or a.get("alert_id") or "",
                "time": a.get("time") or a.get("timestamp") or "",
                "rule": a.get("rule") or "",
                "source": a.get("source") or "",
                "provider_reported": a.get("llm_engine") or "",
                "provider": effective_provider,
                "cache_hit_0_1": 1 if cache_hit else 0,
                "analysis_source": analysis.get("_analysis_source") or "",
                "severity_pred": a.get("severity", ""),
                "threat_type_pred": a.get("threat_type") or analysis.get("threat_type") or "",
                "summary_pred": a.get("summary") or analysis.get("summary") or "",
                "action_pred_class": action_text,
                "scenario_family": "",
                "safety_profile": "",
                "under_escalation_weight": "",
                # Ground truth / scoring columns to fill
                "expected_severity_min": "",
                "expected_severity_max": "",
                "expected_threat_type": "",
                "expected_safe_action_class": "",
                "severity_in_range_score_0_1": "",
                "threat_type_match_score_0_1": "",
                "action_relevance_score_1_to_5": "",
                "explanation_usefulness_score_1_to_5": "",
                "false_high_severity_0_1": "",
                "false_low_severity_0_1": "",
                "weighted_false_low_penalty": "",
                "ot_or_controlplane_sensitive_0_1": "",
                "unsafe_action_recommendation_0_1": "",
                "notes": "",
            }
            gt = match_ground_truth(row, mappings)
            if gt:
                row["scenario_family"] = gt.get("scenario_family", "")
                row["safety_profile"] = gt.get("safety_profile", "")
                row["under_escalation_weight"] = gt.get("under_escalation_weight", "")
                row["expected_severity_min"] = gt.get("expected_severity_min", "")
                row["expected_severity_max"] = gt.get("expected_severity_max", "")
                row["expected_threat_type"] = gt.get("expected_threat_type", "")
                row["expected_safe_action_class"] = gt.get("expected_safe_action_class", "")

                # First-pass auto scores (editable after export)
                try:
                    sev = int(row.get("severity_pred") or 0)
                    smin = int(gt.get("expected_severity_min") or 0)
                    smax = int(gt.get("expected_severity_max") or 0)
                    row["severity_in_range_score_0_1"] = 1 if smin <= sev <= smax else 0
                    row["false_high_severity_0_1"] = 1 if sev > smax else 0
                    row["false_low_severity_0_1"] = 1 if sev < smin else 0
                except Exception:
                    pass
                weight = to_float(gt.get("under_escalation_weight"))
                if weight is None:
                    weight = 1.0
                row["under_escalation_weight"] = weight
                false_low = to_float(row.get("false_low_severity_0_1"))
                if false_low is not None:
                    row["weighted_false_low_penalty"] = round(false_low * weight, 4)
                safety_profile = normalize_text(gt.get("safety_profile"))
                row["ot_or_controlplane_sensitive_0_1"] = 1 if any(
                    k in safety_profile for k in ["ot_", "controlplane", "availability_critical"]
                ) else 0
                row["threat_type_match_score_0_1"] = 1 if threat_matches(row.get("threat_type_pred"), gt.get("expected_threat_type")) else 0
                # Auto action relevance is coarse; human should review.
                row["action_relevance_score_1_to_5"] = 4 if action_matches_expected(row.get("action_pred_class", ""), gt.get("expected_safe_action_class", "")) else 2
                row["unsafe_action_recommendation_0_1"] = 1 if ("isolate" in normalize_text(row.get("action_pred_class")) and "allowlist" in normalize_text(gt.get("expected_safe_action_class"))) else 0
            alert_rows.append(row)
    if strict_eval_rows:
        write_csv(
            out_dir / "strict_eval_raw_results.csv",
            strict_eval_rows,
            [
                "alert_id", "provider", "run_index", "status", "strict_requested",
                "strict_satisfied", "engine_used", "latency_s", "prompt_tokens",
                "completion_tokens", "total_tokens", "estimated_cost_usd", "summary", "severity",
                "threat_type", "action_text", "error",
            ],
        )

    if strict_eval_rows:
        strict_by_provider: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in strict_eval_rows:
            if is_real_provider(row.get("provider")):
                strict_by_provider[normalize_text(row.get("provider"))].append(row)
        for prow in provider_rows:
            name = normalize_text(prow.get("provider"))
            rows = strict_by_provider.get(name, [])
            if not rows:
                continue
            attempts = len(rows)
            successes = [r for r in rows if r.get("status") == "success" and str(r.get("strict_satisfied")) == "True"]
            latencies = [float(r.get("latency_s")) for r in successes if to_float(r.get("latency_s")) is not None]
            latencies_sorted = sorted(latencies)
            p95 = ""
            if latencies_sorted:
                idx = max(0, min(len(latencies_sorted) - 1, int(round((len(latencies_sorted) - 1) * 0.95))))
                p95 = round(latencies_sorted[idx], 4)
            total_tokens = sum(int(to_int(r.get("total_tokens")) or 0) for r in successes)
            total_cost = round(sum(float(to_float(r.get("estimated_cost_usd")) or 0.0) for r in successes), 8)
            per_1m = round((total_cost / total_tokens) * 1_000_000, 6) if total_tokens > 0 else ""
            prow["runtime_attempts"] = attempts
            prow["runtime_successes"] = len(successes)
            prow["runtime_failures"] = attempts - len(successes)
            prow["calls"] = len(successes)
            prow["tokens_total"] = total_tokens
            prow["avg_latency_s"] = round(sum(latencies) / len(latencies), 4) if latencies else ""
            prow["p95_latency_s"] = p95
            prow["success_rate_runtime"] = round(len(successes) / attempts, 4) if attempts else ""
            prow["estimated_cost_usd_total"] = total_cost
            prow["estimated_cost_usd_per_1m_tokens"] = per_1m
    alert_fields = list(alert_rows[0].keys()) if alert_rows else [
        "alert_id","time","rule","source","provider_reported","provider","cache_hit_0_1","analysis_source",
        "severity_pred","threat_type_pred","summary_pred","action_pred_class","scenario_family","safety_profile","under_escalation_weight",
        "expected_severity_min","expected_severity_max","expected_threat_type","expected_safe_action_class",
        "severity_in_range_score_0_1","threat_type_match_score_0_1","action_relevance_score_1_to_5",
        "explanation_usefulness_score_1_to_5","false_high_severity_0_1","false_low_severity_0_1","weighted_false_low_penalty","ot_or_controlplane_sensitive_0_1",
        "unsafe_action_recommendation_0_1","notes"
    ]
    write_csv(out_dir / "scenario_alert_scoring_template.csv", alert_rows, alert_fields)

    # Aggregated scored provider summary (only for rows with matched ground truth)
    scored = [r for r in alert_rows if str(r.get("expected_threat_type", "")).strip()]
    scored_direct = [r for r in scored if not int(r.get("cache_hit_0_1") or 0)]
    scored_cache = [r for r in scored if int(r.get("cache_hit_0_1") or 0)]
    by_provider: dict[str, list[dict[str, Any]]] = {}
    cache_by_provider: dict[str, list[dict[str, Any]]] = {}
    for r in scored_direct:
        p = normalize_text(r.get("provider")) or "unknown"
        if not is_real_provider(p):
            continue
        by_provider.setdefault(p, []).append(r)
    for r in scored_cache:
        p = normalize_text(r.get("provider")) or "cached"
        if not is_real_provider(p):
            continue
        cache_by_provider.setdefault(p, []).append(r)
    scored_provider_rows = []
    for prow in provider_rows:
        name = normalize_text(prow.get("provider"))
        rows = by_provider.get(name, [])
        cache_rows = cache_by_provider.get(name, [])
        n = len(rows)
        def avg_num(key: str) -> float | str:
            vals = []
            for r in rows:
                try:
                    vals.append(float(r.get(key)))
                except Exception:
                    continue
            return round(sum(vals) / len(vals), 4) if vals else ""
        sev_acc = avg_num("severity_in_range_score_0_1")
        thr_acc = avg_num("threat_type_match_score_0_1")
        action_rel = avg_num("action_relevance_score_1_to_5")
        false_high = avg_num("false_high_severity_0_1")
        false_low = avg_num("false_low_severity_0_1")
        weighted_false_low = avg_num("weighted_false_low_penalty")
        unsafe = avg_num("unsafe_action_recommendation_0_1")
        consistency = consistency_score_pct(rows)
        scored_total_for_provider = n + len(cache_rows)
        cache_share = (len(cache_rows) / scored_total_for_provider * 100.0) if scored_total_for_provider else ""
        ot_rows = [r for r in rows if int(float(r.get("ot_or_controlplane_sensitive_0_1") or 0)) == 1]
        ot_under_vals = []
        for r in ot_rows:
            try:
                ot_under_vals.append(float(r.get("false_low_severity_0_1")))
            except Exception:
                continue
        ot_under = round(sum(ot_under_vals) / len(ot_under_vals), 4) if ot_under_vals else ""
        # Composite quality score (first-pass proxy): severity + threat + action relevance.
        quality_components = []
        if sev_acc != "":
            quality_components.append(float(sev_acc) * 100.0 * 0.4)
        if thr_acc != "":
            quality_components.append(float(thr_acc) * 100.0 * 0.4)
        if action_rel != "":
            quality_components.append((float(action_rel) / 5.0) * 100.0 * 0.2)
        quality_composite = round(sum(quality_components), 2) if len(quality_components) == 3 else ""
        # Safety calibration proxy emphasizes under-escalation (especially weighted OT/control-plane rows).
        safety_proxy = ""
        if false_high != "" and weighted_false_low != "" and unsafe != "":
            # Weighted false-low may exceed 1.0 when under_escalation_weight > 1, cap penalty at 1.5 before scaling.
            weighted_low_penalty = min(1.5, float(weighted_false_low))
            false_high_penalty = min(1.0, float(false_high))
            unsafe_penalty = min(1.0, float(unsafe))
            # Penalty budget weights: under-escalation 50%, false-high 30%, unsafe actions 20%.
            penalty = (weighted_low_penalty / 1.5) * 0.5 + false_high_penalty * 0.3 + unsafe_penalty * 0.2
            safety_proxy = round(max(0.0, (1.0 - penalty)) * 100.0, 2)
        scored_provider_rows.append({
            **prow,
            "scored_alerts_n": n,
            "ot_or_controlplane_sensitive_scored_alerts_n": len(ot_rows),
            "scored_cache_alerts_n": len(cache_rows),
            "scored_total_alerts_n": scored_total_for_provider,
            "cache_hit_share_pct_of_scored": round(cache_share, 2) if cache_share != "" else "",
            "severity_accuracy_pct": round(float(sev_acc) * 100, 2) if sev_acc != "" else "",
            "threat_type_accuracy_pct": round(float(thr_acc) * 100, 2) if thr_acc != "" else "",
            "action_relevance_score_1_to_5": action_rel,
            "false_high_severity_rate_pct": round(float(false_high) * 100, 2) if false_high != "" else "",
            "false_low_severity_rate_pct": round(float(false_low) * 100, 2) if false_low != "" else "",
            "ot_under_escalation_rate_pct": round(float(ot_under) * 100, 2) if ot_under != "" else "",
            "weighted_under_escalation_penalty_avg": round(float(weighted_false_low), 4) if weighted_false_low != "" else "",
            "unsafe_action_recommendation_rate_pct": round(float(unsafe) * 100, 2) if unsafe != "" else "",
            "quality_composite_score_pct": quality_composite,
            "safety_calibration_score_proxy_pct": safety_proxy,
            "consistency_score_pct": consistency,
        })
    scored_fields = ["scored_alerts_n"] + [f for f in provider_fields if f != "notes"] + ["notes"]
    # reorder to keep provider fields first
    scored_fields = ["provider", "model", "scored_alerts_n", "ot_or_controlplane_sensitive_scored_alerts_n",
                     "scored_cache_alerts_n", "scored_total_alerts_n",
                     "cache_hit_share_pct_of_scored", "status", "status_category", "last_error_category",
                     "circuit_breaker_state", "runtime_attempts", "runtime_successes", "runtime_failures",
                     "calls", "tokens_total", "avg_latency_s", "p95_latency_s",
                     "success_rate_runtime", "estimated_cost_usd_total", "estimated_cost_usd_per_1m_tokens",
                     "pricing_unit_label", "severity_accuracy_pct", "threat_type_accuracy_pct",
                     "action_relevance_score_1_to_5", "false_high_severity_rate_pct",
                     "false_low_severity_rate_pct", "ot_under_escalation_rate_pct", "weighted_under_escalation_penalty_avg",
                     "unsafe_action_recommendation_rate_pct", "quality_composite_score_pct", "safety_calibration_score_proxy_pct",
                     "consistency_score_pct", "notes"]
    write_csv(out_dir / "provider_summary_scored.csv", scored_provider_rows, scored_fields)

    # Scenario family rollups (provider-specific, scored rows only)
    family_rollups: list[dict[str, Any]] = []
    fam_keys = sorted({normalize_text(r.get("scenario_family")) for r in scored if normalize_text(r.get("scenario_family"))})
    provider_names = sorted({normalize_text(r.get("provider")) for r in scored if is_real_provider(r.get("provider"))})
    for fam in fam_keys:
        fam_rows = [r for r in scored if normalize_text(r.get("scenario_family")) == fam]
        fam_direct = [r for r in fam_rows if not int(r.get("cache_hit_0_1") or 0)]
        fam_cache = [r for r in fam_rows if int(r.get("cache_hit_0_1") or 0)]
        # aggregate all providers for family
        for p in ["__all__"] + provider_names:
            if p == "__all__":
                rows = fam_direct
                cache_rows = fam_cache
            else:
                rows = [r for r in fam_direct if normalize_text(r.get("provider")) == p]
                cache_rows = [r for r in fam_cache if normalize_text(r.get("provider")) == p]
            if not rows and not cache_rows:
                continue

            def fam_avg(rows_in: list[dict[str, Any]], key: str) -> float | str:
                vals = []
                for rr in rows_in:
                    try:
                        vals.append(float(rr.get(key)))
                    except Exception:
                        continue
                return round(sum(vals) / len(vals), 4) if vals else ""

            sev_acc = fam_avg(rows, "severity_in_range_score_0_1")
            thr_acc = fam_avg(rows, "threat_type_match_score_0_1")
            action_rel = fam_avg(rows, "action_relevance_score_1_to_5")
            false_high = fam_avg(rows, "false_high_severity_0_1")
            false_low = fam_avg(rows, "false_low_severity_0_1")
            weighted_false_low = fam_avg(rows, "weighted_false_low_penalty")
            unsafe = fam_avg(rows, "unsafe_action_recommendation_0_1")
            ot_rows = [r for r in rows if int(float(r.get("ot_or_controlplane_sensitive_0_1") or 0)) == 1]
            ot_under_vals = []
            for rr in ot_rows:
                try:
                    ot_under_vals.append(float(rr.get("false_low_severity_0_1")))
                except Exception:
                    continue
            ot_under = round(sum(ot_under_vals) / len(ot_under_vals), 4) if ot_under_vals else ""
            safety_proxy = ""
            if false_high != "" and weighted_false_low != "" and unsafe != "":
                penalty = (min(1.5, float(weighted_false_low)) / 1.5) * 0.5 + min(1.0, float(false_high)) * 0.3 + min(1.0, float(unsafe)) * 0.2
                safety_proxy = round(max(0.0, (1.0 - penalty)) * 100.0, 2)
            total_n = len(rows) + len(cache_rows)
            cache_share = (len(cache_rows) / total_n * 100.0) if total_n else ""
            family_rollups.append({
                "scenario_family": fam,
                "provider": "all_providers" if p == "__all__" else p,
                "scored_alerts_n": len(rows),
                "ot_or_controlplane_sensitive_scored_alerts_n": len(ot_rows),
                "scored_cache_alerts_n": len(cache_rows),
                "scored_total_alerts_n": total_n,
                "cache_hit_share_pct_of_scored": round(cache_share, 2) if cache_share != "" else "",
                "severity_accuracy_pct": round(float(sev_acc) * 100, 2) if sev_acc != "" else "",
                "threat_type_accuracy_pct": round(float(thr_acc) * 100, 2) if thr_acc != "" else "",
                "action_relevance_score_1_to_5": action_rel,
                "false_high_severity_rate_pct": round(float(false_high) * 100, 2) if false_high != "" else "",
                "false_low_severity_rate_pct": round(float(false_low) * 100, 2) if false_low != "" else "",
                "ot_under_escalation_rate_pct": round(float(ot_under) * 100, 2) if ot_under != "" else "",
                "weighted_under_escalation_penalty_avg": round(float(weighted_false_low), 4) if weighted_false_low != "" else "",
                "unsafe_action_recommendation_rate_pct": round(float(unsafe) * 100, 2) if unsafe != "" else "",
                "safety_calibration_score_proxy_pct": safety_proxy,
                "consistency_score_pct": consistency_score_pct(rows),
            })
    family_fields = [
        "scenario_family", "provider", "scored_alerts_n", "ot_or_controlplane_sensitive_scored_alerts_n",
        "scored_cache_alerts_n", "scored_total_alerts_n",
        "cache_hit_share_pct_of_scored", "severity_accuracy_pct", "threat_type_accuracy_pct",
        "action_relevance_score_1_to_5", "false_high_severity_rate_pct", "false_low_severity_rate_pct",
        "ot_under_escalation_rate_pct", "weighted_under_escalation_penalty_avg",
        "unsafe_action_recommendation_rate_pct", "safety_calibration_score_proxy_pct", "consistency_score_pct"
    ]
    write_csv(out_dir / "scenario_family_results_scored.csv", family_rollups, family_fields)

    # Explicit cache-only rollup to avoid mixing cache hits into provider quality claims
    cache_rollup_rows: list[dict[str, Any]] = []
    all_cache = [r for r in scored if int(r.get("cache_hit_0_1") or 0)]
    for p in sorted({normalize_text(r.get("provider")) for r in all_cache if is_real_provider(r.get("provider"))}):
        rows = [r for r in all_cache if normalize_text(r.get("provider")) == p]
        fam_counter = Counter(normalize_text(r.get("scenario_family")) or "unmapped" for r in rows)
        cache_rollup_rows.append({
            "provider_effective": p,
            "cache_scored_alerts_n": len(rows),
            "top_scenario_family": fam_counter.most_common(1)[0][0] if fam_counter else "",
            "top_scenario_family_n": fam_counter.most_common(1)[0][1] if fam_counter else 0,
            "note": "Cache-hit rows excluded from direct provider quality scoring; tracked separately."
        })
    write_csv(out_dir / "cache_hit_rollup.csv", cache_rollup_rows,
              ["provider_effective", "cache_scored_alerts_n", "top_scenario_family", "top_scenario_family_n", "note"])

    # Paper-style scorecard (proxy metrics where exact values are unavailable in current snapshot)
    scorecard_rows = build_provider_scorecard(scored_provider_rows)
    scorecard_fields = [
        "provider", "model", "scored_alerts_n_direct", "scored_alerts_n_total_including_cache",
        "cache_hit_share_pct_of_scored", "quality_composite_score_pct", "severity_accuracy_pct",
        "threat_type_accuracy_pct", "action_relevance_score_1_to_5", "estimated_cost_usd_per_1m_tokens",
        "avg_latency_ms", "reliability_runtime_success_pct", "safety_calibration_score_proxy_pct",
        "ot_under_escalation_rate_pct", "consistency_score_pct",
        "rank_quality", "rank_cost", "rank_latency", "rank_reliability_runtime", "rank_safety_proxy",
        "overall_rank_proxy", "scorecard_note"
    ]
    write_csv(out_dir / "provider_scorecard_ranked.csv", scorecard_rows, scorecard_fields)

    charts_generated: list[str] = []
    if not args.no_charts:
        charts_generated = maybe_write_charts(out_dir, provider_rows, scored_provider_rows, family_rollups)

    summary = {
        "api_url": api_url,
        "pricing_unit_label": "USD_per_1M_tokens",
        "cost_values_are_estimated": bool(usage.get("cost_values_are_estimated", True)),
        "cost_estimation_method": usage.get("cost_estimation_method", "unknown"),
        "provider_count": len(provider_rows),
        "alerts_exported": len(alert_rows),
        "ground_truth_rules_loaded": len(mappings),
        "matched_alerts_for_scoring": len(scored),
        "matched_alerts_for_scoring_direct_provider": len(scored_direct),
        "matched_alerts_for_scoring_cache_hits": len(scored_cache),
        "scenario_families_scored": len(fam_keys),
        "charts_generated_n": len(charts_generated),
        "outputs": [
            str(out_dir / "provider_summary_template.csv"),
            str(out_dir / "scenario_alert_scoring_template.csv"),
            str(out_dir / "provider_summary_scored.csv"),
            str(out_dir / "scenario_family_results_scored.csv"),
            str(out_dir / "cache_hit_rollup.csv"),
            str(out_dir / "provider_scorecard_ranked.csv"),
        ],
        "charts": charts_generated,
        "scoring_scope_note": "Direct provider quality metrics exclude cache-hit rows; cache-hit rows are reported separately.",
        "safety_scoring_note": "Safety calibration fields are proxy metrics derived from ground-truth severity ranges and configurable under_escalation_weight values.",
    }
    if strict_eval_rows:
        summary["strict_eval"] = {
            "providers_requested": sorted({r["provider"] for r in strict_eval_rows}),
            "runs_per_provider": max(1, args.runs),
            "max_per_family": max(0, args.max_per_family),
            "successful_strict_runs": sum(1 for r in strict_eval_rows if r.get("status") == "success" and r.get("strict_satisfied")),
            "failed_strict_runs": sum(1 for r in strict_eval_rows if r.get("status") != "success" or not r.get("strict_satisfied")),
        }
        summary["outputs"].append(str(out_dir / "strict_eval_raw_results.csv"))
    (out_dir / "README.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
