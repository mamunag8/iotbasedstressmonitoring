"""
Comprehensive Automated Tests for the Isolated Mobile-First PhD Field, Instrument AI,
Lab/Harvest, Batch/Single Treatment, HOBO Climate Logger & Professor A4 Print App (/data-app).
"""

import base64
import io
import os
import sys
import tempfile

import openpyxl
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "cloud_backend")))

_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db.name}"

from app import database as db
from app import field_data_ai as fai
from app import field_data_db as fdb
from app.main import app

PIN_HEADERS = {"X-Operator-Pin": "atauniiot"}


@pytest.fixture(autouse=True)
def isolated_field_db(tmp_path, monkeypatch):
    test_db = tmp_path / "field_app_test.db"
    photo_dir = tmp_path / "field_photos"
    photo_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(db, "DATABASE_URL", f"sqlite:///{test_db}")
    monkeypatch.setattr(fai, "get_photo_storage_root", lambda: str(photo_dir))
    db.init_db()
    fdb.init_field_data_db()
    yield


def test_data_app_page_and_pin_security():
    client = TestClient(app)
    r_page = client.get("/data-app")
    assert r_page.status_code == 200
    assert "PhD Field &amp; Lab Data" in r_page.text

    r_man = client.get("/data-app/manifest.json")
    assert r_man.status_code == 200
    assert r_man.json()["short_name"] == "PhD Data"

    # Unauthenticated write must be rejected with 403
    r_unauth = client.post(
        "/api/v1/field-data/measurements",
        json={
            "fertigation_arm": "IoT",
            "treatment_no": "T1",
            "replicate_no": "R1",
            "plant_no": "P1",
            "parameter_key": "plant_height_cm",
            "manual_value": 42.5,
        },
    )
    assert r_unauth.status_code == 403


def test_dual_column_manual_and_ai_measurements_edit_and_summary():
    client = TestClient(app)

    # 1. Save manual morphology measurements across IoT & Manual arms
    for rep, h_val in [("R1", 40.0), ("R2", 42.0), ("R3", 44.0), ("R4", 46.0)]:
        resp = client.post(
            "/api/v1/field-data/measurements",
            headers=PIN_HEADERS,
            json={
                "experiment_code": "EXP2",
                "measured_at": "2026-11-16T10:00:00Z",
                "fertigation_arm": "IoT",
                "treatment_no": "T1",
                "replicate_no": rep,
                "plant_no": "P1",
                "parameter_key": "plant_height_cm",
                "manual_value": h_val,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["record"]["final_value"] == h_val

    # 2. Save Porometer reading with BOTH AI value and Manual confirmation in separate columns
    r_poro = client.post(
        "/api/v1/field-data/measurements",
        headers=PIN_HEADERS,
        json={
            "experiment_code": "EXP2",
            "measured_at": "2026-11-16T12:30:00Z",
            "fertigation_arm": "IoT",
            "treatment_no": "T6",
            "replicate_no": "R2",
            "plant_no": "P1",
            "parameter_key": "stomatal_conductance_gs",
            "manual_value": 168.4,
            "ai_value": 168.4,
            "ai_secondary_value": 168.4,
            "verification_status": "dual_ai_consensus",
            "ai_confidence": 0.99,
            "ai_model": "google/gemini-2.5-flash + openai/gpt-4o-mini",
            "notes": "Midday abaxial leaf 3",
        },
    )
    assert r_poro.status_code == 200
    poro_rec = r_poro.json()["record"]
    assert poro_rec["manual_value"] == 168.4
    assert poro_rec["ai_value"] == 168.4
    assert poro_rec["final_value"] == 168.4
    assert poro_rec["entry_mode"] == "manual_plus_ai"
    assert poro_rec["plc_zone_id"] == 6
    assert poro_rec["plc_sensor_id"] == 14  # (2 - 1)*8 + 6 = 14

    # 3. Inline edit & verify edit_history_json preserves previous value
    rec_id = poro_rec["record_id"]
    r_edit = client.put(
        f"/api/v1/field-data/measurements/{rec_id}",
        headers=PIN_HEADERS,
        json={"manual_value": 168.5, "final_value": 168.5, "notes": "Verified LCD decimal"},
    )
    assert r_edit.status_code == 200
    edited = r_edit.json()["record"]
    assert edited["final_value"] == 168.5
    assert len(edited["edit_history"]) == 1
    assert edited["edit_history"][0]["prev_final_value"] == 168.4

    # 4. Query summary statistics
    r_list = client.get("/api/v1/field-data/measurements?experiment_code=EXP2")
    assert r_list.status_code == 200
    summary = r_list.json()["summary"]
    assert summary["total_records"] == 5
    t1_height = [s for s in summary["summary_rows"] if s["parameter_key"] == "plant_height_cm" and s["treatment_no"] == "T1"][0]
    assert t1_height["n"] == 4
    assert t1_height["mean"] == 43.0


def test_dual_ai_vision_consensus_and_mismatch_detection(monkeypatch):
    client = TestClient(app)

    # Save API key via PIN-protected endpoint
    r_cfg = client.post(
        "/api/v1/field-data/ai-settings",
        headers=PIN_HEADERS,
        json={
            "provider": "openrouter",
            "openrouter_api_key": "sk-or-v1-testkey1234567890",
            "primary_model": "google/gemini-2.5-flash",
            "secondary_model": "openai/gpt-4o-mini",
            "dual_verify_enabled": True,
        },
    )
    assert r_cfg.status_code == 200
    assert r_cfg.json()["ai_settings"]["has_openrouter_key"] is True
    assert "testkey" not in r_cfg.json()["ai_settings"]["openrouter_key_masked"]

    # Fake 1x1 PNG
    tiny_png = base64.b64encode(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
    ).decode("ascii")

    # Case A: Both models agree -> dual_ai_consensus
    async def mock_agree(api_key, model, b64_str, mime_type, prompt):
        return {
            "primary_value": 25.4,
            "detected_unit": "C",
            "confidence": 0.98,
            "unreadable": False,
            "extra_fields": {"stomatal_conductance_gs": 210.5, "porometer_leaf_temp_c": 25.4},
            "_model_used": model,
        }

    monkeypatch.setattr(fai, "_call_openrouter_vision", mock_agree)
    r_ok = client.post(
        "/api/v1/field-data/ai-read",
        headers=PIN_HEADERS,
        json={"image_base64": f"data:image/png;base64,{tiny_png}", "parameter_key": "porometer_leaf_temp_c"},
    )
    assert r_ok.status_code == 200
    d_ok = r_ok.json()
    assert d_ok["verification_status"] == "dual_ai_consensus"
    assert d_ok["consensus_matched"] is True
    assert d_ok["ai_value"] == 25.4

    # Verify saved photo is served properly
    r_photo = client.get(d_ok["photo_url"])
    assert r_photo.status_code == 200

    # Case B: Models disagree (16.1 vs 18.1 LCD 6/8 glare) -> flagged_mismatch!
    async def mock_disagree(api_key, model, b64_str, mime_type, prompt):
        val = 16.1 if "gemini" in model else 18.1
        return {
            "primary_value": val,
            "detected_unit": "mmol/m2/s",
            "confidence": 0.85,
            "unreadable": False,
            "extra_fields": {},
            "_model_used": model,
        }

    monkeypatch.setattr(fai, "_call_openrouter_vision", mock_disagree)
    r_mis = client.post(
        "/api/v1/field-data/ai-read",
        headers=PIN_HEADERS,
        json={"image_base64": tiny_png, "parameter_key": "stomatal_conductance_gs"},
    )
    assert r_mis.status_code == 200
    d_mis = r_mis.json()
    assert d_mis["verification_status"] == "flagged_mismatch"
    assert d_mis["consensus_matched"] is False
    assert d_mis["ai_value"] == 16.1
    assert d_mis["ai_secondary_value"] == 18.1


def test_group_treatment_logging_hobo_upload_and_excel_export():
    client = TestClient(app)

    # 1. Group Treatment Application across all 32 H2S planters (IoT + Manual x T2,T4,T6,T8 x R1..R4)
    r_trt = client.post(
        "/api/v1/field-data/treatments",
        headers=PIN_HEADERS,
        json={
            "experiment_code": "EXP2",
            "applied_at": "2026-11-16T09:45:00Z",
            "target_arms": ["IoT", "Manual"],
            "target_treatments": ["T2", "T4", "T6", "T8"],
            "target_replicates": ["R1", "R2", "R3", "R4"],
            "application_type": "nahs_humic_pulse",
            "nahs_um": 25.0,
            "nahs_stock_mg_100ml": 80.09,
            "humic_mll": 4.0,
            "volume_per_planter_l": 1.0,
            "solution_ec_uscm": 2350,
            "solution_ph": 6.02,
            "hours_after_morning_irrig": 2.5,
            "notes": "Delivered within 20 min",
        },
    )
    assert r_trt.status_code == 200
    assert r_trt.json()["treatment"]["affected_planters_count"] == 32

    # Verify mirrored into existing Stress Studio treatment_applications for IoT zones 2,4,6,8
    stress_trts = client.get("/api/v1/stress/treatments").json()["treatments"]
    assert len(stress_trts) == 4

    # 2. HOBO CSV Upload (with HOBO plot header row + Temp C + RH % + Lux -> auto VPD)
    hobo_csv = (
        "Plot Title: Sera 5 IoT Half\n"
        "#,Date Time,Temp °C,RH %,Intensity Lux\n"
        "1,11/16/26 12:00:00 PM,26.0,55.0,18500\n"
        "2,11/16/26 12:05:00 PM,26.5,53.0,19200\n"
    ).encode("utf-8")

    r_hobo = client.post(
        "/api/v1/field-data/climate/upload?filename=hobo_sera5.csv&logger_type=generic_climate&location_tag=IoT_Half",
        headers=PIN_HEADERS,
        content=hobo_csv,
    )
    assert r_hobo.status_code == 200
    assert r_hobo.json()["rows_inserted"] == 2

    # Re-uploading same file skips duplicates
    r_hobo_dup = client.post(
        "/api/v1/field-data/climate/upload?filename=hobo_sera5.csv&logger_type=generic_climate&location_tag=IoT_Half",
        headers=PIN_HEADERS,
        content=hobo_csv,
    )
    assert r_hobo_dup.json()["rows_inserted"] == 0
    assert r_hobo_dup.json()["rows_skipped_duplicate"] == 2

    c_sum = client.get("/api/v1/field-data/climate/summary").json()
    assert c_sum["location_stats"][0]["mean_vpd_kpa"] > 1.0

    # 3. Add a measurement and verify 5-sheet Excel export
    client.post(
        "/api/v1/field-data/measurements",
        headers=PIN_HEADERS,
        json={
            "fertigation_arm": "Manual",
            "treatment_no": "T8",
            "replicate_no": "R3",
            "plant_no": "P2",
            "parameter_key": "shoot_fw_g",
            "manual_value": 184.55,
            "ai_value": 184.55,
        },
    )
    r_xlsx = client.get("/api/v1/field-data/export/excel?experiment_code=EXP2")
    assert r_xlsx.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(r_xlsx.content))
    assert wb.sheetnames == [
        "Tidy_Measurements",
        "ANOVA_Wide_By_Planter",
        "Summary_Mean_SE",
        "Treatments_Log",
        "HOBO_Climate_Data",
    ]


def test_exp2_64_plot_field_layout_and_walk_controls():
    client = TestClient(app)

    cat = client.get("/api/v1/field-data/catalog").json()
    layout = cat["exp2_field_layout"]
    assert len(layout) == 64

    # Every (arm, rep, treatment) combination is unique (32 IoT + 32 Manual)
    keys = {(p["arm"], p["rep"], p["treatment"]) for p in layout}
    assert len(keys) == 64
    assert len([p for p in layout if p["arm"] == "IoT"]) == 32
    assert len([p for p in layout if p["arm"] == "Manual"]) == 32

    # Every (col, rep) coordinate is unique across Cols 1..16 x R1..R4
    coords = {(p["col"], p["rep"]) for p in layout}
    assert len(coords) == 64

    # Verify exact boundary plots from Sera 5 64-plot randomization poster
    lookup = {(p["col"], p["rep"]): p["treatment"] for p in layout}
    assert (lookup[(1, "R1")], lookup[(4, "R1")], lookup[(5, "R1")], lookup[(8, "R1")]) == ("T1", "T3", "T5", "T7")
    assert (lookup[(1, "R4")], lookup[(4, "R4")], lookup[(5, "R4")], lookup[(8, "R4")]) == ("T3", "T1", "T5", "T6")
    assert (lookup[(9, "R1")], lookup[(12, "R1")], lookup[(13, "R1")], lookup[(16, "R1")]) == ("T7", "T5", "T3", "T1")
    assert (lookup[(9, "R4")], lookup[(12, "R4")], lookup[(13, "R4")], lookup[(16, "R4")]) == ("T6", "T5", "T1", "T3")

    # Verify /data-app contains the interactive 64-plot field map & walk sequence logic
    html = client.get("/data-app").text
    assert "fieldMapSection" in html
    assert "buildWalkSequence" in html
    assert "computeNextTargetObj" in html
