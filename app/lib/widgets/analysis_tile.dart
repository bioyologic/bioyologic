import 'package:flutter/material.dart';

import '../api/models.dart';
import '../screens/result_screen.dart';
import '../screens/trash_screen.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'common.dart';
import 'format.dart';

/// Pregunta antes de mandar análisis a la papelera.
Future<bool> confirmDeleteAnalyses(BuildContext context, int count, {String? name}) async {
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(count == 1 ? '¿Eliminar este análisis?' : '¿Eliminar $count análisis?'),
      content: Text(
          '${count == 1 && name != null ? '"$name"' : count == 1 ? 'El análisis' : 'Los análisis'} '
          '${count == 1 ? 'irá' : 'irán'} a la papelera. Podrás recuperarlo${count == 1 ? '' : 's'} durante 30 días '
          'desde la Papelera (en Perfil).'),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancelar')),
        FilledButton(
          style: FilledButton.styleFrom(backgroundColor: Bio.danger, minimumSize: const Size(0, 40)),
          onPressed: () => Navigator.pop(ctx, true),
          child: const Text('Eliminar'),
        ),
      ],
    ),
  );
  return ok ?? false;
}

/// Aviso tras borrar, con "Deshacer" (recupera de la papelera).
void showDeletedSnack(BuildContext context, List<int> ids) {
  final state = AppScope.read(context);
  final nav = Navigator.of(context);
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
    behavior: SnackBarBehavior.floating,
    duration: const Duration(seconds: 6),
    content: Text(ids.length == 1 ? 'Movido a la papelera' : '${ids.length} análisis movidos a la papelera'),
    action: SnackBarAction(
      label: 'Deshacer',
      onPressed: () async {
        try {
          await state.api.restoreAnalyses(ids);
          state.dataChanged();
        } catch (_) {
          nav.push(MaterialPageRoute(builder: (_) => const TrashScreen()));
        }
      },
    ),
  ));
}

/// Manda un análisis a la papelera tras confirmar; true si se borró.
Future<bool> deleteAnalysisWithConfirm(BuildContext context, Analysis a) async {
  if (!await confirmDeleteAnalyses(context, 1, name: a.sampleName) || !context.mounted) return false;
  final state = AppScope.read(context);
  try {
    await state.api.deleteAnalysis(a.id);
    state.dataChanged();
    if (context.mounted) showDeletedSnack(context, [a.id]);
    return true;
  } catch (e) {
    if (context.mounted) showSnack(context, '$e');
    return false;
  }
}

/// Fila de un análisis en "Últimos análisis" / historial.
///
/// - `selected != null`: modo selección (casilla en vez del estado; tocar marca o desmarca).
/// - `onDeleted != null`: se puede deslizar hacia la izquierda para borrarlo (con confirmación).
class AnalysisTile extends StatelessWidget {
  const AnalysisTile(this.a, {super.key, this.selected, this.onTap, this.onLongPress, this.onDeleted});
  final Analysis a;
  final bool? selected;
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;
  final VoidCallback? onDeleted;

  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    final sel = selected;
    final card = Card(
      color: sel == true ? Bio.greenSoft : null,
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: onTap ??
            () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => ResultScreen(analysisId: a.id))),
        onLongPress: onLongPress,
        child: Padding(
          padding: const EdgeInsets.all(10),
          child: Row(children: [
            ApiImage(a.thumbUrl, width: 58, height: 58),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(a.sampleName,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15)),
                const SizedBox(height: 2),
                Text('${a.summary.total} colonias${a.projectName != null ? ' · ${a.projectName}' : ''}'
                    '${a.isMine ? '' : ' · ${a.authorName}'}',
                    maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(color: muted, fontSize: 13)),
                const SizedBox(height: 2),
                Text(friendlyDate(a.createdAt), style: TextStyle(color: muted, fontSize: 12)),
              ]),
            ),
            if (sel == null && a.review != null && !a.review!.pending)
              Icon(a.review!.status == 'aprobado' ? Icons.verified : Icons.reply,
                  color: a.review!.status == 'aprobado' ? Bio.ok : Bio.danger, size: 20)
            else if (sel == null && a.review?.pending == true)
              const Icon(Icons.hourglass_top, color: Bio.warn, size: 20)
            else if (sel == null)
              StatusChip(a.summary.status)
            else
              Checkbox(value: sel, onChanged: (_) => onTap?.call()),
          ]),
        ),
      ),
    );
    // Solo su autor puede borrar un análisis (en proyectos compartidos hay placas de otros miembros).
    if (onDeleted == null || sel != null || !a.isMine) return card;
    return Dismissible(
      key: ValueKey('analisis-${a.id}'),
      direction: DismissDirection.endToStart,
      background: Container(
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: 24),
        decoration: BoxDecoration(color: Bio.danger, borderRadius: BorderRadius.circular(16)),
        child: const Row(mainAxisSize: MainAxisSize.min, children: [
          Text('Eliminar', style: TextStyle(color: Colors.white, fontWeight: FontWeight.w700)),
          SizedBox(width: 8),
          Icon(Icons.delete_outline, color: Colors.white),
        ]),
      ),
      confirmDismiss: (_) => deleteAnalysisWithConfirm(context, a),
      onDismissed: (_) => onDeleted!(),
      child: card,
    );
  }
}

/// Lista de análisis que se pueden borrar deslizando. El borrado se oculta al instante (lo exige
/// Dismissible) y luego se recarga la lista con `onChanged`.
class DeletableAnalysisList extends StatefulWidget {
  const DeletableAnalysisList(this.items, {super.key, required this.onChanged});
  final List<Analysis> items;
  final Future<void> Function() onChanged;

  @override
  State<DeletableAnalysisList> createState() => _DeletableAnalysisListState();
}

class _DeletableAnalysisListState extends State<DeletableAnalysisList> {
  final _hidden = <int>{};

  @override
  Widget build(BuildContext context) => Column(children: [
        for (final a in widget.items.where((a) => !_hidden.contains(a.id)))
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: AnalysisTile(a, onDeleted: () {
              setState(() => _hidden.add(a.id));
              widget.onChanged();
            }),
          ),
      ]);
}
