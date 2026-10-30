import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'info_screens.dart';
import 'projects_screen.dart';
import 'settings_screen.dart';
import 'start_screen.dart';

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    final subtitle = [state.userRole, state.userInstitution].where((s) => s.isNotEmpty).join(' · ');
    final muted = TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant);
    void push(Widget w) => Navigator.of(context).push(MaterialPageRoute(builder: (_) => w));

    return Scaffold(
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 24),
          children: [
            Card(
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(children: [
                  CircleAvatar(
                    radius: 40,
                    backgroundColor: Bio.green,
                    child: Text(state.initials,
                        style: const TextStyle(color: Colors.white, fontSize: 28, fontWeight: FontWeight.w700)),
                  ),
                  const SizedBox(height: 12),
                  Text(state.userName ?? '', style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700)),
                  const SizedBox(height: 4),
                  Text(state.userEmail, style: muted),
                  if (subtitle.isNotEmpty) ...[
                    const SizedBox(height: 4),
                    Text(subtitle, textAlign: TextAlign.center, style: muted),
                  ],
                  const SizedBox(height: 18),
                  Loader<Stats>(
                    load: state.api.stats,
                    builder: (context, s, _) => Row(children: [
                      _Stat('${s.analyses}', 'Análisis'),
                      _Stat('${s.projects}', 'Proyectos'),
                      _Stat('${s.colonies}', 'Colonias'),
                    ]),
                  ),
                ]),
              ),
            ),
            const SizedBox(height: 16),
            Card(
              child: Column(children: [
                _Item(Icons.person_outline, 'Mi perfil', () => push(const EditProfileScreen())),
                _Item(Icons.settings_outlined, 'Configuración', () => push(const SettingsScreen())),
                _Item(Icons.help_outline, 'Ayuda y soporte', () => push(const HelpScreen())),
                _Item(Icons.description_outlined, 'Acerca de, licencia y privacidad', () => push(const AboutScreen()), last: true),
              ]),
            ),
            const SizedBox(height: 16),
            Card(
              child: Column(children: [
                _Item(Icons.table_view_outlined, 'Exportar mis análisis a Excel', () => exportCsv(context)),
                _Item(Icons.download_outlined, 'Descargar mis datos', () => _exportData(context)),
                _Item(Icons.logout, 'Cerrar sesión', () => confirmLogout(context), danger: true),
                _Item(Icons.delete_forever_outlined, 'Eliminar mi cuenta', () => confirmDeleteAccount(context),
                    danger: true, last: true),
              ]),
            ),
          ],
        ),
      ),
    );
  }
}

/// Derecho de acceso (Ley 1581): descarga en JSON todo lo que el servidor guarda de la cuenta.
Future<void> _exportData(BuildContext context) async {
  try {
    final link = await AppScope.read(context).api.exportLink();
    await launchUrl(Uri.parse(link), mode: LaunchMode.externalApplication);
  } catch (e) {
    if (context.mounted) showSnack(context, '$e');
  }
}

void _toLogin(BuildContext context) => Navigator.of(context, rootNavigator: true)
    .pushAndRemoveUntil(MaterialPageRoute(builder: (_) => const StartScreen()), (_) => false);

/// Derecho de supresión (Ley 1581): borra la cuenta, sus análisis, proyectos y fotos.
Future<void> confirmDeleteAccount(BuildContext context) async {
  final password = TextEditingController();
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('¿Eliminar tu cuenta?'),
      content: Column(mainAxisSize: MainAxisSize.min, children: [
        const Text('Se borrarán del servidor tu cuenta y todos tus análisis, proyectos y fotos. '
            'No se puede deshacer.'),
        const SizedBox(height: 16),
        TextField(
          controller: password,
          obscureText: true,
          autofocus: true,
          decoration: const InputDecoration(labelText: 'Escribe tu contraseña para confirmar'),
        ),
      ]),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancelar')),
        TextButton(
          style: TextButton.styleFrom(foregroundColor: Bio.danger),
          onPressed: () => Navigator.pop(ctx, true),
          child: const Text('Eliminar todo'),
        ),
      ],
    ),
  );
  final pwd = password.text;
  password.dispose();
  if (ok != true || !context.mounted) return;
  try {
    await AppScope.read(context).deleteAccount(pwd);
    if (!context.mounted) return;
    showSnack(context, 'Tu cuenta y tus datos se eliminaron');
    _toLogin(context);
  } catch (e) {
    if (context.mounted) showSnack(context, '$e');
  }
}

Future<void> confirmLogout(BuildContext context) async {
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('¿Cerrar sesión?'),
      content: const Text('Tus análisis quedan guardados en tu cuenta. Vuelve a entrar con tu correo y contraseña.'),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancelar')),
        TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Cerrar sesión')),
      ],
    ),
  );
  if (ok != true || !context.mounted) return;
  await AppScope.read(context).logout();
  if (context.mounted) _toLogin(context);
}

class _Stat extends StatelessWidget {
  const _Stat(this.value, this.label);
  final String value;
  final String label;

  @override
  Widget build(BuildContext context) => Expanded(
        child: Column(children: [
          Text(value, style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700, color: Theme.of(context).colorScheme.primary)),
          Text(label, style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant)),
        ]),
      );
}

class _Item extends StatelessWidget {
  const _Item(this.icon, this.label, this.onTap, {this.danger = false, this.last = false});
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final bool danger;
  final bool last;

  @override
  Widget build(BuildContext context) {
    final color = danger ? Bio.danger : null;
    return Container(
      decoration: BoxDecoration(
          border: last ? null : Border(bottom: BorderSide(color: Theme.of(context).dividerTheme.color!))),
      child: ListTile(
        leading: Icon(icon, color: color ?? Theme.of(context).colorScheme.primary),
        title: Text(label, style: TextStyle(color: color, fontWeight: danger ? FontWeight.w600 : null)),
        trailing: danger ? null : const Icon(Icons.chevron_right),
        onTap: onTap,
      ),
    );
  }
}
