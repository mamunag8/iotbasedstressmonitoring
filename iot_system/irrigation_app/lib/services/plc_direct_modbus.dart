// Direct Modbus TCP Client in pure Dart for Android / iOS / Windows Field Offline Mode.
// When the mobile phone is connected to the on-site Wi-Fi router (or hotspot) and
// internet is disconnected, the app talks directly to GMTCNT GLC-196R (192.168.1.240:502),
// decodes all 24 Soil + 24 Leaf sensors & 8 valves, saves snapshots locally on the phone,
// and syncs them to the Coolify Cloud Server (77.42.89.186:8000) when internet returns.

import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import '../models/telemetry_models.dart';

class DirectPlcModbusClient {
  final String plcIp;
  final int plcPort;
  final int unitId;
  int _txId = 1;

  DirectPlcModbusClient({
    this.plcIp = '192.168.1.240',
    this.plcPort = 502,
    this.unitId = 1,
  });

  static const Map<int, int> ecRegisters = {
    1: 3, 2: 7, 3: 81, 4: 80, 5: 79, 6: 78,
    7: 77, 8: 76, 9: 75, 10: 96, 11: 95, 12: 94,
    13: 93, 14: 91, 15: 92, 16: 90, 17: 89, 18: 88,
    19: 87, 20: 86, 21: 85, 22: 84, 23: 83, 24: 82,
  };

  static const Map<int, int> saltRegisters = {
    1: 4, 2: 8, 3: 37, 4: 36, 5: 35, 6: 34,
    7: 33, 8: 32, 9: 31, 10: 52, 11: 51, 12: 50,
    13: 49, 14: 48, 15: 47, 16: 46, 17: 45, 18: 44,
    19: 43, 20: 42, 21: 41, 22: 40, 23: 39, 24: 38,
  };

  static const Map<int, int> zoneCoils = {
    1: 1,
    2: 2,
    3: 3,
    4: 4,
    5: 5,
    6: 7, // vana6 = Coil 7 in PLC(196R).gpf.csv
    7: 6, // vana7 = Coil 6 in PLC(196R).gpf.csv
    8: 8,
  };

  static const Map<int, String> zoneRelays = {
    1: 'dc1',
    2: 'dc2',
    3: 'dc14',
    4: 'dc13',
    5: 'dc3',
    6: 'dc4',
    7: 'dc5',
    8: 'dc6',
  };

  static double decodeIeee754Float(int regLow, int regHigh) {
    final bd = ByteData(4);
    bd.setUint16(0, regLow & 0xFFFF, Endian.little);
    bd.setUint16(2, regHigh & 0xFFFF, Endian.little);
    final val = bd.getFloat32(0, Endian.little);
    if (val.isNaN || val.isInfinite || val.abs() > 10000) return 0.0;
    return double.parse(val.toStringAsFixed(2));
  }

  Future<Uint8List?> _sendModbusRequest(Uint8List pdu) async {
    Socket? socket;
    try {
      socket = await Socket.connect(
        plcIp,
        plcPort,
        timeout: const Duration(milliseconds: 1200),
      );
      _txId = (_txId + 1) & 0xFFFF;
      final mbap = ByteData(7);
      mbap.setUint16(0, _txId, Endian.big);
      mbap.setUint16(2, 0, Endian.big); // Protocol ID = 0
      mbap.setUint16(4, pdu.length + 1, Endian.big);
      mbap.setUint8(6, unitId);

      final packet = BytesBuilder();
      packet.add(mbap.buffer.asUint8List());
      packet.add(pdu);

      final completer = Completer<Uint8List?>();
      final sub = socket.listen(
        (data) {
          if (!completer.isCompleted) {
            completer.complete(Uint8List.fromList(data));
          }
        },
        onError: (_) {
          if (!completer.isCompleted) completer.complete(null);
        },
        onDone: () {
          if (!completer.isCompleted) completer.complete(null);
        },
      );

      socket.add(packet.toBytes());
      await socket.flush();

      final resp = await completer.future.timeout(
        const Duration(milliseconds: 1500),
        onTimeout: () => null,
      );
      await sub.cancel();
      return resp;
    } catch (_) {
      return null;
    } finally {
      socket?.destroy();
    }
  }

  Future<List<int>?> readHoldingRegisters(int startCsvAddr, int count) async {
    final pduAddr = startCsvAddr > 0 ? startCsvAddr - 1 : 0;
    final pdu = ByteData(5);
    pdu.setUint8(0, 0x03); // FC03 Read Holding Registers
    pdu.setUint16(1, pduAddr, Endian.big);
    pdu.setUint16(3, count, Endian.big);

    final resp = await _sendModbusRequest(pdu.buffer.asUint8List());
    if (resp == null || resp.length < 9 + count * 2) return null;
    if (resp[7] != 0x03) return null;

    final bd = ByteData.sublistView(resp, 9);
    return List<int>.generate(count, (i) => bd.getUint16(i * 2, Endian.big));
  }

  Future<List<bool>?> readCoils(int startCsvAddr, int count) async {
    final pduAddr = startCsvAddr > 0 ? startCsvAddr - 1 : 0;
    final pdu = ByteData(5);
    pdu.setUint8(0, 0x01); // FC01 Read Coils
    pdu.setUint16(1, pduAddr, Endian.big);
    pdu.setUint16(3, count, Endian.big);

    final resp = await _sendModbusRequest(pdu.buffer.asUint8List());
    if (resp == null || resp.length < 10) return null;
    if (resp[7] != 0x01) return null;

    final bits = <bool>[];
    for (int i = 0; i < count; i++) {
      final byteIdx = 9 + (i ~/ 8);
      final bitIdx = i % 8;
      bits.add(((resp[byteIdx] >> bitIdx) & 1) == 1);
    }
    return bits;
  }

  Future<bool> writeValveCoil(int zoneId, bool openState) async {
    // Switch zone to Manual mode (0X:1..8 = False) and write Physical Valve Coil (0X:9..16)
    final modeCoilAddr = zoneCoils[zoneId] ?? zoneId;
    final modePdu = ByteData(5);
    modePdu.setUint8(0, 0x05);
    modePdu.setUint16(1, modeCoilAddr - 1, Endian.big);
    modePdu.setUint16(3, 0x0000, Endian.big);
    await _sendModbusRequest(modePdu.buffer.asUint8List());

    final physValveCoil = 8 + zoneId; // 0X:9..16
    final pduAddr = physValveCoil - 1;
    final pdu = ByteData(5);
    pdu.setUint8(0, 0x05); // FC05 Write Single Coil
    pdu.setUint16(1, pduAddr, Endian.big);
    pdu.setUint16(3, openState ? 0xFF00 : 0x0000, Endian.big);

    final resp = await _sendModbusRequest(pdu.buffer.asUint8List());
    return resp != null && resp.length >= 12 && resp[7] == 0x05;
  }

  Future<TelemetrySnapshot?> pollDirectFromPlc() async {
    final ecSaltRegs = await readHoldingRegisters(3, 94);
    if (ecSaltRegs == null) return null;
    final floatBlock1 = await readHoldingRegisters(2001, 96);
    final floatBlock2 = await readHoldingRegisters(2097, 96);
    final coils = await readCoils(1, 16);
    if (floatBlock1 == null || floatBlock2 == null || coils == null) return null;

    final floatRegs = <int>[...floatBlock1, ...floatBlock2];

    int getHr16(int csvAddr) {
      final idx = csvAddr - 3;
      return (idx >= 0 && idx < ecSaltRegs.length) ? ecSaltRegs[idx] : 0;
    }

    double getHrFloat(int csvAddr) {
      final idx = csvAddr - 2001;
      return (idx >= 0 && idx < floatRegs.length - 1)
          ? decodeIeee754Float(floatRegs[idx], floatRegs[idx + 1])
          : 0.0;
    }

    final sensors = <SensorReading>[];
    for (int n = 1; n <= 24; n++) {
      final zid = ((n - 1) % 8) + 1;
      sensors.add(
        SensorReading(
          sensorId: n,
          zoneId: zid,
          soilName: 'R$n',
          leafName: 'R${n}_L',
          soilSlaveId: n,
          leafSlaveId: 100 + n,
          soilMoisture: getHrFloat(2001 + (n - 1) * 8),
          soilTemp: getHrFloat(2003 + (n - 1) * 8),
          soilEc: getHr16(ecRegisters[n]!),
          soilSalt: getHr16(saltRegisters[n]!),
          soilPh: null,
          leafHumidity: getHrFloat(2005 + (n - 1) * 8),
          leafTemp: getHrFloat(2007 + (n - 1) * 8),
        ),
      );
    }

    final valves = <String, bool>{};
    final zones = <ZoneSummary>[];
    for (int zid = 1; zid <= 8; zid++) {
      final coilAddr = zoneCoils[zid]!;
      final isAutoMode = (coilAddr - 1 < coils.length) ? coils[coilAddr - 1] : true;
      final physCoilIdx = (8 + zid) - 1; // 0X:9..16 -> physical valve relay state
      final isOpen = (physCoilIdx < coils.length) ? coils[physCoilIdx] : false;
      final vTag = 'vana$zid';
      valves[vTag] = isOpen;

      final zSensors = sensors.where((s) => s.zoneId == zid).toList();
      final cnt = zSensors.isEmpty ? 1 : zSensors.length;
      final sIds = zSensors.map((s) => s.sensorId).toList();

      zones.add(
        ZoneSummary(
          zoneId: zid,
          nameTr: 'Bölge $zid (Parsel ${sIds.join("-")})',
          nameEn: 'Zone $zid (Plots ${sIds.join("-")})',
          valveTag: vTag,
          valveCoil: coilAddr,
          relayTag: zoneRelays[zid]!,
          valveOpen: isOpen,
          autoMode: isAutoMode,
          minMoisture: 45.0,
          maxMoisture: 80.0,
          avgSoilMoisture: zSensors.fold(0.0, (a, b) => a + (b.soilMoisture ?? 0.0)) / cnt,
          avgSoilTemp: zSensors.fold(0.0, (a, b) => a + (b.soilTemp ?? 0.0)) / cnt,
          avgSoilEc: zSensors.fold(0.0, (a, b) => a + (b.soilEc ?? 0)) / cnt,
          avgSoilSalt: zSensors.fold(0.0, (a, b) => a + (b.soilSalt ?? 0)) / cnt,
          avgSoilPh: null,
          avgLeafHumidity: zSensors.fold(0.0, (a, b) => a + (b.leafHumidity ?? 0.0)) / cnt,
          avgLeafTemp: zSensors.fold(0.0, (a, b) => a + (b.leafTemp ?? 0.0)) / cnt,
          sensorIds: sIds,
        ),
      );
    }

    final nowIso = DateTime.now().toUtc().toIso8601String();
    return TelemetrySnapshot(
      batchId: 'mobile_direct_${DateTime.now().millisecondsSinceEpoch}',
      recordedAt: nowIso,
      source: 'mobile_direct_plc',
      plcOnline: true,
      zones: zones,
      sensors: sensors,
      valves: valves,
    );
  }
}
