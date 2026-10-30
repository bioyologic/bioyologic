import 'package:bioyologic/api/models.dart';
import 'package:bioyologic/state/app_state.dart';
import 'package:bioyologic/widgets/analysis_tile.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

Analysis _analisis(int id, String nombre) => Analysis.fromJson({
      'id': id,
      'sample_name': nombre,
      'created_at': '2026-10-30T10:00:00',
      'notes': '',
      'summary': {
        'total': 30,
        'by_class': {'colony': 30},
        'status': 'contable',
        'cfu_per_ml': null,
        'predominant': <String, dynamic>{},
        'stats': <String, dynamic>{},
      },
      'image_urls': {'thumb': '/t', 'annotated': '/a', 'original': '/o'},
      'report_url': '/r',
    });

void main() {
  testWidgets('Deslizar un análisis pide confirmación y Cancelar lo conserva', (tester) async {
    SharedPreferences.setMockInitialValues({'server_url': 'http://srv'});
    final state = await AppState.load();
    var recargas = 0;
    await tester.pumpWidget(AppScope(
      state: state,
      child: MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: DeletableAnalysisList([_analisis(1, 'Caja A'), _analisis(2, 'Caja B')],
                onChanged: () async => recargas++),
          ),
        ),
      ),
    ));
    expect(find.text('Caja A'), findsOneWidget);

    await tester.drag(find.text('Caja A'), const Offset(-600, 0));
    await tester.pumpAndSettle();
    expect(find.text('¿Eliminar este análisis?'), findsOneWidget);
    expect(find.textContaining('"Caja A" se borrará con sus fotos y resultados'), findsOneWidget);

    await tester.tap(find.text('Cancelar'));
    await tester.pumpAndSettle();
    expect(find.text('Caja A'), findsOneWidget); // sigue ahí
    expect(recargas, 0);
  });

  testWidgets('El modo selección muestra casillas en vez del estado', (tester) async {
    SharedPreferences.setMockInitialValues({'server_url': 'http://srv'});
    final state = await AppState.load();
    var toques = 0;
    await tester.pumpWidget(AppScope(
      state: state,
      child: MaterialApp(
        home: Scaffold(body: AnalysisTile(_analisis(1, 'Caja A'), selected: true, onTap: () => toques++)),
      ),
    ));
    expect(find.byType(Checkbox), findsOneWidget);
    expect(tester.widget<Checkbox>(find.byType(Checkbox)).value, isTrue);
    await tester.tap(find.text('Caja A'));
    expect(toques, 1);
  });
}
