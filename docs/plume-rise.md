# Elevación de pluma: formulación Briggs verificada

Estado: núcleo, modos de viento, metadatos espaciales e interfaz QGIS
implementados. Pendiente de prueba manual de usabilidad antes de preparar una
nueva versión pública.

## Alcance adoptado

El complemento incorpora Briggs como método calculado de elevación de pluma.
Masters y Ela (2008), ecuaciones 7.51–7.54, se conserva como introducción
pedagógica. Para que el modo calculado no quede limitado a penachos calientes
dominados por flotación, las ramas de momento y el criterio de cruce se toman de
la formulación Briggs documentada por EPA para ISC3.

La implementación actual calcula la elevación **final**. La elevación gradual
con la distancia y la estela de edificios quedan como extensiones separadas
porque requieren cambiar la altura utilizada en cada receptor.

## Variables y unidades

| Símbolo | Definición | Unidad interna |
|---|---|---|
| `h_s` | altura física de la chimenea | m |
| `h_s'` | altura física corregida por descenso en la boca | m |
| `d_s` | diámetro interior en la boca | m |
| `r_s=d_s/2` | radio interior | m |
| `v_s` | velocidad de salida del gas | m/s |
| `u_s` | viento a la altura física de la chimenea | m/s |
| `T_s`, `T_a` | temperatura del gas y ambiente | K |
| `ΔT=T_s-T_a` | diferencia de temperatura | K |
| `F_b` | flujo de flotación | m⁴/s³ |
| `F_m` | flujo de momento | m⁴/s² |
| `s` | parámetro de estabilidad | s⁻² |
| `Δh` | elevación final de la pluma | m |
| `H=h_s'+Δh` | altura efectiva final | m |

Las temperaturas introducidas en °C se convierten a K antes de calcular. El
viento observado se ajusta primero hasta `h_s` para obtener `u_s`. Después de
obtener `H`, se ajusta nuevamente hasta `H` para usarlo en la ecuación de
concentración.

## Flujos de Briggs

Con `g` documentada explícitamente:

```text
F_b = g v_s d_s² ΔT / (4 T_s)
    = g r_s² v_s (1 - T_a/T_s)

F_m = v_s² d_s² T_a / (4 T_s)
```

Las dos expresiones de `F_b` son algebraicamente idénticas. La segunda es la
forma impresa por Masters.

## Condiciones A–D

Para `T_s > T_a`, el cruce entre flotación y momento se evalúa con:

```text
ΔT_c = 0.0297 T_s v_s^(1/3) / d_s^(2/3)    si F_b < 55
ΔT_c = 0.00575 T_s v_s^(2/3) / d_s^(1/3)   si F_b ≥ 55
```

Si `ΔT ≥ ΔT_c`, domina la flotación:

```text
x_f = 49 F_b^(5/8)       si F_b < 55
x_f = 119 F_b^(2/5)      si F_b ≥ 55

Δh = 21.425 F_b^(3/4) / u_s    si F_b < 55
Δh = 38.71 F_b^(3/5) / u_s     si F_b ≥ 55
```

Las constantes directas de `Δh` equivalen, salvo redondeo, a evaluar
`1.6 F_b^(1/3) x_f^(2/3)/u_s`. Masters redondea `49` y `119` a `50` y `120`.

Si `T_s ≤ T_a` o `ΔT < ΔT_c`, domina el momento:

```text
Δh = 3 d_s v_s / u_s
```

## Condiciones E–F

El parámetro de estabilidad se calcula a partir del gradiente de temperatura
potencial. En la notación de Masters, usando el gradiente real de temperatura:

```text
s = (g/T_a) (ΔT_a/Δz + 0.01 K/m)
```

Debe cumplirse `s > 0`. El cruce estable es:

```text
ΔT_c = 0.019582 T_s v_s √s
```

Si domina la flotación:

```text
Δh = 2.6 (F_b/(u_s s))^(1/3)
```

Si domina el momento se evalúan ambas expresiones y se usa la menor:

```text
Δh_1 = 1.5 (F_m/(u_s √s))^(1/3)
Δh_2 = 3 d_s v_s/u_s
Δh = min(Δh_1, Δh_2)
```

El usuario seguirá ingresando la clase A–F. Para E–F se solicitará además el
gradiente vertical de temperatura; no se inferirá la estabilidad desde otras
observaciones.

## Descenso en la boca

Briggs permite corregir la altura física cuando la velocidad de salida es baja:

```text
h_s' = h_s + 2 d_s (v_s/u_s - 1.5)    si v_s < 1.5 u_s
h_s' = h_s                             si v_s ≥ 1.5 u_s
```

Se expondrá como opción avanzada y estará desactivada de manera predeterminada
en el modo docente inicial.

## Verificación del ejemplo 7.14

Con `h_s=250 m`, `r_s=2 m`, `v_s=15 m/s`, `T_s=413 K`, `T_a=298 K`,
`u_s=5 m/s`, gradiente `+2 °C/km` y `g=9.8 m/s²`:

```text
F_b = 163.7288 m⁴/s³ ≈ 164
s = 0.000394631 s⁻² ≈ 0.0004
Δh estable = 113.4039 m ≈ 113
H estable = 363.4039 m ≈ 363
```

Para A–D, la rama correcta es `F_b ≥ 55`. Con los coeficientes redondeados de
Masters se obtiene `x_f=922.2131 m`, `Δh=165.8616 m` y `H=415.8616 m`, que se
redondea a `416 m`. Con los coeficientes ISC3 `119` y `38.71` se obtiene
`x_f=914.5280 m`, `Δh=164.9409 m` y `H=414.9409 m`.

La edición consultada contiene dos inconsistencias en la solución impresa:

1. afirma `F < 55` aunque `F≈164` y aplica correctamente la rama alta;
2. escribe `250 + 166 = 413`, cuando la suma correcta es `416`.

Las pruebas usarán los valores calculados por las ecuaciones, no esos dos textos
erróneos. En `F_b=55` se usará la rama `F_b ≥ 55`, como especifica ISC3.

## Viento múltiple y metadatos

En modos sintéticos o CSV, cada clase de velocidad tendrá su propio `u_s`,
`Δh`, `H` y viento a `H`. No se calculará una sola elevación a partir de la
velocidad media. La rosa conserva 16 sectores y siete bandas de velocidad. El
cálculo con Briggs usa 72 sectores direccionales y clases de velocidad de 1 m/s
hasta 12 m/s, más una clase abierta. En un caso sintético reproducible de 600
observaciones, la comparación con el cálculo fila por fila mantuvo la diferencia
por debajo de 5% en celdas que superan 0,1% del máximo y la diferencia del máximo
por debajo de 2%. Estos son controles de aproximación numérica, no validación de
campo.

Cada salida registrará el método, régimen dominante, `F_b`, `F_m`, `s` cuando
corresponda, descenso en la boca, elevación y altura efectiva. En promedios de
viento registrará también mínimos, máximos y medias ponderadas de `Δh` y `H`.

## Fuentes

- Masters, G. M. y Ela, W. P. (2008). *Introducción a la ingeniería
  medioambiental*, 3.ª edición, ecuaciones 7.51–7.54 y ejemplo 7.14.
- U.S. EPA (1995/2000). *User's Guide for the Industrial Source Complex (ISC3)
  Dispersion Models*, volumen II, sección 1.1.4, ecuaciones 1-7 a 1-22:
  https://gaftp.epa.gov/AIR/aqmg/SCRAM/models/other/isc3/isc3v2.pdf
