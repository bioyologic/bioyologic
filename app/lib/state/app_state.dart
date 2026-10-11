import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/api_client.dart';

/// Estado global: preferencias, perfil local y cliente de la API.
class AppState extends ChangeNotifier {
  AppState._(this._prefs);

  final SharedPreferences _prefs;
  ApiClient? _api;

  static Future<AppState> load() async => AppState._(await SharedPreferences.getInstance());

  /// Servidor fijado al compilar: flutter build apk --dart-define=BIOYOLOGIC_SERVER=https://...
  static const _builtInServer = String.fromEnvironment('BIOYOLOGIC_SERVER');

  /// Repositorio del código fuente (AGPL-3.0). El servidor puede indicar otro en /about.
  static const sourceUrl = String.fromEnvironment('BIOYOLOGIC_SOURCE', defaultValue: 'https://github.com/Godjuanjo/bioyologic');

  static String get defaultServer {
    if (_builtInServer.isNotEmpty) return _builtInServer;
    // En web la app se sirve desde la propia API (/app), así que el servidor es el mismo origen.
    if (kIsWeb) return Uri.base.origin;
    // 10.0.2.2 es el localhost del PC visto desde el emulador de Android.
    if (defaultTargetPlatform == TargetPlatform.android) return 'http://10.0.2.2:8000';
    return 'http://localhost:8000';
  }

  // ----------------------------------------------------------------- servidor
  String get serverUrl => _prefs.getString('server_url') ?? defaultServer;
  set serverUrl(String v) {
    _prefs.setString('server_url', v.trim());
    _api = null;
    notifyListeners();
  }

  ApiClient get api => _api ??= ApiClient(serverUrl);

  // ----------------------------------------------------------------- perfil
  String? get userName => _prefs.getString('user_name');
  String get userRole => _prefs.getString('user_role') ?? '';
  String get userInstitution => _prefs.getString('user_institution') ?? '';
  bool get hasProfile => (userName ?? '').isNotEmpty;

  String get firstName {
    final parts = (userName ?? '').trim().split(RegExp(r'\s+'));
    // "Juan José Martínez" -> "Juan José": nombre compuesto habitual en español.
    return parts.length >= 3 ? '${parts[0]} ${parts[1]}' : parts.first;
  }

  String get initials {
    final parts = (userName ?? '').trim().split(RegExp(r'\s+')).where((p) => p.isNotEmpty).toList();
    if (parts.isEmpty) return '?';
    return parts.take(2).map((p) => p[0].toUpperCase()).join();
  }

  Future<void> saveProfile({required String name, String role = '', String institution = ''}) async {
    await _prefs.setString('user_name', name.trim());
    await _prefs.setString('user_role', role.trim());
    await _prefs.setString('user_institution', institution.trim());
    notifyListeners();
  }

  Future<void> logout() async {
    for (final k in ['user_name', 'user_role', 'user_institution']) {
      await _prefs.remove(k);
    }
    notifyListeners();
  }

  // ----------------------------------------------------------------- preferencias
  bool _flag(String k, bool def) => _prefs.getBool(k) ?? def;
  void _setFlag(String k, bool v) {
    _prefs.setBool(k, v);
    notifyListeners();
  }

  bool get darkMode => _flag('dark_mode', false);
  set darkMode(bool v) => _setFlag('dark_mode', v);

  /// Muestra el círculo guía en la cámara y lo usa para calcular la escala en mm.
  bool get focusGuide => _flag('focus_guide', true);
  set focusGuide(bool v) => _setFlag('focus_guide', v);

  bool get saveOriginal => _flag('save_original', true);
  set saveOriginal(bool v) => _setFlag('save_original', v);

  String get resolution => _prefs.getString('resolution') ?? 'alta';
  set resolution(String v) {
    _prefs.setString('resolution', v);
    notifyListeners();
  }

  String get flashMode => _prefs.getString('flash') ?? 'apagado';
  set flashMode(String v) {
    _prefs.setString('flash', v);
    notifyListeners();
  }

  double get defaultVolumeMl => _prefs.getDouble('volume_ml') ?? 0.1;
  set defaultVolumeMl(double v) {
    _prefs.setDouble('volume_ml', v);
    notifyListeners();
  }

  double get plateDiameterMm => _prefs.getDouble('plate_mm') ?? 90;
  set plateDiameterMm(double v) {
    _prefs.setDouble('plate_mm', v);
    notifyListeners();
  }

  // ----------------------------------------------------------------- datos
  /// Se incrementa cuando cambian análisis o proyectos para que las listas se recarguen.
  int dataVersion = 0;
  void dataChanged() {
    dataVersion++;
    notifyListeners();
  }
}

class AppScope extends InheritedNotifier<AppState> {
  const AppScope({super.key, required AppState state, required super.child}) : super(notifier: state);

  static AppState of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<AppScope>()!.notifier!;

  /// Acceso sin suscribirse a cambios (para callbacks).
  static AppState read(BuildContext context) =>
      context.getInheritedWidgetOfExactType<AppScope>()!.notifier!;
}
