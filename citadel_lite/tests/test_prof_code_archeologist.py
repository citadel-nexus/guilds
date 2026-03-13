"""Tests for MCA ProfCodeArcheologist (MS-5).

Covers:
  - analyze() with mock Bedrock (JSON, markdown-wrapped JSON, None)
  - AST enum detection
  - Empty/invalid input handling
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

from src.mca.professors.prof_code_archeologist import ProfCodeArcheologist

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "test_prof_code_archeologist"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
_SAMPLE_CODE = '''\
from enum import Enum

class Color(Enum):
    RED = "red"
    GREEN = "green"
    BLUE = "blue"

class ShapeFactory:
    """Factory pattern for creating shapes."""

    def create(self, shape_type: str):
        if shape_type == "circle":
            return Circle()
        elif shape_type == "square":
            return Square()

class GodObject:
    """Does everything — anti-pattern."""

    def method_a(self): pass
    def method_b(self): pass
    def method_c(self): pass
    def method_d(self): pass
    def method_e(self): pass
    def method_f(self): pass
    def method_g(self): pass
    def method_h(self): pass
'''

_LLM_JSON_RESPONSE = '''{
  "design_patterns": ["Factory: ShapeFactory creates shapes based on type"],
  "anti_patterns": ["God class: GodObject has too many responsibilities"],
  "architecture_notes": ["Simple module with factory and data model"],
  "complexity_hotspots": []
}'''

_LLM_MARKDOWN_RESPONSE = '''Here is my analysis:

```json
{
  "design_patterns": ["Factory: ShapeFactory"],
  "anti_patterns": ["God class: GodObject"],
  "architecture_notes": ["Mixed patterns"],
  "complexity_hotspots": ["GodObject methods"]
}
```
'''


class TestProfCodeArcheologist:
    """Tests for ProfCodeArcheologist."""

    def _make_prof(self, llm_return: Optional[str] = None) -> ProfCodeArcheologist:
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

        return ProfCodeArcheologist(bedrock_client=mock_bedrock)

    def test_analyze_with_json_response(self) -> None:
        prof = self._make_prof(_LLM_JSON_RESPONSE)
        result = prof.analyze(_SAMPLE_CODE)

        assert len(result["design_patterns"]) == 1
        assert "Factory" in result["design_patterns"][0]
        assert len(result["anti_patterns"]) == 1
        assert "God class" in result["anti_patterns"][0]
        # AST should find Color enum
        assert "Color" in result["ast_enumerations"]
        assert "RED" in result["ast_enumerations"]["Color"]

    def test_analyze_with_markdown_response(self) -> None:
        prof = self._make_prof(_LLM_MARKDOWN_RESPONSE)
        result = prof.analyze(_SAMPLE_CODE)

        assert len(result["design_patterns"]) >= 1
        assert len(result["anti_patterns"]) >= 1
        assert "Color" in result["ast_enumerations"]

    def test_analyze_llm_unavailable(self) -> None:
        prof = self._make_prof(None)
        result = prof.analyze(_SAMPLE_CODE)

        # Should still have AST results
        assert "Color" in result["ast_enumerations"]
        assert result["design_patterns"] == []
        assert result["anti_patterns"] == []

    def test_analyze_empty_input(self) -> None:
        prof = self._make_prof(_LLM_JSON_RESPONSE)
        result = prof.analyze("")

        assert result["design_patterns"] == []
        assert result["anti_patterns"] == []
        assert result["ast_enumerations"] == {}

    def test_analyze_invalid_input(self) -> None:
        prof = self._make_prof(_LLM_JSON_RESPONSE)
        result = prof.analyze(123)  # type: ignore[arg-type]

        assert result == prof._empty_result()

    def test_ast_enum_detection_multiple(self) -> None:
        code = '''\
from enum import Enum

class Status(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"

class Priority(Enum):
    LOW = "low"
    HIGH = "high"
'''
        prof = self._make_prof(_LLM_JSON_RESPONSE)
        result = prof.analyze(code)

        assert "Status" in result["ast_enumerations"]
        assert "Priority" in result["ast_enumerations"]
        assert "ACTIVE" in result["ast_enumerations"]["Status"]
        assert "LOW" in result["ast_enumerations"]["Priority"]

    def test_ast_invalid_syntax(self) -> None:
        prof = self._make_prof(_LLM_JSON_RESPONSE)
        result = prof.analyze("def broken(: pass")

        # AST should fail gracefully
        assert result["ast_enumerations"] == {}

    def test_unparseable_llm_output(self) -> None:
        prof = self._make_prof("This is not JSON at all")
        result = prof.analyze(_SAMPLE_CODE)

        # Should fall back to raw output in architecture_notes
        assert len(result["architecture_notes"]) > 0
        assert result["design_patterns"] == []
