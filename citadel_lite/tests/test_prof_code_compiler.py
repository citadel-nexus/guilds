"""Tests for MCA ProfCodeCompiler (MS-5).

Covers:
  - analyze() with mock Bedrock (JSON, markdown-wrapped JSON, None)
  - Local regex extraction
  - SHA-256 fingerprinting
  - Merge logic (LLM + local)
  - Empty/invalid input handling
"""

from __future__ import annotations

import hashlib
from typing import Optional
from unittest.mock import MagicMock

import pytest

from src.mca.professors.prof_code_compiler import ProfCodeCompiler

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "test_prof_code_compiler"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
_SAMPLE_CODE = '''\
from __future__ import annotations
import logging
from enum import Enum
from pydantic import BaseModel

class StatusEnum(str, Enum):
    active = "active"
    inactive = "inactive"

class UserModel(BaseModel):
    name: str
    email: str

async def fetch_data(url: str) -> dict:
    """Fetch data from the given URL."""
    pass

def process(items: list) -> None:
    """Process a list of items."""
    for item in items:
        with open("output.txt") as f:
            f.write(str(item))
'''

_LLM_JSON_RESPONSE = '''{
  "enums": [{"name": "StatusEnum", "members": ["active", "inactive"]}],
  "functions": [
    {"name": "fetch_data", "params": "url: str", "docstring": "Fetch data from the given URL."},
    {"name": "process", "params": "items: list", "docstring": "Process a list of items."}
  ],
  "schemas": [{"name": "UserModel", "fields": ["name: str", "email: str"]}],
  "dependencies": ["logging", "pydantic"],
  "complexity_tags": ["ASYNC", "IO_BOUND"]
}'''

_LLM_MARKDOWN_RESPONSE = '''Here is the extraction:

```json
{
  "enums": [{"name": "StatusEnum", "members": ["active", "inactive"]}],
  "functions": [{"name": "fetch_data", "params": "url: str", "docstring": "Fetch data"}],
  "schemas": [],
  "dependencies": ["pydantic"],
  "complexity_tags": ["ASYNC"]
}
```
'''


class TestProfCodeCompiler:
    """Tests for ProfCodeCompiler."""

    def _make_prof(self, llm_return: Optional[str] = None) -> ProfCodeCompiler:
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

        return ProfCodeCompiler(bedrock_client=mock_bedrock)

    def test_analyze_with_json_response(self) -> None:
        prof = self._make_prof(_LLM_JSON_RESPONSE)
        result = prof.analyze(_SAMPLE_CODE)

        assert len(result["enums"]) >= 1
        assert result["enums"][0]["name"] == "StatusEnum"
        assert len(result["functions"]) >= 1
        assert any(f["name"] == "fetch_data" for f in result["functions"])
        assert "ASYNC" in result["complexity_tags"]
        assert "fingerprints" in result
        expected_sha = hashlib.sha256(_SAMPLE_CODE.encode("utf-8")).hexdigest()
        assert result["fingerprints"]["full_sha256"] == expected_sha

    def test_analyze_with_markdown_response(self) -> None:
        prof = self._make_prof(_LLM_MARKDOWN_RESPONSE)
        result = prof.analyze(_SAMPLE_CODE)

        assert len(result["enums"]) >= 1
        assert "fingerprints" in result

    def test_analyze_llm_unavailable_local_fallback(self) -> None:
        prof = self._make_prof(None)
        result = prof.analyze(_SAMPLE_CODE)

        # Local extraction should still work
        assert len(result["enums"]) >= 1
        assert any(e["name"] == "StatusEnum" for e in result["enums"])
        assert len(result["functions"]) >= 1
        assert any(f["name"] == "fetch_data" for f in result["functions"])
        assert len(result["schemas"]) >= 1
        assert any(s["name"] == "UserModel" for s in result["schemas"])
        assert "fingerprints" in result

    def test_local_extraction_complexity_tags(self) -> None:
        prof = self._make_prof(None)
        result = prof.analyze(_SAMPLE_CODE)

        assert "ASYNC" in result["complexity_tags"]
        assert "IO_BOUND" in result["complexity_tags"]

    def test_local_extraction_dependencies(self) -> None:
        prof = self._make_prof(None)
        result = prof.analyze(_SAMPLE_CODE)

        assert "logging" in result["dependencies"]
        assert "pydantic" in result["dependencies"]

    def test_empty_input(self) -> None:
        prof = self._make_prof(_LLM_JSON_RESPONSE)
        result = prof.analyze("")

        assert result["enums"] == []
        assert result["functions"] == []
        assert result["fingerprints"] == {}

    def test_invalid_input(self) -> None:
        prof = self._make_prof(_LLM_JSON_RESPONSE)
        result = prof.analyze(42)  # type: ignore[arg-type]

        assert result == prof._empty_result()

    def test_fingerprint_deterministic(self) -> None:
        prof = self._make_prof(_LLM_JSON_RESPONSE)
        r1 = prof.analyze(_SAMPLE_CODE)
        r2 = prof.analyze(_SAMPLE_CODE)
        assert r1["fingerprints"]["full_sha256"] == r2["fingerprints"]["full_sha256"]

    def test_unparseable_llm_output(self) -> None:
        prof = self._make_prof("This is not JSON")
        result = prof.analyze(_SAMPLE_CODE)

        # Should fall back to local extraction
        assert len(result["enums"]) >= 1
        assert "fingerprints" in result
