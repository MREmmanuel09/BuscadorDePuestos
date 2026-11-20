"""Pruebas unitarias para el motor Aho-Corasick (compatibility_engine.py)
y los mecanismos auxiliares de compatibilidad.py.

No tocan red ni archivos: todo pasa en memoria.
"""

import os
import sys
import unittest

RUTA_BUSCADOR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "buscador"
)
if RUTA_BUSCADOR not in sys.path:
    sys.path.insert(0, RUTA_BUSCADOR)

from compatibility_engine import AhoCorasickEngine, sin_acentos, _normalizar
from compatibilidad import (
    CATEGORIA_COMPATIBLE,
    CATEGORIA_RELACIONADA,
    CATEGORIA_DESCARTADA,
    _sector_mezclable,
    _es_mixto,
    _unicos,
    _sin_repetir,
    _coinciden,
)


class TestAhoCorasickEngine(unittest.TestCase):
    """Pruebas del motor Aho-Corasick para coincidencia múltiple."""

    def test_busqueda_simple(self):
        """El motor encuentra cada palabra en su grupo."""
        motor = AhoCorasickEngine([("soporte", "fuertes"), ("ti", "medias")])
        resultado = motor.search("soporte ti")

        self.assertIn("soporte", resultado["fuertes"])
        self.assertIn("ti", resultado["medias"])

    def test_busqueda_con_contexto(self):
        """Varias palabras del mismo grupo se encuentran en un solo pase."""
        motor = AhoCorasickEngine(
            [("windows", "contexto"), ("python", "contexto"), ("git", "contexto")]
        )
        resultado = motor.search("usando python y git")

        self.assertEqual(resultado["contexto"], {"python", "git"})

    def test_busqueda_no_encontrado(self):
        """Sin coincidencias devuelven conjuntos vacios, no error."""
        motor = AhoCorasickEngine([("soporte", "fuertes"), ("ti", "medias")])
        resultado = motor.search("desarrollo de software")

        self.assertEqual(resultado["fuertes"], set())
        self.assertEqual(resultado["medias"], set())

    def test_busqueda_mayusculas(self):
        """El motor ignora mayusculas/minusculas."""
        motor = AhoCorasickEngine([("soporte", "fuertes")])
        resultado = motor.search("SOPORTE TI")

        self.assertIn("soporte", resultado["fuertes"])

    def test_busqueda_acentos(self):
        """Las tildes no impiden encontrar la raiz de la palabra."""
        motor = AhoCorasickEngine([("informatic", "medias")])
        resultado = motor.search("Técnico Informático")

        self.assertIn("informatic", resultado["medias"])

    def test_busqueda_espacios_variables(self):
        """Espacios simples, multiples o tabuladores son equivalentes."""
        motor = AhoCorasickEngine([("help desk", "fuertes")])
        self.assertIn("help desk", motor.search("help   desk")["fuertes"])
        self.assertIn("help desk", motor.search("Help\tDesk")["fuertes"])

    def test_busqueda_palabra_corta(self):
        """Las palabras cortas se encuentran donde esten (el limite de
        palabra lo decide el regex de compatibilidad, no el motor)."""
        motor = AhoCorasickEngine([("n1", "contexto")])
        self.assertIn("n1", motor.search("soporte n1")["contexto"])

    def test_coincidencia_por_sufijo(self):
        """Los enlaces de fallo detectan palabras que son sufijo de otra:
        'porte' esta dentro de 'soporte' sin volver a buscarlo."""
        motor = AhoCorasickEngine([("soporte", "fuertes"), ("porte", "medias")])
        resultado = motor.search("soporte")

        self.assertIn("soporte", resultado["fuertes"])
        self.assertIn("porte", resultado["medias"])

    def test_grupos_independientes(self):
        """La misma palabra puede pertenecer a dos grupos a la vez."""
        motor = AhoCorasickEngine([("redes", "fuertes"), ("redes", "contexto")])
        resultado = motor.search("redes")

        self.assertIn("redes", resultado["fuertes"])
        self.assertIn("redes", resultado["contexto"])

    def test_ignora_patrones_vacios(self):
        """Los patrones vacios o en blanco no rompen la construccion."""
        motor = AhoCorasickEngine([("", "fuertes"), ("   ", "medias"), ("ti", "castigo")])
        resultado = motor.search("ti")

        self.assertEqual(resultado["fuertes"], set())
        self.assertEqual(resultado["medias"], set())
        self.assertIn("ti", resultado["castigo"])

    def test_entrada_no_string(self):
        """Texto no str se convierte a str sin fallar."""
        motor = AhoCorasickEngine([("1", "contexto")])
        self.assertIn("1", motor.search(123)["contexto"])

    def test_search_compatibility(self):
        """La API agrupa los resultados por clave del config."""
        motor = AhoCorasickEngine([])
        cfg = {
            "palabras_fuertes": ["soporte ti"],
            "palabras_clave": ["soporte"],
            "palabras_excluidas": ["ventas"],
        }
        resultado = motor.search_compatibility("Soporte TI para ventas", cfg)

        self.assertIn("soporte ti", resultado["fuertes"])
        self.assertIn("soporte", resultado["medias"])
        self.assertIn("ventas", resultado["excluidas"])

    def test_normalizacion(self):
        """sin_acentos y _normalizar dejan el texto en la forma del buscador."""
        self.assertEqual(sin_acentos("ÁÉÍÓÚñ"), "aeioun")
        self.assertEqual(_normalizar("  Help\t Desk  "), "help desk")


class TestCompatibilidadMecanismos(unittest.TestCase):
    """Pruebas de los mecanismos auxiliares de compatibilidad.py."""

    def test_sector_mezclable(self):
        """Los sectores mezclables se reconocen; un sector de TI no."""
        self.assertTrue(_sector_mezclable("civil"))
        self.assertTrue(_sector_mezclable("electromecanic"))
        self.assertFalse(_sector_mezclable("software"))

    def test_es_mixto_como_anadido(self):
        """Un sector tras 'y' con frase fuerte de TI es un anadido tolerado."""
        texto = "tecnico de redes y obra civil"
        self.assertTrue(_es_mixto(texto, "obra civil", ("redes",)))

    def test_es_mixto_como_objeto(self):
        """Si el sector es el objeto del puesto no se tolera."""
        texto = "soporte para aire acondicionado"
        self.assertFalse(_es_mixto(texto, "aire acondicionado", ("soporte",)))

    def test_es_mixto_sin_frase_fuerte(self):
        """Sin palabras fuertes de TI el sector mezclable no se tolera."""
        texto = "tecnico de obra civil"
        self.assertFalse(_es_mixto(texto, "obra civil", ("redes",)))

    def test_unicos(self):
        """Las palabras contenidas en otra mas larga no se cuentan dos veces."""
        resultado = _unicos(("telecom", "telecomunicacion", "redes"))
        self.assertEqual(resultado, ["telecomunicacion", "redes"])

    def test_sin_repetir(self):
        """Lo ya contado en un grupo de mayor peso no se repite."""
        self.assertEqual(_sin_repetir(["ti"], ["informatica"]), [])
        self.assertEqual(_sin_repetir(["ti"], ["soporte"]), ["ti"])


class TestCompilar(unittest.TestCase):
    """Pruebas del compilador de patrones regex de compatibilidad.py.

    El regex conserva la semantica de palabra con limite: raiz con
    terminaciones para palabras largas y coincidencia exacta para las de
    3 letras o menos ("n1" no coincide dentro de "Fun1dad").
    """

    def test_raiz_con_terminaciones(self):
        """'informatic' coincide con 'informatica' y 'soporte' con 'soporte'.

        El texto llega en minusculas y sin tildes: asi trabaja puntuar()
        en produccion (sin_acentos antes de puntuar).
        """
        self.assertEqual(_coinciden("informatica", ("informatic",)), ["informatic"])
        self.assertEqual(_coinciden("soporte ti", ("soporte",)), ["soporte"])

    def test_frase_con_espacios(self):
        """'help desk' coincide aunque el texto traiga espacios extra."""
        self.assertEqual(_coinciden("help   desk", ("help desk",)), ["help desk"])

    def test_palabra_corta_exacta(self):
        """'n1' no coincide dentro de otra palabra."""
        self.assertEqual(_coinciden("fun1dad de transporte", ("n1",)), [])

    def test_sr_no_coincide_en_sra(self):
        """'sr' de 2 letras exige palabra completa."""
        self.assertEqual(_coinciden("sra. peralta", ("sr",)), [])

    def test_prefiltro_motor_no_cambia_el_resultado(self):
        """El prefiltro Aho-Corasick de _coinciden no altera la semantica:
        devuelve exactamente las palabras que el regex encontraria."""
        casos = [
            ("soporte ti", ("soporte", "ti"), ["soporte", "ti"]),
            ("fun1dad de transporte", ("n1",), []),
            ("tecnico informatico", ("informatic",), ["informatic"]),
            ("help desk remoto", ("help desk", "redes"), ["help desk"]),
            ("obra civil", ("aire acondicionado",), []),
        ]
        for texto, palabras, esperado in casos:
            with self.subTest(texto=texto):
                self.assertEqual(_coinciden(texto, palabras), esperado)


class TestCategorias(unittest.TestCase):
    """Las constantes de categoria se mantienen estables."""

    def test_valores(self):
        self.assertEqual(CATEGORIA_COMPATIBLE, "Compatible")
        self.assertEqual(CATEGORIA_RELACIONADA, "Relacionada")
        self.assertEqual(CATEGORIA_DESCARTADA, "Descartada")


if __name__ == "__main__":
    unittest.main()
