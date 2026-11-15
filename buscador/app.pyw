"""Mis Ofertas TI - Buscador de Puestos: app de escritorio Tkinter.

Gestiona ofertas de trabajo de TI en una tabla filtrable. Botones principales:
Buscar ahora, Verificar disponibilidad, Eliminar seleccionadas, Lista negra,
Marcar estados y Editar perfil.
"""
import ctypes
import os
import queue
import subprocess
import sys
import threading
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import tkinter as tk
from tkinter import messagebox, ttk

from almacen import escribir_json_atomico, leer_json
from compatibilidad import (
    CATEGORIA_COMPATIBLE,
    CATEGORIA_DESCARTADA,
    CATEGORIA_RELACIONADA,
    puntuar,
)
from fuentes.comun import sin_acentos
from main import (
    DATA,
    cargar_config,
    cargar_lista_negra,
    cargar_ofertas,
    clave_url,
    dias_lista_negra,
    eliminar_ofertas,
    guardar_config,
    guardar_lista_negra,
    guardar_ofertas,
    postulaciones_hoy,
    purgar_lista_negra,
    refrescar_reporte,
    registrar,
)
from puestos import FAMILIAS

# ---------- Paleta de colores ----------
COLORES = {
    "fondo": "#F4F6F9",
    "encabezado": "#1A5276",
    "acento": "#2E86C1",
    "acento_oscuro": "#1F6F8B",
    "peligro": "#C0392B",
    "verde": "#1E8449",
    "ambar": "#B9770E",
    "texto": "#2C3E50",
    "fila": "#EAF2F8",
    "blanco": "#FFFFFF",
}

UI_STATE_PATH = os.path.join(DATA, "ui_state.json")
VER_CATEGORIAS = {
    "Compatibles": CATEGORIA_COMPATIBLE,
    "Relacionadas": CATEGORIA_RELACIONADA,
    "Todas": "Todas",
}


# ---------- Funciones helper de modulo ----------
def cargar_estado_ui():
    """Lee la geometria, el orden y el panel de filtros de la ultima sesion."""
    datos = leer_json(UI_STATE_PATH, {})
    return datos if isinstance(datos, dict) else {}


def guardar_estado_ui(datos):
    """Guarda el estado visual sin romper la app si el archivo no se puede escribir."""
    try:
        escribir_json_atomico(UI_STATE_PATH, datos, indent=1)
    except Exception:
        pass


def _texto_busqueda(oferta):
    """Texto normalizado donde busca el filtro de la interfaz."""
    return sin_acentos(
        f"{oferta.get('titulo', '')} {oferta.get('ubicacion', '')} "
        f"{oferta.get('empresa', '')} {oferta.get('fuente', '')}"
    )


def es_remota(oferta, palabras_remoto=None):
    """Indica si el titulo o la ubicacion contienen alguna marca de trabajo remoto."""
    palabras = palabras_remoto or (
        "remoto", "teletrabajo", "remote", "hibrido", "home office",
    )
    texto = sin_acentos(f"{oferta.get('titulo', '')} {oferta.get('ubicacion', '')}")
    return any(
        sin_acentos(str(palabra)) in texto
        for palabra in palabras
        if str(palabra).strip()
    )


def en_zona(oferta, zonas):
    """Indica si la ubicacion de la oferta contiene alguna de las zonas dadas."""
    texto = sin_acentos(oferta.get("ubicacion", ""))
    return any(
        sin_acentos(str(zona)) in texto for zona in zonas if str(zona).strip()
    )


def filtrar(ofertas, texto="", estado="Todos", categoria="Todas", compat=None,
            fuentes=None, zonas=None, estados=None, solo_nuevas=False,
            sin_postular=False, solo_remoto=False, hoy=None, palabras_remoto=None,
            familias=None):
    """Devuelve las ofertas que cumplen todos los filtros pedidos.

    'compat' es el mapa {clave_url: resultado de puntuar}; si falta o la
    categoria es 'Todas', no se filtra por compatibilidad. 'estados' tiene
    prioridad sobre 'estado' para permitir seleccion multiple. 'familias'
    filtra por enfoque del puesto (Soporte, Redes, Infraestructura...).
    """
    t = sin_acentos(texto.strip()) if texto else ""
    fuentes = {str(f) for f in fuentes} if fuentes else None
    zonas = list(zonas) if zonas else None
    estados = {str(e) for e in estados} if estados else None
    familias = {str(f) for f in familias} if familias else None
    hoy = hoy or datetime.now().strftime("%Y-%m-%d")
    salida = []
    for o in ofertas:
        if t and t not in _texto_busqueda(o):
            continue
        est = (o.get("estado_envio") or "").strip()
        if estados is not None:
            if est not in estados:
                continue
        else:
            if estado == "Sin estado" and est:
                continue
            if estado in ("Postulado", "Descartado") and est != estado:
                continue
        if sin_postular and est:
            continue
        if solo_nuevas and (o.get("fecha") or "") != hoy:
            continue
        if fuentes and (o.get("fuente") or "") not in fuentes:
            continue
        if zonas and not en_zona(o, zonas):
            continue
        if solo_remoto and not es_remota(o, palabras_remoto):
            continue
        if categoria != "Todas" and compat is not None:
            info = compat.get(clave_url(o.get("url", "")))
            if not info or info.get("categoria") != categoria:
                continue
        if familias and compat is not None:
            info = compat.get(clave_url(o.get("url", ""))) or {}
            if info.get("familia") not in familias:
                continue
        salida.append(o)
    return salida


def ordenar(ofertas, criterio="compat", descendente=True, compat=None):
    """Ordena las ofertas por la columna elegida (compat, fecha, titulo...)."""
    def clave(oferta):
        """Valor de orden para una oferta segun el criterio activo."""
        if criterio == "compat":
            info = (compat or {}).get(clave_url(oferta.get("url", ""))) or {}
            return (info.get("porcentaje", 0), oferta.get("fecha") or "")
        if criterio == "enfoque":
            info = (compat or {}).get(clave_url(oferta.get("url", ""))) or {}
            return sin_acentos(info.get("familia") or "")
        if criterio in ("dias", "fecha"):
            return oferta.get("fecha") or ""
        if criterio == "estado":
            return sin_acentos(oferta.get("estado_envio") or "")
        if criterio == "empresa":
            return sin_acentos(oferta.get("empresa") or "")
        if criterio == "fuente":
            return sin_acentos(oferta.get("fuente") or "")
        if criterio == "ubicacion":
            return sin_acentos(oferta.get("ubicacion") or "")
        return sin_acentos(oferta.get("titulo") or "")

    return sorted(ofertas, key=clave, reverse=descendente)


def resumen_ofertas(ofertas, compat=None, cfg=None, hoy=None):
    """Cuenta ofertas por categoria, fuente, zona, enfoque, estado y atajos."""
    cfg = cfg or {}
    hoy = hoy or datetime.now().strftime("%Y-%m-%d")
    categorias = {"compatibles": 0, "relacionadas": 0, "descartadas": 0}
    fuentes = {}
    zonas = {str(zona): 0 for zona in cfg.get("zonas", [])}
    familias = {}
    estados = {"Sin estado": 0, "Postulado": 0, "Descartado": 0}
    nuevas = 0
    remotas = 0
    sin_postular = 0
    for oferta in ofertas:
        info = (compat or {}).get(clave_url(oferta.get("url", ""))) or {}
        categoria = info.get("categoria")
        if categoria == CATEGORIA_COMPATIBLE:
            categorias["compatibles"] += 1
        elif categoria == CATEGORIA_RELACIONADA:
            categorias["relacionadas"] += 1
        elif categoria == CATEGORIA_DESCARTADA:
            categorias["descartadas"] += 1
        familia = info.get("familia")
        if familia:
            familias[familia] = familias.get(familia, 0) + 1
        fuente = (oferta.get("fuente") or "").strip() or "Otra"
        fuentes[fuente] = fuentes.get(fuente, 0) + 1
        for zona in zonas:
            if en_zona(oferta, [zona]):
                zonas[zona] += 1
        estado = (oferta.get("estado_envio") or "").strip()
        etiqueta = estado if estado in ("Postulado", "Descartado") else "Sin estado"
        estados[etiqueta] = estados.get(etiqueta, 0) + 1
        if (oferta.get("fecha") or "") == hoy:
            nuevas += 1
        if es_remota(oferta, cfg.get("palabras_remoto")):
            remotas += 1
        if not estado:
            sin_postular += 1
    return {
        "categorias": categorias,
        "fuentes": fuentes,
        "zonas": zonas,
        "familias": familias,
        "estados": estados,
        "nuevas": nuevas,
        "remotas": remotas,
        "sin_postular": sin_postular,
    }


def aplicar_estado(urls, estado):
    """Asigna 'estado' a las ofertas de las URLs dadas, guarda y devuelve cuantas toco."""
    claves = {clave_url(u) for u in urls}
    ofertas = cargar_ofertas()
    n = 0
    for o in ofertas:
        if clave_url(o.get("url", "")) in claves:
            o["estado_envio"] = estado
            n += 1
    if n:
        guardar_ofertas(ofertas)
        refrescar_reporte(0)
        registrar(f"ESTADO '{estado}' filas={n}")
    return n


def restaurar_negra(urls):
    """Quita las URLs dadas de la lista negra, guarda y devuelve cuantas se restauraron."""
    claves = {clave_url(u) for u in urls}
    negra = cargar_lista_negra()
    n = 0
    for k in claves:
        if k in negra:
            negra.pop(k)
            n += 1
    if n:
        guardar_lista_negra(negra)
        registrar(f"NEGRA restauradas={n}")
    return n


def python_consola():
    """Devuelve la ruta de python.exe (evita pythonw.exe) para lanzar subprocess con consola."""
    exe = sys.executable or ""
    if exe.lower().endswith("pythonw.exe"):
        candidato = os.path.join(os.path.dirname(exe), "python.exe")
        if os.path.exists(candidato):
            return candidato
    return exe or "python"


def dias_de(fecha, hoy):
    """Dias transcurridos entre 'fecha' y 'hoy' (YYYY-MM-DD); None si no se pueden leer."""
    from datetime import datetime

    try:
        return (datetime.strptime(hoy, "%Y-%m-%d") - datetime.strptime(fecha, "%Y-%m-%d")).days
    except Exception:
        return None


def calcular_estadisticas(ofertas, hoy=None, compat=None):
    """Resume las ofertas para la ventana de estadisticas.

    Recibe la lista de ofertas, 'hoy' opcional (YYYY-MM-DD) y el mapa de
    compatibilidad {clave_url: resultado}. Devuelve un dict con 'total',
    'estados' (postuladas/descartadas/sin_estado), 'por_dia' (ultimos 7 dias),
    'fuentes' (ordenadas de mayor a menor) y 'categorias' (compatibles,
    relacionadas, descartadas).
    """
    from datetime import datetime, timedelta

    if not hoy:
        hoy = datetime.now().strftime("%Y-%m-%d")
    estados = {"postuladas": 0, "descartadas": 0, "sin_estado": 0}
    categorias = {"compatibles": 0, "relacionadas": 0, "descartadas": 0}
    familias = {}
    por_fecha = {}
    fuentes = {}
    for o in ofertas:
        est = (o.get("estado_envio") or "").strip()
        if est == "Postulado":
            estados["postuladas"] += 1
        elif est == "Descartado":
            estados["descartadas"] += 1
        else:
            estados["sin_estado"] += 1
        fecha = (o.get("fecha") or "").strip()
        if fecha:
            por_fecha[fecha] = por_fecha.get(fecha, 0) + 1
        fuente = (o.get("fuente") or "").strip() or "Otra"
        fuentes[fuente] = fuentes.get(fuente, 0) + 1
        if compat is not None:
            info = compat.get(clave_url(o.get("url", ""))) or {}
            cat = info.get("categoria")
            if cat == CATEGORIA_COMPATIBLE:
                categorias["compatibles"] += 1
            elif cat == CATEGORIA_RELACIONADA:
                categorias["relacionadas"] += 1
            elif cat == CATEGORIA_DESCARTADA:
                categorias["descartadas"] += 1
            familia = info.get("familia")
            if familia:
                familias[familia] = familias.get(familia, 0) + 1
    base = datetime.strptime(hoy, "%Y-%m-%d")
    por_dia = []
    for i in range(6, -1, -1):
        dia = (base - timedelta(days=i)).strftime("%Y-%m-%d")
        por_dia.append((dia, por_fecha.get(dia, 0)))
    fuentes_ordenadas = sorted(fuentes.items(), key=lambda kv: (-kv[1], kv[0]))
    familias_ordenadas = sorted(familias.items(), key=lambda kv: (-kv[1], kv[0]))
    return {"total": len(ofertas), "estados": estados, "por_dia": por_dia,
            "fuentes": fuentes_ordenadas, "familias": familias_ordenadas,
            "categorias": categorias}


def guardar_config_parcial(actualizacion):
    """Fusiona las claves de 'actualizacion' en config.json y lo guarda."""
    datos = cargar_config()
    datos.update(actualizacion)
    return guardar_config(datos)


class Aplicacion:
    def __init__(self, raiz):
        """Monta la ventana: estado visual, estilos, interfaz, cola y carga inicial."""
        self.raiz = raiz
        self.cola = queue.Queue()
        self.trabajando = False
        self.ofertas = []
        self.ofertas_por_url = {}
        self.negra = {}
        self.cfg = {}
        self.compat = {}
        self._auto_id = None
        self._pintar_id = None
        self._proxima_auto = None
        self.estado_ui = cargar_estado_ui()
        self.orden_criterio = self.estado_ui.get("orden_criterio", "compat")
        self.orden_desc = bool(self.estado_ui.get("orden_desc", True))
        self._filtros_abiertos = bool(self.estado_ui.get("filtros_abiertos", False))
        self.var_texto = tk.StringVar()
        self.var_categoria = tk.StringVar(value="Compatibles")
        self.var_nuevas = tk.BooleanVar(value=False)
        self.var_sin_postular = tk.BooleanVar(value=False)
        self.var_remoto = tk.BooleanVar(value=False)
        self.var_auto = tk.BooleanVar(value=False)
        self.var_fuentes = {}
        self.var_zonas = {}
        self.var_estados = {}
        self.var_familias = {}
        self.chips = []
        self._estilos()
        self._construir()
        self.recargar()
        minutos_auto = int(cargar_config().get("app_auto_minutos", 0) or 0)
        self.var_auto.set(minutos_auto > 0)
        if minutos_auto > 0:
            self._programar_auto(minutos_auto)
        self._actualizar_lbl_auto()

    def _estilos(self):
        """Configura el tema 'clam' y los estilos ttk (botones, tabla, entradas, barra)."""
        s = ttk.Style()
        s.theme_use("clam")
        s.configure(".", font=("Segoe UI", 10), background=COLORES["fondo"], foreground=COLORES["texto"])
        s.configure("TFrame", background=COLORES["fondo"])
        s.configure("Fondo.TFrame", background=COLORES["encabezado"])
        s.configure("Toolbar.TFrame", background=COLORES["fondo"])
        s.configure(
            "TButton",
            background=COLORES["acento"],
            foreground=COLORES["blanco"],
            borderwidth=0,
            padding=(12, 7),
            font=("Segoe UI", 10, "bold"),
        )
        s.map("TButton", background=[("active", COLORES["acento_oscuro"]), ("disabled", "#AAB7C4")],
              foreground=[("disabled", "#EEF2F5")])
        s.configure("Peligro.TButton", background=COLORES["peligro"])
        s.map("Peligro.TButton", background=[("active", "#96281B"), ("disabled", "#AAB7C4")])
        s.configure("Verde.TButton", background=COLORES["verde"])
        s.map("Verde.TButton", background=[("active", "#196F3D"), ("disabled", "#AAB7C4")])
        s.configure("Secundario.TButton", background="#DCE4EC", foreground=COLORES["texto"])
        s.map(
            "Secundario.TButton",
            background=[("active", "#C9D6E3"), ("disabled", "#E5E8EB")],
            foreground=[("disabled", "#8C9AA8")],
        )
        s.configure("Pequeno.TButton", padding=(8, 4), font=("Segoe UI", 9))
        s.configure(
            "TMenubutton",
            background="#DCE4EC",
            foreground=COLORES["texto"],
            padding=(10, 7),
            font=("Segoe UI", 10, "bold"),
        )
        s.map("TMenubutton", background=[("active", "#C9D6E3")])
        s.configure(
            "Panel.TCheckbutton",
            background=COLORES["fondo"],
            font=("Segoe UI", 9),
        )
        s.map(
            "Panel.TCheckbutton",
            background=[("active", COLORES["fondo"])],
        )
        s.configure("Treeview", background=COLORES["blanco"], fieldbackground=COLORES["blanco"],
                    foreground=COLORES["texto"], rowheight=27, font=("Segoe UI", 10))
        s.map("Treeview", background=[("selected", COLORES["acento"])],
              foreground=[("selected", COLORES["blanco"])])
        s.configure("Treeview.Heading", background=COLORES["encabezado"], foreground=COLORES["blanco"],
                    font=("Segoe UI", 10, "bold"), padding=(8, 7))
        s.map("Treeview.Heading", background=[("active", COLORES["encabezado"])])
        s.configure("TEntry", fieldbackground=COLORES["blanco"], padding=(8, 6))
        s.configure("TCombobox", padding=(8, 6))
        s.configure("TCheckbutton", background="#DCE4EC")
        s.map("TCheckbutton", background=[("active", "#DCE4EC")],
              foreground=[("active", COLORES["acento_oscuro"])])
        s.configure("Horizontal.TProgressbar", background=COLORES["acento"], troughcolor="#DCE4EC")

    # ---------- Construccion de la ventana ----------
    def _construir(self):
        """Crea encabezado, acciones, filtros, tabla y pie con jerarquia clara."""
        r = self.raiz
        r.title("Mis Ofertas TI - Buscador de Puestos")
        geometria = self.estado_ui.get("geometry") or "1180x700"
        try:
            r.geometry(geometria)
        except Exception:
            r.geometry("1180x700")
        r.minsize(1000, 560)
        r.configure(bg=COLORES["fondo"])
        r.protocol("WM_DELETE_WINDOW", self.cerrar)

        cab = tk.Frame(r, bg=COLORES["encabezado"], padx=16, pady=12)
        cab.pack(fill="x")
        tk.Label(
            cab,
            text="\U0001F4CB Mis Ofertas TI",
            bg=COLORES["encabezado"],
            fg=COLORES["blanco"],
            font=("Segoe UI", 15, "bold"),
        ).pack(side="left")
        self.badges = tk.Label(
            cab, text="", bg=COLORES["encabezado"], fg="#D6EAF8", font=("Segoe UI", 10)
        )
        self.badges.pack(side="left", padx=(16, 0))
        self.menu_btn = ttk.Menubutton(cab, text="\u22ee", style="TMenubutton")
        self.menu_btn.pack(side="right")
        self.btn_perfil = ttk.Button(
            cab,
            text="\u2699 Perfil",
            style="Secundario.TButton",
            command=self.accion_perfil,
        )
        self.btn_perfil.pack(side="right", padx=(0, 8))

        barra = tk.Frame(r, bg=COLORES["fondo"], padx=12, pady=10)
        barra.pack(fill="x")
        self.btn_buscar = ttk.Button(
            barra, text="\U0001F504 Buscar ahora", command=self.accion_buscar
        )
        self.btn_buscar.pack(side="left", padx=(0, 8))
        self.btn_verificar = ttk.Button(
            barra,
            text="\U0001F50E Verificar",
            style="Secundario.TButton",
            command=self.accion_verificar,
        )
        self.btn_verificar.pack(side="left")
        self.progreso = ttk.Progressbar(barra, mode="indeterminate", length=160)

        filtro = tk.Frame(r, bg=COLORES["fondo"], padx=12)
        filtro.pack(fill="x", pady=(0, 4))
        fila1 = tk.Frame(filtro, bg=COLORES["fondo"])
        fila1.pack(fill="x")
        tk.Label(fila1, text="\U0001F50D", bg=COLORES["fondo"]).pack(side="left")
        self.entrada_busqueda = ttk.Entry(fila1, textvariable=self.var_texto)
        self.entrada_busqueda.pack(side="left", fill="x", expand=True, padx=(6, 4))
        ttk.Button(
            fila1,
            text="\u00d7",
            width=3,
            style="Pequeno.TButton",
            command=self.limpiar_texto,
        ).pack(side="left", padx=(0, 6))
        self.btn_filtros = ttk.Button(
            fila1,
            text="Filtros \u25be",
            style="Secundario.TButton",
            command=self._alternar_panel_filtros,
        )
        self.btn_filtros.pack(side="left", padx=(0, 6))
        self.btn_limpiar = ttk.Button(
            fila1, text="Limpiar", style="Pequeno.TButton", command=self.limpiar_filtros
        )
        self.btn_limpiar.pack(side="left")
        self.var_texto.trace_add("write", lambda *a: self._programar_pintar())

        self.fila_chips = tk.Frame(filtro, bg=COLORES["fondo"])
        self.fila_chips.pack(fill="x", pady=(8, 0))
        self._crear_chip(
            self.fila_chips, "Compatibles", self.var_categoria, "Compatibles", True
        )
        self._crear_chip(
            self.fila_chips, "Relacionadas", self.var_categoria, "Relacionadas", True
        )
        self._crear_chip(self.fila_chips, "Todas", self.var_categoria, "Todas", True)
        tk.Frame(self.fila_chips, width=12, bg=COLORES["fondo"]).pack(side="left")
        self._crear_chip(self.fila_chips, "Nuevas hoy", self.var_nuevas)
        self._crear_chip(self.fila_chips, "Sin postular", self.var_sin_postular)
        self._crear_chip(self.fila_chips, "Remoto", self.var_remoto)
        self.lbl_filtros_activos = tk.Label(
            filtro,
            text="",
            bg=COLORES["fondo"],
            fg="#5D6D7E",
            font=("Segoe UI", 8),
            anchor="w",
        )
        self.lbl_filtros_activos.pack(fill="x", pady=(2, 0))

        self.panel_filtros = tk.Frame(r, bg=COLORES["fondo"], padx=12, pady=4)
        self._construir_panel_filtros()

        self.barra_sel = tk.Frame(r, bg="#E8EEF4", padx=12, pady=6)
        self.lbl_sel = tk.Label(
            self.barra_sel,
            text="",
            bg="#E8EEF4",
            fg=COLORES["texto"],
            font=("Segoe UI", 10, "bold"),
        )
        self.lbl_sel.pack(side="left", padx=(0, 10))
        self.combo_estado_accion = ttk.Combobox(
            self.barra_sel,
            values=["Postulado", "Descartado", "(vacio)"],
            state="readonly",
            width=12,
        )
        self.combo_estado_accion.set("Postulado")
        self.combo_estado_accion.pack(side="left", padx=(0, 4))
        self.btn_marcar = ttk.Button(
            self.barra_sel,
            text="Marcar",
            style="Verde.TButton",
            command=self.accion_marcar,
        )
        self.btn_marcar.pack(side="left", padx=(0, 8))
        self.btn_eliminar = ttk.Button(
            self.barra_sel,
            text="Eliminar",
            style="Peligro.TButton",
            command=self.accion_eliminar,
        )
        self.btn_eliminar.pack(side="left", padx=(0, 8))
        self.btn_copiar = ttk.Button(
            self.barra_sel,
            text="Copiar enlace",
            style="Secundario.TButton",
            command=self.copiar_enlace,
        )
        self.btn_copiar.pack(side="left", padx=(0, 8))
        self.btn_abrir = ttk.Button(
            self.barra_sel,
            text="Abrir",
            style="Secundario.TButton",
            command=self.abrir_oferta,
        )
        self.btn_abrir.pack(side="left")
        self._set_habilitado(
            False, self.btn_eliminar, self.btn_marcar, self.btn_copiar, self.btn_abrir
        )

        self.marco_tabla = tk.Frame(r, padx=12, pady=0)
        self.marco_tabla.pack(fill="both", expand=True)
        cols = ("titulo", "empresa", "enfoque", "compat", "ubicacion", "dias", "estado")
        self.tabla = ttk.Treeview(
            self.marco_tabla, columns=cols, show="headings", selectmode="extended"
        )
        for columna, texto, ancho, anclaje in (
            ("titulo", "Puesto", 320, "w"),
            ("empresa", "Empresa", 135, "w"),
            ("enfoque", "Enfoque", 100, "center"),
            ("compat", "Compat", 70, "center"),
            ("ubicacion", "Ubicacion", 175, "w"),
            ("dias", "Dias", 45, "center"),
            ("estado", "Estado", 90, "center"),
        ):
            self.tabla.heading(
                columna,
                text=texto,
                command=lambda c=columna: self.ordenar_por(c),
            )
            self.tabla.column(
                columna, width=ancho, anchor=anclaje, stretch=(columna == "titulo")
            )
        self._actualizar_encabezados()
        scroll = ttk.Scrollbar(
            self.marco_tabla, orient="vertical", command=self.tabla.yview
        )
        self.tabla.configure(yscrollcommand=scroll.set)
        self.tabla.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tabla.tag_configure("nueva", font=("Segoe UI", 10, "bold"))
        self.tabla.tag_configure("postulado", foreground="#1F618D")
        self.tabla.tag_configure("descartado", foreground="#7F8C8D")
        self.tabla.tag_configure("compat", foreground=COLORES["verde"])
        self.tabla.tag_configure("rel", foreground=COLORES["ambar"])
        self.tabla.tag_configure("alt", background=COLORES["fila"])
        self.tabla.bind("<Double-1>", self.abrir_oferta)
        self.tabla.bind("<<TreeviewSelect>>", self.al_seleccionar)
        self.tabla.bind("<Control-a>", self.seleccionar_todo)
        self.tabla.bind("<Control-A>", self.seleccionar_todo)
        self.tabla.bind("<Return>", self.abrir_oferta)
        self.tabla.bind("<Delete>", lambda _e: self.accion_eliminar())
        self.tabla.bind("<Button-3>", self._menu_contextual)
        self._construir_menu_tabla()

        pie = tk.Frame(r, bg="#DCE4EC", padx=12, pady=7)
        pie.pack(fill="x", side="bottom")
        self.lbl_mensaje = tk.Label(
            pie,
            text="Listo. Ctrl/Shift+clic = elegir varios  \u2022  Ctrl+A = todo",
            bg="#DCE4EC",
            fg=COLORES["texto"],
            font=("Segoe UI", 10),
        )
        self.lbl_mensaje.pack(side="left")
        self.lbl_detalle = tk.Label(
            pie, text="", bg="#DCE4EC", fg="#5D6D7E", font=("Segoe UI", 9)
        )
        self.lbl_detalle.pack(side="left", padx=(16, 0))
        self.lbl_cuentas = tk.Label(
            pie, text="", bg="#DCE4EC", fg="#5D6D7E", font=("Segoe UI", 10)
        )
        self.lbl_cuentas.pack(side="right")
        self.lbl_auto = tk.Label(
            pie, text="", bg="#DCE4EC", fg="#5D6D7E", font=("Segoe UI", 9)
        )
        self.lbl_auto.pack(side="right", padx=(0, 8))
        self.chk_auto = ttk.Checkbutton(
            pie, text="Auto", variable=self.var_auto, command=self.alternar_auto
        )
        self.chk_auto.pack(side="right", padx=(0, 6))

        self._construir_menu()
        self._aplicar_visibilidad_panel()
        self._al_cambiar_chip()
        self._actualizar_resumen_filtros()
        self._actualizar_lbl_auto()

        r.bind("<F5>", lambda _e: self.accion_buscar())
        r.bind("<Control-f>", lambda _e: self._enfocar_busqueda())
        r.bind("<Control-F>", lambda _e: self._enfocar_busqueda())
        r.bind("<Escape>", lambda _e: self._escape())

    def _construir_menu(self):
        """Crea el menu de mantenimiento y lo asocia al boton de tres puntos."""
        self.menu = tk.Menu(self.raiz, tearoff=0)
        self.menu.add_command(
            label="Verificar disponibilidad", command=self.accion_verificar
        )
        self.menu.add_command(label="Lista negra", command=self.accion_negra)
        self.menu.add_command(
            label="Depurar incompatibles", command=self.accion_depurar
        )
        self.menu.add_separator()
        self.menu.add_command(label="Estadisticas", command=self.accion_estadisticas)
        self.menu.add_command(label="Preferencias", command=self.accion_preferencias)
        self.menu.add_command(label="Atajos de teclado", command=self.accion_atajos)
        self.menu.add_separator()
        self.menu.add_command(label="Salir", command=self.cerrar)
        self.menu_btn.configure(menu=self.menu)

    def _construir_menu_tabla(self):
        """Crea el menu contextual de la tabla."""
        self.menu_tabla = tk.Menu(self.raiz, tearoff=0)
        self.menu_tabla.add_command(label="Abrir oferta", command=self.abrir_oferta)
        self.menu_tabla.add_command(label="Copiar enlace", command=self.copiar_enlace)
        self.menu_tabla.add_separator()
        self.menu_tabla.add_command(
            label="Marcar como Postulado",
            command=lambda: self.accion_marcar_valor("Postulado"),
        )
        self.menu_tabla.add_command(
            label="Marcar como Descartado",
            command=lambda: self.accion_marcar_valor("Descartado"),
        )
        self.menu_tabla.add_command(
            label="Quitar estado", command=lambda: self.accion_marcar_valor("")
        )
        self.menu_tabla.add_separator()
        self.menu_tabla.add_command(label="Eliminar", command=self.accion_eliminar)

    def _construir_panel_filtros(self):
        """Crea las cuatro secciones de filtros avanzados (fuente, zona, estado y enfoque)."""
        for indice in range(4):
            self.panel_filtros.columnconfigure(indice, weight=1)
        self._secciones = {
            "fuentes": self._crear_seccion_filtro("Fuente", 0, "fuentes"),
            "zonas": self._crear_seccion_filtro("Zona", 1, "zonas"),
            "estados": self._crear_seccion_filtro("Estado", 2, "estados"),
            "familias": self._crear_seccion_filtro("Enfoque", 3, "familias"),
        }

    def _crear_seccion_filtro(self, titulo, columna, clave):
        """Crea una seccion con titulo, boton Todas y un contenedor de opciones."""
        marco = tk.LabelFrame(
            self.panel_filtros,
            text=titulo,
            bg=COLORES["fondo"],
            fg=COLORES["texto"],
            font=("Segoe UI", 9, "bold"),
            padx=8,
            pady=4,
        )
        marco.grid(
            row=0, column=columna, sticky="nsew", padx=(0, 8), pady=(0, 4)
        )
        cabecera = tk.Frame(marco, bg=COLORES["fondo"])
        cabecera.pack(fill="x")
        tk.Label(
            cabecera,
            text="(ninguno = todos)",
            bg=COLORES["fondo"],
            fg="#7F8C8D",
            font=("Segoe UI", 8),
        ).pack(side="left")
        ttk.Button(
            cabecera,
            text="Todas",
            style="Pequeno.TButton",
            command=lambda c=clave: self._marcar_todas(c),
        ).pack(side="right")
        contenido = tk.Frame(marco, bg=COLORES["fondo"])
        contenido.pack(fill="both", expand=True)
        return contenido

    def _crear_chip(self, padre, texto, variable, valor=None, radio=False):
        """Crea un chip de filtro rapido y lo registra para actualizar sus conteos."""
        opciones = {
            "text": texto,
            "indicatoron": 0,
            "bd": 0,
            "relief": "flat",
            "highlightthickness": 0,
            "padx": 10,
            "pady": 4,
            "font": ("Segoe UI", 9, "bold"),
            "cursor": "hand2",
            "command": self._al_cambiar_chip,
            "bg": "#DCE4EC",
            "fg": COLORES["texto"],
            "activebackground": "#C9D6E3",
            "activeforeground": COLORES["texto"],
            "selectcolor": "#DCE4EC",
        }
        if radio:
            widget = tk.Radiobutton(
                padre, variable=variable, value=valor, **opciones
            )
        else:
            widget = tk.Checkbutton(padre, variable=variable, **opciones)
        widget.pack(side="left", padx=(0, 6))
        self.chips.append(
            {
                "widget": widget,
                "variable": variable,
                "valor": valor,
                "base": texto,
                "radio": radio,
            }
        )
        self._pintar_chip(widget, False)
        return widget

    def _pintar_chip(self, widget, activo):
        """Aplica el color de seleccion o reposo a un chip."""
        widget.configure(
            bg=COLORES["acento"] if activo else "#DCE4EC",
            fg=COLORES["blanco"] if activo else COLORES["texto"],
            activebackground=COLORES["acento_oscuro"] if activo else "#C9D6E3",
            activeforeground=COLORES["blanco"] if activo else COLORES["texto"],
            selectcolor=COLORES["acento"] if activo else "#DCE4EC",
        )

    def _al_cambiar_chip(self):
        """Repinta los chips, actualiza el resumen y agenda el filtrado."""
        for chip in self.chips:
            if chip["radio"]:
                activo = chip["variable"].get() == chip["valor"]
            else:
                activo = bool(chip["variable"].get())
            self._pintar_chip(chip["widget"], activo)
        self._actualizar_resumen_filtros()
        self._programar_pintar()

    def _actualizar_chips(self):
        """Actualiza los conteos que muestran los chips."""
        resumen = resumen_ofertas(self.ofertas, self.compat, self.cfg, datetime_hoy())
        conteos = {
            "Compatibles": resumen["categorias"]["compatibles"],
            "Relacionadas": resumen["categorias"]["relacionadas"],
            "Todas": len(self.ofertas),
            "Nuevas hoy": resumen["nuevas"],
            "Sin postular": resumen["sin_postular"],
            "Remoto": resumen["remotas"],
        }
        for chip in self.chips:
            if chip["base"] in conteos:
                chip["widget"].configure(
                    text=f"{chip['base']} ({conteos[chip['base']]})"
                )

    def _sincronizar_vars(self, variables, claves):
        """Conserva las selecciones y crea las opciones nuevas seleccionadas."""
        for clave in list(variables):
            if clave not in claves:
                del variables[clave]
        for clave in claves:
            if clave not in variables:
                variables[clave] = tk.BooleanVar(value=True)

    def _poblar_opciones(self, clave, variables, opciones):
        """Repuebla una seccion de filtros con checkbuttons y sus conteos."""
        contenido = self._secciones[clave]
        for hijo in contenido.winfo_children():
            hijo.destroy()
        claves = [opcion[0] for opcion in opciones]
        self._sincronizar_vars(variables, claves)
        if not opciones:
            tk.Label(
                contenido,
                text="Sin datos",
                bg=COLORES["fondo"],
                fg="#7F8C8D",
                font=("Segoe UI", 9),
            ).pack(anchor="w")
            return
        for valor, etiqueta, conteo in opciones:
            ttk.Checkbutton(
                contenido,
                text=f"{etiqueta} ({conteo})",
                variable=variables[valor],
                style="Panel.TCheckbutton",
                command=lambda c=clave: self._al_cambiar_opcion(c),
            ).pack(anchor="w")

    def _refrescar_opciones_filtros(self):
        """Recalcula las opciones disponibles de fuente, zona y estado."""
        resumen = resumen_ofertas(self.ofertas, self.compat, self.cfg, datetime_hoy())
        fuentes = sorted(
            ((nombre, nombre, conteo) for nombre, conteo in resumen["fuentes"].items()),
            key=lambda opcion: (-opcion[2], opcion[1]),
        )
        zonas = sorted(
            (
                (zona, zona.title(), conteo)
                for zona, conteo in resumen["zonas"].items()
                if conteo > 0
            ),
            key=lambda opcion: (-opcion[2], opcion[1]),
        )
        estados = [
            (estado, estado, resumen["estados"].get(estado, 0))
            for estado in ("Sin estado", "Postulado", "Descartado")
        ]
        orden_familias = {familia: indice for indice, familia in enumerate(FAMILIAS)}
        familias = sorted(
            (
                (familia, familia, conteo)
                for familia, conteo in resumen["familias"].items()
                if conteo > 0
            ),
            key=lambda opcion: (orden_familias.get(opcion[0], 99), -opcion[2]),
        )
        self._poblar_opciones("fuentes", self.var_fuentes, fuentes)
        self._poblar_opciones("zonas", self.var_zonas, zonas)
        self._poblar_opciones("estados", self.var_estados, estados)
        self._poblar_opciones("familias", self.var_familias, familias)

    def _al_cambiar_opcion(self, clave):
        """Evita dejar una seccion sin opciones y agenda el filtrado."""
        variables = getattr(self, "var_" + clave)
        if not any(variable.get() for variable in variables.values()):
            for variable in variables.values():
                variable.set(True)
        self._actualizar_resumen_filtros()
        self._programar_pintar()

    def _marcar_todas(self, clave):
        """Marca todas las opciones de una seccion de filtros."""
        for variable in getattr(self, "var_" + clave).values():
            variable.set(True)
        self._actualizar_resumen_filtros()
        self._programar_pintar()

    def _seleccion_parcial(self, variables, etiqueta):
        """Describe una seleccion parcial de filtros (o None si estan todos)."""
        elegidas = [clave for clave, variable in variables.items() if variable.get()]
        if not elegidas or len(elegidas) == len(variables):
            return None
        if len(elegidas) <= 2:
            return f"{etiqueta}: {', '.join(elegidas)}"
        return f"{etiqueta}: {len(elegidas)}"

    def _leer_filtros(self):
        """Devuelve los filtros activos listos para pasar a filtrar()."""
        fuentes = {clave for clave, variable in self.var_fuentes.items() if variable.get()}
        zonas = {clave for clave, variable in self.var_zonas.items() if variable.get()}
        estados = {clave for clave, variable in self.var_estados.items() if variable.get()}
        familias = {clave for clave, variable in self.var_familias.items() if variable.get()}
        return {
            "texto": self.var_texto.get(),
            "categoria": VER_CATEGORIAS.get(self.var_categoria.get(), "Todas"),
            "fuentes": None if len(fuentes) == len(self.var_fuentes) else fuentes,
            "zonas": None if len(zonas) == len(self.var_zonas) else zonas,
            "estados": (
                None
                if len(estados) == len(self.var_estados)
                else {"" if estado == "Sin estado" else estado for estado in estados}
            ),
            "familias": (
                None
                if len(familias) == len(self.var_familias)
                else familias
            ),
            "solo_nuevas": bool(self.var_nuevas.get()),
            "sin_postular": bool(self.var_sin_postular.get()),
            "solo_remoto": bool(self.var_remoto.get()),
            "hoy": datetime_hoy(),
            "palabras_remoto": self.cfg.get("palabras_remoto"),
        }

    def _actualizar_resumen_filtros(self):
        """Muestra los filtros activos y actualiza el boton y el boton Limpiar."""
        partes = []
        texto = self.var_texto.get().strip()
        if texto:
            partes.append(f'Texto: "{texto[:28]}"')
        if self.var_nuevas.get():
            partes.append("Nuevas hoy")
        if self.var_sin_postular.get():
            partes.append("Sin postular")
        if self.var_remoto.get():
            partes.append("Remoto")
        for variables, etiqueta in (
            (self.var_fuentes, "Fuente"),
            (self.var_zonas, "Zona"),
            (self.var_estados, "Estado"),
            (self.var_familias, "Enfoque"),
        ):
            resumen = self._seleccion_parcial(variables, etiqueta)
            if resumen:
                partes.append(resumen)
        self.btn_filtros.config(
            text=f"Filtros ({len(partes)}) \u25be" if partes else "Filtros \u25be"
        )
        self.lbl_filtros_activos.config(text="  \u00b7  ".join(partes))
        if partes and not self.lbl_filtros_activos.winfo_manager():
            self.lbl_filtros_activos.pack(fill="x", pady=(2, 0))
        elif not partes:
            self.lbl_filtros_activos.pack_forget()
        self._set_habilitado(bool(partes), self.btn_limpiar)

    def _alternar_panel_filtros(self):
        """Muestra u oculta el panel de filtros avanzados y guarda la preferencia."""
        self._filtros_abiertos = not self._filtros_abiertos
        self._aplicar_visibilidad_panel()
        self._guardar_estado_ui()

    def _aplicar_visibilidad_panel(self):
        """Aplica si el panel de filtros avanzados debe estar visible."""
        if self._filtros_abiertos:
            ancla = (
                self.barra_sel
                if self.barra_sel.winfo_manager()
                else self.marco_tabla
            )
            self.panel_filtros.pack(
                fill="x", padx=12, pady=(0, 8), before=ancla
            )
        else:
            self.panel_filtros.pack_forget()

    def _programar_pintar(self):
        """Agenda un repintado con debounce para no repintar en cada tecla."""
        if self._pintar_id is not None:
            self.raiz.after_cancel(self._pintar_id)
        self._pintar_id = self.raiz.after(250, self._pintar_ahora)

    def _pintar_ahora(self):
        """Ejecuta el repintado pendiente y actualiza el resumen de filtros."""
        self._pintar_id = None
        self._actualizar_resumen_filtros()
        self.pintar()

    def _enfocar_busqueda(self):
        """Lleva el foco al buscador y selecciona su contenido."""
        self.entrada_busqueda.focus_set()
        self.entrada_busqueda.select_range(0, "end")

    def _escape(self):
        """Limpia la seleccion, el texto o los filtros, en ese orden."""
        if self.urls_seleccionadas():
            self.limpiar_seleccion()
        elif self.var_texto.get():
            self.limpiar_texto()
        else:
            self.limpiar_filtros()

    def _menu_contextual(self, evento):
        """Selecciona la fila bajo el cursor y abre el menu contextual."""
        fila = self.tabla.identify_row(evento.y)
        if fila and fila not in self.tabla.selection():
            self.tabla.selection_set(fila)
            self.tabla.focus(fila)
        try:
            self.menu_tabla.tk_popup(evento.x_root, evento.y_root)
        finally:
            self.menu_tabla.grab_release()

    def ordenar_por(self, columna):
        """Ordena por la columna clicada y alterna ascendente/descendente."""
        if self.orden_criterio == columna:
            self.orden_desc = not self.orden_desc
        else:
            self.orden_criterio = columna
            self.orden_desc = columna in ("compat", "dias")
        self._actualizar_encabezados()
        self.pintar()
        self._guardar_estado_ui()

    def _actualizar_encabezados(self):
        """Pinta los encabezados con la flecha del orden activo."""
        titulos = {
            "titulo": "Puesto",
            "empresa": "Empresa",
            "enfoque": "Enfoque",
            "compat": "Compat",
            "ubicacion": "Ubicacion",
            "dias": "Dias",
            "estado": "Estado",
        }
        for columna, texto in titulos.items():
            if columna == self.orden_criterio:
                texto += " \u25bc" if self.orden_desc else " \u25b2"
            self.tabla.heading(columna, text=texto)

    def _guardar_estado_ui(self):
        """Guarda geometria, orden y panel de filtros para la proxima sesion."""
        guardar_estado_ui(
            {
                "geometry": self.raiz.geometry(),
                "orden_criterio": self.orden_criterio,
                "orden_desc": self.orden_desc,
                "filtros_abiertos": self._filtros_abiertos,
            }
        )

    def _actualizar_lbl_auto(self):
        """Muestra el estado y la proxima ejecucion de la busqueda automatica."""
        if self.var_auto.get() and self._proxima_auto:
            self.lbl_auto.config(
                text=f"proxima {self._proxima_auto.strftime('%H:%M')}"
            )
        elif self.var_auto.get():
            self.lbl_auto.config(text="activa")
        else:
            self.lbl_auto.config(text="apagada")

    def cerrar(self):
        """Cancela temporizadores, guarda el estado visual y cierra la ventana."""
        self._cancelar_auto()
        if self._pintar_id is not None:
            self.raiz.after_cancel(self._pintar_id)
            self._pintar_id = None
        self._guardar_estado_ui()
        self.raiz.destroy()

    def _set_habilitado(self, activo, *botones):
        """Habilita o deshabilita los botones ttk recibidos segun el flag 'activo'."""
        for b in botones:
            if activo:
                b.state(["!disabled"])
            else:
                b.state(["disabled"])

    def mensaje(self, texto, color=None):
        """Escribe un aviso (y color opcional) en la barra de estado del pie."""
        self.lbl_mensaje.config(text=texto, fg=color or COLORES["texto"])
        self.raiz.update_idletasks()

    def recargar(self):
        """Relee ofertas, lista negra y compatibilidad; actualiza chips y repinta."""
        self.ofertas = cargar_ofertas()
        self.ofertas_por_url = {
            clave_url(o.get("url", "")): o for o in self.ofertas
        }
        self.negra = purgar_lista_negra()
        self.cfg = cargar_config()
        self.compat = {
            clave_url(o.get("url", "")): puntuar(o, self.cfg) for o in self.ofertas
        }
        resumen = resumen_ofertas(self.ofertas, self.compat, self.cfg, datetime_hoy())
        meta = int(self.cfg.get("meta_postulaciones_dia", 5) or 0)
        postuladas = postulaciones_hoy()
        texto_meta = (
            f"  \u2022  Hoy {postuladas}/{meta} postuladas"
            if meta
            else f"  \u2022  Hoy {postuladas} postuladas"
        )
        self.badges.config(
            text=f"{len(self.ofertas)} activas   \u2022   {resumen['nuevas']} nuevas hoy{texto_meta}"
        )
        self._actualizar_chips()
        self._refrescar_opciones_filtros()
        self._actualizar_resumen_filtros()
        self.pintar()

    def pintar(self):
        """Vuelca la lista filtrada y ordenada, conservando seleccion y scroll."""
        if self._pintar_id is not None:
            self.raiz.after_cancel(self._pintar_id)
            self._pintar_id = None
        seleccion = set(self.tabla.selection())
        posicion = self.tabla.yview()[0] if self.tabla.get_children() else 0
        self.tabla.delete(*self.tabla.get_children())
        hoy = datetime_hoy()
        visibles = filtrar(self.ofertas, **self._leer_filtros(), compat=self.compat)
        visibles = ordenar(
            visibles, self.orden_criterio, self.orden_desc, self.compat
        )
        for i, o in enumerate(visibles):
            est = (o.get("estado_envio") or "").strip()
            info = self.compat.get(clave_url(o.get("url", ""))) or {}
            pct = info.get("porcentaje")
            dias = dias_de(o.get("fecha", ""), hoy)
            etiquetas = []
            if (o.get("fecha") or "") == hoy:
                etiquetas.append("nueva")
            if est == "Postulado":
                etiquetas.append("postulado")
            elif est == "Descartado":
                etiquetas.append("descartado")
            elif info.get("categoria") == CATEGORIA_COMPATIBLE:
                etiquetas.append("compat")
            elif info.get("categoria") == CATEGORIA_RELACIONADA:
                etiquetas.append("rel")
            if i % 2 == 1:
                etiquetas.append("alt")
            self.tabla.insert(
                "",
                "end",
                iid=o.get("url", f"fila{i}"),
                values=(
                    o.get("titulo", ""),
                    o.get("empresa") or "\u2014",
                    info.get("familia") or "\u2014",
                    f"{pct}%" if pct is not None else "-",
                    o.get("ubicacion", ""),
                    dias if dias is not None else "-",
                    est or "\u2014",
                ),
                tags=tuple(etiquetas),
            )
        presentes = [url for url in seleccion if self.tabla.exists(url)]
        if presentes:
            self.tabla.selection_set(presentes)
        if posicion:
            self.tabla.yview_moveto(posicion)
        if not self.ofertas:
            self.mensaje("No hay ofertas. Pulsa 'Buscar ahora' para empezar.")
        elif not visibles:
            self.mensaje(
                "Sin resultados con estos filtros. Pulsa 'Limpiar' o cambia la categoria."
            )
        else:
            self.mensaje(
                "Listo. Ctrl/Shift+clic = elegir varios  \u2022  Ctrl+A = todo"
            )
        self._actualizar_contadores()

    def urls_seleccionadas(self):
        """Devuelve las URLs (ids de fila) seleccionadas en la tabla."""
        return list(self.tabla.selection())

    def _actualizar_contadores(self):
        """Actualiza el resumen del pie y el detalle de la seleccion."""
        total = len(self.ofertas)
        visibles = len(self.tabla.get_children())
        n = len(self.urls_seleccionadas())
        texto = f"Mostrando {visibles} de {total}" if total else "0 ofertas"
        if n:
            texto += f"   \u2022   {n} seleccionadas"
        self.lbl_cuentas.config(text=texto)
        self._actualizar_detalle_seleccion()

    def _actualizar_detalle_seleccion(self):
        """Muestra fuente y antiguedad de la oferta seleccionada."""
        seleccion = self.urls_seleccionadas()
        if len(seleccion) != 1:
            self.lbl_detalle.config(text="")
            return
        oferta = self.ofertas_por_url.get(clave_url(seleccion[0]))
        if not oferta:
            self.lbl_detalle.config(text="")
            return
        dias = dias_de(oferta.get("fecha", ""), datetime_hoy())
        info = self.compat.get(clave_url(seleccion[0])) or {}
        fuente = oferta.get("fuente") or "\u2014"
        partes = [f"Fuente: {fuente}"]
        if info.get("familia"):
            partes.append(f"Enfoque: {info['familia']}")
        if dias is not None:
            partes.append(f"hace {dias} dia(s)")
        self.lbl_detalle.config(text="  \u00b7  ".join(partes))

    def al_seleccionar(self, _=None):
        """Muestra la barra contextual y habilita sus acciones."""
        n = len(self.urls_seleccionadas())
        self._set_habilitado(
            n > 0,
            self.btn_eliminar,
            self.btn_marcar,
            self.btn_copiar,
            self.btn_abrir,
        )
        if n:
            self.lbl_sel.config(text=f"{n} seleccionada(s)")
            if not self.barra_sel.winfo_manager():
                self.barra_sel.pack(
                    fill="x", padx=12, pady=(0, 6), before=self.marco_tabla
                )
        else:
            self.barra_sel.pack_forget()
        self._actualizar_contadores()

    def seleccionar_todo(self, _=None):
        """Marca todas las filas visibles (atajo Ctrl+A)."""
        hijos = self.tabla.get_children()
        if hijos:
            self.tabla.selection_set(hijos)
            self.tabla.focus(hijos[-1])
            self.tabla.see(hijos[0])
        self.al_seleccionar()

    def limpiar_seleccion(self, _=None):
        """Quita toda la seleccion de la tabla y actualiza contadores/botones."""
        self.tabla.selection_remove(self.tabla.selection())
        self.al_seleccionar()

    def abrir_oferta(self, _=None):
        """Abre en el navegador la URL de la fila elegida."""
        sel = self.urls_seleccionadas()
        if not sel:
            return
        url = sel[0]
        if not url.lower().startswith(("http://", "https://")):
            messagebox.showerror("Error", "La URL de la oferta no es valida.")
            return
        try:
            os.startfile(url)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir la oferta: {e}")

    def copiar_enlace(self):
        """Copia al portapapeles la URL o URLs seleccionadas."""
        sel = self.urls_seleccionadas()
        if not sel:
            return
        self.raiz.clipboard_clear()
        self.raiz.clipboard_append("\n".join(sel))
        self.mensaje(f"{len(sel)} enlace(s) copiado(s).", COLORES["verde"])

    def limpiar_texto(self):
        """Limpia solo el texto del buscador."""
        self.var_texto.set("")
        self._actualizar_resumen_filtros()

    def limpiar_filtros(self):
        """Restablece la categoria, los chips y los filtros avanzados."""
        self.var_texto.set("")
        self.var_categoria.set("Compatibles")
        self.var_nuevas.set(False)
        self.var_sin_postular.set(False)
        self.var_remoto.set(False)
        for variables in (self.var_fuentes, self.var_zonas, self.var_estados):
            for variable in variables.values():
                variable.set(True)
        self._al_cambiar_chip()
        self._actualizar_resumen_filtros()

    def _ocupado(self, activo):
        """Marca ocupada la app: bloquea acciones lentas y muestra el progreso."""
        self.trabajando = activo
        estado = ["disabled"] if activo else ["!disabled"]
        for boton in (self.btn_buscar, self.btn_verificar, self.btn_perfil):
            boton.state(estado)
        self.al_seleccionar()
        if activo:
            self.progreso.pack(side="right")
            self.progreso.start(12)
        else:
            self.progreso.stop()
            self.progreso.pack_forget()

    # ---------- Acciones de la toolbar ----------
    def accion_eliminar(self):
        """Borra las ofertas seleccionadas con confirmacion y las pasa a lista negra."""
        if self.trabajando:
            return
        sel = self.urls_seleccionadas()
        if not sel:
            return
        dias = dias_lista_negra()
        if not messagebox.askyesno(
            "Eliminar ofertas",
            f"¿Eliminar {len(sel)} oferta(s) seleccionada(s)?\n\n"
            f"No volveran a aparecer por {dias} dias (lista negra).",
        ):
            return
        try:
            n = eliminar_ofertas(sel)
            refrescar_reporte(0)
            self.recargar()
            self.mensaje(
                f"{n} oferta(s) eliminada(s). Lista negra: {dias} dias.",
                COLORES["verde"],
            )
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo eliminar: {e}")
            self.mensaje("Error al eliminar.", COLORES["peligro"])

    def accion_depurar(self):
        """Retira del CSV las ofertas que quedaron bajo el umbral de compatibilidad."""
        if self.trabajando:
            return
        urls = [
            o.get("url", "")
            for o in self.ofertas
            if (self.compat.get(clave_url(o.get("url", ""))) or {}).get("categoria")
            == CATEGORIA_DESCARTADA
        ]
        if not urls:
            self.mensaje("No hay ofertas incompatibles que depurar.", COLORES["verde"])
            return
        dias = dias_lista_negra()
        if not messagebox.askyesno(
            "Depurar incompatibles",
            f"¿Retirar {len(urls)} oferta(s) que no son compatibles con tu perfil?\n\n"
            f"No volveran a aparecer por {dias} dias (lista negra).",
        ):
            return
        try:
            n = eliminar_ofertas(urls)
            refrescar_reporte(0)
            self.recargar()
            self.mensaje(f"{n} oferta(s) incompatibles depuradas.", COLORES["verde"])
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo depurar: {e}")
            self.mensaje("Error al depurar.", COLORES["peligro"])

    def accion_marcar(self):
        """Aplica a la seleccion el estado del combo (Postulado, Descartado o vacio)."""
        valor = self.combo_estado_accion.get()
        estado = "" if valor == "(vacio)" else valor
        self.accion_marcar_valor(estado, etiqueta=estado or "Sin estado")

    def accion_marcar_valor(self, estado, etiqueta=None):
        """Aplica un estado concreto a la seleccion actual."""
        if self.trabajando:
            return
        sel = self.urls_seleccionadas()
        if not sel:
            return
        etiqueta = etiqueta or (estado or "Sin estado")
        try:
            n = aplicar_estado(sel, estado)
            self.recargar()
            self.mensaje(
                f"{n} oferta(s) marcada(s) como '{etiqueta}'.", COLORES["verde"]
            )
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo marcar: {e}")

    # ---------- Ventanas secundarias ----------
    def accion_negra(self):
        """Abre la ventana de lista negra, con sus ofertas y el boton para restaurarlas."""
        dias = dias_lista_negra()
        top = tk.Toplevel(self.raiz)
        top.title(f"Lista negra ({dias} dias)")
        top.geometry("760x420")
        top.configure(bg=COLORES["fondo"])
        tk.Label(
            top,
            text="Ofertas eliminadas: el sistema no las trae de nuevo hasta la fecha indicada.",
            bg=COLORES["fondo"], fg=COLORES["texto"], font=("Segoe UI", 10), pady=8,
        ).pack(fill="x", padx=12)
        marco = tk.Frame(top, padx=12)
        marco.pack(fill="both", expand=True)
        t = ttk.Treeview(marco, columns=("titulo", "fuente", "hasta", "restan"), show="headings",
                         selectmode="extended")
        t.heading("titulo", text="Puesto")
        t.heading("fuente", text="Fuente")
        t.heading("hasta", text="Hasta")
        t.heading("restan", text="Dias restantes")
        t.column("titulo", width=380, anchor="w")
        t.column("fuente", width=110, anchor="center")
        t.column("hasta", width=110, anchor="center")
        t.column("restan", width=100, anchor="center")
        scroll = ttk.Scrollbar(marco, orient="vertical", command=t.yview)
        t.configure(yscrollcommand=scroll.set)
        t.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        hoy = datetime_hoy()

        def pintar_negra():
            """Repuebla la tabla negra: titulo, fuente, fecha limite y dias restantes."""
            t.delete(*t.get_children())
            negra = cargar_lista_negra()
            for url, info in negra.items():
                hasta = info.get("hasta", "")
                try:
                    from datetime import datetime

                    restan = (datetime.strptime(hasta, "%Y-%m-%d") - datetime.strptime(hoy, "%Y-%m-%d")).days
                except Exception:
                    restan = "-"
                t.insert("", "end", iid=url,
                         values=(info.get("titulo") or "(sin titulo, ver URL al restaurar)",
                                 info.get("fuente", ""), hasta, restan))

        pintar_negra()

        def restaurar():
            """Devuelve a la busqueda las filas elegidas de la lista negra, con confirmacion."""
            sel = list(t.selection())
            if not sel:
                return
            if not messagebox.askyesno("Restaurar", f"¿Devolver {len(sel)} oferta(s) a la busqueda?", parent=top):
                return
            n = restaurar_negra(sel)
            pintar_negra()
            self.recargar()
            self.mensaje(f"{n} oferta(s) fuera de la lista negra.", COLORES["verde"])

        barra = tk.Frame(top, bg=COLORES["fondo"], pady=10, padx=12)
        barra.pack(fill="x")
        ttk.Button(barra, text="Restaurar seleccionadas", style="Verde.TButton",
                   command=restaurar).pack(side="left")
        ttk.Button(barra, text="Cerrar", command=top.destroy).pack(side="right")

    def accion_perfil(self):
        """Abre el editor de perfil (busqueda y compatibilidad) y guarda en config.json."""
        cfg = cargar_config()
        top = tk.Toplevel(self.raiz)
        top.title("Editar perfil de busqueda")
        top.geometry("700x760")
        top.configure(bg=COLORES["fondo"])
        tk.Label(
            top,
            text="Define tus zonas y palabras. La compatibilidad se recalcula al guardar.",
            bg=COLORES["fondo"], fg=COLORES["texto"], font=("Segoe UI", 10), pady=8,
        ).pack(fill="x", padx=12)
        cuaderno = ttk.Notebook(top)
        cuaderno.pack(fill="both", expand=True, padx=12)
        cajas = {}

        def pestana(titulo, campos):
            """Crea una pestana con una caja de texto por campo y la agrega al cuaderno."""
            marco = tk.Frame(cuaderno, bg=COLORES["fondo"], padx=10, pady=6)
            cuaderno.add(marco, text=titulo)
            for etiqueta, clave, alto in campos:
                tk.Label(marco, text=etiqueta, bg=COLORES["fondo"], anchor="w",
                         font=("Segoe UI", 9, "bold")).pack(fill="x", pady=(6, 1))
                caja = tk.Text(marco, height=alto, wrap="none", font=("Consolas", 9))
                caja.insert("1.0", "\n".join(cfg.get(clave) or []))
                caja.pack(fill="x")
                cajas[clave] = caja
            return marco

        m_busqueda = pestana("Busqueda", (
            ("Zonas (una por linea)", "zonas", 6),
            ("Terminos de busqueda (una por linea)", "palabras_clave_busqueda", 6),
        ))
        var_remoto = tk.BooleanVar(value=bool(cfg.get("incluir_remoto", True)))
        ttk.Checkbutton(m_busqueda, text="Incluir ofertas remotas sin importar la zona",
                        variable=var_remoto).pack(anchor="w", pady=(10, 0))

        m_comp = pestana("Compatibilidad", (
            ("Palabras fuertes x3 (puestos de TI)", "palabras_fuertes", 4),
            ("Palabras medias x2 (afines a TI)", "palabras_clave", 4),
            ("Contexto x1 (tecnologias y herramientas)", "palabras_contexto", 3),
            ("Castigos -1 (bajan el puntaje: ingles avanzado...)", "palabras_castigo", 2),
            ("Palabras que descartan (ventas, aire acondicionado...)", "palabras_excluidas", 4),
        ))
        # El motor trata palabras_excluidas e incompatibles igual (anulan la
        # oferta), asi que en el editor se muestran y guardan juntas.
        cajas["palabras_excluidas"].delete("1.0", "end")
        cajas["palabras_excluidas"].insert(
            "1.0",
            "\n".join(list(cfg.get("palabras_excluidas") or []) + list(cfg.get("incompatibles") or [])),
        )

        m_enfoques = pestana("Enfoques", (
            ("Anclas de puesto (sin una, la oferta no entra)", "anclas_puesto", 12),
        ))
        tk.Label(
            m_enfoques,
            text=(
                "Son las frases que debe contener el TITULO para que la oferta sea\n"
                "del perfil: soporte, redes, infraestructura, help desk, NOC...\n"
                "La app ademas etiqueta cada oferta como Soporte, Redes,\n"
                "Infraestructura, Campo, Aplicaciones o Seguridad."
            ),
            bg=COLORES["fondo"], fg="#5D6D7E", anchor="w", justify="left",
            font=("Segoe UI", 9),
        ).pack(fill="x", pady=(8, 0))

        marco_umbral = tk.Frame(m_comp, bg=COLORES["fondo"])
        marco_umbral.pack(fill="x", pady=(10, 0))
        tk.Label(marco_umbral, text="Compatible desde (%):", bg=COLORES["fondo"]).pack(side="left")
        var_minima = tk.StringVar(value=str(cfg.get("compatibilidad_minima", 70)))
        ttk.Entry(marco_umbral, textvariable=var_minima, width=5).pack(side="left", padx=(4, 16))
        tk.Label(marco_umbral, text="Relacionada desde (%):", bg=COLORES["fondo"]).pack(side="left")
        var_relacionada = tk.StringVar(value=str(cfg.get("compatibilidad_relacionada", 40)))
        ttk.Entry(marco_umbral, textvariable=var_relacionada, width=5).pack(side="left", padx=(4, 0))

        def guardar():
            """Valida, escribe config.json con lo editado y cierra la ventana."""
            datos = cargar_config()
            for clave, caja in cajas.items():
                datos[clave] = [l.strip() for l in caja.get("1.0", "end").splitlines() if l.strip()]
            try:
                minima = int(var_minima.get().strip())
                relacionada = int(var_relacionada.get().strip())
            except ValueError:
                messagebox.showwarning(
                    "Perfil", "Los umbrales deben ser numeros entre 0 y 100.", parent=top)
                return
            if not (0 <= relacionada <= minima <= 100):
                messagebox.showwarning(
                    "Perfil",
                    "Debe cumplirse: 0 <= Relacionada <= Compatible <= 100.",
                    parent=top,
                )
                return
            datos["compatibilidad_minima"] = minima
            datos["compatibilidad_relacionada"] = relacionada
            datos["incompatibles"] = []
            datos["incluir_remoto"] = bool(var_remoto.get())
            if not datos["zonas"] and not datos["incluir_remoto"]:
                messagebox.showwarning(
                    "Perfil",
                    "Deja al menos una zona o activa 'Incluir ofertas remotas'.",
                    parent=top,
                )
                return
            try:
                guardar_config(datos)
            except Exception as e:
                messagebox.showerror(
                    "Error", f"No se pudo guardar el perfil: {e}", parent=top
                )
                return
            top.destroy()
            self.recargar()
            self.mensaje("Perfil guardado: la proxima busqueda y los puntajes ya lo usan.",
                         COLORES["verde"])

        barra = tk.Frame(top, bg=COLORES["fondo"], pady=10, padx=14)
        barra.pack(fill="x")
        ttk.Button(barra, text="Guardar", style="Verde.TButton", command=guardar).pack(side="left")
        ttk.Button(barra, text="Cancelar", command=top.destroy).pack(side="left", padx=(8, 0))

    # ---------- Preferencias y ayuda ----------
    def accion_preferencias(self):
        """Abre las preferencias diarias: auto-busqueda, avisos y carpeta de datos."""
        cfg = cargar_config()
        top = tk.Toplevel(self.raiz)
        top.title("Preferencias")
        top.geometry("470x470")
        top.configure(bg=COLORES["fondo"])
        marco = tk.Frame(top, bg=COLORES["fondo"], padx=16, pady=14)
        marco.pack(fill="both", expand=True)
        tk.Label(
            marco,
            text="Busqueda automatica",
            bg=COLORES["fondo"],
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w")
        fila = tk.Frame(marco, bg=COLORES["fondo"])
        fila.pack(anchor="w", pady=(6, 0))
        var_minutos = tk.StringVar(value=str(cfg.get("app_auto_minutos", 0)))
        ttk.Spinbox(
            fila, from_=0, to=180, textvariable=var_minutos, width=6
        ).pack(side="left")
        tk.Label(
            fila, text="minutos (0 = desactivada)", bg=COLORES["fondo"]
        ).pack(side="left", padx=(6, 0))
        tk.Label(
            marco,
            text="Meta diaria de postulaciones",
            bg=COLORES["fondo"],
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(14, 0))
        fila_meta = tk.Frame(marco, bg=COLORES["fondo"])
        fila_meta.pack(anchor="w", pady=(6, 0))
        var_meta = tk.StringVar(value=str(cfg.get("meta_postulaciones_dia", 5)))
        ttk.Spinbox(
            fila_meta, from_=0, to=50, textvariable=var_meta, width=6
        ).pack(side="left")
        tk.Label(
            fila_meta, text="postulaciones (0 = sin meta)", bg=COLORES["fondo"]
        ).pack(side="left", padx=(6, 0))
        tk.Label(
            marco,
            text="Consultas por corrida",
            bg=COLORES["fondo"],
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(14, 0))
        fila_consultas = tk.Frame(marco, bg=COLORES["fondo"])
        fila_consultas.pack(anchor="w", pady=(6, 0))
        var_consultas = tk.StringVar(value=str(cfg.get("consultas_por_corrida", 16)))
        ttk.Spinbox(
            fila_consultas, from_=0, to=40, textvariable=var_consultas, width=6
        ).pack(side="left")
        tk.Label(
            fila_consultas,
            text="0 = todas (mas opciones, mas tiempo)",
            bg=COLORES["fondo"],
        ).pack(side="left", padx=(6, 0))
        var_toast = tk.BooleanVar(value=bool(cfg.get("notificar_toast", True)))
        ttk.Checkbutton(
            marco,
            text="Aviso de Windows al terminar",
            variable=var_toast,
        ).pack(anchor="w", pady=(12, 0))
        var_reporte = tk.BooleanVar(value=bool(cfg.get("abrir_reporte", False)))
        ttk.Checkbutton(
            marco,
            text="Abrir el reporte cuando haya ofertas nuevas",
            variable=var_reporte,
        ).pack(anchor="w")
        ttk.Button(
            marco,
            text="Abrir carpeta de datos",
            style="Secundario.TButton",
            command=self._abrir_datos,
        ).pack(anchor="w", pady=(14, 0))

        def guardar():
            """Valida y guarda las preferencias, reprogramando la auto-busqueda."""
            try:
                minutos = max(0, min(180, int(var_minutos.get())))
            except ValueError:
                messagebox.showwarning(
                    "Preferencias", "Los minutos deben ser un numero entre 0 y 180.",
                    parent=top,
                )
                return
            try:
                meta = max(0, min(50, int(var_meta.get())))
            except ValueError:
                messagebox.showwarning(
                    "Preferencias", "La meta diaria debe ser un numero entre 0 y 50.",
                    parent=top,
                )
                return
            try:
                limite_consultas = max(0, min(40, int(var_consultas.get())))
            except ValueError:
                messagebox.showwarning(
                    "Preferencias",
                    "Las consultas por corrida deben ser un numero entre 0 y 40.",
                    parent=top,
                )
                return
            try:
                guardar_config_parcial(
                    {
                        "app_auto_minutos": minutos,
                        "meta_postulaciones_dia": meta,
                        "consultas_por_corrida": limite_consultas,
                        "notificar_toast": bool(var_toast.get()),
                        "abrir_reporte": bool(var_reporte.get()),
                    }
                )
            except Exception as e:
                messagebox.showerror(
                    "Preferencias", f"No se pudieron guardar: {e}", parent=top
                )
                return
            self.var_auto.set(minutos > 0)
            if minutos > 0:
                self._programar_auto(minutos)
            else:
                self._cancelar_auto()
            self._actualizar_lbl_auto()
            top.destroy()
            self.mensaje("Preferencias guardadas.", COLORES["verde"])

        barra = tk.Frame(top, bg=COLORES["fondo"], pady=10, padx=14)
        barra.pack(fill="x")
        ttk.Button(
            barra, text="Guardar", style="Verde.TButton", command=guardar
        ).pack(side="left")
        ttk.Button(barra, text="Cancelar", command=top.destroy).pack(
            side="left", padx=(8, 0)
        )

    def _abrir_datos(self):
        """Abre la carpeta de datos en el explorador de Windows."""
        try:
            os.startfile(DATA)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir la carpeta: {e}")

    def accion_atajos(self):
        """Muestra los atajos de teclado disponibles."""
        messagebox.showinfo(
            "Atajos de teclado",
            "F5\tBuscar ahora\n"
            "Ctrl+F\tEnfocar el buscador\n"
            "Ctrl+A\tSeleccionar todas las filas visibles\n"
            "Enter\tAbrir la oferta seleccionada\n"
            "Delete\tEliminar la seleccion\n"
            "Esc\tLimpiar seleccion, texto o filtros\n\n"
            "Clic derecho\tMenu contextual de la oferta",
        )

    # ---------- Ventana de estadisticas ----------
    def accion_estadisticas(self):
        """Abre una ventana con el resumen: estados, compatibilidad, dias y fuentes."""
        datos = calcular_estadisticas(self.ofertas, compat=self.compat)
        top = tk.Toplevel(self.raiz)
        top.title("Estadisticas")
        top.geometry("420x700")
        top.configure(bg=COLORES["fondo"])
        marco = tk.Frame(top, bg=COLORES["fondo"], padx=16, pady=14)
        marco.pack(fill="both", expand=True)

        def encabezado(texto):
            """Escribe un titulo de seccion dentro de la ventana."""
            tk.Label(marco, text=texto, bg=COLORES["fondo"], anchor="w",
                     font=("Segoe UI", 11, "bold")).pack(fill="x", pady=(12, 2))

        def linea(izq, der):
            """Escribe una fila 'concepto ... valor' dentro de la ventana."""
            fila = tk.Frame(marco, bg=COLORES["fondo"])
            fila.pack(fill="x")
            tk.Label(fila, text=izq, bg=COLORES["fondo"], anchor="w").pack(side="left")
            tk.Label(fila, text=str(der), bg=COLORES["fondo"], anchor="e",
                     font=("Segoe UI", 10, "bold")).pack(side="right")

        tk.Label(marco, text=f"Total: {datos['total']} ofertas activas",
                 bg=COLORES["fondo"], font=("Segoe UI", 12, "bold")).pack(anchor="w")
        encabezado("Por estado")
        linea("Postuladas", datos["estados"]["postuladas"])
        linea("Descartadas", datos["estados"]["descartadas"])
        linea("Sin estado", datos["estados"]["sin_estado"])
        encabezado("Por compatibilidad")
        linea("Compatibles", datos["categorias"]["compatibles"])
        linea("Relacionadas", datos["categorias"]["relacionadas"])
        linea("Descartadas", datos["categorias"]["descartadas"])
        if datos.get("familias"):
            encabezado("Por enfoque")
            for familia, conteo in datos["familias"]:
                linea(familia, conteo)
        encabezado("Nuevas por dia (ultimos 7)")
        for fecha, conteo in datos["por_dia"]:
            linea(fecha, conteo)
        encabezado("Por fuente")
        for fuente, conteo in datos["fuentes"]:
            linea(fuente, conteo)
        ttk.Button(marco, text="Cerrar", command=top.destroy).pack(pady=(16, 0))

    # ---------- Busqueda automatica ----------
    def alternar_auto(self):
        """Activa o desactiva la busqueda periodica y guarda la preferencia."""
        try:
            if self.var_auto.get():
                minutos = int(cargar_config().get("app_auto_minutos", 0) or 0)
                if minutos <= 0:
                    minutos = 10
                    guardar_config_parcial({"app_auto_minutos": minutos})
                self._programar_auto(minutos)
                self.mensaje(f"Busqueda automatica cada {minutos} min.")
            else:
                self._cancelar_auto()
                guardar_config_parcial({"app_auto_minutos": 0})
                self.mensaje("Busqueda automatica desactivada.")
        except Exception as e:
            self.var_auto.set(False)
            self._cancelar_auto()
            messagebox.showerror(
                "Busqueda automatica", f"No se pudo guardar la preferencia: {e}"
            )

    def _programar_auto(self, minutos):
        """Agenda _auto_tick a 'minutos' y muestra la proxima ejecucion."""
        self._cancelar_auto()
        self._auto_id = self.raiz.after(int(minutos) * 60000, self._auto_tick)
        self._proxima_auto = datetime.now() + timedelta(minutes=int(minutos))
        self._actualizar_lbl_auto()

    def _cancelar_auto(self):
        """Cancela el timer de busqueda automatica si esta pendiente."""
        if getattr(self, "_auto_id", None) is not None:
            self.raiz.after_cancel(self._auto_id)
            self._auto_id = None
        self._proxima_auto = None
        if hasattr(self, "lbl_auto"):
            self._actualizar_lbl_auto()

    def _auto_tick(self):
        """Corre una busqueda si no hay trabajo en curso y agenda la siguiente."""
        self._auto_id = None
        self._proxima_auto = None
        minutos = int(cargar_config().get("app_auto_minutos", 0) or 0)
        if minutos <= 0 or not self.var_auto.get():
            self._actualizar_lbl_auto()
            return
        if not self.trabajando:
            self.accion_buscar()
        self._programar_auto(minutos)

    # ---------- Cola de hilos (trabajo en segundo plano) ----------
    def _correr_hilo(self, funcion, al_terminar=None):
        """Ejecuta 'funcion' en un hilo daemon y encola el resultado para la UI."""
        if self.trabajando:
            return
        self._ocupado(True)

        def trabajador():
            """Corre la funcion y encola ('fin', resultado, error, callback) al terminar."""
            resultado = None
            error = None
            try:
                resultado = funcion()
            except Exception as e:
                error = e
            self.cola.put(("fin", resultado, error, al_terminar))

        threading.Thread(target=trabajador, daemon=True).start()
        # Tk solo admite llamadas desde su hilo principal: el hilo encola y after() lo drena.
        self.raiz.after(120, self._procesar_cola)

    def _procesar_cola(self):
        """Drena los eventos 'linea'/'fin' en el hilo principal y se reprograma si sigue el trabajo."""
        try:
            while True:
                evento = self.cola.get_nowait()
                if evento[0] == "linea":
                    self.mensaje(evento[1])
                elif evento[0] == "fin":
                    _, resultado, error, al_terminar = evento
                    self._ocupado(False)
                    if error is not None:
                        messagebox.showerror("Error", f"Fallo la operacion: {error}")
                        self.mensaje(f"Error: {error}", COLORES["peligro"])
                    elif al_terminar:
                        al_terminar(resultado)
        except queue.Empty:
            pass
        if self.trabajando:
            self.raiz.after(150, self._procesar_cola)

    # ---------- Buscar y verificar en subprocess ----------
    def accion_buscar(self):
        """Lanza main.py en un subprocess, muestra su salida y refresca al terminar."""
        if self.trabajando:
            return
        self._ocupado(True)

        def trabajador():
            """Ejecuta main.py, encola cada linea de salida y luego el evento 'fin'."""
            error = None
            codigo = None
            try:
                ruta_main = os.path.join(BASE, "main.py")
                proc = subprocess.Popen(
                    [python_consola(), ruta_main],
                    cwd=BASE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    encoding="utf-8", errors="replace",
                )
                for linea in proc.stdout:
                    linea = linea.strip()
                    if linea:
                        self.cola.put(("linea", linea[:130]))
                proc.wait()
                codigo = proc.returncode
            except Exception as e:
                error = e
            self.cola.put(("fin", codigo, error, self._fin_buscar))

        threading.Thread(target=trabajador, daemon=True).start()
        self.raiz.after(120, self._procesar_cola)

    def _fin_buscar(self, codigo):
        """Recarga tras la busqueda y avisa si termino con errores (codigo distinto de 0)."""
        self.recargar()
        if codigo == 0:
            self.mensaje("Busqueda finalizada. Tabla actualizada.", COLORES["verde"])
        else:
            self.mensaje("La busqueda termino con errores (revisa la consola).", COLORES["peligro"])

    def accion_verificar(self):
        """Comprueba disponibilidad en un hilo y retira las ofertas que ya no existen."""
        def verificar_directo():
            """Corre verificar_ofertas con la config actual y devuelve (retiradas, revisadas)."""
            from verificar import verificar_ofertas

            retiradas, revisadas = verificar_ofertas(cargar_config())
            return retiradas, revisadas

        def al_terminar(resultado):
            """Recarga y avisa cuantas ofertas se retiraron o que todas siguen activas."""
            retiradas, revisadas = resultado
            self.recargar()
            if retiradas:
                self.mensaje(
                    f"{len(retiradas)} oferta(s) ya no disponibles retiradas "
                    f"(revisadas {revisadas}).",
                    COLORES["verde"],
                )
            else:
                self.mensaje(
                    f"Verificadas {revisadas}: todas siguen disponibles.",
                    COLORES["verde"],
                )

        self._correr_hilo(verificar_directo, al_terminar)


def datetime_hoy():
    """Devuelve la fecha de hoy en formato YYYY-MM-DD."""
    from datetime import datetime

    return datetime.now().strftime("%Y-%m-%d")


def _activar_dpi():
    """Activa el escalado nitido de Windows en pantallas de alta densidad."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def ejecutar():
    """Crea la ventana raiz, monta la Aplicacion y arranca el bucle mainloop de Tk."""
    _activar_dpi()
    raiz = tk.Tk()
    Aplicacion(raiz)
    raiz.mainloop()


if __name__ == "__main__":
    try:
        ejecutar()
    except Exception:
        import traceback

        try:
            registrar("ERROR app " + traceback.format_exc().replace("\n", " | "))
            messagebox.showerror("Error inesperado", traceback.format_exc()[-600:])
        except Exception:
            pass
        raise
