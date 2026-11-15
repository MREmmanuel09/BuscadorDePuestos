"""Escrituras atomicas, backups y lectura segura de los archivos de datos."""

import csv
import io
import json
import os
import shutil
from datetime import datetime


def asegurar_directorio(ruta):
    """Crea el directorio indicado (y sus padres) si no existe."""
    if ruta:
        os.makedirs(ruta, exist_ok=True)
    return ruta


def _temporal(ruta):
    """Devuelve una ruta temporal en la misma carpeta que el destino."""
    carpeta = os.path.dirname(os.path.abspath(ruta)) or "."
    asegurar_directorio(carpeta)
    return os.path.join(carpeta, f".{os.path.basename(ruta)}.{os.getpid()}.tmp")


def escribir_texto_atomico(ruta, texto, encoding="utf-8"):
    """Escribe texto en 'ruta' usando un temporal y os.replace."""
    temporal = _temporal(ruta)
    try:
        with open(temporal, "w", encoding=encoding, newline="") as f:
            f.write(texto)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporal, ruta)
    finally:
        if os.path.exists(temporal):
            try:
                os.remove(temporal)
            except OSError:
                pass


def escribir_json_atomico(ruta, datos, indent=2):
    """Serializa 'datos' como JSON y lo guarda de forma atomica."""
    escribir_texto_atomico(
        ruta, json.dumps(datos, ensure_ascii=False, indent=indent) + "\n"
    )


def escribir_csv_atomico(ruta, filas, columnas, delimiter=";", encoding="utf-8-sig"):
    """Escribe filas (diccionarios) como CSV atomico con las columnas indicadas."""
    salida = io.StringIO(newline="")
    escritor = csv.DictWriter(
        salida, fieldnames=columnas, delimiter=delimiter, lineterminator="\r\n"
    )
    escritor.writeheader()
    for fila in filas:
        escritor.writerow({columna: fila.get(columna, "") for columna in columnas})
    escribir_texto_atomico(ruta, salida.getvalue(), encoding=encoding)


def leer_json(ruta, defecto=None):
    """Lee un JSON; devuelve una copia de 'defecto' si falta o esta corrupto."""
    if not os.path.exists(ruta):
        return json.loads(json.dumps(defecto)) if defecto is not None else None
    try:
        with open(ruta, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return json.loads(json.dumps(defecto)) if defecto is not None else None


def copia_seguridad(ruta, directorio, prefijo=None, mantener=10):
    """Copia 'ruta' a 'directorio' con marca de tiempo y rota las copias viejas."""
    if not ruta or not os.path.exists(ruta):
        return None
    asegurar_directorio(directorio)
    prefijo = prefijo or os.path.splitext(os.path.basename(ruta))[0]
    marca = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    destino = os.path.join(
        directorio, f"{prefijo}-{marca}{os.path.splitext(ruta)[1]}"
    )
    try:
        shutil.copy2(ruta, destino)
    except OSError:
        return None
    copias = sorted(
        (
            os.path.join(directorio, nombre)
            for nombre in os.listdir(directorio)
            if nombre.startswith(prefijo + "-")
        ),
        key=lambda ruta_copia: os.path.getmtime(ruta_copia),
    )
    for viejo in copias[: -max(1, mantener)]:
        try:
            os.remove(viejo)
        except OSError:
            pass
    return destino


def rotar_log(ruta, max_bytes=1_000_000, copias=3):
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
    except OSError:
        pass
