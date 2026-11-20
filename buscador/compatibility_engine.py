"""Motor Aho-Corasick para coincidencia múltiple de palabras.

- Busca todas las palabras del config en un solo pase sobre el texto (O(n+m)
  en lugar de un regex por palabra).
- Se usa en compatibilidad.py como PREFILTRO de _coinciden(): si el automata
  no encuentra ningun candidato, no hace falta evaluar los regex individuales
  (caso comun al descartar un titulo). Cuando hay candidato, el regex decide
  para conservar exactamente la semantica de palabra con limite (\\b...\\w*).

Uso:
    motor = AhoCorasickEngine([("soporte", "fuertes"), ("ti", "medias")])
    motor.search("soporte ti")  # {"fuertes": {"soporte"}, "medias": {"ti"}}
"""

import re
import unicodedata
from collections import deque
from typing import Dict, List, Set, Tuple


def sin_acentos(texto: str) -> str:
    """Convierte a minusculas y elimina tildes/diacriticos (idempotente)."""
    forma = unicodedata.normalize("NFKD", str(texto).lower())
    return "".join(c for c in forma if not unicodedata.combining(c))


def _normalizar(texto: str) -> str:
    """Normaliza como el resto del buscador: minusculas, sin tildes y
    espacios colapsados (asi 'help\\t desk' y 'Help Desk' son lo mismo)."""
    return re.sub(r"\s+", " ", sin_acentos(texto)).strip()


class AhoCorasickEngine:
    """Motor de coincidencia múltiple sin dependencias externas.

    Algoritmo: construccion del automata en O(Sigma*L) y busqueda en O(n),
    donde Sigma es el alfabeto, L la longitud total de las palabras y n la
    longitud del texto. El texto y las palabras se normalizan (minusculas y
    sin tildes) antes de construir/buscar.
    """

    def __init__(self, patterns: List[Tuple[str, str]]):
        """Construye el automata y lo deja listo para buscar.

        Args:
            patterns: lista de (palabra, tipo) donde "tipo" es el grupo
                      (fuertes, medias, contexto, castigo, excluidas, incompatibles).
        """
        self.root = self._create_node()
        self.final_states = {}  # {tipo: {palabra_normalizada: 1}}

        for palabra, tipo in patterns:
            # Registrar el grupo aunque la palabra se descarte: search()
            # siempre responde con una clave por cada tipo declarado.
            self.final_states.setdefault(tipo, {})
            if not palabra or not str(palabra).strip():
                continue
            self._add_word(str(palabra), tipo)
        self._build()

    # ============================================================
    # Construcción del automatismo Aho-Corasick
    # ============================================================
    @staticmethod
    def _create_node():
        """Crea un nuevo nodo del automatismo."""
        return {"transitions": {}, "fail": None, "output": []}

    def _add_word(self, palabra: str, tipo: str):
        """Agrega una palabra al automatismo y la marca como final."""
        palabra = _normalizar(palabra)
        if not palabra:
            return
        estado_actual = self.root

        for caracter in palabra:
            if caracter not in estado_actual["transitions"]:
                estado_actual["transitions"][caracter] = self._create_node()
            estado_actual = estado_actual["transitions"][caracter]

        self.final_states.setdefault(tipo, {})[palabra] = 1
        entrada = {"palabra": palabra, "tipo": tipo}
        if entrada not in estado_actual["output"]:
            estado_actual["output"].append(entrada)

    @staticmethod
    def _unir_outputs(listas):
        """Une listas de outputs eliminando repetidos (por palabra+tipo)."""
        vistos = set()
        salida = []
        for lista in listas:
            for item in lista:
                clave = (item["palabra"], item["tipo"])
                if clave not in vistos:
                    vistos.add(clave)
                    salida.append(item)
        return salida

    def _build_failure_links(self):
        """Construye los enlaces de fallo y acumula sus outputs (fallback).

        Se recorre el arbol en anchura: el enlace de fallo de un nodo siempre
        apunta a un nodo de menor profundidad, cuyo output ya esta completo,
        por lo que un solo pase propaga todos los sufijos coincidentes.
        """
        cola = deque()
        for hijo in self.root["transitions"].values():
            hijo["fail"] = self.root
            cola.append(hijo)

        while cola:
            estado_actual = cola.popleft()
            estado_fallo = estado_actual.get("fail") or self.root

            for caracter, hijo in estado_actual["transitions"].items():
                cola.append(hijo)

                # Enlace de fallo del hijo: seguir el del padre y bajar por 'caracter'
                puntero = estado_fallo
                while puntero is not self.root and caracter not in puntero["transitions"]:
                    puntero = puntero.get("fail") or self.root
                if caracter in puntero["transitions"]:
                    hijo["fail"] = puntero["transitions"][caracter]
                else:
                    hijo["fail"] = self.root

                # Acumular los outputs del enlace de fallo (coincidencias por sufijo)
                if hijo["fail"] is not self.root:
                    hijo["output"] = self._unir_outputs(
                        [hijo["output"], hijo["fail"].get("output", [])]
                    )

    def _build(self):
        """Construye el automatismo completo."""
        self._build_failure_links()

    # ============================================================
    # Búsqueda
    # ============================================================
    def search(self, texto: str) -> Dict[str, Set[str]]:
        """Busca todas las palabras del automatismo en 'texto'.

        Returns:
            {tipo: {palabras_encontradas}} por ejemplo
            {"fuertes": {"soporte"}, "medias": {"ti"}}.
        """
        estado_actual = self.root
        resultados = {tipo: set() for tipo in self.final_states}

        for caracter in _normalizar(texto):
            while estado_actual is not self.root and caracter not in estado_actual["transitions"]:
                estado_actual = estado_actual.get("fail") or self.root
            if caracter in estado_actual["transitions"]:
                estado_actual = estado_actual["transitions"][caracter]
            self._recoger_outputs(estado_actual, resultados)

        return resultados

    def _recoger_outputs(self, estado: dict, resultados: Dict[str, Set[str]]):
        """Agrega al resultado los outputs del nodo y de sus enlaces de fallo."""
        for salida in estado.get("output", []):
            tipo = salida["tipo"]
            if tipo in resultados:
                resultados[tipo].add(salida["palabra"])

    # ============================================================
    # API para agrupar palabras por configuración
    # ============================================================
    #: (grupo, clave_en_config) de todos los grupos que usa el buscador.
    CLAVES_GRUPO = (
        ("fuertes", "palabras_fuertes"),
        ("medias", "palabras_clave"),
        ("contexto", "palabras_contexto"),
        ("castigo", "palabras_castigo"),
        ("excluidas", "palabras_excluidas"),
        ("incompatibles", "incompatibles"),
    )

    def search_compatibility(self, texto: str, cfg: dict) -> Dict[str, Set[str]]:
        """Busca en 'texto' todas las palabras de los grupos definidos en cfg.

        Cada grupo se etiqueta con su nombre (fuertes, medias, contexto,
        castigo, excluidas, incompatibles). Los grupos ausentes en cfg no
        generan resultados.
        """
        patrones = []
        for tipo, clave in self.CLAVES_GRUPO:
            for palabra in cfg.get(clave) or []:
                if str(palabra).strip():
                    patrones.append((str(palabra), tipo))
        motor = AhoCorasickEngine(patrones)
        return motor.search(texto)
