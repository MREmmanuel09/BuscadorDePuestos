# Mapa del código

Guía para entender qué hace cada archivo y en qué orden se ejecuta todo.
Léela con el README al lado: aquí está el **cómo**, allá el **qué**.

## Vista general

```
                        ┌──────────────────────────────┐
                        │  config.json  (tu perfil)    │
                        │  zonas, palabras, dias...    │
                        │  umbrales de compatibilidad  │
                        └──────────────┬───────────────┘
                                       │ se lee al inicio
                                       ▼
 8:00 am ──► buscar.cmd ──► main.py :: main()
                                   │
               ┌───────────────────┼────────────────────┐
               ▼                   ▼                    ▼
        1. purgar_ofertas    2. recolectar        3. pasa_filtros
           (retira >15 dias)  (en paralelo,       (ancla TI + familia
                              consultas rotadas)   + zona/remoto)
                                  │
                                  ▼
                    ┌────────────────────────┐
                    │ fuentes/*.py (4 sitios)│
                    │ computrabajo           │
                    │ trabajo_org (8 pags)   │
                    │ findjob24h (buscador)  │
                    │ linkedin               │
                    └────────────────────────┘
                                  │
               4. deduplicar (URL / titulo+empresa)
               5. escribir_csv (nuevas) ──► data/ofertas.csv
               6. verificar.py (ofertas cerradas → lista negra)
               7. escribir_reporte ──► data/reporte.html (por % y categoria)
               8. toast / correo / historial.log

usuario ──► Abrir Ofertas.cmd ──► app.pyw (ventana Tkinter)
                                        │
                                        ├─ "Buscar ahora" ──────► subprocess main.py
                                        ├─ "Verificar" ─────────► verificar.py en hilo
                                        ├─ chips/filtros ───────► filtrar() + ordenar()
                                        ├─ barra contextual ────► marcar / eliminar / copiar / abrir
                                        ├─ menú ⋮ ──────────────► lista negra, depurar, estadísticas, preferencias
                                        ├─ "Perfil" ────────────► escribe config.json
                                        └─ "Auto" ──────────────► raiz.after → busca sola (app_auto_minutos)

 escrituras ──► almacen.py (temporal + os.replace + backups) + bloqueo.py
 secreto SMTP ──► secretos.py (DPAPI; nunca queda en texto plano)

 tests/ ──► python -m unittest discover -s tests      .github/workflows/ci.yml ──► ruff + pruebas + cobertura
```

## Archivo por archivo

| Archivo | Qué hace | Funciones clave |
|---|---|---|
| `main.py` | El cerebro: config, datos, filtros, meta diaria y la corrida completa | `main`, `normalizar_config`, `pasa_filtros`, `recolectar`, `deduplicar`, `postulaciones_hoy` |
| `compatibilidad.py` | Puntúa cada oferta (0-100 %) contra el perfil y la clasifica | `puntuar`, `categoria_de` |
| `puestos.py` | Exige un ancla de TI en el título y etiqueta el enfoque (Soporte, Redes, Infraestructura, Campo, Aplicaciones, Seguridad) | `clasificar`, `familia_de`, `anclas` |
| `consultas.py` | Catálogo de consultas: núcleo fijo + rotación diaria por fuente | `consultas` |
| `app.pyw` | Ventana de escritorio; llama a las mismas funciones de `main` | `Aplicacion._construir`, `_leer_filtros`, `pintar`, `accion_*`, `_correr_hilo` |
| `almacen.py` | Escrituras atómicas, lectura segura, backups y rotación de logs | `escribir_json_atomico`, `escribir_csv_atomico`, `copia_seguridad`, `rotar_log` |
| `bloqueo.py` | Evita que la app y la tarea programada escriban a la vez | `proceso` |
| `secretos.py` | Cifra la clave SMTP con DPAPI de Windows | `cifrar`, `descifrar` |
| `verificar.py` | Detecta ofertas cerradas y las retira (solo con evidencia); no repite las ya revisadas hoy | `obtener`, `estado_oferta`, `verificar_ofertas` |
| `eliminar.py` | Borrado por terminal (menú o `--dias N`) | `purgar`, `menu`, `main` |
| `notificar.py` | Toast de Windows y correo SMTP (opcional) | `toast`, `enviar_correo` |
| `fuentes/comun.py` | Utilidades compartidas de descarga (reintentos y caché por corrida) | `descargar`, `fetch`, `pausar`, `sin_acentos`, `limpiar_cache` |
| `fuentes/computrabajo.py` | Busca en cr.computrabajo.com con las consultas de la corrida | `buscar` |
| `fuentes/trabajo_org.py` | Recorre zonas y hasta 8 páginas, y guarda ubicación/empresa reales | `buscar` |
| `fuentes/findjob24h.py` | Usa el buscador del sitio y lee título, empresa y ubicación del listado | `buscar` |
| `fuentes/linkedin.py` | Endpoint público de invitados de LinkedIn | `buscar` |
| `tests/` | Pruebas unitarias (unittest, sin instalar nada) | `test_main`, `test_verificar`, `test_app_helpers`, `test_compatibilidad`, `test_consultas`, `test_almacen`, `test_bloqueo`, `test_secretos` |
| `.github/workflows/ci.yml` | CI: ruff, compilación, pruebas y cobertura en Windows (3.10/3.12/3.14) | — |
| `pyproject.toml` | Metadatos y configuración de ruff/cobertura | — |
| `docs/` | Capturas de la aplicación que ves en el README | — |
| `config.json` | Tu perfil: zonas, palabras, dias (no se sube a GitHub) | — |
| `config.example.json` | Plantilla que se copia al primer arranque | — |

Cada fuente expone **la misma interfaz**: `buscar(cfg) → [ofertas]` con claves
`titulo, ubicacion, empresa, url, fuente`. Por eso `recolectar` puede llamar a
las 4 sin importar de cuál venga cada oferta.

## El flujo de `main()` (main.py, línea por línea)

0. **`bloqueo.proceso`** — toma el bloqueo de `data/.buscador.lock` para que la app
   y la tarea programada no escriban a la vez.
1. **`asegurar_config` / `cargar_config`** — lee tu perfil, lo normaliza y migra la
   clave SMTP a DPAPI si estaba en texto plano.
2. **`purgar_ofertas(dias)`** — saca del CSV lo viejo (los borrados pasan a lista negra);
   antes de escribir guarda una copia en `data/backups/`.
3. **`recolectar(cfg)`** — consulta las 4 fuentes en paralelo (`ThreadPoolExecutor`); si
   una falla, las demás siguen. Cada fuente usa `consultas(cfg, fuente)`: las 8
   primeras consultas siempre corren y el resto rota según el día y la fuente.
   Trabajo.org recorre hasta 8 páginas por zona; FindJob24h usa su buscador.
4. **`pasa_filtros(oferta, zonas, cfg, resultado)`** — el motor exige un ancla de TI
   en el título, descarta otros rubros/roles, puntúa y etiqueta la familia. Luego
   revisa zona/remoto (Trabajo.org ya no exime del filtro). Las Descartadas no entran.
5. **`deduplicar(ofertas)`** — quita repetidas por URL o por (título, empresa).
6. **`escribir_csv(nuevas)`** — agrega las nuevas al CSV (las ya vistas o en lista negra, no).
7. **`verificar_ofertas(cfg)`** (si `verificar_en_busqueda`) — mira ofertas viejas (salta las
   revisadas hoy según `verificado.json`): si están cerradas, las retira.
8. **`escribir_reporte`** — regenera `reporte.html` con la columna Compat y las secciones
   *Compatibles* / *Relacionadas* ordenadas por porcentaje.
9. **`guardar_vistas` + `registrar`** — marca vistas, escribe `historial.log` con el
   embudo (compatibles/relacionadas/descartadas), el reparto por enfoque, los motivos
   de descarte y la duración de la corrida.
10. **Avisos** — `toast` de Windows y correo si `notificar_toast` / `correo.activo`.

## La clase `Aplicacion` (app.pyw)

- **`_construir`** — encabezado con resumen (incluye la meta diaria), botones
  *Perfil* / menú `⋮`, acciones principales, buscador con chips, panel de filtros,
  barra contextual de selección, tabla `Treeview` (con columna **Enfoque**) y pie
  con mensaje, fuente seleccionada, auto-búsqueda y conteos.
- **`_crear_chip` / `_al_cambiar_chip` / `_actualizar_chips`** — chips de categoría
  y atajos; muestran conteos y combinan sus filtros con AND.
- **`_refrescar_opciones_filtros`** — reconstruye los checkbuttons de fuente, zona,
  estado y enfoque con sus conteos, conservando lo seleccionado.
- **`_leer_filtros`** — traduce chips y checkbuttons a los argumentos de `filtrar()`.
- **`filtrar` / `ordenar` / `resumen_ofertas`** — funciones puras y testeables:
  filtros combinados (incluido `familias`), orden por columna y conteos.
- **`pintar`** — repuebla la tabla conservando selección y scroll; muestra empresa,
  enfoque, compatibilidad, ubicación, días y estado.
- **`al_seleccionar`** — muestra/oculta la barra contextual y habilita sus acciones.
- **`_menu_contextual`** — clic derecho: abrir, copiar, marcar o eliminar.
- **`accion_*`** — una por acción; las lentas (buscar/verificar) corren en hilo vía
  **`_correr_hilo`**: Tk solo se toca desde el hilo principal, por eso los resultados
  vuelven por la **`cola`** y se procesan con `raiz.after` en `_procesar_cola`.
- **`accion_depurar`** — pide confirmación y retira del CSV las ofertas Descartadas
  (bajo el umbral); vuelven a la lista negra.
- **`accion_perfil`** — `ttk.Notebook` con tres pestañas (*Búsqueda*,
  *Compatibilidad* y *Enfoques*): zonas, términos, grupos de palabras por peso,
  umbrales, anclas de puesto y `meta_puntos`; guarda y `recargar()`.
- **`accion_estadisticas`** — ventana con `calcular_estadisticas(compat=...)`: total,
  reparto por estado, reparto por categoría, reparto por enfoque, ofertas nuevas de
  los últimos 7 días y conteo por fuente.
- **`accion_preferencias`** — intervalo de auto-búsqueda, meta diaria de
  postulaciones, consultas por corrida, avisos, abrir reporte y acceso a la carpeta
  de datos; guarda con `guardar_config_parcial`.
- **Búsqueda automática** — la casilla *Auto* del pie (`alternar_auto`) agenda
  `_auto_tick` con `raiz.after(app_auto_minutos × 60000)` y muestra la próxima hora;
  cada tic dispara `accion_buscar` si no hay trabajo en curso y vuelve a agendarse.
- **`cerrar` / `_guardar_estado_ui`** — guarda geometría, orden y panel de filtros en
  `data/ui_state.json`; los filtros se reinician al abrir para no ocultar ofertas.
- **`_activar_dpi`** — activa el escalado nítido de Windows antes de crear `Tk`.

## El puntaje de compatibilidad (compatibilidad.py + puestos.py)

- **Ancla obligatoria**: el TÍTULO debe contener una frase de TI (`soporte`,
  `redes`, `network`, `help desk`, `NOC`, `infraestructura`, `data center`,
  `soporte de aplicaciones`, `ciberseguridad`, `IT`/`TI`...). Sin ancla, la oferta
  es Descartada aunque diga "software" o "sistemas".
- **Naturaleza del puesto**: `palabras_excluidas` e `incompatibles` anulan la oferta
  (desarrollo, ventas, salud, alimentos, electromecánica, atención al cliente...).
  Los sectores que pueden acompañar a un puesto de TI (`... y obra civil`) se
  toleran como *enfoque mixto* y bajan el puntaje; si el sector es el objeto
  (`Soporte para Aire Acondicionado`) se descarta.
- **Grupos y pesos**: `palabras_fuertes` ×3, `palabras_clave` (medias) ×2,
  `palabras_contexto` ×1, `palabras_castigo` −1. Solo se puntúa el título: la
  ubicación decide la zona, no la naturaleza del puesto.
- **Porcentaje**: `puntos × 100 / meta_puntos` (tope 100); categorías según
  `compatibilidad_minima` (defecto 70) y `compatibilidad_relacionada` (defecto 40).
- **Seniority**: si el título dice `senior`, `sr`, `lead`, `principal` o `staff` y no
  es junior/trainee, se muestra como Relacionada (máximo 69 %) para no competir con
  vacantes junior/mid.
- **Familias**: `puestos.familia_de` etiqueta el título como Soporte, Redes,
  Infraestructura, Campo, Aplicaciones, Seguridad u Otro TI. La app usa esa etiqueta
  en la columna **Enfoque**, en el filtro y en el reporte.
- **Coincidencia**: raíces con límite de palabra ("informatic" = informática,
  "n1" no coincide dentro de "Fun1dad"); sin acentos; un concepto cuenta una sola
  vez aunque aparezca en varios grupos.

## Pruebas y CI

- **Dónde**: `tests/` — `test_main.py` (filtros, config, lista negra, purgas, reporte,
  dedupe, paralelismo, meta diaria), `test_verificar.py` (`validthrough`, ID de
  Computrabajo, estados, corrida), `test_app_helpers.py` (filtros de la ventana, orden,
  resumen, estadísticas, config parcial), `test_compatibilidad.py` (puntaje, anclas,
  familias, sectores mixtos, seniority y calibración con ofertas reales),
  `test_consultas.py` (rotación de consultas), `test_almacen.py` (atomicidad, backups,
  rotación), `test_bloqueo.py` (reentrada) y `test_secretos.py` (DPAPI). Todas
  redirigen rutas a un temporal: **nunca tocan tus datos reales**.
- **Cómo** (desde la raíz del proyecto): `python -m unittest discover -s tests -v`.
  Sin dependencias de ejecución: se usa `unittest` de la biblioteca estándar.
- **CI**: `.github/workflows/ci.yml` pasa `ruff`, compila y corre las pruebas con
  cobertura en Windows con Python 3.10, 3.12 y 3.14 en cada push/PR.

## Los archivos de datos (carpeta `data/`, no se sube a GitHub)

| Archivo | Contenido | Quién lo escribe |
|---|---|---|
| `ofertas.csv` | Filas: fecha;fuente;titulo;ubicacion;empresa;url;estado_envio | `main.py`, app (estados) |
| `lista_negra.json` | `{urls: {clave: {hasta, titulo, fuente}}}` — no volver a traer | `pasar_a_lista_negra` |
| `vistas.json` | Qué URLs ya se vieron y cuándo | `main()` |
| `verificado.json` | Qué URLs se revisaron y cuándo (para no repetir el mismo día) | `verificar.py` |
| `reporte.html` | Visor de solo lectura | `escribir_reporte` |
| `historial.log` | Registro con fecha de todo lo que pasó; rota al superar 1 MB | `registrar` |
| `ui_state.json` | Geometría, orden y panel de filtros de la última sesión | `app.pyw` |
| `.buscador.lock` | Bloqueo de proceso entre la app y la tarea programada | `bloqueo.py` |
| `backups/` | Copias de `ofertas.csv` y `config.json` (últimas 10) | `almacen.py` |

## Si quieres cambiar algo, mira aquí

- **Otra zona o palabra** → botón *Perfil* (o `config.json`).
- **Que revise más o menos consultas por corrida** → *Preferencias* (`consultas_por_corrida`; 0 = todas) o `config.json`.
- **Que busque sola cada X minutos** → casilla *Auto* del pie o *Preferencias* (también `app_auto_minutos`; 0 = apagado).
- **La meta diaria de postulaciones** → *Preferencias* (`meta_postulaciones_dia`; 0 = sin meta).
- **Qué puestos entran** → pestaña *Enfoques* (`anclas_puesto`) y *Palabras que descartan* (`palabras_excluidas`/`incompatibles`).
- **La profundidad de Trabajo.org** → `max_paginas_trabajo_org` (defecto 8) en `config.json`.
- **Otra fuente de empleo** → nuevo archivo en `fuentes/` con `buscar(cfg)` + agregarlo a `FUENTES` en `main.py`.
- **El texto de los filtros de la búsqueda** → `pasa_filtros` en `main.py`.
- **Los filtros de la tabla** → `filtrar`, `ordenar` y `_leer_filtros` en `app.pyw`.
- **Cómo se puntúa la compatibilidad** → `compatibilidad.py` (grupos, pesos y umbrales), `puestos.py` (anclas y familias) o *Perfil*.
- **El aspecto de la ventana** → `COLORES`, `_estilos` y `_construir` en `app.pyw`.
- **Cuándo se retira una oferta** → `estado_oferta` en `verificar.py`.
- **La seguridad de los datos** → `almacen.py` (atomicidad/backups), `bloqueo.py` (concurrencia) y `secretos.py` (DPAPI).
- **Cómo se prueba algo** → `tests/`; añade un caso nuevo y corre `python -m unittest discover -s tests -v`.
