from datetime import date

import pytest

import config as cfg
from data.seed import SAMPLE_RECORDS
from intelligence.assistant import FALLBACK, TownshipAssistant
from intelligence.risk import assess_all, assess_asset, level_for_score


def make_asset(**overrides):
    asset = {
        "asset_code": "T-1", "name": "Test asset", "asset_type": "Road", "location": "Here",
        "install_year": 2020, "lifespan_years": 40, "condition": "Good",
        "last_inspection": "2026-10-09", "maintenance_interval_days": 365,
    }
    asset.update(overrides)
    return asset


def repair(date_str):
    return {"category": "Repair", "record_date": date_str}


# ----- risk engine -----

def test_young_good_asset_is_low_risk(today):
    result = assess_asset(make_asset(install_year=2024), [], today)
    assert result.level == "Low"
    assert result.overdue is False
    assert result.repair_count == 0


def test_old_poor_overdue_asset_scores_high(today):
    asset = make_asset(install_year=1985, lifespan_years=30, condition="Poor",
                       last_inspection="2025-01-01", maintenance_interval_days=90)
    result = assess_asset(asset, [], today)
    assert result.overdue is True
    assert result.score >= cfg.RISK_LEVEL_THRESHOLDS[1][1]
    assert result.level in ("High", "Critical")
    assert any("overdue" in reason for reason in result.reasons)


def test_critical_when_all_factors_present(today):
    asset = make_asset(install_year=1950, lifespan_years=20, condition="Poor",
                       last_inspection="2025-01-01", maintenance_interval_days=90)
    records = [repair("2026-01-10"), repair("2026-06-10")]
    result = assess_asset(asset, records, today)
    assert result.score == 95
    assert result.level == "Critical"


def test_every_reason_is_explained(today):
    result = assess_asset(make_asset(condition="Fair", install_year=1990, lifespan_years=30), [], today)
    assert result.reasons, "a risk result must always carry reasons"
    assert all(isinstance(r, str) and r for r in result.reasons)


def test_repeated_repairs_detected_within_window(today):
    records = [repair("2026-08-01"), repair("2026-03-01")]
    result = assess_asset(make_asset(), records, today)
    assert result.repair_count == 2
    assert any("repairs in the last" in r for r in result.reasons)


def test_repairs_outside_window_are_ignored(today):
    records = [repair("2024-01-01"), repair("2026-08-01")]
    result = assess_asset(make_asset(), records, today)
    assert result.repair_count == 1


def test_future_dated_repairs_are_ignored(today):
    records = [repair("2026-08-01"), repair("2027-01-01")]
    assert assess_asset(make_asset(), records, today).repair_count == 1


def test_upcoming_inspection_is_reported_not_overdue(today):
    asset = make_asset(last_inspection="2026-09-25", maintenance_interval_days=30)  # due 2026-10-25
    result = assess_asset(asset, [], today)
    assert result.overdue is False
    assert result.days_to_due == 6
    assert any("due in 6 days" in r for r in result.reasons)


@pytest.mark.parametrize("score, level", [(0, "Low"), (24, "Low"), (25, "Medium"),
                                          (49, "Medium"), (50, "High"), (75, "Critical"), (100, "Critical")])
def test_level_thresholds(score, level):
    assert level_for_score(score) == level


def test_assess_all_sorted_by_score(seeded, today):
    results = assess_all(seeded, today)
    assert len(results) == 12
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_sample_repeated_repairs_flagged(seeded, today):
    flagged = {r.asset_code for r in assess_all(seeded, today) if r.repair_count >= cfg.REPEAT_MIN_REPAIRS}
    assert flagged == {"WP-001", "RD-001"}


# ----- assistant -----

def ask(conn, today, question):
    return TownshipAssistant(conn, today=today).ask(question)


def test_due_question_names_real_overdue_assets(seeded, today):
    result = ask(seeded, today, "Which assets need maintenance soon?")
    assert "WP-001" in result["answer"]
    assert "DR-001" in result["answer"]
    assert "WP-001" in " ".join(result["sources"])


def test_repeated_repairs_question(seeded, today):
    result = ask(seeded, today, "Which assets have repeated repairs?")
    assert "WP-001" in result["answer"]
    assert "2026-09-09" in result["answer"]  # WP-001 repair 40 days before the fixed test date
    assert "RD-001" in result["answer"]


def test_spend_question_uses_real_totals(seeded, today):
    result = ask(seeded, today, "How much has been spent on drainage maintenance?")
    expected = sum(r[4] for r in SAMPLE_RECORDS if r[0].startswith("DR-"))
    assert f"RM {expected:,.2f}" in result["answer"]
    assert "4 maintenance records" in result["answer"]


def test_complaints_question_lists_oldest_open_first(seeded, today):
    answer = ask(seeded, today, "Which complaints have remained open the longest?")["answer"]
    assert answer.index("Drain overflow") < answer.index("Low water pressure")
    assert "Blocked culvert" not in answer  # resolved, so not open


def test_risk_question_gives_reasons(seeded, today):
    result = ask(seeded, today, "What are the highest-risk assets and why?")
    assert "/100" in result["answer"]
    assert "Reasons:" in result["answer"]
    assert "not trained predictions" in result["answer"]


def test_priorities_question(seeded, today):
    answer = ask(seeded, today, "What should management prioritise this month?")["answer"]
    assert "overdue inspections" in answer
    assert "urgent open complaints" in answer.lower() or "Triage" in answer


def test_unknown_question_gets_honest_fallback(seeded, today):
    result = ask(seeded, today, "What is the weather on Mars?")
    assert result["answer"] == FALLBACK
    assert result["sources"] == []


def test_empty_question_is_handled(seeded, today):
    assert "Please type" in ask(seeded, today, "   ")["answer"]


def test_engine_label_states_no_language_model(seeded, today):
    result = ask(seeded, today, "Which complaints have remained open the longest?")
    assert "no language model" in result["engine"].lower()


def test_provider_can_rephrase_but_grounding_stays(seeded, today):
    class Stub:
        name = "stub provider"

        def rephrase(self, question, grounded_answer):
            return "REWRITTEN: " + grounded_answer

    result = TownshipAssistant(seeded, today=today, provider=Stub()).ask("Which assets have repeated repairs?")
    assert result["answer"].startswith("REWRITTEN: ")
    assert "WP-001" in result["answer"]
    assert result["engine"] == "stub provider"


def test_broken_provider_falls_back_to_grounded_answer(seeded, today):
    class Broken:
        name = "broken"

        def rephrase(self, question, grounded_answer):
            raise RuntimeError("network down")

    result = TownshipAssistant(seeded, today=today, provider=Broken()).ask("Which assets have repeated repairs?")
    assert "WP-001" in result["answer"]
