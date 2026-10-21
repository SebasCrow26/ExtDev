# Supuestos y limitaciones

Este documento dice qué supone el sistema, qué no puede afirmar y qué es real y qué es simulado.

## Alcance y origen de los datos

- **Por defecto, el dashboard lee solo tablas sintéticas** (`dashboard/datos_simulados/`). Tienen el mismo esquema que las tablas de la operación, pero sus cifras, fechas, tarifas, metas y eventos son inventados. Son lo que usa cualquier despliegue público.
- **Los modelos de `modelos/modelos.pkl` se entrenaron una sola vez con datos reales de Clarios** y no se reentrenan. El archivo contiene los parámetros ajustados y los intervalos, no las filas originales.
- **Los datos reales no están en este repositorio.** Para verlos solo en una máquina local, se apunta la variable de entorno `CLARIOS_DATOS_REALES` a una carpeta con las tablas; el dashboard muestra entonces un aviso con la fuente activa. Esa ventana no se debe compartir ni desplegar.
- **En el monitoreo en vivo, la historia de partida es la de la fuente activa** (real en local, sintética en el despliegue público) y **las lecturas nuevas que van llegando son siempre simuladas.**

## Supuestos

- **Los contadores del SCADA están en Wh**, así que kWh = valor / 1000. Clarios no lo confirmó.
- **Los turnos son 06:00–14:00, 14:00–22:00 y 22:00–06:00.** La fecha del turno es la del día en que inicia; el tercero cruza la medianoche. Clarios no entregó un calendario de turnos ni de paradas, así que toda cifra por turno depende de este supuesto.
- **La hora del ERP es la hora del reporte**, no la de la producción.
- **La producción de algunos procesos se asocia a la de otro** (filtros y ptari usan la producción de refinación, porque no tienen línea propia). Por eso no se debe sumar producción entre procesos.
- **La tarifa y los presupuestos de los datos sintéticos son valores inventados.** En los datos reales, la tarifa es la de referencia de Clarios.
- **La fracción evitable del exceso (0,5) es un supuesto sin respaldo.** Cualquier ahorro calculado con ella es un escenario, no un ahorro demostrado.
- **Los umbrales del semáforo y de las alertas** (porcentajes, número de turnos seguidos y costo mínimo) son provisionales del equipo y se pueden cambiar en la interfaz.

## Modelos

- Hay un modelo por proceso y nivel temporal (turno, día y semana): regresión robusta (Huber) o GradientBoosting, el que mejor resultó en la prueba. Cada uno trae un intervalo basado en los cuantiles 10 y 90 de sus residuos.
- El pronóstico y el monitoreo en vivo usan estos mismos modelos a través de `modelo_esperado_api.py`.
- **La confianza varía por proceso** y el dashboard la muestra: alta en el horno, media en triturado y ptari, y baja en refinación y filtros. Con confianza baja el resultado es **indicativo**: sirve de referencia, pero no conviene decidir solo con ese dato.
- Los modelos **no usan** `operando` ni el régimen de operación como variables, porque se calculan con el mismo consumo que se quiere explicar (habría fuga de información).
- La producción de la planta llega por lotes, por lo que la relación entre energía y producción es débil por turno y más fuerte al agregar por semana.
- El **exceso neto** (consumo real menos esperado, sumado) es un orden de magnitud, no una medición exacta: un modelo con error siempre deja turnos por encima y por debajo de lo esperado. No debe presentarse la suma de los excesos como ahorro.
- Cuando el dashboard combina tablas sintéticas con estos modelos, los resultados son una demostración y no una validación de desempeño.

## Calidad de los datos y limitaciones

- **Los contadores del SCADA son acumulados.** El consumo sale de restar lecturas. Si un contador se reinicia, esas horas quedan sin consumo: no se inventa lo que se perdió.
- **El SCADA se congela.** Cuando todos los medidores se quedan sin cambio durante varias horas y la energía reaparece después, esas horas se marcan como estimadas y la energía se reparte de forma pareja. Sirve para totales, no para analizar por hora o por turno.
- **Un turno con cobertura insuficiente** (por defecto menos del 75 % de las horas medidas) se muestra como "dato incompleto" y no se evalúa.
- **Los medidores de la planta no cubren toda su operación.** No sirven para calcular un costo total de planta.
- **Las series de gas y de F&A cubren pocos meses**, y el gas no se puede conciliar con la base mensual de Clarios porque no hay un periodo en común.
- **No hay calendario de turnos ni de paradas, plan de producción ni metas por proceso.** Nada de esto se inventa: donde falta, se marca como supuesto.
- **El indicador de kWh por equivalente depende de los factores de equivalencia**, que cambian cuando cambian las listas de materiales; por eso el sistema compara contra el consumo esperado según la producción.
- **Los eventos del monitor** (exceso, parada, congelamiento y reinicio) son escenarios programados o inyectados, no registros de la operación.

## Uso de IA

La documentación y parte del código de este repositorio se desarrollaron con ayuda de inteligencia artificial (Claude, de Anthropic). Todo el contenido fue verificado de antemano por el equipo, y el código se probó antes de entregarse.

## Privacidad

No se agregan al repositorio datos de planta, exportaciones ni capturas con información real. Las tablas reales se cargan solo en local, con `CLARIOS_DATOS_REALES`, y nunca se despliegan en un servicio público.
