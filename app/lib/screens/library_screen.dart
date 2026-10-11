import 'package:flutter/material.dart';

import '../api/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';

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
                  for (final (key, label) in [('todos', 'Todos'), ...lib.categories.entries.map((e) => (e.key, e.value))])
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
            ApiImage(e.imageUrl, width: 72, height: 72),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(e.title,
                    style: TextStyle(
                        fontWeight: FontWeight.w600,
                        fontSize: 15,
                        fontStyle: e.category == 'bacterias' ? FontStyle.italic : FontStyle.normal)),
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
              AspectRatio(aspectRatio: 1.8, child: ApiImage(e.imageUrl, radius: 18)),
              const SizedBox(height: 16),
              Text(e.title,
                  style: TextStyle(fontSize: 24, fontWeight: FontWeight.w700,
                      fontStyle: e.category == 'bacterias' ? FontStyle.italic : FontStyle.normal)),
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
