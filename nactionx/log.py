"""Registro de la app con rotación (evita logs que crecen sin límite)."""
import io
import logging
import logging.handlers
import sys

from . import paths


class _LogWriter(io.TextIOBase):
    """Sustituye stdout/stderr cuando no hay consola (app de ventana empaquetada)."""

    def __init__(self, logger, level):
        self.logger, self.level = logger, level

    def write(self, text):
        text = str(text).rstrip()
        if text:
            self.logger.log(self.level, text)
        return len(text)

    def flush(self):
        pass


def setup(debug=False):
    root = logging.getLogger('nactionx')
    if root.handlers:
        return root
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    handler = logging.handlers.RotatingFileHandler(
        paths.sub_dir('logs') / 'nactionx.log', maxBytes=2 * 1024 * 1024, backupCount=3, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)-7s [%(threadName)s] %(name)s: %(message)s'))
    root.addHandler(handler)
    if sys.stderr is not None and sys.stdout is not None:
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter('%(levelname)s %(name)s: %(message)s'))
        root.addHandler(console)
    else:
        sys.stdout = _LogWriter(logging.getLogger('nactionx.stdout'), logging.INFO)
        sys.stderr = _LogWriter(logging.getLogger('nactionx.stderr'), logging.WARNING)
    return root


def get(name):
    return logging.getLogger(f'nactionx.{name}')
