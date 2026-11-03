// Exact Data Models for Ataturk University Ziraat Fakultesi Otomatik Sulama Sistemi
// Hardware: GMTCNT GLC-196R PLC (192.168.1.240:502) + 070E HMI
// 8 Irrigation Zones (vana1..vana8), 24 Soil Sensors (R1..R24, Slave IDs 1..24),
// 24 Leaf Sensors (R1_L..R24_L, Slave IDs 101..124: L_humidity & L_temp)

class SensorReading {
  final int sensorId;
  final int zoneId;
  final String soilName;
  final String leafName;
  final int soilSlaveId;
  final int leafSlaveId;
  final double? soilMoisture;
  final double? soilTemp;
  final int? soilEc;
  final int? soilSalt;
  final double? soilPh;
  final double? leafHumidity;
  final double? leafTemp;

  const SensorReading({
    required this.sensorId,
    required this.zoneId,
    required this.soilName,
    required this.leafName,
    required this.soilSlaveId,
    required this.leafSlaveId,
    this.soilMoisture,
    this.soilTemp,
    this.soilEc,
    this.soilSalt,
    this.soilPh,
    this.leafHumidity,
    this.leafTemp,
  });

  factory SensorReading.fromJson(Map<String, dynamic> json) {
    final id = (json['sensor_id'] as num).toInt();
    return SensorReading(
      sensorId: id,
      zoneId: (json['zone_id'] as num).toInt(),
      soilName: (json['soil_name'] as String?) ?? 'R$id',
      leafName: (json['leaf_name'] as String?) ?? 'R${id}_L',
      soilSlaveId: (json['soil_slave_id'] as num?)?.toInt() ?? id,
      leafSlaveId: (json['leaf_slave_id'] as num?)?.toInt() ?? (100 + id),
      soilMoisture: (json['soil_moisture'] as num?)?.toDouble(),
      soilTemp: (json['soil_temp'] as num?)?.toDouble(),
      soilEc: (json['soil_ec'] as num?)?.toInt(),
      soilSalt: (json['soil_salt'] as num?)?.toInt(),
      soilPh: (json['soil_ph'] as num?)?.toDouble(),
      leafHumidity: (json['leaf_humidity'] as num?)?.toDouble(),
      leafTemp: (json['leaf_temp'] as num?)?.toDouble(),
    );
  }

  Map<String, dynamic> toJson() => {
        'sensor_id': sensorId,
        'zone_id': zoneId,
        'soil_name': soilName,
        'leaf_name': leafName,
        'soil_slave_id': soilSlaveId,
        'leaf_slave_id': leafSlaveId,
        'soil_moisture': soilMoisture,
        'soil_temp': soilTemp,
        'soil_ec': soilEc,
        'soil_salt': soilSalt,
        'soil_ph': soilPh,
        'leaf_humidity': leafHumidity,
        'leaf_temp': leafTemp,
      };
}

class ZoneSummary {
  final int zoneId;
  final String nameTr;
  final String nameEn;
  final String valveTag;
  final int valveCoil;
  final String relayTag;
  final bool valveOpen;
  final bool autoMode;
  final double minMoisture;
  final double maxMoisture;
  final double? avgSoilMoisture;
  final double? avgSoilTemp;
  final double? avgSoilEc;
  final double? avgSoilSalt;
  final double? avgSoilPh;
  final double? avgLeafHumidity;
  final double? avgLeafTemp;
  final List<int> sensorIds;

  const ZoneSummary({
    required this.zoneId,
    required this.nameTr,
    required this.nameEn,
    required this.valveTag,
    required this.valveCoil,
    required this.relayTag,
    required this.valveOpen,
    required this.autoMode,
    required this.minMoisture,
    required this.maxMoisture,
    this.avgSoilMoisture,
    this.avgSoilTemp,
    this.avgSoilEc,
    this.avgSoilSalt,
    this.avgSoilPh,
    this.avgLeafHumidity,
    this.avgLeafTemp,
    required this.sensorIds,
  });

  factory ZoneSummary.fromJson(Map<String, dynamic> json) {
    return ZoneSummary(
      zoneId: (json['zone_id'] as num).toInt(),
      nameTr: (json['name_tr'] as String?) ?? 'Bölge ${json['zone_id']}',
      nameEn: (json['name_en'] as String?) ?? 'Zone ${json['zone_id']}',
      valveTag: (json['valve_tag'] as String?) ?? 'vana${json['zone_id']}',
      valveCoil: (json['valve_coil'] as num?)?.toInt() ?? 1,
      relayTag: (json['relay_tag'] as String?) ?? 'dc${json['zone_id']}',
      valveOpen: json['valve_open'] == true,
      autoMode: json['auto_mode'] != false,
      minMoisture: (json['min_moisture'] as num?)?.toDouble() ?? 48.0,
      maxMoisture: (json['max_moisture'] as num?)?.toDouble() ?? 90.0,
      avgSoilMoisture: (json['avg_soil_moisture'] as num?)?.toDouble(),
      avgSoilTemp: (json['avg_soil_temp'] as num?)?.toDouble(),
      avgSoilEc: (json['avg_soil_ec'] as num?)?.toDouble(),
      avgSoilSalt: (json['avg_soil_salt'] as num?)?.toDouble(),
      avgSoilPh: (json['avg_soil_ph'] as num?)?.toDouble(),
      avgLeafHumidity: (json['avg_leaf_humidity'] as num?)?.toDouble(),
      avgLeafTemp: (json['avg_leaf_temp'] as num?)?.toDouble(),
      sensorIds: ((json['sensor_ids'] as List<dynamic>?) ?? [])
          .map((e) => (e as num).toInt())
          .toList(),
    );
  }

  Map<String, dynamic> toJson() => {
        'zone_id': zoneId,
        'name_tr': nameTr,
        'name_en': nameEn,
        'valve_tag': valveTag,
        'valve_coil': valveCoil,
        'relay_tag': relayTag,
        'valve_open': valveOpen,
        'auto_mode': autoMode,
        'min_moisture': minMoisture,
        'max_moisture': maxMoisture,
        'avg_soil_moisture': avgSoilMoisture,
        'avg_soil_temp': avgSoilTemp,
        'avg_soil_ec': avgSoilEc,
        'avg_soil_salt': avgSoilSalt,
        'avg_soil_ph': avgSoilPh,
        'avg_leaf_humidity': avgLeafHumidity,
        'avg_leaf_temp': avgLeafTemp,
        'sensor_ids': sensorIds,
      };
}

class TelemetrySnapshot {
  final String batchId;
  final String recordedAt;
  final String source;
  final bool plcOnline;
  final List<ZoneSummary> zones;
  final List<SensorReading> sensors;
  final Map<String, bool> valves;

  const TelemetrySnapshot({
    required this.batchId,
    required this.recordedAt,
    required this.source,
    required this.plcOnline,
    required this.zones,
    required this.sensors,
    required this.valves,
  });

  factory TelemetrySnapshot.fromJson(Map<String, dynamic> json) {
    final rawValves = (json['valves'] as Map<String, dynamic>?) ?? {};
    return TelemetrySnapshot(
      batchId: (json['batch_id'] as String?) ??
          DateTime.now().millisecondsSinceEpoch.toString(),
      recordedAt: (json['recorded_at'] as String?) ??
          DateTime.now().toUtc().toIso8601String(),
      source: (json['source'] as String?) ?? 'cloud',
      plcOnline: json['plc_online'] != false,
      zones: ((json['zones'] as List<dynamic>?) ?? [])
          .map((z) => ZoneSummary.fromJson(z as Map<String, dynamic>))
          .toList(),
      sensors: ((json['sensors'] as List<dynamic>?) ?? [])
          .map((s) => SensorReading.fromJson(s as Map<String, dynamic>))
          .toList(),
      valves: rawValves.map((k, v) => MapEntry(k, v == true)),
    );
  }

  Map<String, dynamic> toJson() => {
        'batch_id': batchId,
        'recorded_at': recordedAt,
        'source': source,
        'plc_online': plcOnline,
        'zones': zones.map((z) => z.toJson()).toList(),
        'sensors': sensors.map((s) => s.toJson()).toList(),
        'valves': valves,
      };
}
