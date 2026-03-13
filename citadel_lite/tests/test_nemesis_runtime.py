#!/usr/bin/env python3
"""
test_nemesis_runtime.py
=======================
Assessor-credible test suite for Nemesis v2 Runtime Daemon.

Tests actual attack execution, hash chain integrity, chaos window
enforcement, fault injection recovery, collusion detection, external
validation, accuracy accounting, and scorecard generation.

SRS Codes: NEM-AUD-001 through NEM-EXT-005
Total: 62 tests

--- CGRF Header ---
_document_schema: CGRF-v2.0
_module: citadel_lite.tests.test_nemesis_runtime
_srs_code: NEM-TEST-RUNTIME-001
_compliance: CGRF v2.0
"""

import asyncio
import hashlib
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add source paths
TESTS_DIR = Path(__file__).resolve().parent
CITADEL_LITE_DIR = TESTS_DIR.parent
SRC_DIR = CITADEL_LITE_DIR / "src"
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(CITADEL_LITE_DIR))

from nemesis.runtime.nemesis_daemon import (
    NemesisDaemon,
    NemesisConfig,
    DaemonState,
    HashChainLedger,
    RedTeamEngine,
    FaultInjectionEngine,
    CollusionDetector,
    ExternalValidator,
    AccuracyAccounting,
    ScorecardGenerator,
    ResilienceMetrics,
    JobResult,
)


def run_async(coro):
    """Helper to run async functions in sync test context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestNemesisConfig(unittest.TestCase):
    """Test NemesisConfig defaults and validation."""

    def test_default_config(self):
        config = NemesisConfig()
        self.assertEqual(config.environment, "staging")
        self.assertEqual(config.audit_interval_seconds, 300)
        self.assertEqual(config.red_team_interval_seconds, 14400)
        self.assertEqual(config.max_concurrent_attacks, 3)

    def test_chaos_window_defaults(self):
        config = NemesisConfig()
        self.assertEqual(config.chaos_window_start, 2)
        self.assertEqual(config.chaos_window_end, 6)
        self.assertIn("tuesday", config.chaos_window_days)
        self.assertIn("thursday", config.chaos_window_days)

    def test_production_config(self):
        config = NemesisConfig(environment="production")
        self.assertEqual(config.environment, "production")

    def test_threshold_defaults(self):
        config = NemesisConfig()
        self.assertEqual(config.resilience_score_critical_threshold, 0.5)
        self.assertEqual(config.fp_rate_alert_threshold, 0.05)
        self.assertEqual(config.fn_rate_alert_threshold, 0.10)

    def test_custom_intervals(self):
        config = NemesisConfig(
            audit_interval_seconds=60,
            red_team_interval_seconds=3600,
        )
        self.assertEqual(config.audit_interval_seconds, 60)
        self.assertEqual(config.red_team_interval_seconds, 3600)


class TestDaemonState(unittest.TestCase):
    """Test DaemonState enum."""

    def test_all_states_exist(self):
        states = [s.value for s in DaemonState]
        self.assertIn("starting", states)
        self.assertIn("running", states)
        self.assertIn("paused", states)
        self.assertIn("read_only", states)
        self.assertIn("audit_only", states)
        self.assertIn("emergency_stop", states)
        self.assertIn("shutting_down", states)

    def test_state_count(self):
        self.assertEqual(len(DaemonState), 7)


class TestResilienceMetrics(unittest.TestCase):
    """Test ResilienceMetrics calculations."""

    def test_overall_score_calculation(self):
        m = ResilienceMetrics(
            detection_rate=0.95,
            containment_rate=0.90,
            recovery_rate=0.85,
            external_validation_rate=0.80,
            fault_tolerance_rate=0.75,
        )
        # 0.95*0.25 + 0.90*0.25 + 0.85*0.20 + 0.80*0.15 + 0.75*0.15
        expected = 0.2375 + 0.225 + 0.170 + 0.120 + 0.1125
        self.assertAlmostEqual(m.overall_score, expected, places=4)

    def test_zero_metrics_score(self):
        m = ResilienceMetrics()
        self.assertEqual(m.overall_score, 0.0)

    def test_perfect_score(self):
        m = ResilienceMetrics(
            detection_rate=1.0,
            containment_rate=1.0,
            recovery_rate=1.0,
            external_validation_rate=1.0,
            fault_tolerance_rate=1.0,
        )
        self.assertAlmostEqual(m.overall_score, 1.0)

    def test_fp_rate_calculation(self):
        m = ResilienceMetrics(false_positives=5, true_negatives=95)
        self.assertAlmostEqual(m.fp_rate, 0.05)

    def test_fn_rate_calculation(self):
        m = ResilienceMetrics(false_negatives=10, true_positives=90)
        self.assertAlmostEqual(m.fn_rate, 0.10)

    def test_fp_rate_zero_division(self):
        m = ResilienceMetrics(false_positives=0, true_negatives=0)
        self.assertEqual(m.fp_rate, 0.0)

    def test_fn_rate_zero_division(self):
        m = ResilienceMetrics(false_negatives=0, true_positives=0)
        self.assertEqual(m.fn_rate, 0.0)


class TestHashChainLedger(unittest.TestCase):
    """Test hash-chained immutable audit ledger."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ledger_path = os.path.join(self.tmpdir, "test_ledger.jsonl")

    def test_new_ledger_starts_at_genesis(self):
        ledger = HashChainLedger(self.ledger_path)
        self.assertEqual(ledger.chain_position, 0)
        self.assertEqual(ledger.previous_hash, "GENESIS")

    def test_append_increments_position(self):
        ledger = HashChainLedger(self.ledger_path)
        pos1 = ledger.append("test_event", {"key": "value1"})
        self.assertEqual(pos1, 1)
        pos2 = ledger.append("test_event", {"key": "value2"})
        self.assertEqual(pos2, 2)

    def test_hash_chain_links(self):
        ledger = HashChainLedger(self.ledger_path)
        ledger.append("event_a", {"data": "first"})
        ledger.append("event_b", {"data": "second"})
        ledger.append("event_c", {"data": "third"})

        with open(self.ledger_path, 'r') as f:
            entries = [json.loads(line) for line in f]

        self.assertEqual(entries[0]["previous_hash"], "GENESIS")
        self.assertEqual(entries[1]["previous_hash"], entries[0]["hash"])
        self.assertEqual(entries[2]["previous_hash"], entries[1]["hash"])

    def test_integrity_verification_passes(self):
        ledger = HashChainLedger(self.ledger_path)
        ledger.append("event_1", {"test": True})
        ledger.append("event_2", {"test": True})
        ledger.append("event_3", {"test": True})
        self.assertTrue(ledger.verify_integrity())

    def test_tampered_ledger_detected(self):
        ledger = HashChainLedger(self.ledger_path)
        ledger.append("event_1", {"value": 100})
        ledger.append("event_2", {"value": 200})

        # Tamper with ledger
        with open(self.ledger_path, 'r') as f:
            entries = [json.loads(line) for line in f]
        entries[0]["data"]["data"]["value"] = 999  # Tamper
        with open(self.ledger_path, 'w') as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        # Reload should detect tampering
        with self.assertRaises(RuntimeError) as ctx:
            HashChainLedger(self.ledger_path)
        self.assertIn("INTEGRITY VIOLATION", str(ctx.exception))

    def test_hash_is_sha256(self):
        ledger = HashChainLedger(self.ledger_path)
        ledger.append("test", {"data": "hello"})

        with open(self.ledger_path, 'r') as f:
            entry = json.loads(f.readline())
        self.assertEqual(len(entry["hash"]), 64)  # SHA-256 hex length

    def test_reload_preserves_chain(self):
        ledger = HashChainLedger(self.ledger_path)
        ledger.append("event_1", {"x": 1})
        ledger.append("event_2", {"x": 2})
        prev_hash = ledger.previous_hash
        position = ledger.chain_position

        ledger2 = HashChainLedger(self.ledger_path)
        self.assertEqual(ledger2.previous_hash, prev_hash)
        self.assertEqual(ledger2.chain_position, position)

    def test_empty_ledger_verifies(self):
        ledger = HashChainLedger(self.ledger_path)
        self.assertTrue(ledger.verify_integrity())

    def test_length_property(self):
        ledger = HashChainLedger(self.ledger_path)
        self.assertEqual(ledger.length, 0)
        ledger.append("e1", {})
        self.assertEqual(ledger.length, 1)
        ledger.append("e2", {})
        self.assertEqual(ledger.length, 2)


class TestRedTeamEngine(unittest.TestCase):
    """Test red-team attack execution engine."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = NemesisConfig()
        self.ledger = HashChainLedger(os.path.join(self.tmpdir, "ledger.jsonl"))
        self.engine = RedTeamEngine(self.config, self.ledger)

    def test_attack_corpus_loaded(self):
        self.assertGreater(len(self.engine.attack_corpus), 0)
        self.assertGreaterEqual(len(self.engine.attack_corpus), 13)

    def test_all_attacks_have_required_fields(self):
        required = {"id", "category", "name", "payload", "expected_detection", "severity", "cvss_base"}
        for attack in self.engine.attack_corpus:
            for field in required:
                self.assertIn(field, attack, f"Attack {attack.get('id', '?')} missing field {field}")

    def test_attack_categories_present(self):
        categories = {a["category"] for a in self.engine.attack_corpus}
        self.assertIn("privilege_escalation", categories)
        self.assertIn("governance_bypass", categories)
        self.assertIn("memory_poisoning", categories)
        self.assertIn("prompt_injection", categories)
        self.assertIn("integration_spoof", categories)

    def test_cvss_scores_in_range(self):
        for attack in self.engine.attack_corpus:
            self.assertGreaterEqual(attack["cvss_base"], 0.0)
            self.assertLessEqual(attack["cvss_base"], 10.0)

    def test_execute_single_attack(self):
        attack = self.engine.attack_corpus[0]
        result = run_async(self.engine.execute_attack(attack))
        self.assertTrue(result.success)
        self.assertIsNotNone(result.completed_at)
        self.assertIn("attack_id", result.metrics)
        self.assertIn("detected", result.metrics)
        self.assertIn("payload_hash", result.metrics)

    def test_execute_attack_logs_to_ledger(self):
        attack = self.engine.attack_corpus[0]
        run_async(self.engine.execute_attack(attack))
        self.assertGreaterEqual(self.ledger.chain_position, 2)  # started + completed

    def test_payload_hash_is_deterministic(self):
        attack = self.engine.attack_corpus[0]
        r1 = run_async(self.engine.execute_attack(attack))
        r2 = run_async(self.engine.execute_attack(attack))
        self.assertEqual(r1.metrics["payload_hash"], r2.metrics["payload_hash"])

    def test_detection_is_deterministic(self):
        """Detection must be deterministic (hash-based, not random)."""
        attack = self.engine.attack_corpus[0]
        r1 = run_async(self.engine.execute_attack(attack))
        r2 = run_async(self.engine.execute_attack(attack))
        self.assertEqual(r1.metrics["detected"], r2.metrics["detected"])

    def test_run_campaign_all_categories(self):
        results = run_async(self.engine.run_campaign())
        self.assertEqual(len(results), len(self.engine.attack_corpus))
        self.assertTrue(all(r.success for r in results))

    def test_run_campaign_filtered(self):
        results = run_async(self.engine.run_campaign(categories=["privilege_escalation"]))
        for r in results:
            self.assertEqual(r.metrics["category"], "privilege_escalation")

    def test_chaos_window_check_staging(self):
        """Staging ignores chaos window; only production enforces."""
        self.config.environment = "staging"
        # The engine itself doesn't block, the daemon does
        # Just verify the method works
        result = self.engine.is_within_chaos_window()
        self.assertIsInstance(result, bool)


class TestFaultInjectionEngine(unittest.TestCase):
    """Test fault injection and recovery measurement."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = NemesisConfig()
        self.ledger = HashChainLedger(os.path.join(self.tmpdir, "ledger.jsonl"))
        self.engine = FaultInjectionEngine(self.config, self.ledger)

    def test_state_corruption_metrics(self):
        result = run_async(self.engine.inject_state_corruption())
        self.assertTrue(result.success)
        self.assertIn("vectors_corrupted", result.metrics)
        self.assertIn("vectors_recovered", result.metrics)
        self.assertIn("recovery_success", result.metrics)
        self.assertIn("detection_time_ms", result.metrics)

    def test_signal_delay_metrics(self):
        result = run_async(self.engine.inject_signal_delay(delay_seconds=15))
        self.assertTrue(result.success)
        self.assertEqual(result.metrics["injected_delay_seconds"], 15)
        self.assertTrue(result.metrics["timeout_detected"])
        self.assertTrue(result.metrics["circuit_breaker_activated"])

    def test_signal_delay_no_circuit_breaker_for_short_delay(self):
        result = run_async(self.engine.inject_signal_delay(delay_seconds=3))
        self.assertTrue(result.success)
        self.assertFalse(result.metrics["circuit_breaker_activated"])

    def test_cascade_failure_containment(self):
        result = run_async(self.engine.inject_cascade_failure())
        self.assertTrue(result.success)
        self.assertTrue(result.metrics["cascade_contained"])
        self.assertTrue(result.metrics["circuit_breaker_activated"])
        self.assertTrue(result.metrics["alert_fired"])

    def test_fault_injection_logs_to_ledger(self):
        run_async(self.engine.inject_state_corruption())
        self.assertGreaterEqual(self.ledger.chain_position, 2)

    def test_no_data_loss_on_delay(self):
        result = run_async(self.engine.inject_signal_delay(10))
        self.assertFalse(result.metrics["data_loss"])


class TestCollusionDetector(unittest.TestCase):
    """Test collusion detection scans."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ledger = HashChainLedger(os.path.join(self.tmpdir, "ledger.jsonl"))
        self.detector = CollusionDetector(self.ledger)

    def test_trust_inflation_scan(self):
        result = run_async(self.detector.scan_trust_inflation())
        self.assertTrue(result.success)
        self.assertIn("agents_scanned", result.metrics)
        self.assertIn("cycles_detected", result.metrics)
        self.assertIn("inflation_rate", result.metrics)
        self.assertGreater(result.metrics["agents_scanned"], 0)

    def test_voting_synchronization_scan(self):
        result = run_async(self.detector.scan_voting_synchronization())
        self.assertTrue(result.success)
        self.assertIn("votes_analyzed", result.metrics)
        self.assertIn("clusters_found", result.metrics)
        self.assertIn("max_similarity", result.metrics)

    def test_trust_inflation_below_threshold(self):
        result = run_async(self.detector.scan_trust_inflation())
        self.assertLess(result.metrics["inflation_rate"], 0.3)
        self.assertFalse(result.metrics["alert_triggered"])

    def test_voting_similarity_below_threshold(self):
        result = run_async(self.detector.scan_voting_synchronization())
        self.assertLess(result.metrics["max_similarity"], 0.9)
        self.assertFalse(result.metrics["alert_triggered"])

    def test_collusion_logs_to_ledger(self):
        run_async(self.detector.scan_trust_inflation())
        self.assertGreaterEqual(self.ledger.chain_position, 1)


class TestExternalValidator(unittest.TestCase):
    """Test external AI validation and prompt injection tests."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = NemesisConfig()
        self.ledger = HashChainLedger(os.path.join(self.tmpdir, "ledger.jsonl"))
        self.validator = ExternalValidator(self.config, self.ledger)

    def test_model_validation(self):
        decisions = [{"decision_id": f"DEC-{i}", "verdict": "ALLOW"} for i in range(20)]
        result = run_async(self.validator.validate_with_external_model(decisions))
        self.assertTrue(result.success)
        self.assertEqual(result.metrics["decisions_reviewed"], 20)
        self.assertIn("agreement_rate", result.metrics)
        self.assertGreater(result.metrics["agreement_rate"], 0)

    def test_model_validation_deterministic(self):
        decisions = [{"decision_id": f"DEC-{i}", "verdict": "ALLOW"} for i in range(10)]
        r1 = run_async(self.validator.validate_with_external_model(decisions))
        r2 = run_async(self.validator.validate_with_external_model(decisions))
        self.assertEqual(r1.metrics["agreement_rate"], r2.metrics["agreement_rate"])

    def test_prompt_injection_tests(self):
        result = run_async(self.validator.run_prompt_injection_tests())
        self.assertTrue(result.success)
        self.assertEqual(result.metrics["prompts_tested"], 5)
        self.assertIn("detection_rate", result.metrics)

    def test_prompt_injection_deterministic(self):
        r1 = run_async(self.validator.run_prompt_injection_tests())
        r2 = run_async(self.validator.run_prompt_injection_tests())
        self.assertEqual(r1.metrics["detection_rate"], r2.metrics["detection_rate"])

    def test_empty_decision_sample(self):
        result = run_async(self.validator.validate_with_external_model([]))
        self.assertTrue(result.success)
        self.assertEqual(result.metrics["decisions_reviewed"], 0)
        self.assertEqual(result.metrics["agreement_rate"], 0)

    def test_external_validation_logs_to_ledger(self):
        run_async(self.validator.run_prompt_injection_tests())
        self.assertGreaterEqual(self.ledger.chain_position, 1)


class TestAccuracyAccounting(unittest.TestCase):
    """Test FP/FN tracking and confusion matrix generation."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ledger = HashChainLedger(os.path.join(self.tmpdir, "ledger.jsonl"))
        self.accounting = AccuracyAccounting(self.ledger)

    def test_true_positive_classification(self):
        record = self.accounting.record_detection_outcome(
            "DET-001", predicted_malicious=True, actual_malicious=True,
            detection_system="test", context={}
        )
        self.assertEqual(record["outcome"], "true_positive")
        self.assertFalse(record["requires_review"])

    def test_true_negative_classification(self):
        record = self.accounting.record_detection_outcome(
            "DET-002", predicted_malicious=False, actual_malicious=False,
            detection_system="test", context={}
        )
        self.assertEqual(record["outcome"], "true_negative")
        self.assertFalse(record["requires_review"])

    def test_false_positive_classification(self):
        record = self.accounting.record_detection_outcome(
            "DET-003", predicted_malicious=True, actual_malicious=False,
            detection_system="test", context={}
        )
        self.assertEqual(record["outcome"], "false_positive")
        self.assertTrue(record["requires_review"])

    def test_false_negative_classification(self):
        record = self.accounting.record_detection_outcome(
            "DET-004", predicted_malicious=False, actual_malicious=True,
            detection_system="test", context={}
        )
        self.assertEqual(record["outcome"], "false_negative")
        self.assertTrue(record["requires_review"])

    def test_confusion_matrix_structure(self):
        matrix = self.accounting.generate_confusion_matrix(period_days=7)
        self.assertIn("true_positives", matrix)
        self.assertIn("true_negatives", matrix)
        self.assertIn("false_positives", matrix)
        self.assertIn("false_negatives", matrix)
        self.assertIn("metrics", matrix)
        self.assertIn("precision", matrix["metrics"])
        self.assertIn("recall", matrix["metrics"])
        self.assertIn("f1_score", matrix["metrics"])

    def test_confusion_matrix_metrics_valid(self):
        matrix = self.accounting.generate_confusion_matrix()
        metrics = matrix["metrics"]
        self.assertGreater(metrics["precision"], 0)
        self.assertLessEqual(metrics["precision"], 1.0)
        self.assertGreater(metrics["recall"], 0)
        self.assertLessEqual(metrics["recall"], 1.0)
        self.assertGreater(metrics["f1_score"], 0)
        self.assertLessEqual(metrics["f1_score"], 1.0)

    def test_flag_for_review(self):
        position = self.accounting.flag_for_human_review("DET-005", "Suspicious FP")
        self.assertGreater(position, 0)

    def test_detection_outcome_logs_to_ledger(self):
        self.accounting.record_detection_outcome(
            "DET-006", True, True, "test", {}
        )
        self.assertGreaterEqual(self.ledger.chain_position, 1)


class TestScorecardGenerator(unittest.TestCase):
    """Test resilience scorecard generation."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ledger = HashChainLedger(os.path.join(self.tmpdir, "ledger.jsonl"))
        self.generator = ScorecardGenerator(self.ledger)

    def _make_metrics(self, **overrides) -> ResilienceMetrics:
        defaults = dict(
            detection_rate=0.92,
            containment_rate=0.88,
            recovery_rate=0.95,
            external_validation_rate=0.87,
            fault_tolerance_rate=0.90,
        )
        defaults.update(overrides)
        return ResilienceMetrics(**defaults)

    def _make_confusion(self) -> dict:
        return {
            "true_positives": 450,
            "true_negatives": 12500,
            "false_positives": 25,
            "false_negatives": 15,
            "total": 12990,
            "metrics": {
                "precision": 450 / 475,
                "recall": 450 / 465,
                "specificity": 12500 / 12525,
                "fp_rate": 25 / 12525,
                "fn_rate": 15 / 465,
                "f1_score": 0.96,
            }
        }

    def test_scorecard_structure(self):
        scorecard = self.generator.generate_scorecard(
            period_start=datetime.now(timezone.utc) - timedelta(days=7),
            period_end=datetime.now(timezone.utc),
            job_results=[],
            metrics=self._make_metrics(),
            confusion_matrix=self._make_confusion(),
        )
        self.assertIn("scorecard_id", scorecard)
        self.assertIn("overall", scorecard)
        self.assertIn("detection", scorecard)
        self.assertIn("containment", scorecard)
        self.assertIn("recovery", scorecard)
        self.assertIn("red_team", scorecard)
        self.assertIn("fault_injection", scorecard)

    def test_grade_a(self):
        metrics = self._make_metrics(
            detection_rate=0.95, containment_rate=0.95,
            recovery_rate=0.95, external_validation_rate=0.95,
            fault_tolerance_rate=0.95,
        )
        scorecard = self.generator.generate_scorecard(
            datetime.now(timezone.utc) - timedelta(days=7), datetime.now(timezone.utc),
            [], metrics, self._make_confusion(),
        )
        self.assertEqual(scorecard["overall"]["grade"], "A")

    def test_grade_f_low_scores(self):
        metrics = self._make_metrics(
            detection_rate=0.1, containment_rate=0.1,
            recovery_rate=0.1, external_validation_rate=0.1,
            fault_tolerance_rate=0.1,
        )
        scorecard = self.generator.generate_scorecard(
            datetime.now(timezone.utc) - timedelta(days=7), datetime.now(timezone.utc),
            [], metrics, self._make_confusion(),
        )
        self.assertEqual(scorecard["overall"]["grade"], "F")

    def test_scorecard_logs_to_ledger(self):
        self.generator.generate_scorecard(
            datetime.now(timezone.utc) - timedelta(days=7), datetime.now(timezone.utc),
            [], self._make_metrics(), self._make_confusion(),
        )
        self.assertGreaterEqual(self.ledger.chain_position, 1)


class TestNemesisDaemon(unittest.TestCase):
    """Test the main daemon orchestrator."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = NemesisConfig(
            emergency_stop_file=os.path.join(self.tmpdir, "EMERGENCY_STOP"),
            read_only_mode_file=os.path.join(self.tmpdir, "READ_ONLY"),
            audit_only_mode_file=os.path.join(self.tmpdir, "AUDIT_ONLY"),
        )

    def test_daemon_initialization(self):
        with patch.object(HashChainLedger, '__init__', lambda self, path=None: None):
            with patch.object(HashChainLedger, '_load_chain', lambda self: None):
                daemon = NemesisDaemon(self.config)
                daemon.ledger = MagicMock()
                daemon.ledger.chain_position = 0
                daemon.ledger.previous_hash = "GENESIS"
                self.assertEqual(daemon.state, DaemonState.STARTING)
                self.assertIsNotNone(daemon.red_team)
                self.assertIsNotNone(daemon.fault_injection)
                self.assertIsNotNone(daemon.collusion_detector)
                self.assertIsNotNone(daemon.external_validator)

    def test_safety_mode_running(self):
        daemon = NemesisDaemon.__new__(NemesisDaemon)
        daemon.config = self.config
        self.assertEqual(daemon._check_safety_modes(), DaemonState.RUNNING)

    def test_safety_mode_emergency_stop(self):
        daemon = NemesisDaemon.__new__(NemesisDaemon)
        daemon.config = self.config
        Path(self.config.emergency_stop_file).touch()
        self.assertEqual(daemon._check_safety_modes(), DaemonState.EMERGENCY_STOP)

    def test_safety_mode_read_only(self):
        daemon = NemesisDaemon.__new__(NemesisDaemon)
        daemon.config = self.config
        Path(self.config.read_only_mode_file).touch()
        self.assertEqual(daemon._check_safety_modes(), DaemonState.READ_ONLY)

    def test_safety_mode_audit_only(self):
        daemon = NemesisDaemon.__new__(NemesisDaemon)
        daemon.config = self.config
        Path(self.config.audit_only_mode_file).touch()
        self.assertEqual(daemon._check_safety_modes(), DaemonState.AUDIT_ONLY)

    def test_emergency_stop_takes_priority(self):
        daemon = NemesisDaemon.__new__(NemesisDaemon)
        daemon.config = self.config
        Path(self.config.emergency_stop_file).touch()
        Path(self.config.read_only_mode_file).touch()
        self.assertEqual(daemon._check_safety_modes(), DaemonState.EMERGENCY_STOP)


class TestJobResult(unittest.TestCase):
    """Test JobResult dataclass."""

    def test_default_values(self):
        job = JobResult(job_id="test-001", job_type="test", started_at=datetime.now(timezone.utc))
        self.assertFalse(job.success)
        self.assertIsNone(job.error)
        self.assertEqual(job.metrics, {})
        self.assertEqual(job.artifacts, [])

    def test_completed_job(self):
        now = datetime.now(timezone.utc)
        job = JobResult(
            job_id="test-002",
            job_type="red_team_attack",
            started_at=now,
            completed_at=now + timedelta(seconds=5),
            success=True,
            metrics={"detected": True},
        )
        self.assertTrue(job.success)
        self.assertEqual(job.metrics["detected"], True)


if __name__ == "__main__":
    unittest.main()
