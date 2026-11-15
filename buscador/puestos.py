"""Clasificacion de puestos: enfoque TI, familia y naturaleza del rol.

Este modulo responde tres preguntas antes de puntuar una oferta:

1. **Enfoque**: el titulo debe contener un ancla de TI (soporte, redes,
   infraestructura, etc.). Sin ancla no es un puesto del perfil, aunque diga
   "desarrollo" o "sistemas" de otra industria.
2. **Naturaleza**: el titulo no debe pertenecer a otro rubro (electromecanica,
   alimentos, salud, ventas, desarrollo de software...). Las palabras que
   descartan siguen viviendo en `palabras_excluidas`/`incompatibles`; aqui solo
   se clasifica lo que ya paso ese filtro.
3. **Familia**: dentro de TI, el puesto se etiqueta como Soporte, Redes,
   Infraestructura, Campo, Aplicaciones, Seguridad u Otro TI. Asi la busqueda
   puede ser flexible sin mezclar soporte de redes con soporte de maquinaria.

Las listas son raices con limite de palabra, igual que en compatibilidad.py:
"red" coincide con "redes" pero "ti" no coincide dentro de "tiempo".
"""
import functools
import re

from fuentes.comun import sin_acentos

FAMILIA_SOPORTE = "Soporte"
FAMILIA_REDES = "Redes"
FAMILIA_INFRAESTRUCTURA = "Infraestructura"
FAMILIA_CAMPO = "Campo"
FAMILIA_APLICACIONES = "Aplicaciones"
FAMILIA_SEGURIDAD = "Seguridad"
FAMILIA_OTRO = "Otro TI"
FAMILIA_NINGUNA = ""

FAMILIAS = (
    FAMILIA_SOPORTE,
    FAMILIA_REDES,
    FAMILIA_INFRAESTRUCTURA,
    FAMILIA_CAMPO,
    FAMILIA_APLICACIONES,
    FAMILIA_SEGURIDAD,
    FAMILIA_OTRO,
)

# Anclas: una debe aparecer en el TITULO para que la oferta sea del perfil.
# Se prefieren frases completas; los terminos cortos se comparan como palabra
# exacta para que "ti" no coincida con "tiempo" ni "noc" con "nocturno".
ANCLAS_DEFECTO = (
    "soporte", "soportista", "support",
    "help desk", "helpdesk", "service desk", "mesa de ayuda",
    "it support", "technical support", "desktop support", "soporte en sitio",
    "tecnico informatico", "tecnico de soporte", "tecnico de redes",
    "tecnico de sistemas", "tecnico de telecomunicaciones",
    "tecnico en redes", "tecnico en sistemas", "tecnico en soporte",
    "tecnico ti", "it technician", "support technician", "support engineer",
    "support analyst", "support specialist", "desktop technician",
    "redes", "network", "networking", "noc", "telecom", "telecomunicacion",
    "cableado", "fibra optica", "planta externa", "wireless", "wifi",
    "sistemas", "system", "sysadmin", "administrador de sistemas",
    "administrador de red", "administrador de redes",
    "infraestructura", "infrastructure", "servidor", "server",
    "data center", "datacenter", "endpoint", "desktop",
    "ciberseguridad", "cybersecurity", "seguridad informatica",
    "information security", "soc", "siem",
    "application support", "soporte de aplicaciones", "product support",
    "service now", "servicenow", "sap support", "erp support",
    "operador de sistemas", "monitoreo de red",
    "field service", "field technician", "instalador de redes",
    "it", "ti",
)

# Familias: se evaluan en orden; la primera que coincide gana. Redes va antes
# que Soporte para que "Soporte de Redes" se muestre como Redes.
FAMILIAS_PALABRAS = (
    (FAMILIA_REDES, (
        "redes", "network", "networking", "noc", "telecom", "telecomunicacion",
        "cableado", "fibra optica", "wireless", "wifi", "enrutamiento",
        "routing", "switching", "conmutacion", "firewall", "access point",
        "planta externa", "isp", "voip", "sd-wan", "cisco", "ccna",
        "juniper", "fortinet", "monitoreo de red", "cctv", "videovigilancia",
    )),
    (FAMILIA_SEGURIDAD, (
        "ciberseguridad", "cybersecurity", "seguridad informatica",
        "information security", "soc", "siem", "pentest", "ethical hacking",
        "seguridad de la informacion",
    )),
    (FAMILIA_INFRAESTRUCTURA, (
        "infraestructura", "infrastructure", "sysadmin",
        "administrador de sistemas", "administrador de red",
        "administrador de redes", "servidor", "server", "data center",
        "datacenter", "virtualizacion", "vmware", "hyper-v", "active directory",
        "windows server", "linux", "ubuntu", "cloud", "azure", "aws",
        "backup", "almacenamiento", "storage", "devops", "sre", "kubernetes",
        "docker", "sistemas", "system", "operador de sistemas",
    )),
    (FAMILIA_APLICACIONES, (
        "application support", "soporte de aplicaciones", "product support",
        "service now", "servicenow", "sap", "erp", "crm", "salesforce",
        "software support", "soporte de software", "base de datos", "dba",
        "sql", "aplicaciones", "applications",
    )),
    (FAMILIA_CAMPO, (
        "tecnico de campo", "field service", "field technician", "on-site",
        "onsite", "instalador", "instalacion", "site technician",
        "soporte en sitio", "servicio de campo", "trabajo en campo",
        "tecnico en campo",
    )),
    (FAMILIA_SOPORTE, (
        "soporte", "soportista", "support", "help desk", "helpdesk",
        "service desk", "mesa de ayuda", "desktop", "endpoint",
        "service center", "usuario", "tecnico",
    )),
)


@functools.lru_cache(maxsize=256)
def _compilar(palabras):
    """Compila una tupla de palabras a patrones con limite inicial.

    Las palabras de 3 letras o menos se comparan como palabra completa; el
    resto admite terminaciones ("red" -> "redes", "support" -> "supporting").
    """
    patrones = []
    for palabra in palabras:
        partes = [re.escape(p) for p in palabra.split()]
        if not partes:
            continue
        cuerpo = r"\s+".join(partes)
        if len(palabra) <= 3 and " " not in palabra:
            patrones.append(re.compile(r"\b" + cuerpo + r"\b"))
        else:
            patrones.append(re.compile(r"\b" + cuerpo + r"\w*"))
    return tuple(patrones)


def _normalizar(lista):
    """Convierte una lista de palabras en tupla sin acentos, sin vacios ni repetidos."""
    salida = []
    vistos = set()
    for palabra in lista or ():
        texto = sin_acentos(str(palabra)).strip()
        if texto and texto not in vistos:
            salida.append(texto)
            vistos.add(texto)
    return tuple(salida)


def anclas(cfg=None):
    """Devuelve las anclas del perfil; si el config no trae, usa las de defecto."""
    cfg = cfg or {}
    valor = cfg.get("anclas_puesto")
    if isinstance(valor, (list, tuple)) and valor:
        return _normalizar(valor)
    return _normalizar(ANCLAS_DEFECTO)


def _coinciden(texto, palabras):
    """Devuelve las palabras cuyos patrones aparecen en el texto normalizado."""
    return [p for p, patron in zip(palabras, _compilar(palabras)) if patron.search(texto)]


def familia_de(titulo):
    """Clasifica un titulo en una familia de TI; None si no coincide ninguna."""
    texto = sin_acentos(str(titulo or ""))
    for familia, palabras in FAMILIAS_PALABRAS:
        if _coinciden(texto, _normalizar(palabras)):
            return familia
    return None


def clasificar(titulo, cfg=None):
    """Devuelve {'familia', 'ancla', 'motivo'} para un titulo.

    - Si no hay ancla de TI, motivo = 'sin enfoque TI' y familia vacia.
    - Si hay ancla, la familia puede ser 'Otro TI' cuando el puesto es de TI
      pero no encaja en Soporte/Redes/Infraestructura/Campo/Aplicaciones/Seguridad.
    """
    texto = sin_acentos(str(titulo or ""))
    encontradas = _coinciden(texto, anclas(cfg))
    if not encontradas:
        return {"familia": FAMILIA_NINGUNA, "ancla": "", "motivo": "sin enfoque TI"}
    return {
        "familia": familia_de(texto) or FAMILIA_OTRO,
        "ancla": encontradas[0],
        "motivo": "",
    }
