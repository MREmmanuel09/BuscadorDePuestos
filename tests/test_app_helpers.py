"""Pruebas de las funciones helper de app.pyw que no necesitan ventana.

Se importa el modulo sin crear ningun widget de Tkinter.
"""

import importlib.util
import os
import sys
import unittest

RUTA_BUSCADOR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "buscador"
)
if RUTA_BUSCADOR not in sys.path:
    sys.path.insert(0, RUTA_BUSCADOR)

RUTA_APP = os.path.join(RUTA_BUSCADOR, "app.pyw")
_spec = importlib.util.spec_from_file_location("app_buscador", RUTA_APP)
app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(app)


class PruebaFiltrar(unittest.TestCase):
    """Casos de filtrar(ofertas, texto, estado, categoria, compat) en memoria."""

    OFERTAS = [
        {"titulo": "Redes y Cableado", "ubicacion": "Alajuela", "empresa": "A",
         "fuente": "Computrabajo", "estado_envio": "", "url": "https://x.com/redes"},
        {"titulo": "Soporte Tecnico", "ubicacion": "San Jose", "empresa": "B",
         "fuente": "LinkedIn", "estado_envio": "Postulado", "url": "https://x.com/soporte"},
        {"titulo": "Help Desk", "ubicacion": "Remoto", "empresa": "C",
         "fuente": "Trabajo.org", "estado_envio": "", "url": "https://x.com/helpdesk"},
    ]

    COMPAT = {
        "https://x.com/redes": {"porcentaje": 75, "categoria": "Compatible"},
        "https://x.com/soporte": {"porcentaje": 50, "categoria": "Relacionada"},
        "https://x.com/helpdesk": {"porcentaje": 100, "categoria": "Compatible"},
    }

    def test_texto_sin_tildes_coincide(self):
        """El filtro de texto ignora tildes y mayusculas."""
        res = app.filtrar(self.OFERTAS, "tecnico")
        self.assertEqual([o["titulo"] for o in res], ["Soporte Tecnico"])

    def test_estado_postulado(self):
        """El filtro por estado muestra solo las marcadas igual."""
        res = app.filtrar(self.OFERTAS, "", "Postulado")
        self.assertEqual([o["titulo"] for o in res], ["Soporte Tecnico"])

    def test_estado_sin_estado(self):
        """'Sin estado' excluye las que ya tienen marcador."""
        res = app.filtrar(self.OFERTAS, "", "Sin estado")
        self.assertEqual([o["titulo"] for o in res], ["Redes y Cableado", "Help Desk"])

    def test_estado_todos(self):
        """'Todos' no descarta nada."""
        self.assertEqual(len(app.filtrar(self.OFERTAS, "", "Todos")), 3)

    def test_texto_y_estado_juntos(self):
        """Texto y estado se aplican a la vez."""
        res = app.filtrar(self.OFERTAS, "soporte", "Postulado")
        self.assertEqual([o["titulo"] for o in res], ["Soporte Tecnico"])

    def test_categoria_compatible(self):
        """Con 'Compatible' solo pasan las marcadas como tal en el mapa."""
        res = app.filtrar(self.OFERTAS, "", "Todos", "Compatible", self.COMPAT)
        self.assertEqual([o["titulo"] for o in res], ["Redes y Cableado", "Help Desk"])

    def test_categoria_relacionada(self):
        """Con 'Relacionada' solo pasa la afin al perfil."""
        res = app.filtrar(self.OFERTAS, "", "Todos", "Relacionada", self.COMPAT)
        self.assertEqual([o["titulo"] for o in res], ["Soporte Tecnico"])

    def test_categoria_todas_no_filtra(self):
        """'Todas' no descarta aunque falten datos de compatibilidad."""
        self.assertEqual(len(app.filtrar(self.OFERTAS, "", "Todos", "Todas", {})), 3)


class PruebaPythonConsola(unittest.TestCase):
    """Pruebas de python_consola (ruta del interprete para subprocess)."""

    def test_devuelve_interprete_de_consola(self):
        """python_consola devuelve python.exe aunque se corra con pythonw."""
        original = sys.executable
        try:
            falso = os.path.join(os.path.dirname(original), "pythonw.exe")
            sys.executable = falso
            ruta = app.python_consola()
            self.assertTrue(ruta.endswith("python.exe"), ruta)
            self.assertTrue(os.path.exists(ruta), ruta)
        finally:
            sys.executable = original
        self.assertTrue(app.python_consola().endswith("python.exe"))


class PruebaEstadisticas(unittest.TestCase):
    """Pruebas de calcular_estadisticas (resumen para la ventana de estadisticas)."""

    OFERTAS = [
        {"fecha": "2999-01-01", "fuente": "LinkedIn", "estado_envio": "Postulado",
         "url": "https://x.com/1"},
        {"fecha": "2999-01-01", "fuente": "LinkedIn", "estado_envio": "",
         "url": "https://x.com/2"},
        {"fecha": "2999-01-02", "fuente": "Computrabajo", "estado_envio": "Descartado",
         "url": "https://x.com/3"},
        {"fecha": "2000-01-01", "fuente": "Computrabajo", "estado_envio": "",
         "url": "https://x.com/4"},
        {"fecha": "", "fuente": "", "estado_envio": "", "url": "https://x.com/5"},
    ]

    def test_totales_y_estados(self):
        """Cuenta el total y reparte por estado (vacio cuenta como sin estado)."""
        datos = app.calcular_estadisticas(self.OFERTAS, hoy="2999-01-03")
        self.assertEqual(datos["total"], 5)
        self.assertEqual(datos["estados"],
                         {"postuladas": 1, "descartadas": 1, "sin_estado": 3})

    def test_por_dia_siete_dias(self):
        """Devuelve exactamente 7 dias ascendentes con los conteos de cada uno."""
        datos = app.calcular_estadisticas(self.OFERTAS, hoy="2999-01-07")
        self.assertEqual(len(datos["por_dia"]), 7)
        self.assertEqual(datos["por_dia"][0][0], "2999-01-01")
        self.assertEqual(datos["por_dia"][-1], ("2999-01-07", 0))
        self.assertEqual(dict(datos["por_dia"])["2999-01-01"], 2)
        self.assertEqual(dict(datos["por_dia"])["2999-01-02"], 1)

    def test_fuentes_ordenadas_por_conteo(self):
        """Las fuentes salen de mayor a menor; la vacia queda como 'Otra'."""
        datos = app.calcular_estadisticas(self.OFERTAS, hoy="2999-01-03")
        self.assertEqual(datos["fuentes"][0], ("Computrabajo", 2))
        self.assertEqual(datos["fuentes"][1], ("LinkedIn", 2))
        self.assertIn(("Otra", 1), datos["fuentes"])

    def test_categorias_con_compat(self):
        """Reparte por categoria; lo que no esta en el mapa no se cuenta."""
        compat = {
            "https://x.com/1": {"porcentaje": 75, "categoria": "Compatible"},
            "https://x.com/2": {"porcentaje": 50, "categoria": "Relacionada"},
            "https://x.com/3": {"porcentaje": 10, "categoria": "Descartada"},
            "https://x.com/4": {"porcentaje": 100, "categoria": "Compatible"},
        }
        datos = app.calcular_estadisticas(self.OFERTAS, hoy="2999-01-03", compat=compat)
        self.assertEqual(datos["categorias"],
                         {"compatibles": 2, "relacionadas": 1, "descartadas": 1})

    def test_categorias_vacias_sin_compat(self):
        """Sin mapa de compatibilidad las categorias quedan en cero."""
        datos = app.calcular_estadisticas(self.OFERTAS, hoy="2999-01-03")
        self.assertEqual(datos["categorias"],
                         {"compatibles": 0, "relacionadas": 0, "descartadas": 0})


class PruebaConfigParcial(unittest.TestCase):
    """Pruebas de guardar_config_parcial (fusion claves en config.json)."""

    def setUp(self):
        """Redirige el config y los datos (main y app) a un temporal."""
        import tempfile
        import main
        self.tmp = tempfile.mkdtemp(prefix="cfg_test_")
        self._orig = (
            main.DATA, main.CONFIG_PATH, main.EJEMPLO_CONFIG_PATH, app.UI_STATE_PATH
        )
        main.DATA = self.tmp
        main.CONFIG_PATH = os.path.join(self.tmp, "config.json")
        main.EJEMPLO_CONFIG_PATH = os.path.join(self.tmp, "sin_ejemplo.json")
        app.UI_STATE_PATH = os.path.join(self.tmp, "ui_state.json")

    def tearDown(self):
        """Restaura las rutas originales y borra el temporal."""
        import shutil
        import main
        main.DATA, main.CONFIG_PATH, main.EJEMPLO_CONFIG_PATH, app.UI_STATE_PATH = (
            self._orig
        )
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_fusiona_sin_tocar_otros(self):
        """guardar_config_parcial agrega la clave y conserva las demas."""
        import json
        import main
        app.guardar_config_parcial({"app_auto_minutos": 10})
        with open(main.CONFIG_PATH, encoding="utf-8") as f:
            datos = json.load(f)
        self.assertEqual(datos["app_auto_minutos"], 10)
        self.assertIn("palabras_clave", datos)


class PruebaFiltrosAvanzados(unittest.TestCase):
    """Casos de los filtros nuevos: fuente, zona, estados multiples y chips."""

    OFERTAS = [
        {"titulo": "Soporte TI", "empresa": "ACME", "ubicacion": "Alajuela",
         "fuente": "LinkedIn", "estado_envio": "", "fecha": "2999-01-01",
         "url": "https://x.com/1"},
        {"titulo": "Help Desk", "empresa": "", "ubicacion": "San Jose",
         "fuente": "Computrabajo", "estado_envio": "Postulado",
         "fecha": "2999-01-02", "url": "https://x.com/2"},
        {"titulo": "Soporte remoto", "empresa": "Beta", "ubicacion": "Remoto",
         "fuente": "LinkedIn", "estado_envio": "Descartado",
         "fecha": "2999-01-03", "url": "https://x.com/3"},
    ]
    COMPAT = {
        "https://x.com/1": {"porcentaje": 100, "categoria": "Compatible", "familia": "Soporte"},
        "https://x.com/2": {"porcentaje": 75, "categoria": "Compatible", "familia": "Soporte"},
        "https://x.com/3": {"porcentaje": 50, "categoria": "Relacionada", "familia": "Redes"},
    }

    def test_fuente(self):
        """El filtro de fuente deja solo las ofertas de esa fuente."""
        res = app.filtrar(self.OFERTAS, categoria="Todas", fuentes={"LinkedIn"})
        self.assertEqual([o["url"] for o in res],
                         ["https://x.com/1", "https://x.com/3"])

    def test_zona_sin_tildes(self):
        """La zona se compara sin tildes y por subcadena."""
        res = app.filtrar(self.OFERTAS, categoria="Todas", zonas=["san jose"])
        self.assertEqual([o["url"] for o in res], ["https://x.com/2"])

    def test_estados_multiples(self):
        """Se pueden elegir varios estados a la vez."""
        res = app.filtrar(
            self.OFERTAS, categoria="Todas",
            estados={"Postulado", "Descartado"},
        )
        self.assertEqual([o["url"] for o in res],
                         ["https://x.com/2", "https://x.com/3"])

    def test_solo_nuevas_de_hoy(self):
        """El chip Nuevas hoy compara la fecha con el dia indicado."""
        res = app.filtrar(
            self.OFERTAS, categoria="Todas", solo_nuevas=True, hoy="2999-01-02"
        )
        self.assertEqual([o["url"] for o in res], ["https://x.com/2"])

    def test_sin_postular(self):
        """Sin postular excluye las que ya tienen cualquier estado."""
        res = app.filtrar(self.OFERTAS, categoria="Todas", sin_postular=True)
        self.assertEqual([o["url"] for o in res], ["https://x.com/1"])

    def test_solo_remoto(self):
        """El chip Remoto usa las palabras del perfil."""
        res = app.filtrar(
            self.OFERTAS, categoria="Todas", solo_remoto=True,
            palabras_remoto=["remoto"],
        )
        self.assertEqual([o["url"] for o in res], ["https://x.com/3"])

    def test_combinacion_and(self):
        """Fuente y remoto se combinan con AND."""
        res = app.filtrar(
            self.OFERTAS, categoria="Todas", fuentes={"LinkedIn"},
            solo_remoto=True, palabras_remoto=["remoto"],
        )
        self.assertEqual([o["url"] for o in res], ["https://x.com/3"])

    def test_categoria_con_mapa(self):
        """La categoria sigue funcionando con el mapa de compatibilidad."""
        res = app.filtrar(
            self.OFERTAS, categoria="Relacionada", compat=self.COMPAT
        )
        self.assertEqual([o["url"] for o in res], ["https://x.com/3"])

    def test_familia_del_puesto(self):
        """El filtro de enfoque deja solo la familia elegida."""
        res = app.filtrar(
            self.OFERTAS, categoria="Todas", compat=self.COMPAT,
            familias={"Redes"},
        )
        self.assertEqual([o["url"] for o in res], ["https://x.com/3"])


class PruebaOrden(unittest.TestCase):
    """Casos del orden por columna de la tabla."""

    OFERTAS = [
        {"titulo": "Zeta", "fecha": "2999-01-01", "url": "https://x.com/z"},
        {"titulo": "Alfa", "fecha": "2999-01-03", "url": "https://x.com/a"},
        {"titulo": "Beta", "fecha": "2999-01-02", "url": "https://x.com/b"},
    ]
    COMPAT = {
        "https://x.com/z": {"porcentaje": 50},
        "https://x.com/a": {"porcentaje": 100},
        "https://x.com/b": {"porcentaje": 75},
    }

    def test_por_compatibilidad(self):
        """Compat ordena del porcentaje mayor al menor."""
        res = app.ordenar(self.OFERTAS, "compat", True, self.COMPAT)
        self.assertEqual([o["titulo"] for o in res], ["Alfa", "Beta", "Zeta"])

    def test_por_titulo_ascendente(self):
        """Titulo ordena alfabeticamente sin distinguir mayusculas."""
        res = app.ordenar(self.OFERTAS, "titulo", False)
        self.assertEqual([o["titulo"] for o in res], ["Alfa", "Beta", "Zeta"])

    def test_por_fecha_descendente(self):
        """Dias/fecha descendente muestra primero la mas nueva."""
        res = app.ordenar(self.OFERTAS, "dias", True)
        self.assertEqual([o["titulo"] for o in res], ["Alfa", "Beta", "Zeta"])


class PruebaResumen(unittest.TestCase):
    """Casos del resumen que alimenta chips y filtros avanzados."""

    OFERTAS = PruebaFiltrosAvanzados.OFERTAS

    def test_conteos(self):
        """Cuenta categorias, fuentes, zonas, estados y atajos."""
        resumen = app.resumen_ofertas(
            self.OFERTAS,
            PruebaFiltrosAvanzados.COMPAT,
            {"zonas": ["alajuela", "san jose"], "palabras_remoto": ["remoto"]},
            hoy="2999-01-02",
        )
        self.assertEqual(resumen["categorias"]["compatibles"], 2)
        self.assertEqual(resumen["categorias"]["relacionadas"], 1)
        self.assertEqual(resumen["fuentes"]["LinkedIn"], 2)
        self.assertEqual(resumen["zonas"]["alajuela"], 1)
        self.assertEqual(resumen["estados"]["Postulado"], 1)
        self.assertEqual(resumen["nuevas"], 1)
        self.assertEqual(resumen["remotas"], 1)
        self.assertEqual(resumen["sin_postular"], 1)
        self.assertEqual(resumen["familias"]["Soporte"], 2)
        self.assertEqual(resumen["familias"]["Redes"], 1)


if __name__ == "__main__":
    unittest.main()
