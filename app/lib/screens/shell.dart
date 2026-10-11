import 'package:flutter/material.dart';

import '../theme.dart';
import 'capture_screen.dart';
import 'history_screen.dart';
import 'home_screen.dart';
import 'profile_screen.dart';
import 'projects_screen.dart';

/// Navegación principal: Inicio · Análisis · (+) · Proyectos · Perfil.
class Shell extends StatefulWidget {
  const Shell({super.key});

  static void goTo(BuildContext context, int tab) =>
      context.findAncestorStateOfType<_ShellState>()?._select(tab);

  @override
  State<Shell> createState() => _ShellState();
}

class _ShellState extends State<Shell> {
  int _tab = 0;

  void _select(int i) => setState(() => _tab = i);

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    const pages = [HomeScreen(), HistoryScreen(), ProjectsScreen(), ProfileScreen()];
    return Scaffold(
      body: IndexedStack(index: _tab, children: pages),
      bottomNavigationBar: Container(
        decoration: BoxDecoration(
          color: cs.surface,
          border: Border(top: BorderSide(color: Theme.of(context).dividerTheme.color!)),
        ),
        child: SafeArea(
          top: false,
          child: SizedBox(
            height: 68,
            child: Row(children: [
              _NavItem(icon: Icons.home_outlined, active: Icons.home, label: 'Inicio', selected: _tab == 0, onTap: () => _select(0)),
              _NavItem(icon: Icons.insert_chart_outlined, active: Icons.insert_chart, label: 'Análisis', selected: _tab == 1, onTap: () => _select(1)),
              Expanded(
                child: Center(
                  child: Material(
                    color: Bio.green,
                    shape: const CircleBorder(),
                    elevation: 3,
                    child: InkWell(
                      customBorder: const CircleBorder(),
                      onTap: () => CaptureScreen.open(context),
                      child: const SizedBox(
                          width: 52, height: 52, child: Icon(Icons.add, color: Colors.white, size: 28)),
                    ),
                  ),
                ),
              ),
              _NavItem(icon: Icons.folder_outlined, active: Icons.folder, label: 'Proyectos', selected: _tab == 2, onTap: () => _select(2)),
              _NavItem(icon: Icons.person_outline, active: Icons.person, label: 'Perfil', selected: _tab == 3, onTap: () => _select(3)),
            ]),
          ),
        ),
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  const _NavItem({required this.icon, required this.active, required this.label, required this.selected, required this.onTap});

  final IconData icon;
  final IconData active;
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final color = selected ? cs.primary : cs.onSurfaceVariant;
    return Expanded(
      child: InkWell(
        onTap: onTap,
        child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
          Icon(selected ? active : icon, color: color),
          const SizedBox(height: 3),
          Text(label,
              style: TextStyle(fontSize: 11, color: color, fontWeight: selected ? FontWeight.w600 : FontWeight.w400)),
        ]),
      ),
    );
  }
}
