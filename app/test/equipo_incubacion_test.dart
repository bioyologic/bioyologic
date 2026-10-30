import 'package:bioyologic/api/models.dart';
import 'package:bioyologic/screens/incubations_screen.dart';
import 'package:bioyologic/screens/team_screen.dart';
import 'package:bioyologic/screens/tutorial_screen.dart';
import 'package:bioyologic/state/app_state.dart';
import 'package:bioyologic/state/reminders.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:shared_preferences/shared_preferences.dart';

Map<String, dynamic> _analisis({Map<String, dynamic>? review, bool mine = false, bool canReview = true}) => {
      'id': 7,
      'sample_name': 'Caja B',
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
      'author_name': 'Beto Ruiz',
      'is_mine': mine,
      'can_review': canReview,
      'review': review,
    };

Incubation _siembra(DateTime seeded, double hours) => Incubation.fromJson({
      'id': 1,
      'name': 'Agua de río',
      'seeded_at': seeded.toUtc().toIso8601String(),
      'ready_at': seeded.add(Duration(minutes: (hours * 60).round())).toUtc().toIso8601String(),
      'hours': hours,
      'temperature_c': 37,
      'analyses_count': 0,
    });

Future<void> _pump(WidgetTester tester, Widget child) async {
  SharedPreferences.setMockInitialValues({'server_url': 'http://srv'});
  final state = await AppState.load();
  await tester.pumpWidget(AppScope(state: state, child: MaterialApp(home: Scaffold(body: child))));
}

void main() {
  setUpAll(() => initializeDateFormatting('es'));

  test('Modelos: revisión, permisos y siembra', () {
    final a = Analysis.fromJson(_analisis(review: {'status': 'pendiente'}));
    expect(a.review!.pending, isTrue);
    expect(a.isMine, isFalse);
    expect(a.canEdit, isTrue); // valor por defecto si el servidor no lo envía
    final viejo = Analysis.fromJson(_analisis()..remove('is_mine')..remove('can_review'));
    expect(viejo.isMine, isTrue);
    expect(viejo.canReview, isFalse);

    final i = _siembra(DateTime.now().subtract(const Duration(hours: 25)), 24);
    expect(i.isReady(), isTrue);
    expect(incubationLabel(i), '24 h a 37 °C');
    expect(Reminders.message(i), 'Tus placas de Agua de río están listas para leer (24 h).');
    expect(durationLabel(const Duration(hours: 5, minutes: 7)), '5 h 07 min');
  });

  testWidgets('Revisor ve Aprobar y Devolver en un análisis pendiente', (tester) async {
    await _pump(tester, ReviewCard(Analysis.fromJson(_analisis(review: {'status': 'pendiente'})), onChanged: () async {}));
    expect(find.text('Pendiente de revisión'), findsOneWidget);
    expect(find.text('Aprobar'), findsOneWidget);
    expect(find.text('Devolver'), findsOneWidget);
    expect(find.text('Analizado por Beto Ruiz'), findsOneWidget);
  });

  testWidgets('El autor ve el estado aprobado sin botones de revisión', (tester) async {
    await _pump(
        tester,
        ReviewCard(
            Analysis.fromJson(_analisis(
                mine: true,
                canReview: false,
                review: {'status': 'aprobado', 'by': 'Carla Gómez', 'at': '2026-10-30T12:00:00', 'note': ''})),
            onChanged: () async {}));
    expect(find.text('Aprobado por Carla Gómez'), findsOneWidget);
    expect(find.text('Aprobar'), findsNothing);
  });

  testWidgets('Siembra lista muestra Analizar placa; una en curso, el tiempo que falta', (tester) async {
    await _pump(
        tester,
        ListView(children: [
          IncubationCard(_siembra(DateTime.now().subtract(const Duration(hours: 25)), 24), onChanged: () async {}),
          IncubationCard(_siembra(DateTime.now().subtract(const Duration(hours: 1)), 48), onChanged: () async {}),
        ]));
    expect(find.textContaining('Lista para leer'), findsOneWidget);
    expect(find.text('Analizar placa'), findsOneWidget);
    expect(find.textContaining('Faltan 46 h'), findsOneWidget);
  });

  testWidgets('Tutorial: tres pantallas y termina con Empezar', (tester) async {
    await _pump(tester, Builder(builder: (context) => TextButton(
        onPressed: () => TutorialScreen.open(context), child: const Text('abrir'))));
    await tester.tap(find.text('abrir'));
    await tester.pumpAndSettle();
    expect(find.text('Usa la caja de iluminación'), findsOneWidget);
    await tester.tap(find.text('Siguiente'));
    await tester.pumpAndSettle();
    expect(find.text('Encaja la placa en el círculo'), findsOneWidget);
    await tester.tap(find.text('Siguiente'));
    await tester.pumpAndSettle();
    expect(find.text('Revisa antes de confiar en el número'), findsOneWidget);
    await tester.tap(find.text('Empezar'));
    await tester.pumpAndSettle();
    expect(find.text('abrir'), findsOneWidget);
  });
}
