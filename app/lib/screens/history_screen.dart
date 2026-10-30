import 'package:flutter/material.dart';

import '../api/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/analysis_tile.dart';
import '../widgets/common.dart';
import 'capture_screen.dart';

/// Pestaña "Análisis": historial completo con búsqueda.
///
/// Para borrar: deslizar un análisis hacia la izquierda, o "Seleccionar" (o mantener presionado) para
/// marcar varios y eliminarlos juntos.
class HistoryScreen extends StatefulWidget {
  const HistoryScreen({super.key});

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  String _query = '';

  /// null = modo normal; un conjunto (aunque esté vacío) = modo selección.
  Set<int>? _selected;
  List<Analysis> _items = [];
  Future<void> Function()? _reload;
  bool _deleting = false;

  /// Borrados al deslizar: se ocultan al instante (Dismissible lo exige) hasta que la lista se recarga.
  final _hidden = <int>{};

  bool get _selecting => _selected != null;

  void _toggle(int id) => setState(() => _selected!.contains(id) ? _selected!.remove(id) : _selected!.add(id));

  void _exitSelection() => setState(() => _selected = null);

  Future<void> _deleteSelected() async {
    final ids = _selected!.toList();
    if (ids.isEmpty) return showSnack(context, 'Marca los análisis que quieres eliminar');
    if (!await confirmDeleteAnalyses(context, ids.length,
            name: ids.length == 1 ? _items.firstWhere((a) => a.id == ids.first).sampleName : null) ||
        !mounted) {
      return;
    }
    final state = AppScope.read(context);
    setState(() => _deleting = true);
    try {
      final n = await state.api.deleteAnalyses(ids);
      state.dataChanged();
      if (!mounted) return;
      showSnack(context, n == 1 ? 'Se eliminó 1 análisis' : 'Se eliminaron $n análisis');
      setState(() => _selected = null);
      await _reload?.call();
    } catch (e) {
      if (mounted) showSnack(context, '$e');
    } finally {
      if (mounted) setState(() => _deleting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final api = AppScope.of(context).api;
    final sel = _selected;
    return PopScope(
      canPop: !_selecting,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _exitSelection();
      },
      child: Scaffold(
        appBar: sel == null
            ? AppBar(title: const Text('Análisis'), actions: [
                TextButton.icon(
                  onPressed: () => setState(() => _selected = {}),
                  icon: const Icon(Icons.checklist),
                  label: const Text('Seleccionar'),
                ),
              ])
            : AppBar(
                leading: IconButton(tooltip: 'Cancelar', icon: const Icon(Icons.close), onPressed: _exitSelection),
                title: Text(sel.isEmpty ? 'Selecciona análisis' : '${sel.length} seleccionado${sel.length == 1 ? '' : 's'}'),
                actions: [
                  TextButton(
                    onPressed: () => setState(() => sel.length == _items.length
                        ? sel.clear()
                        : sel.addAll(_items.map((a) => a.id))),
                    child: Text(sel.length == _items.length && _items.isNotEmpty ? 'Ninguno' : 'Todos'),
                  ),
                  IconButton(
                    tooltip: 'Eliminar seleccionados',
                    icon: _deleting
                        ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.delete_outline, color: Bio.danger),
                    onPressed: _deleting || sel.isEmpty ? null : _deleteSelected,
                  ),
                ],
              ),
        body: Column(children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
            child: SearchBar(
              hintText: 'Buscar muestra o proyecto',
              leading: const Icon(Icons.search),
              elevation: const WidgetStatePropertyAll(0),
              onChanged: (v) => setState(() => _query = v.trim()),
            ),
          ),
          if (!_selecting && _items.isNotEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 4),
              child: Text('Desliza un análisis hacia la izquierda para eliminarlo, o mantén presionado para elegir varios.',
                  style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant)),
            ),
          Expanded(
            child: Loader<List<Analysis>>(
              key: ValueKey(_query),
              load: () => api.analyses(query: _query, limit: 200),
              builder: (context, all, reload) {
                _reload = reload;
                final items = all.where((a) => !_hidden.contains(a.id)).toList();
                if (_items.length != items.length || !identical(_items.firstOrNull, items.firstOrNull)) {
                  _items = items;
                  // Tras recargar, quita de la selección lo que ya no existe.
                  WidgetsBinding.instance.addPostFrameCallback((_) {
                    if (mounted) setState(() => _selected?.removeWhere((id) => !items.any((a) => a.id == id)));
                  });
                }
                if (items.isEmpty) {
                  return EmptyState(
                    icon: Icons.insert_chart_outlined,
                    title: _query.isEmpty ? 'Sin análisis todavía' : 'Sin resultados',
                    message: _query.isEmpty ? 'Tus análisis aparecerán aquí.' : 'Prueba con otro nombre.',
                    action: _query.isEmpty
                        ? FilledButton.icon(
                            onPressed: () => CaptureScreen.open(context),
                            icon: const Icon(Icons.add_a_photo_outlined),
                            label: const Text('Analizar muestra'))
                        : null,
                  );
                }
                return RefreshIndicator(
                  onRefresh: reload,
                  child: ListView.separated(
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
                    itemCount: items.length,
                    separatorBuilder: (_, _) => const SizedBox(height: 10),
                    itemBuilder: (_, i) {
                      final a = items[i];
                      return AnalysisTile(
                        a,
                        selected: sel?.contains(a.id),
                        onTap: sel == null ? null : () => _toggle(a.id),
                        onLongPress: () => setState(() => (_selected ??= {}).add(a.id)),
                        onDeleted: () {
                          setState(() => _hidden.add(a.id));
                          reload();
                        },
                      );
                    },
                  ),
                );
              },
            ),
          ),
        ]),
      ),
    );
  }
}
