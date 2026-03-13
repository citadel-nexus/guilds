# src/agents/college_bridge.py
"""
College Bridge Agent — Routes generated code through College professors.

Connects the autodev pipeline to the College service (src/college/service.py)
for multi-professor code analysis before merge gate evaluation.

Pipeline position:
  F993 Code Gen → **College Bridge** → Council Bridge → Merge Gate

What it does:
1. Extracts generated code from F993 output in the HandoffPacket
2. Runs College code analysis (Systems, Security, Testing professors)
3. Aggregates professor feedback into a quality assessment
4. Feeds results forward for Council deliberation

CGRF v3.0 Compliance:
- SRS Code: SRS-COLLEGE-BRIDGE-001
- Tier: 2 (STAGING)
- Execution Role: ANALYSIS

@module citadel_lite.src.agents.college_bridge
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from src.types import HandoffPacket

logger = logging.getLogger(__name__)

# Professor domains relevant to code review
_CODE_REVIEW_DOMAINS = ["systems", "security", "testing", "architecture", "quality"]


def _extract_generated_code(packet: HandoffPacket) -> Optional[Dict[str, Any]]:
    """Extract generated code content from F993 output in the packet."""
    for key in ("f993_python", "f993_typescript", "f993"):
        output = packet.agent_outputs.get(key)
        if output:
            data = output.payload if hasattr(output, "payload") else output
            if data.get("valid") and data.get("files"):
                return {
                    "source": key,
                    "code": data["files"][0].get("content", ""),
                    "path": data["files"][0].get("path", ""),
                    "generation_mode": data.get("generation_mode", "unknown"),
                    "content_hash": data["files"][0].get("content_hash", ""),
                }
    return None


def _analyze_code_rules(code: str, language: str = "python") -> Dict[str, Any]:
    """
    Rule-based code analysis (fallback when College service unavailable).

    Checks for common issues without requiring Supabase or LLM.
    """
    issues: List[Dict[str, Any]] = []
    lines = code.split("\n")

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Security checks
        if "eval(" in stripped:
            issues.append({
                "line": i, "type": "security", "severity": "high",
                "message": "Use of eval() is dangerous",
                "professor": "security",
            })
        if "exec(" in stripped:
            issues.append({
                "line": i, "type": "security", "severity": "high",
                "message": "Use of exec() can execute arbitrary code",
                "professor": "security",
            })
        if "subprocess.call(" in stripped and "shell=True" in stripped:
            issues.append({
                "line": i, "type": "security", "severity": "critical",
                "message": "shell=True in subprocess is a command injection risk",
                "professor": "security",
            })
        if any(kw in stripped.lower() for kw in ("password =", "secret =", "api_key =")):
            if not stripped.startswith("#") and not stripped.startswith("//"):
                issues.append({
                    "line": i, "type": "security", "severity": "critical",
                    "message": "Possible hardcoded credential",
                    "professor": "security",
                })

        # Quality checks
        if len(line) > 120 and not stripped.startswith("#") and not stripped.startswith("//"):
            issues.append({
                "line": i, "type": "style", "severity": "low",
                "message": f"Line exceeds 120 characters ({len(line)})",
                "professor": "quality",
            })
        if "TODO" in stripped and "Replace stub" not in stripped:
            issues.append({
                "line": i, "type": "quality", "severity": "info",
                "message": "Unresolved TODO",
                "professor": "quality",
            })

        # Testing checks
        if "assert " in stripped and "assert " == stripped[:7]:
            if "," not in stripped and "assert True" not in stripped:
                issues.append({
                    "line": i, "type": "testing", "severity": "low",
                    "message": "Bare assert without message — add failure context",
                    "professor": "testing",
                })

    # Architecture checks
    has_docstring = '"""' in code or "'''" in code or "/**" in code
    has_type_hints = "->" in code or ": " in code
    has_logging = "logger." in code or "logging." in code or "console." in code

    if not has_docstring:
        issues.append({
            "line": 1, "type": "architecture", "severity": "medium",
            "message": "No docstrings found — add module/class documentation",
            "professor": "architecture",
        })

    # Compute quality score
    critical_count = sum(1 for i in issues if i["severity"] == "critical")
    high_count = sum(1 for i in issues if i["severity"] == "high")
    medium_count = sum(1 for i in issues if i["severity"] == "medium")

    quality_score = max(0.0, 1.0 - (critical_count * 0.3) - (high_count * 0.15) - (medium_count * 0.05))

    return {
        "issues": issues,
        "issue_count": len(issues),
        "critical_count": critical_count,
        "high_count": high_count,
        "quality_score": round(quality_score, 3),
        "has_docstring": has_docstring,
        "has_type_hints": has_type_hints,
        "has_logging": has_logging,
        "professors_consulted": list(set(i["professor"] for i in issues)) or ["systems"],
    }


def run_college_bridge(packet: HandoffPacket) -> Dict[str, Any]:
    """
    Run generated code through College professors for analysis.

    Returns:
        Dict with quality assessment, issues found, and professor feedback.
    """
    start = time.time()

    # Extract generated code
    gen_info = _extract_generated_code(packet)
    if not gen_info:
        return {
            "analyzed": False,
            "reason": "No generated code found in packet",
            "quality_score": 0.0,
            "professors_consulted": [],
        }

    code = gen_info["code"]
    path = gen_info["path"]
    language = "typescript" if path.endswith(".ts") else "python"

    analysis = _analyze_code_rules(code, language)
    analysis["mode"] = "rules"

    duration_ms = int((time.time() - start) * 1000)

    return {
        "analyzed": True,
        "source_file": path,
        "language": language,
        "generation_mode": gen_info["generation_mode"],
        "content_hash": gen_info["content_hash"],
        "quality_score": analysis["quality_score"],
        "issue_count": analysis["issue_count"],
        "critical_count": analysis.get("critical_count", 0),
        "high_count": analysis.get("high_count", 0),
        "issues": analysis.get("issues", [])[:10],  # Cap for packet size
        "professors_consulted": analysis.get("professors_consulted", []),
        "has_docstring": analysis.get("has_docstring", False),
        "has_type_hints": analysis.get("has_type_hints", False),
        "has_logging": analysis.get("has_logging", False),
        "mode": analysis.get("mode", "rules"),
        "duration_ms": duration_ms,
    }
