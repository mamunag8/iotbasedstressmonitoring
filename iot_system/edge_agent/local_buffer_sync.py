"""
Offline-First Local SQLite Buffer & Cloud Sync Daemon for Ziraat Fakultesi Otomatik Sulama Sistemi.
- Polls GMTCNT GLC-196R PLC (192.168.1.240:502) over Ethernet cable / Wi-Fi router.
- Strict Zero-Demo Policy: Only saves telemetry snapshots into the local SQLite database (edge_sync_queue.db)
  and Cloud PostgreSQL DB when REAL hardware data is received from the PLC (source == 'plc_hardware_196r').
  When PLC Port 502 is closed or unplugged, values remain blank (—) and no demo rows are saved.
- Saves real telemetry snapshots every 5 minutes (300 seconds) (plus on startup and whenever a valve command is executed).
- Checks for pending remote valve/threshold commands every 5 seconds so mobile/web valve control is instant.
"""

import argparse
import asyncio
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import httpx
import uvicorn

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "cloud_backend")))
from app import database as local_api_db
from app.main import app as local_lan_app, ws_manager
from plc_modbus_client import GLC196RModbusDriver
from hmi_pendrive_scraper import HMIPendriveScraper


DEFAULT_CLOUD_URL = os.getenv("CLOUD_API_URL", "https://iotserver.ertanyildirim.com")
FALLBACK_CLOUD_URLS = [
    "https://iotserver.ertanyildirim.com",
    "https://iotserver.mmreza.com",
    "http://77.42.89.186:8000",
]
DEFAULT_PLC_IP = os.getenv("PLC_IP", "192.168.1.240")
DEFAULT_PLC_PORT = int(os.getenv("PLC_PORT", "502"))
DEFAULT_SAVE_INTERVAL_SEC = float(os.getenv("SAVE_INTERVAL_SEC", "60"))  # 1 minute (60s) default for granular plot history
LOCAL_QUEUE_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "edge_sync_queue.db")


class LocalEdgeSyncQueue:
    """Dedicated SQLite Store-and-Forward Queue guaranteeing zero data loss offline (Real PLC data only)."""

    def __init__(self, db_path: str = LOCAL_QUEUE_DB) -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_queue_db()
        local_api_db.init_db()
        local_api_db.purge_simulated_data()
        self.purge_simulated()

    def _init_queue_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS offline_queue (
                batch_id TEXT PRIMARY KEY,
                recorded_at TEXT UNIQUE NOT NULL,
                payload_json TEXT NOT NULL,
                synced INTEGER NOT NULL DEFAULT 0,
                synced_at TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_queue_synced ON offline_queue(synced, recorded_at ASC)")
        conn.commit()
        conn.close()

    def purge_simulated(self) -> int:
        """Delete any previously stored demo/simulated batches so only real PLC/HMI hardware data remains."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute("SELECT batch_id, payload_json FROM offline_queue")
        to_del: List[str] = []
        for bid, pjson in cur.fetchall():
            try:
                p = json.loads(pjson)
                if p.get("source") not in ("plc_hardware_196r", "hmi_pendrive") or not p.get("plc_online"):
                    to_del.append(bid)
            except Exception:
                to_del.append(bid)
        if to_del:
            placeholders = ",".join(["?"] * len(to_del))
            conn.execute(f"DELETE FROM offline_queue WHERE batch_id IN ({placeholders})", to_del)
            conn.commit()
        conn.close()
        return len(to_del)

    def enqueue(self, batch: Dict[str, Any]) -> None:
        if not batch.get("plc_online") or batch.get("source") not in ("plc_hardware_196r", "hmi_pendrive"):
            return
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO offline_queue (batch_id, recorded_at, payload_json, synced)
            VALUES (?, ?, ?, 0)
            """,
            (batch["batch_id"], batch["recorded_at"], json.dumps(batch)),
        )
        inserted = cur.rowcount > 0
        conn.commit()
        conn.close()
        if inserted:
            self._append_csv_log(batch)

    def _append_csv_log(self, snapshot: Dict[str, Any]) -> None:
        csv_path = os.path.join(os.path.dirname(self.db_path), "plc_live_telemetry_log.csv")
        try:
            write_header = not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0
            zones = {z["zone_id"]: z for z in snapshot.get("zones", [])}
            sensors = {s["sensor_id"]: s for s in snapshot.get("sensors", [])}
            headers = ["recorded_at", "batch_id", "source"]
            row = [str(snapshot.get("recorded_at", "")), str(snapshot.get("batch_id", "")), str(snapshot.get("source", ""))]
            for zid in range(1, 9):
                z = zones.get(zid, {})
                headers.extend([f"Z{zid}_avg_moist", f"Z{zid}_son_ortlama", f"Z{zid}_valve_open", f"Z{zid}_auto_mode"])
                row.extend([
                    str(z.get("avg_soil_moisture", "")),
                    str(z.get("plc_son_ortlama", "")),
                    "1" if z.get("valve_open") else "0",
                    "1" if z.get("auto_mode") else "0",
                ])
            for sid in range(1, 25):
                s = sensors.get(sid, {})
                headers.extend([
                    f"S{sid}_soil_moist",
                    f"S{sid}_soil_temp",
                    f"S{sid}_soil_ec",
                    f"S{sid}_soil_salt",
                    f"S{sid}_leaf_wet",
                    f"S{sid}_leaf_temp",
                ])
                row.extend([
                    str(s.get("soil_moisture", "")),
                    str(s.get("soil_temp", "")),
                    str(s.get("soil_ec", "")),
                    str(s.get("soil_salt", "")),
                    str(s.get("leaf_humidity", "")),
                    str(s.get("leaf_temp", "")),
                ])
            with open(csv_path, "a", encoding="utf-8") as f:
                if write_header:
                    f.write(",".join(headers) + "\n")
                f.write(",".join(row) + "\n")
            try:
                from export_all48_excel_csv import export_all48_files
                export_all48_files(os.path.dirname(self.db_path))
            except Exception:
                pass
        except Exception:
            pass

    def get_unsynced(self, limit: int = 100) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            "SELECT payload_json FROM offline_queue WHERE synced = 0 ORDER BY recorded_at ASC LIMIT ?",
            (limit,),
        )
        rows = [json.loads(r[0]) for r in cur.fetchall()]
        conn.close()
        return [r for r in rows if r.get("source") in ("plc_hardware_196r", "hmi_pendrive") and r.get("plc_online")]

    def mark_synced(self, batch_ids: List[str]) -> None:
        if not batch_ids:
            return
        now_iso = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(self.db_path)
        placeholders = ",".join(["?"] * len(batch_ids))
        conn.execute(
            f"UPDATE offline_queue SET synced = 1, synced_at = ? WHERE batch_id IN ({placeholders})",
            [now_iso, *batch_ids],
        )
        conn.commit()
        conn.close()

    def queue_counts(self) -> Dict[str, int]:
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute("SELECT COUNT(*) FROM offline_queue WHERE synced = 0")
        unsynced = cur.fetchone()[0]
        cur2 = conn.execute("SELECT COUNT(*) FROM offline_queue WHERE synced = 1")
        synced = cur2.fetchone()[0]
        conn.close()
        return {"unsynced": unsynced, "synced": synced, "total_local": unsynced + synced}


def _candidate_cloud_urls(primary_url: str) -> List[str]:
    urls = [primary_url.rstrip("/")]
    for u in FALLBACK_CLOUD_URLS:
        clean = u.rstrip("/")
        if clean not in urls:
            urls.append(clean)
    return urls


async def _execute_remote_commands(
    client: httpx.AsyncClient,
    base_url: str,
    commands: List[Dict[str, Any]],
    driver: GLC196RModbusDriver,
) -> int:
    executed = 0
    for cmd in commands:
        zid = int(cmd["zone_id"])
        target_open = bool(cmd["target_state"]) if cmd.get("target_state") is not None else None
        auto_mode = bool(cmd["auto_mode"]) if cmd.get("auto_mode") is not None else None
        if target_open is not None or auto_mode is not None:
            ok = await asyncio.to_thread(
                driver.write_zone_control, zone_id=zid, auto_mode=auto_mode, target_open=target_open
            )
            if not ok:
                # PLC is unreachable right now; stop trying remaining commands this cycle
                break
            local_api_db.queue_control_command(
                zone_id=zid,
                command_type="cloud_sync_valve",
                target_state=target_open,
                auto_mode=auto_mode if auto_mode is not None else False,
                requested_by="cloud_remote",
            )
        await client.post(f"{base_url}/api/v1/control/ack/{cmd['cmd_id']}")
        executed += 1
    return executed


async def sync_unsent_to_cloud(
    queue: LocalEdgeSyncQueue,
    driver: GLC196RModbusDriver,
    cloud_url: str,
    plc_online_now: Optional[bool] = None,
    hmi_usb_now: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Uploads unsent real PLC records to the Cloud Server if internet is available,
    and executes any pending remote valve commands when the PLC is connected.
    """
    unsynced = queue.get_unsynced(limit=150)
    is_plc_live = int(bool(plc_online_now if plc_online_now is not None else (driver.port23_open or driver.port502_open)))
    is_hmi_live = int(bool(hmi_usb_now)) if hmi_usb_now is not None else 0

    async with httpx.AsyncClient(timeout=6.0) as client:
        for base_url in _candidate_cloud_urls(cloud_url):
            try:
                if unsynced:
                    resp = await client.post(
                        f"{base_url}/api/v1/telemetry/sync",
                        json={"device_id": "ziraat_plc_196r", "batches": unsynced},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    queue.mark_synced([b["batch_id"] for b in unsynced])
                    exec_count = await _execute_remote_commands(
                        client, base_url, data.get("pending_commands", []), driver
                    )
                    await client.get(f"{base_url}/api/v1/control/pending?plc_online={is_plc_live}&hmi_usb={is_hmi_live}")
                    return {
                        "cloud_online": True,
                        "active_url": base_url,
                        "uploaded": len(unsynced),
                        "pending_executed": exec_count,
                    }
                else:
                    resp = await client.get(f"{base_url}/api/v1/control/pending?plc_online={is_plc_live}&hmi_usb={is_hmi_live}")
                    resp.raise_for_status()
                    data = resp.json()
                    exec_count = await _execute_remote_commands(
                        client, base_url, data.get("pending_commands", []), driver
                    )
                    return {
                        "cloud_online": True,
                        "active_url": base_url,
                        "uploaded": 0,
                        "pending_executed": exec_count,
                    }
            except Exception as exc:
                last_err = str(exc)
                continue

    return {"cloud_online": False, "uploaded": 0, "error": locals().get("last_err", "unreachable")}


async def edge_polling_loop(
    driver: GLC196RModbusDriver,
    queue: LocalEdgeSyncQueue,
    scraper: HMIPendriveScraper,
    cloud_url: str,
    save_interval: float = DEFAULT_SAVE_INTERVAL_SEC,
    cmd_poll_interval: float = 5.0,
) -> None:
    local_api_db.init_db()
    local_api_db.purge_simulated_data()
    print(
        f"[EdgeAgent] Polling Real PLC at {driver.plc_ip}:{driver.plc_port} (Zero Demo Data Mode) "
        f"| Command Check: {cmd_poll_interval:.0f}s | Save Interval: {save_interval:.0f}s ({save_interval/60:.1f} min)"
    )
    print(f"[EdgeAgent] Cloud Sync Target: {cloud_url}")
    print("[EdgeAgent] [HMI Watcher] Autonomous HMI USB Flash Drive Watcher: Active (Silently auto-scrapes on USB insert)")

    last_save_ts = -1e9
    last_hmi_scan_ts = -1e9

    while True:
        try:
            # 1. Check if any local LAN commands were queued
            local_cmd_ran = False
            for lcmd in local_api_db.fetch_pending_commands():
                zid = int(lcmd["zone_id"])
                t_open = bool(lcmd["target_state"]) if lcmd.get("target_state") is not None else None
                a_mode = bool(lcmd["auto_mode"]) if lcmd.get("auto_mode") is not None else None
                if t_open is not None or a_mode is not None:
                    ok = await asyncio.to_thread(
                        driver.write_zone_control, zone_id=zid, auto_mode=a_mode, target_open=t_open
                    )
                    if ok:
                        local_cmd_ran = True
                        local_api_db.ack_command(lcmd["cmd_id"])
                    else:
                        # PLC is offline right now; keep remaining pending commands queued until PLC connects
                        break
                else:
                    local_api_db.ack_command(lcmd["cmd_id"])

            now_mono = time.monotonic()

            # 2. Autonomous Silent HMI USB Flash Drive Scraper (Checks every 10 seconds)
            if (now_mono - last_hmi_scan_ts) >= 10.0:
                last_hmi_scan_ts = now_mono
                try:
                    hmi_res = await scraper.scan_and_import(queue_obj=queue)
                    if hmi_res.get("new_minute_records", 0) > 0:
                        print(
                            f"[EdgeAgent] [HMI Scraper] Scraped {hmi_res['new_minute_records']} historical minute records "
                            f"from HMI USB -> Saved to Local PC & Synced to Cloud Server!"
                        )
                        latest_valid = local_api_db.get_latest_telemetry()
                        await ws_manager.broadcast({
                            "type": "hmi_import_success",
                            "records_imported": hmi_res["new_minute_records"],
                            "total_records": hmi_res["total_historical_records"],
                            "data": latest_valid,
                            "queue_stats": queue.queue_counts(),
                        })
                except Exception as e:
                    print(f"[EdgeAgent] HMI scraper loop note: {e}")

            try:
                active_save_interval = float(local_api_db.get_system_settings().get("save_interval_sec", save_interval))
            except Exception:
                active_save_interval = save_interval
            should_save = (now_mono - last_save_ts) >= active_save_interval or local_cmd_ran

            if should_save:
                z_cfgs = {c["zone_id"]: c for c in local_api_db.get_zone_configs()}
                snapshot = await asyncio.to_thread(driver.poll_snapshot, zone_configs=z_cfgs)
                is_plc_live = bool(snapshot.get("plc_online") and snapshot.get("source") == "plc_hardware_196r")
                is_hmi_live = bool(scraper.get_status().get("usb_connected"))
                local_lan_app.state.edge_live_status = {
                    "plc_online": is_plc_live,
                    "hmi_usb": is_hmi_live,
                    "updated_at": datetime.now(timezone.utc).timestamp(),
                }

                if is_plc_live:
                    # Only store to DB when real PLC hardware data arrived!
                    queue.enqueue(snapshot)
                    local_api_db.store_telemetry_batches([snapshot])
                    last_save_ts = now_mono
                    latest_valid = dict(snapshot)
                    latest_valid["plc_live_connected"] = True
                else:
                    # Retry every cycle until PLC comes online
                    last_save_ts = now_mono - active_save_interval + 15.0
                    latest_valid = local_api_db.get_latest_telemetry()
                    if latest_valid:
                        latest_valid = dict(latest_valid)
                        latest_valid["plc_live_connected"] = is_hmi_live

                await ws_manager.broadcast({
                    "type": "telemetry_update",
                    "data": latest_valid,
                    "plc_status": {
                        "plc_online": is_plc_live or is_hmi_live,
                        "port23_open": snapshot.get("port23_open", False),
                        "port502_open": snapshot.get("port502_open", False),
                        "diagnostic_error": snapshot.get("diagnostic_error") if not is_plc_live else None,
                    },
                    "queue_stats": queue.queue_counts(),
                })

            # 2. Sync unsent records & check remote valve commands
            cur_live = getattr(local_lan_app.state, "edge_live_status", {}) or {}
            sync_res = await sync_unsent_to_cloud(
                queue,
                driver,
                cloud_url,
                plc_online_now=cur_live.get("plc_online", False),
                hmi_usb_now=cur_live.get("hmi_usb", False),
            )

            if sync_res.get("pending_executed", 0) > 0:
                z_cfgs = {c["zone_id"]: c for c in local_api_db.get_zone_configs()}
                snapshot = await asyncio.to_thread(driver.poll_snapshot, zone_configs=z_cfgs)
                if snapshot.get("plc_online") and snapshot.get("source") == "plc_hardware_196r":
                    queue.enqueue(snapshot)
                    local_api_db.store_telemetry_batches([snapshot])
                    await sync_unsent_to_cloud(queue, driver, cloud_url)
                    last_save_ts = time.monotonic()
        except Exception as e:
            print(f"[EdgeAgent] Poll cycle error: {e}")

        await asyncio.sleep(cmd_poll_interval)


async def main_async(args: argparse.Namespace) -> None:
    driver = GLC196RModbusDriver(
        plc_ip=args.plc_ip,
        plc_port=args.plc_port,
        allow_simulation_fallback=False,
    )
    queue = LocalEdgeSyncQueue()
    scraper = HMIPendriveScraper()

    async def manual_sync_now() -> Dict[str, Any]:
        # Also run HMI pendrive scan on manual sync request
        try:
            hmi_res = await scraper.scan_and_import(queue_obj=queue)
        except Exception:
            hmi_res = {}

        z_cfgs = {c["zone_id"]: c for c in local_api_db.get_zone_configs()}
        snapshot = await asyncio.to_thread(driver.poll_snapshot, zone_configs=z_cfgs)
        is_plc_live = bool(snapshot.get("plc_online") and snapshot.get("source") == "plc_hardware_196r")
        is_hmi_live = bool(hmi_res.get("usb_connected") or hmi_res.get("new_minute_records", 0) > 0)
        is_live_connected = is_plc_live or is_hmi_live

        local_lan_app.state.edge_live_status = {
            "plc_online": is_plc_live,
            "hmi_usb": is_hmi_live,
            "updated_at": datetime.now(timezone.utc).timestamp(),
        }

        if is_plc_live:
            queue.enqueue(snapshot)
            local_api_db.store_telemetry_batches([snapshot])
            active_data = dict(snapshot)
            active_data["plc_live_connected"] = True
        else:
            active_data = local_api_db.get_latest_telemetry()
            if active_data:
                active_data = dict(active_data)
                active_data["plc_live_connected"] = is_live_connected

        sync_res = await sync_unsent_to_cloud(
            queue, driver, args.cloud_url, plc_online_now=is_plc_live, hmi_usb_now=is_hmi_live
        )
        await ws_manager.broadcast({
            "type": "telemetry_update",
            "data": active_data,
            "plc_status": {
                "plc_online": is_live_connected,
                "port23_open": driver.port23_open,
                "port502_open": driver.port502_open,
                "diagnostic_error": None if is_live_connected else driver.last_error,
            },
            "queue_stats": queue.queue_counts(),
        })
        port23_open = driver.port23_open
        port502_open = driver.port502_open
        rec_at = (active_data or {}).get("recorded_at")
        rec_label = str(rec_at)[:19].replace("T", " ") + " UTC" if rec_at else "—"
        return {
            "status": "ok" if is_live_connected else "offline",
            "mode": "edge_pc",
            "plc_ip": driver.plc_ip,
            "plc_port": 502 if port502_open else 23,
            "ethernet_cable_connected": port23_open or port502_open,
            "modbus_port_502_open": port502_open,
            "port23_direct_open": port23_open,
            "plc_hardware_connected": is_live_connected,
            "source": (active_data or {}).get("source", snapshot.get("source")),
            "recorded_at": rec_at,
            "cloud_sync": sync_res,
            "hmi_flash_drive": hmi_res,
            "message_en": (
                f"✅ Live Hardware Connected! Synced all 48 sensors + 8 Zone Modes & Averages from {'HMI Flash Drive' if is_hmi_live and not is_plc_live else f'PLC {driver.plc_ip}'} & saved to Database!"
                if is_live_connected
                else f"⚠️ PLC ({driver.plc_ip}) and HMI USB are NOT connected right now! No new live reading could be taken. (Dashboard is showing the last saved database record from {rec_label})."
            ),
            "message_bn": (
                f"✅ আসল হার্ডওয়্যার সংযুক্ত আছে! ৪৮টি সেন্সরের ডাটা ও ৮টি জোনের স্ট্যাটাস সফলভাবে সিঙ্ক ও সেভ হয়েছে!"
                if is_live_connected
                else f"⚠️ PLC ({driver.plc_ip}) এবং HMI এখন সংযুক্ত নেই! নতুন কোনো লাইভ ডাটা পাওয়া যায়নি। (ড্যাশবোর্ডে সর্বশেষ সেভ করা ডাটা দেখানো হচ্ছে: {rec_label})।"
            ),
            "message_tr": (
                f"✅ Canlı Donanım Bağlı! 48 sensör verisi ve 8 Bölge durumu kaydedildi ve buluta eşitlendi!"
                if is_live_connected
                else f"⚠️ PLC ({driver.plc_ip}) ve HMI şu anda BAĞLI DEĞİL! Yeni canlı veri alınamadı. (Panelde {rec_label} tarihli son kayıtlı veriler gösteriliyor)."
            ),
            "message_ar": (
                f"✅ الجهاز متصل الآن! تمت مزامنة جميع الحساسات الـ 48 وحفظها في قاعدة البيانات!"
                if is_live_connected
                else f"⚠️ جهاز PLC ({driver.plc_ip}) وشاشة HMI غير متصلين الآن! (يعرض النظام آخر قراءة محفوظة بتاريخ {rec_label})."
            ),
        }

    local_lan_app.state.edge_sync_now_callback = manual_sync_now
    local_lan_app.state.plc_driver = driver
    local_lan_app.state.hmi_scraper = scraper
    local_lan_app.state.edge_queue = queue

    config = uvicorn.Config(local_lan_app, host="0.0.0.0", port=args.local_port, log_level="warning")
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None

    async def _safe_server_loop():
        try:
            await server.serve()
        except BaseException as exc:
            print(f"[EdgeAgent] Local server on port {args.local_port} note: {exc}")

    async def _safe_polling_loop():
        while True:
            try:
                await edge_polling_loop(
                    driver,
                    queue,
                    scraper,
                    args.cloud_url,
                    save_interval=args.save_interval,
                    cmd_poll_interval=args.cmd_interval,
                )
            except BaseException as exc:
                print(f"[EdgeAgent] Polling loop exception: {exc}, restarting in 5s...")
                await asyncio.sleep(5.0)

    print(f"[EdgeAgent] Local SCADA Web Server listening at http://localhost:{args.local_port}")
    await asyncio.gather(_safe_server_loop(), _safe_polling_loop(), return_exceptions=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ziraat Irrigation Offline-First Edge Sync Agent (Zero Demo Data)")
    parser.add_argument("--plc-ip", default=DEFAULT_PLC_IP)
    parser.add_argument("--plc-port", type=int, default=DEFAULT_PLC_PORT)
    parser.add_argument("--cloud-url", default=DEFAULT_CLOUD_URL)
    parser.add_argument("--local-port", type=int, default=8080)
    parser.add_argument(
        "--save-interval",
        "--interval",
        dest="save_interval",
        type=float,
        default=DEFAULT_SAVE_INTERVAL_SEC,
        help="Interval in seconds to save real PLC sensor data (default: 300s = 5 minutes)",
    )
    parser.add_argument(
        "--cmd-interval",
        type=float,
        default=5.0,
        help="Interval in seconds to check for remote valve commands (default: 5s)",
    )
    parsed_args = parser.parse_args()
    print("[EdgeAgent Supervisor] Initializing Zero-Downtime Self-Healing Daemon...", flush=True)

    while True:
        try:
            asyncio.run(main_async(parsed_args))
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("[EdgeAgent Supervisor] Received stop signal. Exiting cleanly.", flush=True)
            break
        except SystemExit as se:
            print(f"[EdgeAgent Supervisor] SystemExit({se}) caught. Auto-restarting in 3s...", flush=True)
            time.sleep(3.0)
        except BaseException as exc:
            import traceback
            print(f"[EdgeAgent Supervisor] Unhandled error: {exc}. Stacktrace:\n{traceback.format_exc()}", flush=True)
            print("[EdgeAgent Supervisor] Auto-restarting agent loop in 3s...", flush=True)
            time.sleep(3.0)
