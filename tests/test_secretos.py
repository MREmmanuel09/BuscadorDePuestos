"""Pruebas del cifrado DPAPI de secretos (solo Windows)."""

import os
import sys
import unittest

RUTA_BUSCADOR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "buscador"
)
if RUTA_BUSCADOR not in sys.path:
    sys.path.insert(0, RUTA_BUSCADOR)

import secretos  # noqa: E402


@unittest.skipUnless(sys.platform == "win32", "DPAPI solo existe en Windows")
class PruebaDpapi(unittest.TestCase):
    """Round-trip de cifrado y descifrado con DPAPI."""

    def test_round_trip(self):
        """La clave se descifra exactamente como se cifro."""
        cifrada = secretos.cifrar("clave-de-prueba")
        self.assertTrue(cifrada)
        self.assertEqual(secretos.descifrar(cifrada), "clave-de-prueba")

    def test_texto_invalido_devuelve_vacio(self):
        """Un valor corrupto no lanza y devuelve cadena vacia."""
        self.assertEqual(secretos.descifrar("no-es-base64"), "")


@unittest.skipIf(sys.platform == "win32", "La prueba aplica fuera de Windows")
class PruebaSinDpapi(unittest.TestCase):
    """En plataformas sin DPAPI el modulo degrada sin errores."""

    def test_no_disponible(self):
        """cifrar devuelve vacio cuando DPAPI no esta disponible."""
        self.assertFalse(secretos.disponible())
        self.assertEqual(secretos.cifrar("x"), "")
        self.assertEqual(secretos.descifrar("x"), "")


if __name__ == "__main__":
    unittest.main()
