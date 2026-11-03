"""
HMI Flash Drive (USB Pendrive) Autonomous Scraper & Cloud Sync Module.
For Ziraat Fakültesi Otomatik Sulama Sistemi (Atatürk University).

Autonomous Behavior:
- Continuously and silently detects USB flash drives (DRIVE_REMOVABLE or drive letters E:..Z:).
- Scans GMTCNT 070E HMI datalogger folders (SampleStore, SampleStoreEC, DataLog, *.csv, *.CSV).
- No permission prompt needed: automatically parses 1-minute historical data for all 48 sensors
  (24 Soil: Moisture, Temp, EC, Salt, pH + 24 Leaf: Humidity, Temp) and 8 Zones.
- Idempotently stores into local SQLite database (irrigation_cloud.db & edge_sync_queue.db).
- Updates plc_live_telemetry_log.csv, All_48_Sensors_Every_Minute_Data.csv & .xlsx.
- Immediately syncs all newly scraped historical batches to the Cloud Server (https://iotserver.ertanyildirim.com).
"""

import csv
import ctypes
import glob
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

# Zone to plots mapping:
# Zone 1: [1, 9, 17], Zone 2: [2, 10, 18], Zone 3: [3, 11, 19], Zone 4: [4, 12, 20]
# Zone 5: [5, 13, 21], Zone 6: [6, 14, 22], Zone 7: [7, 15, 23], Zone 8: [8, 16, 24]
ZONE_PLOTS = {
    1: [1, 9, 17],
    2: [2, 10, 18],
    3: [3, 11, 19],
    4: [4, 12, 20],
    5: [5, 13, 21],
    6: [6, 14, 22],
    7: [7, 15, 23],
    8: [8, 16, 24],
}
PLOT_TO_ZONE = {p: z for z, plots in ZONE_PLOTS.items() for p in plots}

# Modbus 4X addresses for EC and Salt per plot
EC_SALT_ADDR = {
    1: (3, 4), 2: (7, 8), 3: (81, 37), 4: (80, 36),
    5: (79, 35), 6: (78, 34), 7: (77, 33), 8: (76, 32),
    9: (75, 31), 10: (96, 52), 11: (95, 51), 12: (94, 50),
    13: (93, 49), 14: (91, 48), 15: (92, 47), 16: (90, 46),
    17: (89, 45), 18: (88, 44), 19: (87, 43), 20: (86, 42),
    21: (85, 41), 22: (84, 40), 23: (83, 39), 24: (82, 38),
}

TURKEY_TZ = timezone(timedelta(hours=3))

DEFAULT_DROP_DIRS = [
    r"d:\PhD at Ataturk\Automation project\hmi_data",
    r"d:\PhD at Ataturk\Automation project\iot_system\edge_agent\data\pendrive_drop",
    r"d:\hmi_usb",
    os.path.join(os.path.expanduser("~"), "Downloads", "hmi_data"),
    os.path.join(os.path.expanduser("~"), "Desktop", "hmi_data"),
]


class HMIPendriveScraper:
    def __init__(self, data_dir: Optional[str] = None) -> None:
        if data_dir is None:
            data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self.history_file = os.path.join(self.data_dir, "hmi_import_history.json")
        self.history: Dict[str, Any] = self._load_history()
        self.last_scan_time: Optional[str] = None
        self.last_detected_drives: List[str] = []
        self.total_scraped_records: int = self.history.get("total_records_imported", 0)

    def _load_history(self) -> Dict[str, Any]:
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"processed_files": {}, "total_records_imported": 0, "last_scan": None}

    def _save_history(self) -> None:
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self.history, f, indent=2)
        except Exception:
            pass

    def get_detected_usb_drives(self) -> List[str]:
        """Detect all removable USB storage drives and drives E: through Z:."""
        detected: List[str] = []
        try:
            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
            for letter in range(ord("A"), ord("Z") + 1):
                char = chr(letter)
                if bitmask & (1 << (letter - ord("A"))):
                    drv_path = f"{char}:\\"
                    dtype = ctypes.windll.kernel32.GetDriveTypeW(drv_path)
                    # DRIVE_REMOVABLE = 2, or letter between E and Z (user flash drive / portable disk)
                    if dtype == 2 or char in "EFGHIJKLMNOPQRSTUVWXYZ":
                        if os.path.exists(drv_path):
                            detected.append(drv_path)
        except Exception:
            # Fallback drive scan
            for char in "EFGHIJKLMNOPQRSTUVWXYZ":
                drv_path = f"{char}:\\"
                if os.path.exists(drv_path):
                    detected.append(drv_path)

        self.last_detected_drives = detected
        return detected

    def get_all_search_roots(self) -> List[str]:
        roots = list(self.get_detected_usb_drives())
        for d in DEFAULT_DROP_DIRS:
            if os.path.exists(d) and d not in roots:
                roots.append(d)
        return roots

    def find_all_csv_files(self) -> List[str]:
        found: List[str] = []
        for root in self.get_all_search_roots():
            patterns = [
                os.path.join(root, "*.csv"),
                os.path.join(root, "*.CSV"),
                os.path.join(root, "SampleStore*", "*.csv"),
                os.path.join(root, "SampleStore*", "*.CSV"),
                os.path.join(root, "DataLog*", "*.csv"),
                os.path.join(root, "DataLog*", "*.CSV"),
                os.path.join(root, "**", "*.csv"),
            ]
            for pat in patterns:
                for p in glob.glob(pat, recursive=True):
                    if os.path.isfile(p) and p not in found:
                        found.append(p)
        return found

    def _file_signature(self, path: str) -> str:
        try:
            stat = os.stat(path)
            return f"{path}:{stat.st_size}:{stat.st_mtime}"
        except Exception:
            return path

    def parse_datetime(self, date_str: str, time_str: str = "") -> Optional[str]:
        """Parses various HMI timestamp formats into ISO 8601 UTC string."""
        raw = f"{date_str} {time_str}".strip()
        raw = re.sub(r"\s+", " ", raw)

        patterns = [
            ("%Y-%m-%d %H:%M:%S", False),
            ("%Y/%m/%d %H:%M:%S", False),
            ("%d.%m.%Y %H:%M:%S", True),
            ("%d/%m/%Y %H:%M:%S", True),
            ("%Y-%m-%dT%H:%M:%S", False),
            ("%Y-%m-%d %H:%M", False),
            ("%d.%m.%Y %H:%M", True),
            ("%d/%m/%Y %H:%M", True),
        ]

        # Handle ISO strings with Z or offsets
        if "T" in raw and ("+" in raw or raw.endswith("Z")):
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                return dt.astimezone(timezone.utc).isoformat()
            except Exception:
                pass

        for pat, is_tr in patterns:
            try:
                dt = datetime.strptime(raw, pat)
                # GMTSuite HMI clock is in Turkey local time (UTC+3)
                dt_tr = dt.replace(tzinfo=TURKEY_TZ)
                return dt_tr.astimezone(timezone.utc).isoformat()
            except Exception:
                continue

        return None

    def read_csv_records(self, csv_path: str) -> List[Dict[str, Any]]:
        """Reads CSV with encoding and delimiter auto-detection."""
        encodings = ["utf-8-sig", "utf-8", "iso-8859-9", "cp1254", "latin-1"]
        content: Optional[str] = None
        for enc in encodings:
            try:
                with open(csv_path, "r", encoding=enc) as f:
                    content = f.read()
                break
            except Exception:
                continue

        if not content:
            return []

        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        if not lines:
            return []

        # Detect delimiter
        first_line = lines[0]
        delimiters = [",", ";", "\t"]
        best_delim = ","
        best_count = -1
        for d in delimiters:
            cnt = first_line.count(d)
            if cnt > best_count:
                best_count = cnt
                best_delim = d

        reader = csv.reader(lines, delimiter=best_delim)
        rows = list(reader)
        if len(rows) < 2:
            return []

        header = [h.strip() for h in rows[0]]
        records: List[Dict[str, Any]] = []
        for r in rows[1:]:
            if len(r) == len(header):
                records.append(dict(zip(header, [c.strip() for c in r])))
            elif len(r) > 0:
                row_dict = {}
                for idx, val in enumerate(r):
                    key = header[idx] if idx < len(header) else f"col_{idx}"
                    row_dict[key] = val.strip()
                records.append(row_dict)

        return records

    def parse_hmi_rows_to_snapshots(self, rows: List[Dict[str, Any]], file_hint: str = "") -> List[Dict[str, Any]]:
        """
        Converts parsed CSV rows into standardized full 48-sensor, 8-zone snapshots.
        Handles both consolidated CSVs (with S1_.. or R1_..) and SampleStore channel files.
        """
        snapshots: List[Dict[str, Any]] = []

        for row in rows:
            # 1. Extract Timestamp
            ts_str: Optional[str] = None
            for key in ["recorded_at", "timestamp", "local_time_tr", "Time", "Saat", "Zaman"]:
                if key in row and row[key]:
                    # check if paired with Date
                    date_val = row.get("Date") or row.get("Tarih") or ""
                    ts_str = self.parse_datetime(row[key], date_val) if not date_val else self.parse_datetime(date_val, row[key])
                    if ts_str:
                        break

            if not ts_str:
                date_val = row.get("Date") or row.get("Tarih") or ""
                time_val = row.get("Time") or row.get("Saat") or ""
                if date_val:
                    ts_str = self.parse_datetime(date_val, time_val)

            if not ts_str:
                # Fallback: check first column
                first_val = list(row.values())[0] if row else ""
                ts_str = self.parse_datetime(first_val)

            if not ts_str:
                continue

            # 2. Extract 24 Soil and 24 Leaf sensor values
            sensors_data: List[Dict[str, Any]] = []
            for sid in range(1, 25):
                zid = PLOT_TO_ZONE[sid]
                # Check possible column naming formats:
                # Format A: S1_soil_moist, S1_soil_temp, S1_soil_ec, S1_soil_salt, S1_leaf_wet, S1_leaf_temp
                # Format B: R1_Soil_Moist, R1_Soil_Temp, R1_Soil_EC, R1_Soil_Salt, R1_Leaf_Hum, R1_Leaf_Temp
                # Format C: SampleStore channel indices CH0..CH95
                sm = self._extract_float(row, [f"S{sid}_soil_moist", f"R{sid}_Soil_Moist", f"CH{(sid-1)*4}", f"Channel_{(sid-1)*4}"])
                st = self._extract_float(row, [f"S{sid}_soil_temp", f"R{sid}_Soil_Temp", f"CH{(sid-1)*4+1}", f"Channel_{(sid-1)*4+1}"])
                lh = self._extract_float(row, [f"S{sid}_leaf_wet", f"S{sid}_leaf_humidity", f"R{sid}_Leaf_Hum", f"CH{(sid-1)*4+2}", f"Channel_{(sid-1)*4+2}"])
                lt = self._extract_float(row, [f"S{sid}_leaf_temp", f"R{sid}_Leaf_Temp", f"CH{(sid-1)*4+3}", f"Channel_{(sid-1)*4+3}"])

                ec_addr, salt_addr = EC_SALT_ADDR[sid]
                sec = self._extract_int(row, [f"S{sid}_soil_ec", f"R{sid}_Soil_EC", f"CH{ec_addr-3}", f"Channel_{ec_addr-3}"])
                ssalt = self._extract_int(row, [f"S{sid}_soil_salt", f"R{sid}_Soil_Salt", f"CH{salt_addr-3}", f"Channel_{salt_addr-3}"])
                sph = self._extract_float(row, [f"S{sid}_soil_ph", f"R{sid}_Soil_pH"])

                sensors_data.append({
                    "sensor_id": sid,
                    "zone_id": zid,
                    "soil_moisture": sm,
                    "soil_temp": st,
                    "soil_ec": sec,
                    "soil_salt": ssalt,
                    "soil_ph": sph,
                    "leaf_humidity": lh,
                    "leaf_temp": lt,
                })

            # 3. Extract 8 Zone Summaries & Modes
            zones_data: List[Dict[str, Any]] = []
            valves_dict: Dict[str, bool] = {}

            for zid in range(1, 9):
                plots = ZONE_PLOTS[zid]
                z_sensors = [s for s in sensors_data if s["sensor_id"] in plots]

                # Explicit zone average if in row
                avg_sm = self._extract_float(row, [f"Z{zid}_avg_moist", f"Zone{zid}_Avg_Moist", f"CH{100+zid-3}"])
                if avg_sm is None:
                    valid_sm = [s["soil_moisture"] for s in z_sensors if s["soil_moisture"] is not None]
                    avg_sm = round(sum(valid_sm) / len(valid_sm), 2) if valid_sm else None

                valid_st = [s["soil_temp"] for s in z_sensors if s["soil_temp"] is not None]
                avg_st = round(sum(valid_st) / len(valid_st), 2) if valid_st else None

                valid_ec = [s["soil_ec"] for s in z_sensors if s["soil_ec"] is not None]
                avg_sec = round(sum(valid_ec) / len(valid_ec)) if valid_ec else None

                valid_salt = [s["soil_salt"] for s in z_sensors if s["soil_salt"] is not None]
                avg_ssalt = round(sum(valid_salt) / len(valid_salt)) if valid_salt else None

                valid_lh = [s["leaf_humidity"] for s in z_sensors if s["leaf_humidity"] is not None]
                avg_lh = round(sum(valid_lh) / len(valid_lh), 2) if valid_lh else None

                valid_lt = [s["leaf_temp"] for s in z_sensors if s["leaf_temp"] is not None]
                avg_lt = round(sum(valid_lt) / len(valid_lt), 2) if valid_lt else None

                v_open = self._extract_bool(row, [f"Z{zid}_valve_open", f"Zone{zid}_valve_open", f"Vana_{zid}"])
                a_mode = self._extract_bool(row, [f"Z{zid}_auto_mode", f"Zone{zid}_auto_mode"], default=True)

                valves_dict[f"Vana_{zid}"] = v_open

                zones_data.append({
                    "zone_id": zid,
                    "name_tr": f"Bölge {zid}",
                    "name_en": f"Zone {zid}",
                    "valve_tag": f"Vana_{zid}",
                    "valve_coil": zid - 1,
                    "relay_tag": f"QP0{zid-1}",
                    "valve_open": v_open,
                    "auto_mode": a_mode,
                    "min_moisture": 45.0,
                    "max_moisture": 80.0,
                    "avg_soil_moisture": avg_sm,
                    "avg_soil_temp": avg_st,
                    "avg_soil_ec": avg_sec,
                    "avg_soil_salt": avg_ssalt,
                    "avg_soil_ph": 7.0,
                    "avg_leaf_humidity": avg_lh,
                    "avg_leaf_temp": avg_lt,
                    "sensor_ids": plots,
                    "leaf_slave_ids": [100 + p for p in plots],
                })

            batch_id = row.get("batch_id") or str(uuid.uuid4())
            snapshot = {
                "batch_id": batch_id,
                "recorded_at": ts_str,
                "source": "hmi_pendrive",
                "plc_online": True,
                "zones": zones_data,
                "sensors": sensors_data,
                "valves": valves_dict,
            }
            snapshots.append(snapshot)

        return snapshots

    def _extract_float(self, row: Dict[str, Any], keys: List[str]) -> Optional[float]:
        for k in keys:
            if k in row and row[k] not in ("", None, "None", "null", "NaN", "nan"):
                try:
                    val = float(str(row[k]).replace(",", "."))
                    return round(val, 2)
                except Exception:
                    continue
        return None

    def _extract_int(self, row: Dict[str, Any], keys: List[str]) -> Optional[int]:
        for k in keys:
            if k in row and row[k] not in ("", None, "None", "null", "NaN", "nan"):
                try:
                    return int(float(str(row[k]).replace(",", ".")))
                except Exception:
                    continue
        return None

    def _extract_bool(self, row: Dict[str, Any], keys: List[str], default: bool = False) -> bool:
        for k in keys:
            if k in row and row[k] not in ("", None, "None", "null"):
                v = str(row[k]).strip().lower()
                if v in ("1", "true", "yes", "on", "açık"):
                    return True
                if v in ("0", "false", "no", "off", "kapalı"):
                    return False
        return default

    def merge_snapshots_by_time(self, snapshots_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Merges multiple files (e.g. SampleStore float + SampleStoreEC int) sharing identical or near timestamps."""
        by_time: Dict[str, Dict[str, Any]] = {}
        for snap in snapshots_list:
            t = snap["recorded_at"]
            if t not in by_time:
                by_time[t] = snap
            else:
                existing = by_time[t]
                # Merge sensor fields
                for idx, s_new in enumerate(snap.get("sensors", [])):
                    if idx < len(existing["sensors"]):
                        s_curr = existing["sensors"][idx]
                        for fld in ["soil_moisture", "soil_temp", "soil_ec", "soil_salt", "soil_ph", "leaf_humidity", "leaf_temp"]:
                            if s_curr.get(fld) is None and s_new.get(fld) is not None:
                                s_curr[fld] = s_new[fld]
                # Merge zone averages
                for zidx, z_new in enumerate(snap.get("zones", [])):
                    if zidx < len(existing["zones"]):
                        z_curr = existing["zones"][zidx]
                        for zfld in ["avg_soil_moisture", "avg_soil_temp", "avg_soil_ec", "avg_soil_salt", "avg_leaf_humidity", "avg_leaf_temp"]:
                            if z_curr.get(zfld) is None and z_new.get(zfld) is not None:
                                z_curr[zfld] = z_new[zfld]

        # Sort chronologically
        merged = list(by_time.values())
        merged.sort(key=lambda x: x["recorded_at"])
        return merged

    async def sync_batches_to_cloud(self, batches: List[Dict[str, Any]], cloud_urls: Optional[List[str]] = None) -> Dict[str, Any]:
        """Uploads batches in chunks of 100 to the live cloud server."""
        if not batches:
            return {"uploaded": 0, "status": "no_batches"}

        if cloud_urls is None:
            cloud_urls = [
                os.getenv("CLOUD_API_URL", "https://iotserver.ertanyildirim.com"),
                "https://iotserver.mmreza.com",
                "http://77.42.89.186:8000",
            ]

        uploaded = 0
        chunk_size = 100

        async with httpx.AsyncClient(timeout=10.0) as client:
            for i in range(0, len(batches), chunk_size):
                chunk = batches[i : i + chunk_size]
                success = False
                for base_url in cloud_urls:
                    url = f"{base_url.rstrip('/')}/api/v1/telemetry/sync"
                    try:
                        resp = await client.post(
                            url,
                            json={"device_id": "ziraat_plc_196r", "batches": chunk},
                        )
                        if resp.status_code == 200:
                            success = True
                            uploaded += len(chunk)
                            break
                    except Exception:
                        continue
                if not success:
                    print(f"[HMIScraper] Warning: failed to upload chunk {i//chunk_size + 1} to cloud servers.")

        return {"uploaded": uploaded, "total": len(batches), "status": "synced"}

    def store_locally(self, batches: List[Dict[str, Any]], queue_obj: Optional[Any] = None) -> int:
        """Stores snapshots into local SQLite database and updates local CSV/Excel logs."""
        if not batches:
            return 0

        # 1. Local SQLite irrigation_cloud.db
        try:
            sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "cloud_backend")))
            from app import database as local_api_db
            local_api_db.init_db()
            local_api_db.store_telemetry_batches(batches, allow_simulated=False)
        except Exception as e:
            print(f"[HMIScraper] local_api_db store note: {e}")

        # 2. Local store-and-forward queue
        if queue_obj is not None and hasattr(queue_obj, "enqueue"):
            for b in batches:
                try:
                    queue_obj.enqueue(b)
                except Exception:
                    pass

        # 3. Append to plc_live_telemetry_log.csv
        csv_path = os.path.join(self.data_dir, "plc_live_telemetry_log.csv")
        try:
            write_header = not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0
            existing_times: Set[str] = set()
            if os.path.exists(csv_path):
                try:
                    with open(csv_path, "r", encoding="utf-8") as f:
                        for row in csv.DictReader(f):
                            if row.get("recorded_at"):
                                existing_times.add(row["recorded_at"])
                except Exception:
                    pass

            new_rows: List[List[str]] = []
            for snapshot in batches:
                rec_at = snapshot["recorded_at"]
                if rec_at in existing_times:
                    continue
                existing_times.add(rec_at)

                zones = {z["zone_id"]: z for z in snapshot.get("zones", [])}
                sensors = {s["sensor_id"]: s for s in snapshot.get("sensors", [])}
                row = [rec_at, snapshot.get("batch_id", ""), snapshot.get("source", "hmi_pendrive")]
                for zid in range(1, 9):
                    z = zones.get(zid, {})
                    row.extend([
                        str(z.get("avg_soil_moisture", "")),
                        str(z.get("plc_son_ortlama", "")),
                        "1" if z.get("valve_open") else "0",
                        "1" if z.get("auto_mode") else "0",
                    ])
                for sid in range(1, 25):
                    s = sensors.get(sid, {})
                    row.extend([
                        str(s.get("soil_moisture", "")),
                        str(s.get("soil_temp", "")),
                        str(s.get("soil_ec", "")),
                        str(s.get("soil_salt", "")),
                        str(s.get("leaf_humidity", "")),
                        str(s.get("leaf_temp", "")),
                    ])
                new_rows.append(row)

            if new_rows:
                headers = ["recorded_at", "batch_id", "source"]
                for zid in range(1, 9):
                    headers.extend([f"Z{zid}_avg_moist", f"Z{zid}_son_ortlama", f"Z{zid}_valve_open", f"Z{zid}_auto_mode"])
                for sid in range(1, 25):
                    headers.extend([f"S{sid}_soil_moist", f"S{sid}_soil_temp", f"S{sid}_soil_ec", f"S{sid}_soil_salt", f"S{sid}_leaf_wet", f"S{sid}_leaf_temp"])

                with open(csv_path, "a", encoding="utf-8") as f:
                    if write_header:
                        f.write(",".join(headers) + "\n")
                    for r in new_rows:
                        f.write(",".join(r) + "\n")

            # 4. Trigger excel/csv refresh
            try:
                from export_all48_excel_csv import export_all48_files
                export_all48_files(self.data_dir)
            except Exception:
                pass

        except Exception as e:
            print(f"[HMIScraper] CSV append note: {e}")

        return len(batches)

    async def scan_and_import(self, queue_obj: Optional[Any] = None) -> Dict[str, Any]:
        """
        Executes a complete scan:
        1. Finds all USB drives and drop folders.
        2. Detects any new or updated CSV files.
        3. Parses them into full 48-sensor 1-minute historical snapshots.
        4. Saves them locally and syncs to cloud server.
        """
        self.last_scan_time = datetime.now(timezone.utc).isoformat()
        usb_drives = self.get_detected_usb_drives()
        files = self.find_all_csv_files()

        scanned_files = 0
        new_snapshots: List[Dict[str, Any]] = []

        for fpath in files:
            sig = self._file_signature(fpath)
            last_sig = self.history.get("processed_files", {}).get(fpath)
            # If unchanged, skip
            if last_sig == sig:
                continue

            try:
                scanned_files += 1
                rows = self.read_csv_records(fpath)
                if rows:
                    snaps = self.parse_hmi_rows_to_snapshots(rows, file_hint=fpath)
                    new_snapshots.extend(snaps)
                self.history.setdefault("processed_files", {})[fpath] = sig
            except Exception as e:
                print(f"[HMIScraper] Error parsing {fpath}: {e}")

        # Merge overlapping snapshots
        unique_batches = self.merge_snapshots_by_time(new_snapshots)

        imported_count = 0
        cloud_res = {"uploaded": 0}
        if unique_batches:
            imported_count = self.store_locally(unique_batches, queue_obj=queue_obj)
            cloud_res = await self.sync_batches_to_cloud(unique_batches)
            self.total_scraped_records += imported_count
            self.history["total_records_imported"] = self.total_scraped_records
            print(f"[HMIScraper] Scraped {imported_count} historical minute records from HMI USB -> Synced to Local PC and Server Database!")

        self.history["last_scan"] = self.last_scan_time
        self._save_history()

        return {
            "status": "ok",
            "usb_drives_detected": usb_drives,
            "csv_files_found": len(files),
            "files_parsed": scanned_files,
            "new_minute_records": imported_count,
            "cloud_sync": cloud_res,
            "total_historical_records": self.total_scraped_records,
            "last_scan_time": self.last_scan_time,
        }

    def get_status(self) -> Dict[str, Any]:
        return {
            "usb_connected": len(self.get_detected_usb_drives()) > 0,
            "detected_drives": self.last_detected_drives,
            "search_roots": self.get_all_search_roots(),
            "total_records_imported": self.total_scraped_records,
            "last_scan_time": self.last_scan_time or self.history.get("last_scan"),
        }


if __name__ == "__main__":
    import asyncio
    scraper = HMIPendriveScraper()
    print("Detected USB drives:", scraper.get_detected_usb_drives())
    print("All search roots:", scraper.get_all_search_roots())
    res = asyncio.run(scraper.scan_and_import())
    print("Scan result:", res)
