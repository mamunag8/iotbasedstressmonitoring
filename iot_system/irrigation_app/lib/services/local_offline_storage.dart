// Offline-First Local Storage & Command/Telemetry Queue for Android, iOS, Windows & Web.
// Ensures that when internet is disconnected:
// 1. Live telemetry read directly from the PLC (192.168.1.240:502) or cached from Cloud is saved locally.
// 2. Valve control commands & moisture threshold changes made offline are queued locally.
// 3. Everything automatically syncs to the Coolify Cloud Server (http://77.42.89.186:8000) when internet returns.

import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/telemetry_models.dart';

class LocalOfflineStorage {
  static const String _keyLatestSnapshot = 'ziraat_latest_snapshot_v1';
  static const String _keyUnsyncedBatches = 'ziraat_unsynced_batches_v1';
  static const String _keyLastBatchSavedMs = 'ziraat_last_batch_saved_ms_v1';
  static const int saveIntervalMs = 5 * 60 * 1000; // 5 minutes (300,000 ms)
  static const String _keyPendingCommands = 'ziraat_pending_commands_v1';
  static const String _keyCloudUrl = 'ziraat_cloud_url_v1';
  static const String _keyLocalEdgeUrl = 'ziraat_local_edge_url_v1';
  static const String _keyPlcIp = 'ziraat_plc_ip_v1';
  static const String _keyLanguage = 'ziraat_app_language_v1';

  Future<String> loadLanguage() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_keyLanguage) ?? 'en';
  }

  Future<void> saveLanguage(String langCode) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_keyLanguage, langCode);
  }

  Future<void> saveLatestSnapshot(TelemetrySnapshot snapshot) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_keyLatestSnapshot, jsonEncode(snapshot.toJson()));
  }

  Future<TelemetrySnapshot?> loadLatestSnapshot() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_keyLatestSnapshot);
    if (raw == null || raw.isEmpty) return null;
    try {
      return TelemetrySnapshot.fromJson(jsonDecode(raw) as Map<String, dynamic>);
    } catch (_) {
      return null;
    }
  }

  Future<void> enqueueOfflineBatch(
    TelemetrySnapshot snapshot, {
    bool force = false,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    final nowMs = DateTime.now().millisecondsSinceEpoch;
    final lastSavedMs = prefs.getInt(_keyLastBatchSavedMs) ?? 0;
    if (!force && (nowMs - lastSavedMs) < saveIntervalMs) {
      return; // Enforce 5-minute (300s) saving cadence
    }
    final list = prefs.getStringList(_keyUnsyncedBatches) ?? <String>[];
    // Cap local phone buffer at 1000 snapshots (~15 MB max, ~3.5 days of 5-min data)
    if (list.length >= 1000) {
      list.removeAt(0);
    }
    list.add(jsonEncode(snapshot.toJson()));
    await prefs.setStringList(_keyUnsyncedBatches, list);
    await prefs.setInt(_keyLastBatchSavedMs, nowMs);
  }

  Future<List<Map<String, dynamic>>> getUnsyncedBatches() async {
    final prefs = await SharedPreferences.getInstance();
    final list = prefs.getStringList(_keyUnsyncedBatches) ?? <String>[];
    return list
        .map((e) => jsonDecode(e) as Map<String, dynamic>)
        .toList();
  }

  Future<void> clearSyncedBatches(int countUploaded) async {
    final prefs = await SharedPreferences.getInstance();
    final list = prefs.getStringList(_keyUnsyncedBatches) ?? <String>[];
    if (countUploaded >= list.length) {
      await prefs.remove(_keyUnsyncedBatches);
    } else {
      await prefs.setStringList(
        _keyUnsyncedBatches,
        list.sublist(countUploaded),
      );
    }
  }

  Future<void> enqueueOfflineCommand(Map<String, dynamic> cmd) async {
    final prefs = await SharedPreferences.getInstance();
    final list = prefs.getStringList(_keyPendingCommands) ?? <String>[];
    list.add(jsonEncode(cmd));
    await prefs.setStringList(_keyPendingCommands, list);
  }

  Future<List<Map<String, dynamic>>> getPendingOfflineCommands() async {
    final prefs = await SharedPreferences.getInstance();
    final list = prefs.getStringList(_keyPendingCommands) ?? <String>[];
    return list
        .map((e) => jsonDecode(e) as Map<String, dynamic>)
        .toList();
  }

  Future<void> clearPendingOfflineCommands() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_keyPendingCommands);
  }

  Future<Map<String, String>> loadConnectionSettings() async {
    final prefs = await SharedPreferences.getInstance();
    return {
      'cloudUrl':
          prefs.getString(_keyCloudUrl) ?? 'https://iotserver.ertanyildirim.com',
      'localEdgeUrl':
          prefs.getString(_keyLocalEdgeUrl) ?? 'http://192.168.1.100:8080',
      'plcIp': prefs.getString(_keyPlcIp) ?? '192.168.1.240',
    };
  }

  Future<void> saveConnectionSettings({
    required String cloudUrl,
    required String localEdgeUrl,
    required String plcIp,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_keyCloudUrl, cloudUrl.trim());
    await prefs.setString(_keyLocalEdgeUrl, localEdgeUrl.trim());
    await prefs.setString(_keyPlcIp, plcIp.trim());
  }
}
