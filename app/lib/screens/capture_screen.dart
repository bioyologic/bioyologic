import 'dart:typed_data';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../state/app_state.dart';
import '../theme.dart';
import 'new_analysis_screen.dart';

/// Fracción del lado corto de la foto que ocupa el círculo guía.
const guideFraction = 0.80;

/// Cámara con círculo guía para encuadrar la placa.
class CaptureScreen extends StatefulWidget {
  const CaptureScreen({super.key, this.projectId});

  final int? projectId;

  static Future<void> open(BuildContext context, {int? projectId}) => Navigator.of(context).push(
      MaterialPageRoute(fullscreenDialog: true, builder: (_) => CaptureScreen(projectId: projectId)));

  @override
  State<CaptureScreen> createState() => _CaptureScreenState();
}

class _CaptureScreenState extends State<CaptureScreen> {
  CameraController? _cam;
  List<CameraDescription> _cameras = [];
  int _camIndex = 0;
  String? _error;
  bool _busy = false;
  FlashMode _flash = FlashMode.off;

  @override
  void initState() {
    super.initState();
    _initCameras();
  }

  ResolutionPreset get _preset => switch (AppScope.read(context).resolution) {
        'media' => ResolutionPreset.medium,
        'maxima' => ResolutionPreset.max,
        _ => ResolutionPreset.high,
      };

  Future<void> _initCameras() async {
    try {
      _cameras = await availableCameras();
      if (_cameras.isEmpty) throw CameraException('none', 'Sin cámaras');
      final back = _cameras.indexWhere((c) => c.lensDirection == CameraLensDirection.back);
      _camIndex = back >= 0 ? back : 0;
      await _start();
    } catch (_) {
      if (mounted) setState(() => _error = 'No hay una cámara disponible en este dispositivo.');
    }
  }

  Future<void> _start() async {
    final old = _cam;
    final flashPref = AppScope.read(context).flashMode;
    final c = CameraController(_cameras[_camIndex], _preset, enableAudio: false);
    setState(() => _cam = null);
    await old?.dispose();
    try {
      await c.initialize();
      _flash = switch (flashPref) {
        'auto' => FlashMode.auto,
        'encendido' => FlashMode.always,
        _ => FlashMode.off,
      };
      try {
        await c.setFlashMode(_flash);
      } catch (_) {}
      if (mounted) setState(() => _cam = c);
    } catch (e) {
      await c.dispose();
      if (mounted) setState(() => _error = 'No se pudo abrir la cámara. Revisa los permisos.');
    }
  }

  @override
  void dispose() {
    _cam?.dispose();
    super.dispose();
  }

  Future<void> _toggleFlash() async {
    final next = switch (_flash) {
      FlashMode.off => FlashMode.auto,
      FlashMode.auto => FlashMode.always,
      _ => FlashMode.off,
    };
    try {
      await _cam?.setFlashMode(next);
      setState(() => _flash = next);
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('El flash no está disponible en esta cámara')));
      }
    }
  }

  Future<void> _shoot() async {
    final c = _cam;
    if (c == null || _busy) return;
    final useGuide = AppScope.read(context).focusGuide;
    setState(() => _busy = true);
    try {
      final x = await c.takePicture();
      await _continue(await x.readAsBytes(), 'placa.jpg', useGuide ? guideFraction : null);
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('No se pudo hacer la foto')));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _gallery() async {
    final x = await ImagePicker().pickImage(source: ImageSource.gallery, imageQuality: 95);
    if (x == null) return;
    await _continue(await x.readAsBytes(), x.name, null);
  }

  Future<void> _continue(Uint8List bytes, String name, double? plateFraction) async {
    if (!mounted) return;
    await Navigator.of(context).pushReplacement(MaterialPageRoute(
      builder: (_) => NewAnalysisScreen(
        image: bytes,
        filename: name,
        plateFraction: plateFraction,
        fromCamera: plateFraction != null,
        projectId: widget.projectId,
      ),
    ));
  }

  IconData get _flashIcon => switch (_flash) {
        FlashMode.auto => Icons.flash_auto,
        FlashMode.always => Icons.flash_on,
        _ => Icons.flash_off,
      };

  @override
  Widget build(BuildContext context) {
    final guide = AppScope.of(context).focusGuide;
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        leading: IconButton(icon: const Icon(Icons.close), onPressed: () => Navigator.pop(context)),
        centerTitle: true,
        title: const Text('Analizar muestra',
            style: TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w600)),
        actions: [
          if (_cam != null) IconButton(icon: Icon(_flashIcon), tooltip: 'Flash', onPressed: _toggleFlash),
        ],
      ),
      body: SafeArea(
        child: Column(children: [
          const SizedBox(height: 12),
          Text(guide ? 'Centra la placa dentro del círculo' : 'Encuadra la placa completa',
              style: TextStyle(color: Colors.white.withValues(alpha: 0.75))),
          const SizedBox(height: 16),
          Expanded(
            child: Center(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 20),
                child: AspectRatio(
                  aspectRatio: 1,
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(20),
                    child: Stack(fit: StackFit.expand, children: [
                      Container(color: const Color(0xFF151A17)),
                      if (_cam != null)
                        FittedBox(
                          fit: BoxFit.cover,
                          clipBehavior: Clip.hardEdge,
                          child: SizedBox(width: 1000, child: CameraPreview(_cam!)),
                        )
                      else if (_error != null)
                        _NoCamera(message: _error!, onGallery: _gallery)
                      else
                        const Center(child: CircularProgressIndicator(color: Bio.mint)),
                      IgnorePointer(child: CustomPaint(painter: _GuidePainter(showCircle: guide))),
                    ]),
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: 16),
          Container(
            padding: const EdgeInsets.all(4),
            decoration: BoxDecoration(color: Colors.white12, borderRadius: BorderRadius.circular(24)),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              _ModePill('Foto', selected: true, onTap: () {}),
              _ModePill('Galería', selected: false, onTap: _gallery),
            ]),
          ),
          const SizedBox(height: 20),
          Row(mainAxisAlignment: MainAxisAlignment.spaceEvenly, children: [
            IconButton(
              iconSize: 28,
              tooltip: 'Galería',
              onPressed: _gallery,
              icon: const Icon(Icons.photo_library_outlined, color: Colors.white),
            ),
            GestureDetector(
              onTap: _shoot,
              child: Container(
                width: 76,
                height: 76,
                padding: const EdgeInsets.all(5),
                decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: Colors.white, width: 3)),
                child: Container(
                  decoration: BoxDecoration(
                      shape: BoxShape.circle, color: _cam == null ? Colors.white24 : Colors.white),
                  child: _busy ? const Padding(padding: EdgeInsets.all(18), child: CircularProgressIndicator(strokeWidth: 3)) : null,
                ),
              ),
            ),
            IconButton(
              iconSize: 28,
              tooltip: 'Cambiar cámara',
              onPressed: _cameras.length > 1
                  ? () {
                      _camIndex = (_camIndex + 1) % _cameras.length;
                      _start();
                    }
                  : null,
              icon: Icon(Icons.cameraswitch_outlined, color: _cameras.length > 1 ? Colors.white : Colors.white24),
            ),
          ]),
          const SizedBox(height: 24),
        ]),
      ),
    );
  }
}

class _ModePill extends StatelessWidget {
  const _ModePill(this.label, {required this.selected, required this.onTap});
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => GestureDetector(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 8),
          decoration: BoxDecoration(
              color: selected ? Bio.green : Colors.transparent, borderRadius: BorderRadius.circular(20)),
          child: Text(label,
              style: TextStyle(color: Colors.white, fontWeight: selected ? FontWeight.w600 : FontWeight.w400)),
        ),
      );
}

class _NoCamera extends StatelessWidget {
  const _NoCamera({required this.message, required this.onGallery});
  final String message;
  final VoidCallback onGallery;

  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            const Icon(Icons.no_photography_outlined, color: Colors.white54, size: 40),
            const SizedBox(height: 10),
            Text(message, textAlign: TextAlign.center, style: const TextStyle(color: Colors.white70)),
            const SizedBox(height: 14),
            FilledButton.icon(
              style: FilledButton.styleFrom(backgroundColor: Bio.green, minimumSize: const Size(0, 44)),
              onPressed: onGallery,
              icon: const Icon(Icons.photo_library_outlined),
              label: const Text('Elegir de la galería'),
            ),
          ]),
        ),
      );
}

/// Círculo guía (80 % del lado) y esquinas de encuadre.
class _GuidePainter extends CustomPainter {
  _GuidePainter({required this.showCircle});
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
  bool shouldRepaint(covariant _GuidePainter old) => old.showCircle != showCircle;
}
