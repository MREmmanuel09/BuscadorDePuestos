"""Pruebas del bloqueo de proceso y su reentrada."""

import os
import shutil
import sys
import tempfile
import unittest

RUTA_BUSCADOR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "buscador"
)
if RUTA_BUSCADOR not in sys.path:
    sys.path.insert(0, RUTA_BUSCADOR)

import bloqueo  # noqa: E402


class PruebaBloqueo(unittest.TestCase):
    """Casos del context manager proceso()."""

    def setUp(self):
        """Crea un directorio temporal para el archivo de bloqueo."""
        self.tmp = tempfile.mkdtemp(prefix="bloqueo_test_")

    def tearDown(self):
        """Borra el directorio temporal."""
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_crea_archivo_y_permite_reentrada(self):
        """Dos bloques anidados en el mismo hilo no se bloquean entre si."""
        with bloqueo.proceso(self.tmp, "prueba", timeout=1):
            with bloqueo.proceso(self.tmp, "prueba", timeout=1):
                pass
        self.assertTrue(os.path.exists(os.path.join(self.tmp, ".prueba.lock")))

    def test_se_puede_repetir(self):
        """El bloqueo se libera al salir y se puede volver a adquirir."""
        with bloqueo.proceso(self.tmp, "prueba", timeout=1):
            pass
        with bloqueo.proceso(self.tmp, "prueba", timeout=1):
            pass


if __name__ == "__main__":
    unittest.main()
