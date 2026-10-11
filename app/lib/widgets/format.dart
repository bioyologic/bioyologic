import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../theme.dart';

const _sup = {
  '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
  '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹', '-': '⁻',
};

String superscript(int n) => n.toString().split('').map((c) => _sup[c]!).join();

/// 15000000 -> "1,50 × 10⁷"
String scientific(double v) {
  if (v == 0) return '0';
  final exp = (math.log(v.abs()) / math.ln10).floor();
  final mant = v / math.pow(10, exp);
  return '${mant.toStringAsFixed(2).replaceAll('.', ',')} × 10${superscript(exp)}';
}

/// 0.0001 -> "10⁻⁴"
String dilutionLabel(double d) {
  final e = math.log(d) / math.ln10;
  if ((e - e.round()).abs() < 1e-9) return '10${superscript(e.round())}';
  return d.toString();
}

String fmt(num? v, [int digits = 1]) =>
    v == null ? '—' : v.toStringAsFixed(digits).replaceAll('.', ',');

String capitalize(String? s) => (s == null || s.isEmpty) ? '—' : s[0].toUpperCase() + s.substring(1);

/// "Hoy, 10:30" · "Ayer, 18:02" · "12 oct, 09:15"
String friendlyDate(DateTime d) {
  final now = DateTime.now();
  final today = DateTime(now.year, now.month, now.day);
  final day = DateTime(d.year, d.month, d.day);
  final time = DateFormat('HH:mm').format(d);
  if (day == today) return 'Hoy, $time';
  if (day == today.subtract(const Duration(days: 1))) return 'Ayer, $time';
  return '${DateFormat(d.year == now.year ? 'd MMM' : 'd MMM yyyy', 'es').format(d)}, $time';
}

String statusLabel(String s) => switch (s) {
      'contable' => 'Completado',
      'pocas' => 'Pocas colonias',
      'incontable' => 'Incontable',
      _ => s,
    };

String statusDetail(String s) => switch (s) {
      'contable' => 'Placa en rango contable (30–300 colonias).',
      'pocas' => 'Menos de 30 colonias: el recuento de UFC es solo orientativo.',
      'incontable' => 'Más de 300 colonias: repite con una dilución mayor.',
      _ => '',
    };

Color statusColor(String s) => switch (s) {
      'contable' => Bio.ok,
      'pocas' => Bio.warn,
      _ => Bio.danger,
    };

Color hexColor(String hex) => Color(int.parse(hex.substring(1), radix: 16) | 0xFF000000);

/// Nombre de especie legible: "S.aureus" -> "S. aureus"
String speciesLabel(String s) => s == 'colony' ? 'Colonia' : s.replaceAllMapped(RegExp(r'\.(\S)'), (m) => '. ${m[1]}');

const marginLabels = {'entero': 'Entero (liso)', 'ondulado': 'Ondulado', 'lobulado': 'Lobulado'};
