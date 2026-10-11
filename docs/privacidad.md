# Política de privacidad de Bioyologic

*Última actualización: 11 de octubre de 2026*

Bioyologic es una app de software libre (AGPL-3.0) para contar y caracterizar colonias bacterianas a partir de fotos de placas de Petri. Esta política explica qué datos maneja y dónde se guardan.

## Qué datos se recogen

| Dato | Para qué | Dónde se guarda |
|---|---|---|
| **Fotos de placas de Petri** que tomas o eliges | Analizarlas: contar colonias, medirlas y estimar la especie | En el servidor de Bioyologic configurado en la app, junto con la imagen anotada y una miniatura |
| **Datos del análisis**: nombre de la muestra, proyecto, dilución, volumen, notas y resultados | Mostrar tu historial, tus proyectos y el informe PDF | En el servidor de Bioyologic |
| **Perfil**: nombre, cargo e institución | Saludarte y personalizar la app | **Solo en tu teléfono**; nunca se envía al servidor |
| **Preferencias**: servidor, tema, cámara | Configurar la app | Solo en tu teléfono |

Bioyologic **no** tiene cuentas de usuario. **No** usa publicidad, analítica ni rastreadores, y **no** pide tu ubicación ni tus contactos.

## Permisos del teléfono

- **Cámara**: para fotografiar la placa. La foto se envía al servidor solo cuando pulsas «Analizar».
- **Fotos o galería**: para elegir una foto que ya tienes. Solo se envía la foto que eliges.

## Servidor

- **Servidor público del proyecto:** las fotos viajan cifradas (HTTPS) y se guardan para que puedas ver tu historial. Ese servidor no es privado: cualquier persona que use la misma instancia puede ver los análisis guardados en ella.
  - **No subas fotos con datos personales ni de pacientes**, como etiquetas con nombres.
- **Servidor propio:** como Bioyologic es software libre, puedes instalar tu propio servidor (ver `deploy/`) y configurarlo en *Perfil → Configuración → Servidor*. En ese caso tus datos quedan bajo tu control.

## Conservación y borrado

- Los análisis se guardan hasta que los borras desde la app. Al eliminar un análisis también se borran sus fotos.
- Para borrar tu perfil local, usa «Cerrar sesión» en la app o desinstálala.
- Si quieres que se borren datos del servidor público y no puedes hacerlo desde la app, escribe a las personas que mantienen el proyecto (contacto en el repositorio).

## Terceros

- Las fotos **no** se venden ni se comparten con terceros.
- El servidor se aloja en un proveedor de nube (por ejemplo, Oracle Cloud), que solo aporta la máquina donde se ejecuta.

## Uso no médico

Los resultados son orientativos y no constituyen un diagnóstico. Bioyologic no es un dispositivo médico.

## Cambios

Si esta política cambia, se publicará la nueva versión en el repositorio del proyecto con su fecha.
