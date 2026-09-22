# Base pedagógica: Masters y Ela (2008)

Este documento registra la fuente teórica elegida para el complemento. La formulación implementada está descrita con sus ecuaciones, unidades, campo cercano y pruebas en [model.md](model.md).

## Alcance implementado

- ecuación gaussiana estacionaria con reflexión en el suelo;
- clases de estabilidad A–F elegidas por el estudiante;
- ecuaciones 7.47–7.48 y Tabla 7.8 para `σy` y `σz`;
- comprobación de los valores redondeados de la Tabla 7.9;
- ecuación 7.46 para corregir la rapidez por altura;
- altura efectiva igual a la altura física de la chimenea y ascenso cero.

## Decisiones docentes

La aplicación no determina automáticamente la estabilidad. Tampoco calcula todavía el ascenso de pluma: hacerlo exige velocidad y diámetro de salida, temperaturas, condiciones ambientales y expresiones distintas según la estabilidad. El panel conserva estos límites visibles para que el estudiante sepa qué hipótesis está utilizando.

Las ecuaciones de sigma se aplican directamente donde producen valores positivos. La tabla impresa y la figura sirven para contrastar y visualizar; sus primeros valores no se transforman en cortes artificiales. El campo cercano no representable se escribe como NoData hasta la raíz matemática de `σz`.

## Referencia bibliográfica

Masters, G. M. y Ela, W. P. (2008). *Introduction to Environmental Engineering
and Science*, 3.ª edición, capítulo 7. Prentice Hall. ISBN
978-0-13-148193-0. Los coeficientes de dispersión de la Tabla 7.8 se atribuyen
allí a Martin (1976).
