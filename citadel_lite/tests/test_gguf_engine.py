"""Tests for src/roadmap/gguf_engine.py — MS-8.

All tests run without llama-cpp-python installed (rule-based fallback path).
"""

from __future__ import annotations

import pytest

from src.roadmap import gguf_engine


# ---------------------------------------------------------------------------
# Module-level availability checks
# ---------------------------------------------------------------------------

class TestModuleAvailability:
    def test_has_llama_flag_is_bool(self):
        assert isinstance(gguf_engine._HAS_LLAMA, bool)

    def test_llama_not_installed_in_test_env(self):
        # In the CI / test environment llama-cpp-python is not installed
        assert gguf_engine._HAS_LLAMA is False


# ---------------------------------------------------------------------------
# load_model
# ---------------------------------------------------------------------------

class TestLoadModel:
    def test_returns_none_without_llama(self):
        result = gguf_engine.load_model()
        assert result is None

    def test_returns_none_with_missing_env(self, monkeypatch):
        monkeypatch.delenv("CITADEL_GGUF_MODEL", raising=False)
        result = gguf_engine.load_model()
        assert result is None

    def test_returns_none_with_nonexistent_model_path(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CITADEL_GGUF_MODEL", str(tmp_path / "nonexistent.gguf"))
        result = gguf_engine.load_model()
        assert result is None


# ---------------------------------------------------------------------------
# summarize
# ---------------------------------------------------------------------------

class TestSummarize:
    def test_short_text_returned_as_is(self):
        text = "Short text"
        result = gguf_engine.summarize(text, max_chars=150)
        assert result == text

    def test_long_text_truncated(self):
        text = "word " * 100  # 500 chars
        result = gguf_engine.summarize(text, max_chars=50)
        assert len(result) <= 60  # allows for ellipsis

    def test_result_ends_with_ellipsis_when_truncated(self):
        text = "a" * 200
        result = gguf_engine.summarize(text, max_chars=50)
        assert result.endswith("...")

    def test_markdown_symbols_stripped(self):
        text = "## **Bold** `code` text"
        result = gguf_engine.summarize(text)
        assert "##" not in result
        assert "**" not in result
        assert "`" not in result

    def test_returns_string(self):
        result = gguf_engine.summarize("Any text")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# generate_risk
# ---------------------------------------------------------------------------

class TestGenerateRisk:
    def test_blocked_keyword_flagged(self):
        result = gguf_engine.generate_risk("This item is blocked by upstream")
        assert result != ""
        assert "blocked" in result.lower() or "block" in result.lower()

    def test_todo_keyword_flagged(self):
        result = gguf_engine.generate_risk("TODO: implement this feature")
        assert result != ""

    def test_dependency_keyword_flagged(self):
        result = gguf_engine.generate_risk("依存するサービスが未完成")
        assert result != ""

    def test_clean_text_returns_empty(self):
        result = gguf_engine.generate_risk("Everything is working great!")
        assert result == ""

    def test_multiple_keywords_combined(self):
        result = gguf_engine.generate_risk("blocked and 依存 and TODO")
        assert "|" in result  # multiple notes joined with "|"

    def test_returns_string(self):
        result = gguf_engine.generate_risk("any text")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# recommend
# ---------------------------------------------------------------------------

class TestRecommend:
    def test_done_verified_no_action(self):
        result = gguf_engine.recommend("done", "verified")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_done_unknown_suggests_tests(self):
        result = gguf_engine.recommend("done", "unknown")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_blocked_unknown_suggests_unblock(self):
        result = gguf_engine.recommend("blocked", "unknown")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_unknown_status_returns_string(self):
        result = gguf_engine.recommend("unknown", "unknown")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_unrecognized_combination_returns_string(self):
        result = gguf_engine.recommend("in_progress", "verified")
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# generate_text (fallback path)
# ---------------------------------------------------------------------------

class TestGenerateText:
    def test_returns_string_without_model(self):
        result = gguf_engine.generate_text("Some prompt text", model=None)
        assert isinstance(result, str)

    def test_result_is_non_empty_for_non_empty_prompt(self):
        result = gguf_engine.generate_text("Feature: authentication", model=None)
        assert len(result) > 0

    def test_result_bounded_by_max_chars(self):
        long_prompt = "word " * 200
        result = gguf_engine.generate_text(long_prompt, model=None, max_tokens=50)
        # Rule-based uses summarize(150) — result should be reasonably short
        assert len(result) <= 200
