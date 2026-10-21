# Supuestos y limitaciones

Este documento dice qué supone el sistema y qué no puede afirmar. Aplica a los datos simulados que trae el repositorio y también a los datos reales de Clarios que se carguen en local.

## Supuestos

- **Los contadores del SCADA están en Wh**, así que kWh = valor / 1000. Clarios no lo confirmó; el parámetro está en `dashboard/config.yaml` (`unidades.contador_energia_a_kwh`).
- **Los turnos son 06:00–14:00, 14:00–22:00 y 22:00–06:00**, y la fecha del turno es la de su inicio. Clarios no entregó el calendario de turnos ni el de paradas, así que toda cifra por turno depende de este supuesto.
- **La hora del ERP es la hora del reporte**, no la de la producción.
- **Filtros y PTARI no tienen línea propia en el ERP.** Se asocian a la producción de refinación, que por eso aparece repetida en tres procesos: no se debe sumar producción entre procesos.
- **Tarifa del kWh y del gas**: son valores de referencia en `dashboard/config.yaml`. El ahorro que sale de `fraccion_evitable` (0.5) es un escenario, no un ahorro demostrado.
- **Plan de producción y presupuesto FY27**: no existen; el año fiscal va de octubre a septiembre. Nada de esto se inventa.

## Calidad de la medición

- **Los contadores son acumulados.** El consumo sale de restar lecturas. Cuando un contador se reinicia, esas horas quedan marcadas `reinicio` y sin consumo.
- **El SCADA se congela.** Un congelamiento es un periodo en que los medidores no cambian durante varias horas. Si al volver reaparece la energía acumulada, las horas se marcan `estimado` y se reparte parejo: sirve para totales mensuales, no para mirar por turno.
- **Rachas sin cambio** por medidor: se clasifican por lo que pasa después (reaparece energía o no) y se guarda su confianza (alta, media, baja). Sin reaparición no se puede distinguir un cero real de un medidor atascado, y esos casos quedan como indeterminados.
- **Cobertura en tiempo y cobertura en energía son cosas distintas.** La primera son las horas medidas sobre las posibles; la segunda, los kWh medidos sobre medidos más estimados.
- **EMCALI y EDIF_ADMON** no se clasifican ni se modelan: no se sabe qué miden ni en qué unidad.
- **Gas SCADA**: tiene pocos meses y es no conciliable con la base mensual de Clarios, porque no hay un periodo en común.

## Modelos

- Los modelos son regresiones robustas (Huber) y GradientBoosting por proceso y nivel. Se entrenaron una sola vez con los datos reales de Clarios, que solo se usaron para eso, y se entregan ya entrenados en `modelos/modelos.pkl`. **No se reentrenan** con los datos simulados.
- `operando` y el régimen de operación se calculan con el mismo consumo que se quiere explicar, así que no se usan como variables explicativas por fuga de información.
- La confianza de cada modelo (`confianza_modelo`: alta, media o baja) viene en `resultados_modelo`. Donde es baja, el resultado orienta pero no se debe usar para decidir solo.
- La producción de RC llega por lotes, por lo que la relación energía–producción es débil por turno y más fuerte por semana.

## Datos simulados

- Las 29 tablas de `dashboard/datos_simulados/` las genera un script del repositorio de trabajo con una semilla fija: son inventadas, tienen el mismo esquema que las reales y nada de lo que se ve en el dashboard corresponde a Clarios.
- El consumo simulado sale de los modelos entregados más ruido, episodios de exceso sostenido, pocas anomalías puntuales y paradas inesperadas, para que el dashboard tenga algo que mostrar. Esas anomalías están puestas a propósito.
- Para ver datos reales, se copian las tablas a `dashboard/data/clean/` en local. Esa carpeta está en `.gitignore` y no se sube.

## Pendiente de confirmar con Clarios

Unidades de los contadores, qué mide EMCALI, alcance del gas de refinación, causa de los congelamientos y reinicios, calendario de turnos y paradas, y plan de producción FY27.
