# Desarrollo del plugin QGIS

## Plataforma inicial

La instalación seleccionada para el primer MVP es QGIS LTR 3.40.5 Bratislava
en `/Applications/QGIS-LTR.app`. La instalación paralela QGIS 3.30.3 queda
fuera de la primera prueba para no mezclar versiones, perfiles o dependencias.

El diagnóstico reproducible se ejecuta desde la raíz del proyecto:

```bash
QT_QPA_PLATFORM=offscreen \
  /Applications/QGIS-LTR.app/Contents/MacOS/bin/python3 \
  scripts/check_qgis_runtime.py
```

El script configura GDAL y PROJ solo dentro de su proceso a partir del paquete
de QGIS. Escribe `validation/qgis_runtime.json` y comprueba:

- seis concentraciones contrastadas con cálculos analíticos independientes;
- transformación de Patache desde EPSG:4326 a EPSG:32719 con PyProj y QGIS;
- lectura de la tabla sintética de viento;
- escritura y lectura de un ráster float64 mediante GDAL incluido en QGIS.

Si QGIS se abre desde una terminal que hereda `PROJ_LIB` o `GDAL_DATA` de
Anaconda, puede mostrar todos los CRS como desconocidos aunque los archivos
estén bien escritos. Para iniciar una sesión aislada se usa:

```bash
scripts/launch_qgis_ltr_clean.command
```

El lanzador dirige únicamente ese proceso hacia GDAL y PROJ incluidos en QGIS;
no modifica el entorno global. El TIFF de validación contiene EPSG:32719 y los
dos GeoJSON se interpretan como EPSG:4326 mediante el controlador GeoJSON.

## Decisión de dependencias

El cálculo usa `gaussian_core.py`, NumPy y las capas numéricas existentes.
El adaptador del plugin usará CRS, transformación, escritura y simbología de
QGIS/GDAL. Folium y el etiquetado HTML permanecen como herramientas del
notebook. No se instalarán paquetes dentro de QGIS hasta demostrar que son
imprescindibles.

El algoritmo de Procesos ejecuta el caso Patache y carga sus resultados. El
panel interactivo 0.7 se apoya en ese recorrido: captura la fuente, muestra la
normalización de coordenadas y ejecuta el caso base en segundo plano.

## Proyecto visual de validación

El proyecto reproducible se genera con el Python incluido en QGIS:

```bash
QT_QPA_PLATFORM=offscreen \
  /Applications/QGIS-LTR.app/Contents/MacOS/bin/python3 \
  scripts/create_qgis_validation_project.py
```

Produce `outputs/qgis_validation/proyecto_validacion.qgz`, con OpenStreetMap,
ráster semitransparente, bandas YlOrRd, isolíneas categorizadas y etiquetadas y
la fuente. También genera `vista_validacion.png` para comprobar el render sin
interfaz y `validation/qgis_project.json` con CRS y alineación. La fuente queda
exactamente en el centro del ráster; la imagen confirma transporte hacia el sur.

`scripts/verify_qgis_outputs.py` vuelve a abrir ese proyecto con QGIS y verifica
estadísticas, muestras, NoData, unidades, niveles y estilos. Su resultado está
en `validation/qgis_layers.json`.

## Algoritmo de Procesos y panel 0.8.0

La versión experimental 0.8.0 registra **Pluma Gaussiana Educativa → Simulación
→ Simular pluma gaussiana**. Recibe punto con CRS, emisión y unidad, viento
constante o tabla CSV, altura de chimenea (con ascenso nulo), estabilidad A–F, dominio, resolución y unidad de
concentración. Permite elegir la serie automática 1–2–5 más el nivel superior o
ingresar niveles manuales. Escribe un GeoTIFF, isolíneas vectoriales y una capa
puntual de la fuente mediante las API incluidas en QGIS; devuelve CRS, máximo y
máximo periférico. Cuando la pluma visible alcanza el borde, emite una
advertencia no fatal con el valor periférico y su porcentaje respecto del máximo;
el umbral físico predeterminado es 0.1 µg/m³ y se convierte al cambiar la unidad
de visualización. El GeoTIFF sigue siendo válido dentro del dominio calculado,
pero queda truncado.

El código fuente está en `qgis_plugin/gaussian_educativo/`. Los enlaces internos
apuntan a los módulos canónicos para no mantener una segunda copia del núcleo.
`scripts/build_qgis_plugin.py` los materializa en el ZIP instalable junto con su
licencia. `scripts/test_qgis_processing_algorithm.py` ejecuta el algoritmo real
desde el registro de Procesos y deja el resultado en
`validation/qgis_processing_algorithm.json`.

El caso Patache del paquete 0.14.0 reproduce EPSG:32719, grilla 200 × 200,
máximo 221.557028422 µg/m³ y máximo periférico 57.279337014 µg/m³. Genera las
isolíneas 1, 2, 5, 10, 20, 50, 100 y 200 µg/m³. QGIS carga el ráster con
bandas YlOrRd, las líneas categorizadas con etiquetas curvas y la fuente con un
icono de chimenea.

La política predeterminada conserva el dominio fijo. La opción de extensión
duplica solo los márgenes cuyos bordes superan `0.1 µg/m³` o `1 %` del máximo,
mantiene resolución y alineación de píxeles y vuelve a calcular los cuatro
bordes. Se detiene antes de superar 100 km por lado o cuatro millones de celdas.
Para Patache realiza cuatro extensiones y termina en 15 × 85 km: el máximo se
conserva y el borde baja de 57.2793 a 1.19510 µg/m³, pero sigue marcado como
truncado por alcanzar el límite de seguridad.

El modo tabla recomienda `timestamp_utc`, `direction_from_deg` y
`wind_speed_m_s`, en ISO 8601 UTC, grados meteorológicos DESDE y m/s. Cada fila
representa un intervalo de igual duración; el complemento cuenta las
observaciones en cada sector y clase de velocidad para obtener las frecuencias.
La rosa muestra las calmas en el centro y las direcciones variables por
separado; ambas se calculan sobre las observaciones no ausentes junto con los
pétalos direccionales. El núcleo no admite viento nulo ni dirección
indeterminada, por lo que las excluye de la concentración y renormaliza las
filas direccionales válidas como una media condicional. Por compatibilidad
avanzada también acepta `frequency_percent` o `weight`. Calcula una pluma
estacionaria por observación direccional y después su media. La dirección circular
representativa se informa como resumen,
pero no sustituye las direcciones originales. Puede guardar una rosa de vientos
PNG mediante Matplotlib incluido en QGIS. Con las 1200 observaciones sintéticas
NE–SO, 100 g/s y estabilidad A reproduce el notebook: dirección representativa
44.825494°, rapidez media 5.446717 m/s, máximo 941.030852577 µg/m³ y borde
0.862455131 µg/m³.

La extensión automática se restringe por ahora al viento constante. Aplicarla
sin agregación a una tabla de 1200 registros multiplicaría el costo de cada
iteración y puede superar los límites prácticos del MVP; el formulario devuelve
un error claro si se combinan ambas opciones.

El panel lateral se abre desde el menú o el botón **Pluma Gaussiana Educativa**.
Permite usar el centro del lienzo o capturar un punto. Conserva la coordenada y
el CRS del mapa, la transforma a longitud/latitud WGS84 y muestra anticipadamente
el CRS UTM/UPS, Este y Norte que usará el cálculo. Un CSV opcional prepara el
modo tabla y fuerza dominio fijo. El botón final abre el diálogo estándar del
algoritmo con fuente y viento precargados; allí siguen visibles todos los
parámetros y destinos antes de ejecutar. El panel expone emisión y unidad,
altura de chimenea (igual a la efectiva en el modo básico), estabilidad, viento constante o CSV, tamaño y resolución de
grilla, política del dominio, unidad de concentración e isolínea mínima. La
ejecución directa usa esos valores, escribe cada corrida en una carpeta nueva, informa el
progreso, admite cancelación y carga fuente, isolíneas y ráster en un grupo.
`scripts/test_qgis_panel.py` verifica normalización y rutas;
`scripts/test_qgis_direct_run.py` ejecuta y carga el flujo asíncrono completo.

La versión 0.8 guarda `escenario.json` en cada corrida con entradas, coordenadas
originales, CRS en WKT, versión del formato y estado de ejecución. El CSV se
copia junto al escenario y se registra su SHA-256; al abrir se valida antes de
cambiar el panel. Las rutas de CSV guardadas son relativas al JSON para poder
trasladar ambos archivos juntos. Los destinos de una ejecución anterior no se
reutilizan al repetir el escenario. El formato 1 guarda los índices de opciones
del algoritmo actual; cualquier cambio de orden debe migrar el formato.

## Instalación y corrida en el perfil habitual · 2026-09-12

Se instaló el ZIP 0.7.0 en `QGIS3/profiles/default/python/plugins/` y se
compararon sus 14 archivos con el paquete: ninguna diferencia. El helper
`scripts/verify_qgis_interactive_run.py` cargó el complemento instalado y
ejecutó Patache desde el panel. Generó un único grupo de tres capas, máximo
221.557028422 µg/m³, borde 57.279337014 µg/m³ y EPSG:32719.

El proyecto quedó en `outputs/qgis_interactive/proyecto_patache_070.qgz`;
informe y captura en `validation/qgis_installed_interactive.*`. La instancia
se abrió con `--noplugins` y cargó Processing y Gaussian explícitamente porque
el arranque con los demás complementos del perfil no llegó a ejecutar el
helper. Esto no demuestra un conflicto concreto con Gaussian ni modifica
la configuración de los otros complementos; queda pendiente comprobar su
coexistencia en un arranque normal. En macOS, `--profiles-path` debe apuntar a
la carpeta `QGIS3`, que contiene `profiles/`, y no a `profiles/` directamente.

La instalación 0.8.0 se verificó en una nueva ventana del mismo perfil con
Processing y Gaussian cargados explícitamente. Se conservó la ventana anterior
para no perder posibles ediciones pendientes. El helper
`scripts/verify_qgis_scenario_roundtrip.py` ejecutó Patache, descargó y recargó
el complemento, abrió el escenario guardado y repitió la corrida. Conservó el
CRS original EPSG:32719 y obtuvo parámetros idénticos; máximo, borde, CRS de
salida, dimensiones y estado del dominio coincidieron exactamente. El proyecto
quedó en `outputs/qgis_scenarios/proyecto_patache_080.qgz` y la evidencia en
`validation/qgis_scenario_roundtrip.json` y su captura PNG. Esta comprobación
usa la API del panel; queda pendiente probar los diálogos de archivo mediante
interacción manual y la coexistencia con los demás complementos.

## Pruebas de cierre del MVP · 2026-09-13 · 0.8.1

Se respaldaron `validation/`, `outputs/qgis_plugin/` y el complemento instalado
antes de repetir las pruebas. Las pruebas de `scripts/validate.py` pasaron en `gee`; los seis controles
analíticos de centro de pluma tuvieron error relativo máximo cero.

Una prueba nueva demostró un error de encuadre en 0.8.0: el panel asignaba la
extensión UTM del ráster a un lienzo WGS84, produciendo coordenadas del orden de
375000 y 7700000 grados. La corrección 0.8.1 transforma la extensión al CRS
actual del lienzo antes del zoom; no modifica el cálculo ni el CRS del proyecto.

Pruebas ejecutadas con el Python de QGIS LTR y el ZIP 0.8.1 extraído:

- `test_qgis_processing_algorithm.py`: dominio fijo, extensión de cuatro
  iteraciones y CSV de 1200 observaciones con rosa PNG. Valores reproducidos.
- `test_qgis_direct_run.py`: tarea asíncrona, tres salidas agrupadas, encuadre
  WGS84 correcto, cancelación y registro de escenario cancelado.
- `test_qgis_panel.py`: parámetros, botones de guardar/abrir con selector de
  archivo simulado, JSON y CSV trasladados, cancelación del selector, rechazo
  de CSV alterado y escenario inválido sin cambiar las entradas.
- `test_qgis_project_reopen.py`: reapertura de cuatro proyectos con rutas,
  capas, CRS, colores, etiquetas y SVG válidos; produjo nuevas capturas.

`verify_qgis_clean_startup.py` se ejecutó en una instancia real con un perfil
temporal y carga normal de complementos. Pasó junto con Processing, MetaSearch,
DB Manager y GRASS; un clic mediante Qt seleccionó la fuente, restauró la
herramienta anterior y el botón Ejecutar produjo las capas con zoom WGS84
correcto. El punto clicado fue (-70.195, -20.805), próximo pero diferente de
Patache exacto; su máximo fue 335.276328 µg/m³. La captura se inspeccionó.

Para repetir esa prueba, extraer el ZIP en
`<base>/profiles/acceptance/python/plugins/`, habilitar Gaussian y Processing
en ese perfil y lanzar `scripts/launch_qgis_ltr_clean.command --profiles-path
<base> --profile acceptance --code <ruta-absoluta-del-helper>`. En este macOS
los ajustes efectivos del perfil están en `qgis.org/QGIS3.ini`. El helper usa
una carpeta de resultados propia y cierra únicamente su instancia de prueba.

Informes: `validation/qgis_{panel,direct_run,processing_algorithm,project_reopen,
clean_startup}.json`. Se instaló el paquete 0.8.1 en el perfil habitual y sus 14
archivos coincidieron exactamente; `validation/qgis_installation_081.json`
registra el SHA-256 del ZIP. Las ventanas previas se conservaron; una instancia
que ya tiene cargado 0.8.0 necesita recargar el complemento o reiniciar QGIS.

Quedan pendientes la aceptación humana de los selectores de archivo y el
formulario avanzado, y el arranque con los complementos adicionales del perfil
habitual. No se marca la versión como estable. El truncamiento de Patache y la
restricción de extensión automática a viento constante siguen documentados.

## Idiomas y portabilidad · 2026-09-13 · 0.9.0

El catálogo bilingüe cubre panel, Procesos, ayuda, nombres de capas y mensajes
propios. La rosa recibe un argumento opcional de idioma, con español como
default compatible; no cambian las frecuencias ni el cálculo de viento.
Los escenarios usan UTF-8 explícito. El complemento sigue el idioma de QGIS y
requiere recarga después de cambiarlo; IDs y archivos siguen siendo comunes.

Pasaron nuevamente las 42 pruebas de `gee`, las pruebas del panel y, con el
ZIP final, idiomas, tarea/cancelación y Procesos (fijo, extensión y CSV).
`validation/qgis_languages.json` registra es_CL, en_US y fallback fr_FR, con
idénticas entradas del escenario; las capturas español/inglés se generaron y
la vista inglesa se inspeccionó. El paquete instalado coincide en sus 16
archivos, según `validation/qgis_installation_090.json`; la versión anterior
quedó respaldada. No se cerraron ventanas con proyectos del usuario.

`docs/compatibility.md` registra dependencias, pruebas por plataforma y cómo
ejecutar `scripts/check_qgis_installation.py` desde la consola QGIS. En Mac
Intel 3.40.5 están disponibles NumPy, GDAL, PyProj y Matplotlib sin instalación
adicional. Windows, Apple Silicon y QGIS 3.44 LTR siguen pendientes. QGIS 4 no
se declara compatible: metadata limita explícitamente a 3.x hasta completar la
migración y las pruebas Qt6. Las pruebas de arranque limpio anteriores son de
0.8.1 y no se atribuyen a la versión 0.9.0 sin repetirlas.

## Diálogos reales y repetición bilingüe · 0.9.0 · 2026-09-13

`scripts/verify_qgis_scenario_dialogs.py` pasó en una instancia real de QGIS
3.40.5 con un perfil temporal y el ZIP 0.9.0 extraído. El complemento estaba
cargado por el arranque normal antes del helper. Se utilizaron selectores
QFileDialog reales y sus campos/botones, sin sustituir sus respuestas. Se
forzaron widgets Qt: esta prueba no acredita los selectores nativos de macOS.

Se guardó el JSON, se canceló una apertura sin alterar las entradas y se abrió
el escenario para recuperar sus parámetros. Después de la primera corrida se
recargó Gaussian con idioma inglés, se abrió el mismo archivo y se repitió el
caso. Se conservó la entrada original EPSG:32719; parámetros y resultados
coincidieron exactamente, incluidos todos los píxeles del GeoTIFF. La segunda
corrida usó otra carpeta. El informe es
`validation/qgis_scenario_dialogs_090.json` y señala la carpeta de resultados,
capturas de diálogos y `proyecto_patache_090.qgz` con ambos grupos de capas.
La captura inglesa del mapa se inspeccionó.

`scripts/test_qgis_project_reopen.py` admite ahora proyectos explícitos,
`--expected-layers` y `--report`. Se volvió a abrir ese proyecto con seis capas:
CRS, archivos, colores, etiquetas y SVG siguieron válidos; se produjo una
nueva imagen. Evidencia en `validation/qgis_dialog_project_reopen_090.json`.
Se cerró solamente la instancia temporal; las ventanas del usuario quedaron
intactas. No se modificaron las ecuaciones físicas durante esa prueba; el ZIP
conserva su SHA-256 registrado.

Quedan la evaluación humana de usabilidad, los diálogos nativos y el formulario
avanzado, el arranque con complementos adicionales del usuario y la matriz
Mac/Windows en QGIS 3.44 LTR. El siguiente ensayo técnico es instalar 3.44 LTR
en paralelo en Mac y repetir estos casos sin sustituir la instalación actual.

## QGIS 3.44 LTR y corrección de hilos · 0.9.1 · 2026-09-14

Se instaló QGIS 3.44.14 LTR en paralelo y se probó el ZIP 0.9.1 sin añadir
paquetes a QGIS. Pasaron los controles de runtime, dependencias, panel, idiomas,
Procesos, ejecución y cancelación asíncrona, y reapertura de proyectos, tanto
en arm64 nativo como en x86_64/Rosetta. QGIS 3.40.5 pasó la misma batería.

La primera ejecución asíncrona en 3.44 reprodujo un cierre en PROJ cuando
PyProj construía el CRS dentro del trabajador de Qt. La versión 0.9.1 resuelve
esto en `prepareAlgorithm`: transforma la entrada y prepara el CRS en el hilo
principal antes de ejecutar el trabajo pesado. La grilla, concentración,
isolíneas y archivos continúan en segundo plano, con cancelación. Esta es una
corrección de integración; `gaussian_core.py` y las funciones físicas no se
modificaron. Matplotlib 3.11 también requirió sustituir la API retirada
`cm.get_cmap` por `cm.Blues`, conservando la misma paleta y frecuencias.

Los informes separados están en `validation/qgis_340_091/`,
`validation/qgis_344_091/` y `validation/qgis_344_arm64_091/`. Windows, QGIS
4/Qt6, los diálogos nativos de macOS y la evaluación humana de usabilidad
siguen pendientes antes de declarar una versión estable.

## Modos sintéticos simplificados · 0.10.0 · 2026-09-17

El panel ofrece constante, predominante sintético, aleatorio uniforme sintético
y tabla CSV. Para mantener una entrada docente sencilla no expone horas,
desviación ni semilla: los modos sintéticos usan 1200 intervalos y semilla
22001, y el predominante usa desviación 40°, como el notebook. La dirección
DESDE se usa en constante y como centro en predominante; queda desactivada y se
ignora en aleatorio uniforme. Estos parámetros se guardan por modo y las tablas
CSV de escenarios 0.9.1 se migran al abrirlas.

La prueba manual reveló que 10 × 10 km a 10 m produce un millón de celdas y,
con 1200 direcciones, 1200 millones de evaluaciones. QGIS continuaba calculando
al 100 % de un núcleo, pero la interfaz parecía detenida. La versión 0.10.1
añade un límite interactivo de 50 millones, avance por dirección y cancelación
entre direcciones. Esa combinación ahora se rechaza antes de calcular y propone
50 m; no se aproximaron ni agruparon las 1200 direcciones.

## Extensión sintética limitada · 0.10.2 · 2026-09-19

Un dominio de 10 × 10 km a 50 m contiene 40.000 celdas. Con 1200 muestras de
viento sintético requiere 48 millones de celda-direcciones y puede calcularse,
pero la siguiente extensión automática supera el límite de 50 millones. La
versión 0.10.2 detiene esa ampliación, conserva la grilla inicial y termina con
el estado `computational_limit_reached_truncated`. Así entrega el GeoTIFF y las
capas con una advertencia reproducible, en lugar de fallar después del cálculo
inicial.

## Agregación direccional para cálculo · 0.10.5 · 2026-09-19

La rosa mantiene 16 sectores de 22,5° para facilitar su lectura. La dispersión
usa 72 sectores de 5° y siete clases de velocidad; cada grupo conserva su peso,
la dirección circular media y la rapidez armónica. En el prevaleciente
predeterminado quedan 52 clases ocupadas en vez de 1200 plumas individuales.
La comparación controlada registró +0,97 % en el máximo, 0,16 % de RMSE
normalizado y una aceleración aproximada de 23 veces. El límite interactivo se
aplica ahora a celda-clase. `validation/prevailing_method_comparison.*`
conserva el detalle reproducible.
