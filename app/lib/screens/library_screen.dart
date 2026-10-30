import 'package:flutter/material.dart';

import '../api/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';

/// Id de la ficha de una especie ("Escherichia coli" -> "escherichia-coli"), como en el servidor.
String speciesEntryId(String species) =>
    species.toLowerCase().replaceAll(RegExp(r'[^a-z0-9]+'), '-').replaceAll(RegExp(r'^-+|-+$'), '');

const _icons = {
  'diluciones': Icons.science_outlined,
  'siembra': Icons.water_drop_outlined,
  'incubacion': Icons.timer_outlined,
  'calculo': Icons.calculate_outlined,
  'control': Icons.verified_outlined,
  'flujo': Icons.route_outlined,
  'foto': Icons.photo_camera_outlined,
  'avisos': Icons.report_problem_outlined,
  'corregir': Icons.edit_outlined,
  'morfologia': Icons.blur_circular,
  'especie': Icons.biotech_outlined,
  'equipo': Icons.groups_outlined,
  'bioseguridad': Icons.health_and_safety_outlined,
};

/// Imagen de un microorganismo, o ícono de un protocolo o guía.
class _EntryVisual extends StatelessWidget {
  const _EntryVisual(this.e, {required this.size});
  final LibraryEntry e;
  final double size;

  @override
  Widget build(BuildContext context) {
    if (e.isMicro) return ApiImage(e.imageUrl, width: size, height: size);
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(color: Bio.greenSoft, borderRadius: BorderRadius.circular(12)),
      child: Icon(_icons[e.icon] ?? Icons.menu_book_outlined, color: Bio.green, size: size * 0.45),
    );
  }
}

class LibraryScreen extends StatefulWidget {
  const LibraryScreen({super.key});

  @override
  State<LibraryScreen> createState() => _LibraryScreenState();
}

class _LibraryScreenState extends State<LibraryScreen> {
  String _cat = 'todos';
  String _query = '';

  @override
  Widget build(BuildContext context) {
    final api = AppScope.of(context).api;
    return Scaffold(
      appBar: AppBar(title: const Text('Biblioteca')),
      body: Loader(
        load: api.library,
        builder: (context, lib, _) {
          final q = _query.toLowerCase();
          final items = lib.entries
              .where((e) => _cat == 'todos' || e.category == _cat)
              .where((e) => q.isEmpty || '${e.title} ${e.subtitle} ${e.tags.join(' ')}'.toLowerCase().contains(q))
              .toList();
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
            children: [
              SearchBar(
                hintText: 'Buscar en la biblioteca',
                leading: const Icon(Icons.search),
                elevation: const WidgetStatePropertyAll(0),
                onChanged: (v) => setState(() => _query = v.trim()),
              ),
              const SizedBox(height: 12),
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: Row(children: [
                  for (final (key, label) in [
                    ('todos', 'Todos'),
                    ...lib.categories.entries.map(
                        (c) => (c.key, '${c.value} (${lib.entries.where((e) => e.category == c.key).length})')),
                  ])
                    Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: ChoiceChip(
                        label: Text(label),
                        selected: _cat == key,
                        showCheckmark: false,
                        selectedColor: Bio.green,
                        labelStyle: TextStyle(color: _cat == key ? Colors.white : null, fontWeight: FontWeight.w600),
                        onSelected: (_) => setState(() => _cat = key),
                      ),
                    ),
                ]),
              ),
              const SizedBox(height: 12),
              if (items.isEmpty)
                const EmptyState(icon: Icons.search_off, title: 'Sin resultados')
              else
                for (final e in items)
                  Padding(padding: const EdgeInsets.only(bottom: 10), child: _EntryCard(e, lib.categories[e.category]!)),
            ],
          );
        },
      ),
    );
  }
}

class _EntryCard extends StatelessWidget {
  const _EntryCard(this.e, this.category);
  final LibraryEntry e;
  final String category;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => LibraryDetailScreen(e.id))),
        child: Padding(
          padding: const EdgeInsets.all(10),
          child: Row(children: [
            _EntryVisual(e, size: 72),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(e.title,
                    style: TextStyle(
                        fontWeight: FontWeight.w600,
                        fontSize: 15,
                        fontStyle: e.isMicro ? FontStyle.italic : FontStyle.normal)),
                const SizedBox(height: 2),
                Text(e.subtitle, style: TextStyle(color: cs.onSurfaceVariant, fontSize: 12.5)),
                const SizedBox(height: 6),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(color: Bio.greenSoft, borderRadius: BorderRadius.circular(10)),
                  child: Text(category, style: const TextStyle(color: Bio.greenDark, fontSize: 11, fontWeight: FontWeight.w600)),
                ),
              ]),
            ),
            Icon(Icons.chevron_right, color: cs.onSurfaceVariant),
          ]),
        ),
      ),
    );
  }
}

class LibraryDetailScreen extends StatelessWidget {
  const LibraryDetailScreen(this.id, {super.key});
  final String id;

  @override
  Widget build(BuildContext context) {
    final api = AppScope.of(context).api;
    return Scaffold(
      appBar: AppBar(),
      body: Loader<LibraryEntry>(
        load: () => api.libraryEntry(id),
        builder: (context, e, _) {
          final cs = Theme.of(context).colorScheme;
          return ListView(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 32),
            children: [
              if (e.isMicro) ...[
                AspectRatio(aspectRatio: 1.8, child: ApiImage(e.imageUrl, radius: 18)),
                if (e.imageCaption != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: Text(e.imageCaption!,
                        style: TextStyle(color: cs.onSurfaceVariant, fontSize: 12, fontStyle: FontStyle.italic)),
                  ),
              ] else
                Align(alignment: Alignment.centerLeft, child: _EntryVisual(e, size: 64)),
              const SizedBox(height: 16),
              Text(e.title,
                  style: TextStyle(fontSize: 24, fontWeight: FontWeight.w700,
                      fontStyle: e.isMicro ? FontStyle.italic : FontStyle.normal)),
              const SizedBox(height: 4),
              Text(e.subtitle, style: TextStyle(color: cs.onSurfaceVariant)),
              const SizedBox(height: 12),
              Wrap(spacing: 8, runSpacing: 8, children: [
                for (final t in e.tags)
                  Chip(label: Text(t), visualDensity: VisualDensity.compact, backgroundColor: Bio.greenSoft,
                      side: BorderSide.none, labelStyle: const TextStyle(color: Bio.greenDark)),
              ]),
              for (final s in e.sections ?? const <({String title, String body})>[]) ...[
                const SizedBox(height: 20),
                Text(s.title, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
                const SizedBox(height: 6),
                Text(s.body, style: const TextStyle(height: 1.5, fontSize: 15)),
              ],
            ],
          );
        },
      ),
    );
  }
}
