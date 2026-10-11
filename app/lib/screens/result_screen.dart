import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/format.dart';

class ResultScreen extends StatelessWidget {
  const ResultScreen({super.key, required this.analysisId});
  final int analysisId;

  @override
  Widget build(BuildContext context) {
    final api = AppScope.of(context).api;
    return Loader<Analysis>(
      pageTitle: 'Resultados',
      load: () => api.analysis(analysisId),
      builder: (context, a, reload) => _ResultView(a, reload),
    );
  }
}

class _ResultView extends StatelessWidget {
  const _ResultView(this.a, this.reload);
  final Analysis a;
  final Future<void> Function() reload;

  Uri _reportUri(BuildContext context) => Uri.parse(AppScope.read(context).api.url(a.reportUrl));

  Future<void> _download(BuildContext context) async {
    final ok = await launchUrl(_reportUri(context), mode: LaunchMode.externalApplication);
    if (!ok && context.mounted) showSnack(context, 'No se pudo abrir el reporte');
  }

  Future<void> _menu(BuildContext context, String action) async {
    final state = AppScope.read(context);
    switch (action) {
      case 'rename':
        final name = await _prompt(context, 'Renombrar muestra', a.sampleName);
        if (name != null && name.isNotEmpty) {
          await state.api.updateAnalysis(a.id, sampleName: name);
          state.dataChanged();
        }
      case 'move':
        final projects = await state.api.projects();
        if (!context.mounted) return;
        final pid = await showModalBottomSheet<int>(
          context: context,
          showDragHandle: true,
          builder: (_) => ListView(shrinkWrap: true, children: [
            const ListTile(title: Text('Mover a proyecto', style: TextStyle(fontWeight: FontWeight.w700))),
            ListTile(leading: const Icon(Icons.folder_off_outlined), title: const Text('Sin proyecto'),
                onTap: () => Navigator.pop(context, 0)),
            for (final p in projects)
              ListTile(
                leading: const Icon(Icons.folder_outlined),
                title: Text(p.name),
                trailing: p.id == a.projectId ? const Icon(Icons.check) : null,
                onTap: () => Navigator.pop(context, p.id),
              ),
          ]),
        );
        if (pid != null) {
          await state.api.updateAnalysis(a.id, projectId: pid);
          state.dataChanged();
        }
      case 'delete':
        final ok = await showDialog<bool>(
          context: context,
          builder: (ctx) => AlertDialog(
            title: const Text('¿Eliminar análisis?'),
            content: Text('Se borrarán "${a.sampleName}", sus imágenes y sus resultados.'),
            actions: [
              TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancelar')),
              FilledButton(
                  style: FilledButton.styleFrom(backgroundColor: Bio.danger, minimumSize: const Size(0, 40)),
                  onPressed: () => Navigator.pop(ctx, true),
                  child: const Text('Eliminar')),
            ],
          ),
        );
        if (ok == true) {
          await state.api.deleteAnalysis(a.id);
          state.dataChanged();
          if (context.mounted) Navigator.pop(context);
        }
    }
  }

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 3,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Resultados'),
          actions: [
            IconButton(
              tooltip: 'Copiar enlace del reporte',
              icon: const Icon(Icons.share_outlined),
              onPressed: () async {
                await Clipboard.setData(ClipboardData(text: _reportUri(context).toString()));
                if (context.mounted) showSnack(context, 'Enlace del reporte copiado');
              },
            ),
            PopupMenuButton<String>(
              onSelected: (v) => _menu(context, v),
              itemBuilder: (_) => const [
                PopupMenuItem(value: 'rename', child: Text('Renombrar')),
                PopupMenuItem(value: 'move', child: Text('Mover a proyecto')),
                PopupMenuItem(value: 'delete', child: Text('Eliminar')),
              ],
            ),
          ],
        ),
        body: Column(children: [
          Padding(padding: const EdgeInsets.fromLTRB(16, 4, 16, 8), child: _Header(a)),
          const TabBar(tabs: [Tab(text: 'Resumen'), Tab(text: 'Colonias'), Tab(text: 'Morfología')]),
          Expanded(
            child: TabBarView(children: [
              _SummaryTab(a, onDownload: () => _download(context)),
              _ColoniesTab(a),
              _MorphologyTab(a),
            ]),
          ),
        ]),
      ),
    );
  }
}

Future<String?> _prompt(BuildContext context, String title, String initial) {
  final c = TextEditingController(text: initial);
  return showDialog<String>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(title),
      content: TextField(controller: c, autofocus: true, onSubmitted: (v) => Navigator.pop(ctx, v.trim())),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancelar')),
        TextButton(onPressed: () => Navigator.pop(ctx, c.text.trim()), child: const Text('Guardar')),
      ],
    ),
  );
}

class _Header extends StatelessWidget {
  const _Header(this.a);
  final Analysis a;

  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(10),
        child: Row(children: [
          ApiImage(a.thumbUrl, width: 64, height: 64),
          const SizedBox(width: 12),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(a.sampleName, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
              const SizedBox(height: 4),
              StatusChip(a.summary.status),
              const SizedBox(height: 4),
              Text('${friendlyDate(a.createdAt)}${a.projectName != null ? ' · ${a.projectName}' : ''}',
                  style: TextStyle(color: muted, fontSize: 12.5)),
            ]),
          ),
        ]),
      ),
    );
  }
}

// ------------------------------------------------------------------ Resumen
class _SummaryTab extends StatelessWidget {
  const _SummaryTab(this.a, {required this.onDownload});
  final Analysis a;
  final VoidCallback onDownload;

  @override
  Widget build(BuildContext context) {
    final s = a.summary;
    final cs = Theme.of(context).colorScheme;
    final d = s.diameter;
    final colonies = a.colonies ?? [];
    final predColor = s.predominant['color'];
    final swatch = colonies.where((c) => c.colorName == predColor).map((c) => hexColor(c.colorHex)).firstOrNull;
    final species = s.byClass.keys.any((k) => k != 'colony');

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 24),
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Row(children: [
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('Total de colonias', style: TextStyle(color: cs.onSurfaceVariant)),
                  const SizedBox(height: 4),
                  Text('${s.total}', style: const TextStyle(fontSize: 40, fontWeight: FontWeight.w800, height: 1.1)),
                  const SizedBox(height: 4),
                  Text(statusDetail(s.status), style: TextStyle(color: statusColor(s.status), fontSize: 12.5)),
                ]),
              ),
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(color: cs.primary.withValues(alpha: 0.1), shape: BoxShape.circle),
                child: Icon(Icons.bubble_chart_outlined, color: cs.primary, size: 32),
              ),
            ]),
          ),
        ),
        const SizedBox(height: 12),
        Card(
          child: Column(children: [
            _Row(Icons.straighten, 'Tamaño promedio',
                d.stat == null ? '—' : '${fmt(d.stat!.mean, d.unit == 'mm' ? 1 : 0)} ${d.unit}'),
            _Row(Icons.circle_outlined, 'Forma predominante', capitalize(s.predominant['form'])),
            _Row(Icons.palette_outlined, 'Color predominante', capitalize(predColor), swatch: swatch),
            _Row(Icons.blur_circular, 'Bordes', marginLabels[s.predominant['margin']] ?? '—'),
            _Row(Icons.science_outlined, 'UFC/mL', s.cfuPerMl == null ? 'Sin dilución' : scientific(s.cfuPerMl!),
                last: a.dilution == null),
            if (a.dilution != null)
              _Row(Icons.water_drop_outlined, 'Siembra',
                  '${dilutionLabel(a.dilution!)} · ${fmt(a.volumeMl, 2)} mL', last: true),
          ]),
        ),
        const SizedBox(height: 12),
        if (colonies.isNotEmpty) _PredictionCard(a, species: species),
        const SizedBox(height: 12),
        _NotesField(a),
        const SizedBox(height: 16),
        FilledButton.icon(
          onPressed: onDownload,
          icon: const Icon(Icons.download_outlined),
          label: const Text('Descargar reporte'),
        ),
      ],
    );
  }
}

class _Row extends StatelessWidget {
  const _Row(this.icon, this.label, this.value, {this.swatch, this.last = false});
  final IconData icon;
  final String label;
  final String value;
  final Color? swatch;
  final bool last;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 13),
      decoration: BoxDecoration(
          border: last ? null : Border(bottom: BorderSide(color: Theme.of(context).dividerTheme.color!))),
      child: Row(children: [
        Icon(icon, size: 20, color: cs.primary),
        const SizedBox(width: 12),
        Expanded(child: Text(label, style: TextStyle(color: cs.onSurfaceVariant))),
        if (swatch != null) ...[
          Container(
              width: 14, height: 14,
              decoration: BoxDecoration(color: swatch, shape: BoxShape.circle, border: Border.all(color: Colors.black12))),
          const SizedBox(width: 6),
        ],
        Text(value, style: const TextStyle(fontWeight: FontWeight.w600)),
      ]),
    );
  }
}

class _PredictionCard extends StatelessWidget {
  const _PredictionCard(this.a, {required this.species});
  final Analysis a;
  final bool species;

  @override
  Widget build(BuildContext context) {
    final sp = a.species;
    if (sp != null && sp.top.isNotEmpty) return _SpeciesCard(sp, total: a.summary.total);
    final colonies = a.colonies!;
    final s = a.summary;
    final top = s.predominant['class'] ?? 'colony';
    final share = (s.byClass[top] ?? 0) / math.max(1, s.total);
    final conf = colonies.where((c) => c.className == top).map((c) => c.confidence).fold(0.0, (x, y) => x + y) /
        math.max(1, s.byClass[top] ?? 1);
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: Bio.greenSoft, borderRadius: BorderRadius.circular(16)),
      child: Row(children: [
        Container(
          padding: const EdgeInsets.all(10),
          decoration: const BoxDecoration(color: Bio.green, shape: BoxShape.circle),
          child: const Icon(Icons.coronavirus_outlined, color: Colors.white),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(species ? 'Predicción de especie' : 'Detección de colonias',
                style: const TextStyle(color: Bio.greenDark, fontSize: 12.5)),
            const SizedBox(height: 2),
            Text(species ? speciesLabel(top) : '${s.total} colonias detectadas',
                style: TextStyle(
                    color: Bio.greenDark, fontSize: 16, fontWeight: FontWeight.w700,
                    fontStyle: species ? FontStyle.italic : FontStyle.normal)),
            Text(
                species
                    ? '${(share * 100).round()} % de las colonias · confianza ${(conf * 100).round()} %'
                    : 'Confianza media del detector: ${(conf * 100).round()} %',
                style: const TextStyle(color: Bio.greenDark, fontSize: 12.5)),
          ]),
        ),
      ]),
    );
  }
}

const _agarLabels = {
  'blood': 'agar sangre',
  'MacConkey': 'agar MacConkey',
  'nutrient': 'agar nutritivo',
  'chocolate': 'agar chocolate',
  'Salmonella-Shigella': 'agar SS',
  'blood, nutrient': 'agar sangre o nutritivo',
};

/// Especie de la placa según el clasificador: la más probable + alternativas.
class _SpeciesCard extends StatelessWidget {
  const _SpeciesCard(this.sp, {required this.total});
  final SpeciesPrediction sp;
  final int total;

  @override
  Widget build(BuildContext context) {
    final best = sp.top.first;
    final facts = [
      if (best.gram != null) 'Gram ${best.gram == '+' ? 'positiva' : 'negativa'}',
      if (best.agar != null) 'en los datos de entrenamiento: ${_agarLabels[best.agar] ?? best.agar}',
    ].join(' · ');
    const ink = Bio.greenDark;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
          color: sp.identified ? Bio.greenSoft : Bio.warn.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(16)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(color: sp.identified ? Bio.green : Bio.warn, shape: BoxShape.circle),
            child: const Icon(Icons.coronavirus_outlined, color: Colors.white),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(sp.identified ? 'Predicción de especie' : 'Especie no identificada con seguridad',
                  style: const TextStyle(color: ink, fontSize: 12.5)),
              const SizedBox(height: 2),
              Text(best.name,
                  style: const TextStyle(color: ink, fontSize: 16, fontWeight: FontWeight.w700,
                      fontStyle: FontStyle.italic)),
              Text('Probabilidad ${(best.prob * 100).round()} % · votación de $total colonias',
                  style: const TextStyle(color: ink, fontSize: 12.5)),
              if (facts.isNotEmpty) Text(facts, style: const TextStyle(color: ink, fontSize: 12)),
            ]),
          ),
        ]),
        if (sp.top.length > 1) ...[
          const SizedBox(height: 10),
          const Text('Otras posibles', style: TextStyle(color: ink, fontSize: 12, fontWeight: FontWeight.w600)),
          for (final c in sp.top.skip(1))
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Row(children: [
                Expanded(child: Text(c.name, style: const TextStyle(color: ink, fontStyle: FontStyle.italic, fontSize: 13))),
                Text('${(c.prob * 100).round()} %', style: const TextStyle(color: ink, fontSize: 13)),
              ]),
            ),
        ],
        const SizedBox(height: 8),
        const Text('Orientativo: confirma la especie con pruebas microbiológicas.',
            style: TextStyle(color: ink, fontSize: 11.5, fontStyle: FontStyle.italic)),
      ]),
    );
  }
}

class _NotesField extends StatefulWidget {
  const _NotesField(this.a);
  final Analysis a;

  @override
  State<_NotesField> createState() => _NotesFieldState();
}

class _NotesFieldState extends State<_NotesField> {
  late final _c = TextEditingController(text: widget.a.notes);
  Timer? _debounce;

  @override
  void dispose() {
    _debounce?.cancel();
    _c.dispose();
    super.dispose();
  }

  void _changed(String v) {
    _debounce?.cancel();
    final api = AppScope.read(context).api;
    _debounce = Timer(const Duration(milliseconds: 700), () => api.updateAnalysis(widget.a.id, notes: v));
  }

  @override
  Widget build(BuildContext context) => TextField(
        controller: _c,
        minLines: 2,
        maxLines: 4,
        onChanged: _changed,
        decoration: const InputDecoration(labelText: 'Notas', alignLabelWithHint: true),
      );
}

// ------------------------------------------------------------------ Colonias
class _ColoniesTab extends StatelessWidget {
  const _ColoniesTab(this.a);
  final Analysis a;

  @override
  Widget build(BuildContext context) {
    final colonies = a.colonies ?? [];
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 24),
      children: [
        GestureDetector(
          onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => _ZoomImage(a.annotatedUrl))),
          child: Stack(children: [
            ApiImage(a.annotatedUrl, fit: BoxFit.contain, radius: 16),
            Positioned(
              right: 10,
              bottom: 10,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                decoration: BoxDecoration(color: Colors.black54, borderRadius: BorderRadius.circular(20)),
                child: const Row(mainAxisSize: MainAxisSize.min, children: [
                  Icon(Icons.zoom_in, color: Colors.white, size: 16),
                  SizedBox(width: 4),
                  Text('Ampliar', style: TextStyle(color: Colors.white, fontSize: 12)),
                ]),
              ),
            ),
          ]),
        ),
        const SizedBox(height: 8),
        SectionHeader('${colonies.length} colonias'),
        if (colonies.isEmpty)
          Text('No se detectaron colonias.', style: TextStyle(color: muted))
        else
          Card(
            child: Column(children: [
              for (final (i, c) in colonies.indexed)
                ListTile(
                  shape: i == 0
                      ? const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(16)))
                      : null,
                  leading: CircleAvatar(
                    radius: 16,
                    backgroundColor: hexColor(c.colorHex),
                    child: Text('${c.id}', style: TextStyle(fontSize: 11,
                        color: hexColor(c.colorHex).computeLuminance() > 0.5 ? Colors.black87 : Colors.white)),
                  ),
                  title: Text(speciesLabel(c.className)),
                  subtitle: Text('${capitalize(c.form)} · ${c.colorName}'),
                  trailing: Text(
                      c.diameterMm != null ? '${fmt(c.diameterMm, 2)} mm' : '${fmt(c.diameterPx, 0)} px',
                      style: const TextStyle(fontWeight: FontWeight.w600)),
                  onTap: () => _showColony(context, c),
                ),
            ]),
          ),
      ],
    );
  }

  void _showColony(BuildContext context, Colony c) {
    Widget kv(String k, String v) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 6),
          child: Row(children: [
            Expanded(child: Text(k)),
            Text(v, style: const TextStyle(fontWeight: FontWeight.w600)),
          ]),
        );
    final lab = (c.m['color_lab'] as List).map((v) => fmt(v as num, 0)).join(' / ');
    showModalBottomSheet(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (_) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
          children: [
            Row(children: [
              CircleAvatar(radius: 20, backgroundColor: hexColor(c.colorHex)),
              const SizedBox(width: 12),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('Colonia #${c.id}', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
                  Text(c.speciesConfidence == null
                      ? '${speciesLabel(c.className)} · confianza ${(c.confidence * 100).round()} %'
                      : '${speciesLabel(c.className)} (${(c.speciesConfidence! * 100).round()} %) · '
                          'detección ${(c.confidence * 100).round()} %'),
                ]),
              ),
            ]),
            const SizedBox(height: 12),
            if (c.diameterMm != null) ...[
              kv('Diámetro', '${fmt(c.diameterMm, 2)} mm'),
              kv('Área', '${fmt(c.num_('area_mm2'), 2)} mm²'),
            ] else
              kv('Diámetro', '${fmt(c.diameterPx, 0)} px'),
            kv('Forma', capitalize(c.form)),
            kv('Borde', marginLabels[c.margin] ?? c.margin),
            kv('Circularidad', fmt(c.num_('circularity'), 2)),
            kv('Relación de aspecto', fmt(c.num_('aspect_ratio'), 2)),
            kv('Solidez', fmt(c.num_('solidity'), 2)),
            kv('Color', '${capitalize(c.colorName)} · ${c.colorHex.toUpperCase()}'),
            kv('L*a*b*', lab),
            kv('Contraste con el agar (ΔE)', fmt(c.num_('contrast'), 1)),
            if (!c.segmented)
              const Padding(
                padding: EdgeInsets.only(top: 8),
                child: Text('Silueta aproximada a partir de la caja del detector.',
                    style: TextStyle(fontStyle: FontStyle.italic)),
              ),
          ],
        ),
      ),
    );
  }
}

class _ZoomImage extends StatelessWidget {
  const _ZoomImage(this.path);
  final String path;

  @override
  Widget build(BuildContext context) => Scaffold(
        backgroundColor: Colors.black,
        appBar: AppBar(backgroundColor: Colors.black, foregroundColor: Colors.white),
        body: InteractiveViewer(
          maxScale: 10,
          child: Center(child: ApiImage(path, fit: BoxFit.contain, radius: 0)),
        ),
      );
}

// ------------------------------------------------------------------ Morfología
class _MorphologyTab extends StatelessWidget {
  const _MorphologyTab(this.a);
  final Analysis a;

  @override
  Widget build(BuildContext context) {
    final s = a.summary;
    final colonies = a.colonies ?? [];
    final d = s.diameter;
    final diam = colonies.map((c) => d.unit == 'mm' ? c.diameterMm! : c.diameterPx).toList();
    final colorSwatches = {for (final c in colonies) c.colorName: hexColor(c.colorHex)};

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 24),
      children: [
        _Panel('Distribución de tamaños (${d.unit})', _Histogram(diam, unit: d.unit)),
        const SizedBox(height: 12),
        _Panel('Forma', _Bars(s.counts('form').map((k, v) => MapEntry(capitalize(k), v)))),
        const SizedBox(height: 12),
        _Panel('Borde', _Bars(s.counts('margin').map((k, v) => MapEntry(marginLabels[k] ?? k, v)))),
        const SizedBox(height: 12),
        _Panel('Color', _Bars(s.counts('color_name').map((k, v) => MapEntry(capitalize(k), v)),
            colors: {for (final e in colorSwatches.entries) capitalize(e.key): e.value})),
        if (s.byClass.length > 1 || s.byClass.keys.any((k) => k != 'colony')) ...[
          const SizedBox(height: 12),
          _Panel('Clases', _Bars(s.byClass.map((k, v) => MapEntry(speciesLabel(k), v)))),
        ],
        const SizedBox(height: 12),
        _Panel('Descriptores (media ± desv.)', Column(children: [
          for (final (key, label, digits) in [
            (d.unit == 'mm' ? 'diameter_mm' : 'diameter_px', 'Diámetro (${d.unit})', d.unit == 'mm' ? 2 : 0),
            ('area_mm2', 'Área (mm²)', 2),
            ('circularity', 'Circularidad', 2),
            ('solidity', 'Solidez', 2),
            ('contrast', 'Contraste ΔE', 1),
          ])
            if (s.stat(key) case final st?)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 5),
                child: Row(children: [
                  Expanded(child: Text(label)),
                  Text('${fmt(st.mean, digits)} ± ${fmt(st.std, digits)}',
                      style: const TextStyle(fontWeight: FontWeight.w600)),
                ]),
              ),
        ])),
      ],
    );
  }
}

class _Panel extends StatelessWidget {
  const _Panel(this.title, this.child);
  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) => Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
            const SizedBox(height: 12),
            child,
          ]),
        ),
      );
}

class _Bars extends StatelessWidget {
  const _Bars(this.counts, {this.colors = const {}});
  final Map<String, int> counts;
  final Map<String, Color> colors;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final total = counts.values.fold(0, (a, b) => a + b);
    final entries = counts.entries.toList()..sort((a, b) => b.value.compareTo(a.value));
    if (total == 0) return const Text('—');
    return Column(children: [
      for (final e in entries)
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 4),
          child: Row(children: [
            SizedBox(width: 110, child: Text(e.key, overflow: TextOverflow.ellipsis)),
            Expanded(
              child: ClipRRect(
                borderRadius: BorderRadius.circular(6),
                child: LinearProgressIndicator(
                  value: e.value / total,
                  minHeight: 10,
                  backgroundColor: cs.surfaceContainerHighest,
                  color: colors[e.key] ?? cs.primary,
                ),
              ),
            ),
            SizedBox(width: 64, child: Text('${e.value} · ${(100 * e.value / total).round()}%', textAlign: TextAlign.right,
                style: const TextStyle(fontSize: 12.5))),
          ]),
        ),
    ]);
  }
}

class _Histogram extends StatelessWidget {
  const _Histogram(this.values, {required this.unit});
  final List<double> values;
  final String unit;

  @override
  Widget build(BuildContext context) {
    if (values.isEmpty) return const Text('—');
    final cs = Theme.of(context).colorScheme;
    final lo = values.reduce(math.min), hi = values.reduce(math.max);
    const bins = 8;
    final width = (hi - lo) / bins;
    final counts = List.filled(bins, 0);
    for (final v in values) {
      counts[width == 0 ? 0 : math.min(bins - 1, ((v - lo) / width).floor())]++;
    }
    final maxC = counts.reduce(math.max);
    final digits = unit == 'mm' ? 1 : 0;
    return Column(children: [
      SizedBox(
        height: 110,
        child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
          for (final c in counts)
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 2),
                child: Column(mainAxisAlignment: MainAxisAlignment.end, children: [
                  if (c > 0) Text('$c', style: TextStyle(fontSize: 10, color: cs.onSurfaceVariant)),
                  Container(
                    height: maxC == 0 ? 0 : 90 * c / maxC,
                    decoration: BoxDecoration(color: cs.primary, borderRadius: BorderRadius.circular(4)),
                  ),
                ]),
              ),
            ),
        ]),
      ),
      const SizedBox(height: 6),
      Row(children: [
        Text('${fmt(lo, digits)} $unit', style: TextStyle(fontSize: 11, color: cs.onSurfaceVariant)),
        const Spacer(),
        Text('${fmt(hi, digits)} $unit', style: TextStyle(fontSize: 11, color: cs.onSurfaceVariant)),
      ]),
    ]);
  }
}
