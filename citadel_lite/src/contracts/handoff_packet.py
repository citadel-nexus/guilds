from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, Optional
import logging

from jsonschema import validate as jsonschema_validate, ValidationError

logger = logging.getLogger(__name__)


@dataclass
class HandoffPacket:
    """
    Represents the structure of a Handoff Packet for A2A communication.

    Schema validation is structural only (type-level); semantic constraints
    such as non-empty strings are intentionally out of scope per Event JSON v1.
    """

    SCHEMA: ClassVar[Dict[str, Any]] = {
        "type": "object",
        "properties": {
            "source_agent_id": {"type": "string"},
            "target_agent_id": {"type": "string"},
            "payload": {"type": "object"},
            "timestamp": {"type": ["string", "null"]},
            "metadata": {"type": "object"},
        },
        "required": ["source_agent_id", "target_agent_id", "payload"],
    }

    source_agent_id: str
    target_agent_id: str
    payload: Dict[str, Any]
    timestamp: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = field(default_factory=dict)

    def validate(self) -> bool:
        """
        Validates the instance against the JSON Schema.

        Raises:
            jsonschema.ValidationError: If the instance violates the schema.

        Returns:
            True on success.
        """
        instance_dict: Dict[str, Any] = {
            "source_agent_id": self.source_agent_id,
            "target_agent_id": self.target_agent_id,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }
        if self.metadata is not None:
            instance_dict["metadata"] = self.metadata
        jsonschema_validate(instance=instance_dict, schema=self.SCHEMA)
        return True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HandoffPacket":
        """
        Creates a HandoffPacket instance from a dictionary.

        Raises:
            jsonschema.ValidationError: If the data does not satisfy the schema.
        """
        jsonschema_validate(instance=data, schema=cls.SCHEMA)
        return cls(
            source_agent_id=data["source_agent_id"],
            target_agent_id=data["target_agent_id"],
            payload=data["payload"],
            timestamp=data.get("timestamp"),
            metadata=data.get("metadata", {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Returns a dictionary representation of the HandoffPacket."""
        return {
            "source_agent_id": self.source_agent_id,
            "target_agent_id": self.target_agent_id,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }
