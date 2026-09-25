# Comparación pre-Briggs con Manchester

Esta comparación cubre solamente el modelo de pluma gaussiana antes de
calcular elevación de pluma. Manchester recibe la altura efectiva `H`
directamente; no contiene diámetro de chimenea, velocidad de salida,
temperaturas, gradiente vertical, descenso en la boca ni ecuaciones Briggs.

La suite completa contiene 77 pruebas automáticas; las tres pruebas de este
documento añaden la comparación sistemática con Manchester.

Los dos códigos comparten la estructura de fuente puntual continua, dirección
meteorológica **DESDE**, reflexión perfecta en el suelo, emisión `Q` en kg/s,
viento `u` en m/s y altura efectiva `H` en m. No se exige igualdad de
concentraciones absolutas: Manchester usa sus ajustes rurales ISC/Turner por
tramos, mientras el complemento usa Masters y Ela (2008), Tabla 7.8. Una
diferencia numérica entre ambos puede ser correcta si ambos conservan las
propiedades físicas comunes indicadas abajo.

| Prueba ejecutada | Rango de parámetros | Casos | Correspondencia Manchester | Criterio aprobado |
|---|---|---:|---|---|
| Matriz de emisión y viento | `Q`: 0,001; 0,04; 1 kg/s. `u`: 1; 5; 15 m/s. `H`: 10; 50; 250 m. Dirección: 0; 45; 90; 225°. Clases A–F. Distancia: 1; 10; 50 km | 1.944 | `Q`, `u`, `H`, dirección y A–F son entradas directas en ambos | En ambos: duplicar `Q` duplica `C`; duplicar `u` reduce `C` a la mitad; `C>0` a sotavento. |
| Simetría transversal y barlovento | A–F × cuatro direcciones; receptor a 1,5 km y ±200 m transversal | 24 | La rotación de Manchester y la del complemento usan viento meteorológico DESDE | En ambos: `C(y)=C(-y)` y `C=0` a barlovento. |
| Altura efectiva suministrada | `H`: 10; 50; 250 m, A–F × cuatro direcciones | 72 | Manchester recibe `H` directamente, igual que el modo sin elevación o manual del complemento | Concentraciones finitas y no negativas para cada `H`; no se compara valor absoluto por los distintos sigmas. |
| Promedio de observaciones de viento | Archivo DGAC Iquique: 478 filas direccionales, 36 direcciones cada 10° | 478 plumas | Manchester suma una pluma por hora; el modo CSV también promedia plumas ponderadas | Ambos muestran radios bajo F. El cálculo del complemento sin agrupar y con 72 sectores difirió menos de `9×10⁻¹² %` en el máximo para esta tabla, porque los 10° de DGAC ya caen en sectores distintos de 5°. |

La comparación se ejecuta con:

```text
python -m unittest tests.test_manchester_correspondence
```

El archivo de prueba es `tests/test_manchester_correspondence.py`; lee
`reference/manchester/` sin modificarlo. La comparación visual DGAC de
estabilidad F se genera con `scripts/compare_dgac_iquique_f.py` y queda en
`outputs/diagnostics/`.

## Límites explícitos

| Componente | Manchester | Complemento | Tipo de comparación |
|---|---|---|---|
| Ecuación gaussiana, `Q`, `u`, `H`, dirección y reflexión | Sí | Sí | Propiedades algebraicas y geométricas comunes. |
| Coeficientes `σy`, `σz` | ISC/Turner por tramos | Masters 2008 / Martin 1976 | No se exige la misma concentración absoluta. |
| Corrección de viento por altura | No en el caso docente base | Sí, ecuación 7.46 de Masters | Se valida internamente en el complemento. |
| Elevación final Briggs | No | Sí, opcional | Sin correspondencia Manchester; se valida con ecuaciones Briggs/ISC3 y Masters. |
| Terreno, deposición, química, edificios | No | No | Fuera de ambos alcances. |
