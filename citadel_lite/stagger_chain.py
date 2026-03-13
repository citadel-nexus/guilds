"""
Stagger-Step Inference Chain — GGUF → Haiku → Sonnet → Opus
============================================================

Tiered inference pipeline where each stage only escalates to the next
if the current stage can't resolve with sufficient confidence.

Cost model:
  Stage 0 — GGUF (local):   $0.000/request (free, VPS/ECS)
  Stage 1 — Haiku:          ~$0.001/request
  Stage 2 — Sonnet:         ~$0.005/request
  Stage 3 — Opus:           ~$0.025/request

Expected distribution:
  60% resolved by GGUF       (trivial: formatting, classification, routing)
  25% escalated to Haiku     (standard: summaries, data extraction, simple review)
  10% escalated to Sonnet    (complex: code audit, financial analysis, multi-step)
   5% escalated to Opus      (critical: architecture review, legal, strategy)

Average cost: ~$0.002/request vs $0.025 if everything hit Opus (12x savings)

SRS: SRS-STAGGER-CHAIN-001
CGRF: v2.0
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sys
import time
import uuid

# Windows: reconfigure stdout to UTF-8 so Unicode symbols print correctly
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        import io as _io
        sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("citadel.orchestrator.stagger_chain")

# ---------------------------------------------------------------------------
# Project root & env loading
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_ENV_PATHS = [
    _PROJECT_ROOT / "guilds" / "CNWB" / "tools" / "workspace.env",
    _PROJECT_ROOT / "tools" / "workspace.env",
]


def _load_env() -> None:
    for env_path in _ENV_PATHS:
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())
            return


_load_env()


# ---------------------------------------------------------------------------
# Enums & Config
# ---------------------------------------------------------------------------

class Stage(str, Enum):
    GGUF = "gguf"
    HAIKU = "haiku"
    SONNET = "sonnet"
    OPUS = "opus"


class Verdict(str, Enum):
    RESOLVED = "resolved"       # Stage handled it — no escalation needed
    ESCALATE = "escalate"       # Low confidence — send to next stage
    FAILED = "failed"           # Stage errored — force escalation
    BLOCKED = "blocked"         # Cost/rate limit — cannot proceed


# Stage order for escalation
STAGE_ORDER = [Stage.GGUF, Stage.HAIKU, Stage.SONNET, Stage.OPUS]

# Confidence thresholds per stage — below this triggers escalation
CONFIDENCE_THRESHOLDS = {
    Stage.GGUF: float(os.getenv("STAGGER_GGUF_THRESHOLD", "0.80")),
    Stage.HAIKU: float(os.getenv("STAGGER_HAIKU_THRESHOLD", "0.85")),
    Stage.SONNET: float(os.getenv("STAGGER_SONNET_THRESHOLD", "0.92")),
    Stage.OPUS: 0.0,  # Opus is terminal — always resolves
}

# Bedrock model IDs
MODEL_IDS = {
    Stage.HAIKU: os.getenv("BEDROCK_HAIKU_MODEL_ID", "us.anthropic.claude-3-5-haiku-20241022-v1:0"),
    Stage.SONNET: os.getenv("BEDROCK_SONNET_MODEL_ID", "us.anthropic.claude-sonnet-4-6-20250514-v1:0"),
    Stage.OPUS: os.getenv("BEDROCK_OPUS_MODEL_ID", "us.anthropic.claude-opus-4-5-20251101-v1:0"),
}

# GGUF endpoints
GGUF_PRIMARY_URL = os.getenv("GGUF_PRIMARY_URL", "http://52.72.127.48:8081")
GGUF_FALLBACK_URL = os.getenv("GGUF_FALLBACK_URL", "http://52.72.127.48:8080")

# Cost tracking (per 1M tokens USD)
COST_PER_M = {
    Stage.GGUF: {"input": 0.0, "output": 0.0},
    Stage.HAIKU: {"input": 1.0, "output": 5.0},
    Stage.SONNET: {"input": 3.0, "output": 15.0},
    Stage.OPUS: {"input": 15.0, "output": 75.0},
}


# ---------------------------------------------------------------------------
# Data Types
# ---------------------------------------------------------------------------

@dataclass
class ChainRequest:
    """A single work item entering the stagger chain."""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    task_type: str = ""           # "code_review", "classification", "analysis", etc.
    system_prompt: str = ""
    user_prompt: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    min_stage: Stage = Stage.GGUF          # Skip stages below this
    max_stage: Stage = Stage.OPUS          # Don't escalate beyond this
    max_tokens: int = 2048
    temperature: float = 0.3
    caller: str = "unknown"


@dataclass
class StageResult:
    """Result from a single stage in the chain."""
    stage: Stage
    verdict: Verdict
    confidence: float
    response_text: str
    latency_ms: float
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    error: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChainResult:
    """Final result after the chain completes (possibly multiple stages)."""
    request_id: str
    final_stage: Stage
    final_verdict: Verdict
    response_text: str
    total_latency_ms: float
    total_cost_usd: float
    stages_attempted: List[StageResult] = field(default_factory=list)
    escalation_path: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# GGUF Caller (Stage 0)
# ---------------------------------------------------------------------------

def _call_gguf_sync(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 2048,
    temperature: float = 0.3,
) -> Dict[str, Any]:
    """Call GGUF server synchronously (urllib — works on all platforms)."""
    import urllib.request
    body = json.dumps({
        "model": "local",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode()
    last_error = None
    for url in [GGUF_PRIMARY_URL, GGUF_FALLBACK_URL]:
        try:
            req = urllib.request.Request(
                f"{url}/v1/chat/completions" if "/v1/" not in url else url,
                data=body,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
                text = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                return {
                    "text": text,
                    "input_tokens": usage.get("prompt_tokens", 0),
                    "output_tokens": usage.get("completion_tokens", 0),
                }
        except Exception as e:
            last_error = e
            logger.debug("GGUF endpoint %s failed: %s", url, e)
            continue
    raise ConnectionError(f"All GGUF endpoints unreachable (last: {last_error})")


async def _call_gguf(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 2048,
    temperature: float = 0.3,
) -> Dict[str, Any]:
    """Call local GGUF server (async wrapper around sync urllib)."""
    return await asyncio.to_thread(
        _call_gguf_sync, system_prompt, user_prompt, max_tokens, temperature,
    )


# ---------------------------------------------------------------------------
# Bedrock Caller (Stages 1-3)
# ---------------------------------------------------------------------------

async def _call_bedrock(
    stage: Stage,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 2048,
    temperature: float = 0.3,
) -> Dict[str, Any]:
    """Call AWS Bedrock for Haiku/Sonnet/Opus stages."""
    import boto3

    model_id = MODEL_IDS[stage]
    region = os.getenv("AWS_BEDROCK_REGION", os.getenv("AWS_REGION", "us-west-2"))

    client = boto3.client("bedrock-runtime", region_name=region)

    request_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }

    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(
        None,
        lambda: client.invoke_model(modelId=model_id, body=json.dumps(request_body)),
    )

    body = json.loads(response["body"].read())
    content = body.get("content", [])
    text = content[0].get("text", "") if content else ""
    usage = body.get("usage", {})

    return {
        "text": text,
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
    }


# ---------------------------------------------------------------------------
# Confidence Extraction
# ---------------------------------------------------------------------------

# The system prompt injected at each stage to get a structured confidence score
CONFIDENCE_WRAPPER = """
After completing the task, append a JSON block at the end of your response:

```json
{"confidence": 0.XX, "reasoning": "brief explanation of confidence level"}
```

Confidence guidelines:
- 0.95+: Completely certain, trivial/clear-cut
- 0.85-0.95: High confidence, standard task
- 0.70-0.85: Moderate confidence, some ambiguity
- Below 0.70: Low confidence, complex/uncertain, recommend escalation
"""

# Simplified wrapper for GGUF models (small models choke on backtick-heavy prompts)
CONFIDENCE_WRAPPER_GGUF = (
    '\nEnd your response with: {"confidence": X.XX, "reasoning": "why"}'
    " where X.XX is 0.00 to 1.00."
)


def _extract_confidence(text: str) -> tuple[float, str]:
    """Extract confidence score from model response. Returns (confidence, clean_text)."""
    import re

    # Try to find JSON block at end (markdown-wrapped)
    pattern = r'```json\s*(\{[^}]*"confidence"\s*:\s*([\d.]+)[^}]*\})\s*```'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        confidence = float(match.group(2))
        clean_text = text[:match.start()].rstrip()
        # If entire response was just the JSON, extract reasoning as the text
        if not clean_text:
            try:
                j = json.loads(match.group(1))
                clean_text = j.get("reasoning", text)
            except Exception:
                clean_text = text
        return min(max(confidence, 0.0), 1.0), clean_text

    # Try inline JSON
    pattern2 = r'\{"confidence"\s*:\s*([\d.]+)([^}]*)\}'
    match2 = re.search(pattern2, text)
    if match2:
        confidence = float(match2.group(1))
        clean_text = text[:match2.start()].rstrip()
        # If entire response was just the JSON, extract reasoning
        if not clean_text:
            try:
                j = json.loads(match2.group(0))
                clean_text = j.get("reasoning", text)
            except Exception:
                clean_text = text
        return min(max(confidence, 0.0), 1.0), clean_text

    # No confidence found — assume moderate (triggers escalation for lower stages)
    return 0.75, text


# ---------------------------------------------------------------------------
# Supabase Results Store
# ---------------------------------------------------------------------------

def _store_result_supabase(chain_result: ChainResult) -> bool:
    """Store chain result in Supabase for Terraform quality gates."""
    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY",
                             os.getenv("SUPABASE_SERVICE_KEY", ""))
    if not supabase_url or not supabase_key:
        logger.debug("Supabase not configured — skipping result store")
        return False

    try:
        import urllib.request
        payload = json.dumps({
            "request_id": chain_result.request_id,
            "final_stage": chain_result.final_stage.value,
            "final_verdict": chain_result.final_verdict.value,
            "total_cost_usd": round(chain_result.total_cost_usd, 6),
            "total_latency_ms": round(chain_result.total_latency_ms, 1),
            "stages_attempted": len(chain_result.stages_attempted),
            "escalation_path": chain_result.escalation_path,
            "response_preview": chain_result.response_text[:500],
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }).encode()

        req = urllib.request.Request(
            f"{supabase_url}/rest/v1/stagger_chain_results",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "apikey": supabase_key,
                "Authorization": f"Bearer {supabase_key}",
                "Prefer": "return=minimal",
            },
        )
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        logger.warning("Supabase store failed: %s", e)
        return False


# ---------------------------------------------------------------------------
# Metrics Emission
# ---------------------------------------------------------------------------

def _emit_chain_metrics(result: ChainResult) -> None:
    """Emit Datadog + PostHog metrics for the chain execution."""
    dd_host = os.getenv("DD_AGENT_HOST", os.getenv("DATADOG_HOST", "127.0.0.1"))
    dd_port = int(os.getenv("DD_DOGSTATSD_PORT", "8125"))
    try:
        from datadog import DogStatsd
        dd = DogStatsd(host=dd_host, port=dd_port)
        tags = [
            f"final_stage:{result.final_stage.value}",
            f"verdict:{result.final_verdict.value}",
            f"stages:{len(result.stages_attempted)}",
        ]
        dd.increment("stagger_chain.requests", 1, tags=tags)
        dd.histogram("stagger_chain.latency_ms", result.total_latency_ms, tags=tags)
        dd.gauge("stagger_chain.cost_usd", result.total_cost_usd, tags=tags)
        for sr in result.stages_attempted:
            dd.increment(f"stagger_chain.stage.{sr.stage.value}", 1)
        logger.debug("DogStatsd metrics sent to %s:%d", dd_host, dd_port)
    except Exception as e:
        logger.debug("DogStatsd emission failed: %s", e)

    try:
        import posthog
        ph_key = os.getenv("POSTHOG_API_KEY", os.getenv("POSTHOG_PROJECT_API_KEY", ""))
        if ph_key:
            posthog.project_api_key = ph_key
            posthog.host = os.getenv("POSTHOG_HOST", "https://us.posthog.com")
            posthog.capture(
                distinct_id="citadel-stagger-chain",
                event="stagger_chain_complete",
                properties={
                    "request_id": result.request_id,
                    "final_stage": result.final_stage.value,
                    "stages_attempted": len(result.stages_attempted),
                    "total_cost_usd": round(result.total_cost_usd, 6),
                    "total_latency_ms": round(result.total_latency_ms, 1),
                    "escalation_path": result.escalation_path,
                },
            )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# The Chain Engine
# ---------------------------------------------------------------------------

class StaggerChain:
    """
    Tiered inference engine: GGUF → Haiku → Sonnet → Opus

    Each stage evaluates the request. If confidence is below the stage
    threshold, the request escalates to the next tier. Results are stored
    in Supabase for Terraform quality gates.

    Usage::

        chain = StaggerChain()
        result = await chain.run(ChainRequest(
            task_type="code_review",
            system_prompt="You are a code reviewer...",
            user_prompt="Review this diff: ...",
        ))
        print(result.final_stage, result.response_text)
    """

    def __init__(
        self,
        *,
        skip_gguf: bool = False,
        store_supabase: bool = True,
        emit_metrics: bool = True,
        dry_run: bool = False,
    ):
        self._skip_gguf = skip_gguf
        self._store_supabase = store_supabase
        self._emit_metrics = emit_metrics
        self._dry_run = dry_run

        # Aggregate stats
        self.total_requests = 0
        self.total_cost = 0.0
        self.stage_counts = {s: 0 for s in Stage}

    async def run(self, request: ChainRequest) -> ChainResult:
        """Execute the stagger-step chain for a single request."""
        t0 = time.monotonic()
        stages_attempted: List[StageResult] = []
        escalation_path: List[str] = []

        # Determine starting stage
        start_idx = STAGE_ORDER.index(request.min_stage)
        max_idx = STAGE_ORDER.index(request.max_stage)

        if self._skip_gguf and start_idx == 0:
            start_idx = 1

        final_text = ""
        final_stage = Stage.HAIKU
        final_verdict = Verdict.FAILED

        for idx in range(start_idx, max_idx + 1):
            stage = STAGE_ORDER[idx]
            escalation_path.append(stage.value)

            # Inject confidence wrapper into system prompt
            wrapper = CONFIDENCE_WRAPPER_GGUF if stage == Stage.GGUF else CONFIDENCE_WRAPPER
            augmented_system = request.system_prompt + "\n\n" + wrapper

            stage_t0 = time.monotonic()

            try:
                if self._dry_run:
                    raw = {
                        "text": f'[DRY RUN] Stage {stage.value} would process: {request.task_type}\n\n```json\n{{"confidence": 0.95, "reasoning": "dry run"}}\n```',
                        "input_tokens": 100,
                        "output_tokens": 50,
                    }
                elif stage == Stage.GGUF:
                    raw = await _call_gguf(
                        augmented_system, request.user_prompt,
                        request.max_tokens, request.temperature,
                    )
                else:
                    raw = await _call_bedrock(
                        stage, augmented_system, request.user_prompt,
                        request.max_tokens, request.temperature,
                    )

                stage_latency = (time.monotonic() - stage_t0) * 1000
                confidence, clean_text = _extract_confidence(raw["text"])

                # Calculate cost
                costs = COST_PER_M[stage]
                cost = (
                    (raw["input_tokens"] / 1_000_000) * costs["input"]
                    + (raw["output_tokens"] / 1_000_000) * costs["output"]
                )

                # Determine verdict
                threshold = CONFIDENCE_THRESHOLDS[stage]
                if confidence >= threshold or stage == Stage.OPUS:
                    verdict = Verdict.RESOLVED
                else:
                    verdict = Verdict.ESCALATE

                stage_result = StageResult(
                    stage=stage,
                    verdict=verdict,
                    confidence=confidence,
                    response_text=clean_text,
                    latency_ms=stage_latency,
                    input_tokens=raw["input_tokens"],
                    output_tokens=raw["output_tokens"],
                    cost_usd=cost,
                    metadata={"threshold": threshold},
                )

            except Exception as e:
                stage_latency = (time.monotonic() - stage_t0) * 1000
                logger.warning("Stage %s failed: %s", stage.value, e)
                stage_result = StageResult(
                    stage=stage,
                    verdict=Verdict.FAILED,
                    confidence=0.0,
                    response_text="",
                    latency_ms=stage_latency,
                    error=str(e),
                )
                verdict = Verdict.FAILED

            stages_attempted.append(stage_result)
            self.stage_counts[stage] += 1

            if verdict == Verdict.RESOLVED:
                final_text = stage_result.response_text
                final_stage = stage
                final_verdict = Verdict.RESOLVED
                break
            elif verdict == Verdict.ESCALATE:
                logger.info(
                    "[CHAIN] %s: confidence=%.2f < threshold=%.2f → escalating",
                    stage.value, stage_result.confidence,
                    CONFIDENCE_THRESHOLDS[stage],
                )
                # Keep the text in case this is the last stage
                final_text = stage_result.response_text
                final_stage = stage
                final_verdict = Verdict.ESCALATE
            else:
                # Failed — try next stage
                final_stage = stage
                final_verdict = Verdict.FAILED

        total_latency = (time.monotonic() - t0) * 1000
        total_cost = sum(sr.cost_usd for sr in stages_attempted)

        chain_result = ChainResult(
            request_id=request.request_id,
            final_stage=final_stage,
            final_verdict=final_verdict,
            response_text=final_text,
            total_latency_ms=total_latency,
            total_cost_usd=total_cost,
            stages_attempted=stages_attempted,
            escalation_path=escalation_path,
        )

        # Aggregate stats
        self.total_requests += 1
        self.total_cost += total_cost

        # Store + emit
        if self._store_supabase:
            _store_result_supabase(chain_result)
        if self._emit_metrics:
            _emit_chain_metrics(chain_result)

        logger.info(
            "[CHAIN] %s resolved at %s (path=%s, cost=$%.4f, latency=%dms)",
            request.request_id, final_stage.value,
            "→".join(escalation_path), total_cost, int(total_latency),
        )

        return chain_result

    async def run_batch(
        self,
        requests: List[ChainRequest],
        max_concurrent: int = 5,
    ) -> List[ChainResult]:
        """Run multiple requests through the chain with concurrency control."""
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _guarded(req: ChainRequest) -> ChainResult:
            async with semaphore:
                return await self.run(req)

        return await asyncio.gather(*[_guarded(r) for r in requests])

    def stats(self) -> Dict[str, Any]:
        """Return chain statistics."""
        return {
            "total_requests": self.total_requests,
            "total_cost_usd": round(self.total_cost, 4),
            "stage_distribution": {s.value: self.stage_counts[s] for s in Stage},
            "avg_cost_per_request": (
                round(self.total_cost / self.total_requests, 6)
                if self.total_requests > 0 else 0
            ),
        }


# ---------------------------------------------------------------------------
# Pre-built chain configurations for common use cases
# ---------------------------------------------------------------------------

def code_review_chain(diff: str, *, context: str = "") -> ChainRequest:
    """Pre-configured chain request for code review."""
    return ChainRequest(
        task_type="code_review",
        system_prompt=(
            "You are a senior code reviewer. Analyze the following diff for:\n"
            "1. Bugs or logic errors\n"
            "2. Security vulnerabilities (OWASP Top 10)\n"
            "3. Performance issues\n"
            "4. Style/convention violations\n\n"
            "For trivial changes (whitespace, comments, imports), approve immediately "
            "with high confidence. For complex changes, provide detailed feedback."
        ),
        user_prompt=f"Context: {context}\n\nDiff:\n```\n{diff}\n```",
        max_tokens=4096,
    )


def classification_chain(text: str, categories: List[str]) -> ChainRequest:
    """Pre-configured chain request for text classification."""
    cats = ", ".join(categories)
    return ChainRequest(
        task_type="classification",
        system_prompt=(
            f"Classify the following text into one of these categories: {cats}\n\n"
            "Return the category name and a brief justification."
        ),
        user_prompt=text,
        max_tokens=256,
        max_stage=Stage.SONNET,  # Classification doesn't need Opus
    )


def commit_review_chain(commit_msg: str, diff: str) -> ChainRequest:
    """Pre-configured chain for auto-commit review (GitLab CI integration)."""
    return ChainRequest(
        task_type="commit_review",
        system_prompt=(
            "You are a commit reviewer for a CI/CD pipeline. Evaluate this commit:\n\n"
            "Verdicts:\n"
            "- AUTO_APPROVE: Trivial change (typos, formatting, dependency bumps)\n"
            "- APPROVE_WITH_NOTES: Good change with minor suggestions\n"
            "- NEEDS_ATTENTION: Significant change requiring human review\n"
            "- BLOCK: Security issue, breaking change, or architecture violation\n\n"
            "Be strict on security. Be lenient on style."
        ),
        user_prompt=f"Commit message: {commit_msg}\n\nDiff:\n```\n{diff}\n```",
        max_tokens=2048,
    )


def financial_analysis_chain(query: str, data_context: str = "") -> ChainRequest:
    """Pre-configured chain for Finance Guild analysis."""
    return ChainRequest(
        task_type="financial_analysis",
        system_prompt=(
            "You are a financial analyst for Citadel Nexus. Analyze the data and "
            "provide actionable insights. Use real numbers, not estimates. "
            "Flag any data quality issues."
        ),
        user_prompt=f"Query: {query}\n\nData:\n{data_context}",
        min_stage=Stage.HAIKU,  # Financial analysis skips GGUF
        max_tokens=4096,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

async def _main():
    """CLI test harness."""
    import argparse
    parser = argparse.ArgumentParser(description="Stagger-Step Chain CLI")
    parser.add_argument("prompt", nargs="?", default="What is 2+2?")
    parser.add_argument("--task-type", default="general")
    parser.add_argument("--min-stage", choices=[s.value for s in Stage], default="gguf")
    parser.add_argument("--max-stage", choices=[s.value for s in Stage], default="opus")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-gguf", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    chain = StaggerChain(
        skip_gguf=args.skip_gguf,
        dry_run=args.dry_run,
        store_supabase=not args.dry_run,
    )

    request = ChainRequest(
        task_type=args.task_type,
        system_prompt="You are a helpful assistant.",
        user_prompt=args.prompt,
        min_stage=Stage(args.min_stage),
        max_stage=Stage(args.max_stage),
    )

    result = await chain.run(request)

    print(f"\n{'='*60}")
    print(f"Request ID:  {result.request_id}")
    print(f"Final Stage: {result.final_stage.value}")
    print(f"Verdict:     {result.final_verdict.value}")
    print(f"Cost:        ${result.total_cost_usd:.6f}")
    print(f"Latency:     {result.total_latency_ms:.0f}ms")
    print(f"Path:        {' → '.join(result.escalation_path)}")
    print(f"{'='*60}")
    for sr in result.stages_attempted:
        status = "✓" if sr.verdict == Verdict.RESOLVED else "↗" if sr.verdict == Verdict.ESCALATE else "✗"
        print(f"  {status} {sr.stage.value}: confidence={sr.confidence:.2f} cost=${sr.cost_usd:.6f} ({sr.latency_ms:.0f}ms)")
    print(f"{'='*60}")
    print(result.response_text[:1000])


if __name__ == "__main__":
    asyncio.run(_main())
