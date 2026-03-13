# src/llm/client.py
"""
LLM client with Azure OpenAI → OpenAI direct → AWS Bedrock → local fallback chain.

Usage:
    client = LLMClient()  # auto-detects available backend
    result = await client.complete(system_prompt, user_message)
    # result is a parsed dict from JSON-mode response

Backends (tried in order):
    1. Azure OpenAI  (AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_KEY)
    2. OpenAI direct  (OPENAI_API_KEY)
    3. AWS Bedrock    (AWS credentials configured via ~/.aws/credentials or env vars)
    4. Local fallback  (returns None — caller uses rule-based logic)
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports — only loaded if the backend is actually used
# ---------------------------------------------------------------------------

def _get_openai_client(*, azure: bool = False):
    """Lazy-import and instantiate the OpenAI client."""
    try:
        import openai  # type: ignore
    except ImportError:
        return None

    if azure:
        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        key = os.environ.get("AZURE_OPENAI_KEY", "")
        api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
        if not endpoint or not key:
            return None
        return openai.AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=key,
            api_version=api_version,
        )
    else:
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            return None
        return openai.OpenAI(api_key=key)


def _get_bedrock_client():
    """Lazy-import and instantiate AWS Bedrock runtime client."""
    try:
        import boto3  # type: ignore
    except ImportError:
        return None
    try:
        session = boto3.Session(
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )
        return session.client("bedrock-runtime")
    except Exception:
        return None


# Default Bedrock model (Claude Haiku — cheapest)
_BEDROCK_MODELS = {
    "haiku": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "sonnet": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "opus": "us.anthropic.claude-opus-4-5-20251101-v1:0",
}
_BEDROCK_DEFAULT = os.environ.get("BEDROCK_MODEL", "haiku")


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    backend: str = ""
    model: str = ""


@dataclass
class LLMResponse:
    content: str = ""
    parsed: Optional[Dict[str, Any]] = None
    usage: LLMUsage = field(default_factory=LLMUsage)
    success: bool = False
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class LLMClient:
    """
    Multi-backend LLM client.

    Tries Azure OpenAI first, then direct OpenAI, then returns a fallback
    signal so the caller can use rule-based logic.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        max_retries: int = 2,
    ) -> None:
        self._azure_model = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
        self._openai_model = model or os.environ.get("OPENAI_MODEL", "gpt-4o")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retries = max_retries

        # Cumulative usage tracking
        self.total_tokens = 0
        self.total_calls = 0
        self._call_log: List[LLMUsage] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def complete(
        self,
        system_prompt: str,
        user_message: str,
        json_mode: bool = True,
    ) -> LLMResponse:
        """
        Send a chat completion request. Tries backends in priority order.
        Returns LLMResponse with parsed JSON if json_mode=True.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        # Try Azure OpenAI
        resp = self._try_backend("azure", messages, json_mode)
        if resp and resp.success:
            return resp

        # Try direct OpenAI
        resp = self._try_backend("openai", messages, json_mode)
        if resp and resp.success:
            return resp

        # Try AWS Bedrock (Claude)
        resp = self._try_bedrock(messages, json_mode)
        if resp and resp.success:
            return resp

        # Fallback — signal caller to use rule-based logic
        return LLMResponse(
            success=False,
            error="no_llm_backend",
            usage=LLMUsage(backend="fallback"),
        )

    def is_available(self) -> bool:
        """Check if any LLM backend is configured."""
        if os.environ.get("AZURE_OPENAI_ENDPOINT") or os.environ.get("OPENAI_API_KEY"):
            return True
        # Check if AWS credentials exist (boto3 will auto-detect)
        try:
            client = _get_bedrock_client()
            return client is not None
        except Exception:
            return False

    def get_usage_summary(self) -> Dict[str, Any]:
        """Return cumulative usage stats."""
        return {
            "total_calls": self.total_calls,
            "total_tokens": self.total_tokens,
            "calls": [
                {
                    "backend": u.backend,
                    "model": u.model,
                    "tokens": u.total_tokens,
                    "latency_ms": u.latency_ms,
                }
                for u in self._call_log[-20:]  # last 20
            ],
        }

    # ------------------------------------------------------------------
    # Backend dispatch
    # ------------------------------------------------------------------

    def _try_backend(
        self,
        backend: str,
        messages: List[Dict[str, str]],
        json_mode: bool,
    ) -> Optional[LLMResponse]:
        """Attempt a completion on the given backend with retries."""
        is_azure = backend == "azure"
        client = _get_openai_client(azure=is_azure)
        if client is None:
            return None

        model = self._azure_model if is_azure else self._openai_model

        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        last_error = ""
        for attempt in range(self.max_retries + 1):
            try:
                t0 = time.perf_counter()
                response = client.chat.completions.create(**kwargs)
                latency = (time.perf_counter() - t0) * 1000

                content = response.choices[0].message.content or ""
                usage_obj = response.usage

                usage = LLMUsage(
                    prompt_tokens=usage_obj.prompt_tokens if usage_obj else 0,
                    completion_tokens=usage_obj.completion_tokens if usage_obj else 0,
                    total_tokens=usage_obj.total_tokens if usage_obj else 0,
                    latency_ms=latency,
                    backend=backend,
                    model=model,
                )
                self.total_tokens += usage.total_tokens
                self.total_calls += 1
                self._call_log.append(usage)

                parsed = None
                if json_mode and content.strip():
                    try:
                        parsed = json.loads(content)
                    except json.JSONDecodeError:
                        # Try to extract JSON from markdown fences
                        stripped = content.strip()
                        if stripped.startswith("```"):
                            lines = stripped.split("\n")
                            inner = "\n".join(lines[1:-1]) if len(lines) > 2 else ""
                            parsed = json.loads(inner)

                return LLMResponse(
                    content=content,
                    parsed=parsed,
                    usage=usage,
                    success=True,
                )

            except Exception as e:
                last_error = str(e)
                logger.warning(
                    "LLM %s attempt %d failed: %s", backend, attempt + 1, last_error
                )
                if attempt < self.max_retries:
                    time.sleep(0.5 * (attempt + 1))  # simple backoff

        return LLMResponse(
            success=False,
            error=f"{backend}: {last_error}",
            usage=LLMUsage(backend=backend, model=model),
        )

    def _try_bedrock(
        self,
        messages: List[Dict[str, str]],
        json_mode: bool,
    ) -> Optional[LLMResponse]:
        """Attempt a completion via AWS Bedrock (Claude models)."""
        client = _get_bedrock_client()
        if client is None:
            return None

        model_key = os.environ.get("BEDROCK_MODEL", "haiku")
        model_id = _BEDROCK_MODELS.get(model_key, _BEDROCK_MODELS["haiku"])

        # Convert system+user messages to Bedrock Messages API format
        system_text = ""
        bedrock_messages = []
        for m in messages:
            if m["role"] == "system":
                system_text = m["content"]
            else:
                bedrock_messages.append({"role": m["role"], "content": m["content"]})

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": bedrock_messages,
        }
        if system_text:
            body["system"] = system_text

        last_error = ""
        for attempt in range(self.max_retries + 1):
            try:
                t0 = time.perf_counter()
                response = client.invoke_model(
                    modelId=model_id,
                    contentType="application/json",
                    accept="application/json",
                    body=json.dumps(body),
                )
                latency = (time.perf_counter() - t0) * 1000

                result = json.loads(response["body"].read())
                content = result.get("content", [{}])[0].get("text", "")
                input_tokens = result.get("usage", {}).get("input_tokens", 0)
                output_tokens = result.get("usage", {}).get("output_tokens", 0)

                usage = LLMUsage(
                    prompt_tokens=input_tokens,
                    completion_tokens=output_tokens,
                    total_tokens=input_tokens + output_tokens,
                    latency_ms=latency,
                    backend="bedrock",
                    model=model_id,
                )
                self.total_tokens += usage.total_tokens
                self.total_calls += 1
                self._call_log.append(usage)

                parsed = None
                if json_mode and content.strip():
                    try:
                        parsed = json.loads(content)
                    except json.JSONDecodeError:
                        stripped = content.strip()
                        if stripped.startswith("```"):
                            lines = stripped.split("\n")
                            inner = "\n".join(lines[1:-1]) if len(lines) > 2 else ""
                            parsed = json.loads(inner)

                return LLMResponse(
                    content=content,
                    parsed=parsed,
                    usage=usage,
                    success=True,
                )

            except Exception as e:
                last_error = str(e)
                logger.warning(
                    "LLM bedrock attempt %d failed: %s", attempt + 1, last_error
                )
                if attempt < self.max_retries:
                    time.sleep(0.5 * (attempt + 1))

        return LLMResponse(
            success=False,
            error=f"bedrock: {last_error}",
            usage=LLMUsage(backend="bedrock", model=model_id),
        )
