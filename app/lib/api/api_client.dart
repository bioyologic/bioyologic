import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import 'models.dart';

class ApiException implements Exception {
  ApiException(this.message, [this.statusCode]);
  final String message;
  final int? statusCode;
  @override
  String toString() => message;
}

/// Cliente HTTP de la API de Bioyologic.
class ApiClient {
  ApiClient(String baseUrl, {http.Client? client, this.token, this.onUnauthorized, this.onUnverified})
      : baseUrl = baseUrl.replaceAll(RegExp(r'/+$'), ''),
        _client = client ?? http.Client();

  final String baseUrl;
  final http.Client _client;

  /// Token de sesión; se envía como `Authorization: Bearer` en cada petición.
  String? token;

  /// Se llama cuando el servidor rechaza la sesión (caducada o cerrada en otro dispositivo).
  void Function()? onUnauthorized;

  /// Se llama cuando el servidor exige verificar el correo antes de seguir.
  void Function()? onUnverified;

  Map<String, String> get _auth => {if (token != null) 'Authorization': 'Bearer $token'};

  /// URL absoluta de una ruta relativa devuelta por la API (imágenes, reportes).
  String url(String path) => path.startsWith('http') ? path : '$baseUrl$path';

  Uri _uri(String path, [Map<String, String>? query]) =>
      Uri.parse('$baseUrl$path').replace(queryParameters: query);

  Future<dynamic> _json(Future<http.Response> Function() call) async {
    final http.Response r;
    try {
      r = await call().timeout(const Duration(minutes: 3));
    } catch (e) {
      throw ApiException('No se pudo conectar con el servidor ($baseUrl).');
    }
    if (r.statusCode == 401 && token != null) onUnauthorized?.call();
    if (r.statusCode == 403 && r.headers['x-bioyologic-reason'] == 'email-not-verified') onUnverified?.call();
    if (r.statusCode == 204) return null;
    final body = r.bodyBytes.isEmpty ? null : jsonDecode(utf8.decode(r.bodyBytes));
    if (r.statusCode >= 400) {
      var detail = body is Map ? body['detail'] : null;
      if (detail is List && detail.isNotEmpty) detail = (detail.first as Map)['msg'];
      throw ApiException('${detail ?? 'Error ${r.statusCode}'}', r.statusCode);
    }
    return body;
  }

  Future<dynamic> _get(String path, [Map<String, String>? q]) =>
      _json(() => _client.get(_uri(path, q), headers: _auth));

  Future<dynamic> _send(String method, String path, [Object? body]) => _json(() {
        final req = http.Request(method, _uri(path))
          ..headers['Content-Type'] = 'application/json'
          ..headers.addAll(_auth);
        if (body != null) req.body = jsonEncode(body);
        return _client.send(req).then(http.Response.fromStream);
      });

  // ----------------------------------------------------------------- sistema
  Future<bool> health() async {
    try {
      final r = await _client.get(_uri('/health')).timeout(const Duration(seconds: 5));
      return r.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  /// Licencia, código fuente y datasets del servidor (AGPL-3.0, sección 13).
  Future<Map<String, dynamic>> about() async => await _get('/about') as Map<String, dynamic>;

  // ----------------------------------------------------------------- cuenta
  Future<({String token, UserProfile user})> _session(Object? body) async {
    final j = body as Map<String, dynamic>;
    return (token: j['token'] as String, user: UserProfile.fromJson(j['user'] as Map<String, dynamic>));
  }

  Future<({String token, UserProfile user})> login(String email, String password) async =>
      _session(await _send('POST', '/auth/login', {'email': email, 'password': password}));

  Future<({String token, UserProfile user})> register({
    required String email,
    required String password,
    required String name,
    String role = '',
    String institution = '',
    required bool acceptPrivacy,
  }) async =>
      _session(await _send('POST', '/auth/register', {
        'email': email,
        'password': password,
        'name': name,
        'role': role,
        'institution': institution,
        'accept_privacy': acceptPrivacy,
      }));

  Future<void> logout() => _send('POST', '/auth/logout');

  Future<UserProfile> me() async => UserProfile.fromJson(await _get('/auth/me') as Map<String, dynamic>);

  Future<UserProfile> updateMe({String? name, String? role, String? institution}) async =>
      UserProfile.fromJson(await _send('PATCH', '/auth/me', {
        'name': ?name,
        'role': ?role,
        'institution': ?institution,
      }) as Map<String, dynamic>);

  Future<void> changePassword(String current, String next) =>
      _send('POST', '/auth/me/password', {'current_password': current, 'new_password': next});

  /// Confirma el correo con el código de 6 dígitos que llegó al registrarse.
  Future<UserProfile> verifyEmail(String code) async =>
      UserProfile.fromJson(await _send('POST', '/auth/verify', {'code': code}) as Map<String, dynamic>);

  Future<void> resendVerification() => _send('POST', '/auth/verify/resend');

  /// Envía al correo un código para cambiar la contraseña (responde igual exista o no la cuenta).
  Future<void> forgotPassword(String email) => _send('POST', '/auth/password/forgot', {'email': email});

  /// Cambia la contraseña con el código del correo e inicia sesión.
  Future<({String token, UserProfile user})> resetPassword(String email, String code, String newPassword) async =>
      _session(await _send('POST', '/auth/password/reset',
          {'email': email, 'code': code, 'new_password': newPassword}));

  /// Borra la cuenta y todos sus datos del servidor (derecho de supresión).
  Future<void> deleteAccount(String password) => _send('DELETE', '/auth/me', {'password': password});

  /// Enlace de un solo uso (5 min) para descargar todos los datos de la cuenta en JSON.
  Future<String> exportLink() async =>
      url((await _send('POST', '/auth/me/export-link') as Map<String, dynamic>)['url'] as String);

  Future<Stats> stats() async => Stats.fromJson(await _get('/stats') as Map<String, dynamic>);

  // ----------------------------------------------------------------- análisis
  /// `toReview`: los análisis de otros miembros que el usuario debe aprobar o devolver.
  Future<List<Analysis>> analyses({int? projectId, String query = '', int limit = 50, bool toReview = false}) async {
    final list = await _get('/analyses', {
      if (projectId != null) 'project_id': '$projectId',
      if (query.isNotEmpty) 'q': query,
      'limit': '$limit',
      if (toReview) 'to_review': 'true',
    }) as List;
    return list.map((a) => Analysis.fromJson(a as Map<String, dynamic>)).toList();
  }

  Future<Analysis> analysis(int id) async =>
      Analysis.fromJson(await _get('/analyses/$id') as Map<String, dynamic>);

  Future<Analysis> createAnalysis({
    required Uint8List image,
    required String filename,
    required String sampleName,
    int? projectId,
    double? dilution,
    double? volumeMl,
    double? plateFraction,
    double plateDiameterMm = 90,
    String sampleGroup = '',
    int? incubationId,
  }) async {
    final req = http.MultipartRequest('POST', _uri('/analyses'))
      ..headers.addAll(_auth)
      ..fields.addAll({
        'sample_name': sampleName,
        'plate_diameter_mm': '$plateDiameterMm',
        if (projectId != null) 'project_id': '$projectId',
        if (dilution != null) 'dilution': '$dilution',
        if (volumeMl != null) 'volume_ml': '$volumeMl',
        if (plateFraction != null) 'plate_fraction': '$plateFraction',
        if (sampleGroup.trim().isNotEmpty) 'sample_group': sampleGroup.trim(),
        if (incubationId != null) 'incubation_id': '$incubationId',
      })
      ..files.add(http.MultipartFile.fromBytes('image', image, filename: filename));
    final body = await _json(() => _client.send(req).then(http.Response.fromStream));
    return Analysis.fromJson(body as Map<String, dynamic>);
  }

  /// `projectId: 0` quita el análisis de su proyecto.
  Future<Analysis> updateAnalysis(int id, {String? sampleName, String? notes, int? projectId, String? sampleGroup}) async =>
      Analysis.fromJson(await _send('PATCH', '/analyses/$id', {
        'sample_name': ?sampleName,
        'sample_group': ?sampleGroup,
        'notes': ?notes,
        'project_id': ?projectId,
      }) as Map<String, dynamic>);

  Future<void> deleteAnalysis(int id) => _send('DELETE', '/analyses/$id');

  /// Manda varios análisis a la papelera; devuelve cuántos se borraron.
  Future<int> deleteAnalyses(List<int> ids) async =>
      (await _send('POST', '/analyses/delete', {'ids': ids}) as Map<String, dynamic>)['deleted'] as int;

  /// Corrección manual del conteo: ids detectados que se quitan y colonias agregadas (píxeles de la foto).
  /// Listas vacías deshacen la corrección.
  Future<Analysis> correctColonies(int id, {required List<int> removed,
      required List<({double x, double y, double r})> added}) async =>
      Analysis.fromJson(await _send('PUT', '/analyses/$id/colonies', {
        'removed': removed,
        'added': [for (final a in added) {'x': a.x, 'y': a.y, 'r': a.r}],
      }) as Map<String, dynamic>);

  /// Aprueba ('aprobado') o devuelve ('devuelto', con nota) el análisis de otro miembro; '' quita la revisión.
  Future<Analysis> review(int id, String status, {String note = ''}) async =>
      Analysis.fromJson(await _send('POST', '/analyses/$id/review', {'status': status, 'note': note})
          as Map<String, dynamic>);

  // ----------------------------------------------------------------- papelera
  /// Análisis borrados: se pueden recuperar durante 30 días.
  Future<List<Analysis>> trash() async =>
      (await _get('/trash') as List).map((a) => Analysis.fromJson(a as Map<String, dynamic>)).toList();

  /// Recupera análisis de la papelera (null = todos).
  Future<int> restoreAnalyses([List<int>? ids]) async =>
      (await _send('POST', '/trash/restore', {'ids': ids}) as Map<String, dynamic>)['restored'] as int;

  /// Elimina definitivamente, con sus fotos (null = vaciar la papelera). No se puede deshacer.
  Future<int> purgeAnalyses([List<int>? ids]) async =>
      (await _send('POST', '/trash/purge', {'ids': ids}) as Map<String, dynamic>)['deleted'] as int;

  // ----------------------------------------------------------------- equipo
  List<Member> _members(Object? body) =>
      (body as List).map((m) => Member.fromJson(m as Map<String, dynamic>)).toList();

  Future<List<Member>> members(int projectId) async => _members(await _get('/projects/$projectId/members'));

  Future<List<Member>> addMember(int projectId, String email, String role) async =>
      _members(await _send('POST', '/projects/$projectId/members', {'email': email, 'role': role}));

  Future<List<Member>> changeMember(int projectId, int userId, String role) async =>
      _members(await _send('PATCH', '/projects/$projectId/members/$userId', {'role': role}));

  /// El dueño quita a un miembro, o el propio usuario sale del proyecto.
  Future<void> removeMember(int projectId, int userId) => _send('DELETE', '/projects/$projectId/members/$userId');

  // ----------------------------------------------------------------- siembras en incubación
  Future<List<Incubation>> incubations({bool includeDone = false}) async =>
      (await _get('/incubations', {if (includeDone) 'include_done': 'true'}) as List)
          .map((i) => Incubation.fromJson(i as Map<String, dynamic>))
          .toList();

  Future<Incubation> createIncubation({
    required String name,
    required double hours,
    double? temperatureC,
    DateTime? seededAt,
    int? projectId,
    String sampleGroup = '',
    int? plates,
    String notes = '',
  }) async =>
      Incubation.fromJson(await _send('POST', '/incubations', {
        'name': name,
        'hours': hours,
        'temperature_c': temperatureC,
        if (seededAt != null) 'seeded_at': seededAt.toUtc().toIso8601String(),
        'project_id': projectId,
        'sample_group': sampleGroup,
        'plates': plates,
        'notes': notes,
      }) as Map<String, dynamic>);

  /// `done: true` = ya se leyeron las placas.
  Future<Incubation> updateIncubation(int id, {bool? done}) async =>
      Incubation.fromJson(await _send('PATCH', '/incubations/$id', {'done': ?done}) as Map<String, dynamic>);

  Future<void> deleteIncubation(int id) => _send('DELETE', '/incubations/$id');

  // ----------------------------------------------------------------- muestras y exportación
  /// Muestras con varias placas y su UFC/mL combinada (ISO 4833-1).
  Future<List<Sample>> samples({int? projectId, String? name}) async => (await _get('/samples', {
        if (projectId != null) 'project_id': '$projectId',
        'name': ?name,
      }) as List)
          .map((m) => Sample.fromJson(m as Map<String, dynamic>))
          .toList();

  /// Nombres de muestra ya usados, para sugerirlos.
  Future<List<String>> sampleGroups({int? projectId}) async =>
      List<String>.from(await _get('/sample-groups', {if (projectId != null) 'project_id': '$projectId'}) as List);

  /// Enlace de un solo uso (5 min) al CSV para Excel de un proyecto, o de todos los análisis.
  Future<String> csvExportLink({int? projectId}) async =>
      url((await _send('POST', '/export-link', {'project_id': projectId}) as Map<String, dynamic>)['url'] as String);

  // ----------------------------------------------------------------- proyectos
  Future<List<Project>> projects() async => (await _get('/projects') as List)
      .map((p) => Project.fromJson(p as Map<String, dynamic>))
      .toList();

  Future<Project> project(int id) async =>
      Project.fromJson(await _get('/projects/$id') as Map<String, dynamic>);

  Future<Project> createProject(String name, {String description = '', int targetSamples = 10}) async =>
      Project.fromJson(await _send('POST', '/projects',
          {'name': name, 'description': description, 'target_samples': targetSamples}) as Map<String, dynamic>);

  Future<Project> updateProject(int id, {String? name, String? description, int? targetSamples}) async =>
      Project.fromJson(await _send('PATCH', '/projects/$id', {
        'name': ?name,
        'description': ?description,
        'target_samples': ?targetSamples,
      }) as Map<String, dynamic>);

  Future<void> deleteProject(int id) => _send('DELETE', '/projects/$id');

  // ----------------------------------------------------------------- biblioteca
  Future<({Map<String, String> categories, List<LibraryEntry> entries})> library() async {
    final j = await _get('/library') as Map<String, dynamic>;
    return (
      categories: Map<String, String>.from(j['categories'] as Map),
      entries: (j['entries'] as List).map((e) => LibraryEntry.fromJson(e as Map<String, dynamic>)).toList(),
    );
  }

  Future<LibraryEntry> libraryEntry(String id) async =>
      LibraryEntry.fromJson(await _get('/library/$id') as Map<String, dynamic>);
}
