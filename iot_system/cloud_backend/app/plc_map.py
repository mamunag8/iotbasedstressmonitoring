"""
Exact Hardware, Modbus Register Map, PLC Ladder Rules & Diagnostics for Ataturk University
Ziraat Fakultesi Otomatik Sulama Sistemi
PLC: GMTCNT GLC-196R (192.168.1.240:502, Unit ID 1) + GXM-88R + GXM-40U
HMI: GMTCNT 070E (1024x600)
Derived directly from reverse-engineering PLC(196R).gpf and PLC(196R).gpf.csv
"""

from typing import Any, Dict, List, Optional, TypedDict


class SensorAddressEntry(TypedDict):
    sensor_id: int
    zone_id: int
    soil_name: str
    leaf_name: str
    soil_slave_id: int       # RS485 COM2 Slave ID (1..24)
    leaf_slave_id: int       # RS485 COM2 Slave ID (101..124)
    humidity_reg: int        # 4X 32-bit IEEE-754 float (2 registers)
    temp_reg: int            # 4X 32-bit IEEE-754 float (2 registers)
    leaf_humidity_reg: int   # 4X 32-bit IEEE-754 float (2 registers)
    leaf_temp_reg: int       # 4X 32-bit IEEE-754 float (2 registers)
    ec_reg: int              # 4X 16-bit unsigned integer (1 register)
    salt_reg: int            # 4X 16-bit unsigned integer (1 register)
    ph_reg: Optional[int]    # None in PLC(196R).gpf (not configured in COM2 RS485 table yet)


class ZoneDefinition(TypedDict):
    zone_id: int
    name_tr: str
    name_en: str
    valve_tag: str
    valve_coil: int          # 0X Coil address for Auto/Manual Mode switch (vana1..vana8: 0X:1..8)
    valve_manual_coil: int   # 0X Coil address for Physical Solenoid Valve (0X:9..16 -> QP[0,1,23,22,2,3,4,5])
    qp_index: int            # Physical QP array index inside GLC-196R + GXM-88R (0, 1, 23, 22, 2, 3, 4, 5)
    relay_tag: str           # Physical relay output in PLC(196R).gpf (dc1, dc2, dc14, dc13, dc3, dc4, dc5, dc6)
    plc_terminal: str        # Physical hardware terminal on GLC-196R / GXM-88R
    sensor_ids: List[int]    # 3 Soil + 3 Leaf sensors averaged per zone
    sum_tag_1: str           # First intermediate sum tag in AnaProgram
    sum_tag_2: str           # Three-sensor sum tag in AnaProgram
    avg_tag: str             # Final zone moisture average tag (sum / 3.0)
    default_min_moisture: float
    default_max_moisture: float


# Exact EC & Salinity 16-bit Holding Register (4X) addresses from PLC(196R).gpf.csv
EC_REGISTERS: Dict[int, int] = {
    1: 3,   2: 7,   3: 81,  4: 80,  5: 79,  6: 78,
    7: 77,  8: 76,  9: 75,  10: 96, 11: 95, 12: 94,
    13: 93, 14: 91, 15: 92, 16: 90, 17: 89, 18: 88,
    19: 87, 20: 86, 21: 85, 22: 84, 23: 83, 24: 82,
}

SALT_REGISTERS: Dict[int, int] = {
    1: 4,   2: 8,   3: 37,  4: 36,  5: 35,  6: 34,
    7: 33,  8: 32,  9: 31,  10: 52, 11: 51, 12: 50,
    13: 49, 14: 48, 15: 47, 16: 46, 17: 45, 18: 44,
    19: 43, 20: 42, 21: 41, 22: 40, 23: 39, 24: 38,
}

# In PLC(196R).gpf, Soil pH (register 40005 on RS485 sensor) is NOT polled in COM2 and has no 4X register assigned.
PH_REGISTERS: Dict[int, Optional[int]] = {n: None for n in range(1, 25)}

# Hardware Water Flow Meter & Solenoid Valve Specifications (Verified from Greenhouse Photos 2026-11-03)
# Photo: D:\PhD at Ataturk\PhD Thesis\2nd Research data\photos\WhatsApp Image 2026-11-03 at 10.02.41 AM.jpeg
FLOW_METER_SPEC: Dict[str, Any] = {
    "model": "YF-S201",
    "sensor_type": "Hall-Effect Turbine Water Flow Sensor (3-Wire: Red=5-24VDC, Black=GND, Yellow=Pulse Output)",
    "working_range_lpm": "1-30 L/min",
    "max_water_pressure_mpa": 1.75,
    "k_factor_pulses_per_liter": 450,
    "physical_position": "Mounted inline on each drip line directly BEFORE (below/upstream of) the Solenoid Valve",
    "solenoid_valve_model": "hexa CONTROLS AC 230V IP54 NC (Normally Closed)",
    "drippers_per_line": 8,
    "dripper_flow_lph": 4.0,
    "max_line_flow_lph": 32.0,
    "emitter_spec": "8 pcs × 4 L/h drippers running together from a single valve = Max 32 L/h per line (0.533 L/min)",
    "plc_connection_status": "Pending physical DI wiring to GLC-196R / GXM-88R (Pre-mapped to 4X:2201..2232; Auto-calculated from Valve ON duration × 32 L/h [8 × 4 L/h drippers] while disconnected)",
    "default_nominal_flow_lph": 32.0,
    "default_nominal_flow_lpm": 0.5333,
}

# Exact 8 Irrigation Zones decoded from PLC(196R).gpf AnaProgram ladder logic
# Note: vana6 is at Coil 7 and vana7 is at Coil 6 per PLC(196R).gpf.csv
ZONES: Dict[int, ZoneDefinition] = {
    1: {
        "zone_id": 1,
        "name_tr": "Bölge 1 (Parsel 1-9-17)",
        "name_en": "Zone 1 (Plots 1-9-17)",
        "valve_tag": "vana1",
        "valve_coil": 1,
        "valve_manual_coil": 9,
        "qp_index": 0,
        "relay_tag": "dc1",
        "plc_terminal": "GLC-196R CPU QP0 (Physical Valve 1)",
        "sensor_ids": [1, 9, 17],
        "sum_tag_1": "ortlama_1_9",
        "sum_tag_2": "ortlama_1_9_17",
        "avg_tag": "son_ortlama_1_9_17",
        "default_min_moisture": 45.0,
        "default_max_moisture": 80.0,
    },
    2: {
        "zone_id": 2,
        "name_tr": "Bölge 2 (Parsel 2-10-18)",
        "name_en": "Zone 2 (Plots 2-10-18)",
        "valve_tag": "vana2",
        "valve_coil": 2,
        "valve_manual_coil": 10,
        "qp_index": 1,
        "relay_tag": "dc2",
        "plc_terminal": "GLC-196R CPU QP1 (Physical Valve 2)",
        "sensor_ids": [2, 10, 18],
        "sum_tag_1": "ortlama_2_10",
        "sum_tag_2": "ortlama_2_10_18",
        "avg_tag": "son_ortlama_2_10_18",
        "default_min_moisture": 45.0,
        "default_max_moisture": 80.0,
    },
    3: {
        "zone_id": 3,
        "name_tr": "Bölge 3 (Parsel 3-11-19)",
        "name_en": "Zone 3 (Plots 3-11-19)",
        "valve_tag": "vana3",
        "valve_coil": 3,
        "valve_manual_coil": 11,
        "qp_index": 23,
        "relay_tag": "dc14",
        "plc_terminal": "GXM-88R Exp01_QP7 (Physical Valve 3)",
        "sensor_ids": [3, 11, 19],
        "sum_tag_1": "ortlama_3_11",
        "sum_tag_2": "ortlama_3_11_19",
        "avg_tag": "son_ortlama_3_11_19",
        "default_min_moisture": 45.0,
        "default_max_moisture": 80.0,
    },
    4: {
        "zone_id": 4,
        "name_tr": "Bölge 4 (Parsel 4-12-20)",
        "name_en": "Zone 4 (Plots 4-12-20)",
        "valve_tag": "vana4",
        "valve_coil": 4,
        "valve_manual_coil": 12,
        "qp_index": 22,
        "relay_tag": "dc13",
        "plc_terminal": "GXM-88R Exp01_QP6 (Physical Valve 4)",
        "sensor_ids": [4, 12, 20],
        "sum_tag_1": "ortlama_4_12",
        "sum_tag_2": "ortlama_4_12_20",
        "avg_tag": "son_ortlama_4_12_20",
        "default_min_moisture": 45.0,
        "default_max_moisture": 80.0,
    },
    5: {
        "zone_id": 5,
        "name_tr": "Bölge 5 (Parsel 5-13-21)",
        "name_en": "Zone 5 (Plots 5-13-21)",
        "valve_tag": "vana5",
        "valve_coil": 5,
        "valve_manual_coil": 13,
        "qp_index": 2,
        "relay_tag": "dc3",
        "plc_terminal": "GLC-196R CPU QP2 (Physical Valve 5)",
        "sensor_ids": [5, 13, 21],
        "sum_tag_1": "ortlama_5_13",
        "sum_tag_2": "ortlama_5_13_21",
        "avg_tag": "son_ortlama_5_13_21",
        "default_min_moisture": 45.0,
        "default_max_moisture": 80.0,
    },
    6: {
        "zone_id": 6,
        "name_tr": "Bölge 6 (Parsel 6-14-22)",
        "name_en": "Zone 6 (Plots 6-14-22)",
        "valve_tag": "vana6",
        "valve_coil": 7,  # Mapped to Coil 7 in PLC(196R).gpf.csv
        "valve_manual_coil": 14,
        "qp_index": 3,
        "relay_tag": "dc4",
        "plc_terminal": "GLC-196R CPU QP3 (Physical Valve 6)",
        "sensor_ids": [6, 14, 22],
        "sum_tag_1": "ortlama_6_14",
        "sum_tag_2": "ortlama_6_14_22",
        "avg_tag": "son_ortlama_6_14_22",
        "default_min_moisture": 45.0,
        "default_max_moisture": 80.0,
    },
    7: {
        "zone_id": 7,
        "name_tr": "Bölge 7 (Parsel 7-15-23)",
        "name_en": "Zone 7 (Plots 7-15-23)",
        "valve_tag": "vana7",
        "valve_coil": 6,  # Mapped to Coil 6 in PLC(196R).gpf.csv
        "valve_manual_coil": 15,
        "qp_index": 4,
        "relay_tag": "dc5",
        "plc_terminal": "GLC-196R CPU QP4 (Physical Valve 7)",
        "sensor_ids": [7, 15, 23],
        "sum_tag_1": "ortlama_7_15",
        "sum_tag_2": "ortlama_7_15_23",
        "avg_tag": "son_ortlama_7_15_23",
        "default_min_moisture": 45.0,
        "default_max_moisture": 80.0,
    },
    8: {
        "zone_id": 8,
        "name_tr": "Bölge 8 (Parsel 8-16-24)",
        "name_en": "Zone 8 (Plots 8-16-24)",
        "valve_tag": "vana8",
        "valve_coil": 8,
        "valve_manual_coil": 16,
        "qp_index": 5,
        "relay_tag": "dc6",
        "plc_terminal": "GLC-196R CPU QP5 (Physical Valve 8)",
        "sensor_ids": [8, 16, 24],
        "sum_tag_1": "ortlama_8_16",
        "sum_tag_2": "ortlama_8_16_24",
        "avg_tag": "son_ortlama_8_16_24",
        "default_min_moisture": 45.0,
        "default_max_moisture": 80.0,
    },
}


def get_sensor_zone(sensor_id: int) -> int:
    """Return the irrigation zone (1..8) for sensor R{1..24}: ((sensor_id - 1) % 8) + 1."""
    return ((sensor_id - 1) % 8) + 1


SENSORS: Dict[int, SensorAddressEntry] = {
    n: {
        "sensor_id": n,
        "zone_id": get_sensor_zone(n),
        "soil_name": f"R{n}",
        "leaf_name": f"R{n}_L",
        "soil_slave_id": n,
        "leaf_slave_id": 100 + n,
        "humidity_reg": 2001 + (n - 1) * 8,
        "temp_reg": 2003 + (n - 1) * 8,
        "leaf_humidity_reg": 2005 + (n - 1) * 8,
        "leaf_temp_reg": 2007 + (n - 1) * 8,
        "ec_reg": EC_REGISTERS[n],
        "salt_reg": SALT_REGISTERS[n],
        "ph_reg": PH_REGISTERS[n],
    }
    for n in range(1, 25)
}


PLC_RULES_SPEC: Dict[str, Any] = {
    "program_file": "PLC(196R).gpf",
    "tag_export_file": "PLC(196R).gpf.csv",
    "hmi_file": "070E.opb",
    "main_routine": "AnaProgram",
    "hardware": {
        "cpu_model": "GMTCNT GLC-196R (6 DI / 6 Relay DO, Built-in Ethernet & RS232/RS485)",
        "expansion_slot_1": "GXM-88R (8 Digital Inputs / 8 Relay Outputs: Exp01_QP0..QP7 -> dc7..dc14)",
        "expansion_slot_2": "GXM-40U (4 Universal Analog / PT100 Temperature Inputs, 0.1°C Filter=10)",
        "hmi_model": "GMTCNT 070E (7-inch 1024×600 WSVGA Touchscreen, IP 192.168.1.249)",
        "network_config": {
            "plc_ip": "192.168.1.240",
            "subnet_mask": "255.255.255.0",
            "gateway": "192.168.1.1",
            "mac_address": "00:25:FC:02:4F:B9",
            "modbus_tcp_port": 502,
            "gmtsuite_service_port": 23,
            "plc_slave_id": 1,
        },
        "rs485_com2_bus": {
            "port": "COM2 (RS485 2-Wire Half-Duplex)",
            "protocol": "Modbus RTU Master",
            "baud_rate": 4800,
            "data_bits": 8,
            "parity": "None",
            "stop_bits": 1,
            "word_order": "Little-Endian (CDAB)",
            "timeout_ms": 300,
            "inter_frame_delay_ms": 50,
            "retry_count": 0,
            "total_polling_commands": 147,
            "command_tags": "ps2_0 .. ps2_146 (Error flags: pe2_0 .. pe2_146)",
            "soil_sensor_slaves": "Slave IDs 1..24 (R1..R24) — 4 Registers each: 40001(Moisture), 40002(Temp), 40003(EC), 40004(Salt)",
            "leaf_sensor_slaves": "Slave IDs 101..124 (R1_L..R24_L) — 2 Registers each: 40001(Leaf Wetness), 40002(Leaf Temp)",
        },
    },
    "ladder_rules": [
        {
            "rule_id": "RULE_1_SENSOR_SCALING",
            "title_en": "RS485 Raw Integer to IEEE-754 Float Scaling & Calibration (/ 10.0)",
            "title_tr": "RS485 Ham Veriden IEEE-754 Ondalık Sayıya Dönüşüm ve Kalibrasyon (/ 10.0)",
            "formula": "R{n}_humidity = (R{n}_humidity_co + offset) / 10.0  |  R{n}_temp = R{n}_temp_co / 10.0",
            "details_en": (
                "Each soil sensor (R1..R24) and leaf sensor (R1_L..R24_L) returns 16-bit integer values multiplied by 10 over RS485 COM2. "
                "Inside AnaProgram, the PLC divides R{n}_humidity_co, R{n}_temp_co, R{n}_L_humidity_co, and R{n}_L_temp_co by constant 10 (10c) "
                "using Real Opr / Round instructions to store 32-bit IEEE-754 floats at 4X:2001..2192. "
                "Calibration tags (kalibre, kalibre1, kal, kal1) apply integer offsets (0c, 7c, 12c, 13c, 14c, 16c) before scaling. "
                "Soil EC (R1_ec..R24_ec) and Salinity (R1_salt..R24_salt) are stored directly as 16-bit unsigned integers (4X:3..96)."
            ),
        },
        {
            "rule_id": "RULE_2_ZONE_AVERAGING",
            "title_en": "3-Sensor Spatial Moisture Averaging per Irrigation Zone (/ 3.0)",
            "title_tr": "Her Sulama Bölgesi İçin 3 Sensörlü Toprak Nemi Ortalaması (/ 3.0)",
            "formula": "ortlama_a_b = R{a} + R{b}  ->  ortlama_a_b_c = ortlama_a_b + R{c}  ->  son_ortlama_a_b_c = ortlama_a_b_c / 3.0",
            "details_en": (
                "The 24 experimental plots are grouped into 8 irrigation zones using modulo-8 stride: Zone Z averages sensors R{Z}, R{Z+8}, and R{Z+16}. "
                "In AnaProgram, two sequential ADD blocks compute ortlama_{a}_{b} and ortlama_{a}_{b}_{c}, followed by a DIV block dividing by constant 3 (3c) "
                "to produce the control variable son_ortlama_{a}_{b}_{c}."
            ),
        },
        {
            "rule_id": "RULE_3_HYSTERESIS_VALVE_CONTROL",
            "title_en": "Automatic Hysteresis Solenoid Relay Control (Start < 45.0% -> SET dc, Stop >= 80.0% -> RST dc)",
            "title_tr": "Otomatik Histerezisli Solenoid Röle Kontrolü (Başlat < %45.0 -> SET dc, Durdur >= %80.0 -> RST dc)",
            "formula": "--| vana{Z} |-- [ son_ortlama < 45 ] --> --(S)-- dc{Z}   |   --| vana{Z} |-- [ son_ortlama >= 80 ] --> --(R)-- dc{Z}   |   --|/| vana{Z} |-- --> --(R)-- dc{Z}",
            "details_en": (
                "Decoded directly from PLC(196R).gpf AnaProgram (Y=5596.0..9855.0): Each zone uses vana1..vana8 (0X Coils 1..8) as an enable contact (--| vana{Z} |--). "
                "When vana{Z}=1 and average moisture son_ortlama < 45.0% (Tag 610 = 45), the PLC executes --(S)-- dc{Z} (energizing physical relay QP0..QP5 or Exp01_QP6..QP7). "
                "When vana{Z}=1 and son_ortlama >= 80.0% (Tag 614 = 80), the PLC executes --(R)-- dc{Z} (turning OFF the physical relay), "
                "CRITICAL NOTE: The ladder resets dc{Z} (--(R)-- dc{Z}) at >= 80%, but NEVER resets vana{Z} (--(R)-- vana{Z}), and dc2..dc14 have no Modbus addresses! "
                "Because the HMI screen (HMI0.hmi) and Modbus coil 0X:1..8 read vana{Z} instead of dc{Z}, the HMI button/valve icon stays stuck on ON/Run even when R2, R10, R18 = 100%!"
            ),
        },
    ],
}


PLC_PROBLEMS_REPORT: List[Dict[str, Any]] = [
    {
        "problem_id": "PROB_01_NO_AUTO_OFF_SIGN_AT_100_PCT",
        "severity": "critical",
        "category": "Ladder Logic & HMI Valve Status Bug (All 8 Zones)",
        "location": "PLC(196R).gpf -> AnaProgram (Y=6225.0..6335.0) & HMI0.hmi (0X:1..8 vana1..vana8 vs dc1..dc14)",
        "title_en": "Why Zone 2 (R2, R10, R18 = 100%) & All 8 Zones Do Not Show 'OFF' Automatically When Moisture >= 80%",
        "title_tr": "Bölge 2 (R2, R10, R18 = %100) ve Tüm Bölgelerde Nem >= %80 Olduğunda Neden Otomatik 'OFF / Stop' Görünmüyor?",
        "title_bn": "R2, R10, R18 তিনটিই ১০০% হওয়ার পরও কেন স্বয়ংক্রিয়ভাবে 'OFF' সাইন দেখায় না (PLC Ladder ও HMI বাগ)",
        "title_ar": "لماذا لا تظهر علامة الإيقاف التلقائي (OFF) عندما تصل حساسات المنطقة 2 (R2, R10, R18) إلى 100%؟",
        "symptom_en": (
            "When Zone 2 sensors R2, R10, and R18 all reach 100% moisture (average son_ortlama_2_10_18 = 100.0% >= 80.0%), "
            "the physical relay dc2 (QP1) turns OFF, but the HMI touchscreen and Modbus coil status stay on 'ON / Run' (Green Valve) "
            "and never show the 'OFF / Stop' sign automatically. The exact same issue affects all 8 zones (vana1..vana8)."
        ),
        "root_cause_en": (
            "Binary decoding of PLC(196R).gpf (AnaProgram at Y=6036.0, Y=6225.0, Y=6335.0, Y=9195.0) and HMI0.hmi revealed two linked bugs:\n"
            "1. In PLC(196R).gpf Ladder Rung Y=6335.0: `--| vana2 |-- [ son_ortlama_2_10_18 >= 80 ] --> --(R)-- dc2`. "
            "When moisture reaches >= 80% (e.g., 100%), the PLC resets the physical relay output `dc2` (`--(R)-- dc2`), "
            "but it NEVER resets the control coil `vana2` (`--(R)-- vana2`)!\n"
            "2. In HMI0.hmi and PLC(196R).gpf.csv: Both the HMI 'Run/Stop' button and the Red/Green Valve icon are bound to Modbus Coil `0X:2` (`vana2`), NOT `dc2`. "
            "Furthermore, `dc2, dc3, dc4, dc5, dc6, dc13, dc14` have NO Modbus addresses enabled (`ff ff ff ff`) in PLC(196R).gpf! "
            "Because `vana2` stays `1` (`ON`), the screen never shows the `OFF` sign automatically."
        ),
        "fix_steps_en": (
            "1. Web SCADA & Edge Agent Fix (Already Applied Here): Our Web Dashboard and Edge Agent now evaluate `[son_ortlama >= 80%] -> Relay dc OFF` "
            "to immediately display `🛑 AUTO-OFF (≥80% -> dc2 OFF)` on the Zone card, and our Edge Agent automatically sends a Modbus reset (`vana2 = 0`) when moisture >= 80%.\n"
            "2. Permanent PLC Ladder Fix in GMTSuite (`PLC(196R).gpf` -> `AnaProgram`): On the `[ son_ortlama_2_10_18 >= 80 ]` branch (and for all 8 zones), "
            "add a parallel `--(R)-- vana2` coil right below `--(R)-- dc2` (or enable Modbus addresses on `dc1..dc6, dc13, dc14` and bind the HMI valve indicator to `dc`)."
        ),
    },
    {
        "problem_id": "PROB_02_PORT_502_DISABLED",
        "severity": "critical",
        "category": "PLC Network / Hardware Config",
        "location": "PLC(196R).gpf -> Donanım Konfigürasyonu -> GLC-196R -> Ethernet (CPU_Eth_slave_port = 502, Password = 1234)",
        "title_en": "Modbus TCP Slave Port 502 Is Refusing Connections (PLC Not in RUN Mode or Modbus Slave Inactive)",
        "title_tr": "Modbus TCP Slave Port 502 Bağlantıyı Reddediyor (PLC RUN Modunda Değil veya Modbus Slave Pasif)",
        "title_bn": "PLC-তে Modbus TCP Port 502 বন্ধ রয়েছে (GMTSuite থেকে PLC-তে প্রোগ্রাম RUN/Upload করা প্রয়োজন)",
        "title_ar": "منفذ Modbus TCP 502 مغلق في جهاز PLC",
        "symptom_en": (
            "When the Ethernet cable is connected to the PLC (192.168.1.240, MAC 00:25:FC:02:4F:B9), ping responds in 1ms, "
            "but TCP Port 502 returns Connection Refused (WinError 10061). Because demo/simulation data is disabled, "
            "all dashboard readings remain blank (—) until real PLC data arrives."
        ),
        "root_cause_en": (
            "In PLC(196R).gpf (offset 56289), `SI[14]=502` sets CPU_Eth_slave_port = 502 inside `app_init()`, and the project password is `1234`. "
            "However, on GLC-196R firmware, TCP port 502 only opens when the compiled program is downloaded and the PLC CPU is in **RUN** mode with Modbus TCP Slave active."
        ),
        "fix_steps_en": (
            "1. In your open GMTSuite window (`PLC(196R).gpf`), click 'PLC'ye Bağlan' (Connect to PLC at 192.168.1.240; if prompted for password, enter `1234`).\n"
            "2. To sync PLC time with PC time: click 'Gerçek Zaman Saati (RTC)' -> 'PC Saatinden Al / Eşitle'.\n"
            "3. Ensure 'Donanım Konfigürasyonu -> GLC-196R -> Ethernet -> Modbus TCP Slave' is checked (Port 502).\n"
            "4. Click 'PLC'ye Yükle' (Download to PLC) and switch the PLC to **RUN** mode."
        ),
    },
    {
        "problem_id": "PROB_03_NO_PH_IN_PLC",
        "severity": "high",
        "category": "Missing Sensor Parameter (pH)",
        "location": "PLC(196R).gpf -> COM2 RS485 Master Table (ps2_0..ps2_146) & PLC(196R).gpf.csv",
        "title_en": "Soil pH (pH) Is Not Polled on RS485 COM2 or Mapped in PLC(196R).gpf",
        "title_tr": "Toprak pH Değeri PLC(196R).gpf RS485 COM2 Tablosunda ve Adres Haritasında Tanımlanmamış",
        "title_bn": "PLC(196R).gpf প্রোগ্রামে মাটির pH (Soil pH) রেজিস্টার কনফিগার করা হয়নি",
        "title_ar": "لم تتم برمجة قراءة حموضة التربة (Soil pH) داخل ملف PLC(196R).gpf",
        "symptom_en": (
            "Soil pH shows '—' (blank) on the Web Dashboard, 48-Sensor Matrix, and Excel/CSV exports."
        ),
        "root_cause_en": (
            "Reverse-engineering PLC(196R).gpf and PLC(196R).gpf.csv confirms that the COM2 RS485 Modbus RTU Master table "
            "polls Slave IDs 1..24 (R1..R24) for only 4 registers per soil sensor: "
            "40001 (R{n}_humidity_co), 40002 (R{n}_temp_co), 40003 (R{n}_ec), and 40004 (R{n}_salt). "
            "Register 40005 (Soil pH) is never requested on the RS485 bus, and no R1_ph..R24_ph tags exist anywhere in the PLC."
        ),
        "fix_steps_en": (
            "1. Verify whether your field RS485 soil probes are 4-pin (Moisture/Temp/EC/Salt) or 5-in-1 (Moisture/Temp/EC/Salt/pH).\n"
            "2. If the probes support pH (typically Holding Register 40005 / 0x0004), open GMTSuite -> Haberleşme -> COM2 (Modbus RTU Master).\n"
            "3. Add R1_ph_co..R24_ph_co reads for Slave IDs 1..24, divide by 10.0 (or 100.0 per sensor datasheet) in AnaProgram, "
            "and expose R1_ph..R24_ph on Modbus TCP Holding Registers."
        ),
    },
    {
        "problem_id": "PROB_03_R115_TYPO_ZONE7",
        "severity": "high",
        "category": "Ladder Logic Bug (Zone 7)",
        "location": "PLC(196R).gpf -> AnaProgram (Byte Offset 49682: Tag 'R115_humidity')",
        "title_en": "Typo Tag 'R115_humidity' Instead of 'R15_humidity' in Zone 7 Moisture Average",
        "title_tr": "Bölge 7 Nem Ortalamasında 'R15_humidity' Yerine 'R115_humidity' Yazım Hatası",
        "title_bn": "Zone 7-এর গড় আর্দ্রতা হিসাবে 'R15_humidity'-এর বদলে ভুলবশত 'R115_humidity' লেখা হয়েছে",
        "title_ar": "خطأ برمجي في المنطقة 7: كتابة المتغير R115_humidity بدلاً من R15_humidity",
        "symptom_en": (
            "Zone 7 (Plots 7-15-23, Valve vana7 / Relay dc5 on CPU QP4) had a typo tag in original ladder logic."
        ),
        "root_cause_en": (
            "At byte offset 49682 of PLC(196R).gpf, right before ortlama_7_15 and ortlama_7_15_23, the original ladder logic referenced "
            "an unlinked tag named 'R115_humidity' (initial value = 0.0) instead of 'R15_humidity'. "
            "This has been permanently patched in PLC firmware (ladder_patched.c) to compute (R7 + R15 + R23) / 3.0."
        ),
        "fix_steps_en": (
            "1. Already fixed in PLC firmware v2.8 (ladder_patched.c -> R7_humidity + R15_humidity + R23_humidity / 3.0).\n"
            "2. Zone 7 is now mapped to physical relay dc5 (CPU QP4, Modbus Coil 0X:15)."
        ),
    },
    {
        "problem_id": "PROB_04_VANA6_VANA7_SWAPPED_COILS",
        "severity": "medium",
        "category": "Modbus Coil & Physical Solenoid Valve Remapping",
        "location": "PLC(196R).gpf / ladder_patched.c -> Coils 0X:1..8 (Mode) & 0X:9..16 (Physical Valves) | Relays dc1, dc2, dc14, dc13, dc3, dc4, dc5, dc6",
        "title_en": "Physical Solenoid Valve Remapping (Zone 1..8 -> dc1, dc2, dc14, dc13, dc3, dc4, dc5, dc6) & vana6/vana7 Coils",
        "title_tr": "Fiziksel Solenoid Vana Röle Eşlemesi (Bölge 1..8 -> dc1, dc2, dc14, dc13, dc3, dc4, dc5, dc6) ve vana6/vana7 Bobinleri",
        "title_bn": "ফিজিক্যাল সলেনয়েড ভালভ রিম্যাপিং (Zone 1..8 -> dc1, dc2, dc14, dc13, dc3, dc4, dc5, dc6) ও কয়েল কনফিগারেশন",
        "title_ar": "إعادة تعيين صمامات الملف اللولبي الفعلية (المناطق 1..8) وعناوين vana6/vana7",
        "symptom_en": (
            "Physical solenoid valves 3..8 in the greenhouse cabinet were wired in shifted order (3->5, 4->6, 5->7, 6->8, 7->4, 8->3). "
            "Additionally, vana6 is at Mode Coil 0X:7 and vana7 is at Mode Coil 0X:6."
        ),
        "root_cause_en": (
            "Physical field cables for Valves 3..8 were connected to different relay terminals in the PLC cabinet: "
            "Valve 1 -> CPU QP0 (dc1), Valve 2 -> CPU QP1 (dc2), Valve 3 -> GXM-88R Exp01_QP7 (dc14), Valve 4 -> GXM-88R Exp01_QP6 (dc13), "
            "Valve 5 -> CPU QP2 (dc3), Valve 6 -> CPU QP3 (dc4), Valve 7 -> CPU QP4 (dc5), Valve 8 -> CPU QP5 (dc6)."
        ),
        "fix_steps_en": (
            "Permanently remapped in PLC firmware (ladder_patched.c v2.8: qp_idx[8] = {0, 1, 23, 22, 2, 3, 4, 5} and Modbus Coils 0X:9..16), "
            "Edge Agent (PLC_QP_OFFSETS), Web SCADA Dashboard, and Cloud VPS Server so Zone 1..8 directly operate Physical Valves 1..8."
        ),
    },
    {
        "problem_id": "PROB_05_DUPLICATE_ORPHAN_AVERAGE_TAGS",
        "severity": "medium",
        "category": "Ladder Logic Hygiene (Zones 1, 3, 5)",
        "location": "PLC(196R).gpf -> Byte Offsets 47056..47500 (Zone 1), 48506 (Zone 3), 49090 (Zone 5)",
        "title_en": "Leftover / Duplicate Average Tags in Zone 1 (ortlama_1_9_20, ortlama_3_9_17), Zone 3, and Zone 5 (son_ortlama_5_13_20)",
        "title_tr": "Bölge 1, Bölge 3 ve Bölge 5'te Mükerrer / Artık Ortalama Etiketleri",
        "title_bn": "Zone 1, Zone 3 এবং Zone 5-এ অতিরিক্ত/ডুপ্লিকেট গড় ভেরিয়েবল ট্যাগ",
        "title_ar": "وجود متغيرات متوسطة مكررة أو غير مستخدمة في المناطق 1 و 3 و 5",
        "symptom_en": (
            "Multiple conflicting average tag names exist for the same irrigation zones inside PLC(196R).gpf."
        ),
        "root_cause_en": (
            "In Zone 1, tags 'ortlama_1_9_20', 'son_ortlama_1_9_20', 'ortlama_3_9_17', and 'son_ortlama_3_9_17' exist alongside "
            "'ortlama_1_9_17' and 'son_ortlama_1_9_17'. In Zone 3, 'son_ortlama_3' exists alongside 'son_ortlama_3_11_19'. "
            "In Zone 5, 'son_ortlama_5_13_20' (byte 49090) exists right before 'son_ortlama_5_13_21' (byte 49186)."
        ),
        "fix_steps_en": (
            "In GMTSuite -> AnaProgram, verify that the DIV (/ 3.0) output and the < 48 / >= 90 comparators for Zone 1, Zone 3, and Zone 5 "
            "reference the exact same tag (son_ortlama_1_9_17, son_ortlama_3_11_19, and son_ortlama_5_13_21), and remove unused tags."
        ),
    },
    {
        "problem_id": "PROB_06_EC_SALT_REGISTER_ORDER",
        "severity": "low",
        "category": "Modbus Register Addressing",
        "location": "PLC(196R).gpf.csv -> Holding Registers 4X:31..52 (Salt) & 4X:75..96 (EC)",
        "title_en": "Reverse-Ordered EC & Salinity Holding Registers and Swapped R14_ec (4X:91) / R15_ec (4X:92)",
        "title_tr": "Ters Sıralı EC/Tuzluluk Register Adresleri ve R14_ec (4X:91) / R15_ec (4X:92) Yer Değişimi",
        "title_bn": "EC ও Salinity রেজিস্টারের উল্টো ক্রম এবং R14_ec (4X:91) ও R15_ec (4X:92) অদলবদল",
        "title_ar": "ترتيب عكسي لعناوين سجلات الملوحة والتوصيل الكهربائي وتبديل R14_ec مع R15_ec",
        "symptom_en": (
            "R1_ec..R24_ec and R1_salt..R24_salt are not numbered sequentially in Modbus Holding Registers, and R14_ec (91) / R15_ec (92) break the descending sequence."
        ),
        "root_cause_en": (
            "R1_ec=3, R2_ec=7, R3_ec..R9_ec=81..75, R10_ec..R13_ec=96..93, R14_ec=91, R15_ec=92, R16_ec..R24_ec=90..82. "
            "Ourplc_map.py lookup table maps each sensor to its exact CSV register so software readings are unaffected."
        ),
        "fix_steps_en": (
            "No action required for our SCADA/Mobile platform (already mapped in EC_REGISTERS and SALT_REGISTERS). "
            "Keep this table in mind if inspecting registers manually with a third-party Modbus scanner."
        ),
    },
    {
        "problem_id": "PROB_07_RS485_146_POLLS_BOTTLENECK",
        "severity": "medium",
        "category": "RS485 Fieldbus Performance",
        "location": "PLC(196R).gpf -> COM2 RS485 Master (ps2_0..ps2_146, 4800 baud, 300ms timeout)",
        "title_en": "RS485 COM2 Bus Overload: 146 Individual Single-Register Queries at 4800 Baud",
        "title_tr": "RS485 COM2 Veri Yolu Yükü: 4800 Baud Hızında 146 Ayrı Tekil Register Sorgusu",
        "title_bn": "RS485 COM2 বাসে অতিরিক্ত চাপ: ৪৮০০ বাউড রেটে ১৪৬টি আলাদা সিঙ্গেল-রেজিস্টার কুয়েরি",
        "title_ar": "بطء ناقل RS485 COM2 بسبب 146 استعلاماً منفرداً بسرعة 4800 baud",
        "symptom_en": (
            "Sensor updates on the PLC take ~8–12 seconds when all sensors are online, and slow down to 43.8 seconds per cycle if sensors are unpowered."
        ),
        "root_cause_en": (
            "Instead of reading 4 contiguous registers (40001..40004) in one Modbus RTU request per soil sensor, COM2 issues 4 separate "
            "1-word requests per soil sensor (24×4=96) plus 2 separate 1-word requests per leaf sensor (24×2=48) + 3 extra = 147 requests. "
            "With a 300ms timeout per request, offline sensors cause severe bus delays."
        ),
        "fix_steps_en": (
            "In GMTSuite -> COM2 Modbus RTU Master, replace the 4 individual register reads per soil sensor with a single block read "
            "(Start=40001, Length=4) and a single block read per leaf sensor (Start=40001, Length=2). This cuts RS485 queries from 147 to 48 (3× faster)."
        ),
    },
]
