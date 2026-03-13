# AGS: AGENT GOVERNANCE SYSTEM v1.0
## Constitutional AI Judiciary - 4-Stage Policy Enforcement Engine

**Version:** 1.0.0  
**Date:** January 25, 2026  
**Status:** PRODUCTION-READY  
**Classification:** Core Governance Component  
**Integration:** CGRF v3.0, REFLEX, AIS  

---

## TABLE OF CONTENTS

1. [Executive Summary](#1-executive-summary)
2. [Constitutional Compiler Architecture](#2-constitutional-compiler-architecture)
3. [Four-Stage Pipeline (S00-S03)](#3-four-stage-pipeline)
4. [Policy Gate System](#4-policy-gate-system)
5. [CAPS Grading System](#5-caps-grading-system)
6. [Guardian Logs (Immutable Ledger)](#6-guardian-logs)
7. [Implementation Guide](#7-implementation-guide)
8. [API Reference](#8-api-reference)

---

## 1. EXECUTIVE SUMMARY

### What is AGS?

**AGS (Agent Governance System)** is Citadel's **constitutional judiciary**—a 4-stage validation pipeline that ensures every mutation (code change, config update, deployment) complies with governance rules before execution.

```
Traditional Access Control:
├─ RBAC: "Does this user have permission?" (identity-based)
└─ Limitation: Doesn't validate WHAT they're doing

Constitutional Governance (AGS):
├─ Policy Gates: "Is this action allowed by the constitution?"
├─ Validation: Checks against CGRF tiers, CAPS grades, XP/TP budgets
└─ Audit: Immutable ledger of all decisions
```

### Core Innovation

**AGS is the world's first AI-native governance system that:**
1. Validates mutations through constitutional policies (not just ACLs)
2. Auto-adapts enforcement based on module tier (Tier 0 = permissive, Tier 3 = strict)
3. Records all decisions in cryptographically-sealed audit logs
4. Integrates economic incentives (XP/TP budgets via AIS)

### Key Capabilities

| Stage | Purpose | Output |
|-------|---------|--------|
| **S00: GENERATOR** | Normalize intent into SapientPacket | Structured mutation request |
| **S01: DEFINER** | Validate schema + CAPS grades | Compiled packet (JSON sealed) |
| **S02: FATE** | Risk assessment + policy evaluation | ALLOW / REVIEW / DENY |
| **S03: ARCHIVIST** | Immutable recording | Ledger ID + provenance hash |

---

## 2. CONSTITUTIONAL COMPILER ARCHITECTURE

### 2.1 System Overview

```
┌────────────────────────────────────────────────────────────────┐
│         AGS CONSTITUTIONAL COMPILER (4-Stage Pipeline)          │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  INPUT: Mutation Request                                       │
│  ├─ Source: Agent, REFLEX, Human developer                     │
│  ├─ Action: CREATE_MODULE, UPDATE_SRS, DEPLOY_CODE             │
│  └─ Target: {module, tier, dependencies}                       │
│                                                                 │
│  ┌───────────────────────────────────────────────────────┐     │
│  │ S00: GENERATOR (Intent Normalization)                 │     │
│  ├───────────────────────────────────────────────────────┤     │
│  │ • Parse natural language or structured JSON           │     │
│  │ • Extract: {action, target, agent, context}           │     │
│  │ • Assign intent_hash (SHA256 of normalized request)   │     │
│  │ • Output: SapientPacket (standardized format)         │     │
│  └─────────────────────┬─────────────────────────────────┘     │
│                        │                                        │
│  ┌─────────────────────▼─────────────────────────────────┐     │
│  │ S01: DEFINER (Schema Validation)                      │     │
│  ├───────────────────────────────────────────────────────┤     │
│  │ • Validate against CGRF tier requirements             │     │
│  │ • Check CAPS grade (agent capability level)           │     │
│  │ • Verify metadata completeness                        │     │
│  │ • Validate dependencies (circular checks)             │     │
│  │ • Output: Compiled packet (JSON sealed)               │     │
│  └─────────────────────┬─────────────────────────────────┘     │
│                        │                                        │
│  ┌─────────────────────▼─────────────────────────────────┐     │
│  │ S02: FATE (Risk Assessment & Policy Enforcement)      │     │
│  ├───────────────────────────────────────────────────────┤     │
│  │ • Load tier-specific policy gates (YAML)              │     │
│  │ • Evaluate conditions (test coverage, XP budget, etc) │     │
│  │ • Calculate risk score (0-100)                        │     │
│  │ • Check trust score (agent reputation)                │     │
│  │ • Output: Verdict {ALLOW | REVIEW | DENY}             │     │
│  │          + Reason + Cost (XP/TP deduction)            │     │
│  └─────────────────────┬─────────────────────────────────┘     │
│                        │                                        │
│  ┌─────────────────────▼─────────────────────────────────┐     │
│  │ S03: ARCHIVIST (Immutable Recording)                  │     │
│  ├───────────────────────────────────────────────────────┤     │
│  │ • Create cryptographic hash (SHA256)                  │     │
│  │ • Chain to previous entry (blockchain-style)          │     │
│  │ • Write to guardian_logs (PostgreSQL + S3 archive)    │     │
│  │ • Emit event (NATS: "ags.verdict.ALLOW")              │     │
│  │ • Output: {ledger_id, provenance_url, hash}           │     │
│  └───────────────────────────────────────────────────────┘     │
│                                                                 │
│  FINAL OUTPUT:                                                  │
│  ├─ Verdict: ALLOW | REVIEW | DENY                             │
│  ├─ Reason: "Tier 2 requirements met: tests + coverage ✓"      │
│  ├─ Cost: {xp: 50, tp: 10}                                     │
│  ├─ Ledger ID: GL-20260125-001234                              │
│  └─ Provenance Hash: sha256:abc123...                          │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow Example

```
┌─────────────────────────────────────────────────────────────┐
│ EXAMPLE: Agent Updates Tier 2 Module                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ INPUT (Natural Language):                                   │
│ "Add circuit breaker PRD to payment_retry.py"               │
│                                                              │
│ S00 GENERATOR:                                              │
│ ┌───────────────────────────────────────────────────────┐   │
│ │ {                                                     │   │
│ │   "action": "UPDATE_MODULE",                          │   │
│ │   "target": {                                         │   │
│ │     "module": "payment_retry.py",                     │   │
│ │     "tier": 2,                                        │   │
│ │     "section": "production_rules"                     │   │
│ │   },                                                  │   │
│ │   "agent": {                                          │   │
│ │     "id": "gm_payments_master",                       │   │
│ │     "caps_grade": "B",                                │   │
│ │     "xp": 1250,                                       │   │
│ │     "tp": 75,                                         │   │
│ │     "trust_score": 0.85                               │   │
│ │   },                                                  │   │
│ │   "changes": {                                        │   │
│ │     "add_prd": {                                      │   │
│ │       "id": "PRD-PAYMENT-004",                        │   │
│ │       "title": "Circuit Breaker",                     │   │
│ │       "enforcement": "BLOCKING"                       │   │
│ │     }                                                 │   │
│ │   },                                                  │   │
│ │   "intent_hash": "sha256:def456..."                   │   │
│ │ }                                                     │   │
│ └───────────────────────────────────────────────────────┘   │
│                                                              │
│ S01 DEFINER:                                                │
│ ✅ Tier 2 module validated                                   │
│ ✅ Agent CAPS B meets requirement (Tier 2 requires B+)       │
│ ✅ Metadata complete (all required fields present)           │
│ ✅ PRD schema valid (id, title, enforcement fields ✓)        │
│                                                              │
│ S02 FATE:                                                   │
│ Loading policy gate: "tier_2_production_gate"               │
│                                                              │
│ Condition Checks:                                           │
│ ├─ test_coverage: 87% ✅ (≥80% required)                     │
│ ├─ has_prds: true ✅                                         │
│ ├─ claimed_verified_delta: 0.13 ✅ (≤0.20 allowed)           │
│ ├─ no_critical_flaws: true ✅                                │
│ ├─ agent.caps_grade: B ✅ (in [B, A, S])                     │
│ ├─ agent.trust_score: 0.85 ✅ (≥0.70 required)               │
│ ├─ agent.xp: 1250 ✅ (≥50 for this action)                   │
│ └─ agent.tp: 75 ✅ (≥10 for this action)                     │
│                                                              │
│ Risk Score: 12/100 (LOW)                                    │
│ Verdict: ALLOW                                              │
│ Cost: 50 XP, 10 TP                                          │
│                                                              │
│ S03 ARCHIVIST:                                              │
│ ┌───────────────────────────────────────────────────────┐   │
│ │ Guardian Log Entry:                                   │   │
│ │ {                                                     │   │
│ │   "ledger_id": "GL-20260125-001234",                  │   │
│ │   "timestamp": "2026-01-25T17:30:15Z",                │   │
│ │   "event_type": "MUTATION_ALLOWED",                   │   │
│ │   "agent_id": "gm_payments_master",                   │   │
│ │   "action": "UPDATE_MODULE",                          │   │
│ │   "target": "payment_retry.py (Tier 2)",              │   │
│ │   "verdict": "ALLOW",                                 │   │
│ │   "reason": "Tier 2 production gate passed",          │   │
│ │   "cost": {"xp": 50, "tp": 10},                       │   │
│ │   "hash": "sha256:abc123...",                         │   │
│ │   "prev_hash": "sha256:fed987..."                     │   │
│ │ }                                                     │   │
│ └───────────────────────────────────────────────────────┘   │
│                                                              │
│ FINAL RESULT:                                               │
│ ✅ Mutation ALLOWED                                          │
│ ✅ Agent earned 50 XP, paid 10 TP                            │
│ ✅ Trust score updated: 0.85 → 0.86                          │
│ ✅ payment_retry.py updated with PRD-PAYMENT-004             │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. FOUR-STAGE PIPELINE (S00-S03)

### STAGE S00: GENERATOR

#### Purpose
**Normalize intent** from natural language or structured requests into standardized SapientPacket format.

#### Implementation

```python
# ags/stages/s00_generator.py

from typing import Dict, Any
import hashlib
import json

class GeneratorStage:
    """
    S00: Intent Normalization
    
    Converts any input (natural language, JSON, webhook payload)
    into standardized SapientPacket format.
    """
    
    def __init__(self, llm_client):
        self.llm = llm_client
    
    async def parse(self, raw_input: Any) -> Dict:
        """
        Parse input into SapientPacket.
        
        Args:
            raw_input: Natural language string, JSON dict, or webhook
        
        Returns:
            SapientPacket: {
              "action": str,
              "target": dict,
              "agent": dict,
              "changes": dict,
              "intent_hash": str
            }
        """
        # Detect input type
        if isinstance(raw_input, str):
            # Natural language → use LLM to extract intent
            return await self._parse_natural_language(raw_input)
        
        elif isinstance(raw_input, dict):
            # Structured JSON → validate + normalize
            return await self._normalize_structured(raw_input)
        
        else:
            raise ValueError(f"Unsupported input type: {type(raw_input)}")
    
    async def _parse_natural_language(self, text: str) -> Dict:
        """
        Use LLM to extract structured intent from natural language.
        
        Example:
          Input: "Add circuit breaker PRD to payment_retry.py"
          Output: {action: UPDATE_MODULE, target: {module: payment_retry.py}, ...}
        """
        prompt = f"""
        Extract structured intent from this natural language request:
        
        REQUEST: {text}
        
        Output JSON format:
        {{
          "action": "CREATE_MODULE | UPDATE_MODULE | DELETE_MODULE | UPDATE_SRS | DEPLOY_CODE",
          "target": {{
            "module": "module_name.py",
            "tier": 0-3,
            "section": "functional_requirements | production_rules | ..."
          }},
          "changes": {{
            // Describe what's changing
          }}
        }}
        
        Respond with ONLY the JSON, no explanation.
        """
        
        response = await self.llm.generate(
            model="claude-3-sonnet-20240229",
            prompt=prompt,
            max_tokens=500
        )
        
        intent = json.loads(response)
        
        # Add agent context (extracted from request metadata or auth token)
        intent["agent"] = await self._get_agent_context()
        
        # Calculate intent hash (for deduplication + audit)
        intent["intent_hash"] = self._calculate_intent_hash(intent)
        
        return intent
    
    async def _normalize_structured(self, data: Dict) -> Dict:
        """
        Validate + normalize structured JSON input.
        """
        # Ensure required fields
        required_fields = ["action", "target", "agent"]
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")
        
        # Standardize action names
        action_aliases = {
            "create": "CREATE_MODULE",
            "update": "UPDATE_MODULE",
            "delete": "DELETE_MODULE",
            "deploy": "DEPLOY_CODE"
        }
        
        data["action"] = action_aliases.get(
            data["action"].lower(),
            data["action"]
        )
        
        # Add intent hash
        data["intent_hash"] = self._calculate_intent_hash(data)
        
        return data
    
    def _calculate_intent_hash(self, intent: Dict) -> str:
        """
        SHA256 hash of normalized intent (for deduplication).
        """
        # Sort keys for deterministic hashing
        canonical = json.dumps(
            {k: intent[k] for k in sorted(intent.keys()) if k != "intent_hash"},
            sort_keys=True
        )
        
        return hashlib.sha256(canonical.encode()).hexdigest()
    
    async def _get_agent_context(self) -> Dict:
        """
        Fetch agent metadata (CAPS grade, XP, TP, trust score).
        """
        # In production, this would query AIS database
        return {
            "id": "gm_payments_master",
            "caps_grade": "B",
            "xp": 1250,
            "tp": 75,
            "trust_score": 0.85
        }
```

---

### STAGE S01: DEFINER

#### Purpose
**Schema validation** + CAPS grade checks + dependency validation.

```python
# ags/stages/s01_definer.py

class DefinerStage:
    """
    S01: Schema Validation
    
    Validates SapientPacket against CGRF tier requirements and
    agent CAPS grades.
    """
    
    def __init__(self, cgrf_client, ais_client):
        self.cgrf = cgrf_client
        self.ais = ais_client
    
    async def validate(self, packet: Dict) -> Dict:
        """
        Validate packet schema + agent capabilities.
        
        Returns:
            CompileResult: {
              "valid": bool,
              "errors": List[str],
              "warnings": List[str],
              "compiled_packet": dict  # JSON-sealed version
            }
        """
        errors = []
        warnings = []
        
        # 1. Validate action type
        valid_actions = [
            "CREATE_MODULE", "UPDATE_MODULE", "DELETE_MODULE",
            "UPDATE_SRS", "DEPLOY_CODE"
        ]
        
        if packet["action"] not in valid_actions:
            errors.append(f"Invalid action: {packet['action']}")
        
        # 2. Validate target module exists + tier
        target = packet["target"]
        module = target.get("module")
        
        if not module:
            errors.append("Target module not specified")
        else:
            # Fetch module metadata from CGRF
            srs = await self.cgrf.get_srs(module)
            
            if not srs:
                errors.append(f"No SRS found for module: {module}")
            else:
                target["tier"] = srs["_tier"]  # Populate tier from SRS
                target["current_version"] = srs["_module_version"]
        
        # 3. Validate CAPS grade
        agent = packet["agent"]
        required_caps = self._tier_to_caps_requirement(target.get("tier", 0))
        
        if not self._caps_sufficient(agent["caps_grade"], required_caps):
            errors.append(
                f"Agent CAPS grade {agent['caps_grade']} insufficient "
                f"for Tier {target['tier']} (requires {required_caps}+)"
            )
        
        # 4. Validate metadata completeness
        if packet["action"] in ["CREATE_MODULE", "UPDATE_SRS"]:
            metadata_errors = await self._validate_metadata(packet)
            errors.extend(metadata_errors)
        
        # 5. Validate dependencies (circular check)
        if "dependencies" in packet.get("changes", {}):
            dep_errors = await self._validate_dependencies(packet)
            errors.extend(dep_errors)
        
        # Compile result
        if errors:
            return {
                "valid": False,
                "errors": errors,
                "warnings": warnings,
                "compiled_packet": None
            }
        else:
            # Seal packet (JSON + SHA256 signature)
            sealed = self._seal_packet(packet)
            
            return {
                "valid": True,
                "errors": [],
                "warnings": warnings,
                "compiled_packet": sealed
            }
    
    def _tier_to_caps_requirement(self, tier: int) -> str:
        """Map CGRF tier to minimum CAPS grade."""
        return {
            0: "D",  # Tier 0: Any agent
            1: "C",  # Tier 1: Journeyman+
            2: "B",  # Tier 2: Master+
            3: "A"   # Tier 3: Grandmaster+
        }.get(tier, "S")
    
    def _caps_sufficient(self, agent_caps: str, required_caps: str) -> bool:
        """Check if agent CAPS ≥ required."""
        caps_hierarchy = ["D", "C", "B", "A", "S"]
        return caps_hierarchy.index(agent_caps) >= caps_hierarchy.index(required_caps)
    
    async def _validate_metadata(self, packet: Dict) -> List[str]:
        """Validate CGRF metadata completeness."""
        errors = []
        
        required_fields = [
            "_report_id", "_tier", "_module_version",
            "_module_name", "_execution_role"
        ]
        
        changes = packet.get("changes", {})
        metadata = changes.get("metadata", {})
        
        for field in required_fields:
            if field not in metadata:
                errors.append(f"Missing required metadata field: {field}")
        
        return errors
    
    async def _validate_dependencies(self, packet: Dict) -> List[str]:
        """Check for circular dependencies."""
        errors = []
        
        module = packet["target"]["module"]
        new_deps = packet["changes"]["dependencies"]
        
        # Build dependency graph
        graph = await self._build_dependency_graph()
        
        # Check if adding these deps creates a cycle
        for dep in new_deps:
            if self._creates_cycle(graph, module, dep):
                errors.append(f"Circular dependency: {module} → {dep}")
        
        return errors
    
    def _seal_packet(self, packet: Dict) -> Dict:
        """
        Create JSON-sealed version of packet with signature.
        """
        canonical = json.dumps(packet, sort_keys=True)
        signature = hashlib.sha256(canonical.encode()).hexdigest()
        
        return {
            **packet,
            "sealed": True,
            "sealed_at": datetime.utcnow().isoformat(),
            "signature": signature
        }
```

---

### STAGE S02: FATE

#### Purpose
**Risk assessment** + **policy gate evaluation** → ALLOW / REVIEW / DENY

```python
# ags/stages/s02_fate.py

import yaml
from typing import Dict, Literal

class FateStage:
    """
    S02: Risk Assessment & Policy Enforcement
    
    Evaluates mutation against tier-specific policy gates.
    """
    
    def __init__(self, policy_loader, ais_client):
        self.policies = policy_loader
        self.ais = ais_client
    
    async def evaluate(self, compiled_packet: Dict) -> Dict:
        """
        Evaluate packet against policy gates.
        
        Returns:
            Verdict: {
              "verdict": "ALLOW | REVIEW | DENY",
              "reason": str,
              "risk_score": int (0-100),
              "cost_xp": int,
              "cost_tp": int,
              "policy_gate_used": str,
              "escalation": str (if REVIEW)
            }
        """
        target_tier = compiled_packet["target"]["tier"]
        agent = compiled_packet["agent"]
        
        # Load tier-specific policy gate
        policy_gate = await self._load_policy_gate(target_tier)
        
        # Evaluate all conditions
        conditions_met = []
        conditions_failed = []
        
        for rule in policy_gate["rules"]:
            condition = rule["condition"]
            
            # Evaluate condition (string → boolean)
            result = await self._eval_condition(condition, compiled_packet)
            
            if result:
                conditions_met.append(rule)
            else:
                conditions_failed.append(rule)
        
        # Determine verdict
        if conditions_failed:
            # At least one condition failed
            first_failure = conditions_failed[0]
            
            if first_failure.get("verdict") == "DENY":
                return {
                    "verdict": "DENY",
                    "reason": first_failure["reason"],
                    "risk_score": 100,
                    "cost_xp": 0,
                    "cost_tp": 0,
                    "policy_gate_used": policy_gate["name"]
                }
            
            elif first_failure.get("verdict") == "REVIEW":
                return {
                    "verdict": "REVIEW",
                    "reason": first_failure["reason"],
                    "risk_score": 60,
                    "cost_xp": 0,
                    "cost_tp": 0,
                    "policy_gate_used": policy_gate["name"],
                    "escalation": first_failure.get("escalation", "engineering-lead@example.com")
                }
        
        # All conditions passed → ALLOW
        allow_rule = next(r for r in policy_gate["rules"] if r.get("verdict") == "ALLOW")
        
        # Calculate risk score (lower = safer)
        risk_score = await self._calculate_risk_score(compiled_packet)
        
        # Deduct XP/TP from agent
        cost_xp = allow_rule.get("cost_xp", 0)
        cost_tp = allow_rule.get("cost_tp", 0)
        
        await self.ais.deduct_budget(agent["id"], xp=cost_xp, tp=cost_tp)
        
        return {
            "verdict": "ALLOW",
            "reason": allow_rule["reason"],
            "risk_score": risk_score,
            "cost_xp": cost_xp,
            "cost_tp": cost_tp,
            "policy_gate_used": policy_gate["name"]
        }
    
    async def _load_policy_gate(self, tier: int) -> Dict:
        """
        Load YAML policy gate for specific tier.
        
        Policy gates stored in: policies/cgrf_tier_gates.yaml
        """
        policy_file = f"policies/cgrf_tier_{tier}_gate.yaml"
        
        with open(policy_file) as f:
            return yaml.safe_load(f)
    
    async def _eval_condition(self, condition: str, packet: Dict) -> bool:
        """
        Evaluate policy condition string.
        
        Example condition:
          "mutation.target.test_coverage >= 0.80 and
           mutation.agent.caps_grade in ['B', 'A', 'S']"
        
        Context:
          mutation = packet (SapientPacket)
        """
        # Build evaluation context
        ctx = {
            "mutation": packet,
            
            # Helper functions
            "has_tests": await self._check_has_tests(packet),
            "has_prds": await self._check_has_prds(packet),
            "no_critical_flaws": await self._check_no_critical_flaws(packet)
        }
        
        # Safely evaluate condition
        try:
            result = eval(condition, {"__builtins__": {}}, ctx)
            return bool(result)
        except Exception as e:
            # Condition evaluation error → default to DENY
            print(f"Policy condition error: {e}")
            return False
    
    async def _calculate_risk_score(self, packet: Dict) -> int:
        """
        Calculate risk score (0-100, lower = safer).
        
        Factors:
        - Module tier (Tier 3 = high risk)
        - Test coverage (low coverage = high risk)
        - Agent trust score (low trust = high risk)
        - Claimed vs. Verified delta (high delta = high risk)
        """
        tier = packet["target"]["tier"]
        agent_trust = packet["agent"]["trust_score"]
        
        # Fetch module metrics
        srs = await self.cgrf.get_srs(packet["target"]["module"])
        test_coverage = srs.get("testing", {}).get("coverage_percent", 0) / 100
        delta = srs.get("claimed_vs_verified", {}).get("delta", 0)
        
        # Calculate risk
        risk = (
            tier * 15 +  # Tier 3 = +45 points
            (1 - agent_trust) * 30 +  # Low trust = +30 points
            (1 - test_coverage) * 30 +  # No tests = +30 points
            delta * 50  # 50% delta = +25 points
        )
        
        return min(int(risk), 100)
```

---

### STAGE S03: ARCHIVIST

#### Purpose
**Immutable recording** of all decisions in cryptographically-sealed ledger.

```python
# ags/stages/s03_archivist.py

class ArchivistStage:
    """
    S03: Immutable Recording
    
    Writes all AGS decisions to guardian_logs with hash chaining.
    """
    
    def __init__(self, db_client, nats_client, s3_client):
        self.db = db_client
        self.nats = nats_client
        self.s3 = s3_client
    
    async def record(self, verdict: Dict, packet: Dict) -> str:
        """
        Record verdict in guardian_logs.
        
        Returns:
            ledger_id: Unique ID for this entry (e.g., GL-20260125-001234)
        """
        # Generate ledger ID
        ledger_id = self._generate_ledger_id()
        
        # Fetch previous hash (for chaining)
        prev_hash = await self._get_last_hash()
        
        # Create ledger entry
        entry = {
            "ledger_id": ledger_id,
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": f"MUTATION_{verdict['verdict']}",
            "agent_id": packet["agent"]["id"],
            "action": packet["action"],
            "target": packet["target"]["module"],
            "target_tier": packet["target"]["tier"],
            "verdict": verdict["verdict"],
            "reason": verdict["reason"],
            "risk_score": verdict["risk_score"],
            "cost": {
                "xp": verdict["cost_xp"],
                "tp": verdict["cost_tp"]
            },
            "policy_gate": verdict["policy_gate_used"],
            "packet_hash": packet["signature"],
            "prev_hash": prev_hash
        }
        
        # Calculate this entry's hash
        entry_hash = self._calculate_hash(entry)
        entry["hash"] = entry_hash
        
        # Write to database
        await self.db.execute(
            """
            INSERT INTO guardian_logs
            (ledger_id, timestamp, event_type, agent_id, action,
             target, target_tier, verdict, reason, risk_score,
             cost_xp, cost_tp, policy_gate, packet_hash, prev_hash, hash)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
            """,
            ledger_id, entry["timestamp"], entry["event_type"],
            entry["agent_id"], entry["action"], entry["target"],
            entry["target_tier"], entry["verdict"], entry["reason"],
            entry["risk_score"], entry["cost"]["xp"], entry["cost"]["tp"],
            entry["policy_gate"], entry["packet_hash"], entry["prev_hash"],
            entry["hash"]
        )
        
        # Archive to S3 (long-term retention)
        await self._archive_to_s3(entry)
        
        # Emit event (NATS)
        await self.nats.publish(
            f"ags.verdict.{verdict['verdict']}",
            entry
        )
        
        return ledger_id
    
    def _generate_ledger_id(self) -> str:
        """
        Generate unique ledger ID: GL-{YYYYMMDD}-{SEQUENCE}
        """
        today = datetime.utcnow().strftime("%Y%m%d")
        sequence = random.randint(100000, 999999)
        return f"GL-{today}-{sequence}"
    
    async def _get_last_hash(self) -> str:
        """
        Fetch hash of most recent guardian_logs entry (for chaining).
        """
        result = await self.db.fetchrow(
            "SELECT hash FROM guardian_logs ORDER BY timestamp DESC LIMIT 1"
        )
        
        return result["hash"] if result else None
    
    def _calculate_hash(self, entry: Dict) -> str:
        """
        SHA256 hash of ledger entry.
        """
        # Remove hash field (if present) before hashing
        hashable = {k: v for k, v in entry.items() if k != "hash"}
        canonical = json.dumps(hashable, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()
    
    async def _archive_to_s3(self, entry: Dict):
        """
        Archive entry to S3 for 7-year retention.
        """
        bucket = "citadel-guardian-logs-archive"
        key = f"year={entry['timestamp'][:4]}/month={entry['timestamp'][5:7]}/{entry['ledger_id']}.json"
        
        await self.s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(entry),
            ServerSideEncryption="aws:kms"
        )
```

---

## 4. POLICY GATE SYSTEM

### 4.1 Policy Gate YAML Format

```yaml
# policies/cgrf_tier_2_gate.yaml

policy_schema_version: "1.0"
policy_name: "CGRF Tier 2 Production Gate"
policy_description: "Validates mutations against Tier 2 requirements"

gates:
  - name: "tier_2_production_gate"
    priority: 1
    trigger: "mutation.target.tier == 2"
    
    rules:
      # ALLOW rule (all conditions must pass)
      - condition: |
          mutation.target.test_coverage >= 0.80 and
          mutation.target.has_prds == true and
          mutation.target.claimed_vs_verified_delta <= 0.20 and
          mutation.target.no_critical_flaws == true and
          mutation.agent.caps_grade in ['B', 'A', 'S'] and
          mutation.agent.trust_score >= 0.70 and
          mutation.agent.xp >= 50 and
          mutation.agent.tp >= 10
        
        verdict: "ALLOW"
        reason: "Tier 2 production gate passed: all requirements met"
        cost_xp: 50
        cost_tp: 10
      
      # DENY rules (specific failures)
      - condition: "mutation.target.test_coverage < 0.80"
        verdict: "DENY"
        reason: |
          Tier 2 requires 80% test coverage.
          Current: {mutation.target.test_coverage * 100}%
          Add {(0.80 - mutation.target.test_coverage) * mutation.target.total_lines} more tested lines.
      
      - condition: "mutation.target.claimed_vs_verified_delta > 0.20"
        verdict: "REVIEW"
        reason: |
          Claimed vs. Verified gap too large: {mutation.target.claimed_vs_verified_delta * 100}%
          Tier 2 allows max 20%. Requires human approval.
        escalation: "engineering-lead@example.com"
      
      - condition: "mutation.agent.caps_grade not in ['B', 'A', 'S']"
        verdict: "DENY"
        reason: |
          Agent CAPS grade {mutation.agent.caps_grade} insufficient for Tier 2.
          Tier 2 requires CAPS B+ (Master level).
          Earn {XP_NEEDED_FOR_B} more XP to reach Tier 3.
      
      - condition: "mutation.agent.xp < 50"
        verdict: "DENY"
        reason: |
          Insufficient XP: {mutation.agent.xp} < 50 required.
          Complete more tasks to earn XP.
      
      - condition: "mutation.agent.tp < 10"
        verdict: "DENY"
        reason: |
          Insufficient TP: {mutation.agent.tp} < 10 required.
          TP is earned through critical tasks and mentoring.
```

### 4.2 Policy Gate Loading

```python
# ags/policy_loader.py

class PolicyLoader:
    """
    Loads and caches policy gates from YAML files.
    """
    
    def __init__(self, policy_dir="policies"):
        self.policy_dir = policy_dir
        self.cache = {}  # {tier: policy_gate}
    
    async def load_gate(self, tier: int) -> Dict:
        """
        Load policy gate for specific tier.
        """
        if tier in self.cache:
            return self.cache[tier]
        
        policy_file = f"{self.policy_dir}/cgrf_tier_{tier}_gate.yaml"
        
        with open(policy_file) as f:
            policy = yaml.safe_load(f)
        
        # Cache for performance
        self.cache[tier] = policy["gates"][0]
        
        return self.cache[tier]
    
    async def reload_all(self):
        """
        Hot-reload all policy gates (for policy updates without restart).
        """
        self.cache = {}
        
        for tier in [0, 1, 2, 3]:
            await self.load_gate(tier)
```

---

## 5. CAPS GRADING SYSTEM

### 5.1 CAPS Hierarchy

```yaml
caps_grades:
  D: # Tier 1 (Novice)
    xp_range: [0, 100]
    capabilities:
      - "Read CGRF documentation"
      - "Propose Tier 0 updates"
      - "Create experimental modules"
    restrictions:
      - "Cannot modify Tier 1+ modules"
      - "All actions require approval"
  
  C: # Tier 2 (Journeyman)
    xp_range: [101, 500]
    capabilities:
      - "Create Tier 1 modules"
      - "Update Tier 0-1 modules"
      - "Mentor Tier 1 agents"
      - "Propose Tier 2 updates (requires review)"
    restrictions:
      - "Cannot modify Tier 2+ without approval"
  
  B: # Tier 3 (Master)
    xp_range: [501, 2000]
    capabilities:
      - "Create Tier 2 modules"
      - "Update Tier 0-2 modules"
      - "Approve Tier 1 PRs"
      - "Conduct internal audits"
      - "Auto-deploy Tier 1 fixes (REFLEX)"
    restrictions:
      - "Tier 3 modifications require external audit"
  
  A: # Tier 4 (Grandmaster)
    xp_range: [2001, 10000]
    capabilities:
      - "Create Tier 3 modules"
      - "Update any module (Tier 0-3)"
      - "Approve Tier 2-3 PRs"
      - "Design new CGRF patterns"
      - "Auto-deploy Tier 2 fixes (REFLEX)"
      - "Propose constitutional changes"
    restrictions:
      - "Constitutional changes require community vote"
  
  S: # Tier 5 (Sovereign)
    xp_range: [10000, ∞]
    capabilities:
      - "Modify CGRF framework itself"
      - "Override policy gates (with audit)"
      - "Approve constitutional changes"
      - "Emergency system intervention"
    restrictions:
      - "All S-grade actions logged + reviewed quarterly"
```

### 5.2 CAPS Progression

```python
# ags/caps_system.py

class CAPSSystem:
    """
    Manages agent CAPS grade progression.
    """
    
    def __init__(self, ais_client):
        self.ais = ais_client
    
    async def calculate_caps_grade(self, agent_id: str) -> str:
        """
        Calculate agent's CAPS grade based on XP.
        
        Returns: "D" | "C" | "B" | "A" | "S"
        """
        agent_xp = await self.ais.get_agent_xp(agent_id)
        
        if agent_xp >= 10000:
            return "S"
        elif agent_xp >= 2001:
            return "A"
        elif agent_xp >= 501:
            return "B"
        elif agent_xp >= 101:
            return "C"
        else:
            return "D"
    
    async def can_perform_action(
        self,
        agent_id: str,
        action: str,
        target_tier: int
    ) -> Dict:
        """
        Check if agent CAPS grade allows this action.
        
        Returns:
          {
            "allowed": bool,
            "agent_caps": str,
            "required_caps": str,
            "reason": str
          }
        """
        agent_caps = await self.calculate_caps_grade(agent_id)
        required_caps = self._tier_to_caps_requirement(target_tier)
        
        allowed = self._caps_sufficient(agent_caps, required_caps)
        
        return {
            "allowed": allowed,
            "agent_caps": agent_caps,
            "required_caps": required_caps,
            "reason": (
                f"Agent CAPS {agent_caps} {'meets' if allowed else 'does not meet'} "
                f"Tier {target_tier} requirement ({required_caps}+)"
            )
        }
    
    def _tier_to_caps_requirement(self, tier: int) -> str:
        return {0: "D", 1: "C", 2: "B", 3: "A"}[tier]
    
    def _caps_sufficient(self, agent_caps: str, required_caps: str) -> bool:
        hierarchy = ["D", "C", "B", "A", "S"]
        return hierarchy.index(agent_caps) >= hierarchy.index(required_caps)
```

---

## 6. GUARDIAN LOGS (IMMUTABLE LEDGER)

### 6.1 Database Schema

```sql
-- guardian_logs table (PostgreSQL)

CREATE TABLE guardian_logs (
    id BIGSERIAL PRIMARY KEY,
    ledger_id VARCHAR(50) UNIQUE NOT NULL,  -- GL-20260125-001234
    timestamp TIMESTAMPTZ NOT NULL,
    
    -- Event details
    event_type VARCHAR(50) NOT NULL,  -- MUTATION_ALLOWED, MUTATION_DENIED, etc.
    agent_id VARCHAR(100) NOT NULL,
    action VARCHAR(50) NOT NULL,  -- CREATE_MODULE, UPDATE_SRS, etc.
    target VARCHAR(255) NOT NULL,  -- Module name
    target_tier INTEGER NOT NULL,
    
    -- Verdict
    verdict VARCHAR(20) NOT NULL,  -- ALLOW, REVIEW, DENY
    reason TEXT NOT NULL,
    risk_score INTEGER NOT NULL,  -- 0-100
    
    -- Economic cost
    cost_xp INTEGER NOT NULL DEFAULT 0,
    cost_tp INTEGER NOT NULL DEFAULT 0,
    
    -- Policy enforcement
    policy_gate VARCHAR(100),
    
    -- Cryptographic chain
    packet_hash VARCHAR(64) NOT NULL,  -- SHA256 of SapientPacket
    prev_hash VARCHAR(64),  -- Hash of previous entry (blockchain-style)
    hash VARCHAR(64) NOT NULL,  -- SHA256 of this entry
    
    -- Indexes
    INDEX idx_agent_id (agent_id),
    INDEX idx_timestamp (timestamp),
    INDEX idx_verdict (verdict),
    INDEX idx_target_tier (target_tier)
);

-- Verify hash chain integrity
CREATE FUNCTION verify_hash_chain(start_ledger_id VARCHAR, end_ledger_id VARCHAR)
RETURNS BOOLEAN AS $$
DECLARE
    current_entry RECORD;
    expected_prev_hash VARCHAR(64);
BEGIN
    FOR current_entry IN
        SELECT * FROM guardian_logs
        WHERE ledger_id BETWEEN start_ledger_id AND end_ledger_id
        ORDER BY timestamp ASC
    LOOP
        IF current_entry.prev_hash IS NOT NULL THEN
            IF current_entry.prev_hash != expected_prev_hash THEN
                RETURN FALSE;  -- Chain broken!
            END IF;
        END IF;
        
        expected_prev_hash := current_entry.hash;
    END LOOP;
    
    RETURN TRUE;  -- Chain intact
END;
$$ LANGUAGE plpgsql;
```

### 6.2 Audit Trail Verification

```python
# ags/audit_verifier.py

class AuditVerifier:
    """
    Verify guardian_logs hash chain integrity.
    """
    
    def __init__(self, db_client):
        self.db = db_client
    
    async def verify_chain(
        self,
        start_date: str,
        end_date: str
    ) -> Dict:
        """
        Verify hash chain for date range.
        
        Returns:
          {
            "valid": bool,
            "entries_checked": int,
            "broken_at": str (ledger_id if broken),
            "error": str (if broken)
          }
        """
        # Fetch all entries in date range
        entries = await self.db.fetch(
            """
            SELECT * FROM guardian_logs
            WHERE timestamp BETWEEN $1 AND $2
            ORDER BY timestamp ASC
            """,
            start_date, end_date
        )
        
        if not entries:
            return {"valid": True, "entries_checked": 0}
        
        # Verify each link
        for i in range(1, len(entries)):
            current = entries[i]
            previous = entries[i - 1]
            
            # Check prev_hash matches previous entry's hash
            if current["prev_hash"] != previous["hash"]:
                return {
                    "valid": False,
                    "entries_checked": i,
                    "broken_at": current["ledger_id"],
                    "error": f"Hash mismatch: expected {previous['hash']}, got {current['prev_hash']}"
                }
            
            # Verify current entry's hash
            calculated_hash = self._calculate_hash(current)
            if calculated_hash != current["hash"]:
                return {
                    "valid": False,
                    "entries_checked": i,
                    "broken_at": current["ledger_id"],
                    "error": f"Entry hash invalid: expected {calculated_hash}, got {current['hash']}"
                }
        
        return {
            "valid": True,
            "entries_checked": len(entries),
            "broken_at": None,
            "error": None
        }
    
    def _calculate_hash(self, entry: Dict) -> str:
        """Recalculate hash for verification."""
        hashable = {
            k: v for k, v in entry.items()
            if k not in ["id", "hash"]  # Exclude auto-generated fields
        }
        canonical = json.dumps(hashable, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()
```

---

## 7. IMPLEMENTATION GUIDE

### 7.1 Quick Start

```bash
# 1. Install AGS
pip install ags-system==1.0.0

# 2. Initialize
ags init --workspace .

# 3. Load policy gates
ags policy load --dir ./policies

# 4. Start AGS service
ags serve --port 8080
```

### 7.2 API Integration

```python
# Example: Validate mutation through AGS

import ags

client = ags.Client(url="http://localhost:8080")

# Submit mutation
result = await client.validate_mutation(
    action="UPDATE_MODULE",
    target={
        "module": "payment_retry.py",
        "tier": 2
    },
    agent_id="gm_payments_master",
    changes={
        "add_prd": {
            "id": "PRD-PAYMENT-004",
            "title": "Circuit Breaker"
        }
    }
)

# Check verdict
if result["verdict"] == "ALLOW":
    print(f"✅ Mutation allowed (cost: {result['cost_xp']} XP, {result['cost_tp']} TP)")
    print(f"Ledger ID: {result['ledger_id']}")

elif result["verdict"] == "DENY":
    print(f"❌ Mutation denied: {result['reason']}")

elif result["verdict"] == "REVIEW":
    print(f"⚠️ Mutation requires human review: {result['reason']}")
    print(f"Escalate to: {result['escalation']}")
```

---

## 8. API REFERENCE

### 8.1 REST Endpoints

```yaml
POST /ags/validate
  Description: Validate mutation through 4-stage pipeline
  Request:
    {
      "action": "UPDATE_MODULE | CREATE_MODULE | ...",
      "target": {"module": str, "tier": int},
      "agent_id": str,
      "changes": dict
    }
  Response:
    {
      "verdict": "ALLOW | REVIEW | DENY",
      "reason": str,
      "ledger_id": str,
      "cost_xp": int,
      "cost_tp": int
    }

GET /ags/audit/{ledger_id}
  Description: Fetch guardian_logs entry
  Response:
    {
      "ledger_id": str,
      "timestamp": str,
      "verdict": str,
      "agent_id": str,
      "hash": str,
      "prev_hash": str
    }

POST /ags/audit/verify
  Description: Verify hash chain integrity
  Request:
    {
      "start_date": "2026-01-01",
      "end_date": "2026-01-31"
    }
  Response:
    {
      "valid": bool,
      "entries_checked": int,
      "broken_at": str (if invalid)
    }
```

---

**AGS is the constitutional backbone of Citadel—ensuring every mutation is validated, every decision is recorded, and governance is transparent, immutable, and AI-native.**
