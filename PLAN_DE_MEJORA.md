# NactionX Downloader — Auditoría y plan de mejora

**Punto de partida:** prototipo «Descargador» (`server.py` 1.066 líneas + `index.html` 1.250 líneas).
**Uso real analizado:** 11 descargas completadas, 5,27 GB, 0 errores, 4 descargas simultáneas.
**Objetivo:** cerrar la **versión 1.0** y distribuirla como app de escritorio para **Windows y macOS**.

Leyenda de estado: ⬜ pendiente · ✅ hecho · ➡️ movido a v1.1

---

## 1. Cómo se hizo la auditoría

- Revisión completa del backend (motor, cola, API, persistencia) y del frontend (estado, render, eventos).
- Pruebas dirigidas con evidencia:
  - Ordenación de formatos con datos sintéticos y con los 6 primeros vídeos reales de la cola.
  - Combinaciones contenedor/códec descargando un vídeo real.
  - Mensajes de error reales de yt-dlp.
  - Tamaño de la respuesta de la API con la cola real.
  - Revisión del log del servidor y de la carpeta de destino (restos temporales, sincronización).
- Viabilidad de escritorio probada en este equipo: pywebview 6.2 + pythonnet + PyInstaller 6.22 con Python 3.13. También se comprobó que yt-dlp y yt-dlp-ejs cargan desde los paquetes oficiales de PyPI (54 formatos, hasta 2160p).

---

## 2. Hallazgos

### 🔴 Críticos: resultados incorrectos o fallos

| ID | Problema | Evidencia | Solución | Estado |
|---|---|---|---|---|
| A01 | **«Máxima» calidad no garantiza la máxima resolución** si se elige MP4 o WEBM: la preferencia de extensión va antes que la resolución. | Prueba sintética: un 1080p MP4 gana a un 2160p WEBM (`server.py:587`). En tus vídeos no afectó porque su máximo era 1080p. | Orden `res → fps → códec → extensión`. | ✅ |
| A02 | **WEBM + H.264 falla** («Conversion failed!») y la interfaz permite elegirlo. | Descarga real fallida en la prueba. | Validar combinaciones en backend y deshabilitarlas en la interfaz. | ✅ |
| A03 | **No funciona en macOS**: `creationflags` (error fuera de Windows), `os.startfile`, `explorer /select`, rutas de Chrome/Edge, `pythonw`. El selector de carpeta vía `sys.executable -c` tampoco funciona empaquetado. | `server.py:350, 868, 895, 997, 1001, 1042, 1054`. | Capa de plataforma (Windows/macOS/Linux) y diálogos nativos. | ✅ |
| A04 | Si la API de estado falla al serializar devuelve `{}`. La interfaz vacía la cola y rompe los ajustes. | `server.py:857`. | Serialización segura, nunca respuesta vacía, validación en el cliente. | ✅ |
| A05 | **Ajustes sin validar**: un valor no numérico en «simultáneas» hace fallar el planificador cada 0,3 s. La cola deja de arrancar y el log crece sin fin. | `server.py:431, 987`. | Esquema de validación (tipos, rangos, listas cerradas). | ✅ |
| A06 | **Puerto fijo 8765**: si otro programa lo usa, la app no arranca y no avisa. | `server.py:26`. | Puerto dinámico + archivo de instancia única. | ✅ |
| A07 | La actualización de yt-dlp usa `pip`: no sirve en una app empaquetada y exige reinicio manual. | `server.py:864`. | Actualizador propio desde PyPI con verificación SHA-256 y reinicio desde la app. | ✅ |

### 🟠 Importantes

| ID | Problema | Solución | Estado |
|---|---|---|---|
| B01 | Errores crudos en inglés («This video is unavailable», «Sign in to confirm you're not a bot»). | Mensajes en español que dicen qué hacer, con el detalle técnico desplegable. | ✅ |
| B02 | Advertencias de yt-dlp silenciadas (`no_warnings`, `warning()` vacío): se pierden avisos que indican que hay que actualizar. | Registro por descarga + visor «Ver registro». | ✅ |
| B03 | Rendimiento: la cola completa (≈1,3 KB por descarga) se envía cada 0,6 s. Con 500 vídeos son ≈640 KB cada 0,6 s. | Revisiones incrementales: la estructura solo cuando cambia; el progreso, solo de las activas. | ✅ |
| B04 | Datos de la app (cola, historial, log) dentro de OneDrive: reescrituras frecuentes, sincronización continua y bloqueos. | `%APPDATA%` / `~/Library/Application Support`, con migración automática de tus datos. | ✅ |
| B05 | Destino en OneDrive (`TEAMEMUDO`: 5,27 GB subidos a la nube). OneDrive puede bloquear archivos `.part`. | Aviso visible de carpeta sincronizada y de espacio libre. | ✅ |
| B06 | Log sin rotación y con trazas completas. | Log rotativo (2 MB × 3). | ✅ |
| B07 | Cerrar con descargas activas (`os._exit`) puede dejar ffmpeg huérfano bloqueando archivos. | Cierre ordenado: pausar, esperar y terminar procesos hijos. | ✅ |
| B08 | «Pausar todo» no sobrevive a un reinicio: la cola arranca sola. | Persistir el estado de pausa global. | ✅ |
| B09 | «Reanudar todo» también reanuda lo que pausaste a mano. | Distinguir pausa manual y global. | ✅ |
| B10 | Una notificación por archivo: una playlist de 200 vídeos daría 200 avisos. | Aviso resumen al vaciarse la cola; notificaciones nativas del sistema. | ✅ |
| B11 | Las cookies de Chrome/Edge en Windows no funcionan (cifrado de Chrome desde la v127). La opción engaña. | Avisarlo, recomendar Firefox y permitir importar `cookies.txt`. | ✅ |
| B12 | Portapapeles vía `navigator.clipboard` (pide permiso, no funciona en ventana nativa). | Lectura nativa del portapapeles desde la app. | ✅ |
| B13 | Diálogos `confirm()` del navegador. | Diálogos propios con el diseño de la app. | ✅ |
| B14 | Plantilla de nombre sin validar: una plantilla rota hace fallar todas las descargas. | Validar con yt-dlp al guardar. | ✅ |
| B15 | Sin comprobar permisos ni espacio libre del destino. | Comprobación antes de empezar, con mensaje claro. | ✅ |
| B16 | Si falta ffmpeg o el motor JavaScript, la calidad baja o falla sin aviso. | Diagnóstico de componentes; en escritorio van incluidos. | ✅ |
| B17 | Directos en curso y estrenos: descarga infinita o error confuso. | Detectarlos y avisar (grabación de directos en v1.1). | ✅ |
| B18 | Un corte de red deja la descarga en error hasta que reintentas a mano. | Reintento automático con espera (15 s, 45 s, 2 min) para errores de red o límite de peticiones. | ✅ |

### 🟡 Mejoras

| ID | Problema | Solución | Estado |
|---|---|---|---|
| C01 | Vídeos verticales (Shorts) muestran «1920p». | Usar la dimensión menor (1080p). | ✅ |
| C02 | 59,94 fps aparece como «1080p59». | Redondear (1080p60). | ✅ |
| C03 | Miniaturas de playlists de otras webs construidas con URL de YouTube. | Usar la miniatura real de cada web. | ✅ |
| C04 | El historial crece sin límite en memoria. | Límite de 1.000 entradas. | ✅ |
| C05 | Canales: solo la pestaña «Vídeos» (sin Shorts ni Directos). | Selector de pestaña. | ➡️ v1.1 |
| C06 | Desde una búsqueda, «Detalles» pierde los resultados. | Botón «Volver a los resultados». | ✅ |
| C07 | No se pueden cambiar las opciones de una descarga ya en cola. | Editar opciones en cola. | ➡️ v1.1 |
| C08 | Añadir el mismo enlace dos veces no avisa. | Detección de duplicados en cola. | ✅ |
| C09 | El límite de velocidad es por descarga (4 simultáneas = 4×). | Límite global repartido. | ➡️ v1.1 |
| C10 | Accesibilidad: texto secundario con contraste 3,1:1 (mínimo 4,5:1); botones de icono sin `aria-label`. | Contraste ≥4,5:1, etiquetas y foco visible. | ✅ |
| C11 | Sin tema claro. | Seguir el tema del sistema. | ➡️ v1.1 |
| C12 | Tamaño estimado de FLAC/WAV muy por debajo del real. | Estimación por formato. | ✅ |
| C13 | Cancelar durante el procesado puede dejar un archivo final a medias. | Borrar la salida creada en esa descarga. | ✅ |
| C14 | Sin «omitir vídeos ya descargados» para sincronizar canales. | Archivo de descargas de yt-dlp. | ➡️ v1.1 |
| C15 | Sin proxy. | Ajuste de proxy. | ✅ |
| C16 | Solo en español. | Inglés. | ➡️ v1.1 |
| C17 | Sin versión visible, «Acerca de» ni avisos de licencias. | Versión, «Acerca de» y licencias de terceros. | ✅ |

### ⚪ Calidad de código

| ID | Problema | Solución | Estado |
|---|---|---|---|
| D01 | Dos archivos monolíticos con todo mezclado. | Paquete `nactionx/` por módulos y frontend separado (HTML/CSS/JS). | ✅ |
| D02 | Sin tests. | Tests automáticos del núcleo (formatos, nombres, ajustes, errores, cola, API). | ✅ |
| D03 | API local sin token (solo cabecera y Host). | Token aleatorio por sesión. | ✅ |
| D04 | Planificador que sondea cada 0,3 s. | Planificador por eventos. | ✅ |
| D05 | Licencias: FFmpeg y mutagen son GPL al redistribuir. | Avisos de terceros incluidos. Para uso personal no hay obligación adicional. | ✅ |

---

## 3. Plan de ejecución

### Fase 1: cerrar la v1.0
Todo lo marcado como v1.0 en las tablas. Los críticos van primero, luego los importantes y después las mejoras.

### Fase 2: app de escritorio «NactionX Downloader»

**Arquitectura (una sola base de código para los dos sistemas)**
- Motor: yt-dlp + yt-dlp-ejs en Python, con cola persistente y API local con token en un puerto dinámico.
- Interfaz: la interfaz web actual dentro de una **ventana nativa** (pywebview: WebView2 en Windows, WKWebView en macOS). Sin navegador ni pestañas.
- Componentes incluidos: **FFmpeg + FFprobe** y **Deno**, el motor JavaScript que YouTube exige para obtener todas las calidades.
- Actualizador del motor integrado: descarga la última versión de yt-dlp desde PyPI, verifica el SHA-256 y reinicia. Si la versión nueva no arranca, vuelve sola a la incluida.
- **Instancia única**: abrir la app otra vez trae la ventana al frente.
- Al cerrar con descargas activas pide confirmación; al reabrir, continúan donde se quedaron.
- Notificaciones nativas, «Mostrar en carpeta» nativo y diálogo de carpeta nativo en ambos sistemas.
- Datos en `%APPDATA%\NactionX Downloader` o `~/Library/Application Support/NactionX Downloader`, con **migración automática** de ajustes, cola e historial del prototipo.

**Empaquetado**
- **Windows:** PyInstaller + instalador Inno Setup por usuario (sin permisos de administrador), con accesos directos en el escritorio y el menú Inicio.
- **macOS:** `.app` dentro de `.dmg`, en dos versiones (Apple Silicon e Intel). macOS no se puede compilar desde Windows, así que se genera con GitHub Actions en máquinas Mac. Necesita un repositorio en GitHub.
- **Firma:** sin certificados, Windows SmartScreen y macOS Gatekeeper mostrarán un aviso la primera vez. Se documenta cómo abrirla. Firmar es opcional: Apple Developer cuesta 99 USD/año y el certificado de Windows se paga aparte.

### Fase 3: verificación
- Tests automáticos en local y en CI.
- Prueba completa del ejecutable de Windows: arranque, análisis, cola, pausa/reanudar, cancelar, renombrar, recorte, actualización y cierre con descargas activas.
- macOS: build en CI y checklist de prueba manual.

---

## 4. Resultado de la fase 2: empaquetado de escritorio

### Hallazgos durante el empaquetado (todos corregidos y verificados)

| ID | Problema | Solución | Estado |
|---|---|---|---|
| E01 | **Smart App Control** (activo en este PC) bloquea cualquier `.exe` sin firma de pago: bloqueó el ejecutable de PyInstaller y las DLL de FFmpeg de la compilación diaria de yt-dlp. | En Windows, la app corre sobre el **Python oficial firmado** (Python Software Foundation) con FFmpeg 8.1.1 de Gyan y Deno firmado. Se comprobó que las tres piezas pasan el filtro. | ✅ |
| E02 | La ventana de Windows se cerraba al arrancar: WinForms no acepta un icono PNG (`System.Drawing.Icon`). | Icono `.ico` en Windows. | ✅ |
| E03 | Con una carpeta de destino larga, el nombre se truncaba y se perdía el sufijo «(recorte …)» que evita sobrescribir el vídeo completo: el límite de 150/180 caracteres se aplicaba a la ruta entera. | Carpeta en `paths` y plantilla aparte; test con ruta larga. | ✅ |
| E04 | El actualizador del motor fallaba: no creaba la carpeta de paquetes. | Carpeta creada antes de descargar; tests con paquete manipulado (se rechaza). | ✅ |
| E05 | PyInstaller duplicaba las DLL de FFmpeg (494 MB → 313 MB). | Filtro de duplicados en la especificación. | ✅ |
| E06 | Inno Setup se quedaba sin memoria con la compresión `ultra64`. | Compresión `max` en proceso separado. | ✅ |

### Entregables

| Plataforma | Archivo | Estado |
|---|---|---|
| Windows 10/11 x64 | `releases/NactionX-Downloader-1.0.0-Windows-x64-Setup.exe` (99 MB, instalación por usuario sin administrador) | ✅ Compilado y probado: instalar, arrancar y desinstalar |
| Windows 10/11 x64 | `releases/NactionX-Downloader-1.0.0-Windows-x64-Portable.zip` (138 MB) | ✅ Compilado y probado de extremo a extremo |
| macOS Apple Silicon e Intel | `.dmg` generados por `.github/workflows/build.yml` | ⬜ Preparado; necesita un repositorio en GitHub para compilarse en máquinas Mac |

### Pruebas del ejecutable de Windows
- Arranque en 1,7 s con FFmpeg, FFprobe, Deno, yt-dlp y yt-dlp-ejs incluidos y sin avisos.
- Descarga real de vídeo con nombre propio, MP3 recortado (6,0 s exactos) y recorte de 4K con «Máxima» = 2160p60 (3,0 s exactos).
- Instancia única, cierre ordenado con la cola guardada, y actualización del motor cargada desde el paquete actualizado.
- 49 tests automáticos.

### Limitaciones conocidas
- **Firma de código:** sin certificado, Windows SmartScreen avisará en otros PCs al ejecutar el instalador, y macOS pedirá «Abrir igualmente». Firmar (certificado de Windows o Apple Developer, 99 USD/año) elimina los avisos.
- **macOS no se ha probado en un Mac real.** El código es multiplataforma y está revisado, pero la verificación final llegará con el build de CI.
- **Recortar descarga el vídeo entero y luego corta.** Con calidad máxima puede tardar en vídeos largos (a cambio, el corte es exacto y se puede cancelar).

---

## 5. Hoja de ruta posterior (v1.1+)
Selector de pestañas de canal, editar opciones en cola, límite de velocidad global, tema claro, omitir ya descargados, inglés, grabación de directos, icono en la bandeja del sistema, programador de descargas, extensión de navegador «Enviar a NactionX», descargas en procesos aislados y autoactualización completa de la app.
