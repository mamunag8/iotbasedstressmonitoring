"""
Automated Unit & Integration Tests for:
1. GMTCNT GLC-196R Modbus Register Map & IEEE-754 Float Decoder (R1..R24, R1_L..R24_L, vana1..vana8)
2. Offline-First Local SQLite Store-and-Forward Queue (LocalEdgeSyncQueue)
3. FastAPI Cloud Backend Idempotent Sync, Remote Valve Control, and Multi-Sheet Excel (.xlsx) Export
"""

import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "cloud_backend")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "edge_agent")))

# Use isolated temporary SQLite database for tests
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db.name}"

from app import database as db
from app.main import app
from app.plc_map import EC_REGISTERS, SALT_REGISTERS, SENSORS, ZONES
from local_buffer_sync import LocalEdgeSyncQueue
from plc_modbus_client import GLC196RModbusDriver, decode_ieee754_float, encode_ieee754_float


@pytest.fixture(autouse=True)
def setup_test_db():
    db.init_db()
    yield


def test_hardware_register_map_matches_plc_csv():
    """Verify exact register addresses from PLC(196R).gpf.csv."""
    assert len(SENSORS) == 24
    assert len(ZONES) == 8

    # Check R1..R24 float register stride (2001..2191)
    assert SENSORS[1]["humidity_reg"] == 2001
    assert SENSORS[1]["temp_reg"] == 2003
    assert SENSORS[1]["leaf_humidity_reg"] == 2005
    assert SENSORS[1]["leaf_temp_reg"] == 2007

    assert SENSORS[24]["humidity_reg"] == 2185
    assert SENSORS[24]["temp_reg"] == 2187
    assert SENSORS[24]["leaf_humidity_reg"] == 2189
    assert SENSORS[24]["leaf_temp_reg"] == 2191

    # Check non-sequential EC and Salt registers from CSV
    assert EC_REGISTERS[1] == 3 and SALT_REGISTERS[1] == 4
    assert EC_REGISTERS[3] == 81 and SALT_REGISTERS[3] == 37
    assert EC_REGISTERS[14] == 91 and EC_REGISTERS[15] == 92
    assert EC_REGISTERS[24] == 82 and SALT_REGISTERS[24] == 38

    # Check vana6=7 and vana7=6 coil mapping from CSV & remapped physical solenoid relays
    assert ZONES[6]["valve_tag"] == "vana6" and ZONES[6]["valve_coil"] == 7
    assert ZONES[7]["valve_tag"] == "vana7" and ZONES[7]["valve_coil"] == 6
    assert [ZONES[z]["relay_tag"] for z in range(1, 9)] == ["dc1", "dc2", "dc14", "dc13", "dc3", "dc4", "dc5", "dc6"]
    assert [ZONES[z]["valve_manual_coil"] for z in range(1, 9)] == [9, 10, 11, 12, 13, 14, 15, 16]
    assert ZONES[1]["sensor_ids"] == [1, 9, 17]
    assert ZONES[8]["sensor_ids"] == [8, 16, 24]


def test_ieee754_float_roundtrip():
    """Verify 32-bit IEEE-754 float encoding/decoding in GLC-196R little-endian word order."""
    for sample in [0.0, 24.65, 48.0, 67.32, 90.0, -5.25]:
        low, high = encode_ieee754_float(sample, little_endian_word_order=True)
        decoded = decode_ieee754_float(low, high, little_endian_word_order=True)
        assert abs(decoded - sample) < 0.02


def test_offline_queue_and_idempotent_cloud_sync():
    """
    Simulate:
    1. Internet is disconnected -> Edge Agent collects 5 snapshots into local SQLite queue.
    2. Internet reconnects -> All 5 snapshots sync to Cloud API idempotently.
    3. Re-sending the same snapshots results in 0 duplicates.
    4. Remote valve command from mobile app is queued and returned on sync.
    """
    q_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    q_file.close()
    queue = LocalEdgeSyncQueue(db_path=q_file.name)
    driver = GLC196RModbusDriver(plc_ip="127.0.0.1", plc_port=59999, allow_simulation_fallback=True)

    for i in range(5):
        snap = driver.poll_snapshot()
        snap["batch_id"] = f"test_hw_batch_{i}"
        snap["plc_online"] = True
        snap["source"] = "plc_hardware_196r"
        queue.enqueue(snap)

    counts = queue.queue_counts()
    assert counts["unsynced"] == 5
    assert counts["synced"] == 0

    client = TestClient(app)

    # Queue a remote valve command from Mobile App while PLC is offline
    cmd_res = client.post(
        "/api/v1/control/valve",
        json={"zone_id": 6, "valve_open": True, "auto_mode": False, "requested_by": "flutter_mobile"},
    )
    assert cmd_res.status_code == 200
    cmd_data = cmd_res.json()["command"]
    assert cmd_data["valve_tag"] == "vana6"
    assert cmd_data["valve_coil"] == 7

    # Now sync the 5 offline-buffered batches to Cloud API
    unsynced = queue.get_unsynced(limit=100)
    sync_res = client.post(
        "/api/v1/telemetry/sync",
        json={"device_id": "ziraat_plc_196r", "batches": unsynced},
    )
    assert sync_res.status_code == 200
    body = sync_res.json()
    assert body["inserted_batches"] == 5
    assert body["skipped_duplicates"] == 0
    assert len(body["pending_commands"]) >= 1

    # Mark synced locally
    queue.mark_synced([b["batch_id"] for b in unsynced])
    assert queue.queue_counts()["unsynced"] == 0
    assert queue.queue_counts()["synced"] == 5

    # Re-sending same batches must be 100% idempotent (0 duplicates inserted)
    dup_res = client.post(
        "/api/v1/telemetry/sync",
        json={"device_id": "ziraat_plc_196r", "batches": unsynced},
    )
    assert dup_res.json()["inserted_batches"] == 0
    assert dup_res.json()["skipped_duplicates"] == 5

    # Verify Excel & CSV exports for PhD analysis
    excel_res = client.get("/api/v1/export/excel")
    assert excel_res.status_code == 200
    assert len(excel_res.content) > 2000

    csv_res = client.get("/api/v1/export/csv")
    assert csv_res.status_code == 200
    assert "Bölge 1" in csv_res.text
