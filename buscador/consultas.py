"""Seleccion de consultas por corrida: nucleo fijo + rotacion diaria.

Buscar siempre las mismas 8 frases agota el catalogo y deja pocas ofertas
nuevas. Este modulo mantiene las primeras `consultas_fijas` en cada corrida
(lo esencial) y rota el resto de `palabras_clave_busqueda` dia a dia. Cada
fuente usa un desplazamiento distinto para que, el mismo dia, Computrabajo y
LinkedIn exploren colas diferentes del catalogo.
"""
from datetime import date


def _entero(valor, defecto):
    """Convierte a entero sin lanzar; usa el defecto si no es valido."""
    try:
        return int(valor)
    except (TypeError, ValueError):
        return defecto


def consultas(cfg, fuente="", dia=None):
    """Devuelve la lista de consultas que debe usar una fuente en esta corrida.

    - `consultas_por_corrida` = 0 (o mayor que el catalogo) usa todas.
    - Las primeras `consultas_fijas` siempre se incluyen.
    - El resto rota segun el dia ordinal y un desplazamiento propio de la
      fuente, para que dos fuentes no consulten lo mismo el mismo dia.
    """
    cfg = cfg or {}
    base = [str(c).strip() for c in cfg.get("palabras_clave_busqueda", []) if str(c).strip()]
    if not base:
        return []
    limite = _entero(cfg.get("consultas_por_corrida", 0), 0)
    if limite <= 0 or len(base) <= limite:
        return base
    fijas = min(max(0, _entero(cfg.get("consultas_fijas", 0), 0)), limite, len(base))
    resto = base[fijas:]
    cupo = limite - fijas
    if not resto or cupo <= 0:
        return base[:fijas]
    dia = dia or date.today()
    desplazamiento = sum(ord(c) for c in str(fuente)) % len(resto)
    inicio = (dia.toordinal() + desplazamiento) % len(resto)
    ventana = [resto[(inicio + i) % len(resto)] for i in range(min(cupo, len(resto)))]
    return base[:fijas] + ventana
