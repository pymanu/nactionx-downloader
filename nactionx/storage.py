"""Lectura y escritura atómica de JSON, tolerante a bloqueos temporales (antivirus, sincronización)."""
import json
import os
import time

from . import log

logger = log.get('storage')


def read_json(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as e:
        logger.warning('No se pudo leer %s: %s', path, e)
        return default


def write_json(path, data, attempts=6):
    path = str(path)
    tmp = f'{path}.{os.getpid()}.tmp'
    payload = json.dumps(data, ensure_ascii=False, indent=1)
    for i in range(attempts):
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write(payload)
            os.replace(tmp, path)
            return True
        except OSError as e:
            if i == attempts - 1:
                logger.error('No se pudo guardar %s: %s', path, e)
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                return False
            time.sleep(0.05 * (2 ** i))
    return False
