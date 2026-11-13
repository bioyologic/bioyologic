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
  testWidgets('Encuadre: sin tocar es el cuadrado central; con zoom, el trozo que se ve', (tester) async {
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
    await tester.tap(find.text('abrir'));
    await tester.pump();
    // Esperar a que se decodifique la foto
    for (var i = 0; i < 20 && find.text('Usar este encuadre').evaluate().isEmpty; i++) {
      await tester.runAsync(() => Future.delayed(const Duration(milliseconds: 50)));
      await tester.pump();
    }
    await tester.pumpAndSettle();

    await tester.tap(find.text('Usar este encuadre'));
    await tester.pumpAndSettle();
    expect(result!.size, closeTo(1, 1e-6));
    expect(result!.x, closeTo(0, 1e-6));
    expect(result!.y, closeTo((1600 - 1200) / 2 / 1600, 1e-3));

    // Acercar ×2 sobre la esquina superior izquierda del visor: se ve el cuarto de arriba a la izquierda
    await tester.tap(find.text('abrir'));
    await tester.pump();
    for (var i = 0; i < 20 && find.text('Usar este encuadre').evaluate().isEmpty; i++) {
      await tester.runAsync(() => Future.delayed(const Duration(milliseconds: 50)));
      await tester.pump();
    }
    await tester.pumpAndSettle();
    final state = tester.state(find.byType(InteractiveViewer)) as dynamic;
    final ctrl = (state.widget as InteractiveViewer).transformationController!;
    ctrl.value = Matrix4.identity()..scaleByDouble(2, 2, 1, 1);
    await tester.tap(find.text('Usar este encuadre'));
    await tester.pumpAndSettle();
    expect(result!.size, closeTo(0.5, 1e-6));
    expect(result!.x, closeTo(0, 1e-6));
    expect(result!.y, closeTo(0, 1e-6));
  });
}
