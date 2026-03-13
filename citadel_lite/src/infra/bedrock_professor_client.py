"""AWS Bedrock Claude client for MCA professor LLM calls.

Provides a thin wrapper around boto3 Bedrock Runtime to invoke
Claude models.  Follows the retry + exponential backoff pattern
from ``src/llm/client.py``.
"""

from __future__ import annotations

import json
import logging
import os
import time

from dotenv import load_dotenv

load_dotenv()
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "bedrock_professor_client"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Response type
# ---------------------------------------------------------------------------
@dataclass
class BedrockResponse:
    """Result of a Bedrock invocation."""

    content: str = ""
    parsed: Optional[Dict[str, Any]] = None
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    success: bool = False
    error: Optional[str] = None
    model: str = ""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
class BedrockProfessorClient:
    """AWS Bedrock client for Claude model invocations."""

    DEFAULT_MODEL = "us.anthropic.claude-opus-4-5-20251101-v1:0"
    DEFAULT_REGION = "us-east-1"
    ANTHROPIC_VERSION = "bedrock-2023-05-31"

    def __init__(
        self,
        model_id: Optional[str] = None,
        region: Optional[str] = None,
        max_retries: int = 3,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> None:
        self.model_id = model_id or os.environ.get(
            "AWS_BEDROCK_MODEL_ID", self.DEFAULT_MODEL
        )
        self.region = region or os.environ.get(
            "AWS_BEDROCK_REGION", self.DEFAULT_REGION
        )
        self.max_retries = max_retries
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = None

    def _get_client(self) -> Any:
        """Lazy-init boto3 Bedrock Runtime client."""
        if self._client is None:
            try:
                import boto3

                session = boto3.Session(
                    aws_access_key_id=os.environ.get("AWS_BEDROCK_ACCESS_KEY_ID"),
                    aws_secret_access_key=os.environ.get("AWS_BEDROCK_SECRET_ACCESS_KEY"),
                    region_name=self.region,
                )
                self._client = session.client("bedrock-runtime")
            except Exception as exc:
                logger.error("Failed to create Bedrock client: %s", exc)
                raise
        return self._client

    def invoke(
        self,
        system_prompt: str,
        user_message: str,
        json_mode: bool = False,
    ) -> BedrockResponse:
        """Invoke Claude via Bedrock with retry logic."""
        messages: List[Dict[str, str]] = [
            {"role": "user", "content": user_message},
        ]

        body: Dict[str, Any] = {
            "anthropic_version": self.ANTHROPIC_VERSION,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": messages,
        }
        if system_prompt:
            body["system"] = system_prompt

        last_error: Optional[str] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                client = self._get_client()
                t0 = time.monotonic()
                response = client.invoke_model(
                    modelId=self.model_id,
                    contentType="application/json",
                    accept="application/json",
                    body=json.dumps(body),
                )
                latency = (time.monotonic() - t0) * 1000

                resp_body = json.loads(response["body"].read())
                content = ""
                if resp_body.get("content"):
                    content = resp_body["content"][0].get("text", "")

                usage = resp_body.get("usage", {})
                result = BedrockResponse(
                    content=content,
                    input_tokens=usage.get("input_tokens", 0),
                    output_tokens=usage.get("output_tokens", 0),
                    latency_ms=latency,
                    success=True,
                    model=self.model_id,
                )

                # Try JSON parse if requested
                if json_mode and content:
                    result.parsed = _try_parse_json(content)

                return result

            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "Bedrock attempt %d/%d failed: %s",
                    attempt, self.max_retries, last_error,
                )
                if attempt < self.max_retries:
                    time.sleep(min(2 ** attempt, 30))

        return BedrockResponse(
            success=False,
            error=f"All {self.max_retries} attempts failed: {last_error}",
            model=self.model_id,
        )

    def is_available(self) -> bool:
        """Check if Bedrock credentials are configured."""
        return bool(
            os.environ.get("AWS_BEDROCK_ACCESS_KEY_ID")
            and os.environ.get("AWS_BEDROCK_SECRET_ACCESS_KEY")
        )


def _try_parse_json(text: str) -> Optional[Dict[str, Any]]:
    """Try to extract JSON from text (plain, fenced, or embedded).

    Attempts multiple strategies in order:
    1. Direct JSON parse (clean response)
    2. Markdown-fenced JSON (```json ... ``` or ``` ... ```)
    3. First { ... } block extraction (JSON embedded in prose)
    """
    import re

    if not text or not text.strip():
        return None

    stripped = text.strip()

    # 1. Direct parse
    try:
        result = json.loads(stripped)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, TypeError):
        pass

    # 2. Markdown fence — match ```json\n...\n``` or ```\n...\n```
    m = re.search(r"```(?:json)?\s*\n?([\s\S]*?)```", stripped)
    if m:
        try:
            result = json.loads(m.group(1).strip())
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, TypeError):
            pass

    # 3. First { ... } block — greedy match for outermost braces
    m = re.search(r"\{[\s\S]*\}", stripped)
    if m:
        try:
            result = json.loads(m.group(0))
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, TypeError):
            pass

    return None
