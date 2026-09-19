# AGENTS.md — cómo trabajar en NactionX Downloader

Guía para cualquier modelo o persona que vaya a tocar este proyecto. Léela entera antes de escribir código.
Si algo de aquí contradice lo que ves en el código, gana el código: avisa y corrige este documento.

---

## 1. Qué es esto

**NactionX Downloader 1.2.0** es un gestor de descargas de vídeo y audio de escritorio para Windows y
macOS, de uso personal. Descarga con [yt-dlp](https://github.com/yt-dlp/yt-dlp) y convierte con FFmpeg.

No es una librería ni un servicio: es una aplicación que una persona concreta abre, usa y espera que
funcione. Cada decisión se juzga por eso.

| | |
|---|---|
| Propietario | Manuel (`pymanu` en GitHub). Habla español. |
| Idioma | **Todo lo que ve el usuario va en español**: interfaz, errores, notificaciones, documentación. El código (nombres de variables, funciones) va en inglés; los comentarios y docstrings, en español. |
| Código | `pymanu/nactionx-downloader` — **privado** |
| Descargas | `pymanu/nactionx-downloader-releases` — **público**, solo instaladores |
| Carpeta de trabajo | `C:\Users\albov\OneDrive\Desktop\descargador` |

### Por qué hay dos repositorios
La app comprueba si hay una versión nueva consultando la API pública de GitHub. Consultar las
publicaciones de un repositorio privado exigiría llevar un token dentro del ejecutable, y un token
dentro de un ejecutable no es un secreto. Por eso el código es privado y los instaladores públicos.

---

## 2. Tu papel

Eres quien implementa y **verifica**. No eres quien decide por el usuario.

### Reglas no negociables

1. **Verifica con ejecuciones reales, no con razonamiento.** Este proyecto tiene un historial de
   suposiciones que resultaron falsas (§8). Si dices «funciona», tiene que ser porque lo has visto
   funcionar: una descarga real, un test que pasa, una captura de la interfaz. Nunca por deducción.
2. **Si te equivocas en algo que ya dijiste, corrígelo en voz alta.** Ha pasado y es normal. Lo que
   no vale es dejar una afirmación falsa en la documentación o en el resumen al usuario.
3. **Informa de lo que no funciona con la misma claridad que de lo que sí.** Un límite conocido y
   escrito vale más que una promesa que se cae al primer uso.
4. **No amplíes el encargo por tu cuenta.** Si ves algo que arreglarías, dilo; no lo hagas sin pedirlo.
5. **Antes de dar por cerrado un cambio, ejecuta los tests.** `python -m pytest tests -q` y que pasen
   los 121 (o los que haya). Añade tests para lo que cambies.

### Restricciones duras

- **Nunca toques los datos reales del usuario.** Viven en `%APPDATA%\NactionX Downloader` (Windows) y
  `~/Library/Application Support/NactionX Downloader` (macOS): ajustes, cola, historial y registros.
  Los tests los aíslan con `NACTIONX_DATA_DIR` (ver `tests/conftest.py`). Para probar a mano usa
  siempre `python -m nactionx --data-dir <carpeta temporal>`.
- **Nunca subas datos del usuario al repositorio.** `.gitignore` excluye `data/`, `releases/`,
  `packaging/bin/` y `*.lnk`. Comprueba `git status` antes de cada commit.
- **Nada de compilar dentro de OneDrive.** La carpeta del proyecto está sincronizada; PyInstaller e
  Inno Setup fallan o corrompen archivos ahí. Todo lo pesado va a `C:\Users\albov\.nactionx-dev\`
  (entorno virtual, descargas, `dist`, `build`, artefactos).
- **Publicar es irreversible y público.** Crear repositorios públicos, publicar versiones o hacer
  público lo privado se pregunta antes. Siempre.
- **No leas las cookies del navegador del usuario por tu cuenta.** Son credenciales suyas. La app
  tiene una opción para que las configure él.
- **`server.py` e `index.html` en la raíz son el prototipo antiguo**, que el usuario todavía puede
  estar usando. No los borres sin preguntar.

---

## 3. Arquitectura

Proceso único de Python. Un servidor HTTP local sirve la interfaz (HTML/CSS/JS sin framework) a una
ventana nativa (pywebview). No hay base de datos: el estado es JSON en disco.

```
  ventana nativa (pywebview)  ─┐
                               ├─→  web/ (HTML+CSS+JS)  ──HTTP 127.0.0.1──→  api.py
  o navegador (--browser)     ─┘                                               │
                                                               ┌───────────────┼───────────────┐
                                                          manager.py      settings.py     components.py
                                                        (cola, estado)   (validación)    (FFmpeg/Deno/yt-dlp)
                                                               │
                                                          engine.py  ──→  yt-dlp  ──→  FFmpeg
                                                               │
                                              sites.py · formats.py · names.py · errors.py
```

### Módulos

| Archivo | Responsabilidad | No debe |
|---|---|---|
| `__main__.py` | Arranque, argumentos, activar el yt-dlp actualizado **antes** de que nadie importe `yt_dlp` | — |
| `desktop.py` | Ventana nativa, instancia única, cierre ordenado, diálogos de archivo | Saber de descargas |
| `api.py` | **Única** superficie HTTP. Token por sesión, comprobación de `Host`, CSP | Tener lógica de negocio |
| `manager.py` | Cola: planificar, reintentar, pausar, persistir, historial, notificar | Hablar con yt-dlp |
| `engine.py` | **Una** descarga: opciones de yt-dlp, ganchos de progreso, recorte, limpieza | Conocer la cola entera |
| `sites.py` | Qué plataforma es un enlace, perfil o publicación, opciones por sitio | Descargar |
| `formats.py` | Selección de formato y etiquetas de calidad | Tocar red |
| `settings.py` | Esquema y validación de **todos** los ajustes | Aceptar valores sin validar |
| `errors.py` | Traducir errores técnicos a español accionable | Inventar causas |
| `names.py` | Nombres de archivo seguros y únicos | Sobrescribir archivos |
| `paths.py` | Rutas: recursos empaquetados, datos, carpetas del sistema | — |
| `platform_utils.py` | Todo lo específico de cada sistema operativo | Aparecer fuera de aquí |
| `components.py` | Encontrar FFmpeg/Deno; actualizar yt-dlp desde PyPI | — |
| `updates.py` | Aviso de versión nueva de la app | Instalar nada solo |
| `storage.py` | JSON atómico y tolerante a bloqueos | — |
| `log.py` | Registro rotativo | — |

### Invariantes que no se rompen

1. **Todo ajuste pasa por `settings.validate()`.** Claves desconocidas se ignoran; valores inválidos
   lanzan `SettingsError` con mensaje en español. Un ajuste corrupto en disco nunca debe romper el
   arranque: se descarta y se registra. Las opciones que dependen del vídeo y no son ajustes globales
   (`start`, `end`, `audio_track`) se validan aparte, en `job_options()`.
2. **`api.py` es la única puerta.** Token `X-NactionX-Token` por sesión, puerto dinámico, solo
   `127.0.0.1`, comprobación de la cabecera `Host`. El CSP tiene `connect-src 'self'`: **la interfaz
   no puede llamar a servicios externos**. Si hace falta hablar con Internet (por ejemplo GitHub),
   lo hace Python y lo expone por la API local. Por eso existe `updates.py`.
3. **El estado se transmite por revisiones.** `manager.state(srev, prev)` devuelve solo lo que cambió;
   `touch()` sube `srev` (cambios estructurales) y `bump_progress()` sube `prev` (solo progreso). Si
   añades un campo al trabajo, decide cuál de los dos toca.
4. **`JOB_DEFAULTS` define el contrato del trabajo.** Al cargar de disco se filtra contra él: un
   campo nuevo necesita su valor por defecto ahí o se pierde al reiniciar. Las claves de
   `PRIVATE_KEYS` no salen por la API.
5. **Los errores que se ven son `FriendlyError` o pasan por `errors.explain()`.** Devuelve
   `(mensaje, tipo, detalle técnico)`. Los tipos de `RETRYABLE` (`network`, `ratelimit`, `locked`)
   se reintentan solos con `RETRY_DELAYS`.
6. **Nunca se sobrescribe un archivo del usuario.** `names.unique_base()` y `names.rename_file()`
   añaden ` (2)`, ` (3)`… Hay tests que lo vigilan.
7. **El escritorio es opcional.** `--browser` levanta lo mismo sin ventana nativa. No metas
   dependencias de pywebview fuera de `desktop.py`.

---

## 4. Entorno y comandos

El entorno de desarrollo ya existe, **fuera de OneDrive**:

```bash
C:/Users/albov/.nactionx-dev/venv/Scripts/python.exe
```

Si hay que rehacerlo (Windows necesita **Python 3.13 de 64 bits**, para que los paquetes coincidan
con el Python embebido del paquete final):

```bash
python -m venv C:/Users/albov/.nactionx-dev/venv
C:/Users/albov/.nactionx-dev/venv/Scripts/python.exe -m pip install -r requirements-build.txt
```

| Para | Comando |
|---|---|
| Abrir la app | `python -m nactionx` |
| Abrirla en el navegador (desarrollo) | `python -m nactionx --browser` |
| Con datos aislados | `python -m nactionx --data-dir C:/ruta/temporal` |
| Tests | `python -m pytest tests -q` |
| Un solo test | `python -m pytest tests/test_sites_updates.py -q -k tiktok` |

**La consola de Windows usa cp1252 y revienta al imprimir «→» o tildes.** Ejecuta siempre con
`PYTHONIOENCODING=utf-8`, o reconfigura `sys.stdout` en los scripts (lo hace
`packaging/publish_release.py`).

### GitHub

```bash
export GH_CONFIG_DIR="C:/Users/albov/.nactionx-dev/gh-config"
C:/Users/albov/.nactionx-dev/gh/bin/gh.exe auth status
```

La sesión es del usuario. Si caduca, hay que pedirle que autorice un código nuevo: no se puede hacer
por él.

---

## 5. Verificación: qué cuenta como «funciona»

Un cambio no está hecho hasta que estas cuatro cosas se cumplen:

1. **Tests verdes.** `python -m pytest tests -q`.
2. **Un test nuevo por cada corrección**, escrito de forma que falle con el código viejo. El
   comentario del test dice *qué se rompía*, no qué hace el test.
3. **Prueba real contra la plataforma**, si el cambio toca descargas. Analizar y descargar de verdad.
   Los enlaces caducan: consigue uno vivo antes de dar nada por roto (ver §8, lección 6).
4. **La interfaz, vista.** `python -m nactionx --browser --no-open --data-dir <temporal>`, abrirla y
   comprobar el elemento que has tocado. Que el JavaScript no dé error no significa que se vea.

Antes de una versión, además: `python packaging/smoke_test.py --app <ejecutable empaquetado>`, que
arranca la app ya empaquetada, se descarga un vídeo generado al vuelo con FFmpeg desde un servidor
local, lo recorta y comprueba 14 cosas. No depende de ninguna web externa, a propósito.

---

## 6. Empaquetado

### Windows — y por qué no hay un `.exe` propio
El usuario tiene **Smart App Control** activo en Windows 11, que bloquea ejecutables sin firma de
pago. Un `.exe` de PyInstaller sin firmar queda bloqueado. Por eso Windows **no** usa PyInstaller:

```
NactionX Downloader/
  runtime/   Python embebible oficial, firmado por la Python Software Foundation
  app/       código + FFmpeg (Gyan, hash fijado) + Deno (firmado por Deno Land)
```

`packaging/build_windows_portable.py` lo monta y verifica firma y SHA-256 de cada pieza.
`packaging/windows/installer.iss` genera el instalador (Inno Setup, por usuario, sin administrador).

**No conviertas Windows a PyInstaller.** Ya se probó y Smart App Control lo bloqueó.

### macOS
PyInstaller (`packaging/nactionx.spec`) genera el `.app`, y `packaging/make_dmg.sh` lo firma en modo
ad-hoc y crea el `.dmg`. No se puede compilar desde Windows: lo hace GitHub Actions en Macs reales,
o el usuario con `Compilar en Mac.command`.

### Publicar una versión

1. Subir `__version__` en `nactionx/__init__.py` y escribir la sección en `CHANGELOG.md`.
2. Lanzar el flujo de Actions (`gh workflow run build.yml --ref master`) y esperar a las tres máquinas.
3. Bajar los artefactos a `releases/`.
4. `python packaging/publish_release.py` — comprueba que están los tres archivos, toma las notas del
   `CHANGELOG` y publica en el repositorio público. `--dry-run` solo comprueba.

---

## 7. Convenciones de código

- Python 3.12+, sin dependencias nuevas salvo necesidad real y justificada.
- Líneas de hasta ~120 caracteres. Sin formateador automático: imita el estilo que ya hay.
- **Los comentarios explican por qué, no qué.** Y sobre todo: cuando algo está escrito de forma rara
  porque la forma obvia no funcionaba, el comentario dice qué fallaba. Ejemplo real en `engine.py`:

  ```python
  # Solo la plantilla: la carpeta va en 'paths'. Si la carpeta formara parte de la plantilla, el límite
  # de longitud de yt-dlp se aplicaría a la ruta entera y cortaría el nombre (y el sufijo de recorte).
  ```

- Interfaz: nada de frameworks, nada de CDN. `web/app.js` es JavaScript plano con un objeto `S` como
  estado y funciones `render*()`. Mantén el patrón.
- Accesibilidad: todo control tiene `aria-label` o etiqueta visible. No lo quites.
- Git: mensajes en español, cuerpo explicando el porqué. Termina con
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>` cuando el cambio lo haga un modelo.
- `.gitattributes` fuerza LF en `*.sh`, `*.command`, `*.yml` y `*.py`. Con CRLF, macOS falla con
  «bad interpreter».

---

## 8. Lecciones ya pagadas

Errores reales de este proyecto. **No los repitas.**

1. **El orden de `format_sort` importa y la extensión no va primero.** Con `ext` delante, un 1080p MP4
   le ganaba a un 2160p WEBM y «Máxima calidad» mentía. El orden correcto es
   `resolución → fps → códec → extensión`. Consecuencia que sorprende: el selector de códec **solo
   desempata entre formatos de la misma resolución**. En TikTok, poner H.264 no evita el H.265 de
   720p, porque en H.264 solo existe el de 576p.

2. **La carpeta de destino va en `paths`, no en la plantilla.** `trim_file_name` de yt-dlp corta la
   cadena entera: con la carpeta dentro, los nombres salían truncados y sin el sufijo del recorte.

3. **WEBM no admite H.264.** La unión falla con «Conversion failed!». `formats.fix_combo()` lo corrige
   y la interfaz desactiva la opción.

4. **PyInstaller y el icono en Windows:** pasar un PNG revienta con `System.Drawing.Icon.Initialize`
   al arrancar. En Windows hay que dar `.ico`; en macOS, `.icns`.

5. **TikTok rechaza la cabecera por defecto de yt-dlp** y devuelve una página de verificación: no se
   podía analizar ni un vídeo. Con cabecera de navegador funciona (`sites.request_options()`).

6. **Antes de declarar algo roto, comprueba que tu caso de prueba es válido.** Se perdió tiempo
   depurando un «IP bloqueada» de TikTok que en realidad era un identificador de vídeo inventado.
   TikTok e Instagram cargan las cuadrículas por JavaScript: los enlaces reales se sacan con el
   navegador, no leyendo el HTML.

7. **Windows no siempre puede comprobar firmas.** En los runners de GitHub, el módulo de seguridad de
   PowerShell no carga. Una firma que no cuadra debe abortar; que Windows no pueda consultarla solo
   avisa, porque el SHA-256 fijado ya garantiza el contenido.

8. **Inno Setup se queda sin memoria con `lzma2/ultra64`.** Usa `max` con `LZMAUseSeparateProcess=yes`.

9. **Recortar pidiendo rangos por HTTP es inservible**: lentísimo y no se puede cancelar. `TrimPP`
   descarga entero y corta después: exacto y cancelable.

10. **Los enlaces compartidos de Instagram y TikTok llevan identificadores de sesión** (`igsh`,
    `is_from_webapp`…). Sin limpiarlos, el mismo vídeo entra dos veces en la cola.

11. **La clave de duplicados de `manager.add()` define qué es «la misma descarga».** Al añadir la
    pista de audio, el mismo vídeo en español y en alemán se descartaba como repetido y solo bajaba
    el primero. Si añades una opción que cambia el archivo resultante, tiene que entrar en esa clave
    **y** en el nombre del archivo, o el usuario acaba con «Vídeo.mp4» y «Vídeo (2).mp4».

12. **Antes de declarar un fallo, comprueba que tu prueba no lo ha causado.** Un «TAG:language=eng»
    en un audio en español resultó venir de que el propio script de prueba desactivaba
    `embed_metadata`. Con los ajustes reales la etiqueta era correcta.

---

## 9. Estado actual y límites conocidos

**Versión 1.2.0.** 121 tests. Windows, macOS Apple Silicon y macOS Intel compilados y con la prueba
automática superada en máquinas reales.

Plataformas verificadas con descargas reales: YouTube, Instagram, TikTok.

### Límites que ya están documentados (no son fallos por descubrir)

- **Perfiles completos de Instagram y TikTok: no se pueden listar.** Ninguna de las dos lo permite
  desde fuera de su app. Solo publicaciones sueltas. Pegar un perfil da un mensaje que lo explica.
- **Instagram y la sesión.** Cuentas privadas, historias y parte del contenido exigen cookies. En
  Windows, Chrome y Edge cifran las suyas y yt-dlp no puede leerlas: Firefox o `cookies.txt`.
- **Sin firma de pago.** SmartScreen avisa en Windows y macOS pide «Abrir igualmente». Se quita con un
  certificado de Windows y una cuenta de Apple Developer (99 USD/año).
- **Recortar descarga el vídeo entero primero.** Es el precio de que el corte sea exacto y cancelable.
- **La app no se actualiza sola.** Avisa y abre la descarga; instalar lo hace el usuario.

### Hoja de ruta
Selector de pestañas de canal, editar opciones de un trabajo en cola, límite de velocidad global,
tema claro, omitir ya descargados, inglés, grabación de directos, icono en la bandeja, programador de
descargas, extensión «Enviar a NactionX», descargas en procesos aislados.

---

## 10. Dónde mirar antes de preguntar

| Duda | Archivo |
|---|---|
| Qué se auditó, qué se corrigió y con qué prueba | `PLAN_DE_MEJORA.md` |
| Qué cambió en cada versión | `CHANGELOG.md` |
| Instalar, actualizar, compilar, publicar | `README.md` |
| Licencias de terceros | `THIRD_PARTY_NOTICES.md` |
| Qué comprueba la prueba de la app empaquetada | `packaging/smoke_test.py` |
