// Smart 3-Tier Connection & Sync Manager for Ziraat Fakultesi Otomatik Sulama Sistemi
// Tier 1: Cloud Server (https://iotserver.ertanyildirim.com / https://iotserver.mmreza.com / http://77.42.89.186:8000)
// Tier 2: Local Laptop Edge Agent on Mobile Hotspot / LAN (http://192.168.1.100:8080)
// Tier 3: Direct PLC Modbus TCP on Wi-Fi Router (192.168.1.240:502)
// Tier 4: Offline Local Cache & Store-and-Forward Queue

import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;

import '../l10n/app_translations.dart';
import '../models/telemetry_models.dart';
import 'local_offline_storage.dart';
import 'plc_direct_modbus.dart';

enum ConnectionTier {
  cloudOnline,
  localEdgeLan,
  directPlcModbus,
  offlineCached,
}

class IrrigationApiService {
  static const List<String> cloudFallbackUrls = [
    'https://iotserver.ertanyildirim.com',
    'https://iotserver.mmreza.com',
    'http://77.42.89.186:8000',
  ];

  String cloudUrl;
  String localEdgeUrl;
  String plcIp;
  final LocalOfflineStorage storage;

  ConnectionTier activeTier = ConnectionTier.offlineCached;
  int totalServerReadings = 0;
  int unsyncedLocalCount = 0;

  IrrigationApiService({
    this.cloudUrl = 'https://iotserver.ertanyildirim.com',
    this.localEdgeUrl = 'http://192.168.1.100:8080',
    this.plcIp = '192.168.1.240',
    LocalOfflineStorage? storage,
  }) : storage = storage ?? LocalOfflineStorage();

  Future<void> initSettings() async {
    final cfg = await storage.loadConnectionSettings();
    cloudUrl = cfg['cloudUrl']!;
    localEdgeUrl = cfg['localEdgeUrl']!;
    plcIp = cfg['plcIp']!;
    final unsynced = await storage.getUnsyncedBatches();
    unsyncedLocalCount = unsynced.length;
  }

  List<String> _orderedCloudUrls() {
    final urls = <String>[cloudUrl];
    for (final u in cloudFallbackUrls) {
      if (!urls.contains(u)) urls.add(u);
    }
    return urls;
  }

  /// Polls the best available tier, caches locally, and syncs any offline queue if Cloud is reachable.
  Future<TelemetrySnapshot?> fetchLatestAndSync() async {
    // 1. Try Cloud Server (Primary + Automatic Subdomain/IP Fallbacks)
    for (final baseUrl in _orderedCloudUrls()) {
      try {
        await _flushOfflineQueueToCloud(baseUrl);
        final res = await http
            .get(Uri.parse('$baseUrl/api/v1/telemetry/latest'))
            .timeout(const Duration(seconds: 3));
        if (res.statusCode == 200) {
          final body = jsonDecode(res.body) as Map<String, dynamic>;
          activeTier = ConnectionTier.cloudOnline;
          totalServerReadings =
              ((body['stats'] as Map<String, dynamic>?)?['total_sensor_readings'] as num?)
                      ?.toInt() ??
                  0;
          final tel = body['telemetry'] as Map<String, dynamic>?;
          if (tel != null) {
            final snap = TelemetrySnapshot.fromJson(tel);
            await storage.saveLatestSnapshot(snap);
            return snap;
          }
          return null;
        }
      } catch (_) {
        // Try next cloud mirror or fall through to Local LAN / Direct PLC
      }
    }

    // 2. Try Local Laptop Edge Agent over Hotspot/LAN (http://192.168.1.100:8080)
    try {
      final res = await http
          .get(Uri.parse('$localEdgeUrl/api/v1/telemetry/latest'))
          .timeout(const Duration(milliseconds: 1800));
      if (res.statusCode == 200) {
        final body = jsonDecode(res.body) as Map<String, dynamic>;
        activeTier = ConnectionTier.localEdgeLan;
        final tel = body['telemetry'] as Map<String, dynamic>?;
        if (tel != null) {
          final snap = TelemetrySnapshot.fromJson(tel);
          await storage.saveLatestSnapshot(snap);
          await storage.enqueueOfflineBatch(snap);
          unsyncedLocalCount = (await storage.getUnsyncedBatches()).length;
          return snap;
        }
        return null;
      }
    } catch (_) {
      // Local Edge Agent unreachable -> fall through to Direct PLC Modbus TCP
    }

    // 3. Try Direct PLC Modbus TCP (192.168.1.240:502) over on-site Wi-Fi router
    try {
      final directPlc = DirectPlcModbusClient(plcIp: plcIp, plcPort: 502);
      final snap = await directPlc.pollDirectFromPlc();
      if (snap != null) {
        activeTier = ConnectionTier.directPlcModbus;
        await storage.saveLatestSnapshot(snap);
        await storage.enqueueOfflineBatch(snap);
        unsyncedLocalCount = (await storage.getUnsyncedBatches()).length;
        return snap;
      }
    } catch (_) {
      // Direct PLC unreachable -> fall back to local device cache
    }

    // 4. Offline Cached Mode
    activeTier = ConnectionTier.offlineCached;
    unsyncedLocalCount = (await storage.getUnsyncedBatches()).length;
    return await storage.loadLatestSnapshot();
  }

  Future<void> _flushOfflineQueueToCloud(String baseUrl) async {
    final pendingCmds = await storage.getPendingOfflineCommands();
    for (final cmd in pendingCmds) {
      final endpoint = cmd['type'] == 'threshold'
          ? '$baseUrl/api/v1/control/zone-config'
          : '$baseUrl/api/v1/control/valve';
      await http
          .post(
            Uri.parse(endpoint),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(cmd['payload']),
          )
          .timeout(const Duration(seconds: 3));
    }
    if (pendingCmds.isNotEmpty) {
      await storage.clearPendingOfflineCommands();
    }

    final unsynced = await storage.getUnsyncedBatches();
    if (unsynced.isNotEmpty) {
      final batchSlice = unsynced.take(100).toList();
      final res = await http
          .post(
            Uri.parse('$baseUrl/api/v1/telemetry/sync'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'device_id': 'flutter_mobile_offline_sync',
              'batches': batchSlice,
            }),
          )
          .timeout(const Duration(seconds: 5));
      if (res.statusCode == 200) {
        await storage.clearSyncedBatches(batchSlice.length);
      }
    }
    unsyncedLocalCount = (await storage.getUnsyncedBatches()).length;
  }

  Future<String> controlValve({
    required int zoneId,
    bool? valveOpen,
    bool? autoMode,
    String lang = 'en',
  }) async {
    final payload = <String, dynamic>{
      'zone_id': zoneId,
      if (valveOpen != null) 'valve_open': valveOpen,
      if (autoMode != null) 'auto_mode': autoMode,
      'requested_by': 'flutter_mobile_app',
    };

    // Try Cloud Server first (Primary + Fallbacks)
    for (final baseUrl in _orderedCloudUrls()) {
      try {
        final res = await http
            .post(
              Uri.parse('$baseUrl/api/v1/control/valve'),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode(payload),
            )
            .timeout(const Duration(seconds: 3));
        if (res.statusCode == 200) {
          return AppTranslations.tr(
            lang,
            'cmd_sent_live',
            params: {'zone': zoneId.toString()},
          );
        }
      } catch (_) {}
    }

    // Try Local Edge Agent on Hotspot/LAN
    try {
      final res = await http
          .post(
            Uri.parse('$localEdgeUrl/api/v1/control/valve'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(payload),
          )
          .timeout(const Duration(milliseconds: 1800));
      if (res.statusCode == 200) {
        return AppTranslations.tr(
          lang,
          'cmd_sent_live',
          params: {'zone': zoneId.toString()},
        );
      }
    } catch (_) {}

    // Try Direct PLC Modbus TCP (192.168.1.240:502)
    if (valveOpen != null) {
      final directPlc = DirectPlcModbusClient(plcIp: plcIp, plcPort: 502);
      final ok = await directPlc.writeValveCoil(zoneId, valveOpen);
      if (ok) {
        return AppTranslations.tr(
          lang,
          'cmd_sent_live',
          params: {'zone': zoneId.toString()},
        );
      }
    }

    // Queue locally for when internet returns
    await storage.enqueueOfflineCommand({'type': 'valve', 'payload': payload});
    return AppTranslations.tr(
      lang,
      'cmd_queued_offline',
      params: {'zone': zoneId.toString()},
    );
  }
}
