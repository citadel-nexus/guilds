from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import logging
import jsonschema

logger = logging.getLogger(__name__)

@dataclass
class EventContract:
    """
    Defines the schema and validation logic for Event JSON v1.
    """
    schema: Dict[str, Any] = field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "event_id": {"type": "string"},
            "event_type": {"type": "string"},
            "timestamp": {"type": "string", "format": "date-time"},
            "payload": {"type": "object"},
            "metadata": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "version": {"type": "string"}
                },
                "required": ["source", "version"]
            }
        },
        "required": ["event_id", "event_type", "timestamp", "payload", "metadata"]
    })

    def validate(self, event: Dict[str, Any]) -> bool:
        """
        Validates the given event dictionary against the schema.

        Args:
            event (Dict[str, Any]): The event JSON to validate.

        Returns:
            bool: True if the event is valid, False otherwise.

        Raises:
            jsonschema.exceptions.ValidationError: If the event fails validation.
        """
        try:
            jsonschema.validate(instance=event, schema=self.schema)
            logger.info("Event validation successful.")
            return True
        except jsonschema.exceptions.ValidationError as e:
            logger.error(f"Event validation failed: {e.message}")
            raise

# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    contract = EventContract()
    example_event = {
        "event_id": "12345",
        "event_type": "user_signup",
        "timestamp": "2023-10-01T12:00:00Z",
        "payload": {"user_id": "67890"},
        "metadata": {"source": "web", "version": "1.0"}
    }

    try:
        is_valid = contract.validate(example_event)
        print(f"Event is valid: {is_valid}")
    except jsonschema.exceptions.ValidationError as e:
        print(f"Validation error: {e.message}")