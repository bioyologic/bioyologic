import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'shell.dart';
import 'start_screen.dart';

/// Campo para el código de 6 dígitos que llega por correo.
class _CodeField extends StatelessWidget {
  const _CodeField(this.controller, {this.onDone});
  final TextEditingController controller;
  final VoidCallback? onDone;

  @override
  Widget build(BuildContext context) => TextField(
        controller: controller,
        keyboardType: TextInputType.number,
        textAlign: TextAlign.center,
        maxLength: 6,
        autofillHints: const [AutofillHints.oneTimeCode],
        inputFormatters: [FilteringTextInputFormatter.digitsOnly],
        style: const TextStyle(fontSize: 30, fontWeight: FontWeight.w700, letterSpacing: 12),
        decoration: const InputDecoration(hintText: '······', counterText: ''),
        onChanged: (v) {
          if (v.length == 6) onDone?.call();
        },
      );
}

class _Icono extends StatelessWidget {
  const _Icono(this.icon);
  final IconData icon;

  @override
  Widget build(BuildContext context) => Center(
        child: Container(
          width: 84,
          height: 84,
          decoration: BoxDecoration(color: Bio.greenSoft, borderRadius: BorderRadius.circular(26)),
          child: Icon(icon, size: 40, color: Bio.green),
        ),
      );
}

/// Botón "Reenviar" con espera de 60 s entre envíos.
mixin _Cooldown<T extends StatefulWidget> on State<T> {
  int wait = 0;
  Timer? _timer;

  void startCooldown() {
    setState(() => wait = 60);
    _timer?.cancel();
    _timer = Timer.periodic(const Duration(seconds: 1), (t) {
      if (!mounted) return t.cancel();
      setState(() => wait--);
      if (wait <= 0) t.cancel();
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }
}

// ------------------------------------------------------------------ verificar correo
/// Después de registrarse: escribir el código que llegó al correo.
class VerifyEmailScreen extends StatefulWidget {
  const VerifyEmailScreen({super.key});

  @override
  State<VerifyEmailScreen> createState() => _VerifyEmailScreenState();
}

class _VerifyEmailScreenState extends State<VerifyEmailScreen> with _Cooldown {
  final _code = TextEditingController();
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    // El primer código se acaba de enviar al registrarse: espera antes de permitir reenviarlo.
    WidgetsBinding.instance.addPostFrameCallback((_) => startCooldown());
  }

  @override
  void dispose() {
    _code.dispose();
    super.dispose();
  }

  Future<void> _verify() async {
    if (_code.text.length != 6 || _busy) return;
    setState(() => _busy = true);
    try {
      await AppScope.read(context).verifyEmail(_code.text);
      if (!mounted) return;
      showSnack(context, '¡Correo verificado!');
      Navigator.of(context).pushAndRemoveUntil(MaterialPageRoute(builder: (_) => const Shell()), (_) => false);
    } catch (e) {
      if (mounted) showSnack(context, '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _resend() async {
    try {
      await AppScope.read(context).api.resendVerification();
      startCooldown();
      if (mounted) showSnack(context, 'Te enviamos un código nuevo');
    } catch (e) {
      if (mounted) showSnack(context, '$e');
    }
  }

  Future<void> _otherAccount() async {
    await AppScope.read(context).logout();
    if (mounted) {
      Navigator.of(context).pushAndRemoveUntil(MaterialPageRoute(builder: (_) => const StartScreen()), (_) => false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    final muted = TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant, height: 1.4);
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 440),
            child: ListView(padding: const EdgeInsets.all(24), shrinkWrap: true, children: [
              const _Icono(Icons.mark_email_unread_outlined),
              const SizedBox(height: 20),
              const Text('Verifica tu correo', textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 24, fontWeight: FontWeight.w700)),
              const SizedBox(height: 8),
              Text('Te enviamos un código de 6 dígitos a\n${state.userEmail}', textAlign: TextAlign.center, style: muted),
              const SizedBox(height: 4),
              Text('Si no lo ves, revisa la carpeta de spam.', textAlign: TextAlign.center, style: muted),
              const SizedBox(height: 24),
              _CodeField(_code, onDone: _verify),
              const SizedBox(height: 20),
              FilledButton(
                onPressed: _busy ? null : _verify,
                child: _busy
                    ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Text('Verificar'),
              ),
              const SizedBox(height: 8),
              TextButton(
                onPressed: wait > 0 ? null : _resend,
                child: Text(wait > 0 ? 'Reenviar código en $wait s' : 'Reenviar código'),
              ),
              TextButton(onPressed: _otherAccount, child: const Text('Usar otra cuenta')),
            ]),
          ),
        ),
      ),
    );
  }
}

// ------------------------------------------------------------------ recuperar contraseña
/// "¿Olvidaste tu contraseña?": código al correo y contraseña nueva.
class ForgotPasswordScreen extends StatefulWidget {
  const ForgotPasswordScreen({super.key, this.email = ''});
  final String email;

  @override
  State<ForgotPasswordScreen> createState() => _ForgotPasswordScreenState();
}

class _ForgotPasswordScreenState extends State<ForgotPasswordScreen> with _Cooldown {
  late final _email = TextEditingController(text: widget.email);
  final _code = TextEditingController();
  final _pwd = TextEditingController();
  final _pwd2 = TextEditingController();
  bool _sent = false;
  bool _busy = false;
  bool _show = false;

  @override
  void dispose() {
    for (final c in [_email, _code, _pwd, _pwd2]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _run(Future<void> Function() action) async {
    setState(() => _busy = true);
    try {
      await action();
    } catch (e) {
      if (mounted) showSnack(context, '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _send() => _run(() async {
        final email = _email.text.trim();
        if (!RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(email)) {
          return showSnack(context, 'Escribe un correo válido');
        }
        await AppScope.read(context).api.forgotPassword(email);
        if (!mounted) return;
        setState(() => _sent = true);
        startCooldown();
      });

  Future<void> _reset() => _run(() async {
        if (_code.text.length != 6) return showSnack(context, 'Escribe el código de 6 dígitos');
        if (_pwd.text.length < 8) return showSnack(context, 'La contraseña debe tener al menos 8 caracteres');
        if (_pwd.text != _pwd2.text) return showSnack(context, 'Las contraseñas no coinciden');
        await AppScope.read(context).resetPassword(_email.text, _code.text, _pwd.text);
        if (!mounted) return;
        showSnack(context, 'Contraseña cambiada. ¡Bienvenido de nuevo!');
        Navigator.of(context).pushAndRemoveUntil(MaterialPageRoute(builder: (_) => const Shell()), (_) => false);
      });

  @override
  Widget build(BuildContext context) {
    final muted = TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant, height: 1.4);
    final loading = const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2));
    return Scaffold(
      appBar: AppBar(),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 440),
            child: ListView(padding: const EdgeInsets.fromLTRB(24, 0, 24, 24), children: [
              const _Icono(Icons.lock_reset),
              const SizedBox(height: 20),
              Text(_sent ? 'Crea una contraseña nueva' : '¿Olvidaste tu contraseña?', textAlign: TextAlign.center,
                  style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w700)),
              const SizedBox(height: 8),
              Text(
                  _sent
                      ? 'Si ${_email.text.trim()} tiene una cuenta, le llegó un código de 6 dígitos. Vence en 15 minutos.'
                      : 'Escribe el correo con el que te registraste y te enviaremos un código para cambiarla.',
                  textAlign: TextAlign.center,
                  style: muted),
              const SizedBox(height: 24),
              if (!_sent) ...[
                TextField(
                  controller: _email,
                  keyboardType: TextInputType.emailAddress,
                  autofillHints: const [AutofillHints.email],
                  decoration: const InputDecoration(labelText: 'Correo electrónico', prefixIcon: Icon(Icons.alternate_email)),
                  onSubmitted: (_) => _send(),
                ),
                const SizedBox(height: 20),
                FilledButton(onPressed: _busy ? null : _send, child: _busy ? loading : const Text('Enviar código')),
              ] else ...[
                _CodeField(_code),
                const SizedBox(height: 14),
                TextField(
                  controller: _pwd,
                  obscureText: !_show,
                  autofillHints: const [AutofillHints.newPassword],
                  decoration: InputDecoration(
                    labelText: 'Contraseña nueva (mín. 8)',
                    prefixIcon: const Icon(Icons.lock_outline),
                    suffixIcon: IconButton(
                      icon: Icon(_show ? Icons.visibility_off_outlined : Icons.visibility_outlined),
                      onPressed: () => setState(() => _show = !_show),
                    ),
                  ),
                ),
                const SizedBox(height: 14),
                TextField(
                  controller: _pwd2,
                  obscureText: !_show,
                  decoration: const InputDecoration(labelText: 'Repite la contraseña', prefixIcon: Icon(Icons.lock_outline)),
                  onSubmitted: (_) => _reset(),
                ),
                const SizedBox(height: 20),
                FilledButton(onPressed: _busy ? null : _reset, child: _busy ? loading : const Text('Cambiar contraseña')),
                TextButton(
                  onPressed: wait > 0 || _busy ? null : _send,
                  child: Text(wait > 0 ? 'Reenviar código en $wait s' : 'Reenviar código'),
                ),
                TextButton(onPressed: () => setState(() => _sent = false), child: const Text('Cambiar el correo')),
              ],
            ]),
          ),
        ),
      ),
    );
  }
}
