"""Cifrado de secretos con DPAPI de Windows, sin dependencias externas."""

import base64
import ctypes
import sys
from ctypes import wintypes


class _BLOB(ctypes.Structure):
    """Estructura DATA_BLOB usada por CryptProtectData y CryptUnprotectData."""

    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def disponible():
    """Indica si el cifrado DPAPI esta disponible en esta plataforma."""
    return sys.platform == "win32"


def _blob(datos):
    """Construye un DATA_BLOB a partir de bytes."""
    buffer = ctypes.create_string_buffer(datos, len(datos))
    return _BLOB(len(datos), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))


def _leer(blob):
    """Copia los bytes del blob de salida y libera la memoria de Windows."""
    try:
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob.pbData)


def _transformar(datos, proteger):
    """Cifra o descifra bytes con DPAPI."""
    if not disponible():
        raise OSError("DPAPI solo esta disponible en Windows")
    entrada = _blob(datos)
    salida = _BLOB()
    funcion = (
        ctypes.windll.crypt32.CryptProtectData
        if proteger
        else ctypes.windll.crypt32.CryptUnprotectData
    )
    if not funcion(
        ctypes.byref(entrada), None, None, None, None, 0, ctypes.byref(salida)
    ):
        raise ctypes.WinError()
    return _leer(salida)


def cifrar(texto):
    """Cifra un texto con DPAPI y devuelve base64 ('' si no se puede)."""
    if not texto or not disponible():
        return ""
    try:
        return base64.b64encode(_transformar(texto.encode("utf-8"), True)).decode(
            "ascii"
        )
    except Exception:
        return ""


def descifrar(valor):
    """Descifra un base64 creado por cifrar(); devuelve '' si falla."""
    if not valor or not disponible():
        return ""
    try:
        return _transformar(base64.b64decode(valor), False).decode("utf-8")
    except Exception:
        return ""
