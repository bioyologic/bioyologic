import 'package:flutter/material.dart';

import '../api/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/format.dart';
import 'result_screen.dart';

String _ufc(Sample m) => m.cfuPerMl == null ? '—' : scientific(m.cfuPerMl!);

/// Tarjeta de una muestra: UFC/mL combinada y cuántas placas entraron en el cálculo.
class SampleCard extends StatelessWidget {
  const SampleCard(this.m, {super.key});
  final Sample m;

  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: () => Navigator.of(context)
            .push(MaterialPageRoute(builder: (_) => SampleScreen(name: m.name, projectId: m.projectId))),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(children: [
            Container(
              width: 46,
              height: 46,
              decoration: BoxDecoration(color: Bio.greenSoft, borderRadius: BorderRadius.circular(14)),
              child: const Icon(Icons.science_outlined, color: Bio.green),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(m.name, maxLines: 1, overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
                const SizedBox(height: 2),
                Text('${m.plates.length} placas · ${m.usedCount} en el cálculo',
                    style: TextStyle(color: muted, fontSize: 12.5)),
              ]),
            ),
            Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
              Text(_ufc(m), style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16, color: Bio.green)),
              Text(m.estimated ? 'UFC/mL · estimado' : 'UFC/mL',
                  style: TextStyle(color: m.estimated ? Bio.warn : muted, fontSize: 11.5)),
            ]),
          ]),
        ),
      ),
    );
  }
}

/// Detalle de una muestra: resultado combinado (ISO 4833-1), cómo se calculó y sus placas.
class SampleScreen extends StatelessWidget {
  const SampleScreen({super.key, required this.name, this.projectId});
  final String name;
  final int? projectId;

  @override
  Widget build(BuildContext context) {
    final api = AppScope.of(context).api;
    return Loader<List<Sample>>(
      pageTitle: 'Muestra',
      load: () => api.samples(projectId: projectId, name: name),
      builder: (context, list, reload) {
        if (list.isEmpty) {
          return Scaffold(
            appBar: AppBar(title: Text(name)),
            body: const EmptyState(icon: Icons.science_outlined, title: 'Sin placas',
                message: 'Esta muestra ya no tiene placas.'),
          );
        }
        final m = list.first;
        final cs = Theme.of(context).colorScheme;
        return Scaffold(
          appBar: AppBar(title: Text(m.name)),
          body: RefreshIndicator(
            onRefresh: reload,
            child: ListView(padding: const EdgeInsets.fromLTRB(16, 8, 16, 24), children: [
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(18),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text('UFC/mL de la muestra', style: TextStyle(color: cs.onSurfaceVariant)),
                    const SizedBox(height: 4),
                    Text(_ufc(m), style: const TextStyle(fontSize: 34, fontWeight: FontWeight.w800, color: Bio.green)),
                    if (m.estimated)
                      const Padding(
                        padding: EdgeInsets.only(top: 4),
                        child: Text('Estimado: ninguna placa quedó en el rango contable (30–300).',
                            style: TextStyle(color: Bio.warn, fontSize: 12.5, fontWeight: FontWeight.w600)),
                      ),
                    const SizedBox(height: 10),
                    Text(m.rule, style: TextStyle(color: cs.onSurfaceVariant, fontSize: 13, height: 1.35)),
                    const SizedBox(height: 8),
                    Text('Fórmula: UFC/mL = Σ colonias ÷ Σ (volumen × dilución) de las placas usadas.',
                        style: TextStyle(color: cs.onSurfaceVariant, fontSize: 12)),
                  ]),
                ),
              ),
              for (final w in m.warnings)
                Card(
                  color: Bio.warn.withValues(alpha: 0.10),
                  child: ListTile(
                    leading: const Icon(Icons.warning_amber_rounded, color: Bio.warn),
                    title: Text(w, style: const TextStyle(fontSize: 13.5)),
                  ),
                ),
              const SizedBox(height: 4),
              SectionHeader('${m.plates.length} placas'),
              for (final p in m.plates)
                Card(
                  child: ListTile(
                    contentPadding: const EdgeInsets.fromLTRB(10, 4, 12, 4),
                    leading: ApiImage(p.thumbUrl, width: 52, height: 52),
                    title: Text(p.sampleName, maxLines: 1, overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontWeight: FontWeight.w600)),
                    subtitle: Text(
                        '${p.dilution == null ? 'Sin dilución' : dilutionLabel(p.dilution!)} · ${p.total} colonias'),
                    trailing: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: (p.used ? Bio.ok : cs.onSurfaceVariant).withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(20),
                      ),
                      child: Text(p.used ? 'Usada' : statusLabel(p.status),
                          style: TextStyle(
                              color: p.used ? Bio.ok : cs.onSurfaceVariant, fontSize: 12, fontWeight: FontWeight.w700)),
                    ),
                    onTap: () => Navigator.of(context)
                        .push(MaterialPageRoute(builder: (_) => ResultScreen(analysisId: p.id)))
                        .then((_) => reload()),
                  ),
                ),
              const SizedBox(height: 8),
              Text(
                  'Para agregar placas a esta muestra, al crear el análisis escribe "${m.name}" en el campo Muestra. '
                  'Se usan las placas contables (30–300) de las dos diluciones sucesivas más concentradas.',
                  style: TextStyle(color: cs.onSurfaceVariant, fontSize: 12.5, height: 1.4)),
            ]),
          ),
        );
      },
    );
  }
}
