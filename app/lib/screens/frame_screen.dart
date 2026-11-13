import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import '../theme.dart';

/// Fracción del lado del encuadre que ocupa el círculo guía.
const guideFraction = 0.80;

/// Cuadrado elegido sobre la foto: esquina superior izquierda (fracción del ancho y del alto) y lado (fracción
/// del lado corto). Es lo único que se envía a analizar. Puede salirse de la foto (valores < 0 o > 1): esa parte
/// se rellena de negro.
class FrameCrop {
  const FrameCrop(this.x, this.y, this.size);
  final double x, y, size;
}

/// Pasa el cuadro de la pantalla ([box], en píxeles del visor) a un recorte de la foto.
///
/// [view] es la transformación del visor (zoom y desplazamiento) y [k] los píxeles del visor por píxel de la foto
/// sin zoom.
FrameCrop cropFromView({
  required Rect box,
  required Matrix4 view,
  required double k,
  required double iw,
  required double ih,
}) {
  final s = view.entry(0, 0); // zoom (el visor no rota)
  final t = view.getTranslation();
  final left = (box.left - t.x) / s / k, top = (box.top - t.y) / s / k, side = box.width / s / k;
  return FrameCrop(left / iw, top / ih, side / math.min(iw, ih));
}

/// Encuadrar la placa sobre la foto ya tomada. Las esquinas del cuadro se arrastran para agrandarlo o achicarlo,
/// y la foto se pellizca y se mueve, incluso más allá de sus bordes (si la placa está en una esquina o no cabe
/// entera). Lo que queda dentro del cuadro es lo que se analiza, igual a lo que se ve aquí.
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
  static const _minSide = 60.0; // lado mínimo del cuadro en pantalla
  static const _handle = 44.0; // zona táctil de cada esquina

  final _ctrl = TransformationController();
  late final Future<ui.Image> _decoded = decodeImageFromList(widget.image);
  Size? _view; // tamaño del visor con el que se colocó todo
  late double _k;
  late Rect _box;

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  /// Al empezar: la foto entera a la vista y el cuadro sobre su cuadrado central.
  void _reset(Size view, double iw, double ih) {
    _view = view;
    _k = 0.9 * math.min(view.width / iw, view.height / ih);
    final cw = iw * _k, ch = ih * _k;
    _ctrl.value = Matrix4.translationValues((view.width - cw) / 2, (view.height - ch) / 2, 0);
    _box = Rect.fromCenter(center: view.center(Offset.zero), width: math.min(cw, ch), height: math.min(cw, ch));
  }

  /// Arrastrar la esquina [i] (0 arriba izq., 1 arriba der., 2 abajo izq., 3 abajo der.) con la opuesta fija.
  void _dragCorner(int i, Offset d) {
    final b = _box, view = _view!;
    final fixed = [b.bottomRight, b.bottomLeft, b.topRight, b.topLeft][i];
    final sx = i.isEven ? -1.0 : 1.0, sy = i < 2 ? -1.0 : 1.0; // hacia dónde crece el cuadro
    final maxSide = math.min(sx < 0 ? fixed.dx : view.width - fixed.dx, sy < 0 ? fixed.dy : view.height - fixed.dy);
    final side = (b.width + (sx * d.dx + sy * d.dy) / 2).clamp(_minSide, math.max(_minSide, maxSide)).toDouble();
    setState(() => _box = Rect.fromPoints(fixed, fixed + Offset(sx * side, sy * side)));
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
            final iw = img.width.toDouble(), ih = img.height.toDouble();
            return Column(children: [
              const SizedBox(height: 8),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                child: Text(
                  'Arrastra las esquinas para ajustar el cuadro. Pellizca y mueve la foto hasta que la placa '
                  '${widget.showCircle ? 'llene el círculo' : 'quede dentro'}; puedes salirte del borde. '
                  'Solo se analiza lo que queda dentro del cuadro.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.white.withValues(alpha: 0.75), fontSize: 13),
                ),
              ),
              const SizedBox(height: 8),
              Expanded(
                child: LayoutBuilder(builder: (context, c) {
                  final view = Size(c.maxWidth, c.maxHeight);
                  if (_view != view) _reset(view, iw, ih);
                  final corners = [_box.topLeft, _box.topRight, _box.bottomLeft, _box.bottomRight];
                  return ClipRect(
                    child: Stack(children: [
                      Positioned.fill(
                        child: InteractiveViewer(
                          transformationController: _ctrl,
                          constrained: false,
                          minScale: 0.2,
                          maxScale: 10,
                          boundaryMargin: const EdgeInsets.all(double.infinity),
                          child: SizedBox(
                              width: iw * _k, height: ih * _k, child: Image.memory(widget.image, fit: BoxFit.fill)),
                        ),
                      ),
                      Positioned.fill(
                        child: IgnorePointer(
                            child: CustomPaint(painter: FramePainter(showCircle: widget.showCircle, box: _box))),
                      ),
                      for (var i = 0; i < 4; i++)
                        Positioned(
                          left: corners[i].dx - _handle / 2,
                          top: corners[i].dy - _handle / 2,
                          width: _handle,
                          height: _handle,
                          child: GestureDetector(
                            key: ValueKey('esquina-$i'),
                            behavior: HitTestBehavior.opaque,
                            onPanUpdate: (e) => _dragCorner(i, e.delta),
                          ),
                        ),
                    ]),
                  );
                }),
              ),
              const SizedBox(height: 12),
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
                      onPressed: () => Navigator.pop(
                          context, cropFromView(box: _box, view: _ctrl.value, k: _k, iw: iw, ih: ih)),
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

/// Círculo guía (80 % del lado del cuadro) y esquinas del cuadro. Sin [box], el cuadro es todo el lienzo (vista
/// de la cámara).
class FramePainter extends CustomPainter {
  FramePainter({required this.showCircle, this.box});
  final bool showCircle;
  final Rect? box;

  @override
  void paint(Canvas canvas, Size s) {
    final b = box ?? Offset.zero & s;
    if (box != null) {
      // Lo que queda fuera del cuadro no se analiza: más oscuro y con borde fino
      canvas.drawPath(
          Path()
            ..fillType = PathFillType.evenOdd
            ..addRect(Offset.zero & s)
            ..addRect(b),
          Paint()..color = Colors.black.withValues(alpha: 0.6));
      canvas.drawRect(
          b,
          Paint()
            ..style = PaintingStyle.stroke
            ..strokeWidth = 1
            ..color = Colors.white70);
    }
    final c = b.center;
    final r = b.shortestSide * guideFraction / 2;
    if (showCircle) {
      final shade = Path()
        ..fillType = PathFillType.evenOdd
        ..addRect(b)
        ..addOval(Rect.fromCircle(center: c, radius: r));
      canvas.drawPath(shade, Paint()..color = Colors.black.withValues(alpha: 0.3));
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
    final m = box == null ? 18.0 : 0.0; // en la cámara, las esquinas un poco hacia dentro
    final l = math.min(28.0, b.shortestSide / 4);
    for (final (x, y, dx, dy) in [
      (b.left + m, b.top + m, 1.0, 1.0),
      (b.right - m, b.top + m, -1.0, 1.0),
      (b.left + m, b.bottom - m, 1.0, -1.0),
      (b.right - m, b.bottom - m, -1.0, -1.0),
    ]) {
      canvas.drawLine(Offset(x, y), Offset(x + l * dx, y), corner);
      canvas.drawLine(Offset(x, y), Offset(x, y + l * dy), corner);
    }
  }

  @override
  bool shouldRepaint(covariant FramePainter old) => old.showCircle != showCircle || old.box != box;
}
