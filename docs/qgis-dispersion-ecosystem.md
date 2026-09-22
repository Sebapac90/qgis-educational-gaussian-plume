# ISC, AERMOD y QGIS — revisión 2026-09-22

## Resultado

No se encontró en el repositorio oficial de complementos de QGIS una
implementación mantenida que ejecute el sistema regulatorio AERMOD completo o
ISC3 dentro de QGIS. QGIS se usa habitualmente como herramienta de preparación,
conversión, representación y análisis de resultados; el ejecutable del modelo y
sus preprocesadores permanecen externos.

La afirmación se limita a la búsqueda realizada en esta fecha. No demuestra que
nunca haya existido un prototipo, complemento privado o repositorio no
indexado.

## AERMOD

La EPA distribuye AERMOD junto con AERMET y AERMAP como ejecutables, código y
documentación propios, no como complemento QGIS. La página oficial vigente
publica la versión 26135 y señala que AERMOD reemplazó a ISC3 en 2006:

https://www.epa.gov/scram/air-quality-dispersion-modeling-preferred-and-recommended-models

Se encontraron interfaces externas como PyAERMOD, un paquete de R y AERMOD-IPT.
Estas preparan archivos o ejecutan los binarios de EPA, pero no son complementos
oficiales de QGIS. Los resultados tabulares de AERMOD pueden convertirse y
cargarse en QGIS para interpolación, isolíneas y cartografía.

## ISC3

ISC3 es el predecesor retirado de AERMOD. No se encontró un complemento actual
del repositorio oficial que implemente ISCST3/ISCLT3. Su parametrización todavía aparece en algunos códigos docentes y modelos
gaussianos simplificados.

## Complementos relacionados

- **AirEmergency**: complemento experimental de QGIS 4 basado en pluma
  gaussiana para evaluaciones rápidas; declara que no es regulatorio.
  https://plugins.qgis.org/plugins/AirEmergency/
- **EnviFate**: conjunto histórico de módulos ambientales con dispersión
  atmosférica simplificada; no equivale a AERMOD.
- **Open-ALAQS**: inventario aeroportuario y exportación de entradas para
  AUSTAL; demuestra el patrón QGIS como interfaz para un modelo externo.
  https://github.com/eurocontrol-asu/open_alaqs
- **Geodata to ENVI-met**: conecta QGIS con ENVI-met, otro sistema externo de
  microclima urbano; no implementa AERMOD ni ISC.

## Implicación para este proyecto

El complemento ocupa un espacio válido como herramienta docente reproducible en
QGIS. Debe describirse como modelo gaussiano clásico basado en Masters, no como
sustituto de AERMOD. Una integración futura
con AERMOD debería generar entradas, ejecutar binarios oficiales instalados por
separado e importar resultados, manteniendo clara la frontera entre interfaz GIS
y motor regulatorio.
