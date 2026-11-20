"""Escrituras atomicas, backups y lectura segura de los archivos de datos.

- Escritura CSV/JSON con validación de esquema y atomicidad real (temporal + replace).
- Rotación de log con tamaño configurable.
- Copias de seguridad rotativas con retención configurable.
- Lectura defensiva: nunca falla, siempre retorna un valor por defecto seguro.
"""

import csv
import io
import json
import logging
import os
import shutil
from datetime import datetime
from typing import Any, Dict, List

logger = logging.getLogger("buscador")

# ============================================================
# Columnas del CSV de ofertas (para validación de esquema)
# ============================================================
CSV_COLUMNS = ["fecha", "fuente", "titulo", "ubicacion", "empresa", "url", "estado_envio"]


# ============================================================
# Validación de Esquema CSV
# ============================================================
def validacion_esquema_csv(ofertas: List[Dict[str, Any]], columnas: List[str] = None) -> tuple[int, List[str]]:
    """Valida que las ofertas tienen los campos esperados.

    Retorna (conteo_invalidas, lista_de_errores).
    """
    columnas = columnas or CSV_COLUMNS
    errores = []
    invalidas = 0

    for i, oferta in enumerate(ofertas):
        campos_faltantes = [c for c in columnas if c not in oferta]
        if campos_faltantes:
            errores.append(
                f"Oferta {i}: faltan campos - {', '.join(campos_faltantes)} (url={oferta.get('url', '?')})"
            )
            invalidas += 1

    return invalidas, errores


# ============================================================
# Estructura de Archivo Temporal y Atomicidad
# ============================================================
def asegurar_directorio(ruta: str):
    """Crea el directorio indicado (y sus padres) si no existe."""
    if ruta:
        os.makedirs(ruta, exist_ok=True)
    return ruta


def _temporal(ruta: str) -> str:
    """Devuelve una ruta temporal .tmp en la misma carpeta que el destino.

    Incluye el PID para que dos procesos no escriban el mismo temporal.
    """
    carpeta = os.path.dirname(os.path.abspath(ruta)) or "."
    asegurar_directorio(carpeta)
    nombre = f".{os.path.basename(ruta)}.{os.getpid()}.tmp"
    return os.path.join(carpeta, nombre)


# ============================================================
# Escritura Atómica (CSV/JSON/Texto)
# ============================================================
def escribir_texto_atomico(ruta: str, texto: str, encoding: str = "utf-8"):
    """Escribe texto en 'ruta' usando un temporal y os.replace (atomico)."""
    temporal = _temporal(ruta)
    try:
        with open(temporal, "w", encoding=encoding, newline="") as f:
            f.write(texto)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporal, ruta)
        return True
    except Exception as e:
        if os.path.exists(temporal):
            try:
                os.remove(temporal)
            except OSError:
                pass
        raise RuntimeError(f"Error atomico en {ruta}: {e}") from e


def escribir_json_atomico(ruta: str, datos: Dict[str, Any], indent: int = 2):
    """Serializa 'datos' como JSON y lo guarda de forma atomica."""
    try:
        texto = json.dumps(datos, ensure_ascii=False, indent=indent) + "\n"
    except (TypeError, ValueError) as e:
        raise RuntimeError(f"No se puede serializar a JSON: {e}") from e

    return escribir_texto_atomico(ruta, texto)


def escribir_csv_atomico(
    ruta: str,
    filas: List[Dict[str, Any]],
    columnas: List[str] = None,
    delimiter: str = ";",
    encoding: str = "utf-8-sig",
):
    """Escribe filas (diccionarios) como CSV atomico con validación de esquema.

    Validación: verifica que cada fila tenga las columnas esperadas antes de escribir.
    """
    columnas = columnas or CSV_COLUMNS

    # Validar esquema antes de escribir
    _, errores = validacion_esquema_csv(filas, columnas)
    if errores:
        raise ValueError(
            f"Validacion de esquema fallo: {len(errores)} error(es). "
            f"Primero: {errores[0]}"
        )

    salida = io.StringIO(newline="")
    escritor = csv.DictWriter(
        salida, fieldnames=columnas, delimiter=delimiter, lineterminator="\r\n"
    )
    escritor.writeheader()
    for fila in filas:
        escritor.writerow({columna: fila.get(columna, "") for columna in columnas})

    texto = salida.getvalue()
    return escribir_texto_atomico(ruta, texto, encoding=encoding)


def leer_json(ruta: str, defecto: Any = None):
    """Lee un JSON; retorna una copia de 'defecto' si falta o está corrupto."""
    if not os.path.exists(ruta):
        return json.loads(json.dumps(defecto)) if defecto is not None else None

    try:
        with open(ruta, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return json.loads(json.dumps(defecto)) if defecto is not None else None


def leer_csv(ruta: str) -> List[Dict[str, Any]]:
    """Lee un CSV con separador ';' y devuelve sus filas como diccionarios."""
    if not os.path.exists(ruta):
        return []

    try:
        with open(ruta, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")
            return list(reader)
    except Exception as e:
        logger.warning(f"Error leyendo {ruta}: {e}")
        return []


# ============================================================
# Copias de Seguridad Rotativas
# ============================================================
def copia_seguridad(ruta: str, directorio: str, prefijo: str = None, mantener: int = 10):
    """Copia 'ruta' a 'directorio' con marca de tiempo y rota las copias viejas.

    Retorna la ruta del backup creado o None si hubo error.
    """
    if not ruta or not os.path.exists(ruta):
        return None

    asegurar_directorio(directorio)
    prefijo = prefijo or os.path.splitext(os.path.basename(ruta))[0]
    extension = os.path.splitext(ruta)[1]
    marca = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    destino = os.path.join(directorio, f"{prefijo}-{marca}{extension}")
    contador = 1
    while os.path.exists(destino):
        destino = os.path.join(
            directorio, f"{prefijo}-{marca}-{contador}{extension}"
        )
        contador += 1

    try:
        shutil.copy2(ruta, destino)
    except OSError as e:
        logger.error(f"Error creando backup {destino}: {e}")
        return None

    # Rotar copias viejas
    copias = sorted(
        (
            os.path.join(directorio, nombre)
            for nombre in os.listdir(directorio)
            if nombre.startswith(prefijo + "-") and nombre.endswith(extension)
        ),
        key=lambda ruta_copia: os.path.getmtime(ruta_copia),
    )

    for viejo in copias[:-max(1, mantener)]:
        try:
            os.remove(viejo)
        except OSError as e:
            logger.warning(f"Error borrando backup viejo {viejo}: {e}")

    return destino


def rotar_log(ruta: str, max_bytes: int = 1_000_000, copias: int = 3):
    """Rota un log cuando supera 'max_bytes' (ruta.1, ruta.2...)."""
    try:
        if not os.path.exists(ruta) or os.path.getsize(ruta) < max_bytes:
            return
        for indice in range(copias - 1, 0, -1):
            origen = f"{ruta}.{indice}"
            destino = f"{ruta}.{indice + 1}"
            if os.path.exists(origen):
                os.replace(origen, destino)
        os.replace(ruta, f"{ruta}.1")
    except OSError as e:
        logger.warning(f"Error rotando log {ruta}: {e}")
