import 'package:flutter/material.dart';

import '../theme.dart';

/// Tutorial de primer uso: tres pantallas sobre cómo tomar una buena foto con la caja de iluminación.
/// Se muestra una vez al entrar por primera vez, y siempre desde Perfil → Cómo tomar una buena foto.
class TutorialScreen extends StatefulWidget {
  const TutorialScreen({super.key});

  static Future<void> open(BuildContext context) => Navigator.of(context)
      .push(MaterialPageRoute(fullscreenDialog: true, builder: (_) => const TutorialScreen()));

  @override
  State<TutorialScreen> createState() => _TutorialScreenState();
}

class _Page {
  const _Page(this.icon, this.title, this.tips, this.drawing);
  final IconData icon;
  final String title;
  final List<String> tips;
  final Widget drawing;
}

const _pages = [
  _Page(Icons.light_mode_outlined, 'Usa la caja de iluminación', [
    'Pon la placa cerrada en el centro, sobre el fondo negro.',
    'Enciende el anillo LED: la luz rebota en el difusor y no hace reflejos.',
    'Pon la tapa y apoya el celular sobre el agujero: así todas las fotos salen a la misma altura.',
  ], _BoxDrawing()),
  _Page(Icons.center_focus_strong_outlined, 'Encaja la placa en el círculo', [
    'El borde de la placa debe tocar el círculo guía de la cámara: así la app mide las colonias en milímetros.',
    'Celular paralelo a la placa, sin inclinarlo.',
    'Toca la pantalla para enfocar y espera a que la imagen esté nítida.',
  ], _GuideDrawing()),
  _Page(Icons.fact_check_outlined, 'Revisa antes de confiar en el número', [
    'Indica la dilución y el volumen sembrado para obtener las UFC/mL.',
    'Si la app avisa de foto borrosa, oscura o con reflejos, repítela.',
    'Revisa las colonias marcadas y usa «Corregir conteo» si algo no cuadra: la corrección queda registrada.',
  ], _CheckDrawing()),
];

class _TutorialScreenState extends State<TutorialScreen> {
  final _controller = PageController();
  int _page = 0;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _next() {
    if (_page == _pages.length - 1) {
      Navigator.of(context).pop();
    } else {
      _controller.nextPage(duration: const Duration(milliseconds: 280), curve: Curves.easeOut);
    }
  }

  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    final last = _page == _pages.length - 1;
    return Scaffold(
      body: SafeArea(
        child: Column(children: [
          Align(
            alignment: Alignment.centerRight,
            child: TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('Saltar')),
          ),
          Expanded(
            child: PageView(
              controller: _controller,
              onPageChanged: (i) => setState(() => _page = i),
              children: [
                for (final p in _pages)
                  ListView(padding: const EdgeInsets.fromLTRB(24, 0, 24, 16), children: [
                    SizedBox(height: 200, child: Center(child: p.drawing)),
                    const SizedBox(height: 20),
                    Row(children: [
                      Icon(p.icon, color: Bio.green),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(p.title, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700)),
                      ),
                    ]),
                    const SizedBox(height: 16),
                    for (final (n, t) in p.tips.indexed)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 12),
                        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          CircleAvatar(
                            radius: 12,
                            backgroundColor: Bio.greenSoft,
                            child: Text('${n + 1}', style: const TextStyle(fontSize: 12, color: Bio.green, fontWeight: FontWeight.w700)),
                          ),
                          const SizedBox(width: 12),
                          Expanded(child: Text(t, style: TextStyle(fontSize: 15, height: 1.4, color: muted))),
                        ]),
                      ),
                  ]),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(24, 0, 24, 20),
            child: Row(children: [
              for (var i = 0; i < _pages.length; i++)
                AnimatedContainer(
                  duration: const Duration(milliseconds: 200),
                  margin: const EdgeInsets.only(right: 6),
                  width: i == _page ? 22 : 8,
                  height: 8,
                  decoration: BoxDecoration(
                    color: i == _page ? Bio.green : Bio.mint.withValues(alpha: 0.5),
                    borderRadius: BorderRadius.circular(4),
                  ),
                ),
              const Spacer(),
              FilledButton(
                style: FilledButton.styleFrom(minimumSize: const Size(140, 48)),
                onPressed: _next,
                child: Text(last ? 'Empezar' : 'Siguiente'),
              ),
            ]),
          ),
        ]),
      ),
    );
  }
}

/// Placa de Petri vista desde arriba, con colonias.
class _Plate extends StatelessWidget {
  const _Plate({this.size = 120});
  final double size;

  @override
  Widget build(BuildContext context) => CustomPaint(size: Size.square(size), painter: _PlatePainter());
}

class _PlatePainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size s) {
    final c = s.center(Offset.zero), r = s.width / 2;
    canvas.drawCircle(c, r, Paint()..color = const Color(0xFFF3E7C9));
    canvas.drawCircle(c, r, Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3
      ..color = const Color(0xFFBFC9C3));
    const pts = [(0.3, 0.35), (0.62, 0.3), (0.5, 0.55), (0.7, 0.62), (0.35, 0.68), (0.48, 0.28), (0.58, 0.78)];
    for (final (x, y) in pts) {
      canvas.drawCircle(Offset(s.width * x, s.height * y), r * 0.07, Paint()..color = const Color(0xFFD9B26A));
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter old) => false;
}

class _BoxDrawing extends StatelessWidget {
  const _BoxDrawing();

  @override
  Widget build(BuildContext context) => Container(
        width: 220,
        height: 180,
        decoration: BoxDecoration(
          color: const Color(0xFF1B2A30),
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: const Color(0xFF8FA3A0), width: 3),
        ),
        child: Stack(alignment: Alignment.center, children: [
          // Anillo LED y difusor alrededor de la placa
          Container(
            width: 160,
            height: 160,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              border: Border.all(color: const Color(0xFFFFE08A), width: 4),
              boxShadow: [BoxShadow(color: const Color(0xFFFFE08A).withValues(alpha: 0.45), blurRadius: 18)],
            ),
          ),
          Container(
            width: 128,
            height: 128,
            decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: Colors.white70, width: 3)),
          ),
          const _Plate(size: 108),
        ]),
      );
}

class _GuideDrawing extends StatelessWidget {
  const _GuideDrawing();

  @override
  Widget build(BuildContext context) => Container(
        width: 140,
        height: 196,
        decoration: BoxDecoration(color: Colors.black87, borderRadius: BorderRadius.circular(22)),
        child: Stack(alignment: Alignment.center, children: [
          const _Plate(size: 104),
          Container(
            width: 108,
            height: 108,
            decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: Bio.mint, width: 3)),
          ),
          const Positioned(bottom: 12, child: Icon(Icons.circle, color: Colors.white, size: 26)),
        ]),
      );
}

class _CheckDrawing extends StatelessWidget {
  const _CheckDrawing();

  @override
  Widget build(BuildContext context) => Stack(clipBehavior: Clip.none, children: [
        const _Plate(size: 150),
        Positioned(
          right: -18,
          bottom: -6,
          child: Container(
            padding: const EdgeInsets.all(10),
            decoration: const BoxDecoration(color: Bio.ok, shape: BoxShape.circle),
            child: const Icon(Icons.check, color: Colors.white, size: 30),
          ),
        ),
      ]);
}
