import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:timezone/data/latest.dart' as tzdata;
import 'package:timezone/timezone.dart' as tz;

import '../api/models.dart';

/// Recordatorios de incubación: una notificación del teléfono cuando las placas de una siembra están listas
/// para leer ("Tus placas de Agua de río están listas para leer (24 h)").
///
/// Solo en Android. En la web no se pueden programar avisos con la app cerrada: allí la pantalla de inicio
/// muestra las siembras listas al abrirla.
class Reminders {
  Reminders._();

  static final _plugin = FlutterLocalNotificationsPlugin();
  static bool _ready = false;

  static bool get supported => !kIsWeb && defaultTargetPlatform == TargetPlatform.android;

  static const _details = NotificationDetails(
    android: AndroidNotificationDetails(
      'incubacion',
      'Incubación',
      channelDescription: 'Aviso cuando las placas sembradas están listas para leer',
      importance: Importance.high,
      priority: Priority.high,
    ),
  );

  static Future<bool> _init() async {
    if (!supported) return false;
    if (_ready) return true;
    try {
      tzdata.initializeTimeZones();
      await _plugin.initialize(settings: const InitializationSettings(
          android: AndroidInitializationSettings('@mipmap/ic_launcher')));
      _ready = true;
    } catch (e) {
      debugPrint('No se pudieron preparar los recordatorios: $e');
    }
    return _ready;
  }

  /// Pide permiso para notificar (Android 13+). Se llama al registrar la primera siembra.
  static Future<void> requestPermission() async {
    if (!await _init()) return;
    await _plugin
        .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()
        ?.requestNotificationsPermission();
  }

  static String message(Incubation i) {
    final horas = i.hours == i.hours.roundToDouble() ? '${i.hours.round()} h' : '${i.hours} h';
    return 'Tus placas de ${i.name} están listas para leer ($horas).';
  }

  /// Programa un aviso por cada siembra pendiente y cancela los de las que ya se leyeron o se borraron.
  /// Se llama cada vez que la app carga la lista de siembras.
  static Future<void> sync(List<Incubation> pending) async {
    if (!await _init()) return;
    try {
      await _plugin.cancelAllPendingNotifications();
      final now = DateTime.now();
      for (final i in pending) {
        if (i.doneAt != null || !i.readyAt.isAfter(now)) continue;
        await _plugin.zonedSchedule(
          id: i.id,
          title: 'Placas listas para leer',
          body: message(i),
          scheduledDate: tz.TZDateTime.from(i.readyAt.toUtc(), tz.UTC),
          notificationDetails: _details,
          // Sin alarma exacta (no requiere permisos especiales): Android puede retrasarla unos minutos.
          androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
        );
      }
    } catch (e) {
      debugPrint('No se pudieron programar los recordatorios: $e');
    }
  }
}
