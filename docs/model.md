# Modelo y decisiones físicas

## Base pedagógica

El complemento aplica el modelo gaussiano clásico descrito por Gilbert M. Masters y Wendell P. Ela en *Introducción a la ingeniería medioambiental*, 3.ª edición (2008), capítulo 7. La estabilidad atmosférica es una entrada manual A–F: el estudiante la determina a partir de la teoría; el programa no la infiere desde nubosidad, insolación u otras observaciones.

El objetivo es docente y técnico básico. El resultado no sustituye una evaluación regulatoria ni un modelo de capa límite como AERMOD.

La idea de trasladar una simulación educativa a una herramienta interactiva se
inspiró en *Gaussian plume model practical*, de Paul J. Connolly, Universidad
de Manchester (2017). La implementación actual se desarrolló específicamente
para QGIS y adoptó como base física el tratamiento de Masters y Ela indicado
arriba.

## Ecuación y unidades

Para una fuente puntual continua y `x > 0`:

```text
C = Q / (2π u σy σz) · exp[-y²/(2σy²)]
    · {exp[-(z-H)²/(2σz²)] + exp[-(z+H)²/(2σz²)]}
```

| Símbolo | Significado | Unidad interna |
|---|---|---|
| `x` | distancia a sotavento | m |
| `y` | distancia transversal con signo | m |
| `z` | altura del receptor, `z ≥ 0` | m |
| `Q` | emisión continua | kg/s |
| `u` | rapidez del viento a la altura usada por el modelo | m/s |
| `H` | altura efectiva | m |
| `σy`, `σz` | dispersión lateral y vertical | m |
| `C` | concentración | kg/m³ |

La segunda exponencial vertical representa la fuente imagen y la reflexión perfecta en el suelo. Para `x ≤ 0`, incluido el plano singular de la fuente, el programa devuelve cero.

La interfaz convierte de forma explícita kg/s, g/s, mg/s o µg/s a kg/s, y kg/m³ a la unidad elegida. Por ejemplo, `g/s × 10⁻³ = kg/s` y `kg/m³ × 10⁹ = µg/m³`.

## Coeficientes de dispersión

Con `X = x/1000`, expresado en kilómetros, se usan las ecuaciones 7.47 y 7.48 y la Tabla 7.8:

```text
σy = a X^0,894
σz = c X^d + f
```

Los coeficientes de `σz` cambian en 1 km. En el punto común se usa la rama `x ≤ 1 km`. Las constantes están transcritas en `gaussian_core.py` y se comprueban contra los valores redondeados de la Tabla 7.9 para las seis clases.

La Tabla 7.9 comienza en 200 m y la Figura 7.50 en 100 m; esos primeros valores son límites de presentación, no cortes matemáticos de las ecuaciones. Entre 20 y 100 m el programa evalúa directamente las expresiones publicadas, sin interpolar, recortar ni mezclar parámetros.

Para D, E y F, el término `c X^d + f` se vuelve no positivo muy cerca de la fuente. Sus raíces son aproximadamente 16,586 m, 14,629 m y 6,615 m. El ráster usa NoData solo dentro de la raíz exacta de la clase correspondiente. A–C tienen sigma vertical positiva para todo `x > 0`. Este tratamiento evita inventar una sigma y no establece validez empírica en el campo cercano.

## Altura de chimenea y viento

El modo básico pide la altura física de la chimenea `h`, fija el ascenso de pluma en cero y usa:

```text
H = h
Δh = 0
```

El GeoTIFF registra `stack_height_m`, `plume_rise_m` y `effective_height_m`. El
siguiente hito incorporará modos sin ascenso, altura efectiva ingresada y
ascenso final Briggs calculado. Las ecuaciones, ramas de flotación y momento,
entradas y correcciones de dos errores impresos del ejemplo 7.14 están
registradas en [plume-rise.md](plume-rise.md). Hasta completar ese hito, la
versión ejecutable conserva `Δh = 0`.

La rapidez observada se corrige desde la altura de medición `z_ref` hasta la altura de la chimenea mediante la ecuación 7.46:

```text
u(H) = u(z_ref) · (H/z_ref)^p
```

Para exposición rugosa se usan exponentes A–F de 0,15; 0,15; 0,20; 0,25; 0,40 y 0,60. Para exposición plana se multiplica el exponente por 0,6. La corrección cambia la rapidez, no la dirección. La rugosidad aerodinámica explícita y la teoría de Monin–Obukhov quedan fuera del nivel básico.

## Dirección y series de viento

La dirección es meteorológica **DESDE**, horaria desde norte verdadero. Con desplazamientos Este `ΔE` y Norte `ΔN` y azimut `α`:

```text
x_sotavento = -sin(α) ΔE - cos(α) ΔN
y_transversal = -cos(α) ΔE + sin(α) ΔN
```

La convergencia de meridianos transforma una sola vez el norte verdadero al norte de la grilla local.

Los modos disponibles son:

- `constant`: una dirección y una rapidez;
- `prevailing`: 1200 direcciones reproducibles alrededor de una dirección central, con desviación 40°;
- `fluctuating`: 1200 direcciones uniformes reproducibles; la dirección ingresada no interviene;
- `table`: observaciones o frecuencias ingresadas por el usuario.

Cada condición meteorológica genera un campo estacionario. El resultado se obtiene como media ponderada:

```text
C_media(E,N) = Σ wᵢ C(E,N; direcciónᵢ, rapidezᵢ),  con  Σwᵢ = 1
```

La suma o media ponderada de concentraciones por frecuencias meteorológicas es una operación general de los modelos de dispersión climatológicos. La documentación histórica de EPA describe el promedio de resultados horarios y la ponderación por frecuencia relativa de cada combinación meteorológica: [AERMOD User's Guide](https://gaftp.epa.gov/aqmg/SCRAM/models/preferred/aermod/aermod_userguide.pdf) y [evaluación de modelos gaussianos de EPA](https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=20015UWM.txt).

Para tablas largas, el cálculo agrupa primero en 72 sectores direccionales de 5° y siete clases de rapidez. Dentro de cada clase conserva el peso total, usa media circular ponderada para la dirección y media armónica ponderada para la rapidez, porque la concentración es proporcional a `1/u`. La rosa de vientos conserva 16 sectores para una lectura clara.

En 45 casos sintéticos, la agrupación de 72 sectores tuvo una diferencia máxima de 2,90 %, RMSE normalizado máximo de 0,32 % y correlación mínima de 0,99978 frente al cálculo fila por fila. En seis tablas meteorológicas ensayadas, la diferencia máxima fue 1,01 % y la correlación mínima 0,99914. Es una aceptación práctica para el MVP, no una cota universal.

Las calmas y direcciones variables se muestran separadas en la rosa. El campo de concentración se condiciona a observaciones con dirección definida y rapidez positiva, porque la ecuación estacionaria no representa `u = 0` ni una dirección indeterminada. Los datos ausentes se excluyen y todos los recuentos quedan en los metadatos.

## Supuestos y límites

- terreno plano y viento uniforme en cada cálculo estacionario;
- una fuente puntual continua;
- estabilidad A–F fija por escenario;
- reflexión perfecta en el suelo;
- sin ascenso de pluma, deposición, química, edificios ni terreno;
- sin autocorrelación temporal ni ráfagas;
- dominio local máximo de 100 km por lado;
- resultados educativos, sin validez regulatoria declarada.

La política predeterminada conserva el dominio solicitado y reporta los máximos de cada borde. Se considera que un lado necesita revisión si alcanza 0,1 µg/m³ o 1 % del máximo del campo. La opción de extensión duplica solo los márgenes que no cumplen, hasta los límites de tamaño, celdas e iteraciones. Cumplir esos umbrales indica contención numérica de la visualización; no demuestra validez física a grandes distancias.

## Validación reproducible

`tests/test_masters_2008.py` contrasta ecuaciones 7.46–7.48 y tablas 7.8–7.9. Las demás pruebas cubren simetría, escala con emisión y viento, reflexión, unidades, CRS, orientación, ráster, isolíneas, importación meteorológica y agrupación.

La validación actual ejecuta 60 pruebas en el entorno `gee` y seis casos de centro de pluma con cálculo analítico independiente a 1 km. El acuerdo numérico verifica la implementación de las ecuaciones y el software; no constituye validación de campo.
