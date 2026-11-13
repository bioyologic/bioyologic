import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import '../theme.dart';

/// Fracción del lado del encuadre que ocupa el círculo guía.
const guideFraction = 0.80;

/// Cuadrado elegido sobre la foto: esquina superior izquierda (fracción del ancho y del alto) y lado (fracción
/// del lado corto). Es lo único que se envía a analizar.
class FrameCrop {
  const FrameCrop(this.x, this.y, this.size);
  final double x, y, size;
}

/// Encuadrar la placa sobre la foto ya tomada: pellizcar para acercar y arrastrar hasta que la placa llene el
/// círculo. Lo que queda dentro del cuadrado es lo que se analiza, igual a lo que se ve aquí.
///
/// Se hace sobre la foto y no sobre la vista de la cámara porque en algunos celulares (p. ej. iPhone en la web)
/// la vista previa sale ampliada respecto a la foto real, y el recorte no coincidía con lo encuadrado.
class FrameScreen extends StatefulWidget {
  const FrameScreen({super.key, required this.image, this.showCircle = true});
  final Uint8List image;
  final bool showCircle;

  @override
  State<FrameScreen> createState() => _FrameScreenState();
}

class _FrameScreenState extends State<FrameScreen> {
  final _ctrl = TransformationController();
  late final Future<ui.Image> _decoded = decodeImageFromList(widget.image);
  double? _side; // lado del visor con el que se colocó la foto

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  void _confirm(ui.Image img, double side) {
    final iw = img.width.toDouble(), ih = img.height.toDouble();
    final k = side / (iw < ih ? iw : ih); // píxeles del visor por píxel de la foto, sin zoom
    final m = _ctrl.value;
    final scale = m.getMaxScaleOnAxis();
    final t = m.getTranslation();
    final left = -t.x / scale / k, top = -t.y / scale / k; // esquina del cuadrado, en píxeles de la foto
    Navigator.pop(context, FrameCrop(left / iw, top / ih, 1 / scale));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        centerTitle: true,
        title: const Text('Encuadra la placa',
            style: TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w600)),
      ),
      body: SafeArea(
        child: FutureBuilder<ui.Image>(
          future: _decoded,
          builder: (context, snap) {
            if (snap.hasError) {
              return const Center(
                  child: Text('No se pudo abrir la foto', style: TextStyle(color: Colors.white70)));
            }
            if (!snap.hasData) return const Center(child: CircularProgressIndicator(color: Bio.mint));
            final img = snap.data!;
            return Column(children: [
              const SizedBox(height: 12),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                child: Text(
                  widget.showCircle
                      ? 'Pellizca para acercar y arrastra hasta que la placa llene el círculo. '
                          'Solo se analiza lo que queda dentro del cuadro.'
                      : 'Pellizca para acercar y arrastra para dejar la placa dentro del cuadro.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.white.withValues(alpha: 0.75)),
                ),
              ),
              const SizedBox(height: 16),
              Expanded(
                child: LayoutBuilder(builder: (context, c) {
                  final side = (c.maxWidth - 40).clamp(0.0, c.maxHeight).toDouble();
                  final iw = img.width.toDouble(), ih = img.height.toDouble();
                  final k = side / (iw < ih ? iw : ih);
                  final cw = iw * k, ch = ih * k; // la foto cubre el visor por completo
                  if (_side != side) {
                    _side = side;
                    // Al empezar, el cuadrado central (lo que antes se recortaba sin preguntar).
                    _ctrl.value = Matrix4.translationValues(-(cw - side) / 2, -(ch - side) / 2, 0);
                  }
                  return Center(
                    child: SizedBox(
                      width: side,
                      height: side,
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(20),
                        child: Stack(fit: StackFit.expand, children: [
                          InteractiveViewer(
                            transformationController: _ctrl,
                            constrained: false,
                            minScale: 1,
                            maxScale: 8,
                            boundaryMargin: EdgeInsets.zero,
                            child: SizedBox(width: cw, height: ch, child: Image.memory(widget.image, fit: BoxFit.fill)),
                          ),
                          IgnorePointer(child: CustomPaint(painter: FramePainter(showCircle: widget.showCircle))),
                        ]),
                      ),
                    ),
                  );
                }),
              ),
              const SizedBox(height: 20),
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
                child: Row(children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      style: OutlinedButton.styleFrom(
                          foregroundColor: Colors.white, side: const BorderSide(color: Colors.white38)),
                      onPressed: () => Navigator.pop(context),
                      icon: const Icon(Icons.replay),
                      label: const Text('Repetir'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    flex: 2,
                    child: FilledButton.icon(
                      style: FilledButton.styleFrom(backgroundColor: Bio.green),
                      onPressed: () => _confirm(img, _side!),
                      icon: const Icon(Icons.crop),
                      label: const Text('Usar este encuadre'),
                    ),
                  ),
                ]),
              ),
            ]);
          },
        ),
      ),
    );
  }
}

/// Círculo guía (80 % del lado) y esquinas del cuadro.
class FramePainter extends CustomPainter {
  FramePainter({required this.showCircle});
  final bool showCircle;

  @override
  void paint(Canvas canvas, Size s) {
    final c = s.center(Offset.zero);
    final r = s.shortestSide * guideFraction / 2;
    if (showCircle) {
      final shade = Path()
        ..fillType = PathFillType.evenOdd
        ..addRect(Offset.zero & s)
        ..addOval(Rect.fromCircle(center: c, radius: r));
      canvas.drawPath(shade, Paint()..color = Colors.black.withValues(alpha: 0.35));
      canvas.drawCircle(
          c,
          r,
          Paint()
            ..style = PaintingStyle.stroke
            ..strokeWidth = 2.5
            ..color = Bio.mint);
    }
    final corner = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 4
      ..strokeCap = StrokeCap.round
      ..color = Colors.white;
    const m = 18.0, l = 28.0;
    for (final (x, y, dx, dy) in [
      (m, m, 1.0, 1.0),
      (s.width - m, m, -1.0, 1.0),
      (m, s.height - m, 1.0, -1.0),
      (s.width - m, s.height - m, -1.0, -1.0),
    ]) {
      canvas.drawLine(Offset(x, y), Offset(x + l * dx, y), corner);
      canvas.drawLine(Offset(x, y), Offset(x, y + l * dy), corner);
    }
  }

  @override
  bool shouldRepaint(covariant FramePainter old) => old.showCircle != showCircle;
}
