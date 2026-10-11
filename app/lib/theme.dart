import 'package:flutter/material.dart';

/// Paleta del diseño de Bioyologic: verde bosque sobre fondos claros.
class Bio {
  static const green = Color(0xFF1F5C45);
  static const greenDark = Color(0xFF15402F);
  static const greenSoft = Color(0xFFE6F2EC);
  static const mint = Color(0xFF8FD0B0);
  static const bg = Color(0xFFF5F7F5);
  static const ok = Color(0xFF2E8B57);
  static const warn = Color(0xFFE08A1E);
  static const danger = Color(0xFFD64545);
}

ThemeData buildTheme(Brightness brightness) {
  final dark = brightness == Brightness.dark;
  final scheme = ColorScheme.fromSeed(
    seedColor: Bio.green,
    brightness: brightness,
    primary: dark ? Bio.mint : Bio.green,
    onPrimary: dark ? Bio.greenDark : Colors.white,
    surface: dark ? const Color(0xFF111714) : Colors.white,
    error: Bio.danger,
  );
  final bg = dark ? const Color(0xFF0B100D) : Bio.bg;
  final border = dark ? const Color(0xFF26302B) : const Color(0xFFE3E9E5);

  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: bg,
    appBarTheme: AppBarTheme(
      backgroundColor: bg,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      centerTitle: false,
      titleTextStyle: TextStyle(
          fontSize: 20, fontWeight: FontWeight.w700, color: scheme.onSurface, letterSpacing: -0.2),
    ),
    cardTheme: CardThemeData(
      color: scheme.surface,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16), side: BorderSide(color: border)),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(0, 52),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        textStyle: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size(0, 48),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: scheme.surface,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide(color: border)),
      enabledBorder:
          OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide(color: border)),
    ),
    chipTheme: ChipThemeData(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      side: BorderSide(color: border),
    ),
    dividerTheme: DividerThemeData(color: border, space: 1),
    tabBarTheme: TabBarThemeData(
      labelColor: scheme.primary,
      unselectedLabelColor: scheme.onSurfaceVariant,
      indicatorColor: scheme.primary,
      dividerColor: border,
      labelStyle: const TextStyle(fontWeight: FontWeight.w600),
    ),
  );
}
