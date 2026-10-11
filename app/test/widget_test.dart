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
}
