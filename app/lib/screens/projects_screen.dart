import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/api_client.dart';
import '../api/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/analysis_tile.dart';
import '../widgets/common.dart';
import 'samples_screen.dart';
import '../widgets/format.dart';
import 'capture_screen.dart';

class ProjectsScreen extends StatelessWidget {
  const ProjectsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final api = AppScope.of(context).api;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Mis proyectos'),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 12),
            child: FilledButton.icon(
              style: FilledButton.styleFrom(minimumSize: const Size(0, 38), padding: const EdgeInsets.symmetric(horizontal: 14)),
              onPressed: () => showProjectEditor(context),
              icon: const Icon(Icons.add, size: 18),
              label: const Text('Nuevo proyecto'),
            ),
          ),
        ],
      ),
      body: Loader<List<Project>>(
        load: api.projects,
        builder: (context, projects, reload) => projects.isEmpty
            ? EmptyState(
                icon: Icons.folder_open_outlined,
                title: 'Sin proyectos',
                message: 'Agrupa tus análisis por experimento, muestra o fecha.',
                action: FilledButton.icon(
                    onPressed: () => showProjectEditor(context),
                    icon: const Icon(Icons.add),
                    label: const Text('Crear proyecto')),
              )
            : RefreshIndicator(
                onRefresh: reload,
                child: ListView.separated(
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
                  itemCount: projects.length,
                  separatorBuilder: (_, _) => const SizedBox(height: 10),
                  itemBuilder: (_, i) => _ProjectCard(projects[i]),
                ),
              ),
      ),
    );
  }
}

class _ProjectCard extends StatelessWidget {
  const _ProjectCard(this.p);
  final Project p;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final when = p.lastAnalysisAt ?? p.createdAt;
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => ProjectDetailScreen(p.id))),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(children: [
            ApiImage(p.coverUrl, width: 64, height: 64),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(p.name, maxLines: 1, overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15)),
                const SizedBox(height: 2),
                Text('${p.analysesCount} análisis · ${friendlyDate(when).split(',').first}',
                    style: TextStyle(color: cs.onSurfaceVariant, fontSize: 12.5)),
                const SizedBox(height: 8),
                Row(children: [
                  Expanded(
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(6),
                      child: LinearProgressIndicator(
                          value: p.progress, minHeight: 6, color: Bio.ok, backgroundColor: cs.surfaceContainerHighest),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text('${(p.progress * 100).round()}%', style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
                ]),
              ]),
            ),
            const SizedBox(width: 4),
            Icon(Icons.chevron_right, color: cs.onSurfaceVariant),
          ]),
        ),
      ),
    );
  }
}

class ProjectDetailScreen extends StatelessWidget {
  const ProjectDetailScreen(this.projectId, {super.key});
  final int projectId;

  @override
  Widget build(BuildContext context) {
    final api = AppScope.of(context).api;
    return Loader<(Project, List<Analysis>, List<Sample>)>(
      pageTitle: 'Proyecto',
      load: () async => (
        await api.project(projectId),
        await api.analyses(projectId: projectId, limit: 200),
        await api.samples(projectId: projectId),
      ),
      builder: (context, data, reload) {
        final (p, items, samples) = data;
        final cs = Theme.of(context).colorScheme;
        return Scaffold(
          appBar: AppBar(
            title: Text(p.name),
            actions: [
              IconButton(
                tooltip: 'Exportar a Excel (CSV)',
                icon: const Icon(Icons.download_outlined),
                onPressed: () => exportCsv(context, projectId: p.id),
              ),
              PopupMenuButton<String>(
                onSelected: (v) async {
                  if (v == 'edit') {
                    await showProjectEditor(context, project: p);
                  } else if (v == 'delete') {
                    await _delete(context, p);
                  }
                },
                itemBuilder: (_) => const [
                  PopupMenuItem(value: 'edit', child: Text('Editar')),
                  PopupMenuItem(value: 'delete', child: Text('Eliminar proyecto')),
                ],
              ),
            ],
          ),
          floatingActionButton: FloatingActionButton.extended(
            onPressed: () => CaptureScreen.open(context, projectId: p.id),
            icon: const Icon(Icons.add_a_photo_outlined),
            label: const Text('Añadir muestra'),
          ),
          body: RefreshIndicator(
            onRefresh: reload,
            child: ListView(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 96),
              children: [
                if (p.description.isNotEmpty) ...[
                  Text(p.description, style: TextStyle(color: cs.onSurfaceVariant)),
                  const SizedBox(height: 12),
                ],
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(children: [
                      Row(children: [
                        _Kpi('${p.analysesCount}/${p.targetSamples}', 'Muestras'),
                        _Kpi('${p.coloniesTotal}', 'Colonias'),
                        _Kpi(p.analysesCount == 0 ? '—' : fmt(p.coloniesTotal / p.analysesCount, 0), 'Media/placa'),
                      ]),
                      const SizedBox(height: 12),
                      ClipRRect(
                        borderRadius: BorderRadius.circular(6),
                        child: LinearProgressIndicator(
                            value: p.progress, minHeight: 8, color: Bio.ok, backgroundColor: cs.surfaceContainerHighest),
                      ),
                    ]),
                  ),
                ),
                const SizedBox(height: 4),
                if (samples.isNotEmpty) ...[
                  const SectionHeader('UFC/mL por muestra'),
                  if (samples.where((m) => m.cfuPerMl != null).length >= 2)
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.fromLTRB(12, 14, 12, 10),
                        child: CfuChart(samples.reversed.where((m) => m.cfuPerMl != null).toList()),
                      ),
                    ),
                  for (final m in samples) Padding(padding: const EdgeInsets.only(bottom: 8), child: SampleCard(m)),
                ],
                const SectionHeader('Placas'),
                if (items.isEmpty)
                  const EmptyState(icon: Icons.science_outlined, title: 'Sin muestras',
                      message: 'Añade la primera placa a este proyecto.')
                else
                  for (final a in items) Padding(padding: const EdgeInsets.only(bottom: 10), child: AnalysisTile(a)),
              ],
            ),
          ),
        );
      },
    );
  }

  Future<void> _delete(BuildContext context, Project p) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('¿Eliminar proyecto?'),
        content: Text('Se eliminará "${p.name}". Sus ${p.analysesCount} análisis se conservarán sin proyecto.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancelar')),
          FilledButton(
              style: FilledButton.styleFrom(backgroundColor: Bio.danger, minimumSize: const Size(0, 40)),
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Eliminar')),
        ],
      ),
    );
    if (ok != true || !context.mounted) return;
    final state = AppScope.read(context);
    await state.api.deleteProject(p.id);
    state.dataChanged();
    if (context.mounted) Navigator.pop(context);
  }
}

class _Kpi extends StatelessWidget {
  const _Kpi(this.value, this.label);
  final String value;
  final String label;

  @override
  Widget build(BuildContext context) => Expanded(
        child: Column(children: [
          Text(value, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700)),
          Text(label, style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant)),
        ]),
      );
}

/// Crear o editar un proyecto.
Future<void> showProjectEditor(BuildContext context, {Project? project}) async {
  final name = TextEditingController(text: project?.name);
  final desc = TextEditingController(text: project?.description);
  final target = TextEditingController(text: '${project?.targetSamples ?? 10}');
  final formKey = GlobalKey<FormState>();
  final state = AppScope.read(context);

  await showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (ctx) => Padding(
      padding: EdgeInsets.fromLTRB(20, 0, 20, 20 + MediaQuery.viewInsetsOf(ctx).bottom),
      child: Form(
        key: formKey,
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text(project == null ? 'Nuevo proyecto' : 'Editar proyecto',
              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
          const SizedBox(height: 16),
          TextFormField(
            controller: name,
            autofocus: true,
            decoration: const InputDecoration(labelText: 'Nombre'),
            validator: (v) => (v == null || v.trim().isEmpty) ? 'Obligatorio' : null,
          ),
          const SizedBox(height: 12),
          TextFormField(controller: desc, maxLines: 2, decoration: const InputDecoration(labelText: 'Descripción')),
          const SizedBox(height: 12),
          TextFormField(
            controller: target,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(labelText: 'Muestras previstas', helperText: 'Para la barra de progreso'),
            validator: (v) => (int.tryParse(v ?? '') ?? 0) < 1 ? 'Número mayor que 0' : null,
          ),
          const SizedBox(height: 20),
          FilledButton(
            onPressed: () async {
              if (!formKey.currentState!.validate()) return;
              try {
                if (project == null) {
                  await state.api.createProject(name.text.trim(),
                      description: desc.text.trim(), targetSamples: int.parse(target.text));
                } else {
                  await state.api.updateProject(project.id,
                      name: name.text.trim(), description: desc.text.trim(), targetSamples: int.parse(target.text));
                }
                state.dataChanged();
                if (ctx.mounted) Navigator.pop(ctx);
              } on ApiException catch (e) {
                if (ctx.mounted) showSnack(ctx, e.message);
              }
            },
            child: Text(project == null ? 'Crear proyecto' : 'Guardar'),
          ),
        ]),
      ),
    ),
  );
}


/// Descarga en CSV (Excel) los análisis de un proyecto, o todos si no se indica proyecto.
Future<void> exportCsv(BuildContext context, {int? projectId}) async {
  try {
    final link = await AppScope.read(context).api.csvExportLink(projectId: projectId);
    await launchUrl(Uri.parse(link), mode: LaunchMode.externalApplication);
  } catch (e) {
    if (context.mounted) showSnack(context, '$e');
  }
}

/// Barras de UFC/mL por muestra (escala logarítmica: los valores cambian en órdenes de magnitud).
class CfuChart extends StatelessWidget {
  const CfuChart(this.samples, {super.key});
  final List<Sample> samples;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final logs = [for (final m in samples) math.log(m.cfuPerMl!) / math.ln10];
    final lo = (logs.reduce(math.min) - 0.5).floorToDouble();
    final hi = (logs.reduce(math.max) + 0.2).ceilToDouble();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('UFC/mL (escala logarítmica)', style: TextStyle(color: cs.onSurfaceVariant, fontSize: 12)),
      const SizedBox(height: 10),
      SizedBox(
        height: 150,
        child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
          for (var i = 0; i < samples.length; i++)
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 4),
                child: Column(mainAxisAlignment: MainAxisAlignment.end, children: [
                  Text(scientific(samples[i].cfuPerMl!), maxLines: 1, overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 10.5, fontWeight: FontWeight.w700)),
                  const SizedBox(height: 4),
                  Container(
                    height: 110 * ((logs[i] - lo) / (hi - lo)).clamp(0.05, 1.0),
                    decoration: BoxDecoration(
                      color: samples[i].estimated ? Bio.warn.withValues(alpha: 0.7) : Bio.green,
                      borderRadius: const BorderRadius.vertical(top: Radius.circular(6)),
                    ),
                  ),
                ]),
              ),
            ),
        ]),
      ),
      const SizedBox(height: 6),
      Row(children: [
        for (final m in samples)
          Expanded(
            child: Text(m.name, textAlign: TextAlign.center, maxLines: 2, overflow: TextOverflow.ellipsis,
                style: TextStyle(fontSize: 10.5, color: cs.onSurfaceVariant)),
          ),
      ]),
    ]);
  }
}
