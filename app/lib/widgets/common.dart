import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../state/app_state.dart';
import '../theme.dart';
import 'format.dart';

/// Logotipo: doble hélice de ADN que termina en una hoja.
class BioLogo extends StatelessWidget {
  const BioLogo({super.key, this.size = 72, this.color = Bio.mint, this.accent = Colors.white});

  final double size;
  final Color color;
  final Color accent;

  @override
  Widget build(BuildContext context) =>
      CustomPaint(size: Size(size * 0.62, size), painter: _LogoPainter(color, accent));
}

class _LogoPainter extends CustomPainter {
  _LogoPainter(this.color, this.accent);
  final Color color;
  final Color accent;

  @override
  void paint(Canvas canvas, Size s) {
    final w = s.width, h = s.height;
    final top = h * 0.30, bottom = h;
    final strand = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = w * 0.11
      ..strokeCap = StrokeCap.round;
    final rung = Paint()
      ..strokeWidth = w * 0.06
      ..strokeCap = StrokeCap.round;

    Offset pt(double t, double phase) {
      final y = top + (bottom - top) * t;
      return Offset(w / 2 + (w * 0.36) * math.sin(t * 2 * math.pi * 1.25 + phase), y);
    }

    for (var k = 1; k < 8; k++) {
      final t = k / 8;
      rung.color = accent.withValues(alpha: 0.55);
      canvas.drawLine(pt(t, 0), pt(t, math.pi), rung);
    }
    for (final (phase, c) in [(0.0, color), (math.pi, accent)]) {
      final p = Path()..moveTo(pt(0, phase).dx, pt(0, phase).dy);
      for (var i = 1; i <= 40; i++) {
        final o = pt(i / 40, phase);
        p.lineTo(o.dx, o.dy);
      }
      canvas.drawPath(p, strand..color = c);
    }
    // Hoja en la parte superior.
    final base = pt(0, 0);
    final leaf = Path()
      ..moveTo(base.dx, base.dy)
      ..quadraticBezierTo(w * 0.05, h * 0.12, w * 0.62, 0)
      ..quadraticBezierTo(w * 0.78, h * 0.22, base.dx, base.dy)
      ..close();
    canvas.drawPath(leaf, Paint()..color = color);
    canvas.drawLine(base, Offset(w * 0.55, h * 0.05),
        Paint()
          ..color = accent.withValues(alpha: 0.6)
          ..strokeWidth = w * 0.035
          ..strokeCap = StrokeCap.round);
  }

  @override
  bool shouldRepaint(covariant _LogoPainter old) => old.color != color || old.accent != accent;
}

/// Imagen servida por la API (rutas relativas como /analyses/1/image/thumb).
class ApiImage extends StatelessWidget {
  const ApiImage(this.path, {super.key, this.fit = BoxFit.cover, this.radius = 12, this.width, this.height});

  final String? path;
  final BoxFit fit;
  final double radius;
  final double? width;
  final double? height;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final placeholder = Container(
      width: width,
      height: height,
      color: cs.surfaceContainerHighest,
      child: Icon(Icons.biotech_outlined, color: cs.onSurfaceVariant),
    );
    return ClipRRect(
      borderRadius: BorderRadius.circular(radius),
      child: path == null
          ? placeholder
          : Image.network(
              AppScope.of(context).api.url(path!),
              width: width,
              height: height,
              fit: fit,
              errorBuilder: (_, _, _) => placeholder,
              loadingBuilder: (_, child, progress) => progress == null ? child : placeholder,
            ),
    );
  }
}

class StatusChip extends StatelessWidget {
  const StatusChip(this.status, {super.key});
  final String status;

  @override
  Widget build(BuildContext context) {
    final c = statusColor(status);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(color: c.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(20)),
      child: Text(statusLabel(status), style: TextStyle(color: c, fontSize: 12, fontWeight: FontWeight.w600)),
    );
  }
}

class SectionHeader extends StatelessWidget {
  const SectionHeader(this.title, {super.key, this.action, this.onAction});
  final String title;
  final String? action;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(top: 8, bottom: 8),
        child: Row(children: [
          Expanded(
              child: Text(title, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700))),
          if (action != null) TextButton(onPressed: onAction, child: Text(action!)),
        ]),
      );
}

class EmptyState extends StatelessWidget {
  const EmptyState({super.key, required this.icon, required this.title, this.message, this.action});
  final IconData icon;
  final String title;
  final String? message;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Container(
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.08),
                shape: BoxShape.circle),
            child: Icon(icon, size: 36, color: Theme.of(context).colorScheme.primary),
          ),
          const SizedBox(height: 14),
          Text(title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
          if (message != null) ...[
            const SizedBox(height: 6),
            Text(message!, textAlign: TextAlign.center, style: TextStyle(color: muted)),
          ],
          if (action != null) ...[const SizedBox(height: 16), action!],
        ]),
      ),
    );
  }
}

/// Carga asíncrona con estados de cargando / error / datos y recarga al cambiar los datos globales.
class Loader<T> extends StatefulWidget {
  const Loader({super.key, required this.load, required this.builder, this.pageTitle});

  final Future<T> Function() load;

  /// Si se indica, cargando/error se muestran dentro de un Scaffold con este título
  /// (para pantallas completas cuyo Scaffold depende de los datos).
  final String? pageTitle;
  final Widget Function(BuildContext context, T data, Future<void> Function() reload) builder;

  @override
  State<Loader<T>> createState() => _LoaderState<T>();
}

class _LoaderState<T> extends State<Loader<T>> {
  Future<T>? _future;
  int _version = -1;

  Future<void> _reload() async {
    final f = widget.load();
    setState(() => _future = f);
    try {
      await f;
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    if (_version != state.dataVersion) {
      _version = state.dataVersion;
      _future = widget.load();
    }
    Widget page(Widget body) => widget.pageTitle == null
        ? body
        : Scaffold(appBar: AppBar(title: Text(widget.pageTitle!)), body: body);
    return FutureBuilder<T>(
      future: _future,
      builder: (context, snap) {
        if (snap.hasError) {
          return page(EmptyState(
            icon: Icons.cloud_off_outlined,
            title: 'No se pudo cargar',
            message: '${snap.error}',
            action: OutlinedButton.icon(
                onPressed: _reload, icon: const Icon(Icons.refresh), label: const Text('Reintentar')),
          ));
        }
        if (!snap.hasData) return page(const Center(child: CircularProgressIndicator()));
        return widget.builder(context, snap.data as T, _reload);
      },
    );
  }
}

void showSnack(BuildContext context, String msg) =>
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg), behavior: SnackBarBehavior.floating));
