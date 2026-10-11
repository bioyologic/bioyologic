import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'shell.dart';
import 'welcome_screen.dart';

class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> with SingleTickerProviderStateMixin {
  late final _anim = AnimationController(vsync: this, duration: const Duration(milliseconds: 900))..forward();

  @override
  void initState() {
    super.initState();
    Future.delayed(const Duration(milliseconds: 1800), () {
      if (!mounted) return;
      final next = AppScope.read(context).hasProfile ? const Shell() : const WelcomeScreen();
      Navigator.of(context).pushReplacement(PageRouteBuilder(
        pageBuilder: (_, _, _) => next,
        transitionsBuilder: (_, a, _, child) => FadeTransition(opacity: a, child: child),
        transitionDuration: const Duration(milliseconds: 400),
      ));
    });
  }

  @override
  void dispose() {
    _anim.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Bio.green,
      body: Stack(children: [
        const Positioned.fill(child: CustomPaint(painter: _LeavesPainter())),
        Center(
          child: FadeTransition(
            opacity: CurvedAnimation(parent: _anim, curve: Curves.easeOut),
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              const BioLogo(size: 96),
              const SizedBox(height: 22),
              const Text('Bioyologic',
                  style: TextStyle(
                      color: Colors.white, fontSize: 38, fontWeight: FontWeight.w700, letterSpacing: -0.5)),
              const SizedBox(height: 10),
              Text('Conteo y caracterización\nde colonias bacterianas',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.white.withValues(alpha: 0.8), fontSize: 15, height: 1.4)),
            ]),
          ),
        ),
        const Positioned(
          left: 0,
          right: 0,
          bottom: 48,
          child: Center(
            child: SizedBox(
                width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2, color: Bio.mint)),
          ),
        ),
      ]),
    );
  }
}

/// Hojas tenues de fondo, como en el diseño.
class _LeavesPainter extends CustomPainter {
  const _LeavesPainter();

  @override
  void paint(Canvas canvas, Size s) {
    final p = Paint()..color = Colors.white.withValues(alpha: 0.05);
    void leaf(Offset c, double size, double angle) {
      canvas.save();
      canvas.translate(c.dx, c.dy);
      canvas.rotate(angle);
      final path = Path()
        ..moveTo(0, 0)
        ..quadraticBezierTo(size * 0.5, -size * 0.45, size, 0)
        ..quadraticBezierTo(size * 0.5, size * 0.45, 0, 0);
      canvas.drawPath(path, p);
      canvas.restore();
    }

    leaf(Offset(s.width * 0.85, s.height * 0.12), s.width * 0.55, math.pi * 0.75);
    leaf(Offset(s.width * 1.0, s.height * 0.25), s.width * 0.4, math.pi * 0.95);
    leaf(Offset(-s.width * 0.05, s.height * 0.85), s.width * 0.6, -math.pi * 0.2);
    leaf(Offset(s.width * 0.1, s.height * 1.0), s.width * 0.45, -math.pi * 0.4);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
