import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/date_symbol_data_local.dart';

import 'screens/auth_screen.dart';
import 'screens/splash_screen.dart';
import 'state/app_state.dart';
import 'theme.dart';

final navigatorKey = GlobalKey<NavigatorState>();

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await initializeDateFormatting('es');
  final state = await AppState.load();
  // Sesión caducada o cerrada desde otro dispositivo: de vuelta a iniciar sesión.
  state.sessionExpired.addListener(() => navigatorKey.currentState?.pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const AuthScreen(expired: true)), (_) => false));
  runApp(AppScope(state: state, child: const BioyologicApp()));
}

class BioyologicApp extends StatelessWidget {
  const BioyologicApp({super.key});

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    return MaterialApp(
      title: 'Bioyologic',
      navigatorKey: navigatorKey,
      debugShowCheckedModeBanner: false,
      theme: buildTheme(Brightness.light),
      darkTheme: buildTheme(Brightness.dark),
      themeMode: state.darkMode ? ThemeMode.dark : ThemeMode.light,
      locale: const Locale('es'),
      supportedLocales: const [Locale('es')],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      home: const SplashScreen(),
    );
  }
}
