"""Pruebas del motor de compatibilidad (compatibilidad.py).

No tocan red ni archivos: se llama a puntuar() con diccionarios en memoria.
La tabla final usa titulos reales del buscador para validar la calibracion.
"""

import os
import sys
import unittest

RUTA_BUSCADOR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "buscador"
)
if RUTA_BUSCADOR not in sys.path:
    sys.path.insert(0, RUTA_BUSCADOR)

import compatibilidad  # noqa: E402

C = compatibilidad.CATEGORIA_COMPATIBLE
R = compatibilidad.CATEGORIA_RELACIONADA
D = compatibilidad.CATEGORIA_DESCARTADA


def oferta(titulo, ubicacion="Alajuela"):
    """Devuelve una oferta minima para puntuar (solo titulo y ubicacion)."""
    return {"titulo": titulo, "ubicacion": ubicacion}


class PruebaPuntuar(unittest.TestCase):
    """Casos unitarios del puntaje: palabras, castigos, umbrales y config."""

    def test_soporte_tecnico_es_compatible(self):
        """La frase fuerte 'soporte tecnico' da 75 % (3 de 4 puntos)."""
        r = compatibilidad.puntuar(oferta("Soporte Técnico"), {})
        self.assertEqual(r["categoria"], C)
        self.assertEqual(r["porcentaje"], 75)
        self.assertIn("soporte tecnico", r["fuertes"])

    def test_raiz_sin_acentos(self):
        """La raiz 'informatic' coincide con 'informatica' y sin tildes."""
        r = compatibilidad.puntuar(oferta("Soporte Informático"), {})
        self.assertIn("informatic", r["medias"])

    def test_palabra_completa_no_subcadena(self):
        """'n1' no coincide dentro de otra palabra (Fun1dad)."""
        r = compatibilidad.puntuar(oferta("Fun1dad de transporte"), {})
        self.assertNotIn("n1", r["contexto"])

    def test_excluida_anula_todo(self):
        """Una palabra excluida deja el puntaje en 0 aunque sume lo demas."""
        r = compatibilidad.puntuar(oferta("Soporte técnico para ventas"), {})
        self.assertEqual(r["porcentaje"], 0)
        self.assertEqual(r["categoria"], D)
        self.assertEqual(r["excluida"], "ventas")

    def test_incompatible_anula_aunque_sume(self):
        """'aire acondicionado' descarta la oferta aunque diga soporte tecnico."""
        r = compatibilidad.puntuar(oferta("Soporte Técnico para Aire Acondicionado"), {})
        self.assertEqual(r["categoria"], D)
        self.assertEqual(r["excluida"], "aire acondicionado")

    def test_desarrollador_queda_fuera(self):
        """Un desarrollador no es soporte ni redes: no entra a la lista diaria."""
        r = compatibilidad.puntuar(oferta("Desarrollador Full Stack"), {})
        self.assertEqual(r["categoria"], D)

    def test_sin_ancla_ti_queda_fuera(self):
        """Sin una palabra de soporte/redes/infraestructura no hay puntaje."""
        r = compatibilidad.puntuar(oferta("Analista de Datos"), {})
        self.assertEqual(r["categoria"], D)
        self.assertIn("sin enfoque TI", r["motivo"])

    def test_sector_mixto_se_conserva_como_relacionada(self):
        """Cableado estructurado con obra civil sigue siendo redes, no construccion."""
        r = compatibilidad.puntuar(oferta("Técnico de Cableado estructurado y obra civil"), {})
        self.assertEqual(r["categoria"], R)
        self.assertEqual(r["familia"], "Redes")
        self.assertIn("enfoque mixto", r["motivo"])

    def test_sector_como_objeto_se_descarta(self):
        """Si el sector es el objeto del puesto, no se tolera la mezcla."""
        r = compatibilidad.puntuar(oferta("Técnico en Refrigeración"), {})
        self.assertEqual(r["categoria"], D)

    def test_familias(self):
        """Cada titulo se etiqueta con su enfoque para filtrar sin perder opciones."""
        casos = {
            "IT Help Desk Specialist": "Soporte",
            "NOC Analyst": "Redes",
            "Data Center Technician": "Infraestructura",
            "Application Support Analyst": "Aplicaciones",
            "Field Service Technician": "Campo",
            "SOC Analyst I": "Seguridad",
        }
        for titulo, familia in casos.items():
            with self.subTest(titulo=titulo):
                self.assertEqual(
                    compatibilidad.puntuar(oferta(titulo), {})["familia"], familia
                )

    def test_soporte_n1_n2(self):
        """El CV actual es N1/N2: ambos niveles son Compatibles."""
        self.assertEqual(compatibilidad.puntuar(oferta("Soporte N1"), {})["categoria"], C)
        self.assertEqual(compatibilidad.puntuar(oferta("Soporte Nivel 2"), {})["categoria"], C)

    def test_ingles_b1_no_penaliza(self):
        """El CV actual es B1: B1 no resta; B2/C1 siguen siendo castigo."""
        r = compatibilidad.puntuar(oferta("Technical Support English B1"), {})
        self.assertNotIn("english b1", r["castigos"])
        self.assertEqual(r["categoria"], C)
        r2 = compatibilidad.puntuar(oferta("Technical Support English B2"), {})
        self.assertIn("english b2", r2["castigos"])

    def test_videovigilancia_es_contexto_no_ancla(self):
        """CCTV/videovigilancia suma en redes, pero no convierte solo un puesto en TI."""
        self.assertEqual(
            compatibilidad.puntuar(oferta("Técnico en Videovigilancia"), {})["categoria"], D
        )
        r = compatibilidad.puntuar(oferta("Técnico en CCTV y Redes"), {})
        self.assertEqual(r["categoria"], C)
        self.assertEqual(r["familia"], "Redes")

    def test_manager_se_muestra_como_relacionada(self):
        """Los puestos de jefatura no compiten con las vacantes N1/N2."""
        r = compatibilidad.puntuar(oferta("IT Helpdesk Manager"), {})
        self.assertEqual(r["categoria"], R)
        self.assertIn("puesto senior", r["motivo"])

    def test_senior_se_muestra_como_relacionada(self):
        """Un puesto senior no compite con las vacantes junior/mid."""
        r = compatibilidad.puntuar(oferta("Senior Technical Support Engineer"), {})
        self.assertEqual(r["categoria"], R)
        self.assertIn("puesto senior", r["motivo"])
        self.assertLessEqual(r["porcentaje"], 69)

    def test_junior_no_se_penaliza_por_seniority(self):
        """'Junior Helpdesk Analyst' sigue siendo Compatible."""
        r = compatibilidad.puntuar(oferta("Junior Helpdesk Analyst"), {})
        self.assertEqual(r["categoria"], C)

    def test_castigo_baja_el_puntaje(self):
        """'bilingual' resta puntos: technical support baja de 75 a 50 %."""
        r = compatibilidad.puntuar(oferta("Bilingual Technical Support Advisor"), {})
        self.assertEqual(r["porcentaje"], 50)
        self.assertIn("bilingual", r["castigos"])

    def test_solape_interno_no_suma_doble(self):
        """'telecom' y 'telecomunicacion' son el mismo concepto: cuenta una vez."""
        r = compatibilidad.puntuar(oferta("Soporte de Telecomunicaciones"), {})
        self.assertEqual(r["porcentaje"], 100)
        self.assertEqual(r["medias"], ["soporte", "telecomunicacion"])

    def test_solo_el_titulo_cuenta(self):
        """La ubicacion decide la zona, no la naturaleza del puesto."""
        r = compatibilidad.puntuar({"titulo": "Asistente", "ubicacion": "Soporte Remoto"}, {})
        self.assertEqual(r["porcentaje"], 0)
        self.assertEqual(r["categoria"], D)
        self.assertIn("sin enfoque TI", r["motivo"])

    def test_umbrales_personalizados(self):
        """Con meta 2 y minimo 90, un solo 'support' llega a Compatible."""
        cfg = {"meta_puntos": 2, "compatibilidad_minima": 90, "compatibilidad_relacionada": 10}
        r = compatibilidad.puntuar(oferta("Support Engineer"), cfg)
        self.assertEqual(r["porcentaje"], 100)
        self.assertEqual(r["categoria"], C)

    def test_config_legacy_solo_palabras_clave(self):
        """Un config viejo (solo palabras_clave) sigue funcionando como medias."""
        r = compatibilidad.puntuar(oferta("Empleado de Soporte"), {"palabras_clave": ["soporte"]})
        self.assertEqual(r["porcentaje"], 50)
        self.assertEqual(r["categoria"], R)

    def test_categoria_de_clasifica_por_umbral(self):
        """categoria_de respeta los umbrales del config."""
        self.assertEqual(compatibilidad.categoria_de(70, {}), C)
        self.assertEqual(compatibilidad.categoria_de(69, {}), R)
        self.assertEqual(compatibilidad.categoria_de(40, {}), R)
        self.assertEqual(compatibilidad.categoria_de(39, {}), D)


class PruebaCalibracion(unittest.TestCase):
    """Tabla de calibracion con titulos reales del CSV del buscador.

    Cada caso es (titulo, categoria esperada) con el perfil por defecto
    (Soporte TI / Redes). Si un cambio de pesos altera un caso, esta prueba
    falla y avisa que hay que recalibrar.
    """

    COMPATIBLES = [
        "IT Help Desk Specialist",
        "Ingeniero En Ciberseguridad",
        "Ingeniero De Ip Redes Ip Sector Telecomunicaciones Pavas",
        "Soportista Informático con énfasis en Seguridad",
        "Service Desk Analyst L1",
        "Soporte Técnico",
        "Técnico en soporte de Infraestructura",
        "Soporte de Telecomunicaciones",
        "Technical Support Technician",
        "Técnico En Soporte Ti",
        "Data Center Technician - CR - Alajuela - On-site",
        "Asistente De Soporte Y Redes",
        "Network And Firewall Engineer",
        "Ingeniero En Redes",
        "Remote Technical Support - STUDENT CONVERSION",
        "Information Technology Support Technican",
        "Network Security Engineer - RDT Security Platforms",
        "Técnico de Soporte II",
        "Soporte TI",
        "NOC Analyst",
        "Support Engineer II",
        "Operador De Sistemas Medio Tiempo Viernes A Domingo Cd Pdc Coyol",
        "Técnico Planta Externa N1 (San José- Heredia)",
        "Application Support Analyst",
    ]

    RELACIONADAS = [
        "Torrero Junior Para Empresa De Telecomunicaciones San Jose",
        "Domain Support CORE",
        "Bilingual Technical Support Advisor Chat",
        "Técnico de Cableado estructurado y obra civil",
        "Encargado de Infraestructura",
        "Coordinador de equipos de trabajo en campo - Telecomunicaciones",
        "Senior Associate - ServiceNow Application Support Administrator",
        "Senior Technical Support Engineer",
        "Technical Support Manager",
    ]

    DESCARTADAS = [
        "Asistente Comercial Experiencia En Soporte Y Atencion Comercial En Tuetal Norte De Alajuela",
        "Cod 11 Encargado Equipo Tecnicoinfraestructura Civil",
        "Operation Support Manager, Orthopedics",
        "Soporte Técnico para Aire Acondicionado",
        "Vendedor de muebles",
        "Soporte de marketing",
        "Desarrollador Full Stack",
        "Senior Software Engineer",
        "Customer Support Agent",
        "Tecnico Electromecanico",
        "Tecnólogo De Alimentos Para Desarrollo De Productos",
        "Analista de Soporte Trilingüe",
        "Product Support Specialist French",
        "Operational Technology Support Engineer 1",
    ]

    def _verificar(self, titulos, esperada):
        """Comprueba que todos los titulos caen en la categoria esperada."""
        for titulo in titulos:
            with self.subTest(titulo=titulo):
                r = compatibilidad.puntuar(oferta(titulo), {})
                self.assertEqual(r["categoria"], esperada, f"{titulo} -> {r}")

    def test_compatibles(self):
        """Los puestos de soporte/redes/infraestructura son Compatibles."""
        self._verificar(self.COMPATIBLES, C)

    def test_relacionadas(self):
        """Lo afin pero no exacto (developer, support generico) es Relacionada."""
        self._verificar(self.RELACIONADAS, R)

    def test_descartadas(self):
        """Otros rubros y ruido de palabras ('soporte X') quedan fuera."""
        self._verificar(self.DESCARTADAS, D)


if __name__ == "__main__":
    unittest.main()
