"""
FastAPI Router for Isolated Mobile-First PhD Field, Instrument, Lab,
Treatment, HOBO Climate & Professor A4 Print Web App (/data-app).

Zero Extra Dependencies:
- Uses only standard library + FastAPI + openpyxl + httpx already present in container.
"""

import csv
import io
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from . import field_data_ai as fai
from . import field_data_db as fdb

OPERATOR_PIN = os.getenv("OPERATOR_SECURITY_PIN", "atauniiot")

router = APIRouter()


def _verify_pin(pin_header: Optional[str]) -> None:
    supplied = (pin_header or "").strip().lower()
    if supplied != OPERATOR_PIN.lower():
        raise HTTPException(
            status_code=403,
            detail="Read-Only Mode: Unlock with your Operator Security PIN (top-right lock icon) to save, edit, or delete PhD data.",
        )


# ==============================================================================
# Pydantic Request Schemas
# ==============================================================================


class PhotoUploadAndAIRequest(BaseModel):
    image_base64: str
    parameter_key: str = "generic"
    save_only: bool = False
    override_model: Optional[str] = None


class MeasurementCreateRequest(BaseModel):
    experiment_code: str = "EXP2"
    measured_at: Optional[str] = None
    dat: Optional[int] = None
    fertigation_arm: str = "IoT"
    treatment_no: str = "T1"
    replicate_no: str = "R1"
    plant_no: str = "P1"
    truss_no: Optional[int] = None
    category: Optional[str] = None
    parameter_key: str
    parameter_label: Optional[str] = None
    unit: Optional[str] = None
    manual_value: Optional[float] = None
    ai_value: Optional[float] = None
    ai_secondary_value: Optional[float] = None
    final_value: Optional[float] = None
    verification_status: Optional[str] = None
    ai_confidence: Optional[float] = None
    ai_model: Optional[str] = None
    ai_extra: Optional[Dict[str, Any]] = None
    photo_rel_path: Optional[str] = None
    notes: Optional[str] = ""
    recorded_by: Optional[str] = "Mamunur Reza"


class BulkMeasurementsCreateRequest(BaseModel):
    items: List[MeasurementCreateRequest]


class MeasurementUpdateRequest(BaseModel):
    experiment_code: Optional[str] = None
    measured_at: Optional[str] = None
    dat: Optional[int] = None
    fertigation_arm: Optional[str] = None
    treatment_no: Optional[str] = None
    replicate_no: Optional[str] = None
    plant_no: Optional[str] = None
    truss_no: Optional[int] = None
    category: Optional[str] = None
    parameter_key: Optional[str] = None
    parameter_label: Optional[str] = None
    unit: Optional[str] = None
    manual_value: Optional[float] = None
    ai_value: Optional[float] = None
    final_value: Optional[float] = None
    verification_status: Optional[str] = None
    notes: Optional[str] = None


class BulkMeasurementsDeleteRequest(BaseModel):
    record_ids: List[str]


class BulkMeasurementsUpdateRequest(BaseModel):
    record_ids: List[str]
    updates: MeasurementUpdateRequest
    notes_mode: str = "keep"  # keep | replace | append
    value_mode: str = "keep"  # keep | set | adjust
    scale_factor: Optional[float] = None
    add_offset: Optional[float] = None


class BulkTreatmentsDeleteRequest(BaseModel):
    batch_ids: List[str]


class TreatmentBatchCreateRequest(BaseModel):
    experiment_code: str = "EXP2"
    applied_at: str
    dat: Optional[int] = None
    scope_type: str = "group"
    group_label: Optional[str] = None
    target_arms: List[str] = ["IoT"]
    target_treatments: List[str] = ["T1"]
    target_replicates: List[str] = ["R1", "R2", "R3", "R4"]
    application_type: str = "nahs_humic_pulse"
    nahs_um: float = 0.0
    nahs_stock_mg_100ml: Optional[float] = None
    humic_mll: float = 0.0
    humic_product: str = "LIQHUMUS Liquid 18 (NK)"
    nacl_mm: float = 0.0
    nutrient_stage: Optional[str] = None
    volume_per_planter_l: Optional[float] = None
    total_volume_l: Optional[float] = None
    solution_ec_uscm: Optional[int] = None
    solution_ph: Optional[float] = None
    hours_after_morning_irrig: Optional[float] = None
    photo_rel_path: Optional[str] = None
    notes: Optional[str] = ""
    recorded_by: Optional[str] = "Mamunur Reza"
    sync_to_stress_studio: bool = True


class AISettingsUpdateRequest(BaseModel):
    provider: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    primary_model: Optional[str] = None
    secondary_model: Optional[str] = None
    dual_verify_enabled: Optional[bool] = None


# ==============================================================================
# HTML & PWA Routes (/data-app)
# ==============================================================================


def _serve_data_app_html() -> HTMLResponse:
    html_path = os.path.join(os.path.dirname(__file__), "field_data_app.html")
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
        return HTMLResponse("<h1>Field & Lab Data App is loading...</h1>", status_code=503)


@router.get("/data-app/manifest.json")
async def data_app_manifest():
    return JSONResponse({
        "name": "Ataturk Univ PhD Field & Lab Data",
        "short_name": "PhD Data",
        "start_url": "/data-app",
        "display": "standalone",
        "background_color": "#0f172a",
        "theme_color": "#0284c7",
        "icons": [
            {
                "src": "https://atauni.edu.tr/wp-content/uploads/2025/01/cropped-icon-1-192x192.png",
                "sizes": "192x192",
                "type": "image/png",
            }
        ],
    })


@router.get("/data-app", response_class=HTMLResponse)
@router.get("/data-app/{tab_slug}", response_class=HTMLResponse)
async def web_field_data_app(tab_slug: Optional[str] = None):
    return _serve_data_app_html()


# ==============================================================================
# Metadata Catalog, AI Vision & Photo Serving APIs
# ==============================================================================


@router.get("/api/v1/field-data/catalog")
async def get_field_catalog():
    return {
        "transplant_date": fdb.get_transplant_date(),
        "exp2_treatments": fdb.EXP2_TREATMENTS,
        "exp2_field_layout": fdb.EXP2_FIELD_LAYOUT,
        "exp1_treatments": fdb.EXP1_TREATMENTS,
        "parameters": fdb.PARAMETER_CATALOG,
        "ai_settings": fdb.get_ai_settings(include_secrets=False),
    }


@router.get("/api/v1/field-data/ai-settings")
async def get_ai_settings_endpoint():
    return fdb.get_ai_settings(include_secrets=False)


@router.post("/api/v1/field-data/ai-settings")
async def update_ai_settings_endpoint(
    req: AISettingsUpdateRequest,
    x_operator_pin: Optional[str] = Header(None),
):
    _verify_pin(x_operator_pin)
    updated = fdb.update_ai_settings(req.model_dump(exclude_none=True))
    return {"status": "saved", "ai_settings": updated}


@router.post("/api/v1/field-data/ai-read")
async def ai_read_photo_endpoint(
    req: PhotoUploadAndAIRequest,
    x_operator_pin: Optional[str] = Header(None),
):
    _verify_pin(x_operator_pin)
    if req.save_only:
        raw_bytes, mime_type = fai.decode_base64_image(req.image_base64)
        rel_path = fai.save_photo_bytes(raw_bytes, mime_type)
        return {
            "status": "saved_only",
            "photo_rel_path": rel_path,
            "photo_url": f"/api/v1/field-data/photos/{rel_path}",
            "ai_value": None,
            "verification_status": "human_confirmed",
            "message": "Photo attached and saved to server.",
        }
    return await fai.analyze_field_photo(
        image_b64=req.image_base64,
        parameter_key=req.parameter_key,
        override_model=req.override_model,
    )


@router.get("/api/v1/field-data/photos/{month_dir}/{filename}")
async def serve_field_photo(month_dir: str, filename: str):
    if not re.match(r"^\d{4}-\d{2}$", month_dir) or not re.match(r"^[a-fA-F0-9_.-]+\.(jpg|jpeg|png|webp)$", filename):
        raise HTTPException(status_code=400, detail="Invalid photo path")
    full_path = os.path.join(fai.get_photo_storage_root(), month_dir, filename)
    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail="Photo not found")
    return FileResponse(full_path)


# ==============================================================================
# Measurements CRUD & Summary Statistics APIs
# ==============================================================================


@router.post("/api/v1/field-data/measurements")
async def create_measurement_endpoint(
    req: MeasurementCreateRequest,
    x_operator_pin: Optional[str] = Header(None),
):
    _verify_pin(x_operator_pin)
    try:
        rec = fdb.add_measurement(req.model_dump())
        return {"status": "saved", "record": rec}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/v1/field-data/measurements/bulk")
async def create_bulk_measurements_endpoint(
    req: BulkMeasurementsCreateRequest,
    x_operator_pin: Optional[str] = Header(None),
):
    _verify_pin(x_operator_pin)
    saved: List[Dict[str, Any]] = []
    for item in req.items:
        try:
            saved.append(fdb.add_measurement(item.model_dump()))
        except ValueError:
            continue
    return {"status": "saved", "saved_count": len(saved), "records": saved}


@router.get("/api/v1/field-data/measurements")
async def list_measurements_endpoint(
    experiment_code: Optional[str] = Query("EXP2"),
    fertigation_arm: Optional[str] = Query(None),
    treatment_no: Optional[str] = Query(None),
    replicate_no: Optional[str] = Query(None),
    plant_no: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    parameter_key: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    dat_min: Optional[int] = Query(None),
    dat_max: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(1000, ge=1, le=20000),
):
    rows = fdb.query_measurements(
        experiment_code=experiment_code,
        fertigation_arm=fertigation_arm,
        treatment_no=treatment_no,
        replicate_no=replicate_no,
        plant_no=plant_no,
        category=category,
        parameter_key=parameter_key,
        start_date=start_date,
        end_date=end_date,
        dat_min=dat_min,
        dat_max=dat_max,
        search=search,
        limit=limit,
    )
    param_order = (
        [x.strip() for x in parameter_key.split(",") if x.strip()]
        if (parameter_key and parameter_key != "ALL")
        else None
    )
    summary = fdb.compute_summary_statistics(rows, experiment_code=experiment_code or "EXP2", parameter_order=param_order)
    return {
        "records": rows,
        "summary": summary,
    }


@router.post("/api/v1/field-data/measurements/bulk-update")
async def bulk_update_measurements_endpoint(
    req: BulkMeasurementsUpdateRequest,
    x_operator_pin: Optional[str] = Header(None),
):
    _verify_pin(x_operator_pin)
    if not req.record_ids:
        raise HTTPException(status_code=400, detail="No record IDs selected")
    updated = fdb.bulk_update_measurements(
        record_ids=req.record_ids,
        updates=req.updates.model_dump(exclude_unset=True),
        notes_mode=req.notes_mode,
        value_mode=req.value_mode,
        scale_factor=req.scale_factor,
        add_offset=req.add_offset,
    )
    return {"status": "updated", "updated_count": len(updated), "records": updated}


@router.post("/api/v1/field-data/measurements/bulk-delete")
async def bulk_delete_measurements_endpoint(
    req: BulkMeasurementsDeleteRequest,
    x_operator_pin: Optional[str] = Header(None),
):
    _verify_pin(x_operator_pin)
    if not req.record_ids:
        raise HTTPException(status_code=400, detail="No record IDs selected")
    deleted = fdb.bulk_delete_measurements(req.record_ids)
    return {"status": "deleted", "deleted_count": deleted}


@router.put("/api/v1/field-data/measurements/{record_id}")
async def update_measurement_endpoint(
    record_id: str,
    req: MeasurementUpdateRequest,
    x_operator_pin: Optional[str] = Header(None),
):
    _verify_pin(x_operator_pin)
    updated = fdb.update_measurement(record_id, req.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Record not found")
    return {"status": "updated", "record": updated}


@router.delete("/api/v1/field-data/measurements/{record_id}")
async def delete_measurement_endpoint(
    record_id: str,
    x_operator_pin: Optional[str] = Header(None),
):
    _verify_pin(x_operator_pin)
    ok = fdb.delete_measurement(record_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Record not found")
    return {"status": "deleted", "record_id": record_id}


# ==============================================================================
# Batch & Single Treatment Application APIs
# ==============================================================================


@router.post("/api/v1/field-data/treatments")
async def create_treatment_batch_endpoint(
    req: TreatmentBatchCreateRequest,
    x_operator_pin: Optional[str] = Header(None),
):
    _verify_pin(x_operator_pin)
    created = fdb.add_treatment_batch(req.model_dump())
    return {"status": "saved", "treatment": created}


@router.get("/api/v1/field-data/treatments")
async def list_treatment_batches_endpoint(
    experiment_code: Optional[str] = Query("EXP2"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=5000),
):
    return {
        "treatments": fdb.list_treatment_batches(
            experiment_code=experiment_code,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
    }


@router.post("/api/v1/field-data/treatments/bulk-delete")
async def bulk_delete_treatment_batches_endpoint(
    req: BulkTreatmentsDeleteRequest,
    x_operator_pin: Optional[str] = Header(None),
):
    _verify_pin(x_operator_pin)
    if not req.batch_ids:
        raise HTTPException(status_code=400, detail="No treatment batch IDs selected")
    deleted = fdb.bulk_delete_treatment_batches(req.batch_ids)
    return {"status": "deleted", "deleted_count": deleted}


@router.delete("/api/v1/field-data/treatments/{batch_id}")
async def delete_treatment_batch_endpoint(
    batch_id: str,
    x_operator_pin: Optional[str] = Header(None),
):
    _verify_pin(x_operator_pin)
    ok = fdb.delete_treatment_batch(batch_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Treatment record not found")
    return {"status": "deleted", "batch_app_id": batch_id}


# ==============================================================================
# HOBO Light/Temp & Temp/RH Datasheet Parser & Upload API
# ==============================================================================


def _parse_timestamp_flexible(val: Any) -> Optional[str]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%dT%H:%M:%S")
    s = str(val).strip()
    if not s:
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%m/%d/%y %I:%M:%S %p",
        "%m/%d/%Y %I:%M:%S %p",
        "%m/%d/%y %H:%M:%S",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%m/%d/%y %H:%M",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
        "%d.%m.%y %H:%M:%S",
        "%d.%m.%y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%y %H:%M:%S",
        "%d/%m/%y %H:%M",
    ):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue
    # ISO fallback
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        return None


def _to_float(val: Any) -> Optional[float]:
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(",", ".")
    s = re.sub(r"[^0-9.\-+]", "", s)
    if not s or s in (".", "-", "+"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_hobo_rows_from_matrix(matrix: List[List[Any]]) -> List[Dict[str, Any]]:
    header_idx = -1
    col_time = -1
    col_date_only = -1
    col_clock_only = -1
    col_temp = -1
    temp_is_fahrenheit = False
    col_rh = -1
    col_lux = -1
    lux_is_fc = False

    for idx, row in enumerate(matrix[:15]):
        cells = [str(c or "").strip().lower() for c in row]
        has_time = any(any(k in c for k in ("date", "time", "timestamp", "tarih", "zaman", "saat")) for c in cells)
        has_metric = any(any(k in c for k in ("temp", "sicaklik", "sıcaklık", "rh", "humid", "nem", "lux", "intens", "light", "isik", "ışık")) for c in cells)
        if has_time and has_metric:
            header_idx = idx
            for c_i, c_txt in enumerate(cells):
                is_d = any(k in c_txt for k in ("date", "tarih"))
                is_t = any(k in c_txt for k in ("time", "timestamp", "zaman", "saat"))
                if col_time == -1 and ((is_d and is_t) or "timestamp" in c_txt):
                    col_time = c_i
                elif is_d and col_date_only == -1:
                    col_date_only = c_i
                elif is_t and col_clock_only == -1:
                    col_clock_only = c_i
                elif col_temp == -1 and any(k in c_txt for k in ("temp", "sicaklik", "sıcaklık", "°c", "°f")) and "dew" not in c_txt:
                    col_temp = c_i
                    if "°f" in c_txt or "fahrenheit" in c_txt or "(f)" in c_txt:
                        temp_is_fahrenheit = True
                elif col_rh == -1 and any(k in c_txt for k in ("rh", "humid", "nem")):
                    col_rh = c_i
                elif col_lux == -1 and any(k in c_txt for k in ("lux", "intens", "light", "isik", "ışık", "lum/ft")):
                    col_lux = c_i
                    if "lum/ft" in c_txt:
                        lux_is_fc = True
            if col_time == -1:
                col_time = col_date_only if col_date_only != -1 else col_clock_only
            break

    if header_idx == -1 or col_time == -1:
        return []

    use_split_dt = (
        col_date_only != -1
        and col_clock_only != -1
        and col_date_only != col_clock_only
    )

    parsed: List[Dict[str, Any]] = []
    for row in matrix[header_idx + 1 :]:
        if use_split_dt:
            if max(col_date_only, col_clock_only) >= len(row):
                continue
            d_cell = row[col_date_only]
            t_cell = row[col_clock_only]
            d_part = d_cell.strftime("%Y-%m-%d") if hasattr(d_cell, "strftime") else str(d_cell or "").strip()
            t_part = t_cell.strftime("%H:%M:%S") if hasattr(t_cell, "strftime") else str(t_cell or "").strip()
            raw_ts: Any = f"{d_part} {t_part}".strip()
        else:
            if col_time >= len(row):
                continue
            raw_ts = row[col_time]
        ts = _parse_timestamp_flexible(raw_ts)
        if not ts:
            continue
        t_val = _to_float(row[col_temp]) if (0 <= col_temp < len(row)) else None
        if t_val is not None and temp_is_fahrenheit:
            t_val = round((t_val - 32.0) * 5.0 / 9.0, 2)
        rh_val = _to_float(row[col_rh]) if (0 <= col_rh < len(row)) else None
        lux_val = _to_float(row[col_lux]) if (0 <= col_lux < len(row)) else None
        if lux_val is not None and lux_is_fc:
            lux_val = round(lux_val * 10.7639, 1)
        if t_val is None and rh_val is None and lux_val is None:
            continue
        parsed.append({
            "recorded_at": ts,
            "air_temp_c": t_val,
            "rh_pct": rh_val,
            "light_lux": lux_val,
        })
    return parsed


def parse_hobo_bytes(content: bytes, filename: str) -> List[Dict[str, Any]]:
    lower_name = (filename or "").lower()
    matrix: List[List[Any]] = []
    if lower_name.endswith(".xlsx"):
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
        ws = wb.active
        for row in ws.iter_rows(values_only=True):
            matrix.append(list(row))
        wb.close()
    else:
        text = None
        for enc in ("utf-8-sig", "utf-8", "cp1254", "latin-1"):
            try:
                text = content.decode(enc)
                break
            except Exception:
                continue
        if not text:
            return []
        sample = text[:4096]
        delim = ";" if sample.count(";") > sample.count(",") and sample.count(";") > sample.count("\t") else ("\t" if sample.count("\t") > sample.count(",") else ",")
        reader = csv.reader(io.StringIO(text), delimiter=delim)
        for row in reader:
            matrix.append(row)
    return _parse_hobo_rows_from_matrix(matrix)


@router.post("/api/v1/field-data/climate/upload")
async def upload_climate_datasheet_endpoint(
    request: Request,
    filename: str = Query("hobo_upload.csv"),
    logger_type: str = Query("hobo_ua002_light_temp"),
    location_tag: str = Query("IoT_Half"),
    experiment_code: str = Query("EXP2"),
    notes: str = Query(""),
    x_operator_pin: Optional[str] = Header(None),
):
    _verify_pin(x_operator_pin)
    content = await request.body()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    parsed = parse_hobo_bytes(content, filename)
    if not parsed:
        raise HTTPException(
            status_code=400,
            detail="Could not detect Date/Time + Temp/RH/Lux columns in file. Ensure headers include Date/Time and Temp, RH, or Lux.",
        )
    res = fdb.store_env_logger_dataset(
        filename=filename,
        logger_type=logger_type,
        location_tag=location_tag,
        parsed_rows=parsed,
        experiment_code=experiment_code,
        notes=notes,
    )
    return {"status": "imported", **res}


@router.get("/api/v1/field-data/climate/summary")
async def get_climate_summary_endpoint(
    location_tag: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(1500, ge=1, le=20000),
):
    return fdb.get_env_climate_summary(
        location_tag=location_tag,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


# ==============================================================================
# Multi-Sheet PhD Excel (.xlsx) & Tidy CSV Exports
# ==============================================================================


@router.get("/api/v1/field-data/export/csv")
async def export_field_csv(
    experiment_code: Optional[str] = Query("EXP2"),
    fertigation_arm: Optional[str] = Query(None),
    treatment_no: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    parameter_key: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    rows = fdb.query_measurements(
        experiment_code=experiment_code,
        fertigation_arm=fertigation_arm,
        treatment_no=treatment_no,
        category=category,
        parameter_key=parameter_key,
        start_date=start_date,
        end_date=end_date,
        limit=20000,
    )
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([
        "Record_ID", "Experiment", "Measured_At", "DAT", "Arm",
        "Treatment_No", "Treatment_Code", "NaCl_mM", "NaHS_uM", "Humic_mLL",
        "Replicate", "Planter_Code", "Plant_No", "Truss_No",
        "Category", "Parameter_Key", "Parameter_Label", "Unit",
        "Manual_Value", "AI_Value", "AI_Secondary_Value", "Final_Verified_Value",
        "Entry_Mode", "Verification_Status", "AI_Model", "Photo_URL", "Notes", "Recorded_By"
    ])
    for r in rows:
        w.writerow([
            r["record_id"], r["experiment_code"], r["measured_at"], r.get("dat"), r["fertigation_arm"],
            r["treatment_no"], r["treatment_code"], r["nacl_mm"], r["nahs_um"], r["humic_mll"],
            r["replicate_no"], r["planter_code"], r["plant_no"], r.get("truss_no") or "",
            r["category"], r["parameter_key"], r["parameter_label"], r["unit"],
            "" if r.get("manual_value") is None else r["manual_value"],
            "" if r.get("ai_value") is None else r["ai_value"],
            "" if r.get("ai_secondary_value") is None else r["ai_secondary_value"],
            r["final_value"],
            r["entry_mode"], r["verification_status"], r.get("ai_model") or "",
            r.get("photo_url") or "", r.get("notes") or "", r.get("recorded_by") or "",
        ])
    fname = f"PhD_Field_Lab_Tidy_{experiment_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter(["\ufeff" + out.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/api/v1/field-data/export/excel")
async def export_field_excel(
    experiment_code: Optional[str] = Query("EXP2"),
    fertigation_arm: Optional[str] = Query(None),
    treatment_no: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    parameter_key: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    rows = fdb.query_measurements(
        experiment_code=experiment_code,
        fertigation_arm=fertigation_arm,
        treatment_no=treatment_no,
        category=category,
        parameter_key=parameter_key,
        start_date=start_date,
        end_date=end_date,
        limit=20000,
    )
    param_order = (
        [x.strip() for x in parameter_key.split(",") if x.strip()]
        if (parameter_key and parameter_key != "ALL")
        else None
    )
    summary = fdb.compute_summary_statistics(rows, experiment_code=experiment_code or "EXP2", parameter_order=param_order)
    treatments = fdb.list_treatment_batches(experiment_code=experiment_code, start_date=start_date, end_date=end_date, limit=2000)
    climate = fdb.get_env_climate_summary(start_date=start_date, end_date=end_date, limit=5000)

    wb = openpyxl.Workbook()
    hdr_blue = PatternFill(start_color="0284C7", end_color="0284C7", fill_type="solid")
    hdr_teal = PatternFill(start_color="0D9488", end_color="0D9488", fill_type="solid")
    hdr_font = Font(color="FFFFFF", bold=True)

    # Sheet 1: Tidy Long Measurements (Separate Manual & AI Columns)
    ws1 = wb.active
    ws1.title = "Tidy_Measurements"
    ws1.append([
        "Measured At", "DAT", "Experiment", "Arm", "Treatment No", "Treatment Code",
        "NaCl (mM)", "NaHS (uM)", "Humic (mL/L)", "Replicate", "Planter Code", "Plant No", "Truss No",
        "Category", "Parameter", "Unit",
        "Manual Value", "AI Photo Value", "AI Model 2 Check", "Final Verified Value",
        "Entry Mode", "Verification Status", "AI Model", "Photo Path",
        "Concurrent PLC Soil VWC (%)", "Concurrent PLC Soil EC (uS/cm)", "Concurrent PLC Leaf Temp (C)",
        "Notes", "Recorded By"
    ])
    for c in ws1[1]:
        c.fill = hdr_blue
        c.font = hdr_font
        c.alignment = Alignment(horizontal="center")

    for r in rows:
        plc_s = ((r.get("plc_concurrent") or {}).get("sensor")) or ((r.get("plc_concurrent") or {}).get("zone_avg")) or {}
        ws1.append([
            r["measured_at"], r.get("dat"), r["experiment_code"], r["fertigation_arm"],
            r["treatment_no"], r["treatment_code"], r["nacl_mm"], r["nahs_um"], r["humic_mll"],
            r["replicate_no"], r["planter_code"], r["plant_no"], r.get("truss_no"),
            r["category"], r["parameter_label"], r["unit"],
            r.get("manual_value"), r.get("ai_value"), r.get("ai_secondary_value"), r["final_value"],
            r["entry_mode"], r["verification_status"], r.get("ai_model") or "",
            r.get("photo_url") or "",
            plc_s.get("soil_moisture") or plc_s.get("avg_soil_moisture"),
            plc_s.get("soil_ec") or plc_s.get("avg_soil_ec"),
            plc_s.get("leaf_temp") or plc_s.get("avg_leaf_temp"),
            r.get("notes") or "", r.get("recorded_by") or "",
        ])

    # Sheet 2: ANOVA-Ready Wide Table by Experimental Unit (Planter Mean across P1/P2)
    ws2 = wb.create_sheet(title="ANOVA_Wide_By_Planter")
    cat_rank = {p["key"]: idx for idx, p in enumerate(fdb.PARAMETER_CATALOG)}
    exp_rank = {k: idx for idx, k in enumerate(param_order or [])}
    param_cols = sorted(
        {(r["parameter_key"], f"{r['parameter_label']} ({r['unit']})") for r in rows},
        key=lambda item: (0, exp_rank[item[0]], item[0]) if item[0] in exp_rank else (1, cat_rank.get(item[0], 9999), item[0]),
    )
    ws2.append([
        "Planter Code", "Arm", "Treatment No", "Treatment Code",
        "NaCl (mM)", "NaHS (uM)", "Humic (mL/L)", "Block / Replicate",
        *[lbl for _, lbl in param_cols],
    ])
    for c in ws2[1]:
        c.fill = hdr_teal
        c.font = hdr_font

    planter_buckets: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        pcode = r["planter_code"]
        entry = planter_buckets.setdefault(pcode, {
            "meta": [pcode, r["fertigation_arm"], r["treatment_no"], r["treatment_code"], r["nacl_mm"], r["nahs_um"], r["humic_mll"], r["replicate_no"]],
            "vals": {},
        })
        entry["vals"].setdefault(r["parameter_key"], []).append(float(r["final_value"]))

    for pcode in sorted(planter_buckets.keys()):
        b = planter_buckets[pcode]
        row_cells = list(b["meta"])
        for pkey, _ in param_cols:
            vlist = b["vals"].get(pkey)
            row_cells.append(round(sum(vlist) / len(vlist), 4) if vlist else None)
        ws2.append(row_cells)

    # Sheet 3: Treatment Summary (Mean +/- SE)
    ws3 = wb.create_sheet(title="Summary_Mean_SE")
    ws3.append([
        "Parameter", "Unit", "Arm", "Treatment No", "Treatment Code",
        "NaCl (mM)", "NaHS (uM)", "Humic (mL/L)",
        "N", "Mean", "SD", "SE", "Min", "Max", "% vs T1 Control", "% vs T5 Salt Control",
        "R1", "R2", "R3", "R4"
    ])
    for c in ws3[1]:
        c.fill = hdr_blue
        c.font = hdr_font
    for sr in summary["summary_rows"]:
        rm = sr.get("rep_means") or {}
        ws3.append([
            sr["parameter_label"], sr["unit"], sr["fertigation_arm"], sr["treatment_no"], sr["treatment_code"],
            sr["nacl_mm"], sr["nahs_um"], sr["humic_mll"],
            sr["n"], sr["mean"], sr["sd"], sr["se"], sr["min"], sr["max"],
            sr.get("pct_vs_t1_ctrl"), sr.get("pct_vs_t5_salt_ctrl"),
            rm.get("R1"), rm.get("R2"), rm.get("R3"), rm.get("R4"),
        ])

    # Sheet 4: Batch & Single Treatment Applications
    ws4 = wb.create_sheet(title="Treatments_Log")
    ws4.append([
        "Applied At", "DAT", "Scope", "Group Label", "Planters Count",
        "Application Type", "NaHS (uM)", "NaHS Stock (mg/100mL)", "Humic (mL/L)", "NaCl (mM)",
        "Nutrient Stage", "Vol/Planter (L)", "Total Vol (L)", "Solution EC (uS/cm)", "Solution pH",
        "Hours After Morning Irrig", "Notes", "Recorded By"
    ])
    for c in ws4[1]:
        c.fill = hdr_teal
        c.font = hdr_font
    for t in treatments:
        ws4.append([
            t["applied_at"], t.get("dat"), t["scope_type"], t.get("group_label"), t["affected_planters_count"],
            t["application_type"], t["nahs_um"], t.get("nahs_stock_mg_100ml"), t["humic_mll"], t["nacl_mm"],
            t.get("nutrient_stage"), t.get("volume_per_planter_l"), t.get("total_volume_l"),
            t.get("solution_ec_uscm"), t.get("solution_ph"), t.get("hours_after_morning_irrig"),
            t.get("notes") or "", t.get("recorded_by") or "",
        ])

    # Sheet 5: HOBO Climate Loggers
    ws5 = wb.create_sheet(title="HOBO_Climate_Data")
    ws5.append(["Location", "Logger Type", "Recorded At", "Air Temp (C)", "RH (%)", "Light (Lux)", "Est PPFD (umol/m2/s)", "VPD (kPa)", "Dew Point (C)"])
    for c in ws5[1]:
        c.fill = hdr_blue
        c.font = hdr_font
    for cr in climate.get("readings", []):
        ws5.append([
            cr["location_tag"], cr["logger_type"], cr["recorded_at"],
            cr.get("air_temp_c"), cr.get("rh_pct"), cr.get("light_lux"),
            cr.get("estimated_ppfd_umol"), cr.get("vpd_kpa"), cr.get("dew_point_c"),
        ])

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    fname = f"Ziraat_PhD_Field_Lab_Complete_{experiment_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
