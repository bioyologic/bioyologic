import 'package:flutter/material.dart';

import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'shell.dart';

/// Primer uso (o tras cerrar sesión): datos del perfil local.
class WelcomeScreen extends StatefulWidget {
  const WelcomeScreen({super.key});

  @override
  State<WelcomeScreen> createState() => _WelcomeScreenState();
}

class _WelcomeScreenState extends State<WelcomeScreen> {
  final _form = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _role = TextEditingController();
  final _inst = TextEditingController();

  @override
  void dispose() {
    _name.dispose();
    _role.dispose();
    _inst.dispose();
    super.dispose();
  }

  Future<void> _start() async {
    if (!_form.currentState!.validate()) return;
    await AppScope.read(context).saveProfile(name: _name.text, role: _role.text, institution: _inst.text);
    if (!mounted) return;
    Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => const Shell()));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 480),
            child: Form(
              key: _form,
              child: ListView(
                padding: const EdgeInsets.all(24),
                children: [
                  const SizedBox(height: 24),
                  Center(
                    child: Container(
                      padding: const EdgeInsets.all(20),
                      decoration: BoxDecoration(color: Bio.green, borderRadius: BorderRadius.circular(28)),
                      child: const BioLogo(size: 64),
                    ),
                  ),
                  const SizedBox(height: 24),
                  const Text('Bienvenido a Bioyologic',
                      textAlign: TextAlign.center, style: TextStyle(fontSize: 24, fontWeight: FontWeight.w700)),
                  const SizedBox(height: 8),
                  Text('Cuenta y caracteriza colonias bacterianas a partir de una foto de la placa de Petri.',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)),
                  const SizedBox(height: 32),
                  TextFormField(
                    controller: _name,
                    textCapitalization: TextCapitalization.words,
                    decoration: const InputDecoration(
                        labelText: 'Nombre completo', prefixIcon: Icon(Icons.person_outline)),
                    validator: (v) => (v == null || v.trim().isEmpty) ? 'Escribe tu nombre' : null,
                  ),
                  const SizedBox(height: 14),
                  TextFormField(
                    controller: _role,
                    textCapitalization: TextCapitalization.sentences,
                    decoration: const InputDecoration(
                        labelText: 'Profesión o rol', hintText: 'p. ej. Biólogo/a', prefixIcon: Icon(Icons.badge_outlined)),
                  ),
                  const SizedBox(height: 14),
                  TextFormField(
                    controller: _inst,
                    textCapitalization: TextCapitalization.words,
                    decoration: const InputDecoration(
                        labelText: 'Laboratorio o institución', prefixIcon: Icon(Icons.apartment_outlined)),
                    onFieldSubmitted: (_) => _start(),
                  ),
                  const SizedBox(height: 28),
                  FilledButton(onPressed: _start, child: const Text('Comenzar')),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
