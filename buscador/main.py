"""Nucleo del buscador: configura, consulta las fuentes, filtra, guarda y reporta.

Este modulo contiene la logica principal del sistema. La aplicacion de escritorio
(app.pyw) y los scripts de terminal (eliminar.py, verificar.py) importan sus
funciones; la tarea programada de Windows ejecuta main() directamente.
"""
import csv
import html
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import bloqueo
import secretos
from almacen import (
    copia_seguridad,
    escribir_csv_atomico,
    escribir_json_atomico,
    escribir_texto_atomico,
    leer_json,
    rotar_log,
)
from compatibilidad import (
    CASTIGO_DEFECTO,
    CATEGORIA_COMPATIBLE,
    CATEGORIA_DESCARTADA,
    CATEGORIA_RELACIONADA,
    COMPATIBILIDAD_MINIMA_DEFECTO,
    COMPATIBILIDAD_RELACIONADA_DEFECTO,
    CONTEXTO_DEFECTO,
    EXCLUIDAS_DEFECTO,
    FUERTES_DEFECTO,
    INCOMPATIBLES_DEFECTO,
    MEDIAS_DEFECTO,
    META_PUNTOS_DEFECTO,
    puntuar,
)
from fuentes import computrabajo, findjob24h, linkedin, trabajo_org
from fuentes.comun import limpiar_cache, sin_acentos
from notificar import enviar_correo, toast
from puestos import ANCLAS_DEFECTO

# ---------- Rutas de los archivos de datos ----------
DATA = os.path.join(BASE, "data")
CONFIG_PATH = os.path.join(BASE, "config.json")
EJEMPLO_CONFIG_PATH = os.path.join(BASE, "config.example.json")
VISTAS_PATH = os.path.join(DATA, "vistas.json")
OFERTAS_PATH = os.path.join(DATA, "ofertas.csv")
REPORTE_PATH = os.path.join(DATA, "reporte.html")
LOG_PATH = os.path.join(DATA, "historial.log")
NEGRA_PATH = os.path.join(DATA, "lista_negra.json")
VERIFICADO_PATH = os.path.join(DATA, "verificado.json")

# ---------- Valores por defecto (se usan si falta alguna clave en config.json) ----------
REMOTO = ["remoto", "teletrabajo", "hibrido", "remote", "home office", "desde casa", "work from home"]
FUENTES = [computrabajo, trabajo_org, findjob24h, linkedin]
COLUMNAS = ["fecha", "fuente", "titulo", "ubicacion", "empresa", "url", "estado_envio"]


VERSION_CONFIG = 2

DEFECTO_CONFIG = {
    "config_version": VERSION_CONFIG,
    "palabras_clave_busqueda": [
        "soporte ti",
        "soporte tecnico",
        "tecnico informatico",
        "help desk",
        "service desk",
        "mesa de ayuda",
        "soporte de redes",
        "tecnico en redes",
        "redes y telecomunicaciones",
        "administrador de sistemas",
        "infraestructura ti",
        "soporte en sitio",
        "tecnico de campo",
        "cableado estructurado",
        "data center",
        "it support",
        "technical support",
        "desktop support",
        "network technician",
        "noc analyst",
        "sysadmin",
        "field service technician",
        "application support",
        "cybersecurity analyst",
        "soporte n1",
        "soporte n2",
        "helpdesk",
        "network support",
        "noc",
        "administrador de redes",
        "soporte de infraestructura",
        "soporte microsoft 365",
        "field support technician",
        "it help desk",
    ],
    "palabras_fuertes": list(FUERTES_DEFECTO),
    "palabras_clave": list(MEDIAS_DEFECTO),
    "palabras_contexto": list(CONTEXTO_DEFECTO),
    "palabras_castigo": list(CASTIGO_DEFECTO),
    "palabras_excluidas": list(EXCLUIDAS_DEFECTO),
    "incompatibles": list(INCOMPATIBLES_DEFECTO),
    "anclas_puesto": list(ANCLAS_DEFECTO),
    "palabras_remoto": [
        "remoto", "teletrabajo", "hibrido", "remote", "home office",
        "desde casa", "work from home",
    ],
    "zonas": ["alajuela", "san jose"],
    "incluir_remoto": True,
    "compatibilidad_minima": COMPATIBILIDAD_MINIMA_DEFECTO,
    "compatibilidad_relacionada": COMPATIBILIDAD_RELACIONADA_DEFECTO,
    "meta_puntos": META_PUNTOS_DEFECTO,
    "dias_retencion": 15,
    "dias_lista_negra": 15,
    "verificar_en_busqueda": True,
    "verificar_max_por_corrida": 30,
    "linkedin_ubicaciones": ["Costa Rica", "Alajuela, Costa Rica"],
    "max_paginas_por_busqueda": 1,
    "max_paginas_trabajo_org": 8,
    "consultas_fijas": 8,
    "consultas_por_corrida": 16,
    "meta_postulaciones_dia": 5,
    "pausa_segundos": 0.7,
    "notificar_toast": True,
    "abrir_reporte": False,
    "app_auto_minutos": 0,
    "correo": {
        "activo": False,
        "smtp": "smtp.gmail.com",
        "puerto": 465,
        "usuario": "",
        "clave_app": "",
        "clave_app_cifrada": "",
        "destino": "",
    },
}


# ---------- Configuracion ----------
def _lista_texto(valor, defecto):
    """Normaliza una lista de textos: recorta, quita vacios y repetidos."""
    if not isinstance(valor, (list, tuple)):
        return list(defecto)
    salida = []
    vistos = set()
    for item in valor:
        if not isinstance(item, str):
            continue
        texto = item.strip()
        clave = texto.casefold()
        if texto and clave not in vistos:
            salida.append(texto)
            vistos.add(clave)
    return salida


def _entero(valor, defecto, minimo=None, maximo=None):
    """Convierte a entero y aplica limites; usa el defecto si no es valido."""
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        numero = defecto
    if minimo is not None:
        numero = max(minimo, numero)
    if maximo is not None:
        numero = min(maximo, numero)
    return numero


def _flotante(valor, defecto, minimo=None):
    """Convierte a flotante y aplica el minimo; usa el defecto si no es valido."""
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        numero = defecto
    if minimo is not None:
        numero = max(minimo, numero)
    return numero


def _booleano(valor, defecto):
    """Interpreta booleanos de JSON y cadenas habituales como 'true' o 'si'."""
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)):
        return bool(valor)
    if isinstance(valor, str):
        return valor.strip().lower() in ("1", "true", "si", "sí", "yes", "on")
    return defecto


def normalizar_config(datos):
    """Valida y completa el config; nunca lanza por un valor invalido."""
    datos = datos if isinstance(datos, dict) else {}
    salida = dict(DEFECTO_CONFIG)
    salida.update(datos)
    listas = (
        "palabras_clave_busqueda", "palabras_fuertes", "palabras_clave",
        "palabras_contexto", "palabras_castigo", "palabras_excluidas",
        "incompatibles", "anclas_puesto", "palabras_remoto", "zonas",
        "linkedin_ubicaciones",
    )
    for clave in listas:
        salida[clave] = _lista_texto(salida.get(clave), DEFECTO_CONFIG[clave])
    salida["compatibilidad_minima"] = _entero(
        salida.get("compatibilidad_minima"), COMPATIBILIDAD_MINIMA_DEFECTO, 0, 100
    )
    salida["compatibilidad_relacionada"] = _entero(
        salida.get("compatibilidad_relacionada"),
        COMPATIBILIDAD_RELACIONADA_DEFECTO,
        0,
        salida["compatibilidad_minima"],
    )
    salida["meta_puntos"] = _entero(salida.get("meta_puntos"), META_PUNTOS_DEFECTO, 1)
    salida["dias_retencion"] = _entero(salida.get("dias_retencion"), 15, 1)
    salida["dias_lista_negra"] = _entero(salida.get("dias_lista_negra"), 15, 1)
    salida["verificar_max_por_corrida"] = _entero(
        salida.get("verificar_max_por_corrida"), 30, 1
    )
    salida["max_paginas_por_busqueda"] = _entero(
        salida.get("max_paginas_por_busqueda"), 1, 1, 20
    )
    salida["max_paginas_trabajo_org"] = _entero(
        salida.get("max_paginas_trabajo_org"), 8, 1, 30
    )
    salida["consultas_fijas"] = _entero(
        salida.get("consultas_fijas"), 8, 0, 100
    )
    salida["consultas_por_corrida"] = _entero(
        salida.get("consultas_por_corrida"), 16, 0, 100
    )
    if salida["consultas_por_corrida"] and salida["consultas_fijas"] > salida["consultas_por_corrida"]:
        salida["consultas_fijas"] = salida["consultas_por_corrida"]
    salida["meta_postulaciones_dia"] = _entero(
        salida.get("meta_postulaciones_dia"), 5, 0, 50
    )
    salida["pausa_segundos"] = _flotante(salida.get("pausa_segundos"), 0.7, 0.0)
    salida["app_auto_minutos"] = _entero(
        salida.get("app_auto_minutos"), 0, 0, 24 * 60
    )
    for clave in (
        "incluir_remoto", "verificar_en_busqueda", "notificar_toast", "abrir_reporte",
    ):
        salida[clave] = _booleano(salida.get(clave), DEFECTO_CONFIG[clave])
    correo = salida.get("correo")
    correo = correo if isinstance(correo, dict) else {}
    correo_normalizado = dict(DEFECTO_CONFIG["correo"])
    correo_normalizado.update(correo)
    correo_normalizado["activo"] = _booleano(
        correo_normalizado.get("activo"), False
    )
    correo_normalizado["puerto"] = _entero(correo_normalizado.get("puerto"), 465, 1, 65535)
    for clave in ("smtp", "usuario", "clave_app", "clave_app_cifrada", "destino"):
        correo_normalizado[clave] = str(correo_normalizado.get(clave) or "").strip()
    salida["correo"] = correo_normalizado
    # Claves que ya no se usan: FindJob24h ahora lee el listado, sin abrir detalles.
    for obsoleta in ("max_detalles_findjob24h", "max_paginas_findjob24h"):
        salida.pop(obsoleta, None)
    salida["config_version"] = VERSION_CONFIG
    return salida


def _migrar_secreto(datos):
    """Cifra la clave SMTP en texto plano y la mueve a 'clave_app_cifrada'."""
    correo = datos.get("correo")
    if not isinstance(correo, dict):
        return False
    if correo.get("clave_app") and not correo.get("clave_app_cifrada"):
        cifrada = secretos.cifrar(correo["clave_app"])
        if cifrada:
            correo["clave_app_cifrada"] = cifrada
            correo["clave_app"] = ""
            return True
    return False


def guardar_config(datos):
    """Valida y guarda config.json de forma atomica, con backup de la version previa."""
    normalizado = normalizar_config(datos)
    with bloqueo.proceso(DATA, "buscador"):
        os.makedirs(DATA, exist_ok=True)
        if os.path.exists(CONFIG_PATH):
            copia_seguridad(
                CONFIG_PATH, os.path.join(DATA, "backups"), "config", mantener=10
            )
        escribir_json_atomico(CONFIG_PATH, normalizado)
    return normalizado


def asegurar_config():
    """Crea config.json la primera vez (copiando config.example.json o usando DEFECTO_CONFIG)."""
    if os.path.exists(CONFIG_PATH):
        return
    datos = leer_json(EJEMPLO_CONFIG_PATH, None)
    if not isinstance(datos, dict):
        datos = dict(DEFECTO_CONFIG)
    guardar_config(datos)


def cargar_config():
    """Lee config.json, lo normaliza y cifra la clave SMTP si estaba en texto plano."""
    asegurar_config()
    datos = leer_json(CONFIG_PATH, {})
    normalizado = normalizar_config(datos)
    cambio = normalizado != datos
    if _migrar_secreto(normalizado):
        cambio = True
    if cambio:
        guardar_config(normalizado)
    return normalizado


# ---------- Lectura y escritura de datos ----------
def cargar_vistas():
    """Devuelve {clave_url: fecha} de las ofertas ya vistas; dict vacio si falla."""
    datos = leer_json(VISTAS_PATH, {})
    return datos.get("urls", datos) if isinstance(datos, dict) else {}


def guardar_vistas(vistas):
    """Guarda el diccionario de ofertas vistas en vistas.json de forma atomica."""
    with bloqueo.proceso(DATA, "buscador"):
        escribir_json_atomico(VISTAS_PATH, {"urls": vistas}, indent=1)


def cargar_verificado():
    """Devuelve {clave_url: fecha} de la ultima verificacion de disponibilidad."""
    datos = leer_json(VERIFICADO_PATH, {})
    return datos.get("urls", datos) if isinstance(datos, dict) else {}


def guardar_verificado(verificado):
    """Guarda el diccionario de verificaciones en verificado.json de forma atomica."""
    with bloqueo.proceso(DATA, "buscador"):
        escribir_json_atomico(VERIFICADO_PATH, {"urls": verificado}, indent=1)


def cargar_ofertas():
    """Lee ofertas.csv (separador ';') y devuelve la lista de filas como diccionarios."""
    if not os.path.exists(OFERTAS_PATH):
        return []
    with open(OFERTAS_PATH, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def clave_url(url):
    """Normaliza una URL para usarla como clave: sin #final, sin espacios y en minusculas."""
    return url.split("#", 1)[0].strip().lower()


def guardar_ofertas(ofertas):
    """Reescribe ofertas.csv completo de forma atomica con la lista dada."""
    with bloqueo.proceso(DATA, "buscador"):
        escribir_csv_atomico(OFERTAS_PATH, ofertas, COLUMNAS)


def cargar_lista_negra():
    """Lee lista_negra.json migrando al formato {hasta, titulo, fuente} si era el viejo."""
    datos = leer_json(NEGRA_PATH, {})
    urls = datos.get("urls", datos) if isinstance(datos, dict) else {}
    salida = {}
    cambiado = False
    for k, v in urls.items():
        if isinstance(v, dict) and "hasta" in v:
            salida[k] = v
        else:
            salida[k] = {
                "hasta": v if isinstance(v, str) else "",
                "titulo": "",
                "fuente": "",
            }
            cambiado = True
    if cambiado:
        guardar_lista_negra(salida)
    return salida


def guardar_lista_negra(negra):
    """Guarda TODO el diccionario de la lista negra de forma atomica."""
    with bloqueo.proceso(DATA, "buscador"):
        escribir_json_atomico(NEGRA_PATH, {"urls": negra}, indent=1)


def purgar_lista_negra():
    """Elimina de la lista negra las entradas cuya fecha 'hasta' ya paso y devuelve las vivas."""
    negra = cargar_lista_negra()
    hoy = datetime.now().strftime("%Y-%m-%d")
    vivas = {k: v for k, v in negra.items() if (v.get("hasta") or "") >= hoy}
    if len(vivas) != len(negra):
        guardar_lista_negra(vivas)
    return vivas


# ---------- Eliminaciones y lista negra ----------
def dias_lista_negra():
    """Devuelve cuantos dias dura la lista negra (clave del config, defecto 15)."""
    try:
        return int(cargar_config().get("dias_lista_negra", 15))
    except Exception:
        return 15


def pasar_a_lista_negra(items):
    """Pone URLs en lista negra con titulo y fuente. items: dicts con url, titulo, fuente.

    Devuelve la fecha de expiracion (YYYY-MM-DD) o None si no habia URLs.
    """
    claves = {clave_url(i.get("url", "")) for i in items if i.get("url")}
    if not claves:
        return None
    info = {clave_url(i.get("url", "")): i for i in items}
    vistas = cargar_vistas()
    quitadas = [k for k in vistas if k in claves]
    for k in quitadas:
        vistas.pop(k)
    if quitadas:
        guardar_vistas(vistas)
    negra = purgar_lista_negra()
    expira = (datetime.now() + timedelta(days=dias_lista_negra())).strftime("%Y-%m-%d")
    for k in claves:
        i = info.get(k, {})
        negra[k] = {
            "hasta": expira,
            "titulo": i.get("titulo", ""),
            "fuente": i.get("fuente", ""),
        }
    guardar_lista_negra(negra)
    return expira


def purgar_ofertas(dias):
    """Borra del CSV las ofertas con mas de N dias (las marcadas con estado se conservan).

    Las borradas pasan a la lista negra. Devuelve (total_antes, cuantas_borradas).
    """
    if not dias or not os.path.exists(OFERTAS_PATH):
        return 0, 0
    with bloqueo.proceso(DATA, "buscador"):
        ofertas = cargar_ofertas()
        if not ofertas:
            return 0, 0
        limite = (datetime.now() - timedelta(days=int(dias))).strftime("%Y-%m-%d")
        conservadas = []
        borradas = 0
        items = []
        for o in ofertas:
            fecha = (o.get("fecha") or "").strip()
            marcada = (o.get("estado_envio") or "").strip()
            if fecha and fecha < limite and not marcada:
                borradas += 1
                items.append(
                    {
                        "url": o.get("url", ""),
                        "titulo": o.get("titulo", ""),
                        "fuente": o.get("fuente", ""),
                    }
                )
            else:
                conservadas.append(o)
        if borradas:
            copia_seguridad(
                OFERTAS_PATH, os.path.join(DATA, "backups"), "ofertas", mantener=10
            )
            guardar_ofertas(conservadas)
            expira = pasar_a_lista_negra(items)
            registrar(f"PURGA dias={dias} borradas={borradas} negra_hasta={expira}")
        return len(ofertas), borradas


def eliminar_ofertas(urls):
    """Elimina del CSV las ofertas indicadas y las pasa a la lista negra. Devuelve cuantas borró."""
    claves = {clave_url(u) for u in urls if u}
    if not claves:
        return 0
    with bloqueo.proceso(DATA, "buscador"):
        ofertas = cargar_ofertas()
        items = [
            {
                "url": o.get("url", ""),
                "titulo": o.get("titulo", ""),
                "fuente": o.get("fuente", ""),
            }
            for o in ofertas
            if clave_url(o.get("url", "")) in claves
        ]
        restantes = [o for o in ofertas if clave_url(o.get("url", "")) not in claves]
        borradas = len(ofertas) - len(restantes)
        if borradas:
            copia_seguridad(
                OFERTAS_PATH, os.path.join(DATA, "backups"), "ofertas", mantener=10
            )
            guardar_ofertas(restantes)
        expira = pasar_a_lista_negra(items)
        registrar(f"ELIMINADO urls={len(claves)} filas={borradas} negra_hasta={expira}")
        return borradas


# ---------- Reporte y registro ----------
def refrescar_reporte(borradas=0):
    """Regenera reporte.html con los datos actuales; los errores solo se anotan en el log."""
    try:
        cfg = cargar_config()
        todas = cargar_ofertas()
        hoy = datetime.now().strftime("%Y-%m-%d")
        nuevas = [o for o in todas if (o.get("fecha") or "") == hoy]
        escribir_reporte(
            nuevas,
            todas,
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            int(cfg.get("dias_retencion", 15)),
            borradas,
        )
    except Exception as e:
        registrar(f"aviso refrescar reporte {type(e).__name__}")


def _titulo_vencido(titulo, hoy=None):
    """Detecta un 'hasta el DD/MM/YYYY' ya pasado en el titulo de la oferta.

    Algunas fuentes dejan publicadas vacantes temporales con la fecha de cierre
    en el propio titulo. Es evidencia positiva de que ya no aplica, sin abrir
    la pagina.
    """
    hoy = hoy or datetime.now().date()
    texto = sin_acentos(str(titulo or ""))
    for coincidencia in re.finditer(
        r"hasta\s+(?:el\s+)?(\d{1,2})[/-](\d{1,2})[/-](\d{4})", texto
    ):
        try:
            fecha = datetime(
                int(coincidencia.group(3)),
                int(coincidencia.group(2)),
                int(coincidencia.group(1)),
            ).date()
        except ValueError:
            continue
        if fecha < hoy:
            return True
    return False


def pasa_filtros(oferta, zonas, cfg, resultado=None):
    """Decide si una oferta cruda entra al CSV.

    Primero la puntua el motor de compatibilidad: las Descartadas (palabras
    excluidas/incompatibles, otro rubro o sin ancla de TI) nunca entran; las
    Compatibles y Relacionadas siguen. Luego se revisa la zona: zona aceptada
    o remoto permitido. La fuente ya no exime del filtro de zona.
    """
    if _titulo_vencido(oferta.get("titulo", "")):
        return False
    resultado = resultado if resultado is not None else puntuar(oferta, cfg)
    if resultado["categoria"] == CATEGORIA_DESCARTADA:
        return False
    texto = sin_acentos(f"{oferta.get('titulo', '')} {oferta.get('ubicacion', '')}")
    zona_ok = any(z in texto for z in zonas)
    remotos = [sin_acentos(r) for r in cfg.get("palabras_remoto", REMOTO)]
    remoto_ok = cfg.get("incluir_remoto", True) and any(r in texto for r in remotos)
    return zona_ok or remoto_ok


def deduplicar(ofertas):
    """Quita ofertas repetidas por URL o por (titulo, empresa) ya vistos.

    El mismo puesto publicado con dos URLs distintas (o en dos fuentes) se
    conserva una sola vez; solo se compara el par titulo+empresa cuando la
    empresa viene informada, para no descartar empleos distintos homonimos.
    """
    salida = []
    claves_url = set()
    claves_empresa = set()
    for o in ofertas:
        clave_u = clave_url(o.get("url", ""))
        if clave_u in claves_url:
            continue
        empresa = sin_acentos((o.get("empresa") or "").strip())
        titulo = sin_acentos((o.get("titulo") or "").strip())
        clave_e = (titulo, empresa) if empresa else None
        if clave_e and clave_e in claves_empresa:
            continue
        claves_url.add(clave_u)
        if clave_e:
            claves_empresa.add(clave_e)
        salida.append(o)
    return salida


def recolectar(cfg):
    """Consulta las 4 fuentes en paralelo y junta sus ofertas.

    Cada fuente corre en su propio hilo (con sus pausas internas); una fuente
    que falle no detiene ni afecta a las demas.
    """
    todas = []
    with ThreadPoolExecutor(max_workers=len(FUENTES)) as ejecutor:
        futuros = {ejecutor.submit(modulo.buscar, cfg): modulo for modulo in FUENTES}
        for futuro in as_completed(futuros):
            modulo = futuros[futuro]
            try:
                ofertas = futuro.result()
                todas.extend(ofertas)
                print(f"  {modulo.__name__.split('.')[-1]}: {len(ofertas)}")
            except Exception as e:
                print(f"  aviso: {modulo.__name__} falló ({type(e).__name__})")
    return todas


def escribir_csv(nuevas):
    """Agrega las ofertas nuevas a ofertas.csv reescribiendo el archivo de forma atomica."""
    if not nuevas and os.path.exists(OFERTAS_PATH):
        return
    with bloqueo.proceso(DATA, "buscador"):
        existentes = cargar_ofertas()
        escribir_csv_atomico(OFERTAS_PATH, existentes + list(nuevas), COLUMNAS)


def escribir_reporte(nuevas, todas, generado, dias_retencion, borradas):
    """Genera reporte.html de solo lectura con las ofertas ordenadas por compatibilidad."""
    hoy = datetime.now().strftime("%Y-%m-%d")
    try:
        cfg = cargar_config()
    except Exception:
        cfg = {}
    try:
        dias_negra = int(cfg.get("dias_lista_negra", 15))
    except Exception:
        dias_negra = 15

    def dias_de(fecha):
        """Dias transcurridos desde la fecha de la oferta hasta hoy (o '-')."""
        try:
            d = (datetime.strptime(hoy, "%Y-%m-%d") - datetime.strptime(fecha, "%Y-%m-%d")).days
            return str(d)
        except Exception:
            return "-"

    def con_puntaje(items):
        """Empareja cada oferta con su compatibilidad, ordenada de mayor a menor."""
        pares = [(o, puntuar(o, cfg)) for o in items]
        pares.sort(key=lambda p: p[0].get("fecha") or "", reverse=True)
        pares.sort(key=lambda p: p[1]["porcentaje"], reverse=True)
        return pares

    def filas(pares):
        """Convierte pares (oferta, compatibilidad) en filas <tr> con el texto escapado."""
        out = []
        for o, r in pares:
            url = html.escape(o.get("url", ""), quote=True)
            out.append(
                "<tr>"
                f"<td>{html.escape(o.get('fecha', ''))}</td>"
                f"<td>{html.escape(o.get('fuente', ''))}</td>"
                f"<td>{html.escape(r.get('familia') or '')}</td>"
                f"<td><a href=\"{url}\" target=\"_blank\">{html.escape(o.get('titulo', ''))}</a></td>"
                f"<td>{html.escape(o.get('ubicacion', ''))}</td>"
                f"<td>{r['porcentaje']}%</td>"
                f"<td>{dias_de(o.get('fecha', ''))}</td>"
                f"<td>{html.escape(o.get('estado_envio', ''))}</td>"
                "</tr>"
            )
        return "\n".join(out)

    pares_nuevas = con_puntaje(nuevas)
    pares_todas = con_puntaje(todas)
    compatibles = [p for p in pares_todas if p[1]["categoria"] == CATEGORIA_COMPATIBLE]
    relacionadas = [p for p in pares_todas if p[1]["categoria"] == CATEGORIA_RELACIONADA]
    enfoques = {}
    for _, r in compatibles + relacionadas:
        familia = r.get("familia") or "Otro TI"
        enfoques[familia] = enfoques.get(familia, 0) + 1
    resumen_enfoques = " | ".join(
        f"{html.escape(k)}: {v}" for k, v in sorted(enfoques.items(), key=lambda kv: -kv[1])
    )
    encabezados = ("<tr><th>Fecha</th><th>Fuente</th><th>Enfoque</th><th>Puesto</th>"
                   "<th>Ubicacion</th><th>Compat</th><th>Dias</th><th>Estado</th></tr>")
    cuerpo = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<title>Buscador de Puestos - Reporte</title>
<style>
body {{ font-family: Segoe UI, Arial, sans-serif; margin: 24px; color: #222; }}
h1 {{ color: #1a5276; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 28px; }}
th, td {{ border: 1px solid #ccc; padding: 6px 8px; font-size: 14px; text-align: left; }}
th {{ background: #1a5276; color: #fff; }}
tr:nth-child(even) {{ background: #eaf2f8; }}
.nuevas tr {{ background: #d4efdf; }}
.nota {{ background: #fef9e7; border: 1px solid #f9e79f; padding: 10px 14px; font-size: 13px; }}
</style></head><body>
<h1>Buscador de Puestos</h1>
<p>Generado: {html.escape(generado)} | Ofertas nuevas: {len(nuevas)} | Total acumulado: {len(todas)}
   | Compatibles: {len(compatibles)} | Relacionadas: {len(relacionadas)} | Purgadas hoy: {borradas}</p>
<p><b>Enfoques:</b> {resumen_enfoques or 'sin ofertas activas'}</p>
<p class="nota">Visor de solo lectura. Para eliminar ofertas (lista negra de {dias_negra} dias),
marcar estados o buscar, usa la aplicacion: doble clic en <b>Abrir Ofertas</b>.
Las ofertas con mas de {int(dias_retencion)} dias se retiran solas.</p>
<h2>Nuevas de hoy</h2>
<table class="nuevas">{encabezados}
{filas(pares_nuevas)}
</table>
<h2>Compatibles ({len(compatibles)})</h2>
<table>{encabezados}
{filas(compatibles)}
</table>
<h2>Relacionadas ({len(relacionadas)})</h2>
<table>{encabezados}
{filas(relacionadas)}
</table>
</body></html>"""
    escribir_texto_atomico(REPORTE_PATH, cuerpo)


def registrar(mensaje):
    """Agrega una linea con fecha y hora a data/historial.log (con rotacion)."""
    os.makedirs(DATA, exist_ok=True)
    rotar_log(LOG_PATH)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {mensaje}\n")


def postulaciones_hoy(hoy=None, ruta=None):
    """Cuenta las postulaciones marcadas hoy sumando los eventos del historial.

    Cada vez que la app marca ofertas como 'Postulado' registra una linea
    'ESTADO 'Postulado' filas=N'; aqui se suman las de la fecha indicada.
    Sirve para la meta diaria sin cambiar el formato de ofertas.csv.
    """
    hoy = hoy or datetime.now().strftime("%Y-%m-%d")
    ruta = ruta or LOG_PATH
    total = 0
    try:
        with open(ruta, encoding="utf-8", errors="replace") as f:
            for linea in f:
                if not linea.startswith(f"[{hoy}") or "ESTADO 'Postulado'" not in linea:
                    continue
                coincidencia = re.search(r"filas=(\d+)", linea)
                if coincidencia:
                    total += int(coincidencia.group(1))
    except OSError:
        return 0
    return total


# ---------- Ejecucion principal ----------
def main():
    """Corre una busqueda completa con bloqueo de proceso."""
    with bloqueo.proceso(DATA, "buscador"):
        _correr()


def _correr():
    """Corre una busqueda completa: purga, consulta, filtra, guarda, verifica y reporta.

    Orden: (1) purga por antiguedad, (2) recolectar de las 4 fuentes en paralelo,
    (3) deduplicar, (4) filtrar por compatibilidad y zona, (5) descartar
    vistas/negra y guardar nuevas, (6) verificar ofertas cerradas, (7) reporte,
    vistas, avisos y log (con duracion y embudo del filtro).
    """
    inicio = time.perf_counter()
    os.makedirs(DATA, exist_ok=True)
    limpiar_cache()
    cfg = cargar_config()
    zonas = [sin_acentos(z) for z in cfg.get("zonas", [])]
    dias_retencion = int(cfg.get("dias_retencion", 15))
    _, borradas = purgar_ofertas(dias_retencion)
    if borradas:
        print(f"  purgadas (>{dias_retencion} dias): {borradas}")
    print("Buscando ofertas...")
    crudas = deduplicar(recolectar(cfg))
    print(f"  crudas: {len(crudas)}")
    resultados = [puntuar(o, cfg) for o in crudas]
    compatibles = sum(1 for r in resultados if r["categoria"] == CATEGORIA_COMPATIBLE)
    relacionadas = sum(1 for r in resultados if r["categoria"] == CATEGORIA_RELACIONADA)
    descartadas = sum(1 for r in resultados if r["categoria"] == CATEGORIA_DESCARTADA)
    familias = {}
    motivos = {}
    for resultado in resultados:
        if resultado["categoria"] == CATEGORIA_DESCARTADA:
            motivo = resultado.get("motivo") or "otro"
            motivos[motivo] = motivos.get(motivo, 0) + 1
        else:
            familia = resultado.get("familia") or "Otro TI"
            familias[familia] = familias.get(familia, 0) + 1
    filtradas = [
        o for o, r in zip(crudas, resultados)
        if pasa_filtros(o, zonas, cfg, r)
    ]
    print(f"  coinciden: {len(filtradas)} (compatibles {compatibles}, relacionadas {relacionadas}, descartadas {descartadas})")
    if familias:
        print("  enfoques: " + ", ".join(f"{k} {v}" for k, v in sorted(familias.items())))
    if motivos:
        top = sorted(motivos.items(), key=lambda kv: -kv[1])[:4]
        print("  descartes: " + ", ".join(f"{k} {v}" for k, v in top))
    vistas = cargar_vistas()
    negra = purgar_lista_negra()
    previas = {clave_url(o["url"]) for o in cargar_ofertas()}
    hoy = datetime.now().strftime("%Y-%m-%d")
    nuevas = []
    for o in filtradas:
        clave = clave_url(o["url"])
        if clave in negra or clave in vistas or clave in previas:
            continue
        vistas[clave] = hoy
        nuevas.append(
            {
                "fecha": hoy,
                "fuente": o["fuente"],
                "titulo": o["titulo"],
                "ubicacion": o["ubicacion"],
                "empresa": o.get("empresa", ""),
                "url": o["url"],
                "estado_envio": "",
            }
        )
    escribir_csv(nuevas)
    cerradas = 0
    if cfg.get("verificar_en_busqueda", True):
        try:
            from verificar import verificar_ofertas

            retiradas, revisadas = verificar_ofertas(cfg)
            cerradas = len(retiradas)
            if retiradas:
                print(f"  ofertas cerradas retiradas: {cerradas} (revisadas {revisadas})")
        except Exception as e:
            print(f"  aviso: verificación falló ({type(e).__name__})")
    todas = cargar_ofertas()
    generado = datetime.now().strftime("%Y-%m-%d %H:%M")
    escribir_reporte(nuevas, todas, generado, dias_retencion, borradas)
    negra_actual = purgar_lista_negra()
    guardar_vistas({clave: fecha for clave, fecha in vistas.items() if clave not in negra_actual})
    duracion = round(time.perf_counter() - inicio, 1)
    print(f"  nuevas: {len(nuevas)} | acumuladas: {len(todas)} | duracion: {duracion} s")
    for o in nuevas:
        print(f"   + [{o['fuente']}] {o['titulo']} ({o['ubicacion']})")
    print(f"Reporte: {REPORTE_PATH}")
    if nuevas and cfg.get("notificar_toast", True):
        titulo = "Buscador de Puestos"
        mensaje = f"{len(nuevas)} oferta(s) nueva(s). Revisa postulaciones/ofertas.csv"
        toast(titulo, mensaje)
    if nuevas:
        try:
            enviar_correo(cfg.get("correo", {}), f"{len(nuevas)} ofertas nuevas", f"<p>Revisa el reporte en {REPORTE_PATH}</p>")
        except Exception as e:
            print(f"  aviso: correo falló ({type(e).__name__})")
    motivos_log = dict(sorted(motivos.items(), key=lambda kv: -kv[1])[:10])
    familias_log = dict(sorted(familias.items(), key=lambda kv: -kv[1]))
    registrar(
        f"OK segundos={duracion} crudas={len(crudas)} compatibles={compatibles} "
        f"relacionadas={relacionadas} descartadas={descartadas} coinciden={len(filtradas)} "
        f"nuevas={len(nuevas)} borradas={borradas} cerradas={cerradas} acumuladas={len(todas)} "
        f"familias={familias_log} motivos={motivos_log}"
    )
    if cfg.get("abrir_reporte") and nuevas:
        os.startfile(REPORTE_PATH)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        registrar("ERROR " + traceback.format_exc().replace("\n", " | "))
        raise
