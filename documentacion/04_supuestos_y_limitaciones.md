# Supuestos y limitaciones de la demostración

Este repositorio contiene una demostración aislada. El dashboard carga exclusivamente las tablas sintéticas de `dashboard/datos_simulados/`. Sus cifras, fechas, tarifas, metas y eventos son ficticios y no deben interpretarse como mediciones ni compromisos de una empresa.

## Supuestos de simulación

- Los acumulados se interpretan como Wh y se convierten a kWh dividiendo entre 1.000.
- Se simulan tres turnos de ocho horas. El tercero cruza la medianoche y su fecha corresponde al día en que inicia.
- La producción equivalente se asocia a los procesos según `dashboard/config.yaml`; esa asociación sirve para ilustrar filtros y gráficas.
- Las tarifas y presupuestos incluidos en las tablas son valores inventados para la demostración.
- Los eventos de exceso, parada, congelamiento y reinicio que aparecen en el monitor son escenarios programados o inyectados.

## Estimador de consumo

El pronóstico interactivo usa la mediana sintética de kWh por kg para el proceso y periodo, con filtros de turno y día de semana cuando hay suficientes observaciones. La banda muestra percentiles 10–90 de esas razones. No es un modelo validado, no usa modelos entrenados con datos reales y no representa un intervalo estadístico de confianza.

## Limitaciones

- Las tablas sintéticas imitan el esquema y algunos patrones de una operación industrial; no describen una operación real.
- Las fechas son etiquetas ficticias. No sirven para inferir horarios, temporadas, producción o eventos reales.
- La cobertura, calidad, semáforos, alertas y costos solo ilustran el funcionamiento de la interfaz.
- La base mensual y las series del SCADA son conjuntos sintéticos separados; sus magnitudes no se concilian entre sí.

## Regla de privacidad

No agregar al repositorio datos de planta, exportaciones, capturas con información real ni modelos entrenados con datos reales. Las tablas locales de datos y los artefactos de modelos están excluidos por `.gitignore`; el lector del dashboard no los carga.
