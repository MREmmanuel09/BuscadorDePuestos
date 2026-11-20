"""Utilidades comunes: descarga de paginas, pausas y limpieza de texto."""

import ssl
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

from .common import CircuitBreaker, CircuitBreakerConfig

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Encoding": "identity",
    "Accept-Language": "es-CR,es;q=0.9,en;q=0.8",
}

CTX = ssl.create_default_context()

# Cache de paginas de la corrida actual: evita descargar dos veces la misma
# URL (por ejemplo FindJob24h repetido entre corridas del mismo proceso).
_CACHE = {}
_CACHE_MAX = 300

# Circuitos por host: tras N fallos seguidos el host deja de recibir
# peticiones durante un rato (una fuente caida no gasta timeouts en cada
# pagina de la corrida).
_BREAKERS = {}
_BREAKER_MAX_FALLOS = 3
_BREAKER_VENTANA = 120.0


def _breaker(url):
    """Devuelve el circuito del host de 'url' (uno por host y por corrida)."""
    host = urllib.parse.urlsplit(url).netloc
    cb = _BREAKERS.get(host)
    if cb is None:
        cb = _BREAKERS[host] = CircuitBreaker(
            CircuitBreakerConfig(
                max_failures=_BREAKER_MAX_FALLOS,
                duration_seconds=_BREAKER_VENTANA,
            )
        )
    cb.reset()  # si ya paso la ventana, deja el circuito en half_open
    return cb


def limpiar_cache():
    """Vacia la cache de paginas y los circuitos; se llama al iniciar cada corrida."""
    _CACHE.clear()
    _BREAKERS.clear()


def descargar(url, timeout=30, intentos=3):
    """Descarga una pagina y devuelve (codigo HTTP, url final, HTML).

    Reintenta hasta 'intentos' veces con espera creciente (1.5s, 3s...) ante
    timeouts, errores de red y respuestas 5xx; los 4xx se propagan de inmediato
    para no reintentar algo que no existe (p. ej. un 404). Dentro de una misma
    corrida, la misma URL se sirve de la cache.

    Circuit breaker por host: si un host falla _BREAKER_MAX_FALLOS veces
    seguidas, las siguientes URLs del mismo host fallan de inmediato durante
    _BREAKER_VENTANA segundos en lugar de esperar timeouts completos.
    """
    if url in _CACHE:
        return _CACHE[url]

    cb = _breaker(url)
    if not cb.allow_request():
        host = urllib.parse.urlsplit(url).netloc
        raise RuntimeError(f"host bloqueado temporalmente (circuito abierto): {host}")

    ultimo_error = None
    for intento in range(1, intentos + 1):
        req = urllib.request.Request(url, headers=UA)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                resultado = (r.status, r.geturl(), r.read().decode("utf-8", "replace"))
                if len(_CACHE) >= _CACHE_MAX:
                    _CACHE.clear()
                _CACHE[url] = resultado
                cb.record_success()
                return resultado
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500:
                # El servidor responde: el host esta sano, solo la pagina no existe.
                cb.record_success()
                raise
            ultimo_error = e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            ultimo_error = e
        if intento < intentos:
            time.sleep(1.5 * intento)
    cb.record_failure()
    raise ultimo_error


def fetch(url, timeout=30):
    """Descarga una pagina web y devuelve su HTML como texto (con reintentos)."""
    return descargar(url, timeout)[2]


def pausar(segundos):
    """Espera los segundos indicados; no hace nada si son 0 o negativos."""
    if segundos and segundos > 0:
        time.sleep(segundos)


def sin_acentos(texto):
    """Convierte el texto a minusculas y elimina tildes/diacriticos."""
    forma = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in forma if not unicodedata.combining(c))
