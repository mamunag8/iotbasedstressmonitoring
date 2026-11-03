import 'dart:async';
import 'package:flutter/material.dart';

import 'l10n/app_translations.dart';
import 'models/telemetry_models.dart';
import 'services/irrigation_api_service.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const ZiraatIrrigationApp());
}

class ZiraatIrrigationApp extends StatelessWidget {
  const ZiraatIrrigationApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Ziraat Smart Irrigation Telemetry',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.light,
        scaffoldBackgroundColor: const Color(0xFFF3F8FC),
        colorScheme: const ColorScheme.light(
          primary: Color(0xFF0284C7),
          secondary: Color(0xFF0D9488),
          surface: Color(0xFFFFFFFF),
          onSurface: Color(0xFF0F172A),
        ),
        cardTheme: CardThemeData(
          color: const Color(0xFFFFFFFF),
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(14),
            side: const BorderSide(color: Color(0xFFD8E6F3)),
          ),
        ),
        useMaterial3: true,
      ),
      home: const IrrigationHomeScreen(),
    );
  }
}

class IrrigationHomeScreen extends StatefulWidget {
  const IrrigationHomeScreen({super.key});

  @override
  State<IrrigationHomeScreen> createState() => _IrrigationHomeScreenState();
}

class _IrrigationHomeScreenState extends State<IrrigationHomeScreen> {
  final IrrigationApiService _api = IrrigationApiService();
  TelemetrySnapshot? _snapshot;
  int _selectedIndex = 0;
  bool _loading = true;
  String _lang = 'en';
  String _sensorFilter = '';
  Timer? _pollTimer;

  late final TextEditingController _cloudUrlCtrl;
  late final TextEditingController _edgeUrlCtrl;
  late final TextEditingController _plcIpCtrl;

  String _t(String key, {Map<String, String>? params}) =>
      AppTranslations.tr(_lang, key, params: params);

  @override
  void initState() {
    super.initState();
    _cloudUrlCtrl = TextEditingController(text: _api.cloudUrl);
    _edgeUrlCtrl = TextEditingController(text: _api.localEdgeUrl);
    _plcIpCtrl = TextEditingController(text: _api.plcIp);
    _initialize();
  }

  Future<void> _initialize() async {
    final savedLang = await _api.storage.loadLanguage();
    await _api.initSettings();
    _lang = savedLang;
    _cloudUrlCtrl.text = _api.cloudUrl;
    _edgeUrlCtrl.text = _api.localEdgeUrl;
    _plcIpCtrl.text = _api.plcIp;
    await _refreshData();
    _pollTimer = Timer.periodic(
      const Duration(seconds: 5),
      (_) => _refreshData(),
    );
  }

  Future<void> _changeLanguage(String langCode) async {
    await _api.storage.saveLanguage(langCode);
    if (!mounted) return;
    setState(() {
      _lang = langCode;
    });
  }

  Future<void> _refreshData() async {
    final snap = await _api.fetchLatestAndSync();
    if (!mounted) return;
    setState(() {
      _snapshot = snap;
      _loading = false;
    });
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _cloudUrlCtrl.dispose();
    _edgeUrlCtrl.dispose();
    _plcIpCtrl.dispose();
    super.dispose();
  }

  Color _tierColor(ConnectionTier tier) {
    switch (tier) {
      case ConnectionTier.cloudOnline:
        return const Color(0xFF0D9488);
      case ConnectionTier.localEdgeLan:
        return const Color(0xFF0284C7);
      case ConnectionTier.directPlcModbus:
        return const Color(0xFF6366F1);
      case ConnectionTier.offlineCached:
        return const Color(0xFFD97706);
    }
  }

  String _tierLabel(ConnectionTier tier) {
    switch (tier) {
      case ConnectionTier.cloudOnline:
        return '${_t('mode_cloud_online')} (${_api.cloudUrl.replaceFirst('https://', '').replaceFirst('http://', '')})';
      case ConnectionTier.localEdgeLan:
        return '${_t('mode_edge_lan')} (${_api.localEdgeUrl})';
      case ConnectionTier.directPlcModbus:
        return '${_t('mode_plc_direct')} (${_api.plcIp}:502)';
      case ConnectionTier.offlineCached:
        return _t('mode_offline_cache');
    }
  }

  Future<void> _handleValveCommand(
    int zoneId, {
    bool? valveOpen,
    bool? autoMode,
  }) async {
    final msg = await _api.controlValve(
      zoneId: zoneId,
      valveOpen: valveOpen,
      autoMode: autoMode,
      lang: _lang,
    );
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(msg),
        backgroundColor: const Color(0xFF0284C7),
        duration: const Duration(seconds: 2),
      ),
    );
    await _refreshData();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Colors.white,
        surfaceTintColor: Colors.white,
        elevation: 1,
        shadowColor: Colors.black12,
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              _t('app_title'),
              style: const TextStyle(
                fontSize: 15,
                fontWeight: FontWeight.w800,
                color: Color(0xFF0F172A),
              ),
            ),
            Text(
              '${_tierLabel(_api.activeTier)} • 5-Min Auto-Save',
              style: TextStyle(
                fontSize: 11,
                color: _tierColor(_api.activeTier),
                fontWeight: FontWeight.w700,
              ),
            ),
          ],
        ),
        actions: [
          PopupMenuButton<String>(
            tooltip: _t('lang_section_title'),
            initialValue: _lang,
            onSelected: _changeLanguage,
            itemBuilder: (context) => AppTranslations.supportedLanguages
                .map(
                  (code) => PopupMenuItem<String>(
                    value: code,
                    child: Text(
                      AppTranslations.languageFullNames[code] ?? code,
                      style: TextStyle(
                        fontWeight:
                            _lang == code ? FontWeight.bold : FontWeight.normal,
                      ),
                    ),
                  ),
                )
                .toList(),
            child: Container(
              margin: const EdgeInsets.symmetric(vertical: 10, horizontal: 4),
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: const Color(0xFFE0F2FE),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: const Color(0xFF7DD3FC)),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    AppTranslations.languageLabels[_lang] ?? '🇬🇧 EN',
                    style: const TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.bold,
                      color: Color(0xFF0369A1),
                    ),
                  ),
                  const SizedBox(width: 2),
                  const Icon(
                    Icons.arrow_drop_down,
                    size: 16,
                    color: Color(0xFF0369A1),
                  ),
                ],
              ),
            ),
          ),
          IconButton(
            onPressed: _refreshData,
            icon: const Icon(Icons.sync, color: Color(0xFF0284C7)),
            tooltip: _t('refresh_sync'),
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : IndexedStack(
              index: _selectedIndex,
              children: [
                _buildZonesTab(),
                _buildSensorsTab(),
                _buildSettingsTab(),
              ],
            ),
      bottomNavigationBar: NavigationBar(
        backgroundColor: Colors.white,
        indicatorColor: const Color(0xFFE0F2FE),
        selectedIndex: _selectedIndex,
        onDestinationSelected: (idx) => setState(() => _selectedIndex = idx),
        destinations: [
          NavigationDestination(
            icon: const Icon(Icons.water_drop_outlined),
            selectedIcon: const Icon(
              Icons.water_drop,
              color: Color(0xFF0284C7),
            ),
            label: _t('nav_zones'),
          ),
          NavigationDestination(
            icon: const Icon(Icons.sensors_outlined),
            selectedIcon: const Icon(Icons.sensors, color: Color(0xFF0284C7)),
            label: _t('nav_sensors'),
          ),
          NavigationDestination(
            icon: const Icon(Icons.tune_outlined),
            selectedIcon: const Icon(Icons.tune, color: Color(0xFF0284C7)),
            label: _t('nav_settings'),
          ),
        ],
      ),
    );
  }

  String _fmtD(double? v, {int digits = 1, String suffix = ''}) {
    if (v == null) return '—';
    return '${v.toStringAsFixed(digits)}$suffix';
  }

  String _fmtI(int? v, {String suffix = ''}) {
    if (v == null) return '—';
    return '$v$suffix';
  }

  List<ZoneSummary> _effectiveZones() {
    final snapZones = _snapshot?.zones ?? [];
    if (snapZones.isNotEmpty) return snapZones;
    return List.generate(8, (i) {
      final zid = i + 1;
      final sIds = [zid, zid + 8, zid + 16];
      return ZoneSummary(
        zoneId: zid,
        nameTr: 'Bölge $zid (Parsel ${sIds.join("-")})',
        nameEn: 'Zone $zid (Plots ${sIds.join("-")})',
        valveTag: 'vana$zid',
        valveCoil: zid == 6 ? 7 : (zid == 7 ? 6 : zid),
        relayTag: zid <= 6 ? 'dc$zid' : 'dc${zid + 6}',
        valveOpen: false,
        autoMode: true,
        minMoisture: 48.0,
        maxMoisture: 90.0,
        sensorIds: sIds,
      );
    });
  }

  List<SensorReading> _effectiveSensors() {
    final snapSensors = _snapshot?.sensors ?? [];
    if (snapSensors.isNotEmpty) return snapSensors;
    return List.generate(24, (i) {
      final sid = i + 1;
      final zid = (i % 8) + 1;
      return SensorReading(
        sensorId: sid,
        zoneId: zid,
        soilName: 'R$sid',
        leafName: 'R${sid}_L',
        soilSlaveId: sid,
        leafSlaveId: 100 + sid,
      );
    });
  }

  Widget _buildZonesTab() {
    final zones = _effectiveZones();
    final sensors = _effectiveSensors();
    final sensorMap = <int, SensorReading>{
      for (final s in sensors) s.sensorId: s,
    };

    return RefreshIndicator(
      onRefresh: _refreshData,
      child: ListView.builder(
        padding: const EdgeInsets.all(12),
        itemCount: zones.length,
        itemBuilder: (context, idx) {
          final z = zones[idx];
          final progress = ((z.avgSoilMoisture ?? 0.0) / 100.0).clamp(0.0, 1.0);
          final leafSlaves = z.sensorIds.map((id) => 100 + id).join(', ');
          return Card(
            margin: const EdgeInsets.only(bottom: 12),
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              '${_t('zone_prefix')} ${z.zoneId} — ${z.valveTag.toUpperCase()}',
                              style: const TextStyle(
                                fontSize: 16,
                                fontWeight: FontWeight.w800,
                                color: Color(0xFF0F172A),
                              ),
                            ),
                            Text(
                              '🌱 Soil R${z.sensorIds.join(", R")} (Slave ${z.sensorIds.join(", ")})  •  🌿 Leaf R${z.sensorIds.join("_L, R")}_L (Slave $leafSlaves)',
                              style: const TextStyle(
                                fontSize: 11,
                                color: Color(0xFF64748B),
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ],
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 10,
                          vertical: 5,
                        ),
                        decoration: BoxDecoration(
                          color: z.valveOpen
                              ? const Color(0xFFE0F2FE)
                              : const Color(0xFFF1F5F9),
                          borderRadius: BorderRadius.circular(20),
                          border: Border.all(
                            color: z.valveOpen
                                ? const Color(0xFF7DD3FC)
                                : const Color(0xFFCBD5E1),
                          ),
                        ),
                        child: Text(
                          z.avgSoilMoisture == null
                              ? '—'
                              : (z.valveOpen ? _t('irrigating') : _t('closed')),
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w800,
                            color: z.valveOpen
                                ? const Color(0xFF0369A1)
                                : const Color(0xFF475569),
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: const Color(0xFFF3F8FC),
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(color: const Color(0xFFD8E6F3)),
                    ),
                    child: Column(
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text(
                              '${_t('soil_moisture')} (${z.minMoisture.toStringAsFixed(0)}%–${z.maxMoisture.toStringAsFixed(0)}%)',
                              style: const TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.w700,
                                color: Color(0xFF334155),
                              ),
                            ),
                            Text(
                              _fmtD(z.avgSoilMoisture, digits: 1, suffix: ' %'),
                              style: const TextStyle(
                                fontSize: 18,
                                fontWeight: FontWeight.w900,
                                color: Color(0xFF0284C7),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 6),
                        ClipRRect(
                          borderRadius: BorderRadius.circular(6),
                          child: LinearProgressIndicator(
                            value: progress,
                            minHeight: 8,
                            backgroundColor: const Color(0xFFE2E8F0),
                            color: const Color(0xFF0284C7),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 10),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      _metricBox(
                        _t('soil_temp'),
                        _fmtD(z.avgSoilTemp, digits: 1, suffix: ' °C'),
                        const Color(0xFF0F172A),
                      ),
                      _metricBox(
                        _t('soil_ec'),
                        _fmtD(z.avgSoilEc, digits: 0, suffix: ' µS'),
                        const Color(0xFF0369A1),
                      ),
                      _metricBox(
                        _t('salinity'),
                        _fmtD(z.avgSoilSalt, digits: 0, suffix: ' mg/L'),
                        const Color(0xFF334155),
                      ),
                      _metricBox(
                        'Soil pH',
                        _fmtD(z.avgSoilPh, digits: 2),
                        const Color(0xFFD97706),
                      ),
                      _metricBox(
                        '🌿 L_humidity',
                        _fmtD(z.avgLeafHumidity, digits: 1, suffix: ' %'),
                        const Color(0xFF15803D),
                      ),
                      _metricBox(
                        '🌿 L_temp',
                        _fmtD(z.avgLeafTemp, digits: 1, suffix: ' °C'),
                        const Color(0xFF15803D),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: z.sensorIds.map((sid) {
                      final sr = sensorMap[sid];
                      if (sr == null) return const SizedBox.shrink();
                      return Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 8,
                          vertical: 5,
                        ),
                        decoration: BoxDecoration(
                          color: const Color(0xFFF8FAFC),
                          borderRadius: BorderRadius.circular(6),
                          border: Border.all(color: const Color(0xFFD8E6F3)),
                        ),
                        child: Text(
                          'R$sid (S:$sid/L:${sr.leafSlaveId}): Soil ${_fmtD(sr.soilMoisture, suffix: "%")} | Leaf ${_fmtD(sr.leafHumidity, suffix: "%")} • ${_fmtD(sr.leafTemp, suffix: "°C")}',
                          style: const TextStyle(
                            fontSize: 10.5,
                            fontWeight: FontWeight.w700,
                            color: Color(0xFF334155),
                          ),
                        ),
                      );
                    }).toList(),
                  ),
                  const Divider(height: 20, color: Color(0xFFE2E8F0)),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Flexible(
                        child: Text(
                          z.autoMode
                              ? '${_t('mode_auto')} (${z.minMoisture.toStringAsFixed(0)}%–${z.maxMoisture.toStringAsFixed(0)}%)'
                              : _t('mode_manual'),
                          style: const TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w700,
                            color: Color(0xFF475569),
                          ),
                        ),
                      ),
                      Row(
                        children: [
                          ElevatedButton(
                            style: ElevatedButton.styleFrom(
                              backgroundColor: const Color(0xFF0284C7),
                              foregroundColor: Colors.white,
                              padding:
                                  const EdgeInsets.symmetric(horizontal: 12),
                            ),
                            onPressed: () => _handleValveCommand(
                              z.zoneId,
                              valveOpen: true,
                              autoMode: false,
                            ),
                            child: Text(_t('btn_open')),
                          ),
                          const SizedBox(width: 6),
                          OutlinedButton(
                            onPressed: () => _handleValveCommand(
                              z.zoneId,
                              valveOpen: false,
                              autoMode: false,
                            ),
                            child: Text(_t('btn_close')),
                          ),
                          const SizedBox(width: 6),
                          OutlinedButton(
                            onPressed: () => _handleValveCommand(
                              z.zoneId,
                              autoMode: true,
                            ),
                            child: Text(_t('btn_auto')),
                          ),
                        ],
                      ),
                    ],
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _metricBox(String label, String value, Color valueColor) {
    return Container(
      width: 104,
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
      decoration: BoxDecoration(
        color: const Color(0xFFF3F8FC),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0xFFE2E8F0)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.w600,
              color: Color(0xFF64748B),
            ),
            overflow: TextOverflow.ellipsis,
          ),
          const SizedBox(height: 2),
          Text(
            value,
            style: TextStyle(
              fontSize: 13.5,
              fontWeight: FontWeight.w800,
              color: valueColor,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSensorsTab() {
    final sensors = _effectiveSensors().where((s) {
      if (_sensorFilter.trim().isEmpty) return true;
      final q = _sensorFilter.trim().toLowerCase();
      return 'r${s.sensorId}'.contains(q) ||
          'zone ${s.zoneId}'.contains(q) ||
          '${s.leafSlaveId}'.contains(q) ||
          '${s.zoneId}' == q;
    }).toList();

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 12, 12, 4),
          child: TextField(
            decoration: const InputDecoration(
              prefixIcon: Icon(Icons.search),
              hintText: 'Filter by Sensor (R1..R24, Slave 101..124) or Zone (1–8)...',
              filled: true,
              fillColor: Colors.white,
              border: OutlineInputBorder(),
              isDense: true,
            ),
            onChanged: (v) => setState(() => _sensorFilter = v),
          ),
        ),
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.all(12),
            itemCount: sensors.length,
            itemBuilder: (context, idx) {
              final s = sensors[idx];
              return Card(
                margin: const EdgeInsets.only(bottom: 8),
                child: ListTile(
                  dense: true,
                  leading: CircleAvatar(
                    backgroundColor: const Color(0xFFE0F2FE),
                    child: Text(
                      'R${s.sensorId}',
                      style: const TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w800,
                        color: Color(0xFF0369A1),
                      ),
                    ),
                  ),
                  title: Text(
                    '🌱 R${s.sensorId} (Slave ${s.soilSlaveId}, Zone ${s.zoneId}) — Soil: ${_fmtD(s.soilMoisture, suffix: "%")} | ${_fmtD(s.soilTemp, suffix: "°C")} | pH: ${_fmtD(s.soilPh, digits: 2)}',
                    style: const TextStyle(
                      fontWeight: FontWeight.w800,
                      fontSize: 12.5,
                      color: Color(0xFF0F172A),
                    ),
                  ),
                  subtitle: Text(
                    'EC: ${_fmtI(s.soilEc, suffix: " µS/cm")} • ${_t('salinity_short')}: ${_fmtI(s.soilSalt, suffix: " mg/L")}  |  🌿 Leaf R${s.sensorId}_L (Slave ${s.leafSlaveId}): L_humidity ${_fmtD(s.leafHumidity, suffix: "%")} • L_temp ${_fmtD(s.leafTemp, suffix: "°C")}',
                    style: const TextStyle(
                      fontSize: 11.5,
                      fontWeight: FontWeight.w600,
                      color: Color(0xFF15803D),
                    ),
                  ),
                ),
              );
            },
          ),
        ),
      ],
    );
  }

  Widget _buildSettingsTab() {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(
          _t('lang_section_title'),
          style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          children: AppTranslations.supportedLanguages.map((code) {
            final selected = _lang == code;
            return ChoiceChip(
              selected: selected,
              selectedColor: const Color(0xFF0284C7),
              label: Text(
                AppTranslations.languageFullNames[code] ?? code,
                style: TextStyle(
                  color: selected ? Colors.white : const Color(0xFF0F172A),
                  fontWeight: FontWeight.bold,
                ),
              ),
              onSelected: (_) => _changeLanguage(code),
            );
          }).toList(),
        ),
        const Divider(height: 28),
        Text(
          _t('conn_arch_title'),
          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 6),
        Text(
          _t('conn_arch_desc'),
          style: const TextStyle(fontSize: 12, color: Color(0xFF475569)),
        ),
        const SizedBox(height: 16),
        TextField(
          controller: _cloudUrlCtrl,
          decoration: InputDecoration(
            labelText: _t('cloud_url_label'),
            filled: true,
            fillColor: Colors.white,
            border: const OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: 8),
        Text(
          _t('preset_domains_label'),
          style: const TextStyle(fontSize: 11, color: Color(0xFF475569)),
        ),
        const SizedBox(height: 4),
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: IrrigationApiService.cloudFallbackUrls.map((url) {
            return ActionChip(
              label: Text(url, style: const TextStyle(fontSize: 11)),
              onPressed: () {
                setState(() {
                  _cloudUrlCtrl.text = url;
                });
              },
            );
          }).toList(),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _edgeUrlCtrl,
          decoration: InputDecoration(
            labelText: _t('edge_url_label'),
            filled: true,
            fillColor: Colors.white,
            border: const OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _plcIpCtrl,
          decoration: InputDecoration(
            labelText: _t('plc_ip_label'),
            filled: true,
            fillColor: Colors.white,
            border: const OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: 16),
        ElevatedButton.icon(
          icon: const Icon(Icons.save),
          label: Text(_t('btn_save_connect')),
          style: ElevatedButton.styleFrom(
            backgroundColor: const Color(0xFF0284C7),
            foregroundColor: Colors.white,
            padding: const EdgeInsets.symmetric(vertical: 14),
          ),
          onPressed: () async {
            await _api.storage.saveConnectionSettings(
              cloudUrl: _cloudUrlCtrl.text,
              localEdgeUrl: _edgeUrlCtrl.text,
              plcIp: _plcIpCtrl.text,
            );
            await _api.initSettings();
            await _refreshData();
            if (!mounted) return;
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text(_t('settings_saved')),
              ),
            );
          },
        ),
        const SizedBox(height: 20),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _t('offline_box_title'),
                  style: const TextStyle(fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 6),
                Text(
                  '• ${_t('last_telemetry_time')}: ${_snapshot?.recordedAt ?? "--"}',
                ),
                Text(
                  '• ${_t('total_cloud_records')}: ${_api.totalServerReadings}',
                ),
                Text(
                  '• ${_t('queued_valve_cmds')}: ${_api.unsyncedLocalCount}',
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}
