import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../state/app_state.dart';
import '../widgets/common.dart';

class EditProfileScreen extends StatefulWidget {
  const EditProfileScreen({super.key});

  @override
  State<EditProfileScreen> createState() => _EditProfileScreenState();
}

class _EditProfileScreenState extends State<EditProfileScreen> {
  late final AppState _s = AppScope.read(context);
  late final _name = TextEditingController(text: _s.userName);
  late final _role = TextEditingController(text: _s.userRole);
  late final _inst = TextEditingController(text: _s.userInstitution);

  @override
  void dispose() {
    _name.dispose();
    _role.dispose();
    _inst.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Mi perfil')),
        body: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            TextField(controller: _name, decoration: const InputDecoration(labelText: 'Nombre completo')),
            const SizedBox(height: 14),
            TextField(controller: _role, decoration: const InputDecoration(labelText: 'Profesión o rol')),
            const SizedBox(height: 14),
            TextField(controller: _inst, decoration: const InputDecoration(labelText: 'Laboratorio o institución')),
            const SizedBox(height: 24),
            FilledButton(
              onPressed: () async {
                if (_name.text.trim().isEmpty) return showSnack(context, 'El nombre es obligatorio');
                try {
                  await _s.updateProfile(name: _name.text, role: _role.text, institution: _inst.text);
                  if (context.mounted) Navigator.pop(context);
                } catch (e) {
                  if (context.mounted) showSnack(context, '$e');
                }
              },
              child: const Text('Guardar'),
            ),
            const SizedBox(height: 28),
            Text('Correo: ${_s.userEmail}',
                style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              icon: const Icon(Icons.lock_reset),
              label: const Text('Cambiar contraseña'),
              onPressed: () => _changePassword(context),
            ),
          ],
        ),
      );

  Future<void> _changePassword(BuildContext context) async {
    final current = TextEditingController();
    final next = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Cambiar contraseña'),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(controller: current, obscureText: true,
              decoration: const InputDecoration(labelText: 'Contraseña actual')),
          const SizedBox(height: 12),
          TextField(controller: next, obscureText: true,
              decoration: const InputDecoration(labelText: 'Nueva contraseña (mín. 8)')),
        ]),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancelar')),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Cambiar')),
        ],
      ),
    );
    final (cur, nxt) = (current.text, next.text);
    current.dispose();
    next.dispose();
    if (ok != true || !context.mounted) return;
    if (nxt.length < 8) return showSnack(context, 'La nueva contraseña debe tener al menos 8 caracteres');
    try {
      final email = _s.userEmail;
      await _s.api.changePassword(cur, nxt);
      // El servidor cierra todas las sesiones al cambiar la contraseña: se entra de nuevo con la nueva.
      await _s.login(email, nxt);
      if (context.mounted) showSnack(context, 'Contraseña actualizada');
    } catch (e) {
      if (context.mounted) showSnack(context, '$e');
    }
  }
}

class _TextPage extends StatelessWidget {
  const _TextPage(this.title, this.sections);
  final String title;
  final List<(String, String)> sections;

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: Text(title)),
        body: ListView(
          padding: const EdgeInsets.fromLTRB(20, 4, 20, 32),
          children: [
            for (final (h, body) in sections) ...[
              Text(h, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
              const SizedBox(height: 6),
              Text(body, style: const TextStyle(height: 1.5)),
              const SizedBox(height: 20),
            ],
          ],
        ),
      );
}

class HelpScreen extends StatelessWidget {
  const HelpScreen({super.key});

  @override
  Widget build(BuildContext context) => const _TextPage('Ayuda y soporte', [
        ('¿Cómo analizo una placa?',
            'Pulsa el botón + o "Analizar muestra", centra la placa dentro del círculo guía y haz la foto. '
                'Indica la dilución y el volumen sembrado si quieres obtener las UFC/mL, y pulsa "Analizar placa".'),
        ('¿Por qué el tamaño aparece en píxeles?',
            'Para medir en milímetros, Bioyologic necesita saber la escala de la foto. Con la cámara se calcula a '
                'partir del círculo guía; con fotos de la galería, activa "La placa ocupa toda la foto".'),
        ('El recuento sale "Incontable"',
            'Hay más de 300 colonias: siembra una dilución mayor. Con menos de 30 colonias el resultado es solo '
                'orientativo.'),
        ('No conecta con el servidor',
            'Comprueba tu conexión a internet. La app usa el servidor de Bioyologic en la nube '
                '(https://bioyologic.duckdns.org); puedes verlo o cambiarlo en Configuración, en Servidor.'),
      ]);
}

class AboutScreen extends StatefulWidget {
  const AboutScreen({super.key});

  @override
  State<AboutScreen> createState() => _AboutScreenState();
}

class _AboutScreenState extends State<AboutScreen> {
  static const _agpl = 'https://www.gnu.org/licenses/agpl-3.0.html';
  late final Future<Map<String, dynamic>?> _about =
      AppScope.read(context).api.about().then<Map<String, dynamic>?>((v) => v).catchError((_) => null);

  Future<void> _open(String url) async {
    final ok = await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
    if (!ok && mounted) showSnack(context, 'No se pudo abrir $url');
  }

  Widget _link(IconData icon, String title, String subtitle, VoidCallback? onTap) => Card(
        child: ListTile(
          leading: Icon(icon),
          title: Text(title, style: const TextStyle(fontWeight: FontWeight.w600)),
          subtitle: Text(subtitle),
          trailing: onTap == null ? null : const Icon(Icons.chevron_right),
          onTap: onTap,
        ),
      );

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Acerca de')),
        body: FutureBuilder<Map<String, dynamic>?>(
          future: _about,
          builder: (context, snap) {
            final about = snap.data;
            final server = (about?['source_url'] as String?) ?? '';
            final source = server.isNotEmpty ? server : AppState.sourceUrl;
            return ListView(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 32),
              children: [
                const Padding(
                  padding: EdgeInsets.fromLTRB(4, 8, 4, 16),
                  child: Text(
                      'Bioyologic es un sistema híbrido de conteo y caracterización de colonias bacterianas: un '
                      'detector YOLO localiza cada colonia, técnicas clásicas de visión por computador miden su '
                      'tamaño, forma, borde y color, y un clasificador estima la especie.',
                      style: TextStyle(height: 1.5)),
                ),
                _link(Icons.volunteer_activism_outlined, 'Software libre · AGPL-3.0',
                    'Puedes usar, estudiar, modificar y compartir Bioyologic. Quien lo modifique y lo ofrezca '
                        'como servicio debe publicar también su código.',
                    () => _open(_agpl)),
                _link(Icons.code, 'Código fuente',
                    source.isEmpty ? 'Pendiente de publicar' : source, source.isEmpty ? null : () => _open(source)),
                _link(Icons.privacy_tip_outlined, 'Política de privacidad', 'Qué datos se guardan y dónde',
                    () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const PrivacyScreen()))),
                _link(Icons.article_outlined, 'Licencias de software', 'Flutter y paquetes que usa la app',
                    () => showLicensePage(
                        context: context, applicationName: 'Bioyologic', applicationLegalese: 'AGPL-3.0-or-later')),
                const SizedBox(height: 12),
                const Text('Datos de entrenamiento', style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
                const SizedBox(height: 6),
                _link(Icons.dataset_outlined, 'Makrai, L. et al. (2023)',
                    'Annotated dataset for deep-learning-based bacterial colony detection. Scientific Data 10:497 · '
                        '369 placas, 24 especies · CC BY 4.0',
                    () => _open('https://doi.org/10.6084/m9.figshare.22022540')),
                _link(Icons.dataset_outlined, 'Du, J. (2026)',
                    'Clinical Dataset of 19 Bacterial Colony Images. First Hospital of Jilin University; '
                        'publicado en Zenodo · 950 placas, 19 especies · CC BY 4.0',
                    () => _open('https://doi.org/10.5281/zenodo.18256864')),
                const SizedBox(height: 12),
                const Text('Aviso', style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
                const SizedBox(height: 6),
                const Text(
                    'Bioyologic es una herramienta de apoyo y no es un dispositivo médico. Los resultados, incluida '
                    'la especie, son orientativos y deben ser revisados por personal cualificado.',
                    style: TextStyle(height: 1.5)),
              ],
            );
          },
        ),
      );
}

class PrivacyScreen extends StatelessWidget {
  const PrivacyScreen({super.key});

  @override
  Widget build(BuildContext context) => const _TextPage('Política de privacidad', [
        ('Marco legal',
            'Bioyologic trata tus datos personales conforme a la Ley 1581 de 2012 de protección de datos '
                'personales de Colombia y el Decreto 1377 de 2013. Versión de la política: octubre de 2026.'),
        ('Responsable',
            'El equipo del proyecto Bioyologic (Pontificia Universidad Javeriana), que administra el servidor '
                'donde se guarda tu cuenta. Para consultas, reclamos o ejercer tus derechos sobre tus datos, '
                'escribe a martinezc.juanjo@gmail.com. Respondemos consultas en máximo 10 días hábiles y '
                'reclamos en máximo 15 días hábiles, como fija la ley.'),
        ('Qué datos guardamos',
            'De tu cuenta: nombre, correo, profesión o rol, institución y la fecha en que aceptaste esta '
                'política. Tu contraseña se guarda cifrada (scrypt) y nadie, ni siquiera el equipo, puede leerla. '
                'De tu trabajo: las fotos que analizas, los datos de cada muestra (nombre, proyecto, dilución, '
                'volumen, notas y resultados), tus siembras en incubación y las revisiones que haces.'),
        ('Para qué',
            'Solo para identificarte, calcular los resultados y guardar tu historial y tus proyectos. '
                'No vendemos ni compartimos tus datos, no hay publicidad, analítica ni rastreadores, y no pedimos '
                'tu ubicación ni tus contactos.'),
        ('Quién ve tus datos',
            'Solo tú, salvo en los proyectos compartidos. Si compartes un proyecto, o alguien te invita a uno, '
                'sus miembros ven las placas de ese proyecto, el nombre de quien hizo cada análisis y quién lo '
                'revisó; tu correo solo lo ve quien creó el proyecto. Lo que está fuera de un proyecto compartido '
                'solo lo ves tú. Las fotos y los informes PDF se abren con un enlace secreto propio de cada '
                'análisis. La conexión con el servidor va cifrada (HTTPS).'),
        ('Datos de pacientes',
            'No subas fotos ni notas con nombres, documentos u otros datos de pacientes. Usa códigos de muestra.'),
        ('Tus derechos',
            'Puedes conocer, actualizar, rectificar y suprimir tus datos, y revocar esta autorización, en '
                'cualquier momento y sin costo, desde Perfil: "Mi perfil" para actualizarlos, "Descargar mis '
                'datos" para recibir una copia completa y "Eliminar mi cuenta" para borrar del servidor la cuenta '
                'y todos sus análisis, proyectos, siembras y fotos. Puedes salir de un proyecto compartido cuando '
                'quieras.'),
        ('Conservación',
            'Tus datos se guardan mientras tengas la cuenta. Un análisis que eliminas pasa a la papelera '
                '(en Perfil, Papelera): durante 30 días puedes recuperarlo o eliminarlo definitivamente, y al día 30 '
                'se borra solo, con sus fotos. Al eliminar la cuenta se borra todo de inmediato del servidor, '
                'papelera incluida; las copias de seguridad nocturnas se sobrescriben en un máximo de 14 días.'),
        ('Permisos del teléfono',
            'Cámara: para fotografiar la placa. Fotos: para elegir una imagen de la galería. Solo se envía la '
                'foto cuando pulsas "Analizar".'),
      ]);
}
