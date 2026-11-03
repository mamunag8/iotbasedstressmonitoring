# iotbasedstressmonitoring

**Atatürk University Faculty of Agriculture — Continuous IoT-based Stress Monitoring and Automatic Fertigation Controlling System**

## Repository Structure (Website, Cloud/Edge Backend & Final Telemetry Data)

- **`iot_system/cloud_backend/`**:
  - `app/dashboard.html`: Main interactive web dashboard (8 Drip Fertigation & Irrigation Lines, 32 Replicate & Drip-Only Plots with live drip irrigation animation, Multi-Mode Historical Graph Studio, 48-Sensor Matrix, and Excel/CSV Export Center).
  - `app/stress_studio.html`: PhD Biophysical Plant Stress & Biostimulant Recovery Studio.
  - `app/main.py`: FastAPI backend server for telemetry ingestion, live PLC/HMI hardware status verification, valve/mode control, and historical data aggregation.
  - `app/database.py`: SQLite/PostgreSQL telemetry database engine.
  - `app/plc_map.py`: GMTSoft GLC-196R PLC & GHS-070E HMI Modbus register map (24 Soil + 24 Leaf RS485 sensors, 8 solenoid valves).
  - `app/stress_engine.py`: Biophysical stress & recovery computation engine.
  - `Dockerfile` & `docker-compose.yml`: Cloud deployment configuration.
- **`iot_system/edge_agent/`**:
  - `local_buffer_sync.py`: Edge agent daemon & local web server (`http://localhost:8080`) with offline SQLite buffering and live cloud synchronization.
  - `plc_modbus_client.py`: Direct Modbus TCP / Telnet client for GLC-196R PLC (`192.168.1.240`).
  - `hmi_pendrive_scraper.py` & `export_all48_excel_csv.py`: USB pendrive telemetry scraper and 48-sensor Excel/CSV exporter.
  - `data/`: Exported 48-sensor every-minute CSV/Excel datasets (`All_48_Sensors_Every_Minute_Data.csv`, `All_48_Sensors_Every_Minute_Data.xlsx`, `plc_live_telemetry_log.csv`).
- **`data/`**:
  - `irrigation_cloud.db`: Final historical telemetry SQLite database.
