import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class DecisionContract:
    """
    Represents a decision contract with optional metadata and participants.
    """
    decision_id: str
    timestamp: str  # ISO 8601 format expected, 'T' separator required
    metadata: Optional[dict] = field(default_factory=dict)
    participants: Optional[List[str]] = field(default_factory=list)

    @staticmethod
    def validate(data: dict) -> bool:
        """
        Validates the input data against the DecisionContract specification.

        Args:
            data (dict): Input data to validate.

        Returns:
            bool: True if validation passes, False otherwise.
        """
        try:
            # Validate required fields
            if 'decision_id' not in data or not isinstance(data['decision_id'], str):
                logger.error("Validation failed: 'decision_id' is missing or not a string.")
                return False

            if 'timestamp' not in data or not isinstance(data['timestamp'], str):
                logger.error("Validation failed: 'timestamp' is missing or not a string.")
                return False

            # Validate ISO 8601 timestamp — require 'T' separator (space separator rejected)
            if 'T' not in data['timestamp']:
                logger.error("Validation failed: 'timestamp' must use 'T' separator (ISO 8601).")
                return False
            try:
                datetime.fromisoformat(data['timestamp'])
            except ValueError:
                logger.error("Validation failed: 'timestamp' is not a valid ISO 8601 format.")
                return False

            # Validate optional fields
            if 'metadata' in data and not isinstance(data['metadata'], dict):
                logger.error("Validation failed: 'metadata' is not a dictionary.")
                return False

            if 'participants' in data and not isinstance(data['participants'], list):
                logger.error("Validation failed: 'participants' is not a list.")
                return False

            logger.info("Validation passed for input data.")
            return True

        except Exception as e:
            logger.error(f"Unexpected error during validation: {e}")
            return False
