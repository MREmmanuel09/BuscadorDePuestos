"""Bloqueo de proceso para evitar escrituras simultaneas de la app y la tarea."""

import contextlib
import os
import sys
import threading
import time

_HILO = threading.RLock()
_PROFUNDIDAD = 0


def _ruta(directorio, nombre):
    """Devuelve la ruta del archivo de bloqueo, creando el directorio."""
    os.makedirs(directorio, exist_ok=True)
    return os.path.join(directorio, f".{nombre}.lock")


def _adquirir(ruta, timeout):
    """Abre y bloquea el archivo de bloqueo, esperando hasta 'timeout' segundos."""
    manejador = open(ruta, "a+b")
    if os.path.getsize(ruta) == 0:
        manejador.write(b"0")
        manejador.flush()
    inicio = time.monotonic()
    while True:
        try:
            if sys.platform == "win32":
                import msvcrt

                manejador.seek(0)
                msvcrt.locking(manejador.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(manejador.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return manejador
        except OSError:
            if time.monotonic() - inicio >= timeout:
                manejador.close()
                raise TimeoutError(
                    "Otro proceso esta usando el buscador; intenta de nuevo."
                )
            time.sleep(0.2)


def _liberar(manejador):
    """Libera el bloqueo y cierra el archivo."""
    try:
        if sys.platform == "win32":
            import msvcrt

            manejador.seek(0)
            msvcrt.locking(manejador.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(manejador.fileno(), fcntl.LOCK_UN)
    finally:
        manejador.close()


@contextlib.contextmanager
def proceso(directorio, nombre="buscador", timeout=10.0):
    """Adquiere el bloqueo del proceso; admite llamadas anidadas en el mismo hilo."""
    global _PROFUNDIDAD
    with _HILO:
        if _PROFUNDIDAD > 0:
            _PROFUNDIDAD += 1
            try:
                yield
            finally:
                _PROFUNDIDAD -= 1
            return
        manejador = _adquirir(_ruta(directorio, nombre), timeout)
        _PROFUNDIDAD = 1
        try:
            yield
        finally:
            _PROFUNDIDAD = 0
            _liberar(manejador)
