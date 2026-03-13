# src/approval/request.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List


def _clamp_str(s: Any, max_len: int) -> str:
    text = "" if s is None else str(s)
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _get(d: Dict[str, Any], path: List[str], default: Any = None) -> Any:
    cur: Any = d
    for key in path:
        if not isinstance(cur, dict):
            return default
        if key not in cur:
            return default
        cur = cur[key]
    return cur


def build_approval_request(audit_report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build minimal approval request payload for Slack/Teams.
    MVP contract:
      - contains a short message text
      - contains structured fields for UI rendering later
      - includes pointers (event_id, repo, ref, links)
    """
    event_id = _get(audit_report, ["event", "event_id"], "")
    repo = _get(audit_report, ["event", "repo"], "")
    ref = _get(audit_report, ["event", "ref"], "")
    event_type = _get(audit_report, ["event", "event_type"], "")

    decision = _get(audit_report, ["decision"], {}) or {}
    action = decision.get("action", "")
    risk_score = decision.get("risk_score", None)
    policy_refs = decision.get("policy_refs", []) or []
    rationale = decision.get("rationale", "")

    summary = audit_report.get("summary", "")
    event_summary = _get(audit_report, ["event", "summary"], "")
    hypotheses = _get(audit_report, ["diagnosis", "hypotheses"], []) or []
    fix_plan = _get(audit_report, ["proposed_fix", "fix_plan"], "")
    links = _get(audit_report, ["artifacts", "links"], []) or []

    # Slack/Teams向けの短文（MVP）
    msg_lines = [
        "Approval required: CI incident needs human review.",
        f"- event_id: {event_id}",
        f"- repo: {repo}",
        f"- ref: {ref}",
        f"- type: {event_type}",
        f"- decision: {action} (risk={risk_score})",
        f"- rationale: {_clamp_str(rationale, 200)}",
        f"- summary: {_clamp_str(event_summary, 240)}",
    ]
    if hypotheses:
        h0 = hypotheses[0]
        if isinstance(h0, dict):
            h_text = h0.get("title") or h0.get("explanation", "")
            h_conf = int(h0.get("confidence", 0) * 100)
            msg_lines.append(f"- top_hypothesis: {_clamp_str(h_text, 160)} (confidence: {h_conf}%)")
        else:
            msg_lines.append(f"- top_hypothesis: {_clamp_str(str(h0), 160)}")
    if fix_plan:
        msg_lines.append(f"- proposed_fix: {_clamp_str(fix_plan, 240)}")
    if links:
        msg_lines.append(f"- link: {links[0]}")

    return {
        "schema_version": "approval_request_v0",
        "generated_at": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        "channel": "slack_or_teams",
        "event_id": event_id,
        "repo": repo,
        "ref": ref,
        "event_type": event_type,
        "decision": {
            "action": action,
            "risk_score": risk_score,
            "policy_refs": policy_refs,
        },
        "message": "\n".join(msg_lines),
        "fields": {
            "summary": summary,
            "rationale": rationale,
            "hypotheses": hypotheses,
            "proposed_fix": fix_plan,
            "links": links,
        },
        "actions": [
            {"id": "approve", "label": "Approve"},
            {"id": "reject", "label": "Reject"},
            {"id": "request_changes", "label": "Request changes"},
        ],
    }