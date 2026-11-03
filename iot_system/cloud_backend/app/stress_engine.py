"""
Monitoring-Only Multi-Sensor Tomato Stress & Biostimulant Recovery Engine
for Ataturk University PhD Thesis (Experiment 1 & Experiment 2: IoT Fertigation x Peat-Perlite x NaHS x Humic).

STRICT MONITORING-ONLY GUARANTEE:
- This module is 100% passive: it computes biophysical, physiological, root-zone, and canopy
  stress/recovery indices from the 48 RS485 sensors (24 Soil + 24 Leaf) and logged treatments.
- It NEVER triggers, opens, closes, or modifies any PLC solenoid valve (vana1..vana8 / dc1..dc14).
"""

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_CALIBRATION: Dict[str, Any] = {
    "substrate_name": "Agrimix Peat : Perlite 3:1 (v/v)",
    "hilhorst_epsilon_0": 2.5,         # Peat-perlite dry permittivity offset (coir=1.64, mineral soil=4.1)
    "hilhorst_epsilon_offset": 2.5,
    "container_capacity_vwc": 78.0,    # Measured container capacity (%) for 3:1 peat-perlite
    "container_capacity_pct": 78.0,
    "wilting_point_pct": 30.0,
    "optimal_vwc_min": 55.0,           # 70% of container capacity
    "optimal_vwc_max": 80.0,           # PLC upper cut-off band
    "optimal_vwc_min_pct": 55.0,
    "optimal_vwc_max_pct": 80.0,
    "critical_vwc_low": 35.0,          # Drought / peat shrinkage / BER risk threshold
    "critical_vwc_high": 90.0,         # Root hypoxia / waterlogging threshold
    "ec_threshold_dsm": 2.5,           # Maas & Hoffman tomato salinity threshold (2.5 dS/m = 2500 uS/cm)
    "maas_hoffman_threshold_dsm": 2.5,
    "ec_slope_pct_per_dsm": 9.9,       # Maas & Hoffman yield loss slope (9.9% per dS/m above 2.5)
    "maas_hoffman_slope_pct_per_dsm": 9.9,
    "optimal_ec_max_uscm": 2500.0,     # Control nutrient solution upper bound
    "saline_target_ec_uscm": 7500.0,   # 50 mM NaCl nutrient solution nominal EC (~7.3-7.8 mS/cm)
    "salt_coeff_expected": 0.55,       # Default TDS/EC salt conversion factor (mg/L per uS/cm)
    "optimal_ph_min": 5.8,
    "optimal_ph_max": 6.2,
    "default_ref_ph": 6.0,
    "optimal_soil_temp_min": 18.0,
    "optimal_soil_temp_max": 25.0,
    "optimal_leaf_temp_min": 18.0,
    "optimal_leaf_temp_max": 27.0,
    "cwsi_ll_slope": -1.35,            # Tomato Non-Water-Stressed Lower Baseline slope (deg C / kPa VPD)
    "cwsi_ll_intercept": 0.45,         # Tomato Lower Baseline intercept (deg C)
    "cwsi_ul_delta_t": 3.8,            # Tomato Non-Transpiring Upper Baseline (deg C)
    "cwsi_ul_degc": 3.8,
    "line_leaf_outlier_c": 2.0,        # Manuscript Section 2.8 alarm threshold (+2.0 deg C over line peers)
    "leaf_outlier_delta_c": 2.0,
    "transplant_date": "2026-10-16",   # Day 0 (DAT = 0) for automatic Days After Transplanting calculation
}


# Default 8-Line Treatment Assignment (Manuscript Table 2: 2 Salinity x 4 Biostimulant, Nutrient-Matched)
DEFAULT_LINE_PROFILES: Dict[int, Dict[str, Any]] = {
    1: {
        "zone_id": 1,
        "treatment_code": "I-C-0",
        "treatment_label": "Control (0 mM NaCl) + No Biostimulant (N-K Matched)",
        "salinity_regime": "Control (0 mM NaCl)",
        "fertigation_mode": "IoT",
        "growth_stage": "Solution 1 — Vegetative",
        "nacl_level_mm": 0.0,
        "nacl_mm": 0.0,
        "target_ec_uscm": 2300,
        "target_solution_ec_uscm": 2300,
        "nahs_dose_um": 0.0,
        "humic_dose_mll": 0.0,
        "nutrient_matched": 1,
        "ref_soil_ph": 6.0,
        "ref_drainage_ec_uscm": 2450,
        "ref_drainage_ph": 6.05,
        "notes": "Unstressed Control baseline; receives 0.88 g/L urea + 0.34 g/L K2SO4 in pulse",
    },
    2: {
        "zone_id": 2,
        "treatment_code": "I-C-H2S",
        "treatment_label": "Control (0 mM NaCl) + 25 uM NaHS Pulse",
        "salinity_regime": "Control (0 mM NaCl)",
        "fertigation_mode": "IoT",
        "growth_stage": "Solution 1 — Vegetative",
        "nacl_level_mm": 0.0,
        "nacl_mm": 0.0,
        "target_ec_uscm": 2300,
        "target_solution_ec_uscm": 2300,
        "nahs_dose_um": 25.0,
        "humic_dose_mll": 0.0,
        "nutrient_matched": 1,
        "ref_soil_ph": 6.0,
        "ref_drainage_ec_uscm": 2420,
        "ref_drainage_ph": 6.02,
        "notes": "Constitutive H2S donor effect at 0 mM NaCl; N-K matched in weekly pulse",
    },
    3: {
        "zone_id": 3,
        "treatment_code": "I-C-HS",
        "treatment_label": "Control (0 mM NaCl) + 4 mL/L LIQHUMUS NK Pulse",
        "salinity_regime": "Control (0 mM NaCl)",
        "fertigation_mode": "IoT",
        "growth_stage": "Solution 1 — Vegetative",
        "nacl_level_mm": 0.0,
        "nacl_mm": 0.0,
        "target_ec_uscm": 2300,
        "target_solution_ec_uscm": 2300,
        "nahs_dose_um": 0.0,
        "humic_dose_mll": 4.0,
        "nutrient_matched": 1,
        "ref_soil_ph": 6.05,
        "ref_drainage_ec_uscm": 2500,
        "ref_drainage_ph": 6.10,
        "notes": "Humic + fulvic acid pulse (638 mg/L) at 0 mM NaCl; pH adjusted to 6.0",
    },
    4: {
        "zone_id": 4,
        "treatment_code": "I-C-H2S+HS",
        "treatment_label": "Control (0 mM NaCl) + 25 uM NaHS + 4 mL/L Humic",
        "salinity_regime": "Control (0 mM NaCl)",
        "fertigation_mode": "IoT",
        "growth_stage": "Solution 1 — Vegetative",
        "nacl_level_mm": 0.0,
        "nacl_mm": 0.0,
        "target_ec_uscm": 2300,
        "target_solution_ec_uscm": 2300,
        "nahs_dose_um": 25.0,
        "humic_dose_mll": 4.0,
        "nutrient_matched": 1,
        "ref_soil_ph": 6.05,
        "ref_drainage_ec_uscm": 2480,
        "ref_drainage_ph": 6.08,
        "notes": "Combined NaHS + LIQHUMUS NK pulse under non-saline conditions",
    },
    5: {
        "zone_id": 5,
        "treatment_code": "I-S-0",
        "treatment_label": "Salinity (50 mM NaCl) + No Biostimulant (Positive Stress Control)",
        "salinity_regime": "Salinity Stress (NaCl)",
        "fertigation_mode": "IoT",
        "growth_stage": "Solution 1 — Vegetative",
        "nacl_level_mm": 50.0,
        "nacl_mm": 50.0,
        "target_ec_uscm": 7500,
        "target_solution_ec_uscm": 7500,
        "nahs_dose_um": 0.0,
        "humic_dose_mll": 0.0,
        "nutrient_matched": 1,
        "ref_soil_ph": 5.95,
        "ref_drainage_ec_uscm": 8400,
        "ref_drainage_ph": 5.90,
        "notes": "Unmitigated NaCl salinity baseline for Stress Recovery Index (SRI %)",
    },
    6: {
        "zone_id": 6,
        "treatment_code": "I-S-H2S",
        "treatment_label": "Salinity (50 mM NaCl) + 25 uM NaHS Pulse",
        "salinity_regime": "Salinity Stress (NaCl)",
        "fertigation_mode": "IoT",
        "growth_stage": "Solution 1 — Vegetative",
        "nacl_level_mm": 50.0,
        "nacl_mm": 50.0,
        "target_ec_uscm": 7500,
        "target_solution_ec_uscm": 7500,
        "nahs_dose_um": 25.0,
        "humic_dose_mll": 0.0,
        "nutrient_matched": 1,
        "ref_soil_ph": 6.0,
        "ref_drainage_ec_uscm": 8150,
        "ref_drainage_ph": 5.96,
        "notes": "Tests H1: Root-zone H2S donor (25 uM NaHS) mitigation of NaCl stress",
    },
    7: {
        "zone_id": 7,
        "treatment_code": "I-S-HS",
        "treatment_label": "Salinity (50 mM NaCl) + 4 mL/L LIQHUMUS NK Pulse",
        "salinity_regime": "Salinity Stress (NaCl)",
        "fertigation_mode": "IoT",
        "growth_stage": "Solution 1 — Vegetative",
        "nacl_level_mm": 50.0,
        "nacl_mm": 50.0,
        "target_ec_uscm": 7500,
        "target_solution_ec_uscm": 7500,
        "nahs_dose_um": 0.0,
        "humic_dose_mll": 4.0,
        "nutrient_matched": 1,
        "ref_soil_ph": 6.05,
        "ref_drainage_ec_uscm": 8200,
        "ref_drainage_ph": 6.02,
        "notes": "Tests H2: Nutrient-matched humic substance mitigation of NaCl stress",
    },
    8: {
        "zone_id": 8,
        "treatment_code": "I-S-H2S+HS",
        "treatment_label": "Salinity (50 mM NaCl) + 25 uM NaHS + 4 mL/L Humic (Synergy)",
        "salinity_regime": "Salinity Stress (NaCl)",
        "fertigation_mode": "IoT",
        "growth_stage": "Solution 1 — Vegetative",
        "nacl_level_mm": 50.0,
        "nacl_mm": 50.0,
        "target_ec_uscm": 7500,
        "target_solution_ec_uscm": 7500,
        "nahs_dose_um": 25.0,
        "humic_dose_mll": 4.0,
        "nutrient_matched": 1,
        "ref_soil_ph": 6.05,
        "ref_drainage_ec_uscm": 7950,
        "ref_drainage_ph": 6.04,
        "notes": "Tests H3: Combined 25 uM NaHS + 4 mL/L LIQHUMUS NK synergy under NaCl",
    },
}


def _clamp(val: float, low: float, high: float) -> float:
    return max(low, min(high, val))


def _safe_float(val: Any) -> Optional[float]:
    if val is None or val == "" or val == "—":
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (ValueError, TypeError):
        return None


def compute_dat(timestamp_str: Optional[str], transplant_date_str: str = "2026-10-16") -> int:
    """Compute Days After Transplanting (DAT) from an ISO timestamp and transplant date."""
    try:
        t_base = datetime.fromisoformat(transplant_date_str.strip()[:10]).date()
        if timestamp_str:
            s = str(timestamp_str).strip()[:10]
            t_cur = datetime.fromisoformat(s).date()
        else:
            t_cur = datetime.now(timezone.utc).date()
        return max(0, (t_cur - t_base).days)
    except Exception:
        return 0


def compute_days_after_transplant(transplant_date_str: str = "2026-10-16", ref_iso: Optional[str] = None) -> int:
    """Alias for compute_dat used by database layer."""
    return compute_dat(ref_iso, transplant_date_str)


def compute_h2s_speciation(
    ph: Optional[float] = None,
    temp_c: Optional[float] = 22.0,
    nahs_dose_um: float = 0.0,
    *,
    soil_ph: Optional[float] = None,
    soil_temp_c: Optional[float] = None,
) -> Dict[str, float]:
    """
    Henderson-Hasselbalch speciation for H2S (aq/gas) <-> H+ + HS- in the root zone:
    pKa1(T) ≈ 7.05 - 0.014 * (T - 25.0)
    Returns % dissolved H2S gas, % HS- hydrosulfide ion, and active molecular H2S (uM).
    """
    eff_ph = float(soil_ph if soil_ph is not None else (ph if ph is not None else 6.0))
    eff_t = float(soil_temp_c if soil_temp_c is not None else (temp_c if temp_c is not None else 22.0))
    pka1 = round(7.05 - 0.014 * (eff_t - 25.0), 3)
    ratio = math.pow(10.0, eff_ph - pka1)
    f_h2s_pct = round(100.0 / (1.0 + ratio), 2)
    f_hs_ion_pct = round(100.0 - f_h2s_pct, 2)
    active_h2s_um = round(float(nahs_dose_um or 0.0) * (f_h2s_pct / 100.0), 2)
    return {
        "pka1": pka1,
        "pka1_at_temp": pka1,
        "f_h2s_pct": f_h2s_pct,
        "h2s_gas_fraction_pct": f_h2s_pct,
        "f_hs_minus_pct": f_hs_ion_pct,
        "hs_ion_fraction_pct": f_hs_ion_pct,
        "active_h2s_um": active_h2s_um,
    }


def compute_vpd_and_dewpoint(
    temp_c: Optional[float] = None,
    rh_pct: Optional[float] = None,
    *,
    leaf_temp_c: Optional[float] = None,
    leaf_rh_pct: Optional[float] = None,
) -> Dict[str, Optional[float]]:
    """
    Returns dict with vpd_kpa, dew_point_c, dew_point_margin_c, sat_vp_kpa from temperature (deg C) and relative humidity (%).
    """
    t_in = leaf_temp_c if leaf_temp_c is not None else temp_c
    rh_in = leaf_rh_pct if leaf_rh_pct is not None else rh_pct
    if t_in is None or rh_in is None:
        return {
            "vpd_kpa": None,
            "dew_point_c": None,
            "dew_point_margin_c": None,
            "sat_vp_kpa": None,
        }
    t = float(t_in)
    rh = _clamp(float(rh_in), 1.0, 100.0)
    es = 0.61078 * math.exp((17.27 * t) / (t + 237.3))
    ea = es * (rh / 100.0)
    vpd = max(0.0, es - ea)
    gamma = math.log(rh / 100.0) + (17.27 * t) / (237.3 + t)
    dew = (237.3 * gamma) / max(0.001, 17.27 - gamma)
    return {
        "vpd_kpa": round(vpd, 3),
        "dew_point_c": round(dew, 2),
        "dew_point_margin_c": round(t - dew, 2),
        "sat_vp_kpa": round(es, 3),
    }


def compute_hilhorst_pore_ec(
    soil_moisture_pct: Optional[float],
    soil_ec_uscm: Optional[float],
    soil_temp_c: Optional[float] = 22.0,
    epsilon_0: float = 2.5,
    epsilon_offset: Optional[float] = None,
) -> Dict[str, Optional[float]]:
    """
    Computes temperature-standardized bulk EC (EC_25), Hilhorst (2000) pore-water EC (EC_p),
    and root-zone osmotic potential (Psi_pi, MPa) for 3:1 peat-perlite substrate.
    """
    eps_off = float(epsilon_offset if epsilon_offset is not None else epsilon_0)
    if soil_ec_uscm is None:
        return {
            "ec_25_uscm": None,
            "epsilon_b": None,
            "epsilon_w": None,
            "pore_ec_uscm": None,
            "pore_ec_dsm": None,
            "osmotic_potential_mpa": None,
        }

    t = float(soil_temp_c) if soil_temp_c is not None else 22.0
    ec_raw = max(0.0, float(soil_ec_uscm))
    temp_factor = max(0.5, 1.0 + 0.019 * (t - 25.0))
    ec_25 = round(ec_raw / temp_factor, 1)

    if soil_moisture_pct is None or soil_moisture_pct <= 1.0:
        return {
            "ec_25_uscm": ec_25,
            "epsilon_b": None,
            "epsilon_w": None,
            "pore_ec_uscm": None,
            "pore_ec_dsm": None,
            "osmotic_potential_mpa": None,
        }

    # Bound effective VWC at >= 15% for Hilhorst stability per Manuscript Section 9.2
    theta = _clamp(float(soil_moisture_pct), 15.0, 95.0) / 100.0
    epsilon_w = round(80.3 - 0.37 * (t - 20.0), 2)
    # Calibrated dielectric permittivity curve for peat-perlite 3:1
    epsilon_b = round(1.6 + 22.0 * theta + 110.0 * (theta * theta), 2)
    denom = max(1.8, epsilon_b - eps_off)
    pore_ec_uscm = round((epsilon_w * ec_25) / denom, 1)
    pore_ec_dsm = round(pore_ec_uscm / 1000.0, 3)
    t_kelvin_ratio = (t + 273.15) / 298.15
    osmotic_mpa = round(-0.036 * pore_ec_dsm * t_kelvin_ratio, 3)

    return {
        "ec_25_uscm": ec_25,
        "epsilon_b": epsilon_b,
        "epsilon_w": epsilon_w,
        "pore_ec_uscm": pore_ec_uscm,
        "pore_ec_dsm": pore_ec_dsm,
        "osmotic_potential_mpa": osmotic_mpa,
    }


def compute_single_sensor_stress(
    reading: Optional[Dict[str, Any]] = None,
    line_profile: Optional[Dict[str, Any]] = None,
    calibration: Optional[Dict[str, Any]] = None,
    ambient_canopy_temp_c: Optional[float] = None,
    line_mean_leaf_temp_c: Optional[float] = None,
    *,
    sensor_row: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Calculates all biophysical parameters, 6 stress sub-indices (0-100), Composite PSI (0-100),
    Plant Vitality Index (PVI, 0-100), CWSI, and Dominant Stress Diagnosis for a single plot/row.
    Preserves None when raw hardware data is absent.
    """
    if reading is None:
        reading = sensor_row or {}
    cal = dict(DEFAULT_CALIBRATION)
    if calibration:
        cal.update({k: v for k, v in calibration.items() if v is not None})

    prof = dict(DEFAULT_LINE_PROFILES.get(int(reading.get("zone_id") or 1), DEFAULT_LINE_PROFILES[1]))
    if line_profile:
        prof.update({k: v for k, v in line_profile.items() if v is not None})

    moist = _safe_float(reading.get("soil_moisture") if "soil_moisture" in reading else reading.get("avg_soil_moisture"))
    stemp = _safe_float(reading.get("soil_temp") if "soil_temp" in reading else reading.get("avg_soil_temp"))
    sec = _safe_float(reading.get("soil_ec") if "soil_ec" in reading else reading.get("avg_soil_ec"))
    ssalt = _safe_float(reading.get("soil_salt") if "soil_salt" in reading else reading.get("avg_soil_salt"))
    sph_raw = _safe_float(reading.get("soil_ph") if "soil_ph" in reading else reading.get("avg_soil_ph"))
    lhum = _safe_float(reading.get("leaf_humidity") if "leaf_humidity" in reading else reading.get("avg_leaf_humidity"))
    ltemp = _safe_float(reading.get("leaf_temp") if "leaf_temp" in reading else reading.get("avg_leaf_temp"))

    has_any_data = any(v is not None for v in (moist, stemp, sec, ssalt, lhum, ltemp))
    eff_ph = sph_raw if sph_raw is not None else _safe_float(prof.get("ref_soil_ph")) or cal["default_ref_ph"]
    ph_source = "live_rs485" if sph_raw is not None else "reference_anchor"

    if not has_any_data:
        spec = compute_h2s_speciation(eff_ph, 22.0, float(prof.get("nahs_dose_um", 0.0)))
        return {
            "has_data": False,
            "effective_ph": eff_ph,
            "ph_source": ph_source,
            "ec_25_uscm": None,
            "pore_ec_uscm": None,
            "pore_ec_dsm": None,
            "pore_water_ec_dsm": None,
            "salt_coeff": None,
            "pore_tds_mgl": None,
            "osmotic_potential_mpa": None,
            "yield_loss_est_pct": None,
            "leaf_vpd_kpa": None,
            "vpd_kpa": None,
            "leaf_dew_point_c": None,
            "leaf_delta_t_c": None,
            "canopy_soil_delta_t": None,
            "line_leaf_anomaly_c": None,
            "line_leaf_outlier_flag": False,
            "leaf_temp_anomaly_flag": False,
            "cwsi": None,
            "h2s_gas_fraction_pct": spec["h2s_gas_fraction_pct"],
            "hs_ion_fraction_pct": spec["hs_ion_fraction_pct"],
            "pka1_at_temp": spec["pka1_at_temp"],
            "h2s_speciation": spec,
            "sub_indices": {
                "moisture_stress_pct": None,
                "osmotic_ec_stress_pct": None,
                "salt_ionic_stress_pct": None,
                "thermal_stress_pct": None,
                "leaf_cwsi_stress_pct": None,
                "ph_stress_pct": None,
            },
            "composite_psi": None,
            "vitality_pvi": None,
            "plant_vitality_pvi": None,
            "stress_category": "No Live Data (—)",
            "dominant_stress": "Waiting for PLC / HMI Telemetry",
        }

    # 1. Hilhorst Pore-Water EC & Temp-Corrected EC25
    hil = compute_hilhorst_pore_ec(moist, sec, stemp, epsilon_0=float(cal["hilhorst_epsilon_0"]))
    ec_25 = hil["ec_25_uscm"]
    pore_ec_uscm = hil["pore_ec_uscm"] if hil["pore_ec_uscm"] is not None else ec_25
    pore_ec_dsm = round(pore_ec_uscm / 1000.0, 3) if pore_ec_uscm is not None else None

    # 2. Salt Coefficient (K_salt = Salt / EC) & Effective Pore TDS
    salt_coeff: Optional[float] = None
    pore_tds_mgl: Optional[float] = None
    if ssalt is not None and sec is not None and sec > 5.0:
        salt_coeff = round(float(ssalt) / float(sec), 3)
        if pore_ec_uscm is not None:
            pore_tds_mgl = round(pore_ec_uscm * salt_coeff, 1)

    # 3. Root-Zone Osmotic Potential (Psi_pi, MPa) & Maas-Hoffman Yield Loss Estimate (%)
    osmotic_mpa: Optional[float] = None
    yield_loss_pct: Optional[float] = None
    t_kelvin_ratio = ((stemp if stemp is not None else 22.0) + 273.15) / 298.15
    if pore_ec_dsm is not None:
        osmotic_mpa = round(-0.036 * pore_ec_dsm * t_kelvin_ratio, 3)
        th_dsm = float(cal["ec_threshold_dsm"])
        slope_pct = float(cal["ec_slope_pct_per_dsm"])
        yield_loss_pct = round(_clamp(slope_pct * max(0.0, pore_ec_dsm - th_dsm), 0.0, 100.0), 1)

    # 4. Leaf Microclimate: VPD_leaf, Dew Point, Leaf-Air Delta T, Intra-Line Outlier, and CWSI
    vpd_info = compute_vpd_and_dewpoint(ltemp, lhum)
    leaf_vpd_kpa = vpd_info["vpd_kpa"]
    leaf_dew_c = vpd_info["dew_point_c"]
    ref_amb = ambient_canopy_temp_c if ambient_canopy_temp_c is not None else (stemp + 1.2 if stemp is not None else 23.0)
    leaf_delta_t_c = round(ltemp - ref_amb, 2) if (ltemp is not None and ref_amb is not None) else None
    line_anomaly_c = round(ltemp - line_mean_leaf_temp_c, 2) if (ltemp is not None and line_mean_leaf_temp_c is not None) else 0.0
    outlier_flag = bool(line_anomaly_c is not None and abs(line_anomaly_c) >= float(cal["line_leaf_outlier_c"]))

    cwsi: Optional[float] = None
    if leaf_delta_t_c is not None and leaf_vpd_kpa is not None:
        dt_ll = float(cal["cwsi_ll_slope"]) * leaf_vpd_kpa + float(cal["cwsi_ll_intercept"])
        dt_ul = float(cal["cwsi_ul_delta_t"])
        span = max(0.5, dt_ul - dt_ll)
        cwsi = round(_clamp((leaf_delta_t_c - dt_ll) / span, 0.0, 1.0), 3)

    # 5. Henderson-Hasselbalch H2S / HS- Speciation
    spec = compute_h2s_speciation(eff_ph, stemp if stemp is not None else 22.0, float(prof.get("nahs_dose_um", 0.0)))

    # -------------------------------------------------------------------------
    # 6. Compute the 6 Normalized Sub-Indices (0.0 to 100.0%)
    # -------------------------------------------------------------------------
    # (a) Moisture Stress (S_moist)
    s_moist: Optional[float] = None
    if moist is not None:
        opt_min = float(cal["optimal_vwc_min"])
        opt_max = float(cal["optimal_vwc_max"])
        crit_low = float(cal["critical_vwc_low"])
        crit_high = float(cal["critical_vwc_high"])
        if opt_min <= moist <= opt_max:
            s_moist = 0.0
        elif moist < opt_min:
            s_moist = _clamp(((opt_min - moist) / max(1.0, opt_min - crit_low)) * 80.0, 0.0, 100.0)
        else:
            s_moist = _clamp(((moist - opt_max) / max(1.0, crit_high - opt_max)) * 75.0, 0.0, 100.0)
        s_moist = round(s_moist, 1)

    # (b) Osmotic / Pore-Water EC Stress (S_ec)
    s_ec: Optional[float] = None
    if pore_ec_uscm is not None:
        opt_ec = float(cal["optimal_ec_max_uscm"])
        if pore_ec_uscm <= opt_ec:
            # Check nutrient deficiency if extremely low (< 700 uS/cm)
            s_ec = round(_clamp(((700.0 - pore_ec_uscm) / 700.0) * 35.0, 0.0, 35.0), 1) if pore_ec_uscm < 700.0 else 0.0
        else:
            # Above 2500 uS/cm -> scales up to 100% around 10,500 uS/cm (10.5 dS/m)
            s_ec = round(_clamp(((pore_ec_uscm - opt_ec) / 8000.0) * 100.0, 0.0, 100.0), 1)

    # (c) Salt Coefficient / Ionic Stress (S_salt)
    s_salt: Optional[float] = None
    if ssalt is not None:
        salt_mass_stress = 0.0
        if ssalt > 1350.0:
            salt_mass_stress = _clamp(((ssalt - 1350.0) / 3650.0) * 100.0, 0.0, 100.0)
        coeff_dev_stress = 0.0
        if salt_coeff is not None:
            exp_k = float(cal["salt_coeff_expected"])
            dev = abs(salt_coeff - exp_k)
            if dev > 0.06:
                coeff_dev_stress = _clamp(((dev - 0.06) / 0.25) * 60.0, 0.0, 60.0)
        s_salt = round(_clamp(0.75 * salt_mass_stress + 0.25 * coeff_dev_stress, 0.0, 100.0), 1)

    # (d) Root & Canopy Thermal Stress (S_temp)
    s_temp: Optional[float] = None
    temp_scores: List[float] = []
    if stemp is not None:
        st_min = float(cal["optimal_soil_temp_min"])
        st_max = float(cal["optimal_soil_temp_max"])
        if stemp < st_min:
            temp_scores.append(_clamp(((st_min - stemp) / 10.0) * 100.0, 0.0, 100.0))
        elif stemp > st_max:
            temp_scores.append(_clamp(((stemp - st_max) / 10.0) * 100.0, 0.0, 100.0))
        else:
            temp_scores.append(0.0)
    if ltemp is not None:
        lt_min = float(cal["optimal_leaf_temp_min"])
        lt_max = float(cal["optimal_leaf_temp_max"])
        if ltemp < lt_min:
            temp_scores.append(_clamp(((lt_min - ltemp) / 10.0) * 100.0, 0.0, 100.0))
        elif ltemp > lt_max:
            temp_scores.append(_clamp(((ltemp - lt_max) / 10.0) * 100.0, 0.0, 100.0))
        else:
            temp_scores.append(0.0)
    if temp_scores:
        s_temp = round(max(temp_scores), 1)

    # (e) Leaf Stomatal / VPD / CWSI / Wetness Stress (S_leaf)
    s_leaf: Optional[float] = None
    if cwsi is not None or leaf_vpd_kpa is not None or lhum is not None:
        cwsi_score = (cwsi * 100.0) if cwsi is not None else 0.0
        vpd_score = 0.0
        if leaf_vpd_kpa is not None:
            if leaf_vpd_kpa > 1.4:
                vpd_score = _clamp(((leaf_vpd_kpa - 1.4) / 1.6) * 100.0, 0.0, 100.0)
            elif leaf_vpd_kpa < 0.35:
                vpd_score = _clamp(((0.35 - leaf_vpd_kpa) / 0.35) * 65.0, 0.0, 65.0)
        wet_score = 0.0
        if lhum is not None and lhum >= 85.0:
            wet_score = _clamp(((lhum - 85.0) / 15.0) * 85.0, 0.0, 85.0)
        outlier_score = 75.0 if outlier_flag else 0.0
        s_leaf = round(_clamp(max(cwsi_score, 0.6 * cwsi_score + 0.4 * vpd_score, wet_score, outlier_score), 0.0, 100.0), 1)

    # (f) Root-Zone pH Stress (S_ph)
    ph_min = float(cal["optimal_ph_min"])
    ph_max = float(cal["optimal_ph_max"])
    if ph_min <= eff_ph <= ph_max:
        s_ph = 0.0
    elif eff_ph < ph_min:
        s_ph = round(_clamp(((ph_min - eff_ph) / 1.5) * 100.0, 0.0, 100.0), 1)
    else:
        s_ph = round(_clamp(((eff_ph - ph_max) / 1.6) * 100.0, 0.0, 100.0), 1)

    # 7. Composite Plant Stress Index (PSI, 0-100) & Vitality (PVI = 100 - PSI)
    weights = [
        ("Moisture Deficit / Excess", s_moist, 0.25),
        ("Osmotic / Pore-Water EC", s_ec, 0.25),
        ("Leaf CWSI / VPD Stomatal", s_leaf, 0.20),
        ("Root / Canopy Temperature", s_temp, 0.15),
        ("Salinity / Salt Coefficient", s_salt, 0.10),
        ("Root-Zone pH", s_ph, 0.05),
    ]
    active_w = [(label, val, w) for (label, val, w) in weights if val is not None]
    total_w = sum(w for _, _, w in active_w) or 1.0
    weighted_sum = sum(float(val) * w for _, val, w in active_w) / total_w
    max_label, max_val, _ = max(active_w, key=lambda x: float(x[1])) if active_w else ("None", 0.0, 1.0)

    # Max-hazard boost so severe single-factor stress is never masked
    if float(max_val) > 65.0:
        composite_psi = round(_clamp(0.55 * weighted_sum + 0.45 * float(max_val), 0.0, 100.0), 1)
    else:
        composite_psi = round(_clamp(weighted_sum, 0.0, 100.0), 1)

    vitality_pvi = round(100.0 - composite_psi, 1)

    if composite_psi <= 20.0:
        stress_cat = "Optimal (Unstressed)"
    elif composite_psi <= 40.0:
        stress_cat = "Mild / Priming"
    elif composite_psi <= 65.0:
        stress_cat = "Moderate Stress"
    elif composite_psi <= 82.0:
        stress_cat = "High Stress"
    else:
        stress_cat = "Critical Stress"

    # Dominant stress classifier
    if composite_psi <= 18.0 and not outlier_flag:
        dom_stress = "Optimal Root-Zone & Stomatal Status"
    elif outlier_flag:
        dom_stress = f"Canopy Leaf Outlier ({line_anomaly_c:+.1f} deg C vs Line)"
    elif s_ec is not None and s_ec >= 40.0 and s_ec >= (s_moist or 0.0):
        dom_stress = f"Salinity Osmotic Stress (ECp {pore_ec_dsm:.2f} dS/m, {osmotic_mpa:.2f} MPa)"
    elif s_moist is not None and s_moist >= 35.0 and (moist or 50.0) < float(cal["optimal_vwc_min"]):
        dom_stress = f"Root-Zone Drying Deficit (VWC {moist:.1f}%)"
    elif s_leaf is not None and (lhum or 0.0) >= 85.0:
        dom_stress = f"High Leaf Surface Wetness / Fungal Risk (RH {lhum:.1f}%)"
    elif s_leaf is not None and cwsi is not None and cwsi > 0.36:
        dom_stress = f"Stomatal Closure Stress (CWSI {cwsi:.2f})"
    else:
        dom_stress = f"{max_label} ({max_val:.0f}%)"

    return {
        "has_data": True,
        "effective_ph": eff_ph,
        "ph_source": ph_source,
        "ec_25_uscm": ec_25,
        "epsilon_b": hil["epsilon_b"],
        "epsilon_w": hil["epsilon_w"],
        "pore_ec_uscm": pore_ec_uscm,
        "pore_ec_dsm": pore_ec_dsm,
        "pore_water_ec_dsm": pore_ec_dsm,
        "salt_coeff": salt_coeff,
        "pore_tds_mgl": pore_tds_mgl,
        "osmotic_potential_mpa": osmotic_mpa,
        "yield_loss_est_pct": yield_loss_pct,
        "leaf_vpd_kpa": leaf_vpd_kpa,
        "vpd_kpa": leaf_vpd_kpa,
        "leaf_dew_point_c": leaf_dew_c,
        "leaf_delta_t_c": leaf_delta_t_c,
        "canopy_soil_delta_t": leaf_delta_t_c,
        "line_leaf_anomaly_c": line_anomaly_c,
        "line_leaf_outlier_flag": outlier_flag,
        "leaf_temp_anomaly_flag": outlier_flag,
        "cwsi": cwsi,
        "h2s_gas_fraction_pct": spec["h2s_gas_fraction_pct"],
        "hs_ion_fraction_pct": spec["hs_ion_fraction_pct"],
        "pka1_at_temp": spec["pka1_at_temp"],
        "h2s_speciation": spec,
        "sub_indices": {
            "moisture_stress_pct": s_moist,
            "osmotic_ec_stress_pct": s_ec,
            "salt_ionic_stress_pct": s_salt,
            "thermal_stress_pct": s_temp,
            "leaf_cwsi_stress_pct": s_leaf,
            "ph_stress_pct": s_ph,
        },
        "composite_psi": composite_psi,
        "vitality_pvi": vitality_pvi,
        "plant_vitality_pvi": vitality_pvi,
        "stress_category": stress_cat,
        "dominant_stress": dom_stress,
    }


def _avg(vals: List[Optional[float]], digits: int = 2) -> Optional[float]:
    clean = [float(v) for v in vals if v is not None]
    if not clean:
        return None
    return round(sum(clean) / len(clean), digits)


def _min_val(vals: List[Optional[float]], digits: int = 2) -> Optional[float]:
    clean = [float(v) for v in vals if v is not None]
    return round(min(clean), digits) if clean else None


def _max_val(vals: List[Optional[float]], digits: int = 2) -> Optional[float]:
    clean = [float(v) for v in vals if v is not None]
    return round(max(clean), digits) if clean else None


def _normalize_line_profiles(line_profiles: Any) -> Dict[int, Dict[str, Any]]:
    out = {zid: dict(p) for zid, p in DEFAULT_LINE_PROFILES.items()}
    if isinstance(line_profiles, dict):
        for k, v in line_profiles.items():
            zid = int(k)
            if zid in out and isinstance(v, dict):
                out[zid].update({pk: pv for pk, pv in v.items() if pv is not None})
    elif isinstance(line_profiles, list):
        for item in line_profiles:
            if isinstance(item, dict) and item.get("zone_id") is not None:
                zid = int(item["zone_id"])
                if zid in out:
                    out[zid].update({pk: pv for pk, pv in item.items() if pv is not None})
    for zid, p in out.items():
        if "nacl_mm" in p and p.get("nacl_level_mm") is None:
            p["nacl_level_mm"] = p["nacl_mm"]
        if "nacl_level_mm" in p and p.get("nacl_mm") is None:
            p["nacl_mm"] = p["nacl_level_mm"]
        if "target_solution_ec_uscm" in p and p.get("target_ec_uscm") is None:
            p["target_ec_uscm"] = p["target_solution_ec_uscm"]
        if "target_ec_uscm" in p and p.get("target_solution_ec_uscm") is None:
            p["target_solution_ec_uscm"] = p["target_ec_uscm"]
    return out


def compute_live_stress_report(
    latest_telemetry: Optional[Dict[str, Any]] = None,
    line_profiles: Any = None,
    calibration: Optional[Dict[str, Any]] = None,
    recent_treatments: Optional[List[Dict[str, Any]]] = None,
    recent_notes: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Computes the complete live 8-Line and 24-Plot Stress & Recovery Report,
    including Stress Recovery Index (SRI %), NaHS x Humic Synergy, and monitoring alerts.
    """
    cal = dict(DEFAULT_CALIBRATION)
    if calibration:
        cal.update({k: v for k, v in calibration.items() if v is not None})

    prof_map = _normalize_line_profiles(line_profiles)
    recent_treatments = recent_treatments or []
    recent_notes = recent_notes or []

    recorded_at = (latest_telemetry or {}).get("recorded_at")
    plc_online = bool((latest_telemetry or {}).get("plc_online", False))
    dat = compute_dat(recorded_at, cal.get("transplant_date", "2026-10-16"))
    sensors_raw = (latest_telemetry or {}).get("sensors") or []
    sensors_by_id = {int(s["sensor_id"]): s for s in sensors_raw if "sensor_id" in s}

    # Compute reference ambient canopy temperature from Control lines (Zones 1..4) or overall mean
    control_leaf_temps = [
        _safe_float(s.get("leaf_temp"))
        for s in sensors_raw
        if int(s.get("zone_id") or 1) in (1, 2, 3, 4) and _safe_float(s.get("leaf_temp")) is not None
    ]
    all_leaf_temps = [_safe_float(s.get("leaf_temp")) for s in sensors_raw if _safe_float(s.get("leaf_temp")) is not None]
    ambient_canopy_c = _avg(control_leaf_temps, 2) if control_leaf_temps else _avg(all_leaf_temps, 2)

    # Compute per-line mean leaf temperature for Manuscript Section 2.8 (+2.0 deg C outlier rule)
    line_leaf_means: Dict[int, Optional[float]] = {}
    for zid in range(1, 9):
        z_ltemps = [
            _safe_float(sensors_by_id.get(sid, {}).get("leaf_temp"))
            for sid in [zid, zid + 8, zid + 16]
        ]
        line_leaf_means[zid] = _avg(z_ltemps, 2)

    plots_report: List[Dict[str, Any]] = []
    plots_by_zone: Dict[int, List[Dict[str, Any]]] = {z: [] for z in range(1, 9)}
    monitoring_alerts: List[Dict[str, Any]] = []

    for sid in range(1, 25):
        zid = ((sid - 1) % 8) + 1
        rep_num = ((sid - 1) // 8) + 1
        raw = sensors_by_id.get(sid, {"sensor_id": sid, "zone_id": zid})
        prof = prof_map[zid]
        st = compute_single_sensor_stress(
            reading=raw,
            line_profile=prof,
            calibration=cal,
            ambient_canopy_temp_c=ambient_canopy_c,
            line_mean_leaf_temp_c=line_leaf_means.get(zid),
        )
        plot_item = {
            "sensor_id": sid,
            "plot_tag": f"R{sid}",
            "leaf_tag": f"R{sid}_L",
            "zone_id": zid,
            "replicate": rep_num,
            "treatment_code": prof.get("treatment_code", f"Line-{zid}"),
            "nacl_level_mm": prof.get("nacl_level_mm", 0.0),
            "nahs_dose_um": prof.get("nahs_dose_um", 0.0),
            "humic_dose_mll": prof.get("humic_dose_mll", 0.0),
            "soil_moisture": _safe_float(raw.get("soil_moisture")),
            "soil_temp": _safe_float(raw.get("soil_temp")),
            "soil_ec": _safe_float(raw.get("soil_ec")),
            "soil_salt": _safe_float(raw.get("soil_salt")),
            "soil_ph": _safe_float(raw.get("soil_ph")),
            "leaf_humidity": _safe_float(raw.get("leaf_humidity")),
            "leaf_temp": _safe_float(raw.get("leaf_temp")),
            **st,
        }
        plots_report.append(plot_item)
        plots_by_zone[zid].append(plot_item)

        if st.get("line_leaf_outlier_flag"):
            monitoring_alerts.append({
                "severity": "high",
                "type": "leaf_temp_outlier_2c",
                "zone_id": zid,
                "sensor_id": sid,
                "plot_tag": f"R{sid}",
                "title": f"Plot R{sid} (Line {zid}) Leaf Temp Outlier ({st['line_leaf_anomaly_c']:+.1f} deg C)",
                "message": "Manuscript Section 2.8 Alert: Leaf-air temperature difference exceeds line peers by >= 2.0 deg C (Monitoring only; irrigation unchanged).",
            })
        if st.get("composite_psi") is not None and st["composite_psi"] >= 68.0:
            monitoring_alerts.append({
                "severity": "warning",
                "type": "high_composite_stress",
                "zone_id": zid,
                "sensor_id": sid,
                "plot_tag": f"R{sid}",
                "title": f"Plot R{sid} (Line {zid}) High Stress (PSI {st['composite_psi']:.1f}/100)",
                "message": f"Dominant factor: {st['dominant_stress']} (Treatment: {prof.get('treatment_code')}).",
            })

    # First pass over 8 Lines to compute Zone Means, Mins, Maxes
    lines_report: List[Dict[str, Any]] = []
    for zid in range(1, 9):
        zplots = plots_by_zone[zid]
        prof = prof_map[zid]
        psis = [p["composite_psi"] for p in zplots]
        pvis = [p["vitality_pvi"] for p in zplots]
        cwsis = [p["cwsi"] for p in zplots]
        ecps = [p["pore_ec_dsm"] for p in zplots]
        osms = [p["osmotic_potential_mpa"] for p in zplots]
        ksalts = [p["salt_coeff"] for p in zplots]
        vpds = [p["leaf_vpd_kpa"] for p in zplots]
        dts = [p["leaf_delta_t_c"] for p in zplots]
        h2s_fracs = [p["h2s_gas_fraction_pct"] for p in zplots]

        sub_keys = [
            "moisture_stress_pct",
            "osmotic_ec_stress_pct",
            "salt_ionic_stress_pct",
            "thermal_stress_pct",
            "leaf_cwsi_stress_pct",
            "ph_stress_pct",
        ]
        sub_means = {k: _avg([p["sub_indices"].get(k) for p in zplots], 1) for k in sub_keys}
        sub_maxes = {k: _max_val([p["sub_indices"].get(k) for p in zplots], 1) for k in sub_keys}

        mean_psi = _avg(psis, 1)
        mean_pvi = _avg(pvis, 1)
        avg_stemp = _avg([p["soil_temp"] for p in zplots], 1)
        avg_sph = _avg([p["soil_ph"] for p in zplots], 2)
        eff_ph = avg_sph if avg_sph is not None else float(prof.get("ref_soil_ph", 6.0))
        z_spec = compute_h2s_speciation(eff_ph, avg_stemp or 22.0, float(prof.get("nahs_dose_um", 0.0)))

        if mean_psi is None:
            s_class = "no_data"
        elif mean_psi < 20.0:
            s_class = "optimal"
        elif mean_psi < 45.0:
            s_class = "mild"
        elif mean_psi < 70.0:
            s_class = "moderate"
        else:
            s_class = "severe"

        lines_report.append({
            "zone_id": zid,
            "line_name": f"Line {zid}",
            "line_label": f"Line {zid} (Zone {zid})",
            "has_data": any(p.get("has_data") for p in zplots),
            "plot_tags": [p["plot_tag"] for p in zplots],
            "sensor_ids": [p["sensor_id"] for p in zplots],
            "treatment_code": prof.get("treatment_code", f"Line-{zid}"),
            "treatment_label": prof.get("treatment_label", ""),
            "salinity_regime": prof.get("salinity_regime", prof.get("treatment_label", "")),
            "fertigation_mode": prof.get("fertigation_mode", "IoT"),
            "growth_stage": prof.get("growth_stage", "Solution 1 — Vegetative"),
            "nacl_level_mm": float(prof.get("nacl_level_mm", prof.get("nacl_mm", 0.0))),
            "nacl_mm": float(prof.get("nacl_mm", prof.get("nacl_level_mm", 0.0))),
            "target_ec_uscm": int(prof.get("target_ec_uscm", prof.get("target_solution_ec_uscm", 2300))),
            "target_solution_ec_uscm": int(prof.get("target_solution_ec_uscm", prof.get("target_ec_uscm", 2300))),
            "nahs_dose_um": float(prof.get("nahs_dose_um", 0.0)),
            "humic_dose_mll": float(prof.get("humic_dose_mll", 0.0)),
            "nutrient_matched": int(prof.get("nutrient_matched", 1)),
            "ref_soil_ph": float(prof.get("ref_soil_ph", 6.0)),
            "ref_drainage_ec_uscm": prof.get("ref_drainage_ec_uscm"),
            "ref_drainage_ph": prof.get("ref_drainage_ph"),
            "avg_soil_moisture": _avg([p["soil_moisture"] for p in zplots], 1),
            "min_soil_moisture": _min_val([p["soil_moisture"] for p in zplots], 1),
            "max_soil_moisture": _max_val([p["soil_moisture"] for p in zplots], 1),
            "avg_soil_temp": avg_stemp,
            "avg_soil_ec": _avg([p["soil_ec"] for p in zplots], 0),
            "max_soil_ec": _max_val([p["soil_ec"] for p in zplots], 0),
            "avg_soil_salt": _avg([p["soil_salt"] for p in zplots], 0),
            "avg_soil_ph": avg_sph,
            "avg_leaf_humidity": _avg([p["leaf_humidity"] for p in zplots], 1),
            "avg_leaf_temp": _avg([p["leaf_temp"] for p in zplots], 1),
            "min_leaf_temp": _min_val([p["leaf_temp"] for p in zplots], 1),
            "max_leaf_temp": _max_val([p["leaf_temp"] for p in zplots], 1),
            "avg_pore_ec_dsm": _avg(ecps, 3),
            "max_pore_ec_dsm": _max_val(ecps, 3),
            "avg_osmotic_mpa": _avg(osms, 3),
            "avg_osmotic_potential_mpa": _avg(osms, 3),
            "avg_salt_coeff": _avg(ksalts, 3),
            "avg_leaf_vpd_kpa": _avg(vpds, 3),
            "avg_vpd_kpa": _avg(vpds, 3),
            "avg_leaf_delta_t_c": _avg(dts, 2),
            "avg_cwsi": _avg(cwsis, 3),
            "max_cwsi": _max_val(cwsis, 3),
            "avg_h2s_gas_fraction_pct": _avg(h2s_fracs, 2),
            "h2s_speciation": z_spec,
            "mean_psi": mean_psi,
            "avg_psi": mean_psi,
            "min_psi": _min_val(psis, 1),
            "max_psi": _max_val(psis, 1),
            "mean_vitality_pvi": mean_pvi,
            "avg_pvi": mean_pvi,
            "stress_class": s_class,
            "avg_s_moisture": sub_means.get("moisture_stress_pct"),
            "avg_s_salinity": sub_means.get("osmotic_ec_stress_pct"),
            "avg_s_ph": sub_means.get("ph_stress_pct"),
            "avg_s_salt_ratio": sub_means.get("salt_ionic_stress_pct"),
            "avg_s_canopy_temp": sub_means.get("thermal_stress_pct"),
            "avg_s_leaf_vpd": sub_means.get("leaf_cwsi_stress_pct"),
            "avg_s_canopy": sub_means.get("leaf_cwsi_stress_pct"),
            "sub_indices_mean": sub_means,
            "sub_indices_max": sub_maxes,
            "dominant_stress": zplots[0]["dominant_stress"] if zplots else "—",
            "stress_recovery_index_sri_pct": None,
            "recovery_sri_pct": None,
            "psi_reduction_vs_salt_ctrl": None,
            "cwsi_recovery_index_pct": None,
        })

    # Second pass: Compute Stress Recovery Index (SRI %) and NaHS x Humic Synergy
    ctrl_lines = [l for l in lines_report if l["nacl_level_mm"] == 0 and l["nahs_dose_um"] == 0 and l["humic_dose_mll"] == 0]
    salt_untreated_lines = [l for l in lines_report if l["nacl_level_mm"] > 0 and l["nahs_dose_um"] == 0 and l["humic_dose_mll"] == 0]

    psi_ctrl = ctrl_lines[0]["mean_psi"] if (ctrl_lines and ctrl_lines[0]["mean_psi"] is not None) else 12.0
    psi_salt_base = (
        salt_untreated_lines[0]["mean_psi"]
        if (salt_untreated_lines and salt_untreated_lines[0]["mean_psi"] is not None)
        else _max_val([l["mean_psi"] for l in lines_report], 1)
    )
    cwsi_ctrl = ctrl_lines[0]["avg_cwsi"] if (ctrl_lines and ctrl_lines[0]["avg_cwsi"] is not None) else 0.15
    cwsi_salt_base = (
        salt_untreated_lines[0]["avg_cwsi"]
        if (salt_untreated_lines and salt_untreated_lines[0]["avg_cwsi"] is not None)
        else _max_val([l["avg_cwsi"] for l in lines_report], 3)
    )

    for l in lines_report:
        if l["mean_psi"] is not None and psi_salt_base is not None:
            denom = max(2.0, float(psi_salt_base) - float(psi_ctrl))
            sri = round(_clamp(((float(psi_salt_base) - float(l["mean_psi"])) / denom) * 100.0, -50.0, 150.0), 1)
            l["stress_recovery_index_sri_pct"] = sri
            l["recovery_sri_pct"] = sri
            l["psi_reduction_vs_salt_ctrl"] = round(float(psi_salt_base) - float(l["mean_psi"]), 1)
        if l["avg_cwsi"] is not None and cwsi_salt_base is not None and cwsi_ctrl is not None:
            c_denom = max(0.05, float(cwsi_salt_base) - float(cwsi_ctrl))
            c_sri = ((float(cwsi_salt_base) - float(l["avg_cwsi"])) / c_denom) * 100.0
            l["cwsi_recovery_index_pct"] = round(_clamp(c_sri, -50.0, 150.0), 1)

    for p in plots_report:
        if p["composite_psi"] is not None and psi_salt_base is not None:
            denom = max(2.0, float(psi_salt_base) - float(psi_ctrl))
            p["stress_recovery_index_sri_pct"] = round(
                _clamp(((float(psi_salt_base) - float(p["composite_psi"])) / denom) * 100.0, -50.0, 150.0),
                1,
            )
        else:
            p["stress_recovery_index_sri_pct"] = None

    lines_by_id = {l["zone_id"]: l for l in lines_report}
    synergy_summary: Dict[str, Any] = {
        "saline_baseline_psi": lines_by_id.get(5, {}).get("mean_psi"),
        "nahs_alone_sri_pct": lines_by_id.get(6, {}).get("stress_recovery_index_sri_pct"),
        "humic_alone_sri_pct": lines_by_id.get(7, {}).get("stress_recovery_index_sri_pct"),
        "combined_nahs_humic_sri_pct": lines_by_id.get(8, {}).get("stress_recovery_index_sri_pct"),
        "synergy_excess_sri_pct": None,
        "interaction_type": "Waiting for live telemetry",
    }
    sri_h2s = synergy_summary["nahs_alone_sri_pct"]
    sri_hs = synergy_summary["humic_alone_sri_pct"]
    sri_comb = synergy_summary["combined_nahs_humic_sri_pct"]
    if sri_h2s is not None and sri_hs is not None and sri_comb is not None:
        best_single = max(float(sri_h2s), float(sri_hs))
        excess_over_best = round(float(sri_comb) - best_single, 1)
        synergy_summary["synergy_excess_sri_pct"] = excess_over_best
        if excess_over_best >= 8.0:
            synergy_summary["interaction_type"] = f"Synergistic / Cooperative Gain (+{excess_over_best:.1f}% over best single agent)"
        elif excess_over_best >= 0.0:
            synergy_summary["interaction_type"] = f"Complementary Positive Alleviation (+{excess_over_best:.1f}%)"
        else:
            synergy_summary["interaction_type"] = f"Sub-additive ({excess_over_best:+.1f}% vs best single agent)"

    mean_stemp = _avg([p["soil_temp"] for p in plots_report], 1) or 22.0
    speciation_curve = []
    for step in range(45, 86):
        ph_pt = round(step / 10.0, 1)
        sp = compute_h2s_speciation(ph_pt, mean_stemp)
        speciation_curve.append({
            "ph": ph_pt,
            "h2s_gas_pct": sp["h2s_gas_fraction_pct"],
            "hs_ion_pct": sp["hs_ion_fraction_pct"],
        })

    return {
        "monitoring_only_mode": True,
        "valve_control_disabled_in_engine": True,
        "plc_online": plc_online,
        "recorded_at": recorded_at,
        "dat": dat,
        "ambient_canopy_ref_c": ambient_canopy_c,
        "mean_soil_temp_c": mean_stemp,
        "calibration": cal,
        "line_profiles": list(prof_map.values()),
        "overall": {
            "mean_psi": _avg([p["composite_psi"] for p in plots_report], 1),
            "max_psi": _max_val([p["composite_psi"] for p in plots_report], 1),
            "min_psi": _min_val([p["composite_psi"] for p in plots_report], 1),
            "mean_vitality_pvi": _avg([p["vitality_pvi"] for p in plots_report], 1),
            "mean_cwsi": _avg([p["cwsi"] for p in plots_report], 3),
            "max_cwsi": _max_val([p["cwsi"] for p in plots_report], 3),
            "mean_pore_ec_dsm": _avg([p["pore_ec_dsm"] for p in plots_report], 3),
            "max_pore_ec_dsm": _max_val([p["pore_ec_dsm"] for p in plots_report], 3),
            "mean_osmotic_mpa": _avg([p["osmotic_potential_mpa"] for p in plots_report], 3),
            "mean_salt_coeff": _avg([p["salt_coeff"] for p in plots_report], 3),
            "mean_leaf_vpd_kpa": _avg([p["leaf_vpd_kpa"] for p in plots_report], 3),
        },
        "synergy_h3": synergy_summary,
        "lines": lines_report,
        "zones": lines_report,
        "plots": plots_report,
        "sensors": plots_report,
        "speciation_curve": speciation_curve,
        "alerts": monitoring_alerts,
        "recent_treatments": recent_treatments[:25],
        "recent_notes": recent_notes[:30],
    }


def _parse_iso_ts(ts_str: Optional[str]) -> Optional[datetime]:
    if not ts_str:
        return None
    try:
        s = str(ts_str).strip()
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            s += "T12:00:00+00:00"
        elif s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def compute_historical_stress_report(
    zone_rows: List[Dict[str, Any]],
    sensor_rows: List[Dict[str, Any]],
    line_profiles: Any,
    calibration: Optional[Dict[str, Any]] = None,
    treatments: Optional[List[Dict[str, Any]]] = None,
    notes: Optional[List[Dict[str, Any]]] = None,
    target_zone_id: Optional[int] = None,
    target_sensor_id: Optional[int] = None,
    resolution: str = "15min",
) -> Dict[str, Any]:
    """
    Computes historical stress & recovery time-series, min/max envelopes, 24-hour diurnal profiles,
    pre/post-pulse recovery curves around logged H2S/Humic applications, and Stress Degree-Hours (SDH).
    """
    cal = dict(DEFAULT_CALIBRATION)
    if calibration:
        cal.update({k: v for k, v in calibration.items() if v is not None})

    prof_map = _normalize_line_profiles(line_profiles)
    treatments = treatments or []
    notes = notes or []

    by_ts: Dict[str, List[Dict[str, Any]]] = {}
    zone_series: Dict[str, List[Dict[str, Any]]] = {str(z): [] for z in range(1, 9)}

    for zr in sorted(zone_rows, key=lambda x: str(x.get("recorded_at") or "")):
        ts = str(zr.get("recorded_at") or "")
        if not ts:
            continue
        zid = int(zr.get("zone_id") or 1)
        prof = prof_map.get(zid) or DEFAULT_LINE_PROFILES[zid]
        st = compute_single_sensor_stress(zr, line_profile=prof, calibration=cal)
        enriched = {
            **zr,
            "recorded_at": ts,
            "treatment_code": prof.get("treatment_code", f"Line-{zid}"),
            "nacl_level_mm": float(prof.get("nacl_level_mm", 0.0)),
            "nahs_dose_um": float(prof.get("nahs_dose_um", 0.0)),
            "humic_dose_mll": float(prof.get("humic_dose_mll", 0.0)),
            **st,
        }
        by_ts.setdefault(ts, []).append(enriched)
        if str(zid) in zone_series:
            zone_series[str(zid)].append(enriched)

    sorted_timestamps = sorted(by_ts.keys())
    timeline_series: List[Dict[str, Any]] = []
    diurnal_buckets: Dict[int, Dict[str, List[float]]] = {
        h: {"psi": [], "pvi": [], "cwsi": [], "vpd": [], "pore_ec": [], "leaf_temp": [], "soil_moist": []}
        for h in range(24)
    }
    severity_counts = {"optimal": 0, "mild": 0, "moderate": 0, "high": 0, "critical": 0}
    sdh_by_zone: Dict[int, Dict[str, Any]] = {
        zid: {
            "zone_id": zid,
            "treatment_code": (prof_map.get(zid) or DEFAULT_LINE_PROFILES[zid]).get("treatment_code", f"Line-{zid}"),
            "stress_degree_hours": 0.0,
            "total_sdh": 0.0,
            "recovery_degree_hours": 0.0,
            "optimal_pct": 0.0,
            "mild_pct": 0.0,
            "moderate_pct": 0.0,
            "high_pct": 0.0,
            "critical_pct": 0.0,
            "samples": 0,
            "_counts": {"opt": 0, "mild": 0, "mod": 0, "high": 0, "crit": 0},
        }
        for zid in range(1, 9)
    }

    for ts in sorted_timestamps:
        rows_at_ts = by_ts[ts]
        z1 = next((r for r in rows_at_ts if int(r.get("zone_id") or 0) == 1), None)
        z5 = next((r for r in rows_at_ts if int(r.get("zone_id") or 0) == 5), None)
        psi_c = z1["composite_psi"] if (z1 and z1.get("composite_psi") is not None) else 12.0
        psi_s = z5["composite_psi"] if (z5 and z5.get("composite_psi") is not None) else _max_val([r.get("composite_psi") for r in rows_at_ts], 1)

        for r in rows_at_ts:
            zid = int(r.get("zone_id") or 1)
            psi_val = r.get("composite_psi")
            if psi_val is not None and zid in sdh_by_zone:
                z_sdh = sdh_by_zone[zid]
                z_sdh["samples"] += 1
                z_sdh["stress_degree_hours"] += max(0.0, float(psi_val) - 20.0) * 0.0833
                if psi_s is not None:
                    denom = max(2.0, float(psi_s) - float(psi_c))
                    r["sri_pct"] = round(_clamp(((float(psi_s) - float(psi_val)) / denom) * 100.0, -50.0, 150.0), 1)
                    z_sdh["recovery_degree_hours"] += max(0.0, float(r["sri_pct"])) * 0.0833
                else:
                    r["sri_pct"] = None

                if psi_val <= 20.0:
                    z_sdh["_counts"]["opt"] += 1
                elif psi_val <= 40.0:
                    z_sdh["_counts"]["mild"] += 1
                elif psi_val <= 65.0:
                    z_sdh["_counts"]["mod"] += 1
                elif psi_val <= 82.0:
                    z_sdh["_counts"]["high"] += 1
                else:
                    z_sdh["_counts"]["crit"] += 1

        scoped = [r for r in rows_at_ts if (not target_zone_id or int(r.get("zone_id") or 0) == int(target_zone_id))]
        if not scoped:
            continue

        psis = [r.get("composite_psi") for r in scoped]
        pvis = [r.get("vitality_pvi") for r in scoped]
        sris = [r.get("sri_pct") for r in scoped]
        cwsis = [r.get("cwsi") for r in scoped]
        ecps = [r.get("pore_ec_dsm") for r in scoped]
        osms = [r.get("osmotic_potential_mpa") for r in scoped]
        ksalts = [r.get("salt_coeff") for r in scoped]
        vpds = [r.get("leaf_vpd_kpa") for r in scoped]
        dts = [r.get("leaf_delta_t_c") for r in scoped]
        moists = [_safe_float(r.get("avg_soil_moisture")) for r in scoped]
        ecs = [_safe_float(r.get("avg_soil_ec")) for r in scoped]
        ltemps = [_safe_float(r.get("avg_leaf_temp")) for r in scoped]
        lhums = [_safe_float(r.get("avg_leaf_humidity")) for r in scoped]
        stemps = [_safe_float(r.get("avg_soil_temp")) for r in scoped]

        mean_psi = _avg(psis, 1)
        if mean_psi is not None:
            if mean_psi <= 20.0:
                severity_counts["optimal"] += 1
            elif mean_psi <= 40.0:
                severity_counts["mild"] += 1
            elif mean_psi <= 65.0:
                severity_counts["moderate"] += 1
            elif mean_psi <= 82.0:
                severity_counts["high"] += 1
            else:
                severity_counts["critical"] += 1

        dt_obj = _parse_iso_ts(ts)
        if dt_obj is not None:
            hr = (dt_obj.hour + 3) % 24
            if mean_psi is not None:
                diurnal_buckets[hr]["psi"].append(mean_psi)
            if _avg(pvis, 1) is not None:
                diurnal_buckets[hr]["pvi"].append(float(_avg(pvis, 1)))
            if _avg(cwsis, 3) is not None:
                diurnal_buckets[hr]["cwsi"].append(float(_avg(cwsis, 3)))
            if _avg(vpds, 3) is not None:
                diurnal_buckets[hr]["vpd"].append(float(_avg(vpds, 3)))
            if _avg(ecps, 3) is not None:
                diurnal_buckets[hr]["pore_ec"].append(float(_avg(ecps, 3)))
            if _avg(ltemps, 2) is not None:
                diurnal_buckets[hr]["leaf_temp"].append(float(_avg(ltemps, 2)))
            if _avg(moists, 2) is not None:
                diurnal_buckets[hr]["soil_moist"].append(float(_avg(moists, 2)))

        timeline_series.append({
            "recorded_at": ts,
            "mean_psi": mean_psi,
            "min_psi": _min_val(psis, 1),
            "max_psi": _max_val(psis, 1),
            "mean_vitality_pvi": _avg(pvis, 1),
            "mean_sri_pct": _avg(sris, 1),
            "max_sri_pct": _max_val(sris, 1),
            "mean_cwsi": _avg(cwsis, 3),
            "max_cwsi": _max_val(cwsis, 3),
            "mean_pore_ec_dsm": _avg(ecps, 3),
            "max_pore_ec_dsm": _max_val(ecps, 3),
            "mean_osmotic_mpa": _avg(osms, 3),
            "mean_salt_coeff": _avg(ksalts, 3),
            "mean_leaf_vpd_kpa": _avg(vpds, 3),
            "mean_leaf_delta_t_c": _avg(dts, 2),
            "mean_soil_moisture": _avg(moists, 1),
            "min_soil_moisture": _min_val(moists, 1),
            "max_soil_moisture": _max_val(moists, 1),
            "mean_soil_ec": _avg(ecs, 0),
            "max_soil_ec": _max_val(ecs, 0),
            "mean_soil_temp": _avg(stemps, 1),
            "mean_leaf_temp": _avg(ltemps, 1),
            "max_leaf_temp": _max_val(ltemps, 1),
            "mean_leaf_humidity": _avg(lhums, 1),
            "moisture_stress_pct": _avg([r["sub_indices"].get("moisture_stress_pct") for r in scoped], 1),
            "osmotic_ec_stress_pct": _avg([r["sub_indices"].get("osmotic_ec_stress_pct") for r in scoped], 1),
            "salt_ionic_stress_pct": _avg([r["sub_indices"].get("salt_ionic_stress_pct") for r in scoped], 1),
            "thermal_stress_pct": _avg([r["sub_indices"].get("thermal_stress_pct") for r in scoped], 1),
            "leaf_cwsi_stress_pct": _avg([r["sub_indices"].get("leaf_cwsi_stress_pct") for r in scoped], 1),
            "ph_stress_pct": _avg([r["sub_indices"].get("ph_stress_pct") for r in scoped], 1),
        })

    sdh_map_out: Dict[str, Dict[str, Any]] = {}
    for zid in range(1, 9):
        item = sdh_by_zone[zid]
        n = max(1, item["samples"])
        c = item.pop("_counts")
        item["stress_degree_hours"] = round(item["stress_degree_hours"], 1)
        item["total_sdh"] = item["stress_degree_hours"]
        item["recovery_degree_hours"] = round(item["recovery_degree_hours"], 1)
        item["optimal_pct"] = round((c["opt"] / n) * 100.0, 1)
        item["mild_pct"] = round((c["mild"] / n) * 100.0, 1)
        item["moderate_pct"] = round((c["mod"] / n) * 100.0, 1)
        item["high_pct"] = round((c["high"] / n) * 100.0, 1)
        item["critical_pct"] = round((c["crit"] / n) * 100.0, 1)
        sdh_map_out[str(zid)] = item

    diurnal_profile: List[Dict[str, Any]] = []
    for hr in range(24):
        b = diurnal_buckets[hr]
        diurnal_profile.append({
            "hour_local": hr,
            "hour_label": f"{hr:02d}:00",
            "is_midday_window": 12 <= hr <= 14,
            "mean_psi": _avg(b["psi"], 1),
            "avg_psi": _avg(b["psi"], 1),
            "max_psi": _max_val(b["psi"], 1),
            "mean_pvi": _avg(b["pvi"], 1),
            "mean_cwsi": _avg(b["cwsi"], 3),
            "mean_vpd_kpa": _avg(b["vpd"], 3),
            "mean_pore_ec_dsm": _avg(b["pore_ec"], 3),
            "mean_leaf_temp_c": _avg(b["leaf_temp"], 2),
            "mean_soil_moisture_pct": _avg(b["soil_moist"], 1),
        })

    pulse_recovery_curves: List[Dict[str, Any]] = []
    ts_parsed = [(_parse_iso_ts(pt["recorded_at"]), pt) for pt in timeline_series]
    ts_parsed = [(dt, pt) for (dt, pt) in ts_parsed if dt is not None]

    for tr in treatments[:15]:
        t_dt = _parse_iso_ts(tr.get("applied_at"))
        if t_dt is None:
            continue
        offsets_hours = [-12, -6, -3, -1, 0, 1, 3, 6, 12, 24, 36, 48, 72]
        curve_pts = []
        by_off = {}
        for off_h in offsets_hours:
            window_pts = [
                pt for (dt, pt) in ts_parsed
                if abs(((dt - t_dt).total_seconds() / 3600.0) - off_h) <= 6.0
            ]
            m_psi = _avg([p.get("mean_psi") for p in window_pts], 1)
            by_off[off_h] = m_psi
            curve_pts.append({
                "offset_hours": off_h,
                "mean_psi": m_psi,
                "mean_sri_pct": _avg([p.get("mean_sri_pct") for p in window_pts], 1),
                "mean_cwsi": _avg([p.get("mean_cwsi") for p in window_pts], 3),
                "mean_pore_ec_dsm": _avg([p.get("mean_pore_ec_dsm") for p in window_pts], 3),
            })
        pulse_recovery_curves.append({
            "app_id": tr.get("app_id"),
            "applied_at": tr.get("applied_at"),
            "dat": tr.get("dat"),
            "zone_id": tr.get("zone_id"),
            "treatment_code": tr.get("treatment_code"),
            "h2s_dose_um": tr.get("h2s_dose_um"),
            "humic_dose_mll": tr.get("humic_dose_mll"),
            "nacl_dose_mm": tr.get("nacl_dose_mm"),
            "pre_12h_psi": by_off.get(-12),
            "post_24h_psi": by_off.get(24),
            "post_48h_psi": by_off.get(48),
            "post_72h_psi": by_off.get(72),
            "points": curve_pts,
        })

    return {
        "monitoring_only_mode": True,
        "resolution": resolution,
        "target_zone_id": target_zone_id,
        "target_sensor_id": target_sensor_id,
        "total_time_buckets": len(timeline_series),
        "severity_counts": severity_counts,
        "timeline": timeline_series,
        "zone_series": zone_series,
        "diurnal_profile": diurnal_profile,
        "diurnal_24h": diurnal_profile,
        "sdh_by_zone": sdh_map_out,
        "pulse_recovery_curves": pulse_recovery_curves,
        "pulse_recovery_events": pulse_recovery_curves,
        "treatments": treatments,
        "notes": notes,
    }
