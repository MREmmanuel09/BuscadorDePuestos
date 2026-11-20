"""Pruebas unitarias para el módulo almacen.py (escrituras atómicas, CSV,
lectura defensiva, backups y rotación de log).

Cada prueba trabaja en su propio directorio temporal: nunca se toca el
data/ real del buscador.
"""

import json
import os
import shutil
import sys
import tempfile
import time
import unittest

RUTA_BUSCADOR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "buscador"
)
if RUTA_BUSCADOR not in sys.path:
    sys.path.insert(0, RUTA_BUSCADOR)

from almacen import (
    CSV_COLUMNS,
    asegurar_directorio,
    _temporal,
    escribir_texto_atomico,
    escribir_json_atomico,
    escribir_csv_atomico,
    leer_json,
    leer_csv,
    copia_seguridad,
    rotar_log,
    validacion_esquema_csv,
)


class TestAlmacen(unittest.TestCase):
    """Pruebas de escritura/lectura en un directorio temporal aislado."""

    def setUp(self):
        """Crea un directorio temporal por prueba."""
        self.test_dir = tempfile.mkdtemp(prefix="almacen_test_")

    def tearDown(self):
        """Elimina el directorio temporal."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def ruta(self, nombre):
        """Ruta completa dentro del directorio temporal."""
        return os.path.join(self.test_dir, nombre)

    def temporales(self):
        """Archivos temporales que quedaron sin consumir."""
        return [n for n in os.listdir(self.test_dir) if n.endswith(".tmp")]

    # ----------------------------------------------------------
    # Directorios y rutas temporales
    # ----------------------------------------------------------
    def test_asegurar_directorio(self):
        """asegurar_directorio crea los directorios si no existen."""
        subdirectorio = os.path.join(self.test_dir, "a", "b")
        asegurar_directorio(subdirectorio)

        self.assertTrue(os.path.isdir(subdirectorio))
        # Llamado dos veces no falla (exist_ok)
        asegurar_directorio(subdirectorio)

    def test_temporal(self):
        """_temporal devuelve un archivo .tmp en la carpeta del destino."""
        for nombre in ("prueba.txt", "datos.json", "ofertas.csv"):
            with self.subTest(nombre=nombre):
                ruta = self.ruta(nombre)
                temporal = _temporal(ruta)

                self.assertTrue(temporal.endswith(".tmp"))
                self.assertTrue(temporal.startswith(self.test_dir))
                self.assertNotEqual(temporal, ruta)

    # ----------------------------------------------------------
    # Escritura atómica de texto y JSON
    # ----------------------------------------------------------
    def test_escribir_texto_atomico(self):
        """escribir_texto_atomico guarda el texto exacto sin temporales huérfanos."""
        ruta = self.ruta("prueba.txt")
        texto = "Hola Mundo\nPrueba de atomicidad"

        escribir_texto_atomico(ruta, texto)

        with open(ruta, encoding="utf-8") as f:
            self.assertEqual(f.read(), texto)
        self.assertEqual(self.temporales(), [])

    def test_escribir_texto_atomico_sobreescribe(self):
        """Una segunda escritura reemplaza el contenido completo."""
        ruta = self.ruta("prueba.txt")
        escribir_texto_atomico(ruta, "version 1")
        escribir_texto_atomico(ruta, "version 2")

        with open(ruta, encoding="utf-8") as f:
            self.assertEqual(f.read(), "version 2")

    def test_escribir_json_atomico(self):
        """escribir_json_atomico serializa y deja el JSON legible."""
        ruta = self.ruta("prueba.json")
        datos = {"clave": "valor", "listas": [1, 2, 3]}

        escribir_json_atomico(ruta, datos)

        with open(ruta, encoding="utf-8") as f:
            self.assertEqual(json.load(f), datos)
        self.assertEqual(self.temporales(), [])

    def test_escribir_json_no_serializable(self):
        """Un objeto no serializable produce un error claro, no archivo a medias."""
        ruta = self.ruta("malo.json")

        with self.assertRaises(RuntimeError):
            escribir_json_atomico(ruta, {"fecha": object()})

        self.assertFalse(os.path.exists(ruta))

    # ----------------------------------------------------------
    # Lectura defensiva
    # ----------------------------------------------------------
    def test_leer_json_faltante(self):
        """Un archivo que no existe devuelve el valor por defecto."""
        resultado = leer_json(self.ruta("no_existe.json"), {"k": 1})

        self.assertEqual(resultado, {"k": 1})

    def test_leer_json_corrupto(self):
        """Un JSON corrupto devuelve el valor por defecto, sin excepción."""
        ruta = self.ruta("corrupto.json")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write("NOT JSON {")

        resultado = leer_json(ruta, {"k": 2})

        self.assertEqual(resultado, {"k": 2})

    def test_leer_json_devuelve_copia(self):
        """El defecto devuelto es una copia: mutarlo no afecta al original."""
        defecto = {"k": 1}
        ruta = self.ruta("no_existe.json")

        resultado = leer_json(ruta, defecto)
        resultado["k"] = 99

        self.assertEqual(defecto["k"], 1)

    def test_leer_json_conserva_listas(self):
        """Un JSON válido que sea lista se devuelve tal cual."""
        ruta = self.ruta("lista.json")
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(["a", "b"], f)

        self.assertEqual(leer_json(ruta, []), ["a", "b"])

    # ----------------------------------------------------------
    # CSV con validación de esquema
    # ----------------------------------------------------------
    def _fila_completa(self, **cambios):
        fila = {c: f"valor_{c}" for c in CSV_COLUMNS}
        fila.update(cambios)
        return fila

    def test_validacion_esquema_csv_ok(self):
        """Una fila completa no genera errores."""
        borradas, errores = validacion_esquema_csv([self._fila_completa()])

        self.assertEqual(borradas, 0)
        self.assertEqual(errores, [])

    def test_validacion_esquema_csv_faltantes(self):
        """Una fila incompleta se cuenta y explica qué campos faltan."""
        fila = {"titulo": "Soporte TI", "url": "https://x"}
        borradas, errores = validacion_esquema_csv([fila])

        self.assertEqual(borradas, 1)
        self.assertEqual(len(errores), 1)
        self.assertIn("ubicacion", errores[0])

    def test_escribir_csv_atomico(self):
        """El CSV se escribe con encabezado y separador del buscador."""
        ruta = self.ruta("ofertas.csv")
        filas = [self._fila_completa(titulo="Soporte TI"), self._fila_completa(titulo="Redes")]

        escribir_csv_atomico(ruta, filas)

        with open(ruta, encoding="utf-8-sig", newline="") as f:
            contenido = f.read()
        self.assertTrue(contenido.startswith("fecha;fuente;titulo;"))
        self.assertIn("Soporte TI", contenido)
        self.assertEqual(self.temporales(), [])

    def test_escribir_csv_atomico_rechaza_esquema_malo(self):
        """Una fila sin columnas obligatorias cancela la escritura."""
        ruta = self.ruta("ofertas.csv")

        with self.assertRaises(ValueError):
            escribir_csv_atomico(ruta, [{"titulo": "incompleta"}])

        self.assertFalse(os.path.exists(ruta))

    def test_leer_csv(self):
        """leer_csv devuelve las filas escritas y [] si el archivo falta."""
        ruta = self.ruta("ofertas.csv")
        filas = [self._fila_completa(titulo="Soporte TI")]
        escribir_csv_atomico(ruta, filas)

        leidas = leer_csv(ruta)

        self.assertEqual(len(leidas), 1)
        self.assertEqual(leidas[0]["titulo"], "Soporte TI")
        self.assertEqual(leer_csv(self.ruta("falta.csv")), [])

    # ----------------------------------------------------------
    # Copias de seguridad y rotación
    # ----------------------------------------------------------
    def test_copia_seguridad(self):
        """copia_seguridad crea un backup con marca de tiempo."""
        fuente = self.ruta("original.txt")
        with open(fuente, "w", encoding="utf-8") as f:
            f.write("contenido")
        backup_dir = os.path.join(self.test_dir, "backups")

        destino = copia_seguridad(fuente, backup_dir, prefijo="original", mantener=10)

        self.assertIsNotNone(destino)
        self.assertTrue(os.path.exists(destino))
        self.assertTrue(os.path.basename(destino).startswith("original-"))

    def test_copia_seguridad_no_sobrescribe(self):
        """Dos copias seguidas generan archivos distintos, aunque sea el mismo segundo."""
        fuente = self.ruta("original.txt")
        with open(fuente, "w", encoding="utf-8") as f:
            f.write("contenido")
        backup_dir = os.path.join(self.test_dir, "backups")

        primera = copia_seguridad(fuente, backup_dir, prefijo="original", mantener=10)
        segunda = copia_seguridad(fuente, backup_dir, prefijo="original", mantener=10)

        self.assertNotEqual(primera, segunda)
        self.assertEqual(len(os.listdir(backup_dir)), 2)

    def test_copia_seguridad_rota_viejas(self):
        """Solo se conservan las 'mantener' copias más recientes."""
        fuente = self.ruta("original.txt")
        with open(fuente, "w", encoding="utf-8") as f:
            f.write("contenido")
        backup_dir = os.path.join(self.test_dir, "backups")
        os.makedirs(backup_dir)

        # 5 copias antiguas con marcas de tiempo distintas
        ahora = time.time()
        for i in range(5):
            vieja = os.path.join(backup_dir, f"original-2020010{i}-000000.txt")
            with open(vieja, "w", encoding="utf-8") as f:
                f.write("vieja")
            os.utime(vieja, (ahora - (5 - i) * 60, ahora - (5 - i) * 60))

        copia_seguridad(fuente, backup_dir, prefijo="original", mantener=3)

        copias = [n for n in os.listdir(backup_dir) if n.startswith("original-")]
        self.assertEqual(len(copias), 3)

    def test_copia_seguridad_fuente_inexistente(self):
        """Una fuente que no existe devuelve None sin crear nada."""
        backup_dir = os.path.join(self.test_dir, "backups")

        self.assertIsNone(copia_seguridad(self.ruta("no_existe.txt"), backup_dir))
        self.assertFalse(os.path.exists(backup_dir))

    def test_rotar_log(self):
        """rotar_log mueve el log a log.1 cuando supera el máximo."""
        ruta = self.ruta("historial.log")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write("a" * 600_000)  # 600 KB

        rotar_log(ruta, max_bytes=500_000)

        self.assertTrue(os.path.exists(ruta + ".1"))
        self.assertFalse(os.path.exists(ruta))

    def test_rotar_log_pequeno_no_rota(self):
        """Un log por debajo del máximo no se mueve."""
        ruta = self.ruta("historial.log")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write("corto")

        rotar_log(ruta, max_bytes=500_000)

        self.assertTrue(os.path.exists(ruta))
        self.assertFalse(os.path.exists(ruta + ".1"))


if __name__ == "__main__":
    unittest.main()
