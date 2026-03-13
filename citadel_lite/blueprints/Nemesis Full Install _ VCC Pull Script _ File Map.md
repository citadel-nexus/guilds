---
title: Nemesis Full Install — VCC Pull Script + File Map
url: https://www.notion.so/Nemesis-Full-Install-VCC-Pull-Script-File-Map-b115dc36a6814d6a8ad95ffa2d23e84d
fetched: 1772333089.6372464
---

# Nemesis Full Install — VCC Pull Script + File Map

Status: Ready for VCC | Date: Feb 26, 2026

Owner: mr.nobody | Scope: Single script to pull, place, migrate, and wire ALL Nemesis files (L1–L6 + Red Team)

References: Nemesis Defense System, L5 Shield, L6 Compliance, Red Team blueprints

---

## File Map — Every Nemesis File by Layer

---

## VCC Pull + Install Script

### scripts/nemesis_full_install.sh

```bash
#!/usr/bin/env bash
# ============================================================
# Nemesis Full Install — VCC Deployment Script
# Pulls ALL Nemesis files (L1-L6 + Red Team) and installs them
# in correct order with dependency checks.
#
# Usage:
#   chmod +x scripts/nemesis_full_install.sh
#   ./scripts/nemesis_full_install.sh [--dry-run] [--skip-migrations] [--layer L1,L2,...]
#
# Prereqs:
#   - SSH access to VPS (root@147.93.43.117)
#   - GitLab repo cloned at $REPO_ROOT
#   - Ansible, Helm, Terraform, Docker Compose available
#   - Vault secrets decrypted (ansible-vault)
#   - .env file with SUPABASE_URL, SUPABASE_SERVICE_KEY,
#     NEMESIS_ADMIN_TOKEN, GEOIP_*, ABUSEIPDB_KEY, PII_ENCRYPTION_KEY
# ============================================================

set -euo pipefail

# ── Config ──
REPO_ROOT="${REPO_ROOT:-$(git rev-parse --show-toplevel)}"
VPS_HOST="${VPS_HOST:-root@147.93.43.117}"
SSH_KEY="${SSH_KEY:-~/.ssh/id_ed25519_deploy}"
DRY_RUN=false
SKIP_MIGRATIONS=false
LAYERS="L1,L2,L3,L4,L5,L6,RT"

for arg in "$@"; do
  case $arg in
    --dry-run)       DRY_RUN=true ;;
    --skip-migrations) SKIP_MIGRATIONS=true ;;
    --layer=*)       LAYERS="${arg#*=}" ;;
  esac
done

log()  { echo "[$(date '+%H:%M:%S')] $*"; }
run()  { if $DRY_RUN; then echo "  [DRY-RUN] $*"; else eval "$*"; fi; }
has_layer() { [[ ",${LAYERS}," == *",$1,"* ]]; }

log "=== Nemesis Full Install ==="
log "Repo:    $REPO_ROOT"
log "VPS:     $VPS_HOST"
log "Layers:  $LAYERS"
log "Dry-run: $DRY_RUN"
echo ""

# ── Pre-flight checks ──
log "--- Pre-flight checks ---"
command -v ansible-playbook >/dev/null || { log "ERROR: ansible-playbook not found"; exit 1; }
command -v helm >/dev/null            || { log "ERROR: helm not found"; exit 1; }
command -v docker >/dev/null           || { log "ERROR: docker not found"; exit 1; }
command -v psql >/dev/null             || log "WARN: psql not found — migrations will use supabase CLI"
command -v terraform >/dev/null        || log "WARN: terraform not found — skip L6 WAF if needed"

# Verify SSH
run "ssh -i $SSH_KEY -o ConnectTimeout=5 $VPS_HOST 'echo SSH_OK' >/dev/null 2>&1" \
  || { log "ERROR: SSH connection failed"; exit 1; }

# Verify .env
[[ -f "$REPO_ROOT/.env" ]] || { log "ERROR: .env not found at $REPO_ROOT/.env"; exit 1; }
source "$REPO_ROOT/.env"

log "Pre-flight: PASS"
echo ""

# ============================================================
# PHASE 0: Create directory structure
# ============================================================
log "--- Phase 0: Directory scaffold ---"
DIRS=(
  "middleware"
  "routes"
  "services"
  "services/redteam"
  "config"
  "migrations"
  "scripts"
  "terraform"
  "docs"
  ".semgrep"
  "docker"
  "playbooks"
  "inventory"
  "roles/shield-nats-tls/tasks"
  "roles/shield-nftables-egress/tasks"
  "roles/shield-probe-logger/tasks"
  "roles/shield-fail2ban-bridge/tasks"
  "roles/shield-dns-logger/tasks"
  "roles/shield-nginx-ja3/tasks"
  "roles/shield-canary-tokens/tasks"
  "roles/compliance-asv-scan/tasks"
  "helm/nemesis-shield/templates"
  "helm/nemesis-redteam/templates"
)
for d in "${DIRS[@]}"; do
  run "mkdir -p $REPO_ROOT/$d"
done
log "Directories created."
echo ""

# ============================================================
# PHASE 1: Supabase Migrations (all layers)
# ============================================================
if ! $SKIP_MIGRATIONS; then
  log "--- Phase 1: Supabase Migrations ---"

  MIGRATION_FILES=()
  has_layer L4 && MIGRATION_FILES+=("migrations/20260226_nemesis.sql")
  has_layer L5 && MIGRATION_FILES+=("migrations/20260226_shield.sql")
  has_layer L6 && MIGRATION_FILES+=("migrations/20260226_compliance.sql")
  has_layer RT && MIGRATION_FILES+=("migrations/20260226_redteam.sql")

  for mig in "${MIGRATION_FILES[@]}"; do
    if [[ -f "$REPO_ROOT/$mig" ]]; then
      log "  Running migration: $mig"
      if command -v psql >/dev/null; then
        run "psql \"$DATABASE_URL\" -f $REPO_ROOT/$mig"
      else
        run "supabase db push --db-url \"$DATABASE_URL\" < $REPO_ROOT/$mig"
      fi
    else
      log "  WARN: Migration file not found: $mig — extract from blueprint"
    fi
  done
  log "Migrations complete."
else
  log "--- Phase 1: Migrations SKIPPED ---"
fi
echo ""

# ============================================================
# PHASE 2: L1 Perimeter — nftables + CrowdSec
# ============================================================
if has_layer L1; then
  log "--- Phase 2: L1 Perimeter ---"
  log "  Deploying nftables rules..."
  run "scp -i $SSH_KEY $REPO_ROOT/config/nemesis_firewall.nft $VPS_HOST:/etc/nftables.d/nemesis_firewall.nft"
  run "ssh -i $SSH_KEY $VPS_HOST 'nft -f /etc/nftables.d/nemesis_firewall.nft'"

  log "  Verifying CrowdSec..."
  run "ssh -i $SSH_KEY $VPS_HOST 'systemctl is-active crowdsec || systemctl start crowdsec'"

  log "L1 Perimeter: DONE"
fi
echo ""

# ============================================================
# PHASE 3: L2 Inspector — AI Firewall Middleware
# ============================================================
if has_layer L2; then
  log "--- Phase 3: L2 Inspector ---"
  log "  Placing middleware/nemesis_inspector.py"
  # File should already be in repo from blueprint extraction
  [[ -f "$REPO_ROOT/middleware/nemesis_inspector.py" ]] \
    || log "  WARN: middleware/nemesis_inspector.py not found — extract from blueprint"

  log "  Placing middleware/cors_hardening.py (L6)"
  [[ -f "$REPO_ROOT/middleware/cors_hardening.py" ]] \
    || log "  WARN: middleware/cors_hardening.py not found — extract from blueprint"

  log "L2 Inspector: DONE (restart MCP to activate)"
fi
echo ""

# ============================================================
# PHASE 4: L3 Hunter — Honeypots
# ============================================================
if has_layer L3; then
  log "--- Phase 4: L3 Hunter ---"
  [[ -f "$REPO_ROOT/routes/nemesis_honeypots.py" ]] \
    || log "  WARN: routes/nemesis_honeypots.py not found — extract from blueprint"
  log "L3 Hunter: DONE (restart MCP to activate)"
fi
echo ""

# ============================================================
# PHASE 5: L4 Oracle — Classifier + Geo + Retrain
# ============================================================
if has_layer L4; then
  log "--- Phase 5: L4 Oracle ---"

  FILES_L4=(
    "services/nemesis_oracle.py"
    "services/nemesis_retrain.py"
    "services/nemesis_geo_aggregator.py"
    "routes/nemesis_api.py"
    "config/nats-nemesis.yaml"
    "config/n8n-nemesis-workflows.yaml"
    "docker/docker-compose.nemesis.yaml"
  )
  for f in "${FILES_L4[@]}"; do
    [[ -f "$REPO_ROOT/$f" ]] || log "  WARN: $f not found — extract from blueprint"
  done

  log "  Adding NATS Nemesis stream..."
  run "nats stream add --config $REPO_ROOT/config/nats-nemesis.yaml 2>/dev/null || nats stream edit CITADEL_NEMESIS --config $REPO_ROOT/config/nats-nemesis.yaml"

  log "  Starting GeoIP updater container..."
  run "docker compose -f $REPO_ROOT/docker/docker-compose.yaml -f $REPO_ROOT/docker/docker-compose.nemesis.yaml up -d geoip-updater"

  log "L4 Oracle: DONE"
fi
echo ""

# ============================================================
# PHASE 6: L5 Shield — Ansible roles + NATS TLS + Helm
# ============================================================
if has_layer L5; then
  log "--- Phase 6: L5 Shield ---"

  log "  Adding Shield NATS subjects..."
  [[ -f "$REPO_ROOT/config/nats-shield.yaml" ]] \
    && run "nats stream edit CITADEL_NEMESIS --config $REPO_ROOT/config/nats-shield.yaml" \
    || log "  WARN: config/nats-shield.yaml not found"

  log "  Running Shield Ansible playbook (--check first)..."
  run "ansible-playbook -i $REPO_ROOT/inventory/citadel.ini $REPO_ROOT/playbooks/shield-deploy.yaml --check"

  if ! $DRY_RUN; then
    read -rp "  Shield --check passed. Apply for real? [y/N] " confirm
    if [[ "$confirm" == "y" || "$confirm" == "Y" ]]; then
      run "ansible-playbook -i $REPO_ROOT/inventory/citadel.ini $REPO_ROOT/playbooks/shield-deploy.yaml"
    else
      log "  Skipped Shield apply."
    fi
  fi

  log "  Deploying Helm chart (nemesis-shield)..."
  run "helm upgrade --install nemesis-shield $REPO_ROOT/helm/nemesis-shield/ --dry-run" \
    || log "  WARN: Helm dry-run failed — check chart"

  log "L5 Shield: DONE"
fi
echo ""

# ============================================================
# PHASE 7: L6 Compliance — CI + WAF + Policies
# ============================================================
if has_layer L6; then
  log "--- Phase 7: L6 Compliance ---"

  FILES_L6=(
    ".gitlab-ci.yml"
    ".semgrep/citadel-rules.yml"
    "scripts/aggregate_security_reports.py"
    "terraform/cloudflare_waf.tf"
    "middleware/cors_hardening.py"
    "docs/pentest-scope.md"
  )
  for f in "${FILES_L6[@]}"; do
    [[ -f "$REPO_ROOT/$f" ]] || log "  WARN: $f not found — extract from blueprint"
  done

  log "  Applying Cloudflare WAF via Terraform..."
  if command -v terraform >/dev/null && [[ -f "$REPO_ROOT/terraform/cloudflare_waf.tf" ]]; then
    run "cd $REPO_ROOT/terraform && terraform init && terraform plan"
    if ! $DRY_RUN; then
      read -rp "  Terraform plan OK. Apply WAF rules? [y/N] " tf_confirm
      if [[ "$tf_confirm" == "y" || "$tf_confirm" == "Y" ]]; then
        run "cd $REPO_ROOT/terraform && terraform apply -auto-approve"
      fi
    fi
  else
    log "  WARN: Terraform or WAF file missing — skipping WAF deploy"
  fi

  log "  Deploying ASV scan role..."
  [[ -d "$REPO_ROOT/roles/compliance-asv-scan" ]] \
    || log "  WARN: roles/compliance-asv-scan/ not found"

  log "L6 Compliance: DONE"
fi
echo ""

# ============================================================
# PHASE 8: Red Team — Scanners + Campaign Manager
# ============================================================
if has_layer RT; then
  log "--- Phase 8: Red Team ---"

  FILES_RT=(
    "services/redteam/__init__.py"
    "services/redteam/scanner_base.py"
    "services/redteam/rt_inject.py"
    "services/redteam/rt_llm.py"
    "services/redteam/rt_recon.py"
    "services/redteam/rt_auth.py"
    "services/redteam/rt_honey.py"
    "services/redteam/rt_exfil.py"
    "services/redteam/campaign_manager.py"
    "routes/redteam_api.py"
    "config/nats-redteam.yaml"
  )
  for f in "${FILES_RT[@]}"; do
    [[ -f "$REPO_ROOT/$f" ]] || log "  WARN: $f not found — extract from blueprint"
  done

  # Ensure __init__.py exists
  run "touch $REPO_ROOT/services/redteam/__init__.py"

  log "  Adding Red Team NATS stream..."
  [[ -f "$REPO_ROOT/config/nats-redteam.yaml" ]] \
    && run "nats stream add --config $REPO_ROOT/config/nats-redteam.yaml" \
    || log "  WARN: config/nats-redteam.yaml not found"

  log "  Deploying Helm chart (nemesis-redteam)..."
  run "helm upgrade --install nemesis-redteam $REPO_ROOT/helm/nemesis-redteam/ --dry-run" \
    || log "  WARN: Helm dry-run failed — check chart"

  log "Red Team: DONE"
fi
echo ""

# ============================================================
# PHASE 9: Wire main.py + Restart MCP
# ============================================================
log "--- Phase 9: Wire FastAPI main.py + Restart ---"

MAIN_PY="$REPO_ROOT/src/api/main.py"
if [[ -f "$MAIN_PY" ]]; then
  # Check if Nemesis already wired
  if ! grep -q 'NEMESIS_ENABLED' "$MAIN_PY"; then
    log "  Appending Nemesis mount block to main.py..."
    cat >> "$MAIN_PY" << 'NEMESIS_MOUNT'

# ============================================================
# Nemesis Defense System — mount block
# ============================================================
import os

if os.getenv("NEMESIS_ENABLED") == "true":
    # L2 Inspector middleware
    from middleware.nemesis_inspector import NemesisInspectorMiddleware
    app.add_middleware(NemesisInspectorMiddleware)

    # L6 CORS hardening (replaces default CORSMiddleware)
    from middleware.cors_hardening import add_cors
    add_cors(app)

    # L4 Nemesis admin API
    from routes.nemesis_api import router as nemesis_router
    app.include_router(nemesis_router)

    # L3 Honeypots
    from routes.nemesis_honeypots import honeypot_router
    app.include_router(honeypot_router)

    # Red Team API
    from routes.redteam_api import router as redteam_router
    app.include_router(redteam_router)

    # Load Oracle classifier on startup
    from services.nemesis_oracle import _fast_classifier
    _fast_classifier.load()
NEMESIS_MOUNT
    log "  main.py patched."
  else
    log "  main.py already has Nemesis mount — skipping."
  fi
else
  log "  WARN: main.py not found at $MAIN_PY"
fi

log "  Restarting MCP server..."
run "docker compose -f $REPO_ROOT/docker/docker-compose.yaml -f $REPO_ROOT/docker/docker-compose.nemesis.yaml up -d --build mcp-server"

echo ""

# ============================================================
# PHASE 10: Smoke Tests
# ============================================================
log "--- Phase 10: Smoke Tests ---"
sleep 5

# Nemesis health
log "  Checking /api/nemesis/health..."
run "curl -sf -H 'Authorization: Bearer $NEMESIS_ADMIN_TOKEN' http://localhost:8443/api/nemesis/health | python3 -m json.tool" \
  || log "  FAIL: Nemesis health check"

# Red Team health
log "  Checking /api/redteam/health..."
run "curl -sf -H 'Authorization: Bearer $NEMESIS_ADMIN_TOKEN' http://localhost:8443/api/redteam/health | python3 -m json.tool" \
  || log "  FAIL: Red Team health check"

# Honeypot test
log "  Testing honeypot /admin..."
run "curl -sf http://localhost:8443/admin | head -c 200" \
  || log "  FAIL: Honeypot not responding"

# Inspector test — send known bad payload
log "  Testing L2 Inspector (SQLi payload)..."
STATUS=$(run "curl -sf -o /dev/null -w '%{http_code}' -X POST http://localhost:8443/api/rooms/create -H 'Content-Type: application/json' -d '{\"room_name\": \"\' OR 1=1 --\"}'")
if [[ "$STATUS" == "403" ]]; then
  log "  L2 Inspector: PASS (blocked SQLi)"
else
  log "  WARN: L2 Inspector returned $STATUS — expected 403"
fi

echo ""
log "=== Nemesis Full Install COMPLETE ==="
log ""
log "Next steps for VCC:"
log "  1. Verify all WARN items above — extract missing files from Notion blueprints"
log "  2. Import n8n workflows from config/n8n-nemesis-workflows.yaml"
log "  3. Run first Red Team campaign:"
log "     curl -X POST http://localhost:8443/api/redteam/campaign/start \\"
log "       -H 'Authorization: Bearer \$NEMESIS_ADMIN_TOKEN' \\"
log "       -H 'Content-Type: application/json' \\"
log "       -d '{\"name\": \"First Sweep\", \"campaign_type\": \"full_sweep\"}'"
log "  4. Check dashboard: GET /api/nemesis/dashboard/summary"
log "  5. Run Terraform apply for Cloudflare WAF if not done above"
```

---

## .env Template for VCC

```bash
# ============================================================
# Nemesis .env — VCC must fill these before running install
# ============================================================

# Supabase
DATABASE_URL=postgresql://postgres:[PASSWORD]@db.[PROJECT].supabase.co:5432/postgres
SUPABASE_URL=https://[PROJECT].supabase.co
SUPABASE_SERVICE_KEY=eyJ...

# Nemesis
NEMESIS_ENABLED=true
NEMESIS_ADMIN_TOKEN=[GENERATE: openssl rand -hex 32]

# GeoIP (MaxMind)
GEOIP_ACCOUNT_ID=[YOUR_MAXMIND_ID]
GEOIP_LICENSE_KEY=[YOUR_MAXMIND_KEY]

# AbuseIPDB
ABUSEIPDB_KEY=[YOUR_ABUSEIPDB_KEY]

# PII Encryption
PII_ENCRYPTION_KEY=[GENERATE: openssl rand -hex 32]

# Cloudflare (for L6 WAF)
CLOUDFLARE_API_TOKEN=[YOUR_CF_TOKEN]
CLOUDFLARE_ZONE_ID=[YOUR_ZONE_ID]

# VPS
VPS_HOST=root@147.93.43.117
SSH_KEY=~/.ssh/id_ed25519_deploy
```

---

## Execution Order — Quick Reference

---

## Exit Criteria

---

## Datadog Integration — Metrics, Traces & Alerts

### services/nemesis_datadog.py

```python
"""
Nemesis Datadog Integration
─────────────────────────────────────────────
Centralized observability for L1-L6 + Red Team.
Emits StatsD metrics, APM traces, and log correlation.

Prereqs:
  pip install ddtrace datadog
  DD_AGENT_HOST / DD_API_KEY / DD_APP_KEY in .env
  Datadog Agent running (docker or host-level)
"""

import os
import time
import functools
import logging
from typing import Optional, Dict, Any
from contextlib import contextmanager

from datadog import initialize, statsd, api as dd_api
from ddtrace import tracer, patch_all
from ddtrace.contrib.trace_utils import set_user

logger = logging.getLogger("nemesis.datadog")

# ── Init ──────────────────────────────────────────────

DD_OPTIONS = {
    "statsd_host": os.getenv("DD_AGENT_HOST", "127.0.0.1"),
    "statsd_port": int(os.getenv("DD_DOGSTATSD_PORT", 8125)),
    "api_key": os.getenv("DD_API_KEY", ""),
    "app_key": os.getenv("DD_APP_KEY", ""),
}


def init_datadog():
    """Call once at FastAPI startup."""
    initialize(**DD_OPTIONS)
    patch_all()  # auto-instrument aiohttp, psycopg2, redis, etc.
    tracer.configure(
        hostname=DD_OPTIONS["statsd_host"],
        port=8126,
        service="nemesis-defense",
        env=os.getenv("DD_ENV", "production"),
        version=os.getenv("DD_VERSION", "1.0.0"),
    )
    logger.info("Datadog initialized — service=nemesis-defense")


# ── StatsD Metric Helpers ─────────────────────────────

METRIC_PREFIX = "nemesis"


def _metric(name: str) -> str:
    return f"{METRIC_PREFIX}.{name}"


# ── L1 Perimeter Metrics ─────────────────────────────

def track_firewall_block(ip: str, rule: str, geo_country: str = "unknown"):
    """L1 — nftables / CrowdSec block event."""
    statsd.increment(
        _metric("l1.firewall.blocks"),
        tags=[f"rule:{rule}", f"country:{geo_country}"],
    )
    statsd.set(_metric("l1.firewall.unique_blocked_ips"), ip)


def track_crowdsec_decision(action: str, scenario: str, ip: str):
    """L1 — CrowdSec ban/captcha decision."""
    statsd.increment(
        _metric("l1.crowdsec.decisions"),
        tags=[f"action:{action}", f"scenario:{scenario}"],
    )


# ── L2 Inspector Metrics ─────────────────────────────

def track_inspection(
    verdict: str,
    threat_type: str,
    confidence: float,
    latency_ms: float,
    tenant_id: Optional[str] = None,
):
    """L2 — AI firewall inspection result."""
    tags = [f"verdict:{verdict}", f"threat_type:{threat_type}"]
    if tenant_id:
        tags.append(f"tenant_id:{tenant_id}")

    statsd.increment(_metric("l2.inspector.requests"), tags=tags)
    statsd.histogram(_metric("l2.inspector.confidence"), confidence, tags=tags)
    statsd.histogram(_metric("l2.inspector.latency_ms"), latency_ms, tags=tags)

    if verdict == "block":
        statsd.increment(_metric("l2.inspector.blocks"), tags=tags)
    elif verdict == "flag":
        statsd.increment(_metric("l2.inspector.flags"), tags=tags)


def track_inspector_error(error_type: str):
    """L2 — Inspector pipeline error."""
    statsd.increment(
        _metric("l2.inspector.errors"), tags=[f"error_type:{error_type}"]
    )


# ── L3 Honeypot Metrics ──────────────────────────────

def track_honeypot_hit(path: str, ip: str, user_agent: str, geo_country: str = "unknown"):
    """L3 — Honeypot trap triggered."""
    statsd.increment(
        _metric("l3.honeypot.hits"),
        tags=[f"path:{path}", f"country:{geo_country}"],
    )
    statsd.set(_metric("l3.honeypot.unique_ips"), ip)


# ── L4 Oracle Metrics ────────────────────────────────

def track_oracle_classification(
    ip: str, risk_score: float, classification: str, latency_ms: float
):
    """L4 — Oracle ML classifier result."""
    statsd.histogram(
        _metric("l4.oracle.risk_score"),
        risk_score,
        tags=[f"classification:{classification}"],
    )
    statsd.histogram(_metric("l4.oracle.latency_ms"), latency_ms)
    statsd.increment(
        _metric("l4.oracle.classifications"),
        tags=[f"classification:{classification}"],
    )


def track_oracle_retrain(model_version: str, accuracy: float, sample_count: int):
    """L4 — Model retrain event."""
    statsd.gauge(_metric("l4.oracle.model_accuracy"), accuracy)
    statsd.gauge(_metric("l4.oracle.training_samples"), sample_count)
    statsd.event(
        title="Nemesis Oracle Retrained",
        text=f"Model {model_version} — accuracy: {accuracy:.4f} — samples: {sample_count}",
        tags=[f"model_version:{model_version}"],
        alert_type="info",
    )


def track_geo_aggregation(country: str, threat_count: int):
    """L4 — GeoIP aggregation update."""
    statsd.gauge(
        _metric("l4.geo.threats_by_country"),
        threat_count,
        tags=[f"country:{country}"],
    )


# ── L5 Shield Metrics ────────────────────────────────

def track_shield_probe(probe_type: str, source_ip: str, blocked: bool):
    """L5 — Shield probe detection."""
    statsd.increment(
        _metric("l5.shield.probes"),
        tags=[f"probe_type:{probe_type}", f"blocked:{blocked}"],
    )


def track_pii_erasure(tenant_id: str, records_erased: int):
    """L5 — GDPR/PII erasure event."""
    statsd.increment(_metric("l5.shield.pii_erasures"), tags=[f"tenant_id:{tenant_id}"])
    statsd.histogram(_metric("l5.shield.records_erased"), records_erased)


def track_canary_trigger(token_name: str, source_ip: str):
    """L5 — Canary token triggered (high severity)."""
    statsd.increment(
        _metric("l5.shield.canary_triggers"), tags=[f"token:{token_name}"]
    )
    # Fire Datadog event for immediate alerting
    statsd.event(
        title=f"🚨 Canary Token Triggered: {token_name}",
        text=f"Source IP: {source_ip}. Possible intrusion.",
        tags=[f"token:{token_name}", f"source_ip:{source_ip}"],
        alert_type="error",
    )


# ── L6 Compliance Metrics ────────────────────────────

def track_sast_scan(tool: str, findings: int, critical: int, high: int):
    """L6 — SAST scan results."""
    tags = [f"tool:{tool}"]
    statsd.gauge(_metric("l6.sast.findings_total"), findings, tags=tags)
    statsd.gauge(_metric("l6.sast.findings_critical"), critical, tags=tags)
    statsd.gauge(_metric("l6.sast.findings_high"), high, tags=tags)


def track_dast_scan(target: str, findings: int, duration_s: float):
    """L6 — DAST scan results."""
    statsd.gauge(_metric("l6.dast.findings"), findings, tags=[f"target:{target}"])
    statsd.histogram(_metric("l6.dast.duration_s"), duration_s)


def track_waf_event(rule_id: str, action: str, uri: str):
    """L6 — Cloudflare WAF event."""
    statsd.increment(
        _metric("l6.waf.events"),
        tags=[f"rule_id:{rule_id}", f"action:{action}"],
    )


def track_pentest_finding(severity: str, category: str, status: str):
    """L6 — Pen test finding tracked."""
    statsd.increment(
        _metric("l6.pentest.findings"),
        tags=[f"severity:{severity}", f"category:{category}", f"status:{status}"],
    )


# ── Red Team Metrics ─────────────────────────────────

def track_rt_campaign(campaign_id: str, campaign_type: str, status: str):
    """RT — Campaign lifecycle event."""
    statsd.increment(
        _metric("rt.campaigns"),
        tags=[f"type:{campaign_type}", f"status:{status}"],
    )


def track_rt_scan(
    scanner: str, target: str, findings: int, severity_max: str, latency_s: float
):
    """RT — Individual scanner result."""
    tags = [f"scanner:{scanner}", f"severity_max:{severity_max}"]
    statsd.increment(_metric("rt.scans.completed"), tags=tags)
    statsd.histogram(_metric("rt.scans.findings"), findings, tags=tags)
    statsd.histogram(_metric("rt.scans.latency_s"), latency_s, tags=tags)


def track_rt_scorecard(overall_score: float, grade: str):
    """RT — Scorecard generated."""
    statsd.gauge(_metric("rt.scorecard.score"), overall_score)
    statsd.event(
        title="Red Team Scorecard Generated",
        text=f"Score: {overall_score}/100 — Grade: {grade}",
        tags=[f"grade:{grade}"],
        alert_type="info" if overall_score >= 70 else "warning",
    )


# ── APM Trace Decorator ──────────────────────────────

def traced(operation_name: str, resource: Optional[str] = None):
    """Decorator to wrap any function in a Datadog APM span."""
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            with tracer.trace(operation_name, resource=resource or func.__name__) as span:
                span.set_tag("nemesis.layer", operation_name.split(".")[0])
                try:
                    result = await func(*args, **kwargs)
                    span.set_tag("nemesis.success", True)
                    return result
                except Exception as e:
                    span.set_tag("nemesis.success", False)
                    span.set_tag("error.msg", str(e))
                    raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            with tracer.trace(operation_name, resource=resource or func.__name__) as span:
                span.set_tag("nemesis.layer", operation_name.split(".")[0])
                try:
                    result = func(*args, **kwargs)
                    span.set_tag("nemesis.success", True)
                    return result
                except Exception as e:
                    span.set_tag("nemesis.success", False)
                    span.set_tag("error.msg", str(e))
                    raise

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


# ── Latency Context Manager ──────────────────────────

@contextmanager
def measure_latency(metric_name: str, tags: list[str] | None = None):
    """Context manager to measure and emit latency."""
    start = time.perf_counter()
    yield
    elapsed_ms = (time.perf_counter() - start) * 1000
    statsd.histogram(_metric(metric_name), elapsed_ms, tags=tags or [])


# ── System Health Gauge (called on interval) ─────────

def emit_system_health(
    oracle_loaded: bool,
    nats_connected: bool,
    redis_connected: bool,
    blocked_ips_count: int,
    active_campaigns: int,
):
    """Periodic system health gauge — call every 30s via background task."""
    statsd.gauge(_metric("system.oracle_loaded"), int(oracle_loaded))
    statsd.gauge(_metric("system.nats_connected"), int(nats_connected))
    statsd.gauge(_metric("system.redis_connected"), int(redis_connected))
    statsd.gauge(_metric("system.blocked_ips"), blocked_ips_count)
    statsd.gauge(_metric("system.active_rt_campaigns"), active_campaigns)
```

---

### Datadog Dashboard JSON — config/datadog_nemesis_dashboard.json

```json
{
  "title": "Nemesis Defense System — Operational Dashboard",
  "description": "L1-L6 + Red Team metrics, SLA tracking, and threat intelligence",
  "widgets": [
    {
      "title": "L1 Firewall Blocks (5m)",
      "type": "timeseries",
      "query": "sum:nemesis.l1.firewall.blocks{*}.as_count()"
    },
    {
      "title": "L2 Inspector Verdicts",
      "type": "toplist",
      "query": "sum:nemesis.l2.inspector.requests{*} by {verdict}.as_count()"
    },
    {
      "title": "L2 Inspector Latency (p95)",
      "type": "timeseries",
      "query": "p95:nemesis.l2.inspector.latency_ms{*}"
    },
    {
      "title": "L3 Honeypot Hits by Path",
      "type": "toplist",
      "query": "sum:nemesis.l3.honeypot.hits{*} by {path}.as_count()"
    },
    {
      "title": "L4 Oracle Risk Score Distribution",
      "type": "distribution",
      "query": "avg:nemesis.l4.oracle.risk_score{*} by {classification}"
    },
    {
      "title": "L4 Model Accuracy",
      "type": "query_value",
      "query": "avg:nemesis.l4.oracle.model_accuracy{*}"
    },
    {
      "title": "L5 Canary Triggers",
      "type": "event_stream",
      "query": "tags:token:* Canary Token Triggered"
    },
    {
      "title": "L6 SAST/DAST Findings",
      "type": "timeseries",
      "query": "sum:nemesis.l6.sast.findings_critical{*}, sum:nemesis.l6.dast.findings{*}"
    },
    {
      "title": "Red Team Scorecard",
      "type": "query_value",
      "query": "avg:nemesis.rt.scorecard.score{*}"
    },
    {
      "title": "System Health",
      "type": "check_status",
      "query": "avg:nemesis.system.oracle_loaded{*}, avg:nemesis.system.nats_connected{*}, avg:nemesis.system.redis_connected{*}"
    },
    {
      "title": "Blocked IPs (Global)",
      "type": "geomap",
      "query": "sum:nemesis.l1.firewall.blocks{*} by {country}.as_count()"
    },
    {
      "title": "RT Scan Latency (p99)",
      "type": "timeseries",
      "query": "p99:nemesis.rt.scans.latency_s{*} by {scanner}"
    }
  ],
  "monitors": [
    {
      "name": "Nemesis Oracle Down",
      "type": "metric alert",
      "query": "avg(last_5m):avg:nemesis.system.oracle_loaded{*} < 1",
      "message": "@pagerduty-nemesis Oracle classifier is not loaded. L4 protection degraded."
    },
    {
      "name": "L2 Inspector High Latency",
      "type": "metric alert",
      "query": "avg(last_5m):p95:nemesis.l2.inspector.latency_ms{*} > 50",
      "message": "@slack-nemesis-alerts Inspector p95 latency > 50ms. Check model size or Redis cache."
    },
    {
      "name": "Canary Token Triggered",
      "type": "event alert",
      "query": "events('Canary Token Triggered').rollup('count').last('5m') > 0",
      "message": "@pagerduty-nemesis 🚨 Canary token fired. Possible intrusion. Investigate immediately."
    },
    {
      "name": "Red Team Score Below Threshold",
      "type": "metric alert",
      "query": "avg(last_1h):avg:nemesis.rt.scorecard.score{*} < 70",
      "message": "@slack-nemesis-alerts Security posture score dropped below 70. Review latest campaign."
    },
    {
      "name": "NATS Disconnected",
      "type": "metric alert",
      "query": "avg(last_5m):avg:nemesis.system.nats_connected{*} < 1",
      "message": "@pagerduty-nemesis NATS JetStream connection lost. Event pipeline down."
    },
    {
      "name": "Firewall Block Spike",
      "type": "metric alert",
      "query": "avg(last_5m):anomalies(sum:nemesis.l1.firewall.blocks{*}.as_count(), 'agile', 3) >= 1",
      "message": "@slack-nemesis-alerts Anomalous spike in firewall blocks. Possible DDoS or coordinated attack."
    }
  ]
}
```

---

### Datadog Monitor Terraform — terraform/datadog_monitors.tf

```hcl
# ── Datadog Provider ────────────────────────────────
terraform {
  required_providers {
    datadog = {
      source  = "DataDog/datadog"
      version = "~> 3.30"
    }
  }
}

provider "datadog" {
  api_key = var.dd_api_key
  app_key = var.dd_app_key
}

variable "dd_api_key" { sensitive = true }
variable "dd_app_key" { sensitive = true }

# ── Oracle Down ────────────────────────────────────
resource "datadog_monitor" "oracle_down" {
  name    = "Nemesis Oracle Classifier Down"
  type    = "metric alert"
  message = <<-EOT
    Oracle classifier not loaded. L4 threat detection degraded.
    @pagerduty-nemesis @slack-nemesis-alerts
  EOT
  query   = "avg(last_5m):avg:nemesis.system.oracle_loaded{*} < 1"
  monitor_thresholds {
    critical = 1
  }
  tags = ["team:security", "layer:L4", "system:nemesis"]
}

# ── Inspector Latency ─────────────────────────────
resource "datadog_monitor" "inspector_latency" {
  name    = "L2 Inspector p95 Latency > 50ms"
  type    = "metric alert"
  message = <<-EOT
    Inspector middleware p95 latency exceeded 50ms.
    Check Redis cache hit rate and model inference time.
    @slack-nemesis-alerts
  EOT
  query   = "avg(last_5m):p95:nemesis.l2.inspector.latency_ms{*} > 50"
  monitor_thresholds {
    critical = 50
    warning  = 30
  }
  tags = ["team:security", "layer:L2", "system:nemesis"]
}

# ── Canary Token ──────────────────────────────────
resource "datadog_monitor" "canary_trigger" {
  name    = "🚨 Canary Token Triggered"
  type    = "event-v2 alert"
  message = <<-EOT
    Canary token was accessed — possible intrusion.
    Investigate source IP immediately.
    @pagerduty-nemesis
  EOT
  query   = "events(\"Canary Token Triggered\").rollup(\"count\").last(\"5m\") > 0"
  tags = ["team:security", "layer:L5", "system:nemesis", "priority:P0"]
}

# ── NATS Disconnect ───────────────────────────────
resource "datadog_monitor" "nats_disconnect" {
  name    = "NATS JetStream Disconnected"
  type    = "metric alert"
  message = <<-EOT
    NATS connection lost. Nemesis event pipeline is down.
    @pagerduty-nemesis @slack-nemesis-alerts
  EOT
  query   = "avg(last_5m):avg:nemesis.system.nats_connected{*} < 1"
  monitor_thresholds {
    critical = 1
  }
  tags = ["team:security", "layer:L4", "system:nemesis"]
}

# ── Firewall Anomaly ──────────────────────────────
resource "datadog_monitor" "firewall_spike" {
  name    = "Firewall Block Anomaly Detected"
  type    = "metric alert"
  message = <<-EOT
    Anomalous spike in L1 firewall blocks.
    Possible DDoS or coordinated scanning.
    @slack-nemesis-alerts
  EOT
  query   = "avg(last_5m):anomalies(sum:nemesis.l1.firewall.blocks{*}.as_count(), 'agile', 3) >= 1"
  tags = ["team:security", "layer:L1", "system:nemesis"]
}
```

---

## PostHog Integration — Product Analytics, Feature Flags & Session Replay

### services/nemesis_posthog.py

```python
"""
Nemesis PostHog Integration
─────────────────────────────────────────────
Product analytics, feature flags, session replay hooks,
and security event tracking for the Nemesis admin UI
and customer-facing dashboards.

Prereqs:
  pip install posthog
  POSTHOG_API_KEY / POSTHOG_HOST in .env
"""

import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

import posthog

logger = logging.getLogger("nemesis.posthog")

# ── Init ──────────────────────────────────────────────

POSTHOG_API_KEY = os.getenv("POSTHOG_API_KEY", "")
POSTHOG_HOST = os.getenv("POSTHOG_HOST", "https://us.i.posthog.com")


def init_posthog():
    """Call once at FastAPI startup."""
    posthog.project_api_key = POSTHOG_API_KEY
    posthog.host = POSTHOG_HOST
    posthog.debug = os.getenv("POSTHOG_DEBUG", "false").lower() == "true"
    posthog.on_error = _on_posthog_error
    logger.info(f"PostHog initialized — host={POSTHOG_HOST}")


def _on_posthog_error(error, items):
    logger.error(f"PostHog error: {error} — items: {len(items)}")


def shutdown_posthog():
    """Call on FastAPI shutdown to flush queue."""
    posthog.shutdown()


# ── Identity / Group ─────────────────────────────────

def identify_user(
    user_id: str,
    email: str,
    name: str,
    tenant_id: str,
    role: str = "user",
    plan: Optional[str] = None,
):
    """Identify a user with properties for segmentation."""
    posthog.identify(
        user_id,
        {
            "email": email,
            "name": name,
            "role": role,
            "plan": plan or "unknown",
            "tenant_id": tenant_id,
        },
    )
    # Associate user with tenant group
    posthog.group_identify(
        "tenant", tenant_id, {"tenant_id": tenant_id, "plan": plan}
    )


def alias_user(previous_id: str, new_id: str):
    """Alias anonymous → authenticated user."""
    posthog.alias(previous_id, new_id)


# ── Event Tracking ───────────────────────────────────

def track(
    user_id: str,
    event: str,
    properties: Optional[Dict[str, Any]] = None,
    groups: Optional[Dict[str, str]] = None,
):
    """Generic event capture with optional group context."""
    posthog.capture(
        distinct_id=user_id,
        event=event,
        properties=properties or {},
        groups=groups or {},
    )


# ── Finance Guild Events ─────────────────────────────

def track_invoice_sent(user_id: str, tenant_id: str, amount: float, method: str):
    """Finance — Invoice sent (text-to-pay, email, etc.)."""
    track(
        user_id,
        "invoice_sent",
        {
            "amount": amount,
            "method": method,
            "currency": "USD",
        },
        groups={"tenant": tenant_id},
    )


def track_payment_received(user_id: str, tenant_id: str, amount: float, source: str):
    """Finance — Payment received."""
    track(
        user_id,
        "payment_received",
        {
            "amount": amount,
            "source": source,  # stripe, manual, etc.
            "$set": {"last_payment_date": datetime.now(timezone.utc).isoformat()},
        },
        groups={"tenant": tenant_id},
    )


def track_quote_generated(user_id: str, tenant_id: str, trade: str, ai_used: bool):
    """Finance — AI quote generated."""
    track(
        user_id,
        "quote_generated",
        {"trade_industry": trade, "ai_generated": ai_used},
        groups={"tenant": tenant_id},
    )


def track_dashboard_view(user_id: str, tenant_id: str, dashboard_name: str):
    """Finance — Dashboard viewed."""
    track(
        user_id,
        "dashboard_viewed",
        {"dashboard": dashboard_name},
        groups={"tenant": tenant_id},
    )


# ── Onboarding Funnel Events ─────────────────────────

def track_onboarding_step(
    user_id: str,
    tenant_id: str,
    step: str,
    step_number: int,
    completed: bool = True,
    duration_s: Optional[float] = None,
):
    """Onboarding — step completed or abandoned."""
    track(
        user_id,
        f"onboarding_{step}",
        {
            "step_number": step_number,
            "completed": completed,
            "duration_s": duration_s,
            "funnel": "finance_onboarding",
        },
        groups={"tenant": tenant_id},
    )


ONBOARDING_STEPS = [
    (1, "account_created"),
    (2, "integrations_connected"),
    (3, "profile_completed"),
    (4, "first_invoice_sent"),
    (5, "onboarding_completed"),
]


# ── Nemesis Security Events ──────────────────────────

def track_security_event(
    event_type: str,
    layer: str,
    severity: str,
    details: Dict[str, Any],
    source_ip: Optional[str] = None,
):
    """Security event — used by Nemesis layers for PostHog visibility."""
    posthog.capture(
        distinct_id="system:nemesis",
        event=f"nemesis_{event_type}",
        properties={
            "layer": layer,
            "severity": severity,
            "source_ip": source_ip or "unknown",
            **details,
        },
    )


def track_threat_blocked(ip: str, layer: str, threat_type: str, confidence: float):
    """Nemesis — threat blocked at any layer."""
    track_security_event(
        "threat_blocked",
        layer=layer,
        severity="high" if confidence > 0.8 else "medium",
        details={
            "threat_type": threat_type,
            "confidence": confidence,
            "ip": ip,
        },
        source_ip=ip,
    )


def track_rt_campaign_event(
    campaign_id: str, event_type: str, findings: int = 0, score: float = 0
):
    """Red Team — campaign lifecycle event."""
    posthog.capture(
        distinct_id="system:redteam",
        event=f"rt_campaign_{event_type}",
        properties={
            "campaign_id": campaign_id,
            "findings": findings,
            "score": score,
        },
    )


# ── Feature Flags ────────────────────────────────────

def is_feature_enabled(
    flag_key: str,
    user_id: str,
    default: bool = False,
    groups: Optional[Dict[str, str]] = None,
    properties: Optional[Dict[str, Any]] = None,
) -> bool:
    """Check PostHog feature flag for user."""
    try:
        return posthog.feature_enabled(
            flag_key,
            user_id,
            groups=groups or {},
            person_properties=properties or {},
        )
    except Exception as e:
        logger.warning(f"Feature flag check failed for {flag_key}: {e}")
        return default


def get_feature_payload(
    flag_key: str, user_id: str, default: Any = None
) -> Any:
    """Get feature flag payload (JSON) for dynamic config."""
    try:
        return posthog.get_feature_flag_payload(flag_key, user_id) or default
    except Exception as e:
        logger.warning(f"Feature flag payload failed for {flag_key}: {e}")
        return default


# ── Predefined Feature Flags ─────────────────────────
# Create these in PostHog dashboard:

FEATURE_FLAGS = {
    "nemesis_ai_inspector_v2": "Enables v2 of the AI inspector model (A/B test)",
    "finance_text_to_pay": "Enables text-to-pay SMS invoicing",
    "finance_ai_quotes": "Enables AI quote generation",
    "finance_recurring_billing": "Enables recurring billing automation",
    "finance_multi_currency": "Enables multi-currency support",
    "finance_batch_operations": "Enables batch invoice/payment operations",
    "nemesis_redteam_auto": "Enables automatic Red Team campaign scheduling",
    "dashboard_dark_mode": "Enables dark mode for dashboards",
    "onboarding_v2": "Enables the new 5-step onboarding wizard",
}


def check_finance_features(user_id: str, tenant_id: str) -> Dict[str, bool]:
    """Return all finance feature flag states for a user."""
    groups = {"tenant": tenant_id}
    return {
        key: is_feature_enabled(key, user_id, groups=groups)
        for key in FEATURE_FLAGS
        if key.startswith("finance_")
    }


# ── Session Replay Hooks ─────────────────────────────
# PostHog session replay runs client-side (JS/React).
# These server-side hooks tag sessions for filtering.

def tag_session_security_event(
    user_id: str, session_id: str, event_type: str, severity: str
):
    """Tag a session with a security event for replay filtering."""
    track(
        user_id,
        "$session_security_tag",
        {
            "$session_id": session_id,
            "security_event_type": event_type,
            "severity": severity,
        },
    )


def tag_session_error(
    user_id: str, session_id: str, error_type: str, error_msg: str
):
    """Tag a session with an error for replay filtering."""
    track(
        user_id,
        "$session_error_tag",
        {
            "$session_id": session_id,
            "error_type": error_type,
            "error_message": error_msg[:500],
        },
    )
```

---

### PostHog Client-Side Setup — frontend/src/lib/posthog.ts

```javascript
// PostHog client-side initialization for React + session replay
// Place in your app's entry point (App.tsx or main.tsx)

import posthog from 'posthog-js';
import { PostHogProvider } from 'posthog-js/react';

// ── Init ──────────────────────────────────────────
const POSTHOG_KEY = import.meta.env.VITE_POSTHOG_KEY;
const POSTHOG_HOST = import.meta.env.VITE_POSTHOG_HOST || 'https://us.i.posthog.com';

export function initPostHog() {
  if (!POSTHOG_KEY) return;

  posthog.init(POSTHOG_KEY, {
    api_host: POSTHOG_HOST,
    // Session replay
    session_recording: {
      maskAllInputs: true,           // PCI compliance — mask card fields
      maskTextSelector: '.ph-mask',  // custom mask class
      recordCrossOriginIframes: false,
    },
    // Autocapture
    autocapture: true,
    capture_pageview: true,
    capture_pageleave: true,
    // Performance
    loaded: (ph) => {
      // Disable in dev
      if (import.meta.env.DEV) ph.opt_out_capturing();
    },
    // Privacy
    respect_dnt: true,
    persistence: 'localStorage+cookie',
  });
}

// ── Identify after login ─────────────────────────
export function identifyUser(
  userId: string,
  email: string,
  name: string,
  tenantId: string,
  plan: string,
  role: string = 'user'
) {
  posthog.identify(userId, {
    email,
    name,
    role,
    plan,
    tenant_id: tenantId,
  });
  posthog.group('tenant', tenantId, {
    plan,
    tenant_id: tenantId,
  });
}

// ── Feature flag hooks ───────────────────────────
export function useFinanceFeatures() {
  return {
    textToPay: posthog.isFeatureEnabled('finance_text_to_pay'),
    aiQuotes: posthog.isFeatureEnabled('finance_ai_quotes'),
    recurringBilling: posthog.isFeatureEnabled('finance_recurring_billing'),
    multiCurrency: posthog.isFeatureEnabled('finance_multi_currency'),
    batchOps: posthog.isFeatureEnabled('finance_batch_operations'),
    darkMode: posthog.isFeatureEnabled('dashboard_dark_mode'),
    onboardingV2: posthog.isFeatureEnabled('onboarding_v2'),
  };
}

// ── Track finance events ─────────────────────────
export const financeEvents = {
  invoiceSent: (amount: number, method: string) =>
    posthog.capture('invoice_sent', { amount, method, currency: 'USD' }),

  paymentReceived: (amount: number, source: string) =>
    posthog.capture('payment_received', { amount, source }),

  quoteGenerated: (trade: string, aiUsed: boolean) =>
    posthog.capture('quote_generated', { trade_industry: trade, ai_generated: aiUsed }),

  dashboardViewed: (name: string) =>
    posthog.capture('dashboard_viewed', { dashboard: name }),

  onboardingStep: (step: string, stepNumber: number, durationS?: number) =>
    posthog.capture(`onboarding_${step}`, {
      step_number: stepNumber,
      funnel: 'finance_onboarding',
      duration_s: durationS,
    }),
};

// ── Nemesis admin events (admin dashboard only) ──
export const nemesisEvents = {
  threatViewed: (threatId: string, layer: string) =>
    posthog.capture('nemesis_threat_viewed', { threat_id: threatId, layer }),

  campaignStarted: (campaignId: string, type: string) =>
    posthog.capture('rt_campaign_started_ui', { campaign_id: campaignId, type }),

  dashboardFiltered: (filter: string, value: string) =>
    posthog.capture('nemesis_dashboard_filtered', { filter, value }),
};

export { posthog, PostHogProvider };
```

---

### services/nemesis_diagnostics.py — Unified Health & Diagnostic Endpoint

```python
"""
Nemesis Diagnostics — Unified health check that queries both
Datadog and PostHog status and returns a single diagnostic payload.
Mounted at: /api/nemesis/diagnostics
"""

import os
import time
import asyncio
import logging
from typing import Dict, Any
from datetime import datetime, timezone

import httpx
from datadog import api as dd_api
import posthog

logger = logging.getLogger("nemesis.diagnostics")


# ── Component Health Checks ─────────────────────────

async def check_datadog_agent() -> Dict[str, Any]:
    """Verify Datadog Agent is reachable and accepting metrics."""
    dd_host = os.getenv("DD_AGENT_HOST", "127.0.0.1")
    dd_port = int(os.getenv("DD_TRACE_AGENT_PORT", 8126))
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"http://{dd_host}:{dd_port}/info")
            info = resp.json() if resp.status_code == 200 else {}
            return {
                "status": "healthy" if resp.status_code == 200 else "degraded",
                "agent_version": info.get("version", "unknown"),
                "endpoint": f"{dd_host}:{dd_port}",
                "latency_ms": resp.elapsed.total_seconds() * 1000,
            }
    except Exception as e:
        return {"status": "down", "error": str(e), "endpoint": f"{dd_host}:{dd_port}"}


async def check_datadog_api() -> Dict[str, Any]:
    """Verify Datadog API key is valid."""
    try:
        result = dd_api.DashboardList.get_all()
        return {
            "status": "healthy",
            "api_key_valid": True,
            "dashboard_count": len(result.get("dashboard_lists", [])),
        }
    except Exception as e:
        return {"status": "error", "api_key_valid": False, "error": str(e)}


async def check_posthog() -> Dict[str, Any]:
    """Verify PostHog is reachable and accepting events."""
    ph_host = os.getenv("POSTHOG_HOST", "https://us.i.posthog.com")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Health check endpoint
            resp = await client.get(f"{ph_host}/_health")
            healthy = resp.status_code == 200

            # Test feature flags endpoint
            flags_resp = await client.post(
                f"{ph_host}/decide/?v=3",
                json={
                    "api_key": os.getenv("POSTHOG_API_KEY", ""),
                    "distinct_id": "system:diagnostic",
                },
            )
            flags_ok = flags_resp.status_code == 200
            flags_data = flags_resp.json() if flags_ok else {}

            return {
                "status": "healthy" if healthy else "degraded",
                "host": ph_host,
                "health_latency_ms": resp.elapsed.total_seconds() * 1000,
                "feature_flags_active": len(flags_data.get("featureFlags", {})),
                "session_recording_enabled": flags_data.get(
                    "sessionRecording", False
                ),
            }
    except Exception as e:
        return {"status": "down", "host": ph_host, "error": str(e)}


async def check_dogstatsd() -> Dict[str, Any]:
    """Verify DogStatsD UDP port is accepting packets."""
    import socket

    dd_host = os.getenv("DD_AGENT_HOST", "127.0.0.1")
    dd_port = int(os.getenv("DD_DOGSTATSD_PORT", 8125))
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2)
        # Send a test gauge
        test_metric = b"nemesis.diagnostic.ping:1|g|#source:diagnostic"
        sock.sendto(test_metric, (dd_host, dd_port))
        sock.close()
        return {"status": "healthy", "endpoint": f"{dd_host}:{dd_port}"}
    except Exception as e:
        return {"status": "down", "endpoint": f"{dd_host}:{dd_port}", "error": str(e)}


# ── Metric Summary (last N minutes from Datadog) ────

async def get_metric_summary(minutes: int = 60) -> Dict[str, Any]:
    """Pull key Nemesis metrics from Datadog for the diagnostic payload."""
    now = int(time.time())
    start = now - (minutes * 60)
    metrics = {}

    queries = {
        "firewall_blocks": "sum:nemesis.l1.firewall.blocks{*}.as_count()",
        "inspector_requests": "sum:nemesis.l2.inspector.requests{*}.as_count()",
        "inspector_blocks": "sum:nemesis.l2.inspector.blocks{*}.as_count()",
        "inspector_p95_ms": "p95:nemesis.l2.inspector.latency_ms{*}",
        "honeypot_hits": "sum:nemesis.l3.honeypot.hits{*}.as_count()",
        "oracle_accuracy": "avg:nemesis.l4.oracle.model_accuracy{*}",
        "rt_score": "avg:nemesis.rt.scorecard.score{*}",
        "blocked_ips": "avg:nemesis.system.blocked_ips{*}",
    }

    for key, query in queries.items():
        try:
            result = dd_api.Metric.query(start=start, end=now, query=query)
            series = result.get("series", [])
            if series and series[0].get("pointlist"):
                points = series[0]["pointlist"]
                metrics[key] = round(points[-1][1], 2)  # latest value
            else:
                metrics[key] = None
        except Exception:
            metrics[key] = None

    return {"window_minutes": minutes, "metrics": metrics}


# ── Full Diagnostic Payload ──────────────────────────

async def run_full_diagnostic() -> Dict[str, Any]:
    """Run all diagnostic checks in parallel and return unified payload."""
    start = time.perf_counter()

    (
        dd_agent,
        dd_api_status,
        dd_statsd,
        ph_status,
        metric_summary,
    ) = await asyncio.gather(
        check_datadog_agent(),
        check_datadog_api(),
        check_dogstatsd(),
        check_posthog(),
        get_metric_summary(minutes=60),
        return_exceptions=True,
    )

    # Handle any exceptions that leaked through
    def safe(result):
        if isinstance(result, Exception):
            return {"status": "error", "error": str(result)}
        return result

    elapsed_ms = (time.perf_counter() - start) * 1000

    all_healthy = all(
        safe(r).get("status") == "healthy"
        for r in [dd_agent, dd_api_status, dd_statsd, ph_status]
    )

    return {
        "diagnostic_run_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": "healthy" if all_healthy else "degraded",
        "diagnostic_latency_ms": round(elapsed_ms, 1),
        "components": {
            "datadog_agent": safe(dd_agent),
            "datadog_api": safe(dd_api_status),
            "dogstatsd": safe(dd_statsd),
            "posthog": safe(ph_status),
        },
        "metric_summary": safe(metric_summary),
        "env": {
            "DD_ENV": os.getenv("DD_ENV", "production"),
            "DD_SERVICE": "nemesis-defense",
            "DD_VERSION": os.getenv("DD_VERSION", "1.0.0"),
            "POSTHOG_HOST": os.getenv("POSTHOG_HOST", "https://us.i.posthog.com"),
        },
    }
```

---

### routes/nemesis_diagnostics_api.py — FastAPI Router

```python
"""
FastAPI routes for Nemesis diagnostics.
Mount in main.py alongside other Nemesis routes.
"""

from fastapi import APIRouter, Depends, HTTPException
from services.nemesis_diagnostics import run_full_diagnostic
from middleware.nemesis_inspector import require_admin_token

router = APIRouter(prefix="/api/nemesis/diagnostics", tags=["Nemesis Diagnostics"])


@router.get("/health")
async def diagnostics_health():
    """Quick liveness — no auth required."""
    return {"status": "ok", "service": "nemesis-diagnostics"}


@router.get("/full", dependencies=[Depends(require_admin_token)])
async def full_diagnostic():
    """
    Full diagnostic payload — Datadog Agent, API, DogStatsD,
    PostHog, and 60-min metric summary.
    Requires NEMESIS_ADMIN_TOKEN.
    """
    try:
        result = await run_full_diagnostic()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Diagnostic failed: {str(e)}")


@router.get("/metrics", dependencies=[Depends(require_admin_token)])
async def metric_snapshot(minutes: int = 60):
    """Pull metric summary from Datadog for the last N minutes."""
    from services.nemesis_diagnostics import get_metric_summary
    return await get_metric_summary(minutes=minutes)


@router.get("/posthog/flags", dependencies=[Depends(require_admin_token)])
async def posthog_flags(user_id: str = "system:diagnostic"):
    """Return all active PostHog feature flags for a given user."""
    import posthog as ph
    try:
        flags = ph.get_all_flags(user_id)
        return {"user_id": user_id, "flags": flags}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PostHog flags error: {str(e)}")
```

---

### Wire-Up — Append to main.py Mount Block

```python
# ── Datadog + PostHog Diagnostics ─────────────────
if os.getenv("NEMESIS_ENABLED") == "true":
    from services.nemesis_datadog import init_datadog
    from services.nemesis_posthog import init_posthog, shutdown_posthog
    from routes.nemesis_diagnostics_api import router as diag_router

    init_datadog()
    init_posthog()

    app.include_router(diag_router)

    @app.on_event("shutdown")
    async def _shutdown_observability():
        shutdown_posthog()
```

---

### .env Additions

```bash
# ── Datadog ────────────────────────────────────────
DD_AGENT_HOST=127.0.0.1
DD_DOGSTATSD_PORT=8125
DD_TRACE_AGENT_PORT=8126
DD_API_KEY=[YOUR_DD_API_KEY]
DD_APP_KEY=[YOUR_DD_APP_KEY]
DD_ENV=production
DD_SERVICE=nemesis-defense
DD_VERSION=1.0.0

# ── PostHog ────────────────────────────────────────
POSTHOG_API_KEY=phc_[YOUR_KEY]
POSTHOG_HOST=https://us.i.posthog.com
POSTHOG_DEBUG=false
```

---

### File Map Addition

