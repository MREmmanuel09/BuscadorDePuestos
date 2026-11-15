"""Motor de compatibilidad: puntua cada oferta contra el perfil configurado.

Funciones puras (sin red ni archivos): reciben la oferta y el diccionario de
configuracion, y devuelven el porcentaje y la categoria (Compatible,
Relacionada o Descartada). Los grupos de palabras tienen pesos: fuertes x3,
medias x2, contexto x1 y castigo -1; una palabra excluida o incompatible
anula la oferta (0 %).

Antes de sumar puntos se exige un **ancla de puesto** (soporte, redes,
infraestructura...) en el TITULO. Asi "Senior Software Engineer" o "Tecnologo
de Alimentos" no entran solo porque digan "software" o "sistemas". La familia
del puesto (Soporte, Redes, Infraestructura...) se devuelve en el resultado
para que la app pueda filtrar sin perder flexibilidad.

Las palabras son raices con limite de palabra: "informatic" coincide con
"informatica" y "soporte tecnico" con "Soporte Tecnico", pero "n1" no
coincide dentro de otra palabra.
"""
import functools
import re

from fuentes.comun import sin_acentos
from puestos import FAMILIA_NINGUNA, clasificar

CATEGORIA_COMPATIBLE = "Compatible"
CATEGORIA_RELACIONADA = "Relacionada"
CATEGORIA_DESCARTADA = "Descartada"

PESO_FUERTE = 3
PESO_MEDIA = 2
PESO_CONTEXTO = 1
PESO_CASTIGO = -1

FUERTES_DEFECTO = [
    "soporte ti", "soporte tecnico", "soporte al usuario", "soporte de ti",
    "tecnico informatico", "help desk", "helpdesk", "service desk",
    "mesa de ayuda", "technical support", "it support", "soporte en sitio",
    "support engineer", "support analyst", "support specialist",
    "support technician", "desktop support", "desktop technician",
    "it technician", "network technician", "network engineer",
    "network administrator", "network operations", "noc", "noc analyst",
    "soc analyst", "redes", "network", "networking", "sysadmin",
    "administrador de red", "administrador de redes",
    "administrador de sistemas", "ciberseguridad", "cybersecurity",
    "data center", "datacenter", "application support", "product support",
    "service now", "servicenow", "field service", "field technician",
    "tecnico de redes", "tecnico de soporte", "tecnico de sistemas",
    "operador de sistemas",
    "planta externa", "soportista", "cableado estructurado", "fibra optica",
    "soporte n1", "soporte n2", "soporte nivel 1", "soporte nivel 2",
]

MEDIAS_DEFECTO = [
    "soporte", "support", "sistemas", "infraestructura", "telecom",
    "telecomunicacion", "servidor", "cableado", "informatic",
    "information technology", "software", "base de datos", "dba",
    "aplicaciones", "applications",
]

CONTEXTO_DEFECTO = [
    "windows", "m365", "office 365", "microsoft teams", "teams",
    "active directory", "endpoint", "n1", "nivel 1", "l1", "n2", "nivel 2",
    "l2", "wifi", "wireless", "desktop", "firewall", "vlan", "dhcp",
    "dns", "vpn", "ipv4", "ipv6", "enrutamiento", "routing", "switching",
    "switch", "router", "cisco", "ccna", "ccst", "juniper", "fortinet",
    "hardware", "impresora", "linux", "ubuntu", "docker", "kubernetes",
    "vmware", "virtualizacion", "powershell", "python", "git", "azure",
    "aws", "cloud", "sql", "tecnico", "technician", "analista", "analyst",
    "especialista", "specialist", "ingeniero", "engineer", "administrador",
    "administrator", "operador", "operator", "access point", "monitoreo",
    "tickets", "cctv", "videovigilancia",
]

CASTIGO_DEFECTO = [
    "bilingual", "bilingue", "fluent english", "ingles avanzado",
    "advanced english", "english advanced", "english b2", "english c1",
    "ingles b2", "ingles c1", "french", "frances", "portugues", "german",
    "aleman", "italian", "italiano", "mandarin", "trilingue", "senior",
    "sr", "lead", "principal",
]

EXCLUIDAS_DEFECTO = [
    "redes sociales", "community manager", "marketing", "publicidad",
    "calidad", "vendedor", "ventas", "comercial", "contabilidad",
    "recursos humanos", "rrhh", "abogad", "juridic", "legal", "contador",
    "secretari", "recepcionista", "customer support", "customer service",
    "servicio al cliente", "atencion al cliente", "call center",
    "telemarketing", "sales representative", "sales manager", "sales support",
    "account executive", "business development", "software engineer",
    "software developer", "full stack", "frontend", "backend",
    "desarrollador", "programador", "developer", "data scientist",
    "machine learning", "qa engineer", "qa analyst", "quality assurance",
    "tester", "french", "frances", "portugues", "german", "aleman",
    "italian", "italiano", "mandarin", "chino", "trilingue",
    "business support", "quality", "p2p helpdesk", "client support representative",
    "client support agent", "banking support representative",
    "multichannel banking support", "soporte a clientes", "parqueo",
    "mensajeria", "marchamo", "people support", "employee support",
    "hr support", "talent support", "account manager", "operations support agent",
    "customer engagement", "sales engineer", "title & registration",
]

INCOMPATIBLES_DEFECTO = [
    "aire acondicionado", "hvac", "refrigeracion", "climatizacion",
    "plomeria", "fontaneria", "electricista", "electricidad", "soldadura",
    "mecanica automotriz", "mecanic", "electromecanic", "civil",
    "construccion", "constructiv", "alimentos", "nutricion", "ortoped",
    "orthoped", "odontolog", "dental", "enfermer", "farmac", "veterinari",
    "paciente", "laboratorista", "quirofan", "maquinaria", "equipos medicos",
    "biomedic", "electromedicina", "plc", "scada", "robotica", "industrial",
    "operational technology", "sistemas de agua",
]

# Sectores que pueden aparecer como añadido en un puesto de TI sin anularlo:
# "Tecnico de Cableado Estructurado y Obra Civil" sigue siendo redes. Si el
# sector es el objeto del puesto ("Soporte para Aire Acondicionado") se
# descarta igual, y si no hay una frase fuerte de TI tambien.
SECTORES_MEZCLABLES = (
    "civil", "construccion", "electromecanic", "mecanic", "electricidad",
    "soldadura", "hvac", "refrigeracion", "aire acondicionado", "plomeria",
    "alimentos", "nutricion", "paciente", "farmac", "odontolog", "dental",
    "enfermer", "veterinari", "ortoped", "orthoped", "laboratorista",
    "quirofan", "maquinaria", "equipos medicos", "biomedic",
    "electromedicina", "plc", "scada", "robotica", "industrial",
)

COMPATIBILIDAD_MINIMA_DEFECTO = 70
COMPATIBILIDAD_RELACIONADA_DEFECTO = 40
META_PUNTOS_DEFECTO = 4

# Los puestos senior se muestran como Relacionadas aunque el titulo sume mucho:
# siguen siendo una opcion, pero no compiten con las vacantes junior/mid.
SENIORIDAD = (
    "senior", "sr", "lead", "principal", "staff", "manager", "gerente",
    "jefe", "supervisor", "coordinador", "lider", "l3", "n3", "nivel 3",
)
JUNIOR = ("junior", "jr", "trainee", "practicante", "intern", "pasant")


def _normalizar(lista):
    """Convierte una lista de palabras del config en tupla sin acentos ni vacios."""
    return tuple(sin_acentos(str(p)).strip() for p in lista if str(p).strip())


@functools.lru_cache(maxsize=128)
def _compilar(palabras):
    """Compila una tupla de palabras a patrones de palabra completa con raiz.

    Cada palabra se busca con limite inicial y admite terminaciones: "help
    desk" coincide con "Help Desk" e "informatic" con "informatica". Las
    palabras de 3 letras o menos se comparan exactas para que "n1" no coincida
    dentro de "Fun1dad" ni "sr" dentro de "sra".
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


def _grupo(cfg, clave, defecto):
    """Lista normalizada del config; los defectos se usan solo si la clave falta."""
    return _normalizar(cfg[clave] if clave in cfg else defecto)


def _listas(cfg):
    """Extrae y normaliza los grupos de palabras del config (con valores por defecto)."""
    return {
        "fuertes": _grupo(cfg, "palabras_fuertes", FUERTES_DEFECTO),
        "medias": _grupo(cfg, "palabras_clave", MEDIAS_DEFECTO),
        "contexto": _grupo(cfg, "palabras_contexto", CONTEXTO_DEFECTO),
        "castigo": _grupo(cfg, "palabras_castigo", CASTIGO_DEFECTO),
        "excluidas": _grupo(cfg, "palabras_excluidas", EXCLUIDAS_DEFECTO),
        "incompatibles": _grupo(cfg, "incompatibles", INCOMPATIBLES_DEFECTO),
    }


def _coinciden(texto, palabras):
    """Devuelve las palabras (normalizadas) cuyos patrones aparecen en el texto."""
    return [p for p, patron in zip(palabras, _compilar(palabras)) if patron.search(texto)]


def _unicos(palabras):
    """Quita de un grupo las palabras contenidas en otra mas larga ya presente.

    Evita contar dos veces el mismo concepto: "telecom" con "telecomunicacion"
    o "civil" con "obra civil".
    """
    return [
        p for p in palabras
        if not any(p != q and len(q) > len(p) and p in q for q in palabras)
    ]


def _sin_repetir(menores, mayores):
    """Quita de 'menores' lo que ya conto en un grupo de mayor peso."""
    return [p for p in menores if not any(p in m for m in mayores)]


def _sector_mezclable(palabra):
    """Indica si la palabra descartada es un sector que puede ir como añadido."""
    return any(
        palabra == sector or palabra in sector or sector in palabra
        for sector in SECTORES_MEZCLABLES
    )


def _es_mixto(texto, palabra, fuertes):
    """Decide si un sector ajeno acompaña al puesto en vez de definirlo.

    Se tolera solo cuando hay una frase fuerte de TI y el sector aparece como
    añadido ("... y obra civil", "... , area industrial"). Si el sector es el
    objeto ("soporte para aire acondicionado", "tecnico en refrigeracion") no
    se tolera y la oferta se descarta.
    """
    patron = _compilar((palabra,))[0]
    coincidencia = patron.search(texto)
    if not coincidencia:
        return False
    antes = texto[: coincidencia.start()]
    if re.search(r"\b(?:para|en)\s+(?:\w+\s+){0,3}$", antes):
        return False
    if not re.search(r"(?:\by\b|\be\b|,)\s+(?:\w+\s+){0,3}$", antes):
        return False
    return bool(_coinciden(texto, fuertes))



def categoria_de(porcentaje, cfg):
    """Clasifica un porcentaje como Compatible, Relacionada o Descartada."""
    try:
        minima = int(cfg.get("compatibilidad_minima", COMPATIBILIDAD_MINIMA_DEFECTO))
        relacionada = int(cfg.get("compatibilidad_relacionada", COMPATIBILIDAD_RELACIONADA_DEFECTO))
    except (TypeError, ValueError):
        minima, relacionada = COMPATIBILIDAD_MINIMA_DEFECTO, COMPATIBILIDAD_RELACIONADA_DEFECTO
    if porcentaje >= minima:
        return CATEGORIA_COMPATIBLE
    if porcentaje >= relacionada:
        return CATEGORIA_RELACIONADA
    return CATEGORIA_DESCARTADA


def puntuar(oferta, cfg):
    """Puntua una oferta contra el perfil y devuelve su compatibilidad.

    Devuelve un dict con 'porcentaje' (0-100), 'puntos', 'categoria'
    (Compatible/Relacionada/Descartada), 'familia' (Soporte/Redes/...),
    'motivo' (por que se descarto, si aplica), las palabras que sumaron en
    'fuertes'/'medias'/'contexto', las que restaron en 'castigos' y la
    palabra culpable en 'excluida' (o None si no hubo).

    Solo se puntua el TITULO: la ubicacion decide la zona, no la naturaleza
    del puesto. Primero se exige un ancla de TI; sin ella no hay puntaje.
    """
    listas = _listas(cfg)
    texto = sin_acentos(str(oferta.get("titulo", "")))
    resultado = {
        "porcentaje": 0,
        "puntos": 0,
        "categoria": CATEGORIA_DESCARTADA,
        "familia": FAMILIA_NINGUNA,
        "motivo": "",
        "fuertes": [],
        "medias": [],
        "contexto": [],
        "castigos": [],
        "excluida": None,
    }
    anuladas = _coinciden(texto, listas["excluidas"] + listas["incompatibles"])
    mezclables = [
        palabra for palabra in anuladas
        if _sector_mezclable(palabra) and _es_mixto(texto, palabra, listas["fuertes"])
    ]
    if anuladas and not mezclables:
        resultado["excluida"] = anuladas[0]
        resultado["motivo"] = f"otro rubro o rol: {anuladas[0]}"
        return resultado
    if mezclables:
        resultado["motivo"] = f"enfoque mixto: {', '.join(mezclables)}"
    clasificacion = clasificar(texto, cfg)
    if clasificacion["motivo"]:
        resultado["motivo"] = clasificacion["motivo"]
        return resultado
    resultado["familia"] = clasificacion["familia"]
    fuertes = _unicos(_coinciden(texto, listas["fuertes"]))
    medias = _sin_repetir(_unicos(_coinciden(texto, listas["medias"])), fuertes)
    contexto = _sin_repetir(_unicos(_coinciden(texto, listas["contexto"])), fuertes + medias)
    castigos = _unicos(_coinciden(texto, listas["castigo"]))
    for sector in mezclables:
        if sector not in castigos:
            castigos.append(sector)
    puntos = (
        len(fuertes) * PESO_FUERTE
        + len(medias) * PESO_MEDIA
        + len(contexto) * PESO_CONTEXTO
        + len(castigos) * PESO_CASTIGO
        - len(mezclables)  # el sector añadido pesa -2 en total (-1 de castigo)
    )
    try:
        meta = max(1, int(cfg.get("meta_puntos", META_PUNTOS_DEFECTO)))
    except (TypeError, ValueError):
        meta = META_PUNTOS_DEFECTO
    resultado["puntos"] = max(0, puntos)
    resultado["porcentaje"] = max(0, min(100, int(round(puntos * 100 / meta))))
    resultado["categoria"] = categoria_de(resultado["porcentaje"], cfg)
    resultado["fuertes"] = fuertes
    resultado["medias"] = medias
    resultado["contexto"] = contexto
    resultado["castigos"] = castigos
    if resultado["categoria"] == CATEGORIA_COMPATIBLE:
        es_senior = bool(_coinciden(texto, _normalizar(SENIORIDAD)))
        es_junior = bool(_coinciden(texto, _normalizar(JUNIOR)))
        if es_senior and not es_junior:
            resultado["porcentaje"] = min(resultado["porcentaje"], 69)
            resultado["categoria"] = CATEGORIA_RELACIONADA
            resultado["motivo"] = (
                f"puesto senior; {resultado['motivo']}"
                if resultado["motivo"]
                else "puesto senior"
            )
    if resultado["categoria"] == CATEGORIA_DESCARTADA and not resultado["motivo"]:
        resultado["motivo"] = "pocas coincidencias con el perfil"
    return resultado
