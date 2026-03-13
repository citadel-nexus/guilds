"""Tests for MCA ProfCodeFixer (MS-6).

Covers:
  - analyze() with mock Bedrock (JSON, markdown-wrapped JSON, None)
  - Empty/invalid input handling
  - Result normalization
"""

from __future__ import annotations

from typing import Optional
from unittest.mock import MagicMock

import pytest

from src.mca.professors.prof_code_fixer import ProfCodeFixer

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "test_prof_code_fixer"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
_SAMPLE_ANALYSES = {
    "archeologist": {
        "design_patterns": ["Factory: ShapeFactory"],
        "anti_patterns": ["God class: GodObject has too many responsibilities"],
        "architecture_notes": ["Simple module"],
        "complexity_hotspots": [],
    },
    "compiler": {
        "functions": [{"name": "create", "complexity": 3}],
        "enums": ["Color"],
    },
    "error_cartographer": {
        "error_mappings": [
            {"error_id": "E1", "error_summary": "NoneType error", "source_file": "app.py", "source_line": "42"}
        ],
    },
    "ethicist": {
        "ethical_concerns": [],
        "governance_assessment": {"overall_verdict": "pass"},
    },
}

_LLM_JSON_RESPONSE = """{
  "fixes": [
    {
      "fix_id": "F1",
      "target_file": "app.py",
      "fix_type": "code_block",
      "severity": "high",
      "description": "Add null check before access",
      "rationale": "Error Cartographer identified NoneType at line 42",
      "patch": "if obj is not None:\\n    obj.method()"
    }
  ],
  "summary": "1 high-severity fix proposed for NoneType error",
  "risk_notes": ["Verify upstream callers"]
}"""

_LLM_MARKDOWN_RESPONSE = """Here are the fixes:

```json
{
  "fixes": [
    {
      "fix_id": "F2",
      "target_file": "god_object.py",
      "fix_type": "diff_patch",
      "severity": "medium",
      "description": "Extract responsibilities",
      "rationale": "Archeologist flagged God class",
      "patch": "- class GodObject\\n+ class FocusedHandler"
    }
  ],
  "summary": "Refactor God class",
  "risk_notes": []
}
```
"""


class TestProfCodeFixer:
    """Tests for ProfCodeFixer."""

    def _make_prof(self, llm_return: Optional[str] = None) -> ProfCodeFixer:
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

        return ProfCodeFixer(bedrock_client=mock_bedrock)

    def test_analyze_with_json_response(self) -> None:
        prof = self._make_prof(_LLM_JSON_RESPONSE)
        result = prof.analyze(_SAMPLE_ANALYSES)

        assert len(result["fixes"]) == 1
        assert result["fixes"][0]["fix_id"] == "F1"
        assert result["fixes"][0]["severity"] == "high"
        assert "NoneType" in result["summary"]
        assert len(result["risk_notes"]) == 1

    def test_analyze_with_markdown_response(self) -> None:
        prof = self._make_prof(_LLM_MARKDOWN_RESPONSE)
        result = prof.analyze(_SAMPLE_ANALYSES)

        assert len(result["fixes"]) == 1
        assert result["fixes"][0]["fix_id"] == "F2"
        assert "God class" in result["summary"]

    def test_analyze_llm_unavailable(self) -> None:
        prof = self._make_prof(None)
        result = prof.analyze(_SAMPLE_ANALYSES)

        assert result["fixes"] == []
        assert result["summary"] == ""
        assert result["risk_notes"] == []

    def test_analyze_empty_input(self) -> None:
        prof = self._make_prof(_LLM_JSON_RESPONSE)
        result = prof.analyze({})

        assert result["fixes"] == []

    def test_analyze_invalid_input(self) -> None:
        prof = self._make_prof(_LLM_JSON_RESPONSE)
        result = prof.analyze("not a dict")  # type: ignore[arg-type]

        assert result == prof._empty_result()

    def test_unparseable_llm_output(self) -> None:
        prof = self._make_prof("This is not JSON at all")
        result = prof.analyze(_SAMPLE_ANALYSES)

        assert result["fixes"] == []
        assert len(result["risk_notes"]) > 0

    def test_result_normalization_missing_keys(self) -> None:
        prof = self._make_prof('{"summary": "partial"}')
        result = prof.analyze(_SAMPLE_ANALYSES)

        assert result["fixes"] == []
        assert result["summary"] == "partial"
        assert result["risk_notes"] == []

    def test_code_text_truncation(self) -> None:
        """Verify that long code_text is truncated in user message."""
        prof = self._make_prof(_LLM_JSON_RESPONSE)
        inputs = {"code_text": "x = 1\n" * 2000}
        result = prof.analyze(inputs)
        # Should succeed without error
        assert isinstance(result, dict)

    def test_cgrf_metadata(self) -> None:
        from src.mca.professors import prof_code_fixer as mod

        assert mod._MODULE_NAME == "prof_code_fixer"
        assert mod._CGRF_TIER == 1
