# SAFE BACKUP — Ziraat Fakültesi Otomatik Sulama Sistemi (PLC & HMI Final Verified)
Date: 2026-11-04

## 1. Contents
- `HMI(070E)_FINAL/HMI(070E).pkgx` (11,194,058 bytes, MD5 trailer: `990f48662bdb5d26104caccec77e4740`)
  - Ready-to-download package for **GMTCNT GHS-070E HMI** (`GMTPDesignerDownLoad.exe` via USB port).
  - Mode button displays **`Man. running`** (`vana = 0`) and **`Auto running`** (`vana = 1`).
  - All 8 Valve touch buttons (`0X:9..16` / `QP`) have aligned `BitButton` (`0x0303`) pointers (`+134 = 0`, `+138 = new_off + 146`).
- `HMI(070E)_FINAL/tar/HMI0/HMI0.hmi` (3,176,289 bytes, Header Checksum `@16 = 258792911`)
  - Compiled HMI runtime binary embedded inside `HMI(070E).pkgx`.
- `PLC(196R)_FINAL/ladder_patched.bin` & `ladder.bin` (22,400 bytes, STM32 `CRC32 = 2394708402`, Live PLC `Chks = -1900258894`)
  - Compiled Cortex-M4 PLC firmware binary for **GMTCNT GLC-196R** (`192.168.1.240`).
  - **Physical Solenoid Valve Remapping (`Zone 1..8 -> Physical Valve 1..8`):**
    - Zone 1 (`1+9+17`, `0X:9`)  -> `QP[0]`  (`CPU QP0`, Physical Valve 1)
    - Zone 2 (`2+10+18`, `0X:10`) -> `QP[1]`  (`CPU QP1`, Physical Valve 2)
    - Zone 3 (`3+11+19`, `0X:11`) -> `QP[23]` (`Exp01 QP7`, Physical Valve 3, previously 8)
    - Zone 4 (`4+12+20`, `0X:12`) -> `QP[22]` (`Exp01 QP6`, Physical Valve 4, previously 7)
    - Zone 5 (`5+13+21`, `0X:13`) -> `QP[2]`  (`CPU QP2`, Physical Valve 5, previously 3)
    - Zone 6 (`6+14+22`, `0X:14`) -> `QP[3]`  (`CPU QP3`, Physical Valve 6, previously 4)
    - Zone 7 (`7+15+23`, `0X:15`) -> `QP[4]`  (`CPU QP4`, Physical Valve 7, previously 5)
    - Zone 8 (`8+16+24`, `0X:16`) -> `QP[5]`  (`CPU QP5`, Physical Valve 8, previously 6)
  - **Manual Mode (`vana = 0`, `Man. running`):** Touching the valve icon on the HMI toggles the solenoid valve ON (green) and OFF (red) freely; moisture thresholds do not override it.
  - **Auto Mode (`vana = 1`, `Auto running`):** Touching the valve icon on the HMI is blocked by the PLC (`< 1 ms` scan cycle); the valve turns ON automatically when the 3-plot average soil moisture (`son_ortlama`) is `<= 45%` and turns OFF when `>= 80%`.
- `PLC(196R)_FINAL/ladder_patched.c` & `ladder.c` (158,919 bytes)
  - Full C source code for the GLC-196R PLC runtime.
- `PLC(196R)_FINAL/restore_and_flash_plc.py`
  - Standalone Python script to flash `ladder_patched.bin` directly to PLC `192.168.1.240` (Port 23 + Port 61163).
