"""Utilidades de resiliencia para las fuentes externas.

- **RetryPolicy**: reintentos con espera exponencial y jitter.
- **CircuitBreaker**: tras N fallos seguidos deja de intentar un host
  durante un tiempo (evita esperar timeouts completos en cada pagina de
  una fuente caida).
- **FuenteRobusta**: envuelve cualquier funcion de fuente con ambos
  mecanismos para quien la necesite reutilizar.
"""

import logging
import random
import time
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# ============================================================
# Configuracion por defecto de reintentos
# ============================================================
DEFAULT_RETRY_CONFIG = {
    "max_retries": 3,
    "base_delay": 1.0,       # segundos entre intentos consecutivos
    "backoff_factor": 2.0,   # multiplicador exponencial (1s, 2s, 4s...)
    "jitter_range": 0.5,     # +/- 50% de jitter para no sincronizar reintentos
}


# ============================================================
# Circuit Breaker
# ============================================================
class CircuitBreakerState:
    """Estados del interruptor: cerrado (normal), abierto (bloqueado)
    y medio abierto (permite una prueba de recuperacion)."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerMetrics:
    """Contadores observables del interruptor."""

    successes: int = 0
    failures: int = 0
    last_failure_time: float = 0.0


@dataclass
class CircuitBreakerConfig:
    """Umbral de fallos y ventana de bloqueo."""

    max_failures: int = 3
    duration_seconds: float = 60.0


class CircuitBreaker:
    """Interrumpidor de circuito contra fallos en cascada de un servicio externo.

    Estados:
      - closed: normal, las peticiones pasan.
      - open: fallos recientes, las peticiones se rechazan de inmediato.
      - half_open: paso la ventana, se permite UNA prueba de recuperacion.
    """

    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        self.config = config or CircuitBreakerConfig()
        self.metrics = CircuitBreakerMetrics()
        self._state = CircuitBreakerState.CLOSED

    @property
    def state(self) -> str:
        """Estado actual como texto ('closed', 'open' o 'half_open')."""
        return self._state

    def record_success(self):
        """Registra una llamada exitosa y cierra el circuito si estaba a prueba."""
        self.metrics.successes += 1
        self.metrics.failures = 0
        if self._state == CircuitBreakerState.HALF_OPEN:
            logger.debug("CircuitBreaker -> CLOSED (recuperacion exitosa)")
            self._state = CircuitBreakerState.CLOSED

    def record_failure(self):
        """Registra un fallo; abre el circuito al llegar al umbral."""
        self.metrics.failures += 1
        self.metrics.last_failure_time = time.time()

        if self._state == CircuitBreakerState.HALF_OPEN:
            logger.warning("CircuitBreaker -> OPEN (fallo durante la recuperacion)")
            self._state = CircuitBreakerState.OPEN
        elif self.metrics.failures >= self.config.max_failures:
            logger.error(
                f"CircuitBreaker -> OPEN ({self.metrics.failures}/{self.config.max_failures})"
            )
            self._state = CircuitBreakerState.OPEN

    def reset(self):
        """Pasa a half_open si ya transcurrio la ventana de bloqueo."""
        if self._state == CircuitBreakerState.OPEN:
            elapsed = time.time() - self.metrics.last_failure_time
            if elapsed >= self.config.duration_seconds:
                logger.debug("CircuitBreaker -> HALF_OPEN (prueba de recuperacion)")
                self._state = CircuitBreakerState.HALF_OPEN
                self.metrics.successes = 0

    def allow_request(self) -> bool:
        """True si la peticion puede pasar; llama a reset() antes en
        circuitos abiertos para evaluar la recuperacion."""
        if self._state == CircuitBreakerState.CLOSED:
            return True
        if self._state == CircuitBreakerState.HALF_OPEN:
            logger.debug("CircuitBreaker HALF_OPEN -> permite 1 prueba")
            return True
        logger.warning("CircuitBreaker OPEN -> peticion rechazada")
        return False

    def __repr__(self):
        return (
            f"CircuitBreaker(state={self._state}, "
            f"failures={self.metrics.failures})"
        )


# ============================================================
# Politica de reintentos con espera exponencial y jitter
# ============================================================
class RetryPolicy:
    """Reintentos con espera exponencial y jitter opcional."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        backoff_factor: float = 2.0,
        jitter_range: float = 0.5,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.backoff_factor = backoff_factor
        self.jitter_range = jitter_range

    def wait_time(self, intento: int) -> float:
        """Espera del proximo reintento: base * factor^intento +/- jitter."""
        delay = self.base_delay * (self.backoff_factor ** intento)
        jitter = random.uniform(-1, 1) * self.jitter_range
        return max(0.1, delay + jitter)

    def execute_with_retry(self, func: Callable, *args, **kwargs):
        """Ejecuta 'func' reintentando hasta max_retries veces.

        La espera entre intentos crece exponencialmente; si se agotan los
        reintentos se propaga la ultima excepcion.
        """
        ultimo_error = None
        for intento in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                ultimo_error = e
                if intento < self.max_retries:
                    espera = self.wait_time(intento)
                    logger.warning(
                        f"Reintento {intento + 1}/{self.max_retries} "
                        f"tras {espera:.2f}s: {type(e).__name__}"
                    )
                    time.sleep(espera)
        raise ultimo_error  # type: ignore[misc]


# ============================================================
# Envoltorio de fuente con proteccion
# ============================================================
class FuenteRobusta:
    """Envuelve una funcion de fuente con CircuitBreaker + RetryPolicy.

    Uso:
        fuente = FuenteRobusta(linkedin.buscar, "LinkedIn")
        ofertas = fuente.buscar(cfg)
    """

    def __init__(
        self,
        fuente: Callable,
        nombre: str = "fuente",
        config: Optional[dict] = None,
    ):
        self._func = fuente
        self.nombre = nombre
        self.cb = CircuitBreaker(CircuitBreakerConfig(max_failures=3, duration_seconds=60))
        permitidas = ("max_retries", "base_delay", "backoff_factor", "jitter_range")
        opciones = {k: v for k, v in (config or DEFAULT_RETRY_CONFIG).items() if k in permitidas}
        self.retry_policy = RetryPolicy(**opciones)

    def buscar(self, cfg: dict):
        """Consulta la fuente con reintentos; registra el resultado en el
        circuito y propaga el error si se agotan los reintentos."""
        if not self.cb.allow_request():
            raise RuntimeError(f"{self.nombre} bloqueado (circuito abierto)")

        try:
            resultado = self.retry_policy.execute_with_retry(self._func, cfg)
        except Exception:
            self.cb.record_failure()
            logger.error(f"{self.nombre} fallo tras los reintentos")
            raise
        self.cb.record_success()
        return resultado if resultado is not None else []

    def __repr__(self):
        return f"FuenteRobusta({self.nombre}, cb={self.cb})"


# ============================================================
# Fabrica
# ============================================================
def crear_fuente_robusta(funcion: Callable, nombre: str = None, **kwargs) -> FuenteRobusta:
    """Crea una FuenteRobusta a partir de la funcion original de una fuente.

    Ejemplo:
        import fuentes.linkedin as linkedin
        fuente = crear_fuente_robusta(linkedin.buscar, "LinkedIn")
    """
    nombre = nombre or getattr(funcion, "__name__", "fuente")
    return FuenteRobusta(funcion, nombre, config=kwargs)
