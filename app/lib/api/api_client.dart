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
  ApiClient(String baseUrl, {http.Client? client})
      : baseUrl = baseUrl.replaceAll(RegExp(r'/+$'), ''),
        _client = client ?? http.Client();

  final String baseUrl;
  final http.Client _client;

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
      _json(() => _client.get(_uri(path, q)));

  Future<dynamic> _send(String method, String path, [Object? body]) => _json(() {
        final req = http.Request(method, _uri(path))
          ..headers['Content-Type'] = 'application/json';
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

  Future<Stats> stats() async => Stats.fromJson(await _get('/stats') as Map<String, dynamic>);

  // ----------------------------------------------------------------- análisis
  Future<List<Analysis>> analyses({int? projectId, String query = '', int limit = 50}) async {
    final list = await _get('/analyses', {
      if (projectId != null) 'project_id': '$projectId',
      if (query.isNotEmpty) 'q': query,
      'limit': '$limit',
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
  }) async {
    final req = http.MultipartRequest('POST', _uri('/analyses'))
      ..fields.addAll({
        'sample_name': sampleName,
        'plate_diameter_mm': '$plateDiameterMm',
        if (projectId != null) 'project_id': '$projectId',
        if (dilution != null) 'dilution': '$dilution',
        if (volumeMl != null) 'volume_ml': '$volumeMl',
        if (plateFraction != null) 'plate_fraction': '$plateFraction',
      })
      ..files.add(http.MultipartFile.fromBytes('image', image, filename: filename));
    final body = await _json(() => _client.send(req).then(http.Response.fromStream));
    return Analysis.fromJson(body as Map<String, dynamic>);
  }

  /// `projectId: 0` quita el análisis de su proyecto.
  Future<Analysis> updateAnalysis(int id, {String? sampleName, String? notes, int? projectId}) async =>
      Analysis.fromJson(await _send('PATCH', '/analyses/$id', {
        'sample_name': ?sampleName,
        'notes': ?notes,
        'project_id': ?projectId,
      }) as Map<String, dynamic>);

  Future<void> deleteAnalysis(int id) => _send('DELETE', '/analyses/$id');

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
