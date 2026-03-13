"""Bedrock adapter for ProfessorBase — overrides LLM calls to use AWS Bedrock.

Instead of modifying ``professor_base.py`` directly, this adapter
inherits from ``ProfessorBase`` and overrides ``refine_text_with_llm()``
to route through ``BedrockProfessorClient``.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.infra.bedrock_professor_client import BedrockProfessorClient

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "bedrock_adapter"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

logger = logging.getLogger(__name__)

# Lazy import to avoid circular dependency with professor_base
_ProfessorBase = None


def _get_professor_base():
    """Lazy import of ProfessorBase."""
    global _ProfessorBase
    if _ProfessorBase is None:
        from src.mca.professors.professor_base import ProfessorBase
        _ProfessorBase = ProfessorBase
    return _ProfessorBase


class BedrockProfessorBase:
    """Mixin/adapter that provides Bedrock-backed LLM calls.

    MCA professors inherit from this alongside (or instead of) direct
    ProfessorBase usage.  The key method ``refine_text_with_llm()``
    mirrors ProfessorBase's signature but uses BedrockProfessorClient.
    """

    def __init__(
        self,
        bedrock_client: Optional[BedrockProfessorClient] = None,
        **kwargs,
    ) -> None:
        self._bedrock = bedrock_client or BedrockProfessorClient()

    def refine_text_with_llm(
        self,
        text_to_refine: str,
        llm_system_prompt: str,
        current_session_id: Optional[str] = None,
    ) -> Optional[str]:
        """Call LLM via AWS Bedrock instead of OpenAI.

        Signature mirrors ``ProfessorBase.refine_text_with_llm()`` so
        existing professor code that calls ``self.refine_text_with_llm()``
        works transparently.
        """
        if not self._bedrock.is_available():
            logger.warning("Bedrock not available — returning None")
            return None

        resp = self._bedrock.invoke(
            system_prompt=llm_system_prompt,
            user_message=text_to_refine,
        )

        if resp.success:
            logger.info(
                "Bedrock call OK: %d in / %d out tokens (%.0f ms)",
                resp.input_tokens, resp.output_tokens, resp.latency_ms,
            )
            return resp.content

        logger.error("Bedrock call failed: %s", resp.error)
        return None

    def invoke_json(
        self,
        system_prompt: str,
        user_message: str,
    ) -> Optional[dict]:
        """Invoke Bedrock and parse JSON response."""
        resp = self._bedrock.invoke(
            system_prompt=system_prompt,
            user_message=user_message,
            json_mode=True,
        )
        if resp.success and resp.parsed:
            return resp.parsed
        if resp.success and resp.content:
            # Try manual parse
            import json as _json
            try:
                return _json.loads(resp.content)
            except _json.JSONDecodeError:
                pass
        return None
