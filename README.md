# Pluma Gaussiana Educativa para QGIS

Complemento docente para explorar una pluma gaussiana estacionaria sobre terreno plano. El modelo físico sigue a Masters y Ela (2008), capítulo 7: clases de estabilidad A–F, coeficientes de dispersión de Martin (1976), reflexión perfecta en el suelo y corrección de la rapidez del viento por altura.

No es un modelo regulatorio. No representa terreno, edificios, deposición, química, variación vertical de la dirección ni ascenso de pluma.

## Instalación en QGIS

El paquete experimental actual es `dist/gaussian_educativo-0.14.0.zip`.

1. Abrir QGIS.
2. Ir a **Complementos → Administrar e instalar complementos…**.
3. Elegir **Instalar a partir de ZIP**.
4. Seleccionar el ZIP y aceptar la advertencia de complemento experimental.
5. Abrir **Ver → Paneles → Pluma Gaussiana Educativa**.

La versión 0.14.0 usa un único modelo físico. Los escenarios guardados con los esquemas 1 y 2 se pueden abrir; los campos adicionales de versiones previas se ignoran y el cálculo se ejecuta con Masters.

## Uso básico

El panel permite:

- elegir la fuente en cualquier parte del mundo en WGS84 o desde el lienzo de QGIS;
- convertir automáticamente a UTM/UPS para calcular en metros;
- ingresar emisión en kg/s, g/s, mg/s o µg/s;
- escoger estabilidad A–F, altura de chimenea y altura de medición del viento;
- usar viento constante, predominante sintético, aleatorio uniforme sintético o una tabla CSV;
- generar GeoTIFF, isolíneas GeoPackage, fuente puntual y rosa de vientos;
- guardar y recuperar el escenario en JSON.

La tabla normalizada de observaciones tiene tres columnas:

```csv
timestamp_utc,direction_from_deg,wind_speed_m_s
2026-09-01T00:00:00Z,45,4.2
```

Cada fila representa un intervalo de igual duración. La dirección es meteorológica **DESDE**, en grados horarios desde norte verdadero, y la rapidez está en m/s. El asistente puede asignar columnas, interpretar fechas, convertir km/h o nudos, convertir direcciones HACIA y excluir códigos declarados de calma, variable o ausente sin modificar el archivo original.

La rosa usa 16 sectores. El cálculo agrupa las observaciones en 72 sectores de 5° y siete clases de rapidez, conserva sus frecuencias y promedia las concentraciones ponderadas. Esta reducción fue aceptada para el MVP docente; no implica equivalencia regulatoria.

## Núcleo y archivos

- `gaussian_core.py`: ecuación y parametrizaciones físicas, independiente de QGIS.
- `gaussian_spatial.py`: CRS, marco de la pluma y grilla.
- `gaussian_wind.py`: series, agrupación, promedio y rosa de vientos.
- `gaussian_raster.py`, `gaussian_contours.py`, `gaussian_map.py`: salidas espaciales.
- `qgis_plugin/gaussian_educativo/`: complemento QGIS.
- `notebooks/01_explorar_nucleo.ipynb`: introducción al modelo.
- `notebooks/02_pluma_sobre_mapa.ipynb`: escenario espacial interactivo.
- `examples/patache.json`: caso docente reproducible.
- `docs/model.md`: ecuaciones, unidades y decisiones físicas.
- `docs/spatial.md`: decisiones espaciales y política de dominio.
- `docs/qgis-checklist.md`: lista de validación manual.

Las unidades internas son kg/s, m/s, m y kg/m³. Las conversiones de masa se realizan de forma explícita en la capa de entrada y salida.

## Entorno de desarrollo

Abrir `Gaussian.code-workspace` y seleccionar el kernel `gee`:

el intérprete Python del entorno `gee`

Validación completa sin modificar variables globales de PROJ:

```bash
conda run -n gee env -u PROJ_LIB -u PROJ_DATA \
  PYTHONDONTWRITEBYTECODE=1 python scripts/validate.py
```

Reproducir Patache:

```bash
conda run -n gee env -u PROJ_LIB -u PROJ_DATA \
  PYTHONDONTWRITEBYTECODE=1 python scripts/run_spatial_case.py examples/patache.json
```

El caso genera en `outputs/patache/`:

- `pluma_ug_m3.tif`;
- `isolineas.geojson` y `fuente.geojson`;
- `caso_y_resultados.json`;
- `mapa_pluma.html`;
- `rosa_vientos.png`.

Validación del 22 de septiembre de 2026: **60 pruebas correctas** con Python 3.12.0 en `gee`. El algoritmo real y el panel pasaron además bajo QGIS 3.44.14 LTR en macOS, y el usuario confirmó el funcionamiento del ZIP 0.14.0 en una prueba manual.

Para Patache, con dominio 10 × 10 km, resolución 50 m, clase D, emisión 40 g/s, viento observado de 5 m/s a 10 m y chimenea de 50 m, el máximo es 221,557 µg/m³ y el máximo del borde 57,279 µg/m³. La pluma alcanza el borde; el resultado debe declararse truncado o repetirse con la política de extensión.

## Licencia

Código distribuido bajo GNU GPL versión 2 o posterior. Véase `LICENSE`.
