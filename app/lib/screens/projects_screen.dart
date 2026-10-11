import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../api/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/analysis_tile.dart';
import '../widgets/common.dart';
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
    return Loader<(Project, List<Analysis>)>(
      pageTitle: 'Proyecto',
      load: () async => (await api.project(projectId), await api.analyses(projectId: projectId, limit: 200)),
      builder: (context, data, reload) {
        final (p, items) = data;
        final cs = Theme.of(context).colorScheme;
        return Scaffold(
          appBar: AppBar(
            title: Text(p.name),
            actions: [
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
                const SectionHeader('Muestras'),
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
