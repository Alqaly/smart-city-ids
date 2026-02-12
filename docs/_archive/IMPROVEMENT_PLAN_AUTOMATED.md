# IMPROVEMENT PLAN - AUTOMATED

**This document is DEPRECATED. Use the automated improvement system instead.**

## Quick Start

```bash
# Preview changes
./scripts/improvements/improve.sh dry-run

# Apply improvements
./scripts/improvements/improve.sh run

# Rollback if needed
./scripts/improvements/improve.sh rollback
```

## Why Automated?

| Manual Approach (OLD) | Automated Approach (NEW) |
|----------------------|--------------------------|
| ❌ Copy-paste commands | ✅ Single command |
| ❌ Easy to miss steps | ✅ Consistent execution |
| ❌ No rollback | ✅ Built-in rollback |
| ❌ No dry-run | ✅ Preview changes first |
| ❌ Hard to extend | ✅ Plugin-based, add new improvements easily |
| ❌ Manual tracking | ✅ Automatic logging & audit trail |

## Documentation

See: [scripts/improvements/README.md](./scripts/improvements/README.md)

## Files

```
scripts/improvements/
├── improve.sh           # Main entry point
├── run_improvements.py  # Plugin-based improvement engine
├── config.yaml          # Enable/disable improvements
└── README.md            # Full documentation
```

## Available Improvements

### Phase 0: Stabilization
- `disable_duplicate_configmaps` - Fix duplicate Grafana ConfigMaps
- `disable_orphaned_manifests` - Disable orphaned K8s manifests

### Phase 1: Data Quality
- `suppress_false_positives` - Filter known false positive alerts
- `add_prometheus_alerts` - Add alerting rules

### Phase 2: Monitoring (TODO)
- `add_data_quality_panels` - Dashboard panels for data quality
- `enable_alert_deduplication` - Reduce duplicate alerts

## Configuration

Edit `scripts/improvements/config.yaml`:

```yaml
improvements:
  disable_duplicate_configmaps:
    enabled: true  # Set to false to skip
    
  suppress_false_positives:
    enabled: true
    config:
      rules:
        - rule: "Read sensitive file untrusted"
          filters:
            - container_pattern: "postgres*"
```

## Adding New Improvements

Just add a class with the `@ImprovementRegistry.register()` decorator:

```python
@ImprovementRegistry.register("my_improvement", phase=1)
class MyImprovement(BaseImprovement):
    def check_applicable(self) -> bool:
        return True
    
    def apply(self) -> ImprovementResult:
        # Do the work
        return ImprovementResult(name="my_improvement", success=True, message="Done")
    
    def rollback(self, rollback_data: Dict) -> bool:
        return True
```

The system auto-discovers new improvements. No hardcoded lists.

---

**Generated:** 2026-02-05  
**Replaces:** COMPREHENSIVE_IMPROVEMENT_PLAN.md (900+ lines of manual steps)
