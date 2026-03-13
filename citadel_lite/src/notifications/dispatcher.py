# src/notifications/dispatcher.py
"""
Notification dispatcher for pipeline events.

Sends alerts to configured channels: Slack, Teams, generic webhook.
All channels are optional — if no URL is configured, the call is a no-op.

Usage:
    from src.notifications.dispatcher import NotificationDispatcher
    notifier = NotificationDispatcher(config)
    notifier.send_approval_request(event, decision, approval_url)
    notifier.send_pipeline_complete(event, decision, outcome)
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class NotificationDispatcher:
    """Routes notifications to Slack, Teams, and/or generic webhooks."""

    def __init__(self, config: Any = None) -> None:
        if config is None:
            from src.config import get_config
            config = get_config()
        self._config = config
        self._httpx = self._get_httpx()

    @staticmethod
    def _get_httpx():
        try:
            import httpx
            return httpx
        except ImportError:
            return None

    @property
    def is_available(self) -> bool:
        return self._httpx is not None and self._config.has_notifications

    # ---- Public API ----

    def send_approval_request(
        self,
        event_id: str,
        event_type: str,
        summary: str,
        risk_score: float,
        decision_action: str,
        rationale: str = "",
        approval_url: str = "",
    ) -> None:
        """Send approval request to configured notification channels."""
        payload = {
            "type": "approval_request",
            "event_id": event_id,
            "event_type": event_type,
            "summary": summary,
            "risk_score": risk_score,
            "decision": decision_action,
            "rationale": rationale,
            "approval_url": approval_url,
        }

        if self._config.has_slack:
            self._send_slack_approval(payload)
        if self._config.has_teams:
            self._send_teams_approval(payload)
        if self._config.notification_webhook_url:
            self._send_webhook(payload)

    def send_pipeline_complete(
        self,
        event_id: str,
        event_type: str,
        decision_action: str,
        risk_score: float,
        outcome_details: str = "",
        pr_url: str = "",
    ) -> None:
        """Notify on pipeline completion."""
        payload = {
            "type": "pipeline_complete",
            "event_id": event_id,
            "event_type": event_type,
            "decision": decision_action,
            "risk_score": risk_score,
            "outcome": outcome_details,
            "pr_url": pr_url,
        }

        if self._config.has_slack:
            self._send_slack_complete(payload)
        if self._config.has_teams:
            self._send_teams_complete(payload)
        if self._config.notification_webhook_url:
            self._send_webhook(payload)

    def send_alert(
        self,
        event_id: str,
        severity: str,
        message: str,
    ) -> None:
        """Send a generic alert."""
        payload = {
            "type": "alert",
            "event_id": event_id,
            "severity": severity,
            "message": message,
        }

        if self._config.has_slack:
            self._post_slack({"text": f":rotating_light: [{severity.upper()}] {message}\nEvent: `{event_id}`"})
        if self._config.notification_webhook_url:
            self._send_webhook(payload)

    # ---- Slack ----

    def _send_slack_approval(self, payload: Dict[str, Any]) -> None:
        risk_emoji = ":white_check_mark:" if payload["risk_score"] < 0.3 else ":warning:" if payload["risk_score"] < 0.6 else ":red_circle:"
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "Citadel Lite — Approval Required"}
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Event:* `{payload['event_id'][:12]}`"},
                    {"type": "mrkdwn", "text": f"*Type:* {payload['event_type']}"},
                    {"type": "mrkdwn", "text": f"*Risk:* {risk_emoji} {payload['risk_score']:.2f}"},
                    {"type": "mrkdwn", "text": f"*Decision:* {payload['decision']}"},
                ]
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Summary:* {payload['summary'][:200]}"}
            },
        ]
        if payload.get("rationale"):
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Rationale:* {payload['rationale'][:300]}"}
            })
        if payload.get("approval_url"):
            blocks.append({
                "type": "actions",
                "elements": [
                    {"type": "button", "text": {"type": "plain_text", "text": "Review"}, "url": payload["approval_url"]},
                ]
            })

        self._post_slack({"channel": self._config.slack_channel, "blocks": blocks})

    def _send_slack_complete(self, payload: Dict[str, Any]) -> None:
        emoji = ":white_check_mark:" if payload["decision"] == "approve" else ":no_entry:" if payload["decision"] == "block" else ":hourglass:"
        text = f"{emoji} Pipeline complete: *{payload['event_type']}* — {payload['decision'].upper()} (risk {payload['risk_score']:.2f})"
        if payload.get("pr_url"):
            text += f"\n:link: PR: {payload['pr_url']}"
        self._post_slack({"channel": self._config.slack_channel, "text": text})

    def _post_slack(self, body: Dict[str, Any]) -> None:
        if not self._httpx or not self._config.slack_webhook_url:
            return
        try:
            self._httpx.post(self._config.slack_webhook_url, json=body, timeout=10.0)
        except Exception as e:
            logger.warning("Slack notification failed: %s", e)

    # ---- Teams ----

    def _send_teams_approval(self, payload: Dict[str, Any]) -> None:
        card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": "Citadel Lite — Approval Required",
            "themeColor": "FF6600" if payload["risk_score"] >= 0.3 else "00CC00",
            "sections": [{
                "activityTitle": "Approval Required",
                "facts": [
                    {"name": "Event", "value": payload["event_id"][:12]},
                    {"name": "Type", "value": payload["event_type"]},
                    {"name": "Risk", "value": f"{payload['risk_score']:.2f}"},
                    {"name": "Decision", "value": payload["decision"]},
                    {"name": "Summary", "value": payload["summary"][:200]},
                ],
            }],
        }
        if payload.get("approval_url"):
            card["potentialAction"] = [{"@type": "OpenUri", "name": "Review", "targets": [{"os": "default", "uri": payload["approval_url"]}]}]
        self._post_teams(card)

    def _send_teams_complete(self, payload: Dict[str, Any]) -> None:
        card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": f"Pipeline complete: {payload['decision']}",
            "themeColor": "00CC00" if payload["decision"] == "approve" else "FF0000",
            "sections": [{
                "activityTitle": "Pipeline Complete",
                "facts": [
                    {"name": "Event", "value": payload["event_id"][:12]},
                    {"name": "Decision", "value": payload["decision"].upper()},
                    {"name": "Risk", "value": f"{payload['risk_score']:.2f}"},
                ],
            }],
        }
        self._post_teams(card)

    def _post_teams(self, card: Dict[str, Any]) -> None:
        if not self._httpx or not self._config.teams_webhook_url:
            return
        try:
            self._httpx.post(self._config.teams_webhook_url, json=card, timeout=10.0)
        except Exception as e:
            logger.warning("Teams notification failed: %s", e)

    # ---- Generic webhook ----

    def _send_webhook(self, payload: Dict[str, Any]) -> None:
        if not self._httpx or not self._config.notification_webhook_url:
            return
        try:
            headers = {"Content-Type": "application/json"}
            headers.update(self._config.notification_webhook_headers)
            self._httpx.post(
                self._config.notification_webhook_url,
                json=payload,
                headers=headers,
                timeout=10.0,
            )
        except Exception as e:
            logger.warning("Webhook notification failed: %s", e)
