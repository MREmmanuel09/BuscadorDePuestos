"""Pruebas de la rotacion de consultas por corrida (consultas.py)."""

import os
import sys
import unittest
from datetime import date

RUTA_BUSCADOR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "buscador"
)
if RUTA_BUSCADOR not in sys.path:
    sys.path.insert(0, RUTA_BUSCADOR)

from consultas import consultas  # noqa: E402

CFG = {
    "palabras_clave_busqueda": [f"consulta {i}" for i in range(10)],
    "consultas_fijas": 2,
    "consultas_por_corrida": 5,
}


class PruebaConsultas(unittest.TestCase):
    """Casos de la ventana fija + rotacion diaria."""

    def test_respeta_limite_y_fijas(self):
        """Devuelve el limite y conserva las primeras consultas fijas."""
        lista = consultas(CFG, "Computrabajo", date(2026, 11, 15))
        self.assertEqual(len(lista), 5)
        self.assertEqual(lista[:2], ["consulta 0", "consulta 1"])
        self.assertEqual(len(set(lista)), len(lista))

    def test_rota_el_resto_por_dia(self):
        """Dos dias seguidos no usan exactamente la misma cola."""
        dia1 = consultas(CFG, "Computrabajo", date(2026, 11, 15))
        dia2 = consultas(CFG, "Computrabajo", date(2026, 11, 16))
        self.assertNotEqual(dia1[2:], dia2[2:])

    def test_cubre_todo_el_catalogo_en_una_semana(self):
        """En varios dias la rotacion termina visitando todas las consultas."""
        vistas = set()
        for offset in range(10):
            vistas.update(consultas(CFG, "LinkedIn", date(2026, 11, 1 + offset)))
        self.assertEqual(vistas, set(CFG["palabras_clave_busqueda"]))

    def test_fuentes_rotan_distinto(self):
        """Dos fuentes el mismo dia exploran colas diferentes."""
        a = consultas(CFG, "Computrabajo", date(2026, 11, 15))
        b = consultas(CFG, "LinkedIn", date(2026, 11, 15))
        self.assertNotEqual(a[2:], b[2:])

    def test_cero_usa_todas(self):
        """El limite 0 significa 'sin recorte'."""
        cfg = dict(CFG, consultas_por_corrida=0)
        self.assertEqual(len(consultas(cfg, "Computrabajo")), 10)

    def test_catalogo_corto_no_rota(self):
        """Si el catalogo cabe en el limite, devuelve todo."""
        cfg = dict(CFG, consultas_por_corrida=20)
        self.assertEqual(consultas(cfg, "Computrabajo"), CFG["palabras_clave_busqueda"])

    def test_config_vacio(self):
        """Sin consultas devuelve lista vacia sin lanzar."""
        self.assertEqual(consultas({}, "Computrabajo"), [])


if __name__ == "__main__":
    unittest.main()
