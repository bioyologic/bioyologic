import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/api_client.dart';
import '../api/models.dart';

/// Estado global: preferencias, sesión del usuario y cliente de la API.
class AppState extends ChangeNotifier {
  AppState._(this._prefs);

  final SharedPreferences _prefs;
  ApiClient? _api;

  static Future<AppState> load() async => AppState._(await SharedPreferences.getInstance());

  /// Servidor fijado al compilar: flutter build apk --dart-define=BIOYOLOGIC_SERVER=https://...
  static const _builtInServer = String.fromEnvironment('BIOYOLOGIC_SERVER');

  /// Repositorio del código fuente (AGPL-3.0). El servidor puede indicar otro en /about.
  static const sourceUrl = String.fromEnvironment('BIOYOLOGIC_SOURCE', defaultValue: 'https://github.com/bioyologic/bioyologic');

  /// Servidor público de Bioyologic (Oracle Cloud, HTTPS).
  static const cloudServer = 'https://bioyologic.duckdns.org';

  static String get defaultServer {
    if (_builtInServer.isNotEmpty) return _builtInServer;
    // En web la app se sirve desde la propia API (/app), así que el servidor es el mismo origen.
    if (kIsWeb) return Uri.base.origin;
    // La versión publicada usa la nube; en desarrollo, el servidor del PC.
    if (!kDebugMode) return cloudServer;
    // 10.0.2.2 es el localhost del PC visto desde el emulador de Android.
    if (defaultTargetPlatform == TargetPlatform.android) return 'http://10.0.2.2:8000';
    return 'http://localhost:8000';
  }

  // ----------------------------------------------------------------- servidor
  String get serverUrl => _prefs.getString('server_url') ?? defaultServer;
  set serverUrl(String v) {
    if (v.trim() == serverUrl) return;
    _prefs.setString('server_url', v.trim());
    _api = null;
    // Las cuentas viven en cada servidor: al cambiarlo hay que iniciar sesión otra vez.
    _clearSession();
    notifyListeners();
  }

  ApiClient get api =>
      _api ??= ApiClient(serverUrl, token: _token, onUnauthorized: _sessionExpired, onUnverified: _unverified);

  // ----------------------------------------------------------------- sesión
  String? get _token => _prefs.getString('auth_token');

  /// Hay una sesión iniciada en este dispositivo.
  bool get isLoggedIn => _token != null;

  /// Se activa cuando el servidor rechaza la sesión; la app vuelve a la pantalla de inicio de sesión.
  final sessionExpired = ValueNotifier<int>(0);

  /// La cuenta debe confirmar su correo antes de usar la app.
  bool get needsVerification => _prefs.getBool('needs_verification') ?? false;

  /// Se activa cuando el servidor pide verificar el correo; la app abre la pantalla del código.
  final verificationNeeded = ValueNotifier<int>(0);

  void _unverified() {
    if (needsVerification) return; // varias peticiones rechazadas a la vez: una sola pantalla
    _prefs.setBool('needs_verification', true);
    verificationNeeded.value++;
  }

  /// Correo con el que se entró por última vez en este dispositivo: si existe, la app propone
  /// iniciar sesión en vez de registrarse. Se conserva al cerrar sesión.
  String? get lastEmail => _prefs.getString('last_email');

  String? get userName => _prefs.getString('user_name');
  String get userEmail => _prefs.getString('user_email') ?? '';
  String get userRole => _prefs.getString('user_role') ?? '';
  String get userInstitution => _prefs.getString('user_institution') ?? '';

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

  /// Guarda en el dispositivo una copia del perfil para mostrarlo sin esperar al servidor.
  Future<void> _cacheProfile(UserProfile u) async {
    await _prefs.setString('user_name', u.name);
    await _prefs.setString('user_email', u.email);
    await _prefs.setString('user_role', u.role);
    await _prefs.setString('user_institution', u.institution);
    await _prefs.setBool('needs_verification', u.needsVerification);
    notifyListeners();
  }

  Future<void> verifyEmail(String code) async => _cacheProfile(await api.verifyEmail(code.trim()));

  Future<void> resetPassword(String email, String code, String newPassword) async =>
      _startSession(await api.resetPassword(email.trim(), code.trim(), newPassword));

  Future<void> _startSession(({String token, UserProfile user}) s) async {
    await _prefs.setString('auth_token', s.token);
    await _prefs.setString('last_email', s.user.email);
    api.token = s.token;
    await _cacheProfile(s.user);
    dataChanged();
  }

  Future<void> login(String email, String password) async => _startSession(await api.login(email, password));

  Future<void> register({
    required String email,
    required String password,
    required String name,
    String role = '',
    String institution = '',
    required bool acceptPrivacy,
  }) async =>
      _startSession(await api.register(
          email: email,
          password: password,
          name: name,
          role: role,
          institution: institution,
          acceptPrivacy: acceptPrivacy));

  /// Actualiza la copia local con los datos del servidor (al abrir la app).
  Future<void> refreshProfile() async => _cacheProfile(await api.me());

  Future<void> updateProfile({required String name, String role = '', String institution = ''}) async =>
      _cacheProfile(await api.updateMe(name: name.trim(), role: role.trim(), institution: institution.trim()));

  Future<void> deleteAccount(String password) async {
    await api.deleteAccount(password);
    await _prefs.remove('last_email');  // la cuenta ya no existe: la próxima vez, registrarse
    await _clearSession();
    notifyListeners();
  }

  Future<void> logout() async {
    try {
      await api.logout();
    } catch (_) {
      // Sin conexión: la sesión caduca sola en el servidor.
    }
    await _clearSession();
    notifyListeners();
  }

  Future<void> _clearSession() async {
    for (final k in ['auth_token', 'user_name', 'user_email', 'user_role', 'user_institution', 'needs_verification']) {
      await _prefs.remove(k);
    }
    _api?.token = null;
  }

  void _sessionExpired() {
    if (!isLoggedIn) return;
    _clearSession().then((_) {
      sessionExpired.value++;
      notifyListeners();
    });
  }

  // ----------------------------------------------------------------- preferencias
  bool _flag(String k, bool def) => _prefs.getBool(k) ?? def;
  void _setFlag(String k, bool v) {
    _prefs.setBool(k, v);
    notifyListeners();
  }

  /// El tutorial de primer uso ya se mostró en este dispositivo.
  bool get tutorialSeen => _flag('tutorial_seen', false);
  set tutorialSeen(bool v) => _setFlag('tutorial_seen', v);

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
