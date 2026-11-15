"""Buscador de ofertas en cr.findjob24h.com por consulta y pagina de resultados."""
import html
import re
from urllib.parse import quote, urljoin

from compatibilidad import CATEGORIA_DESCARTADA, puntuar
from consultas import consultas

from .comun import fetch, pausar

BASE = "https://cr.findjob24h.com"
# La busqueda devuelve tarjetas <li id=NNNN> con titulo, empresa y ubicacion.
BLOQUE = re.compile(r"<li[^>]*\bid=\d+[^>]*>(.*?)</li>", re.S)
TITULO = re.compile(r"<p class=entry-title>\s*<a[^>]*>(.*?)</a>", re.S)
EMPRESA = re.compile(r"<p class=company>\s*<a[^>]*>(.*?)</a>", re.S)
UBICACION = re.compile(r"<div class=location>\s*(.*?)</div>", re.S)
ENLACE = re.compile(r'href=(?:"([^"]+)"|\'([^\']+)\'|([^\s>]+))')
ETIQUETAS = re.compile(r"<[^>]+>")


def _limpiar(valor):
    """Quita etiquetas, entidades y simbolos iniciales; recorta espacios."""
    texto = ETIQUETAS.sub(" ", valor or "")
    texto = html.unescape(re.sub(r"\s+", " ", texto)).strip()
    return re.sub(r"^[^\w]+", "", texto).strip()


def _enlace(bloque):
    """Devuelve el primer href del bloque, venga entre comillas o sin ellas."""
    m = ENLACE.search(bloque)
    if not m:
        return ""
    return next((grupo for grupo in m.groups() if grupo), "")


def _titulo_desde_slug(rel):
    """Construye el titulo de la oferta a partir del ultimo tramo de la URL."""
    parte = rel.split("/")[-1]
    parte = re.sub(r"-job\d+$", "", parte)
    return parte.replace("-", " ").title()


def _candidata(titulo, cfg):
    """Indica si el titulo parece del perfil, reutilizando el motor de compatibilidad."""
    return puntuar({"titulo": titulo}, cfg)["categoria"] != CATEGORIA_DESCARTADA


def buscar(cfg):
    """Busca en FindJob24h con el catalogo de consultas y devuelve las afines.

    Cada consulta devuelve hasta ~36 tarjetas con titulo, empresa y ubicacion,
    sin abrir el detalle: el filtro de compatibilidad descarta el ruido antes
    de guardarlo y la corrida es mucho mas rapida que antes.
    """
    ofertas = []
    vistos = set()
    pausa = cfg.get("pausa_segundos", 0.7)
    for consulta in consultas(cfg, "FindJob24h"):
        url = f"{BASE}/list-job-search?search-query={quote(consulta)}&search-job=1"
        try:
            pagina = fetch(url)
        except Exception:
            continue
        for bloque in BLOQUE.findall(pagina):
            rel = _enlace(bloque)
            if not rel or "-job" not in rel:
                continue
            m_titulo = TITULO.search(bloque)
            titulo = _limpiar(m_titulo.group(1)) if m_titulo else _titulo_desde_slug(rel)
            if not titulo or not _candidata(titulo, cfg):
                continue
            enlace = urljoin(BASE + "/", rel.lstrip("/"))
            if enlace in vistos:
                continue
            vistos.add(enlace)
            m_empresa = EMPRESA.search(bloque)
            m_ubicacion = UBICACION.search(bloque)
            ofertas.append(
                {
                    "titulo": titulo,
                    "empresa": _limpiar(m_empresa.group(1)) if m_empresa else "",
                    "ubicacion": _limpiar(m_ubicacion.group(1)) if m_ubicacion else "",
                    "url": enlace,
                    "fuente": "FindJob24h",
                }
            )
        pausar(pausa)
    return ofertas
