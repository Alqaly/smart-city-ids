# Documentation index

Quick reference for all documentation in this repo. **Start here** to find what you need.

## Quick links for common tasks
- **Quick-start (5 min)**: see README.md (repo root) → Quick start section
- **Set up locally (30 min)**: see QUICK_START.md
- **Run full demo (K3s + services)**: see PROJECT_CONTEXT.md → Full demo runbook
- **Understand the architecture**: see PROJECT_CONTEXT.md → Architecture section
- **Report project status to instructor/LLM**: see PROJECT_STATUS.md
- **Validate before PR/demo**: see DOCS_CHECKLIST.md and SMOKE_TESTS.md
- **Troubleshoot common issues**: see PROJECT_CONTEXT.md → Troubleshooting section

## All docs (organized by purpose)

### Project overview & status
- **PROJECT_STATUS.md** — snapshot of current progress, recent changes, next steps. **Show this to instructors.**
- **PROJECT_CONTEXT.md** — full architecture, demo runbook, K8s manifests, Falco config, troubleshooting, recovery commands. **Read this before running the full demo.**
- **QUICK_START.md** — step-by-step: virtualenv, IDS API, sample alert, and smoke tests. **Quickest way to get running locally.**

### Quality assurance & validation
- **DOCS_CHECKLIST.md** — checklist for contributors: validate quick-start, migrations, examples, links, lint.
- **SMOKE_TESTS.md** — local and CI smoke-test steps, expected outputs, how to debug failures.

### Developer guides & conventions
- **CONTRIBUTING.md** (if present) — contribution workflow, branch strategy, PR template.
- **.github/copilot-instructions.md** — AI agent guidance: key workflows, LLM contract, integration points, troubleshooting.

### Config & deployment
- **Makefile** (repo root) — targets: check, db-migrate, start, ids-api-venv, test, docs-check, smoke-test.
- **.markdownlint.json** (repo root) — markdown style rules (lint config).
- **.github/workflows/*.yml** — CI automation: docs validation, smoke tests.

## How to use this index
1. **New contributor?** Start with QUICK_START.md, then PROJECT_CONTEXT.md.
2. **Running a demo?** Follow PROJECT_CONTEXT.md → Full demo runbook.
3. **Making a change?** Check DOCS_CHECKLIST.md and update relevant docs.
4. **Report progress?** Copy PROJECT_STATUS.md and share with instructors.
5. **Troubleshoot?** Search PROJECT_CONTEXT.md Troubleshooting section or ask an LLM.

## Keeping docs current
- Update PROJECT_STATUS.md after each major milestone (new features, fixes, infra changes).
- Update PROJECT_CONTEXT.md when changing automation thresholds, K8s manifests, Falco config, or troubleshooting steps.
- Update DOCS_CHECKLIST.md when onboarding new contributors or adding validation steps.
- Run `make docs-check` before committing doc changes (checks markdown lint + broken links).

---
Last updated: 2026-01-11
