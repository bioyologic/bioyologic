# Seguridad y rendimiento de Bioyologic

Qué protege el sistema, cómo, y qué queda fuera. Todo lo que dice este documento está cubierto por pruebas automáticas (`backend/tests/test_seguridad.py`, `test_accounts.py`).

## Cuentas y sesiones

| Medida | Cómo |
|---|---|
| Contraseñas | Se guardan con **scrypt** y una sal distinta por cuenta; nunca en texto. Mínimo 8 caracteres y se rechazan las más comunes, un solo carácter repetido o el propio correo |
| Sesiones | Token aleatorio de 256 bits; en la base de datos solo se guarda su hash (SHA-256). Vencen a los 30 días y se cierran todas al cambiar la contraseña |
| Fuerza bruta por IP | 10 intentos de inicio de sesión o registro por minuto y por IP |
| Fuerza bruta por cuenta | 10 contraseñas incorrectas bloquean la cuenta 15 minutos, vengan de la IP que vengan; cambiar la contraseña por correo la desbloquea |
| Códigos por correo | 6 dígitos, vencen en 15–30 minutos, valen 5 intentos y solo se guarda su hash. Como mucho 3 correos por cuenta cada 15 minutos |
| Enumeración de cuentas | Iniciar sesión y «olvidé mi contraseña» responden igual y tardan lo mismo exista o no el correo |

## Datos de cada usuario

- Cada petición comprueba a quién pertenece el dato: un usuario solo ve sus análisis y proyectos, y los de los proyectos que otros comparten con él. Lo ajeno responde «no encontrado», igual que si no existiera.
- Las fotos y los informes PDF se abren con una clave secreta de 128 bits por análisis, que va en la URL. La cabecera `Referrer-Policy: no-referrer` evita que esa URL se filtre a otros sitios.
- Derechos de la Ley 1581 de 2012: descargar todos los datos, y borrar la cuenta con todo su contenido ([PRIVACIDAD.md](PRIVACIDAD.md)).
- Todas las consultas a la base de datos usan parámetros (sin inyección SQL).

## Lo que entra al servidor

| Riesgo | Protección |
|---|---|
| Fotos enormes | Máximo 15 MB por foto (la API) y 20 MB por petición (el proxy) |
| «Bomba de descompresión»: un archivo de pocos KB que declara miles de megapíxeles y agota la memoria | Se lee el tamaño en la cabecera del JPEG/PNG **antes** de abrirlo: máximo 64 megapíxeles. OpenCV tiene además su propio tope |
| Textos gigantes | Nombres ≤ 120 caracteres; notas y descripciones ≤ 5000 |
| Listados sin límite | Máximo 200 análisis por petición |
| Abuso del análisis (el paso costoso) | 20 análisis por minuto y por IP; se procesan de a uno y los demás esperan su turno |
| Fórmulas en Excel | En el CSV, los textos que empiezan por `=`, `+`, `-` o `@` se guardan como texto: Excel no los ejecuta |
| HTML o etiquetas en el PDF | Todo texto del usuario se escapa antes de entrar al informe |

## Navegador y transporte

- **HTTPS** obligatorio con certificado de Let's Encrypt (Caddy), y `Strict-Transport-Security` durante un año.
- `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` y `Content-Security-Policy: frame-ancestors 'none'`: una foto subida nunca se interpreta como página y la app no se puede incrustar en otro sitio (clickjacking).
- `Permissions-Policy`: la app web solo puede usar la cámara.
- `Cache-Control: no-store` en los datos de la cuenta: no quedan copias en la caché del navegador.

## Servidor

- El contenedor corre con un usuario sin privilegios, sin capacidades de Linux (`cap_drop: ALL`) y sin poder ganarlas (`no-new-privileges`). Solo Caddy está expuesto a internet.
- Los secretos (dominio, contraseña del correo) viven en `deploy/.env`, que no está en el repositorio.
- Copia de seguridad diaria de la base de datos y las fotos, con 14 días de historial (`deploy/backup.sh`).
- Los registros rotan (3 archivos de 10 MB): no llenan el disco.
- En Android, la app no entra en las copias de seguridad del sistema (`allowBackup="false"`), donde quedaría el token de sesión.

## Rendimiento

Medido con una foto real de 12 MP (4056 × 3040) en un computador de 8 núcleos:

| Qué | Antes | Ahora |
|---|---|---|
| Servidor mientras analiza una foto (3–4 s) | No atendía a nadie más | Responde en menos de 10 ms |
| Informe PDF | 1680 KB, 550 ms | 364 KB, 280 ms |
| Imagen anotada | 1340 KB | 936 KB |
| Listar análisis | Leía todas las colonias de cada placa (hasta cientos de KB por análisis) | Lee solo el resumen (unos 2 KB por análisis) |
| Biblioteca | Se pedía cada vez | El navegador la guarda una hora |

El análisis en sí (detectar, clasificar la especie, medir) tarda 3–4 s por foto; dos tercios son el detector.

## Límites conocidos

- Los límites de intentos se llevan en memoria: se reinician si el servidor se reinicia, y valen para un solo proceso (así está desplegado).
- El APK se firma con la clave de depuración: sirve para instalarlo a mano, no para publicarlo en Google Play.
- En Android el token de sesión se guarda en el almacenamiento privado de la app, sin cifrado adicional.
- CORS está abierto por defecto (la autenticación va en una cabecera, no en cookies, así que otro sitio no puede usar la sesión de nadie). Se puede cerrar con `BIOYOLOGIC_CORS_ORIGINS`.
- Las dependencias de Python se instalan con versión mínima, no exacta.

Para avisar de un problema de seguridad, escribe al correo de contacto de la [política de privacidad](PRIVACIDAD.md).
