# Cambios

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
