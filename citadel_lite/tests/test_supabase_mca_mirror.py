"""
Tests for src/infra/supabase_mca_mirror.py — MS-7 Phase 1-B

All external HTTP calls are mocked; no real Supabase connection is needed.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.infra.supabase_mca_mirror import (
    mirror_evo_cycle,
    mirror_proposals,
    get_recent_cycles,
    get_proposals_for_cycle,
    get_domain_health_summary,
)


# ============================================================
# mirror_evo_cycle
# ============================================================

class TestMirrorEvoCycle:
    def test_dry_run_returns_placeholder_id(self):
        result = mirror_evo_cycle(
            cycle_id="evo-test-001",
            event_type="market_expansion",
            domain="sales",
            health_score=85.0,
            proposal_count=10,
            approved_count=4,
            duration_seconds=15.0,
            dry_run=True,
        )
        assert result == "dry-run-row-id"

    def test_no_credentials_returns_none(self):
        with patch("src.infra.supabase_mca_mirror._base_url", return_value=None):
            result = mirror_evo_cycle(
                cycle_id="evo-002",
                event_type="test",
                domain="ops",
                health_score=50.0,
                proposal_count=0,
                approved_count=0,
                duration_seconds=1.0,
            )
        assert result is None

    def test_successful_insert_returns_row_id(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"id": "row-uuid-123"}]
        mock_resp.raise_for_status = MagicMock()

        with patch("src.infra.supabase_mca_mirror._base_url", return_value="https://example.supabase.co"), \
             patch("src.infra.supabase_mca_mirror._service_key", return_value="service-key"), \
             patch("requests.post", return_value=mock_resp):
            result = mirror_evo_cycle(
                cycle_id="evo-003",
                event_type="market_expansion",
                domain="sales",
                health_score=90.0,
                proposal_count=5,
                approved_count=3,
                duration_seconds=20.0,
            )

        assert result == "row-uuid-123"

    def test_request_exception_returns_none(self):
        import requests as req_lib
        with patch("src.infra.supabase_mca_mirror._base_url", return_value="https://example.supabase.co"), \
             patch("src.infra.supabase_mca_mirror._service_key", return_value="key"), \
             patch("requests.post", side_effect=req_lib.RequestException("timeout")):
            result = mirror_evo_cycle(
                cycle_id="evo-fail",
                event_type="test",
                domain="cs",
                health_score=40.0,
                proposal_count=1,
                approved_count=0,
                duration_seconds=5.0,
            )
        assert result is None

    def test_notion_page_id_included_in_payload(self):
        captured_body = {}

        def mock_post(url, headers, json, timeout):
            captured_body.update(json)
            resp = MagicMock()
            resp.json.return_value = [{"id": "r1"}]
            resp.raise_for_status = MagicMock()
            return resp

        with patch("src.infra.supabase_mca_mirror._base_url", return_value="https://x.supabase.co"), \
             patch("src.infra.supabase_mca_mirror._service_key", return_value="k"), \
             patch("requests.post", side_effect=mock_post):
            mirror_evo_cycle(
                cycle_id="evo-004",
                event_type="market_expansion",
                domain="product",
                health_score=75.0,
                proposal_count=3,
                approved_count=1,
                duration_seconds=10.0,
                notion_page_id="notion-abc-123",
            )

        assert captured_body["payload"]["notion_page_id"] == "notion-abc-123"


# ============================================================
# mirror_proposals
# ============================================================

class TestMirrorProposals:
    def test_empty_proposals_returns_zero(self):
        result = mirror_proposals("evo-001", [])
        assert result == 0

    def test_dry_run_returns_count(self):
        proposals = [
            {"title": "Prop A", "priority": "P1", "ep_type": "new_feature", "domain": "sales", "status": "pending"},
            {"title": "Prop B", "priority": "P2", "ep_type": "market_expansion", "domain": "marketing", "status": "pending"},
        ]
        result = mirror_proposals("evo-001", proposals, dry_run=True)
        assert result == 2

    def test_no_credentials_returns_zero(self):
        with patch("src.infra.supabase_mca_mirror._base_url", return_value=None):
            result = mirror_proposals("evo-001", [{"title": "X", "priority": "P1", "ep_type": "t", "domain": "d", "status": "pending"}])
        assert result == 0

    def test_successful_bulk_insert(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"id": "r1"}, {"id": "r2"}]
        mock_resp.raise_for_status = MagicMock()

        proposals = [
            {"title": "A", "priority": "P1", "ep_type": "new_feature", "domain": "sales", "status": "pending"},
            {"title": "B", "priority": "P2", "ep_type": "cost_reduction", "domain": "ops", "status": "pending"},
        ]
        with patch("src.infra.supabase_mca_mirror._base_url", return_value="https://x.supabase.co"), \
             patch("src.infra.supabase_mca_mirror._service_key", return_value="k"), \
             patch("requests.post", return_value=mock_resp):
            result = mirror_proposals("evo-002", proposals)

        assert result == 2

    def test_extra_keys_go_to_metadata(self):
        captured = {}

        def mock_post(url, headers, json, timeout):
            captured["rows"] = json
            resp = MagicMock()
            resp.json.return_value = [{"id": "r1"}]
            resp.raise_for_status = MagicMock()
            return resp

        proposals = [{"title": "X", "priority": "P1", "ep_type": "t", "domain": "sales", "status": "pending", "my_custom": "value"}]
        with patch("src.infra.supabase_mca_mirror._base_url", return_value="https://x.supabase.co"), \
             patch("src.infra.supabase_mca_mirror._service_key", return_value="k"), \
             patch("requests.post", side_effect=mock_post):
            mirror_proposals("evo-003", proposals)

        row = captured["rows"][0]
        assert row["metadata"]["my_custom"] == "value"
        assert "my_custom" not in row


# ============================================================
# get_recent_cycles
# ============================================================

class TestGetRecentCycles:
    def test_no_credentials_returns_empty(self):
        with patch("src.infra.supabase_mca_mirror._base_url", return_value=None):
            result = get_recent_cycles()
        assert result == []

    def test_returns_parsed_rows(self):
        raw_payload = json.dumps({"cycle_id": "evo-001", "domain": "sales", "health_score": 88.0})
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {"id": "row-1", "event_type": "mca_evo_cycle", "payload": raw_payload, "created_at": "2026-02-25T10:00:00Z"},
        ]
        mock_resp.raise_for_status = MagicMock()

        with patch("src.infra.supabase_mca_mirror._base_url", return_value="https://x.supabase.co"), \
             patch("src.infra.supabase_mca_mirror._service_key", return_value="k"), \
             patch("requests.get", return_value=mock_resp):
            result = get_recent_cycles(limit=5)

        assert len(result) == 1
        assert result[0]["payload"]["cycle_id"] == "evo-001"
        assert result[0]["payload"]["health_score"] == 88.0


# ============================================================
# get_domain_health_summary
# ============================================================

class TestGetDomainHealthSummary:
    def test_no_credentials_returns_empty(self):
        with patch("src.infra.supabase_mca_mirror._base_url", return_value=None):
            result = get_domain_health_summary()
        assert result == []

    def test_returns_health_entries(self):
        payload = {"cycle_id": "evo-001", "domain": "sales", "health_score": 75.0}
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {"payload": json.dumps(payload), "created_at": "2026-02-25T10:00:00Z"},
        ]
        mock_resp.raise_for_status = MagicMock()

        with patch("src.infra.supabase_mca_mirror._base_url", return_value="https://x.supabase.co"), \
             patch("src.infra.supabase_mca_mirror._service_key", return_value="k"), \
             patch("requests.get", return_value=mock_resp):
            result = get_domain_health_summary(domain="sales")

        assert len(result) == 1
        assert result[0]["health_score"] == 75.0
        assert result[0]["domain"] == "sales"
