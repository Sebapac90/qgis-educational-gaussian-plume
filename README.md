# Pluma Gaussiana Educativa para QGIS

Complemento experimental y bilingüe para enseñar la dispersión atmosférica con una pluma gaussiana estacionaria sobre terreno plano. La implementación física sigue a Masters y Ela (2008), capítulo 7, y utiliza las ecuaciones de dispersión de Martin (1976).

El complemento es una herramienta docente. **No es un modelo regulatorio** y no representa terreno, edificios, deposición, química atmosférica, variación vertical de la dirección del viento ni elevación gradual de la pluma.

## Descarga e instalación

Descargue el archivo `gaussian_educativo-0.14.0.zip` desde la sección [Releases](https://github.com/Sebapac90/qgis-educational-gaussian-plume/releases). No descomprima el archivo.

1. Abra QGIS.
2. Vaya a **Complementos → Administrar e instalar complementos…**.
3. Seleccione **Instalar a partir de ZIP**.
4. Elija el archivo descargado y acepte la advertencia de complemento experimental.
5. Abra **Ver → Paneles → Pluma Gaussiana Educativa**.

El complemento no requiere Jupyter ni un entorno Conda. En las versiones de QGIS verificadas utiliza Python, PyQGIS, GDAL, NumPy, PyProj y Matplotlib incluidos con QGIS.

## Funciones principales

- selección de una fuente desde el lienzo o mediante coordenadas;
- coordenadas de entrada en WGS 84 o en el CRS del proyecto;
- conversión automática a UTM/UPS para calcular distancias en metros;
- emisión en kg/s, g/s, mg/s o µg/s;
- clases de estabilidad atmosférica A–F;
- corrección de la rapidez del viento desde su altura de medición hasta la altura de la chimenea;
- viento constante, predominante sintético, aleatorio uniforme sintético o tabla de observaciones;
- dominio fijo o extensión automática controlada para viento constante;
- isolíneas automáticas 1–2–5 o niveles definidos por el usuario;
- interfaz en español e inglés;
- guardado y recuperación de escenarios JSON.

## Tabla de viento

El asistente de importación permite seleccionar las columnas y declarar el formato de fecha, las unidades, el sentido de la dirección y los códigos usados para calma, dirección variable o datos ausentes. El archivo original no se modifica.

El formato interno normalizado es:

```csv
timestamp_utc,direction_from_deg,wind_speed_m_s
2026-09-01T00:00:00Z,45,4.2
```

Cada fila representa un intervalo de igual duración. La dirección es meteorológica **DESDE**, medida en grados horarios desde el norte verdadero, y la rapidez está en m/s. La rosa muestra 16 sectores; el cálculo agrupa las observaciones en 72 sectores de 5° y siete clases de rapidez antes de promediar las concentraciones ponderadas.

## Resultados

Cada ejecución puede producir:

- concentración como GeoTIFF georreferenciado;
- isolíneas y fuente puntual como capas vectoriales;
- rosa de vientos en PNG;
- escenario y resumen de resultados en JSON;
- capas agrupadas, etiquetadas y simbolizadas en el proyecto QGIS.

La política predeterminada conserva el dominio solicitado y advierte si la pluma alcanza su borde. La extensión automática está limitada por tamaño y costo computacional; reducir la concentración periférica no demuestra contención física completa.

## Modelo y unidades

El modelo usa reflexión perfecta en el suelo. La altura puede tratarse sin elevación, ingresarse como altura efectiva manual o calcularse como elevación final con Briggs. Las unidades internas son kg/s, m/s, m y kg/m³; las conversiones de entrada y salida son explícitas.

La comparación de los componentes compartidos con el cuaderno Manchester y sus
límites está documentada en [docs/manchester-correspondence.md](docs/manchester-correspondence.md).

La formulación, los supuestos y las decisiones están documentados en [docs/model.md](docs/model.md). La política espacial se describe en [docs/spatial.md](docs/spatial.md).

## Fundamento e inspiración

La formulación física adoptada corresponde al modelo gaussiano clásico presentado por Masters y Ela (2008), capítulo 7. De esa fuente proceden la ecuación de concentración, la corrección de la rapidez del viento por altura y las ecuaciones de Martin (1976) para los coeficientes de dispersión.

La idea de crear una herramienta docente interactiva se inspiró en *Gaussian plume model practical*, desarrollado por Paul J. Connolly en la Universidad de Manchester. Ese antecedente utiliza experimentos sintéticos para enseñar el efecto de la estabilidad y del viento. La implementación publicada aquí fue desarrollada específicamente como complemento QGIS, con entradas geográficas, resultados georreferenciados e importación de observaciones meteorológicas.

### Referencias

- Masters, G. M. y Ela, W. P. (2008). *Introduction to Environmental Engineering and Science* (3.ª ed., capítulo 7). Prentice Hall. ISBN 978-0-13-148193-0. [Ficha editorial de Pearson](https://www.pearson.com/en-us/subject-catalog/p/introduction-to-environmental-engineering-and-science/P200000003392).
- Connolly, P. J. (2017). *Gaussian plume model practical* [software docente]. University of Manchester. [Repositorio consultado, commit `7aaadea`](https://github.com/EnvModelling/gaussian-plume-model-practical/tree/7aaadeae4f7217ec658c20ff70939066ffd2da83).

## Código fuente

El repositorio se concentra en el complemento QGIS y su implementación en Python:

- `qgis_plugin/gaussian_educativo/`: paquete instalable del complemento;
- `docs/`: fundamento físico y documentación técnica;
- `examples/`: escenarios y tablas sintéticas redistribuibles;
- `tests/`: pruebas del núcleo numérico y espacial;
- `scripts/`: construcción del ZIP y comprobaciones reproducibles;
- `validation/`: evidencia compacta de las pruebas aceptadas.

El núcleo físico permanece independiente de la interfaz QGIS para que sus ecuaciones puedan probarse directamente. Los datos meteorológicos originales se conservan fuera de la publicación.

## Licencia

Copyright © 2026 Sebastián Pacheco Mercado.

Código distribuido bajo GNU GPL versión 2 o posterior
(`SPDX-License-Identifier: GPL-2.0-or-later`). Véase [LICENSE](LICENSE).
