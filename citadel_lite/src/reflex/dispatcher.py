# src/reflex/dispatcher.py
"""
Simplified reflex dispatcher for Citadel Lite.
Loads declarative YAML rules and matches them against event/decision context.

Adapted from CNWB src/runtime/reflex_dispatcher.py (340 lines → ~100 lines).
Removes CAPS/TP gating for hackathon simplicity while keeping the pattern.
"""
from __future__ import annotations

import ast
import operator
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False
    import json


@dataclass
class ReflexRule:
    """A single declarative reflex rule."""
    id: str = ""
    trigger: str = ""
    condition: str = ""
    action: str = ""
    description: str = ""
    enabled: bool = True


@dataclass
class ReflexResult:
    """Result of executing a reflex rule."""
    rule_id: str = ""
    action: str = ""
    success: bool = False
    details: str = ""


# ---------- Action Handlers ----------

_ACTION_REGISTRY: Dict[str, Callable[[Dict[str, Any]], ReflexResult]] = {}


def reflex_action(name: str):
    """Decorator to register a reflex action handler."""
    def decorator(fn: Callable[[Dict[str, Any]], ReflexResult]):
        _ACTION_REGISTRY[name] = fn
        return fn
    return decorator


@reflex_action("auto_fix_and_rerun")
def _auto_fix_and_rerun(ctx: Dict[str, Any]) -> ReflexResult:
    return ReflexResult(
        rule_id=ctx.get("rule_id", ""),
        action="auto_fix_and_rerun",
        success=True,
        details="Low-risk: auto-fix approved, proceeding to execution",
    )


@reflex_action("request_approval")
def _request_approval(ctx: Dict[str, Any]) -> ReflexResult:
    return ReflexResult(
        rule_id=ctx.get("rule_id", ""),
        action="request_approval",
        success=True,
        details="Medium-risk: routing to human approval",
    )


@reflex_action("escalate_and_block")
def _escalate_and_block(ctx: Dict[str, Any]) -> ReflexResult:
    return ReflexResult(
        rule_id=ctx.get("rule_id", ""),
        action="escalate_and_block",
        success=True,
        details="High-risk/critical: blocked and escalated",
    )


@reflex_action("log_and_alert")
def _log_and_alert(ctx: Dict[str, Any]) -> ReflexResult:
    return ReflexResult(
        rule_id=ctx.get("rule_id", ""),
        action="log_and_alert",
        success=True,
        details="Logged and alert sent",
    )


# ---------- Manifest ----------

class ReflexManifest:
    """Loads and matches reflex rules from a YAML manifest."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or (Path(__file__).parent / "manifest.yaml")
        self.rules: List[ReflexRule] = []
        self.reload()

    def reload(self) -> None:
        """Load rules from manifest file."""
        if not self.path.exists():
            self.rules = []
            return

        raw_text = self.path.read_text(encoding="utf-8")

        if _HAS_YAML:
            data = yaml.safe_load(raw_text)
        else:
            # Fallback: rudimentary YAML parsing not possible without pyyaml
            # For MVP, return empty if yaml not available
            self.rules = []
            return

        self.rules = [
            ReflexRule(
                id=r.get("id", ""),
                trigger=r.get("trigger", ""),
                condition=r.get("condition", ""),
                action=r.get("action", ""),
                description=r.get("description", ""),
                enabled=r.get("enabled", True),
            )
            for r in data.get("rules", [])
        ]

    def match(self, event_type: str, context: Dict[str, Any]) -> List[ReflexRule]:
        """Return rules whose trigger and condition match the given context."""
        matched = []
        for rule in self.rules:
            if not rule.enabled:
                continue
            if rule.trigger and rule.trigger != event_type:
                continue
            if rule.condition and not _eval_condition(rule.condition, context):
                continue
            matched.append(rule)
        return matched


_SAFE_COMPARE_OPS = {
    ast.Lt: operator.lt,
    ast.Gt: operator.gt,
    ast.LtE: operator.le,
    ast.GtE: operator.ge,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}

_SAFE_BOOL_OPS = {
    ast.And: all,
    ast.Or: any,
}


def _eval_condition(condition: str, context: Dict[str, Any]) -> bool:
    """
    Evaluate a simple condition string against a context dict.
    Supports: <, >, <=, >=, ==, !=, 'and', 'or'
    Variables are looked up in context dict.

    Uses ``ast.parse()`` instead of ``eval()`` to prevent arbitrary
    code execution.  Only literal constants, variable names (looked up
    in *context*), comparisons, and boolean operators are allowed.
    """
    if not condition.strip():
        return True
    try:
        tree = ast.parse(condition, mode="eval")
        return bool(_eval_node(tree.body, context))
    except Exception:
        return False


def _eval_node(node: ast.AST, ctx: Dict[str, Any]) -> Any:
    """Recursively evaluate a white-listed AST node."""
    # Literal values (numbers, strings, True/False/None)
    if isinstance(node, ast.Constant):
        return node.value

    # Variable name → look up in context
    if isinstance(node, ast.Name):
        if node.id in ("True", "False", "None"):
            return {"True": True, "False": False, "None": None}[node.id]
        if node.id not in ctx:
            raise ValueError(f"Unknown variable: {node.id}")
        return ctx[node.id]

    # Comparison: a < b, x == y, 1 <= z <= 10
    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, ctx)
        for op, comparator in zip(node.ops, node.comparators):
            op_func = _SAFE_COMPARE_OPS.get(type(op))
            if op_func is None:
                raise ValueError(f"Unsupported comparison: {type(op).__name__}")
            right = _eval_node(comparator, ctx)
            if not op_func(left, right):
                return False
            left = right
        return True

    # Boolean: x > 1 and y < 5
    if isinstance(node, ast.BoolOp):
        func = _SAFE_BOOL_OPS.get(type(node.op))
        if func is None:
            raise ValueError(f"Unsupported bool op: {type(node.op).__name__}")
        return func(_eval_node(v, ctx) for v in node.values)

    # Unary not
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _eval_node(node.operand, ctx)

    raise ValueError(f"Unsupported expression: {type(node).__name__}")


# ---------- Dispatcher ----------

class ReflexDispatcher:
    """
    Matches reflex rules against events and executes action handlers.
    """

    def __init__(self, manifest: Optional[ReflexManifest] = None) -> None:
        self.manifest = manifest or ReflexManifest()

    def dispatch(
        self,
        event_type: str,
        context: Dict[str, Any],
    ) -> List[ReflexResult]:
        """Match rules and execute their actions. Returns list of results."""
        matched = self.manifest.match(event_type, context)
        results = []

        for rule in matched:
            handler = _ACTION_REGISTRY.get(rule.action)
            if handler is None:
                results.append(ReflexResult(
                    rule_id=rule.id,
                    action=rule.action,
                    success=False,
                    details=f"Unknown action: {rule.action}",
                ))
                continue

            ctx = {**context, "rule_id": rule.id}
            result = handler(ctx)
            results.append(result)

        return results
