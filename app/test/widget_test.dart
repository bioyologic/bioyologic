import 'dart:convert';
import 'dart:typed_data';

import 'package:bioyologic/api/api_client.dart';
import 'package:bioyologic/widgets/format.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

Map<String, dynamic> _analysisJson({bool withColonies = true}) => {
      'id': 7,
      'project_id': 2,
      'project_name': 'Agua de río',
      'sample_name': 'Caja #1',
      'created_at': '2026-10-10T10:30:00',
      'dilution': 0.001,
      'volume_ml': 0.1,
      'mm_per_px': 0.08,
      'notes': '',
      'total': 2,
      'summary': {
        'total': 2,
        'by_class': {'S.aureus': 2},
        'status': 'pocas',
        'cfu_per_ml': 20000.0,
        'predominant': {'class': 'S.aureus', 'form': 'circular', 'margin': 'entero', 'color': 'amarillo'},
        'stats': {
          'diameter_mm': {'mean': 1.2, 'std': 0.1, 'median': 1.2, 'min': 1.1, 'max': 1.3},
          'form': {'circular': 2},
        },
      },
      if (withColonies)
        'colonies': [
          {
            'id': 1,
            'class_name': 'S.aureus',
            'confidence': 0.91,
            'morphology': {
              'diameter_px': 15.0, 'diameter_mm': 1.2, 'circularity': 0.93, 'form': 'circular',
              'margin': 'entero', 'color_hex': '#ebc35f', 'color_name': 'amarillo', 'segmented': true,
            },
          },
        ],
      'image_urls': {
        'original': '/analyses/7/image/original',
        'annotated': '/analyses/7/image/annotated',
        'thumb': '/analyses/7/image/thumb',
      },
      'report_url': '/analyses/7/report.pdf',
      'species': {
        'identified': true,
        'top': [
          {'name': 'Staphylococcus aureus', 'prob': 0.91, 'gram': '+', 'agar': 'blood'},
          {'name': 'Staphylococcus epidermidis', 'prob': 0.05, 'gram': '+', 'agar': 'blood'},
        ],
      },
    };

http.Response _json(Object body, [int status = 200]) =>
    http.Response.bytes(utf8.encode(jsonEncode(body)), status, headers: {'content-type': 'application/json'});

void main() {
  test('formatos', () {
    expect(scientific(15000000), '1,50 × 10⁷');
    expect(dilutionLabel(0.0001), '10⁻⁴');
    expect(speciesLabel('S.aureus'), 'S. aureus');
    expect(speciesLabel('colony'), 'Colonia');
    expect(capitalize('beige'), 'Beige');
  });

  test('ApiClient: detalle de análisis y URLs absolutas', () async {
    final api = ApiClient('http://srv:8000/', client: MockClient((req) async {
      expect(req.url.toString(), 'http://srv:8000/analyses/7');
      return _json(_analysisJson());
    }));
    final a = await api.analysis(7);
    expect(a.sampleName, 'Caja #1');
    expect(a.summary.total, 2);
    expect(a.summary.cfuPerMl, 20000.0);
    expect(a.summary.diameter.unit, 'mm');
    expect(a.summary.diameter.stat!.mean, 1.2);
    expect(a.summary.predominant['color'], 'amarillo');
    expect(a.colonies!.single.colorName, 'amarillo');
    expect(api.url(a.thumbUrl), 'http://srv:8000/analyses/7/image/thumb');
    expect(a.species!.identified, isTrue);
    expect(a.species!.top.first.name, 'Staphylococcus aureus');
    expect(a.species!.top.first.gram, '+');
    expect(a.colonies!.single.speciesConfidence, isNull);
  });

  test('ApiClient: listado con filtros y subida multipart', () async {
    late http.BaseRequest upload;
    final api = ApiClient('http://srv', client: MockClient.streaming((req, body) async {
      if (req.method == 'GET') {
        expect(req.url.queryParameters, {'project_id': '2', 'q': 'caja', 'limit': '50'});
        return http.StreamedResponse(Stream.value(utf8.encode(jsonEncode([_analysisJson(withColonies: false)]))), 200);
      }
      upload = req;
      final text = utf8.decode(await body.toBytes(), allowMalformed: true);
      expect(text, contains('name="sample_name"'));
      expect(text, contains('name="plate_fraction"'));
      expect(text, isNot(contains('name="project_id"')));
      return http.StreamedResponse(Stream.value(utf8.encode(jsonEncode(_analysisJson()))), 201);
    }));
    final list = await api.analyses(projectId: 2, query: 'caja');
    expect(list.single.colonies, isNull);
    final created = await api.createAnalysis(
        image: Uint8List.fromList([1, 2, 3]), filename: 'p.jpg', sampleName: 'Caja #1', plateFraction: 0.8);
    expect(upload.url.path, '/analyses');
    expect(created.id, 7);
  });

  test('ApiClient: errores del servidor legibles', () async {
    final api = ApiClient('http://srv', client: MockClient((_) async => _json({'detail': 'Proyecto no encontrado'}, 404)));
    await expectLater(api.project(9),
        throwsA(isA<ApiException>().having((e) => e.message, 'message', 'Proyecto no encontrado')));
    final api422 = ApiClient('http://srv', client: MockClient((_) async => _json({
          'detail': [
            {'msg': 'Field required'}
          ]
        }, 422)));
    await expectLater(api422.createProject(''), throwsA(isA<ApiException>().having((e) => e.message, 'm', 'Field required')));
  });

  test('ApiClient: sesión con token y aviso cuando caduca', () async {
    final seen = <String?>[];
    var expired = 0;
    late final ApiClient api;
    api = ApiClient('http://srv', onUnauthorized: () => expired++, client: MockClient((req) async {
      seen.add(req.headers['authorization']);
      if (req.url.path == '/auth/login') {
        return _json({
          'token': 'tok123',
          'user': {'id': 1, 'email': 'ana@lab.co', 'name': 'Ana', 'role': '', 'institution': 'PUJ'},
        }, 200);
      }
      return _json({'detail': 'Inicia sesión para continuar'}, 401);
    }));
    final s = await api.login('ana@lab.co', 'clave-segura-1');
    expect(s.token, 'tok123');
    expect(s.user.institution, 'PUJ');
    expect(seen.single, isNull);
    api.token = s.token;
    await expectLater(api.stats(), throwsA(isA<ApiException>()));
    expect(seen.last, 'Bearer tok123');
    expect(expired, 1);
  });

  test('ApiClient: corrección manual del conteo y correo sin verificar', () async {
    var unverified = 0;
    late Map<String, dynamic> sent;
    final api = ApiClient('http://srv', token: 't', onUnverified: () => unverified++,
        client: MockClient((req) async {
      if (req.method == 'PUT') {
        sent = jsonDecode(req.body) as Map<String, dynamic>;
        return _json({
          ..._analysisJson(),
          'image_size': [800, 600],
          'removed_colonies': [
            {
              'id': 2, 'class_name': 'S.aureus', 'confidence': 0.5, 'bbox': [10, 10, 30, 30], 'center': [20, 20],
              'morphology': (_analysisJson()['colonies'] as List).first['morphology'],
            }
          ],
          'correction': {
            'at': '2026-10-30T10:00:00', 'by': 'ana@lab.co', 'detected_total': 2, 'removed': [2],
            'added': [{'x': 100.0, 'y': 50.0, 'r': 8.0}],
          },
        }, 200);
      }
      return http.Response(jsonEncode({'detail': 'Verifica tu correo para continuar'}), 403,
          headers: {'x-bioyologic-reason': 'email-not-verified', 'content-type': 'application/json'});
    }));
    final a = await api.correctColonies(7, removed: [2], added: [(x: 100.0, y: 50.0, r: 8.0)]);
    expect(sent['removed'], [2]);
    expect(sent['added'], [{'x': 100.0, 'y': 50.0, 'r': 8.0}]);
    expect(a.correction!.detectedTotal, 2);
    expect(a.correction!.added.single.r, 8.0);
    expect(a.removedColonies.single.radius, 10.0);
    expect(a.imageSize, [800.0, 600.0]);
    await expectLater(api.stats(), throwsA(isA<ApiException>()));
    expect(unverified, 1);
  });

  test('Muestra con varias placas y enlace de exportación', () async {
    final api = ApiClient('http://srv', token: 't', client: MockClient((req) async {
      if (req.url.path == '/samples') {
        expect(req.url.queryParameters['project_id'], '3');
        return _json([
          {
            'name': 'Punto 1', 'project_id': 3, 'project_name': 'Río', 'last_at': '2026-10-30T10:00:00',
            'result': {'cfu_per_ml': 2.74e6, 'estimated': false, 'used': [1, 2], 'rule': 'ISO', 'warnings': ['ojo']},
            'plates': [
              {'id': 1, 'sample_name': 'A', 'created_at': '2026-10-30T09:00:00', 'dilution': 0.001, 'volume_ml': 0.1,
               'total': 280, 'status': 'contable', 'cfu_per_ml': 2.8e6, 'used': true, 'thumb_url': '/t1'},
              {'id': 3, 'sample_name': 'C', 'created_at': '2026-10-30T09:05:00', 'dilution': 0.00001, 'volume_ml': 0.1,
               'total': 2, 'status': 'pocas', 'cfu_per_ml': 2e6, 'used': false, 'thumb_url': '/t3'},
            ],
          }
        ], 200);
      }
      expect(jsonDecode(req.body), {'project_id': 3});
      return _json({'url': '/export/R%C3%ADo.csv?token=x'}, 200);
    }));
    final m = (await api.samples(projectId: 3)).single;
    expect(m.cfuPerMl, 2.74e6);
    expect(m.usedCount, 1);
    expect(m.plates.last.used, isFalse);
    expect(await api.csvExportLink(projectId: 3), 'http://srv/export/R%C3%ADo.csv?token=x');
  });
}
