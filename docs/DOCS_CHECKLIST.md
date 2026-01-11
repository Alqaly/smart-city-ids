# Docs validation checklist

Use this before PRs, demos, or major releases.

## Pre-commit checks
- [ ] Run `make docs-check` (markdown lint + link validation) — should pass with no errors.
- [ ] Run `make check` (environment validation) — should show all tools present.
- [ ] Run `make smoke-test` (API smoke tests) — should pass with no failures.

## Documentation updates
- [ ] Update docs/PROJECT_STATUS.md if scope, architecture, or workflows changed.
- [ ] Update docs/PROJECT_CONTEXT.md if thresholds, K8s manifests, or troubleshooting steps changed.
- [ ] Update docs/QUICK_START.md if setup steps or prerequisites changed.
- [ ] Add new docs to docs/INDEX.md if creating new documentation.

## Code examples & contracts
- [ ] LLM input/output examples in PROJECT_CONTEXT.md match actual code.
- [ ] Alert JSON examples in QUICK_START.md and PROJECT_CONTEXT.md are valid and tested.
- [ ] API endpoint examples in docs are correct and runnable.

## Links & references
- [ ] No broken internal links (check with `make docs-check`).
- [ ] All file paths use correct repo structure.
- [ ] Cross-references between docs are accurate.

## Quick-start validation
- [ ] Follow docs/QUICK_START.md end-to-end locally and verify all steps work.
- [ ] Sample alert in step 6 returns HTTP 200 with valid analysis.
- [ ] Smoke tests in step 8 pass without modifications.

## Full demo validation
- [ ] Follow docs/PROJECT_CONTEXT.md → Full demo runbook.
- [ ] All pods start successfully: `kubectl get pods -n smart-city`.
- [ ] Falco detects attacks and forwards alerts.
- [ ] IDS API receives alerts and analyzes with LLM.
- [ ] K8s automation actions execute (scale, evict).
- [ ] No errors in logs: `kubectl logs -n smart-city --all-containers=true --tail=50`.

## Troubleshooting coverage
- [ ] All common errors from docs/PROJECT_CONTEXT.md Troubleshooting are documented with fixes.
- [ ] New errors encountered during testing are added to troubleshooting section.

## Commit message
- [ ] Commit message references which docs were updated.
- [ ] Example: `git commit -m "docs: update QUICK_START and PROJECT_CONTEXT with new thresholds"`

---
**Estimated time:** 30–60 min depending on scope of changes.  
**Best practice:** Run this checklist before every PR and release.
