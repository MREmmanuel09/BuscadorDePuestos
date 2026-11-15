# Buscador de Puestos

Busca ofertas que coincidan con tu perfil (Soporte TI / Redes / Infraestructura) en las zonas configuradas, las clasifica por **enfoque real del puesto** y te ayuda a postular todos los días.

## Uso diario (aplicacion)

- **Icono del escritorio "Mis Ofertas"** (o doble clic en `Abrir Ofertas.cmd`): abre la aplicacion
  para ver las ofertas, buscar, verificar disponibilidad y gestionar la lista negra.
  No necesita servidor ni conexion especial: siempre funciona.
- **Filtros rapidos**: chips de *Compatibles*, *Relacionadas*, *Todas*, *Nuevas hoy*,
  *Sin postular* y *Remoto*; el boton *Filtros* abre fuente, zona, estado y **enfoque**
  (Soporte, Redes, Infraestructura, Campo, Aplicaciones, Seguridad). Los filtros
  activos se ven en una linea de resumen y *Limpiar* los restablece.
- **Orden por columna**: clic en *Puesto*, *Empresa*, *Enfoque*, *Compat*, *Ubicacion*,
  *Dias* o *Estado*; la flecha indica el sentido.
- **Seleccion contextual**: al marcar filas aparecen *Marcar*, *Eliminar*, *Copiar
  enlace* y *Abrir*. El menu contextual (clic derecho) ofrece las mismas acciones.
- **Menu `⋮`**: verificar, lista negra, depurar incompatibles, estadisticas,
  preferencias y atajos.
- **Editar perfil**: cambiar zonas, terminos de busqueda, grupos de palabras del
  puntaje y **anclas de puesto** (pestañas Busqueda, Compatibilidad y Enfoques;
  guarda en `config.json`).
- Cada oferta muestra su **% de compatibilidad** y su **enfoque**; la fuente y la
  antiguedad aparecen en el pie al seleccionarla.
- El encabezado muestra la **meta diaria**: `Hoy 3/5 postuladas`.
- Doble clic o `Enter` abre la oferta en el navegador.
- `buscar.cmd` solo ejecuta la busqueda sin abrir la app (para corridas manuales/rapidas).

## Que hace cada ejecucion

1. Consulta 4 fuentes publicas (en paralelo): Computrabajo, Trabajo.org, FindJob24h y LinkedIn (endpoint publico de invitados). Si una fuente falla, las demas siguen. Cada fuente usa una **ventana de consultas rotada** (`consultas.py`): las 8 esenciales siempre corren y el resto cambia dia a dia.
2. **Exige un ancla de TI en el titulo** (soporte, redes, help desk, NOC, infraestructura, data center...) y descarta otros rubros/roles. Luego **puntua (0-100 %)** contra tu perfil: fuertes x3, medias x2, contexto x1 y castigos -1. Bajo el umbral = Descartada (no entra); 40-69 % = Relacionada; 70 %+ = Compatible. Los puestos senior se muestran como Relacionadas.
3. Etiqueta cada oferta con su **enfoque** (Soporte, Redes, Infraestructura, Campo, Aplicaciones, Seguridad u Otro TI) para filtrar sin perder flexibilidad.
4. Descarta repetidas (misma URL o mismo titulo + empresa), ofertas ya vistas (`buscador\data\vistas.json`), en lista negra (`buscador\data\lista_negra.json`, vigencia de `dias_lista_negra`) y vacantes temporales con fecha de cierre vencida en el titulo.
5. Borra automaticamente las ofertas con mas de `dias_retencion` dias (por defecto 15; las marcadas con `estado_envio` se conservan) y las mueve a la lista negra.
6. Agrega las nuevas a `buscador\data\ofertas.csv` (abrelo con Excel, separador `;`).
7. **Verifica si las ofertas siguen disponibles** (`verificar.py`): si una pagina dice "ya no se aceptan solicitudes", "oferta finalizada", responde 404/410, perdio su ID o su `validthrough` vencio, la retira del CSV y la pone en lista negra. Solo con evidencia positiva: un error de red nunca borra nada. Las ya revisadas hoy no se repiten.
8. Genera `buscador\data\reporte.html` (visor de solo lectura, con columna Compat, columna Enfoque y secciones Compatibles/Relacionadas).
9. Muestra una notificacion de Windows si hay ofertas nuevas.

## Configuracion

En el primer arranque se crea `buscador\config.json` a partir de
`buscador\config.example.json` (la plantilla versionada en Git). Lo mas comun es
editar el perfil desde la aplicacion; las claves manuales son:

- `palabras_clave_busqueda`: terminos que se consultan en las fuentes (catalogo de 27; la corrida usa una ventana).
- `consultas_fijas`: cuantas de esas consultas corren siempre (defecto 8).
- `consultas_por_corrida`: cuantas consultas usa cada fuente por corrida (defecto 16; `0` = todas).
- `anclas_puesto`: frases que debe contener el titulo para que la oferta sea del perfil (soporte, redes, help desk, NOC, infraestructura...).
- `palabras_fuertes`: puestos de TI (x3): "soporte ti", "help desk", "redes", "sysadmin", "noc analyst"...
- `palabras_clave`: palabras medias (x2): "soporte", "support", "sistemas", "infraestructura", "telecom"...
- `palabras_contexto`: tecnologias y herramientas (x1): "windows", "m365", "active directory", "wifi", "cisco"...
- `palabras_castigo`: bajan el puntaje (-1): "bilingual", "ingles avanzado", "senior", "french"...
- `palabras_excluidas` e `incompatibles`: anulan la oferta (ventas, desarrollo, atencion al cliente, aire acondicionado, enfermeria, electromecanica...). Los sectores que acompañan a un puesto de TI ("... y obra civil") se toleran como enfoque mixto; si son el objeto del puesto, se descartan.
- `compatibilidad_minima`: % desde el que una oferta es **Compatible** (defecto 70).
- `compatibilidad_relacionada`: % desde el que es **Relacionada** (defecto 40; debajo queda Descartada).
- `meta_puntos`: puntos que equivalen a 100 % (defecto 4; subirlo = mas exigente).
- `palabras_remoto`: palabras que marcan una oferta como remota.
- `zonas`: zonas aceptadas (tambien se usan para las paginas de Trabajo.org).
- `incluir_remoto`: acepta teletrabajo sin importar la zona.
- `dias_retencion`: dias antes de que una oferta se borre sola del CSV (defecto 15; pon 7 para una semana).
- `dias_lista_negra`: dias que una oferta eliminada no puede volver a aparecer (defecto 15).
- `verificar_en_busqueda`: activa la deteccion de ofertas cerradas en cada corrida (defecto true).
- `verificar_max_por_corrida`: cuantas ofertas viejas se revisan por corrida (defecto 30).
- `max_paginas_por_busqueda`: paginas por consulta en Computrabajo/LinkedIn (defecto 1).
- `max_paginas_trabajo_org`: paginas por zona en Trabajo.org (defecto 8; mas = mas opciones y mas tiempo).
- `meta_postulaciones_dia`: meta diaria que se muestra en el encabezado (defecto 5; `0` = sin meta).
- `notificar_toast`: notificacion de Windows.
- `abrir_reporte`: abrir `reporte.html` automaticamente cuando hay ofertas nuevas.
- `app_auto_minutos`: cada cuantos minutos la app busca sola (defecto 0 = apagado; se activa con la casilla *Auto* del pie o desde *Preferencias*).
- `config_version`: version del formato de configuracion; la app la actualiza sola.
- `correo`: para recibir el aviso por email, activar y llenar con una clave de aplicacion de Gmail. La clave se cifra con DPAPI en `clave_app_cifrada` al guardar.

## Aplicacion (`buscador\app.pyw`)

- **Buscar ahora**: corre la busqueda completa y actualiza la tabla (barra de estado con el progreso).
- **Verificar**: revisa las ofertas viejas y retira las que ya no existen (tambien en el menu `⋮`).
- **Filtros**: chips de categoria y atajos; *Filtros* abre fuente, zona, estado y enfoque; *Limpiar* restablece todo.
- **Orden**: clic en cualquier encabezado; la flecha muestra el sentido.
- **Barra contextual**: al seleccionar aparecen *Marcar*, *Eliminar*, *Copiar enlace* y *Abrir*.
- **Menu `⋮`**: verificar, lista negra, depurar, estadisticas, preferencias y atajos.
- **Lista negra**: ventana con lo oculto, fecha de expiracion y boton para restaurar.
- **Depurar**: retira las ofertas **Descartadas** (bajo el umbral de compatibilidad) a la lista negra.
- **Editar perfil**: pestanas *Busqueda* (zonas, terminos, remotas), *Compatibilidad*
  (grupos de palabras, descartes y umbrales) y *Enfoques* (anclas de puesto); se
  aplica al guardar.
- **Estadisticas**: resumen con total, estados, categoria de compatibilidad, reparto
  por enfoque, ofertas nuevas de los ultimos 7 dias y conteo por fuente.
- **Preferencias**: auto-busqueda, meta diaria, consultas por corrida, avisos de
  Windows, abrir reporte y carpeta de datos.
- `reporte.html` es un visor de solo lectura (la gestion es en la app).

## Como tener mas opciones cada dia

- En *Preferencias*, sube **Consultas por corrida** a 20-24 o pon `0` para usar las 27.
- Revisa la pestana *Enfoques*: si un puesto que si te interesa queda fuera, agrega su palabra (por ejemplo `noc`, `field service`, `soporte de aplicaciones`).
- Revisa *Palabras que descartan*: la lista nueva ya quita desarrollo, ventas, salud, electromecanica y atencion al cliente. Si quieres volver a ver algo, quita la frase.
- Agrega zonas solo si el transporte lo permite: Heredia y los distritos del GAM destraban muchas ofertas de LinkedIn.
- Corre la busqueda a diario: la rotacion cubre el catalogo completo en varios dias sin repetir siempre lo mismo.
- Usa el filtro **Enfoque** y la columna del mismo nombre para armar una lista corta (primero Compatibles, despues Relacionadas).

## Datos y seguridad

- Cada escritura usa un archivo temporal y `os.replace`: un cierre inesperado no
  deja el CSV o los JSON a medias.
- `buscador\data\.buscador.lock` evita que la app y la tarea programada escriban a la vez.
- Antes de purgar o eliminar ofertas se guarda una copia en `buscador\data\backups\`
  (se conservan las ultimas 10).
- La clave SMTP se cifra con DPAPI de Windows; `config.json` deja de contenerla en texto plano.
- `buscador\data\ui_state.json` guarda tamano de ventana, orden y panel de filtros;
  los filtros no se conservan entre sesiones para que ninguna oferta quede oculta.

## Pruebas y CI

- Corre `python -m unittest discover -s tests -v` desde la raiz del proyecto
  (carpeta `tests/`): pruebas de filtros, lista negra, verificador, almacenamiento,
  bloqueo, cifrado y helpers de la app. Todo usa temporales, nunca toca tus datos reales.
- GitHub Actions (`.github/workflows/ci.yml`) revisa con `ruff`, compila y ejecuta
  las pruebas con cobertura en Windows para Python 3.10, 3.12 y 3.14 en cada push/PR.

## Borrar ofertas (evitar cola infinita)

- **Manual (app):** seleccionar y pulsar *Eliminar* en la barra contextual → entra a
  `lista_negra.json` por `dias_lista_negra` dias: el sistema no la vuelve a traer como
  nueva en ese plazo.
- **Depurar (app):** en el menu `⋮`, *Depurar incompatibles* retira de una vez todas las
  ofertas Descartadas (que no llegan al umbral): ideal si el perfil cambio o entro ruido.
- **Automatico:** cada corrida purga del CSV las ofertas con mas de `dias_retencion` dias (y las
  mueve a la lista negra); las marcadas con `estado_envio` no se purgan por antiguedad.
- **Cerradas:** el verificador retira sola las ofertas finalizadas/cerradas (ver paso 6).
- **Terminal (avanzado):** `python buscador\eliminar.py` (purga 7/15 dias o por numeros) o
  `python buscador\verificar.py` (solo verificacion).

## Programar una vez al dia (8:00 am)

Ejecutar una vez en PowerShell:

```
schtasks /Create /TN "BuscadorPuestos" /TR "\"D:\Proyectos\BucadorDePuestos\buscar.cmd\"" /SC DAILY /ST 08:00
```

Para probar: `schtasks /Run /TN "BuscadorPuestos"`
Para eliminar: `schtasks /Delete /TN "BuscadorPuestos" /F`

## Limitaciones conocidas

- Algunos portales (ej. Gente Coyol) requieren inicio de sesion: revisarlos manualmente.
- LinkedIn se consulta por su endpoint publico de invitados; puede cambiar o bloquearse sin aviso. Respaldo: activar alertas de empleo por correo en LinkedIn.
- Las zonas se amplian desde **Editar perfil** en la aplicacion.
- Uso personal, las fuentes son publicas y se consultan con pausas entre solicitudes.
