import 'package:flutter_test/flutter_test.dart';
import 'package:ziraat_irrigation_app/models/telemetry_models.dart';
import 'package:ziraat_irrigation_app/services/plc_direct_modbus.dart';

void main() {
  test('IEEE-754 float decode and GLC-196R coil mapping test', () {
    // 48.0 in IEEE-754 little-endian word order: 0x0000, 0x4240
    final val = DirectPlcModbusClient.decodeIeee754Float(0x0000, 0x4240);
    expect(val, closeTo(48.0, 0.01));

    // Verify vana6 = Coil 7 and vana7 = Coil 6 per PLC(196R).gpf.csv
    expect(DirectPlcModbusClient.zoneCoils[6], equals(7));
    expect(DirectPlcModbusClient.zoneCoils[7], equals(6));
  });

  test('TelemetrySnapshot JSON roundtrip', () {
    final sample = {
      'batch_id': 'test_1',
      'recorded_at': '2026-11-01T10:00:00Z',
      'source': 'edge_laptop',
      'plc_online': true,
      'zones': [
        {
          'zone_id': 1,
          'name_tr': 'Bölge 1 (Parsel 1-9-17)',
          'name_en': 'Zone 1',
          'valve_tag': 'vana1',
          'valve_coil': 1,
          'relay_tag': 'dc1',
          'valve_open': true,
          'auto_mode': true,
          'min_moisture': 48.0,
          'max_moisture': 90.0,
          'avg_soil_moisture': 55.2,
          'avg_soil_temp': 21.4,
          'avg_soil_ec': 480.0,
          'avg_soil_salt': 264.0,
          'avg_leaf_humidity': 62.1,
          'avg_leaf_temp': 22.8,
          'sensor_ids': [1, 9, 17],
        }
      ],
      'sensors': [
        {
          'sensor_id': 1,
          'zone_id': 1,
          'soil_name': 'R1',
          'leaf_name': 'R1_L',
          'soil_moisture': 55.2,
          'soil_temp': 21.4,
          'soil_ec': 480,
          'soil_salt': 264,
          'leaf_humidity': 62.1,
          'leaf_temp': 22.8,
        }
      ],
      'valves': {'vana1': true},
    };

    final snap = TelemetrySnapshot.fromJson(sample);
    expect(snap.zones.first.valveOpen, isTrue);
    expect(snap.sensors.first.soilMoisture, closeTo(55.2, 0.01));
  });
}
