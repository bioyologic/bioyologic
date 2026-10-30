import 'package:flutter/material.dart';

import '../theme.dart';
import '../widgets/common.dart';
import 'auth_screen.dart';

/// Portada para quien no ha iniciado sesión: elegir entre crear una cuenta o entrar.
class StartScreen extends StatelessWidget {
  const StartScreen({super.key});

  @override
  Widget build(BuildContext context) {
    void open(bool register) => Navigator.of(context)
        .push(MaterialPageRoute(builder: (_) => AuthScreen(register: register)));
    final light = Colors.white.withValues(alpha: 0.82);
    return Scaffold(
      backgroundColor: Bio.green,
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 440),
            child: Padding(
              padding: const EdgeInsets.fromLTRB(28, 24, 28, 32),
              child: Column(children: [
                const Spacer(flex: 2),
                const BioLogo(size: 96),
                const SizedBox(height: 22),
                const Text('Bioyologic',
                    style: TextStyle(color: Colors.white, fontSize: 38, fontWeight: FontWeight.w700, letterSpacing: -0.5)),
                const SizedBox(height: 10),
                Text('Conteo y caracterización de colonias bacterianas desde tu celular',
                    textAlign: TextAlign.center, style: TextStyle(color: light, fontSize: 16, height: 1.4)),
                const Spacer(flex: 3),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    style: FilledButton.styleFrom(
                        backgroundColor: Colors.white,
                        foregroundColor: Bio.green,
                        padding: const EdgeInsets.symmetric(vertical: 16)),
                    onPressed: () => open(true),
                    child: const Text('Crear cuenta', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                  ),
                ),
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton(
                    style: OutlinedButton.styleFrom(
                        foregroundColor: Colors.white,
                        side: const BorderSide(color: Colors.white, width: 1.5),
                        padding: const EdgeInsets.symmetric(vertical: 16)),
                    onPressed: () => open(false),
                    child: const Text('Iniciar sesión', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                  ),
                ),
                const SizedBox(height: 16),
                Text('¿Primera vez? Crea tu cuenta gratis. ¿Ya tienes una? Inicia sesión.',
                    textAlign: TextAlign.center, style: TextStyle(color: light, fontSize: 13)),
              ]),
            ),
          ),
        ),
      ),
    );
  }
}
