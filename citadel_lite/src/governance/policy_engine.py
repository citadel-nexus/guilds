# src/governance/policy_engine.py
"""
Responsible AI policy engine for Citadel Lite.

Loads governance policies from YAML and provides:
- Policy lookup by ID
- Compliance report generation
- Policy violation detection
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


@dataclass
class Policy:
    id: str = ""
    name: str = ""
    description: str = ""
    enforcement: str = ""
    risk_threshold: Optional[float] = None
    action: Optional[str] = None
    trigger: Optional[str] = None


@dataclass
class ComplianceMapping:
    standard: str = ""
    alignment: str = ""


class PolicyEngine:
    """Loads and queries governance policies."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or (Path(__file__).parent / "policies.yaml")
        self.principles: List[Policy] = []
        self.governance_rules: List[Policy] = []
        self.compliance: List[ComplianceMapping] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists() or not _HAS_YAML:
            return

        data = yaml.safe_load(self.path.read_text(encoding="utf-8"))

        self.principles = [
            Policy(
                id=p.get("id", ""),
                name=p.get("name", ""),
                description=p.get("description", ""),
                enforcement=p.get("enforcement", ""),
            )
            for p in data.get("principles", [])
        ]

        self.governance_rules = [
            Policy(
                id=r.get("id", ""),
                name=r.get("name", ""),
                description=r.get("description", ""),
                risk_threshold=r.get("risk_threshold"),
                action=r.get("action"),
                trigger=r.get("trigger"),
            )
            for r in data.get("governance_rules", [])
        ]

        self.compliance = [
            ComplianceMapping(
                standard=c.get("standard", ""),
                alignment=c.get("alignment", ""),
            )
            for c in data.get("compliance", [])
        ]

    def get_policy(self, policy_id: str) -> Optional[Policy]:
        """Look up a policy by ID."""
        for p in self.principles + self.governance_rules:
            if p.id == policy_id:
                return p
        return None

    def check_compliance(self, decision_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check a decision against all policies and return compliance report.
        """
        risk_score = decision_data.get("risk_score", 0)
        action = decision_data.get("action", "")
        policy_refs = decision_data.get("policy_refs", [])

        violations: List[str] = []
        satisfied: List[str] = []

        # Check governance rules
        for rule in self.governance_rules:
            if rule.risk_threshold is not None:
                if rule.action == "approve" and risk_score < rule.risk_threshold:
                    if action == "approve":
                        satisfied.append(rule.id)
                    elif action in ("need_approval", "block"):
                        satisfied.append(rule.id)  # stricter is fine
                elif rule.action == "block" and risk_score >= (rule.risk_threshold or 0):
                    if action != "block":
                        violations.append(f"{rule.id}: risk {risk_score} >= threshold, expected block")
                    else:
                        satisfied.append(rule.id)

        # Check RAI principles are referenced
        for principle in self.principles:
            if principle.id in policy_refs:
                satisfied.append(principle.id)

        return {
            "compliant": len(violations) == 0,
            "violations": violations,
            "satisfied_policies": satisfied,
            "total_policies": len(self.principles) + len(self.governance_rules),
            "compliance_standards": [
                {"standard": c.standard, "alignment": c.alignment}
                for c in self.compliance
            ],
        }

    def generate_report(self) -> Dict[str, Any]:
        """Generate a full policy inventory report."""
        return {
            "framework": "Citadel Responsible AI Framework",
            "principles": [
                {"id": p.id, "name": p.name, "description": p.description}
                for p in self.principles
            ],
            "governance_rules": [
                {"id": r.id, "name": r.name, "action": r.action, "threshold": r.risk_threshold}
                for r in self.governance_rules
            ],
            "compliance_mappings": [
                {"standard": c.standard, "alignment": c.alignment}
                for c in self.compliance
            ],
        }
