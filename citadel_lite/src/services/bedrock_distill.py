# src/services/bedrock_distill.py
"""
Bedrock Claude helpers for Sentinel memory extraction and distillation.

Functions:
  bedrock_extract_structured(prompt, context, response_schema)
      → dict matching response_schema
  bedrock_distill_memories(query, memories, prompt)
      → str (compact narrative)
  bedrock_classify_domain(text, domains)
      → str domain name
  bedrock_chunk_transcript(transcript, max_chunk=500)
      → list[str]
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger("sentinel.bedrock")

# ── Bedrock model routing ─────────────────────────────────────────────────────
_MODEL_IDS = {
    "haiku": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "sonnet": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
}
_DEFAULT_MODEL = _MODEL_IDS["haiku"]  # fast + cheap for extraction


def _get_bedrock_client():
    try:
        import boto3
        session = boto3.Session(
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", ""),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", ""),
            region_name=os.environ.get("AWS_DEFAULT_REGION", "us-west-2"),
        )
        return session.client("bedrock-runtime")
    except Exception as e:
        logger.warning("[Bedrock] client init failed: %s", e)
        return None


def _invoke_bedrock(client, model_id: str, messages: list, max_tokens: int = 2048) -> str:
    """Synchronous Bedrock invoke — runs inside asyncio.to_thread."""
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "messages": messages,
    }).encode()
    resp = client.invoke_model(
        modelId=model_id,
        body=body,
        contentType="application/json",
        accept="application/json",
    )
    result = json.loads(resp["body"].read())
    return result["content"][0]["text"]


# ── Public API ────────────────────────────────────────────────────────────────

async def bedrock_extract_structured(
    prompt: str,
    context: Dict[str, Any],
    response_schema: Dict[str, Any],
    model: str = "haiku",
) -> Dict[str, Any]:
    """
    Use Bedrock Claude to extract structured memory objects from conversation context.

    Returns a dict matching *response_schema*. Falls back to empty schema on error.
    """
    def _sync():
        client = _get_bedrock_client()
        if client is None:
            return {}

        schema_str = json.dumps(response_schema, indent=2)
        context_str = json.dumps(context, indent=2, ensure_ascii=False)

        messages = [
            {
                "role": "user",
                "content": (
                    f"{prompt}\n\n"
                    f"## Conversation context\n{context_str}\n\n"
                    f"## Required JSON schema\n{schema_str}\n\n"
                    "Return ONLY valid JSON matching the schema above. No prose."
                ),
            }
        ]

        raw = _invoke_bedrock(
            client,
            _MODEL_IDS.get(model, _DEFAULT_MODEL),
            messages,
            max_tokens=2048,
        )

        # Strip markdown fences + parse first JSON object
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        idx = text.find("{")
        if idx == -1:
            return {}
        import json as _json
        decoder = _json.JSONDecoder()
        parsed, _ = decoder.raw_decode(text[idx:])
        return parsed

    try:
        return await asyncio.to_thread(_sync)
    except Exception as e:
        logger.warning("[Bedrock] extract_structured failed: %s", e)
        # Return empty but schema-valid defaults
        defaults = {}
        for key, val in response_schema.items():
            defaults[key] = [] if isinstance(val, list) else ({} if isinstance(val, dict) else "")
        return defaults


async def bedrock_distill_memories(
    query: str,
    memories: List[Dict[str, Any]],
    prompt: str,
    model: str = "haiku",
) -> str:
    """
    Distil a list of memory fragments into a concise narrative string.

    Each memory dict should have: content_chunk, similarity, domain, date.
    Returns a compact bullet-point string (≤ 200 words).
    """
    def _sync():
        client = _get_bedrock_client()
        if client is None:
            # Fallback: simple concatenation
            return "\n".join(f"- {m.get('content_chunk', '')}" for m in memories[:5])

        fragments_str = json.dumps(memories, indent=2, ensure_ascii=False)
        messages = [
            {
                "role": "user",
                "content": (
                    f"{prompt}\n\n"
                    f"## Query context\n{query}\n\n"
                    f"## Memory fragments\n{fragments_str}"
                ),
            }
        ]
        return _invoke_bedrock(
            client, _MODEL_IDS.get(model, _DEFAULT_MODEL), messages, max_tokens=512
        )

    try:
        return await asyncio.to_thread(_sync)
    except Exception as e:
        logger.warning("[Bedrock] distill_memories failed: %s", e)
        return "\n".join(f"- {m.get('content_chunk', '')[:120]}" for m in memories[:5])


async def bedrock_classify_domain(
    text: str,
    domains: List[str],
    model: str = "haiku",
) -> str:
    """
    Classify a text chunk into the most appropriate Sentinel domain.
    Returns the domain string (e.g. 'sentinel:technical').
    """
    def _sync():
        client = _get_bedrock_client()
        if client is None:
            return domains[0] if domains else "sentinel:personal"

        messages = [
            {
                "role": "user",
                "content": (
                    f"Classify this text into exactly one domain from the list below.\n"
                    f"Domains: {', '.join(domains)}\n\n"
                    f"Text: {text[:500]}\n\n"
                    "Return ONLY the domain string — no explanation, no punctuation."
                ),
            }
        ]
        raw = _invoke_bedrock(
            client, _MODEL_IDS.get(model, _DEFAULT_MODEL), messages, max_tokens=64
        )
        raw = raw.strip().lower()
        for d in domains:
            if d in raw:
                return d
        return domains[0] if domains else "sentinel:personal"

    try:
        return await asyncio.to_thread(_sync)
    except Exception as e:
        logger.warning("[Bedrock] classify_domain failed: %s", e)
        return domains[0] if domains else "sentinel:personal"


async def bedrock_chunk_transcript(
    transcript: str,
    max_chunk: int = 500,
    model: str = "haiku",
) -> List[str]:
    """
    Use Bedrock to split a transcript into semantically coherent chunks.
    Falls back to naive splitting on sentence boundaries.
    """
    if len(transcript) <= max_chunk:
        return [transcript]

    def _naive_chunk(text: str, size: int) -> List[str]:
        chunks = []
        sentences = text.replace("? ", "?\n").replace("! ", "!\n").replace(". ", ".\n").split("\n")
        buf = ""
        for s in sentences:
            if len(buf) + len(s) > size and buf:
                chunks.append(buf.strip())
                buf = s + " "
            else:
                buf += s + " "
        if buf.strip():
            chunks.append(buf.strip())
        return chunks

    def _sync():
        client = _get_bedrock_client()
        if client is None:
            return _naive_chunk(transcript, max_chunk)

        messages = [
            {
                "role": "user",
                "content": (
                    f"Split this transcript into semantically coherent chunks of "
                    f"~{max_chunk} characters. Each chunk should be a complete thought.\n\n"
                    f"Return a JSON array of strings: [\"chunk1\", \"chunk2\", ...]\n\n"
                    f"Transcript:\n{transcript[:6000]}"
                ),
            }
        ]
        raw = _invoke_bedrock(
            client, _MODEL_IDS.get(model, _DEFAULT_MODEL), messages, max_tokens=1024
        )
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        idx = text.find("[")
        if idx == -1:
            return _naive_chunk(transcript, max_chunk)
        import json as _json
        decoder = _json.JSONDecoder()
        parsed, _ = decoder.raw_decode(text[idx:])
        return parsed if isinstance(parsed, list) else _naive_chunk(transcript, max_chunk)

    try:
        return await asyncio.to_thread(_sync)
    except Exception as e:
        logger.warning("[Bedrock] chunk_transcript failed: %s", e)
        return _naive_chunk(transcript, max_chunk)
