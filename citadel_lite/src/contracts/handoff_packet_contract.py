import json
from dataclasses import dataclass
from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class HandoffPacketContract:
    """
    Lightweight contract for A2A handoff packets (Event JSON v1).

    Required fields: id, timestamp, payload.
    Missing any required field raises ValueError on construction.
    """

    id: Optional[str] = None
    timestamp: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        missing = [
            field
            for field, value in [
                ("id", self.id),
                ("timestamp", self.timestamp),
                ("payload", self.payload),
            ]
            if value is None
        ]
        if missing:
            raise ValueError(f"Missing required fields: {missing}")

    def to_json(self) -> str:
        """Serializes the contract to a compact JSON string."""
        return json.dumps(
            {"id": self.id, "timestamp": self.timestamp, "payload": self.payload}
        )

    @classmethod
    def from_json(cls, json_data: str) -> "HandoffPacketContract":
        """
        Creates an instance from a JSON string.

        Raises:
            ValueError: If the JSON is malformed or required fields are missing.
        """
        try:
            data = json.loads(json_data)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON: {e}")
            raise ValueError(f"Invalid JSON data: {e}") from e

        return cls(
            id=data.get("id"),
            timestamp=data.get("timestamp"),
            payload=data.get("payload"),
        )
