import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../api/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';

typedef Added = ({double x, double y, double r});

/// Corrección manual del conteo sobre la foto original:
/// "Quitar" tacha una detección del modelo (reflejo, burbuja, mancha) y "Agregar" marca una colonia que el
/// modelo no vio. El servidor mide las agregadas, recalcula las UFC/mL y guarda el registro de la corrección.
class CorrectionScreen extends StatefulWidget {
  const CorrectionScreen(this.analysis, {super.key});
  final Analysis analysis;

  @override
  State<CorrectionScreen> createState() => _CorrectionScreenState();
}

class _CorrectionScreenState extends State<CorrectionScreen> {
  Analysis get a => widget.analysis;

  /// Todo lo que detectó el modelo, incluidas las colonias que ya se habían quitado.
  late final List<Colony> detected = [
    ...?a.colonies?.where((c) => !c.manual),
    ...a.removedColonies,
  ]..sort((x, y) => x.id.compareTo(y.id));

  late Set<int> removed = {...?a.correction?.removed};
  late List<Added> added = [...?a.correction?.added];
  final _history = <(Set<int>, List<Added>)>[];
  bool _addMode = false;
  bool _saving = false;

  double get _w => a.imageSize?[0] ?? 1000;
  double get _h => a.imageSize?[1] ?? 1000;

  /// Radio de una colonia nueva: la mediana de las detectadas (o 1,2 % del lado de la foto).
  double get _newRadius {
    if (detected.isEmpty) return math.min(_w, _h) * 0.012;
    final r = detected.map((c) => c.radius).toList()..sort();
    return r[r.length ~/ 2];
  }

  int get total => detected.length - removed.length + added.length;

  bool get _changed {
    final before = {...?a.correction?.removed};
    final beforeAdded = a.correction?.added ?? [];
    return removed.length != before.length ||
        !removed.containsAll(before) ||
        added.length != beforeAdded.length ||
        Iterable.generate(added.length).any((i) => added[i] != beforeAdded[i]);
  }

  void _apply(void Function() change) {
    _history.add(({...removed}, [...added]));
    setState(change);
  }

  void _undo() {
    if (_history.isEmpty) return;
    final (r, ad) = _history.removeLast();
    setState(() {
      removed = r;
      added = ad;
    });
  }

  void _tap(Offset p, double scale) {
    final tol = 10 / scale; // 10 px de pantalla de margen alrededor de cada colonia
    double dist(double x, double y) => (Offset(x, y) - p).distance;

    // 1) Tocar una colonia agregada la quita (en cualquier modo).
    final ai = added.indexWhere((c) => dist(c.x, c.y) <= c.r + tol);
    if (ai >= 0) return _apply(() => added.removeAt(ai));

    // 2) La detección más cercana bajo el dedo.
    Colony? hit;
    var best = double.infinity;
    for (final c in detected) {
      final d = dist(c.center[0], c.center[1]);
      if (d <= c.radius + tol && d < best) {
        best = d;
        hit = c;
      }
    }
    if (hit != null) {
      final id = hit.id;
      if (!_addMode || removed.contains(id)) {
        return _apply(() => removed.contains(id) ? removed.remove(id) : removed.add(id));
      }
      return showSnack(context, 'Esa colonia ya está contada');
    }

    // 3) Espacio vacío.
    if (_addMode) {
      _apply(() => added.add((x: p.dx, y: p.dy, r: _newRadius)));
    } else {
      showSnack(context, 'Toca una colonia marcada para quitarla, o cambia a "Agregar"');
    }
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    final state = AppScope.read(context);
    try {
      await state.api.correctColonies(a.id, removed: removed.toList()..sort(), added: added);
      state.dataChanged();
      if (!mounted) return;
      showSnack(context, 'Conteo corregido: $total colonias');
      Navigator.pop(context, true);
    } catch (e) {
      if (mounted) showSnack(context, '$e');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<bool> _confirmExit() async {
    if (!_changed) return true;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('¿Salir sin guardar?'),
        content: const Text('Se perderán los cambios de esta corrección.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Seguir corrigiendo')),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Salir')),
        ],
      ),
    );
    return ok ?? false;
  }

  @override
  Widget build(BuildContext context) {
    final muted = TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant, fontSize: 13);
    return PopScope(
      canPop: !_changed,
      onPopInvokedWithResult: (didPop, _) async {
        if (didPop) return;
        if (await _confirmExit() && context.mounted) Navigator.pop(context);
      },
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Corregir conteo'),
          actions: [
            IconButton(tooltip: 'Deshacer', icon: const Icon(Icons.undo), onPressed: _history.isEmpty ? null : _undo),
            PopupMenuButton<String>(
              onSelected: (_) => _apply(() {
                removed = {};
                added = [];
              }),
              itemBuilder: (_) => const [
                PopupMenuItem(value: 'reset', child: Text('Volver al conteo del modelo')),
              ],
            ),
          ],
        ),
        body: Column(children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 6),
            child: Column(children: [
              SegmentedButton<bool>(
                segments: const [
                  ButtonSegment(value: false, icon: Icon(Icons.remove_circle_outline), label: Text('Quitar')),
                  ButtonSegment(value: true, icon: Icon(Icons.add_circle_outline), label: Text('Agregar')),
                ],
                selected: {_addMode},
                onSelectionChanged: (s) => setState(() => _addMode = s.first),
              ),
              const SizedBox(height: 6),
              Text(
                  _addMode
                      ? 'Toca donde haya una colonia que el modelo no marcó.'
                      : 'Toca una colonia mal detectada (reflejo, burbuja, mancha) para tacharla.',
                  textAlign: TextAlign.center,
                  style: muted),
            ]),
          ),
          Expanded(
            child: Container(
              color: Colors.black,
              child: InteractiveViewer(
                maxScale: 10,
                child: Center(
                  child: AspectRatio(
                    aspectRatio: _w / _h,
                    child: LayoutBuilder(builder: (context, box) {
                      final scale = box.maxWidth / _w;
                      return GestureDetector(
                        onTapUp: (d) => _tap(d.localPosition / scale, scale),
                        child: Stack(children: [
                          Positioned.fill(child: ApiImage(a.originalUrl, fit: BoxFit.fill, radius: 0)),
                          Positioned.fill(
                            child: CustomPaint(painter: _Overlay(detected, removed, added, scale)),
                          ),
                        ]),
                      );
                    }),
                  ),
                ),
              ),
            ),
          ),
          SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 10, 16, 12),
              child: Row(children: [
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
                    Text('Total: $total colonias', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
                    const SizedBox(height: 2),
                    Wrap(spacing: 10, children: [
                      Text('Modelo ${detected.length}', style: muted),
                      Text('−${removed.length} quitadas', style: muted.copyWith(color: Bio.danger)),
                      Text('+${added.length} agregadas', style: muted.copyWith(color: Bio.warn)),
                    ]),
                  ]),
                ),
                FilledButton(
                  onPressed: _saving || !_changed ? null : _save,
                  child: _saving
                      ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Text('Guardar'),
                ),
              ]),
            ),
          ),
        ]),
      ),
    );
  }
}

class _Overlay extends CustomPainter {
  _Overlay(this.detected, this.removed, this.added, this.scale);
  final List<Colony> detected;
  final Set<int> removed;
  final List<Added> added;
  final double scale;

  @override
  void paint(Canvas canvas, Size size) {
    final kept = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2
      ..color = Bio.mint;
    final gone = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.5
      ..color = Bio.danger;
    final manual = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.5
      ..color = Bio.warn;
    for (final c in detected) {
      final o = Offset(c.center[0], c.center[1]) * scale;
      final r = c.radius * scale + 2;
      if (removed.contains(c.id)) {
        canvas.drawCircle(o, r, gone);
        final d = r * 0.7;
        canvas.drawLine(o + Offset(-d, -d), o + Offset(d, d), gone);
        canvas.drawLine(o + Offset(-d, d), o + Offset(d, -d), gone);
      } else {
        canvas.drawCircle(o, r, kept);
      }
    }
    for (final c in added) {
      final o = Offset(c.x, c.y) * scale;
      final r = c.r * scale + 2;
      canvas.drawCircle(o, r, manual);
      canvas.drawCircle(o, r, Paint()..color = Bio.warn.withValues(alpha: 0.18));
      final d = math.max(3.0, r * 0.45);
      canvas.drawLine(o + Offset(-d, 0), o + Offset(d, 0), manual);
      canvas.drawLine(o + Offset(0, -d), o + Offset(0, d), manual);
    }
  }

  @override
  bool shouldRepaint(covariant _Overlay old) => true;
}
