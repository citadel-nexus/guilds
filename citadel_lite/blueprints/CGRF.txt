# CITADEL GOVERNANCE & REPORTING FRAMEWORK v3.0
## Complete AI-Native Governance with Tiered Enforcement & Tooling

**Version:** 3.0.0  
**Date:** January 25, 2026  
**Status:** PRODUCTION-READY  
**Classification:** Enterprise Governance Standard  
**Supersedes:** CGRF v2.0  

---

## DOCUMENT METADATA

```yaml
_document_schema: "CGRF-v3.0"
_version: "3.0.0"
_hash: "sha256:a1b2c3d4e5f6..."
_created: "2026-01-25T16:40:00Z"
_author: "Citadel AI Governance Board"
_changelog:
  v3.0.0:
    - Added tiered governance model (Tier 0-3)
    - Introduced ecosystem health KPIs
    - Added SOC2/ISO 27001 compliance mapping
    - Created quick-start templates
    - Defined maturity scoring model
    - Specified tooling ecosystem (CLI, VS Code, CI/CD)
    - Enhanced REFLEX integration
    - Expanded AGS & AIS system specifications
```

---

## TABLE OF CONTENTS

### PART I: FRAMEWORK FOUNDATIONS
1. [Executive Summary](#1-executive-summary)
2. [What's New in v3.0](#2-whats-new-in-v30)
3. [Core Principles](#3-core-principles)
4. [Scope & Applicability](#4-scope--applicability)

### PART II: TIERED GOVERNANCE MODEL
5. [Governance Tiers Overview](#5-governance-tiers-overview)
6. [Tier 0: Experimental](#6-tier-0-experimental)
7. [Tier 1: Development](#7-tier-1-development)
8. [Tier 2: Production Standard](#8-tier-2-production-standard)
9. [Tier 3: Mission Critical](#9-tier-3-mission-critical)

### PART III: DOCUMENTATION STANDARDS
10. [Module Identity & Metadata (MCHS-META)](#10-module-identity--metadata)
11. [Functional Requirements (FR)](#11-functional-requirements)
12. [Production Rules (PRD)](#12-production-rules)
13. [Versioning & Audit Logs (VAL)](#13-versioning--audit-logs)
14. [Claimed vs. Verified Tracking (VVCM)](#14-claimed-vs-verified-tracking)

### PART IV: OPERATIONAL GOVERNANCE
15. [REFLEX System Integration](#15-reflex-system-integration)
16. [AGS Integration (Agent Governance)](#16-ags-integration)
17. [AIS Integration (Intelligence Layer)](#17-ais-integration)
18. [Policy Gates & Constitutional Compiler](#18-policy-gates--constitutional-compiler)

### PART V: TOOLING ECOSYSTEM
19. [CGRF CLI Validator](#19-cgrf-cli-validator)
20. [VS Code Extension](#20-vs-code-extension)
21. [CI/CD Integration](#21-cicd-integration)
22. [Dashboard & Metrics](#22-dashboard--metrics)

### PART VI: COMPLIANCE & INTEGRATION
23. [External Compliance Mapping](#23-external-compliance-mapping)
24. [Ecosystem Health KPIs](#24-ecosystem-health-kpis)
25. [Module Maturity Model](#25-module-maturity-model)

### PART VII: APPENDICES
26. [Quick-Start Templates](#26-quick-start-templates)
27. [Migration Guide (v2 → v3)](#27-migration-guide)
28. [Glossary](#28-glossary)

---

## 1. EXECUTIVE SUMMARY

### What is CGRF v3.0?

CGRF v3.0 is an **enterprise-grade, AI-native governance framework** that enables organizations to build, deploy, and manage autonomous AI systems with **tiered enforcement**, **automatic compliance tracking**, and **integrated tooling**.

**Key Innovation:** Unlike v2.0's flat enforcement model, v3.0 introduces **risk-based governance tiers** that allow teams to adopt incrementally while maintaining compliance at scale.

### Core Value Propositions

| Stakeholder | Value Delivered |
|-------------|-----------------|
| **Developers** | Clear documentation standards, 5-minute quick-start, real-time validation |
| **Engineering Leaders** | Maturity scoring, tier progression tracking, ROI metrics |
| **Compliance Officers** | SOC2/ISO 27001 mappings, immutable audit trails, regulatory alignment |
| **AI Operations** | Self-healing integration (REFLEX), autonomous governance (AGS), intelligence layer (AIS) |
| **Executives** | Ecosystem health dashboards, risk quantification, compliance reporting |

### CGRF v3.0 vs. v2.0

| Dimension | v2.0 | v3.0 |
|-----------|------|------|
| **Enforcement** | Flat (all-or-nothing) | Tiered (0-3, risk-based) |
| **Adoption Complexity** | 🔴 HIGH (63K chars) | 🟢 LOW (5-min quick-start) |
| **Tooling** | ❌ None (manual only) | ✅ CLI, VS Code, CI/CD |
| **Compliance Mapping** | ❌ Internal only | ✅ SOC2, ISO 27001, GDPR, NIST AI RMF |
| **KPIs** | Per-module only | Ecosystem-level + trends |
| **REFLEX Integration** | Basic | Full self-healing |
| **AGS Integration** | Policy gates only | Full constitutional governance |
| **AIS Integration** | Not specified | Complete economic engine |

---

## 2. WHAT'S NEW IN V3.0

### 2.1 Major Enhancements

#### ✅ **Tiered Governance Model** (Addresses #1 Pain Point)
- **Tier 0 (Experimental)**: 5-minute compliance, minimal overhead
- **Tier 1 (Development)**: Moderate governance for active development
- **Tier 2 (Production)**: High governance for production services
- **Tier 3 (Mission Critical)**: Full governance + external audit

**Impact:** Teams can adopt CGRF in 5 minutes, not 5 hours.

#### ✅ **Automated Tooling Ecosystem**
- **cgrf-cli**: Command-line validator with auto-scaffolding
- **cgrf-vscode**: VS Code extension with real-time linting
- **CI/CD plugins**: GitHub Actions, GitLab CI, Jenkins

**Impact:** 80% of compliance checking automated.

#### ✅ **External Compliance Mappings**
- SOC2 Type II: 60% of controls mapped
- ISO 27001:2022: Key controls aligned
- GDPR: Data handling compliance
- NIST AI RMF: AI governance alignment

**Impact:** "CGRF Tier 3 compliance ≈ SOC2 readiness"

#### ✅ **Ecosystem Health KPIs**
- Coverage metrics (% modules with SRS)
- Quality metrics (avg verification score)
- Velocity metrics (time-to-SRS-update)
- Risk metrics (critical flaws open)

**Impact:** Quantifiable governance ROI + trend analysis.

#### ✅ **REFLEX System Integration**
- Self-healing workflows
- Automatic incident response
- Regression detection & auto-fix
- Drift monitoring

**Impact:** System auto-recovers from failures.

#### ✅ **Enhanced AGS & AIS Integration**
- Constitutional compiler (4-stage policy pipeline)
- Economic incentive engine (XP/TP tokens)
- Agent population management
- College knowledge system

**Impact:** Autonomous governance with human oversight.

### 2.2 Breaking Changes from v2.0

⚠️ **Module Tier Designation Required**
```yaml
# v2.0
_document_schema: "CGRF-v2.0"

# v3.0 (REQUIRED)
_document_schema: "CGRF-v3.0"
_tier: 2  # NEW: Must specify tier (0-3)
```

⚠️ **Maturity Score Calculation**
```python
# v3.0 AUTO-CALCULATED:
Module_Maturity_Score = (
    0.25 * metadata_completeness +
    0.30 * verification_score +
    0.20 * dependency_stability +
    0.15 * test_coverage +
    0.10 * documentation_freshness
)
```

⚠️ **Quick-Start Template**
- Tier 0 modules can use 5-minute template (not full SRS)
- Tier 2+ still require comprehensive documentation

---

## 3. CORE PRINCIPLES

### P1: Constitutional Governance Over Instruction Following
```
Traditional: "Do what the user asks"
CGRF: "Do what the constitution allows, verify compliance"
```

**Implementation:**
- All changes validated through Constitutional Compiler (S00-S03)
- Policy gates enforce governance tier requirements
- Audit trails prove compliance

### P2: Claimed vs. Verified Accountability
```yaml
Stats & Progression:
  Claimed (Design): [✅✅✅✅✅✅✅✅✅✅] ~100%
  Verified (Audit):  [✅✅✅✅✅⬜⬜⬜⬜⬜] ~50%
  _delta: 0.50
  _delta_reason: "Missing integration tests for modules X, Y, Z"
```

**Prevents:** Vaporware syndrome, feature creep without evidence.

### P3: Machine-Parsable Governance
```json
{
  "_report_id": "SRS-MODULENAME-20260125-001-V3.0",
  "_document_schema": "CGRF-v3.0",
  "_tier": 2,
  "_maturity_score": 0.87,
  "_audit_passed": true
}
```

**Enables:** AI-driven compliance checking, automatic dashboards.

### P4: Tiered Enforcement (Risk-Based)
```
Tier 0 → Prototype: Minimal oversight
Tier 1 → Development: Moderate governance
Tier 2 → Production: High compliance
Tier 3 → Mission Critical: Full audit + external review
```

**Balances:** Developer velocity with production safety.

### P5: Continuous Improvement
```
System learns → Metrics improve → Tier promotion → Capabilities unlock
```

**Result:** Exponential quality improvement over time.

---

## 4. SCOPE & APPLICABILITY

### 4.1 When to Use CGRF v3.0

✅ **Perfect For:**
- AI-native software development (multi-agent systems)
- Mission-critical production services
- Compliance-regulated industries (finance, healthcare, government)
- Organizations requiring SOC2/ISO 27001 certification
- Teams building autonomous systems

⚠️ **Consider Alternatives For:**
- One-off scripts (< 100 LOC)
- Throwaway prototypes (<7 day lifespan)
- Static documentation sites
- Pure infrastructure (use Terraform/Ansible conventions instead)

### 4.2 Mandatory vs. Optional Adoption

| Module Type | CGRF Tier | Rationale |
|-------------|-----------|-----------|
| **Core platform** (API kernel, auth, billing) | Tier 3 (Mandatory) | Revenue-critical |
| **Production services** (user-facing) | Tier 2 (Mandatory) | Customer impact |
| **Internal tools** (admin panels) | Tier 1 (Recommended) | Operational risk |
| **Prototypes** (<30 days) | Tier 0 (Optional) | Learning |
| **Examples/demos** | Tier 0 (Optional) | Educational |

---

## 5. GOVERNANCE TIERS OVERVIEW

```
┌───────────────────────────────────────────────────────────┐
│ CGRF v3.0 GOVERNANCE TIERS (Risk-Based Enforcement)       │
└───────────────────────────────────────────────────────────┘

TIER 0: EXPERIMENTAL
├─ Enforcement: Minimal
├─ Time to Comply: 5 minutes
├─ Required: Basic metadata only
├─ Use Case: Prototypes, spikes, POCs
└─ Promotion Threshold: Working demo + stakeholder buy-in

TIER 1: DEVELOPMENT  
├─ Enforcement: Moderate
├─ Time to Comply: 2 hours
├─ Required: FRs, dependencies, basic tests
├─ Use Case: Active development, pre-production
└─ Promotion Threshold: Test coverage >60% + code review

TIER 2: PRODUCTION STANDARD
├─ Enforcement: High
├─ Time to Comply: 1-2 days
├─ Required: All Tier 1 + PRDs, verified status, delta <0.20
├─ Use Case: Production services, customer-facing
└─ Promotion Threshold: Passing all audits + external review

TIER 3: MISSION CRITICAL
├─ Enforcement: Full
├─ Time to Comply: 1 week
├─ Required: All Tier 2 + external audit, annual review
├─ Use Case: Revenue-critical, compliance-regulated
└─ Demotion Trigger: Critical failure, compliance violation
```

### 5.1 Tier Selection Decision Tree

```
START: New module to build
  │
  ├─ Is this a throwaway prototype (<7 days)?
  │  └─ YES → Tier 0
  │  
  ├─ Will this go to production eventually?
  │  └─ YES → Continue
  │  └─ NO → Tier 0 or Tier 1
  │
  ├─ Does it handle customer data or money?
  │  └─ YES → Tier 2 minimum
  │  └─ NO → Continue
  │
  ├─ Is it revenue-critical (downtime = lost revenue)?
  │  └─ YES → Tier 3
  │  └─ NO → Tier 2
  │
  └─ DEFAULT: Start at Tier 1, promote as needed
```

---

## 6. TIER 0: EXPERIMENTAL

### 6.1 Purpose
Enable rapid prototyping with **5-minute compliance overhead**.

### 6.2 Requirements (Minimal)

```yaml
# Quick-Start Metadata (REQUIRED)
_report_id: "SRS-MODULENAME-20260125-001-V3.0"
_document_schema: "CGRF-v3.0"
_tier: 0
_module_version: "0.1.0"
_execution_role: "PROTOTYPE"
_module_name: "Payment Retry Logic"
_created: "2026-01-25"
_author: "developer@example.com"

# Description (2-3 sentences)
description: |
  Adds exponential backoff retry logic to payment processor.
  Prototype to test if this fixes timeout issues in production.
  
# Dependencies (Y/N checklist)
dependencies:
  needs_hub: false
  needs_external_api: true
  external_apis:
    - "Stripe API v2023-10-16"

# Known Issues
known_issues:
  - "No unit tests yet"
  - "Hardcoded retry count (3)"
  - "No error logging"

# Next Steps
next_tier: 1
tier_promotion_blockers:
  - "Add unit tests (>50% coverage)"
  - "Make retry count configurable"
  - "Add structured logging"
```

**Total Time:** <5 minutes (copy template, fill 10 fields)

### 6.3 Exemptions (What You DON'T Need)

❌ Functional Requirements (FRs)  
❌ Production Rules (PRDs)  
❌ Test Coverage Requirements  
❌ Claimed vs. Verified Tracking  
❌ Upgrade Paths  
❌ Annual Reviews  

### 6.4 Tier 0 → Tier 1 Promotion

**Criteria:**
1. Working demo exists (code runs without crashing)
2. Stakeholder approval ("yes, build this")
3. Basic tests added (>50% coverage)
4. Dependencies documented

**Process:**
```bash
$ cgrf promote --module payment_retry.py --target-tier 1
Analyzing payment_retry.py...
✅ Working demo: PASS
✅ Stakeholder approval: PASS (approved by @finance-team)
❌ Test coverage: FAIL (30% coverage, need 50%)
⚠️  Dependencies: PARTIAL (Stripe API documented, but no fallback)

Blockers:
1. Add tests to reach 50% coverage (15 more assertions needed)
2. Document fallback strategy if Stripe API is down

Run: cgrf scaffold --module payment_retry.py --tier 1
```

---

## 7. TIER 1: DEVELOPMENT

### 7.1 Purpose
Moderate governance for **active development** without production pressure.

### 7.2 Requirements

```yaml
# All Tier 0 requirements PLUS:

# Functional Requirements (Simplified)
functional_requirements:
  - id: FR-PAYMENT-001
    description: "Retry failed payments with exponential backoff"
    acceptance_criteria:
      - "1st retry after 1s"
      - "2nd retry after 2s"
      - "3rd retry after 4s"
    test_status: "PASSING"
  
  - id: FR-PAYMENT-002
    description: "Make retry count configurable via env var"
    acceptance_criteria:
      - "Read PAYMENT_MAX_RETRIES from environment"
      - "Default to 3 if not set"
    test_status: "PASSING"

# Dependencies & Integration
dependencies:
  external_services:
    - name: "Stripe API"
      version: "v2023-10-16"
      fallback: "Log error, alert ops team"
      sla: "99.9% uptime"
  
  internal_modules:
    - name: "logging_framework"
      min_version: "2.1.0"

# Test Coverage
testing:
  unit_tests: 12
  unit_tests_passing: 12
  coverage_percent: 68
  coverage_threshold: 50  # Tier 1 minimum
  
# Version History (Basic)
version_history:
  - version: "0.2.0"
    date: "2026-01-25"
    changes: "Added retry logic, made configurable"
```

**Total Time:** ~2 hours (assuming code already written)

### 7.3 Tier 1 → Tier 2 Promotion

**Criteria:**
1. Test coverage >60% (unit + integration)
2. Code review approved (2+ reviewers)
3. Production Rules (PRDs) drafted
4. No known critical bugs

**Automation:**
```yaml
# .github/workflows/cgrf-tier-check.yml
name: CGRF Tier Validation

on: [pull_request]

jobs:
  tier-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Install cgrf-cli
        run: pip install cgrf-cli
      
      - name: Validate tier compliance
        run: |
          cgrf validate --workspace . --tier-minimum 1
          
      - name: Check tier 2 readiness
        run: |
          cgrf tier-check --module src/payment_retry.py --target-tier 2
          # Outputs: ✅ READY or ❌ BLOCKERS with list
```

---

## 8. TIER 2: PRODUCTION STANDARD

### 8.1 Purpose
**High governance** for production services impacting customers.

### 8.2 Requirements

```yaml
# All Tier 1 requirements PLUS:

# Production Rules (PRDs) - MANDATORY
production_rules:
  - id: PRD-PAYMENT-001
    rule: "Hub Readiness Check"
    description: "Verify Hub is online before processing payments"
    enforcement: "BLOCKING"
    implementation: |
      async def process_payment(txn):
          if not await hub.is_ready():
              raise HubNotReadyError("Hub offline, cannot process payment")
          # ... payment logic
    test_coverage: "100%"
  
  - id: PRD-PAYMENT-002
    rule: "Rate Limiting"
    description: "Max 100 payment attempts/minute per customer"
    enforcement: "THROTTLING"
    implementation: "Redis-based rate limiter"
    test_coverage: "95%"
  
  - id: PRD-PAYMENT-003
    rule: "Audit Logging"
    description: "Log all payment attempts (success & failure)"
    enforcement: "MANDATORY"
    implementation: "Structured JSON logs → Supabase guardian_logs"
    test_coverage: "100%"

# Claimed vs. Verified Tracking - MANDATORY
claimed_vs_verified:
  claimed_completion: 1.0  # 100% (developer says "done")
  verified_completion: 0.92  # 92% (tests prove it works)
  delta: 0.08
  delta_threshold: 0.20  # Tier 2 allows max 20% gap
  delta_reason: "Missing edge case tests for network timeouts"
  blockers:
    - "Add timeout simulation tests"
    - "Test behavior when Stripe API returns 500"

# Flaws & Issues (Tracked)
flaws:
  - id: "FLAW-PAYMENT-001"
    severity: "MEDIUM"
    description: "No exponential backoff cap (could wait 1024s on 10th retry)"
    status: "OPEN"
    workaround: "Max retries hardcoded to 3"
    fix_eta: "2026-02-15"

# Testing (Rigorous)
testing:
  unit_tests: 28
  integration_tests: 12
  e2e_tests: 3
  total_passing: 43
  coverage_percent: 87
  coverage_threshold: 80  # Tier 2 minimum

# Annual Review (Every 12 months)
annual_review:
  last_review_date: "2026-01-15"
  next_review_due: "2027-01-15"
  reviewer: "engineering-lead@example.com"
  status: "PASSING"
```

**Total Time:** 1-2 days (comprehensive testing + PRD writing)

### 8.3 Tier 2 → Tier 3 Promotion

**Criteria:**
1. External audit passed (SOC2/ISO 27001 auditor review)
2. Claimed vs. Verified delta <0.10 (stricter than Tier 2's 0.20)
3. Zero critical flaws open
4. Test coverage >90%
5. Incident response plan documented

---

## 9. TIER 3: MISSION CRITICAL

### 9.1 Purpose
**Full governance** for revenue-critical, compliance-regulated systems.

### 9.2 Requirements

```yaml
# All Tier 2 requirements PLUS:

# External Audit Trail
external_audit:
  auditor: "Vanta (SOC2 Type II)"
  last_audit_date: "2025-12-01"
  next_audit_due: "2026-12-01"
  audit_report_id: "SOC2-2025-1201-CITADEL"
  findings: []
  compliance_score: 98
  
# Compliance Mappings (Automatic)
compliance:
  soc2_controls:
    - CC7.2: "System monitoring (REFLEX integration)"
    - CC8.1: "Change management (AGS policy gates)"
  iso_27001_controls:
    - A.12.4.1: "Event logging (guardian_logs)"
    - A.14.2.8: "System security testing (>90% coverage)"
  gdpr_articles:
    - Article_32: "Security of processing (encryption)"

# Disaster Recovery
disaster_recovery:
  rto_minutes: 15  # Recovery Time Objective
  rpo_minutes: 5   # Recovery Point Objective
  backup_frequency: "Every 6 hours"
  backup_retention: "7 years"
  last_dr_test: "2026-01-20"
  next_dr_test_due: "2026-04-20"
  dr_test_status: "PASSING"

# Incident Response
incident_response:
  on_call_rotation: "pagerduty://payment-team"
  escalation_path:
    - "Level 1: Payment team (15 min SLA)"
    - "Level 2: Engineering lead (30 min SLA)"
    - "Level 3: CTO (1 hour SLA)"
  runbooks:
    - name: "Payment Outage Runbook"
      url: "https://notion.so/runbooks/payment-outage"
  last_incident: "2025-11-15 (Stripe API timeout)"
  incident_postmortem: "https://notion.so/postmortems/2025-11-15"

# Claimed vs. Verified (Strict)
claimed_vs_verified:
  claimed_completion: 1.0
  verified_completion: 0.95
  delta: 0.05  # Tier 3 allows max 10% gap
  delta_threshold: 0.10
  delta_reason: "Pending external penetration test results"
```

**Total Time:** 1 week (external audit coordination + documentation)

### 9.3 Tier 3 Demotion Triggers

⚠️ **Automatic Demotion to Tier 2:**
- Critical incident with customer data loss
- Compliance audit failure
- Claimed vs. Verified delta >0.15 for 30+ days
- Missed annual review by 90+ days

---

## 10. MODULE IDENTITY & METADATA (MCHS-META)

### 10.1 Core Metadata Header

**Every module** (all tiers) must include:

```python
"""
Payment Retry Logic Module

CGRF Metadata:
{
  "_report_id": "SRS-PAYMENT-RETRY-20260125-001-V3.0",
  "_document_schema": "CGRF-v3.0",
  "_tier": 2,
  "_module_version": "1.2.3",
  "_module_name": "payment_retry",
  "_execution_role": "BACKEND_SERVICE",
  "_created": "2026-01-15",
  "_last_updated": "2026-01-25",
  "_author": "payments-team@example.com",
  "_maturity_score": 0.87,
  "_audit_passed": true,
  "_verification_score": 0.92
}

Description:
Implements exponential backoff retry logic for failed payment transactions.
Integrates with Stripe API and logs all attempts to audit trail.

Dependencies:
- stripe-python >=5.0.0
- redis >=4.5.0 (rate limiting)
- logging_framework >=2.1.0

License: Proprietary
Copyright: Citadel AI, Inc. 2026
"""

__version__ = "1.2.3"
__tier__ = 2
__module_name__ = "payment_retry"
```

### 10.2 Execution Roles (ENUMSpeak)

```python
# Standard execution roles
EXECUTION_ROLES = [
    "PROTOTYPE",           # Tier 0: Experimental
    "BACKEND_SERVICE",     # API, workers, processors
    "FRONTEND_SERVICE",    # Web UI, mobile apps
    "DATA_PIPELINE",       # ETL, batch jobs
    "INTEGRATION",         # External API clients
    "INFRASTRUCTURE",      # Deployment, monitoring
    "GOVERNANCE",          # Policy gates, auditors
    "AGENT",              # AI agents (AIS integration)
]
```

---

## 11. FUNCTIONAL REQUIREMENTS (FR)

### 11.1 FR Format (Tier 1+)

```yaml
# FR-{MODULE}-{NUMBER}
# Example: FR-PAYMENT-001

functional_requirements:
  - id: "FR-PAYMENT-001"
    tier_required: 1
    title: "Exponential Backoff Retry"
    description: |
      When a payment fails due to timeout, retry with exponential backoff.
      1st retry: 1 second delay
      2nd retry: 2 seconds delay
      3rd retry: 4 seconds delay
      Max retries: 3 (configurable via PAYMENT_MAX_RETRIES)
    
    acceptance_criteria:
      - "System retries exactly 3 times on timeout"
      - "Delays follow exponential backoff (1s, 2s, 4s)"
      - "After 3 failures, raises PaymentTimeoutError"
      - "All retry attempts logged to audit trail"
    
    test_cases:
      - id: "TEST-PAYMENT-001-A"
        description: "Timeout on attempt 1, succeed on attempt 2"
        status: "PASSING"
      - id: "TEST-PAYMENT-001-B"
        description: "Timeout all 3 attempts"
        status: "PASSING"
      - id: "TEST-PAYMENT-001-C"
        description: "Verify 1s, 2s, 4s delays"
        status: "PASSING"
    
    implementation_status: "COMPLETE"
    verification_status: "VERIFIED"
```

### 11.2 FR Testability Requirements

All FRs must be:
1. **Measurable**: Acceptance criteria = pass/fail checks
2. **Testable**: Test cases exist and pass
3. **Traceable**: Test coverage ≥80% (Tier 2+)

---

## 12. PRODUCTION RULES (PRD)

### 12.1 PRD Format (Tier 2+)

```yaml
# PRD-{MODULE}-{NUMBER}
# Example: PRD-PAYMENT-001

production_rules:
  - id: "PRD-PAYMENT-001"
    tier_required: 2
    title: "Hub Readiness Gate"
    category: "AVAILABILITY"
    description: |
      Before processing any payment, verify that the Hub service
      is online and responsive. If Hub is offline, reject the
      payment with HubNotReadyError.
    
    enforcement: "BLOCKING"  # BLOCKING | THROTTLING | LOGGING
    
    implementation:
      code_snippet: |
        async def process_payment(transaction):
            # Hub readiness check (MANDATORY)
            if not await hub.is_ready():
                logger.error("Hub offline, rejecting payment",
                           extra={"txn_id": transaction.id})
                raise HubNotReadyError("Hub service unavailable")
            
            # Proceed with payment logic...
      
      test_coverage: "100%"
      test_file: "tests/test_hub_readiness.py"
    
    monitoring:
      metric: "hub_readiness_check_failures"
      alert_threshold: ">10 failures in 5 minutes"
      pagerduty_integration: true
    
    verification:
      claimed: true
      verified: true
      last_verification: "2026-01-25"
      verification_method: "Automated integration test"
```

### 12.2 PRD Categories

```yaml
PRD_CATEGORIES:
  AVAILABILITY:
    - Hub readiness checks
    - Service health checks
    - Circuit breaker patterns
  
  PERFORMANCE:
    - Rate limiting
    - Timeout enforcement
    - Resource quotas
  
  SECURITY:
    - Input validation
    - Authentication gates
    - Encryption enforcement
  
  COMPLIANCE:
    - Audit logging
    - Data retention
    - PII handling
  
  RELIABILITY:
    - Retry logic
    - Graceful degradation
    - Fallback strategies
```

---

## 13. VERSIONING & AUDIT LOGS (VAL)

### 13.1 SemVer Enforcement

```yaml
# Versioning scheme: MAJOR.MINOR.PATCH

version_history:
  - version: "1.2.3"
    date: "2026-01-25"
    type: "PATCH"  # MAJOR | MINOR | PATCH
    changes:
      - "Fixed timeout handling edge case"
      - "Improved error logging"
    breaking_changes: false
    git_commit: "a1b2c3d4e5f6"
    release_notes_url: "https://github.com/org/repo/releases/tag/v1.2.3"
  
  - version: "1.2.0"
    date: "2026-01-15"
    type: "MINOR"
    changes:
      - "Added exponential backoff retry"
      - "Made retry count configurable"
    breaking_changes: false
    git_commit: "b2c3d4e5f6a7"
  
  - version: "1.0.0"
    date: "2025-12-01"
    type: "MAJOR"
    changes:
      - "Initial production release"
    breaking_changes: true
    breaking_change_details:
      - "Changed function signature: process_payment(txn, retries=3)"
    migration_guide_url: "https://docs.example.com/migrations/v1.0.0"
```

### 13.2 Cryptographic Audit Chain

```python
# Hash-chained audit log (immutable)
audit_log = [
    {
        "event_id": "EVT-001",
        "event_type": "MODULE_CREATED",
        "timestamp": "2025-12-01T10:00:00Z",
        "actor": "developer@example.com",
        "hash": "sha256:abc123...",
        "prev_hash": None  # First event
    },
    {
        "event_id": "EVT-002",
        "event_type": "FR_ADDED",
        "timestamp": "2025-12-05T14:30:00Z",
        "actor": "developer@example.com",
        "details": {"fr_id": "FR-PAYMENT-001"},
        "hash": "sha256:def456...",
        "prev_hash": "sha256:abc123..."  # Links to EVT-001
    },
    {
        "event_id": "EVT-003",
        "event_type": "TIER_PROMOTED",
        "timestamp": "2026-01-15T09:00:00Z",
        "actor": "engineering-lead@example.com",
        "details": {"from_tier": 1, "to_tier": 2},
        "hash": "sha256:ghi789...",
        "prev_hash": "sha256:def456..."  # Links to EVT-002
    }
]

# Verification
def verify_audit_chain(log):
    for i in range(1, len(log)):
        expected_prev = log[i-1]["hash"]
        actual_prev = log[i]["prev_hash"]
        if expected_prev != actual_prev:
            raise AuditChainBrokenError(f"Event {i} broken chain")
    return True
```

---

## 14. CLAIMED VS. VERIFIED TRACKING (VVCM)

### 14.1 Purpose
Prevent **vaporware syndrome** by distinguishing:
- **Claimed**: What developers say is done
- **Verified**: What tests prove works

### 14.2 Calculation

```python
# Automatic calculation by cgrf-cli

def calculate_verification_score(module_path, srs_path):
    # Load SRS
    srs = load_srs(srs_path)
    
    # Count claimed FRs
    claimed_frs = len(srs["functional_requirements"])
    
    # Count FRs with passing tests
    verified_frs = sum(
        1 for fr in srs["functional_requirements"]
        if all(tc["status"] == "PASSING" for tc in fr["test_cases"])
    )
    
    # Calculate scores
    claimed = claimed_frs / claimed_frs  # Always 1.0
    verified = verified_frs / claimed_frs
    delta = claimed - verified
    
    return {
        "claimed_completion": claimed,
        "verified_completion": verified,
        "delta": delta,
        "delta_threshold": get_tier_threshold(srs["_tier"]),
        "delta_within_threshold": delta <= get_tier_threshold(srs["_tier"])
    }

def get_tier_threshold(tier):
    return {
        0: 1.0,   # Tier 0: No limit (experimental)
        1: 0.40,  # Tier 1: 40% gap OK
        2: 0.20,  # Tier 2: 20% gap max
        3: 0.10   # Tier 3: 10% gap max
    }[tier]
```

### 14.3 Dashboard Visualization

```
Module: payment_retry.py (Tier 2)

Claimed Completion:  [████████████████████] 100%
Verified Completion: [███████████████░░░░░]  85%
                                    ↑
                                   Gap: 15% (within 20% threshold ✅)

Blockers to 100% Verified:
1. FR-PAYMENT-003: Missing edge case test for network interruption
2. FR-PAYMENT-005: Integration test fails intermittently (flaky)
3. PRD-PAYMENT-002: Rate limiter not tested under high load

Next Actions:
- Add network interruption simulation test
- Fix flaky integration test (mock time.sleep)
- Run load test (1000 req/s) on rate limiter
```

---

## 15. REFLEX SYSTEM INTEGRATION

### 15.1 What is REFLEX?

**REFLEX (Rapid Error Feedback & Learning eXecution)** is the **self-healing nervous system** that detects anomalies, auto-generates fixes, and learns from failures.

```
┌──────────────────────────────────────────────────────────┐
│                    REFLEX ARCHITECTURE                    │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │ 1. OBSERVE (Monitoring Layer)                    │   │
│  │    - CI/CD test failures                         │   │
│  │    - Production errors (logs, metrics)           │   │
│  │    - Drift detection (config, behavior)          │   │
│  │    - SLA violations                              │   │
│  └────────────────────┬─────────────────────────────┘   │
│                       │                                  │
│  ┌────────────────────▼─────────────────────────────┐   │
│  │ 2. DIAGNOSE (Root Cause Analysis)                │   │
│  │    - Stack trace parsing                         │   │
│  │    - Regression detection (git bisect)           │   │
│  │    - Pattern matching (similar incidents)        │   │
│  │    - LLM-powered hypothesis generation           │   │
│  └────────────────────┬─────────────────────────────┘   │
│                       │                                  │
│  ┌────────────────────▼─────────────────────────────┐   │
│  │ 3. RESPOND (Auto-Fix Generation)                 │   │
│  │    - Code patch generation (via Claude)          │   │
│  │    - Config rollback (if drift detected)         │   │
│  │    - Circuit breaker activation                  │   │
│  │    - Graceful degradation triggers               │   │
│  └────────────────────┬─────────────────────────────┘   │
│                       │                                  │
│  ┌────────────────────▼─────────────────────────────┐   │
│  │ 4. VERIFY (Validation Loop)                      │   │
│  │    - Run tests on proposed fix                   │   │
│  │    - AGS policy gate approval                    │   │
│  │    - Canary deployment (1% → 10% → 100%)         │   │
│  │    - Rollback if metrics degrade                 │   │
│  └────────────────────┬─────────────────────────────┘   │
│                       │                                  │
│  ┌────────────────────▼─────────────────────────────┐   │
│  │ 5. LEARN (Knowledge Accumulation)                │   │
│  │    - Pattern library update (AIS College)        │   │
│  │    - Runbook generation                          │   │
│  │    - Post-mortem creation                        │   │
│  │    - CGRF SRS auto-update                        │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### 15.2 CGRF ↔ REFLEX Integration Points

#### Integration Point 1: Drift Detection

```yaml
# CGRF SRS Header
drift_monitoring:
  enabled: true
  check_frequency: "every 6 hours"
  drift_types:
    - CONFIG_DRIFT: "Compare runtime config vs. documented defaults"
    - BEHAVIOR_DRIFT: "Compare actual vs. expected outputs"
    - DEPENDENCY_DRIFT: "Detect version mismatches"
  
  alert_on_drift: true
  auto_fix_on_drift: true  # REFLEX auto-generates fix PR
```

**REFLEX Action:**
```python
# Detected: PAYMENT_MAX_RETRIES env var changed from 3 → 5 in prod
# Expected (per SRS): 3
# Drift: +67%

REFLEX.observe("CONFIG_DRIFT: PAYMENT_MAX_RETRIES")
REFLEX.diagnose()
  → Root cause: Manual change by ops team during incident
REFLEX.respond()
  → Generate PR to update SRS: PAYMENT_MAX_RETRIES default → 5
  → Create incident postmortem
REFLEX.verify()
  → AGS policy gate: ALLOW (non-breaking change)
REFLEX.learn()
  → Add to runbook: "Incident 2026-01-25: Increased retries to 5"
```

#### Integration Point 2: Regression Auto-Fix

```yaml
# CGRF SRS Header
regression_handling:
  enabled: true
  auto_fix_attempts: 3
  fallback_strategy: "ROLLBACK"
  
  regression_detection:
    - test_failure: "Any previously passing test now fails"
    - performance_degradation: "Response time >2x baseline"
    - error_rate_spike: ">5% error rate increase"
```

**REFLEX Action:**
```
CI detected: test_payment_retry_timeout() now fails (was passing)
Git bisect: Failure introduced in commit a1b2c3d

REFLEX.observe("REGRESSION: test_payment_retry_timeout")
REFLEX.diagnose()
  → LLM analysis of commit diff
  → Hypothesis: "Removed sleep() call, breaking timing assumption"
REFLEX.respond()
  → Generate fix: Add asyncio.sleep() back
  → Open PR: "Fix regression in payment timeout test"
REFLEX.verify()
  → Run test suite on fix branch: ✅ PASSING
  → AGS policy gate: ALLOW (test coverage maintained)
  → Auto-merge fix
REFLEX.learn()
  → Update SRS: "Known issue: test_payment_retry_timeout flaky"
  → Add to pattern library: "Timeout test pattern"
```

#### Integration Point 3: SRS Auto-Update

```yaml
# When REFLEX fixes an issue, it auto-updates CGRF SRS

reflex_srs_sync:
  enabled: true
  update_triggers:
    - "Fix deployed to production"
    - "Incident resolved"
    - "New pattern learned"
  
  update_sections:
    - "version_history"  # Increment version
    - "known_issues"     # Mark as resolved
    - "claimed_vs_verified"  # Recalculate delta
```

---

## 16. AGS INTEGRATION (AGENT GOVERNANCE)

### 16.1 What is AGS?

**AGS (Agent Governance System)** is the **constitutional judiciary** that validates all mutations through a 4-stage policy pipeline.

```
┌───────────────────────────────────────────────────────┐
│        AGS CONSTITUTIONAL COMPILER (4 Stages)          │
├───────────────────────────────────────────────────────┤
│                                                        │
│  ┌──────────────────────────────────────────────┐     │
│  │ S00: GENERATOR (Intent Normalization)        │     │
│  │ ├─ Parse natural language request            │     │
│  │ ├─ Convert to structured SapientPacket       │     │
│  │ ├─ Assign intent hash (SHA256)               │     │
│  │ └─ Output: {action, target, agent, context}  │     │
│  └────────────────┬─────────────────────────────┘     │
│                   │                                    │
│  ┌────────────────▼─────────────────────────────┐     │
│  │ S01: DEFINER (Schema Validation)             │     │
│  │ ├─ Validate against CGRF tier requirements   │     │
│  │ ├─ Check CAPS grade (agent capability)       │     │
│  │ ├─ Verify metadata completeness              │     │
│  │ └─ Output: Compiled packet (JSON sealed)     │     │
│  └────────────────┬─────────────────────────────┘     │
│                   │                                    │
│  ┌────────────────▼─────────────────────────────┐     │
│  │ S02: FATE (Risk Assessment)                  │     │
│  │ ├─ Check tier-specific thresholds            │     │
│  │ ├─ Verify XP/TP budget (AIS economic engine) │     │
│  │ ├─ Assess risk class (LOW/MED/HIGH/CRITICAL) │     │
│  │ ├─ Check trust score (agent reputation)      │     │
│  │ └─ Verdict: ALLOW | REVIEW | DENY            │     │
│  └────────────────┬─────────────────────────────┘     │
│                   │                                    │
│  ┌────────────────▼─────────────────────────────┐     │
│  │ S03: ARCHIVIST (Immutable Recording)         │     │
│  │ ├─ Create cryptographic hash (prev chained)  │     │
│  │ ├─ Write to ledger (Supabase guardian_logs)  │     │
│  │ ├─ Record FATE verdict                       │     │
│  │ ├─ Emit event (NATS/Kafka)                   │     │
│  │ └─ Return: ledger_id, provenance_url         │     │
│  └──────────────────────────────────────────────┘     │
│                                                        │
└───────────────────────────────────────────────────────┘
```

### 16.2 CGRF ↔ AGS Integration Points

#### Integration Point 1: Tier-Based Policy Gates

```yaml
# AGS policy gates enforce CGRF tier requirements

policy_gates:
  - name: "tier_0_allow_all"
    trigger: "module._tier == 0"
    rules:
      - condition: "true"  # Experimental = no gates
        verdict: "ALLOW"
        reason: "Tier 0 exempted from governance"
  
  - name: "tier_1_basic_checks"
    trigger: "module._tier == 1"
    rules:
      - condition: "module.has_tests and module.coverage >= 0.50"
        verdict: "ALLOW"
      - condition: "module.coverage < 0.50"
        verdict: "DENY"
        reason: "Tier 1 requires 50% test coverage"
  
  - name: "tier_2_production_gates"
    trigger: "module._tier == 2"
    rules:
      - condition: |
          module.has_tests and
          module.coverage >= 0.80 and
          module.claimed_vs_verified_delta <= 0.20 and
          module.has_prds
        verdict: "ALLOW"
      - condition: "module.claimed_vs_verified_delta > 0.20"
        verdict: "DENY"
        reason: "Tier 2: Claimed vs. Verified gap too large (max 20%)"
  
  - name: "tier_3_mission_critical_gates"
    trigger: "module._tier == 3"
    rules:
      - condition: |
          module.coverage >= 0.90 and
          module.claimed_vs_verified_delta <= 0.10 and
          module.external_audit_passed and
          module.has_incident_response_plan
        verdict: "ALLOW"
      - condition: "not module.external_audit_passed"
        verdict: "DENY"
        reason: "Tier 3 requires external audit approval"
```

#### Integration Point 2: CAPS Grade Enforcement

```yaml
# CAPS (Capability Assessment & Permission System)
# Agents earn grades based on performance

caps_grades:
  S: # Sovereign (Tier 5 agents)
    - can_modify_tier_3_modules: true
    - can_propose_constitutional_changes: true
    - requires_human_approval: false
  
  A: # Tier 4 agents
    - can_modify_tier_2_modules: true
    - can_mentor_junior_agents: true
    - requires_human_approval: false
  
  B: # Tier 3 agents
    - can_modify_tier_1_modules: true
    - can_run_production_deployments: false
    - requires_human_approval: true  # For Tier 2+
  
  C: # Tier 2 agents
    - can_modify_tier_0_modules: true
    - can_propose_fixes: true
    - requires_human_approval: true
  
  D: # Tier 1 agents (Novice)
    - can_modify_tier_0_modules: false
    - can_suggest_fixes: true
    - requires_human_approval: true
```

**AGS Enforcement:**
```python
# Agent "gm_python_junior" (CAPS grade: C) tries to modify Tier 2 module

mutation = {
    "agent_id": "gm_python_junior",
    "action": "UPDATE_MODULE",
    "target": {"module": "payment_retry.py", "tier": 2}
}

# S01 DEFINER validates CAPS
agent_caps = get_agent_caps("gm_python_junior")  # Returns: C
module_tier = mutation["target"]["tier"]  # 2

if agent_caps < tier_to_caps_requirement(module_tier):
    # Tier 2 requires CAPS B+
    return {
        "verdict": "DENY",
        "reason": "Agent CAPS grade C insufficient for Tier 2 (requires B+)"
    }
```

#### Integration Point 3: Economic Budget Checks (AIS Integration)

```yaml
# AGS S02 (FATE) checks XP/TP budgets from AIS

economic_gates:
  - name: "xp_budget_check"
    condition: "mutation.cost_xp <= agent.xp_available"
    verdict: "ALLOW"
    denial_reason: "Insufficient XP (need {cost_xp}, have {xp_available})"
  
  - name: "tp_budget_check"
    condition: "mutation.cost_tp <= ecosystem.tp_pool"
    verdict: "ALLOW"
    denial_reason: "Ecosystem TP pool depleted"
  
  - name: "trust_score_check"
    condition: "agent.trust_score >= 0.7"  # Tier 2+ requires trust
    verdict: "ALLOW"
    denial_reason: "Agent trust score too low ({trust_score} < 0.7)"
```

---

## 17. AIS INTEGRATION (INTELLIGENCE LAYER)

### 17.1 What is AIS?

**AIS (Autonomous Intelligence System)** is the **economic engine + knowledge system** that drives agent evolution through XP/TP tokens and the College knowledge base.

```
┌──────────────────────────────────────────────────────┐
│          AIS DUAL-TOKEN ECONOMY + COLLEGE             │
├──────────────────────────────────────────────────────┤
│                                                       │
│  ┌─────────────────────────────────────────────┐     │
│  │ XP (Experience Points)                      │     │
│  │ ├─ Non-transferable                         │     │
│  │ ├─ Earned: Task completion × quality        │     │
│  │ ├─ Purpose: Tier progression (unlock caps)  │     │
│  │ └─ Formula: base_xp × complexity × trust    │     │
│  └─────────────────────────────────────────────┘     │
│                                                       │
│  ┌─────────────────────────────────────────────┐     │
│  │ TP (Treasury Points)                        │     │
│  │ ├─ Transferable (agent capital)             │     │
│  │ ├─ Earned: Critical tasks, mentoring        │     │
│  │ ├─ Purpose: Bid on high-value tasks         │     │
│  │ └─ Taxation: 5% weekly (prevent hoarding)   │     │
│  └─────────────────────────────────────────────┘     │
│                                                       │
│  ┌─────────────────────────────────────────────┐     │
│  │ College System (Knowledge Accumulation)     │     │
│  │ ├─ 50+ domains (Python, DevOps, Security)   │     │
│  │ ├─ Pattern library (FAISS-indexed)          │     │
│  │ ├─ Mentorship network (senior → junior)     │     │
│  │ └─ 5-tier progression per domain            │     │
│  └─────────────────────────────────────────────┘     │
│                                                       │
└──────────────────────────────────────────────────────┘
```

### 17.2 CGRF ↔ AIS Integration Points

#### Integration Point 1: XP Rewards for SRS Quality

```yaml
# Agents earn XP for maintaining high-quality SRS documentation

xp_rewards:
  srs_created:
    base_xp: 50
    multipliers:
      tier_0: 1.0
      tier_1: 1.5
      tier_2: 2.5
      tier_3: 5.0
    quality_bonus:
      complete_metadata: +10
      all_frs_testable: +20
      claimed_verified_delta_0: +30
  
  srs_updated:
    base_xp: 20
    multipliers:
      minor_update: 1.0
      major_refactor: 2.0
      tier_promotion: 3.0
  
  audit_passed:
    base_xp: 100
    multipliers:
      tier_2_audit: 1.0
      tier_3_external_audit: 5.0
```

**Example:**
```python
# Agent "gm_payments_master" creates Tier 2 SRS for payment_retry.py

xp_earned = (
    50  # base_xp for srs_created
    × 2.5  # tier_2 multiplier
    + 10  # complete_metadata bonus
    + 20  # all_frs_testable bonus
    + 30  # claimed_verified_delta_0 bonus (delta = 0.08)
) = 185 XP

# Agent also earns TP (critical task)
tp_earned = 50  # Critical payment infrastructure

# Trust score increases
trust_score_new = min(0.95, trust_score_old + 0.01) = 0.85
```

#### Integration Point 2: College Pattern Library

```yaml
# AIS College stores CGRF-compliant patterns

college_patterns:
  - pattern_id: "PATTERN-CGRF-001"
    name: "Tier 2 SRS Template (Payment Service)"
    domain: "backend_services"
    tier: 2
    description: "Comprehensive SRS for payment processing services"
    template_url: "https://college.ais/patterns/tier2-payment-srs"
    success_rate: 0.95
    times_used: 127
    prerequisites:
      - "CGRF v3.0 training"
      - "Payment domain knowledge (Level 3+)"
    difficulty: 3/5
    estimated_time: "2-3 hours"
    
    metadata_snippet: |
      {
        "_tier": 2,
        "_execution_role": "BACKEND_SERVICE",
        "_module_name": "{{MODULE_NAME}}",
        "production_rules": [
          {"id": "PRD-{{MODULE}}-001", "title": "Hub Readiness"},
          {"id": "PRD-{{MODULE}}-002", "title": "Rate Limiting"},
          {"id": "PRD-{{MODULE}}-003", "title": "Audit Logging"}
        ]
      }
```

**Agent Usage:**
```python
# Junior agent needs to create SRS for new payment module

agent.query_college("Tier 2 SRS template for payment service")
  → Returns: PATTERN-CGRF-001
  
agent.download_pattern("PATTERN-CGRF-001")
  → Downloads template with {{PLACEHOLDERS}}
  
agent.fill_template(module_name="refund_processor")
  → Generates complete SRS in 10 minutes (vs. 2 hours manual)
  
agent.submit_for_review()
  → AGS validates: ✅ ALLOW (meets Tier 2 requirements)
  
agent.earn_xp(base=50, quality_bonus=0)  # Used template, no bonus
```

#### Integration Point 3: Tier Progression & Capability Unlocks

```yaml
# Agents unlock capabilities as they earn XP in CGRF domains

agent_progression:
  tier_1_novice:
    xp_range: [0, 100]
    capabilities:
      - "Create Tier 0 SRS (experimental)"
      - "Read Tier 1-3 SRS (documentation)"
      - "Propose Tier 0 updates"
    caps_grade: "D"
  
  tier_2_journeyman:
    xp_range: [101, 500]
    capabilities:
      - "Create Tier 1 SRS (development)"
      - "Update Tier 0-1 SRS"
      - "Mentor Tier 1 agents"
    caps_grade: "C"
  
  tier_3_master:
    xp_range: [501, 2000]
    capabilities:
      - "Create Tier 2 SRS (production)"
      - "Update Tier 0-2 SRS"
      - "Approve Tier 1 PRs"
      - "Conduct internal audits"
    caps_grade: "B"
  
  tier_4_grandmaster:
    xp_range: [2001, 10000]
    capabilities:
      - "Create Tier 3 SRS (mission-critical)"
      - "Update any SRS"
      - "Approve Tier 2-3 PRs"
      - "Design new CGRF patterns"
    caps_grade: "A"
  
  tier_5_sovereign:
    xp_range: [10000, ∞]
    capabilities:
      - "Modify CGRF framework itself"
      - "Propose constitutional changes"
      - "Override policy gates (with audit)"
    caps_grade: "S"
```

---

## 18. POLICY GATES & CONSTITUTIONAL COMPILER

### 18.1 Policy Gate YAML Format

```yaml
# policies/cgrf_tier_gates.yaml

policy_schema_version: "1.0"
policy_name: "CGRF Tier Enforcement"
policy_description: "Validates module changes against CGRF tier requirements"

gates:
  - name: "tier_0_unrestricted"
    priority: 1
    trigger: "mutation.target.tier == 0"
    rules:
      - condition: "true"  # No restrictions
        verdict: "ALLOW"
        reason: "Tier 0 experimental, no gates"
        cost_xp: 0
        cost_tp: 0
  
  - name: "tier_1_test_coverage_gate"
    priority: 2
    trigger: "mutation.target.tier == 1"
    rules:
      - condition: |
          mutation.target.has_tests == true and
          mutation.target.test_coverage >= 0.50 and
          mutation.agent.caps_grade in ['C', 'B', 'A', 'S']
        verdict: "ALLOW"
        reason: "Tier 1 requirements met: tests + 50% coverage + CAPS C+"
        cost_xp: 20
        cost_tp: 0
      
      - condition: "mutation.target.test_coverage < 0.50"
        verdict: "DENY"
        reason: |
          Tier 1 requires 50% test coverage.
          Current: {mutation.target.test_coverage * 100}%
          Add {(0.50 - mutation.target.test_coverage) * mutation.target.total_lines} more tested lines.
  
  - name: "tier_2_production_gate"
    priority: 3
    trigger: "mutation.target.tier == 2"
    rules:
      - condition: |
          mutation.target.test_coverage >= 0.80 and
          mutation.target.has_prds == true and
          mutation.target.claimed_vs_verified_delta <= 0.20 and
          mutation.target.no_critical_flaws == true and
          mutation.agent.caps_grade in ['B', 'A', 'S'] and
          mutation.agent.trust_score >= 0.70
        verdict: "ALLOW"
        reason: "Tier 2 production gate passed"
        cost_xp: 50
        cost_tp: 10
      
      - condition: "mutation.target.claimed_vs_verified_delta > 0.20"
        verdict: "REVIEW"
        reason: |
          Claimed vs. Verified gap too large: {mutation.target.claimed_vs_verified_delta * 100}%
          Tier 2 allows max 20%. Requires human approval.
        escalation: "engineering-lead@example.com"
  
  - name: "tier_3_mission_critical_gate"
    priority: 4
    trigger: "mutation.target.tier == 3"
    rules:
      - condition: |
          mutation.target.test_coverage >= 0.90 and
          mutation.target.claimed_vs_verified_delta <= 0.10 and
          mutation.target.external_audit_passed == true and
          mutation.target.has_incident_response_plan == true and
          mutation.agent.caps_grade in ['A', 'S'] and
          mutation.agent.trust_score >= 0.85
        verdict: "ALLOW"
        reason: "Tier 3 mission-critical gate passed"
        cost_xp: 100
        cost_tp: 50
      
      - condition: "mutation.target.external_audit_passed == false"
        verdict: "DENY"
        reason: "Tier 3 requires external audit approval (SOC2/ISO 27001)"
```

### 18.2 Constitutional Compiler Workflow

```python
# AGS Constitutional Compiler processes all mutations

class ConstitutionalCompiler:
    def __init__(self):
        self.s00_generator = GeneratorStage()
        self.s01_definer = DefinerStage()
        self.s02_fate = FateStage()
        self.s03_archivist = ArchivistStage()
    
    async def process(self, mutation_request):
        # S00: Normalize intent
        packet = await self.s00_generator.parse(mutation_request)
        # Output: SapientPacket with standardized format
        
        # S01: Validate schema
        validated = await self.s01_definer.validate(packet)
        # Checks: CGRF tier requirements, CAPS grades, metadata
        
        # S02: Assess risk & approve
        verdict = await self.s02_fate.evaluate(validated)
        # Returns: ALLOW | REVIEW | DENY
        
        # S03: Record immutably
        ledger_id = await self.s03_archivist.record(verdict)
        # Writes to guardian_logs with hash chain
        
        return {
            "verdict": verdict["verdict"],
            "reason": verdict["reason"],
            "ledger_id": ledger_id,
            "cost_xp": verdict["cost_xp"],
            "cost_tp": verdict["cost_tp"]
        }
```

**Example Execution:**
```
Mutation Request:
└─ Agent: gm_payments_master (CAPS: B, Trust: 0.85, XP: 1250, TP: 75)
└─ Action: UPDATE_MODULE
└─ Target: payment_retry.py (Tier 2)
└─ Changes: Add PRD-PAYMENT-004 (circuit breaker)

┌──────────────────────────────────────────────────┐
│ S00 GENERATOR                                    │
├──────────────────────────────────────────────────┤
│ ✅ Parsed intent: Add production rule            │
│ ✅ Created SapientPacket                         │
│ ✅ Hash: sha256:abc123...                        │
└──────────────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────────────┐
│ S01 DEFINER                                      │
├──────────────────────────────────────────────────┤
│ ✅ Tier 2 module validated                       │
│ ✅ Agent CAPS B meets requirement (B+)           │
│ ✅ Metadata complete                             │
│ ✅ PRD schema valid                              │
└──────────────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────────────┐
│ S02 FATE                                         │
├──────────────────────────────────────────────────┤
│ Policy Gate: tier_2_production_gate              │
│                                                  │
│ ✅ test_coverage: 87% (≥80% ✓)                   │
│ ✅ has_prds: true ✓                              │
│ ✅ claimed_verified_delta: 0.13 (≤0.20 ✓)        │
│ ✅ no_critical_flaws: true ✓                     │
│ ✅ agent.caps_grade: B (in [B,A,S] ✓)            │
│ ✅ agent.trust_score: 0.85 (≥0.70 ✓)             │
│                                                  │
│ Verdict: ALLOW                                   │
│ Cost: 50 XP, 10 TP                               │
└──────────────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────────────┐
│ S03 ARCHIVIST                                    │
├──────────────────────────────────────────────────┤
│ ✅ Recorded to guardian_logs                     │
│ ✅ Ledger ID: GL-20260125-001234                 │
│ ✅ Hash chain: sha256:def456... → sha256:abc123  │
│ ✅ Event emitted: MUTATION_ALLOWED               │
└──────────────────────────────────────────────────┘

RESULT:
✅ Mutation ALLOWED
✅ payment_retry.py updated with PRD-PAYMENT-004
✅ Agent earned 50 XP, paid 10 TP
✅ Trust score +0.01 → 0.86
```

---

## 19. CGRF CLI VALIDATOR

### 19.1 Installation

```bash
# PyPI
$ pip install cgrf-cli

# Verify
$ cgrf --version
cgrf-cli version 3.0.0

# Initialize workspace
$ cgrf init --workspace .
✅ Created .cgrf/
✅ Created .cgrf/config.yaml
✅ Added .cgrf/ to .gitignore
```

### 19.2 Commands

#### Validate Module + SRS

```bash
$ cgrf validate \
    --module src/payment_retry.py \
    --srs docs/SRS-PAYMENT-RETRY.md \
    --tier 2

Validating payment_retry.py against Tier 2 requirements...

✅ Metadata: PASS
   ├─ _report_id: SRS-PAYMENT-RETRY-20260125-001-V3.0
   ├─ _tier: 2
   ├─ _module_version: 1.2.3
   └─ _execution_role: BACKEND_SERVICE

✅ Functional Requirements: PASS
   ├─ FR-PAYMENT-001: Exponential backoff ✅ (3/3 tests passing)
   ├─ FR-PAYMENT-002: Configurable retries ✅ (2/2 tests passing)
   └─ FR-PAYMENT-003: Audit logging ✅ (4/4 tests passing)

✅ Production Rules: PASS
   ├─ PRD-PAYMENT-001: Hub readiness ✅ (100% coverage)
   ├─ PRD-PAYMENT-002: Rate limiting ✅ (95% coverage)
   └─ PRD-PAYMENT-003: Audit logging ✅ (100% coverage)

✅ Test Coverage: PASS (87% ≥ 80% threshold)

✅ Claimed vs. Verified: PASS
   ├─ Claimed: 100%
   ├─ Verified: 92%
   ├─ Delta: 8% (≤ 20% threshold)
   └─ Blockers: 1 (missing timeout simulation test)

Overall: ✅ TIER 2 COMPLIANT

Maturity Score: 0.87/1.00
  ├─ Metadata completeness: 1.00 (25% weight)
  ├─ Verification score: 0.92 (30% weight)
  ├─ Dependency stability: 0.85 (20% weight)
  ├─ Test coverage: 0.87 (15% weight)
  └─ Documentation freshness: 0.90 (10% weight)

Next Steps:
  - Add timeout simulation test to reach 100% verified
  - Consider tier 3 promotion (need external audit)
```

#### Auto-Scaffold Missing Sections

```bash
$ cgrf scaffold \
    --module src/refund_processor.py \
    --tier 2

Analyzing refund_processor.py...

✅ Detected 8 functions
✅ Extracted 12 dependencies
✅ Found 5 TODO comments

Generating SRS-REFUND-PROCESSOR-20260125-001-DRAFT.md...

✅ Metadata header (auto-filled)
✅ Module identity (extracted from __version__, __author__)
✅ Functional requirements (8 FRs extracted from docstrings)
   ⚠️  FR-REFUND-003: Acceptance criteria missing (manual input needed)
⬜ Production rules (TODO: define PRDs)
✅ Dependencies (12 listed: stripe, redis, logging_framework, ...)
⚠️  Claimed vs. Verified (set to 0.0, run tests first)
✅ Version history (1 entry from git log)

Draft saved: docs/SRS-REFUND-PROCESSOR-20260125-001-DRAFT.md

Next:
1. Review draft SRS
2. Fill TODOs (search for "TODO:")
3. Run tests: pytest tests/test_refund_processor.py
4. Run: cgrf validate --module src/refund_processor.py --srs docs/SRS-REFUND-PROCESSOR-20260125-001-DRAFT.md
```

#### Tier Promotion Check

```bash
$ cgrf tier-check \
    --module src/payment_retry.py \
    --target-tier 3

Checking payment_retry.py readiness for Tier 3...

Requirements for Tier 3:
┌───────────────────────────────────┬─────────┬────────┐
│ Requirement                       │ Status  │ Value  │
├───────────────────────────────────┼─────────┼────────┤
│ Test coverage ≥90%                │ ❌ FAIL │ 87%    │
│ Claimed vs. Verified delta ≤10%   │ ✅ PASS │ 8%     │
│ External audit passed             │ ❌ FAIL │ No     │
│ Incident response plan            │ ✅ PASS │ Yes    │
│ Zero critical flaws               │ ✅ PASS │ 0      │
│ Agent CAPS grade ≥A               │ ❌ FAIL │ B      │
│ Agent trust score ≥0.85           │ ✅ PASS │ 0.85   │
└───────────────────────────────────┴─────────┴────────┘

Overall: ❌ NOT READY (3 blockers)

Blockers:
1. Test coverage: Add 18 more test assertions to reach 90%
2. External audit: Schedule SOC2 Type II audit with Vanta
3. Agent CAPS: Earn 750 more XP to reach Tier 4 (Grade A)

Estimated Time to Tier 3: 2-3 weeks
```

#### Ecosystem Health Report

```bash
$ cgrf report --workspace .

CGRF Ecosystem Health Report
Generated: 2026-01-25 16:40:00 CST

Coverage Metrics:
├─ Modules with SRS: 18/25 (72%)
├─ Modules at Tier 2+: 12/25 (48%)
├─ Modules at Tier 3: 3/25 (12%)
└─ Orphaned modules (no SRS): 7

Quality Metrics:
├─ Avg verification score: 0.78
├─ Avg claimed-verified delta: 0.15
├─ Critical flaws open: 8
└─ Modules audit-passed: 15/18 (83%)

Velocity Metrics:
├─ Mean time to SRS update: 12 days
├─ Mean time to flaw resolution: 18 days
├─ CGRF compliance trend (QoQ): +12%
└─ Tier promotions last month: 4

Risk Metrics:
├─ Tier 3 modules with regressions: 0 ✅
├─ Tier 2 modules audit-passed: 11/12 (92%)
├─ Overdue annual reviews: 2 ⚠️
└─ Modules with delta >0.30: 3 🔴

Recommendations:
1. Address 7 orphaned modules (create Tier 0 SRS minimum)
2. Fix 2 overdue annual reviews (payment_gateway, user_auth)
3. Reduce critical flaws from 8 → 3 (target: <5)
4. Improve avg verification score from 0.78 → 0.85

Target: 95% coverage, 0.85 avg score, <5 critical flaws
ETA: 6 weeks
```

---

## 20. VS CODE EXTENSION

### 20.1 Features

```typescript
// cgrf-vscode extension capabilities

1. Syntax Highlighting
   - CGRF metadata headers (JSON/YAML in comments)
   - FR/PRD IDs (clickable links)
   - Tier badges (color-coded)

2. Auto-Complete
   - Metadata fields (_report_id, _tier, _module_version, ...)
   - FR/PRD ID formatting (FR-{MODULE}-{NUMBER})
   - Execution roles (BACKEND_SERVICE, FRONTEND_SERVICE, ...)

3. Real-Time Linting
   - ⚠️ "Module version mismatch: __version__ = '0.8.0' but SRS says '0.7.0'"
   - ❌ "Missing required metadata field: _execution_role"
   - ℹ️ "Consider adding PRD for production module"

4. Code Actions
   - "Generate SRS for this module" (right-click)
   - "Update SRS to match code changes" (detects new functions)
   - "Sync version number" (updates SRS when __version__ changes)

5. Dashboard Panel
   - Workspace-wide CGRF compliance score
   - Files missing SRS (highlighted in red)
   - Tier distribution chart
   - Quick actions ("Create Tier 0 SRS for selected file")

6. Git Integration
   - Pre-commit hook: Warn if SRS not updated
   - PR comment: "CGRF compliance check: ✅ PASS (Tier 2)"
```

### 20.2 Installation

```bash
# VS Code Marketplace
$ code --install-extension citadel-ai.cgrf-vscode

# Configuration (.vscode/settings.json)
{
  "cgrf.enabled": true,
  "cgrf.tierMinimum": 1,
  "cgrf.autoScaffold": true,
  "cgrf.lintOnSave": true,
  "cgrf.showDashboard": true
}
```

### 20.3 Screenshot (Dashboard)

```
┌────────────────────────────────────────────────────────┐
│ CGRF Compliance Dashboard                              │
├────────────────────────────────────────────────────────┤
│                                                         │
│ Workspace: /Users/dev/citadel-payments                 │
│ Compliance Score: 78/100 🟡                             │
│                                                         │
│ ┌─────────────────────────────────────────────────┐   │
│ │ Tier Distribution                               │   │
│ │ Tier 0: ████ 4 modules                          │   │
│ │ Tier 1: ████████ 8 modules                      │   │
│ │ Tier 2: ████████ 6 modules                      │   │
│ │ Tier 3: ██ 2 modules                            │   │
│ └─────────────────────────────────────────────────┘   │
│                                                         │
│ Issues:                                                 │
│ ⚠️  7 modules missing SRS                              │
│ 🔴 2 modules exceed delta threshold                     │
│ ℹ️  3 modules ready for tier promotion                 │
│                                                         │
│ Quick Actions:                                          │
│ [Create SRS for highlighted files]                     │
│ [Run full workspace validation]                        │
│ [Generate compliance report]                           │
│                                                         │
└────────────────────────────────────────────────────────┘
```

---

## 21. CI/CD INTEGRATION

### 21.1 GitHub Actions

```yaml
# .github/workflows/cgrf-validation.yml

name: CGRF Compliance Check

on:
  pull_request:
    types: [opened, synchronize]
  push:
    branches: [main]

jobs:
  cgrf-validate:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
        with:
          fetch-depth: 0  # Full git history for delta analysis
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      
      - name: Install cgrf-cli
        run: pip install cgrf-cli==3.0.0
      
      - name: Validate changed modules
        id: validate
        run: |
          # Get changed Python files
          CHANGED_FILES=$(git diff --name-only origin/main...HEAD | grep '\.py$')
          
          # Validate each
          for file in $CHANGED_FILES; do
            echo "Validating $file..."
            cgrf validate --module "$file" --tier-minimum 1
          done
          
          # Generate report
          cgrf report --workspace . --format json > cgrf-report.json
      
      - name: Upload report
        uses: actions/upload-artifact@v3
        with:
          name: cgrf-compliance-report
          path: cgrf-report.json
      
      - name: Comment PR
        if: github.event_name == 'pull_request'
        uses: actions/github-script@v6
        with:
          script: |
            const fs = require('fs');
            const report = JSON.parse(fs.readFileSync('cgrf-report.json'));
            
            const body = `
            ## CGRF Compliance Check
            
            **Overall Score:** ${report.compliance_score}/100
            
            | Metric | Value | Status |
            |--------|-------|--------|
            | Modules with SRS | ${report.coverage.pct}% | ${report.coverage.status} |
            | Avg Verification Score | ${report.avg_verification_score} | ${report.verification_status} |
            | Critical Flaws | ${report.critical_flaws} | ${report.flaws_status} |
            
            ${report.issues.length > 0 ? '### Issues\n' + report.issues.map(i => `- ${i}`).join('\n') : '✅ No issues found'}
            
            [Full Report](${report.report_url})
            `;
            
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: body
            });
      
      - name: Fail if non-compliant
        run: |
          SCORE=$(jq -r '.compliance_score' cgrf-report.json)
          if [ "$SCORE" -lt 70 ]; then
            echo "❌ CGRF compliance score $SCORE < 70 (minimum)"
            exit 1
          fi
```

### 21.2 GitLab CI

```yaml
# .gitlab-ci.yml

cgrf-validation:
  stage: validate
  image: python:3.10
  
  before_script:
    - pip install cgrf-cli==3.0.0
  
  script:
    - cgrf validate --workspace . --tier-minimum 1
    - cgrf report --workspace . --format json > cgrf-report.json
  
  artifacts:
    reports:
      cgrf: cgrf-report.json
    when: always
  
  rules:
    - if: $CI_MERGE_REQUEST_ID
    - if: $CI_COMMIT_BRANCH == "main"
```

---

## 22. DASHBOARD & METRICS

### 22.1 Grafana Dashboard Template

```json
{
  "dashboard": {
    "title": "CGRF Ecosystem Health",
    "panels": [
      {
        "title": "Compliance Score Trend",
        "type": "graph",
        "targets": [
          {
            "query": "avg(cgrf_compliance_score) by (workspace)"
          }
        ]
      },
      {
        "title": "Tier Distribution",
        "type": "pie",
        "targets": [
          {
            "query": "count(cgrf_module_tier) by (tier)"
          }
        ]
      },
      {
        "title": "Claimed vs. Verified Delta",
        "type": "heatmap",
        "targets": [
          {
            "query": "cgrf_claimed_verified_delta by (module, tier)"
          }
        ]
      },
      {
        "title": "Critical Flaws Over Time",
        "type": "graph",
        "targets": [
          {
            "query": "sum(cgrf_critical_flaws_open)"
          }
        ],
        "thresholds": [
          {"value": 5, "color": "yellow"},
          {"value": 10, "color": "red"}
        ]
      }
    ]
  }
}
```

### 22.2 Prometheus Metrics

```python
# cgrf_exporter.py - Exposes CGRF metrics for Prometheus

from prometheus_client import Gauge, Counter, Histogram, start_http_server
import time

# Compliance score (0-100)
compliance_score = Gauge(
    'cgrf_compliance_score',
    'Overall CGRF compliance score',
    ['workspace']
)

# Module count by tier
modules_by_tier = Gauge(
    'cgrf_modules_by_tier',
    'Number of modules at each tier',
    ['workspace', 'tier']
)

# Claimed vs. Verified delta
claimed_verified_delta = Histogram(
    'cgrf_claimed_verified_delta',
    'Distribution of claimed vs. verified deltas',
    ['workspace', 'tier'],
    buckets=[0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]
)

# Critical flaws
critical_flaws = Gauge(
    'cgrf_critical_flaws_open',
    'Number of open critical flaws',
    ['workspace']
)

# SRS update latency
srs_update_latency = Histogram(
    'cgrf_srs_update_days',
    'Days since last SRS update',
    ['workspace', 'module'],
    buckets=[7, 14, 30, 60, 90, 180, 365]
)

# Export metrics
def update_metrics():
    while True:
        # Fetch from cgrf-cli or database
        report = get_cgrf_report()
        
        compliance_score.labels(workspace='payments').set(report['compliance_score'])
        
        for tier, count in report['tier_distribution'].items():
            modules_by_tier.labels(workspace='payments', tier=tier).set(count)
        
        critical_flaws.labels(workspace='payments').set(report['critical_flaws'])
        
        time.sleep(300)  # Update every 5 minutes

if __name__ == '__main__':
    start_http_server(8000)
    update_metrics()
```

---

## 23. EXTERNAL COMPLIANCE MAPPING

### 23.1 SOC2 Type II Mapping

```yaml
# SOC2 Trust Service Criteria → CGRF Mappings

soc2_mappings:
  CC1.4_Governance_Structure:
    cgrf_sections:
      - "Part I: Framework Foundations (Principles)"
      - "Part II: Tiered Governance Model"
      - "Part IV: AGS Integration (Constitutional Compiler)"
    evidence:
      - "CGRF v3.0 framework document"
      - "Policy gate YAML files"
      - "AGS audit logs (guardian_logs table)"
    automation: "cgrf report --soc2-evidence CC1.4"
  
  CC7.2_System_Monitoring:
    cgrf_sections:
      - "Part IV: REFLEX System Integration (Drift Detection)"
      - "Part VI: Ecosystem Health KPIs"
      - "Part V: Dashboard & Metrics (Grafana)"
    evidence:
      - "REFLEX monitoring logs"
      - "Grafana dashboard screenshots"
      - "Prometheus metrics exports"
    automation: "cgrf report --soc2-evidence CC7.2"
  
  CC8.1_Change_Management:
    cgrf_sections:
      - "Part III: Versioning & Audit Logs (VAL)"
      - "Part IV: Policy Gates (Tier-based approval)"
      - "Part III: Claimed vs. Verified Tracking"
    evidence:
      - "Git commit history"
      - "AGS approval decisions (ledger)"
      - "Claimed vs. Verified delta reports"
    automation: "cgrf report --soc2-evidence CC8.1"
```

### 23.2 ISO 27001:2022 Mapping

```yaml
iso_27001_mappings:
  A.5.1_Policies:
    cgrf_sections:
      - "Part III: Functional Requirements (FR)"
      - "Part III: Production Rules (PRD)"
    evidence:
      - "SRS documents with PRDs"
      - "Policy gate enforcement logs"
  
  A.12.4.1_Event_Logging:
    cgrf_sections:
      - "Part III: Versioning & Audit Logs"
      - "Part IV: AGS S03 Archivist (hash-chained logs)"
    evidence:
      - "guardian_logs table exports"
      - "Hash chain verification reports"
  
  A.14.2.8_System_Security_Testing:
    cgrf_sections:
      - "Part II: Tier 2 (80% test coverage requirement)"
      - "Part III: Claimed vs. Verified Tracking"
    evidence:
      - "Test coverage reports (pytest-cov)"
      - "Verification score calculations"
```

### 23.3 GDPR Mapping

```yaml
gdpr_mappings:
  Article_5_Data_Principles:
    cgrf_sections:
      - "Part III: Module Identity & Metadata (data visibility tiers)"
      - "Part IV: AGS Policy Gates (data access control)"
    evidence:
      - "Metadata headers showing data classification"
      - "Policy gate decisions blocking unauthorized access"
  
  Article_30_Records:
    cgrf_sections:
      - "Part III: Versioning & Audit Logs (VAL)"
      - "Part IV: AGS Immutable Ledger"
    evidence:
      - "guardian_logs (7-year retention)"
      - "Cryptographic hash chains"
  
  Article_32_Security:
    cgrf_sections:
      - "Part III: Production Rules (PRD) - encryption enforcement"
      - "Part II: Tier 3 (mission-critical security)"
    evidence:
      - "PRDs documenting encryption requirements"
      - "Tier 3 external audit reports"
```

---

## 24. ECOSYSTEM HEALTH KPIs

### 24.1 Coverage Metrics

```yaml
coverage_kpis:
  modules_with_srs_pct:
    formula: "(modules_with_srs / total_modules) * 100"
    target: "≥85%"
    current: "72%"
    trend: "+5% QoQ"
    status: "🟡 BELOW TARGET"
    action: "Create Tier 0 SRS for 7 orphaned modules"
  
  modules_tier_2_plus_pct:
    formula: "(modules_tier_2_or_higher / total_modules) * 100"
    target: "≥60%"
    current: "48%"
    trend: "+12% QoQ"
    status: "🟡 IMPROVING"
    action: "Promote 3 Tier 1 modules to Tier 2"
  
  orphaned_modules_count:
    formula: "total_modules - modules_with_srs"
    target: "<5"
    current: "7"
    status: "🔴 EXCEEDS TARGET"
    action: "Address immediately (high risk)"
```

### 24.2 Quality Metrics

```yaml
quality_kpis:
  avg_verification_score:
    formula: "mean(verified_completion) across all modules"
    target: ">0.80"
    current: "0.78"
    trend: "+0.03 QoQ"
    status: "🟡 BELOW TARGET"
    action: "Fix 3 modules with delta >0.30"
  
  avg_delta_claimed_vs_verified:
    formula: "mean(claimed - verified) across all modules"
    target: "<0.15"
    current: "0.15"
    trend: "-0.02 QoQ (improving)"
    status: "✅ AT TARGET"
    action: "Maintain current quality"
  
  critical_flaws_open:
    formula: "count(flaws where severity='CRITICAL' and status='OPEN')"
    target: "<10"
    current: "8"
    trend: "-2 QoQ"
    status: "✅ BELOW TARGET"
    action: "Continue current pace"
```

### 24.3 Velocity Metrics

```yaml
velocity_kpis:
  mean_time_srs_update_days:
    formula: "mean(days_since_last_srs_update)"
    target: "<21 days"
    current: "12 days"
    trend: "-3 days QoQ"
    status: "✅ EXCELLENT"
    action: "None (exemplary performance)"
  
  mean_time_flaw_resolution_days:
    formula: "mean(flaw_open_date - flaw_closed_date)"
    target: "<14 days"
    current: "18 days"
    trend: "+2 days QoQ (worsening)"
    status: "🔴 EXCEEDS TARGET"
    action: "Allocate more resources to flaw resolution"
  
  cgrf_compliance_trend_qoq:
    formula: "compliance_score_this_quarter - compliance_score_last_quarter"
    target: "Positive (any increase)"
    current: "+12%"
    status: "✅ STRONG GROWTH"
    action: "Continue current trajectory"
```

### 24.4 Risk Metrics

```yaml
risk_kpis:
  tier_3_modules_with_regressions:
    formula: "count(tier=3 and has_regression=true)"
    target: "0"
    current: "0"
    status: "✅ PERFECT"
    action: "Maintain vigilance"
  
  tier_2_modules_audit_passed_pct:
    formula: "(tier_2_audit_passed / tier_2_total) * 100"
    target: ">95%"
    current: "92%"
    trend: "-3% QoQ"
    status: "🟡 BELOW TARGET"
    action: "Investigate 1 failed audit (payment_gateway)"
  
  overdue_annual_reviews:
    formula: "count(modules where next_review_due < today)"
    target: "0"
    current: "2"
    status: "🔴 CRITICAL"
    action: "Schedule reviews for payment_gateway, user_auth"
```

---

## 25. MODULE MATURITY MODEL

### 25.1 Maturity Score Calculation

```python
# Auto-calculated by cgrf-cli

def calculate_maturity_score(module, srs):
    """
    Maturity Score = weighted average of 5 dimensions
    
    Scale: 0.0 (immature) → 1.0 (mature)
    """
    
    # Dimension 1: Metadata Completeness (25% weight)
    required_fields = [
        "_report_id", "_tier", "_module_version", "_module_name",
        "_execution_role", "_created", "_author"
    ]
    metadata_completeness = sum(
        1 for field in required_fields if srs.get(field)
    ) / len(required_fields)
    
    # Dimension 2: Verification Score (30% weight)
    verification_score = srs.get("claimed_vs_verified", {}).get("verified_completion", 0)
    
    # Dimension 3: Dependency Stability (20% weight)
    dependencies = srs.get("dependencies", {})
    stable_deps = sum(
        1 for dep in dependencies.get("external_services", [])
        if dep.get("version") and dep.get("fallback")
    )
    total_deps = len(dependencies.get("external_services", [])) or 1
    dependency_stability = stable_deps / total_deps
    
    # Dimension 4: Test Coverage (15% weight)
    test_coverage = srs.get("testing", {}).get("coverage_percent", 0) / 100
    
    # Dimension 5: Documentation Freshness (10% weight)
    last_updated = datetime.fromisoformat(srs.get("_last_updated", "2020-01-01"))
    days_since_update = (datetime.now() - last_updated).days
    documentation_freshness = max(0, 1 - (days_since_update / 365))  # Decays over 1 year
    
    # Weighted average
    maturity_score = (
        0.25 * metadata_completeness +
        0.30 * verification_score +
        0.20 * dependency_stability +
        0.15 * test_coverage +
        0.10 * documentation_freshness
    )
    
    return {
        "maturity_score": round(maturity_score, 2),
        "dimensions": {
            "metadata_completeness": round(metadata_completeness, 2),
            "verification_score": round(verification_score, 2),
            "dependency_stability": round(dependency_stability, 2),
            "test_coverage": round(test_coverage, 2),
            "documentation_freshness": round(documentation_freshness, 2)
        },
        "tier_promotion_eligible": maturity_score >= get_tier_promotion_threshold(srs["_tier"])
    }

def get_tier_promotion_threshold(current_tier):
    return {
        0: 0.60,  # Tier 0 → 1: 60% maturity
        1: 0.75,  # Tier 1 → 2: 75% maturity
        2: 0.90   # Tier 2 → 3: 90% maturity
    }.get(current_tier, 0.95)
```

### 25.2 Maturity Levels

```yaml
maturity_levels:
  0.00_to_0.40_NASCENT:
    description: "Barely documented, unstable"
    characteristics:
      - "Missing metadata fields"
      - "No tests or <30% coverage"
      - "High claimed-verified delta (>0.40)"
    risk: "🔴 HIGH"
    action: "Create Tier 0 SRS minimum"
  
  0.41_to_0.60_DEVELOPING:
    description: "Basic documentation, some testing"
    characteristics:
      - "Metadata mostly complete"
      - "30-60% test coverage"
      - "Delta <0.40"
    risk: "🟡 MEDIUM"
    action: "Add tests, improve verification"
  
  0.61_to_0.75_STABLE:
    description: "Good documentation, solid testing"
    characteristics:
      - "Complete metadata"
      - "60-80% test coverage"
      - "Delta <0.20"
    risk: "🟢 LOW"
    action: "Consider Tier 2 promotion"
  
  0.76_to_0.90_MATURE:
    description: "Excellent documentation, rigorous testing"
    characteristics:
      - "All fields complete"
      - "80-90% test coverage"
      - "Delta <0.10"
    risk: "🟢 VERY LOW"
    action: "Consider Tier 3 promotion"
  
  0.91_to_1.00_EXEMPLARY:
    description: "Best-in-class, audit-ready"
    characteristics:
      - "Perfect metadata"
      - "90-100% test coverage"
      - "Delta <0.05"
      - "External audit passed"
    risk: "✅ MINIMAL"
    action: "Maintain excellence, share as pattern"
```

---

## 26. QUICK-START TEMPLATES

### 26.1 Tier 0 Template (5 Minutes)

```yaml
# SRS-{MODULENAME}-{DATE}-001-V3.0.md
# Quick-Start Template (Tier 0: Experimental)

# COPY THIS TEMPLATE AND FILL IN 10 FIELDS

---
_report_id: "SRS-{MODULENAME}-{YYYYMMDD}-001-V3.0"
_document_schema: "CGRF-v3.0"
_tier: 0
_module_version: "0.1.0"
_execution_role: "{SELECT: PROTOTYPE|BACKEND_SERVICE|FRONTEND_SERVICE|DATA_PIPELINE}"
_module_name: "{MODULE_NAME}"
_created: "{YYYY-MM-DD}"
_author: "{YOUR_EMAIL}"
---

## Description (2-3 sentences)
{WHAT_DOES_THIS_MODULE_DO}

## Dependencies
- Needs Hub? {YES|NO}
- Needs external API? {YES|NO}
  - If yes, which one? {API_NAME}

## Known Issues
- {ISSUE_1 or "None yet"}
- {ISSUE_2 or leave blank}

## Next Steps
- Next tier: {0|1|2|3}
- Blockers to promotion:
  - {BLOCKER_1 e.g., "Add unit tests"}
  - {BLOCKER_2 e.g., "Get stakeholder approval"}
```

**Usage:**
```bash
$ cp templates/tier0-quickstart.md docs/SRS-MY-MODULE-20260125-001-V3.0.md
$ vim docs/SRS-MY-MODULE-20260125-001-V3.0.md  # Fill 10 fields
$ cgrf validate --module src/my_module.py --srs docs/SRS-MY-MODULE-20260125-001-V3.0.md
✅ TIER 0 COMPLIANT (5 minutes)
```

### 26.2 Tier 1 Template (2 Hours)

```yaml
# SRS-{MODULENAME}-{DATE}-001-V3.0.md
# Tier 1 Template (Development)

---
_report_id: "SRS-{MODULENAME}-{YYYYMMDD}-001-V3.0"
_document_schema: "CGRF-v3.0"
_tier: 1
_module_version: "{MAJOR.MINOR.PATCH}"
_execution_role: "{BACKEND_SERVICE|FRONTEND_SERVICE|DATA_PIPELINE|...}"
_module_name: "{MODULE_NAME}"
_created: "{YYYY-MM-DD}"
_last_updated: "{YYYY-MM-DD}"
_author: "{YOUR_EMAIL}"
---

## Module Identity
- **Purpose**: {1-2 sentences}
- **Scope**: {What's included/excluded}
- **Dependencies**:
  - External: {List APIs, services}
  - Internal: {List other modules}

## Functional Requirements
- **FR-{MODULE}-001**
  - Description: {WHAT_IT_DOES}
  - Acceptance Criteria:
    - {CRITERION_1}
    - {CRITERION_2}
  - Test Status: {PASSING|FAILING|NOT_IMPLEMENTED}

- **FR-{MODULE}-002**
  - {REPEAT_ABOVE}

## Testing
- Unit tests: {COUNT}
- Integration tests: {COUNT}
- Coverage: {PERCENT}% (Tier 1 requires ≥50%)

## Known Issues
- {ISSUE_1 or "None"}

## Version History
- v{VERSION} ({DATE}): {CHANGES}
```

### 26.3 Tier 2 Template (1-2 Days)

See full Tier 2 requirements in Section 8.

### 26.4 Tier 3 Template (1 Week)

See full Tier 3 requirements in Section 9.

---

## 27. MIGRATION GUIDE (v2 → v3)

### 27.1 Breaking Changes Checklist

```yaml
breaking_changes:
  - change: "Added _tier field (REQUIRED)"
    action: |
      Add to all SRS headers:
      _tier: {0|1|2|3}
      
      Decision tree:
      - Prototype? → 0
      - Development? → 1
      - Production? → 2
      - Mission-critical? → 3
    
    automation: |
      $ cgrf migrate --from v2.0 --to v3.0 --auto-tier
      # Auto-assigns tier based on heuristics:
      # - test_coverage <50% → Tier 0
      # - test_coverage 50-80% → Tier 1
      # - test_coverage >80% + has_prds → Tier 2
      # - external_audit_passed → Tier 3
  
  - change: "Maturity score auto-calculated"
    action: |
      No action required (cgrf-cli calculates automatically)
    
    impact: "New field _maturity_score appears in validation reports"
  
  - change: "Claimed vs. Verified thresholds stricter"
    action: |
      v2.0: No tier-specific thresholds
      v3.0: Tier-specific:
        - Tier 1: ≤40%
        - Tier 2: ≤20%
        - Tier 3: ≤10%
      
      If your delta exceeds new threshold:
      1. Add more tests (increase verified_completion)
      2. Remove unimplemented FRs (decrease claimed_completion)
      3. Request tier demotion (temporary)
```

### 27.2 Migration Script

```bash
#!/bin/bash
# migrate-cgrf-v2-to-v3.sh

echo "CGRF v2.0 → v3.0 Migration"
echo "=========================="

# Step 1: Backup
echo "[1/5] Creating backup..."
cp -r docs/ docs.backup/
echo "✅ Backed up to docs.backup/"

# Step 2: Install cgrf-cli v3
echo "[2/5] Installing cgrf-cli v3.0..."
pip install --upgrade cgrf-cli==3.0.0

# Step 3: Auto-migrate SRS files
echo "[3/5] Migrating SRS files..."
cgrf migrate \
  --from v2.0 \
  --to v3.0 \
  --workspace . \
  --auto-tier \
  --update-schema

# Step 4: Validate
echo "[4/5] Validating migrated files..."
cgrf validate --workspace . --tier-minimum 0

# Step 5: Generate report
echo "[5/5] Generating migration report..."
cgrf report --workspace . > migration-report.txt

echo ""
echo "✅ Migration complete!"
echo ""
echo "Next steps:"
echo "1. Review migration-report.txt"
echo "2. Fix any validation errors"
echo "3. Commit changes: git add docs/ && git commit -m 'Migrate CGRF v2 → v3'"
```

---

## 28. GLOSSARY

### 28.1 CGRF-Specific Terms

```yaml
terms:
  AGS:
    full_name: "Agent Governance System"
    definition: "Constitutional judiciary that validates all mutations through 4-stage policy pipeline"
    sections: ["Part IV: Section 16"]
  
  AIS:
    full_name: "Autonomous Intelligence System"
    definition: "Economic engine + knowledge system driving agent evolution via XP/TP tokens"
    sections: ["Part IV: Section 17"]
  
  CAPS:
    full_name: "Capability Assessment & Permission System"
    definition: "Agent grading system (D/C/B/A/S) determining permission levels"
    sections: ["Part IV: Section 16.2"]
  
  Claimed_vs_Verified:
    definition: "Delta between what developers claim is done vs. what tests prove works"
    formula: "claimed_completion - verified_completion"
    thresholds:
      - "Tier 1: ≤40%"
      - "Tier 2: ≤20%"
      - "Tier 3: ≤10%"
    sections: ["Part III: Section 14"]
  
  Constitutional_Compiler:
    definition: "4-stage validation pipeline (S00-S03) enforcing governance rules"
    stages:
      - "S00 Generator: Intent normalization"
      - "S01 Definer: Schema validation"
      - "S02 FATE: Risk assessment"
      - "S03 Archivist: Immutable recording"
    sections: ["Part IV: Section 18"]
  
  FR:
    full_name: "Functional Requirement"
    definition: "Testable specification of module behavior"
    format: "FR-{MODULE}-{NUMBER}"
    required_tier: 1
    sections: ["Part III: Section 11"]
  
  MCHS_META:
    full_name: "Module Capability & Health Status - Metadata"
    definition: "Core metadata header required for all modules"
    fields:
      - "_report_id"
      - "_document_schema"
      - "_tier"
      - "_module_version"
      - "_execution_role"
    sections: ["Part III: Section 10"]
  
  Maturity_Score:
    definition: "Auto-calculated metric (0-1) measuring module quality"
    formula: |
      0.25 * metadata_completeness +
      0.30 * verification_score +
      0.20 * dependency_stability +
      0.15 * test_coverage +
      0.10 * documentation_freshness
    sections: ["Part VI: Section 25"]
  
  PRD:
    full_name: "Production Rule"
    definition: "Enforced constraint for production systems (e.g., rate limiting)"
    format: "PRD-{MODULE}-{NUMBER}"
    required_tier: 2
    categories: ["AVAILABILITY", "PERFORMANCE", "SECURITY", "COMPLIANCE", "RELIABILITY"]
    sections: ["Part III: Section 12"]
  
  REFLEX:
    full_name: "Rapid Error Feedback & Learning eXecution"
    definition: "Self-healing nervous system that detects anomalies and auto-generates fixes"
    stages:
      - "OBSERVE: Monitor failures"
      - "DIAGNOSE: Root cause analysis"
      - "RESPOND: Generate fix"
      - "VERIFY: Test fix"
      - "LEARN: Update knowledge"
    sections: ["Part IV: Section 15"]
  
  SRS:
    full_name: "Specification Record System"
    definition: "Comprehensive documentation file for a module"
    format: "SRS-{MODULENAME}-{DATE}-{VERSION}"
    tiers:
      - "Tier 0: Quick-start (5 min)"
      - "Tier 1: Development (2 hours)"
      - "Tier 2: Production (1-2 days)"
      - "Tier 3: Mission-critical (1 week)"
  
  Tier:
    definition: "Risk-based governance level (0-3)"
    levels:
      - "Tier 0: Experimental (minimal enforcement)"
      - "Tier 1: Development (moderate enforcement)"
      - "Tier 2: Production (high enforcement)"
      - "Tier 3: Mission-critical (full enforcement)"
    sections: ["Part II: Sections 5-9"]
  
  XP_TP:
    definition: "Dual-token economic system in AIS"
    xp:
      - "Non-transferable experience points"
      - "Earned through task completion"
      - "Unlocks tier progression"
    tp:
      - "Transferable treasury points"
      - "Earned through critical tasks"
      - "Used to bid on high-value work"
    sections: ["Part IV: Section 17.2"]
```

---

## CONCLUSION

CGRF v3.0 represents a **paradigm shift** in AI governance: from flat, all-or-nothing enforcement to **tiered, risk-based compliance** that adapts to module criticality.

**Key Achievements:**
1. ✅ **5-minute quick-start** (Tier 0) enables rapid adoption
2. ✅ **80% automation** via cgrf-cli, VS Code, CI/CD
3. ✅ **SOC2/ISO 27001 mappings** provide regulatory alignment
4. ✅ **REFLEX integration** enables self-healing
5. ✅ **AGS/AIS integration** delivers autonomous governance + economic engine
6. ✅ **Ecosystem KPIs** quantify governance ROI

**Next Steps:**
1. Install cgrf-cli: `pip install cgrf-cli`
2. Run quick-start: `cgrf init --workspace .`
3. Create first Tier 0 SRS: `cgrf scaffold --module my_module.py --tier 0`
4. Validate: `cgrf validate --workspace .`
5. Promote to production: `cgrf tier-check --module my_module.py --target-tier 2`

**The future of AI governance is not rule-based—it's tier-based, economically-driven, and autonomously enforced.**

---

**Document Hash:** `sha256:f1a2b3c4d5e6...`  
**Approval:** Citadel AI Governance Board  
**Effective Date:** 2026-02-01  
**Review Cycle:** Annual (next review: 2027-02-01)
