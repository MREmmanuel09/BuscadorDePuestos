"""Pruebas de escrituras atomicas, backups y lectura segura de almacen.py."""

import json
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

import almacen  # noqa: E402


class BasePrueba(unittest.TestCase):
    """Base con un directorio temporal por prueba."""

    def setUp(self):
        """Crea el directorio temporal de la prueba."""
        self.tmp = tempfile.mkdtemp(prefix="almacen_test_")

    def tearDown(self):
        """Borra el directorio temporal."""
        shutil.rmtree(self.tmp, ignore_errors=True)


class PruebaEscrituras(BasePrueba):
    """Pruebas de escritura atomica de texto, JSON y CSV."""

    def test_texto_atomico_no_deja_temporales(self):
        """El texto se escribe completo y no quedan archivos temporales."""
        ruta = os.path.join(self.tmp, "nota.txt")
        almacen.escribir_texto_atomico(ruta, "hola")
        with open(ruta, encoding="utf-8") as f:
            self.assertEqual(f.read(), "hola")
        self.assertEqual(os.listdir(self.tmp), ["nota.txt"])

    def test_json_atomico(self):
        """El JSON se puede leer de vuelta con acentos intactos."""
        ruta = os.path.join(self.tmp, "datos.json")
        almacen.escribir_json_atomico(ruta, {"nombre": "Jóse"})
        with open(ruta, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"nombre": "Jóse"})

    def test_csv_atomico(self):
        """El CSV usa punto y coma y conserva las columnas pedidas."""
        ruta = os.path.join(self.tmp, "ofertas.csv")
        almacen.escribir_csv_atomico(
            ruta,
            [{"titulo": "Soporte; TI", "url": "https://x.com/1"}],
            ["titulo", "url"],
        )
        with open(ruta, encoding="utf-8-sig", newline="") as f:
            contenido = f.read()
        self.assertIn("titulo;url", contenido)
        self.assertIn("Soporte; TI", contenido)

    def test_leer_json_corrupto_devuelve_defecto(self):
        """Un JSON invalido no rompe la carga y devuelve el defecto."""
        ruta = os.path.join(self.tmp, "roto.json")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write("{no es json")
        self.assertEqual(almacen.leer_json(ruta, {"ok": True}), {"ok": True})


class PruebaBackups(BasePrueba):
    """Pruebas de copias de seguridad y rotacion."""

    def test_copia_seguridad_rota(self):
        """Se conservan solo las copias mas recientes."""
        ruta = os.path.join(self.tmp, "ofertas.csv")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write("a")
        destino = os.path.join(self.tmp, "backups")
        for _ in range(3):
            almacen.copia_seguridad(ruta, destino, "ofertas", mantener=2)
        copias = os.listdir(destino)
        self.assertEqual(len(copias), 2)

    def test_rotar_log(self):
        """El log se rota y se conserva la version anterior."""
        ruta = os.path.join(self.tmp, "historial.log")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write("x" * 50)
        almacen.rotar_log(ruta, max_bytes=10, copias=2)
        self.assertFalse(os.path.exists(ruta))
        self.assertTrue(os.path.exists(ruta + ".1"))
        with open(ruta + ".1", encoding="utf-8") as f:
            self.assertEqual(f.read(), "x" * 50)


if __name__ == "__main__":
    unittest.main()
