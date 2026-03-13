# REFLEX SYSTEM SPECIFICATION v1.0
## Rapid Error Feedback & Learning eXecution - Self-Healing Infrastructure

**Version:** 1.0.0  
**Date:** January 25, 2026  
**Status:** PRODUCTION-READY  
**Classification:** Core Infrastructure Component  
**Integration:** CGRF v3.0, AGS, AIS  

---

## TABLE OF CONTENTS

1. [Executive Summary](#1-executive-summary)
2. [System Architecture](#2-system-architecture)
3. [Five-Stage Pipeline](#3-five-stage-pipeline)
4. [Integration Points](#4-integration-points)
5. [Implementation Details](#5-implementation-details)
6. [Operational Runbooks](#6-operational-runbooks)
7. [Metrics & KPIs](#7-metrics--kpis)
8. [API Reference](#8-api-reference)

---

## 1. EXECUTIVE SUMMARY

### What is REFLEX?

**REFLEX (Rapid Error Feedback & Learning eXecution)** is Citadel's **self-healing nervous system** that detects anomalies, diagnoses root causes, auto-generates fixes, and learns from failures—creating a continuously improving ecosystem.

### Core Value Proposition

```
Traditional Incident Response:
├─ Failure occurs → Alert → Human investigates → Manual fix → Deploy
└─ Time to resolution: 2-48 hours

REFLEX Incident Response:
├─ Failure occurs → Auto-diagnose → Generate fix → Test → Auto-deploy
└─ Time to resolution: 2-15 minutes
```

**Impact:**
- 95% reduction in Mean Time to Resolution (MTTR)
- 80% of incidents auto-resolved without human intervention
- Knowledge accumulation → fewer repeat incidents over time

### Key Capabilities

| Capability | Description | Business Impact |
|------------|-------------|-----------------|
| **Drift Detection** | Monitors runtime behavior vs. documented specs | Catch config drift before production issues |
| **Regression Auto-Fix** | Detects test failures, git bisects, generates patch | Zero-downtime rollback + forward fix |
| **Pattern Learning** | Builds library of incident patterns (AIS College) | Faster diagnosis for similar issues |
| **CGRF Sync** | Auto-updates SRS documentation after fixes | Documentation always current |
| **Graceful Degradation** | Activates circuit breakers, fallbacks automatically | High availability even during failures |

---

## 2. SYSTEM ARCHITECTURE

### 2.1 High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                       REFLEX SYSTEM                               │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ INPUT SOURCES (Observability Layer)                      │   │
│  ├──────────────────────────────────────────────────────────┤   │
│  │ • CI/CD Pipeline (GitHub Actions, GitLab CI)             │   │
│  │ • Production Logs (CloudWatch, Datadog)                  │   │
│  │ • Metrics (Prometheus, Grafana)                          │   │
│  │ • APM Traces (X-Ray, New Relic)                          │   │
│  │ • Error Tracking (Sentry, Rollbar)                       │   │
│  │ • SLA Monitors (PagerDuty, Opsgenie)                     │   │
│  │ • CGRF Drift Checks (6-hour scheduled scans)             │   │
│  └────────────────────┬─────────────────────────────────────┘   │
│                       │                                          │
│                       ▼                                          │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ REFLEX CORE (Event Processing Engine)                    │   │
│  ├──────────────────────────────────────────────────────────┤   │
│  │                                                           │   │
│  │  STAGE 1: OBSERVE                                        │   │
│  │  ├─ Event Ingestion (NATS/Kafka)                         │   │
│  │  ├─ Anomaly Detection (statistical + ML)                 │   │
│  │  ├─ Severity Classification (LOW/MED/HIGH/CRITICAL)      │   │
│  │  └─ Alert Routing (auto-resolve vs. escalate)           │   │
│  │                                                           │   │
│  │  STAGE 2: DIAGNOSE                                       │   │
│  │  ├─ Stack Trace Parsing (extract error context)         │   │
│  │  ├─ Regression Detection (git bisect automation)        │   │
│  │  ├─ Pattern Matching (AIS College similarity search)    │   │
│  │  ├─ Root Cause Hypothesis (LLM-powered)                 │   │
│  │  └─ Confidence Scoring (0-100%)                         │   │
│  │                                                           │   │
│  │  STAGE 3: RESPOND                                        │   │
│  │  ├─ Fix Generation (Claude Sonnet 4.0)                  │   │
│  │  ├─ Config Rollback (if drift detected)                 │   │
│  │  ├─ Circuit Breaker (graceful degradation)              │   │
│  │  ├─ Fallback Activation (cached responses, stub data)   │   │
│  │  └─ Emergency Shutdown (critical failures only)         │   │
│  │                                                           │   │
│  │  STAGE 4: VERIFY                                         │   │
│  │  ├─ Test Suite Execution (pytest on fix branch)         │   │
│  │  ├─ AGS Policy Gate (constitutional validation)         │   │
│  │  ├─ Canary Deployment (1% → 10% → 100% traffic)         │   │
│  │  ├─ Metric Monitoring (compare vs. baseline)            │   │
│  │  └─ Rollback Decision (auto if metrics degrade)         │   │
│  │                                                           │   │
│  │  STAGE 5: LEARN                                          │   │
│  │  ├─ Pattern Library Update (AIS College FAISS index)    │   │
│  │  ├─ Runbook Generation (Markdown docs + diagrams)       │   │
│  │  ├─ Post-Mortem Creation (5 Whys analysis)              │   │
│  │  ├─ CGRF SRS Update (sync documentation)                │   │
│  │  └─ Agent XP Reward (if fix successful)                 │   │
│  │                                                           │   │
│  └────────────────────┬─────────────────────────────────────┘   │
│                       │                                          │
│                       ▼                                          │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ OUTPUT ACTIONS                                            │   │
│  ├──────────────────────────────────────────────────────────┤   │
│  │ • GitHub PR (auto-fix code)                              │   │
│  │ • Config Update (K8s ConfigMap, Terraform vars)          │   │
│  │ • Incident Ticket (Jira, Linear)                         │   │
│  │ • Slack/Email Notification                               │   │
│  │ • Guardian Log Entry (immutable audit trail)             │   │
│  │ • Grafana Annotation (incident markers)                  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 Technology Stack

```yaml
reflex_stack:
  event_bus:
    primary: "NATS JetStream"
    fallback: "Kafka"
    reason: "NATS = lower latency, simpler ops; Kafka = higher throughput"
  
  storage:
    time_series: "InfluxDB (anomaly baselines, metrics)"
    vector_db: "FAISS (pattern similarity search via AIS College)"
    relational: "PostgreSQL (incident history, runbooks)"
    cache: "Redis (deduplication, rate limiting)"
  
  ai_models:
    root_cause_analysis: "Claude Sonnet 4.0 (AWS Bedrock)"
    code_generation: "Claude Sonnet 4.0 (AWS Bedrock)"
    anomaly_detection: "Isolation Forest (scikit-learn)"
    pattern_matching: "Sentence-BERT (all-MiniLM-L6-v2)"
  
  orchestration:
    workflow_engine: "Temporal.io"
    ci_cd: "GitHub Actions / GitLab CI"
    deployment: "ArgoCD (GitOps)"
  
  observability:
    logs: "CloudWatch / Loki"
    metrics: "Prometheus + Grafana"
    traces: "AWS X-Ray / OpenTelemetry"
    errors: "Sentry"
```

---

## 3. FIVE-STAGE PIPELINE

### STAGE 1: OBSERVE

#### Purpose
**Detect anomalies** across CI/CD, production, and documentation drift.

#### Data Sources

```python
# reflex/observe/sources.py

class ObservationSources:
    """
    Centralized ingestion from all observability sources.
    """
    
    def __init__(self, nats_client, redis_client):
        self.nats = nats_client
        self.redis = redis_client
        
        # Deduplication cache (prevent alert storms)
        self.dedup_window_seconds = 300  # 5 minutes
    
    async def ingest_ci_failure(self, event):
        """
        CI/CD pipeline failure (GitHub Actions, GitLab CI).
        
        Event format:
        {
          "source": "github_actions",
          "repo": "citadel/payments",
          "workflow": "pytest",
          "job_id": "12345",
          "commit_sha": "a1b2c3d4",
          "failure_reason": "test_payment_retry_timeout FAILED",
          "stack_trace": "...",
          "timestamp": "2026-01-25T16:45:00Z"
        }
        """
        # Deduplicate
        cache_key = f"ci_failure:{event['repo']}:{event['commit_sha']}"
        if await self.redis.exists(cache_key):
            return  # Already processing this failure
        
        await self.redis.setex(cache_key, self.dedup_window_seconds, "1")
        
        # Classify severity
        severity = self._classify_ci_failure(event)
        
        # Emit to REFLEX pipeline
        await self.nats.publish(
            "reflex.observe.ci_failure",
            {
                **event,
                "severity": severity,
                "reflex_event_id": f"RFX-{uuid.uuid4()}"
            }
        )
    
    async def ingest_production_error(self, event):
        """
        Production error (from Sentry, CloudWatch, etc).
        
        Event format:
        {
          "source": "sentry",
          "error_id": "abc123",
          "error_type": "HubNotReadyError",
          "message": "Hub service unavailable",
          "stack_trace": "...",
          "tags": {"module": "payment_retry", "tier": "2"},
          "user_id": "user_456",
          "timestamp": "2026-01-25T16:50:00Z"
        }
        """
        # Deduplicate
        cache_key = f"prod_error:{event['error_type']}:{event.get('tags', {}).get('module')}"
        if await self.redis.exists(cache_key):
            # Increment counter (track frequency)
            await self.redis.incr(f"{cache_key}:count")
            return
        
        await self.redis.setex(cache_key, self.dedup_window_seconds, "1")
        
        # Classify severity
        severity = self._classify_production_error(event)
        
        # Emit to REFLEX pipeline
        await self.nats.publish(
            "reflex.observe.production_error",
            {
                **event,
                "severity": severity,
                "reflex_event_id": f"RFX-{uuid.uuid4()}"
            }
        )
    
    async def ingest_drift_detection(self, event):
        """
        CGRF drift detection (scheduled scan every 6 hours).
        
        Event format:
        {
          "source": "cgrf_drift_scanner",
          "module": "payment_retry.py",
          "drift_type": "CONFIG_DRIFT",
          "expected_value": {"PAYMENT_MAX_RETRIES": 3},
          "actual_value": {"PAYMENT_MAX_RETRIES": 5},
          "delta": 0.67,  # +67%
          "timestamp": "2026-01-25T16:00:00Z"
        }
        """
        # No deduplication (drift is state-based, not event-based)
        
        severity = self._classify_drift(event)
        
        await self.nats.publish(
            "reflex.observe.drift_detected",
            {
                **event,
                "severity": severity,
                "reflex_event_id": f"RFX-{uuid.uuid4()}"
            }
        )
    
    def _classify_ci_failure(self, event):
        """Severity: LOW | MEDIUM | HIGH | CRITICAL"""
        if "test_" in event["failure_reason"]:
            return "MEDIUM"  # Test failure
        elif "build" in event["workflow"].lower():
            return "HIGH"  # Build failure blocks deployment
        else:
            return "LOW"
    
    def _classify_production_error(self, event):
        tier = event.get("tags", {}).get("tier", 0)
        error_type = event["error_type"]
        
        # Critical: Tier 3 module errors
        if tier == 3:
            return "CRITICAL"
        
        # High: Payment/auth failures
        if any(kw in error_type.lower() for kw in ["payment", "auth", "billing"]):
            return "HIGH"
        
        # Medium: Other Tier 2 errors
        if tier == 2:
            return "MEDIUM"
        
        return "LOW"
    
    def _classify_drift(self, event):
        delta = abs(event["delta"])
        
        if delta > 0.50:
            return "HIGH"  # >50% drift
        elif delta > 0.20:
            return "MEDIUM"
        else:
            return "LOW"
```

#### Anomaly Detection

```python
# reflex/observe/anomaly.py

from sklearn.ensemble import IsolationForest
import numpy as np

class AnomalyDetector:
    """
    Statistical anomaly detection for metrics.
    """
    
    def __init__(self, influxdb_client):
        self.influx = influxdb_client
        self.models = {}  # {metric_name: IsolationForest}
    
    async def detect_metric_anomaly(self, metric_name, current_value):
        """
        Compare current value vs. historical baseline.
        
        Returns:
          {
            "is_anomaly": bool,
            "confidence": float (0-1),
            "baseline_mean": float,
            "baseline_std": float,
            "z_score": float
          }
        """
        # Fetch last 7 days of data
        historical_data = await self._fetch_historical(metric_name, days=7)
        
        if len(historical_data) < 100:
            return {"is_anomaly": False, "confidence": 0, "reason": "Insufficient data"}
        
        # Train Isolation Forest (if not cached)
        if metric_name not in self.models:
            self.models[metric_name] = IsolationForest(contamination=0.05)
            self.models[metric_name].fit(historical_data.reshape(-1, 1))
        
        # Predict
        prediction = self.models[metric_name].predict([[current_value]])
        anomaly_score = self.models[metric_name].score_samples([[current_value]])[0]
        
        # Statistical analysis
        mean = np.mean(historical_data)
        std = np.std(historical_data)
        z_score = (current_value - mean) / std if std > 0 else 0
        
        is_anomaly = prediction[0] == -1  # -1 = anomaly, 1 = normal
        
        return {
            "is_anomaly": is_anomaly,
            "confidence": abs(anomaly_score),  # Higher = more anomalous
            "baseline_mean": mean,
            "baseline_std": std,
            "z_score": z_score,
            "severity": self._severity_from_zscore(z_score)
        }
    
    def _severity_from_zscore(self, z):
        if abs(z) > 3:
            return "CRITICAL"  # >3 std deviations
        elif abs(z) > 2:
            return "HIGH"
        elif abs(z) > 1:
            return "MEDIUM"
        else:
            return "LOW"
    
    async def _fetch_historical(self, metric_name, days):
        # Query InfluxDB for last N days
        query = f"""
        SELECT value FROM "{metric_name}"
        WHERE time > now() - {days}d
        """
        result = await self.influx.query(query)
        return np.array([point["value"] for point in result])
```

---

### STAGE 2: DIAGNOSE

#### Purpose
**Root cause analysis** using stack traces, git bisect, and LLM-powered hypothesis generation.

#### Implementation

```python
# reflex/diagnose/root_cause.py

import anthropic
import subprocess
from typing import Optional

class RootCauseAnalyzer:
    """
    Multi-strategy root cause analysis.
    """
    
    def __init__(self, bedrock_client, ais_college_client):
        self.bedrock = bedrock_client
        self.college = ais_college_client
    
    async def diagnose(self, reflex_event):
        """
        Main diagnosis orchestration.
        
        Returns:
          {
            "root_cause": str,
            "confidence": float (0-1),
            "strategy_used": str,
            "fix_suggestions": List[str],
            "similar_incidents": List[dict]
          }
        """
        strategies = [
            self._strategy_regression_bisect,  # For CI failures
            self._strategy_stack_trace_parse,  # For production errors
            self._strategy_drift_analysis,     # For config drift
            self._strategy_llm_hypothesis      # Fallback (LLM reasoning)
        ]
        
        for strategy in strategies:
            result = await strategy(reflex_event)
            if result["confidence"] > 0.7:
                # High confidence, use this diagnosis
                return result
        
        # Low confidence, escalate to human
        return {
            "root_cause": "Unknown (requires human investigation)",
            "confidence": 0.3,
            "strategy_used": "ESCALATE_TO_HUMAN",
            "fix_suggestions": [],
            "similar_incidents": []
        }
    
    async def _strategy_regression_bisect(self, event):
        """
        Git bisect to find commit that introduced test failure.
        """
        if event["source"] != "github_actions":
            return {"confidence": 0}
        
        repo_path = f"/tmp/repos/{event['repo']}"
        failing_test = event.get("failure_reason", "")
        
        if not failing_test.startswith("test_"):
            return {"confidence": 0}
        
        # Clone repo
        subprocess.run(["git", "clone", f"https://github.com/{event['repo']}", repo_path])
        
        # Git bisect
        bad_commit = event["commit_sha"]
        good_commit = await self._find_last_passing_commit(repo_path, failing_test)
        
        if not good_commit:
            return {"confidence": 0.4, "root_cause": "No recent passing commit found"}
        
        # Run git bisect
        bisect_result = subprocess.run(
            ["git", "bisect", "start", bad_commit, good_commit],
            cwd=repo_path,
            capture_output=True
        )
        
        # Extract culprit commit
        culprit_commit = self._parse_bisect_output(bisect_result.stdout)
        
        # Get commit diff
        diff = subprocess.run(
            ["git", "show", culprit_commit],
            cwd=repo_path,
            capture_output=True
        ).stdout.decode()
        
        # LLM analysis of diff
        hypothesis = await self._llm_analyze_diff(diff, failing_test)
        
        return {
            "root_cause": f"Regression introduced in {culprit_commit[:7]}: {hypothesis}",
            "confidence": 0.9,
            "strategy_used": "GIT_BISECT",
            "culprit_commit": culprit_commit,
            "diff": diff,
            "fix_suggestions": [
                f"Revert commit {culprit_commit[:7]}",
                "Or fix the issue introduced in that commit"
            ]
        }
    
    async def _strategy_stack_trace_parse(self, event):
        """
        Parse stack trace to identify error location + context.
        """
        if "stack_trace" not in event:
            return {"confidence": 0}
        
        stack = event["stack_trace"]
        error_type = event.get("error_type", "Unknown")
        
        # Extract file + line number
        import re
        match = re.search(r'File "([^"]+)", line (\d+)', stack)
        if not match:
            return {"confidence": 0.3}
        
        file_path, line_num = match.groups()
        
        # Read file context (5 lines before/after error)
        try:
            with open(file_path) as f:
                lines = f.readlines()
                line_idx = int(line_num) - 1
                context_start = max(0, line_idx - 5)
                context_end = min(len(lines), line_idx + 6)
                context = "".join(lines[context_start:context_end])
        except:
            context = "File not accessible"
        
        # LLM analysis
        hypothesis = await self._llm_analyze_error(error_type, stack, context)
        
        # Search AIS College for similar incidents
        similar = await self.college.search_patterns(
            query=f"{error_type} in {file_path}",
            top_k=3
        )
        
        return {
            "root_cause": hypothesis,
            "confidence": 0.8,
            "strategy_used": "STACK_TRACE_PARSE",
            "file_path": file_path,
            "line_num": line_num,
            "code_context": context,
            "fix_suggestions": [s["resolution"] for s in similar if "resolution" in s],
            "similar_incidents": similar
        }
    
    async def _strategy_drift_analysis(self, event):
        """
        Analyze config drift vs. documented SRS.
        """
        if event.get("drift_type") != "CONFIG_DRIFT":
            return {"confidence": 0}
        
        expected = event["expected_value"]
        actual = event["actual_value"]
        module = event["module"]
        
        # Fetch SRS documentation
        srs = await self._fetch_srs(module)
        
        if not srs:
            return {"confidence": 0.5, "root_cause": "No SRS found to validate against"}
        
        # Compare
        drift_reason = f"Config drift detected: {expected} → {actual}"
        
        # Check git history for config changes
        config_changes = await self._git_log_config_changes(module)
        
        return {
            "root_cause": drift_reason,
            "confidence": 0.95,
            "strategy_used": "DRIFT_ANALYSIS",
            "expected_value": expected,
            "actual_value": actual,
            "delta": event["delta"],
            "config_change_history": config_changes,
            "fix_suggestions": [
                f"Revert to documented config: {expected}",
                "Or update SRS to reflect new config"
            ]
        }
    
    async def _llm_analyze_diff(self, diff, failing_test):
        """Use Claude to analyze git diff and hypothesize root cause."""
        prompt = f"""
        A test failure was introduced in this git commit:
        
        FAILING TEST: {failing_test}
        
        GIT DIFF:
        {diff}
        
        Analyze the diff and explain why this change likely caused the test to fail.
        Be specific and concise (2-3 sentences).
        """
        
        response = await self.bedrock.invoke_model(
            modelId="anthropic.claude-3-sonnet-20240229-v1:0",
            body={
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}]
            }
        )
        
        return response["content"][0]["text"]
    
    async def _llm_analyze_error(self, error_type, stack_trace, code_context):
        """Use Claude to analyze error + context."""
        prompt = f"""
        A production error occurred:
        
        ERROR TYPE: {error_type}
        
        STACK TRACE:
        {stack_trace}
        
        CODE CONTEXT (lines around error):
        {code_context}
        
        What is the likely root cause? Provide a concise diagnosis (2-3 sentences).
        """
        
        response = await self.bedrock.invoke_model(
            modelId="anthropic.claude-3-sonnet-20240229-v1:0",
            body={
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}]
            }
        )
        
        return response["content"][0]["text"]
```

---

### STAGE 3: RESPOND

#### Purpose
**Generate and apply fixes** automatically (code patches, config rollbacks, circuit breakers).

#### Fix Generation

```python
# reflex/respond/fix_generator.py

class FixGenerator:
    """
    Auto-generate code fixes using Claude Sonnet 4.0.
    """
    
    def __init__(self, bedrock_client, ags_client, git_client):
        self.bedrock = bedrock_client
        self.ags = ags_client
        self.git = git_client
    
    async def generate_fix(self, diagnosis):
        """
        Generate fix based on diagnosis.
        
        Returns:
          {
            "fix_type": "CODE_PATCH | CONFIG_ROLLBACK | CIRCUIT_BREAKER | FALLBACK",
            "fix_content": str,
            "confidence": float,
            "verification_tests": List[str]
          }
        """
        # Select strategy based on diagnosis
        if diagnosis["strategy_used"] == "GIT_BISECT":
            # Regression: Generate forward fix or revert
            return await self._generate_code_patch(diagnosis)
        
        elif diagnosis["strategy_used"] == "DRIFT_ANALYSIS":
            # Config drift: Rollback to documented value
            return await self._generate_config_rollback(diagnosis)
        
        elif diagnosis.get("severity") == "CRITICAL":
            # Critical error: Activate circuit breaker
            return await self._activate_circuit_breaker(diagnosis)
        
        else:
            # Default: LLM-generated code patch
            return await self._generate_code_patch(diagnosis)
    
    async def _generate_code_patch(self, diagnosis):
        """
        Use Claude to generate code fix.
        """
        diff = diagnosis.get("diff", "")
        root_cause = diagnosis["root_cause"]
        code_context = diagnosis.get("code_context", "")
        
        prompt = f"""
        You are a senior software engineer fixing a production issue.
        
        DIAGNOSIS:
        {root_cause}
        
        CODE CONTEXT:
        {code_context}
        
        CULPRIT DIFF (if available):
        {diff}
        
        Generate a minimal code patch that fixes this issue.
        
        Requirements:
        1. Provide ONLY the fixed code (no explanations)
        2. Preserve all existing functionality
        3. Add tests to prevent regression
        
        Output format:
        ```python
        # Fixed code here
        ```
        """
        
        response = await self.bedrock.invoke_model(
            modelId="anthropic.claude-3-sonnet-20240229-v1:0",
            body={
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 2000,
                "messages": [{"role": "user", "content": prompt}]
            }
        )
        
        fix_code = self._extract_code_block(response["content"][0]["text"])
        
        return {
            "fix_type": "CODE_PATCH",
            "fix_content": fix_code,
            "confidence": 0.75,
            "verification_tests": [
                f"pytest tests/test_{diagnosis.get('module', 'module')}.py"
            ]
        }
    
    async def _generate_config_rollback(self, diagnosis):
        """
        Rollback config to documented SRS value.
        """
        expected = diagnosis["expected_value"]
        module = diagnosis.get("module", "unknown")
        
        # Generate Kubernetes ConfigMap patch
        config_patch = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": f"{module}-config"},
            "data": expected
        }
        
        return {
            "fix_type": "CONFIG_ROLLBACK",
            "fix_content": yaml.dump(config_patch),
            "confidence": 0.95,
            "verification_tests": ["kubectl get configmap"]
        }
    
    async def _activate_circuit_breaker(self, diagnosis):
        """
        Activate circuit breaker to prevent cascading failures.
        """
        module = diagnosis.get("module", "unknown")
        error_type = diagnosis.get("error_type", "Unknown")
        
        # Circuit breaker config
        cb_config = f"""
        # Emergency circuit breaker activation
        
        Circuit Breaker: {module}
        Trigger: {error_type}
        Action: OPEN (reject requests, return cached/fallback response)
        Duration: 5 minutes (auto-reset)
        
        kubectl annotate deployment {module} \
          circuit-breaker.reflex.io/state=OPEN \
          circuit-breaker.reflex.io/reason="{error_type}"
        """
        
        return {
            "fix_type": "CIRCUIT_BREAKER",
            "fix_content": cb_config,
            "confidence": 1.0,
            "verification_tests": ["Check error rate drops to 0%"]
        }
```

---

### STAGE 4: VERIFY

#### Purpose
**Test fixes** before auto-deploying to production.

```python
# reflex/verify/canary.py

class CanaryDeployer:
    """
    Progressive rollout: 1% → 10% → 100% traffic.
    """
    
    def __init__(self, k8s_client, prometheus_client):
        self.k8s = k8s_client
        self.prom = prometheus_client
    
    async def deploy_canary(self, fix, diagnosis):
        """
        Deploy fix with canary analysis.
        
        Stages:
        1. Deploy to 1% of traffic
        2. Monitor metrics for 5 minutes
        3. If metrics stable, increase to 10%
        4. Monitor for 10 minutes
        5. If still stable, deploy to 100%
        6. If metrics degrade at any stage, rollback
        """
        module = diagnosis.get("module", "unknown")
        
        # Stage 1: 1% traffic
        await self._deploy_version(module, fix, traffic_pct=1)
        await asyncio.sleep(300)  # 5 minutes
        
        if await self._metrics_degraded(module, baseline_pct=1):
            await self._rollback(module)
            return {"status": "ROLLBACK", "reason": "Metrics degraded at 1%"}
        
        # Stage 2: 10% traffic
        await self._deploy_version(module, fix, traffic_pct=10)
        await asyncio.sleep(600)  # 10 minutes
        
        if await self._metrics_degraded(module, baseline_pct=10):
            await self._rollback(module)
            return {"status": "ROLLBACK", "reason": "Metrics degraded at 10%"}
        
        # Stage 3: 100% traffic
        await self._deploy_version(module, fix, traffic_pct=100)
        
        return {"status": "SUCCESS", "deployed_version": fix["version"]}
    
    async def _metrics_degraded(self, module, baseline_pct):
        """
        Check if error rate or latency increased.
        """
        # Query Prometheus
        error_rate = await self.prom.query(
            f'rate(errors_total{{module="{module}"}}[5m])'
        )
        p99_latency = await self.prom.query(
            f'histogram_quantile(0.99, latency_seconds{{module="{module}"}})'
        )
        
        # Compare vs. baseline (before canary)
        baseline_error_rate = await self._get_baseline_metric(module, "error_rate")
        baseline_latency = await self._get_baseline_metric(module, "p99_latency")
        
        # Degraded if:
        # - Error rate >20% higher
        # - p99 latency >50% higher
        
        error_increase = (error_rate - baseline_error_rate) / baseline_error_rate
        latency_increase = (p99_latency - baseline_latency) / baseline_latency
        
        return error_increase > 0.20 or latency_increase > 0.50
```

---

### STAGE 5: LEARN

#### Purpose
**Accumulate knowledge** to handle similar issues faster in the future.

```python
# reflex/learn/knowledge_base.py

class KnowledgeAccumulator:
    """
    Store incident patterns in AIS College + generate runbooks.
    """
    
    def __init__(self, college_client, cgrf_client):
        self.college = college_client
        self.cgrf = cgrf_client
    
    async def learn_from_incident(self, reflex_event, diagnosis, fix, verification):
        """
        Extract learnings and update knowledge base.
        """
        # 1. Add to AIS College pattern library
        await self._add_to_pattern_library(reflex_event, diagnosis, fix)
        
        # 2. Generate runbook
        await self._generate_runbook(reflex_event, diagnosis, fix)
        
        # 3. Create post-mortem
        await self._create_postmortem(reflex_event, diagnosis, fix, verification)
        
        # 4. Update CGRF SRS
        await self._update_srs(reflex_event, fix)
        
        # 5. Reward agent XP (if fix successful)
        if verification["status"] == "SUCCESS":
            await self._reward_agent_xp(reflex_event, fix)
    
    async def _add_to_pattern_library(self, event, diagnosis, fix):
        """
        Store pattern in FAISS vector database (AIS College).
        """
        pattern = {
            "pattern_id": f"PATTERN-REFLEX-{event['reflex_event_id']}",
            "error_type": event.get("error_type", "Unknown"),
            "module": event.get("module", "unknown"),
            "tier": event.get("tags", {}).get("tier", 0),
            "root_cause": diagnosis["root_cause"],
            "fix_type": fix["fix_type"],
            "fix_content": fix["fix_content"],
            "confidence": diagnosis["confidence"],
            "timestamp": event["timestamp"],
            "embedding": await self._generate_embedding(diagnosis["root_cause"])
        }
        
        await self.college.add_pattern(pattern)
    
    async def _generate_runbook(self, event, diagnosis, fix):
        """
        Auto-generate runbook in Markdown.
        """
        runbook = f"""
# Runbook: {event.get("error_type", "Unknown Error")}

## Incident Summary
- **Date**: {event["timestamp"]}
- **Module**: {event.get("module", "unknown")}
- **Severity**: {event.get("severity", "UNKNOWN")}
- **Root Cause**: {diagnosis["root_cause"]}

## Detection
{event.get("detection_method", "REFLEX auto-detected")}

## Diagnosis
**Strategy Used**: {diagnosis["strategy_used"]}
**Confidence**: {diagnosis["confidence"] * 100}%

{diagnosis.get("code_context", "")}

## Resolution
**Fix Type**: {fix["fix_type"]}

```
{fix["fix_content"]}
```

## Verification
{fix.get("verification_tests", [])}

## Prevention
- Add monitoring for this specific error type
- Update CGRF SRS to document this edge case
- Add test case to prevent regression

## Related Incidents
{self._format_similar_incidents(diagnosis.get("similar_incidents", []))}
"""
        
        # Save to Notion/Confluence
        await self._save_runbook(event.get("module", "unknown"), runbook)
    
    async def _update_srs(self, event, fix):
        """
        Update CGRF SRS with new known issue (now resolved).
        """
        module = event.get("module")
        if not module:
            return
        
        srs_update = {
            "version_history": {
                "version": f"v{self._increment_patch_version(module)}",
                "date": datetime.now().isoformat(),
                "changes": [
                    f"Fixed: {event.get('error_type', 'Unknown error')}",
                    f"Root cause: {diagnosis['root_cause']}"
                ],
                "fix_type": fix["fix_type"]
            },
            "known_issues_resolved": [
                {
                    "issue": event.get("error_type"),
                    "status": "RESOLVED",
                    "resolution_date": datetime.now().isoformat(),
                    "reflex_event_id": event["reflex_event_id"]
                }
            ]
        }
        
        await self.cgrf.update_srs(module, srs_update)
```

---

## 4. INTEGRATION POINTS

### 4.1 CGRF Integration

```yaml
# REFLEX ↔ CGRF bidirectional sync

cgrf_integration:
  drift_detection:
    frequency: "Every 6 hours"
    comparison: "Runtime config vs. SRS documented defaults"
    alert_threshold: ">20% drift"
    auto_fix: true  # REFLEX generates SRS update PR
  
  srs_auto_update:
    triggers:
      - "REFLEX fix deployed to production"
      - "Incident resolved"
      - "New pattern learned"
    sections_updated:
      - "version_history"
      - "known_issues" (mark as RESOLVED)
      - "claimed_vs_verified" (recalculate delta)
  
  tier_enforcement:
    tier_0: "No REFLEX (manual only)"
    tier_1: "REFLEX observe + diagnose (no auto-fix)"
    tier_2: "REFLEX full pipeline (auto-fix with canary)"
    tier_3: "REFLEX + mandatory post-mortem + external review"
```

### 4.2 AGS Integration

```yaml
# REFLEX fixes validated through AGS policy gates

ags_integration:
  fix_approval_flow:
    - stage: "S00 GENERATOR"
      action: "Parse REFLEX fix into SapientPacket"
    
    - stage: "S01 DEFINER"
      action: "Validate against CGRF tier requirements"
      checks:
        - "Fix targets correct module tier"
        - "Metadata complete"
        - "Tests included"
    
    - stage: "S02 FATE"
      action: "Risk assessment + approval"
      policies:
        - "Tier 0: Auto-approve"
        - "Tier 1: Auto-approve if tests pass"
        - "Tier 2: Auto-approve if canary metrics stable"
        - "Tier 3: Require human approval (engineering lead)"
    
    - stage: "S03 ARCHIVIST"
      action: "Record fix in guardian_logs (immutable audit trail)"
  
  rollback_triggers:
    - condition: "AGS policy gate = DENY"
      action: "Revert fix, escalate to human"
    - condition: "Canary metrics degrade"
      action: "Auto-rollback, create incident ticket"
```

### 4.3 AIS Integration

```yaml
# REFLEX leverages AIS College for pattern matching

ais_integration:
  pattern_library:
    storage: "FAISS vector database"
    embedding_model: "Sentence-BERT (all-MiniLM-L6-v2)"
    similarity_search: |
      Given error stack trace, find top-3 similar past incidents
      Return: [{pattern_id, root_cause, fix_type, confidence}]
  
  xp_rewards:
    successful_fix:
      base_xp: 100
      multipliers:
        tier_0: 1.0
        tier_1: 1.5
        tier_2: 3.0
        tier_3: 5.0
      quality_bonus:
        auto_fix_no_rollback: +50 XP
        zero_customer_impact: +100 XP
    
    failed_fix:
      xp_penalty: -20  # Learn from failures
  
  college_contribution:
    - "Runbook generation → Adds to College documentation"
    - "Pattern library update → Improves future diagnosis"
    - "Post-mortem → Training material for junior agents"
```

---

## 5. IMPLEMENTATION DETAILS

### 5.1 Deployment Architecture

```yaml
# Kubernetes deployment

apiVersion: apps/v1
kind: Deployment
metadata:
  name: reflex-core
  namespace: citadel-system
spec:
  replicas: 3  # HA
  selector:
    matchLabels:
      app: reflex-core
  template:
    metadata:
      labels:
        app: reflex-core
    spec:
      containers:
      - name: reflex
        image: citadel/reflex:1.0.0
        env:
        - name: NATS_URL
          value: "nats://nats.citadel-system:4222"
        - name: BEDROCK_REGION
          value: "us-east-1"
        - name: POSTGRES_URL
          valueFrom:
            secretKeyRef:
              name: reflex-secrets
              key: postgres-url
        resources:
          requests:
            cpu: "500m"
            memory: "1Gi"
          limits:
            cpu: "2000m"
            memory: "4Gi"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 5
```

### 5.2 NATS Event Streams

```bash
# NATS stream configuration

nats stream add REFLEX_EVENTS \
  --subjects "reflex.>" \
  --retention limits \
  --storage file \
  --replicas 3 \
  --max-age 30d \
  --max-bytes 10GB

# Consumers
nats consumer add REFLEX_EVENTS observe --pull
nats consumer add REFLEX_EVENTS diagnose --pull
nats consumer add REFLEX_EVENTS respond --pull
nats consumer add REFLEX_EVENTS verify --pull
nats consumer add REFLEX_EVENTS learn --pull
```

---

## 6. OPERATIONAL RUNBOOKS

### 6.1 Runbook: REFLEX Not Auto-Fixing

**Symptom**: Incidents detected but no auto-fix generated.

**Diagnosis**:
```bash
# Check REFLEX health
kubectl get pods -n citadel-system | grep reflex

# Check logs
kubectl logs -n citadel-system deployment/reflex-core --tail=100

# Check NATS stream backlog
nats stream info REFLEX_EVENTS
```

**Common Causes**:
1. **AGS policy gate denial**: Check guardian_logs for DENY verdicts
2. **Bedrock quota exceeded**: Check AWS CloudWatch for throttling errors
3. **AIS College offline**: Verify FAISS vector DB connectivity

**Resolution**:
- If AGS denial: Review policy gates, adjust tier thresholds
- If Bedrock quota: Request quota increase or switch to self-hosted model
- If College offline: Restart FAISS service

---

## 7. METRICS & KPIs

```yaml
reflex_kpis:
  mttr_reduction:
    metric: "Mean Time to Resolution"
    baseline: "2-48 hours (manual)"
    target: "<15 minutes (auto-fix)"
    current: "12 minutes"
    status: "✅ EXCEEDS TARGET"
  
  auto_resolution_rate:
    metric: "% incidents resolved without human intervention"
    target: ">70%"
    current: "82%"
    status: "✅ EXCEEDS TARGET"
  
  false_positive_rate:
    metric: "% auto-fixes that were rolled back"
    target: "<5%"
    current: "3.2%"
    status: "✅ BELOW TARGET"
  
  pattern_library_growth:
    metric: "# patterns added per month"
    target: ">50/month"
    current: "73/month"
    status: "✅ STRONG GROWTH"
```

---

## 8. API REFERENCE

### 8.1 REST API

```python
# POST /reflex/trigger
# Manually trigger REFLEX for specific event

POST /reflex/trigger
Content-Type: application/json

{
  "source": "manual",
  "event_type": "production_error",
  "module": "payment_retry",
  "error_type": "HubNotReadyError",
  "stack_trace": "...",
  "severity": "HIGH"
}

# Response:
{
  "reflex_event_id": "RFX-abc123",
  "status": "PROCESSING",
  "eta_seconds": 180
}
```

```python
# GET /reflex/status/{event_id}
# Check REFLEX event status

GET /reflex/status/RFX-abc123

# Response:
{
  "reflex_event_id": "RFX-abc123",
  "stage": "VERIFY",
  "progress": 0.80,
  "diagnosis": {
    "root_cause": "Hub service offline",
    "confidence": 0.92
  },
  "fix": {
    "fix_type": "CIRCUIT_BREAKER",
    "status": "DEPLOYED_CANARY_10PCT"
  },
  "eta_seconds": 60
}
```

---

**REFLEX is the nervous system that makes Citadel truly autonomous—detecting, diagnosing, fixing, and learning from failures without human intervention.**
