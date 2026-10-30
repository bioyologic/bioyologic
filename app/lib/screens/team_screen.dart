import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../api/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/analysis_tile.dart';
import '../widgets/common.dart';
import '../widgets/format.dart';

/// Equipo de un proyecto: el dueño invita por correo a otras cuentas como analista (cuenta placas) o revisor
/// (además aprueba o devuelve los análisis de los demás).
class TeamScreen extends StatefulWidget {
  const TeamScreen(this.project, {super.key});
  final Project project;

  @override
  State<TeamScreen> createState() => _TeamScreenState();
}

class _TeamScreenState extends State<TeamScreen> {
  Project get p => widget.project;

  Future<void> _run(Future<void> Function() action, [String? ok]) async {
    final state = AppScope.read(context);
    try {
      await action();
      state.dataChanged();
      if (ok != null && mounted) showSnack(context, ok);
    } on ApiException catch (e) {
      if (mounted) showSnack(context, e.message);
    }
  }

  Future<void> _invite() async {
    final email = TextEditingController();
    var role = 'analista';
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setD) => AlertDialog(
          title: const Text('Invitar al proyecto'),
          content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            TextField(
              controller: email,
              autofocus: true,
              keyboardType: TextInputType.emailAddress,
              decoration: const InputDecoration(labelText: 'Correo de su cuenta de Bioyologic'),
            ),
            const SizedBox(height: 12),
            RadioGroup<String>(
              groupValue: role,
              onChanged: (v) => setD(() => role = v!),
              child: const Column(children: [
                RadioListTile(
                    contentPadding: EdgeInsets.zero,
                    value: 'analista',
                    title: Text('Analista'),
                    subtitle: Text('Analiza placas y ve las del proyecto')),
                RadioListTile(
                    contentPadding: EdgeInsets.zero,
                    value: 'revisor',
                    title: Text('Revisor'),
                    subtitle: Text('Además corrige, aprueba o devuelve los análisis de otros')),
              ]),
            ),
          ]),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancelar')),
            FilledButton(
                style: FilledButton.styleFrom(minimumSize: const Size(0, 40)),
                onPressed: () => Navigator.pop(ctx, true),
                child: const Text('Invitar')),
          ],
        ),
      ),
    );
    if (ok == true && email.text.trim().isNotEmpty) {
      await _run(() => AppScope.read(context).api.addMember(p.id, email.text.trim(), role),
          'Listo: ya puede ver el proyecto');
    }
    email.dispose();
  }

  Future<void> _memberMenu(Member m, String action) async {
    final api = AppScope.read(context).api;
    switch (action) {
      case 'analista' || 'revisor':
        await _run(() => api.changeMember(p.id, m.userId, action));
      case 'remove':
        final ok = await _confirm('¿Quitar a ${m.name}?',
            'Dejará de ver el proyecto. Los análisis que hizo se conservan en el proyecto y en su cuenta.');
        if (ok) await _run(() => api.removeMember(p.id, m.userId));
    }
  }

  Future<bool> _confirm(String title, String body) async =>
      await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: Text(title),
          content: Text(body),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancelar')),
            TextButton(
                style: TextButton.styleFrom(foregroundColor: Bio.danger),
                onPressed: () => Navigator.pop(ctx, true),
                child: const Text('Aceptar')),
          ],
        ),
      ) ??
      false;

  Future<void> _leave(int myId) async {
    if (!await _confirm('¿Salir del proyecto?', 'Dejarás de verlo. Tus análisis siguen en tu cuenta.')) return;
    if (!mounted) return;
    final state = AppScope.read(context);
    try {
      await state.api.removeMember(p.id, myId);
      state.dataChanged();
      if (mounted) Navigator.of(context).popUntil((r) => r.isFirst);
    } on ApiException catch (e) {
      if (mounted) showSnack(context, e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    return Scaffold(
      appBar: AppBar(title: const Text('Equipo del proyecto')),
      floatingActionButton: p.isOwner
          ? FloatingActionButton.extended(
              onPressed: _invite, icon: const Icon(Icons.person_add_alt), label: const Text('Invitar'))
          : null,
      body: Loader<(List<Member>, UserProfile)>(
        load: () async => (await state.api.members(p.id), await state.api.me()),
        builder: (context, data, reload) {
          final (members, me) = data;
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 96),
            children: [
              Text(p.name, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
              const SizedBox(height: 6),
              Text(
                  'Cada miembro ve las placas del proyecto y suma las suyas. Los revisores (y el dueño) aprueban o '
                  'devuelven los análisis de los demás; nadie aprueba su propio análisis. Si un conteo se corrige '
                  'después de aprobado, vuelve a quedar pendiente.',
                  style: TextStyle(color: muted, fontSize: 13)),
              const SizedBox(height: 12),
              Card(
                child: Column(children: [
                  for (final m in members)
                    ListTile(
                      leading: CircleAvatar(
                        backgroundColor: Bio.greenSoft,
                        child: Text(m.name.isEmpty ? '?' : m.name[0].toUpperCase(),
                            style: const TextStyle(color: Bio.green, fontWeight: FontWeight.w700)),
                      ),
                      title: Text(m.userId == me.id ? '${m.name} (tú)' : m.name),
                      subtitle: Text([roleLabel(m.role), ?m.email].join(' · ')),
                      trailing: p.isOwner && m.role != 'owner'
                          ? PopupMenuButton<String>(
                              onSelected: (v) => _memberMenu(m, v),
                              itemBuilder: (_) => [
                                CheckedPopupMenuItem(value: 'analista', checked: m.role == 'analista', child: const Text('Analista')),
                                CheckedPopupMenuItem(value: 'revisor', checked: m.role == 'revisor', child: const Text('Revisor')),
                                const PopupMenuItem(value: 'remove', child: Text('Quitar del proyecto')),
                              ],
                            )
                          : null,
                    ),
                ]),
              ),
              if (!p.isOwner) ...[
                const SizedBox(height: 16),
                OutlinedButton.icon(
                  style: OutlinedButton.styleFrom(foregroundColor: Bio.danger),
                  onPressed: () => _leave(me.id),
                  icon: const Icon(Icons.logout),
                  label: const Text('Salir del proyecto'),
                ),
              ],
              if (p.isOwner && members.length == 1)
                Padding(
                  padding: const EdgeInsets.only(top: 16),
                  child: Text('La otra persona debe tener una cuenta de Bioyologic. Invítala con el correo con el que se '
                      'registró.', style: TextStyle(color: muted, fontSize: 13)),
                ),
            ],
          );
        },
      ),
    );
  }
}

/// Análisis de otros miembros que el usuario debe aprobar o devolver.
class ReviewQueueScreen extends StatelessWidget {
  const ReviewQueueScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final api = AppScope.of(context).api;
    return Scaffold(
      appBar: AppBar(title: const Text('Por revisar')),
      body: Loader<List<Analysis>>(
        load: () => api.analyses(toReview: true, limit: 200),
        builder: (context, items, reload) => items.isEmpty
            ? const EmptyState(
                icon: Icons.task_alt,
                title: 'Nada por revisar',
                message: 'Aquí aparecen los análisis de tu equipo que esperan tu aprobación.')
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
    );
  }
}

/// Estado de revisión de un análisis y, si el usuario puede revisarlo, los botones para aprobar o devolver.
class ReviewCard extends StatelessWidget {
  const ReviewCard(this.a, {super.key, required this.onChanged});
  final Analysis a;
  final Future<void> Function() onChanged;

  Future<void> _send(BuildContext context, String status) async {
    var note = '';
    if (status == 'devuelto') {
      final c = TextEditingController();
      final ok = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Devolver para corregir'),
          content: TextField(
            controller: c,
            autofocus: true,
            maxLines: 3,
            decoration: const InputDecoration(labelText: '¿Qué hay que corregir?', hintText: 'p. ej. Hay un reflejo contado como colonia'),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancelar')),
            TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Devolver')),
          ],
        ),
      );
      note = c.text.trim();
      c.dispose();
      if (ok != true || !context.mounted) return;
    }
    final state = AppScope.read(context);
    try {
      await state.api.review(a.id, status, note: note);
      state.dataChanged();
      await onChanged();
      if (context.mounted) {
        showSnack(context, switch (status) { 'aprobado' => 'Análisis aprobado', 'devuelto' => 'Devuelto a ${a.authorName}', _ => 'Revisión quitada' });
      }
    } on ApiException catch (e) {
      if (context.mounted) showSnack(context, e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final r = a.review;
    if (r == null) return const SizedBox.shrink();
    final (color, icon, title) = switch (r.status) {
      'aprobado' => (Bio.ok, Icons.verified_outlined, 'Aprobado por ${r.by}'),
      'devuelto' => (Bio.danger, Icons.reply_outlined, 'Devuelto por ${r.by}'),
      _ => (Bio.warn, Icons.hourglass_top, 'Pendiente de revisión'),
    };
    return Card(
      color: color.withValues(alpha: 0.08),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Icon(icon, color: color, size: 20),
            const SizedBox(width: 8),
            Expanded(child: Text(title, style: TextStyle(fontWeight: FontWeight.w700, color: color))),
          ]),
          if (r.at != null)
            Padding(padding: const EdgeInsets.only(top: 2), child: Text(friendlyDate(r.at!), style: const TextStyle(fontSize: 12.5))),
          if (r.note.isNotEmpty)
            Padding(padding: const EdgeInsets.only(top: 6), child: Text('«${r.note}»', style: const TextStyle(height: 1.35))),
          if (!a.isMine && a.authorName.isNotEmpty)
            Padding(padding: const EdgeInsets.only(top: 6), child: Text('Analizado por ${a.authorName}', style: const TextStyle(fontSize: 12.5))),
          if (a.canReview) ...[
            const SizedBox(height: 10),
            Row(children: [
              if (r.status != 'aprobado')
                Expanded(
                  child: FilledButton.icon(
                    style: FilledButton.styleFrom(minimumSize: const Size(0, 40)),
                    onPressed: () => _send(context, 'aprobado'),
                    icon: const Icon(Icons.check, size: 18),
                    label: const Text('Aprobar'),
                  ),
                ),
              if (r.status != 'aprobado' && r.status != 'devuelto') const SizedBox(width: 8),
              if (r.status != 'devuelto')
                Expanded(
                  child: OutlinedButton.icon(
                    style: OutlinedButton.styleFrom(minimumSize: const Size(0, 40)),
                    onPressed: () => _send(context, 'devuelto'),
                    icon: const Icon(Icons.reply, size: 18),
                    label: const Text('Devolver'),
                  ),
                ),
              if (!r.pending) ...[
                const SizedBox(width: 8),
                TextButton(onPressed: () => _send(context, ''), child: const Text('Deshacer')),
              ],
            ]),
          ],
        ]),
      ),
    );
  }
}
