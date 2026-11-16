"""
Isolated Database Layer for PhD Greenhouse, Meter LCD AI Vision, Lab/Harvest,
Batch/Individual Treatment, HOBO Climate Logger & Professor A4 Print App (/data-app).

100% Additive & Non-Intrusive:
- Uses its own dedicated tables (field_measurements, field_treatment_batches,
  env_logger_uploads, env_logger_readings, field_ai_settings).
- Never alters or deletes any existing PLC/HMI SCADA table.
- Supports both PostgreSQL 16 (production Coolify VPS) and SQLite (Edge/Local PC).
"""

import json
import math
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from . import database as db
from .stress_engine import compute_dat, compute_vpd_and_dewpoint


# Exact 8 Color-Coded Treatments from Exp2_Planter_Tags_2x2in_A4.html
EXP2_TREATMENTS: Dict[str, Dict[str, Any]] = {
    "T1": {
        "treatment_no": "T1",
        "zone_id": 1,
        "code_iot": "I-C-0",
        "code_manual": "M-C-0",
        "nacl_mm": 0.0,
        "nahs_um": 0.0,
        "humic_mll": 0.0,
        "bg_hex": "#E2E8F0",
        "header_hex": "#334155",
        "border_hex": "#0F172A",
        "short_en": "0 NaCl | 0 H2S | 0 HS",
        "short_tr": "0 Tuz | 0 H2S | 0 HS",
        "label_en": "T1: Control (0 mM NaCl, 0 uM H2S, 0 mL/L HS)",
        "label_tr": "T1: Kontrol (0 mM Tuz, 0 uM H2S, 0 mL/L Humik)",
    },
    "T2": {
        "treatment_no": "T2",
        "zone_id": 2,
        "code_iot": "I-C-H2S",
        "code_manual": "M-C-H2S",
        "nacl_mm": 0.0,
        "nahs_um": 25.0,
        "humic_mll": 0.0,
        "bg_hex": "#DBEAFE",
        "header_hex": "#1D4ED8",
        "border_hex": "#1E3A8A",
        "short_en": "0 NaCl | 25 uM H2S | 0 HS",
        "short_tr": "0 Tuz | 25 uM H2S | 0 HS",
    "label_en": "T2: 0 mM NaCl + 25 uM NaHS",
        "label_tr": "T2: 0 mM Tuz + 25 uM NaHS",
    },
    "T3": {
        "treatment_no": "T3",
        "zone_id": 3,
        "code_iot": "I-C-HS",
        "code_manual": "M-C-HS",
        "nacl_mm": 0.0,
        "nahs_um": 0.0,
        "humic_mll": 4.0,
        "bg_hex": "#FEF08A",
        "header_hex": "#A16207",
        "border_hex": "#713F12",
        "short_en": "0 NaCl | 0 H2S | 4 mL HS",
        "short_tr": "0 Tuz | 0 H2S | 4 mL HS",
        "label_en": "T3: 0 mM NaCl + 4 mL/L LIQHUMUS NK",
        "label_tr": "T3: 0 mM Tuz + 4 mL/L LIQHUMUS NK",
    },
    "T4": {
        "treatment_no": "T4",
        "zone_id": 4,
        "code_iot": "I-C-H2S+HS",
        "code_manual": "M-C-H2S+HS",
        "nacl_mm": 0.0,
        "nahs_um": 25.0,
        "humic_mll": 4.0,
        "bg_hex": "#DCFCE7",
        "header_hex": "#15803D",
        "border_hex": "#14532D",
        "short_en": "0 NaCl | 25 uM H2S | 4 mL HS",
        "short_tr": "0 Tuz | 25 uM H2S | 4 mL HS",
        "label_en": "T4: 0 mM NaCl + 25 uM NaHS + 4 mL/L HS",
        "label_tr": "T4: 0 mM Tuz + 25 uM NaHS + 4 mL/L HS",
    },
    "T5": {
        "treatment_no": "T5",
        "zone_id": 5,
        "code_iot": "I-S-0",
        "code_manual": "M-S-0",
        "nacl_mm": 80.0,
        "nahs_um": 0.0,
        "humic_mll": 0.0,
        "bg_hex": "#FEE2E2",
        "header_hex": "#DC2626",
        "border_hex": "#7F1D1D",
        "short_en": "80 NaCl | 0 H2S | 0 HS",
        "short_tr": "80 Tuz | 0 H2S | 0 HS",
        "label_en": "T5: Salt Stress (80 mM NaCl, 0 H2S, 0 HS)",
        "label_tr": "T5: Tuz Stresi (80 mM Tuz, 0 H2S, 0 HS)",
    },
    "T6": {
        "treatment_no": "T6",
        "zone_id": 6,
        "code_iot": "I-S-H2S",
        "code_manual": "M-S-H2S",
        "nacl_mm": 80.0,
        "nahs_um": 25.0,
        "humic_mll": 0.0,
        "bg_hex": "#CCFBF1",
        "header_hex": "#0F766E",
        "border_hex": "#134E4A",
        "short_en": "80 NaCl | 25 uM H2S | 0 HS",
        "short_tr": "80 Tuz | 25 uM H2S | 0 HS",
        "label_en": "T6: 80 mM NaCl + 25 uM NaHS",
        "label_tr": "T6: 80 mM Tuz + 25 uM NaHS",
    },
    "T7": {
        "treatment_no": "T7",
        "zone_id": 7,
        "code_iot": "I-S-HS",
        "code_manual": "M-S-HS",
        "nacl_mm": 80.0,
        "nahs_um": 0.0,
        "humic_mll": 4.0,
        "bg_hex": "#FCE7F3",
        "header_hex": "#BE185D",
        "border_hex": "#831843",
        "short_en": "80 NaCl | 0 H2S | 4 mL HS",
        "short_tr": "80 Tuz | 0 H2S | 4 mL HS",
        "label_en": "T7: 80 mM NaCl + 4 mL/L LIQHUMUS NK",
        "label_tr": "T7: 80 mM Tuz + 4 mL/L LIQHUMUS NK",
    },
    "T8": {
        "treatment_no": "T8",
        "zone_id": 8,
        "code_iot": "I-S-H2S+HS",
        "code_manual": "M-S-H2S+HS",
        "nacl_mm": 80.0,
        "nahs_um": 25.0,
        "humic_mll": 4.0,
        "bg_hex": "#EDE9FE",
        "header_hex": "#6D28D9",
        "border_hex": "#4C1D95",
        "short_en": "80 NaCl | 25 uM H2S | 4 mL HS",
        "short_tr": "80 Tuz | 25 uM H2S | 4 mL HS",
        "label_en": "T8: 80 mM NaCl + 25 uM NaHS + 4 mL/L HS",
        "label_tr": "T8: 80 mM Tuz + 25 uM NaHS + 4 mL/L HS",
    },
}


# Visual block fill & ink colors matching the Sera 5 64-Plot Experimental Field Layout poster
FIELD_MAP_COLORS: Dict[str, Dict[str, str]] = {
    "T1": {"bg": "#1565C0", "text": "#FFFFFF", "name": "Blue"},
    "T2": {"bg": "#2E7D32", "text": "#FFFFFF", "name": "Green"},
    "T3": {"bg": "#E65100", "text": "#FFFFFF", "name": "Orange"},
    "T4": {"bg": "#C62828", "text": "#FFFFFF", "name": "Red"},
    "T5": {"bg": "#FACC15", "text": "#0F172A", "name": "Yellow"},
    "T6": {"bg": "#6A1B9A", "text": "#FFFFFF", "name": "Purple"},
    "T7": {"bg": "#81D4FA", "text": "#0F172A", "name": "Light Blue"},
    "T8": {"bg": "#1B4D1E", "text": "#FFFFFF", "name": "Dark Green"},
}

# Exact 64-Plot Randomized Field Layout (Cols 1..8 = IoT Block; Cols 9..16 = Manual Mirror Block)
_IOT_LAYOUT_ROWS: Dict[str, List[str]] = {
    "R1": ["T1", "T2", "T4", "T3", "T5", "T6", "T8", "T7"],  # Cols 1..8
    "R2": ["T2", "T3", "T1", "T4", "T6", "T7", "T8", "T5"],  # Cols 1..8
    "R3": ["T1", "T4", "T3", "T2", "T7", "T8", "T6", "T5"],  # Cols 1..8
    "R4": ["T3", "T2", "T4", "T1", "T5", "T8", "T7", "T6"],  # Cols 1..8
}

_MANUAL_LAYOUT_ROWS: Dict[str, List[str]] = {
    "R1": ["T7", "T8", "T6", "T5", "T3", "T4", "T2", "T1"],  # Cols 9..16
    "R2": ["T5", "T8", "T7", "T6", "T4", "T1", "T3", "T2"],  # Cols 9..16
    "R3": ["T5", "T6", "T8", "T7", "T2", "T3", "T4", "T1"],  # Cols 9..16
    "R4": ["T6", "T7", "T8", "T5", "T1", "T4", "T2", "T3"],  # Cols 9..16
}


def build_exp2_field_layout() -> List[Dict[str, Any]]:
    """Return all 64 Experiment 2 plots in physical Sera 5 greenhouse coordinates (Cols 1..16 x R1..R4)."""
    plots: List[Dict[str, Any]] = []
    for arm, row_map, col_start in (
        ("IoT", _IOT_LAYOUT_ROWS, 1),
        ("Manual", _MANUAL_LAYOUT_ROWS, 9),
    ):
        for r_idx in (1, 2, 3, 4):
            rep = f"R{r_idx}"
            t_list = row_map[rep]
            for offset, t_key in enumerate(t_list):
                col = col_start + offset
                colors = FIELD_MAP_COLORS[t_key]
                t_info = EXP2_TREATMENTS[t_key]
                salt_zone = "80mM Salt" if float(t_info["nacl_mm"]) > 0 else "No Salt"
                plots.append({
                    "arm": arm,
                    "rep": rep,
                    "row_idx": r_idx,
                    "col": col,
                    "treatment": t_key,
                    "plot_label": f"{rep}{t_key}",
                    "plot_code": f"C{col:02d}-{rep}{t_key}",
                    "salt_zone": salt_zone,
                    "map_bg_hex": colors["bg"],
                    "map_text_hex": colors["text"],
                    "color_name": colors["name"],
                })
    return plots


EXP2_FIELD_LAYOUT: List[Dict[str, Any]] = build_exp2_field_layout()
EXP2_FIELD_PLOT_LOOKUP: Dict[Tuple[str, str, str], Dict[str, Any]] = {
    (p["arm"], p["rep"], p["treatment"]): p for p in EXP2_FIELD_LAYOUT
}


def lookup_field_plot(arm: str, rep: str, treatment: str) -> Optional[Dict[str, Any]]:
    """Return physical field coordinates (col 1..16, plot_label) for an Exp 2 (arm, rep, treatment)."""
    return EXP2_FIELD_PLOT_LOOKUP.get((arm, rep, treatment))


def build_exp1_treatments() -> Dict[str, Dict[str, Any]]:
    """Experiment 1 factorial key (27 treatments: 0/80/120 mM NaCl x 0/25/100 uM NaHS x 0/2/4 mL/L Humic)."""
    out: Dict[str, Dict[str, Any]] = {}
    idx = 1
    for salt in (0.0, 80.0, 120.0):
        for nahs in (0.0, 25.0, 100.0):
            for humic in (0.0, 2.0, 4.0):
                t_key = f"T{idx}"
                out[t_key] = {
                    "treatment_no": t_key,
                    "zone_id": None,
                    "code_iot": f"EXP1-{t_key}",
                    "code_manual": f"EXP1-{t_key}",
                    "nacl_mm": salt,
                    "nahs_um": nahs,
                    "humic_mll": humic,
                    "bg_hex": "#F1F5F9" if salt == 0 else ("#FEF3C7" if salt == 80 else "#FEE2E2"),
                    "header_hex": "#334155" if salt == 0 else ("#B45309" if salt == 80 else "#B91C1C"),
                    "border_hex": "#0F172A",
                    "short_en": f"{int(salt)} NaCl | {int(nahs)} H2S | {int(humic)} HS",
                    "short_tr": f"{int(salt)} Tuz | {int(nahs)} H2S | {int(humic)} HS",
                    "label_en": f"{t_key}: {int(salt)} mM NaCl + {int(nahs)} uM NaHS + {int(humic)} mL/L HS",
                    "label_tr": f"{t_key}: {int(salt)} mM Tuz + {int(nahs)} uM NaHS + {int(humic)} mL/L HS",
                }
                idx += 1
    return out


EXP1_TREATMENTS = build_exp1_treatments()


PARAMETER_CATALOG: List[Dict[str, Any]] = [
    # 1. Greenhouse Morphology & Phenology
    {"key": "plant_height_cm", "category": "morphology", "label_en": "Plant Height", "label_tr": "Bitki Boyu", "unit": "cm", "min": 2.0, "max": 350.0, "decimals": 1, "ai_profile": "ruler_or_plant"},
    {"key": "stem_diameter_mm", "category": "morphology", "label_en": "Stem Diameter", "label_tr": "Govde Capi", "unit": "mm", "min": 1.0, "max": 35.0, "decimals": 2, "ai_profile": "caliper_lcd"},
    {"key": "leaf_count", "category": "morphology", "label_en": "Number of Leaves", "label_tr": "Yaprak Sayisi", "unit": "count", "min": 1.0, "max": 90.0, "decimals": 0, "ai_profile": "plant_count"},
    {"key": "spad_value", "category": "morphology", "label_en": "SPAD Chlorophyll", "label_tr": "SPAD Klorofil", "unit": "SPAD", "min": 5.0, "max": 95.0, "decimals": 1, "ai_profile": "spad_lcd"},
    {"key": "internode_length_cm", "category": "morphology", "label_en": "Internode Length", "label_tr": "Bogum Arasi Uzunlugu", "unit": "cm", "min": 0.5, "max": 35.0, "decimals": 1, "ai_profile": "ruler_or_plant"},
    {"key": "truss_count", "category": "morphology", "label_en": "Truss / Cluster Count", "label_tr": "Salkim Sayisi", "unit": "count", "min": 0.0, "max": 15.0, "decimals": 0, "ai_profile": "plant_count"},
    {"key": "flower_count_truss", "category": "morphology", "label_en": "Flowers per Truss", "label_tr": "Salkimda Cicek Sayisi", "unit": "count", "min": 0.0, "max": 25.0, "decimals": 0, "ai_profile": "plant_count"},
    {"key": "fruit_set_truss", "category": "morphology", "label_en": "Fruits Set per Truss", "label_tr": "Salkimda Meyve Tutumu", "unit": "count", "min": 0.0, "max": 25.0, "decimals": 0, "ai_profile": "plant_count"},
    {"key": "days_to_flowering", "category": "morphology", "label_en": "Days to First Flower", "label_tr": "Ilk Ciceklenme Gun Sayisi", "unit": "days", "min": 1.0, "max": 140.0, "decimals": 0, "ai_profile": "generic_lcd"},

    # 2. Porometer & Leaf Gas Exchange (Decagon SC-1 / LI-6400XT)
    {"key": "stomatal_conductance_gs", "category": "porometer", "label_en": "Stomatal Conductance (gs)", "label_tr": "Stoma Iletkenligi (gs)", "unit": "mmol/m2/s", "min": 1.0, "max": 1200.0, "decimals": 1, "ai_profile": "porometer_lcd"},
    {"key": "porometer_leaf_temp_c", "category": "porometer", "label_en": "Porometer Leaf Temp", "label_tr": "Porometre Yaprak Sicakligi", "unit": "°C", "min": 5.0, "max": 50.0, "decimals": 1, "ai_profile": "porometer_lcd"},
    {"key": "porometer_leaf_rh_pct", "category": "porometer", "label_en": "Porometer Leaf RH", "label_tr": "Porometre Yaprak Nemi", "unit": "%", "min": 5.0, "max": 100.0, "decimals": 1, "ai_profile": "porometer_lcd"},
    {"key": "porometer_sensor_temp_c", "category": "porometer", "label_en": "Porometer Sensor Temp", "label_tr": "Porometre Sensor Sicakligi", "unit": "°C", "min": 5.0, "max": 50.0, "decimals": 1, "ai_profile": "porometer_lcd"},
    {"key": "porometer_sensor_rh_pct", "category": "porometer", "label_en": "Porometer Sensor RH", "label_tr": "Porometre Sensor Nemi", "unit": "%", "min": 5.0, "max": 100.0, "decimals": 1, "ai_profile": "porometer_lcd"},
    {"key": "photosynthesis_pn", "category": "porometer", "label_en": "Net Photosynthesis (Pn)", "label_tr": "Net Fotosentez Hizi (Pn)", "unit": "umol/m2/s", "min": 0.0, "max": 50.0, "decimals": 2, "ai_profile": "licor_lcd"},
    {"key": "transpiration_tr", "category": "porometer", "label_en": "Transpiration Rate (Tr)", "label_tr": "Transpirasyon Hizi (Tr)", "unit": "mmol/m2/s", "min": 0.0, "max": 25.0, "decimals": 2, "ai_profile": "licor_lcd"},
    {"key": "intercellular_ci", "category": "porometer", "label_en": "Intercellular CO2 (Ci)", "label_tr": "Hucreselarasi CO2 (Ci)", "unit": "umol/mol", "min": 20.0, "max": 800.0, "decimals": 1, "ai_profile": "licor_lcd"},

    # 3. Spectrum #2958 IR & Penetration Probe Thermometer
    {"key": "ir_leaf_temp_c", "category": "ir_thermometer", "label_en": "IR Leaf Surface Temp", "label_tr": "IR Yaprak Yuzey Sicakligi", "unit": "°C", "min": 5.0, "max": 50.0, "decimals": 1, "ai_profile": "ir_thermometer_lcd"},
    {"key": "probe_root_temp_c", "category": "ir_thermometer", "label_en": "Probe Root-Zone Temp", "label_tr": "Prob Kok Bolgesi Sicakligi", "unit": "°C", "min": 5.0, "max": 45.0, "decimals": 1, "ai_profile": "ir_thermometer_lcd"},
    {"key": "probe_solution_temp_c", "category": "ir_thermometer", "label_en": "Probe Solution Temp", "label_tr": "Prob Cozelti Sicakligi", "unit": "°C", "min": 5.0, "max": 45.0, "decimals": 1, "ai_profile": "ir_thermometer_lcd"},
    {"key": "canopy_delta_t_c", "category": "ir_thermometer", "label_en": "Leaf-Air Delta T", "label_tr": "Yaprak-Hava Delta T", "unit": "°C", "min": -12.0, "max": 15.0, "decimals": 2, "ai_profile": "ir_thermometer_lcd"},

    # 4. Handheld Soil 4-in-1 & Leaf RH/T Reference Unit (Manual Arm Weekly Check)
    {"key": "hh_soil_vwc_pct", "category": "handheld_sensor", "label_en": "Handheld Substrate VWC", "label_tr": "El Sensoru Ortam Nemi (VWC)", "unit": "%", "min": 1.0, "max": 100.0, "decimals": 1, "ai_profile": "generic_lcd"},
    {"key": "hh_soil_ec_uscm", "category": "handheld_sensor", "label_en": "Handheld Substrate EC", "label_tr": "El Sensoru Ortam EC", "unit": "uS/cm", "min": 50.0, "max": 25000.0, "decimals": 0, "ai_profile": "ec_ph_lcd"},
    {"key": "hh_soil_ph", "category": "handheld_sensor", "label_en": "Handheld Substrate pH", "label_tr": "El Sensoru Ortam pH", "unit": "pH", "min": 3.0, "max": 9.5, "decimals": 2, "ai_profile": "ec_ph_lcd"},
    {"key": "hh_soil_temp_c", "category": "handheld_sensor", "label_en": "Handheld Substrate Temp", "label_tr": "El Sensoru Ortam Sicakligi", "unit": "°C", "min": 5.0, "max": 45.0, "decimals": 1, "ai_profile": "generic_lcd"},
    {"key": "hh_leaf_temp_c", "category": "handheld_sensor", "label_en": "Handheld Leaf Temp", "label_tr": "El Sensoru Yaprak Sicakligi", "unit": "°C", "min": 5.0, "max": 50.0, "decimals": 1, "ai_profile": "generic_lcd"},
    {"key": "hh_leaf_rh_pct", "category": "handheld_sensor", "label_en": "Handheld Leaf RH", "label_tr": "El Sensoru Yaprak Nemi", "unit": "%", "min": 5.0, "max": 100.0, "decimals": 1, "ai_profile": "generic_lcd"},

    # 5. Daily Water Supply & Tray Drainage Balance (ATC EC/TDS & pH Meters)
    {"key": "water_supplied_ml", "category": "drainage", "label_en": "Supplied Solution Volume", "label_tr": "Verilen Cozelti Hacmi", "unit": "mL", "min": 10.0, "max": 25000.0, "decimals": 0, "ai_profile": "generic_lcd"},
    {"key": "drainage_volume_ml", "category": "drainage", "label_en": "Collected Drainage Volume", "label_tr": "Toplanan Drenaj Hacmi", "unit": "mL", "min": 0.0, "max": 20000.0, "decimals": 0, "ai_profile": "generic_lcd"},
    {"key": "drainage_fraction_pct", "category": "drainage", "label_en": "Drainage Fraction", "label_tr": "Drenaj Orani", "unit": "%", "min": 0.0, "max": 100.0, "decimals": 1, "ai_profile": "generic_lcd"},
    {"key": "drainage_ec_uscm", "category": "drainage", "label_en": "Drainage EC", "label_tr": "Drenaj EC", "unit": "uS/cm", "min": 100.0, "max": 30000.0, "decimals": 0, "ai_profile": "ec_ph_lcd"},
    {"key": "drainage_tds_ppm", "category": "drainage", "label_en": "Drainage TDS", "label_tr": "Drenaj TDS", "unit": "ppm", "min": 50.0, "max": 20000.0, "decimals": 0, "ai_profile": "ec_ph_lcd"},
    {"key": "drainage_ph", "category": "drainage", "label_en": "Drainage pH", "label_tr": "Drenaj pH", "unit": "pH", "min": 3.0, "max": 9.5, "decimals": 2, "ai_profile": "ec_ph_lcd"},
    {"key": "feed_ec_uscm", "category": "drainage", "label_en": "Supplied Feed EC", "label_tr": "Besleme Cozeltisi EC", "unit": "uS/cm", "min": 100.0, "max": 20000.0, "decimals": 0, "ai_profile": "ec_ph_lcd"},
    {"key": "feed_ph", "category": "drainage", "label_en": "Supplied Feed pH", "label_tr": "Besleme Cozeltisi pH", "unit": "pH", "min": 3.5, "max": 9.0, "decimals": 2, "ai_profile": "ec_ph_lcd"},

    # 6. Fruit Ripening, Yield & Quality
    {"key": "days_flower_to_breaker", "category": "fruit_harvest", "label_en": "Days Flower to Breaker", "label_tr": "Cicekten Renk Donumune Gun", "unit": "days", "min": 15.0, "max": 90.0, "decimals": 0, "ai_profile": "generic_lcd"},
    {"key": "days_flower_to_red_ripe", "category": "fruit_harvest", "label_en": "Days Flower to Red-Ripe", "label_tr": "Cicekten Tam Olgunluga Gun", "unit": "days", "min": 25.0, "max": 110.0, "decimals": 0, "ai_profile": "generic_lcd"},
    {"key": "harvest_fruit_count", "category": "fruit_harvest", "label_en": "Harvested Fruit Count", "label_tr": "Hasat Edilen Meyve Sayisi", "unit": "count", "min": 0.0, "max": 60.0, "decimals": 0, "ai_profile": "plant_count"},
    {"key": "marketable_fruit_fw_g", "category": "fruit_harvest", "label_en": "Marketable Fruit Weight", "label_tr": "Pazarlanabilir Meyve Agirligi", "unit": "g", "min": 1.0, "max": 15000.0, "decimals": 2, "ai_profile": "balance_lcd"},
    {"key": "total_fruit_fw_g", "category": "fruit_harvest", "label_en": "Total Fruit Weight", "label_tr": "Toplam Meyve Agirligi", "unit": "g", "min": 1.0, "max": 15000.0, "decimals": 2, "ai_profile": "balance_lcd"},
    {"key": "single_fruit_fw_g", "category": "fruit_harvest", "label_en": "Mean Single Fruit Weight", "label_tr": "Ortalama Tek Meyve Agirligi", "unit": "g", "min": 5.0, "max": 600.0, "decimals": 2, "ai_profile": "balance_lcd"},
    {"key": "fruit_equatorial_diam_mm", "category": "fruit_harvest", "label_en": "Fruit Equatorial Diameter", "label_tr": "Meyve Ekvator Capi", "unit": "mm", "min": 10.0, "max": 140.0, "decimals": 2, "ai_profile": "caliper_lcd"},
    {"key": "fruit_polar_diam_mm", "category": "fruit_harvest", "label_en": "Fruit Polar Diameter", "label_tr": "Meyve Kutup Capi", "unit": "mm", "min": 10.0, "max": 140.0, "decimals": 2, "ai_profile": "caliper_lcd"},
    {"key": "ber_fruit_pct", "category": "fruit_harvest", "label_en": "Blossom-End Rot (BER)", "label_tr": "Cicek Burnu Curuklugu (BER)", "unit": "%", "min": 0.0, "max": 100.0, "decimals": 1, "ai_profile": "generic_lcd"},
    {"key": "cracked_fruit_pct", "category": "fruit_harvest", "label_en": "Fruit Cracking", "label_tr": "Meyve Catlamasi", "unit": "%", "min": 0.0, "max": 100.0, "decimals": 1, "ai_profile": "generic_lcd"},
    {"key": "juice_brix_pct", "category": "fruit_harvest", "label_en": "Soluble Solids (TSS / Brix)", "label_tr": "SCKM (Brix)", "unit": "% Brix", "min": 1.0, "max": 16.0, "decimals": 2, "ai_profile": "generic_lcd"},
    {"key": "juice_ph", "category": "fruit_harvest", "label_en": "Fruit Juice pH", "label_tr": "Meyve Suyu pH", "unit": "pH", "min": 3.0, "max": 6.5, "decimals": 2, "ai_profile": "ec_ph_lcd"},
    {"key": "juice_ec_uscm", "category": "fruit_harvest", "label_en": "Fruit Juice EC", "label_tr": "Meyve Suyu EC", "unit": "uS/cm", "min": 500.0, "max": 15000.0, "decimals": 0, "ai_profile": "ec_ph_lcd"},
    {"key": "juice_tds_ppm", "category": "fruit_harvest", "label_en": "Fruit Juice TDS", "label_tr": "Meyve Suyu TDS", "unit": "ppm", "min": 250.0, "max": 10000.0, "decimals": 0, "ai_profile": "ec_ph_lcd"},
    {"key": "fruit_dry_matter_pct", "category": "fruit_harvest", "label_en": "Fruit Dry Matter", "label_tr": "Meyve Kuru Madde Orani", "unit": "%", "min": 2.0, "max": 20.0, "decimals": 2, "ai_profile": "balance_lcd"},

    # 7. CI-202 Leaf Area & Destructive Biomass (0.0001 g Balance)
    {"key": "leaf_area_cm2", "category": "biomass_leaf_area", "label_en": "Total Plant Leaf Area (CI-202)", "label_tr": "Toplam Yaprak Alani (CI-202)", "unit": "cm2", "min": 5.0, "max": 35000.0, "decimals": 2, "ai_profile": "leaf_area_lcd"},
    {"key": "single_leaf_area_cm2", "category": "biomass_leaf_area", "label_en": "Single Leaf Area (CI-202)", "label_tr": "Tek Yaprak Alani (CI-202)", "unit": "cm2", "min": 1.0, "max": 2500.0, "decimals": 2, "ai_profile": "leaf_area_lcd"},
    {"key": "shoot_fw_g", "category": "biomass_leaf_area", "label_en": "Shoot Fresh Weight", "label_tr": "Surgun Yas Agirligi", "unit": "g", "min": 0.5, "max": 5000.0, "decimals": 4, "ai_profile": "balance_lcd"},
    {"key": "shoot_dw_g", "category": "biomass_leaf_area", "label_en": "Shoot Dry Weight (65-70 C)", "label_tr": "Surgun Kuru Agirligi", "unit": "g", "min": 0.05, "max": 1000.0, "decimals": 4, "ai_profile": "balance_lcd"},
    {"key": "root_fw_g", "category": "biomass_leaf_area", "label_en": "Root Fresh Weight", "label_tr": "Kok Yas Agirligi", "unit": "g", "min": 0.1, "max": 1500.0, "decimals": 4, "ai_profile": "balance_lcd"},
    {"key": "root_dw_g", "category": "biomass_leaf_area", "label_en": "Root Dry Weight (65-70 C)", "label_tr": "Kok Kuru Agirligi", "unit": "g", "min": 0.01, "max": 400.0, "decimals": 4, "ai_profile": "balance_lcd"},
    {"key": "root_length_cm", "category": "biomass_leaf_area", "label_en": "Root Length", "label_tr": "Kok Uzunlugu", "unit": "cm", "min": 2.0, "max": 180.0, "decimals": 1, "ai_profile": "ruler_or_plant"},
    {"key": "root_shoot_dw_ratio", "category": "biomass_leaf_area", "label_en": "Root:Shoot Dry Ratio", "label_tr": "Kok:Surgun Kuru Agirlik Orani", "unit": "ratio", "min": 0.01, "max": 2.0, "decimals": 3, "ai_profile": "generic_lcd"},

    # 8. Laboratory Biochemical, Enzymatic, Hormonal & Mineral Suite
    {"key": "leaf_rwc_pct", "category": "biochemical_lab", "label_en": "Leaf Relative Water Content (RWC)", "label_tr": "Yaprak Oransal Su Icerigi (RWC)", "unit": "%", "min": 20.0, "max": 100.0, "decimals": 2, "ai_profile": "generic_lcd"},
    {"key": "electrolyte_leakage_pct", "category": "biochemical_lab", "label_en": "Electrolyte Leakage (EL)", "label_tr": "Elektrolit Sizintisi (EL)", "unit": "%", "min": 1.0, "max": 100.0, "decimals": 2, "ai_profile": "ec_ph_lcd"},
    {"key": "chl_a_mgg", "category": "biochemical_lab", "label_en": "Chlorophyll a (663/645 nm)", "label_tr": "Klorofil a", "unit": "mg/g FW", "min": 0.05, "max": 15.0, "decimals": 4, "ai_profile": "generic_lcd"},
    {"key": "chl_b_mgg", "category": "biochemical_lab", "label_en": "Chlorophyll b (663/645 nm)", "label_tr": "Klorofil b", "unit": "mg/g FW", "min": 0.02, "max": 10.0, "decimals": 4, "ai_profile": "generic_lcd"},
    {"key": "chl_total_mgg", "category": "biochemical_lab", "label_en": "Total Chlorophyll", "label_tr": "Toplam Klorofil", "unit": "mg/g FW", "min": 0.1, "max": 20.0, "decimals": 4, "ai_profile": "generic_lcd"},
    {"key": "carotenoid_mgg", "category": "biochemical_lab", "label_en": "Carotenoids (470 nm)", "label_tr": "Karotenoid", "unit": "mg/g FW", "min": 0.02, "max": 8.0, "decimals": 4, "ai_profile": "generic_lcd"},
    {"key": "h2o2_mmolkg", "category": "biochemical_lab", "label_en": "Hydrogen Peroxide (H2O2)", "label_tr": "Hidrojen Peroksit (H2O2)", "unit": "mmol/kg FW", "min": 0.01, "max": 200.0, "decimals": 3, "ai_profile": "generic_lcd"},
    {"key": "mda_mmolkg", "category": "biochemical_lab", "label_en": "Malondialdehyde (MDA)", "label_tr": "Malondialdehit (MDA)", "unit": "mmol/kg FW", "min": 0.01, "max": 200.0, "decimals": 3, "ai_profile": "generic_lcd"},
    {"key": "proline_mmolkg", "category": "biochemical_lab", "label_en": "Free Proline", "label_tr": "Serbest Prolin", "unit": "mmol/kg FW", "min": 0.01, "max": 500.0, "decimals": 3, "ai_profile": "generic_lcd"},
    {"key": "sod_eu", "category": "biochemical_lab", "label_en": "SOD Activity (560 nm)", "label_tr": "SOD Enzim Aktivitesi", "unit": "EU/g FW", "min": 0.1, "max": 5000.0, "decimals": 2, "ai_profile": "generic_lcd"},
    {"key": "cat_eu", "category": "biochemical_lab", "label_en": "CAT Activity (240 nm)", "label_tr": "CAT Enzim Aktivitesi", "unit": "EU/g FW", "min": 0.01, "max": 5000.0, "decimals": 2, "ai_profile": "generic_lcd"},
    {"key": "apx_eu", "category": "biochemical_lab", "label_en": "APX Activity (290 nm)", "label_tr": "APX Enzim Aktivitesi", "unit": "EU/g FW", "min": 0.01, "max": 5000.0, "decimals": 2, "ai_profile": "generic_lcd"},
    {"key": "pod_eu", "category": "biochemical_lab", "label_en": "POD Activity (436 nm)", "label_tr": "POD Enzim Aktivitesi", "unit": "EU/g FW", "min": 0.1, "max": 20000.0, "decimals": 2, "ai_profile": "generic_lcd"},
    {"key": "gr_eu", "category": "biochemical_lab", "label_en": "GR Activity (340 nm)", "label_tr": "GR Enzim Aktivitesi", "unit": "EU/g FW", "min": 0.01, "max": 5000.0, "decimals": 2, "ai_profile": "generic_lcd"},
    {"key": "iaa_ngg", "category": "biochemical_lab", "label_en": "IAA Auxin (HPLC)", "label_tr": "IAA Oksin (HPLC)", "unit": "ng/g FW", "min": 0.01, "max": 5000.0, "decimals": 2, "ai_profile": "generic_lcd"},
    {"key": "ga_ngg", "category": "biochemical_lab", "label_en": "GA Gibberellin (HPLC)", "label_tr": "GA Giberellin (HPLC)", "unit": "ng/g FW", "min": 0.01, "max": 5000.0, "decimals": 2, "ai_profile": "generic_lcd"},
    {"key": "aba_ngg", "category": "biochemical_lab", "label_en": "ABA Abscisic Acid (HPLC)", "label_tr": "ABA Absisik Asit (HPLC)", "unit": "ng/g FW", "min": 0.01, "max": 10000.0, "decimals": 2, "ai_profile": "generic_lcd"},
    {"key": "leaf_k_pct", "category": "biochemical_lab", "label_en": "Leaf Potassium (K+)", "label_tr": "Yaprak Potasyum (K+)", "unit": "% DW", "min": 0.1, "max": 10.0, "decimals": 3, "ai_profile": "generic_lcd"},
    {"key": "leaf_na_pct", "category": "biochemical_lab", "label_en": "Leaf Sodium (Na+)", "label_tr": "Yaprak Sodyum (Na+)", "unit": "% DW", "min": 0.01, "max": 8.0, "decimals": 3, "ai_profile": "generic_lcd"},
    {"key": "leaf_k_na_ratio", "category": "biochemical_lab", "label_en": "Leaf K+/Na+ Ratio", "label_tr": "Yaprak K+/Na+ Orani", "unit": "ratio", "min": 0.05, "max": 100.0, "decimals": 2, "ai_profile": "generic_lcd"},
]

PARAM_MAP: Dict[str, Dict[str, Any]] = {p["key"]: p for p in PARAMETER_CATALOG}


def init_field_data_db() -> None:
    """Create isolated Field & Lab Data App tables without modifying any existing SCADA table."""
    with db.get_conn() as conn:
        cur = conn.cursor()
        if db.IS_POSTGRES:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS field_measurements (
                    record_id TEXT PRIMARY KEY,
                    experiment_code TEXT NOT NULL DEFAULT 'EXP2',
                    measured_at TEXT NOT NULL,
                    dat INTEGER,
                    fertigation_arm TEXT NOT NULL DEFAULT 'IoT',
                    treatment_no TEXT NOT NULL,
                    treatment_code TEXT NOT NULL,
                    nacl_mm REAL NOT NULL DEFAULT 0.0,
                    nahs_um REAL NOT NULL DEFAULT 0.0,
                    humic_mll REAL NOT NULL DEFAULT 0.0,
                    replicate_no TEXT NOT NULL,
                    planter_code TEXT NOT NULL,
                    plc_zone_id INTEGER,
                    plc_sensor_id INTEGER,
                    plant_no TEXT NOT NULL DEFAULT 'P1',
                    truss_no INTEGER,
                    category TEXT NOT NULL,
                    parameter_key TEXT NOT NULL,
                    parameter_label TEXT NOT NULL,
                    unit TEXT NOT NULL,
                    manual_value REAL,
                    ai_value REAL,
                    ai_secondary_value REAL,
                    final_value REAL NOT NULL,
                    entry_mode TEXT NOT NULL DEFAULT 'manual',
                    verification_status TEXT NOT NULL DEFAULT 'human_confirmed',
                    ai_confidence REAL,
                    ai_model TEXT,
                    ai_extra_json TEXT,
                    plc_concurrent_json TEXT,
                    photo_rel_path TEXT,
                    notes TEXT,
                    recorded_by TEXT NOT NULL DEFAULT 'Mamunur Reza',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    edit_history_json TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_fm_measured_at ON field_measurements(measured_at DESC);
                CREATE INDEX IF NOT EXISTS idx_fm_exp_param ON field_measurements(experiment_code, parameter_key, treatment_no);
                CREATE INDEX IF NOT EXISTS idx_fm_planter ON field_measurements(planter_code, measured_at DESC);

                CREATE TABLE IF NOT EXISTS field_treatment_batches (
                    batch_app_id TEXT PRIMARY KEY,
                    experiment_code TEXT NOT NULL DEFAULT 'EXP2',
                    applied_at TEXT NOT NULL,
                    dat INTEGER,
                    scope_type TEXT NOT NULL DEFAULT 'group',
                    group_label TEXT,
                    target_arms_json TEXT NOT NULL,
                    target_treatments_json TEXT NOT NULL,
                    target_replicates_json TEXT NOT NULL,
                    affected_planters_count INTEGER NOT NULL DEFAULT 1,
                    application_type TEXT NOT NULL DEFAULT 'nahs_humic_pulse',
                    nahs_um REAL NOT NULL DEFAULT 0.0,
                    nahs_stock_mg_100ml REAL,
                    humic_mll REAL NOT NULL DEFAULT 0.0,
                    humic_product TEXT NOT NULL DEFAULT 'LIQHUMUS Liquid 18 (NK)',
                    nacl_mm REAL NOT NULL DEFAULT 0.0,
                    nutrient_stage TEXT,
                    volume_per_planter_l REAL,
                    total_volume_l REAL,
                    solution_ec_uscm INTEGER,
                    solution_ph REAL,
                    hours_after_morning_irrig REAL,
                    photo_rel_path TEXT,
                    notes TEXT,
                    recorded_by TEXT NOT NULL DEFAULT 'Mamunur Reza',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_ftb_applied_at ON field_treatment_batches(applied_at DESC);

                CREATE TABLE IF NOT EXISTS env_logger_uploads (
                    upload_id TEXT PRIMARY KEY,
                    uploaded_at TEXT NOT NULL,
                    experiment_code TEXT NOT NULL DEFAULT 'EXP2',
                    logger_type TEXT NOT NULL,
                    location_tag TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    rows_parsed INTEGER NOT NULL DEFAULT 0,
                    rows_inserted INTEGER NOT NULL DEFAULT 0,
                    rows_skipped_duplicate INTEGER NOT NULL DEFAULT 0,
                    start_time TEXT,
                    end_time TEXT,
                    notes TEXT,
                    uploaded_by TEXT NOT NULL DEFAULT 'Mamunur Reza'
                );

                CREATE TABLE IF NOT EXISTS env_logger_readings (
                    id SERIAL PRIMARY KEY,
                    upload_id TEXT NOT NULL,
                    experiment_code TEXT NOT NULL DEFAULT 'EXP2',
                    location_tag TEXT NOT NULL,
                    logger_type TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    air_temp_c REAL,
                    rh_pct REAL,
                    light_lux REAL,
                    estimated_ppfd_umol REAL,
                    vpd_kpa REAL,
                    dew_point_c REAL,
                    UNIQUE(location_tag, logger_type, recorded_at)
                );
                CREATE INDEX IF NOT EXISTS idx_env_loc_time ON env_logger_readings(location_tag, recorded_at DESC);

                CREATE TABLE IF NOT EXISTS field_ai_settings (
                    id INTEGER PRIMARY KEY,
                    provider TEXT NOT NULL DEFAULT 'openrouter',
                    openrouter_api_key TEXT,
                    gemini_api_key TEXT,
                    primary_model TEXT NOT NULL DEFAULT 'google/gemini-2.5-flash',
                    secondary_model TEXT NOT NULL DEFAULT 'openai/gpt-4o-mini',
                    dual_verify_enabled INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL
                );
            """)
        else:
            cur.executescript("""
                CREATE TABLE IF NOT EXISTS field_measurements (
                    record_id TEXT PRIMARY KEY,
                    experiment_code TEXT NOT NULL DEFAULT 'EXP2',
                    measured_at TEXT NOT NULL,
                    dat INTEGER,
                    fertigation_arm TEXT NOT NULL DEFAULT 'IoT',
                    treatment_no TEXT NOT NULL,
                    treatment_code TEXT NOT NULL,
                    nacl_mm REAL NOT NULL DEFAULT 0.0,
                    nahs_um REAL NOT NULL DEFAULT 0.0,
                    humic_mll REAL NOT NULL DEFAULT 0.0,
                    replicate_no TEXT NOT NULL,
                    planter_code TEXT NOT NULL,
                    plc_zone_id INTEGER,
                    plc_sensor_id INTEGER,
                    plant_no TEXT NOT NULL DEFAULT 'P1',
                    truss_no INTEGER,
                    category TEXT NOT NULL,
                    parameter_key TEXT NOT NULL,
                    parameter_label TEXT NOT NULL,
                    unit TEXT NOT NULL,
                    manual_value REAL,
                    ai_value REAL,
                    ai_secondary_value REAL,
                    final_value REAL NOT NULL,
                    entry_mode TEXT NOT NULL DEFAULT 'manual',
                    verification_status TEXT NOT NULL DEFAULT 'human_confirmed',
                    ai_confidence REAL,
                    ai_model TEXT,
                    ai_extra_json TEXT,
                    plc_concurrent_json TEXT,
                    photo_rel_path TEXT,
                    notes TEXT,
                    recorded_by TEXT NOT NULL DEFAULT 'Mamunur Reza',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    edit_history_json TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_fm_measured_at ON field_measurements(measured_at DESC);
                CREATE INDEX IF NOT EXISTS idx_fm_exp_param ON field_measurements(experiment_code, parameter_key, treatment_no);
                CREATE INDEX IF NOT EXISTS idx_fm_planter ON field_measurements(planter_code, measured_at DESC);

                CREATE TABLE IF NOT EXISTS field_treatment_batches (
                    batch_app_id TEXT PRIMARY KEY,
                    experiment_code TEXT NOT NULL DEFAULT 'EXP2',
                    applied_at TEXT NOT NULL,
                    dat INTEGER,
                    scope_type TEXT NOT NULL DEFAULT 'group',
                    group_label TEXT,
                    target_arms_json TEXT NOT NULL,
                    target_treatments_json TEXT NOT NULL,
                    target_replicates_json TEXT NOT NULL,
                    affected_planters_count INTEGER NOT NULL DEFAULT 1,
                    application_type TEXT NOT NULL DEFAULT 'nahs_humic_pulse',
                    nahs_um REAL NOT NULL DEFAULT 0.0,
                    nahs_stock_mg_100ml REAL,
                    humic_mll REAL NOT NULL DEFAULT 0.0,
                    humic_product TEXT NOT NULL DEFAULT 'LIQHUMUS Liquid 18 (NK)',
                    nacl_mm REAL NOT NULL DEFAULT 0.0,
                    nutrient_stage TEXT,
                    volume_per_planter_l REAL,
                    total_volume_l REAL,
                    solution_ec_uscm INTEGER,
                    solution_ph REAL,
                    hours_after_morning_irrig REAL,
                    photo_rel_path TEXT,
                    notes TEXT,
                    recorded_by TEXT NOT NULL DEFAULT 'Mamunur Reza',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_ftb_applied_at ON field_treatment_batches(applied_at DESC);

                CREATE TABLE IF NOT EXISTS env_logger_uploads (
                    upload_id TEXT PRIMARY KEY,
                    uploaded_at TEXT NOT NULL,
                    experiment_code TEXT NOT NULL DEFAULT 'EXP2',
                    logger_type TEXT NOT NULL,
                    location_tag TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    rows_parsed INTEGER NOT NULL DEFAULT 0,
                    rows_inserted INTEGER NOT NULL DEFAULT 0,
                    rows_skipped_duplicate INTEGER NOT NULL DEFAULT 0,
                    start_time TEXT,
                    end_time TEXT,
                    notes TEXT,
                    uploaded_by TEXT NOT NULL DEFAULT 'Mamunur Reza'
                );

                CREATE TABLE IF NOT EXISTS env_logger_readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    upload_id TEXT NOT NULL,
                    experiment_code TEXT NOT NULL DEFAULT 'EXP2',
                    location_tag TEXT NOT NULL,
                    logger_type TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    air_temp_c REAL,
                    rh_pct REAL,
                    light_lux REAL,
                    estimated_ppfd_umol REAL,
                    vpd_kpa REAL,
                    dew_point_c REAL,
                    UNIQUE(location_tag, logger_type, recorded_at)
                );
                CREATE INDEX IF NOT EXISTS idx_env_loc_time ON env_logger_readings(location_tag, recorded_at DESC);

                CREATE TABLE IF NOT EXISTS field_ai_settings (
                    id INTEGER PRIMARY KEY,
                    provider TEXT NOT NULL DEFAULT 'openrouter',
                    openrouter_api_key TEXT,
                    gemini_api_key TEXT,
                    primary_model TEXT NOT NULL DEFAULT 'google/gemini-2.5-flash',
                    secondary_model TEXT NOT NULL DEFAULT 'openai/gpt-4o-mini',
                    dual_verify_enabled INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL
                );
            """)

        now_iso = datetime.now(timezone.utc).isoformat()
        if db.IS_POSTGRES:
            cur.execute(
                """
                INSERT INTO field_ai_settings (id, provider, primary_model, secondary_model, dual_verify_enabled, updated_at)
                VALUES (1, 'openrouter', 'google/gemini-2.5-flash', 'openai/gpt-4o-mini', 1, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (now_iso,),
            )
        else:
            cur.execute(
                """
                INSERT OR IGNORE INTO field_ai_settings (id, provider, primary_model, secondary_model, dual_verify_enabled, updated_at)
                VALUES (1, 'openrouter', 'google/gemini-2.5-flash', 'openai/gpt-4o-mini', 1, ?)
                """,
                (now_iso,),
            )

    # Ensure dashboard.html top-menu link to /data-app is present in container builds
    try:
        import os as _os
        dash_path = _os.path.join(_os.path.dirname(__file__), "dashboard.html")
        if _os.path.isfile(dash_path):
            with open(dash_path, "r", encoding="utf-8") as _df:
                _html = _df.read()
            if 'id="menuFieldDataApp"' not in _html and 'id="menuStressStudio"' in _html:
                _target = 'id="menuStressStudio" href="/stress" onclick="event.preventDefault(); switchTab(\'stressStudio\');">🧬 Stress, Recovery &amp; Notes</a>'
                _link = _target + '\n        <a class="top-nav-link" id="menuFieldDataApp" href="/data-app" style="border-color:#0d9488; background:rgba(13,148,136,0.10); color:var(--teal);">📋 Field &amp; Lab Data</a>'
                if _target in _html:
                    with open(dash_path, "w", encoding="utf-8") as _wf:
                        _wf.write(_html.replace(_target, _link, 1))
    except Exception:
        pass


def _resolve_unit_metadata(
    experiment_code: str,
    fertigation_arm: str,
    treatment_no: str,
    replicate_no: str,
) -> Dict[str, Any]:
    exp = (experiment_code or "EXP2").upper().strip()
    arm = "Manual" if str(fertigation_arm).strip().lower() == "manual" else ("EXP1" if exp == "EXP1" else "IoT")
    t_clean = str(treatment_no).strip().upper()
    r_clean = str(replicate_no).strip().upper()
    if not r_clean.startswith("R") and r_clean.isdigit():
        r_clean = f"R{r_clean}"

    t_dict = EXP1_TREATMENTS if exp == "EXP1" else EXP2_TREATMENTS
    t_info = t_dict.get(t_clean)
    if not t_info:
        t_info = {
            "treatment_no": t_clean,
            "zone_id": None,
            "code_iot": f"{arm}-{t_clean}",
            "code_manual": f"{arm}-{t_clean}",
            "nacl_mm": 0.0,
            "nahs_um": 0.0,
            "humic_mll": 0.0,
        }

    zone_id = t_info.get("zone_id") if arm == "IoT" and exp == "EXP2" else None
    plc_sensor_id: Optional[int] = None
    if zone_id is not None and r_clean.startswith("R") and r_clean[1:].isdigit():
        rep_idx = int(r_clean[1:])
        if 1 <= rep_idx <= 4:
            plc_sensor_id = (rep_idx - 1) * 8 + int(zone_id)

    treatment_code = t_info["code_manual"] if arm == "Manual" else t_info["code_iot"]
    planter_code = f"{arm}-{t_clean}-{r_clean}" if exp == "EXP2" else f"EXP1-{t_clean}-{r_clean}"
    return {
        "experiment_code": exp,
        "fertigation_arm": arm,
        "treatment_no": t_clean,
        "treatment_code": treatment_code,
        "nacl_mm": float(t_info["nacl_mm"]),
        "nahs_um": float(t_info["nahs_um"]),
        "humic_mll": float(t_info["humic_mll"]),
        "replicate_no": r_clean,
        "planter_code": planter_code,
        "plc_zone_id": zone_id,
        "plc_sensor_id": plc_sensor_id,
    }


def _snapshot_concurrent_plc(plc_zone_id: Optional[int], plc_sensor_id: Optional[int]) -> Optional[str]:
    """Capture live PLC Soil & Leaf reading at the moment of manual/meter measurement for instant validation."""
    if plc_zone_id is None:
        return None
    try:
        latest = db.get_latest_telemetry()
        if not latest:
            return None
        snap: Dict[str, Any] = {
            "plc_recorded_at": latest.get("recorded_at"),
            "zone_id": plc_zone_id,
            "sensor_id": plc_sensor_id,
        }
        sensors = latest.get("sensors") or []
        if plc_sensor_id and 1 <= plc_sensor_id <= 24:
            for s in sensors:
                if int(s.get("sensor_id") or 0) == plc_sensor_id:
                    snap["sensor"] = {
                        "soil_moisture": s.get("soil_moisture"),
                        "soil_temp": s.get("soil_temp"),
                        "soil_ec": s.get("soil_ec"),
                        "soil_ph": s.get("soil_ph"),
                        "leaf_temp": s.get("leaf_temp"),
                        "leaf_humidity": s.get("leaf_humidity"),
                    }
                    break
        zones = latest.get("zones") or []
        for z in zones:
            if int(z.get("zone_id") or 0) == plc_zone_id:
                snap["zone_avg"] = {
                    "avg_soil_moisture": z.get("avg_soil_moisture"),
                    "avg_soil_temp": z.get("avg_soil_temp"),
                    "avg_soil_ec": z.get("avg_soil_ec"),
                    "avg_leaf_temp": z.get("avg_leaf_temp"),
                    "avg_leaf_humidity": z.get("avg_leaf_humidity"),
                }
                break
        return json.dumps(snap)
    except Exception:
        return None


def get_transplant_date() -> str:
    try:
        cal = db.get_stress_calibration()
        return str(cal.get("transplant_date") or "2026-10-16")
    except Exception:
        return "2026-10-16"


def check_plausibility(parameter_key: str, val: Optional[float]) -> Optional[str]:
    """Returns a warning message if value falls outside biological bounds (e.g. missing decimal point)."""
    if val is None:
        return None
    meta = PARAM_MAP.get(parameter_key)
    if not meta:
        return None
    lo, hi = float(meta["min"]), float(meta["max"])
    if val < lo or val > hi:
        suggested = round(val / 10.0, 2) if (lo <= val / 10.0 <= hi) else None
        hint = f" (Did you mean {suggested} {meta['unit']}?)" if suggested is not None else ""
        return f"Value {val} {meta['unit']} is outside expected range [{lo} .. {hi}] for {meta['label_en']}{hint}"
    return None


def add_measurement(payload: Dict[str, Any]) -> Dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    measured_at = (payload.get("measured_at") or "").strip() or now_iso
    t_date = get_transplant_date()
    dat = payload.get("dat")
    if dat is None:
        dat = compute_dat(measured_at, t_date)

    unit_meta = _resolve_unit_metadata(
        experiment_code=payload.get("experiment_code", "EXP2"),
        fertigation_arm=payload.get("fertigation_arm", "IoT"),
        treatment_no=payload.get("treatment_no", "T1"),
        replicate_no=payload.get("replicate_no", "R1"),
    )

    pkey = str(payload.get("parameter_key") or "custom").strip()
    pdef = PARAM_MAP.get(pkey, {})
    category = str(payload.get("category") or pdef.get("category") or "morphology").strip()
    plabel = str(payload.get("parameter_label") or pdef.get("label_en") or pkey).strip()
    unit = str(payload.get("unit") or pdef.get("unit") or "").strip()

    manual_val = float(payload["manual_value"]) if payload.get("manual_value") is not None and payload.get("manual_value") != "" else None
    ai_val = float(payload["ai_value"]) if payload.get("ai_value") is not None and payload.get("ai_value") != "" else None
    ai_sec_val = float(payload["ai_secondary_value"]) if payload.get("ai_secondary_value") is not None and payload.get("ai_secondary_value") != "" else None

    if payload.get("final_value") is not None and payload.get("final_value") != "":
        final_val = float(payload["final_value"])
    elif manual_val is not None:
        final_val = manual_val
    elif ai_val is not None:
        final_val = ai_val
    else:
        raise ValueError("Either manual_value or ai_value is required.")

    if manual_val is not None and ai_val is not None:
        entry_mode = "manual_plus_ai"
    elif ai_val is not None:
        entry_mode = "ai_photo"
    else:
        entry_mode = "manual"

    verification_status = str(payload.get("verification_status") or ("dual_ai_consensus" if entry_mode != "manual" else "human_confirmed"))
    record_id = payload.get("record_id") or str(uuid.uuid4())
    plant_no = str(payload.get("plant_no") or "P1").strip()
    truss_no = int(payload["truss_no"]) if payload.get("truss_no") not in (None, "") else None
    ai_conf = float(payload["ai_confidence"]) if payload.get("ai_confidence") not in (None, "") else None
    ai_model = str(payload.get("ai_model") or "") or None
    ai_extra_raw = payload.get("ai_extra")
    ai_extra_json = json.dumps(ai_extra_raw) if isinstance(ai_extra_raw, (dict, list)) else (str(ai_extra_raw) if ai_extra_raw else None)

    plc_snap = _snapshot_concurrent_plc(unit_meta["plc_zone_id"], unit_meta["plc_sensor_id"])
    photo_rel = str(payload.get("photo_rel_path") or "").strip() or None
    notes = str(payload.get("notes") or "").strip()
    recorded_by = str(payload.get("recorded_by") or "Mamunur Reza").strip()

    with db.get_conn() as conn:
        cur = conn.cursor()
        db._exec(
            cur,
            """
            INSERT INTO field_measurements (
                record_id, experiment_code, measured_at, dat, fertigation_arm,
                treatment_no, treatment_code, nacl_mm, nahs_um, humic_mll,
                replicate_no, planter_code, plc_zone_id, plc_sensor_id,
                plant_no, truss_no, category, parameter_key, parameter_label, unit,
                manual_value, ai_value, ai_secondary_value, final_value,
                entry_mode, verification_status, ai_confidence, ai_model,
                ai_extra_json, plc_concurrent_json, photo_rel_path, notes,
                recorded_by, created_at, updated_at, edit_history_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                unit_meta["experiment_code"],
                measured_at,
                dat,
                unit_meta["fertigation_arm"],
                unit_meta["treatment_no"],
                unit_meta["treatment_code"],
                unit_meta["nacl_mm"],
                unit_meta["nahs_um"],
                unit_meta["humic_mll"],
                unit_meta["replicate_no"],
                unit_meta["planter_code"],
                unit_meta["plc_zone_id"],
                unit_meta["plc_sensor_id"],
                plant_no,
                truss_no,
                category,
                pkey,
                plabel,
                unit,
                manual_val,
                ai_val,
                ai_sec_val,
                final_val,
                entry_mode,
                verification_status,
                ai_conf,
                ai_model,
                ai_extra_json,
                plc_snap,
                photo_rel,
                notes,
                recorded_by,
                now_iso,
                now_iso,
                "[]",
            ),
        )
    rec = get_measurement_by_id(record_id)
    if rec:
        rec["plausibility_warning"] = check_plausibility(pkey, final_val)
    return rec or {"record_id": record_id}


def get_measurement_by_id(record_id: str) -> Optional[Dict[str, Any]]:
    with db.get_conn() as conn:
        cur = conn.cursor()
        db._exec(cur, "SELECT * FROM field_measurements WHERE record_id = ?", (record_id,))
        rows = db._fetchall_dicts(cur)
        return _enrich_measurement_row(rows[0]) if rows else None


def _enrich_measurement_row(row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    for jkey in ("ai_extra_json", "plc_concurrent_json", "edit_history_json"):
        raw = out.get(jkey)
        parsed = None
        if raw:
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = None
        out[jkey.replace("_json", "")] = parsed
    if out.get("photo_rel_path"):
        out["photo_url"] = f"/api/v1/field-data/photos/{out['photo_rel_path']}"
    else:
        out["photo_url"] = None
    return out


def update_measurement(record_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    existing = get_measurement_by_id(record_id)
    if not existing:
        return None

    now_iso = datetime.now(timezone.utc).isoformat()
    history = existing.get("edit_history") or []
    if not isinstance(history, list):
        history = []

    history.append({
        "edited_at": now_iso,
        "prev_manual_value": existing.get("manual_value"),
        "prev_ai_value": existing.get("ai_value"),
        "prev_final_value": existing.get("final_value"),
        "prev_planter_code": existing.get("planter_code"),
        "prev_plant_no": existing.get("plant_no"),
        "prev_notes": existing.get("notes"),
    })

    exp_code = updates.get("experiment_code") or existing["experiment_code"]
    arm = updates.get("fertigation_arm") or existing["fertigation_arm"]
    t_no = updates.get("treatment_no") or existing["treatment_no"]
    r_no = updates.get("replicate_no") or existing["replicate_no"]
    unit_meta = _resolve_unit_metadata(exp_code, arm, t_no, r_no)

    measured_at = (updates.get("measured_at") or existing["measured_at"]).strip()
    dat = updates.get("dat") if updates.get("dat") is not None else compute_dat(measured_at, get_transplant_date())
    plant_no = str(updates.get("plant_no") if updates.get("plant_no") is not None else existing["plant_no"]).strip()
    truss_no = int(updates["truss_no"]) if updates.get("truss_no") not in (None, "") else existing.get("truss_no")

    pkey = str(updates.get("parameter_key") or existing["parameter_key"]).strip()
    pdef = PARAM_MAP.get(pkey, {})
    plabel = str(updates.get("parameter_label") or pdef.get("label_en") or existing["parameter_label"]).strip()
    category = str(updates.get("category") or pdef.get("category") or existing["category"]).strip()
    unit = str(updates.get("unit") or pdef.get("unit") or existing["unit"]).strip()

    manual_val = (
        float(updates["manual_value"])
        if ("manual_value" in updates and updates["manual_value"] not in (None, ""))
        else (None if ("manual_value" in updates and updates["manual_value"] == "") else existing.get("manual_value"))
    )
    ai_val = (
        float(updates["ai_value"])
        if ("ai_value" in updates and updates["ai_value"] not in (None, ""))
        else existing.get("ai_value")
    )
    if "final_value" in updates and updates["final_value"] not in (None, ""):
        final_val = float(updates["final_value"])
        if manual_val is None:
            manual_val = final_val
    elif manual_val is not None:
        final_val = manual_val
    elif ai_val is not None:
        final_val = ai_val
    else:
        final_val = float(existing["final_value"])

    notes = str(updates["notes"]) if "notes" in updates and updates["notes"] is not None else existing.get("notes", "")
    ver_status = str(updates.get("verification_status") or "human_edited")

    with db.get_conn() as conn:
        cur = conn.cursor()
        db._exec(
            cur,
            """
            UPDATE field_measurements
            SET experiment_code = ?, measured_at = ?, dat = ?, fertigation_arm = ?,
                treatment_no = ?, treatment_code = ?, nacl_mm = ?, nahs_um = ?, humic_mll = ?,
                replicate_no = ?, planter_code = ?, plc_zone_id = ?, plc_sensor_id = ?,
                plant_no = ?, truss_no = ?, category = ?, parameter_key = ?, parameter_label = ?, unit = ?,
                manual_value = ?, ai_value = ?, final_value = ?, verification_status = ?,
                notes = ?, updated_at = ?, edit_history_json = ?
            WHERE record_id = ?
            """,
            (
                unit_meta["experiment_code"],
                measured_at,
                dat,
                unit_meta["fertigation_arm"],
                unit_meta["treatment_no"],
                unit_meta["treatment_code"],
                unit_meta["nacl_mm"],
                unit_meta["nahs_um"],
                unit_meta["humic_mll"],
                unit_meta["replicate_no"],
                unit_meta["planter_code"],
                unit_meta["plc_zone_id"],
                unit_meta["plc_sensor_id"],
                plant_no,
                truss_no,
                category,
                pkey,
                plabel,
                unit,
                manual_val,
                ai_val,
                final_val,
                ver_status,
                notes,
                now_iso,
                json.dumps(history),
                record_id,
            ),
        )
    return get_measurement_by_id(record_id)


def delete_measurement(record_id: str) -> bool:
    with db.get_conn() as conn:
        cur = conn.cursor()
        db._exec(cur, "DELETE FROM field_measurements WHERE record_id = ?", (record_id,))
        return cur.rowcount > 0


def query_measurements(
    experiment_code: Optional[str] = None,
    fertigation_arm: Optional[str] = None,
    treatment_no: Optional[str] = None,
    replicate_no: Optional[str] = None,
    plant_no: Optional[str] = None,
    category: Optional[str] = None,
    parameter_key: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    dat_min: Optional[int] = None,
    dat_max: Optional[int] = None,
    search: Optional[str] = None,
    limit: int = 1000,
) -> List[Dict[str, Any]]:
    clauses: List[str] = []
    params: List[Any] = []

    if experiment_code and experiment_code != "ALL":
        clauses.append("experiment_code = ?")
        params.append(experiment_code.upper().strip())
    if fertigation_arm and fertigation_arm != "ALL":
        clauses.append("fertigation_arm = ?")
        params.append(fertigation_arm.strip())
    if treatment_no and treatment_no != "ALL":
        t_list = [x.strip().upper() for x in treatment_no.split(",") if x.strip()]
        if len(t_list) == 1:
            clauses.append("treatment_no = ?")
            params.append(t_list[0])
        elif t_list:
            placeholders = ",".join(["?"] * len(t_list))
            clauses.append(f"treatment_no IN ({placeholders})")
            params.extend(t_list)
    if replicate_no and replicate_no != "ALL":
        clauses.append("replicate_no = ?")
        params.append(replicate_no.upper().strip())
    if plant_no and plant_no != "ALL":
        clauses.append("plant_no = ?")
        params.append(plant_no.strip())
    if category and category != "ALL":
        clauses.append("category = ?")
        params.append(category.strip())
    if parameter_key and parameter_key != "ALL":
        p_list = [x.strip() for x in parameter_key.split(",") if x.strip()]
        if len(p_list) == 1:
            clauses.append("parameter_key = ?")
            params.append(p_list[0])
        elif p_list:
            placeholders = ",".join(["?"] * len(p_list))
            clauses.append(f"parameter_key IN ({placeholders})")
            params.extend(p_list)
    if start_date:
        clauses.append("measured_at >= ?")
        params.append(start_date.strip())
    if end_date:
        e_val = end_date.strip()
        if len(e_val) == 10:
            e_val = e_val + "T23:59:59"
        clauses.append("measured_at <= ?")
        params.append(e_val)
    if dat_min is not None:
        clauses.append("dat >= ?")
        params.append(int(dat_min))
    if dat_max is not None:
        clauses.append("dat <= ?")
        params.append(int(dat_max))
    if search and search.strip():
        q = f"%{search.strip()}%"
        clauses.append("(planter_code LIKE ? OR parameter_label LIKE ? OR notes LIKE ? OR treatment_code LIKE ?)")
        params.extend([q, q, q, q])

    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT * FROM field_measurements {where_sql} ORDER BY measured_at DESC, created_at DESC LIMIT ?"
    params.append(max(1, min(int(limit), 20000)))

    with db.get_conn() as conn:
        cur = conn.cursor()
        db._exec(cur, sql, tuple(params))
        return [_enrich_measurement_row(r) for r in db._fetchall_dicts(cur)]


def compute_summary_statistics(rows: List[Dict[str, Any]], experiment_code: str = "EXP2") -> Dict[str, Any]:
    """
    Computes publication-ready Mean, SD, SE, Min, Max, N, % vs Control (T1 / T5),
    and 64-Planter Completeness Matrix for the Dashboard & Bilingual A4 Professor Print Studio.
    """
    grouped: Dict[Tuple[str, str, str], List[float]] = {}
    rep_values: Dict[Tuple[str, str, str], Dict[str, List[float]]] = {}
    param_meta_seen: Dict[str, Dict[str, str]] = {}
    planters_measured = set()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_planters = set()

    for r in rows:
        pkey = r["parameter_key"]
        arm = r["fertigation_arm"]
        t_no = r["treatment_no"]
        rep = r["replicate_no"]
        val = r.get("final_value")
        if val is None:
            continue
        fval = float(val)
        param_meta_seen[pkey] = {
            "parameter_key": pkey,
            "parameter_label": r["parameter_label"],
            "label_tr": PARAM_MAP.get(pkey, {}).get("label_tr", r["parameter_label"]),
            "unit": r["unit"],
            "category": r["category"],
        }
        gkey = (pkey, arm, t_no)
        grouped.setdefault(gkey, []).append(fval)
        rep_values.setdefault(gkey, {}).setdefault(rep, []).append(fval)
        planters_measured.add(r["planter_code"])
        if str(r.get("measured_at", ""))[:10] == today_str:
            today_planters.add(r["planter_code"])

    def _stats(vals: List[float]) -> Dict[str, Optional[float]]:
        n = len(vals)
        if n == 0:
            return {"n": 0, "mean": None, "sd": None, "se": None, "min": None, "max": None}
        mean = sum(vals) / n
        if n > 1:
            var = sum((x - mean) ** 2 for x in vals) / (n - 1)
            sd = math.sqrt(var)
            se = sd / math.sqrt(n)
        else:
            sd = 0.0
            se = 0.0
        return {
            "n": n,
            "mean": round(mean, 3),
            "sd": round(sd, 3),
            "se": round(se, 3),
            "min": round(min(vals), 3),
            "max": round(max(vals), 3),
        }

    # Baselines (T1 for 0 mM NaCl, T5 for 80 mM NaCl) per parameter & arm
    summary_rows: List[Dict[str, Any]] = []
    t_sort_order = [f"T{i}" for i in range(1, 28)]

    for pkey, pinfo in param_meta_seen.items():
        for arm in ("IoT", "Manual", "EXP1"):
            ctrl_0 = _stats(grouped.get((pkey, arm, "T1"), []))["mean"]
            ctrl_salt = _stats(grouped.get((pkey, arm, "T5"), []))["mean"]
            for t_no in t_sort_order:
                vals = grouped.get((pkey, arm, t_no))
                if not vals:
                    continue
                st = _stats(vals)
                t_def = (EXP1_TREATMENTS if experiment_code == "EXP1" else EXP2_TREATMENTS).get(t_no, {})
                pct_vs_t1 = round(((st["mean"] - ctrl_0) / ctrl_0) * 100.0, 1) if (ctrl_0 and st["mean"] is not None) else None
                pct_vs_t5 = round(((st["mean"] - ctrl_salt) / ctrl_salt) * 100.0, 1) if (ctrl_salt and st["mean"] is not None and t_def.get("nacl_mm", 0) > 0) else None
                reps_map = {
                    rk: round(sum(rv) / len(rv), 3)
                    for rk, rv in sorted(rep_values.get((pkey, arm, t_no), {}).items())
                }
                summary_rows.append({
                    **pinfo,
                    "fertigation_arm": arm,
                    "treatment_no": t_no,
                    "treatment_code": t_def.get("code_manual" if arm == "Manual" else "code_iot", t_no),
                    "nacl_mm": t_def.get("nacl_mm", 0.0),
                    "nahs_um": t_def.get("nahs_um", 0.0),
                    "humic_mll": t_def.get("humic_mll", 0.0),
                    **st,
                    "pct_vs_t1_ctrl": pct_vs_t1,
                    "pct_vs_t5_salt_ctrl": pct_vs_t5,
                    "rep_means": reps_map,
                })

    return {
        "total_records": len(rows),
        "parameters_count": len(param_meta_seen),
        "unique_planters_measured": sorted(planters_measured),
        "today_planters_measured": sorted(today_planters),
        "summary_rows": summary_rows,
    }


# ==============================================================================
# Batch & Individual Treatment Applications
# ==============================================================================


def add_treatment_batch(payload: Dict[str, Any]) -> Dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    applied_at = (payload.get("applied_at") or "").strip() or now_iso
    exp_code = (payload.get("experiment_code") or "EXP2").upper().strip()
    dat = payload.get("dat") if payload.get("dat") is not None else compute_dat(applied_at, get_transplant_date())

    arms = payload.get("target_arms") or ["IoT"]
    if isinstance(arms, str):
        arms = [x.strip() for x in arms.split(",") if x.strip()]
    treatments = payload.get("target_treatments") or ["T1"]
    if isinstance(treatments, str):
        treatments = [x.strip().upper() for x in treatments.split(",") if x.strip()]
    replicates = payload.get("target_replicates") or ["R1", "R2", "R3", "R4"]
    if isinstance(replicates, str):
        replicates = [x.strip().upper() for x in replicates.split(",") if x.strip()]

    affected_count = max(1, len(arms) * len(treatments) * len(replicates))
    scope_type = str(payload.get("scope_type") or ("single_planter" if affected_count == 1 else "group"))
    group_label = str(payload.get("group_label") or f"{','.join(arms)} x {','.join(treatments)} ({affected_count} planters)")

    app_type = str(payload.get("application_type") or "nahs_humic_pulse")
    nahs_um = float(payload.get("nahs_um") or 0.0)
    nahs_stock = float(payload["nahs_stock_mg_100ml"]) if payload.get("nahs_stock_mg_100ml") not in (None, "") else None
    humic_mll = float(payload.get("humic_mll") or 0.0)
    humic_prod = str(payload.get("humic_product") or "LIQHUMUS Liquid 18 (NK)")
    nacl_mm = float(payload.get("nacl_mm") or 0.0)
    nut_stage = str(payload.get("nutrient_stage") or "") or None
    vol_planter = float(payload["volume_per_planter_l"]) if payload.get("volume_per_planter_l") not in (None, "") else None
    tot_vol = (
        float(payload["total_volume_l"])
        if payload.get("total_volume_l") not in (None, "")
        else (round(vol_planter * affected_count, 2) if vol_planter is not None else None)
    )
    sol_ec = int(float(payload["solution_ec_uscm"])) if payload.get("solution_ec_uscm") not in (None, "") else None
    sol_ph = float(payload["solution_ph"]) if payload.get("solution_ph") not in (None, "") else None
    hrs_after = float(payload["hours_after_morning_irrig"]) if payload.get("hours_after_morning_irrig") not in (None, "") else None
    photo_rel = str(payload.get("photo_rel_path") or "").strip() or None
    notes = str(payload.get("notes") or "").strip()
    recorded_by = str(payload.get("recorded_by") or "Mamunur Reza").strip()
    batch_id = str(uuid.uuid4())

    with db.get_conn() as conn:
        cur = conn.cursor()
        db._exec(
            cur,
            """
            INSERT INTO field_treatment_batches (
                batch_app_id, experiment_code, applied_at, dat, scope_type, group_label,
                target_arms_json, target_treatments_json, target_replicates_json,
                affected_planters_count, application_type, nahs_um, nahs_stock_mg_100ml,
                humic_mll, humic_product, nacl_mm, nutrient_stage,
                volume_per_planter_l, total_volume_l, solution_ec_uscm, solution_ph,
                hours_after_morning_irrig, photo_rel_path, notes, recorded_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_id,
                exp_code,
                applied_at,
                dat,
                scope_type,
                group_label,
                json.dumps(arms),
                json.dumps(treatments),
                json.dumps(replicates),
                affected_count,
                app_type,
                nahs_um,
                nahs_stock,
                humic_mll,
                humic_prod,
                nacl_mm,
                nut_stage,
                vol_planter,
                tot_vol,
                sol_ec,
                sol_ph,
                hrs_after,
                photo_rel,
                notes,
                recorded_by,
                now_iso,
                now_iso,
            ),
        )

    # Also mirror IoT zone treatments into existing treatment_applications so /stress charts show pins automatically
    if exp_code == "EXP2" and "IoT" in arms and payload.get("sync_to_stress_studio", True):
        for t_no in treatments:
            t_info = EXP2_TREATMENTS.get(t_no)
            if t_info and t_info.get("zone_id"):
                try:
                    db.add_treatment_application({
                        "applied_at": applied_at,
                        "dat": dat,
                        "zone_id": t_info["zone_id"],
                        "target_scope": "zone",
                        "treatment_code": t_info["code_iot"],
                        "h2s_applied": nahs_um > 0,
                        "h2s_dose_um": nahs_um,
                        "h2s_solution_vol_l": vol_planter or 0.0,
                        "humic_applied": humic_mll > 0,
                        "humic_product": humic_prod,
                        "humic_dose_mll": humic_mll,
                        "salt_applied": nacl_mm > 0,
                        "nacl_dose_mm": nacl_mm,
                        "supplied_solution_ec_uscm": sol_ec,
                        "supplied_solution_ph": sol_ph,
                        "notes": f"[{app_type}] {notes}".strip(),
                        "recorded_by": recorded_by,
                    })
                except Exception:
                    pass

    return get_treatment_batch_by_id(batch_id) or {"batch_app_id": batch_id}


def _enrich_treatment_row(row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    for k in ("target_arms_json", "target_treatments_json", "target_replicates_json"):
        try:
            out[k.replace("_json", "")] = json.loads(out.get(k) or "[]")
        except Exception:
            out[k.replace("_json", "")] = []
    out["photo_url"] = f"/api/v1/field-data/photos/{out['photo_rel_path']}" if out.get("photo_rel_path") else None
    return out


def get_treatment_batch_by_id(batch_id: str) -> Optional[Dict[str, Any]]:
    with db.get_conn() as conn:
        cur = conn.cursor()
        db._exec(cur, "SELECT * FROM field_treatment_batches WHERE batch_app_id = ?", (batch_id,))
        rows = db._fetchall_dicts(cur)
        return _enrich_treatment_row(rows[0]) if rows else None


def list_treatment_batches(
    experiment_code: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    clauses: List[str] = []
    params: List[Any] = []
    if experiment_code and experiment_code != "ALL":
        clauses.append("experiment_code = ?")
        params.append(experiment_code.upper().strip())
    if start_date:
        clauses.append("applied_at >= ?")
        params.append(start_date.strip())
    if end_date:
        e_val = end_date.strip()
        if len(e_val) == 10:
            e_val = e_val + "T23:59:59"
        clauses.append("applied_at <= ?")
        params.append(e_val)
    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(max(1, min(int(limit), 5000)))
    with db.get_conn() as conn:
        cur = conn.cursor()
        db._exec(cur, f"SELECT * FROM field_treatment_batches {where_sql} ORDER BY applied_at DESC LIMIT ?", tuple(params))
        return [_enrich_treatment_row(r) for r in db._fetchall_dicts(cur)]


def delete_treatment_batch(batch_id: str) -> bool:
    with db.get_conn() as conn:
        cur = conn.cursor()
        db._exec(cur, "DELETE FROM field_treatment_batches WHERE batch_app_id = ?", (batch_id,))
        return cur.rowcount > 0


# ==============================================================================
# HOBO Environmental Data Logger Uploads & VPD Time-Series
# ==============================================================================


def store_env_logger_dataset(
    filename: str,
    logger_type: str,
    location_tag: str,
    parsed_rows: List[Dict[str, Any]],
    experiment_code: str = "EXP2",
    notes: str = "",
    uploaded_by: str = "Mamunur Reza",
) -> Dict[str, Any]:
    upload_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()
    inserted = 0
    skipped = 0
    times: List[str] = []

    with db.get_conn() as conn:
        cur = conn.cursor()
        for r in parsed_rows:
            rec_at = str(r.get("recorded_at") or "").strip()
            if not rec_at:
                continue
            t_c = r.get("air_temp_c")
            rh = r.get("rh_pct")
            lux = r.get("light_lux")
            if t_c is None and rh is None and lux is None:
                continue
            ppfd = round(float(lux) * 0.0185, 2) if lux is not None else None
            vpd_info = compute_vpd_and_dewpoint(temp_c=t_c, rh_pct=rh) if (t_c is not None and rh is not None) else {}
            vpd_kpa = vpd_info.get("vpd_kpa")
            dew_c = vpd_info.get("dew_point_c")

            if db.IS_POSTGRES:
                cur.execute(
                    """
                    INSERT INTO env_logger_readings (
                        upload_id, experiment_code, location_tag, logger_type,
                        recorded_at, air_temp_c, rh_pct, light_lux,
                        estimated_ppfd_umol, vpd_kpa, dew_point_c
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (location_tag, logger_type, recorded_at) DO NOTHING
                    """,
                    (upload_id, experiment_code, location_tag, logger_type, rec_at, t_c, rh, lux, ppfd, vpd_kpa, dew_c),
                )
            else:
                cur.execute(
                    """
                    INSERT OR IGNORE INTO env_logger_readings (
                        upload_id, experiment_code, location_tag, logger_type,
                        recorded_at, air_temp_c, rh_pct, light_lux,
                        estimated_ppfd_umol, vpd_kpa, dew_point_c
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (upload_id, experiment_code, location_tag, logger_type, rec_at, t_c, rh, lux, ppfd, vpd_kpa, dew_c),
                )
            if cur.rowcount > 0:
                inserted += 1
                times.append(rec_at)
            else:
                skipped += 1

        start_t = min(times) if times else None
        end_t = max(times) if times else None
        db._exec(
            cur,
            """
            INSERT INTO env_logger_uploads (
                upload_id, uploaded_at, experiment_code, logger_type, location_tag,
                filename, rows_parsed, rows_inserted, rows_skipped_duplicate,
                start_time, end_time, notes, uploaded_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                upload_id,
                now_iso,
                experiment_code,
                logger_type,
                location_tag,
                filename,
                len(parsed_rows),
                inserted,
                skipped,
                start_t,
                end_t,
                notes,
                uploaded_by,
            ),
        )

    return {
        "upload_id": upload_id,
        "filename": filename,
        "logger_type": logger_type,
        "location_tag": location_tag,
        "rows_parsed": len(parsed_rows),
        "rows_inserted": inserted,
        "rows_skipped_duplicate": skipped,
        "start_time": start_t,
        "end_time": end_t,
    }


def get_env_climate_summary(
    location_tag: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 1500,
) -> Dict[str, Any]:
    clauses: List[str] = []
    params: List[Any] = []
    if location_tag and location_tag != "ALL":
        clauses.append("location_tag = ?")
        params.append(location_tag.strip())
    if start_date:
        clauses.append("recorded_at >= ?")
        params.append(start_date.strip())
    if end_date:
        e_val = end_date.strip()
        if len(e_val) == 10:
            e_val = e_val + "T23:59:59"
        clauses.append("recorded_at <= ?")
        params.append(e_val)
    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(max(1, min(int(limit), 20000)))

    with db.get_conn() as conn:
        cur = conn.cursor()
        db._exec(
            cur,
            f"SELECT * FROM env_logger_readings {where_sql} ORDER BY recorded_at DESC LIMIT ?",
            tuple(params),
        )
        readings = db._fetchall_dicts(cur)

        db._exec(cur, "SELECT * FROM env_logger_uploads ORDER BY uploaded_at DESC LIMIT 50")
        uploads = db._fetchall_dicts(cur)

    by_loc: Dict[str, Dict[str, List[float]]] = {}
    for r in readings:
        loc = r["location_tag"]
        bucket = by_loc.setdefault(loc, {"temp": [], "rh": [], "lux": [], "vpd": []})
        if r.get("air_temp_c") is not None:
            bucket["temp"].append(float(r["air_temp_c"]))
        if r.get("rh_pct") is not None:
            bucket["rh"].append(float(r["rh_pct"]))
        if r.get("light_lux") is not None:
            bucket["lux"].append(float(r["light_lux"]))
        if r.get("vpd_kpa") is not None:
            bucket["vpd"].append(float(r["vpd_kpa"]))

    loc_stats: List[Dict[str, Any]] = []
    for loc, b in sorted(by_loc.items()):
        loc_stats.append({
            "location_tag": loc,
            "samples": max(len(b["temp"]), len(b["rh"]), len(b["lux"])),
            "mean_temp_c": round(sum(b["temp"]) / len(b["temp"]), 2) if b["temp"] else None,
            "min_temp_c": round(min(b["temp"]), 2) if b["temp"] else None,
            "max_temp_c": round(max(b["temp"]), 2) if b["temp"] else None,
            "mean_rh_pct": round(sum(b["rh"]) / len(b["rh"]), 1) if b["rh"] else None,
            "mean_light_lux": round(sum(b["lux"]) / len(b["lux"]), 0) if b["lux"] else None,
            "max_light_lux": round(max(b["lux"]), 0) if b["lux"] else None,
            "mean_vpd_kpa": round(sum(b["vpd"]) / len(b["vpd"]), 3) if b["vpd"] else None,
        })

    return {
        "location_stats": loc_stats,
        "recent_uploads": uploads,
        "readings": readings[:500],
        "total_readings_returned": len(readings),
    }


# ==============================================================================
# PIN-Protected AI Vision Provider Settings
# ==============================================================================


def get_ai_settings(include_secrets: bool = False) -> Dict[str, Any]:
    with db.get_conn() as conn:
        cur = conn.cursor()
        db._exec(cur, "SELECT * FROM field_ai_settings WHERE id = 1")
        rows = db._fetchall_dicts(cur)
        row = rows[0] if rows else {
            "provider": "openrouter",
            "openrouter_api_key": None,
            "gemini_api_key": None,
            "primary_model": "google/gemini-2.5-flash",
            "secondary_model": "openai/gpt-4o-mini",
            "dual_verify_enabled": 1,
        }

    or_key = row.get("openrouter_api_key") or ""
    gem_key = row.get("gemini_api_key") or ""
    out = {
        "provider": row.get("provider") or "openrouter",
        "primary_model": row.get("primary_model") or "google/gemini-2.5-flash",
        "secondary_model": row.get("secondary_model") or "openai/gpt-4o-mini",
        "dual_verify_enabled": bool(row.get("dual_verify_enabled", 1)),
        "has_openrouter_key": bool(or_key.strip()),
        "has_gemini_key": bool(gem_key.strip()),
        "openrouter_key_masked": (or_key[:9] + "..." + or_key[-4:]) if len(or_key) > 14 else ("Configured" if or_key else ""),
        "gemini_key_masked": (gem_key[:6] + "..." + gem_key[-4:]) if len(gem_key) > 12 else ("Configured" if gem_key else ""),
        "updated_at": row.get("updated_at"),
    }
    if include_secrets:
        out["openrouter_api_key"] = or_key
        out["gemini_api_key"] = gem_key
    return out


def update_ai_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    cur_cfg = get_ai_settings(include_secrets=True)
    now_iso = datetime.now(timezone.utc).isoformat()

    provider = str(payload.get("provider") or cur_cfg["provider"]).strip().lower()
    primary_model = str(payload.get("primary_model") or cur_cfg["primary_model"]).strip()
    secondary_model = str(payload.get("secondary_model") or cur_cfg["secondary_model"]).strip()
    dual_verify = 1 if payload.get("dual_verify_enabled", cur_cfg["dual_verify_enabled"]) else 0

    or_key = cur_cfg["openrouter_api_key"]
    if "openrouter_api_key" in payload and payload["openrouter_api_key"] is not None:
        raw_or = str(payload["openrouter_api_key"]).strip()
        if raw_or == "CLEAR":
            or_key = ""
        elif raw_or and "..." not in raw_or:
            or_key = raw_or

    gem_key = cur_cfg["gemini_api_key"]
    if "gemini_api_key" in payload and payload["gemini_api_key"] is not None:
        raw_gem = str(payload["gemini_api_key"]).strip()
        if raw_gem == "CLEAR":
            gem_key = ""
        elif raw_gem and "..." not in raw_gem:
            gem_key = raw_gem

    with db.get_conn() as conn:
        cur = conn.cursor()
        db._exec(
            cur,
            """
            UPDATE field_ai_settings
            SET provider = ?, openrouter_api_key = ?, gemini_api_key = ?,
                primary_model = ?, secondary_model = ?, dual_verify_enabled = ?, updated_at = ?
            WHERE id = 1
            """,
            (provider, or_key, gem_key, primary_model, secondary_model, dual_verify, now_iso),
        )
    return get_ai_settings(include_secrets=False)
