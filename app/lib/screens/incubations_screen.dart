import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../api/api_client.dart';
import '../api/models.dart';
import '../state/app_state.dart';
import '../state/reminders.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/format.dart';
import 'capture_screen.dart';

/// "24 h a 37 °C"
String incubationLabel(Incubation i) {
  final h = i.hours == i.hours.roundToDouble() ? '${i.hours.round()} h' : '${fmt(i.hours, 1)} h';
  return i.temperatureC == null ? h : '$h a ${fmt(i.temperatureC, 0)} °C';
}

/// "5 h 20 min" · "45 min"
String durationLabel(Duration d) {
  final h = d.inHours, m = d.inMinutes % 60;
  if (h >= 48) return '${(d.inHours / 24).floor()} d ${h % 24} h';
  return h > 0 ? '$h h ${m.toString().padLeft(2, '0')} min' : '${d.inMinutes} min';
}

/// Siembras en incubación: cuánto falta para leer cada una y acceso directo a analizar sus placas.
class IncubationsScreen extends StatelessWidget {
  const IncubationsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final api = AppScope.of(context).api;
    return Scaffold(
      appBar: AppBar(title: const Text('Incubación')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => showIncubationEditor(context),
        icon: const Icon(Icons.add),
        label: const Text('Nueva siembra'),
      ),
      body: Loader<List<Incubation>>(
        load: () async {
          final all = await api.incubations(includeDone: true);
          await Reminders.sync(all.where((i) => i.doneAt == null).toList());
          return all;
        },
        builder: (context, all, reload) {
          final pending = all.where((i) => i.doneAt == null).toList();
          final done = all.where((i) => i.doneAt != null).take(10).toList();
          if (all.isEmpty) {
            return EmptyState(
              icon: Icons.timer_outlined,
              title: 'Sin siembras en incubación',
              message: 'Registra la siembra al sembrar las placas: la app te avisará cuando estén listas para '
                  'leer y guardará las horas reales de incubación en el informe.',
              action: FilledButton.icon(
                  onPressed: () => showIncubationEditor(context),
                  icon: const Icon(Icons.add),
                  label: const Text('Registrar siembra')),
            );
          }
          return RefreshIndicator(
            onRefresh: reload,
            child: ListView(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 96),
              children: [
                if (!Reminders.supported)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Text('En la versión web no llegan avisos con la app cerrada: abre Bioyologic para ver '
                        'qué placas están listas. En la app de Android sí te llega la notificación.',
                        style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant, fontSize: 12.5)),
                  ),
                if (pending.isEmpty)
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 16),
                    child: Text('No hay placas incubando.', textAlign: TextAlign.center),
                  ),
                for (final i in pending)
                  Padding(padding: const EdgeInsets.only(bottom: 10), child: IncubationCard(i, onChanged: reload)),
                if (done.isNotEmpty) ...[
                  const SectionHeader('Leídas'),
                  for (final i in done)
                    Padding(padding: const EdgeInsets.only(bottom: 10), child: IncubationCard(i, onChanged: reload)),
                ],
              ],
            ),
          );
        },
      ),
    );
  }
}

/// Tarjeta de una siembra con cuenta regresiva (se actualiza cada minuto).
class IncubationCard extends StatelessWidget {
  const IncubationCard(this.i, {super.key, required this.onChanged, this.compact = false});
  final Incubation i;
  final Future<void> Function() onChanged;
  final bool compact;

  Future<void> _markDone(BuildContext context) async {
    final state = AppScope.read(context);
    try {
      await state.api.updateIncubation(i.id, done: i.doneAt == null);
      state.dataChanged();
    } on ApiException catch (e) {
      if (context.mounted) showSnack(context, e.message);
    }
  }

  Future<void> _delete(BuildContext context) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('¿Eliminar la siembra?'),
        content: Text('Se borra el recordatorio de "${i.name}". Los análisis ya hechos se conservan.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancelar')),
          TextButton(
              style: TextButton.styleFrom(foregroundColor: Bio.danger),
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Eliminar')),
        ],
      ),
    );
    if (ok != true || !context.mounted) return;
    final state = AppScope.read(context);
    try {
      await state.api.deleteIncubation(i.id);
      state.dataChanged();
    } on ApiException catch (e) {
      if (context.mounted) showSnack(context, e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return StreamBuilder<int>(
      stream: Stream.periodic(const Duration(minutes: 1), (n) => n),
      builder: (context, _) {
        final now = DateTime.now();
        final done = i.doneAt != null;
        final ready = i.isReady(now);
        final total = i.readyAt.difference(i.seededAt).inSeconds;
        final progress = total <= 0 ? 1.0 : (now.difference(i.seededAt).inSeconds / total).clamp(0.0, 1.0);
        final color = done ? cs.onSurfaceVariant : (ready ? Bio.ok : Bio.green);
        final status = done
            ? 'Leída · ${i.analysesCount} placa${i.analysesCount == 1 ? '' : 's'} analizada${i.analysesCount == 1 ? '' : 's'}'
            : ready
                ? 'Lista para leer${now.difference(i.readyAt).inMinutes >= 30 ? ' · hace ${durationLabel(now.difference(i.readyAt))}' : ''}'
                : 'Faltan ${durationLabel(i.readyAt.difference(now))} · ${friendlyDate(i.readyAt)}';
        final where = [
          if (i.projectName != null) i.projectName!,
          if (i.sampleGroup.isNotEmpty) 'Muestra ${i.sampleGroup}',
          if (i.plates != null) '${i.analysesCount}/${i.plates} placas',
          if (!i.isMine && i.createdBy.isNotEmpty) 'por ${i.createdBy}',
        ].join(' · ');
        return Card(
          color: ready && !done ? Bio.ok.withValues(alpha: 0.08) : null,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(14, 12, 6, 12),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Icon(done ? Icons.check_circle_outline : (ready ? Icons.notifications_active_outlined : Icons.timer_outlined),
                    color: color),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(i.name, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
                    Text('${incubationLabel(i)} · sembrada ${friendlyDate(i.seededAt).toLowerCase()}',
                        style: TextStyle(color: cs.onSurfaceVariant, fontSize: 12.5)),
                  ]),
                ),
                PopupMenuButton<String>(
                  onSelected: (v) => v == 'done' ? _markDone(context) : _delete(context),
                  itemBuilder: (_) => [
                    PopupMenuItem(value: 'done', child: Text(done ? 'Volver a incubación' : 'Ya las leí')),
                    if (i.isMine) const PopupMenuItem(value: 'delete', child: Text('Eliminar')),
                  ],
                ),
              ]),
              const SizedBox(height: 8),
              Padding(
                padding: const EdgeInsets.only(right: 8),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(6),
                  child: LinearProgressIndicator(
                      value: done ? 1 : progress, minHeight: 6, color: color, backgroundColor: cs.surfaceContainerHighest),
                ),
              ),
              const SizedBox(height: 6),
              Text(status, style: TextStyle(color: color, fontWeight: FontWeight.w600, fontSize: 13)),
              if (where.isNotEmpty && !compact)
                Padding(
                  padding: const EdgeInsets.only(top: 2),
                  child: Text(where, style: TextStyle(color: cs.onSurfaceVariant, fontSize: 12.5)),
                ),
              if (!done && (ready || !compact))
                Padding(
                  padding: const EdgeInsets.only(top: 8, right: 8),
                  child: Row(children: [
                    Expanded(
                      child: ready
                          ? FilledButton.icon(
                              onPressed: () => CaptureScreen.open(context, incubation: i),
                              icon: const Icon(Icons.add_a_photo_outlined, size: 18),
                              label: const Text('Analizar placa'),
                            )
                          : OutlinedButton.icon(
                              onPressed: () => CaptureScreen.open(context, incubation: i),
                              icon: const Icon(Icons.add_a_photo_outlined, size: 18),
                              label: const Text('Analizar antes de tiempo'),
                            ),
                    ),
                  ]),
                ),
            ]),
          ),
        );
      },
    );
  }
}

/// Registrar una siembra nueva.
Future<void> showIncubationEditor(BuildContext context, {int? projectId}) async {
  final state = AppScope.read(context);
  final name = TextEditingController();
  final group = TextEditingController();
  final plates = TextEditingController();
  final otherHours = TextEditingController();
  final formKey = GlobalKey<FormState>();
  var hours = 24.0;
  double? temp = 37;
  var seeded = DateTime.now();
  var pid = projectId;
  List<Project> projects = [];
  try {
    projects = await state.api.projects();
  } catch (_) {}
  if (!context.mounted) return;

  await showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (ctx) => StatefulBuilder(
      builder: (ctx, setSheet) => Padding(
        padding: EdgeInsets.fromLTRB(20, 0, 20, 20 + MediaQuery.viewInsetsOf(ctx).bottom),
        child: Form(
          key: formKey,
          child: ListView(shrinkWrap: true, children: [
            const Text('Nueva siembra', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
            const SizedBox(height: 4),
            Text('Te avisaremos cuando las placas estén listas para leer.',
                style: TextStyle(color: Theme.of(ctx).colorScheme.onSurfaceVariant)),
            const SizedBox(height: 16),
            TextFormField(
              controller: name,
              autofocus: true,
              textCapitalization: TextCapitalization.sentences,
              decoration: const InputDecoration(labelText: 'Qué sembraste', hintText: 'p. ej. Agua de río'),
              validator: (v) => (v == null || v.trim().isEmpty) ? 'Obligatorio' : null,
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<int?>(
              initialValue: pid,
              decoration: const InputDecoration(labelText: 'Proyecto'),
              items: [
                const DropdownMenuItem(value: null, child: Text('Sin proyecto')),
                for (final p in projects) DropdownMenuItem(value: p.id, child: Text(p.name)),
              ],
              onChanged: (v) => setSheet(() => pid = v),
            ),
            const SizedBox(height: 12),
            Row(children: [
              Expanded(
                flex: 3,
                child: TextFormField(
                  controller: group,
                  decoration: const InputDecoration(labelText: 'Muestra (opcional)'),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                flex: 2,
                child: TextFormField(
                  controller: plates,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(labelText: 'N.º de placas'),
                  validator: (v) => (v == null || v.isEmpty || (int.tryParse(v) ?? 0) > 0) ? null : 'Número > 0',
                ),
              ),
            ]),
            const SizedBox(height: 16),
            const Text('Tiempo de incubación', style: TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 6),
            Wrap(spacing: 8, children: [
              for (final h in [24.0, 48.0, 72.0])
                ChoiceChip(
                  label: Text('${h.round()} h'),
                  selected: hours == h && otherHours.text.isEmpty,
                  onSelected: (_) => setSheet(() {
                    hours = h;
                    otherHours.clear();
                  }),
                ),
              SizedBox(
                width: 110,
                child: TextField(
                  controller: otherHours,
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  decoration: const InputDecoration(labelText: 'Otro', suffixText: 'h', isDense: true),
                  onChanged: (v) => setSheet(() => hours = double.tryParse(v.replaceAll(',', '.')) ?? hours),
                ),
              ),
            ]),
            const SizedBox(height: 12),
            const Text('Temperatura', style: TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 6),
            Wrap(spacing: 8, children: [
              for (final t in [30.0, 35.0, 37.0])
                ChoiceChip(label: Text('${t.round()} °C'), selected: temp == t, onSelected: (_) => setSheet(() => temp = t)),
              ChoiceChip(label: const Text('No indicar'), selected: temp == null, onSelected: (_) => setSheet(() => temp = null)),
            ]),
            const SizedBox(height: 4),
            Text('Referencia: recuento de aerobios mesófilos (ISO 4833-1), 72 h a 30 °C. Sigue el protocolo de tu laboratorio.',
                style: TextStyle(color: Theme.of(ctx).colorScheme.onSurfaceVariant, fontSize: 12)),
            const SizedBox(height: 8),
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.schedule),
              title: Text('Sembrada: ${friendlyDate(seeded)}'),
              subtitle: Text('Lista: ${DateFormat("EEE d MMM, HH:mm", 'es').format(seeded.add(Duration(minutes: (hours * 60).round())))}'),
              trailing: const Text('Cambiar'),
              onTap: () async {
                final day = await showDatePicker(
                    context: ctx,
                    initialDate: seeded,
                    firstDate: DateTime.now().subtract(const Duration(days: 14)),
                    lastDate: DateTime.now());
                if (day == null || !ctx.mounted) return;
                final t = await showTimePicker(context: ctx, initialTime: TimeOfDay.fromDateTime(seeded));
                if (t == null) return;
                setSheet(() => seeded = DateTime(day.year, day.month, day.day, t.hour, t.minute));
              },
            ),
            const SizedBox(height: 12),
            FilledButton.icon(
              icon: const Icon(Icons.timer_outlined),
              label: const Text('Empezar a contar'),
              onPressed: () async {
                if (!formKey.currentState!.validate()) return;
                if (hours <= 0) return showSnack(ctx, 'Indica las horas de incubación');
                try {
                  await state.api.createIncubation(
                    name: name.text.trim(),
                    hours: hours,
                    temperatureC: temp,
                    seededAt: seeded,
                    projectId: pid,
                    sampleGroup: group.text.trim(),
                    plates: int.tryParse(plates.text),
                  );
                  await Reminders.requestPermission();
                  state.dataChanged();
                  if (ctx.mounted) Navigator.pop(ctx);
                } on ApiException catch (e) {
                  if (ctx.mounted) showSnack(ctx, e.message);
                }
              },
            ),
          ]),
        ),
      ),
    ),
  );
}
