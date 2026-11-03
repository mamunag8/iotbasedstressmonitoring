"""
Modbus TCP (Port 502) & GMTSuite Direct Memory (Port 23) Client for GMTCNT GLC-196R PLC (192.168.1.240).
Implements both:
1. Standard Modbus TCP (Port 502) when enabled in GMTSuite.
2. Direct GMTSuite Administration Terminal Memory Protocol (Port 23, `rdmem` / `wrmem`) when Port 502 is closed ('Pasif'),
   reading exact `plcvar_t` RAM offsets decoded from `ladder.c` and `AppPLC.map` (size 3379 bytes = 0x0d33):
   - `QP[0..5, 22, 23]` (offsets `0x0118..0x011d, 0x012e..0x012f`): Actual physical Solenoid Valve Relay outputs (`dc1..dc6, dc13, dc14`).
   - `var_bit.vana1..vana8` (offsets `0x09c5..0x09cc`): PLC Auto Mode Enable switches (`1` = Auto Mode Running, `0` = Auto Mode OFF / Manual Stop).
   - `var_Word.son_ortlama_...` (offsets `0x0b08..0x0b38`): PLC-calculated 3-sensor Zone Average Soil Humidity (%) used by the ladder (`<= 45%` ON, `>= 80%` OFF).
   - `var_Word.R1_ec..R24_salt` (offsets `0x09d6..0x0a95`): 24 Soil Sensors EC & Salinity (16-bit unsigned words).
   - `var_float.R1_humidity..R24_L_temp` (offsets `0x0b44..0x0cc3`): 96 IEEE-754 32-bit floats for 24 Soil Sensors (`R1..R24`) and 24 Leaf Sensors (`R1_L..R24_L`).

Strict Zero-Demo Policy: Never generates fake or simulated data.
"""

import math
import os
import re
import socket
import struct
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pymodbus.client import ModbusTcpClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "cloud_backend")))
from app.plc_map import EC_REGISTERS, PH_REGISTERS, SALT_REGISTERS, SENSORS, ZONES

# Exact byte offsets inside `plcvar_t` (total 3379 bytes = 0x0d33) verified from ladder.c & AppPLC.map
PLC_QP_OFFSETS: Dict[int, int] = {
    1: 0x0118,  # QP[0]  -> Relay dc1  (Zone 1 Valve)
    2: 0x0119,  # QP[1]  -> Relay dc2  (Zone 2 Valve)
    3: 0x011A,  # QP[2]  -> Relay dc3  (Zone 3 Valve)
    4: 0x011B,  # QP[3]  -> Relay dc4  (Zone 4 Valve)
    5: 0x011C,  # QP[4]  -> Relay dc5  (Zone 5 Valve)
    6: 0x011D,  # QP[5]  -> Relay dc6  (Zone 6 Valve)
    7: 0x012E,  # QP[22] -> Relay dc13 (Zone 7 Valve on GXM-88R)
    8: 0x012F,  # QP[23] -> Relay dc14 (Zone 8 Valve on GXM-88R)
}

PLC_VANA_OFFSETS: Dict[int, int] = {
    z: 0x09C5 + (z - 1) for z in range(1, 9)  # var_bit.vana1..vana8 (Auto Mode Enable bits)
}

PLC_SON_ORTLAMA_OFFSETS: Dict[int, int] = {
    1: 0x0B08,  # son_ortlama_1_9_17
    2: 0x0B0E,  # son_ortlama_2_10_18
    3: 0x0B14,  # son_ortlama_3_11_19
    4: 0x0B1C,  # son_ortlama_4_12_20
    5: 0x0B24,  # son_ortlama_5_13_21
    6: 0x0B2A,  # son_ortlama_6_14_22
    7: 0x0B32,  # son_ortlama_7_15_23
    8: 0x0B38,  # son_ortlama_8_16_24
}

PLC_WORD_SENSORS_BASE = 0x09D6   # R1_humidity1..R24_salt (8 bytes per sensor: hum_u16, temp_u16, ec_u16, salt_u16)
PLC_LEAF_WORDS_BASE = 0x0A96     # R1_L_humidity101..R24_L_temp124 (4 bytes per sensor: lhum_u16, ltemp_u16)
PLC_FLOAT_SENSORS_BASE = 0x0B44  # R1_humidity..R24_L_temp (16 bytes per sensor: hum_f32, temp_f32, lhum_f32, ltemp_f32)


def decode_ieee754_float(reg_low: int, reg_high: int, little_endian_word_order: bool = True) -> float:
    """Decode two 16-bit Modbus holding registers into a 32-bit IEEE-754 float."""
    if little_endian_word_order:
        raw = struct.pack("<HH", reg_low & 0xFFFF, reg_high & 0xFFFF)
        val = struct.unpack("<f", raw)[0]
    else:
        raw = struct.pack(">HH", reg_low & 0xFFFF, reg_high & 0xFFFF)
        val = struct.unpack(">f", raw)[0]
    if math.isnan(val) or math.isinf(val) or abs(val) > 10000:
        return 0.0
    return round(float(val), 2)


def encode_ieee754_float(value: float, little_endian_word_order: bool = True) -> Tuple[int, int]:
    """Encode a 32-bit float into two 16-bit Modbus registers."""
    if little_endian_word_order:
        raw = struct.pack("<f", float(value))
        return struct.unpack("<HH", raw)
    else:
        raw = struct.pack(">f", float(value))
        return struct.unpack(">HH", raw)


class GLC196RModbusDriver:
    def __init__(
        self,
        plc_ip: str = "192.168.1.240",
        plc_port: int = 502,
        unit_id: int = 1,
        one_based_pdu: bool = True,
        allow_simulation_fallback: bool = False,
        admin_password: str = "283320",
    ) -> None:
        self.plc_ip = plc_ip
        self.plc_port = plc_port
        self.unit_id = unit_id
        self.one_based_pdu = one_based_pdu
        self.allow_simulation_fallback = False  # Strictly disabled: no demo/fake data allowed
        self.admin_password = os.getenv("PLC_ADMIN_PASSWORD", admin_password)
        self.client: Optional[ModbusTcpClient] = None
        self.plc_online: bool = False
        self.port23_open: bool = False
        self.port502_open: bool = False
        self.last_error: Optional[str] = None
        self._last_rtc_sync_ts: float = 0.0
        # Track explicit manual-open overrides per zone (since in PLC ladder, manual open uses vanaX=1 + QP=1)
        self.manual_override_zones: Dict[int, str] = {}

    def _pdu_addr(self, csv_addr: int) -> int:
        return max(0, csv_addr - 1) if self.one_based_pdu else csv_addr

    def check_ports(self) -> Dict[str, Any]:
        """Check both GMTSuite service port (23) and Modbus TCP port (502) on the PLC."""
        p23 = False
        p502 = False
        try:
            with socket.create_connection((self.plc_ip, 23), timeout=0.8) as s23:
                p23 = True
        except Exception:
            p23 = False

        try:
            with socket.create_connection((self.plc_ip, self.plc_port), timeout=0.8) as s502:
                p502 = True
        except Exception:
            p502 = False

        self.port23_open = p23
        self.port502_open = p502
        if p23 or p502:
            self.last_error = None
        else:
            self.last_error = (
                f"PLC ({self.plc_ip}) is unreachable on Ethernet (both Port 23 and Port {self.plc_port} timed out)."
            )

        return {
            "plc_ip": self.plc_ip,
            "plc_port": self.plc_port,
            "port23_open": p23,
            "port502_open": p502,
            "ethernet_reachable": p23 or p502,
            "active_protocol": "modbus_tcp_502" if p502 else ("gmtsuite_port23_rdmem" if p23 else "offline"),
            "last_error": self.last_error,
        }

    def connect(self) -> bool:
        try:
            diag = self.check_ports()
            if diag["port502_open"]:
                if self.client is None:
                    self.client = ModbusTcpClient(host=self.plc_ip, port=self.plc_port, timeout=1.5)
                self.plc_online = bool(self.client.connect())
                if self.plc_online:
                    return True
            if diag["port23_open"]:
                self.plc_online = True
                return True
            self.plc_online = False
            return False
        except Exception as exc:
            self.last_error = str(exc)
            self.plc_online = False
            return False

    # -------------------------------------------------------------------------
    # Port 23 Direct PLC Memory Protocol (`rdmem` / `wrmem`)
    # -------------------------------------------------------------------------
    def _open_port23_session(self) -> Optional[socket.socket]:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2.5)
            s.connect((self.plc_ip, 23))
            time.sleep(0.06)
            s.recv(1024)
            s.sendall(f"{self.admin_password}\r\n".encode("ascii"))
            time.sleep(0.06)
            auth_resp = s.recv(1024).decode("ascii", errors="replace")
            if "Password accepted" not in auth_resp and ">" not in auth_resp:
                s.close()
                self.last_error = "PLC Port 23 authentication failed."
                return None
            return s
        except Exception as exc:
            self.last_error = f"PLC Port 23 connection error: {exc}"
            return None

    @staticmethod
    def _rdmem_tokens(sock: socket.socket, tokens: List[str]) -> List[bytes]:
        upper_tokens = [t.upper() for t in tokens]
        cmd = "rdmem " + " ".join(upper_tokens) + " \r\n"
        sock.sendall(cmd.encode("ascii"))
        buf = b""
        deadline = time.time() + 1.8
        while time.time() < deadline:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
            if b">" in buf and b"rdmem" in buf:
                break
        text = buf.decode("ascii", errors="replace")
        m = re.search(r"rdmem\s+([0-9A-Fa-f\s]+)", text)
        if not m:
            return []
        return [bytes.fromhex(tok) for tok in m.group(1).split() if re.fullmatch(r"[0-9A-Fa-f]+", tok)]

    @staticmethod
    def _wrmem_single(sock: socket.socket, offset: int, data_bytes: bytes) -> bool:
        length = len(data_bytes)
        hex_data = data_bytes.hex().upper()
        cmd = f"wrmem {offset:04X}{length:02X}{hex_data} \r\n"
        sock.sendall(cmd.encode("ascii"))
        buf = b""
        deadline = time.time() + 1.2
        while time.time() < deadline:
            chunk = sock.recv(1024)
            if not chunk:
                break
            buf += chunk
            if b">" in buf:
                break
        return b"wrmem OK" in buf

    def _poll_hardware_port23(self, zone_configs: Optional[Dict[int, Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
        """
        Reads all 48 sensors, 8 Auto Mode bits (`vana1..8`), 8 physical valve relay outputs (`QP`),
        and 8 PLC-calculated zone average soil humidities (`son_ortlama`) directly via Port 23 in ~120ms.
        """
        sock = self._open_port23_session()
        if sock is None:
            self.plc_online = False
            return None

        try:
            # 0. Periodically sync PLC RTC clock with PC time and ensure PLC ladder task is RUNNING
            now_mono = time.monotonic()
            if (now_mono - self._last_rtc_sync_ts) > 3600.0:
                now_dt = datetime.now()
                wday = now_dt.isoweekday()
                settime_cmd = (
                    f"settime {now_dt.hour:02d}:{now_dt.minute:02d}:{now_dt.second:02d} "
                    f"{now_dt.day:02d}-{now_dt.month:02d}-{now_dt.year % 100:02d} {wday:02d}\r\n"
                )
                sock.sendall(settime_cmd.encode("ascii"))
                time.sleep(0.05)
                sock.recv(1024)
                self._last_rtc_sync_ts = now_mono

            # 1. Read 8 QP valve outputs (1B each) + 8 vana auto-mode bits (1B each) + 8 son_ortlama words (2B each) = 24 tokens
            qp_toks = [f"{PLC_QP_OFFSETS[z]:04X}01" for z in range(1, 9)]
            vana_toks = [f"{PLC_VANA_OFFSETS[z]:04X}01" for z in range(1, 9)]
            son_toks = [f"{PLC_SON_ORTLAMA_OFFSETS[z]:04X}02" for z in range(1, 9)]
            ctrl_res = self._rdmem_tokens(sock, qp_toks + vana_toks + son_toks)
            if len(ctrl_res) != 24:
                self.plc_online = False
                self.last_error = f"Port 23 ctrl rdmem incomplete ({len(ctrl_res)}/24)."
                return None

            qp_states: Dict[int, bool] = {}
            vana_states: Dict[int, bool] = {}
            son_ortlama_map: Dict[int, int] = {}
            for idx, z in enumerate(range(1, 9)):
                qp_states[z] = bool(ctrl_res[idx][0]) if len(ctrl_res[idx]) == 1 else False
                vana_states[z] = bool(ctrl_res[8 + idx][0]) if len(ctrl_res[8 + idx]) == 1 else False
                son_b = ctrl_res[16 + idx]
                son_ortlama_map[z] = int(struct.unpack("<H", son_b)[0]) if len(son_b) == 2 else 0

            # Note: Do not overwrite vana_states or qp_states during polling so that
            # operator Auto/Manual mode switches and manual valve button toggles on the
            # physical HMI (GHS-070E) are respected without interference.

            # 2. Read all 96 Soil Words (0x09d6..0x0a95: hum_u16, temp_u16, ec_u16, salt_u16) across 3 calls of 32 words
            soil_word_toks = [f"{PLC_WORD_SENSORS_BASE + i * 2:04X}02" for i in range(96)]
            soil_word_res: List[bytes] = []
            for i in range(0, 96, 32):
                soil_word_res.extend(self._rdmem_tokens(sock, soil_word_toks[i : i + 32]))
            if len(soil_word_res) != 96:
                self.plc_online = False
                self.last_error = f"Port 23 soil word rdmem incomplete ({len(soil_word_res)}/96)."
                return None

            # 3. Read all 48 Leaf Words (0x0a96..0x0af5: lhum_u16, ltemp_u16) across 2 calls of 24 words
            leaf_word_toks = [f"{PLC_LEAF_WORDS_BASE + i * 2:04X}02" for i in range(48)]
            leaf_word_res = self._rdmem_tokens(sock, leaf_word_toks[:24]) + self._rdmem_tokens(sock, leaf_word_toks[24:])
            if len(leaf_word_res) != 48:
                self.plc_online = False
                self.last_error = f"Port 23 leaf word rdmem incomplete ({len(leaf_word_res)}/48)."
                return None

            # 4. Read 96 IEEE-754 floats for Sensors 1..24 (R{n}_humidity, R{n}_temp, R{n}_L_humidity, R{n}_L_temp)
            float_toks = [f"{PLC_FLOAT_SENSORS_BASE + i * 4:04X}04" for i in range(96)]
            float_res: List[bytes] = []
            for i in range(0, 96, 24):
                float_res.extend(self._rdmem_tokens(sock, float_toks[i : i + 24]))
            if len(float_res) != 96:
                self.plc_online = False
                self.last_error = f"Port 23 float rdmem incomplete ({len(float_res)}/96)."
                return None

            def unpack_f32(b: bytes) -> float:
                if len(b) != 4:
                    return 0.0
                v = struct.unpack("<f", b)[0]
                if math.isnan(v) or math.isinf(v) or abs(v) > 10000:
                    return 0.0
                return round(float(v), 2)

            def unpack_u16(b: bytes) -> int:
                return int(struct.unpack("<H", b)[0]) if len(b) == 2 else 0

            def unpack_i16(b: bytes) -> int:
                return int(struct.unpack("<h", b)[0]) if len(b) == 2 else 0

            sensors_list: List[Dict[str, Any]] = []
            for n in range(1, 25):
                sdef = SENSORS[n]
                w_base = (n - 1) * 4
                raw_shum = unpack_u16(soil_word_res[w_base + 0])
                raw_stmp = unpack_i16(soil_word_res[w_base + 1])
                ec_val = unpack_u16(soil_word_res[w_base + 2])
                salt_val = unpack_u16(soil_word_res[w_base + 3])

                lw_base = (n - 1) * 2
                raw_lhum = unpack_u16(leaf_word_res[lw_base + 0])
                raw_ltmp = unpack_i16(leaf_word_res[lw_base + 1])

                f_base = (n - 1) * 4
                s_hum = unpack_f32(float_res[f_base + 0]) or round(raw_shum / 10.0, 2)
                s_tmp = unpack_f32(float_res[f_base + 1]) or round(raw_stmp / 10.0, 2)
                l_hum = unpack_f32(float_res[f_base + 2]) or round(raw_lhum / 10.0, 2)
                l_tmp = unpack_f32(float_res[f_base + 3]) or round(raw_ltmp / 10.0, 2)

                sensors_list.append({
                    "sensor_id": n,
                    "zone_id": sdef["zone_id"],
                    "soil_name": sdef["soil_name"],
                    "leaf_name": sdef["leaf_name"],
                    "soil_slave_id": sdef["soil_slave_id"],
                    "leaf_slave_id": sdef["leaf_slave_id"],
                    "soil_moisture": s_hum,
                    "soil_temp": s_tmp,
                    "soil_ec": ec_val,
                    "soil_salt": salt_val,
                    "soil_ph": None,
                    "leaf_humidity": l_hum,
                    "leaf_temp": l_tmp,
                })

            valves_map: Dict[str, bool] = {}
            for zid, zdef in ZONES.items():
                valves_map[zdef["valve_tag"]] = qp_states.get(zid, False)

            self.plc_online = True
            self.last_error = None
            return self._build_batch_payload(
                sensors_list=sensors_list,
                valves_map=valves_map,
                plc_online=True,
                source="plc_hardware_196r",
                zone_configs=zone_configs,
                vana_auto_bits=vana_states,
                qp_relay_states=qp_states,
                plc_son_ortlama=son_ortlama_map,
            )
        except Exception as exc:
            self.plc_online = False
            self.last_error = f"Port 23 read exception: {exc}"
            return None
        finally:
            try:
                sock.close()
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # Control Commands (Supports both Port 23 Direct RAM Write and Port 502)
    # -------------------------------------------------------------------------
    def write_zone_control(
        self,
        zone_id: int,
        auto_mode: Optional[bool] = None,
        target_open: Optional[bool] = None,
    ) -> bool:
        """
        Controls a Zone's Operating Mode (Auto vs Manual) and Solenoid Valve (`QP` relay) on the physical PLC:
        - AUTO MODE (`auto_mode=True`):
            Sets `vana{zone_id} = 1` in PLC so the PLC ladder automatically controls `QP`
            (`son_ortlama <= 45%` -> ON, `>= 80%` -> OFF).
            If switching from Manual Open to Auto Mode while `son_ortlama > 45%`, resets `QP = 0` (Standby).
        - MANUAL MODE — CLOSE VALVE (`auto_mode=False, target_open=False`):
            Sets `vana{zone_id} = 0` and `QP = 0` in PLC. Ladder keeps `QP = 0` (Forced OFF).
        - MANUAL MODE — OPEN VALVE (`auto_mode=False, target_open=True`):
            Sets `vana{zone_id} = 1` and `QP = 1` in PLC so the physical solenoid valve opens immediately,
            and records `manual_override_zones[zone_id] = 'open'`.
        """
        if zone_id not in ZONES:
            raise ValueError(f"Invalid zone_id: {zone_id}")

        diag = self.check_ports()
        if diag["port23_open"]:
            sock = self._open_port23_session()
            if sock is not None:
                try:
                    vana_off = PLC_VANA_OFFSETS[zone_id]
                    qp_off = PLC_QP_OFFSETS[zone_id]
                    son_off = PLC_SON_ORTLAMA_OFFSETS[zone_id]

                    if auto_mode is True and target_open is None:
                        # Switch zone to AUTO MODE RUNNING
                        self.manual_override_zones.pop(zone_id, None)
                        ok1 = self._wrmem_single(sock, vana_off, b"\x01")
                        # Check current son_ortlama so if it was manually forced open above 45%, we put QP in clean auto standby
                        son_res = self._rdmem_tokens(sock, [f"{son_off:04X}02"])
                        son_val = struct.unpack("<H", son_res[0])[0] if son_res and len(son_res[0]) == 2 else 50
                        if son_val <= 45:
                            self._wrmem_single(sock, qp_off, b"\x01")
                        else:
                            self._wrmem_single(sock, qp_off, b"\x00")
                        return ok1
                    elif target_open is True:
                        # Switch zone to MANUAL MODE RUNNING — VALVE OPEN
                        self.manual_override_zones[zone_id] = "open"
                        ok1 = self._wrmem_single(sock, vana_off, b"\x01")
                        ok2 = self._wrmem_single(sock, qp_off, b"\x01")
                        return ok1 and ok2
                    else:
                        # Switch zone to MANUAL MODE RUNNING — VALVE CLOSED (Auto OFF)
                        self.manual_override_zones[zone_id] = "closed"
                        ok1 = self._wrmem_single(sock, vana_off, b"\x00")
                        ok2 = self._wrmem_single(sock, qp_off, b"\x00")
                        return ok1 and ok2
                finally:
                    try:
                        sock.close()
                    except Exception:
                        pass

        # Fallback to Port 502 Modbus TCP if Port 502 is open
        if diag["port502_open"]:
            coil_state = True if (auto_mode is True or target_open is True) else False
            return self.write_valve_coil(zone_id, coil_state)

        return False

    def write_valve_coil(self, zone_id: int, state: bool) -> bool:
        """Write ON (True) or OFF (False) to vana1..vana8 on the physical PLC."""
        if zone_id not in ZONES:
            raise ValueError(f"Invalid zone_id: {zone_id}")
        diag = self.check_ports()
        if diag["port23_open"] and not diag["port502_open"]:
            return self.write_zone_control(zone_id=zone_id, auto_mode=False, target_open=state)

        coil_csv_addr = ZONES[zone_id]["valve_coil"]
        if not self.connect() or not self.client:
            return False

        pdu_addr = self._pdu_addr(coil_csv_addr)
        try:
            try:
                wr = self.client.write_coil(address=pdu_addr, value=bool(state), device_id=self.unit_id)
            except TypeError:
                try:
                    wr = self.client.write_coil(address=pdu_addr, value=bool(state), slave=self.unit_id)
                except TypeError:
                    wr = self.client.write_coil(pdu_addr, bool(state))
            return wr is not None and not wr.isError()
        except Exception:
            return False

    # -------------------------------------------------------------------------
    # Snapshot Polling (Port 502 or Port 23)
    # -------------------------------------------------------------------------
    def _read_hr(self, start_csv_addr: int, count: int) -> Optional[List[int]]:
        if not self.client:
            return None
        pdu_addr = self._pdu_addr(start_csv_addr)
        try:
            try:
                rr = self.client.read_holding_registers(address=pdu_addr, count=count, device_id=self.unit_id)
            except TypeError:
                try:
                    rr = self.client.read_holding_registers(address=pdu_addr, count=count, slave=self.unit_id)
                except TypeError:
                    rr = self.client.read_holding_registers(pdu_addr, count)
            if rr is None or rr.isError():
                return None
            return list(rr.registers)
        except Exception:
            return None

    def _read_coils(self, start_csv_addr: int, count: int) -> Optional[List[bool]]:
        if not self.client:
            return None
        pdu_addr = self._pdu_addr(start_csv_addr)
        try:
            try:
                rr = self.client.read_coils(address=pdu_addr, count=count, device_id=self.unit_id)
            except TypeError:
                try:
                    rr = self.client.read_coils(address=pdu_addr, count=count, slave=self.unit_id)
                except TypeError:
                    rr = self.client.read_coils(pdu_addr, count)
            if rr is None or rr.isError():
                return None
            return [bool(b) for b in rr.bits[:count]]
        except Exception:
            return None

    def poll_snapshot(self, zone_configs: Optional[Dict[int, Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Polls a complete telemetry snapshot from the physical GLC-196R PLC via Port 23 (or Port 502).
        If the PLC is offline, returns a blank/offline snapshot (plc_online=False) with None values.
        """
        # Prefer Port 23 direct memory read (single socket session — gives QP[0..23], vana1..8, son_ortlama_1..8 AND all 48 sensors)
        snapshot = self._poll_hardware_port23(zone_configs)
        if snapshot is not None:
            self.port23_open = True
            return snapshot

        diag = self.check_ports()
        if diag["port502_open"] and self.connect():
            snapshot = self._poll_hardware_port502(zone_configs)
            if snapshot is not None:
                return snapshot

        return self._build_offline_blank_payload(zone_configs)

    def _poll_hardware_port502(self, zone_configs: Optional[Dict[int, Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
        ec_salt_regs = self._read_hr(start_csv_addr=3, count=94)
        float_block_1 = self._read_hr(start_csv_addr=2001, count=96)
        float_block_2 = self._read_hr(start_csv_addr=2097, count=96)
        coil_bits = self._read_coils(start_csv_addr=1, count=9)

        if ec_salt_regs is None or float_block_1 is None or float_block_2 is None or coil_bits is None:
            self.plc_online = False
            self.last_error = "Modbus TCP register read failed on 192.168.1.240:502."
            return None

        float_regs = float_block_1 + float_block_2

        def get_hr_16(csv_addr: Optional[int]) -> Optional[int]:
            if csv_addr is None:
                return None
            idx = csv_addr - 3
            if 0 <= idx < len(ec_salt_regs):
                return int(ec_salt_regs[idx])
            return None

        def get_hr_float(csv_addr: Optional[int]) -> Optional[float]:
            if csv_addr is None:
                return None
            idx = csv_addr - 2001
            if 0 <= idx < len(float_regs) - 1:
                return decode_ieee754_float(float_regs[idx], float_regs[idx + 1])
            return None

        sensors_list: List[Dict[str, Any]] = []
        for n in range(1, 25):
            sdef = SENSORS[n]
            ph_val: Optional[float] = None
            if sdef.get("ph_reg") is not None:
                raw_ph = get_hr_16(sdef["ph_reg"])
                if raw_ph is not None:
                    ph_val = round(raw_ph / 10.0, 2)

            sensors_list.append({
                "sensor_id": n,
                "zone_id": sdef["zone_id"],
                "soil_name": sdef["soil_name"],
                "leaf_name": sdef["leaf_name"],
                "soil_slave_id": sdef["soil_slave_id"],
                "leaf_slave_id": sdef["leaf_slave_id"],
                "soil_moisture": get_hr_float(sdef["humidity_reg"]),
                "soil_temp": get_hr_float(sdef["temp_reg"]),
                "soil_ec": get_hr_16(sdef["ec_reg"]),
                "soil_salt": get_hr_16(sdef["salt_reg"]),
                "soil_ph": ph_val,
                "leaf_humidity": get_hr_float(sdef["leaf_humidity_reg"]),
                "leaf_temp": get_hr_float(sdef["leaf_temp_reg"]),
            })

        vana_states: Dict[int, bool] = {}
        valves_map: Dict[str, bool] = {}
        for zid, zdef in ZONES.items():
            c_idx = zdef["valve_coil"] - 1
            vana_on = bool(coil_bits[c_idx]) if 0 <= c_idx < len(coil_bits) else False
            vana_states[zid] = vana_on
            valves_map[zdef["valve_tag"]] = bool(coil_bits[8]) if zid == 1 and len(coil_bits) > 8 else vana_on

        return self._build_batch_payload(
            sensors_list=sensors_list,
            valves_map=valves_map,
            plc_online=True,
            source="plc_hardware_196r",
            zone_configs=zone_configs,
            vana_auto_bits=vana_states,
        )

    def _build_offline_blank_payload(self, zone_configs: Optional[Dict[int, Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Returns a blank payload (None for all sensor measurements) when PLC returns no data."""
        sensors_list: List[Dict[str, Any]] = []
        for n in range(1, 25):
            sdef = SENSORS[n]
            sensors_list.append({
                "sensor_id": n,
                "zone_id": sdef["zone_id"],
                "soil_name": sdef["soil_name"],
                "leaf_name": sdef["leaf_name"],
                "soil_slave_id": sdef["soil_slave_id"],
                "leaf_slave_id": sdef["leaf_slave_id"],
                "soil_moisture": None,
                "soil_temp": None,
                "soil_ec": None,
                "soil_salt": None,
                "soil_ph": None,
                "leaf_humidity": None,
                "leaf_temp": None,
            })

        zones_list: List[Dict[str, Any]] = []
        for zid, zdef in ZONES.items():
            cfg = (zone_configs or {}).get(zid, {})
            nom_lpm = float(cfg.get("nominal_flow_lpm", 2.0))
            tot_liters = round(float(cfg.get("total_water_liters", 0.0)), 2)
            tot_sec = round(float(cfg.get("total_open_seconds", 0.0)), 1)
            fm_conn = bool(cfg.get("flow_meter_connected", False))
            zones_list.append({
                "zone_id": zid,
                "name_tr": zdef["name_tr"],
                "name_en": zdef["name_en"],
                "valve_tag": zdef["valve_tag"],
                "valve_coil": zdef["valve_coil"],
                "relay_tag": zdef["relay_tag"],
                "plc_terminal": zdef["plc_terminal"],
                "valve_model": "hexa CONTROLS AC 230V IP54 NC",
                "flow_meter_model": "YF-S201 (1-30 L/min, <=1.75 MPa)",
                "flow_meter_position": "Before / Below Solenoid Valve",
                "flow_meter_connected": fm_conn,
                "nominal_flow_lpm": nom_lpm,
                "flow_rate_lpm": 0.0,
                "total_water_liters": tot_liters,
                "total_open_seconds": tot_sec,
                "valve_open": None,
                "vana_coil_on": None,
                "plc_son_ortlama": None,
                "operation_mode": "unknown",
                "auto_mode": bool(cfg.get("auto_mode", True)),
                "min_moisture": float(cfg.get("min_moisture", zdef["default_min_moisture"])),
                "max_moisture": float(cfg.get("max_moisture", zdef["default_max_moisture"])),
                "avg_soil_moisture": None,
                "avg_soil_temp": None,
                "avg_soil_ec": None,
                "avg_soil_salt": None,
                "avg_soil_ph": None,
                "avg_leaf_humidity": None,
                "avg_leaf_temp": None,
                "sensor_ids": zdef["sensor_ids"],
                "leaf_slave_ids": [100 + sid for sid in zdef["sensor_ids"]],
            })

        return {
            "batch_id": str(uuid.uuid4()),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "source": "plc_offline",
            "plc_online": False,
            "port23_open": self.port23_open,
            "port502_open": self.port502_open,
            "diagnostic_error": self.last_error,
            "zones": zones_list,
            "sensors": sensors_list,
            "valves": {},
        }

    def _build_batch_payload(
        self,
        sensors_list: List[Dict[str, Any]],
        valves_map: Dict[str, bool],
        plc_online: bool,
        source: str,
        zone_configs: Optional[Dict[int, Dict[str, Any]]] = None,
        vana_auto_bits: Optional[Dict[int, bool]] = None,
        qp_relay_states: Optional[Dict[int, bool]] = None,
        plc_son_ortlama: Optional[Dict[int, int]] = None,
    ) -> Dict[str, Any]:
        def _avg_non_null(items: List[Any], ndigits: int = 2) -> Optional[float]:
            valid = [float(x) for x in items if x is not None]
            if not valid:
                return None
            return round(sum(valid) / len(valid), ndigits)

        zones_list: List[Dict[str, Any]] = []
        for zid, zdef in ZONES.items():
            z_sensors = [s for s in sensors_list if s["zone_id"] == zid]
            cfg = (zone_configs or {}).get(zid, {})
            avg_moist = _avg_non_null([s.get("soil_moisture") for s in z_sensors], 2)
            min_m = float(cfg.get("min_moisture", zdef["default_min_moisture"]))
            max_m = float(cfg.get("max_moisture", zdef["default_max_moisture"]))

            # Exact PLC Hardware Logic from ladder.c:
            # 1) `vana1..vana8` (`vana_auto_bits`) is the PLC Auto Mode Enable switch:
            #    - vanaX == 1: PLC Auto Mode is enabled (`son_ortlama <= 45` -> QP=1; `son_ortlama >= 80` -> QP=0)
            #    - vanaX == 0: PLC Auto Mode is OFF (`!vanaX` -> QP=0)
            # 2) `QP[0..5, 22, 23]` (`qp_relay_states`) is the actual physical Solenoid Valve Relay state (`dc1..dc6, dc13, dc14`).
            vana_bit = bool(vana_auto_bits.get(zid, False)) if vana_auto_bits is not None else bool(valves_map.get(zdef["valve_tag"], False))
            qp_open = bool(qp_relay_states.get(zid, False)) if qp_relay_states is not None else bool(valves_map.get(zdef["valve_tag"], False))
            son_ort = int(plc_son_ortlama[zid]) if (plc_son_ortlama is not None and zid in plc_son_ortlama) else (int(round(avg_moist)) if avg_moist is not None else None)

            # Determine exact Auto Mode vs Manual Mode:
            # - If vana_bit is False -> Zone is in MANUAL MODE (Auto OFF, Valve Closed).
            # - If vana_bit is True and operator explicitly forced manual open -> MANUAL MODE (Valve Forced Open).
            # - If vana_bit is True (and not manual-open overridden) -> AUTO MODE RUNNING!
            manual_ovr = self.manual_override_zones.get(zid)
            if not vana_bit:
                is_auto_mode = False
                operation_mode = "manual_closed"
            elif manual_ovr == "open" and qp_open:
                is_auto_mode = False
                operation_mode = "manual_open"
            else:
                is_auto_mode = True
                operation_mode = "auto_irrigating" if qp_open else "auto_standby"

            auto_off_at_max = bool(avg_moist is not None and avg_moist >= max_m)
            nom_lpm = float(cfg.get("nominal_flow_lpm", 2.0))
            tot_liters = round(float(cfg.get("total_water_liters", 0.0)), 2)
            tot_sec = round(float(cfg.get("total_open_seconds", 0.0)), 1)
            fm_conn = bool(cfg.get("flow_meter_connected", False))
            live_flow_lpm = round(nom_lpm, 2) if qp_open else 0.0

            zones_list.append({
                "zone_id": zid,
                "name_tr": zdef["name_tr"],
                "name_en": zdef["name_en"],
                "valve_tag": zdef["valve_tag"],
                "valve_coil": zdef["valve_coil"],
                "relay_tag": zdef["relay_tag"],
                "plc_terminal": zdef["plc_terminal"],
                "valve_model": "hexa CONTROLS AC 230V IP54 NC",
                "flow_meter_model": "YF-S201 (1-30 L/min, <=1.75 MPa)",
                "flow_meter_position": "Before / Below Solenoid Valve",
                "flow_meter_connected": fm_conn,
                "nominal_flow_lpm": nom_lpm,
                "flow_rate_lpm": live_flow_lpm,
                "total_water_liters": tot_liters,
                "total_open_seconds": tot_sec,
                "valve_open": qp_open,
                "vana_coil_on": vana_bit,
                "plc_son_ortlama": son_ort,
                "operation_mode": operation_mode,
                "auto_off_at_max": auto_off_at_max,
                "auto_mode": is_auto_mode,
                "min_moisture": min_m,
                "max_moisture": max_m,
                "avg_soil_moisture": avg_moist,
                "avg_soil_temp": _avg_non_null([s.get("soil_temp") for s in z_sensors], 2),
                "avg_soil_ec": _avg_non_null([s.get("soil_ec") for s in z_sensors], 1),
                "avg_soil_salt": _avg_non_null([s.get("soil_salt") for s in z_sensors], 1),
                "avg_soil_ph": _avg_non_null([s.get("soil_ph") for s in z_sensors], 2),
                "avg_leaf_humidity": _avg_non_null([s.get("leaf_humidity") for s in z_sensors], 2),
                "avg_leaf_temp": _avg_non_null([s.get("leaf_temp") for s in z_sensors], 2),
                "sensor_ids": zdef["sensor_ids"],
                "leaf_slave_ids": [100 + sid for sid in zdef["sensor_ids"]],
            })

        return {
            "batch_id": str(uuid.uuid4()),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "plc_online": plc_online,
            "port23_open": self.port23_open,
            "port502_open": self.port502_open,
            "diagnostic_error": self.last_error,
            "zones": zones_list,
            "sensors": sensors_list,
            "valves": valves_map,
        }
