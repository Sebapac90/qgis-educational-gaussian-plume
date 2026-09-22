# Primer caso sobre mapa real — 2026-09-08

## Objetivo y ubicación

Prueba docente de georreferenciación sobre terreno plano. Patache es una
entrada del escenario, no una ubicación fija del núcleo o del módulo espacial.
La selección con clic y la interfaz de QGIS pertenecen a la siguiente etapa.

Coordenadas referenciales: longitud -70.193195, latitud -20.805320, WGS84.
Fuente: https://www.gem.wiki/Patache_power_station
No se afirma que el punto corresponda al eje exacto de una chimenea.
No se reconstruyen emisiones históricas ni operación actual de la central.

## Arquitectura y uso

- `gaussian_core.py`: ecuaciones previamente validadas, sin cambios.
- `gaussian_spatial.py`: ubicación, UTM, viento y grilla de receptores.
- `gaussian_raster.py`: GeoTIFF y reproyección para la vista web.
- `gaussian_map.py`: visualización cartográfica con Folium/OpenStreetMap.
- `examples/patache.json`: todas las entradas del caso, con unidades.
- `scripts/run_spatial_case.py`: recorrido reproducible del caso espacial.

El mapa permite navegar, activar capas y leer coordenadas al hacer clic.
El control de capas incluye **Información del escenario**, activada inicialmente:
permite ocultar y volver a mostrar el panel completo de parámetros, leyenda e
instrucciones, sin alterar la visibilidad del ráster, isolíneas o máximo.
La dirección del viento se representa en una rosa compacta fija en pantalla,
fuera de la pluma, con flecha hacia el azimut de transporte. Su capa se puede
ocultar desde el mismo control. La fuente usa un símbolo de chimenea anclado
en sus coordenadas; el humo del icono es solo gráfico y no codifica dirección.
El clic no cambia la fuente ni recalcula la pluma en esta versión.
Las teselas de OpenStreetMap son cartografía web, no una fotografía ajustada
manualmente al dominio. La capa de concentración se deriva del GeoTIFF.
Las teselas y los recursos JavaScript del mapa necesitan internet; el cálculo
y la salida GeoTIFF son locales y no dependen de conexión.

## Decisiones espaciales

- Entrada: WGS84 geográfico (EPSG:4326) o WGS84 UTM/UPS con EPSG explícito.
  En WGS84, `x` es longitud y `y` latitud; en UTM/UPS, `x` es Este y `y` Norte.
  Los números UTM sin CRS son ambiguos y el futuro formulario debe rechazarlos.
- Cálculo: `calculation_crs: "auto"` elige la zona WGS84 UTM local entre
  80°S y 84°N, incluidas las excepciones de Noruega y Svalbard; usa WGS84 UPS
  Norte/Sur más allá de esos límites. Si la entrada ya es UTM/UPS, el modo
  automático conserva ese CRS después de comprobar su área de uso. Para
  Patache el resultado es WGS84 / UTM 19S, EPSG:32719, metros.
- Orden: longitude/latitude al ingresar WGS84; Easting/Northing al proyectar.
  Se usa `always_xy=True` para evitar intercambio de ejes.
- Viento meteorológico DESDE, horario desde norte verdadero. El escenario
  usa explícitamente **0° desde el norte, hacia 180° sur**, 5 m/s.
  No se introdujo ni se cambió un valor predeterminado a 180°.
- Norte de la grilla: α_grid = α_true − convergencia de meridianos en la
  fuente. En Patache, la convergencia es aproximadamente +0.423870°.
  Se mantiene ese ángulo uniforme en todo el dominio plano.
- La rotación cartesiana sigue las fórmulas de `docs/model.md`. Los valores
  residuales menores que 32 eps × max(1 m, distancia) se fijan a cero para
  representar correctamente el plano x_downwind=0 ante redondeo numérico.
- Grilla: 10 000 × 10 000 m, centrada en la fuente, píxeles de 50 × 50 m.
  Son 200 filas × 200 columnas, 40 000 receptores en centros de píxel.
  No confundir con los 101 × 101 vértices del cuaderno de paso 100 m.
- Las dimensiones deben ser múltiplos de la resolución; no se redondea el
  dominio silenciosamente. Máximo de esta implementación: 4 millones de
  celdas y 100 km por lado como límite de recursos/alcance local, no como
  rango de validez física del modelo. La selección automática se prueba en
  ambos hemisferios y regiones polares. Esto permite ubicar el caso globalmente,
  pero no convierte el modelo en uno de transporte a larga distancia: cada
  simulación conserva el alcance local.
- Matriz: fila 0 al norte; columnas de oeste a este. Transformación afín
  definida en la esquina exterior noroeste; altura de píxel negativa.
- Receptor z=0 m sobre un suelo idealizado horizontal, sin DEM, máscara
  terrestre ni efectos de edificios. Se calcula también sobre el mar.
- Altura efectiva 50 m suministrada; no se calcula ascenso de pluma.
- Emisión hipotética: 40 g/s → 0.04 kg/s; clase D, estabilidad constante.
- GeoTIFF float64, una banda, µg/m³: conversión explícita desde kg/m³ × 1e9.
  Los valores corresponden a centros, no a promedios del área de cada píxel.
- NoData reservado=-9999; cero es dato válido. Se conservan todas las
  concentraciones del dominio, incluidos los ceros upwind.
- Mapa: reproyección real a EPSG:3857, vecino más próximo, antes de mostrar
  la matriz sobre Leaflet. No se estira directamente la matriz UTM usando
  únicamente sus esquinas geográficas. El TIFF original queda en UTM.
- Umbral visual 0.1 µg/m³; inferior a él es transparente, no eliminado del TIFF.
  La versión actual usa bandas YlOrRd delimitadas por las isolíneas, como se detalla en
  «Visualizaciones alternativas».

## Resultado inicial y límites

El caso Masters produce un máximo muestreado de aproximadamente 221,557 µg/m³.
Es diferente del receptor puntual usado durante la exploración inicial porque la grilla tiene
otros centros de muestreo. Al borde sur aún hay aproximadamente 57,279 µg/m³:
la pluma visible **alcanza el límite del dominio**. No se afirma que desaparezca
a 5 km. El informe registra este hecho; se puede ampliar el dominio después.

## Validación

Las 12 pruebas físicas previas se mantienen. Las pruebas espaciales cubren:
ida/vuelta WGS84-UTM, rechazo de CRS inadecuados, cardinales y oblicuas,
corrección de norte verdadero contra una trayectoria geodésica independiente,
grilla rectangular y centros, traslación y plano fuente, comparación directa
entre la capa espacial y el núcleo en cinco direcciones, y lectura del GeoTIFF/reproyección web.
También verifican selección automática en ambos hemisferios, excepciones UTM,
UPS polar y equivalencia de la concentración al ingresar la misma fuente en
EPSG:4326 o EPSG:32719.

La comparación espacial permite rtol=1e-10, atol=1e-300 kg/m³ por diferencias
de redondeo de ángulos equivalentes, especialmente en colas exponenciales.
Las tolerancias anteriores del núcleo permanecen sin cambios.

Se verifica que el CRS leído sea EPSG:32719, valores, unidades, forma, bordes,
NoData, que cero conserve máscara válida y que un patrón de datos asimétrico
mantenga su orientación tras escritura y reproyección para el mapa.

## Entorno de ejecución

Comprobado con Python 3.11.4, NumPy 1.24.3, PyProj 3.6.0, Rasterio 1.4.3,
Folium 0.14.0 y Matplotlib 3.7.1.

Anaconda heredaba PROJ_LIB apuntando a una base PROJ incompatible con Rasterio.
Los lanzadores de pruebas y escenario eliminan PROJ_LIB/PROJ_DATA solo del
proceso actual antes de importar GIS, para usar las bases incluidas con las
bibliotecas. No se modifica la configuración global ni ningún archivo de PROJ.

Desde la raíz, con el entorno espacial `gee`:

```
conda run -n gee python scripts/validate.py
conda run -n gee python scripts/run_spatial_case.py examples/patache.json
conda run -n gee python scripts/analyze_domain.py
```

Para ejecutar unittest directamente con ese entorno:

```
conda run -n gee env -u PROJ_LIB -u PROJ_DATA python -B -m unittest discover -s tests -v
```

Si se usa otro entorno, instalar `requirements-spatial.txt`.

## Abrir resultados en QGIS

Arrastrar `outputs/patache/pluma_ug_m3.tif` y `fuente.geojson` a QGIS.
El TIFF conserva CRS, tamaño y posición geográfica; no se asigna georreferencia
manualmente. Elegir simbología de pseudocolor para visualizar concentraciones;
la banda está en µg/m³. Este hito genera archivos compatibles, no un plugin
ni una configuración automática de simbología. No se ha validado su apertura
en una sesión de QGIS: se verificó el archivo leyendo su estructura y valores.

## Documentación de APIs consultada

- https://pyproj4.github.io/pyproj/stable/api/transformer.html
- https://pyproj4.github.io/pyproj/stable/api/proj.html
- https://rasterio.readthedocs.io/en/stable/quickstart.html
- https://rasterio.readthedocs.io/en/stable/topics/reproject.html
- https://python-visualization.github.io/folium/latest/user_guide/raster_layers/image_overlay.html

## Visualizaciones alternativas — 2026-09-08

A pedido del usuario se conservan ambas vistas: ráster e isolíneas etiquetadas.
`visualization` elige la vista inicial (`isolines`, `raster`, `both`); el control
de capas permite combinarlas sin ejecutar nuevamente el cálculo. Por defecto
se muestran isolíneas. Se incluye un marcador para el máximo muestreado.

Cambio visual explícito: antes el ráster usaba escala logarítmica inferno;
ahora ambas vistas comparten bandas YlOrRd cuyos cortes coinciden con las isolíneas.
Los niveles se eligen automáticamente con valores legibles inferiores al
máximo, sin añadir el umbral de transparencia como una curva extra.
La leyenda y el máximo se actualizan
por ejecución. Comparar colores entre escenarios exige mirar sus escalas,
pues no son absolutas ni comunes entre ejecuciones.

Las isolíneas se interpolan en la grilla UTM original y sus vértices pasan a
WGS84 como geometrías vectoriales. No se extraen de la imagen coloreada ni de
la vista reproyectada. Sin suavizado ni extrapolación al exterior de los
centros periféricos; las líneas que llegan al borde quedan abiertas. No se
fuerza una curva en el máximo: puede ser un punto. El etiquetado actual se
integra en el trazo y se adapta a la escala, como se describe a continuación.

`outputs/patache/isolineas.geojson` conserva valores numéricos en
`concentration_ug_m3`, para simbolizar y etiquetar en QGIS. El GeoTIFF y el
núcleo físico conservan sus cálculos y unidades. Sin concentraciones superiores
al umbral no se dibujan curvas; la leyenda informa los niveles disponibles.
Se añadieron pruebas con un campo lineal conocido para validar interpolación,
georreferencia y etiquetas, niveles adaptativos y campo nulo.

### Tres regímenes sintéticos de viento — 2026-09-09

`wind_mode` acepta `constant`, `fluctuating`, `prevailing` y `table`. El primero conserva
la pluma estacionaria de una dirección. Los otros dos generan `wind_hours`
direcciones con `wind_random_seed` y promedian una pluma por intervalo. En el
modo predominante, `wind_from_deg` es el centro y `wind_direction_std_deg` su
dispersión angular; en el fluctuante, `wind_from_deg` no participa porque las
direcciones cubren uniformemente 0°–360°.

El informe y el GeoTIFF registran modo, número de muestras y semilla. El mapa
muestra flecha para el viento constante, eje y dispersión para el predominante,
y un símbolo circular sin dirección preferente para el fluctuante. Son
experimentos sintéticos con rapidez y estabilidad constantes, no meteorología
horaria observada.

El modo `table` solicita una tabla manual de observaciones:

```
timestamp_utc,direction_from_deg,wind_speed_m_s
2025-01-01T00:00:00Z,45,3.2
2025-01-01T01:00:00Z,50,4.8
2025-01-01T02:00:00Z,225,2.7
```

La fecha se ingresa en UTC con formato ISO 8601, la dirección en grados
meteorológicos DESDE dentro de [0,360) y la rapidez en m/s mayor que cero. Cada
fila representa un intervalo de igual duración. El programa construye por conteo
la frecuencia conjunta de dirección y velocidad para la rosa de 16 sectores.
Para la concentración agrupa las observaciones en 72 sectores direccionales de
5° y siete clases de velocidad; conserva la suma de frecuencias de cada grupo y
usa su dirección circular media y rapidez armónica. Las calmas aparecen al
centro de la rosa y la dirección variable se anota aparte, ambas como fracción
del total no ausente. Para la concentración se excluyen y se renormalizan las
filas direccionales válidas; el resultado es una media condicional. Por
compatibilidad avanzada también se
acepta una tabla agregada con `frequency_percent` o `weight`.
`examples/synthetic_wind_observations.csv` contiene 1200 registros horarios
docentes: 70 % con tendencia desde 0° y desviación de 40°, 30 % distribuido en
todas las direcciones y rapidez Weibull sintética. Esta mezcla demuestra que el
modo `table` no presupone un régimen. Se reproduce mediante
`scripts/make_synthetic_wind_table.py`; no describe Patache ni otra estación.
Cada ejecución guarda `rosa_vientos.png` separada del mapa de concentraciones.

`examples/synthetic_ne_sw_wind.csv` sirve para una prueba visual más marcada:
92 % de los 1200 registros proviene del noreste (45° ± 6°) y 8 % del suroeste
(225° ± 8°), con rapidez normal sintética de 5.5 ± 1.2 m/s limitada a 1–9.5
m/s. Por la convención DESDE, se espera una pluma principal hacia el suroeste y
una secundaria débil hacia el noreste.

Para una futura fuente DMC/DGAC se conservarán fecha UTC, identificador y altura
de estación, indicadores de calidad, dirección verdadera DESDE y rapidez
convertida a m/s. Los formatos propios de cada agencia deben pasar por un
adaptador hacia este esquema común antes del cálculo.

### Etiquetado integrado en las curvas — 2026-09-09

`gaussian_labels.py` coloca los valores sobre tramos localmente rectos de las
isolíneas visibles, orientados según su tangente y sin texto invertido. Una
máscara SVG interrumpe únicamente el trazo bajo el número: no hay cartel,
recuadro ni fondo rectangular sobre la cartografía. Un halo blanco fino
mantiene el contraste del texto. Las unidades se conservan en la leyenda.

El tamaño varía entre 10 y 13 píxeles CSS con el zoom. Se recalculan posición
y visibilidad al acercar, alejar, desplazar, redimensionar o alternar la capa.
Se omiten etiquetas en curvas demasiado cortas o cerradas y se evitan
superposiciones entre etiquetas; al acercarse pueden aparecer más niveles.
El valor sigue disponible al pasar el cursor por una curva sin etiqueta.
La detección de colisiones cubre las etiquetas entre sí, no los nombres de la
cartografía ni los marcadores. Las geometrías GeoJSON y valores del TIFF no
se alteran; la máscara solo afecta la vista web del prototipo independiente.

Comprobación visual en Chrome con el escenario actual de clase A: etiqueta
alineada en la vista general, niveles interiores al acercar y ocultación al
desactivar la capa. El prototipo independiente importa este renderizador y
permite actualizar una salida guardada anteriormente.

### Selección de concentraciones para las isolíneas — 2026-09-09

La guía oficial de [HYSPLIT, NOAA](https://www.ready.noaa.gov/hysplitusersguide/S330.htm)
admite niveles dinámicos o fijos, intervalos lineales o exponenciales y valores
especificados por el usuario. No establece una única cantidad obligatoria de
curvas. Se toma como referencia esa separación entre cálculo y representación;
la elección siguiente es propia para este cuaderno, no una prescripción NOAA.

La vista automática usa la serie 1–2–5 por década, habitual para representar
varios órdenes de magnitud sin confundir la unidad con el criterio de interés.
El usuario declara `contour_minimum` en la unidad de salida; desde allí se
incluyen 1, 2 y 5 multiplicados por potencias de diez hasta el máximo. También
puede entregar una lista manual. La clave `contour_levels` usa
`auto_125_upper` de forma predeterminada; una lista como `[1, 10, 50, 100]`
activa niveles manuales. El antiguo nombre `auto_125` sigue aceptándose y se
normaliza a la regla actual. `raster_minimum` controla solo transparencia
y no agrega una isolínea. Por ejemplo, con mínimo 1 µg/m³ y máximo 335.3 se
dibujan 1, 2, 5, 10, 20, 50, 100, 200 y 300 µg/m³.

El ráster usa esos mismos niveles como límites de bandas de color YlOrRd. Los
valores comprendidos entre dos isolíneas comparten color y el color cambia al
cruzar la isolínea. La primera banda comienza en `raster_minimum` y la última
termina en el máximo calculado. Por eso la lectura cromática ya no depende de
una interpolación lineal entre cero y el máximo.

Se añade un nivel superior redondeando el máximo hacia abajo a una cifra
significativa. Si coincide exactamente con el máximo, se usa el valor de una
cifra inmediatamente inferior para evitar una curva degenerada. Casos de
prueba: 335→300, 630→600, 800→700, 2030→2000 y 2330→2000. Si ese valor ya
pertenece a la serie 1–2–5, no se duplica.

Estos niveles son de exploración, no límites sanitarios. Una referencia de
salud requiere contaminante, período de promedio, concentración de fondo y
norma aplicable; el caso estacionario actual no basta para declarar cumplimiento.
Para comparar escenarios se deben fijar la misma unidad, mínimos y niveles.

La vista inicial de isolíneas encuadra las curvas principales, la fuente y
el máximo, con margen y zoom máximo 16. Al alejarse se conserva el dominio
completo. Las vistas iniciales ráster/ambas conservan el encuadre del dominio.
El TIFF conserva todos los valores aunque su transparencia sea 0.1. Tampoco cambia el diagnóstico
del borde: omitir una curva no significa ausencia de concentración fuera de
ella. El GeoJSON y el informe usan los mismos niveles que el mapa, registrados
como `automatic_1_2_5_plus_upper`, `contour_levels` y `lowest_contour`. Cuando la salida
es µg/m³ se mantienen además los campos antiguos terminados en `_ug_m3`.

La entrada admite kg/s, g/s, mg/s o µg/s y siempre se convierte a kg/s antes
del núcleo. El GeoTIFF puede escribirse en kg/m³, g/m³, mg/m³ o µg/m³; nombre,
metadatos, leyenda, etiquetas, informe y valores comparten la unidad elegida.
Cambiar solo la unidad conserva la misma pluma y reescala sus números.

Validación: 42 pruebas correctas en `gee`, incluida la serie 1–2–5, niveles
manuales, equivalencia de tasas de emisión y salida de ráster configurable.
No se modificó el núcleo físico.

## Cierre reproducible — 2026-09-10

Se ejecutó el intérprete Python del entorno `gee`:
Python 3.12.0, NumPy 1.26.2, PyProj 3.8.0, Rasterio 1.4.4,
Folium 0.15.0, Matplotlib 3.8.2 y attrs 26.1.0. La restricción
`attrs>=26.1,<27` conserva la familia de versiones comprobada; no pretende
establecer la versión mínima histórica compatible. Rasterio declara attrs
como dependencia. Todos los paquetes instalados satisfacen los rangos de
`requirements-spatial.txt`, incluidos sus archivos referenciados.

`scripts/validate.py`: **60 pruebas, cero errores y cero fallos**. Verificó
las ecuaciones publicadas, el núcleo, las transformaciones espaciales y las salidas.
`validation/summary.json` registra la ejecución reproducible. Los informes detallados
de la instalación local de QGIS se conservan fuera del repositorio público.

Se regeneraron TIFF, fuente e isolíneas GeoJSON, informe JSON y mapa HTML.
La comparación de todos los píxeles con el TIFF previo dio diferencia máxima
**0 µg/m³**; los archivos binarios/HTML pueden cambiar entre entornos por
metadatos o identificadores de Folium sin cambiar la concentración.
Se comprobaron CRS, centros/extensión, orientación, tipo, máscaras, ceros,
unidades, máximo y consistencia del informe; también geometrías y niveles de
GeoJSON y presencia de capas e imagen incrustada en HTML. La inspección
visual del HTML en navegador y la apertura en QGIS siguen pendientes.
Matplotlib usó caché temporal por permisos de su carpeta habitual; las
ejecuciones finalizaron correctamente sin alterar configuración global.

La lista manual está en [qgis-checklist.md](qgis-checklist.md). Este cierre
acredita reproducibilidad y validación automática del hito espacial; la
aceptación dentro de QGIS requiere completar esa lista.

## Análisis del borde y política recomendada antes de la interfaz

Experimento reproducible: `scripts/analyze_domain.py`, resultados en
`validation/domain_sensitivity.json`. Se mantiene Patache, viento, emisión,
clase y resolución; solo se amplían cuadrados centrados. Los centros coinciden
en las zonas superpuestas. No se reemplaza el escenario de 10 × 10 km ni sus
salidas. El máximo muestreado permanece en 221.557028 µg/m³.

| Lado del dominio | Celdas | Máximo del borde (µg/m³) | Borde / máximo |
|---|---:|---:|---:|
| 10 km | 40 000 | 57.279337 | 25.853 % |
| 20 km | 160 000 | 22.471041 | 10.142 % |
| 40 km | 640 000 | 8.516716 | 3.844 % |
| 80 km | 2 560 000 | 3.194801 | 1.442 % |
| 100 km | 4 000 000 | 2.328219 | 1.051 % |

En estos casos el máximo periférico está al sur. El borde se mide en los
centros de la fila/columna periférica, 25 m hacia dentro del límite exterior;
no es una evaluación continua de todo el contorno. El viento transporta la
pluma fuera de la grilla: el corte no indica deposición ni desaparición.
Incluso el límite computacional de 100 km por lado supera el umbral visual
0.1 µg/m³. Estos ensayos son sensibilidad numérica, no evidencia de validez
del modelo plano o de sus ajustes a 50 km de la fuente.

Política propuesta para implementar y probar antes de la interfaz:

1. **Dominio fijo como opción inicial**, conservando dimensiones explícitas.
   Mostrar y guardar siempre el estado de truncamiento, máximos por cada
   borde y razón borde/máximo. No cerrar isolíneas ni convertir el exterior en
   concentración cero. El informe actual ya guarda máximo periférico y bandera
   visual; los diagnósticos por borde están por ahora en el experimento.
2. **Extensión opcional y acotada**, manteniendo resolución y alineación de
   centros. El adaptador QGIS 0.4.0 duplica solo los márgenes cuyos bordes no
   cumplen los criterios y reevalúa los cuatro lados; la grilla asimétrica se
   construye con `make_grid_bounds`. El dominio fijo sigue siendo el valor
   predeterminado y nunca se cambia silenciosamente el paso.
3. **Criterio explícito de contención muestreada**: todos los bordes por debajo
   de un umbral absoluto configurable (0.1 µg/m³ para este caso) y de 1 % del
   máximo. El 1 % es una tolerancia propuesta de diagnóstico, no normativa.
   Separar ese umbral de la simbología; ocultar valores no resuelve el recorte.
   Para un campo nulo, informar «sin pluma» sin dividir por cero. Un borde
   pequeño tampoco garantiza ausencia de máximos fuera del dominio: exigir
   comparar dos extensiones sucesivas, incluyendo máximo y su ubicación,
   antes de declarar contención muestreada. No declarar contención física.
4. **Parada obligatoria** al alcanzar 100 km por lado, 4 millones de celdas o
   el alcance local justificado para el estudio, el que sea más restrictivo.
   Comprobar límites antes de reservar memoria. Si no converge, devolver el
   resultado con «pluma truncada; extensión insuficiente» y el motivo de parada.
   Patache sigue en este estado: la extensión acotada llega a 15 × 85 km y
   1.81358 µg/m³ en el borde antes de la parada. No ampliar sin límite ni
   aumentar el umbral para forzar un resultado satisfactorio.
5. Registrar dominio inicial/final, resolución, umbrales, iteraciones y motivo
   de parada en el informe. Antes de activar extensión automática, ensayar
   vientos oblicuos, campo nulo, límites de recursos, alineación de centros y
   conservación de valores en zonas superpuestas.

## Entrada al MVP de QGIS

Primero completar la lista manual en una versión concreta de QGIS y registrar
sus versiones Python/GDAL/PROJ; el entorno `gee` no acredita compatibilidad
con el Python incluido en QGIS. Después implementar y probar el contrato de
dominio anterior en la capa espacial, conservando el núcleo. El primer corte
del MVP será un adaptador mínimo que lea el escenario, invoque el cálculo y
cargue TIFF/fuente/isolíneas con unidades y simbología explícitas en un proyecto
QGIS. Evaluar las dependencias en ese entorno antes de elegir su distribución.
El adaptador recibirá una de estas dos entradas manuales:

```
WGS84: crs=EPSG:4326, x=longitud, y=latitud
UTM:   crs=EPSG:326xx/327xx, x=Este, y=Norte
```

También podrá tomar un punto elegido en el lienzo y transformarlo desde el CRS
del proyecto a WGS84 antes de llamar a esta misma API. El formulario debe
mostrar siempre el CRS interpretado, la zona/hemisferio y la coordenada
normalizada para que el usuario pueda revisarlos. La selección con clic y el
formulario de parámetros vendrán después.

La comprobación automática inicial se completó el 2026-09-10 con QGIS LTR
3.40.5, Python 3.9.5, NumPy 1.20.1, GDAL 3.3.2 y PROJ 8.1. Las seis
concentraciones de control conservaron un error relativo máximo de
4.59e-16; QGIS y PyProj transformaron Patache a la misma coordenada UTM, y
GDAL escribió y leyó correctamente un ráster float64. El resultado completo
se conserva como evidencia local. La inspección visual fue aceptada por el usuario
en la prueba manual de la versión 0.14.0.
