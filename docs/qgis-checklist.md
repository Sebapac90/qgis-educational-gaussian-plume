# Validación manual del hito espacial en QGIS

Estado: **versión 0.14.0 aceptada en pruebas funcionales del usuario en macOS
(2026-09-22) y Windows 10 con QGIS 3.44 LTR (2026-09-23)**. No marcar una casilla solo porque
las pruebas Python pasan. Usar `outputs/patache/` recién generado y registrar
fecha, responsable, sistema operativo, versiones QGIS/Python/GDAL/PROJ,
resultado de cada comprobación y capturas o incidencias.

Actualización 2026-09-13: 0.8.1 pasó las pruebas automáticas del panel, tareas,
CSV, dominio y reapertura de cuatro proyectos. En una instancia real se probó
arranque normal con complementos incluidos, selección por clic de Qt y zoom
WGS84. Evidencia en `validation/qgis_clean_startup.*` y registro detallado en
`qgis-development.md`. Los selectores de archivos se simularon en pruebas;
esto no sustituye la aceptación humana de los diálogos ni demuestra convivencia
con los complementos adicionales del perfil habitual. Las casillas manuales
pendientes se conservan hasta comprobar sus recorridos completos.

Ensayo adicional 0.9.0: se probaron selectores Qt reales para guardar, cancelar
y abrir; se recargó el complemento en inglés y se repitió el escenario con
todos los píxeles idénticos y otra carpeta. El proyecto de ambas corridas
reabrió con seis capas y estilos válidos. Informes
`validation/qgis_scenario_dialogs_090.json` y
`validation/qgis_dialog_project_reopen_090.json`. Sigue pendiente la revisión
humana y los selectores nativos; no se marcan recorridos manuales completos
a partir de este ensayo automatizado.

Ensayo 0.9.1: la batería automática pasó en QGIS 3.40.5 y 3.44.14, esta última
en arm64 nativo y x86_64/Rosetta. Incluyó el caso fijo, extensión, viento CSV,
rosa PNG, idiomas, ejecución/cancelación desde el panel y reapertura. La lista
manual continúa abierta para los selectores nativos y la apreciación visual.

Ensayo 0.10.0: el selector del panel contiene constante, predominante sintético,
aleatorio uniforme sintético y CSV. Comprobar manualmente que la dirección esté
activa en constante/predominante, desactivada en aleatorio, y que CSV use las
direcciones de la tabla. Los modos sintéticos deben informar 1200 intervalos.

Ensayo 0.14.0: el panel aplica Masters 2008 / Martin 1976 como formulación única.
La prueba automática QGIS verificó el ajuste de viento de 10 a 50 m en clase D
rugosa (factor 1,495348781), identificación del modelo y radios
en metadatos, y 12 celdas NoData dentro del radio matemático de 16,586 m para
clase D en una grilla de 10 m.

Confirmación manual 0.14.0, 2026-09-22: el usuario instaló y probó el nuevo ZIP
basado únicamente en Masters y confirmó que funciona correctamente. Esta
aceptación cubre el recorrido funcional realizado en su QGIS habitual. Las
casillas específicas que todavía aparecen abiertas conservan su carácter de
pruebas adicionales y de documentación para publicación.

Confirmación manual Windows, 2026-09-23: el usuario instaló el mismo ZIP 0.14.0
en Windows 10 con QGIS 3.44 LTR y completó sin incidencias el recorrido de
instalación, cálculo constante y CSV, revisión de capas y CRS, simbología y
reapertura del proyecto.

Ensayo 0.12.0: el panel incorpora «Preparar CSV…». La prueba automática asigna
columnas con nombres libres, fecha `DD/MM/AAAA HH:MM`, UTC, rumbos cardinales y
nudos; conserva una fila válida y contabiliza por separado una dirección VRB y
una calma de rapidez cero.

Confirmación manual 0.13.0; regresión automática 0.14.0, 2026-09-22: el usuario importó en macOS el CSV
limpio `DGAC IQUIQUE.csv` y confirmó que el flujo funciona acorde. El panel
clasificó 478 filas direccionales, 7 calmas, 22 direcciones `.` variables y
ninguna ausente; la rosa mostró 94,3 %, 1,4 % y 4,3 %, respectivamente. La
evidencia y sus huellas están en
`validation/qgis_wind_csv_manual_0130.json`. Esta confirmación cubre la
importación y visualización, pero no la portabilidad manual de escenarios ni
un caso con ausentes.

- [x] Crear un proyecto de prueba en EPSG:32719 (WGS 84 / UTM zone 19S).
  Cargar `pluma_ug_m3.tif`, `fuente.geojson` e `isolineas.geojson`.
  Verificado por el usuario: las tres capas cargan y reconocen sus CRS.
- [x] **CRS:** propiedades del TIFF: EPSG:32719, metros. Los GeoJSON contienen
  longitud/latitud WGS84 (EPSG:4326); QGIS debe reproyectarlos al proyecto.
  Verificado después de iniciar QGIS con sus propias rutas GDAL/PROJ. No asignar
  EPSG:32719 a las coordenadas geográficas ni georreferenciar a mano.
- [x] **Ubicación:** fuente en longitud -70.193195, latitud -20.805320;
  coordenadas UTM aproximadas E=375825.819, N=7698938.582 m (tolerancia 0.01 m).
  Confirmar costa de Patache con cartografía de referencia. El punto es
  referencial; no acredita la posición exacta de una chimenea. El usuario
  confirmó la ubicación y la comprobación QGIS midió 0 m entre fuente y centro.
- [ ] **Entrada equivalente:** ejecutar el caso una vez con EPSG:4326
  (`x=-70.193195`, `y=-20.805320`) y otra con EPSG:32719
  (`x=375825.819`, `y=7698938.582`). Confirmar que ambos se normalicen al
  mismo punto y produzcan EPSG:32719. No aceptar UTM sin zona/hemisferio o EPSG.
- [x] **Grilla:** 200 columnas × 200 filas, una banda float64, píxel 50 × 50 m.
  Extensión: oeste 370825.819, sur 7693938.582, este 380825.819,
  norte 7703938.582 m (tolerancia 0.01 m). La fuente está en el centro del
  dominio y en una intersección de píxeles; no es centro de un píxel.
- [x] **Orientación:** con norte arriba, pluma hacia el sur, viento DESDE 0°
  norte verdadero. Hay una leve componente hacia el este respecto de la grilla
  por convergencia +0.423870°. No debe aparecer una pluma hacia el norte ni una
  matriz reflejada. Las isolíneas deben superponerse al campo del TIFF.
- [x] **Valores:** calcular estadísticas de toda la banda, sin muestreo
  aproximado: mínimo 0, máximo 221.557028 µg/m³ (tolerancia 0.001 µg/m³).
  Con Identificar consultar el centro E=375850.819, N=7697913.582 m: es el
  máximo muestreado. Comprobar un píxel al norte, por ejemplo E=375850.819,
  N=7703913.582 m: valor 0 válido.
- [x] **Borde:** consultar la fila sur (centros N=7693963.582 m); su máximo es
  57.279337 µg/m³ (tolerancia 0.001). Puede localizarse alrededor de
  E=375850.819 m. Confirmar el corte de isolíneas en la periferia y la bandera
  `visible_plume_reaches_domain_edge: true` del informe. No interpretar el
  exterior sin datos como concentración cero.
- [x] **Extensión controlada 0.14.0:** comparar el proyecto fijo con el extendido.
  Patache debe pasar de 10 × 10 km a 15 × 85 km en cuatro iteraciones, conservar
  el máximo 221.557028 µg/m³ y reducir el máximo periférico a 1.813580 µg/m³.
  Debe mantener la advertencia `safety_limit_reached_truncated`; no interpretar
  la parada computacional como contención física.
- [ ] **Viento desde CSV 0.4.0:** seleccionar
  `examples/synthetic_ne_sw_wind.csv`, emisión 100 g/s, estabilidad A y dominio
  fijo. Confirmar 1200 filas, rapidez media 5.446717 m/s, dirección circular
  representativa DESDE 44.825494°, máximo 754.544532 µg/m³ y borde
  0.140910 µg/m³. La rosa debe concentrarse en NE con una fracción pequeña en
  SO; el campo debe mostrar una pluma principal hacia SO y una secundaria hacia
  NE. La dirección representativa es informativa: no recalcular con una sola
  dirección.
- [x] **Asistente CSV 0.12.0:** elegir un archivo limpio de tres columnas y
  confirmar que la vista previa conserva sus encabezados. Asignar fecha,
  dirección y rapidez; escoger formato, zona horaria, unidad y DESDE/HACIA.
  Verificar el resumen de filas válidas, calmas, variables y ausentes. El
  archivo original no debe cambiar y el escenario debe conservar una copia
  normalizada reproducible.
  **Cierre 2026-09-22:** selección, mapeo, unidades, códigos, resumen, guardado
  y reapertura aprobados con DGAC Iquique. `escenario.json` y su copia canónica
  `escenario_viento.csv` se copiaron juntos a `Downloads/prueba_trasladada`; el
  complemento instalado los abrió desde allí, verificó la huella y recuperó
  478 filas válidas, 7 calmas, 22 variables y 0 ausentes. El CSV DGAC original
  se conserva como procedencia, pero la reapertura usa la copia canónica. El
  usuario ejecutó después el caso trasladado y confirmó la carga de ráster,
  isolíneas y fuente. La revisión automática encontró una grilla 200 × 200 en
  EPSG:32719, máximo 146,561263 µg/m³, 10 entidades de isolíneas, una fuente y
  una rosa PNG válida. El usuario confirmó visualmente que el viento
  principalmente DESDE suroeste/oeste produce transporte hacia noreste/este;
  véase `validation/qgis_dgac_execution_0130.json`.
- [x] **Rosa con categorías 0.14.0:** usar una tabla que contenga al menos una
  fila direccional válida, una calma, una dirección variable y una ausente.
  Comprobar que la calma aparece al centro, que el porcentaje variable se
  muestra aparte y que la suma de pétalos + calma + variable es 100 % sobre
  las filas no ausentes. Verificar en los metadatos del GeoTIFF los cuatro
  recuentos y la base condicional del cálculo.
  **Cierre 2026-09-22:** calma central, variable separada y porcentajes
  aprobados manualmente con DGAC Iquique. La prueba del paquete mostró además
  `Ausentes excluidos: 5`; sus metadatos conservaron total 1230, 10 calmas,
  15 variables y 5 ausentes, y el cálculo mantuvo pesos condicionales entre
  las 1200 filas direccionales.
- [ ] **Panel 0.8.0:** activar «Elegir en el mapa» y marcar Patache. Confirmar
  que Entrada muestra el CRS del lienzo, WGS84 muestra longitud/latitud y
  Cálculo muestra EPSG:32719, E=375825.819 y N=7698938.582 m. Elegir el CSV,
  abrir los parámetros y comprobar que aparecen modo tabla, dominio fijo y la
  ruta seleccionada. Cancelar el diálogo no debe ejecutar ni crear capas.
  Después ejecutar el caso base: debe mostrar progreso, crear una carpeta nueva
  sin sobrescribir corridas anteriores y cargar fuente, isolíneas y ráster en un
  grupo «Pluma». Comprobar también que «Cancelar cálculo» detenga una corrida.
  Guardar y abrir un escenario: comprobar recuperación de todos los parámetros
  y del CRS original. Trasladar JSON y su CSV juntos; deben seguir abriendo.
  Un CSV alterado debe rechazarse antes de cambiar el panel.
- [x] **Unidades y NoData:** banda «Ground concentration (ug/m3)», metadato
  `units=ug/m3`; ya contiene µg/m³, no multiplicar otra vez por 1e9.
  Emisión del escenario: 40 g/s = 0.04 kg/s. NoData=-9999; cero es dato válido.
  La altura efectiva es 50 m y los receptores están a z=0 m sobre suelo plano.
- [x] **Modelo Masters 0.14.0:** ejecutar Patache con estabilidad D, viento
  observado 5 m/s a 10 m, chimenea 50 m y exposición rugosa. Confirmar en los
  metadatos `dispersion_model=masters_2008_martin_1976`, factor de viento 1,495348781 y
  rapidez usada 7,476743906 m/s. Con resolución de 10 m debe existir NoData
  dentro del radio matemático de 16,586 m para D. Entre 20 y 100 m deben
  aplicarse directamente las ecuaciones 7.47–7.48, sin interpolación ni
  recorte.
- [ ] **Elevación final Briggs:** seleccionar «Briggs calculado» y comprobar
  que se habiliten diámetro, velocidad de salida, temperaturas, gradiente y
  descenso en la boca. Usar chimenea 50 m, diámetro 2 m, salida 10 m/s, gas
  126,85 °C, ambiente 26,85 °C, clase D, viento 5 m/s medido a 10 m y
  exposición rugosa. La ejecución automática en QGIS 3.44 LTR obtuvo elevación
  31,556068 m y altura efectiva 81,556068 m. Confirmar en el GeoTIFF
  `height_mode=briggs`, `stack_height_m=50.0`, `plume_rise_m=31.556068...` y
  `effective_height_m=81.556068...`. Guardar, cerrar y abrir el escenario; debe
  recuperar los parámetros. Abrir además un escenario 0.14.0 y confirmar que
  migre a «Sin elevación» con el mismo resultado anterior.
- [x] **Simbología del TIFF:** pseudocolor monobanda con clases discretas
  YlOrRd y cortes coincidentes con las isolíneas del informe. Para el escenario
  de referencia: 0.1, 1, 2, 5, 10, 20, 50, 100, 200 y 221.557028 µg/m³;
  amarillo para menor concentración y rojo oscuro para la mayor. Usar vecino
  más próximo en pantalla para cotejar píxeles. Si se ocultan valores inferiores
  a 0.1, hacerlo solo en la representación, conservando los valores originales.
  No usar el estiramiento automático por extensión visible para comparar.
- [x] **Isolíneas:** comprobar los campos `concentration` y
  `concentration_unit`. Con mínimo 1 µg/m³, el escenario D de referencia usa
  1, 2, 5, 10, 20, 50, 100, 200 y 300. Para entradas editadas manualmente,
  cotejar `contour_levels` y `concentration_unit` del informe. Si la salida es
  µg/m³ también existe el campo compatible `concentration_ug_m3`.
  Etiquetar con el campo y la unidad declarados;
  asignar a las líneas el color de su banda YlOrRd correspondiente.
  Las líneas terminan en centros periféricos, no necesariamente en el borde
  exterior del píxel. No exigir una curva cerrada en el máximo.
  Los controles anteriores fueron verificados mediante QGIS 3.40.5 y quedaron
  registrados en `validation/qgis_layers.json`; la orientación se inspeccionó
  además en `outputs/qgis_validation/vista_validacion.png`.
- [ ] **Comparación web:** abrir `mapa_pluma.html` con conexión; alternar
  ráster/isolíneas, comprobar leyenda, fuente, máximo y avance hacia el sur.
  La vista web reproyecta a EPSG:3857; contrastar ubicación y datos, no una
  igualdad de tamaño aparente de píxel en pantalla. Confirmar carga de teselas.
- [ ] Guardar el proyecto de prueba y las evidencias, cerrarlo y reabrirlo;
  comprobar rutas y simbología. Registrar aprobado/fallido y pendientes.

Aceptar la carga espacial solo si coinciden CRS, ubicación, orientación,
valores y unidades. El truncamiento conocido puede registrarse como limitación
del caso docente; no marcar la pluma como contenida ni el modelo como validado
ambientalmente. El adaptador QGIS 0.14.0 sigue siendo experimental.
