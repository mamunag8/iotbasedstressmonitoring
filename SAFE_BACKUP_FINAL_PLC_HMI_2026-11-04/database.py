"""
Database layer for Ziraat Fakultesi Otomatik Sulama Sistemi Cloud Backend.
Supports PostgreSQL 16 (production on Hetzner Coolify VPS) and SQLite (Edge PC / standalone).
Strict Zero-Demo Policy: Purges any simulated/demo rows and stores only authentic PLC hardware telemetry
(or explicit unit test batches when allow_simulated=True).
Includes full support for:
- Soil Sensors R1..R24 (RS485 Slave IDs 1..24): Moisture, Temp, EC, Salinity, and Soil pH
- Leaf Sensors R1_L..R24_L (RS485 Slave IDs 101..124): Leaf Humidity (L_humidity) and Leaf Temperature (L_temp)
"""

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .plc_map import SENSORS, ZONES
from .stress_engine import (
    DEFAULT_CALIBRATION,
    DEFAULT_LINE_PROFILES,
    compute_days_after_transplant,
)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/irrigation_cloud.db")
IS_POSTGRES = DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")

if IS_POSTGRES:
    import psycopg2
    import psycopg2.extras


def get_sqlite_path() -> str:
    path = DATABASE_URL.replace("sqlite:///", "")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    return path


@contextmanager
def get_conn():
    if IS_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(get_sqlite_path(), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def init_db() -> None:
    """Create all tables, migrate soil_ph column if needed, and seed default 8-zone configurations."""
    with get_conn() as conn:
        cur = conn.cursor()
        if IS_POSTGRES:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS telemetry_batches (
                    batch_id TEXT PRIMARY KEY,
                    recorded_at TEXT UNIQUE NOT NULL,
                    received_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    plc_online INTEGER NOT NULL DEFAULT 1,
                    zones_json TEXT NOT NULL,
                    sensors_json TEXT NOT NULL,
                    valves_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_batches_recorded_at ON telemetry_batches(recorded_at DESC);

                CREATE TABLE IF NOT EXISTS sensor_readings (
                    id SERIAL PRIMARY KEY,
                    recorded_at TEXT NOT NULL,
                    sensor_id INTEGER NOT NULL,
                    zone_id INTEGER NOT NULL,
                    soil_moisture REAL,
                    soil_temp REAL,
                    soil_ec INTEGER,
                    soil_salt INTEGER,
                    soil_ph REAL,
                    leaf_humidity REAL,
                    leaf_temp REAL,
                    UNIQUE(recorded_at, sensor_id)
                );
                CREATE INDEX IF NOT EXISTS idx_sensor_time ON sensor_readings(recorded_at DESC, zone_id);
                ALTER TABLE sensor_readings ADD COLUMN IF NOT EXISTS soil_ph REAL;

                CREATE TABLE IF NOT EXISTS zone_configs (
                    zone_id INTEGER PRIMARY KEY,
                    name_tr TEXT NOT NULL,
                    name_en TEXT NOT NULL,
                    valve_tag TEXT NOT NULL,
                    valve_coil INTEGER NOT NULL,
                    relay_tag TEXT NOT NULL,
                    auto_mode INTEGER NOT NULL DEFAULT 1,
                    manual_valve_state INTEGER NOT NULL DEFAULT 0,
                    min_moisture REAL NOT NULL DEFAULT 45.0,
                    max_moisture REAL NOT NULL DEFAULT 80.0,
                    nominal_flow_lpm REAL NOT NULL DEFAULT 0.5333,
                    total_water_liters REAL NOT NULL DEFAULT 0.0,
                    total_open_seconds REAL NOT NULL DEFAULT 0.0,
                    flow_meter_connected INTEGER NOT NULL DEFAULT 0,
                    last_valve_open_at TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS pending_commands (
                    cmd_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    zone_id INTEGER NOT NULL,
                    command_type TEXT NOT NULL,
                    valve_tag TEXT NOT NULL,
                    valve_coil INTEGER NOT NULL,
                    target_state INTEGER,
                    auto_mode INTEGER,
                    min_moisture REAL,
                    max_moisture REAL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    executed_at TEXT,
                    requested_by TEXT NOT NULL DEFAULT 'mobile_app'
                );

                CREATE TABLE IF NOT EXISTS valve_events (
                    event_id TEXT PRIMARY KEY,
                    recorded_at TEXT NOT NULL,
                    zone_id INTEGER NOT NULL,
                    valve_tag TEXT NOT NULL,
                    state INTEGER NOT NULL,
                    trigger_source TEXT NOT NULL,
                    zone_moisture REAL
                );

                CREATE TABLE IF NOT EXISTS alarm_events (
                    alarm_id TEXT PRIMARY KEY,
                    recorded_at TEXT NOT NULL,
                    zone_id INTEGER,
                    sensor_id INTEGER,
                    severity TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    acknowledged INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS system_settings (
                    setting_id INTEGER PRIMARY KEY,
                    save_interval_sec INTEGER NOT NULL DEFAULT 60,
                    default_min_moisture REAL NOT NULL DEFAULT 45.0,
                    default_max_moisture REAL NOT NULL DEFAULT 80.0,
                    global_auto_mode INTEGER NOT NULL DEFAULT 1,
                    high_ec_alarm_threshold INTEGER NOT NULL DEFAULT 2500,
                    low_moisture_alarm_threshold REAL NOT NULL DEFAULT 35.0,
                    high_temp_alarm_threshold REAL NOT NULL DEFAULT 35.0,
                    auto_sync_plc_clock INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL
                );
                ALTER TABLE zone_configs ADD COLUMN IF NOT EXISTS nominal_flow_lpm REAL NOT NULL DEFAULT 2.0;
                ALTER TABLE zone_configs ADD COLUMN IF NOT EXISTS total_water_liters REAL NOT NULL DEFAULT 0.0;
                ALTER TABLE zone_configs ADD COLUMN IF NOT EXISTS total_open_seconds REAL NOT NULL DEFAULT 0.0;
                ALTER TABLE zone_configs ADD COLUMN IF NOT EXISTS flow_meter_connected INTEGER NOT NULL DEFAULT 0;
                ALTER TABLE zone_configs ADD COLUMN IF NOT EXISTS last_valve_open_at TEXT;

                CREATE TABLE IF NOT EXISTS line_treatment_profiles (
                    zone_id INTEGER PRIMARY KEY,
                    treatment_code TEXT NOT NULL,
                    salinity_regime TEXT NOT NULL,
                    nacl_mm REAL NOT NULL DEFAULT 0.0,
                    target_solution_ec_uscm INTEGER NOT NULL DEFAULT 2000,
                    nahs_dose_um REAL NOT NULL DEFAULT 0.0,
                    humic_dose_mll REAL NOT NULL DEFAULT 0.0,
                    nutrient_matched INTEGER NOT NULL DEFAULT 1,
                    ref_soil_ph REAL NOT NULL DEFAULT 6.0,
                    notes TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS treatment_applications (
                    app_id TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL,
                    dat INTEGER,
                    zone_id INTEGER,
                    sensor_id INTEGER,
                    target_scope TEXT NOT NULL DEFAULT 'zone',
                    treatment_code TEXT NOT NULL,
                    h2s_applied INTEGER NOT NULL DEFAULT 0,
                    h2s_dose_um REAL NOT NULL DEFAULT 0.0,
                    h2s_stock_ml_per_l REAL NOT NULL DEFAULT 0.0,
                    h2s_solution_vol_l REAL NOT NULL DEFAULT 0.0,
                    measured_dripper_h2s_um REAL,
                    humic_applied INTEGER NOT NULL DEFAULT 0,
                    humic_product TEXT NOT NULL DEFAULT 'LIQHUMUS Liquid 18 (NK)',
                    humic_dose_mll REAL NOT NULL DEFAULT 0.0,
                    humic_total_ml REAL NOT NULL DEFAULT 0.0,
                    nutrient_match_applied INTEGER NOT NULL DEFAULT 1,
                    salt_applied INTEGER NOT NULL DEFAULT 0,
                    nacl_dose_mm REAL NOT NULL DEFAULT 0.0,
                    salt_amount_g_per_l REAL NOT NULL DEFAULT 0.0,
                    supplied_solution_ec_uscm INTEGER,
                    supplied_solution_ph REAL,
                    drainage_fraction_pct REAL,
                    drainage_ec_uscm INTEGER,
                    drainage_ph REAL,
                    notes TEXT,
                    recorded_by TEXT NOT NULL DEFAULT 'Mamunur Reza'
                );
                CREATE INDEX IF NOT EXISTS idx_treatment_applied_at ON treatment_applications(applied_at DESC);

                CREATE TABLE IF NOT EXISTS research_notes (
                    note_id TEXT PRIMARY KEY,
                    recorded_at TEXT NOT NULL,
                    dat INTEGER,
                    zone_id INTEGER,
                    sensor_id INTEGER,
                    treatment_code TEXT,
                    category TEXT NOT NULL DEFAULT 'observation',
                    severity_or_tag TEXT NOT NULL DEFAULT 'normal',
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    author TEXT NOT NULL DEFAULT 'Mamunur Reza',
                    pinned_on_chart INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_notes_recorded_at ON research_notes(recorded_at DESC);

                CREATE TABLE IF NOT EXISTS stress_calibration_settings (
                    id INTEGER PRIMARY KEY,
                    substrate_name TEXT NOT NULL DEFAULT '3:1 Peat : Perlite (v/v)',
                    hilhorst_epsilon_offset REAL NOT NULL DEFAULT 2.5,
                    container_capacity_pct REAL NOT NULL DEFAULT 78.0,
                    wilting_point_pct REAL NOT NULL DEFAULT 30.0,
                    optimal_vwc_min_pct REAL NOT NULL DEFAULT 50.0,
                    optimal_vwc_max_pct REAL NOT NULL DEFAULT 78.0,
                    maas_hoffman_threshold_dsm REAL NOT NULL DEFAULT 2.5,
                    maas_hoffman_slope_pct_per_dsm REAL NOT NULL DEFAULT 9.9,
                    optimal_ph_min REAL NOT NULL DEFAULT 5.5,
                    optimal_ph_max REAL NOT NULL DEFAULT 6.5,
                    cwsi_ll_intercept REAL NOT NULL DEFAULT -1.8,
                    cwsi_ll_slope REAL NOT NULL DEFAULT -1.35,
                    cwsi_ul_degc REAL NOT NULL DEFAULT 3.5,
                    leaf_outlier_delta_c REAL NOT NULL DEFAULT 2.0,
                    transplant_date TEXT NOT NULL DEFAULT '2026-10-16',
                    updated_at TEXT NOT NULL
                );
            """)
        else:
            cur.executescript("""
                CREATE TABLE IF NOT EXISTS telemetry_batches (
                    batch_id TEXT PRIMARY KEY,
                    recorded_at TEXT UNIQUE NOT NULL,
                    received_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    plc_online INTEGER NOT NULL DEFAULT 1,
                    zones_json TEXT NOT NULL,
                    sensors_json TEXT NOT NULL,
                    valves_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_batches_recorded_at ON telemetry_batches(recorded_at DESC);

                CREATE TABLE IF NOT EXISTS sensor_readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorded_at TEXT NOT NULL,
                    sensor_id INTEGER NOT NULL,
                    zone_id INTEGER NOT NULL,
                    soil_moisture REAL,
                    soil_temp REAL,
                    soil_ec INTEGER,
                    soil_salt INTEGER,
                    soil_ph REAL,
                    leaf_humidity REAL,
                    leaf_temp REAL,
                    UNIQUE(recorded_at, sensor_id)
                );
                CREATE INDEX IF NOT EXISTS idx_sensor_time ON sensor_readings(recorded_at DESC, zone_id);

                CREATE TABLE IF NOT EXISTS zone_configs (
                    zone_id INTEGER PRIMARY KEY,
                    name_tr TEXT NOT NULL,
                    name_en TEXT NOT NULL,
                    valve_tag TEXT NOT NULL,
                    valve_coil INTEGER NOT NULL,
                    relay_tag TEXT NOT NULL,
                    auto_mode INTEGER NOT NULL DEFAULT 1,
                    manual_valve_state INTEGER NOT NULL DEFAULT 0,
                    min_moisture REAL NOT NULL DEFAULT 45.0,
                    max_moisture REAL NOT NULL DEFAULT 80.0,
                    nominal_flow_lpm REAL NOT NULL DEFAULT 0.5333,
                    total_water_liters REAL NOT NULL DEFAULT 0.0,
                    total_open_seconds REAL NOT NULL DEFAULT 0.0,
                    flow_meter_connected INTEGER NOT NULL DEFAULT 0,
                    last_valve_open_at TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS pending_commands (
                    cmd_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    zone_id INTEGER NOT NULL,
                    command_type TEXT NOT NULL,
                    valve_tag TEXT NOT NULL,
                    valve_coil INTEGER NOT NULL,
                    target_state INTEGER,
                    auto_mode INTEGER,
                    min_moisture REAL,
                    max_moisture REAL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    executed_at TEXT,
                    requested_by TEXT NOT NULL DEFAULT 'mobile_app'
                );

                CREATE TABLE IF NOT EXISTS valve_events (
                    event_id TEXT PRIMARY KEY,
                    recorded_at TEXT NOT NULL,
                    zone_id INTEGER NOT NULL,
                    valve_tag TEXT NOT NULL,
                    state INTEGER NOT NULL,
                    trigger_source TEXT NOT NULL,
                    zone_moisture REAL
                );

                CREATE TABLE IF NOT EXISTS alarm_events (
                    alarm_id TEXT PRIMARY KEY,
                    recorded_at TEXT NOT NULL,
                    zone_id INTEGER,
                    sensor_id INTEGER,
                    severity TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    acknowledged INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS system_settings (
                    setting_id INTEGER PRIMARY KEY,
                    save_interval_sec INTEGER NOT NULL DEFAULT 60,
                    default_min_moisture REAL NOT NULL DEFAULT 45.0,
                    default_max_moisture REAL NOT NULL DEFAULT 80.0,
                    global_auto_mode INTEGER NOT NULL DEFAULT 1,
                    high_ec_alarm_threshold INTEGER NOT NULL DEFAULT 2500,
                    low_moisture_alarm_threshold REAL NOT NULL DEFAULT 35.0,
                    high_temp_alarm_threshold REAL NOT NULL DEFAULT 35.0,
                    auto_sync_plc_clock INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS line_treatment_profiles (
                    zone_id INTEGER PRIMARY KEY,
                    treatment_code TEXT NOT NULL,
                    salinity_regime TEXT NOT NULL,
                    nacl_mm REAL NOT NULL DEFAULT 0.0,
                    target_solution_ec_uscm INTEGER NOT NULL DEFAULT 2000,
                    nahs_dose_um REAL NOT NULL DEFAULT 0.0,
                    humic_dose_mll REAL NOT NULL DEFAULT 0.0,
                    nutrient_matched INTEGER NOT NULL DEFAULT 1,
                    ref_soil_ph REAL NOT NULL DEFAULT 6.0,
                    notes TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS treatment_applications (
                    app_id TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL,
                    dat INTEGER,
                    zone_id INTEGER,
                    sensor_id INTEGER,
                    target_scope TEXT NOT NULL DEFAULT 'zone',
                    treatment_code TEXT NOT NULL,
                    h2s_applied INTEGER NOT NULL DEFAULT 0,
                    h2s_dose_um REAL NOT NULL DEFAULT 0.0,
                    h2s_stock_ml_per_l REAL NOT NULL DEFAULT 0.0,
                    h2s_solution_vol_l REAL NOT NULL DEFAULT 0.0,
                    measured_dripper_h2s_um REAL,
                    humic_applied INTEGER NOT NULL DEFAULT 0,
                    humic_product TEXT NOT NULL DEFAULT 'LIQHUMUS Liquid 18 (NK)',
                    humic_dose_mll REAL NOT NULL DEFAULT 0.0,
                    humic_total_ml REAL NOT NULL DEFAULT 0.0,
                    nutrient_match_applied INTEGER NOT NULL DEFAULT 1,
                    salt_applied INTEGER NOT NULL DEFAULT 0,
                    nacl_dose_mm REAL NOT NULL DEFAULT 0.0,
                    salt_amount_g_per_l REAL NOT NULL DEFAULT 0.0,
                    supplied_solution_ec_uscm INTEGER,
                    supplied_solution_ph REAL,
                    drainage_fraction_pct REAL,
                    drainage_ec_uscm INTEGER,
                    drainage_ph REAL,
                    notes TEXT,
                    recorded_by TEXT NOT NULL DEFAULT 'Mamunur Reza'
                );
                CREATE INDEX IF NOT EXISTS idx_treatment_applied_at ON treatment_applications(applied_at DESC);

                CREATE TABLE IF NOT EXISTS research_notes (
                    note_id TEXT PRIMARY KEY,
                    recorded_at TEXT NOT NULL,
                    dat INTEGER,
                    zone_id INTEGER,
                    sensor_id INTEGER,
                    treatment_code TEXT,
                    category TEXT NOT NULL DEFAULT 'observation',
                    severity_or_tag TEXT NOT NULL DEFAULT 'normal',
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    author TEXT NOT NULL DEFAULT 'Mamunur Reza',
                    pinned_on_chart INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_notes_recorded_at ON research_notes(recorded_at DESC);

                CREATE TABLE IF NOT EXISTS stress_calibration_settings (
                    id INTEGER PRIMARY KEY,
                    substrate_name TEXT NOT NULL DEFAULT '3:1 Peat : Perlite (v/v)',
                    hilhorst_epsilon_offset REAL NOT NULL DEFAULT 2.5,
                    container_capacity_pct REAL NOT NULL DEFAULT 78.0,
                    wilting_point_pct REAL NOT NULL DEFAULT 30.0,
                    optimal_vwc_min_pct REAL NOT NULL DEFAULT 50.0,
                    optimal_vwc_max_pct REAL NOT NULL DEFAULT 78.0,
                    maas_hoffman_threshold_dsm REAL NOT NULL DEFAULT 2.5,
                    maas_hoffman_slope_pct_per_dsm REAL NOT NULL DEFAULT 9.9,
                    optimal_ph_min REAL NOT NULL DEFAULT 5.5,
                    optimal_ph_max REAL NOT NULL DEFAULT 6.5,
                    cwsi_ll_intercept REAL NOT NULL DEFAULT -1.8,
                    cwsi_ll_slope REAL NOT NULL DEFAULT -1.35,
                    cwsi_ul_degc REAL NOT NULL DEFAULT 3.5,
                    leaf_outlier_delta_c REAL NOT NULL DEFAULT 2.0,
                    transplant_date TEXT NOT NULL DEFAULT '2026-10-16',
                    updated_at TEXT NOT NULL
                );
            """)
            try:
                cur.execute("ALTER TABLE sensor_readings ADD COLUMN soil_ph REAL")
            except Exception:
                pass
            for col_sql in (
                "ALTER TABLE zone_configs ADD COLUMN nominal_flow_lpm REAL NOT NULL DEFAULT 2.0",
                "ALTER TABLE zone_configs ADD COLUMN total_water_liters REAL NOT NULL DEFAULT 0.0",
                "ALTER TABLE zone_configs ADD COLUMN total_open_seconds REAL NOT NULL DEFAULT 0.0",
                "ALTER TABLE zone_configs ADD COLUMN flow_meter_connected INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE zone_configs ADD COLUMN last_valve_open_at TEXT",
            ):
                try:
                    cur.execute(col_sql)
                except Exception:
                    pass

        now_iso = datetime.now(timezone.utc).isoformat()
        for zid, zdef in ZONES.items():
            if IS_POSTGRES:
                cur.execute("""
                    INSERT INTO zone_configs (
                        zone_id, name_tr, name_en, valve_tag, valve_coil, relay_tag,
                        auto_mode, manual_valve_state, min_moisture, max_moisture, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, 1, 0, %s, %s, %s)
                    ON CONFLICT (zone_id) DO NOTHING
                """, (
                    zid, zdef["name_tr"], zdef["name_en"], zdef["valve_tag"],
                    zdef["valve_coil"], zdef["relay_tag"],
                    zdef["default_min_moisture"], zdef["default_max_moisture"], now_iso
                ))
            else:
                cur.execute("""
                    INSERT OR IGNORE INTO zone_configs (
                        zone_id, name_tr, name_en, valve_tag, valve_coil, relay_tag,
                        auto_mode, manual_valve_state, min_moisture, max_moisture, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, 0, ?, ?, ?)
                """, (
                    zid, zdef["name_tr"], zdef["name_en"], zdef["valve_tag"],
                    zdef["valve_coil"], zdef["relay_tag"],
                    zdef["default_min_moisture"], zdef["default_max_moisture"], now_iso
                ))
            # Always keep relay_tag, valve_coil, and zone names synced with ZONES physical valve mapping
            _exec(
                cur,
                "UPDATE zone_configs SET relay_tag = ?, valve_coil = ?, valve_tag = ?, name_tr = ?, name_en = ? WHERE zone_id = ?",
                (zdef["relay_tag"], zdef["valve_coil"], zdef["valve_tag"], zdef["name_tr"], zdef["name_en"], zid),
            )
        _exec(
            cur,
            "UPDATE zone_configs SET min_moisture = 45.0, max_moisture = 80.0 WHERE min_moisture = 48.0 AND max_moisture = 90.0",
        )
        _exec(
            cur,
            "UPDATE zone_configs SET auto_mode = 1 WHERE auto_mode = 0 AND manual_valve_state = 0",
        )
        _exec(
            cur,
            "UPDATE zone_configs SET nominal_flow_lpm = 0.5333, total_water_liters = ROUND(CAST((total_open_seconds / 3600.0) * 32.0 AS NUMERIC), 3) WHERE nominal_flow_lpm IN (2.0, 4.0)" if IS_POSTGRES else "UPDATE zone_configs SET nominal_flow_lpm = 0.5333, total_water_liters = ROUND((total_open_seconds / 3600.0) * 32.0, 3) WHERE nominal_flow_lpm IN (2.0, 4.0)",
        )
        if IS_POSTGRES:
            cur.execute("""
                INSERT INTO system_settings (
                    setting_id, save_interval_sec, default_min_moisture, default_max_moisture,
                    global_auto_mode, high_ec_alarm_threshold, low_moisture_alarm_threshold,
                    high_temp_alarm_threshold, auto_sync_plc_clock, updated_at
                ) VALUES (1, 60, 45.0, 80.0, 1, 2500, 35.0, 35.0, 1, %s)
                ON CONFLICT (setting_id) DO NOTHING
            """, (now_iso,))
        else:
            cur.execute("""
                INSERT OR IGNORE INTO system_settings (
                    setting_id, save_interval_sec, default_min_moisture, default_max_moisture,
                    global_auto_mode, high_ec_alarm_threshold, low_moisture_alarm_threshold,
                    high_temp_alarm_threshold, auto_sync_plc_clock, updated_at
                ) VALUES (1, 60, 45.0, 80.0, 1, 2500, 35.0, 35.0, 1, ?)
            """, (now_iso,))

        # Seed default 8-line PhD treatment profiles (Zones 1..8)
        for zid, pdef in DEFAULT_LINE_PROFILES.items():
            if IS_POSTGRES:
                cur.execute("""
                    INSERT INTO line_treatment_profiles (
                        zone_id, treatment_code, salinity_regime, nacl_mm,
                        target_solution_ec_uscm, nahs_dose_um, humic_dose_mll,
                        nutrient_matched, ref_soil_ph, notes, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (zone_id) DO NOTHING
                """, (
                    zid,
                    pdef["treatment_code"],
                    pdef["salinity_regime"],
                    pdef["nacl_mm"],
                    pdef["target_solution_ec_uscm"],
                    pdef["nahs_dose_um"],
                    pdef["humic_dose_mll"],
                    1 if pdef["nutrient_matched"] else 0,
                    pdef["ref_soil_ph"],
                    pdef["notes"],
                    now_iso,
                ))
            else:
                cur.execute("""
                    INSERT OR IGNORE INTO line_treatment_profiles (
                        zone_id, treatment_code, salinity_regime, nacl_mm,
                        target_solution_ec_uscm, nahs_dose_um, humic_dose_mll,
                        nutrient_matched, ref_soil_ph, notes, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    zid,
                    pdef["treatment_code"],
                    pdef["salinity_regime"],
                    pdef["nacl_mm"],
                    pdef["target_solution_ec_uscm"],
                    pdef["nahs_dose_um"],
                    pdef["humic_dose_mll"],
                    1 if pdef["nutrient_matched"] else 0,
                    pdef["ref_soil_ph"],
                    pdef["notes"],
                    now_iso,
                ))

        # Seed default stress calibration settings (id = 1)
        cdef = DEFAULT_CALIBRATION
        if IS_POSTGRES:
            cur.execute("""
                INSERT INTO stress_calibration_settings (
                    id, substrate_name, hilhorst_epsilon_offset, container_capacity_pct,
                    wilting_point_pct, optimal_vwc_min_pct, optimal_vwc_max_pct,
                    maas_hoffman_threshold_dsm, maas_hoffman_slope_pct_per_dsm,
                    optimal_ph_min, optimal_ph_max, cwsi_ll_intercept, cwsi_ll_slope,
                    cwsi_ul_degc, leaf_outlier_delta_c, transplant_date, updated_at
                ) VALUES (1, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, (
                cdef["substrate_name"],
                cdef["hilhorst_epsilon_offset"],
                cdef["container_capacity_pct"],
                cdef["wilting_point_pct"],
                cdef["optimal_vwc_min_pct"],
                cdef["optimal_vwc_max_pct"],
                cdef["maas_hoffman_threshold_dsm"],
                cdef["maas_hoffman_slope_pct_per_dsm"],
                cdef["optimal_ph_min"],
                cdef["optimal_ph_max"],
                cdef["cwsi_ll_intercept"],
                cdef["cwsi_ll_slope"],
                cdef["cwsi_ul_degc"],
                cdef["leaf_outlier_delta_c"],
                cdef["transplant_date"],
                now_iso,
            ))
        else:
            cur.execute("""
                INSERT OR IGNORE INTO stress_calibration_settings (
                    id, substrate_name, hilhorst_epsilon_offset, container_capacity_pct,
                    wilting_point_pct, optimal_vwc_min_pct, optimal_vwc_max_pct,
                    maas_hoffman_threshold_dsm, maas_hoffman_slope_pct_per_dsm,
                    optimal_ph_min, optimal_ph_max, cwsi_ll_intercept, cwsi_ll_slope,
                    cwsi_ul_degc, leaf_outlier_delta_c, transplant_date, updated_at
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cdef["substrate_name"],
                cdef["hilhorst_epsilon_offset"],
                cdef["container_capacity_pct"],
                cdef["wilting_point_pct"],
                cdef["optimal_vwc_min_pct"],
                cdef["optimal_vwc_max_pct"],
                cdef["maas_hoffman_threshold_dsm"],
                cdef["maas_hoffman_slope_pct_per_dsm"],
                cdef["optimal_ph_min"],
                cdef["optimal_ph_max"],
                cdef["cwsi_ll_intercept"],
                cdef["cwsi_ll_slope"],
                cdef["cwsi_ul_degc"],
                cdef["leaf_outlier_delta_c"],
                cdef["transplant_date"],
                now_iso,
            ))


def _exec(cur, sql_sqlite: str, params: tuple = ()):
    if IS_POSTGRES:
        sql_pg = sql_sqlite.replace("?", "%s")
        cur.execute(sql_pg, params)
    else:
        cur.execute(sql_sqlite, params)


def _fetchall_dicts(cur) -> List[Dict[str, Any]]:
    rows = cur.fetchall()
    if not rows:
        return []
    cols = [col[0] for col in cur.description]
    return [dict(zip(cols, row)) for row in rows]


def purge_simulated_data() -> Dict[str, int]:
    """
    Removes all non-hardware (demo/simulated) batches and sensor readings from the database
    so that if no real PLC data has arrived, the database and UI remain 100% blank.
    Preserves authentic PLC hardware data (plc_hardware_196r) and HMI USB datalogs (hmi_pendrive).
    """
    with get_conn() as conn:
        cur = conn.cursor()
        _exec(cur, "SELECT recorded_at FROM telemetry_batches WHERE source NOT IN ('plc_hardware_196r', 'hmi_pendrive') OR plc_online = 0")
        sim_times = [r["recorded_at"] for r in _fetchall_dicts(cur)]
        deleted_batches = 0
        for rec_t in sim_times:
            _exec(cur, "DELETE FROM sensor_readings WHERE recorded_at = ?", (rec_t,))
            _exec(cur, "DELETE FROM telemetry_batches WHERE recorded_at = ?", (rec_t,))
            deleted_batches += 1
        # Also remove any orphaned sensor_readings not tied to a valid hardware batch
        _exec(
            cur,
            "DELETE FROM sensor_readings WHERE recorded_at NOT IN (SELECT recorded_at FROM telemetry_batches)"
        )
        return {"purged_batches": deleted_batches}


def store_telemetry_batches(
    batches: List[Dict[str, Any]],
    enforce_5min_interval: bool = False,
    allow_simulated: bool = False,
) -> Dict[str, int]:
    """
    Idempotently store a list of real PLC telemetry snapshots.
    Ignores offline/blank or simulated batches unless allow_simulated=True.
    """
    inserted = 0
    skipped = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    with get_conn() as conn:
        cur = conn.cursor()
        last_saved_dt: Optional[datetime] = None
        if enforce_5min_interval:
            _exec(cur, "SELECT recorded_at FROM telemetry_batches ORDER BY recorded_at DESC LIMIT 1")
            row = cur.fetchone()
            if row:
                try:
                    last_saved_dt = datetime.fromisoformat(row[0].replace("Z", "+00:00"))
                except Exception:
                    last_saved_dt = None

        for b in batches:
            source = b.get("source", "plc_hardware_196r")
            plc_online = 1 if b.get("plc_online", True) else 0
            if not allow_simulated and (not plc_online or source in ("plc_offline", "plc_simulator", "edge_laptop")):
                skipped += 1
                continue

            rec_at = b["recorded_at"]
            if enforce_5min_interval and last_saved_dt is not None:
                try:
                    cur_dt = datetime.fromisoformat(rec_at.replace("Z", "+00:00"))
                    if abs((cur_dt - last_saved_dt).total_seconds()) < 280:
                        skipped += 1
                        continue
                    last_saved_dt = cur_dt
                except Exception:
                    pass
            batch_id = b.get("batch_id") or str(uuid.uuid4())
            zones = b.get("zones", [])
            sensors = b.get("sensors", [])
            valves = b.get("valves", {})

            if IS_POSTGRES:
                cur.execute("""
                    INSERT INTO telemetry_batches (
                        batch_id, recorded_at, received_at, source, plc_online,
                        zones_json, sensors_json, valves_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (recorded_at) DO NOTHING
                """, (
                    batch_id, rec_at, now_iso, source, plc_online,
                    json.dumps(zones), json.dumps(sensors), json.dumps(valves)
                ))
            else:
                cur.execute("""
                    INSERT OR IGNORE INTO telemetry_batches (
                        batch_id, recorded_at, received_at, source, plc_online,
                        zones_json, sensors_json, valves_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    batch_id, rec_at, now_iso, source, plc_online,
                    json.dumps(zones), json.dumps(sensors), json.dumps(valves)
                ))

            if cur.rowcount == 0:
                skipped += 1
                continue

            inserted += 1
            for s in sensors:
                sm = float(s["soil_moisture"]) if s.get("soil_moisture") is not None else None
                st = float(s["soil_temp"]) if s.get("soil_temp") is not None else None
                sec = int(s["soil_ec"]) if s.get("soil_ec") is not None else None
                ssalt = int(s["soil_salt"]) if s.get("soil_salt") is not None else None
                sph = float(s["soil_ph"]) if s.get("soil_ph") is not None else None
                lh = float(s["leaf_humidity"]) if s.get("leaf_humidity") is not None else None
                lt = float(s["leaf_temp"]) if s.get("leaf_temp") is not None else None

                if IS_POSTGRES:
                    cur.execute("""
                        INSERT INTO sensor_readings (
                            recorded_at, sensor_id, zone_id, soil_moisture, soil_temp,
                            soil_ec, soil_salt, soil_ph, leaf_humidity, leaf_temp
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (recorded_at, sensor_id) DO NOTHING
                    """, (
                        rec_at, int(s["sensor_id"]), int(s["zone_id"]),
                        sm, st, sec, ssalt, sph, lh, lt
                    ))
                else:
                    cur.execute("""
                        INSERT OR IGNORE INTO sensor_readings (
                            recorded_at, sensor_id, zone_id, soil_moisture, soil_temp,
                            soil_ec, soil_salt, soil_ph, leaf_humidity, leaf_temp
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        rec_at, int(s["sensor_id"]), int(s["zone_id"]),
                        sm, st, sec, ssalt, sph, lh, lt
                    ))

                if sec is not None and sec > 2500:
                    _create_alarm_if_needed(
                        cur, rec_at, int(s["zone_id"]), int(s["sensor_id"]),
                        "warning",
                        f"High Soil EC on R{s['sensor_id']} (Zone {s['zone_id']})",
                        f"Soil EC reached {sec} µS/cm (Salinity: {ssalt} mg/L)."
                    )

            for z in zones:
                zid = int(z["zone_id"])
                is_v_open = bool(z.get("valve_open"))
                if plc_online:
                    _accumulate_zone_flow_in_tx(cur, zid, is_v_open, rec_at)
                if plc_online and z.get("vana_coil_on") is not None:
                    _exec(
                        cur,
                        "UPDATE zone_configs SET auto_mode = ?, manual_valve_state = ?, updated_at = ? WHERE zone_id = ?",
                        (1 if z.get("auto_mode") else 0, 1 if is_v_open else 0, now_iso, zid),
                    )
                z_moist = z.get("avg_soil_moisture")
                if z_moist is not None and float(z_moist) < 35.0 and plc_online:
                    _create_alarm_if_needed(
                        cur, rec_at, zid, None,
                        "critical",
                        f"Low Soil Moisture in Zone {z['zone_id']}",
                        f"Zone {z['zone_id']} average moisture dropped to {float(z_moist):.1f}%."
                    )

    return {"inserted": inserted, "skipped": skipped}


def _accumulate_zone_flow_in_tx(cur, zone_id: int, is_open: bool, event_iso: str) -> None:
    """
    Calculates and accumulates water supplied (Total Liters) for a zone based on Valve ON duration
    and the zone's configured `nominal_flow_lpm` (8 pcs x 4 L/h drippers = 32 L/h max = 0.5333 L/min).
    """
    _exec(
        cur,
        "SELECT nominal_flow_lpm, total_water_liters, total_open_seconds, last_valve_open_at FROM zone_configs WHERE zone_id = ?",
        (zone_id,),
    )
    rows = _fetchall_dicts(cur)
    if not rows:
        return
    r = rows[0]
    nom_lpm = float(r.get("nominal_flow_lpm") or 0.5333)
    tot_l = float(r.get("total_water_liters") or 0.0)
    tot_sec = float(r.get("total_open_seconds") or 0.0)
    last_open_str = r.get("last_valve_open_at")

    if last_open_str:
        try:
            dt_prev = datetime.fromisoformat(last_open_str.replace("Z", "+00:00"))
            dt_curr = datetime.fromisoformat(event_iso.replace("Z", "+00:00"))
            elapsed_sec = (dt_curr - dt_prev).total_seconds()
            if 0.0 < elapsed_sec <= 3600.0:
                tot_sec = round(tot_sec + elapsed_sec, 2)
                tot_l = round(tot_l + (elapsed_sec / 60.0) * nom_lpm, 3)
        except Exception:
            pass

    new_last_open = event_iso if is_open else None
    _exec(
        cur,
        "UPDATE zone_configs SET total_water_liters = ?, total_open_seconds = ?, last_valve_open_at = ? WHERE zone_id = ?",
        (tot_l, tot_sec, new_last_open, zone_id),
    )


def _create_alarm_if_needed(
    cur, rec_at: str, zone_id: Optional[int], sensor_id: Optional[int],
    severity: str, title: str, message: str
) -> None:
    _exec(
        cur,
        "SELECT alarm_id FROM alarm_events WHERE title = ? AND acknowledged = 0 LIMIT 1",
        (title,)
    )
    if cur.fetchone() is None:
        _exec(
            cur,
            """
            INSERT INTO alarm_events (alarm_id, recorded_at, zone_id, sensor_id, severity, title, message, acknowledged)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (str(uuid.uuid4()), rec_at, zone_id, sensor_id, severity, title, message)
        )


def get_zone_configs() -> List[Dict[str, Any]]:
    now_dt = datetime.now(timezone.utc)
    with get_conn() as conn:
        cur = conn.cursor()
        _exec(cur, "SELECT * FROM zone_configs ORDER BY zone_id ASC")
        rows = _fetchall_dicts(cur)
        for r in rows:
            zid = int(r["zone_id"])
            nom_lpm = float(r.get("nominal_flow_lpm") or 0.5333)
            nom_lph = round(nom_lpm * 60.0, 1)
            tot_l = float(r.get("total_water_liters") or 0.0)
            tot_sec = float(r.get("total_open_seconds") or 0.0)
            last_open_str = r.get("last_valve_open_at")
            is_open_now = bool(r.get("manual_valve_state"))
            if is_open_now and last_open_str:
                try:
                    dt_prev = datetime.fromisoformat(str(last_open_str).replace("Z", "+00:00"))
                    extra_sec = max(0.0, min(3600.0, (now_dt - dt_prev).total_seconds()))
                    tot_sec += extra_sec
                    tot_l += (extra_sec / 60.0) * nom_lpm
                except Exception:
                    pass
            r["nominal_flow_lpm"] = round(nom_lpm, 3)
            r["nominal_flow_lph"] = nom_lph
            r["total_water_liters"] = round(tot_l, 2)
            r["total_open_seconds"] = round(tot_sec, 1)
            r["flow_meter_connected"] = bool(r.get("flow_meter_connected", 0))
            r["flow_rate_lpm"] = round(nom_lpm, 2) if is_open_now else 0.0
            r["flow_rate_lph"] = nom_lph if is_open_now else 0.0
            r["drippers_spec"] = "8 pcs × 4 L/h drippers = Max 32 L/h"
            r["flow_meter_model"] = "YF-S201 (8 × 4 L/h drippers = 32 L/h max)"
            r["valve_model"] = "hexa CONTROLS AC 230V IP54 NC"
            if zid in ZONES:
                r["relay_tag"] = ZONES[zid]["relay_tag"]
                r["valve_coil"] = ZONES[zid]["valve_coil"]
                r["valve_manual_coil"] = ZONES[zid].get("valve_manual_coil", 8 + zid)
                r["qp_index"] = ZONES[zid].get("qp_index")
                r["sensor_ids"] = ZONES[zid]["sensor_ids"]
                r["leaf_slave_ids"] = [100 + s for s in ZONES[zid]["sensor_ids"]]
                r["plc_terminal"] = ZONES[zid]["plc_terminal"]
                r["avg_tag"] = ZONES[zid]["avg_tag"]
        return rows


def get_latest_telemetry() -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.cursor()
        _exec(cur, "SELECT * FROM telemetry_batches ORDER BY recorded_at DESC LIMIT 1")
        rows = _fetchall_dicts(cur)
        if not rows:
            return None
        r = rows[0]
        configs = {c["zone_id"]: c for c in get_zone_configs()}
        zones = json.loads(r["zones_json"])
        for z in zones:
            zid = z.get("zone_id")
            if zid in configs:
                cfg = configs[zid]
                if z.get("vana_coil_on") is None and "operation_mode" not in z:
                    z["auto_mode"] = bool(cfg["auto_mode"])
                z["min_moisture"] = float(cfg["min_moisture"])
                z["max_moisture"] = float(cfg["max_moisture"])
                z["relay_tag"] = ZONES[zid]["relay_tag"]
                z["plc_terminal"] = ZONES[zid]["plc_terminal"]
                z["valve_coil"] = ZONES[zid]["valve_coil"]
                z["valve_manual_coil"] = ZONES[zid].get("valve_manual_coil", 8 + zid)
                z["qp_index"] = ZONES[zid].get("qp_index")
                z["sensor_ids"] = ZONES[zid]["sensor_ids"]
                z["leaf_slave_ids"] = [100 + s for s in ZONES[zid]["sensor_ids"]]
                nom_lpm = float(cfg.get("nominal_flow_lpm", 0.5333))
                nom_lph = round(nom_lpm * 60.0, 1)
                v_open = bool(z.get("valve_open"))
                z["nominal_flow_lpm"] = round(nom_lpm, 3)
                z["nominal_flow_lph"] = nom_lph
                z["total_water_liters"] = round(float(cfg.get("total_water_liters", 0.0)), 2)
                z["total_open_seconds"] = round(float(cfg.get("total_open_seconds", 0.0)), 1)
                z["flow_meter_connected"] = bool(cfg.get("flow_meter_connected", False))
                z["flow_rate_lpm"] = round(nom_lpm, 2) if v_open else 0.0
                z["flow_rate_lph"] = nom_lph if v_open else 0.0
                z["drippers_spec"] = "8 pcs × 4 L/h drippers = Max 32 L/h"
                z["flow_meter_model"] = "YF-S201 (8 × 4 L/h drippers = 32 L/h max)"
                z["valve_model"] = "hexa CONTROLS AC 230V IP54 NC"
            if "avg_soil_ph" not in z:
                z["avg_soil_ph"] = None
        sensors = json.loads(r["sensors_json"])
        for s in sensors:
            sid = int(s.get("sensor_id", 1))
            s.setdefault("soil_slave_id", sid)
            s.setdefault("leaf_slave_id", 100 + sid)
            s.setdefault("soil_ph", None)
        return {
            "batch_id": r["batch_id"],
            "recorded_at": r["recorded_at"],
            "received_at": r["received_at"],
            "source": r["source"],
            "plc_online": bool(r["plc_online"]),
            "zones": zones,
            "sensors": sensors,
            "valves": json.loads(r["valves_json"]),
        }


def get_history_batches(limit: int = 120) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.cursor()
        _exec(cur, "SELECT * FROM telemetry_batches ORDER BY recorded_at DESC LIMIT ?", (limit,))
        rows = _fetchall_dicts(cur)
        result = []
        for r in reversed(rows):
            result.append({
                "batch_id": r["batch_id"],
                "recorded_at": r["recorded_at"],
                "source": r["source"],
                "plc_online": bool(r["plc_online"]),
                "zones": json.loads(r["zones_json"]),
                "valves": json.loads(r["valves_json"]),
            })
        return result


def queue_control_command(
    zone_id: int,
    command_type: str,
    target_state: Optional[bool] = None,
    auto_mode: Optional[bool] = None,
    min_moisture: Optional[float] = None,
    max_moisture: Optional[float] = None,
    requested_by: str = "mobile_app"
) -> Dict[str, Any]:
    if zone_id not in ZONES:
        raise ValueError(f"Invalid zone_id {zone_id} (must be 1..8)")

    zdef = ZONES[zone_id]
    now_iso = datetime.now(timezone.utc).isoformat()
    cmd_id = str(uuid.uuid4())

    with get_conn() as conn:
        cur = conn.cursor()
        if target_state is not None:
            _accumulate_zone_flow_in_tx(cur, zone_id, bool(target_state), now_iso)
            _exec(
                cur,
                "UPDATE zone_configs SET manual_valve_state = ?, auto_mode = ?, updated_at = ? WHERE zone_id = ?",
                (1 if target_state else 0, 0 if auto_mode is None else (1 if auto_mode else 0), now_iso, zone_id)
            )
            _exec(
                cur,
                """
                INSERT INTO valve_events (event_id, recorded_at, zone_id, valve_tag, state, trigger_source, zone_moisture)
                VALUES (?, ?, ?, ?, ?, ?, NULL)
                """,
                (str(uuid.uuid4()), now_iso, zone_id, zdef["valve_tag"], 1 if target_state else 0, requested_by)
            )

        if auto_mode is not None:
            if target_state is None and bool(auto_mode):
                _accumulate_zone_flow_in_tx(cur, zone_id, False, now_iso)
                _exec(
                    cur,
                    "UPDATE zone_configs SET auto_mode = 1, manual_valve_state = 0, updated_at = ? WHERE zone_id = ?",
                    (now_iso, zone_id)
                )
            else:
                _exec(
                    cur,
                    "UPDATE zone_configs SET auto_mode = ?, updated_at = ? WHERE zone_id = ?",
                    (1 if auto_mode else 0, now_iso, zone_id)
                )

        if min_moisture is not None and max_moisture is not None:
            _exec(
                cur,
                "UPDATE zone_configs SET min_moisture = ?, max_moisture = ?, updated_at = ? WHERE zone_id = ?",
                (float(min_moisture), float(max_moisture), now_iso, zone_id)
            )

        # Supersede any older pending commands for the same zone so the queue never piles up while PLC is offline
        _exec(
            cur,
            "UPDATE pending_commands SET status = 'superseded', executed_at = ? WHERE zone_id = ? AND status = 'pending'",
            (now_iso, zone_id)
        )

        _exec(
            cur,
            """
            INSERT INTO pending_commands (
                cmd_id, created_at, zone_id, command_type, valve_tag, valve_coil,
                target_state, auto_mode, min_moisture, max_moisture, status, requested_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                cmd_id, now_iso, zone_id, command_type, zdef["valve_tag"], zdef["valve_coil"],
                None if target_state is None else (1 if target_state else 0),
                None if auto_mode is None else (1 if auto_mode else 0),
                min_moisture, max_moisture, requested_by
            )
        )

    return {
        "cmd_id": cmd_id,
        "created_at": now_iso,
        "zone_id": zone_id,
        "command_type": command_type,
        "valve_tag": zdef["valve_tag"],
        "valve_coil": zdef["valve_coil"],
        "target_state": target_state,
        "auto_mode": auto_mode,
        "min_moisture": min_moisture,
        "max_moisture": max_moisture,
        "status": "pending",
    }


def update_flow_meter_config(
    zone_id: int,
    nominal_flow_lpm: Optional[float] = None,
    total_water_liters: Optional[float] = None,
    reset_counter: bool = False,
    flow_meter_connected: Optional[bool] = None,
    apply_to_all_zones: bool = False,
) -> Dict[str, Any]:
    """
    Updates the YF-S201 Flow Meter settings and/or resets/calibrates cumulative Total Liters Supplied (`total_water_liters`)
    for a single zone (1..8) or all 8 zones.
    """
    if zone_id not in ZONES and not apply_to_all_zones:
        raise ValueError(f"Invalid zone_id {zone_id} (must be 1..8)")

    now_iso = datetime.now(timezone.utc).isoformat()
    target_zones = list(ZONES.keys()) if apply_to_all_zones else [zone_id]

    with get_conn() as conn:
        cur = conn.cursor()
        for zid in target_zones:
            if nominal_flow_lpm is not None:
                _exec(
                    cur,
                    "UPDATE zone_configs SET nominal_flow_lpm = ?, updated_at = ? WHERE zone_id = ?",
                    (max(0.05, min(30.0, float(nominal_flow_lpm))), now_iso, zid),
                )
            if reset_counter:
                _exec(
                    cur,
                    "UPDATE zone_configs SET total_water_liters = 0.0, total_open_seconds = 0.0, last_valve_open_at = CASE WHEN manual_valve_state = 1 THEN ? ELSE NULL END, updated_at = ? WHERE zone_id = ?",
                    (now_iso, now_iso, zid),
                )
            elif total_water_liters is not None:
                _exec(
                    cur,
                    "UPDATE zone_configs SET total_water_liters = ?, updated_at = ? WHERE zone_id = ?",
                    (max(0.0, float(total_water_liters)), now_iso, zid),
                )
            if flow_meter_connected is not None:
                _exec(
                    cur,
                    "UPDATE zone_configs SET flow_meter_connected = ?, updated_at = ? WHERE zone_id = ?",
                    (1 if flow_meter_connected else 0, now_iso, zid),
                )

    configs = {c["zone_id"]: c for c in get_zone_configs()}
    return {
        "updated_zones": target_zones,
        "zone_config": configs.get(zone_id),
        "all_zone_configs": list(configs.values()),
    }


def fetch_pending_commands() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.cursor()
        _exec(cur, "SELECT * FROM pending_commands WHERE status = 'pending' ORDER BY created_at ASC")
        return _fetchall_dicts(cur)


def ack_command(cmd_id: str) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        cur = conn.cursor()
        _exec(
            cur,
            "UPDATE pending_commands SET status = 'executed', executed_at = ? WHERE cmd_id = ?",
            (now_iso, cmd_id)
        )


def get_alarms(include_acknowledged: bool = False) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.cursor()
        if include_acknowledged:
            _exec(cur, "SELECT * FROM alarm_events ORDER BY recorded_at DESC LIMIT 100")
        else:
            _exec(cur, "SELECT * FROM alarm_events WHERE acknowledged = 0 ORDER BY recorded_at DESC LIMIT 100")
        return _fetchall_dicts(cur)


def ack_alarm(alarm_id: str) -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        _exec(cur, "UPDATE alarm_events SET acknowledged = 1 WHERE alarm_id = ?", (alarm_id,))


def get_stats_summary() -> Dict[str, Any]:
    with get_conn() as conn:
        cur = conn.cursor()
        _exec(cur, "SELECT COUNT(*) AS cnt FROM telemetry_batches")
        total_batches = _fetchall_dicts(cur)[0]["cnt"]
        _exec(cur, "SELECT COUNT(*) AS cnt FROM sensor_readings")
        total_readings = _fetchall_dicts(cur)[0]["cnt"]
        _exec(cur, "SELECT COUNT(*) AS cnt FROM pending_commands WHERE status = 'pending'")
        pending_cmds = _fetchall_dicts(cur)[0]["cnt"]
        _exec(cur, "SELECT COUNT(*) AS cnt FROM alarm_events WHERE acknowledged = 0")
        active_alarms = _fetchall_dicts(cur)[0]["cnt"]
        return {
            "total_batches": total_batches,
            "total_sensor_readings": total_readings,
            "pending_commands": pending_cmds,
            "active_alarms": active_alarms,
        }


def get_system_settings() -> Dict[str, Any]:
    with get_conn() as conn:
        cur = conn.cursor()
        _exec(cur, "SELECT * FROM system_settings WHERE setting_id = 1")
        rows = _fetchall_dicts(cur)
        if not rows:
            return {
                "setting_id": 1,
                "save_interval_sec": 60,
                "default_min_moisture": 45.0,
                "default_max_moisture": 80.0,
                "global_auto_mode": True,
                "high_ec_alarm_threshold": 2500,
                "low_moisture_alarm_threshold": 35.0,
                "high_temp_alarm_threshold": 35.0,
                "auto_sync_plc_clock": True,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        r = rows[0]
        return {
            "setting_id": 1,
            "save_interval_sec": int(r.get("save_interval_sec", 60)),
            "default_min_moisture": float(r.get("default_min_moisture", 45.0)),
            "default_max_moisture": float(r.get("default_max_moisture", 80.0)),
            "global_auto_mode": bool(r.get("global_auto_mode", 1)),
            "high_ec_alarm_threshold": int(r.get("high_ec_alarm_threshold", 2500)),
            "low_moisture_alarm_threshold": float(r.get("low_moisture_alarm_threshold", 35.0)),
            "high_temp_alarm_threshold": float(r.get("high_temp_alarm_threshold", 35.0)),
            "auto_sync_plc_clock": bool(r.get("auto_sync_plc_clock", 1)),
            "updated_at": r.get("updated_at"),
        }


def update_system_settings(
    save_interval_sec: int = 60,
    default_min_moisture: float = 45.0,
    default_max_moisture: float = 80.0,
    global_auto_mode: bool = True,
    high_ec_alarm_threshold: int = 2500,
    low_moisture_alarm_threshold: float = 35.0,
    high_temp_alarm_threshold: float = 35.0,
    auto_sync_plc_clock: bool = True,
    apply_to_all_zones: bool = False,
) -> Dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        cur = conn.cursor()
        _exec(
            cur,
            """
            UPDATE system_settings SET
                save_interval_sec = ?,
                default_min_moisture = ?,
                default_max_moisture = ?,
                global_auto_mode = ?,
                high_ec_alarm_threshold = ?,
                low_moisture_alarm_threshold = ?,
                high_temp_alarm_threshold = ?,
                auto_sync_plc_clock = ?,
                updated_at = ?
            WHERE setting_id = 1
            """,
            (
                int(save_interval_sec),
                float(default_min_moisture),
                float(default_max_moisture),
                1 if global_auto_mode else 0,
                int(high_ec_alarm_threshold),
                float(low_moisture_alarm_threshold),
                float(high_temp_alarm_threshold),
                1 if auto_sync_plc_clock else 0,
                now_iso,
            ),
        )
        if apply_to_all_zones:
            _exec(
                cur,
                "UPDATE zone_configs SET min_moisture = ?, max_moisture = ?, auto_mode = ?, updated_at = ?",
                (float(default_min_moisture), float(default_max_moisture), 1 if global_auto_mode else 0, now_iso),
            )
    return get_system_settings()


def prune_to_5min_intervals() -> int:
    """Preserves all recorded snapshots (1-minute, 5-minute, etc.) for granular plot history inspection."""
    return 0


def _bucket_key(iso_str: str, resolution: str) -> str:
    """Groups ISO timestamps into raw, 1min, 2min, 5min, 10min, 15min, 30min, hourly, or daily buckets (UTC)."""
    if not resolution or resolution == "raw":
        return iso_str
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        if resolution == "1min":
            return dt.replace(second=0, microsecond=0).isoformat()
        if resolution == "2min":
            m = (dt.minute // 2) * 2
            return dt.replace(minute=m, second=0, microsecond=0).isoformat()
        if resolution == "5min":
            m = (dt.minute // 5) * 5
            return dt.replace(minute=m, second=0, microsecond=0).isoformat()
        if resolution == "10min":
            m = (dt.minute // 10) * 10
            return dt.replace(minute=m, second=0, microsecond=0).isoformat()
        if resolution == "15min":
            m = (dt.minute // 15) * 15
            return dt.replace(minute=m, second=0, microsecond=0).isoformat()
        if resolution == "30min":
            m = (dt.minute // 30) * 30
            return dt.replace(minute=m, second=0, microsecond=0).isoformat()
        if resolution in ("hourly", "1hour"):
            return dt.replace(minute=0, second=0, microsecond=0).isoformat()
        if resolution in ("daily", "1day"):
            return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    return iso_str


def _normalize_iso_bound(iso_str: Optional[str], is_end: bool = False) -> Optional[str]:
    """Normalizes any ISO date/time string ('Z' or offset) to UTC '+00:00' format matching DB recorded_at."""
    if not iso_str or not str(iso_str).strip():
        return None
    s = str(iso_str).strip()
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        if is_end and dt.second == 0 and dt.microsecond == 0:
            dt = dt.replace(second=59, microsecond=999999)
        return dt.isoformat()
    except Exception:
        return s


def query_filtered_telemetry(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    hours: Optional[float] = None,
    zone_ids: Optional[List[int]] = None,
    sensor_ids: Optional[List[int]] = None,
    min_moisture: Optional[float] = None,
    max_moisture: Optional[float] = None,
    min_temp: Optional[float] = None,
    max_temp: Optional[float] = None,
    min_ec: Optional[int] = None,
    max_ec: Optional[int] = None,
    valve_state: str = "all",
    resolution: str = "5min",
    limit: int = 5000,
) -> Dict[str, Any]:
    """
    Multi-criteria query engine for filtering and aggregating
    both 8-Zone summaries and 24-Sensor (Soil Slave 1..24 + Leaf Slave 101..124) raw readings.
    Supports relative `hours` windows (e.g., 0.25, 0.5, 1, 3, 6, 12, 24, 72, 168, 720)
    as well as explicit `start_date` and `end_date` bounds.
    """
    norm_start = _normalize_iso_bound(start_date, is_end=False)
    norm_end = _normalize_iso_bound(end_date, is_end=True)

    with get_conn() as conn:
        cur = conn.cursor()

        # If a relative `hours` window is requested (e.g. Last 1H, Last 6H, Last 24H),
        # compute [now - hours, now] in UTC; if no batches exist in that wall-clock window
        # (e.g. PLC paused briefly), anchor the window to the latest recorded batch timestamp.
        if hours is not None and hours > 0:
            now_utc = datetime.now(timezone.utc)
            win_start = (now_utc - timedelta(hours=float(hours))).isoformat()
            win_end = now_utc.isoformat()
            _exec(
                cur,
                "SELECT COUNT(*) AS cnt FROM telemetry_batches WHERE recorded_at >= ? AND recorded_at <= ?",
                (win_start, win_end),
            )
            cnt_rows = _fetchall_dicts(cur)
            cnt_row = cnt_rows[0] if cnt_rows else None
            if cnt_row and int(cnt_row.get("cnt", 0)) > 0:
                norm_start = win_start
                norm_end = win_end
            else:
                _exec(cur, "SELECT MAX(recorded_at) AS max_ts FROM telemetry_batches")
                max_rows = _fetchall_dicts(cur)
                max_row = max_rows[0] if max_rows else None
                max_ts = (max_row or {}).get("max_ts")
                if max_ts:
                    try:
                        latest_dt = datetime.fromisoformat(str(max_ts).replace("Z", "+00:00"))
                        if latest_dt.tzinfo is None:
                            latest_dt = latest_dt.replace(tzinfo=timezone.utc)
                        norm_start = (latest_dt - timedelta(hours=float(hours))).isoformat()
                        norm_end = (latest_dt + timedelta(seconds=1)).isoformat()
                    except Exception:
                        norm_start = win_start
                        norm_end = win_end
                else:
                    norm_start = win_start
                    norm_end = win_end

        where_batches = ["1=1"]
        params_batches: List[Any] = []
        if norm_start:
            where_batches.append("recorded_at >= ?")
            params_batches.append(norm_start)
        if norm_end:
            where_batches.append("recorded_at <= ?")
            params_batches.append(norm_end)

        # Fetch sufficient raw 1-minute batches BEFORE time-bucket aggregation so multi-minute / hourly / daily
        # intervals over 24H / 7D / 30D are never prematurely truncated at 500 raw minutes!
        if resolution and resolution != "raw":
            raw_batch_limit = max(int(limit) * 60, 25000)
        elif norm_start or norm_end:
            raw_batch_limit = max(int(limit), 10000)
        else:
            raw_batch_limit = int(limit)

        sql_b = (
            f"SELECT * FROM telemetry_batches WHERE {' AND '.join(where_batches)} "
            f"ORDER BY recorded_at DESC LIMIT ?"
        )
        _exec(cur, sql_b, tuple(params_batches + [raw_batch_limit]))
        batch_rows = _fetchall_dicts(cur)

        zone_rows: List[Dict[str, Any]] = []
        valve_open_times_by_zone: Dict[tuple, bool] = {}

        for b in batch_rows:
            rec_at = b["recorded_at"]
            src = b["source"]
            plc_ok = bool(b["plc_online"])
            zones = json.loads(b["zones_json"])
            for z in zones:
                zid = int(z.get("zone_id", 0))
                v_open = bool(z.get("valve_open", False))
                valve_open_times_by_zone[(rec_at, zid)] = v_open

                if zone_ids and zid not in zone_ids:
                    continue
                if valve_state == "open" and not v_open:
                    continue
                if valve_state == "closed" and v_open:
                    continue

                moist = z.get("avg_soil_moisture")
                temp = z.get("avg_soil_temp")
                ec = z.get("avg_soil_ec")
                salt = z.get("avg_soil_salt")
                ph = z.get("avg_soil_ph")
                lh = z.get("avg_leaf_humidity")
                lt = z.get("avg_leaf_temp")

                if min_moisture is not None and (moist is None or float(moist) < min_moisture):
                    continue
                if max_moisture is not None and (moist is None or float(moist) > max_moisture):
                    continue
                if min_temp is not None and (temp is None or float(temp) < min_temp):
                    continue
                if max_temp is not None and (temp is None or float(temp) > max_temp):
                    continue
                if min_ec is not None and (ec is None or float(ec) < min_ec):
                    continue
                if max_ec is not None and (ec is None or float(ec) > max_ec):
                    continue

                zone_rows.append({
                    "recorded_at": rec_at,
                    "bucket": _bucket_key(rec_at, resolution),
                    "samples_count": 1,
                    "source": src,
                    "plc_online": plc_ok,
                    "zone_id": zid,
                    "zone_name": z.get("name_tr", f"Zone {zid}"),
                    "valve_tag": z.get("valve_tag", f"vana{zid}"),
                    "valve_open": v_open,
                    "avg_soil_moisture": round(float(moist), 2) if moist is not None else None,
                    "avg_soil_temp": round(float(temp), 2) if temp is not None else None,
                    "avg_soil_ec": round(float(ec), 1) if ec is not None else None,
                    "avg_soil_salt": round(float(salt), 1) if salt is not None else None,
                    "avg_soil_ph": round(float(ph), 2) if ph is not None else None,
                    "avg_leaf_humidity": round(float(lh), 2) if lh is not None else None,
                    "avg_leaf_temp": round(float(lt), 2) if lt is not None else None,
                })

        where_s = ["1=1"]
        params_s: List[Any] = []
        if norm_start:
            where_s.append("recorded_at >= ?")
            params_s.append(norm_start)
        if norm_end:
            where_s.append("recorded_at <= ?")
            params_s.append(norm_end)
        if sensor_ids and len(sensor_ids) == 1:
            where_s.append("sensor_id = ?")
            params_s.append(int(sensor_ids[0]))
        if zone_ids and len(zone_ids) == 1:
            where_s.append("zone_id = ?")
            params_s.append(int(zone_ids[0]))
        if min_moisture is not None:
            where_s.append("soil_moisture >= ?")
            params_s.append(min_moisture)
        if max_moisture is not None:
            where_s.append("soil_moisture <= ?")
            params_s.append(max_moisture)
        if min_temp is not None:
            where_s.append("soil_temp >= ?")
            params_s.append(min_temp)
        if max_temp is not None:
            where_s.append("soil_temp <= ?")
            params_s.append(max_temp)
        if min_ec is not None:
            where_s.append("soil_ec >= ?")
            params_s.append(min_ec)
        if max_ec is not None:
            where_s.append("soil_ec <= ?")
            params_s.append(max_ec)

        sensor_mult = 1 if (sensor_ids and len(sensor_ids) == 1) else 24
        sql_s = (
            f"SELECT * FROM sensor_readings WHERE {' AND '.join(where_s)} "
            f"ORDER BY recorded_at DESC, sensor_id ASC LIMIT ?"
        )
        _exec(cur, sql_s, tuple(params_s + [raw_batch_limit * sensor_mult]))
        raw_s_rows = _fetchall_dicts(cur)

        sensor_rows: List[Dict[str, Any]] = []
        for r in raw_s_rows:
            sid = int(r["sensor_id"])
            zid = int(r["zone_id"])
            if zone_ids and zid not in zone_ids:
                continue
            if sensor_ids and sid not in sensor_ids:
                continue
            v_open = valve_open_times_by_zone.get((r["recorded_at"], zid), False)
            if valve_state == "open" and not v_open:
                continue
            if valve_state == "closed" and v_open:
                continue

            sensor_rows.append({
                "recorded_at": r["recorded_at"],
                "bucket": _bucket_key(r["recorded_at"], resolution),
                "samples_count": 1,
                "sensor_id": sid,
                "soil_slave_id": sid,
                "leaf_slave_id": 100 + sid,
                "sensor_tag": f"R{sid}",
                "leaf_tag": f"R{sid}_L",
                "zone_id": zid,
                "valve_open": v_open,
                "soil_moisture": round(float(r["soil_moisture"]), 2) if r.get("soil_moisture") is not None else None,
                "soil_temp": round(float(r["soil_temp"]), 2) if r.get("soil_temp") is not None else None,
                "soil_ec": int(r["soil_ec"]) if r.get("soil_ec") is not None else None,
                "soil_salt": int(r["soil_salt"]) if r.get("soil_salt") is not None else None,
                "soil_ph": round(float(r["soil_ph"]), 2) if r.get("soil_ph") is not None else None,
                "leaf_humidity": round(float(r["leaf_humidity"]), 2) if r.get("leaf_humidity") is not None else None,
                "leaf_temp": round(float(r["leaf_temp"]), 2) if r.get("leaf_temp") is not None else None,
            })

        raw_zone_samples = len(zone_rows)
        raw_sensor_samples = len(sensor_rows)

        if resolution in ("1min", "2min", "5min", "10min", "15min", "30min", "hourly", "1hour", "daily", "1day"):
            zone_rows = _aggregate_zone_rows(zone_rows)
            sensor_rows = _aggregate_sensor_rows(sensor_rows)

        if limit and limit > 0:
            zone_rows = zone_rows[: int(limit)]
            sensor_rows = sensor_rows[: int(limit) * 24]

        zone_stats: List[Dict[str, Any]] = []
        for zid in sorted(ZONES.keys()):
            if zone_ids and zid not in zone_ids:
                continue
            z_sub = [zr for zr in zone_rows if zr["zone_id"] == zid and zr["avg_soil_moisture"] is not None]
            if not z_sub:
                continue
            m_vals = [float(x["avg_soil_moisture"]) for x in z_sub if x["avg_soil_moisture"] is not None]
            t_vals = [float(x["avg_soil_temp"]) for x in z_sub if x["avg_soil_temp"] is not None]
            ec_vals = [float(x["avg_soil_ec"]) for x in z_sub if x["avg_soil_ec"] is not None]
            lh_vals = [float(x["avg_leaf_humidity"]) for x in z_sub if x["avg_leaf_humidity"] is not None]
            lt_vals = [float(x["avg_leaf_temp"]) for x in z_sub if x.get("avg_leaf_temp") is not None]
            open_cnt = sum(1 for x in z_sub if x["valve_open"])
            zone_stats.append({
                "zone_id": zid,
                "valve_tag": ZONES[zid]["valve_tag"],
                "sample_count": len(z_sub),
                "min_moisture": round(min(m_vals), 2) if m_vals else None,
                "max_moisture": round(max(m_vals), 2) if m_vals else None,
                "mean_moisture": round(sum(m_vals) / len(m_vals), 2) if m_vals else None,
                "mean_temp": round(sum(t_vals) / len(t_vals), 2) if t_vals else None,
                "mean_ec": round(sum(ec_vals) / len(ec_vals), 1) if ec_vals else None,
                "mean_leaf_humidity": round(sum(lh_vals) / len(lh_vals), 2) if lh_vals else None,
                "mean_leaf_temp": round(sum(lt_vals) / len(lt_vals), 2) if lt_vals else None,
                "irrigating_intervals": open_cnt,
            })

        _exec(cur, "SELECT * FROM valve_events ORDER BY recorded_at DESC LIMIT 2000")
        valve_events = _fetchall_dicts(cur)
        if zone_ids:
            valve_events = [v for v in valve_events if int(v["zone_id"]) in zone_ids]

    return {
        "zone_rows": zone_rows,
        "sensor_rows": sensor_rows,
        "raw_zone_samples": raw_zone_samples,
        "raw_sensor_samples": raw_sensor_samples,
        "effective_start_date": norm_start,
        "effective_end_date": norm_end,
        "zone_stats": zone_stats,
        "valve_events": valve_events,
    }


def _avg_opt(vals: List[Any], ndigits: int = 2) -> Optional[float]:
    clean = [float(v) for v in vals if v is not None]
    if not clean:
        return None
    return round(sum(clean) / len(clean), ndigits)


def _aggregate_zone_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[tuple, List[Dict[str, Any]]] = {}
    for r in rows:
        key = (r["bucket"], r["zone_id"])
        grouped.setdefault(key, []).append(r)
    out: List[Dict[str, Any]] = []
    for (bucket, zid), items in grouped.items():
        first = items[0]
        out.append({
            "recorded_at": bucket,
            "bucket": bucket,
            "samples_count": len(items),
            "source": first["source"],
            "plc_online": any(x["plc_online"] for x in items),
            "zone_id": zid,
            "zone_name": first["zone_name"],
            "valve_tag": first["valve_tag"],
            "valve_open": any(x["valve_open"] for x in items),
            "avg_soil_moisture": _avg_opt([x.get("avg_soil_moisture") for x in items], 2),
            "avg_soil_temp": _avg_opt([x.get("avg_soil_temp") for x in items], 2),
            "avg_soil_ec": _avg_opt([x.get("avg_soil_ec") for x in items], 1),
            "avg_soil_salt": _avg_opt([x.get("avg_soil_salt") for x in items], 1),
            "avg_soil_ph": _avg_opt([x.get("avg_soil_ph") for x in items], 2),
            "avg_leaf_humidity": _avg_opt([x.get("avg_leaf_humidity") for x in items], 2),
            "avg_leaf_temp": _avg_opt([x.get("avg_leaf_temp") for x in items], 2),
        })
    return out


def _aggregate_sensor_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[tuple, List[Dict[str, Any]]] = {}
    for r in rows:
        key = (r["bucket"], r["sensor_id"])
        grouped.setdefault(key, []).append(r)
    out: List[Dict[str, Any]] = []
    for (bucket, sid), items in grouped.items():
        first = items[0]
        ec_avg = _avg_opt([x.get("soil_ec") for x in items], 0)
        salt_avg = _avg_opt([x.get("soil_salt") for x in items], 0)
        out.append({
            "recorded_at": bucket,
            "bucket": bucket,
            "samples_count": len(items),
            "sensor_id": sid,
            "soil_slave_id": first.get("soil_slave_id", sid),
            "leaf_slave_id": first.get("leaf_slave_id", 100 + sid),
            "sensor_tag": first["sensor_tag"],
            "leaf_tag": first["leaf_tag"],
            "zone_id": first["zone_id"],
            "valve_open": any(x["valve_open"] for x in items),
            "soil_moisture": _avg_opt([x.get("soil_moisture") for x in items], 2),
            "soil_temp": _avg_opt([x.get("soil_temp") for x in items], 2),
            "soil_ec": int(ec_avg) if ec_avg is not None else None,
            "soil_salt": int(salt_avg) if salt_avg is not None else None,
            "soil_ph": _avg_opt([x.get("soil_ph") for x in items], 2),
            "leaf_humidity": _avg_opt([x.get("leaf_humidity") for x in items], 2),
            "leaf_temp": _avg_opt([x.get("leaf_temp") for x in items], 2),
        })
    return out


def get_plot_history(
    sensor_id: int,
    resolution: str = "1min",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    hours: Optional[float] = None,
    limit: int = 2000,
) -> Dict[str, Any]:
    """
    Returns complete single-plot metadata, current live state, summary statistics,
    and historical time-series aggregated at `resolution` (raw, 1min, 2min, 5min, 10min, 15min, 30min, hourly, daily).
    """
    if sensor_id not in SENSORS:
        raise ValueError(f"Invalid sensor_id {sensor_id} (must be 1..24)")

    sdef = SENSORS[sensor_id]
    zid = int(sdef["zone_id"])
    zdef = ZONES[zid]

    configs = {c["zone_id"]: c for c in get_zone_configs()}
    zcfg = configs.get(zid, {})
    latest_batch = get_latest_telemetry() or {}
    latest_sensor = next(
        (s for s in latest_batch.get("sensors", []) if int(s.get("sensor_id", 0)) == sensor_id),
        None,
    )
    latest_zone = next(
        (z for z in latest_batch.get("zones", []) if int(z.get("zone_id", 0)) == zid),
        None,
    )

    q = query_filtered_telemetry(
        start_date=start_date,
        end_date=end_date,
        hours=hours,
        sensor_ids=[sensor_id],
        resolution=resolution,
        limit=limit,
    )
    rows_desc = q["sensor_rows"]
    rows_asc = list(reversed(rows_desc))
    total_raw_samples = sum(int(r.get("samples_count", 1)) for r in rows_desc)

    def _stat_triplet(key: str, ndigits: int = 2) -> Dict[str, Optional[float]]:
        vals = [float(r[key]) for r in rows_desc if r.get(key) is not None]
        if not vals:
            return {"min": None, "max": None, "avg": None}
        return {
            "min": round(min(vals), ndigits),
            "max": round(max(vals), ndigits),
            "avg": round(sum(vals) / len(vals), ndigits),
        }

    nom_lpm = float(zcfg.get("nominal_flow_lpm", 0.5333))
    nom_lph = round(nom_lpm * 60.0, 1)
    is_open_now = bool((latest_zone or {}).get("valve_open", False))

    return {
        "sensor_id": sensor_id,
        "plot_label": f"Plot R{sensor_id}",
        "soil_name": sdef["soil_name"],
        "leaf_name": sdef["leaf_name"],
        "soil_slave_id": sdef["soil_slave_id"],
        "leaf_slave_id": sdef["leaf_slave_id"],
        "zone_id": zid,
        "zone_name_en": zdef["name_en"],
        "zone_name_tr": zdef["name_tr"],
        "valve_tag": zdef["valve_tag"],
        "relay_tag": zdef["relay_tag"],
        "plc_terminal": zdef["plc_terminal"],
        "min_moisture": float(zcfg.get("min_moisture", zdef["default_min_moisture"])),
        "max_moisture": float(zcfg.get("max_moisture", zdef["default_max_moisture"])),
        "auto_mode": bool((latest_zone or {}).get("auto_mode", zcfg.get("auto_mode", True))),
        "valve_open": is_open_now,
        "operation_mode": (latest_zone or {}).get("operation_mode", "auto_standby"),
        "nominal_flow_lpm": nom_lpm,
        "nominal_flow_lph": nom_lph,
        "total_water_liters": float(zcfg.get("total_water_liters", 0.0)),
        "total_open_seconds": float(zcfg.get("total_open_seconds", 0.0)),
        "flow_rate_lpm": nom_lpm if is_open_now else 0.0,
        "flow_rate_lph": nom_lph if is_open_now else 0.0,
        "flow_meter_connected": bool(zcfg.get("flow_meter_connected", False)),
        "flow_meter_model": "8 pcs × 4 L/h Drippers (Max 32 L/h per line) + YF-S201",
        "valve_model": "hexa CONTROLS AC 230V IP54 NC",
        "resolution": resolution,
        "effective_start_date": q.get("effective_start_date"),
        "effective_end_date": q.get("effective_end_date"),
        "latest": latest_sensor,
        "stats": {
            "sample_count": len(rows_desc),
            "raw_sample_count": total_raw_samples,
            "soil_moisture": _stat_triplet("soil_moisture", 2),
            "soil_temp": _stat_triplet("soil_temp", 2),
            "soil_ec": _stat_triplet("soil_ec", 1),
            "soil_salt": _stat_triplet("soil_salt", 1),
            "soil_ph": _stat_triplet("soil_ph", 2),
            "leaf_humidity": _stat_triplet("leaf_humidity", 2),
            "leaf_temp": _stat_triplet("leaf_temp", 2),
        },
        "series": rows_asc,
        "rows": rows_desc,
    }


def get_zone_history(
    zone_id: int,
    resolution: str = "1min",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    hours: Optional[float] = None,
    limit: int = 2000,
) -> Dict[str, Any]:
    """
    Returns complete single-line (zone 1..8) metadata, live valve & 3-plot status,
    summary statistics, and historical time-series aggregated at `resolution`.
    """
    if zone_id not in ZONES:
        raise ValueError(f"Invalid zone_id {zone_id} (must be 1..8)")

    zdef = ZONES[zone_id]
    s_ids = list(zdef["sensor_ids"])
    configs = {c["zone_id"]: c for c in get_zone_configs()}
    zcfg = configs.get(zone_id, {})
    latest_batch = get_latest_telemetry() or {}
    latest_zone = next(
        (z for z in latest_batch.get("zones", []) if int(z.get("zone_id", 0)) == zone_id),
        None,
    )
    latest_plots = [
        s for s in latest_batch.get("sensors", []) if int(s.get("sensor_id", 0)) in s_ids
    ]

    q = query_filtered_telemetry(
        start_date=start_date,
        end_date=end_date,
        hours=hours,
        zone_ids=[zone_id],
        sensor_ids=s_ids,
        resolution=resolution,
        limit=limit,
    )
    rows_desc = q["zone_rows"]
    rows_asc = list(reversed(rows_desc))
    total_raw_samples = sum(int(r.get("samples_count", 1)) for r in rows_desc)

    def _stat_triplet(key: str, ndigits: int = 2) -> Dict[str, Optional[float]]:
        vals = [float(r[key]) for r in rows_desc if r.get(key) is not None]
        if not vals:
            return {"min": None, "max": None, "avg": None}
        return {
            "min": round(min(vals), ndigits),
            "max": round(max(vals), ndigits),
            "avg": round(sum(vals) / len(vals), ndigits),
        }

    norm_rows_desc = [
        {
            "recorded_at": r["recorded_at"],
            "bucket": r.get("bucket", r["recorded_at"]),
            "samples_count": int(r.get("samples_count", 1)),
            "zone_id": zone_id,
            "valve_open": bool(r.get("valve_open")),
            "soil_moisture": r.get("avg_soil_moisture"),
            "soil_temp": r.get("avg_soil_temp"),
            "soil_ec": r.get("avg_soil_ec"),
            "soil_salt": r.get("avg_soil_salt"),
            "soil_ph": r.get("avg_soil_ph"),
            "leaf_humidity": r.get("avg_leaf_humidity"),
            "leaf_temp": r.get("avg_leaf_temp"),
        }
        for r in rows_desc
    ]
    norm_rows_asc = list(reversed(norm_rows_desc))

    nom_lpm = float(zcfg.get("nominal_flow_lpm", 0.5333))
    nom_lph = round(nom_lpm * 60.0, 1)
    is_open_now = bool((latest_zone or {}).get("valve_open", False))

    return {
        "zone_id": zone_id,
        "line_label": f"Line {zone_id} (Zone {zone_id})",
        "zone_name_en": zdef["name_en"],
        "zone_name_tr": zdef["name_tr"],
        "sensor_ids": s_ids,
        "valve_tag": zdef["valve_tag"],
        "relay_tag": zdef["relay_tag"],
        "plc_terminal": zdef["plc_terminal"],
        "min_moisture": float(zcfg.get("min_moisture", zdef["default_min_moisture"])),
        "max_moisture": float(zcfg.get("max_moisture", zdef["default_max_moisture"])),
        "auto_mode": bool((latest_zone or {}).get("auto_mode", zcfg.get("auto_mode", True))),
        "valve_open": is_open_now,
        "operation_mode": (latest_zone or {}).get("operation_mode", "auto_standby"),
        "nominal_flow_lpm": nom_lpm,
        "nominal_flow_lph": nom_lph,
        "total_water_liters": float(zcfg.get("total_water_liters", 0.0)),
        "total_open_seconds": float(zcfg.get("total_open_seconds", 0.0)),
        "flow_rate_lpm": nom_lpm if is_open_now else 0.0,
        "flow_rate_lph": nom_lph if is_open_now else 0.0,
        "flow_meter_connected": bool(zcfg.get("flow_meter_connected", False)),
        "flow_meter_model": "8 pcs × 4 L/h Drippers (Max 32 L/h per line) + YF-S201",
        "valve_model": "hexa CONTROLS AC 230V IP54 NC",
        "resolution": resolution,
        "effective_start_date": q.get("effective_start_date"),
        "effective_end_date": q.get("effective_end_date"),
        "latest": {
            "soil_moisture": (latest_zone or {}).get("avg_soil_moisture"),
            "soil_temp": (latest_zone or {}).get("avg_soil_temp"),
            "soil_ec": (latest_zone or {}).get("avg_soil_ec"),
            "soil_salt": (latest_zone or {}).get("avg_soil_salt"),
            "soil_ph": (latest_zone or {}).get("avg_soil_ph"),
            "leaf_humidity": (latest_zone or {}).get("avg_leaf_humidity"),
            "leaf_temp": (latest_zone or {}).get("avg_leaf_temp"),
            "plc_son_ortlama": (latest_zone or {}).get("plc_son_ortlama"),
        },
        "latest_plots": latest_plots,
        "stats": {
            "sample_count": len(norm_rows_desc),
            "raw_sample_count": total_raw_samples,
            "soil_moisture": _stat_triplet("avg_soil_moisture", 2),
            "soil_temp": _stat_triplet("avg_soil_temp", 2),
            "soil_ec": _stat_triplet("avg_soil_ec", 1),
            "soil_salt": _stat_triplet("avg_soil_salt", 1),
            "soil_ph": _stat_triplet("avg_soil_ph", 2),
            "leaf_humidity": _stat_triplet("avg_leaf_humidity", 2),
            "leaf_temp": _stat_triplet("avg_leaf_temp", 2),
        },
        "series": norm_rows_asc,
        "rows": norm_rows_desc,
    }


# ==============================================================================
# PhD Stress, Biostimulant Recovery, Treatment Applications & Research Notes DB
# ==============================================================================


def get_stress_calibration() -> Dict[str, Any]:
    """Return the active biophysical & substrate calibration settings."""
    with get_conn() as conn:
        cur = conn.cursor()
        _exec(cur, "SELECT * FROM stress_calibration_settings WHERE id = 1")
        rows = _fetchall_dicts(cur)
        if not rows:
            return dict(DEFAULT_CALIBRATION)
        row = rows[0]
        return {
            "id": int(row.get("id", 1)),
            "substrate_name": str(row.get("substrate_name", DEFAULT_CALIBRATION["substrate_name"])),
            "hilhorst_epsilon_offset": float(row.get("hilhorst_epsilon_offset", 2.5)),
            "container_capacity_pct": float(row.get("container_capacity_pct", 78.0)),
            "wilting_point_pct": float(row.get("wilting_point_pct", 30.0)),
            "optimal_vwc_min_pct": float(row.get("optimal_vwc_min_pct", 50.0)),
            "optimal_vwc_max_pct": float(row.get("optimal_vwc_max_pct", 78.0)),
            "maas_hoffman_threshold_dsm": float(row.get("maas_hoffman_threshold_dsm", 2.5)),
            "maas_hoffman_slope_pct_per_dsm": float(row.get("maas_hoffman_slope_pct_per_dsm", 9.9)),
            "optimal_ph_min": float(row.get("optimal_ph_min", 5.5)),
            "optimal_ph_max": float(row.get("optimal_ph_max", 6.5)),
            "cwsi_ll_intercept": float(row.get("cwsi_ll_intercept", -1.8)),
            "cwsi_ll_slope": float(row.get("cwsi_ll_slope", -1.35)),
            "cwsi_ul_degc": float(row.get("cwsi_ul_degc", 3.5)),
            "leaf_outlier_delta_c": float(row.get("leaf_outlier_delta_c", 2.0)),
            "transplant_date": str(row.get("transplant_date", "2026-10-16")),
            "updated_at": row.get("updated_at"),
        }


def update_stress_calibration(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update biophysical & substrate calibration settings."""
    current = get_stress_calibration()
    merged = {**current, **{k: v for k, v in updates.items() if v is not None}}
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        cur = conn.cursor()
        _exec(
            cur,
            """
            UPDATE stress_calibration_settings
            SET substrate_name = ?,
                hilhorst_epsilon_offset = ?,
                container_capacity_pct = ?,
                wilting_point_pct = ?,
                optimal_vwc_min_pct = ?,
                optimal_vwc_max_pct = ?,
                maas_hoffman_threshold_dsm = ?,
                maas_hoffman_slope_pct_per_dsm = ?,
                optimal_ph_min = ?,
                optimal_ph_max = ?,
                cwsi_ll_intercept = ?,
                cwsi_ll_slope = ?,
                cwsi_ul_degc = ?,
                leaf_outlier_delta_c = ?,
                transplant_date = ?,
                updated_at = ?
            WHERE id = 1
            """,
            (
                str(merged["substrate_name"]),
                float(merged["hilhorst_epsilon_offset"]),
                float(merged["container_capacity_pct"]),
                float(merged["wilting_point_pct"]),
                float(merged["optimal_vwc_min_pct"]),
                float(merged["optimal_vwc_max_pct"]),
                float(merged["maas_hoffman_threshold_dsm"]),
                float(merged["maas_hoffman_slope_pct_per_dsm"]),
                float(merged["optimal_ph_min"]),
                float(merged["optimal_ph_max"]),
                float(merged["cwsi_ll_intercept"]),
                float(merged["cwsi_ll_slope"]),
                float(merged["cwsi_ul_degc"]),
                float(merged["leaf_outlier_delta_c"]),
                str(merged["transplant_date"]),
                now_iso,
            ),
        )
    return get_stress_calibration()


def get_line_treatment_profiles() -> List[Dict[str, Any]]:
    """Return treatment profiles for all 8 irrigation lines (Zones 1..8)."""
    with get_conn() as conn:
        cur = conn.cursor()
        _exec(cur, "SELECT * FROM line_treatment_profiles ORDER BY zone_id ASC")
        rows = _fetchall_dicts(cur)
        by_zid = {int(r["zone_id"]): r for r in rows}

    out: List[Dict[str, Any]] = []
    for zid in range(1, 9):
        pdef = DEFAULT_LINE_PROFILES[zid]
        r = by_zid.get(zid, {})
        zdef = ZONES.get(zid, {})
        out.append({
            "zone_id": zid,
            "line_label": f"Line {zid} (Zone {zid})",
            "sensor_ids": list(zdef.get("sensor_ids", [])),
            "treatment_code": str(r.get("treatment_code") or pdef["treatment_code"]),
            "salinity_regime": str(r.get("salinity_regime") or pdef["salinity_regime"]),
            "nacl_mm": float(r["nacl_mm"]) if r.get("nacl_mm") is not None else float(pdef["nacl_mm"]),
            "target_solution_ec_uscm": int(r["target_solution_ec_uscm"]) if r.get("target_solution_ec_uscm") is not None else int(pdef["target_solution_ec_uscm"]),
            "nahs_dose_um": float(r["nahs_dose_um"]) if r.get("nahs_dose_um") is not None else float(pdef["nahs_dose_um"]),
            "humic_dose_mll": float(r["humic_dose_mll"]) if r.get("humic_dose_mll") is not None else float(pdef["humic_dose_mll"]),
            "nutrient_matched": bool(r["nutrient_matched"]) if r.get("nutrient_matched") is not None else bool(pdef["nutrient_matched"]),
            "ref_soil_ph": float(r["ref_soil_ph"]) if r.get("ref_soil_ph") is not None else float(pdef["ref_soil_ph"]),
            "notes": str(r.get("notes") if r.get("notes") is not None else pdef["notes"]),
            "updated_at": r.get("updated_at"),
        })
    return out


def update_line_treatment_profile(zone_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update a single irrigation line's treatment profile (Zone 1..8)."""
    if zone_id not in ZONES:
        raise ValueError(f"Invalid zone_id {zone_id} (must be 1..8)")
    profiles = {p["zone_id"]: p for p in get_line_treatment_profiles()}
    current = profiles[zone_id]
    merged = {**current, **{k: v for k, v in updates.items() if v is not None}}
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        cur = conn.cursor()
        _exec(
            cur,
            """
            UPDATE line_treatment_profiles
            SET treatment_code = ?,
                salinity_regime = ?,
                nacl_mm = ?,
                target_solution_ec_uscm = ?,
                nahs_dose_um = ?,
                humic_dose_mll = ?,
                nutrient_matched = ?,
                ref_soil_ph = ?,
                notes = ?,
                updated_at = ?
            WHERE zone_id = ?
            """,
            (
                str(merged["treatment_code"]),
                str(merged["salinity_regime"]),
                float(merged["nacl_mm"]),
                int(merged["target_solution_ec_uscm"]),
                float(merged["nahs_dose_um"]),
                float(merged["humic_dose_mll"]),
                1 if bool(merged["nutrient_matched"]) else 0,
                float(merged["ref_soil_ph"]),
                str(merged.get("notes") or ""),
                now_iso,
                int(zone_id),
            ),
        )
    return {p["zone_id"]: p for p in get_line_treatment_profiles()}[zone_id]


def add_treatment_application(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Record an experimental treatment or biostimulant pulse application (H2S / NaHS, Humic Substance,
    NaCl Salinity, nutrient matching, and solution/drainage EC & pH) into treatment_applications.
    Optionally updates ref_soil_ph on the corresponding line profile if update_line_ref_ph is True.
    """
    app_id = str(payload.get("app_id") or f"trt-{uuid.uuid4().hex[:12]}")
    applied_at = str(payload.get("applied_at") or datetime.now(timezone.utc).isoformat())
    cal = get_stress_calibration()
    dat_val = payload.get("dat")
    if dat_val is None:
        dat_val = compute_days_after_transplant(cal.get("transplant_date", "2026-10-16"), applied_at)

    zone_id = int(payload["zone_id"]) if payload.get("zone_id") not in (None, "", 0, "0") else None
    sensor_id = int(payload["sensor_id"]) if payload.get("sensor_id") not in (None, "", 0, "0") else None
    if sensor_id is not None and zone_id is None and sensor_id in SENSORS:
        zone_id = int(SENSORS[sensor_id]["zone_id"])

    target_scope = str(payload.get("target_scope") or ("plot" if sensor_id else ("zone" if zone_id else "all_lines")))

    profiles_by_zid = {p["zone_id"]: p for p in get_line_treatment_profiles()}
    default_code = profiles_by_zid[zone_id]["treatment_code"] if zone_id in profiles_by_zid else "ALL-LINES"
    treatment_code = str(payload.get("treatment_code") or default_code)

    h2s_dose_um = float(payload.get("h2s_dose_um") or 0.0)
    h2s_applied = 1 if (payload.get("h2s_applied") or h2s_dose_um > 0) else 0
    h2s_stock_ml_per_l = float(payload.get("h2s_stock_ml_per_l") or 0.0)
    h2s_solution_vol_l = float(payload.get("h2s_solution_vol_l") or 0.0)
    measured_dripper_h2s_um = (
        float(payload["measured_dripper_h2s_um"])
        if payload.get("measured_dripper_h2s_um") not in (None, "")
        else None
    )

    humic_dose_mll = float(payload.get("humic_dose_mll") or 0.0)
    humic_applied = 1 if (payload.get("humic_applied") or humic_dose_mll > 0) else 0
    humic_product = str(payload.get("humic_product") or "LIQHUMUS Liquid 18 (NK)")
    humic_total_ml = float(payload.get("humic_total_ml") or round(humic_dose_mll * h2s_solution_vol_l, 2))
    nutrient_match_applied = 1 if payload.get("nutrient_match_applied", True) else 0

    nacl_dose_mm = float(payload.get("nacl_dose_mm") or 0.0)
    salt_applied = 1 if (payload.get("salt_applied") or nacl_dose_mm > 0) else 0
    # Molecular weight of NaCl = 58.44 g/mol -> 100 mM = 5.844 g/L
    salt_amount_g_per_l = (
        float(payload["salt_amount_g_per_l"])
        if payload.get("salt_amount_g_per_l") not in (None, "")
        else round(nacl_dose_mm * 0.05844, 3)
    )

    supplied_solution_ec_uscm = (
        int(float(payload["supplied_solution_ec_uscm"]))
        if payload.get("supplied_solution_ec_uscm") not in (None, "")
        else None
    )
    supplied_solution_ph = (
        float(payload["supplied_solution_ph"])
        if payload.get("supplied_solution_ph") not in (None, "")
        else None
    )
    drainage_fraction_pct = (
        float(payload["drainage_fraction_pct"])
        if payload.get("drainage_fraction_pct") not in (None, "")
        else None
    )
    drainage_ec_uscm = (
        int(float(payload["drainage_ec_uscm"]))
        if payload.get("drainage_ec_uscm") not in (None, "")
        else None
    )
    drainage_ph = (
        float(payload["drainage_ph"])
        if payload.get("drainage_ph") not in (None, "")
        else None
    )
    notes = str(payload.get("notes") or "")
    recorded_by = str(payload.get("recorded_by") or "Mamunur Reza")

    with get_conn() as conn:
        cur = conn.cursor()
        _exec(
            cur,
            """
            INSERT INTO treatment_applications (
                app_id, applied_at, dat, zone_id, sensor_id, target_scope, treatment_code,
                h2s_applied, h2s_dose_um, h2s_stock_ml_per_l, h2s_solution_vol_l, measured_dripper_h2s_um,
                humic_applied, humic_product, humic_dose_mll, humic_total_ml, nutrient_match_applied,
                salt_applied, nacl_dose_mm, salt_amount_g_per_l,
                supplied_solution_ec_uscm, supplied_solution_ph,
                drainage_fraction_pct, drainage_ec_uscm, drainage_ph,
                notes, recorded_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                app_id,
                applied_at,
                int(dat_val) if dat_val is not None else None,
                zone_id,
                sensor_id,
                target_scope,
                treatment_code,
                h2s_applied,
                h2s_dose_um,
                h2s_stock_ml_per_l,
                h2s_solution_vol_l,
                measured_dripper_h2s_um,
                humic_applied,
                humic_product,
                humic_dose_mll,
                humic_total_ml,
                nutrient_match_applied,
                salt_applied,
                nacl_dose_mm,
                salt_amount_g_per_l,
                supplied_solution_ec_uscm,
                supplied_solution_ph,
                drainage_fraction_pct,
                drainage_ec_uscm,
                drainage_ph,
                notes,
                recorded_by,
            ),
        )

    # If the researcher logged a solution or drainage pH and requested updating line reference pH
    ref_ph_candidate = drainage_ph if drainage_ph is not None else supplied_solution_ph
    if ref_ph_candidate is not None and payload.get("update_line_ref_ph", True):
        if zone_id in ZONES:
            update_line_treatment_profile(zone_id, {"ref_soil_ph": ref_ph_candidate})
        elif target_scope == "all_lines":
            for zid in ZONES:
                update_line_treatment_profile(zid, {"ref_soil_ph": ref_ph_candidate})

    return {
        "app_id": app_id,
        "applied_at": applied_at,
        "dat": dat_val,
        "zone_id": zone_id,
        "sensor_id": sensor_id,
        "target_scope": target_scope,
        "treatment_code": treatment_code,
        "h2s_applied": bool(h2s_applied),
        "h2s_dose_um": h2s_dose_um,
        "h2s_stock_ml_per_l": h2s_stock_ml_per_l,
        "h2s_solution_vol_l": h2s_solution_vol_l,
        "measured_dripper_h2s_um": measured_dripper_h2s_um,
        "humic_applied": bool(humic_applied),
        "humic_product": humic_product,
        "humic_dose_mll": humic_dose_mll,
        "humic_total_ml": humic_total_ml,
        "nutrient_match_applied": bool(nutrient_match_applied),
        "salt_applied": bool(salt_applied),
        "nacl_dose_mm": nacl_dose_mm,
        "salt_amount_g_per_l": salt_amount_g_per_l,
        "supplied_solution_ec_uscm": supplied_solution_ec_uscm,
        "supplied_solution_ph": supplied_solution_ph,
        "drainage_fraction_pct": drainage_fraction_pct,
        "drainage_ec_uscm": drainage_ec_uscm,
        "drainage_ph": drainage_ph,
        "notes": notes,
        "recorded_by": recorded_by,
    }


def get_treatment_applications(
    zone_id: Optional[int] = None,
    sensor_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    """Query treatment application logs ordered by applied_at DESC."""
    clauses: List[str] = []
    params: List[Any] = []
    if zone_id is not None:
        clauses.append("(zone_id = ? OR zone_id IS NULL)")
        params.append(int(zone_id))
    if sensor_id is not None:
        zid_for_sensor = SENSORS.get(int(sensor_id), {}).get("zone_id")
        clauses.append("(sensor_id = ? OR (sensor_id IS NULL AND (zone_id = ? OR zone_id IS NULL)))")
        params.extend([int(sensor_id), zid_for_sensor])
    if start_date:
        clauses.append("applied_at >= ?")
        params.append(str(start_date))
    if end_date:
        clauses.append("applied_at <= ?")
        params.append(str(end_date))

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"SELECT * FROM treatment_applications {where_sql} ORDER BY applied_at DESC LIMIT ?"
    params.append(int(limit))

    with get_conn() as conn:
        cur = conn.cursor()
        _exec(cur, sql, tuple(params))
        rows = _fetchall_dicts(cur)

    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append({
            **r,
            "h2s_applied": bool(r.get("h2s_applied")),
            "humic_applied": bool(r.get("humic_applied")),
            "nutrient_match_applied": bool(r.get("nutrient_match_applied")),
            "salt_applied": bool(r.get("salt_applied")),
        })
    return out


def delete_treatment_application(app_id: str) -> bool:
    """Delete a treatment application entry by app_id."""
    with get_conn() as conn:
        cur = conn.cursor()
        _exec(cur, "DELETE FROM treatment_applications WHERE app_id = ?", (str(app_id),))
        return (cur.rowcount or 0) > 0


def add_research_note(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Insert a new persistent research note into the research_notes database table."""
    note_id = str(payload.get("note_id") or f"note-{uuid.uuid4().hex[:12]}")
    now_iso = datetime.now(timezone.utc).isoformat()
    recorded_at = str(payload.get("recorded_at") or now_iso)
    cal = get_stress_calibration()
    dat_val = payload.get("dat")
    if dat_val is None:
        dat_val = compute_days_after_transplant(cal.get("transplant_date", "2026-10-16"), recorded_at)

    zone_id = int(payload["zone_id"]) if payload.get("zone_id") not in (None, "", 0, "0") else None
    sensor_id = int(payload["sensor_id"]) if payload.get("sensor_id") not in (None, "", 0, "0") else None
    if sensor_id is not None and zone_id is None and sensor_id in SENSORS:
        zone_id = int(SENSORS[sensor_id]["zone_id"])

    profiles_by_zid = {p["zone_id"]: p for p in get_line_treatment_profiles()}
    default_code = profiles_by_zid[zone_id]["treatment_code"] if zone_id in profiles_by_zid else "ALL-LINES"
    treatment_code = str(payload.get("treatment_code") or default_code)
    category = str(payload.get("category") or "observation")
    severity_or_tag = str(payload.get("severity_or_tag") or "normal")
    title = str(payload.get("title") or "Research Observation").strip()
    content = str(payload.get("content") or "").strip()
    author = str(payload.get("author") or "Mamunur Reza").strip()
    pinned_on_chart = 1 if payload.get("pinned_on_chart", True) else 0

    with get_conn() as conn:
        cur = conn.cursor()
        _exec(
            cur,
            """
            INSERT INTO research_notes (
                note_id, recorded_at, dat, zone_id, sensor_id, treatment_code,
                category, severity_or_tag, title, content, author,
                pinned_on_chart, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                note_id,
                recorded_at,
                int(dat_val) if dat_val is not None else None,
                zone_id,
                sensor_id,
                treatment_code,
                category,
                severity_or_tag,
                title,
                content,
                author,
                pinned_on_chart,
                now_iso,
                now_iso,
            ),
        )

    return {
        "note_id": note_id,
        "recorded_at": recorded_at,
        "dat": dat_val,
        "zone_id": zone_id,
        "sensor_id": sensor_id,
        "treatment_code": treatment_code,
        "category": category,
        "severity_or_tag": severity_or_tag,
        "title": title,
        "content": content,
        "author": author,
        "pinned_on_chart": bool(pinned_on_chart),
        "created_at": now_iso,
        "updated_at": now_iso,
    }


def update_research_note(note_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update an existing research note in the database."""
    with get_conn() as conn:
        cur = conn.cursor()
        _exec(cur, "SELECT * FROM research_notes WHERE note_id = ?", (str(note_id),))
        rows = _fetchall_dicts(cur)
        if not rows:
            return None
        current = rows[0]

        now_iso = datetime.now(timezone.utc).isoformat()
        recorded_at = str(payload.get("recorded_at") or current["recorded_at"])
        zone_id = (
            int(payload["zone_id"])
            if "zone_id" in payload and payload["zone_id"] not in (None, "", 0, "0")
            else (None if "zone_id" in payload and payload["zone_id"] in (None, "", 0, "0") else current.get("zone_id"))
        )
        sensor_id = (
            int(payload["sensor_id"])
            if "sensor_id" in payload and payload["sensor_id"] not in (None, "", 0, "0")
            else (None if "sensor_id" in payload and payload["sensor_id"] in (None, "", 0, "0") else current.get("sensor_id"))
        )
        treatment_code = str(payload.get("treatment_code") if payload.get("treatment_code") is not None else current.get("treatment_code") or "ALL-LINES")
        category = str(payload.get("category") or current.get("category") or "observation")
        severity_or_tag = str(payload.get("severity_or_tag") or current.get("severity_or_tag") or "normal")
        title = str(payload.get("title") if payload.get("title") is not None else current.get("title") or "").strip()
        content = str(payload.get("content") if payload.get("content") is not None else current.get("content") or "").strip()
        author = str(payload.get("author") or current.get("author") or "Mamunur Reza").strip()
        pinned_on_chart = (
            (1 if payload["pinned_on_chart"] else 0)
            if "pinned_on_chart" in payload and payload["pinned_on_chart"] is not None
            else int(current.get("pinned_on_chart", 1))
        )

        _exec(
            cur,
            """
            UPDATE research_notes
            SET recorded_at = ?,
                zone_id = ?,
                sensor_id = ?,
                treatment_code = ?,
                category = ?,
                severity_or_tag = ?,
                title = ?,
                content = ?,
                author = ?,
                pinned_on_chart = ?,
                updated_at = ?
            WHERE note_id = ?
            """,
            (
                recorded_at,
                zone_id,
                sensor_id,
                treatment_code,
                category,
                severity_or_tag,
                title,
                content,
                author,
                pinned_on_chart,
                now_iso,
                str(note_id),
            ),
        )
        _exec(cur, "SELECT * FROM research_notes WHERE note_id = ?", (str(note_id),))
        updated_rows = _fetchall_dicts(cur)
        if not updated_rows:
            return None
        r = updated_rows[0]
        return {
            **r,
            "pinned_on_chart": bool(r.get("pinned_on_chart")),
        }


def get_research_notes(
    zone_id: Optional[int] = None,
    sensor_id: Optional[int] = None,
    category: Optional[str] = None,
    pinned_only: bool = False,
    search: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    """Query persistent research notes from the database ordered by recorded_at DESC."""
    clauses: List[str] = []
    params: List[Any] = []
    if zone_id is not None:
        clauses.append("(zone_id = ? OR zone_id IS NULL)")
        params.append(int(zone_id))
    if sensor_id is not None:
        zid_for_sensor = SENSORS.get(int(sensor_id), {}).get("zone_id")
        clauses.append("(sensor_id = ? OR (sensor_id IS NULL AND (zone_id = ? OR zone_id IS NULL)))")
        params.extend([int(sensor_id), zid_for_sensor])
    if category:
        clauses.append("category = ?")
        params.append(str(category))
    if pinned_only:
        clauses.append("pinned_on_chart = 1")
    if start_date:
        clauses.append("recorded_at >= ?")
        params.append(str(start_date))
    if end_date:
        clauses.append("recorded_at <= ?")
        params.append(str(end_date))
    if search:
        clauses.append("(LOWER(title) LIKE ? OR LOWER(content) LIKE ? OR LOWER(treatment_code) LIKE ?)")
        like_pat = f"%{search.strip().lower()}%"
        params.extend([like_pat, like_pat, like_pat])

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"SELECT * FROM research_notes {where_sql} ORDER BY recorded_at DESC LIMIT ?"
    params.append(int(limit))

    with get_conn() as conn:
        cur = conn.cursor()
        _exec(cur, sql, tuple(params))
        rows = _fetchall_dicts(cur)

    return [
        {
            **r,
            "pinned_on_chart": bool(r.get("pinned_on_chart")),
        }
        for r in rows
    ]


def delete_research_note(note_id: str) -> bool:
    """Delete a research note from the database by note_id."""
    with get_conn() as conn:
        cur = conn.cursor()
        _exec(cur, "DELETE FROM research_notes WHERE note_id = ?", (str(note_id),))
        return (cur.rowcount or 0) > 0

