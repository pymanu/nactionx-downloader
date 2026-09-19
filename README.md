# NactionX Downloader

Gestor de descargas de vídeo y audio para Windows y macOS. Funciona con YouTube, Instagram, TikTok y más de 1.000 webs gracias a [yt-dlp](https://github.com/yt-dlp/yt-dlp).

- Cola real: descargas simultáneas, pausar y reanudar desde donde se quedó, reordenar arrastrando y reintento automático.
- Vista previa con calidades y tamaños estimados, playlists, canales y búsqueda.
- Vídeo en MP4/MKV/WEBM con el códec que elijas, o audio en MP3/M4A/OPUS/FLAC/WAV.
- Nombre de archivo propio, recorte de fragmentos, subtítulos, carátula, metadatos y SponsorBlock.
- Motor actualizable desde la propia app, y aviso cuando hay una versión nueva de la app.

### Instagram y TikTok
Pega el enlace de una publicación concreta (`instagram.com/reel/…`, `instagram.com/p/…`, `tiktok.com/@usuario/video/…`, o los enlaces cortos `vm.tiktok.com/…`). Valen las mismas opciones que en YouTube: calidad, solo audio, recorte y nombre propio.

Los **perfiles enteros** no se pueden listar: ni Instagram ni TikTok lo permiten desde fuera de sus apps. Para Instagram, si la publicación es de una cuenta privada o exige sesión, configura las cookies en *Ajustes → Cuenta y red* (Firefox o un `cookies.txt`; en Windows, Chrome y Edge cifran sus cookies y no se pueden leer).

## Instalar

Descarga la última versión en **[github.com/pymanu/nactionx-downloader-releases/releases/latest](https://github.com/pymanu/nactionx-downloader-releases/releases/latest)**.

### Windows 10/11
- **Instalador (recomendado):** ejecuta `NactionX-Downloader-<versión>-Windows-x64-Setup.exe`. No pide permisos de administrador y crea accesos en el escritorio y en el menú Inicio. Si SmartScreen avisa de que la app no es conocida, pulsa **Más información → Ejecutar de todas formas**: el aviso sale porque el instalador no está firmado con un certificado de pago.
- **Portable:** descomprime `NactionX-Downloader-<versión>-Windows-x64-Portable.zip` donde quieras y abre `NactionX Downloader.cmd`. En **Ajustes → Comportamiento** puedes crear los accesos directos.

La versión de Windows funciona con **Smart App Control** de Windows 11, que bloquea programas sin firma. En lugar de un `.exe` propio, usa el Python oficial firmado por la Python Software Foundation, FFmpeg de Gyan y Deno firmado. Necesita Microsoft Edge WebView2, que viene de serie en Windows 11; si falta, la app lo avisa y abre la página oficial.

### macOS 11 o posterior
1. Descarga el `.dmg` de tu Mac: **Apple Silicon** (M1 o posterior) o **Intel**.
2. Arrastra **NactionX Downloader** a **Aplicaciones**.
3. La primera vez, macOS lo bloqueará por no estar firmado por Apple:
   - **macOS 15 o posterior:** intenta abrirla, cierra el aviso y ve a **Ajustes del Sistema → Privacidad y seguridad → Abrir igualmente**.
   - **macOS 14 o anterior:** clic derecho sobre la app → **Abrir** → **Abrir**.

## Dónde se guardan las cosas
- **Descargas:** `Descargas/NactionX Downloader` por defecto. Se puede cambiar en la app.
- **Ajustes, cola, historial y registros:**
  - Windows: `%APPDATA%\NactionX Downloader`
  - macOS: `~/Library/Application Support/NactionX Downloader`

Al abrir la app por primera vez se importan automáticamente los ajustes y el historial del prototipo «Descargador».

## Actualizar
La app avisa sola cuando hay una versión nueva y el botón **Descargar** abre el archivo que le toca a tu sistema. Después:

- **Windows:** ejecuta el `Setup.exe` nuevo encima del anterior. No hace falta desinstalar nada; si la app está abierta, el instalador te ofrece cerrarla. Tus ajustes, la cola y el historial se conservan porque viven en `%APPDATA%`, fuera de la carpeta del programa.
- **macOS:** abre el `.dmg` y arrastra la app a *Aplicaciones*, sustituyendo la anterior. Los datos viven en `~/Library/Application Support`, así que no se tocan.

Si prefieres no recibir avisos, desactívalos en *Ajustes → Comportamiento*. El aviso solo consulta la versión publicada; no instala nada por su cuenta.

## Desarrollo
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-build.txt
python -m nactionx
```
En macOS, activa el entorno con `source .venv/bin/activate`.

Otros modos:
- `python -m nactionx --browser`: sirve la interfaz en el navegador (sin ventana nativa).
- `python -m nactionx --data-dir <carpeta>`: usa datos aislados para pruebas.
- `python -m pytest tests`: ejecuta los tests.

### Estructura
| Ruta | Contenido |
|---|---|
| `nactionx/engine.py` | Análisis y descarga con yt-dlp (formatos, recorte, ganchos de progreso) |
| `nactionx/manager.py` | Cola: planificación, reintentos, pausa, historial, migración |
| `nactionx/api.py` | API local con token para la interfaz |
| `nactionx/desktop.py` | Ventana nativa, instancia única, cierre ordenado |
| `nactionx/sites.py` | Plataformas: qué es cada enlace, perfiles frente a publicaciones, opciones por sitio |
| `nactionx/components.py` | FFmpeg, Deno y actualizador de yt-dlp |
| `nactionx/updates.py` | Aviso de versión nueva de la app |
| `nactionx/web/` | Interfaz (HTML, CSS, JS) |
| `packaging/` | Iconos, componentes, PyInstaller, instalador, DMG y publicación |

## Compilar
- **Windows:** `powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1`. Genera la carpeta portable, el ZIP y, si encuentra Inno Setup 6, el instalador. Usa Python 3.13 de 64 bits y trabaja en `%USERPROFILE%\.nactionx-dev`, fuera de OneDrive.
- **macOS**, en un Mac: abre Terminal, escribe `bash ` y arrastra el archivo **`Compilar en Mac.command`** que hay en la raíz del proyecto. Hace todo: entorno, componentes, tests, app, prueba automática y `.dmg`. Solo necesita Python 3.12 o superior instalado. (Equivalente manual: `bash packaging/build_macos.sh`.)
- **Los dos a la vez:** sube el proyecto a GitHub y lanza el flujo **Compilar NactionX Downloader** en *Actions*, o crea una etiqueta `v1.0.0`. El flujo genera el instalador de Windows y los DMG de Apple Silicon e Intel.

macOS no se puede compilar desde Windows. Por eso los DMG se generan en las máquinas Mac de GitHub Actions.

## Publicar una versión
El código está en un repositorio privado y los instaladores en uno público, `pymanu/nactionx-downloader-releases`, para que la app pueda comprobar si hay versión nueva sin llevar ninguna credencial dentro.

1. Sube la versión en `nactionx/__init__.py` y escribe su sección en `CHANGELOG.md`.
2. Lanza el flujo de *Actions* y deja los tres archivos (`Setup.exe` y los dos `.dmg`) en `releases/`.
3. `python packaging/publish_release.py` — comprueba que están los tres, toma las notas del `CHANGELOG` y publica. Con `--dry-run` solo comprueba.

A partir de ahí, las apps ya instaladas ven el aviso la próxima vez que se abran.

## Licencias
Consulta `THIRD_PARTY_NOTICES.md`. Uso personal: descarga solo contenido que tengas derecho a guardar y respeta los términos de cada plataforma.
