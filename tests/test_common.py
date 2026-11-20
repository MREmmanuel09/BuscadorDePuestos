"""Pruebas de resiliencia: CircuitBreaker, RetryPolicy, FuenteRobusta
y el circuito por host integrado en fuentes.comun.descargar.

Nada toca la red: urllib y time.sleep se mockean.
"""

import os
import sys
import time
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

RUTA_BUSCADOR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "buscador"
)
if RUTA_BUSCADOR not in sys.path:
    sys.path.insert(0, RUTA_BUSCADOR)

from fuentes.common import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerState,
    RetryPolicy,
    FuenteRobusta,
    crear_fuente_robusta,
)
from fuentes import comun


class TestCircuitBreaker(unittest.TestCase):
    """Transiciones de estado del interruptor."""

    def test_inicia_cerrado(self):
        """En reposo el circuito deja pasar peticiones."""
        cb = CircuitBreaker()
        self.assertEqual(cb.state, CircuitBreakerState.CLOSED)
        self.assertTrue(cb.allow_request())

    def test_se_abre_al_llegar_al_umbral(self):
        """Tras max_failures fallos seguidos se abre y rechaza."""
        cb = CircuitBreaker(CircuitBreakerConfig(max_failures=3))
        for _ in range(2):
            cb.record_failure()
        self.assertTrue(cb.allow_request())  # aun cerrado

        cb.record_failure()
        self.assertEqual(cb.state, CircuitBreakerState.OPEN)
        self.assertFalse(cb.allow_request())

    def test_exito_reinicia_los_fallos(self):
        """Un exito limpia el contador de fallos."""
        cb = CircuitBreaker(CircuitBreakerConfig(max_failures=3))
        cb.record_failure()
        cb.record_failure()
        cb.record_success()

        self.assertEqual(cb.metrics.failures, 0)
        self.assertEqual(cb.state, CircuitBreakerState.CLOSED)

    def test_reset_pasa_a_half_open_tras_la_ventana(self):
        """Despues de la ventana de bloqueo se permite una prueba."""
        cb = CircuitBreaker(CircuitBreakerConfig(max_failures=1, duration_seconds=60))
        cb.record_failure()
        self.assertEqual(cb.state, CircuitBreakerState.OPEN)

        # Ventana transcurrida (sin dormir: se retrocede el reloj)
        cb.metrics.last_failure_time = time.time() - 61
        cb.reset()
        self.assertEqual(cb.state, CircuitBreakerState.HALF_OPEN)
        self.assertTrue(cb.allow_request())

    def test_reset_sin_ventana_sigue_abierto(self):
        """Dentro de la ventana el circuito sigue cerrado a pruebas."""
        cb = CircuitBreaker(CircuitBreakerConfig(max_failures=1, duration_seconds=300))
        cb.record_failure()

        cb.reset()
        self.assertEqual(cb.state, CircuitBreakerState.OPEN)
        self.assertFalse(cb.allow_request())

    def test_fallo_en_half_open_vuelve_a_abrir(self):
        """La prueba de recuperacion fallida regresa a OPEN."""
        cb = CircuitBreaker(CircuitBreakerConfig(max_failures=1, duration_seconds=60))
        cb.record_failure()
        cb.metrics.last_failure_time = time.time() - 61
        cb.reset()

        cb.record_failure()
        self.assertEqual(cb.state, CircuitBreakerState.OPEN)

    def test_exito_en_half_open_cierra(self):
        """La prueba de recuperacion exitosa cierra el circuito."""
        cb = CircuitBreaker(CircuitBreakerConfig(max_failures=1, duration_seconds=60))
        cb.record_failure()
        cb.metrics.last_failure_time = time.time() - 61
        cb.reset()

        cb.record_success()
        self.assertEqual(cb.state, CircuitBreakerState.CLOSED)
        self.assertTrue(cb.allow_request())


class TestRetryPolicy(unittest.TestCase):
    """Reintentos con espera exponencial y jitter."""

    def test_wait_time_crece_exponencialmente_con_jitter_acotado(self):
        """La espera sigue base*factor^n dentro del rango del jitter."""
        politica = RetryPolicy(base_delay=1.0, backoff_factor=2.0, jitter_range=0.5)

        for intento, esperado in ((0, 1.0), (1, 2.0), (2, 4.0)):
            with self.subTest(intento=intento):
                espera = politica.wait_time(intento)
                self.assertGreaterEqual(espera, max(0.1, esperado - 0.5))
                self.assertLessEqual(espera, esperado + 0.5)

    def test_wait_time_nunca_es_negativa(self):
        """El jitter no puede provocar espera negativa."""
        politica = RetryPolicy(base_delay=0.2, jitter_range=5.0)
        self.assertGreaterEqual(politica.wait_time(0), 0.1)

    def test_reintenta_hasta_tener_exito(self):
        """Falla dos veces y a la tercera devuelve el resultado."""
        politica = RetryPolicy(max_retries=3)
        llamadas = {"n": 0}

        def falla_dos_veces():
            llamadas["n"] += 1
            if llamadas["n"] < 3:
                raise ValueError("transitorio")
            return "ok"

        with patch("fuentes.common.time.sleep") as dormir:
            resultado = politica.execute_with_retry(falla_dos_veces)

        self.assertEqual(resultado, "ok")
        self.assertEqual(llamadas["n"], 3)
        self.assertEqual(dormir.call_count, 2)  # no duerme tras el exito

    def test_agota_reintentos_y_propaga(self):
        """Con max_retries=2 se intenta 3 veces y lanza la ultima excepcion."""
        politica = RetryPolicy(max_retries=2)
        llamadas = {"n": 0}

        def falla_siempre():
            llamadas["n"] += 1
            raise ValueError("caido")

        with patch("fuentes.common.time.sleep"):
            with self.assertRaises(ValueError):
                politica.execute_with_retry(falla_siempre)

        self.assertEqual(llamadas["n"], 3)


class TestFuenteRobusta(unittest.TestCase):
    """El envoltorio combina circuito y reintentos sin tragar errores."""

    def test_exito(self):
        """Devuelve el resultado y registra el exito."""
        fuente = FuenteRobusta(lambda cfg: [{"url": "x"}], "Prueba")

        self.assertEqual(fuente.buscar({}), [{"url": "x"}])
        self.assertEqual(fuente.cb.metrics.successes, 1)

    def test_resultado_none_es_lista_vacia(self):
        """Una fuente que no devuelve nada responde [] (extend seguro)."""
        fuente = FuenteRobusta(lambda cfg: None, "Prueba")
        self.assertEqual(fuente.buscar({}), [])

    def test_falla_propaga_y_registra(self):
        """El error se propaga (para reportarlo) y alimenta el circuito."""
        def caido(cfg):
            raise ValueError("fuente rota")

        fuente = FuenteRobusta(caido, "Prueba")

        with patch("fuentes.common.time.sleep"):
            with self.assertRaises(ValueError):
                fuente.buscar({})

        self.assertEqual(fuente.cb.metrics.failures, 1)

    def test_circuito_abierto_falla_rapido(self):
        """Con el circuito abierto no se vuelve a llamar a la fuente."""
        llamadas = {"n": 0}

        def caido(cfg):
            llamadas["n"] += 1
            raise ValueError("fuente rota")

        fuente = FuenteRobusta(caido, "Prueba", config={"max_retries": 0})

        with patch("fuentes.common.time.sleep"):
            for _ in range(3):
                with self.assertRaises(ValueError):
                    fuente.buscar({})

        self.assertEqual(llamadas["n"], 3)
        self.assertEqual(fuente.cb.state, CircuitBreakerState.OPEN)

        with self.assertRaises(RuntimeError):
            fuente.buscar({})  # ahora falla de inmediato
        self.assertEqual(llamadas["n"], 3)  # sin nueva llamada

    def test_fabrica_filtra_claves_desconocidas(self):
        """crear_fuente_robusta ignora claves que RetryPolicy no entiende."""
        fuente = crear_fuente_robusta(lambda cfg: [], "X", pausa_segundos=0.7)
        self.assertIsInstance(fuente, FuenteRobusta)
        self.assertEqual(fuente.nombre, "X")


class TestDescargarConCircuito(unittest.TestCase):
    """Integracion del circuito por host en comun.descargar."""

    def setUp(self):
        """Limpia cache y circuitos entre pruebas."""
        comun.limpiar_cache()

    def tearDown(self):
        comun.limpiar_cache()

    @staticmethod
    def _respuesta(url="https://ejemplo.test/pagina"):
        """Mock de urlopen que devuelve un contexto con HTML."""
        respuesta = MagicMock()
        respuesta.status = 200
        respuesta.geturl.return_value = url
        respuesta.read.return_value = b"<html>ok</html>"
        contexto = MagicMock()
        contexto.__enter__.return_value = respuesta
        contexto.__exit__.return_value = False
        return contexto

    def test_exito_cachea_y_no_abre_el_circuito(self):
        """La primera descarga guarda cache y marca el host sano."""
        with patch("urllib.request.urlopen", return_value=self._respuesta()) as mock_urlopen:
            codigo, _, html = comun.descargar("https://ejemplo.test/pagina")
            _, _, html2 = comun.descargar("https://ejemplo.test/pagina")

        self.assertEqual(codigo, 200)
        self.assertEqual(html, "<html>ok</html>")
        self.assertEqual(html2, "<html>ok</html>")
        self.assertEqual(mock_urlopen.call_count, 1)  # segunda viene del cache

        cb = comun._BREAKERS["ejemplo.test"]
        self.assertEqual(cb.state, CircuitBreakerState.CLOSED)

    def test_404_no_abre_el_circuito(self):
        """Un 404 es respuesta del servidor: no cuenta como fallo del host."""
        error_404 = urllib.error.HTTPError(
            "https://ejemplo.test/falta", 404, "Not Found", None, None
        )
        with patch("urllib.request.urlopen", side_effect=error_404):
            with self.assertRaises(urllib.error.HTTPError):
                comun.descargar("https://ejemplo.test/falta", intentos=1)

        cb = comun._BREAKERS["ejemplo.test"]
        self.assertEqual(cb.metrics.failures, 0)
        self.assertTrue(cb.allow_request())

    def test_fallos_seguidos_abren_el_circuito(self):
        """Tres fallos de red abren el circuito del host."""
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("sin red"),
        ):
            for _ in range(3):
                with self.assertRaises(urllib.error.URLError):
                    comun.descargar("https://caida.test/x", intentos=1)

        cb = comun._BREAKERS["caida.test"]
        self.assertEqual(cb.state, CircuitBreakerState.OPEN)

        # La siguiente URL del mismo host falla de inmediato y sin red
        with patch("urllib.request.urlopen") as mock_urlopen:
            with self.assertRaises(RuntimeError) as captura:
                comun.descargar("https://caida.test/y", intentos=1)
            self.assertEqual(mock_urlopen.call_count, 0)

        self.assertIn("circuito abierto", str(captura.exception))

    def test_otro_host_no_se_afecta(self):
        """El circuito es por host: un host caido no bloquea a los demas."""
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("sin red"),
        ):
            for _ in range(3):
                with self.assertRaises(urllib.error.URLError):
                    comun.descargar("https://caida.test/x", intentos=1)

        with patch("urllib.request.urlopen", return_value=self._respuesta()) as mock_urlopen:
            codigo, _, _ = comun.descargar("https://sano.test/pagina")

        self.assertEqual(codigo, 200)
        self.assertEqual(mock_urlopen.call_count, 1)

    def test_limpiar_cache_tambien_limpia_circuitos(self):
        """Al iniciar corrida se resetean cache y circuitos."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.URLError("sin red")
            for _ in range(3):
                with self.assertRaises(urllib.error.URLError):
                    comun.descargar("https://caida.test/x", intentos=1)

        self.assertTrue(comun._BREAKERS)
        comun.limpiar_cache()
        self.assertEqual(comun._BREAKERS, {})
        self.assertEqual(comun._CACHE, {})

    def test_breaker_uno_por_host(self):
        """Dos hosts distintos tienen circuitos distintos."""
        cb1 = comun._breaker("https://a.test/1")
        cb2 = comun._breaker("https://a.test/2")
        cb3 = comun._breaker("https://b.test/1")

        self.assertIs(cb1, cb2)
        self.assertIsNot(cb1, cb3)


if __name__ == "__main__":
    unittest.main()
