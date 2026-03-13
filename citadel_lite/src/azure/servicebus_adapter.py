# src/azure/servicebus_adapter.py
"""
Azure Service Bus adapter implementing OutboxAdapter.

Sends EventJsonV1 messages to a Service Bus queue for reliable event processing.
Requires: pip install azure-servicebus azure-identity
"""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Callable, Optional

from src.types import EventJsonV1, EventArtifact
from src.ingest.outbox import OutboxAdapter
from src.azure.config import AzureConfig

try:
    from azure.servicebus import ServiceBusClient, ServiceBusMessage, ServiceBusReceiver
    _HAS_SERVICEBUS = True
except ImportError:
    _HAS_SERVICEBUS = False


class ServiceBusOutbox(OutboxAdapter):
    """
    Azure Service Bus implementation of OutboxAdapter.
    Falls back to raising ImportError if SDK not installed.
    """

    def __init__(self, config: AzureConfig) -> None:
        if not _HAS_SERVICEBUS:
            raise ImportError("azure-servicebus is required. Install with: pip install azure-servicebus")
        if not config.service_bus_connection:
            raise ValueError("AZURE_SERVICEBUS_CONNECTION is required")

        self._client = ServiceBusClient.from_connection_string(config.service_bus_connection)
        self._queue = config.service_bus_queue
        self._sender = self._client.get_queue_sender(queue_name=self._queue)

    def push(self, event: EventJsonV1) -> None:
        """Send event to Service Bus queue."""
        body = json.dumps(asdict(event), ensure_ascii=False)
        message = ServiceBusMessage(
            body=body,
            content_type="application/json",
            subject=event.event_type,
            application_properties={
                "event_id": event.event_id,
                "source": event.source,
                "event_type": event.event_type,
            },
        )
        self._sender.send_messages(message)

    def pull(self) -> Optional[EventJsonV1]:
        """Receive next event from Service Bus queue."""
        receiver: ServiceBusReceiver = self._client.get_queue_receiver(
            queue_name=self._queue, max_wait_time=5
        )
        with receiver:
            messages = receiver.receive_messages(max_message_count=1, max_wait_time=5)
            if not messages:
                return None

            msg = messages[0]
            raw = json.loads(str(msg))
            receiver.complete_message(msg)

            artifacts_raw = raw.get("artifacts", {}) or {}
            return EventJsonV1(
                schema_version=raw.get("schema_version", "event_json_v1"),
                event_id=raw.get("event_id", ""),
                event_type=raw.get("event_type", ""),
                source=raw.get("source", ""),
                occurred_at=raw.get("occurred_at", ""),
                repo=raw.get("repo"),
                ref=raw.get("ref"),
                summary=raw.get("summary"),
                artifacts=EventArtifact(
                    log_excerpt=artifacts_raw.get("log_excerpt"),
                    links=artifacts_raw.get("links", []),
                    extra=artifacts_raw.get("extra", {}),
                ),
            )

    def listen(self, callback: Callable[[EventJsonV1], None]) -> None:
        """Long-poll listener for continuous processing."""
        receiver = self._client.get_queue_receiver(queue_name=self._queue)
        with receiver:
            for msg in receiver:
                raw = json.loads(str(msg))
                artifacts_raw = raw.get("artifacts", {}) or {}
                event = EventJsonV1(
                    schema_version=raw.get("schema_version", "event_json_v1"),
                    event_id=raw.get("event_id", ""),
                    event_type=raw.get("event_type", ""),
                    source=raw.get("source", ""),
                    occurred_at=raw.get("occurred_at", ""),
                    repo=raw.get("repo"),
                    ref=raw.get("ref"),
                    summary=raw.get("summary"),
                    artifacts=EventArtifact(
                        log_excerpt=artifacts_raw.get("log_excerpt"),
                        links=artifacts_raw.get("links", []),
                        extra=artifacts_raw.get("extra", {}),
                    ),
                )
                callback(event)
                receiver.complete_message(msg)

    def close(self) -> None:
        self._sender.close()
        self._client.close()
