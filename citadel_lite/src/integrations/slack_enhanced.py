# src/integrations/slack_enhanced.py
"""
Enhanced Slack integration with bidirectional communication.

Extends the existing webhook-based notifications with:
- Interactive message buttons (approve/reject via Slack)
- Slash command handling (/citadel status, /citadel run, /citadel memory)
- Thread-based incident conversations
- Rich Block Kit formatting with incident cards

Falls back to basic webhook notifications if Bot token not configured.

Usage:
    from src.integrations.slack_enhanced import SlackBot
    bot = SlackBot(bot_token="xoxb-...", signing_secret="...")
    bot.send_incident_card(channel, event_id, summary, risk_score, decision)
    bot.handle_interaction(payload)  # Button clicks
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

_SLACK_API = "https://slack.com/api"


class SlackBot:
    """
    Enhanced Slack bot with interactive messages and slash commands.
    Uses Bot Token for full API access (vs just incoming webhooks).
    """

    def __init__(
        self,
        bot_token: str = "",
        signing_secret: str = "",
        default_channel: str = "#citadel-alerts",
    ) -> None:
        self._token = bot_token
        self._signing_secret = signing_secret
        self._channel = default_channel
        self._headers = {
            "Authorization": f"Bearer {bot_token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    @property
    def is_available(self) -> bool:
        return bool(self._token and _HAS_HTTPX)

    # ---- Send Incident Card ----

    def send_incident_card(
        self,
        event_id: str,
        event_type: str,
        summary: str,
        risk_score: float,
        decision: str,
        rationale: str = "",
        channel: Optional[str] = None,
        thread_ts: Optional[str] = None,
    ) -> Optional[str]:
        """Send a rich incident card with interactive approve/reject buttons. Returns message ts."""
        if not self.is_available:
            return None

        risk_emoji = ":white_check_mark:" if risk_score < 0.3 else ":warning:" if risk_score < 0.6 else ":red_circle:"
        decision_emoji = {
            "approve": ":white_check_mark:",
            "block": ":no_entry:",
            "need_approval": ":hourglass:",
        }.get(decision, ":question:")

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"Citadel Lite — {event_type.upper()}"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Event:*\n`{event_id[:16]}`"},
                    {"type": "mrkdwn", "text": f"*Risk:*\n{risk_emoji} {risk_score:.2f}"},
                    {"type": "mrkdwn", "text": f"*Decision:*\n{decision_emoji} {decision.upper()}"},
                    {"type": "mrkdwn", "text": f"*Type:*\n{event_type}"},
                ],
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Summary:*\n{summary[:500]}"},
            },
        ]

        if rationale:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Rationale:*\n{rationale[:500]}"},
            })

        # Interactive buttons for approval
        if decision == "need_approval":
            blocks.append({
                "type": "actions",
                "block_id": f"approval_{event_id[:16]}",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Approve"},
                        "style": "primary",
                        "action_id": "citadel_approve",
                        "value": event_id,
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Reject"},
                        "style": "danger",
                        "action_id": "citadel_reject",
                        "value": event_id,
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "View Details"},
                        "action_id": "citadel_details",
                        "value": event_id,
                    },
                ],
            })

        blocks.append({"type": "divider"})
        blocks.append({
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f":robot_face: Citadel Lite Agentic Pipeline | {event_id[:12]}"},
            ],
        })

        body: Dict[str, Any] = {
            "channel": channel or self._channel,
            "blocks": blocks,
            "text": f"[{event_type}] {summary[:100]}",
        }
        if thread_ts:
            body["thread_ts"] = thread_ts

        return self._post("chat.postMessage", body)

    # ---- Pipeline Complete Notification ----

    def send_pipeline_complete(
        self,
        event_id: str,
        decision: str,
        risk_score: float,
        pr_url: str = "",
        channel: Optional[str] = None,
    ) -> Optional[str]:
        """Send pipeline completion summary."""
        if not self.is_available:
            return None

        emoji = ":white_check_mark:" if decision == "approve" else ":no_entry:" if decision == "block" else ":hourglass:"
        text = f"{emoji} Pipeline complete for `{event_id[:12]}` — *{decision.upper()}* (risk {risk_score:.2f})"
        if pr_url:
            text += f"\n:link: <{pr_url}|View PR>"

        body = {
            "channel": channel or self._channel,
            "text": text,
        }
        return self._post("chat.postMessage", body)

    # ---- Slash Command Handling ----

    def handle_slash_command(self, command: str, text: str, user_id: str) -> Dict[str, Any]:
        """
        Handle /citadel slash commands.
        Returns Slack response payload.

        Commands:
            /citadel status     - Current pipeline status
            /citadel memory <q> - Search memory KB
            /citadel history    - Recent pipeline runs
            /citadel skills     - List agent skills
        """
        parts = text.strip().split(maxsplit=1)
        sub = parts[0].lower() if parts else "help"
        arg = parts[1] if len(parts) > 1 else ""

        if sub == "status":
            return {
                "response_type": "ephemeral",
                "text": ":robot_face: Citadel Lite is online. Use the dashboard for real-time monitoring.",
            }
        elif sub == "memory":
            return {
                "response_type": "ephemeral",
                "text": f":brain: Memory search for `{arg}` — use the dashboard Memory menu for full results.",
            }
        elif sub == "history":
            return {
                "response_type": "ephemeral",
                "text": ":scroll: Recent pipeline history — check the dashboard for details.",
            }
        elif sub == "skills":
            return {
                "response_type": "ephemeral",
                "text": ":gear: Agent skills: Sentinel (detect, classify), Sherlock (diagnose, root_cause), Fixer (patch, dependency), Guardian (risk_gate, approval).",
            }
        else:
            return {
                "response_type": "ephemeral",
                "text": ":wave: Citadel Lite commands: `status`, `memory <query>`, `history`, `skills`",
            }

    # ---- Interaction Handling ----

    def handle_interaction(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle interactive message button clicks (approve/reject).
        Returns action details for the orchestrator.
        """
        actions = payload.get("actions", [])
        user = payload.get("user", {})
        action_result = {
            "action": None,
            "event_id": None,
            "user_id": user.get("id", ""),
            "user_name": user.get("username", ""),
        }

        for action in actions:
            action_id = action.get("action_id", "")
            event_id = action.get("value", "")

            if action_id == "citadel_approve":
                action_result["action"] = "approve"
                action_result["event_id"] = event_id
            elif action_id == "citadel_reject":
                action_result["action"] = "reject"
                action_result["event_id"] = event_id
            elif action_id == "citadel_details":
                action_result["action"] = "details"
                action_result["event_id"] = event_id

        return action_result

    # ---- Signature Verification ----

    def verify_signature(self, body: bytes, timestamp: str, signature: str) -> bool:
        """Verify Slack request signature for security."""
        if not self._signing_secret:
            return True  # Skip if not configured

        if abs(time.time() - float(timestamp)) > 300:
            return False

        base = f"v0:{timestamp}:{body.decode('utf-8')}"
        computed = "v0=" + hmac.new(
            self._signing_secret.encode(),
            base.encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(computed, signature)

    # ---- Internal ----

    def _post(self, method: str, body: Dict[str, Any]) -> Optional[str]:
        """Post to Slack API. Returns message ts on success."""
        if not _HAS_HTTPX:
            return None
        try:
            resp = httpx.post(
                f"{_SLACK_API}/{method}",
                headers=self._headers,
                json=body,
                timeout=10.0,
            )
            data = resp.json()
            if data.get("ok"):
                return data.get("ts")
            else:
                logger.warning("Slack API error: %s", data.get("error", "unknown"))
                return None
        except Exception as e:
            logger.warning("Slack API call failed: %s", e)
            return None
