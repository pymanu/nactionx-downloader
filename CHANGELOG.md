# Cambios

## 1.2.0 — elegir la pista de audio

### Novedades
- **Selector de pista de audio.** En los vídeos con varios idiomas (habitual en YouTube), la vista previa muestra un desplegable «Pista de audio» con todas las disponibles, la original marcada y primera. Vale tanto para vídeo como para «solo audio», y se puede combinar con el recorte.
- El idioma elegido aparece en la etiqueta de la descarga (`MP4 · 1080p · H.264 · Español`) y en el nombre del archivo, para poder distinguir el mismo vídeo en dos idiomas.
- En los vídeos con una sola pista no aparece nada: la interfaz no cambia.

### Correcciones
- El mismo vídeo en dos idiomas distintos se descartaba como repetido y solo se descargaba el primero: la detección de duplicados no miraba la pista de audio.
- Si el vídeo no tiene la pista pedida, se usa la de siempre en lugar de fallar, y la etiqueta dice cuál se usó de verdad.

## 1.1.0 — Instagram, TikTok y aviso de versión

### Novedades
- **Instagram y TikTok**: pega el enlace de un reel, un post o un vídeo y se descarga como cualquier otro, con las mismas opciones (calidad, audio, recorte, nombre propio).
- **Aviso de versión nueva**: la app comprueba si hay una versión más reciente y lo dice, en Windows y en macOS. El botón «Descargar» abre directamente el instalador que corresponde a tu sistema. Se puede desactivar en *Ajustes → Comportamiento*.

### Correcciones
- TikTok no se podía ni analizar: devolvía una página de verificación en lugar del vídeo. Ahora se pide con una cabecera de navegador normal.
- Instagram y TikTok sirven el vídeo y el audio en un único archivo; se les pide así en vez de buscar pistas separadas que no existen.
- Los enlaces compartidos desde las apps de Instagram y TikTok llevan identificadores de sesión que colaban duplicados en la cola: ahora se limpian.
- Pegar el perfil en lugar de la publicación explica qué hacer, en vez de mostrar «please report this issue on GitHub».
- Instagram sin sesión iniciada indica cómo configurar las cookies.
- La compilación de Windows en GitHub Actions fallaba al comprobar la firma del Python oficial; además el paquete de origen se verifica ahora también por SHA-256.

## 1.0.0 — primera versión de escritorio

Nace **NactionX Downloader** a partir del prototipo «Descargador». El detalle está en `PLAN_DE_MEJORA.md`.

### Correcciones importantes
- «Máxima» calidad elige de verdad la resolución más alta: antes, con MP4, un 1080p podía ganar a un 4K en WEBM.
- WEBM con H.264 ya no falla: se usa VP9 y la opción incompatible se desactiva.
- Ajustes, plantillas de nombre y recortes se validan: un valor erróneo ya no rompe la cola.
- Puerto dinámico, token por sesión e instancia única.
- Un error de serialización ya no vacía la cola en pantalla.

- Con una carpeta de destino larga, el nombre del archivo ya no se trunca ni pierde el sufijo del recorte.
- El actualizador del motor ya no falla por no tener creada su carpeta.

### Empaquetado
- Windows: distribución sobre el Python oficial firmado, compatible con Smart App Control. Incluye instalador por usuario y ZIP portable.
- macOS: `.app` y `.dmg` para Apple Silicon e Intel, generados en GitHub Actions.

### Novedades
- App de escritorio con ventana nativa para Windows y macOS, con FFmpeg y Deno incluidos.
- Actualizador del motor yt-dlp integrado, con verificación SHA-256 y vuelta automática a la versión incluida si falla.
- Reintento automático ante cortes de red o límites de YouTube (15 s, 45 s, 2 min).
- Mensajes de error en español con detalle técnico y visor de registro por descarga.
- «Pausar todo» persiste tras reiniciar; «Reanudar todo» respeta las pausas manuales.
- Aviso único al terminar la cola (notificación nativa) en lugar de uno por archivo.
- Detección de duplicados, de directos y de carpetas sincronizadas con la nube; espacio libre visible.
- Comprobación de permisos y de espacio libre antes de descargar.
- Archivo de cookies (cookies.txt) y proxy.
- Búsqueda con «Volver a los resultados».
- Diálogos propios, mejor contraste y etiquetas de accesibilidad.
- Cierre ordenado: pausa las descargas, cierra procesos de FFmpeg y la cola continúa al volver.
- Migración automática de ajustes, cola e historial del prototipo.
- Datos de la app fuera de OneDrive (`%APPDATA%` / `~/Library/Application Support`).
- Registro rotativo, 46 tests automáticos y compilación para Windows y macOS con GitHub Actions.
