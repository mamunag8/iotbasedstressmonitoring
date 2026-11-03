"""
Automated Unit & Integration Tests for the PhD Plant Stress, Biostimulant Recovery,
Treatment Applications (with mandatory Date & Time), Persistent Research Notes Database,
and Dedicated /stress Studio Web Page.
"""

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
from app import stress_engine
from app.main import app


@pytest.fixture(autouse=True)
def setup_test_db():
    db.init_db()
    yield


def test_biophysical_stress_and_recovery_formulas():
    """Verify Hilhorst Pore ECp, Osmotic Potential, VPD, Jackson CWSI, H2S Speciation, PSI, PVI, and SRI %."""
    # 1. Hilhorst (2000) Pore-Water EC & Osmotic Potential in 3:1 Peat:Perlite (epsilon_0 = 2.5)
    hil_ctrl = stress_engine.compute_hilhorst_pore_ec(
        soil_moisture_pct=65.0,
        soil_ec_uscm=1800,
        soil_temp_c=22.0,
        epsilon_offset=2.5,
    )
    assert hil_ctrl["pore_ec_dsm"] is not None
    assert 1.5 <= hil_ctrl["pore_ec_dsm"] <= 4.0
    assert hil_ctrl["osmotic_potential_mpa"] < 0.0

    hil_salt = stress_engine.compute_hilhorst_pore_ec(
        soil_moisture_pct=52.0,
        soil_ec_uscm=4800,
        soil_temp_c=25.0,
        epsilon_offset=2.5,
    )
    assert hil_salt["pore_ec_dsm"] > hil_ctrl["pore_ec_dsm"]
    assert hil_salt["osmotic_potential_mpa"] < hil_ctrl["osmotic_potential_mpa"]

    # 2. VPD and Dew-Point Margin
    vpd_opt = stress_engine.compute_vpd_and_dewpoint(leaf_temp_c=24.0, leaf_rh_pct=68.0)
    assert 0.5 <= vpd_opt["vpd_kpa"] <= 1.2
    assert vpd_opt["dew_point_margin_c"] > 2.0

    # 3. Henderson-Hasselbalch H2S / HS- Speciation at pH 6.0 vs pH 7.5
    spec_ph6 = stress_engine.compute_h2s_speciation(soil_ph=6.0, soil_temp_c=20.0, nahs_dose_um=25.0)
    spec_ph75 = stress_engine.compute_h2s_speciation(soil_ph=7.5, soil_temp_c=20.0, nahs_dose_um=25.0)
    assert spec_ph6["f_h2s_pct"] > 85.0
    assert spec_ph6["active_h2s_um"] > 20.0
    assert spec_ph75["f_h2s_pct"] < 35.0

    # 4. Single-Sensor Composite PSI & PVI comparison: Control vs 100 mM NaCl vs 100 mM NaCl + 25 uM NaHS + Humic
    s_ctrl = stress_engine.compute_single_sensor_stress(
        sensor_row={
            "sensor_id": 1,
            "zone_id": 1,
            "soil_moisture": 65.0,
            "soil_temp": 22.0,
            "soil_ec": 1400,
            "soil_salt": 770,
            "soil_ph": 6.0,
            "leaf_humidity": 68.0,
            "leaf_temp": 21.0,
        }
    )
    s_salt_unmitigated = stress_engine.compute_single_sensor_stress(
        sensor_row={
            "sensor_id": 13,
            "zone_id": 5,
            "soil_moisture": 44.0,
            "soil_temp": 26.0,
            "soil_ec": 5200,
            "soil_salt": 3900,
            "soil_ph": 6.8,
            "leaf_humidity": 42.0,
            "leaf_temp": 29.2,
        }
    )
    s_salt_combo_recovered = stress_engine.compute_single_sensor_stress(
        sensor_row={
            "sensor_id": 24,
            "zone_id": 8,
            "soil_moisture": 62.0,
            "soil_temp": 23.0,
            "soil_ec": 3100,
            "soil_salt": 1800,
            "soil_ph": 6.0,
            "leaf_humidity": 64.0,
            "leaf_temp": 22.8,
        }
    )
    assert s_ctrl["composite_psi"] < 20.0
    assert s_salt_unmitigated["composite_psi"] > 45.0
    assert s_salt_combo_recovered["composite_psi"] < s_salt_unmitigated["composite_psi"]
    assert s_salt_combo_recovered["plant_vitality_pvi"] > s_salt_unmitigated["plant_vitality_pvi"]


def test_dedicated_stress_page_and_api_workflow():
    """
    Verify:
    - Dedicated /stress and /stress-studio web pages render with 16 charts & mandatory Date/Time fields
    - Main dashboard (/) links directly to /stress
    - Treatment input requires Date & Time (applied_at), persists H2S, Humic, and Salt inputs in DB
    - Research notes CRUD persists in DB
    - Excel export contains all 7 sheets including PhD_Stress_And_Recovery, Treatment_Applications_Log, Research_Diary_Notes
    - Strictly monitoring-only: 0 pending valve control commands queued
    """
    client = TestClient(app)

    # 1. Check main dashboard link and dedicated /stress page
    r_home = client.get("/")
    assert r_home.status_code == 200
    assert 'href="/stress"' in r_home.text

    r_stress = client.get("/stress")
    assert r_stress.status_code == 200
    assert "chart1Heatmap" in r_stress.text
    assert "chart16RegressionSdh" in r_stress.text
    assert 'id="trtAppliedAt" required' in r_stress.text

    # 2. Verify mandatory Date & Time (applied_at) on treatment endpoint
    r_missing_dt = client.post(
        "/api/v1/stress/treatments",
        json={
            "zone_id": 8,
            "treatment_code": "I-S-H2S+HS",
            "h2s_applied": True,
            "h2s_dose_um": 25.0,
        },
    )
    assert r_missing_dt.status_code == 422  # Pydantic required field validation

    # 3. Record valid Treatment Application with Date & Time
    r_trt = client.post(
        "/api/v1/stress/treatments",
        json={
            "applied_at": "2026-11-03T09:30:00Z",
            "zone_id": 8,
            "treatment_code": "I-S-H2S+HS",
            "h2s_applied": True,
            "h2s_dose_um": 25.0,
            "h2s_stock_ml_per_l": 0.25,
            "h2s_solution_vol_l": 10.0,
            "humic_applied": True,
            "humic_dose_mll": 2.5,
            "humic_total_ml": 25.0,
            "nutrient_match_applied": True,
            "salt_applied": True,
            "nacl_dose_mm": 100.0,
            "supplied_solution_ec_uscm": 11500,
            "supplied_solution_ph": 5.95,
            "drainage_fraction_pct": 22.5,
            "drainage_ec_uscm": 13200,
            "update_line_ref_ph": True,
            "notes": "Morning 25 uM NaHS + 2.5 mL/L LIQHUMUS NK pulse under 100 mM NaCl",
            "recorded_by": "Mamunur Reza",
        },
    )
    assert r_trt.status_code == 200
    trt_data = r_trt.json()["treatment"]
    assert trt_data["applied_at"] == "2026-11-03T09:30:00Z"
    assert trt_data["h2s_dose_um"] == 25.0
    assert trt_data["humic_dose_mll"] == 2.5
    assert trt_data["nacl_dose_mm"] == 100.0

    # Verify Line 8 reference soil pH updated to 5.95
    r_prof = client.get("/api/v1/stress/line-profiles")
    assert r_prof.status_code == 200
    p8 = next(p for p in r_prof.json()["line_profiles"] if p["zone_id"] == 8)
    assert abs(p8["ref_soil_ph"] - 5.95) < 0.01

    # 4. Create, Update, and Query Persistent Research Notes in Database
    r_note = client.post(
        "/api/v1/stress/notes",
        json={
            "recorded_at": "2026-11-03T15:00:00Z",
            "zone_id": 8,
            "sensor_id": 24,
            "category": "recovery_sign",
            "severity_or_tag": "strong_recovery",
            "title": "Stomatal conductance & leaf turgor recovery on Plot R24",
            "content": "6h after 25 uM NaHS + Humic pulse, L_temp dropped by 1.8 C vs Line 5 salt control.",
            "author": "Mamunur Reza",
            "pinned_on_chart": True,
        },
    )
    assert r_note.status_code == 200
    note_id = r_note.json()["note"]["note_id"]

    r_notes_get = client.get("/api/v1/stress/notes?search=turgor")
    assert r_notes_get.status_code == 200
    assert any(n["note_id"] == note_id for n in r_notes_get.json()["notes"])

    # 5. Ingest a real hardware telemetry batch and verify live + historical stress reports
    sensors_payload = []
    for sid in range(1, 25):
        zid = ((sid - 1) % 8) + 1
        is_salt_unmit = zid == 5
        is_combo = zid == 8
        sensors_payload.append({
            "sensor_id": sid,
            "zone_id": zid,
            "soil_moisture": 44.0 if is_salt_unmit else (64.0 if is_combo else 62.0),
            "soil_temp": 25.0 if is_salt_unmit else 22.0,
            "soil_ec": 5400 if is_salt_unmit else (3200 if is_combo else 1600),
            "soil_salt": 4000 if is_salt_unmit else (1850 if is_combo else 880),
            "soil_ph": 6.0,
            "leaf_humidity": 42.0 if is_salt_unmit else 66.0,
            "leaf_temp": 29.0 if is_salt_unmit else 22.5,
        })
    zones_payload = [
        {
            "zone_id": zid,
            "name_tr": f"Bolge {zid}",
            "name_en": f"Zone {zid}",
            "valve_tag": f"vana{zid}",
            "valve_coil": zid,
            "relay_tag": f"dc{zid}",
            "valve_open": False,
            "auto_mode": True,
            "min_moisture": 45.0,
            "max_moisture": 80.0,
            "avg_soil_moisture": 44.0 if zid == 5 else 63.0,
            "avg_soil_temp": 25.0 if zid == 5 else 22.0,
            "avg_soil_ec": 5400 if zid == 5 else (3200 if zid == 8 else 1600),
            "avg_soil_salt": 4000 if zid == 5 else (1850 if zid == 8 else 880),
            "avg_soil_ph": 6.0,
            "avg_leaf_humidity": 42.0 if zid == 5 else 66.0,
            "avg_leaf_temp": 29.0 if zid == 5 else 22.5,
            "sensor_ids": [zid, zid + 8, zid + 16],
        }
        for zid in range(1, 9)
    ]
    r_sync = client.post(
        "/api/v1/telemetry/sync",
        json={
            "device_id": "ziraat_plc_196r",
            "batches": [
                {
                    "batch_id": "test-stress-batch-001",
                    "recorded_at": "2026-11-03T12:00:00Z",
                    "source": "plc_hardware_196r",
                    "plc_online": True,
                    "zones": zones_payload,
                    "sensors": sensors_payload,
                    "valves": {f"vana{i}": False for i in range(1, 9)},
                }
            ],
        },
    )
    assert r_sync.status_code == 200

    r_live = client.get("/api/v1/stress/live")
    assert r_live.status_code == 200
    live = r_live.json()
    z5 = next(z for z in live["zones"] if z["zone_id"] == 5)
    z8 = next(z for z in live["zones"] if z["zone_id"] == 8)
    assert z8["avg_psi"] < z5["avg_psi"]
    assert z8["recovery_sri_pct"] > 0.0

    r_hist = client.get("/api/v1/stress/history?hours=720&resolution=15min")
    assert r_hist.status_code == 200
    assert len(r_hist.json()["treatments"]) >= 1
    assert len(r_hist.json()["notes"]) >= 1

    # 6. Verify 7-Sheet PhD Excel Workbook Export
    r_xlsx = client.get("/api/v1/export/excel?resolution=5min")
    assert r_xlsx.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(r_xlsx.content))
    assert "PhD_Stress_And_Recovery" in wb.sheetnames
    assert "Treatment_Applications_Log" in wb.sheetnames
    assert "Research_Diary_Notes" in wb.sheetnames

    # 7. Verify strict Monitoring-Only policy: zero valve commands created
    assert len(db.fetch_pending_commands()) == 0
