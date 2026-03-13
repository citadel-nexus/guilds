"""Tests for MCA ProfErrorCartographer (MS-6).

Covers:
  - analyze() with mock Bedrock (JSON, markdown-wrapped JSON, None)
  - Empty/invalid input handling
  - Result normalization
"""

from __future__ import annotations

from typing import Optional
from unittest.mock import MagicMock

import pytest

from src.mca.professors.prof_error_cartographer import ProfErrorCartographer

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "test_prof_error_cartographer"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
_SAMPLE_ERROR_LOG = """\
Traceback (most recent call last):
  File "src/agents/fixer_v3.py", line 142, in apply_fix
    result = self.llm_client.call(prompt)
  File "src/llm/client.py", line 88, in call
    response = self._openai.chat.completions.create(**kwargs)
TypeError: 'NoneType' object is not callable

During handling of the above exception:
  File "src/agents/fixer_v3.py", line 148, in apply_fix
    self._fallback(error=e)
"""

_LLM_JSON_RESPONSE = """{
  "error_mappings": [
    {
      "error_id": "E1",
      "error_summary": "NoneType not callable in LLM client",
      "source_file": "src/llm/client.py",
      "source_line": "88",
      "root_cause": "OpenAI client not initialized",
      "lineage": "systemic"
    }
  ],
  "risk_patterns": [
    {
      "pattern": "Silent fallback masking",
      "severity": "high",
      "locations": ["src/agents/fixer_v3.py:148"],
      "description": "Fallback handler may swallow the root cause"
    }
  ],
  "mitigations": [
    "Add assertion or early return if OpenAI client is None",
    "Log original exception before fallback"
  ],
  "summary": "LLM client initialization failure with silent fallback risk"
}"""

_LLM_MARKDOWN_RESPONSE = """Analysis complete:

```json
{
  "error_mappings": [
    {
      "error_id": "E2",
      "error_summary": "TypeError in LLM call",
      "source_file": "client.py",
      "source_line": "88",
      "root_cause": "Uninitialized client",
      "lineage": "surface"
    }
  ],
  "risk_patterns": [],
  "mitigations": ["Initialize client in __init__"],
  "summary": "Simple init issue"
}
```
"""


class TestProfErrorCartographer:
    """Tests for ProfErrorCartographer."""

    def _make_prof(self, llm_return: Optional[str] = None) -> ProfErrorCartographer:
        """Create professor with mocked Bedrock."""
        mock_bedrock = MagicMock()
        mock_bedrock.is_available.return_value = llm_return is not None

        if llm_return is not None:
            resp = MagicMock()
            resp.success = True
            resp.content = llm_return
            resp.input_tokens = 100
            resp.output_tokens = 50
            resp.latency_ms = 200
            mock_bedrock.invoke.return_value = resp
        else:
            resp = MagicMock()
            resp.success = False
            resp.content = None
            resp.error = "unavailable"
            mock_bedrock.invoke.return_value = resp

        return ProfErrorCartographer(bedrock_client=mock_bedrock)

    def test_analyze_with_json_response(self) -> None:
        prof = self._make_prof(_LLM_JSON_RESPONSE)
        result = prof.analyze(_SAMPLE_ERROR_LOG)

        assert len(result["error_mappings"]) == 1
        assert result["error_mappings"][0]["lineage"] == "systemic"
        assert len(result["risk_patterns"]) == 1
        assert result["risk_patterns"][0]["severity"] == "high"
        assert len(result["mitigations"]) == 2
        assert "LLM client" in result["summary"]

    def test_analyze_with_markdown_response(self) -> None:
        prof = self._make_prof(_LLM_MARKDOWN_RESPONSE)
        result = prof.analyze(_SAMPLE_ERROR_LOG)

        assert len(result["error_mappings"]) == 1
        assert result["error_mappings"][0]["error_id"] == "E2"
        assert len(result["mitigations"]) == 1

    def test_analyze_llm_unavailable(self) -> None:
        prof = self._make_prof(None)
        result = prof.analyze(_SAMPLE_ERROR_LOG)

        assert result["error_mappings"] == []
        assert result["risk_patterns"] == []
        assert result["mitigations"] == []

    def test_analyze_empty_input(self) -> None:
        prof = self._make_prof(_LLM_JSON_RESPONSE)
        result = prof.analyze("")

        assert result == prof._empty_result()

    def test_analyze_invalid_input(self) -> None:
        prof = self._make_prof(_LLM_JSON_RESPONSE)
        result = prof.analyze(123)  # type: ignore[arg-type]

        assert result == prof._empty_result()

    def test_unparseable_llm_output(self) -> None:
        prof = self._make_prof("Just some text, no JSON")
        result = prof.analyze(_SAMPLE_ERROR_LOG)

        assert result["error_mappings"] == []
        assert "Just some text" in result["summary"]

    def test_result_normalization(self) -> None:
        """Missing keys should default to empty."""
        prof = self._make_prof('{"summary": "partial"}')
        result = prof.analyze(_SAMPLE_ERROR_LOG)

        assert result["error_mappings"] == []
        assert result["risk_patterns"] == []
        assert result["mitigations"] == []
        assert result["summary"] == "partial"

    def test_cgrf_metadata(self) -> None:
        from src.mca.professors import prof_error_cartographer as mod

        assert mod._MODULE_NAME == "prof_error_cartographer"
        assert mod._CGRF_TIER == 1
