import 'package:flutter/material.dart';

import '../api/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/analysis_tile.dart';
import '../widgets/common.dart';
import '../widgets/format.dart';
import 'capture_screen.dart';
import 'library_screen.dart';
import 'shell.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    return Scaffold(
      body: SafeArea(
        child: Loader<(List<Analysis>, Stats)>(
          load: () async => (await state.api.analyses(limit: 5), await state.api.stats()),
          builder: (context, data, reload) {
            final (recent, stats) = data;
            return RefreshIndicator(
              onRefresh: reload,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
                children: [
                  Row(children: [
                    Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text('Hola, ${state.firstName} 👋',
                            style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w700, letterSpacing: -0.3)),
                        const SizedBox(height: 4),
                        Text('¿Qué analizaremos hoy?', style: TextStyle(color: muted, fontSize: 15)),
                      ]),
                    ),
                    IconButton.outlined(
                      tooltip: 'Notificaciones',
                      onPressed: () => _showNotifications(context, recent),
                      icon: Badge(isLabelVisible: recent.isNotEmpty, smallSize: 8,
                          child: const Icon(Icons.notifications_none)),
                    ),
                  ]),
                  const SizedBox(height: 20),
                  Row(children: [
                    _Action(Icons.document_scanner_outlined, 'Analizar\nmuestra', primary: true,
                        onTap: () => CaptureScreen.open(context)),
                    const SizedBox(width: 10),
                    _Action(Icons.folder_outlined, 'Mis\nproyectos', onTap: () => Shell.goTo(context, 2)),
                    const SizedBox(width: 10),
                    _Action(Icons.menu_book_outlined, 'Biblioteca',
                        onTap: () => Navigator.of(context)
                            .push(MaterialPageRoute(builder: (_) => const LibraryScreen()))),
                    const SizedBox(width: 10),
                    _Action(Icons.history, 'Historial', onTap: () => Shell.goTo(context, 1)),
                  ]),
                  const SizedBox(height: 20),
                  _StatsBanner(stats),
                  const SizedBox(height: 8),
                  SectionHeader('Últimos análisis', action: 'Ver todo', onAction: () => Shell.goTo(context, 1)),
                  if (recent.isEmpty)
                    EmptyState(
                      icon: Icons.biotech_outlined,
                      title: 'Aún no hay análisis',
                      message: 'Fotografía una placa de Petri para contar y caracterizar sus colonias.',
                      action: FilledButton.icon(
                        onPressed: () => CaptureScreen.open(context),
                        icon: const Icon(Icons.add_a_photo_outlined),
                        label: const Text('Analizar muestra'),
                      ),
                    )
                  else
                    for (final a in recent)
                      Padding(padding: const EdgeInsets.only(bottom: 10), child: AnalysisTile(a)),
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  void _showNotifications(BuildContext context, List<Analysis> recent) {
    showModalBottomSheet(
      context: context,
      showDragHandle: true,
      builder: (_) => ListView(
        shrinkWrap: true,
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
        children: [
          const Text('Notificaciones', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          if (recent.isEmpty) const ListTile(title: Text('No tienes notificaciones')),
          for (final a in recent.take(4))
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: CircleAvatar(
                backgroundColor: statusColor(a.summary.status).withValues(alpha: 0.12),
                child: Icon(Icons.check_circle_outline, color: statusColor(a.summary.status)),
              ),
              title: Text('Análisis listo: ${a.sampleName}'),
              subtitle: Text('${a.summary.total} colonias · ${friendlyDate(a.createdAt)}'),
            ),
        ],
      ),
    );
  }
}

class _Action extends StatelessWidget {
  const _Action(this.icon, this.label, {this.primary = false, required this.onTap});
  final IconData icon;
  final String label;
  final bool primary;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final fg = primary ? Colors.white : cs.primary;
    return Expanded(
      child: Material(
        color: primary ? Bio.green : cs.surface,
        borderRadius: BorderRadius.circular(16),
        child: InkWell(
          borderRadius: BorderRadius.circular(16),
          onTap: onTap,
          child: Container(
            height: 92,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(16),
              border: primary ? null : Border.all(color: Theme.of(context).dividerTheme.color!),
            ),
            child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
              Icon(icon, color: fg, size: 26),
              const SizedBox(height: 6),
              Text(label,
                  textAlign: TextAlign.center,
                  style: TextStyle(color: primary ? Colors.white : cs.onSurface, fontSize: 11.5,
                      fontWeight: FontWeight.w600, height: 1.15)),
            ]),
          ),
        ),
      ),
    );
  }
}

class _StatsBanner extends StatelessWidget {
  const _StatsBanner(this.s);
  final Stats s;

  @override
  Widget build(BuildContext context) {
    Widget item(String v, String l) => Expanded(
          child: Column(children: [
            Text(v, style: const TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.w700)),
            Text(l, style: TextStyle(color: Colors.white.withValues(alpha: 0.75), fontSize: 12)),
          ]),
        );
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 16),
      decoration: BoxDecoration(
        gradient: const LinearGradient(colors: [Bio.green, Color(0xFF2B7A5C)]),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Row(children: [
        item('${s.analyses}', 'Análisis'),
        item('${s.colonies}', 'Colonias'),
        item('${s.projects}', 'Proyectos'),
      ]),
    );
  }
}
