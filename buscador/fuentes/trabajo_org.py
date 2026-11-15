"""Buscador de ofertas en cr.trabajo.org, recorriendo zonas y paginas."""
import html
import re

from compatibilidad import CATEGORIA_DESCARTADA, puntuar

from .comun import fetch, pausar, sin_acentos

BASE = "https://cr.trabajo.org"
# Cada oferta es un <li class="... job-item" data-url="..." title="...">.
BLOQUE = re.compile(r'<li[^>]*class="[^"]*job-item[^"]*"[^>]*>.*?</li>', re.S)
ENLACE = re.compile(r'data-url="([^"]+)"')
TITULO_ATTR = re.compile(r'title="([^"]*)"')
TITULO = re.compile(r"<h2[^>]*>\s*<a[^>]*>(.*?)</a>", re.S)
EMPRESA = re.compile(r'lnr-briefcase[^>]*></i>\s*(.*?)\s*</span>', re.S)
UBICACION = re.compile(r'lnr-map-marker[^>]*></i>\s*(.*?)\s*</span>', re.S)
ETIQUETAS = re.compile(r"<[^>]+>")


def _limpiar(valor):
    """Quita etiquetas HTML, decodifica entidades y recorta espacios."""
    texto = ETIQUETAS.sub(" ", valor or "")
    return html.unescape(re.sub(r"\s+", " ", texto)).strip(" |")


def _slug(zona):
    """Convierte una zona del perfil en el slug de URL de Trabajo.org."""
    return sin_acentos(str(zona)).strip().replace(" ", "-")


def _candidata(titulo, cfg):
    """Descarta en el listado lo que no tiene enfoque TI, antes de acumularlo."""
    return puntuar({"titulo": titulo}, cfg)["categoria"] != CATEGORIA_DESCARTADA


def buscar(cfg):
    """Recorre las zonas del perfil y sus paginas en Trabajo.org.

    La pagina de zona trae 20 ofertas con titulo, empresa y ubicacion real;
    se piden `max_paginas_trabajo_org` paginas por zona y se filtra por
    compatibilidad en el listado. Antes solo se leia la primera pagina y la
    ubicacion era el nombre de la zona, lo que dejaba entrar ofertas de otros
    lugares y perdia casi todo el catalogo.
    """
    ofertas = []
    vistos = set()
    pausa = cfg.get("pausa_segundos", 0.7)
    paginas = int(cfg.get("max_paginas_trabajo_org", 2))
    zonas = cfg.get("zonas") or []
    slugs_vistos = set()
    for zona in zonas:
        slug = _slug(zona)
        if not slug or slug in slugs_vistos:
            continue
        slugs_vistos.add(slug)
        for pagina in range(1, paginas + 1):
            url = f"{BASE}/empleo-en-{slug}"
            if pagina > 1:
                url += f"?page={pagina}"
            try:
                html_pagina = fetch(url)
            except Exception:
                break
            bloques = BLOQUE.findall(html_pagina)
            if not bloques:
                break
            nuevos = 0
            for bloque in bloques:
                m_enlace = ENLACE.search(bloque)
                if not m_enlace:
                    continue
                enlace = m_enlace.group(1)
                if not enlace or enlace in vistos:
                    continue
                m_titulo = TITULO.search(bloque)
                titulo = _limpiar(m_titulo.group(1)) if m_titulo else ""
                if not titulo:
                    m_attr = TITULO_ATTR.search(bloque)
                    if m_attr:
                        titulo = _limpiar(html.unescape(m_attr.group(1)).rsplit(" en ", 1)[0])
                if not titulo or not _candidata(titulo, cfg):
                    continue
                m_ubicacion = UBICACION.search(bloque)
                m_empresa = EMPRESA.search(bloque)
                vistos.add(enlace)
                nuevos += 1
                ofertas.append(
                    {
                        "titulo": titulo,
                        "empresa": _limpiar(m_empresa.group(1)) if m_empresa else "",
                        "ubicacion": (
                            _limpiar(m_ubicacion.group(1))
                            if m_ubicacion
                            else str(zona).strip().title()
                        ),
                        "url": enlace,
                        "fuente": "Trabajo.org",
                    }
                )
            if not nuevos:
                break
            pausar(pausa)
    return ofertas
