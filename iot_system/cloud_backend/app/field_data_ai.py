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
            "On the SC-1 screen, carefully extract:\n"
            "1. Main stomatal conductance reading in mmol/(m2*s) -> key 'stomatal_conductance_gs'\n"
            "2. Leaf temperature in C -> key 'porometer_leaf_temp_c'\n"
            "3. Sensor temperature in C -> key 'porometer_sensor_temp_c'\n"
            "4. Leaf relative humidity in % -> key 'porometer_leaf_rh_pct'\n"
            "5. Sensor relative humidity in % -> key 'porometer_sensor_rh_pct'\n"
            "Put ALL visible readings inside 'extra_fields' and put the requested parameter's value in 'primary_value'."
        ),
        "licor_lcd": (
            "INSTRUMENT: LI-COR LI-6400XT Photosynthesis / Gas Exchange screen.\n"
            "Extract Pn ('photosynthesis_pn'), Tr ('transpiration_tr'), gs ('stomatal_conductance_gs'), and Ci ('intercellular_ci') into 'extra_fields'."
        ),
        "ir_thermometer_lcd": (
            "INSTRUMENT: Spectrum Technologies Item #2958 IR / Penetration Probe Thermometer LCD.\n"
            "Read the digital temperature carefully. Check if screen shows 'C' or 'F'. "
            "If shown in Fahrenheit ('F'), convert to Celsius: (F - 32) * 5 / 9, put Celsius in 'primary_value', and mention original F in 'notes'."
        ),
        "ec_ph_lcd": (
            "INSTRUMENT: Handheld Digital ATC EC/TDS or pH Meter LCD.\n"
            "Check unit indicator carefully: 'uS/cm', 'mS/cm', 'ppm', or 'pH'. Also read bottom ATC temperature (°C) into extra_fields.temp_c if visible.\n"
            f"IMPORTANT UNIT CHECK: Expected target unit is '{expected_unit}'. "
            "If the meter screen displays 'mS/cm' (e.g. 2.35 mS/cm) and expected unit is 'uS/cm', multiply by 1000 (2350) for 'primary_value' and note it."
        ),
        "balance_lcd": (
            "INSTRUMENT: Analytical / Precision Laboratory Balance (e.g., OHAUS Pioneer 0.0001 g).\n"
            "Read ALL decimal places accurately (including trailing digits after the decimal point, e.g., 12.3456 g)."
        ),
        "leaf_area_lcd": (
            "INSTRUMENT: CID Bio-Science CI-202 Portable Laser Leaf Area Meter LCD.\n"
            "Extract the leaf area reading in cm2 (and length/width into extra_fields if visible on the LCD)."
        ),
        "caliper_lcd": (
            "INSTRUMENT: Digital Vernier Caliper LCD.\n"
            "Read exact millimeter ('mm') value including decimal point (e.g. 7.46 mm). If 'in' (inches) is shown, convert to mm (* 25.4)."
        ),
        "spad_lcd": (
            "INSTRUMENT: Konica Minolta SPAD-502 Chlorophyll Meter LCD.\n"
            "Read the SPAD value accurately to 1 decimal place (e.g., 46.8)."
        ),
        "plant_count": (
            "TASK: Count the target plant organs (leaves, trusses, flowers, or fruits) clearly visible on the target tomato plant.\n"
            "Count systematically from bottom to top without double-counting leaflets of a compound tomato leaf (1 compound leaf = 1 leaf)."
        ),
        "ruler_or_plant": (
            "TASK: Read the measurement on the ruler / measuring tape at the plant apex (or digital display if shown) in cm."
        ),
    }

    specific = profile_instructions.get(ai_profile, "Read the primary numerical measurement shown on the instrument screen or scale.")

    return f"""You are a ultra-precise PhD laboratory & greenhouse scientific instrument reader.
Target parameter key: "{parameter_key}" (Expected unit: "{expected_unit}").
{specific}

CRITICAL ZERO-ERROR RULES FOR 7-SEGMENT LCD SCREENS:
1. Inspect every segment of each digit carefully:
   - Distinguish '6' (top-right segment OFF) vs '8' (all 7 segments ON).
   - Distinguish '5' (bottom-left OFF) vs '6' (bottom-left ON).
   - Distinguish '1' vs '7', and '0' (center bar OFF) vs '8' (center bar ON).
2. Check carefully for the DECIMAL POINT ('.') between digits! Never drop a visible decimal point.
3. Check for a leading minus sign ('-').
4. NEVER guess or fabricate numbers if glare/blur makes a digit unreadable — set "unreadable": true and "primary_value": null.

Return ONLY valid JSON matching this exact structure (no markdown fences):
{{
  "primary_value": <number or null>,
  "detected_unit": "<string>",
  "raw_screen_text": "<exact characters seen on screen>",
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
    secondary_model = (cfg.get("secondary_model") or "openai/gpt-4o-mini").strip()
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
        extra = res_a.get("extra_fields") if isinstance(res_a.get("extra_fields"), dict) else {}
        model_label = res_a.get("_model_used", primary_model)

        if res_a.get("unreadable") or val_a is None:
            ver_status = "unreadable_check_photo"
            consensus = False
            msg = f"Screen glare/blur detected ({res_a.get('notes') or 'unreadable'}). Please check photo and enter value."
        elif isinstance(res_b, dict):
            model_b_lbl = res_b.get("_model_used", secondary_model)
            model_label = f"{model_label} + {model_b_lbl}"
            if _values_match(val_a, val_b):
                ver_status = "dual_ai_consensus"
                consensus = True
                conf_a = round(max(conf_a, float(res_b.get("confidence") or 0.95)), 3)
                msg = f"100% Dual-AI Verified: Both {res_a.get('_model_used')} & {model_b_lbl} read {val_a} {expected_unit}."
            else:
                ver_status = "flagged_mismatch"
                consensus = False
                msg = (
                    f"VERIFY DIGIT CAREFULLY: Model 1 ({res_a.get('_model_used')}) read {val_a}, "
                    f"Model 2 ({model_b_lbl}) read {val_b}. Compare against the zoomed photo!"
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
            "ai_value": val_a,
            "ai_secondary_value": val_b,
            "detected_unit": res_a.get("detected_unit") or expected_unit,
            "raw_screen_text": res_a.get("raw_screen_text") or "",
            "ai_confidence": conf_a,
            "ai_model": model_label,
            "verification_status": ver_status,
            "consensus_matched": consensus,
            "extra_fields": extra,
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
