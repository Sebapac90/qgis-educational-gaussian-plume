# Desde la descarga original de MeteoChile hasta QGIS

Esta guía enseña a transformar manualmente la descarga de viento de MeteoChile
en la tabla que acepta Gaussian Educativo. El estudiante debe conservar siempre
el archivo original y trabajar sobre una copia.

El ejemplo corresponde a Diego Aracena Iquique Ap. (200006). La descarga usada
en este ejercicio tiene estas columnas:

```text
Fecha | Hora (UTC) | dd (°) | ff (kt) | VRB ()
```

## 1. Comprender las columnas originales

- `Fecha`: fecha de la observación.
- `Hora (UTC)`: hora en UTC; no necesita corrección de zona horaria.
- `dd (°)`: dirección meteorológica **DESDE** donde sopla el viento.
- `ff (kt)`: rapidez en nudos.
- `VRB ()`: indica que la dirección fue variable. En esas filas `dd` aparece
  como `.` y no existe una dirección numérica que pueda simularse.

El complemento requiere exactamente:

```text
timestamp_utc,direction_from_deg,wind_speed_m_s
```

Por ello se debe unir fecha y hora, conservar la convención DESDE, convertir
nudos a m/s y aplicar una política explícita a vientos variables y calmas.

## 2. Conservar el original y crear una copia de trabajo

1. Abrir el `.xls` descargado con Excel.
2. Si Excel advierte que la extensión y el formato no coinciden, elegir la
   opción para abrirlo. MeteoChile entrega una tabla HTML con extensión `.xls`.
3. No guardar cambios sobre ese archivo.
4. Elegir **Archivo → Guardar como**.
5. Guardar una copia con formato `.xlsx`, por ejemplo
   `viento_meteochile_trabajo.xlsx`.

Todas las operaciones siguientes se hacen en esa copia.

## 3. Añadir las columnas de preparación

Suponiendo que las columnas originales están en `A:E`, escribir estos
encabezados desde `F1` hasta `I1`:

```text
usar | timestamp_utc | direction_from_deg | wind_speed_m_s
```

### Columna F: decidir qué filas se pueden usar

En `F2` escribir:

```excel
=Y(E2="Falso";C2<>".";VALOR(D2)>0)
```

Esta fórmula devuelve `VERDADERO` solamente cuando existe una dirección
numérica y la rapidez es mayor que cero.

### Columna G: construir la fecha UTC

Si Excel reconoce `Fecha` y `Hora` como fecha y hora, en `G2` escribir:

```excel
=TEXTO(A2+B2;"aaaa-mm-dd""T""hh:mm:ss""Z""")
```

El resultado debe verse así:

```text
2026-09-01T00:00:00Z
```

Si la fórmula anterior produce un error porque la fecha fue leída como texto,
usar:

```excel
=DERECHA(A2;4)&"-"&EXTRAE(A2;4;2)&"-"&IZQUIERDA(A2;2)&"T"&B2&":00Z"
```

### Columna H: preparar la dirección

En `H2` escribir:

```excel
=SI(F2;RESIDUO(VALOR(C2);360);"")
```

Esto conserva la dirección DESDE y transforma `360°` en `0°`, que representan
el mismo norte.

### Columna I: convertir nudos a metros por segundo

La conversión es:

```text
1 kt = 0,514444 m/s
```

En `I2` escribir:

```excel
=SI(F2;SUSTITUIR(TEXTO(VALOR(D2)*0,514444;"0,000000");",";".");"")
```

`SUSTITUIR` fuerza el punto decimal que necesita el CSV, aunque Excel use coma
decimal en pantalla.

## 4. Aplicar las fórmulas a toda la tabla

1. Seleccionar `F2:I2`.
2. Hacer doble clic en el pequeño cuadrado de la esquina inferior derecha de la
   selección, o arrastrarlo hasta la última observación.
3. Revisar algunas filas al inicio, al centro y al final.
4. Confirmar que las filas `VRB = Verdadero` y las velocidades iguales a cero
   muestran `FALSO` en la columna `usar`.

En el archivo de ejemplo deben existir:

- 507 observaciones originales;
- 22 direcciones variables;
- 7 calmas;
- 478 observaciones utilizables.

Si el resultado no es 478, revisar las fórmulas antes de continuar.

## 5. Crear la hoja final

1. Activar **Datos → Filtro**.
2. En la columna `usar`, mostrar solamente `VERDADERO`.
3. Crear una hoja nueva y llamarla `CSV_QGIS`.
4. En `A1:C1` escribir exactamente:

```text
timestamp_utc | direction_from_deg | wind_speed_m_s
```

5. En la hoja de trabajo, copiar solamente las celdas visibles de las columnas
   `G:I`, sin incluir sus encabezados.
6. En `CSV_QGIS`, usar **Pegado especial → Valores** desde `A2`.
7. Confirmar que existan 478 filas de datos más la fila de encabezados.

No copiar la columna `usar` ni las cinco columnas originales a la hoja final.

## 6. Guardar el CSV

1. Dejar activa la hoja `CSV_QGIS`.
2. Elegir **Archivo → Guardar como**.
3. Seleccionar **CSV UTF-8 (delimitado por comas) (.csv)**.
4. Usar un nombre descriptivo, por ejemplo
   `DMC_200006_2026-09_viento_qgis.csv`.
5. Aceptar el aviso de que solo se guardará la hoja activa.

Abrir el CSV en VS Code y revisar la primera línea. Debe ser exactamente:

```csv
timestamp_utc,direction_from_deg,wind_speed_m_s
```

Una fila debe verse así:

```csv
2026-09-01T00:00:00Z,200,7.202216
```

Si Excel guardó las columnas con punto y coma, usar **Buscar y reemplazar** en
VS Code para reemplazar `;` por `,`. Como la rapidez ya fue convertida a texto
con punto decimal, este reemplazo no altera los números.

## 7. Cargar el CSV en Gaussian Educativo

1. Abrir QGIS y el panel **Pluma Gaussiana Educativa**.
2. Ubicar la fuente. Para Diego Aracena usar longitud `-70.181110`, latitud
   `-20.549166` en EPSG:4326 y pulsar **Usar centro**.
3. En **Viento → Modo**, seleccionar **Tabla CSV de observaciones**.
4. Pulsar **CSV…** y elegir el archivo creado por el estudiante.
5. Es normal que rapidez y dirección manuales queden desactivadas.
6. Para la primera prueba usar dominio fijo de 10 000 × 10 000 m y resolución
   de 100 m.
7. Completar emisión, altura de la chimenea, estabilidad y unidad de concentración.
   En este modo básico el complemento supone ascenso de pluma cero, de modo que
   la altura efectiva usada por la ecuación es igual a la altura ingresada.
8. Pulsar **Ejecutar y cargar capas**.

El complemento calculará las frecuencias desde las filas horarias, generará la
rosa de vientos y agrupará los datos para el cálculo espacial.

## 8. Criterios que deben quedar registrados

- La hora original ya estaba en UTC.
- La dirección es meteorológica DESDE.
- La velocidad se convirtió de nudos a m/s multiplicando por `0,514444`.
- Los registros `VRB` se excluyeron porque no contienen dirección numérica.
- Las calmas se excluyeron porque el núcleo estacionario requiere rapidez
  positiva.
- No se reemplazaron datos ausentes por cero ni por una dirección inventada.

El CSV preparado por el proyecto puede usarse como respuesta de control después
de que el estudiante complete el procedimiento, no como sustituto del ejercicio.
