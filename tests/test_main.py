"""Pruebas de la logica de main.py: configuracion, filtros, lista negra y purgas.

Redirige todas las rutas de main a un directorio temporal: nunca tocan los
datos reales de la carpeta data/.
"""

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

import main  # noqa: E402


class BasePrueba(unittest.TestCase):
    """Base: apunta las rutas de main a un tempdir y las restaura al final."""

    def setUp(self):
        """Crea un directorio temporal y redirige todas las rutas de main."""
        self.tmp = tempfile.mkdtemp(prefix="buscador_test_")
        claves = ("DATA", "CONFIG_PATH", "EJEMPLO_CONFIG_PATH", "VISTAS_PATH",
                  "OFERTAS_PATH", "REPORTE_PATH", "LOG_PATH", "NEGRA_PATH",
                  "VERIFICADO_PATH")
        self._originales = {c: getattr(main, c) for c in claves}
        main.DATA = self.tmp
        main.CONFIG_PATH = os.path.join(self.tmp, "config.json")
        main.EJEMPLO_CONFIG_PATH = os.path.join(self.tmp, "sin_ejemplo.json")
        main.VISTAS_PATH = os.path.join(self.tmp, "vistas.json")
        main.OFERTAS_PATH = os.path.join(self.tmp, "ofertas.csv")
        main.REPORTE_PATH = os.path.join(self.tmp, "reporte.html")
        main.LOG_PATH = os.path.join(self.tmp, "historial.log")
        main.NEGRA_PATH = os.path.join(self.tmp, "lista_negra.json")
        main.VERIFICADO_PATH = os.path.join(self.tmp, "verificado.json")

    def tearDown(self):
        """Restaura las rutas originales y borra el temporal."""
        for clave, valor in self._originales.items():
            setattr(main, clave, valor)
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def fila(fecha, titulo, url, fuente="Computrabajo", ubicacion="Alajuela",
             estado="", empresa="Ejemplo"):
        """Devuelve una fila de oferta completa para escribirla en el CSV."""
        return {"fecha": fecha, "fuente": fuente, "titulo": titulo,
                "ubicacion": ubicacion, "empresa": empresa, "url": url,
                "estado_envio": estado}


class PruebaClavesYConfig(BasePrueba):
    """Pruebas de normalizacion de URLs y creacion automatica del config."""

    def test_clave_url_normaliza(self):
        """clave_url quita fragmentos, espacios y pasa a minusculas."""
        self.assertEqual(main.clave_url("HTTP://X.com/A#1 "), "http://x.com/a")
        self.assertEqual(main.clave_url("https://x.com/b"), "https://x.com/b")

    def test_config_se_crea_desde_defecto(self):
        """cargar_config crea config.json con los valores por defecto si falta."""
        self.assertFalse(os.path.exists(main.CONFIG_PATH))
        cfg = main.cargar_config()
        self.assertTrue(os.path.exists(main.CONFIG_PATH))
        self.assertEqual(cfg["zonas"], main.DEFECTO_CONFIG["zonas"])
        self.assertTrue(cfg["incluir_remoto"])


class PruebaFiltros(BasePrueba):
    """Pruebas de pasa_filtros: exclusion, palabras clave, zona y remoto."""

    def setUp(self):
        """Carga el config por defecto para usarlo en los casos."""
        super().setUp()
        self.cfg = main.cargar_config()
        self.zonas = ["alajuela"]

    def test_acepta_soporte_en_zona(self):
        """Una oferta de soporte en zona aceptada pasa el filtro."""
        o = {"titulo": "Soporte tecnico N1", "ubicacion": "Alajuela", "fuente": "Computrabajo"}
        self.assertTrue(main.pasa_filtros(o, self.zonas, self.cfg))

    def test_rechaza_sin_palabra_clave(self):
        """Un puesto sin palabras de TI no pasa aunque este en zona."""
        o = {"titulo": "Vendedor de muebles", "ubicacion": "Alajuela", "fuente": "Computrabajo"}
        self.assertFalse(main.pasa_filtros(o, self.zonas, self.cfg))

    def test_rechaza_palabra_excluida(self):
        """Las palabras excluidas ganan aunque el titulo tenga palabra clave."""
        o = {"titulo": "Soporte de marketing", "ubicacion": "Alajuela", "fuente": "Computrabajo"}
        self.assertFalse(main.pasa_filtros(o, self.zonas, self.cfg))

    def test_acepta_remoto_fuera_de_zona(self):
        """Con incluir_remoto, una oferta remota fuera de zona pasa."""
        o = {"titulo": "Soporte TI remoto", "ubicacion": "Heredia", "fuente": "Computrabajo"}
        self.assertTrue(main.pasa_filtros(o, self.zonas, self.cfg))

    def test_rechaza_fuera_de_zona_sin_remoto(self):
        """Fuera de zona y sin remoto, no pasa."""
        o = {"titulo": "Soporte TI", "ubicacion": "Heredia", "fuente": "Computrabajo"}
        self.assertFalse(main.pasa_filtros(o, self.zonas, self.cfg))

    def test_trabajo_org_tambien_respeta_la_zona(self):
        """Trabajo.org ya no exime del filtro: fuera de zona y sin remoto no pasa."""
        o = {"titulo": "Soporte TI", "ubicacion": "Heredia", "fuente": "Trabajo.org"}
        self.assertFalse(main.pasa_filtros(o, self.zonas, self.cfg))

    def test_descarta_soporte_de_otro_rubro(self):
        """'Soporte para aire acondicionado' no tiene que ver con el perfil."""
        o = {"titulo": "Soporte Tecnico para Aire Acondicionado",
             "ubicacion": "Alajuela", "fuente": "Computrabajo"}
        self.assertFalse(main.pasa_filtros(o, self.zonas, self.cfg))

    def test_descarta_desarrollador(self):
        """Un desarrollador no es soporte/redes y no entra a la lista diaria."""
        o = {"titulo": "Desarrollador Full Stack", "ubicacion": "Alajuela",
             "fuente": "LinkedIn"}
        self.assertFalse(main.pasa_filtros(o, self.zonas, self.cfg))

    def test_descarta_soporte_de_otro_sector(self):
        """'Soporte para refrigeracion' no es un puesto de TI."""
        o = {"titulo": "Tecnico en Refrigeracion", "ubicacion": "Alajuela",
             "fuente": "Computrabajo"}
        self.assertFalse(main.pasa_filtros(o, self.zonas, self.cfg))

    def test_descarta_temporal_ya_vencida(self):
        """Si el titulo dice 'hasta el 31/12/2024', la vacante ya no aplica."""
        o = {"titulo": "Tecnico de Soporte - Temporal hasta el 31/12/2024",
             "ubicacion": "Alajuela", "fuente": "FindJob24h"}
        self.assertFalse(main.pasa_filtros(o, self.zonas, self.cfg))

    def test_acepta_temporal_futura(self):
        """Una fecha de cierre futura no descarta la oferta."""
        o = {"titulo": "Tecnico de Soporte - Temporal hasta el 31/12/2999",
             "ubicacion": "Alajuela", "fuente": "FindJob24h"}
        self.assertTrue(main.pasa_filtros(o, self.zonas, self.cfg))

    def test_descarta_tecnico_de_otra_ingenieria(self):
        """Un puesto de otra ingenieria (civil) no pasa aunque diga tecnico."""
        o = {"titulo": "Cod 11 Encargado Equipo Tecnicoinfraestructura Civil",
             "ubicacion": "Alajuela", "fuente": "FindJob24h"}
        self.assertFalse(main.pasa_filtros(o, self.zonas, self.cfg))

    def test_descarta_puesto_medico(self):
        """Operacion con 'support' en el titulo pero rubro medico queda fuera."""
        o = {"titulo": "Operation Support Manager, Orthopedics",
             "ubicacion": "Grecia", "fuente": "Trabajo.org"}
        self.assertFalse(main.pasa_filtros(o, self.zonas, self.cfg))


class PruebaListaNegra(BasePrueba):
    """Pruebas de migracion, expiracion y alta en la lista negra."""

    def test_migra_formato_viejo(self):
        """El formato viejo {url: fecha} se migra a {hasta, titulo, fuente}."""
        import json
        with open(main.NEGRA_PATH, "w", encoding="utf-8") as f:
            json.dump({"urls": {"https://x.com/o": "2027-01-01"}}, f)
        negra = main.cargar_lista_negra()
        self.assertEqual(negra["https://x.com/o"]["hasta"], "2027-01-01")
        self.assertEqual(negra["https://x.com/o"]["titulo"], "")

    def test_purga_expiradas(self):
        """Las entradas con 'hasta' vencido se borran; las vigentes quedan."""
        import json
        with open(main.NEGRA_PATH, "w", encoding="utf-8") as f:
            json.dump({"urls": {
                "https://x.com/vieja": {"hasta": "2000-01-01", "titulo": "", "fuente": ""},
                "https://x.com/nueva": {"hasta": "2999-01-01", "titulo": "", "fuente": ""},
            }}, f)
        vivas = main.purgar_lista_negra()
        self.assertEqual(list(vivas), ["https://x.com/nueva"])

    def test_pasar_a_lista_negra_guarda_y_limpia_vistas(self):
        """El alta guarda titulo/fuente/fecha y quita la URL de vistas."""
        main.guardar_vistas({"https://x.com/o": "2026-01-01"})
        expira = main.pasar_a_lista_negra(
            [{"url": "https://x.com/o", "titulo": "Puesto X", "fuente": "LinkedIn"}]
        )
        negra = main.cargar_lista_negra()
        self.assertEqual(negra["https://x.com/o"]["titulo"], "Puesto X")
        self.assertEqual(negra["https://x.com/o"]["hasta"], expira)
        self.assertNotIn("https://x.com/o", main.cargar_vistas())


class PruebaPurgasYBorrado(BasePrueba):
    """Pruebas de purgar_ofertas (por antiguedad) y eliminar_ofertas (manual)."""

    def test_purga_conserva_marcadas_y_recientes(self):
        """Purga solo lo viejo sin estado; lo marcado y lo nuevo se queda."""
        hoy = "2999-01-01"
        main.guardar_ofertas([
            self.fila("2000-01-01", "Vieja", "https://x.com/1"),
            self.fila("2000-01-01", "Vieja marcada", "https://x.com/2", estado="Postulado"),
            self.fila(hoy, "Nueva", "https://x.com/3"),
        ])
        total, borradas = main.purgar_ofertas(15)
        self.assertEqual((total, borradas), (3, 1))
        self.assertEqual(len(main.cargar_ofertas()), 2)
        self.assertIn("https://x.com/1", main.cargar_lista_negra())

    def test_eliminar_ofertas_quita_y_en_negra(self):
        """Borrar una URL la saca del CSV y queda en lista negra con titulo."""
        main.guardar_ofertas([
            self.fila("2999-01-01", "Borrar", "https://x.com/borrar"),
            self.fila("2999-01-01", "Quedar", "https://x.com/quedar"),
        ])
        borradas = main.eliminar_ofertas(["https://x.com/borrar"])
        self.assertEqual(borradas, 1)
        restantes = main.cargar_ofertas()
        self.assertEqual([o["titulo"] for o in restantes], ["Quedar"])
        negra = main.cargar_lista_negra()
        self.assertEqual(negra["https://x.com/borrar"]["titulo"], "Borrar")

    def test_escribir_reporte_genera_html(self):
        """el reporte se crea con titulo, datos y la nota de solo lectura."""
        oferta = self.fila("2999-01-01", "Soporte Tecnico & Prueba", "https://x.com/p")
        main.escribir_reporte([oferta], [oferta], "2999-01-01 10:00", 15, 0)
        with open(main.REPORTE_PATH, encoding="utf-8") as f:
            html = f.read()
        self.assertIn("Buscador de Puestos", html)
        self.assertIn("Soporte Tecnico &amp; Prueba", html)
        self.assertIn("solo lectura", html)
        self.assertIn("Compatibles", html)
        self.assertIn("Relacionadas", html)

    def test_reporte_ordenado_por_compatibilidad(self):
        """En el reporte, la oferta mas compatible aparece antes que la relacionada."""
        compatible = self.fila("2999-01-01", "Soporte TI", "https://x.com/a")
        relacionada = self.fila("2999-01-01", "Domain Support CORE", "https://x.com/b")
        main.escribir_reporte([], [relacionada, compatible], "2999-01-01 10:00", 15, 0)
        with open(main.REPORTE_PATH, encoding="utf-8") as f:
            html = f.read()
        self.assertLess(html.index("Soporte TI"), html.index("Domain Support CORE"))


class PruebaDeduplicar(BasePrueba):
    """Pruebas del descarte de repetidos por URL o por (titulo, empresa)."""

    def test_quita_url_repetida(self):
        """La misma URL solo se conserva una vez."""
        ofertas = [
            {"titulo": "Soporte TI", "empresa": "", "url": "https://x.com/a"},
            {"titulo": "Soporte TI", "empresa": "", "url": "https://x.com/a#frag"},
        ]
        self.assertEqual(len(main.deduplicar(ofertas)), 1)

    def test_quita_mismo_titulo_y_empresa(self):
        """El mismo puesto con dos URLs (p. ej. LinkedIn duplicado) queda una vez."""
        ofertas = [
            {"titulo": "Domain Support CORE", "empresa": "Ericsson", "url": "https://x.com/1"},
            {"titulo": "Domain Support CORE", "empresa": "Ericsson", "url": "https://x.com/2"},
        ]
        self.assertEqual(len(main.deduplicar(ofertas)), 1)

    def test_conserva_titulos_iguales_sin_empresa(self):
        """Sin empresa informada no se descarta: pueden ser puestos distintos."""
        ofertas = [
            {"titulo": "Soporte Tecnico", "empresa": "", "url": "https://x.com/1"},
            {"titulo": "Soporte Tecnico", "empresa": "", "url": "https://x.com/2"},
        ]
        self.assertEqual(len(main.deduplicar(ofertas)), 2)


class PruebaPostulacionesHoy(BasePrueba):
    """Pruebas del conteo diario de postulaciones desde historial.log."""

    def test_suma_solo_las_de_hoy(self):
        """Solo cuenta eventos 'Postulado' de la fecha pedida."""
        with open(main.LOG_PATH, "w", encoding="utf-8") as f:
            f.write("[2026-11-15 09:00:00] ESTADO 'Postulado' filas=2\n")
            f.write("[2026-11-15 10:00:00] ESTADO 'Postulado' filas=1\n")
            f.write("[2026-11-14 10:00:00] ESTADO 'Postulado' filas=9\n")
            f.write("[2026-11-15 11:00:00] ESTADO 'Descartado' filas=4\n")
        self.assertEqual(main.postulaciones_hoy("2026-11-15"), 3)
        self.assertEqual(main.postulaciones_hoy("2026-11-14"), 9)
        self.assertEqual(main.postulaciones_hoy("2026-11-13"), 0)

    def test_sin_historial_devuelve_cero(self):
        """Si el historial no existe, la meta diaria arranca en cero."""
        self.assertEqual(main.postulaciones_hoy("2026-11-15"), 0)


class PruebaRecolectarEnParalelo(BasePrueba):
    """Pruebas de recolectar: junta fuentes y aisla los fallos de una sola."""

    def test_junta_fuentes_y_aisla_errores(self):
        """Una fuente que falla no impide las ofertas de las demas."""
        import types

        def buscar_ok(cfg):
            return [{"titulo": "Soporte TI", "ubicacion": "Alajuela", "empresa": "",
                     "url": "https://ok.com/1", "fuente": "Falsa"}]

        def buscar_falla(cfg):
            raise RuntimeError("sin red")

        falsas = [
            types.SimpleNamespace(__name__="fuente_ok", buscar=buscar_ok),
            types.SimpleNamespace(__name__="fuente_mala", buscar=buscar_falla),
        ]
        originales = main.FUENTES
        main.FUENTES = falsas
        try:
            ofertas = main.recolectar(main.cargar_config())
        finally:
            main.FUENTES = originales
        self.assertEqual([o["url"] for o in ofertas], ["https://ok.com/1"])


class PruebaConfigNormalizada(BasePrueba):
    """Pruebas de validacion del config y de las copias antes de borrar."""

    def test_normaliza_umbrales_y_listas(self):
        """Los valores fuera de rango se limitan y las listas se limpian."""
        cfg = main.normalizar_config(
            {
                "compatibilidad_minima": 300,
                "compatibilidad_relacionada": 500,
                "meta_puntos": 0,
                "palabras_fuertes": [" Soporte ", "", "soporte"],
                "dias_retencion": -4,
            }
        )
        self.assertEqual(cfg["compatibilidad_minima"], 100)
        self.assertEqual(cfg["compatibilidad_relacionada"], 100)
        self.assertEqual(cfg["meta_puntos"], 1)
        self.assertEqual(cfg["palabras_fuertes"], ["Soporte"])
        self.assertEqual(cfg["dias_retencion"], 1)
        self.assertEqual(cfg["config_version"], main.VERSION_CONFIG)

    def test_config_version_se_guarda(self):
        """cargar_config deja la version y las claves nuevas en el archivo."""
        cfg = main.cargar_config()
        self.assertEqual(cfg["config_version"], main.VERSION_CONFIG)
        self.assertIn("clave_app_cifrada", cfg["correo"])

    def test_eliminar_ofertas_crea_backup(self):
        """Antes de borrar se guarda una copia del CSV en data/backups."""
        main.guardar_ofertas(
            [self.fila("2999-01-01", "Borrar", "https://x.com/borrar")]
        )
        main.eliminar_ofertas(["https://x.com/borrar"])
        backups = os.listdir(os.path.join(self.tmp, "backups"))
        self.assertTrue(any(nombre.startswith("ofertas-") for nombre in backups))


if __name__ == "__main__":
    unittest.main()
