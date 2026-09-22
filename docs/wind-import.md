# Importación manual de viento

## Criterio de entrada

La rosa representa exactamente el periodo incluido por el usuario. No se exige
un mínimo temporal: seis horas, un día y un mes son periodos válidos y distintos.
El informe debe mostrar el inicio, término, cantidad de observaciones e intervalo
predominante para que esa cobertura sea explícita.

El CSV conserva una primera fila de encabezados. El usuario selecciona en el
formulario de QGIS qué columna contiene fecha, dirección y velocidad, junto
con la unidad de velocidad, zona horaria y formato de fecha. No se descarta la
primera fila a ciegas; se usa para identificar las columnas.

`gaussian_wind_import.py` implementa la normalización independiente de QGIS:

- fechas con zona explícita o una zona IANA seleccionada por el usuario;
- formatos ISO 8601 o un formato de fecha indicado;
- dirección meteorológica `DESDE` o conversión desde `HACIA`;
- velocidad en m/s, km/h o nudos;
- delimitadores coma, punto y coma o tabulador;
- punto o coma decimal cuando el separador de columnas no es la coma;
- validación de columnas, rangos, duplicados y valores no numéricos.

El resultado canónico conserva las tres variables físicas y cuatro recuentos
de procedencia repetidos en cada fila válida:

```csv
timestamp_utc,direction_from_deg,wind_speed_m_s,source_total_rows,excluded_calm_rows,excluded_variable_rows,excluded_missing_rows
```

Los cuatro campos finales son metadatos internos creados por el asistente; el
estudiante no tiene que agregarlos a su archivo original. Permiten reconstruir
la frecuencia completa sin guardar un archivo auxiliar.

## Prueba con fuentes reales

Se prepararon localmente tres periodos para cada fuente: seis horas,
un día y un mes. Cada caso conserva un archivo `*_source.csv`, el archivo
`*_ready.csv` normalizado y la rosa `*_rose.png`.

### DMC / DGAC Chile

- Estación: Teniente Vidal, Coyhaique Ad., código 450004.
- Periodo mensual: agosto de 2026.
- Fuente pública: `graficosRecienteEma`, una vista por día.
- Datos originales: hora local, dirección meteorológica en grados y velocidad
  presentada por el gráfico en km/h.
- Resolución de origen: un minuto; para la prueba se tomaron los registros de cada
  cuarto de hora.
- Conversión: `America/Santiago` a UTC y km/h dividido por 3,6.

La Dirección Meteorológica de Chile indica que los datos publicados en su portal
son de acceso público y solicita citar a la institución. La documentación actual
del servicio histórico por API requiere usuario y token; esta prueba usa la vista
pública diaria y no guarda credenciales.

Fuente: <https://climatologia.meteochile.gob.cl/application/diariob/graficosRecienteEma/450004/2026/08/01>

### NOAA Global Hourly

- Estación: JFK International Airport, Nueva York, código 74486094789.
- Periodo mensual: enero de 2025.
- Fuente: archivo CSV anual de Global Hourly.
- Se seleccionaron reportes horarios FM-15.
- El campo `WND` se decodificó como dirección en grados y velocidad en décimas de
  m/s; las fechas ya están en UTC.

Fuente: <https://www.ncei.noaa.gov/data/global-hourly/access/2025/74486094789.csv>

## Resultados

| Fuente | Periodo | Filas válidas | Intervalo predominante |
|---|---:|---:|---:|
| DMC/DGAC | 6 horas | 24 | 15 minutos |
| DMC/DGAC | 1 día | 96 | 15 minutos |
| DMC/DGAC | agosto 2026 | 2954 | 15 minutos |
| NOAA | 6 horas | 6 | 1 hora |
| NOAA | 1 día | 24 | 1 hora |
| NOAA | enero 2025 | 723 | 1 hora |

Las seis tablas fueron leídas por `gaussian_wind.py`, produjeron su rosa y
completaron un cálculo de concentración sobre una grilla de prueba de 2 × 2 km a
100 m. El registro reproducible está en
`validation/real_wind_import_trials.json`.

Los registros con rapidez igual a cero no se envían al núcleo gaussiano
estacionario, que requiere velocidad positiva. En la rosa se muestran como
porcentaje de calma en el centro. Las direcciones variables se muestran como
porcentaje aparte y los ausentes se informan, pero no forman parte del
denominador meteorológico.

### Ejemplos en formato de origen

El directorio local de pruebas contiene también seis versiones anteriores
a la normalización. Para DMC/DGAC son extractos de las series de los gráficos
HTML: el portal no entrega esos ejemplos como CSV. Conservan sus etiquetas
visibles `Hora del día (local)`, `Dirección del Viento en °` e `Intensidad del
Viento en Kph`. La fecha completa y la estación provienen del contexto de cada
página diaria.

Las versiones NOAA conservan literalmente las 98 columnas del CSV Global
Hourly para las observaciones seleccionadas. El viento permanece en `WND`:
dirección en grados, código de calidad de dirección, tipo, velocidad en décimas
de m/s y código de calidad de velocidad. Estos archivos permiten ensayar el
mapeo de columnas y decodificación. Desde 0.12.0, el panel convierte un CSV
simple de tres columnas al formato canónico; la decodificación automática del
campo compuesto NOAA `WND` continúa fuera de alcance.

### Extracción directa de la estación 200006

En el archivo local de pruebas se conserva una descarga
directa del producto público **Hoja Mensual de Datos** para Diego Aracena Iquique
Ap. (200006), agosto de 2026. El archivo `.xls` es el fragmento HTML original
entregado por el portal y contiene las 744 observaciones horarias con todos sus
elementos.

Los tres CSV de 6 horas, 1 día y 1 mes seleccionan `Dia`, `Hora` y las dos
subcolumnas de `Viento ( ° - kt.)`: `DD Inst` y `FF Inst`. Conservan las dos
filas de encabezado de la fuente y no filtran valores. El producto no declara la
zona horaria en la tabla ni en la descarga; por ello estos ejemplos no deben
normalizarse a UTC sin que el usuario confirme esa información. La dirección
vacía se conserva como dato faltante y no debe interpretarse como cero grados.

Fuente: <https://climatologia.meteochile.gob.cl/application/mensualb/hojaMensualDatos/200006/2026/8>

## Decisión para la interfaz

El formulario de importación muestra una vista previa antes de ejecutar y
permite elegir:

1. columna y formato de fecha;
2. zona horaria cuando la fecha no incluya desplazamiento UTC;
3. columna y convención de dirección;
4. columna y unidad de velocidad.

Después de convertir, debe mostrar periodo UTC, filas válidas, intervalo
predominante e irregularidades. La simulación sólo recibe el archivo canónico;
las conversiones no se incorporan a `gaussian_core.py`.

### Diseño acordado para la entrada docente

El estudiante entrega preferentemente un CSV limpio con tres columnas: fecha y
hora, dirección y rapidez. Los nombres pueden variar porque el panel permite
asignar el significado de cada columna. Para el MVP se prioriza CSV sobre Excel:
`.xlsx`, `.xls` binario y HTML con extensión `.xls` requieren lectores distintos
y no están disponibles de forma uniforme en QGIS para macOS y Windows.

Antes de convertir, el panel muestra una vista previa y solicita:

1. columna de fecha y hora;
2. formato de fecha entre opciones frecuentes, con opción personalizada;
3. zona horaria, salvo que cada fecha ya incluya `Z` o desplazamiento;
4. columna de dirección, representación en grados o rumbos cardinales y
   convención meteorológica DESDE/HACIA;
5. columna de rapidez y unidad `m/s`, `km/h` o nudos;
6. códigos opcionales de calma, dirección variable y dato ausente.

La periodicidad diaria, horaria o subhoraria se infiere después de leer las
fechas; no se usa como sustituto del formato. El resumen informa intervalo
predominante e irregularidades.

Los códigos especiales no son universales. En la descarga DMC 200006 de
septiembre de 2026, `dd=.` junto con `VRB=Verdadero` indica dirección variable,
mientras que la calma aparece como `dd=0` y `ff=0.0`. Un guion no debe asumirse
como calma: puede significar dato ausente. El panel propone velocidad cero como
regla de calma y permite añadir códigos declarados por el usuario. Para dirección
variable acepta tokens declarados, por ejemplo `VRB` o `.`, y la excluye del
cálculo direccional con recuento explícito.

La validación previa debe separar: filas válidas, calmas, variables, ausentes y
erróneas. El informe indica que la concentración calculada es condicional a las
observaciones direccionales con rapidez positiva; no debe ocultar la exclusión ni
renormalizarla conceptualmente como si las calmas y variables no hubieran
ocurrido.

### Denominadores implementados

Sea `N` el total leído, `M` las filas ausentes, `C` las calmas, `V` las
variables y `D = N - M - C - V` las observaciones direccionales válidas. La
rosa usa `N - M`: sus pétalos suman `100 D/(N-M)`, el centro muestra
`100 C/(N-M)` y la anotación variable muestra `100 V/(N-M)`. Así las tres
fracciones suman 100 %. Para calcular concentración, únicamente las `D` filas
reciben pesos iguales cuya suma es uno. Por ello el resultado representa la
concentración media condicionada a viento direccional positivo y no una media
temporal que asigne concentración cero a calma o dirección variable.


Los extractos meteorológicos reales no se redistribuyen en el repositorio. Los scripts permiten reconstruir las pruebas a partir de archivos obtenidos legítimamente por cada usuario.
