import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../api/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/format.dart';

/// Papelera: los análisis borrados se pueden recuperar durante 30 días; después, o al vaciarla, se eliminan
/// definitivamente con sus fotos.
class TrashScreen extends StatelessWidget {
  const TrashScreen({super.key});

  static Future<bool> _confirm(BuildContext context, String title, String body, String action) async =>
      await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: Text(title),
          content: Text(body),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancelar')),
            FilledButton(
              style: FilledButton.styleFrom(backgroundColor: Bio.danger, minimumSize: const Size(0, 40)),
              onPressed: () => Navigator.pop(ctx, true),
              child: Text(action),
            ),
          ],
        ),
      ) ??
      false;

  static Future<void> _run(BuildContext context, Future<int> Function() action, String Function(int) done) async {
    final state = AppScope.read(context);
    try {
      final n = await action();
      state.dataChanged();
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).hideCurrentSnackBar(); // p. ej. el "Movido a la papelera" de antes
      showSnack(context, done(n));
    } on ApiException catch (e) {
      if (context.mounted) showSnack(context, e.message);
    }
  }

  static Future<void> restore(BuildContext context, [List<int>? ids]) => _run(
      context,
      () => AppScope.read(context).api.restoreAnalyses(ids),
      (n) => n == 1 ? 'Análisis recuperado' : '$n análisis recuperados');

  static Future<void> purge(BuildContext context, {Analysis? one, int total = 0}) async {
    final ok = await _confirm(
      context,
      one == null ? '¿Vaciar la papelera?' : '¿Eliminar definitivamente?',
      one == null
          ? 'Se borrarán para siempre los $total análisis de la papelera, con sus fotos. No se puede deshacer.'
          : '"${one.sampleName}" se borrará para siempre, con sus fotos. No se puede deshacer.',
      one == null ? 'Vaciar' : 'Eliminar',
    );
    if (!ok || !context.mounted) return;
    await _run(context, () => AppScope.read(context).api.purgeAnalyses(one == null ? null : [one.id]),
        (n) => n == 1 ? 'Eliminado definitivamente' : '$n análisis eliminados definitivamente');
  }

  @override
  Widget build(BuildContext context) {
    final api = AppScope.of(context).api;
    return Loader<List<Analysis>>(
      pageTitle: 'Papelera',
      load: api.trash,
      builder: (context, items, reload) => Scaffold(
        appBar: AppBar(
          title: const Text('Papelera'),
          actions: [
            if (items.isNotEmpty)
              PopupMenuButton<String>(
                onSelected: (v) => v == 'restore' ? restore(context) : purge(context, total: items.length),
                itemBuilder: (_) => const [
                  PopupMenuItem(value: 'restore', child: Text('Recuperar todo')),
                  PopupMenuItem(value: 'empty', child: Text('Vaciar papelera')),
                ],
              ),
          ],
        ),
        body: items.isEmpty
            ? const EmptyState(
                icon: Icons.delete_outline,
                title: 'La papelera está vacía',
                message: 'Lo que elimines queda aquí 30 días: puedes recuperarlo o borrarlo para siempre.')
            : RefreshIndicator(
                onRefresh: reload,
                child: ListView(
                  padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
                  children: [
                    Padding(
                      padding: const EdgeInsets.only(bottom: 10),
                      child: Text('Los análisis se eliminan definitivamente 30 días después de borrarlos.',
                          style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant, fontSize: 13)),
                    ),
                    for (final a in items)
                      Padding(padding: const EdgeInsets.only(bottom: 10), child: _TrashTile(a)),
                  ],
                ),
              ),
      ),
    );
  }
}

class _TrashTile extends StatelessWidget {
  const _TrashTile(this.a);
  final Analysis a;

  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    final dias = a.purgeAt == null ? null : (a.purgeAt!.difference(DateTime.now()).inHours / 24).ceil();
    return Card(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(10, 10, 4, 10),
        child: Row(children: [
          Opacity(opacity: 0.6, child: ApiImage(a.thumbUrl, width: 54, height: 54)),
          const SizedBox(width: 12),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(a.sampleName,
                  maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w600)),
              Text('${a.summary.total} colonias${a.projectName != null ? ' · ${a.projectName}' : ''}',
                  maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(color: muted, fontSize: 12.5)),
              if (a.deletedAt != null)
                Text('Borrado ${friendlyDate(a.deletedAt!).toLowerCase()}'
                    '${dias == null ? '' : ' · se elimina en ${dias <= 1 ? '1 día' : '$dias días'}'}',
                    style: TextStyle(color: (dias ?? 30) <= 3 ? Bio.danger : muted, fontSize: 12)),
            ]),
          ),
          IconButton(
            tooltip: 'Recuperar',
            icon: const Icon(Icons.restore, color: Bio.green),
            onPressed: () => TrashScreen.restore(context, [a.id]),
          ),
          IconButton(
            tooltip: 'Eliminar definitivamente',
            icon: const Icon(Icons.delete_forever_outlined, color: Bio.danger),
            onPressed: () => TrashScreen.purge(context, one: a),
          ),
        ]),
      ),
    );
  }
}
