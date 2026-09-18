import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# Nunca tocar los datos reales del usuario durante los tests
os.environ['NACTIONX_DATA_DIR'] = tempfile.mkdtemp(prefix='nactionx-tests-')
