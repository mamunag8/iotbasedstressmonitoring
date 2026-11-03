import csv
import glob
import os
from datetime import datetime
from typing import Any, Dict, List
import pandas as pd


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

EC_SALT_ADDR = {
    1: (3, 4), 2: (7, 8), 3: (81, 37), 4: (80, 36),
    5: (79, 35), 6: (78, 34), 7: (77, 33), 8: (76, 32),
    9: (75, 31), 10: (96, 52), 11: (95, 51), 12: (94, 50),
    13: (93, 49), 14: (91, 48), 15: (92, 47), 16: (90, 46),
    17: (89, 45), 18: (88, 44), 19: (87, 43), 20: (86, 42),
    21: (85, 41), 22: (84, 40), 23: (83, 39), 24: (82, 38),
}


def scan_pendrive_csvs() -> List[str]:
    found: List[str] = []
    for drv in "EFGHIJKLMNOPQRSTUVWXYZ":
        root = f"{drv}:\\"
        if os.path.exists(root):
            for pat in ("SampleStore*/*.csv", "SampleStore*/*.CSV", "*.csv"):
                for p in glob.glob(os.path.join(root, pat)):
                    found.append(p)
    return found


def export_all48_files(data_dir: str) -> Dict[str, Any]:
    src_csv = os.path.join(data_dir, "plc_live_telemetry_log.csv")
    out_csv = os.path.join(data_dir, "All_48_Sensors_Every_Minute_Data.csv")
    out_xlsx = os.path.join(data_dir, "All_48_Sensors_Every_Minute_Data.xlsx")

    if not os.path.exists(src_csv):
        return {"ok": False, "error": "Source CSV not found"}

    df = pd.read_csv(src_csv)
    # Add local timestamp column (UTC+3 Turkey time) as first column
    local_times: List[str] = []
    for ts in df["recorded_at"].astype(str):
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
            local_times.append(dt.strftime("%Y-%m-%d %H:%M:%S"))
        except Exception:
            local_times.append(ts)
    df.insert(0, "local_time_tr", local_times)

    # Save clean UTF-8-SIG CSV for instant Excel opening
    df.to_csv(out_csv, index=False, encoding="utf-8-sig")

    # Build Sheet 2: Latest 48 Sensors Snapshot (24 Soil + 24 Leaf)
    latest = df.iloc[-1] if len(df) > 0 else {}
    snapshot_rows: List[Dict[str, Any]] = []
    for plot_id in range(1, 25):
        zid = PLOT_TO_ZONE[plot_id]
        base_4x = 2001 + (plot_id - 1) * 8
        ec_4x, salt_4x = EC_SALT_ADDR[plot_id]
        snapshot_rows.append({
            "Sensor_Group": f"Soil Sensor #{plot_id} (Plot R{plot_id})",
            "Leaf_Sensor_Group": f"Leaf Sensor #{plot_id} (Plot R{plot_id}_L)",
            "Zone": f"Zone {zid}",
            "Soil_Slave_ID": plot_id,
            "Leaf_Slave_ID": 100 + plot_id,
            "Soil_Moisture_%": latest.get(f"S{plot_id}_soil_moist", ""),
            "Soil_Temp_C": latest.get(f"S{plot_id}_soil_temp", ""),
            "Soil_EC_uS_cm": latest.get(f"S{plot_id}_soil_ec", ""),
            "Soil_Salt_mg_L": latest.get(f"S{plot_id}_soil_salt", ""),
            "Leaf_Humidity_%": latest.get(f"S{plot_id}_leaf_wet", ""),
            "Leaf_Temp_C": latest.get(f"S{plot_id}_leaf_temp", ""),
            "HMI_Pendrive_Tags": f"R{plot_id}_Soil_Moist, R{plot_id}_Soil_Temp, R{plot_id}_Soil_EC, R{plot_id}_Soil_Salt, R{plot_id}_Leaf_Hum, R{plot_id}_Leaf_Temp",
            "Modbus_4X_Registers": f"4X:{base_4x}..{base_4x+7}, 4X:{ec_4x}, 4X:{salt_4x}",
        })
    df_snap = pd.DataFrame(snapshot_rows)

    # Build Sheet 3: HMI Pendrive Datalogger Channel Map
    map_rows: List[Dict[str, Any]] = []
    for s in range(1, 25):
        b = 2001 + (s - 1) * 8
        for idx, (p_name, unit) in enumerate([
            (f"R{s}_Soil_Moist", "%"),
            (f"R{s}_Soil_Temp", "C"),
            (f"R{s}_Leaf_Hum", "%"),
            (f"R{s}_Leaf_Temp", "C"),
        ]):
            map_rows.append({
                "Pendrive_Folder": "SampleStore",
                "Channel_Index": (s - 1) * 4 + idx,
                "Tag_Name": p_name,
                "Modbus_Address": f"4X:{b + idx*2}",
                "Data_Type": "32-bit Float (2 Words)",
                "Unit": unit,
                "Interval": "60 sec (1 min)",
            })
    for s in range(1, 25):
        ec_4x, salt_4x = EC_SALT_ADDR[s]
        map_rows.append({
            "Pendrive_Folder": "SampleStoreEC",
            "Channel_Index": ec_4x - 3,
            "Tag_Name": f"R{s}_Soil_EC",
            "Modbus_Address": f"4X:{ec_4x}",
            "Data_Type": "16-bit Signed Int (1 Word)",
            "Unit": "uS/cm",
            "Interval": "60 sec (1 min)",
        })
        map_rows.append({
            "Pendrive_Folder": "SampleStoreEC",
            "Channel_Index": salt_4x - 3,
            "Tag_Name": f"R{s}_Soil_Salt",
            "Modbus_Address": f"4X:{salt_4x}",
            "Data_Type": "16-bit Signed Int (1 Word)",
            "Unit": "mg/L",
            "Interval": "60 sec (1 min)",
        })
    for z in range(1, 9):
        addr = 100 + z
        map_rows.append({
            "Pendrive_Folder": "SampleStoreEC",
            "Channel_Index": addr - 3,
            "Tag_Name": f"Zone{z}_Avg_Moist",
            "Modbus_Address": f"4X:{addr}",
            "Data_Type": "16-bit Signed Int (1 Word)",
            "Unit": "%",
            "Interval": "60 sec (1 min)",
        })
    df_map = pd.DataFrame(map_rows)

    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="All_48_Sensors_Minute_Log", index=False)
        df_snap.to_excel(writer, sheet_name="Latest_48_Sensors_Snapshot", index=False)
        df_map.to_excel(writer, sheet_name="HMI_Pendrive_Datalogger_Map", index=False)

    return {
        "ok": True,
        "rows_exported": len(df),
        "columns_exported": len(df.columns),
        "csv_path": out_csv,
        "xlsx_path": out_xlsx,
        "pendrive_files_detected": scan_pendrive_csvs(),
    }


if __name__ == "__main__":
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    res = export_all48_files(data_dir)
    print(res)
