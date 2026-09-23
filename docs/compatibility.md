# Compatibilidad e idiomas · 0.14.0 · 2026-09-23

| Sistema / versión | Estado |
|---|---|
| macOS Intel · QGIS 3.40.5 · Qt5 | Probado con el ZIP: cálculo, CSV, extensión, cancelación e idiomas |
| macOS Apple Silicon · QGIS 3.44.14 LTR · Qt5 | Batería automática nativa y prueba funcional del usuario aprobadas con el ZIP 0.14.0 |
| macOS Intel/Rosetta · QGIS 3.44.14 LTR · Qt5 | Batería automática aprobada con el ZIP 0.9.1 |
| Windows 10 · QGIS 3.44 LTR | Prueba funcional manual del usuario aprobada con el ZIP 0.14.0 |
| QGIS 4 · Qt6 | Pendiente de adaptación y pruebas; metadata limita la serie a 3.x |

La versión 0.10.0 añade al panel los modos predominante y aleatorio uniforme
con los parámetros sintéticos reproducibles del notebook. El ZIP pasó panel,
idiomas, Procesos y ejecución/cancelación en QGIS 3.40.5 y 3.44.14 para Mac.
El modo predominante conserva la dirección central; el aleatorio desactiva e
ignora esa entrada. Los resultados físicos constantes y CSV permanecen iguales.
La corrección 0.10.1 impide iniciar promedios mayores que 50 millones de
celda-direcciones, actualiza el progreso durante el promedio y consulta la
cancelación entre direcciones. El caso detectado de 10 km, 10 m y 1200 vientos
se rechaza de inmediato y recomienda 50 m.

La corrección 0.10.2 cubre el caso en que la grilla inicial cumple ese límite
pero la extensión automática no. Se exporta la grilla ya calculada y se registra
`computational_limit_reached_truncated`, sin terminar la tarea con error.

La versión 0.10.5 conserva 16 sectores para la rosa y agrupa el cálculo en
72 sectores direccionales de 5° y siete clases de velocidad. El límite de
50 millones cuenta desde esta versión las clases ocupadas, no las filas de
entrada. Las observaciones y frecuencias originales se conservan para la rosa
y los metadatos.

La versión 0.14.0 consolida Masters 2008 como formulación única, junto con la altura
de medición del viento y la exposición rugosa o plana. La batería automática
pasó con el Python de QGIS LTR en macOS y verificó también el NoData próximo a
la fuente. El usuario instaló y probó funcionalmente el ZIP 0.14.0 en macOS y
en Windows 10 con QGIS 3.44 LTR. En ambos sistemas confirmó el cálculo, las
salidas georreferenciadas, la simbología y la reapertura del proyecto. QGIS 4
continúa pendiente de adaptación y prueba real.

La versión 0.12.0 integra el asistente de CSV de tres columnas y su prueba
automática dentro del panel QGIS. Usa solamente la biblioteca estándar de
Python y no añade dependencias al complemento.

La corrección 0.12.1 añade el formato `DD-MM-AAAA HH:MM:SS` al selector.

La corrección 0.12.2 reconoce por defecto `VRB` y `.` como códigos declarados
de dirección variable en tablas DGAC de tres columnas.

La versión 0.14.0 conserva en el CSV normalizado los recuentos de filas válidas,
calmas, variables y ausentes. La rosa usa como denominador las observaciones
meteorológicas no ausentes: muestra la calma al centro, el porcentaje variable
por separado y deja que la suma de los pétalos sea la fracción direccional. El
cálculo gaussiano conserva pesos condicionales que suman uno únicamente entre
las observaciones direccionales de rapidez positiva.

La [página oficial de descarga](https://qgis.org/download/) consultada el
2026-09-13 ofrece 3.44.14 como LTR y 4.2.2 como versión regular. Una versión
reciente no es necesariamente la LTR. La guía de
[migración QGIS 4](https://plugins.qgis.org/docs/migrate-qgis4) describe el
cambio a Qt6; cambiar metadata no demuestra compatibilidad.

## Dependencias

El complemento usa QGIS/PyQt, GDAL, NumPy y PyProj para calcular, y Matplotlib
para la rosa PNG. No necesita `gee`, Jupyter, Folium, Rasterio ni attrs en el
flujo QGIS. Las herramientas espaciales independientes de desarrollo usan
`requirements-spatial.txt`; ese archivo no debe instalarse indiscriminadamente
en el Python de QGIS.

En QGIS 3.40.5 y 3.44.14 para Mac estas bibliotecas ya estaban disponibles y no
se instaló ningún paquete. En 3.44.14 nativo se comprobaron Python 3.12.11,
NumPy 2.5.2, GDAL 3.13.3, PROJ 9.8, PyProj 3.7.2 y Matplotlib 3.11.1. En
Windows 10, la instalación estándar de QGIS 3.44 LTR utilizada por el usuario
ejecutó el complemento sin instalar paquetes adicionales. Esto no garantiza
su presencia en otros distribuidores o instalaciones personalizadas de QGIS.

Comprobación sin instalar ni cambiar nada, desde la consola Python de QGIS:

```python
import runpy
check = runpy.run_path(r"C:/ruta/al/proyecto/scripts/check_qgis_installation.py")
result = check["report"]()
```

En Mac usar una ruta absoluta `/Users/.../scripts/check_qgis_installation.py`.
El informe registra sistema, arquitectura, QGIS, Python, Qt y bibliotecas.
No certifica el funcionamiento del plugin: después deben ejecutarse los casos.
La evidencia local está en `validation/qgis_installation_dependencies.json`.
Si falta una biblioteca, registrar el instalador y el error antes de decidir
un adaptador o una dependencia adicional; no mezclar Python de Anaconda con QGIS.

## Idiomas

`qgis_plugin/gaussian_educativo/i18n.py` selecciona el idioma configurado en
QGIS. El catálogo `i18n/en.json` traduce 139 textos propios desde español.
Se conserva español para locales `es_*` e inglés para el resto. El panel,
Procesos, ayuda, nombres de capas y mensajes propios están traducidos. Los
errores emitidos directamente por bibliotecas conservan el texto de origen;
los códigos técnicos de estado del dominio permanecen comunes a los idiomas.
La rosa usa los mismos sectores y frecuencias; solo cambian título, leyenda y
abreviaturas de oeste. No se traducen CSV, campos, unidades, claves ni IDs.

Después de cambiar el idioma de QGIS, reiniciar la aplicación o recargar el
complemento. Las capas ya guardadas conservan sus nombres hasta volver a
generarlas. Los escenarios JSON se leen y escriben explícitamente en UTF-8.

`scripts/test_qgis_languages.py` pasó con es_CL, en_US y fr_FR simulado desde
los ajustes de idioma, comprobando controles, Procesos, placeholders,
recuperación del mismo escenario y descarga limpia. Capturas en
`validation/panel_{es,en}_090.png`; informe `validation/qgis_languages.json`.

Además, `validation/qgis_scenario_dialogs_090.json` registra un ensayo en QGIS
real con selectores Qt sin mocks: guardar, cancelar, abrir, recargar en inglés
y ejecutar dos veces. Todas las entradas y píxeles coincidieron. El proyecto
con ambas corridas pasó su reapertura, según
`validation/qgis_dialog_project_reopen_090.json`. Esto no sustituye la revisión
humana de usabilidad ni comprueba los selectores nativos de macOS.

## Aceptación en QGIS 3.44 LTR

1. Usar un perfil limpio e instalar el ZIP 0.14.0, sin paquetes adicionales.
2. Ejecutar la comprobación de dependencias y registrar el instalador exacto.
3. Repetir Patache con fuente WGS84 y UTM; máximo 221.557028 µg/m³ y borde
   57.279337 µg/m³, tolerancia 0.001. Verificar zoom sobre mapa WGS84 y UTM.
4. Probar CSV NE–SO con 100 g/s y estabilidad A: 1200 observaciones, máximo
   754.544532 µg/m³ y borde 0.140910 µg/m³. Abrir la rosa y revisar orientación.
5. Cancelar una corrida, guardar/abrir/trasladar un escenario con CSV y comprobar
   que una segunda ejecución no sobrescribe la primera.
6. Cambiar QGIS a inglés, reiniciar y repetir controles y recuperación; volver
   a español y comprobar títulos y mensajes.
7. Reabrir el proyecto: capas, CRS, etiquetas, SVG y simbología conservados.
8. Repetir con los complementos habituales y registrar incidencias.

La batería automatizada de estos recorridos pasó en Mac 3.44.14 para arm64 y
x86_64/Rosetta. Sus informes están en `validation/qgis_344_arm64_091/` y
`validation/qgis_344_091/`; el control equivalente de 3.40 está en
`validation/qgis_340_091/`. La corrección 0.9.1 prepara CRS/PyProj en el hilo
principal antes de iniciar la tarea: evita el fallo reproducido dentro de PROJ
en un trabajador Qt sin cambiar el cálculo. El usuario completó además el
recorrido funcional con el ZIP 0.14.0 en Windows 10 y QGIS 3.44 LTR el
2026-09-23. El paquete permanece experimental por su alcance docente y porque
QGIS 4/Qt6 aún no está soportado.
