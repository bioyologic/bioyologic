import 'package:flutter/material.dart';

import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'info_screens.dart';
import 'shell.dart';

/// Iniciar sesión o crear una cuenta. Cada cuenta solo ve sus propios análisis y proyectos.
class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key, this.register = false, this.expired = false});

  /// Abre en "Crear cuenta" (true) o en "Iniciar sesión" (false); se puede cambiar desde la pantalla.
  final bool register;

  /// Se llegó aquí porque la sesión caducó.
  final bool expired;

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  final _form = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _password2 = TextEditingController();
  final _name = TextEditingController();
  final _role = TextEditingController();
  final _inst = TextEditingController();
  late bool _register;
  bool _consent = false;
  bool _busy = false;
  bool _showPassword = false;

  @override
  void initState() {
    super.initState();
    _register = widget.register;
    // Si ya se entró antes en este dispositivo, el correo aparece escrito.
    final last = AppScope.read(context).lastEmail;
    if (last != null && !_register) _email.text = last;
    if (widget.expired) {
      WidgetsBinding.instance.addPostFrameCallback(
          (_) => showSnack(context, 'Tu sesión caducó. Vuelve a iniciar sesión.'));
    }
  }

  @override
  void dispose() {
    for (final c in [_email, _password, _password2, _name, _role, _inst]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_form.currentState!.validate()) return;
    if (_register && !_consent) {
      return showSnack(context, 'Debes autorizar el tratamiento de tus datos para crear la cuenta');
    }
    final state = AppScope.read(context);
    setState(() => _busy = true);
    try {
      if (_register) {
        await state.register(
            email: _email.text.trim(),
            password: _password.text,
            name: _name.text.trim(),
            role: _role.text.trim(),
            institution: _inst.text.trim(),
            acceptPrivacy: _consent);
      } else {
        await state.login(_email.text.trim(), _password.text);
      }
      if (!mounted) return;
      Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => const Shell()));
    } catch (e) {
      if (mounted) showSnack(context, '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final muted = TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant);
    return Scaffold(
      appBar: Navigator.of(context).canPop() ? AppBar() : null,
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 480),
            child: Form(
              key: _form,
              child: AutofillGroup(
                child: ListView(
                  padding: const EdgeInsets.all(24),
                  children: [
                    Center(
                      child: Container(
                        padding: const EdgeInsets.all(20),
                        decoration: BoxDecoration(color: Bio.green, borderRadius: BorderRadius.circular(28)),
                        child: const BioLogo(size: 64),
                      ),
                    ),
                    const SizedBox(height: 24),
                    Text(_register ? 'Crea tu cuenta' : 'Inicia sesión',
                        textAlign: TextAlign.center,
                        style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w700)),
                    const SizedBox(height: 8),
                    Text(
                        _register
                            ? '¿Es tu primera vez en Bioyologic? Regístrate gratis en un minuto.'
                            : 'Entra con el correo y la contraseña con los que te registraste.',
                        textAlign: TextAlign.center,
                        style: muted),
                    const SizedBox(height: 16),
                    if (_register) const _HowTo(),
                    const SizedBox(height: 20),
                    if (_register) ...[
                      TextFormField(
                        controller: _name,
                        textCapitalization: TextCapitalization.words,
                        autofillHints: const [AutofillHints.name],
                        decoration: const InputDecoration(
                            labelText: 'Nombre completo', prefixIcon: Icon(Icons.person_outline)),
                        validator: (v) => (v == null || v.trim().isEmpty) ? 'Escribe tu nombre' : null,
                      ),
                      const SizedBox(height: 14),
                    ],
                    TextFormField(
                      controller: _email,
                      keyboardType: TextInputType.emailAddress,
                      autofillHints: const [AutofillHints.email],
                      decoration: const InputDecoration(
                          labelText: 'Correo electrónico', prefixIcon: Icon(Icons.alternate_email)),
                      validator: (v) => RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch((v ?? '').trim())
                          ? null
                          : 'Escribe un correo válido',
                    ),
                    const SizedBox(height: 14),
                    TextFormField(
                      controller: _password,
                      obscureText: !_showPassword,
                      autofillHints: [_register ? AutofillHints.newPassword : AutofillHints.password],
                      decoration: InputDecoration(
                        labelText: 'Contraseña',
                        helperText: _register ? 'Mínimo 8 caracteres' : null,
                        prefixIcon: const Icon(Icons.lock_outline),
                        suffixIcon: IconButton(
                          tooltip: _showPassword ? 'Ocultar' : 'Mostrar',
                          icon: Icon(_showPassword ? Icons.visibility_off_outlined : Icons.visibility_outlined),
                          onPressed: () => setState(() => _showPassword = !_showPassword),
                        ),
                      ),
                      validator: (v) {
                        if ((v ?? '').isEmpty) return 'Escribe tu contraseña';
                        if (_register && v!.length < 8) return 'Usa al menos 8 caracteres';
                        return null;
                      },
                      onFieldSubmitted: _register ? null : (_) => _submit(),
                    ),
                    if (_register) ...[
                      const SizedBox(height: 14),
                      TextFormField(
                        controller: _password2,
                        obscureText: !_showPassword,
                        decoration: const InputDecoration(
                            labelText: 'Repite la contraseña', prefixIcon: Icon(Icons.lock_outline)),
                        validator: (v) => v == _password.text ? null : 'Las contraseñas no coinciden',
                      ),
                      const SizedBox(height: 14),
                      TextFormField(
                        controller: _role,
                        textCapitalization: TextCapitalization.sentences,
                        decoration: const InputDecoration(
                            labelText: 'Profesión o rol (opcional)',
                            hintText: 'p. ej. Bacteriólogo/a',
                            prefixIcon: Icon(Icons.badge_outlined)),
                      ),
                      const SizedBox(height: 14),
                      TextFormField(
                        controller: _inst,
                        textCapitalization: TextCapitalization.words,
                        decoration: const InputDecoration(
                            labelText: 'Laboratorio o institución (opcional)',
                            prefixIcon: Icon(Icons.apartment_outlined)),
                      ),
                      const SizedBox(height: 12),
                      CheckboxListTile(
                        value: _consent,
                        onChanged: (v) => setState(() => _consent = v ?? false),
                        contentPadding: EdgeInsets.zero,
                        controlAffinity: ListTileControlAffinity.leading,
                        title: const Text(
                            'Autorizo el tratamiento de mis datos personales según la política de privacidad '
                            '(Ley 1581 de 2012).',
                            style: TextStyle(fontSize: 14)),
                      ),
                      Align(
                        alignment: Alignment.centerLeft,
                        child: TextButton.icon(
                          icon: const Icon(Icons.privacy_tip_outlined, size: 18),
                          label: const Text('Leer la política de privacidad'),
                          onPressed: () => Navigator.of(context)
                              .push(MaterialPageRoute(builder: (_) => const PrivacyScreen())),
                        ),
                      ),
                    ],
                    const SizedBox(height: 20),
                    FilledButton(
                      onPressed: _busy ? null : _submit,
                      child: _busy
                          ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                          : Text(_register ? 'Crear cuenta' : 'Entrar'),
                    ),
                    const SizedBox(height: 12),
                    Wrap(
                      alignment: WrapAlignment.center,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: [
                        Text(_register ? '¿Ya tienes una cuenta?' : '¿No tienes cuenta?', style: muted),
                        TextButton(
                          onPressed: _busy ? null : () => setState(() => _register = !_register),
                          child: Text(_register ? 'Inicia sesión' : 'Regístrate aquí',
                              style: const TextStyle(fontWeight: FontWeight.w700)),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Qué se necesita para registrarse, a la vista antes de llenar el formulario.
class _HowTo extends StatelessWidget {
  const _HowTo();

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    Widget step(String n, String t) => Padding(
          padding: const EdgeInsets.only(top: 6),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            CircleAvatar(
                radius: 10,
                backgroundColor: Bio.green,
                child: Text(n, style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w700))),
            const SizedBox(width: 10),
            Expanded(child: Text(t, style: const TextStyle(height: 1.35))),
          ]),
        );
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 14),
      decoration: BoxDecoration(
          color: cs.surfaceContainerHighest.withValues(alpha: 0.6), borderRadius: BorderRadius.circular(14)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('Cómo registrarte', style: TextStyle(fontWeight: FontWeight.w700)),
        step('1', 'Escribe tu nombre, tu correo y una contraseña de al menos 8 caracteres.'),
        step('2', 'Si quieres, agrega tu profesión y tu laboratorio (opcional).'),
        step('3', 'Acepta la política de privacidad y pulsa "Crear cuenta".'),
        const SizedBox(height: 8),
        Text('Después entras siempre con tu correo y tu contraseña. Tus análisis solo los ves tú.',
            style: TextStyle(fontSize: 13, color: cs.onSurfaceVariant)),
      ]),
    );
  }
}
