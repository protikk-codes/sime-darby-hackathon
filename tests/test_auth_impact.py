import pytest

import config as cfg
from data.seed import SAMPLE_RECORDS
from intelligence.impact import impact_summary
from services import auth
from services.errors import ValidationError


def test_no_pin_until_set(conn):
    assert auth.pin_is_set(conn) is False
    assert auth.verify_staff_pin(conn, "anything") is False


def test_pin_verifies_and_rejects_wrong_value(conn):
    auth.set_staff_pin(conn, "township-2026")
    assert auth.pin_is_set(conn)
    assert auth.verify_staff_pin(conn, "township-2026")
    assert not auth.verify_staff_pin(conn, "township-2025")
    assert not auth.verify_staff_pin(conn, "")


def test_pin_is_stored_hashed_not_plain(conn):
    auth.set_staff_pin(conn, "township-2026")
    stored = conn.execute("SELECT value FROM app_settings WHERE key='staff_pin'").fetchone()["value"]
    assert "township-2026" not in stored
    assert ":" in stored


def test_short_pin_rejected(conn):
    with pytest.raises(ValidationError):
        auth.set_staff_pin(conn, "123")
    assert auth.pin_is_set(conn) is False


def test_changing_pin_replaces_old_one(conn):
    auth.set_staff_pin(conn, "first-pin-1")
    auth.set_staff_pin(conn, "second-pin-2")
    assert auth.verify_staff_pin(conn, "second-pin-2")
    assert not auth.verify_staff_pin(conn, "first-pin-1")


def test_impact_numbers_come_from_records(seeded, today):
    s = impact_summary(seeded, today)
    # WP-001 (3 repairs) and RD-001 (2 repairs) are the recurring-defect assets in the sample data
    expected_spend = sum(r[4] for r in SAMPLE_RECORDS if r[2] == "Repair" and r[0] in ("WP-001", "RD-001"))
    assert s["recurring_defect_assets"] == 2
    assert s["repeat_repair_spend_rm"] == pytest.approx(expected_spend)
    share = cfg.IMPACT_ASSUMPTIONS["avoidable_repeat_repair_share"]
    assert s["estimated_avoidable_spend_rm"] == pytest.approx(expected_spend * share)
    assert s["overdue_inspections"] == 3
    assert s["open_complaints"] == 6
    assert s["assumptions"], "estimates must always list their assumptions"


def test_impact_on_empty_database(conn, today):
    s = impact_summary(conn, today)
    assert s["total_assets"] == 0
    assert s["repeat_repair_spend_rm"] == 0
    assert s["avg_open_complaint_days"] == 0
