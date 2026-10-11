import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/format.dart';
import 'profile_screen.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Configuración')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 32),
        children: [
          const _Title('Cámara'),
          Card(
            child: Column(children: [
              SwitchListTile(
                secondary: const Icon(Icons.center_focus_strong_outlined),
                title: const Text('Guía de enfoque'),
                subtitle: const Text('Círculo para encuadrar la placa y medir en mm'),
                value: s.focusGuide,
                onChanged: (v) => s.focusGuide = v,
              ),
              const Divider(),
              _Choice(
                icon: Icons.high_quality_outlined,
                title: 'Resolución',
                value: s.resolution,
                options: const {'media': 'Media', 'alta': 'Alta', 'maxima': 'Máxima'},
                onChanged: (v) => s.resolution = v,
              ),
              const Divider(),
              _Choice(
                icon: Icons.flash_on_outlined,
                title: 'Flash',
                value: s.flashMode,
                options: const {'apagado': 'Apagado', 'auto': 'Automático', 'encendido': 'Encendido'},
                onChanged: (v) => s.flashMode = v,
              ),
            ]),
          ),
          const _Title('Análisis'),
          Card(
            child: Column(children: [
              _NumberTile(
                icon: Icons.circle_outlined,
                title: 'Diámetro de la placa',
                suffix: 'mm',
                value: s.plateDiameterMm,
                onChanged: (v) => s.plateDiameterMm = v,
              ),
              const Divider(),
              _NumberTile(
                icon: Icons.water_drop_outlined,
                title: 'Volumen sembrado por defecto',
                suffix: 'mL',
                value: s.defaultVolumeMl,
                digits: 2,
                onChanged: (v) => s.defaultVolumeMl = v,
              ),
            ]),
          ),
          const _Title('Preferencias'),
          Card(
            child: Column(children: [
              SwitchListTile(
                secondary: const Icon(Icons.dark_mode_outlined),
                title: const Text('Modo oscuro'),
                value: s.darkMode,
                onChanged: (v) => s.darkMode = v,
              ),
              const Divider(),
              const ListTile(
                leading: Icon(Icons.language),
                title: Text('Idioma'),
                trailing: Text('Español'),
              ),
            ]),
          ),
          const _Title('Servidor'),
          const Card(child: _ServerTile()),
          const _Title('Información'),
          const Card(
            child: Column(children: [
              ListTile(leading: Icon(Icons.info_outline), title: Text('Versión de la app'), trailing: Text('1.0.0')),
            ]),
          ),
          const SizedBox(height: 20),
          OutlinedButton.icon(
            style: OutlinedButton.styleFrom(foregroundColor: Bio.danger, side: const BorderSide(color: Bio.danger)),
            onPressed: () => confirmLogout(context),
            icon: const Icon(Icons.logout),
            label: const Text('Cerrar sesión'),
          ),
        ],
      ),
    );
  }
}

class _Title extends StatelessWidget {
  const _Title(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(4, 20, 4, 8),
        child: Text(text,
            style: TextStyle(fontWeight: FontWeight.w700, color: Theme.of(context).colorScheme.primary)),
      );
}

class _Choice extends StatelessWidget {
  const _Choice({required this.icon, required this.title, required this.value, required this.options, required this.onChanged});
  final IconData icon;
  final String title;
  final String value;
  final Map<String, String> options;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) => ListTile(
        leading: Icon(icon),
        title: Text(title),
        trailing: Row(mainAxisSize: MainAxisSize.min, children: [
          Text(options[value] ?? value, style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)),
          const Icon(Icons.chevron_right),
        ]),
        onTap: () async {
          final v = await showModalBottomSheet<String>(
            context: context,
            showDragHandle: true,
            builder: (ctx) => RadioGroup<String>(
              groupValue: value,
              onChanged: (v) => Navigator.pop(ctx, v),
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                ListTile(title: Text(title, style: const TextStyle(fontWeight: FontWeight.w700))),
                for (final e in options.entries) RadioListTile<String>(value: e.key, title: Text(e.value)),
                const SizedBox(height: 12),
              ]),
            ),
          );
          if (v != null) onChanged(v);
        },
      );
}

class _NumberTile extends StatelessWidget {
  const _NumberTile({required this.icon, required this.title, required this.suffix, required this.value,
      required this.onChanged, this.digits = 0});
  final IconData icon;
  final String title;
  final String suffix;
  final double value;
  final int digits;
  final ValueChanged<double> onChanged;

  @override
  Widget build(BuildContext context) => ListTile(
        leading: Icon(icon),
        title: Text(title),
        trailing: Text('${fmt(value, digits)} $suffix',
            style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)),
        onTap: () async {
          final c = TextEditingController(text: fmt(value, digits));
          final v = await showDialog<double>(
            context: context,
            builder: (ctx) => AlertDialog(
              title: Text(title),
              content: TextField(
                controller: c,
                autofocus: true,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: InputDecoration(suffixText: suffix),
              ),
              actions: [
                TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancelar')),
                TextButton(
                  onPressed: () => Navigator.pop(ctx, double.tryParse(c.text.replaceAll(',', '.'))),
                  child: const Text('Guardar'),
                ),
              ],
            ),
          );
          if (v != null && v > 0) onChanged(v);
        },
      );
}

class _ServerTile extends StatefulWidget {
  const _ServerTile();

  @override
  State<_ServerTile> createState() => _ServerTileState();
}

class _ServerTileState extends State<_ServerTile> {
  bool? _online;

  @override
  void initState() {
    super.initState();
    _check();
  }

  Future<void> _check() async {
    setState(() => _online = null);
    final ok = await ApiClient(AppScope.read(context).serverUrl).health();
    if (mounted) setState(() => _online = ok);
  }

  Future<void> _edit() async {
    final s = AppScope.read(context);
    final c = TextEditingController(text: s.serverUrl);
    final v = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Servidor de análisis'),
        content: TextField(
          controller: c,
          keyboardType: TextInputType.url,
          decoration: const InputDecoration(helperText: 'Móvil real: http://<IP del PC>:8000', helperMaxLines: 2),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancelar')),
          TextButton(onPressed: () => Navigator.pop(ctx, c.text.trim()), child: const Text('Guardar')),
        ],
      ),
    );
    if (v != null && v.isNotEmpty) {
      s.serverUrl = v;
      s.dataChanged();
      _check();
    }
  }

  @override
  Widget build(BuildContext context) {
    final color = _online == null ? Colors.grey : (_online! ? Bio.ok : Bio.danger);
    return ListTile(
      leading: const Icon(Icons.dns_outlined),
      title: const Text('Servidor de análisis'),
      subtitle: Text(AppScope.of(context).serverUrl),
      trailing: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(Icons.circle, size: 10, color: color),
        const SizedBox(width: 6),
        Text(_online == null ? '…' : (_online! ? 'Conectado' : 'Sin conexión'), style: TextStyle(color: color)),
      ]),
      onTap: _edit,
      onLongPress: _check,
    );
  }
}
