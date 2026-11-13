import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:bioyologic/screens/frame_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// PNG de [w] × [h] para probar el encuadre.
Future<Uint8List> _png(int w, int h) async {
  final rec = ui.PictureRecorder();
  Canvas(rec).drawRect(Rect.fromLTWH(0, 0, w.toDouble(), h.toDouble()), Paint()..color = Colors.grey);
  final img = await rec.endRecording().toImage(w, h);
  final data = await img.toByteData(format: ui.ImageByteFormat.png);
  return data!.buffer.asUint8List();
}

void main() {
  test('El cuadro de la pantalla se pasa a píxeles de la foto, también fuera de sus bordes', () {
    // Zoom ×2 y foto desplazada (-50, -30); 0,5 px de visor por px de foto; foto de 1000 × 800
    final view = Matrix4.translationValues(-50, -30, 0)..scaleByDouble(2, 2, 1, 1);
    final c = cropFromView(box: const Rect.fromLTWH(10, 20, 100, 100), view: view, k: 0.5, iw: 1000, ih: 800);
    expect(c.x, closeTo(60 / 1000, 1e-9)); // (10 + 50) / 2 / 0,5 = 60 px
    expect(c.y, closeTo(50 / 800, 1e-9));
    expect(c.size, closeTo(100 / 800, 1e-9));
    // Foto alejada (×0,5) y movida a la derecha: el cuadro empieza antes de la foto y es más grande que ella
    final lejos = Matrix4.translationValues(200, 100, 0)..scaleByDouble(0.5, 0.5, 1, 1);
    final f = cropFromView(box: const Rect.fromLTWH(0, 0, 300, 300), view: lejos, k: 0.5, iw: 1000, ih: 800);
    expect(f.x, closeTo(-800 / 1000, 1e-9));
    expect(f.y, closeTo(-400 / 800, 1e-9));
    expect(f.size, closeTo(1200 / 800, 1e-9));
  });

  testWidgets('Encuadre: sin tocar es el cuadrado central; arrastrar una esquina achica el cuadro', (tester) async {
    tester.view.physicalSize = const Size(400, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);

    final bytes = await tester.runAsync(() => _png(1200, 1600));
    FrameCrop? result;
    await tester.pumpWidget(MaterialApp(
      home: Builder(
        builder: (context) => TextButton(
          onPressed: () async => result = await Navigator.push<FrameCrop>(context,
              MaterialPageRoute(builder: (_) => FrameScreen(image: bytes!))),
          child: const Text('abrir'),
        ),
      ),
    ));

    Future<void> open() async {
      await tester.tap(find.text('abrir'));
      await tester.pump();
      for (var i = 0; i < 20 && find.text('Usar este encuadre').evaluate().isEmpty; i++) {
        await tester.runAsync(() => Future.delayed(const Duration(milliseconds: 50)));
        await tester.pump();
      }
      await tester.pumpAndSettle();
    }

    await open();
    await tester.tap(find.text('Usar este encuadre'));
    await tester.pumpAndSettle();
    expect(result!.size, closeTo(1, 1e-6));
    expect(result!.x, closeTo(0, 1e-6));
    expect(result!.y, closeTo((1600 - 1200) / 2 / 1600, 1e-6));

    // Esquina de abajo a la derecha hacia dentro: el cuadro se achica desde la esquina de arriba a la izquierda
    await open();
    await tester.drag(find.byKey(const ValueKey('esquina-3')), const Offset(-80, -80));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Usar este encuadre'));
    await tester.pumpAndSettle();
    expect(result!.size, inExclusiveRange(0.6, 0.95));
    expect(result!.x, closeTo(0, 1e-6));
    expect(result!.y, closeTo(0.125, 1e-6));
  });
}
