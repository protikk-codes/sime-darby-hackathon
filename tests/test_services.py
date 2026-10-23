import pytest

from data.database import init_db
from data.seed import SAMPLE_ASSETS, SAMPLE_COMPLAINTS, SAMPLE_RECORDS, load_sample, seed_if_empty
from intelligence.analytics import dashboard_metrics
from services import assets as asset_svc
from services import complaints as comp_svc
from services import maintenance as maint_svc
from services.errors import NotFoundError, ValidationError


def valid_asset(**overrides):
    data = {
        "asset_code": "wp-900", "name": "Test main", "asset_type": "Water pipeline",
        "location": "Block Z", "install_year": 2015, "lifespan_years": 40, "condition": "Good",
        "last_inspection": "2026-09-01", "maintenance_interval_days": 180, "notes": "",
    }
    data.update(overrides)
    return data


# ----- asset creation and validation -----

def test_create_asset_normalises_code_and_persists(conn):
    code = asset_svc.create_asset(conn, valid_asset())
    assert code == "WP-900"
    assert asset_svc.get_asset(conn, "WP-900")["name"] == "Test main"


def test_duplicate_asset_code_rejected(conn):
    asset_svc.create_asset(conn, valid_asset())
    with pytest.raises(ValidationError, match="already exists"):
        asset_svc.create_asset(conn, valid_asset())


@pytest.mark.parametrize("override, message", [
    ({"asset_type": "Spaceship"}, "Asset type"),
    ({"condition": "Excellent"}, "Condition"),
    ({"lifespan_years": 0}, "lifespan"),
    ({"install_year": "abc"}, "Installation year"),
    ({"last_inspection": "01/09/2026"}, "Last inspection"),
    ({"asset_code": "bad code!"}, "Asset code"),
    ({"name": ""}, "Name"),
])
def test_invalid_asset_inputs_rejected(conn, override, message):
    with pytest.raises(ValidationError, match=message):
        asset_svc.create_asset(conn, valid_asset(**override))


def test_update_asset_keeps_code_and_changes_fields(conn):
    asset_svc.create_asset(conn, valid_asset())
    asset_svc.update_asset(conn, "WP-900", valid_asset(condition="Poor", name="Renamed"))
    updated = asset_svc.get_asset(conn, "WP-900")
    assert updated["condition"] == "Poor"
    assert updated["name"] == "Renamed"


def test_missing_asset_raises_not_found(conn):
    with pytest.raises(NotFoundError):
        asset_svc.get_asset(conn, "NOPE-1")


def test_search_and_filter_assets(seeded):
    drainage = asset_svc.list_assets(seeded, asset_type="Drainage")
    assert {a["asset_code"] for a in drainage} == {"DR-001", "DR-002"}
    assert len(asset_svc.list_assets(seeded, search="Reservoir")) == 1
    assert all(a["condition"] == "Poor" for a in asset_svc.list_assets(seeded, condition="Poor"))


def test_delete_asset_removes_its_records(seeded):
    before = len(maint_svc.list_records(seeded, "WP-001"))
    assert before == 4
    asset_svc.delete_asset(seeded, "WP-001")
    assert maint_svc.list_records(seeded, "WP-001") == []


# ----- maintenance records -----

def test_add_record_requires_existing_asset(conn):
    with pytest.raises(NotFoundError):
        maint_svc.add_record(conn, {"asset_code": "GHOST", "record_date": "2026-01-01",
                                    "category": "Repair", "description": "x", "cost_rm": 1, "status": "Completed"})


def test_add_record_validates_fields(seeded):
    base = {"asset_code": "WP-002", "record_date": "2026-01-01", "category": "Repair",
            "description": "Leak", "cost_rm": 10, "status": "Completed"}
    with pytest.raises(ValidationError):
        maint_svc.add_record(seeded, {**base, "category": "Magic"})
    with pytest.raises(ValidationError):
        maint_svc.add_record(seeded, {**base, "cost_rm": -5})
    with pytest.raises(ValidationError):
        maint_svc.add_record(seeded, {**base, "record_date": "yesterday"})


def test_records_are_chronological_and_linked(seeded):
    records = maint_svc.list_records(seeded, "WP-001")
    dates = [r["record_date"] for r in records]
    assert dates == sorted(dates)
    assert all(r["asset_code"] == "WP-001" for r in records)


def test_total_cost_by_asset_type(seeded):
    expected = sum(r[4] for r in SAMPLE_RECORDS if r[0] in ("DR-001", "DR-002"))
    assert maint_svc.total_cost(seeded, asset_type="Drainage") == pytest.approx(expected)


# ----- complaints -----

def test_complaint_defaults_to_open_and_links_asset(seeded):
    cid = comp_svc.create_complaint(seeded, {
        "title": "Leak", "location": "Block C", "category": "Water pipeline",
        "urgency": "High", "asset_code": "WP-002",
    })
    complaint = comp_svc.get_complaint(seeded, cid)
    assert complaint["status"] == "Open"
    assert complaint["asset_code"] == "WP-002"


def test_complaint_with_unknown_asset_rejected(conn):
    with pytest.raises(NotFoundError):
        comp_svc.create_complaint(conn, {"title": "x", "location": "y", "category": "Road",
                                         "urgency": "Low", "asset_code": "NOPE"})


def test_status_change_is_logged_to_history(seeded):
    cid = comp_svc.list_complaints(seeded, status="Open")[0]["id"]
    comp_svc.update_complaint(seeded, cid, {"status": "Resolved"}, note="Fixed on site")
    history = comp_svc.complaint_history(seeded, cid)
    assert history[-1]["old_value"] == "Open"
    assert history[-1]["new_value"] == "Resolved"
    assert history[-1]["note"] == "Fixed on site"
    assert comp_svc.get_complaint(seeded, cid)["status"] == "Resolved"


def test_no_change_writes_no_history(seeded):
    cid = comp_svc.list_complaints(seeded)[0]["id"]
    current = comp_svc.get_complaint(seeded, cid)["status"]
    before = len(comp_svc.complaint_history(seeded, cid))
    comp_svc.update_complaint(seeded, cid, {"status": current})
    assert len(comp_svc.complaint_history(seeded, cid)) == before


def test_invalid_status_rejected(seeded):
    cid = comp_svc.list_complaints(seeded)[0]["id"]
    with pytest.raises(ValidationError):
        comp_svc.update_complaint(seeded, cid, {"status": "Done-ish"})


def test_disallowed_field_rejected(seeded):
    cid = comp_svc.list_complaints(seeded)[0]["id"]
    with pytest.raises(ValidationError):
        comp_svc.update_complaint(seeded, cid, {"title": "Hacked"})


def test_list_complaints_filters_by_status(seeded):
    resolved = comp_svc.list_complaints(seeded, status="Resolved")
    assert len(resolved) == 1 and resolved[0]["title"].startswith("Blocked culvert")


# ----- dashboard, seeding and persistence -----

def test_dashboard_metrics_come_from_data(seeded, today):
    m = dashboard_metrics(seeded, today)
    assert m["total_assets"] == len(SAMPLE_ASSETS)
    assert sum(m["by_risk"].values()) == len(SAMPLE_ASSETS)
    assert {r.asset_code for r in m["overdue"]} == {"WP-001", "DR-001", "PM-002"}
    open_count = sum(1 for c in SAMPLE_COMPLAINTS if c[6] in ("Open", "Under review", "Assigned", "In progress"))
    assert m["open_complaints"] == open_count
    assert m["total_spend"] == pytest.approx(sum(r[4] for r in SAMPLE_RECORDS))


def test_seed_if_empty_does_not_overwrite(conn):
    assert seed_if_empty(conn) is True
    asset_svc.create_asset(conn, valid_asset())
    assert seed_if_empty(conn) is False
    assert len(asset_svc.list_assets(conn)) == len(SAMPLE_ASSETS) + 1


def test_data_persists_across_connections(tmp_path, today):
    path = tmp_path / "town.db"
    first = init_db(path)
    load_sample(first, today)
    first.close()
    second = init_db(path)
    assert len(asset_svc.list_assets(second)) == len(SAMPLE_ASSETS)
    second.close()
