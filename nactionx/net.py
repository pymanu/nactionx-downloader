"""Peticiones HTTPS que hace la propia app (GitHub, PyPI).

macOS no le da a Python un almacén de certificados utilizable: la app empaquetada busca el archivo de
CA en la ruta que OpenSSL trae compilada, que existe en la máquina donde se compiló pero no en el Mac
del usuario. Resultado: todas las peticiones fallan con CERTIFICATE_VERIFY_FAILED aunque las descargas
funcionen, porque yt-dlp resuelve esto por su cuenta.

Por eso el contexto TLS se construye aquí cargando explícitamente un paquete de certificados, y
**todo lo que hable por HTTPS desde la app pasa por este módulo**. No uses urllib directamente.
"""
import os
import ssl
import urllib.request

from . import log

logger = log.get('net')

# Almacenes del sistema que sí existen en un Mac, por si el paquete de certificados no viajara dentro.
SYSTEM_BUNDLES = ('/etc/ssl/cert.pem', '/private/etc/ssl/cert.pem', '/usr/local/etc/openssl/cert.pem')

_context = None
_source = ''


def _load(context):
    """Carga un paquete de certificados y devuelve de dónde salió, para poder diagnosticarlo."""
    try:
        import certifi
        path = certifi.where()
        if path and os.path.isfile(path):
            context.load_verify_locations(path)
            return 'certifi'
    except Exception as e:
        logger.debug('certifi no disponible: %s', e)
    for path in SYSTEM_BUNDLES:
        if os.path.isfile(path):
            try:
                context.load_verify_locations(path)
                return path
            except Exception as e:
                logger.debug('No se pudo cargar %s: %s', path, e)
    return 'sistema' if context.cert_store_stats().get('x509_ca') else ''


def context():
    global _context, _source
    if _context is None:
        ctx = ssl.create_default_context()
        _source = _load(ctx)
        _context = ctx
        logger.info('Certificados HTTPS: %s', _source or 'ninguno encontrado')
    return _context


def source():
    """De dónde salen los certificados, o cadena vacía si no hay ninguno."""
    context()
    return _source


def urlopen(request, timeout=30):
    return urllib.request.urlopen(request, timeout=timeout, context=context())
