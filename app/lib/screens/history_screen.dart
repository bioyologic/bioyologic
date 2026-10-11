import 'package:flutter/material.dart';

import '../api/models.dart';
import '../state/app_state.dart';
import '../widgets/analysis_tile.dart';
import '../widgets/common.dart';
import 'capture_screen.dart';

/// Pestaña "Análisis": historial completo con búsqueda.
class HistoryScreen extends StatefulWidget {
  const HistoryScreen({super.key});

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  String _query = '';

  @override
  Widget build(BuildContext context) {
    final api = AppScope.of(context).api;
    return Scaffold(
      appBar: AppBar(title: const Text('Análisis')),
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
        Expanded(
          child: Loader<List<Analysis>>(
            key: ValueKey(_query),
            load: () => api.analyses(query: _query, limit: 200),
            builder: (context, items, reload) => items.isEmpty
                ? EmptyState(
                    icon: Icons.insert_chart_outlined,
                    title: _query.isEmpty ? 'Sin análisis todavía' : 'Sin resultados',
                    message: _query.isEmpty ? 'Tus análisis aparecerán aquí.' : 'Prueba con otro nombre.',
                    action: _query.isEmpty
                        ? FilledButton.icon(
                            onPressed: () => CaptureScreen.open(context),
                            icon: const Icon(Icons.add_a_photo_outlined),
                            label: const Text('Analizar muestra'))
                        : null,
                  )
                : RefreshIndicator(
                    onRefresh: reload,
                    child: ListView.separated(
                      padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
                      itemCount: items.length,
                      separatorBuilder: (_, _) => const SizedBox(height: 10),
                      itemBuilder: (_, i) => AnalysisTile(items[i]),
                    ),
                  ),
          ),
        ),
      ]),
    );
  }
}
