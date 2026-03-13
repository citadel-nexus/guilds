"""
VCC Order contracts — BuildRequest / BuildResult dataclasses.

These are the thin JSON contracts between Citadel Lite and the VCC
(Virtual Construction Crew).  Schema identifiers use semver slugs so
that schema evolution can be tracked without breaking consumers.

CGRF compliance
---------------
_MODULE_NAME    = "orders"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "CONTRACT"
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

# ── CGRF Metadata ────────────────────────────────────────────────────────────
_MODULE_NAME    = "orders"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "CONTRACT"
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class BuildRequest:
    """
    Citadel Lite → VCC: request to start a build cycle.

    ``target``, ``constraints``, and ``context`` are open dicts so that
    VCC can evolve its schema without forcing changes here.
    """
    schema: str = "vcc.build_request.v1"
    order_id: str = ""
    repo: str = ""
    target: Dict[str, Any] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "order_id": self.order_id,
            "repo": self.repo,
            "target": self.target,
            "constraints": self.constraints,
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BuildRequest":
        return cls(
            schema=data.get("schema", "vcc.build_request.v1"),
            order_id=data.get("order_id", ""),
            repo=data.get("repo", ""),
            target=data.get("target", {}),
            constraints=data.get("constraints", {}),
            context=data.get("context", {}),
        )


@dataclass
class BuildResult:
    """
    VCC → Citadel Lite: result of a completed build cycle.

    ``build_checks_passed`` summarises the CRP guardrail status.
    The raw test counts (vcc_test_*) are included in ``metrics``.
    """
    schema: str = "vcc.build_result.v1"
    order_id: str = ""
    status: str = "ok"           # "ok" | "error" | "partial" | "dry_run" | "stub"
    artifacts: Dict[str, Any] = field(default_factory=dict)
    crp_cycle_id: str = ""
    notes: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)
    build_checks_passed: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "order_id": self.order_id,
            "status": self.status,
            "artifacts": self.artifacts,
            "crp_cycle_id": self.crp_cycle_id,
            "notes": self.notes,
            "metrics": self.metrics,
            "build_checks_passed": self.build_checks_passed,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BuildResult":
        return cls(
            schema=data.get("schema", "vcc.build_result.v1"),
            order_id=data.get("order_id", ""),
            status=data.get("status", "ok"),
            artifacts=data.get("artifacts", {}),
            crp_cycle_id=data.get("crp_cycle_id", ""),
            notes=data.get("notes", ""),
            metrics=data.get("metrics", {}),
            build_checks_passed=data.get("build_checks_passed", True),
        )
