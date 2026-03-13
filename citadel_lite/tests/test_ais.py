"""Unit tests for AIS (Agent Intelligence System) — Phase 25."""
import sys
import shutil
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ais.profile import AgentProfile
from src.ais.storage import ProfileStore
from src.ais.rewards import RewardCalculator, RewardEvent
from src.ais.costs import CostTable
from src.ais.engine import AISEngine
from src.ags.caps_stub import CAPSGrade, resolve_caps_grade


# ========== helpers ==========

def _temp_storage():
    """Create a ProfileStore backed by a temporary directory."""
    tmp = Path(tempfile.mkdtemp())
    return ProfileStore(base_path=tmp / "profiles"), tmp


# ========== Profile tests ==========

def test_agent_profile_xp_grade_resolution():
    """XP thresholds determine CAPS grade correctly."""
    p = AgentProfile(agent_id="t", xp=50)
    assert p.grade == CAPSGrade.D

    p.add_xp(100, "task")
    assert p.xp == 150
    assert p.grade == CAPSGrade.C

    p.add_xp(400, "tier2")
    assert p.xp == 550
    assert p.grade == CAPSGrade.B


def test_agent_profile_tp_budget():
    """can_afford enforces TP balance."""
    p = AgentProfile(agent_id="t", xp=1000, tp=100)
    assert p.can_afford(50)
    assert p.can_afford(100)
    assert not p.can_afford(101)

    p.add_tp(-60, "cost")
    assert p.tp == 40
    assert not p.can_afford(50)


def test_agent_profile_xp_floor():
    """XP cannot go below zero."""
    p = AgentProfile(agent_id="t", xp=10)
    p.add_xp(-100, "big_penalty")
    assert p.xp == 0
    assert p.grade == CAPSGrade.D


def test_agent_profile_transaction_log():
    """Transaction log records each mutation."""
    p = AgentProfile(agent_id="t")
    p.add_xp(50, "task_1")
    p.add_tp(20, "critical")
    p.add_xp(-10, "penalty")

    assert len(p.transaction_log) == 3
    assert p.transaction_log[0]["type"] == "xp"
    assert p.transaction_log[0]["amount"] == 50
    assert p.transaction_log[2]["amount"] == -10


def test_agent_profile_caps_conversion():
    """to_caps_profile produces a valid CAPSProfile for AGS."""
    p = AgentProfile(agent_id="sentinel", xp=1500, tp=75)
    caps = p.to_caps_profile()

    assert caps.agent_id == "sentinel"
    assert caps.xp == 1500
    assert caps.tp == 75
    assert caps.grade == CAPSGrade.B
    assert caps.meets_tier(2)
    assert not caps.meets_tier(3)


def test_agent_profile_serialisation_roundtrip():
    """to_dict / from_dict roundtrip preserves all fields."""
    p = AgentProfile(agent_id="rt", xp=2500, tp=80)
    p.add_xp(100, "bonus")
    d = p.to_dict()
    p2 = AgentProfile.from_dict(d)

    assert p2.agent_id == "rt"
    assert p2.xp == p.xp
    assert p2.tp == p.tp
    assert p2.grade == p.grade
    assert len(p2.transaction_log) == len(p.transaction_log)


# ========== Storage tests ==========

def test_profile_store_save_load():
    """Profiles survive a save → fresh-load cycle."""
    store, tmp = _temp_storage()
    try:
        store.save_profile(AgentProfile(agent_id="a1", xp=1000, tp=50))

        # Force cache miss by creating a new store instance on same path
        store2 = ProfileStore(base_path=store.base_path)
        loaded = store2.get_profile("a1")
        assert loaded is not None
        assert loaded.xp == 1000
        assert loaded.grade == CAPSGrade.B
    finally:
        shutil.rmtree(tmp)


def test_profile_store_get_or_create():
    """get_or_create initialises with defaults on first call."""
    store, tmp = _temp_storage()
    try:
        p = store.get_or_create_profile("new_agent")
        assert p.xp == 1000
        assert p.tp == 50

        p2 = store.get_or_create_profile("new_agent")
        assert p2.agent_id == p.agent_id
    finally:
        shutil.rmtree(tmp)


def test_profile_store_list_all():
    """list_all_profiles returns every persisted profile."""
    store, tmp = _temp_storage()
    try:
        store.save_profile(AgentProfile(agent_id="x1", xp=500))
        store.save_profile(AgentProfile(agent_id="x2", xp=1500))
        store.save_profile(AgentProfile(agent_id="x3", xp=3000))

        all_p = store.list_all_profiles()
        assert len(all_p) == 3
        assert "x1" in all_p
        assert all_p["x3"].grade == CAPSGrade.A
    finally:
        shutil.rmtree(tmp)


# ========== Reward tests ==========

def test_reward_base_xp_tier0():
    """Base XP for tier-0 approve is 50."""
    calc = RewardCalculator()
    ev = RewardEvent(
        event_type="ci_failed", outcome="approve", tier=0,
        risk_score=0.15, fix_verified=False, is_critical=False,
    )
    r = calc.calculate_reward(ev)
    # base 50 * 1.0 = 50, penalty -20 (not verified) → 30
    assert r["xp"] == 30


def test_reward_tier_multiplier():
    """Tier-2 multiplier scales XP by 2.5x."""
    calc = RewardCalculator()
    ev = RewardEvent(
        event_type="ci_failed", outcome="approve", tier=2,
        risk_score=0.15, fix_verified=False, is_critical=False,
    )
    r = calc.calculate_reward(ev)
    # base 50 * 2.5 = 125, penalty -20 → 105
    assert r["xp"] == 105


def test_reward_quality_bonus():
    """Verified fixes earn +50% quality bonus."""
    calc = RewardCalculator()
    ev = RewardEvent(
        event_type="ci_failed", outcome="approve", tier=1,
        risk_score=0.10, fix_verified=True, is_critical=False,
    )
    r = calc.calculate_reward(ev)
    # base 50 * 1.5 = 75, quality +37 → 112
    assert r["xp"] == 112


def test_reward_critical_tp():
    """Critical events award TP."""
    calc = RewardCalculator()
    ev = RewardEvent(
        event_type="security_alert", outcome="need_approval", tier=2,
        risk_score=0.35, fix_verified=False, is_critical=True,
    )
    r = calc.calculate_reward(ev)
    assert r["tp"] >= 200  # security_alert = 200 TP


def test_reward_low_risk_tp_bonus():
    """Low risk (< 0.25) approved events earn +20 TP."""
    calc = RewardCalculator()
    ev = RewardEvent(
        event_type="ci_failed", outcome="approve", tier=0,
        risk_score=0.10, fix_verified=True, is_critical=False,
    )
    r = calc.calculate_reward(ev)
    assert r["tp"] >= 20


def test_reward_penalty():
    """calculate_penalty returns negative XP."""
    calc = RewardCalculator()
    r = calc.calculate_penalty("policy_violation")
    assert r["xp"] == -50
    assert r["tp"] == 0


# ========== Cost tests ==========

def test_cost_table_lookup():
    """Known actions return correct costs."""
    c = CostTable.get_cost("approve_fix")
    assert c is not None
    assert c.tp_required == 50
    assert c.xp_cost == 10

    c2 = CostTable.get_cost("deploy")
    assert c2 is not None
    assert c2.tp_required == 90


def test_cost_table_unknown():
    """Unknown action returns None."""
    assert CostTable.get_cost("unknown_xyz") is None


# ========== Engine tests ==========

def test_engine_get_profile():
    """Engine creates a default profile on first access."""
    store, tmp = _temp_storage()
    try:
        engine = AISEngine(storage=store)
        p = engine.get_profile("sentinel")
        assert p.agent_id == "sentinel"
        assert p.xp == 1000
        assert p.grade == CAPSGrade.B
    finally:
        shutil.rmtree(tmp)


def test_engine_budget_check():
    """Budget check respects TP balance."""
    store, tmp = _temp_storage()
    try:
        engine = AISEngine(storage=store)
        p = engine.get_profile("t")
        p.tp = 60
        store.save_profile(p)

        ok, _ = engine.check_budget(p, "approve_fix")
        assert ok  # 60 >= 50

        ok2, _ = engine.check_budget(p, "deploy")
        assert not ok2  # 60 < 90
    finally:
        shutil.rmtree(tmp)


def test_engine_record_reward_manual():
    """Manual XP/TP grant updates profile."""
    store, tmp = _temp_storage()
    try:
        engine = AISEngine(storage=store)
        engine.record_reward("t", xp=100, tp=50, reason="manual")

        p = engine.get_profile("t")
        assert p.xp == 1100  # 1000 + 100
        assert p.tp == 100   # 50 + 50
    finally:
        shutil.rmtree(tmp)


def test_engine_record_reward_event():
    """Event-based reward calculates and applies correctly."""
    store, tmp = _temp_storage()
    try:
        engine = AISEngine(storage=store)
        ev = RewardEvent(
            event_type="deploy_failed", outcome="approve", tier=2,
            risk_score=0.15, fix_verified=True, is_critical=True,
        )
        result = engine.record_reward("t", event=ev)
        assert result["xp"] > 0
        assert result["tp"] > 0

        p = engine.get_profile("t")
        assert p.xp > 1000
        assert p.tp > 50
    finally:
        shutil.rmtree(tmp)


def test_engine_caps_profile_integration():
    """get_caps_profile returns real grade from AIS data."""
    store, tmp = _temp_storage()
    try:
        engine = AISEngine(storage=store)
        p = engine.get_profile("adv")
        p.add_xp(2000, "promote_to_A")  # 1000 + 2000 = 3000 → A-grade
        store.save_profile(p)

        caps = engine.get_caps_profile("adv")
        assert caps.grade == CAPSGrade.A
        assert caps.meets_tier(3)
    finally:
        shutil.rmtree(tmp)


def test_engine_spend_tp():
    """spend_tp deducts TP and rejects insufficient balances."""
    store, tmp = _temp_storage()
    try:
        engine = AISEngine(storage=store)
        p = engine.get_profile("s")  # 50 TP default

        assert engine.spend_tp("s", 30, "action")
        p2 = engine.get_profile("s")
        assert p2.tp == 20

        assert not engine.spend_tp("s", 25, "too_much")
    finally:
        shutil.rmtree(tmp)


def test_engine_fail_open():
    """Engine falls back to stub when storage is broken."""
    store, tmp = _temp_storage()
    engine = AISEngine(storage=store)
    # Destroy storage
    shutil.rmtree(tmp)

    caps = engine.get_caps_profile("any")
    assert caps.grade == CAPSGrade.B
    assert caps.xp == 1000


# ========== Integration test ==========

def test_full_reward_cycle():
    """Complete cycle: check budget → record reward → grade progression."""
    store, tmp = _temp_storage()
    try:
        engine = AISEngine(storage=store)
        agent = "cycle_agent"

        p = engine.get_profile(agent)
        initial_xp = p.xp

        # Budget check
        ok, _ = engine.check_budget(p, "approve_fix")
        assert ok

        # Simulate task completion
        ev = RewardEvent(
            event_type="ci_failed", outcome="approve", tier=2,
            risk_score=0.15, fix_verified=True, is_critical=False,
        )
        engine.record_reward(agent, event=ev)

        p2 = engine.get_profile(agent)
        assert p2.xp > initial_xp
        assert len(p2.transaction_log) > 0
    finally:
        shutil.rmtree(tmp)
