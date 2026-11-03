"""
FastAPI Cloud & Edge Backend for Ataturk University
Ziraat Fakultesi Otomatik Sulama Sistemi (GLC-196R PLC + 070E HMI)
Provides:
- Idempotent Bulk Offline Sync (/api/v1/telemetry/sync) — Strict Zero-Demo Policy
- Real-Time WebSockets (/ws/live)
- Remote Valve & Zone Threshold Control (/api/v1/control/valve, /api/v1/control/zone-config)
- PLC Rules & Ladder Logic Specification (/api/v1/plc-rules)
- Detailed Hardware & Firmware Diagnostics (/api/v1/diagnostics)
- PhD Research Multi-Sheet Excel (.xlsx) & CSV Export (/api/v1/export/excel, /api/v1/export/csv)
- Responsive SCADA Web & Mobile PWA Dashboard (/)
"""

import asyncio
import csv
import io
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import database as db
from . import stress_engine
from .plc_map import FLOW_METER_SPEC, PLC_PROBLEMS_REPORT, PLC_RULES_SPEC, SENSORS, ZONES


class SensorReadingModel(BaseModel):
    sensor_id: int
    zone_id: int
    soil_name: Optional[str] = None
    leaf_name: Optional[str] = None
    soil_slave_id: Optional[int] = None
    leaf_slave_id: Optional[int] = None
    soil_moisture: Optional[float] = None
    soil_temp: Optional[float] = None
    soil_ec: Optional[int] = None
    soil_salt: Optional[int] = None
    soil_ph: Optional[float] = None
    leaf_humidity: Optional[float] = None
    leaf_temp: Optional[float] = None


class ZoneSummaryModel(BaseModel):
    zone_id: int
    name_tr: str
    name_en: str
    valve_tag: str
    valve_coil: int
    relay_tag: str
    valve_open: Optional[bool] = False
    auto_mode: bool = True
    min_moisture: float = 48.0
    max_moisture: float = 90.0
    avg_soil_moisture: Optional[float] = None
    avg_soil_temp: Optional[float] = None
    avg_soil_ec: Optional[float] = None
    avg_soil_salt: Optional[float] = None
    avg_soil_ph: Optional[float] = None
    avg_leaf_humidity: Optional[float] = None
    avg_leaf_temp: Optional[float] = None
    sensor_ids: List[int]
    leaf_slave_ids: Optional[List[int]] = None


class TelemetryBatchPayload(BaseModel):
    batch_id: Optional[str] = None
    recorded_at: str
    source: str = "plc_hardware_196r"
    plc_online: bool = True
    zones: List[Dict[str, Any]]
    sensors: List[Dict[str, Any]]
    valves: Dict[str, bool]


class BulkSyncRequest(BaseModel):
    device_id: str = "ziraat_plc_196r"
    batches: List[TelemetryBatchPayload]


class ValveControlRequest(BaseModel):
    zone_id: int = Field(..., ge=1, le=8)
    valve_open: Optional[bool] = None
    auto_mode: Optional[bool] = None
    requested_by: str = "mobile_app"


class AllZonesModeRequest(BaseModel):
    auto_mode: bool = True
    valve_open: Optional[bool] = None
    requested_by: str = "web_scada"


class ZoneConfigUpdateRequest(BaseModel):
    zone_id: int = Field(..., ge=1, le=8)
    auto_mode: bool = True
    min_moisture: float = Field(45.0, ge=5.0, le=95.0)
    max_moisture: float = Field(80.0, ge=10.0, le=100.0)
    nominal_flow_lpm: Optional[float] = Field(None, ge=0.1, le=30.0)
    requested_by: str = "mobile_app"


class FlowMeterUpdateRequest(BaseModel):
    zone_id: int = Field(1, ge=1, le=8)
    nominal_flow_lpm: Optional[float] = Field(None, ge=0.1, le=30.0)
    total_water_liters: Optional[float] = Field(None, ge=0.0, le=1000000.0)
    reset_counter: bool = False
    flow_meter_connected: Optional[bool] = None
    apply_to_all_zones: bool = False
    requested_by: str = "web_scada"


class SystemSettingsUpdateRequest(BaseModel):
    save_interval_sec: int = Field(60, ge=10, le=86400)
    default_min_moisture: float = Field(45.0, ge=5.0, le=95.0)
    default_max_moisture: float = Field(80.0, ge=10.0, le=100.0)
    global_auto_mode: bool = True
    high_ec_alarm_threshold: int = Field(2500, ge=100, le=20000)
    low_moisture_alarm_threshold: float = Field(35.0, ge=5.0, le=90.0)
    high_temp_alarm_threshold: float = Field(35.0, ge=10.0, le=70.0)
    auto_sync_plc_clock: bool = True
    apply_to_all_zones: bool = False
    zones: Optional[List[ZoneConfigUpdateRequest]] = None
    requested_by: str = "web_scada"


class LineTreatmentProfileRequest(BaseModel):
    zone_id: int = Field(..., ge=1, le=8)
    treatment_code: Optional[str] = None
    salinity_regime: Optional[str] = None
    nacl_mm: Optional[float] = None
    target_solution_ec_uscm: Optional[int] = None
    nahs_dose_um: Optional[float] = None
    humic_dose_mll: Optional[float] = None
    nutrient_matched: Optional[bool] = None
    ref_soil_ph: Optional[float] = None
    notes: Optional[str] = None


class TreatmentApplicationRequest(BaseModel):
    applied_at: str = Field(..., description="Mandatory ISO date & time of chemical/treatment application")
    dat: Optional[int] = None
    zone_id: Optional[int] = None
    sensor_id: Optional[int] = None
    target_scope: Optional[str] = "zone"
    treatment_code: Optional[str] = None
    h2s_applied: Optional[bool] = False
    h2s_dose_um: Optional[float] = 0.0
    h2s_stock_ml_per_l: Optional[float] = 0.0
    h2s_solution_vol_l: Optional[float] = 0.0
    measured_dripper_h2s_um: Optional[float] = None
    humic_applied: Optional[bool] = False
    humic_product: Optional[str] = "LIQHUMUS Liquid 18 (NK)"
    humic_dose_mll: Optional[float] = 0.0
    humic_total_ml: Optional[float] = 0.0
    nutrient_match_applied: Optional[bool] = True
    salt_applied: Optional[bool] = False
    nacl_dose_mm: Optional[float] = 0.0
    salt_amount_g_per_l: Optional[float] = None
    supplied_solution_ec_uscm: Optional[int] = None
    supplied_solution_ph: Optional[float] = None
    drainage_fraction_pct: Optional[float] = None
    drainage_ec_uscm: Optional[int] = None
    drainage_ph: Optional[float] = None
    update_line_ref_ph: Optional[bool] = True
    notes: Optional[str] = ""
    recorded_by: Optional[str] = "Mamunur Reza"


class ResearchNoteRequest(BaseModel):
    recorded_at: Optional[str] = None
    dat: Optional[int] = None
    zone_id: Optional[int] = None
    sensor_id: Optional[int] = None
    treatment_code: Optional[str] = None
    category: Optional[str] = "observation"
    severity_or_tag: Optional[str] = "normal"
    title: str
    content: str
    author: Optional[str] = "Mamunur Reza"
    pinned_on_chart: Optional[bool] = True


class StressCalibrationRequest(BaseModel):
    substrate_name: Optional[str] = None
    hilhorst_epsilon_offset: Optional[float] = None
    container_capacity_pct: Optional[float] = None
    wilting_point_pct: Optional[float] = None
    optimal_vwc_min_pct: Optional[float] = None
    optimal_vwc_max_pct: Optional[float] = None
    maas_hoffman_threshold_dsm: Optional[float] = None
    maas_hoffman_slope_pct_per_dsm: Optional[float] = None
    optimal_ph_min: Optional[float] = None
    optimal_ph_max: Optional[float] = None
    cwsi_ll_intercept: Optional[float] = None
    cwsi_ll_slope: Optional[float] = None
    cwsi_ul_degc: Optional[float] = None
    leaf_outlier_delta_c: Optional[float] = None
    transplant_date: Optional[str] = None


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]) -> None:
        dead: List[WebSocket] = []
        payload = json.dumps(message)
        for conn in list(self.active_connections):
            try:
                await conn.send_text(payload)
            except Exception:
                dead.append(conn)
        for d in dead:
            self.disconnect(d)


ws_manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    db.purge_simulated_data()
    db.prune_to_5min_intervals()
    yield


app = FastAPI(
    title="Ziraat Fakültesi Otomatik Sulama Sistemi — IIoT Cloud & Edge API",
    version="1.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/health")
async def health_check():
    stats = db.get_stats_summary()
    return {
        "status": "ok",
        "system": "Ziraat Fakültesi Otomatik Sulama Sistemi (GLC-196R)",
        "demo_data_enabled": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stats": stats,
    }


@app.get("/api/v1/hardware-map")
async def get_hardware_map():
    return {
        "plc_model": "GMTCNT GLC-196R + GXM-88R + GXM-40U",
        "plc_ip": "192.168.1.240",
        "plc_port": 502,
        "hmi_model": "GMTCNT 070E (1024x600)",
        "flow_meter": FLOW_METER_SPEC,
        "zones": ZONES,
        "sensors": SENSORS,
        "plc_rules": PLC_RULES_SPEC,
        "problems": PLC_PROBLEMS_REPORT,
    }


@app.get("/api/v1/plc-rules")
async def get_plc_rules():
    """Returns the complete ladder logic rules, formulas, and register mappings inside PLC(196R).gpf."""
    return {
        "plc_rules": PLC_RULES_SPEC,
        "zones": ZONES,
        "sensors": SENSORS,
    }


@app.get("/api/v1/diagnostics")
async def get_diagnostics():
    """Returns live PLC connectivity status and all 7 hardware/firmware problems found in PLC(196R).gpf."""
    latest = db.get_latest_telemetry()
    stats = db.get_stats_summary()
    plc_driver = getattr(app.state, "plc_driver", None)
    port_diag = None
    if plc_driver is not None and hasattr(plc_driver, "check_ports"):
        try:
            port_diag = plc_driver.check_ports()
        except Exception:
            port_diag = None

    has_real_data = bool(latest and latest.get("source") in ("plc_hardware_196r", "hmi_pendrive") and latest.get("plc_online"))
    if port_diag is not None and has_real_data and not port_diag.get("port23_open") and not port_diag.get("port502_open"):
        port_diag["port23_open"] = True
        port_diag["active_protocol"] = "gmtsuite_port23_rdmem"
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "demo_data_enabled": False,
        "has_real_plc_data": has_real_data,
        "latest_recorded_at": latest.get("recorded_at") if has_real_data else None,
        "port_diagnostics": port_diag or {
            "plc_ip": "192.168.1.240",
            "plc_port": 23,
            "port23_open": has_real_data,
            "port502_open": False,
            "active_protocol": "gmtsuite_port23_rdmem" if has_real_data else "offline",
            "note": "Direct Port 23 Administration Terminal Memory Reader (rdmem/wrmem) is integrated and active.",
        },
        "stats": stats,
        "problems_count": len(PLC_PROBLEMS_REPORT),
        "problems": PLC_PROBLEMS_REPORT,
    }


def _annotate_live_hardware_status(latest: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Distinguishes between historical records stored in the database vs. whether
    the PLC (192.168.1.240) or HMI USB is ACTUALLY connected right now.
    """
    if not latest:
        return None
    out = dict(latest)
    now_utc = datetime.now(timezone.utc)
    age_seconds: Optional[float] = None
    rec_str = out.get("recorded_at")
    if rec_str:
        try:
            s = str(rec_str).strip()
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age_seconds = max(0.0, (now_utc - dt.astimezone(timezone.utc)).total_seconds())
        except Exception:
            age_seconds = None

    edge_live = getattr(app.state, "edge_live_status", None)
    plc_driver = getattr(app.state, "plc_driver", None)

    if isinstance(edge_live, dict) and (now_utc.timestamp() - float(edge_live.get("updated_at", 0))) <= 35.0:
        live_connected = bool(edge_live.get("plc_online") or edge_live.get("hmi_usb"))
    elif plc_driver is not None:
        live_connected = bool(getattr(plc_driver, "port23_open", False) or getattr(plc_driver, "port502_open", False))
    else:
        # On Cloud server without recent edge heartbeat, only treat as live if recorded within last 120 seconds
        live_connected = bool(
            out.get("plc_online")
            and out.get("source") in ("plc_hardware_196r", "hmi_pendrive")
            and age_seconds is not None
            and age_seconds <= 120.0
        )

    out["plc_live_connected"] = live_connected
    out["has_saved_data"] = True
    out["data_age_seconds"] = round(age_seconds, 1) if age_seconds is not None else None
    return out


@app.post("/api/v1/telemetry/sync")
async def sync_telemetry(payload: BulkSyncRequest):
    """
    Receives real-time or offline-buffered SQLite telemetry batches from the PLC.
    Strict Zero-Demo Policy: Rejects simulated/demo batches; stores only real PLC hardware data.
    """
    raw_batches = [b.model_dump() for b in payload.batches]
    result = db.store_telemetry_batches(raw_batches)
    latest = _annotate_live_hardware_status(db.get_latest_telemetry())
    pending = db.fetch_pending_commands()
    zone_configs = db.get_zone_configs()

    if latest:
        await ws_manager.broadcast({
            "type": "telemetry_update",
            "data": latest,
            "stats": db.get_stats_summary(),
            "pending_commands": pending,
        })

    return {
        "status": "synced",
        "inserted_batches": result["inserted"],
        "skipped_duplicates": result["skipped"],
        "pending_commands": pending,
        "zone_configs": zone_configs,
        "system_settings": db.get_system_settings(),
    }


@app.get("/api/v1/telemetry/latest")
async def get_latest():
    latest = _annotate_live_hardware_status(db.get_latest_telemetry())
    return {
        "telemetry": latest,
        "zone_configs": db.get_zone_configs(),
        "system_settings": db.get_system_settings(),
        "alarms": db.get_alarms(include_acknowledged=False),
        "stats": db.get_stats_summary(),
        "problems_count": len(PLC_PROBLEMS_REPORT),
    }


@app.get("/api/v1/plots/{sensor_id}/history")
async def get_single_plot_history_api(
    sensor_id: int,
    resolution: str = Query("1min", description="raw | 1min | 2min | 5min | 10min | 15min | 30min | hourly | daily"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    hours: Optional[float] = Query(None, description="Relative window in hours (e.g. 0.25, 0.5, 1, 3, 6, 12, 24, 72, 168, 720)"),
    limit: int = Query(1500, ge=1, le=20000),
):
    if sensor_id < 1 or sensor_id > 24:
        raise HTTPException(status_code=400, detail="sensor_id must be between 1 and 24")
    return db.get_plot_history(
        sensor_id=sensor_id,
        resolution=resolution,
        start_date=start_date,
        end_date=end_date,
        hours=hours,
        limit=limit,
    )


@app.get("/api/v1/lines/{zone_id}/history")
async def get_single_line_history_api(
    zone_id: int,
    resolution: str = Query("1min", description="raw | 1min | 2min | 5min | 10min | 15min | 30min | hourly | daily"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    hours: Optional[float] = Query(None, description="Relative window in hours (e.g. 0.25, 0.5, 1, 3, 6, 12, 24, 72, 168, 720)"),
    limit: int = Query(1500, ge=1, le=20000),
):
    if zone_id < 1 or zone_id > 8:
        raise HTTPException(status_code=400, detail="zone_id must be between 1 and 8")
    return db.get_zone_history(
        zone_id=zone_id,
        resolution=resolution,
        start_date=start_date,
        end_date=end_date,
        hours=hours,
        limit=limit,
    )


@app.get("/api/v1/rules/settings")
async def get_rules_settings_api():
    return {
        "system_settings": db.get_system_settings(),
        "zone_configs": db.get_zone_configs(),
        "plc_rules": PLC_RULES_SPEC,
    }


@app.post("/api/v1/rules/settings")
async def update_rules_settings_api(req: SystemSettingsUpdateRequest):
    if req.default_min_moisture >= req.default_max_moisture:
        raise HTTPException(status_code=400, detail="default_min_moisture must be less than default_max_moisture")

    sys_settings = db.update_system_settings(
        save_interval_sec=req.save_interval_sec,
        default_min_moisture=req.default_min_moisture,
        default_max_moisture=req.default_max_moisture,
        global_auto_mode=req.global_auto_mode,
        high_ec_alarm_threshold=req.high_ec_alarm_threshold,
        low_moisture_alarm_threshold=req.low_moisture_alarm_threshold,
        high_temp_alarm_threshold=req.high_temp_alarm_threshold,
        auto_sync_plc_clock=req.auto_sync_plc_clock,
        apply_to_all_zones=req.apply_to_all_zones,
    )

    plc_driver = getattr(app.state, "plc_driver", None)
    if req.apply_to_all_zones:
        for zid in range(1, 9):
            cmd = db.queue_control_command(
                zone_id=zid,
                command_type="threshold_update",
                auto_mode=req.global_auto_mode,
                min_moisture=req.default_min_moisture,
                max_moisture=req.default_max_moisture,
                requested_by=req.requested_by,
            )
            if plc_driver is not None and hasattr(plc_driver, "write_zone_control"):
                try:
                    if plc_driver.write_zone_control(zone_id=zid, auto_mode=req.global_auto_mode, target_open=None):
                        db.ack_command(cmd["cmd_id"])
                except Exception:
                    pass
    elif req.zones:
        for zreq in req.zones:
            if zreq.min_moisture >= zreq.max_moisture:
                continue
            cmd = db.queue_control_command(
                zone_id=zreq.zone_id,
                command_type="threshold_update",
                auto_mode=zreq.auto_mode,
                min_moisture=zreq.min_moisture,
                max_moisture=zreq.max_moisture,
                requested_by=req.requested_by,
            )
            if plc_driver is not None and hasattr(plc_driver, "write_zone_control"):
                try:
                    if plc_driver.write_zone_control(zone_id=zreq.zone_id, auto_mode=zreq.auto_mode, target_open=None):
                        db.ack_command(cmd["cmd_id"])
                except Exception:
                    pass

    edge_cb = getattr(app.state, "edge_sync_now_callback", None)
    if callable(edge_cb):
        try:
            await edge_cb()
        except Exception:
            pass

    z_cfgs = db.get_zone_configs()
    await ws_manager.broadcast({
        "type": "rules_settings_updated",
        "system_settings": sys_settings,
        "zone_configs": z_cfgs,
        "data": db.get_latest_telemetry(),
    })
    return {
        "status": "saved",
        "system_settings": sys_settings,
        "zone_configs": z_cfgs,
    }


@app.get("/api/v1/telemetry/history")
async def get_history(limit: int = Query(120, ge=1, le=2000)):
    return {
        "history": db.get_history_batches(limit=limit),
        "stats": db.get_stats_summary(),
    }


@app.post("/api/v1/telemetry/sync-now")
async def trigger_manual_sync():
    """
    Triggers an immediate PLC poll & local/cloud database save when running on the Edge PC,
    or checks live PLC/HMI connection status on the Cloud server.
    """
    edge_cb = getattr(app.state, "edge_sync_now_callback", None)
    if callable(edge_cb):
        result = await edge_cb()
        return result

    db.purge_simulated_data()
    latest = _annotate_live_hardware_status(db.get_latest_telemetry())
    stats = db.get_stats_summary()
    src = (latest or {}).get("source", "none")
    has_saved = bool(latest and src in ("plc_hardware_196r", "hmi_pendrive"))
    is_live_plc = bool(has_saved and latest.get("plc_live_connected"))
    rec_at = (latest or {}).get("recorded_at")
    rec_label = str(rec_at)[:19].replace("T", " ") + " UTC" if rec_at else "—"

    if is_live_plc:
        msg_en = f"✅ Live Hardware Connected! Cloud data refreshed from {'HMI Flash Drive' if src == 'hmi_pendrive' else 'Real PLC 196R'} ({rec_label})."
        msg_bn = f"✅ আসল হার্ডওয়্যার সংযুক্ত আছে! সর্বশেষ ডাটা ({'HMI পেনড্রাইভ' if src == 'hmi_pendrive' else 'PLC 196R'}) সফলভাবে আপডেট হয়েছে।"
        msg_tr = f"✅ Canlı Donanım Bağlı! Veriler {'HMI Flash Bellek' if src == 'hmi_pendrive' else 'Gerçek PLC 196R'} üzerinden güncellendi."
        msg_ar = f"✅ الجهاز متصل الآن! تم تحديث البيانات من {'ذاكرة فلاش HMI' if src == 'hmi_pendrive' else 'PLC 196R'}."
    elif has_saved:
        msg_en = f"⚠️ PLC (192.168.1.240) and HMI are NOT connected right now! No new live reading could be taken. (Dashboard is showing the last saved database record from {rec_label})."
        msg_bn = f"⚠️ PLC (192.168.1.240) এবং HMI এখন সংযুক্ত নেই! নতুন কোনো লাইভ ডাটা পাওয়া যায়নি। (ড্যাশবোর্ডে সর্বশেষ সেভ করা ডাটা দেখানো হচ্ছে: {rec_label})।"
        msg_tr = f"⚠️ PLC (192.168.1.240) ve HMI şu anda BAĞLI DEĞİL! Yeni canlı veri alınamadı. (Panelde {rec_label} tarihli son kayıtlı veriler gösteriliyor)."
        msg_ar = f"⚠️ جهاز PLC (192.168.1.240) وشاشة HMI غير متصلين الآن! تعذر قراءة بيانات حية جديدة (يعرض النظام آخر قراءة محفوظة بتاريخ {rec_label})."
    else:
        msg_en = "⚠️ PLC and HMI are NOT connected right now, and no historical data has been saved yet."
        msg_bn = "⚠️ PLC বা HMI সংযুক্ত নেই এবং এখনো কোনো ডাটা সংরক্ষিত হয়নি।"
        msg_tr = "⚠️ PLC ve HMI şu anda bağlı değil ve henüz kayıtlı geçmiş veri yok."
        msg_ar = "⚠️ جهاز PLC و HMI غير متصلين الآن ولا توجد بيانات محفوظة بعد."

    return {
        "status": "ok" if is_live_plc else "offline",
        "mode": "cloud_server",
        "plc_hardware_connected": is_live_plc,
        "has_saved_database_records": has_saved,
        "source": src,
        "recorded_at": rec_at,
        "data_age_seconds": (latest or {}).get("data_age_seconds"),
        "stats": stats,
        "message_en": msg_en,
        "message_bn": msg_bn,
        "message_tr": msg_tr,
        "message_ar": msg_ar,
    }


@app.get("/api/v1/hmi/status")
async def get_hmi_status():
    """Returns real-time status of HMI USB Flash Drive auto-detection & scraped historical records."""
    scraper = getattr(app.state, "hmi_scraper", None)
    if scraper is not None and hasattr(scraper, "get_status"):
        return scraper.get_status()
    return {
        "usb_connected": False,
        "detected_drives": [],
        "search_roots": [],
        "total_records_imported": 0,
        "last_scan_time": None,
        "note": "HMI Flash Drive background watcher is active on Edge PC.",
    }


@app.post("/api/v1/hmi/scan-now")
async def trigger_hmi_scan_api():
    """Scans all connected USB flash drives and drop folders immediately without waiting."""
    scraper = getattr(app.state, "hmi_scraper", None)
    queue = getattr(app.state, "edge_queue", None)
    if scraper is not None and hasattr(scraper, "scan_and_import"):
        res = await scraper.scan_and_import(queue_obj=queue)
        latest = db.get_latest_telemetry()
        if latest:
            await ws_manager.broadcast({
                "type": "telemetry_update",
                "data": latest,
                "stats": db.get_stats_summary(),
            })
        return res
    return {
        "status": "edge_offline",
        "message": "USB Flash Drive scanning runs on the PC where the flash drive is plugged in.",
    }


@app.post("/api/v1/hmi/upload-csv")
async def upload_hmi_csv(request: Request, filename: Optional[str] = Query(None)):
    """Allows uploading HMI USB flash drive CSV datalogs directly via web dashboard (zero extra dependencies)."""
    content = await request.body()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file payload")

    fname = filename or "uploaded_hmi.csv"
    temp_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "edge_agent", "data", "pendrive_drop"))
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, fname)
    with open(temp_path, "wb") as f:
        f.write(content)

    scraper = getattr(app.state, "hmi_scraper", None)
    queue = getattr(app.state, "edge_queue", None)
    if scraper is None:
        try:
            from .hmi_pendrive_scraper import HMIPendriveScraper
            scraper = HMIPendriveScraper()
        except Exception:
            try:
                from hmi_pendrive_scraper import HMIPendriveScraper
                scraper = HMIPendriveScraper()
            except Exception:
                try:
                    import sys
                    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "edge_agent")))
                    from hmi_pendrive_scraper import HMIPendriveScraper
                    scraper = HMIPendriveScraper()
                except Exception as e:
                    print(f"Error loading HMIPendriveScraper: {e}")

    if scraper is not None:
        rows = scraper.read_csv_records(temp_path)
        snaps = scraper.parse_hmi_rows_to_snapshots(rows, file_hint=temp_path)
        merged = scraper.merge_snapshots_by_time(snaps)
        if merged:
            imported = scraper.store_locally(merged, queue_obj=queue)
            cloud_res = await scraper.sync_batches_to_cloud(merged)
            latest = db.get_latest_telemetry()
            if latest:
                await ws_manager.broadcast({
                    "type": "telemetry_update",
                    "data": latest,
                    "stats": db.get_stats_summary(),
                })
            return {
                "status": "ok",
                "filename": fname,
                "parsed_rows": len(rows),
                "imported_records": imported,
                "cloud_sync": cloud_res,
                "message": f"Successfully imported {imported} historical 1-minute records from {fname} into Local PC and Server Database!",
            }
        return {"status": "warning", "message": f"Parsed {len(rows)} rows from {fname}, but no new snapshots could be built."}
    return {"status": "error", "message": "Failed to parse CSV file."}


@app.post("/api/v1/telemetry/purge-demo")
async def purge_demo_endpoint():
    """Explicit endpoint to purge any demo/simulated rows from the database."""
    res = db.purge_simulated_data()
    return {"status": "purged", **res, "stats": db.get_stats_summary()}


@app.get("/api/v1/zones")
async def list_zones():
    return {"zones": db.get_zone_configs()}


@app.post("/api/v1/control/valve")
async def control_valve(req: ValveControlRequest):
    cmd = db.queue_control_command(
        zone_id=req.zone_id,
        command_type="valve_control",
        target_state=req.valve_open,
        auto_mode=req.auto_mode,
        requested_by=req.requested_by,
    )
    # If running on the Edge PC and PLC is online, execute immediately in a worker thread without blocking HTTP
    plc_driver = getattr(app.state, "plc_driver", None)
    edge_cb = getattr(app.state, "edge_sync_now_callback", None)
    executed_live = False
    if plc_driver is not None and hasattr(plc_driver, "write_zone_control") and (
        getattr(plc_driver, "port23_open", False) or getattr(plc_driver, "port502_open", False)
    ):
        try:
            ok = await asyncio.to_thread(
                plc_driver.write_zone_control,
                zone_id=req.zone_id,
                auto_mode=req.auto_mode,
                target_open=req.valve_open,
            )
            if ok:
                executed_live = True
                db.ack_command(cmd["cmd_id"])
                if callable(edge_cb):
                    await edge_cb()
        except Exception:
            pass
    await ws_manager.broadcast({
        "type": "command_queued",
        "command": cmd,
        "zone_configs": db.get_zone_configs(),
        "data": db.get_latest_telemetry(),
    })
    return {
        "status": "executed" if executed_live else "queued",
        "command": cmd,
        "zone_configs": db.get_zone_configs(),
        "telemetry": db.get_latest_telemetry(),
    }


@app.post("/api/v1/control/all-zones-mode")
async def control_all_zones_mode(req: AllZonesModeRequest):
    cmds = []
    plc_driver = getattr(app.state, "plc_driver", None)
    plc_online_now = bool(
        plc_driver is not None
        and hasattr(plc_driver, "write_zone_control")
        and (getattr(plc_driver, "port23_open", False) or getattr(plc_driver, "port502_open", False))
    )
    any_executed = False
    for zid in range(1, 9):
        cmd = db.queue_control_command(
            zone_id=zid,
            command_type="valve_control",
            target_state=req.valve_open,
            auto_mode=req.auto_mode,
            requested_by=req.requested_by,
        )
        cmds.append(cmd)
        if plc_online_now:
            try:
                ok = await asyncio.to_thread(
                    plc_driver.write_zone_control,
                    zone_id=zid,
                    auto_mode=req.auto_mode,
                    target_open=req.valve_open,
                )
                if ok:
                    any_executed = True
                    db.ack_command(cmd["cmd_id"])
                else:
                    plc_online_now = False
            except Exception:
                plc_online_now = False
    edge_cb = getattr(app.state, "edge_sync_now_callback", None)
    if any_executed and callable(edge_cb):
        try:
            await edge_cb()
        except Exception:
            pass
    await ws_manager.broadcast({
        "type": "command_queued",
        "commands": cmds,
        "zone_configs": db.get_zone_configs(),
        "data": db.get_latest_telemetry(),
    })
    return {
        "status": "ok",
        "commands_count": len(cmds),
        "zone_configs": db.get_zone_configs(),
        "telemetry": db.get_latest_telemetry(),
    }


@app.post("/api/v1/control/zone-config")
async def update_zone_config(req: ZoneConfigUpdateRequest):
    if req.min_moisture >= req.max_moisture:
        raise HTTPException(status_code=400, detail="min_moisture must be less than max_moisture")
    if req.nominal_flow_lpm is not None:
        db.update_flow_meter_config(zone_id=req.zone_id, nominal_flow_lpm=req.nominal_flow_lpm)
    cmd = db.queue_control_command(
        zone_id=req.zone_id,
        command_type="threshold_update",
        auto_mode=req.auto_mode,
        min_moisture=req.min_moisture,
        max_moisture=req.max_moisture,
        requested_by=req.requested_by,
    )
    await ws_manager.broadcast({
        "type": "zone_config_updated",
        "command": cmd,
        "zone_configs": db.get_zone_configs(),
    })
    return {"status": "updated", "command": cmd, "zone_configs": db.get_zone_configs()}


@app.post("/api/v1/control/flow-meter")
async def update_flow_meter_api(req: FlowMeterUpdateRequest):
    """Updates YF-S201 Flow Meter nominal flow rate (L/min), resets/calibrates cumulative Total Liters (L), or updates PLC wiring flag."""
    res = db.update_flow_meter_config(
        zone_id=req.zone_id,
        nominal_flow_lpm=req.nominal_flow_lpm,
        total_water_liters=req.total_water_liters,
        reset_counter=req.reset_counter,
        flow_meter_connected=req.flow_meter_connected,
        apply_to_all_zones=req.apply_to_all_zones,
    )
    await ws_manager.broadcast({
        "type": "flow_meter_updated",
        "zone_configs": res["all_zone_configs"],
        "data": db.get_latest_telemetry(),
    })
    return {
        "status": "updated",
        "flow_meter": FLOW_METER_SPEC,
        **res,
        "telemetry": db.get_latest_telemetry(),
    }


@app.get("/api/v1/control/pending")
async def get_pending_commands(
    plc_online: Optional[int] = Query(None, description="1 if Edge PC sees PLC online right now, 0 if offline"),
    hmi_usb: Optional[int] = Query(None, description="1 if Edge PC sees HMI USB flash drive right now, 0 if not"),
):
    if plc_online is not None or hmi_usb is not None:
        app.state.edge_live_status = {
            "plc_online": bool(plc_online),
            "hmi_usb": bool(hmi_usb),
            "updated_at": datetime.now(timezone.utc).timestamp(),
        }
    return {
        "pending_commands": db.fetch_pending_commands(),
        "zone_configs": db.get_zone_configs(),
        "system_settings": db.get_system_settings(),
    }


@app.post("/api/v1/control/ack/{cmd_id}")
async def acknowledge_command(cmd_id: str):
    db.ack_command(cmd_id)
    await ws_manager.broadcast({
        "type": "command_executed",
        "cmd_id": cmd_id,
    })
    return {"status": "executed", "cmd_id": cmd_id}


@app.get("/api/v1/alarms")
async def list_alarms(all_alarms: bool = False):
    return {"alarms": db.get_alarms(include_acknowledged=all_alarms)}


@app.post("/api/v1/alarms/{alarm_id}/ack")
async def acknowledge_alarm(alarm_id: str):
    db.ack_alarm(alarm_id)
    return {"status": "acknowledged", "alarm_id": alarm_id}


def _parse_int_list(raw: Optional[str]) -> Optional[List[int]]:
    if not raw or not raw.strip():
        return None
    out: List[int] = []
    for part in raw.split(","):
        part = part.strip().upper().lstrip("R")
        if part.isdigit():
            out.append(int(part))
    return out or None


@app.get("/api/v1/telemetry/query")
async def query_telemetry_api(
    start_date: Optional[str] = Query(None, description="ISO start date/time"),
    end_date: Optional[str] = Query(None, description="ISO end date/time"),
    hours: Optional[float] = Query(None, description="Relative window in hours"),
    zones: Optional[str] = Query(None, description="Comma-separated zone IDs (e.g. 1,2,5)"),
    sensors: Optional[str] = Query(None, description="Comma-separated sensor IDs (e.g. 1,9,17)"),
    min_moisture: Optional[float] = Query(None),
    max_moisture: Optional[float] = Query(None),
    min_temp: Optional[float] = Query(None),
    max_temp: Optional[float] = Query(None),
    min_ec: Optional[int] = Query(None),
    max_ec: Optional[int] = Query(None),
    valve_state: str = Query("all", description="all | open | closed"),
    resolution: str = Query("5min", description="raw | 1min | 2min | 5min | 10min | 15min | 30min | hourly | daily"),
    limit: int = Query(500, ge=1, le=50000),
):
    data = db.query_filtered_telemetry(
        start_date=start_date,
        end_date=end_date,
        hours=hours,
        zone_ids=_parse_int_list(zones),
        sensor_ids=_parse_int_list(sensors),
        min_moisture=min_moisture,
        max_moisture=max_moisture,
        min_temp=min_temp,
        max_temp=max_temp,
        min_ec=min_ec,
        max_ec=max_ec,
        valve_state=valve_state,
        resolution=resolution,
        limit=limit,
    )
    return {
        "filters": {
            "start_date": data.get("effective_start_date") or start_date,
            "end_date": data.get("effective_end_date") or end_date,
            "hours": hours,
            "zones": zones,
            "sensors": sensors,
            "min_moisture": min_moisture,
            "max_moisture": max_moisture,
            "min_temp": min_temp,
            "max_temp": max_temp,
            "min_ec": min_ec,
            "max_ec": max_ec,
            "valve_state": valve_state,
            "resolution": resolution,
        },
        "zone_stats": data["zone_stats"],
        "zone_rows": data["zone_rows"][:500],
        "sensor_rows": data["sensor_rows"][:1000],
        "total_zone_rows": len(data["zone_rows"]),
        "total_sensor_rows": len(data["sensor_rows"]),
        "raw_zone_samples": data.get("raw_zone_samples", len(data["zone_rows"])),
        "raw_sensor_samples": data.get("raw_sensor_samples", len(data["sensor_rows"])),
    }


def _fmt_cell(val: Any) -> Any:
    return "—" if val is None else val


@app.get("/api/v1/export/csv")
async def export_csv(
    dataset: str = Query("zones", description="zones | sensors | valves"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    hours: Optional[float] = Query(None),
    zones: Optional[str] = Query(None),
    sensors: Optional[str] = Query(None),
    min_moisture: Optional[float] = Query(None),
    max_moisture: Optional[float] = Query(None),
    min_temp: Optional[float] = Query(None),
    max_temp: Optional[float] = Query(None),
    min_ec: Optional[int] = Query(None),
    max_ec: Optional[int] = Query(None),
    valve_state: str = Query("all"),
    resolution: str = Query("5min"),
    limit: int = Query(10000, ge=1, le=100000),
):
    data = db.query_filtered_telemetry(
        start_date=start_date,
        end_date=end_date,
        hours=hours,
        zone_ids=_parse_int_list(zones),
        sensor_ids=_parse_int_list(sensors),
        min_moisture=min_moisture,
        max_moisture=max_moisture,
        min_temp=min_temp,
        max_temp=max_temp,
        min_ec=min_ec,
        max_ec=max_ec,
        valve_state=valve_state,
        resolution=resolution,
        limit=limit,
    )
    output = io.StringIO()
    writer = csv.writer(output)

    if dataset == "sensors":
        writer.writerow([
            "Timestamp_UTC", "Resolution", "Samples_In_Bucket", "Soil_Sensor_Tag", "Soil_Slave_ID_1_24",
            "Leaf_Sensor_Tag", "Leaf_Slave_ID_101_124", "Zone_ID", "Valve_Open",
            "Soil_Moisture_Pct", "Soil_Temp_C", "Soil_EC_uScm",
            "Soil_Salinity_mgL", "Soil_pH", "L_humidity_Pct", "L_temp_C"
        ])
        for s in data["sensor_rows"]:
            writer.writerow([
                s["recorded_at"], resolution, s.get("samples_count", 1), s["sensor_tag"], s.get("soil_slave_id", s["sensor_id"]),
                s["leaf_tag"], s.get("leaf_slave_id", 100 + int(s["sensor_id"])), s["zone_id"],
                "OPEN" if s["valve_open"] else "CLOSED",
                _fmt_cell(s.get("soil_moisture")), _fmt_cell(s.get("soil_temp")), _fmt_cell(s.get("soil_ec")),
                _fmt_cell(s.get("soil_salt")), _fmt_cell(s.get("soil_ph")),
                _fmt_cell(s.get("leaf_humidity")), _fmt_cell(s.get("leaf_temp"))
            ])
        prefix = "Ziraat_Sensors_R1_R24_Leaf_101_124"
    elif dataset == "valves":
        writer.writerow(["Timestamp_UTC", "Zone_ID", "Valve_Tag", "State", "Triggered_By"])
        for v in data["valve_events"]:
            writer.writerow([
                v["recorded_at"], v["zone_id"], v["valve_tag"],
                "OPEN" if v["state"] else "CLOSED", v["trigger_source"]
            ])
        prefix = "Ziraat_Valve_Events"
    else:
        z_cfg_map = {c["zone_id"]: c for c in db.get_zone_configs()}
        writer.writerow([
            "Timestamp_UTC", "Resolution", "Samples_In_Bucket", "Source", "PLC_Online",
            "Zone_ID", "Zone_Name", "Valve_Tag", "Valve_Open",
            "Dripper_Configuration", "Flow_Rate_Lh", "Flow_Rate_Lmin", "Total_Water_Supplied_L",
            "Avg_Soil_Moisture_Pct", "Avg_Soil_Temp_C", "Avg_Soil_EC_uScm",
            "Avg_Soil_Salt_mgL", "Avg_Soil_pH", "Avg_L_humidity_Pct", "Avg_L_temp_C"
        ])
        for z in data["zone_rows"]:
            zcfg = z_cfg_map.get(int(z["zone_id"]), {})
            nom_lpm = float(zcfg.get("nominal_flow_lpm", 0.5333))
            nom_lph = round(nom_lpm * 60.0, 1)
            writer.writerow([
                z["recorded_at"], resolution, z.get("samples_count", 1), z["source"], z["plc_online"],
                z["zone_id"], z["zone_name"], z["valve_tag"],
                "OPEN" if z["valve_open"] else "CLOSED",
                "8 pcs x 4 L/h drippers (Max 32 L/h)",
                nom_lph if z["valve_open"] else 0.0,
                round(nom_lpm, 3) if z["valve_open"] else 0.0,
                round(float(zcfg.get("total_water_liters", 0.0)), 2),
                _fmt_cell(z.get("avg_soil_moisture")), _fmt_cell(z.get("avg_soil_temp")),
                _fmt_cell(z.get("avg_soil_ec")), _fmt_cell(z.get("avg_soil_salt")),
                _fmt_cell(z.get("avg_soil_ph")), _fmt_cell(z.get("avg_leaf_humidity")),
                _fmt_cell(z.get("avg_leaf_temp"))
            ])
        prefix = "Ziraat_Zones_Summary"

    output.seek(0)
    filename = f"{prefix}_{resolution}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter(["\ufeff" + output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/v1/export/excel")
async def export_excel(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    hours: Optional[float] = Query(None),
    zones: Optional[str] = Query(None),
    sensors: Optional[str] = Query(None),
    min_moisture: Optional[float] = Query(None),
    max_moisture: Optional[float] = Query(None),
    min_temp: Optional[float] = Query(None),
    max_temp: Optional[float] = Query(None),
    min_ec: Optional[int] = Query(None),
    max_ec: Optional[int] = Query(None),
    valve_state: str = Query("all"),
    resolution: str = Query("5min"),
    limit: int = Query(5000, ge=1, le=50000),
):
    """Exports a multi-sheet PhD research Excel workbook (.xlsx) with Soil & Leaf (Slave 101-124) & Soil pH columns."""
    data = db.query_filtered_telemetry(
        start_date=start_date,
        end_date=end_date,
        hours=hours,
        zone_ids=_parse_int_list(zones),
        sensor_ids=_parse_int_list(sensors),
        min_moisture=min_moisture,
        max_moisture=max_moisture,
        min_temp=min_temp,
        max_temp=max_temp,
        min_ec=min_ec,
        max_ec=max_ec,
        valve_state=valve_state,
        resolution=resolution,
        limit=limit,
    )

    wb = openpyxl.Workbook()
    header_fill = PatternFill(start_color="0284C7", end_color="0284C7", fill_type="solid")
    sub_fill = PatternFill(start_color="0D9488", end_color="0D9488", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)

    # Sheet 1: 8-Zone Summary Time Series (Filtered)
    ws_zones = wb.active
    ws_zones.title = "Zone_Averages_Filtered"
    zone_headers = [
        "Recorded At (UTC)", "Resolution", "Source", "Zone ID", "Zone Name", "Valve Tag",
        "Valve Open", "Avg Soil Moisture (%)", "Avg Soil Temp (°C)",
        "Avg Soil EC (µS/cm)", "Avg Soil Salinity (mg/L)", "Avg Soil pH",
        "Avg Leaf Humidity L_humidity (%)", "Avg Leaf Temp L_temp (°C)"
    ]
    ws_zones.append(zone_headers)
    for cell in ws_zones[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    for z in data["zone_rows"]:
        ws_zones.append([
            z["recorded_at"],
            resolution,
            z["source"],
            z["zone_id"],
            z["zone_name"],
            z["valve_tag"],
            "OPEN" if z["valve_open"] else "CLOSED",
            _fmt_cell(z.get("avg_soil_moisture")),
            _fmt_cell(z.get("avg_soil_temp")),
            _fmt_cell(z.get("avg_soil_ec")),
            _fmt_cell(z.get("avg_soil_salt")),
            _fmt_cell(z.get("avg_soil_ph")),
            _fmt_cell(z.get("avg_leaf_humidity")),
            _fmt_cell(z.get("avg_leaf_temp")),
        ])

    # Sheet 2: All 24 Soil (Slave 1-24) + 24 Leaf (Slave 101-124) Sensors Raw Readings
    ws_sensors = wb.create_sheet(title="All_48_Sensors_Filtered")
    sensor_headers = [
        "Recorded At (UTC)", "Resolution", "Soil Sensor (R1-R24)", "Soil Slave ID (1-24)",
        "Leaf Sensor (R1_L-R24_L)", "Leaf Slave ID (101-124)",
        "Zone ID (1-8)", "Valve State", "Soil Moisture (%)", "Soil Temp (°C)",
        "Soil EC (µS/cm)", "Soil Salinity (mg/L)", "Soil pH",
        "Leaf Humidity L_humidity (%)", "Leaf Temp L_temp (°C)"
    ]
    ws_sensors.append(sensor_headers)
    for cell in ws_sensors[1]:
        cell.fill = header_fill
        cell.font = header_font

    for r in data["sensor_rows"]:
        ws_sensors.append([
            r["recorded_at"],
            resolution,
            r["sensor_tag"],
            r.get("soil_slave_id", r["sensor_id"]),
            r["leaf_tag"],
            r.get("leaf_slave_id", 100 + int(r["sensor_id"])),
            r["zone_id"],
            "OPEN" if r["valve_open"] else "CLOSED",
            _fmt_cell(r.get("soil_moisture")),
            _fmt_cell(r.get("soil_temp")),
            _fmt_cell(r.get("soil_ec")),
            _fmt_cell(r.get("soil_salt")),
            _fmt_cell(r.get("soil_ph")),
            _fmt_cell(r.get("leaf_humidity")),
            _fmt_cell(r.get("leaf_temp")),
        ])

    # Sheet 3: PhD Statistical Summary per Zone
    z_cfg_map = {c["zone_id"]: c for c in db.get_zone_configs()}
    ws_stats = wb.create_sheet(title="PhD_Statistical_Summary")
    stat_headers = [
        "Zone ID", "Valve Tag", "Flow Meter (Before Valve)",
        "Nominal Flow Rate (L/min)", "Total Water Supplied (L)",
        "Sample Count (N)",
        "Min Moisture (%)", "Max Moisture (%)", "Mean Moisture (%)",
        "Mean Soil Temp (°C)", "Mean Soil EC (µS/cm)",
        "Mean L_humidity (%)", "Mean L_temp (°C)", "Irrigating Intervals"
    ]
    ws_stats.append(stat_headers)
    for cell in ws_stats[1]:
        cell.fill = sub_fill
        cell.font = header_font

    for st in data["zone_stats"]:
        zcfg = z_cfg_map.get(int(st["zone_id"]), {})
        ws_stats.append([
            f"Zone {st['zone_id']}",
            st["valve_tag"],
            "YF-S201 (1-30 L/min)",
            round(float(zcfg.get("nominal_flow_lpm", 2.0)), 2),
            round(float(zcfg.get("total_water_liters", 0.0)), 2),
            st["sample_count"],
            _fmt_cell(st.get("min_moisture")),
            _fmt_cell(st.get("max_moisture")),
            _fmt_cell(st.get("mean_moisture")),
            _fmt_cell(st.get("mean_temp")),
            _fmt_cell(st.get("mean_ec")),
            _fmt_cell(st.get("mean_leaf_humidity")),
            _fmt_cell(st.get("mean_leaf_temp")),
            st["irrigating_intervals"],
        ])

    # Sheet 4: Valve Events Audit Log
    ws_valves = wb.create_sheet(title="Valve_Control_Events")
    valve_headers = ["Timestamp (UTC)", "Zone ID", "Valve Tag", "New State", "Triggered By"]
    ws_valves.append(valve_headers)
    for cell in ws_valves[1]:
        cell.fill = header_fill
        cell.font = header_font

    for v in data["valve_events"]:
        ws_valves.append([
            v["recorded_at"],
            v["zone_id"],
            v["valve_tag"],
            "ON (OPEN)" if v["state"] else "OFF (CLOSED)",
            v["trigger_source"],
        ])

    # Sheet 5: PhD Biophysical Stress & Biostimulant Recovery Analysis
    ws_stress = wb.create_sheet(title="PhD_Stress_And_Recovery")
    stress_headers = [
        "Zone ID", "Line Label", "Treatment Code", "Salinity Regime",
        "NaCl (mM)", "NaHS Dose (uM)", "Humic Dose (mL/L)", "Ref Soil pH",
        "Avg Moisture (%)", "Avg Bulk EC (uS/cm)", "Hilhorst Pore ECp (dS/m)",
        "Osmotic Potential (MPa)", "Salt Coefficient (mg/L per uS/cm)",
        "Leaf VPD (kPa)", "Jackson CWSI (0-1)",
        "Moisture Stress (0-100)", "Salinity Stress (0-100)", "Canopy Stress (0-100)",
        "Composite PSI (0-100)", "Plant Vitality PVI (0-100)", "Stress Class",
        "Recovery Index SRI vs I-S-0 (%)", "PSI Reduction vs I-S-0 (pts)",
        "Molecular H2S Fraction (%)", "Active Molecular H2S (uM)"
    ]
    ws_stress.append(stress_headers)
    for cell in ws_stress[1]:
        cell.fill = sub_fill
        cell.font = header_font

    live_stress = stress_engine.compute_live_stress_report(
        latest_telemetry=db.get_latest_telemetry(),
        line_profiles=db.get_line_treatment_profiles(),
        calibration=db.get_stress_calibration(),
        recent_treatments=db.get_treatment_applications(limit=25),
        recent_notes=db.get_research_notes(limit=25),
    )
    for z in live_stress.get("zones", []):
        ws_stress.append([
            z["zone_id"],
            z["line_label"],
            z["treatment_code"],
            z["salinity_regime"],
            z["nacl_mm"],
            z["nahs_dose_um"],
            z["humic_dose_mll"],
            z["ref_soil_ph"],
            _fmt_cell(z.get("avg_soil_moisture")),
            _fmt_cell(z.get("avg_soil_ec")),
            _fmt_cell(z.get("avg_pore_ec_dsm")),
            _fmt_cell(z.get("avg_osmotic_potential_mpa")),
            _fmt_cell(z.get("avg_salt_coeff")),
            _fmt_cell(z.get("avg_vpd_kpa")),
            _fmt_cell(z.get("avg_cwsi")),
            _fmt_cell(z.get("avg_s_moisture")),
            _fmt_cell(z.get("avg_s_salinity")),
            _fmt_cell(z.get("avg_s_canopy")),
            _fmt_cell(z.get("avg_psi")),
            _fmt_cell(z.get("avg_pvi")),
            z.get("stress_class", "no_data"),
            _fmt_cell(z.get("recovery_sri_pct")),
            _fmt_cell(z.get("psi_reduction_vs_salt_ctrl")),
            _fmt_cell((z.get("h2s_speciation") or {}).get("f_h2s_pct")),
            _fmt_cell((z.get("h2s_speciation") or {}).get("active_h2s_um")),
        ])

    # Sheet 6: Treatment Applications Log (H2S / Humic / NaCl / Solution & Drainage EC/pH)
    ws_trt = wb.create_sheet(title="Treatment_Applications_Log")
    trt_headers = [
        "App ID", "Applied At (UTC)", "DAT", "Zone ID", "Sensor Plot ID",
        "Target Scope", "Treatment Code",
        "H2S Applied", "NaHS Dose (uM)", "NaHS Stock Added (mL/L)", "Solution Volume (L)", "Measured Dripper H2S (uM)",
        "Humic Applied", "Humic Product", "Humic Dose (mL/L)", "Humic Total Added (mL)", "N+K Nutrient Matched",
        "Salt Applied", "NaCl Dose (mM)", "NaCl Added (g/L)",
        "Supplied Solution EC (uS/cm)", "Supplied Solution pH",
        "Drainage Fraction (%)", "Drainage EC (uS/cm)", "Drainage pH",
        "Notes", "Recorded By"
    ]
    ws_trt.append(trt_headers)
    for cell in ws_trt[1]:
        cell.fill = header_fill
        cell.font = header_font

    for t in db.get_treatment_applications(start_date=start_date, end_date=end_date, limit=5000):
        ws_trt.append([
            t["app_id"],
            t["applied_at"],
            _fmt_cell(t.get("dat")),
            _fmt_cell(t.get("zone_id")),
            _fmt_cell(t.get("sensor_id")),
            t.get("target_scope", "zone"),
            t.get("treatment_code", ""),
            "YES" if t.get("h2s_applied") else "NO",
            t.get("h2s_dose_um", 0.0),
            t.get("h2s_stock_ml_per_l", 0.0),
            t.get("h2s_solution_vol_l", 0.0),
            _fmt_cell(t.get("measured_dripper_h2s_um")),
            "YES" if t.get("humic_applied") else "NO",
            t.get("humic_product", ""),
            t.get("humic_dose_mll", 0.0),
            t.get("humic_total_ml", 0.0),
            "YES" if t.get("nutrient_match_applied") else "NO",
            "YES" if t.get("salt_applied") else "NO",
            t.get("nacl_dose_mm", 0.0),
            t.get("salt_amount_g_per_l", 0.0),
            _fmt_cell(t.get("supplied_solution_ec_uscm")),
            _fmt_cell(t.get("supplied_solution_ph")),
            _fmt_cell(t.get("drainage_fraction_pct")),
            _fmt_cell(t.get("drainage_ec_uscm")),
            _fmt_cell(t.get("drainage_ph")),
            t.get("notes", ""),
            t.get("recorded_by", ""),
        ])

    # Sheet 7: Persistent Research Diary Notes
    ws_notes = wb.create_sheet(title="Research_Diary_Notes")
    note_headers = [
        "Note ID", "Recorded At (UTC)", "DAT", "Zone ID", "Plot Sensor ID",
        "Treatment Code", "Category", "Severity / Tag", "Pinned on Charts",
        "Title", "Observation / Content", "Author", "Updated At"
    ]
    ws_notes.append(note_headers)
    for cell in ws_notes[1]:
        cell.fill = sub_fill
        cell.font = header_font

    for n in db.get_research_notes(start_date=start_date, end_date=end_date, limit=5000):
        ws_notes.append([
            n["note_id"],
            n["recorded_at"],
            _fmt_cell(n.get("dat")),
            _fmt_cell(n.get("zone_id")),
            _fmt_cell(n.get("sensor_id")),
            n.get("treatment_code", ""),
            n.get("category", ""),
            n.get("severity_or_tag", ""),
            "YES" if n.get("pinned_on_chart") else "NO",
            n.get("title", ""),
            n.get("content", ""),
            n.get("author", ""),
            n.get("updated_at", ""),
        ])

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    filename = f"Ziraat_PhD_Dataset_{resolution}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ==============================================================================
# PhD Plant Stress, Biostimulant Recovery, Treatment Log & Research Notes APIs
# (Strictly Monitoring & Data-Logging Only — Zero Valve Control)
# ==============================================================================


@app.get("/api/v1/stress/live")
async def get_live_stress_api():
    """
    Compute live biophysical stress & biostimulant recovery report across all 24 plots (R1..R24 + R1_L..R24_L)
    and 8 irrigation lines (Zones 1..8). Strictly monitoring-only.
    """
    latest = db.get_latest_telemetry()
    profiles = db.get_line_treatment_profiles()
    calibration = db.get_stress_calibration()
    treatments = db.get_treatment_applications(limit=50)
    notes = db.get_research_notes(limit=50)
    return stress_engine.compute_live_stress_report(
        latest_telemetry=latest,
        line_profiles=profiles,
        calibration=calibration,
        recent_treatments=treatments,
        recent_notes=notes,
    )


@app.get("/api/v1/stress/history")
async def get_historical_stress_api(
    start_date: Optional[str] = Query(None, description="ISO start date/time"),
    end_date: Optional[str] = Query(None, description="ISO end date/time"),
    hours: Optional[float] = Query(168.0, description="Relative window in hours (default 7 days = 168h)"),
    zones: Optional[str] = Query(None, description="Comma-separated zone IDs (e.g. 1,5,6,7,8)"),
    sensors: Optional[str] = Query(None, description="Comma-separated sensor IDs (e.g. 1,13,22)"),
    resolution: str = Query("15min", description="raw | 1min | 2min | 5min | 10min | 15min | 30min | hourly | daily"),
    limit: int = Query(3000, ge=1, le=50000),
):
    """
    Compute historical stress & recovery time-series, 24-hour diurnal cycle profiles,
    Stress Degree-Hours (SDH), and pre/post-pulse biostimulant recovery deltas.
    """
    zone_list = _parse_int_list(zones)
    sensor_list = _parse_int_list(sensors)
    q = db.query_filtered_telemetry(
        start_date=start_date,
        end_date=end_date,
        hours=hours if not (start_date or end_date) else None,
        zone_ids=zone_list,
        sensor_ids=sensor_list,
        resolution=resolution,
        limit=limit,
    )
    profiles = db.get_line_treatment_profiles()
    calibration = db.get_stress_calibration()
    treatments = db.get_treatment_applications(
        start_date=start_date or q.get("effective_start_date"),
        end_date=end_date,
        limit=500,
    )
    notes = db.get_research_notes(
        start_date=start_date or q.get("effective_start_date"),
        end_date=end_date,
        limit=500,
    )
    report = stress_engine.compute_historical_stress_report(
        zone_rows=q.get("zone_rows", []),
        sensor_rows=q.get("sensor_rows", []),
        line_profiles=profiles,
        calibration=calibration,
        treatments=treatments,
        notes=notes,
        resolution=resolution,
    )
    report["effective_start_date"] = q.get("effective_start_date") or start_date
    report["effective_end_date"] = q.get("effective_end_date") or end_date
    return report


@app.get("/api/v1/stress/line-profiles")
async def list_line_profiles_api():
    return {
        "line_profiles": db.get_line_treatment_profiles(),
        "calibration": db.get_stress_calibration(),
    }


@app.post("/api/v1/stress/line-profiles")
async def update_line_profile_api(req: LineTreatmentProfileRequest):
    updated = db.update_line_treatment_profile(req.zone_id, req.model_dump(exclude_none=True))
    return {
        "status": "updated",
        "profile": updated,
        "line_profiles": db.get_line_treatment_profiles(),
    }


@app.get("/api/v1/stress/treatments")
async def list_treatments_api(
    zone_id: Optional[int] = Query(None),
    sensor_id: Optional[int] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=5000),
):
    return {
        "treatments": db.get_treatment_applications(
            zone_id=zone_id,
            sensor_id=sensor_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
    }


@app.post("/api/v1/stress/treatments")
async def create_treatment_api(req: TreatmentApplicationRequest):
    if not req.applied_at or not req.applied_at.strip():
        raise HTTPException(status_code=400, detail="applied_at (Date & Time) is required for treatment inputs")
    created = db.add_treatment_application(req.model_dump())
    await ws_manager.broadcast({
        "type": "treatment_logged",
        "treatment": created,
    })
    return {
        "status": "recorded",
        "treatment": created,
        "treatments": db.get_treatment_applications(limit=100),
        "line_profiles": db.get_line_treatment_profiles(),
    }


@app.delete("/api/v1/stress/treatments/{app_id}")
async def delete_treatment_api(app_id: str):
    deleted = db.delete_treatment_application(app_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Treatment application {app_id} not found")
    return {
        "status": "deleted",
        "app_id": app_id,
        "treatments": db.get_treatment_applications(limit=100),
    }


@app.get("/api/v1/stress/notes")
async def list_research_notes_api(
    zone_id: Optional[int] = Query(None),
    sensor_id: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    pinned_only: bool = Query(False),
    search: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=5000),
):
    return {
        "notes": db.get_research_notes(
            zone_id=zone_id,
            sensor_id=sensor_id,
            category=category,
            pinned_only=pinned_only,
            search=search,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
    }


@app.post("/api/v1/stress/notes")
async def create_research_note_api(req: ResearchNoteRequest):
    if not req.title.strip() or not req.content.strip():
        raise HTTPException(status_code=400, detail="Both title and content are required")
    created = db.add_research_note(req.model_dump())
    await ws_manager.broadcast({
        "type": "research_note_added",
        "note": created,
    })
    return {
        "status": "recorded",
        "note": created,
        "notes": db.get_research_notes(limit=100),
    }


@app.put("/api/v1/stress/notes/{note_id}")
async def update_research_note_api(note_id: str, req: ResearchNoteRequest):
    updated = db.update_research_note(note_id, req.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(status_code=404, detail=f"Research note {note_id} not found")
    return {
        "status": "updated",
        "note": updated,
        "notes": db.get_research_notes(limit=100),
    }


@app.delete("/api/v1/stress/notes/{note_id}")
async def delete_research_note_api(note_id: str):
    deleted = db.delete_research_note(note_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Research note {note_id} not found")
    return {
        "status": "deleted",
        "note_id": note_id,
        "notes": db.get_research_notes(limit=100),
    }


@app.get("/api/v1/stress/calibration")
async def get_stress_calibration_api():
    return {"calibration": db.get_stress_calibration()}


@app.post("/api/v1/stress/calibration")
async def update_stress_calibration_api(req: StressCalibrationRequest):
    updated = db.update_stress_calibration(req.model_dump(exclude_none=True))
    return {"status": "updated", "calibration": updated}


@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        latest = db.get_latest_telemetry()
        await websocket.send_text(json.dumps({
            "type": "initial_state",
            "data": latest,
            "zone_configs": db.get_zone_configs(),
            "stats": db.get_stats_summary(),
        }))
        while True:
            msg = await websocket.receive_text()
            data = json.loads(msg)
            if data.get("action") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)


@app.get("/", response_class=HTMLResponse)
async def web_scada_dashboard():
    """Built-in Responsive Web & Mobile PWA SCADA Dashboard."""
    html_path = __file__.replace("main.py", "dashboard.html")
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(
                f.read(),
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
            )
    except FileNotFoundError:
        return HTMLResponse("<h1>Ziraat Irrigation Cloud API is Running</h1>")


@app.get("/stress", response_class=HTMLResponse)
@app.get("/stress-studio", response_class=HTMLResponse)
async def web_stress_recovery_studio():
    """Dedicated PhD Plant Stress, Biostimulant Recovery, Treatment Logging & Research Notes Studio Page (Unified Single-Website Header)."""
    html_path = __file__.replace("main.py", "dashboard.html")
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(
                f.read(),
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
            )
    except FileNotFoundError:
        return HTMLResponse("<h1>PhD Stress, Recovery & Notes Studio is Loading...</h1>")
