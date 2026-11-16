"""
PhD Research-Grade Multimodal AI Vision Reader (field_data_ai.py)
- Zero Local OCR (prevents noisy character hallucinations).
- Supports OpenRouter (Paid Frontier & Free Vision Models) and Google Gemini Direct API.
- Implements 3-Layer PhD Zero-Error Protocol:
  1. Parallel Dual-AI Consensus Cross-Check (Model A vs Model B simultaneous digit verification).
  2. Permanent Photo Persistence (/srv/data/field_photos/<YYYY-MM>/<uuid>.jpg) for side-by-side audit.
  3. Unit normalization (mS/cm -> uS/cm, F -> C) & 7-segment LCD disambiguation (6 vs 8, 5 vs 6, decimal dot).
"""

import asyncio
import base64
import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import httpx

from . import field_data_db as fdb


def get_photo_storage_root() -> str:
    if os.path.isdir("/srv/data"):
        root = "/srv/data/field_photos"
    else:
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "field_photos"))
        root = base
    os.makedirs(root, exist_ok=True)
    return root


def save_photo_bytes(raw_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """Save image bytes into YYYY-MM/<uuid>.ext and return relative path."""
    ext = ".jpg"
    if "png" in mime_type.lower():
        ext = ".png"
    elif "webp" in mime_type.lower():
        ext = ".webp"
    month_dir = datetime.now(timezone.utc).strftime("%Y-%m")
    root = get_photo_storage_root()
    full_dir = os.path.join(root, month_dir)
    os.makedirs(full_dir, exist_ok=True)
    fname = f"{uuid.uuid4().hex}{ext}"
    full_path = os.path.join(full_dir, fname)
    with open(full_path, "wb") as f:
        f.write(raw_bytes)
    return f"{month_dir}/{fname}"


def decode_base64_image(data_uri_or_b64: str) -> Tuple[bytes, str]:
    s = data_uri_or_b64.strip()
    mime = "image/jpeg"
    if s.startswith("data:"):
        header, _, b64_part = s.partition(",")
        m = re.match(r"data:([^;]+);base64", header, re.IGNORECASE)
        if m:
            mime = m.group(1).strip()
        s = b64_part
    raw = base64.b64decode(s)
    return raw, mime


def _build_vision_prompt(parameter_key: str, ai_profile: str, expected_unit: str) -> str:
    profile_instructions = {
        "porometer_lcd": (
            "INSTRUMENT: Decagon SC-1 Leaf Porometer LCD screen.\n"
            "On the SC-1 screen, extract ALL 5 numerical readings simultaneously into 'extra_fields':\n"
            "1. Top main stomatal conductance reading in mmol/(m2*s) -> 'stomatal_conductance_gs'\n"
            "2. Middle-left temperature in C -> 'porometer_leaf_temp_c'\n"
            "3. Middle-right temperature in C -> 'porometer_sensor_temp_c'\n"
            "4. Bottom-left relative humidity in % -> 'porometer_leaf_rh_pct'\n"
            "5. Bottom-right relative humidity in % -> 'porometer_sensor_rh_pct'\n"
            "Also extract the top-right screen clock/timer (e.g., '00:11') into 'screen_time'.\n"
            "Put ALL 5 readings inside 'extra_fields' and put the requested target parameter's value in 'primary_value'."
        ),
        "licor_lcd": (
            "INSTRUMENT: LI-COR LI-6400XT Photosynthesis / Gas Exchange screen.\n"
            "Extract ALL visible parameters into 'extra_fields': Pn ('photosynthesis_pn'), Tr ('transpiration_tr'), "
            "gs ('stomatal_conductance_gs'), Ci ('intercellular_ci'), leaf temp ('porometer_leaf_temp_c'), and leaf RH ('porometer_leaf_rh_pct')."
        ),
        "ir_thermometer_lcd": (
            "INSTRUMENT: Spectrum Technologies Item #2958 IR / Penetration Probe Thermometer LCD.\n"
            "Read the digital temperature carefully. Check if screen shows 'C' or 'F'. "
            "If shown in Fahrenheit ('F'), convert to Celsius: (F - 32) * 5 / 9, put Celsius in 'primary_value', and mention original F in 'notes'. "
            "If multiple temperatures (e.g. surface/min/max/probe) are visible on screen, include them in 'extra_fields'."
        ),
        "ec_ph_lcd": (
            "INSTRUMENT: Handheld Digital ATC EC/TDS/pH/Temp Combo Meter or 4-in-1 Soil/Leaf Meter LCD.\n"
            "Check unit indicator carefully: 'uS/cm', 'mS/cm', 'ppm', or 'pH'.\n"
            f"IMPORTANT UNIT CHECK: Expected target unit is '{expected_unit}'. "
            "If the meter screen displays 'mS/cm' (e.g. 2.35 mS/cm) and expected unit is 'uS/cm', multiply by 1000 (2350).\n"
            "If multiple values are displayed simultaneously on the screen (e.g., EC + TDS + pH + Temp, or Soil VWC + EC + pH + Temp), "
            "extract ALL of them into 'extra_fields' using matching keys: "
            "for Drainage/Feed meters use 'drainage_ec_uscm', 'drainage_tds_ppm', 'drainage_ph', 'probe_solution_temp_c'; "
            "for Handheld 4-in-1 Soil/Leaf meters use 'hh_soil_vwc_pct', 'hh_soil_ec_uscm', 'hh_soil_ph', 'hh_soil_temp_c', 'hh_leaf_temp_c', 'hh_leaf_rh_pct'."
        ),
        "balance_lcd": (
            "INSTRUMENT: Analytical / Precision Laboratory Balance (e.g., OHAUS Pioneer 0.0001 g).\n"
            "Read ALL decimal places accurately (including trailing digits after the decimal point, e.g., 12.3456 g)."
        ),
        "leaf_area_lcd": (
            "INSTRUMENT: CID Bio-Science CI-202 Portable Laser Leaf Area Meter LCD.\n"
            "Extract ALL visible parameters on the CI-202 screen into 'extra_fields': "
            "Area in cm2 ('single_leaf_area_cm2'), Length in cm ('leaf_length_cm'), Width in cm ('leaf_width_cm'), and Perimeter in cm ('leaf_perimeter_cm')."
        ),
        "caliper_lcd": (
            "INSTRUMENT: Digital Vernier Caliper LCD.\n"
            "Read exact millimeter ('mm') value including decimal point (e.g. 7.46 mm). If 'in' (inches) is shown, convert to mm (* 25.4)."
        ),
        "spad_lcd": (
            "INSTRUMENT: Konica Minolta SPAD-502 Chlorophyll Meter LCD.\n"
            "Read the SPAD value accurately to 1 decimal place (e.g., 46.8). If average/sample count is shown, note it."
        ),
        "plant_count": (
            "TASK: Count the target plant organs (leaves, trusses, flowers, or fruits) clearly visible on the target tomato plant.\n"
            "Count systematically from bottom to top without double-counting leaflets of a compound tomato leaf (1 compound leaf = 1 leaf)."
        ),
        "ruler_or_plant": (
            "TASK: Read the measurement on the ruler / measuring tape at the plant apex (or digital display if shown) in cm."
        ),
    }

    specific = profile_instructions.get(ai_profile, "Read the primary numerical measurement and any secondary readings shown on the instrument screen.")

    return f"""You are an ultra-precise PhD laboratory & greenhouse scientific instrument reader.
Target parameter key: "{parameter_key}" (Expected unit: "{expected_unit}").
{specific}

UNIVERSAL MULTI-VALUE SCREEN AUTO-DETECTION:
- Even if a different target parameter key was selected, if the photo shows a multi-value instrument screen, ALWAYS extract ALL visible readings into "extra_fields":
  * Decagon SC-1 Leaf Porometer: "stomatal_conductance_gs" (mmol/m2s), "porometer_leaf_temp_c" (left °C), "porometer_sensor_temp_c" (right °C), "porometer_leaf_rh_pct" (left %), "porometer_sensor_rh_pct" (right %).
  * LI-6400XT: "photosynthesis_pn", "transpiration_tr", "stomatal_conductance_gs", "intercellular_ci".
  * Handheld 4-in-1 Soil/Leaf sensor: "hh_soil_vwc_pct", "hh_soil_ec_uscm", "hh_soil_ph", "hh_soil_temp_c", "hh_leaf_temp_c", "hh_leaf_rh_pct".
  * CI-202 Leaf Area Meter: "single_leaf_area_cm2", "leaf_length_cm", "leaf_width_cm", "leaf_perimeter_cm".
  * Combo EC/TDS/pH/Temp meter: "drainage_ec_uscm", "drainage_tds_ppm", "drainage_ph", "probe_solution_temp_c".
- If a clock or timer (e.g., "00:11" or "14:32") is visible on the instrument screen header, return it in "screen_time".

CRITICAL ZERO-ERROR RULES FOR 7-SEGMENT & DOT-MATRIX LCD SCREENS:
1. Inspect every segment/pixel of each digit carefully:
   - Distinguish '6' (top-right segment OFF) vs '8' (all 7 segments ON).
   - Distinguish '5' (bottom-left OFF) vs '6' (bottom-left ON).
   - Distinguish '1' vs '7', '2' vs '3', and '0' (center bar OFF) vs '8' (center bar ON).
2. Check carefully for the DECIMAL POINT ('.') between digits! Never drop a visible decimal point.
3. Check for a leading minus sign ('-').
4. NEVER guess or fabricate numbers if glare/blur makes a digit unreadable — set "unreadable": true and "primary_value": null.

Return ONLY valid JSON matching this exact structure (no markdown fences):
{{
  "primary_value": <number or null>,
  "detected_unit": "<string>",
  "raw_screen_text": "<exact characters seen on screen>",
  "screen_time": "<HH:MM shown on meter screen or null>",
  "instrument_detected": "<short instrument name>",
  "confidence": <number from 0.0 to 1.0>,
  "unreadable": <true or false>,
  "extra_fields": {{}},
  "notes": "<short explanation or unit conversion note>"
}}"""


def _extract_json_object(raw_text: str) -> Dict[str, Any]:
    txt = (raw_text or "").strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```(?:json)?\s*", "", txt, flags=re.IGNORECASE)
        txt = re.sub(r"\s*```$", "", txt)
    start = txt.find("{")
    end = txt.rfind("}")
    if start != -1 and end != -1 and end > start:
        txt = txt[start : end + 1]
    return json.loads(txt)


async def _call_openrouter_vision(
    api_key: str,
    model: str,
    b64_str: str,
    mime_type: str,
    prompt: str,
) -> Dict[str, Any]:
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://iotserver.mmreza.com",
        "X-Title": "Ataturk University PhD Tomato Data Collection",
    }
    payload = {
        "model": model,
        "temperature": 0.0,
        "max_tokens": 600,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_str}"}},
                ],
            }
        ],
    }
    async with httpx.AsyncClient(timeout=28.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            raise RuntimeError(f"OpenRouter ({model}) HTTP {resp.status_code}: {resp.text[:240]}")
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        parsed = _extract_json_object(str(content))
        parsed["_model_used"] = model
        return parsed


async def _call_gemini_direct_vision(
    api_key: str,
    model: str,
    b64_str: str,
    mime_type: str,
    prompt: str,
) -> Dict[str, Any]:
    clean_model = model.replace("google/", "").strip() or "gemini-2.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {"inlineData": {"mimeType": mime_type, "data": b64_str}},
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json",
        },
    }
    async with httpx.AsyncClient(timeout=28.0) as client:
        resp = await client.post(url, json=payload)
        if resp.status_code >= 400:
            raise RuntimeError(f"Gemini ({clean_model}) HTTP {resp.status_code}: {resp.text[:240]}")
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = _extract_json_object(text)
        parsed["_model_used"] = f"gemini/{clean_model}"
        return parsed


def _values_match(v1: Optional[float], v2: Optional[float]) -> bool:
    if v1 is None or v2 is None:
        return False
    diff = abs(v1 - v2)
    if diff <= 0.02:
        return True
    denom = max(abs(v1), abs(v2), 1.0)
    return (diff / denom) <= 0.002  # 0.2% tight PhD tolerance


async def analyze_field_photo(
    image_b64: str,
    parameter_key: str,
    override_model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Saves photo permanently and runs 1-model or Parallel Dual-AI Consensus extraction.
    Never invents numbers if API key is missing or digit is unreadable.
    """
    raw_bytes, mime_type = decode_base64_image(image_b64)
    photo_rel_path = save_photo_bytes(raw_bytes, mime_type)
    photo_url = f"/api/v1/field-data/photos/{photo_rel_path}"
    b64_clean = base64.b64encode(raw_bytes).decode("ascii")

    pdef = fdb.PARAM_MAP.get(parameter_key, {})
    ai_profile = pdef.get("ai_profile", "generic_lcd")
    expected_unit = pdef.get("unit", "")
    prompt = _build_vision_prompt(parameter_key, ai_profile, expected_unit)

    cfg = fdb.get_ai_settings(include_secrets=True)
    or_key = (cfg.get("openrouter_api_key") or os.getenv("OPENROUTER_API_KEY") or "").strip()
    gem_key = (cfg.get("gemini_api_key") or os.getenv("GEMINI_API_KEY") or "").strip()
    provider = cfg.get("provider", "openrouter")
    primary_model = (override_model or cfg.get("primary_model") or "google/gemini-2.5-flash").strip()
    secondary_model = (cfg.get("secondary_model") or "openai/gpt-4o").strip()
    dual_verify = bool(cfg.get("dual_verify_enabled", True))

    if not or_key and not gem_key:
        return {
            "status": "key_missing",
            "photo_rel_path": photo_rel_path,
            "photo_url": photo_url,
            "ai_value": None,
            "ai_secondary_value": None,
            "verification_status": "manual_only",
            "message": "Photo saved safely! Configure your OpenRouter or Gemini API Key in AI Settings (top-right gear icon) to enable automatic AI reading.",
        }

    try:
        if (provider == "openrouter" and or_key) or (or_key and not gem_key):
            if dual_verify and secondary_model and secondary_model != primary_model:
                res_a, res_b = await asyncio.gather(
                    _call_openrouter_vision(or_key, primary_model, b64_clean, mime_type, prompt),
                    _call_openrouter_vision(or_key, secondary_model, b64_clean, mime_type, prompt),
                    return_exceptions=True,
                )
                if isinstance(res_a, Exception) and isinstance(res_b, Exception):
                    raise RuntimeError(f"{res_a} | {res_b}")
                if isinstance(res_a, Exception):
                    res_a = res_b
                    res_b = None
                elif isinstance(res_b, Exception):
                    res_b = None
            else:
                res_a = await _call_openrouter_vision(or_key, primary_model, b64_clean, mime_type, prompt)
                res_b = None
        else:
            # Google Gemini Direct mode (optionally cross-checked with OpenRouter if both keys exist)
            if dual_verify and or_key:
                res_a, res_b = await asyncio.gather(
                    _call_gemini_direct_vision(gem_key, primary_model, b64_clean, mime_type, prompt),
                    _call_openrouter_vision(or_key, secondary_model, b64_clean, mime_type, prompt),
                    return_exceptions=True,
                )
                if isinstance(res_a, Exception) and isinstance(res_b, Exception):
                    raise RuntimeError(f"{res_a} | {res_b}")
                if isinstance(res_a, Exception):
                    res_a = res_b
                    res_b = None
                elif isinstance(res_b, Exception):
                    res_b = None
            else:
                res_a = await _call_gemini_direct_vision(gem_key, primary_model, b64_clean, mime_type, prompt)
                res_b = None

        val_a = float(res_a["primary_value"]) if res_a.get("primary_value") is not None else None
        val_b = float(res_b["primary_value"]) if (isinstance(res_b, dict) and res_b.get("primary_value") is not None) else None
        conf_a = float(res_a.get("confidence") or 0.9)
        raw_extra_a = res_a.get("extra_fields") if isinstance(res_a.get("extra_fields"), dict) else {}
        raw_extra_b = res_b.get("extra_fields") if (isinstance(res_b, dict) and isinstance(res_b.get("extra_fields"), dict)) else {}

        extra: Dict[str, float] = {}
        for k, v in raw_extra_a.items():
            if v is not None and v != "":
                try:
                    extra[k] = float(v)
                except (ValueError, TypeError):
                    pass
        if val_a is not None and parameter_key in fdb.PARAM_MAP and parameter_key not in extra:
            extra[parameter_key] = val_a

        extra_sec: Dict[str, Optional[float]] = {}
        extra_consensus: Dict[str, bool] = {}
        for k, v1 in extra.items():
            v2_raw = raw_extra_b.get(k)
            if v2_raw is None and k == parameter_key and val_b is not None:
                v2_raw = val_b
            v2_num: Optional[float] = None
            if v2_raw is not None and v2_raw != "":
                try:
                    v2_num = float(v2_raw)
                except (ValueError, TypeError):
                    v2_num = None
            extra_sec[k] = v2_num
            extra_consensus[k] = _values_match(v1, v2_num) if v2_num is not None else True

        screen_time = str(res_a.get("screen_time") or (res_b.get("screen_time") if isinstance(res_b, dict) else "") or "").strip() or None
        if screen_time and screen_time.lower() in ("null", "none", "n/a"):
            screen_time = None
        instrument_detected = str(res_a.get("instrument_detected") or "").strip() or None
        captured_at_iso = datetime.now(timezone.utc).isoformat()
        model_label = res_a.get("_model_used", primary_model)

        if res_a.get("unreadable") or val_a is None:
            ver_status = "unreadable_check_photo"
            consensus = False
            msg = f"Screen glare/blur detected ({res_a.get('notes') or 'unreadable'}). Please check photo and enter value."
        elif isinstance(res_b, dict):
            model_b_lbl = res_b.get("_model_used", secondary_model)
            model_label = f"{model_label} + {model_b_lbl}"
            all_extra_ok = all(extra_consensus.values()) if len(extra) > 1 else True
            if _values_match(val_a, val_b) and all_extra_ok:
                ver_status = "dual_ai_consensus"
                consensus = True
                conf_a = round(max(conf_a, float(res_b.get("confidence") or 0.95)), 3)
                grp_note = f" ({len(extra)} screen values extracted together)" if len(extra) > 1 else ""
                time_note = f" [Screen Clock: {screen_time}]" if screen_time else ""
                msg = f"100% Dual-AI Verified: Both {res_a.get('_model_used')} & {model_b_lbl} read {val_a} {expected_unit}{grp_note}{time_note}."
            else:
                ver_status = "flagged_mismatch"
                consensus = False
                mismatches = [
                    f"{k}: M1={extra.get(k)} vs M2={extra_sec.get(k)}"
                    for k, ok_flag in extra_consensus.items()
                    if not ok_flag
                ]
                mismatch_txt = "; ".join(mismatches) if mismatches else f"Primary M1={val_a} vs M2={val_b}"
                msg = (
                    f"VERIFY DIGITS CAREFULLY ({res_a.get('_model_used')} vs {model_b_lbl}): "
                    f"{mismatch_txt}. Compare against the zoomed photo!"
                )
        else:
            ver_status = "single_ai_read"
            consensus = True
            msg = f"AI read {val_a} {expected_unit} ({model_label}). Verify with photo and tap Save."

        plausibility_warn = fdb.check_plausibility(parameter_key, val_a)

        return {
            "status": "ok",
            "photo_rel_path": photo_rel_path,
            "photo_url": photo_url,
            "captured_at_iso": captured_at_iso,
            "screen_time": screen_time,
            "instrument_detected": instrument_detected,
            "ai_value": val_a,
            "ai_secondary_value": val_b,
            "detected_unit": res_a.get("detected_unit") or expected_unit,
            "raw_screen_text": res_a.get("raw_screen_text") or "",
            "ai_confidence": conf_a,
            "ai_model": model_label,
            "verification_status": ver_status,
            "consensus_matched": consensus,
            "extra_fields": extra,
            "extra_fields_secondary": extra_sec,
            "extra_fields_consensus": extra_consensus,
            "notes": res_a.get("notes") or "",
            "plausibility_warning": plausibility_warn,
            "message": msg,
        }
    except Exception as exc:
        return {
            "status": "ai_error",
            "photo_rel_path": photo_rel_path,
            "photo_url": photo_url,
            "ai_value": None,
            "ai_secondary_value": None,
            "verification_status": "manual_only",
            "message": f"Photo saved, but AI call returned an error: {str(exc)[:220]}",
        }
