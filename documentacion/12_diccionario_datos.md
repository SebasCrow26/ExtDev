# Diccionario de datos

**Generado automáticamente desde `config/contrato_datos.yaml` con `python tools/generar_diccionario.py`. No se edita a mano.**
El contrato narrativo y las reglas de uso están en `documentacion/01_contrato_datos.md`; las cifras y su estado de validación, en `documentacion/11_cifras_verificadas.md`.

**Zona horaria:** Hora local de la planta, sin zona declarada por el SCADA (no hay cambio de horario en Colombia).

Tipos: `str` texto, `int` entero, `float` decimal, `bin` 0 o 1, `fecha` AAAA-MM-DD, `fechahora` AAAA-MM-DD HH:MM:SS, `mes` AAAA-MM, `bool` True o False.
Rango entre corchetes = límite duro (un valor fuera es un error); "plausible" = advertencia.

## `mapa_procesos`

Relación entre procesos de modelado, medidores del SCADA y líneas de producción del ERP.

| propiedad | valor |
|---|---|
| clase de dato | depurado: datos depurados (derivados de una fuente original sin cambiar su significado) |
| fuente | Mapa de líneas de Clarios (Comparativo lineas.xlsx) y nombres de medidores del SCADA |
| script | `src/datos/01_energia_scada.py` |
| granularidad | sin granularidad temporal fija |
| clave | `planta`, `proceso_modelo` |
| consumidores | Modelos, Dashboard |

| columna | tipo | unidad | nulos | rango | valores permitidos | descripción |
|---|---|---|---|---|---|---|
| `planta` | str |  | no |  | RC, F&A |  |
| `proceso_modelo` | str |  | no |  |  |  |
| `medidores_scada` | str |  | sí |  |  | medidores que se suman, separados por punto y coma |
| `lineas_erp` | str |  | sí |  |  |  |
| `unidad_produccion` | str |  | sí |  | kg, unidades |  |
| `nota` | str |  | sí |  |  |  |

## `energia_hora`

Consumo eléctrico por hora y medidor, convertido de contador acumulado a kWh.

| propiedad | valor |
|---|---|
| clase de dato | depurado: datos depurados (derivados de una fuente original sin cambiar su significado) |
| fuente | SCADA (Energía RC y F&A), contadores acumulados en Wh (supuesto) |
| script | `src/datos/01_energia_scada.py y 05_energia_fa.py` |
| granularidad | hora |
| clave | `hora_inicio`, `medidor` |
| consumidores | Dashboard, Auditoría |
| continuidad | sin huecos en `hora_inicio` (paso: horas, por planta, medidor) |
| nulos condicionados | `kwh` es nulo solo si `calidad` está en ['faltante', 'salto', 'reinicio'] |

| columna | tipo | unidad | nulos | rango | valores permitidos | descripción |
|---|---|---|---|---|---|---|
| `hora_inicio` | fechahora |  | no |  |  |  |
| `planta` | str |  | no |  | RC, F&A |  |
| `medidor` | str |  | no |  |  |  |
| `kwh` | float | kWh | sí | [0, 50000] plausible [-inf, 3000] |  |  |
| `calidad` | str |  | no |  | ok, interpolado, estimado, faltante, salto, reinicio |  |

## `energia_turno`

Energía por turno y medidor. Solo suma horas ok e interpoladas; las estimadas no entran.

| propiedad | valor |
|---|---|
| clase de dato | agregado: datos agregados (suma por turno u otro nivel) |
| fuente | energia_hora |
| script | `src/datos/01_energia_scada.py y 05_energia_fa.py` |
| granularidad | turno (fecha de inicio del turno) |
| clave | `fecha_turno`, `turno`, `planta`, `medidor` |
| consumidores | Modelos, Dashboard |
| continuidad | sin huecos en `fecha_turno` (paso: turnos, por planta, medidor) |

| columna | tipo | unidad | nulos | rango | valores permitidos | descripción |
|---|---|---|---|---|---|---|
| `fecha_turno` | fecha |  | no |  |  |  |
| `turno` | int |  | no | [1, 3] |  |  |
| `planta` | str |  | no |  | RC, F&A |  |
| `medidor` | str |  | no |  |  |  |
| `kwh` | float | kWh | sí | [0, +inf] plausible [-inf, 30000] |  |  |
| `horas_validas` | int |  | no | [0, 8] |  |  |
| `cobertura` | float |  | no | [0, 1] |  |  |

## `produccion_turno`

Producción neta del ERP (transacciones RCT-WO) por turno y línea; la cantidad ya descuenta los reversos.

| propiedad | valor |
|---|---|
| clase de dato | agregado: datos agregados (suma por turno u otro nivel) |
| fuente | ERP (Explorar transacciones por artículo) y mapa de líneas |
| script | `src/datos/02_produccion_erp.py` |
| granularidad | turno |
| clave | `fecha_turno`, `turno`, `planta`, `linea_erp`, `proceso_modelo`, `categoria_equs`, `unidad` |
| consumidores | Modelos, Dashboard |

| columna | tipo | unidad | nulos | rango | valores permitidos | descripción |
|---|---|---|---|---|---|---|
| `fecha_turno` | fecha |  | no |  |  |  |
| `turno` | int |  | no | [1, 3] |  |  |
| `planta` | str |  | no |  | RC, F&A, OREC, Ensamble, Componentes, Sin_planta |  |
| `linea_erp` | str |  | no |  |  |  |
| `proceso_modelo` | str |  | sí |  |  |  |
| `categoria_equs` | str |  | no |  |  |  |
| `cantidad` | float |  | no | plausible [0, +inf] |  | puede ser negativa si hay reversos mayores que la producción del turno |
| `unidad` | str |  | no |  | unidades, kg, litros, m3, otra |  |
| `n_transacciones` | int |  | no | [1, +inf] |  |  |
| `n_fecha_ajustada` | int |  | no | [0, +inf] |  |  |

## `calendario_operacion`

Si cada proceso operaba en cada turno. Inferido de la energía, no es el calendario de Clarios.

| propiedad | valor |
|---|---|
| clase de dato | derivado: tabla analítica derivada |
| fuente | dataset_modelo (kwh) |
| script | `src/datos/03_dataset_modelo.py` |
| granularidad | turno |
| clave | `fecha_turno`, `turno`, `proceso_modelo` |
| consumidores | Modelos, Dashboard |
| continuidad | sin huecos en `fecha_turno` (paso: turnos, por proceso_modelo) |

| columna | tipo | unidad | nulos | rango | valores permitidos | descripción |
|---|---|---|---|---|---|---|
| `fecha_turno` | fecha |  | no |  |  |  |
| `turno` | int |  | no | [1, 3] |  |  |
| `planta` | str |  | no |  | RC, F&A |  |
| `proceso_modelo` | str |  | no |  |  |  |
| `operando` | bin |  | sí |  |  |  |
| `fuente` | str |  | no |  | inferido, programado |  |

## `dataset_modelo`

Energía y producción por proceso y turno. kwh está reescalado a cobertura completa.

| propiedad | valor |
|---|---|
| clase de dato | derivado: tabla analítica derivada |
| fuente | energia_turno, produccion_turno, mapa_procesos |
| script | `src/datos/03_dataset_modelo.py` |
| granularidad | turno |
| clave | `fecha_turno`, `turno`, `proceso_modelo` |
| consumidores | Modelos |
| continuidad | sin huecos en `fecha_turno` (paso: turnos, por proceso_modelo) |

| columna | tipo | unidad | nulos | rango | valores permitidos | descripción |
|---|---|---|---|---|---|---|
| `fecha_turno` | fecha |  | no |  |  |  |
| `turno` | int |  | no | [1, 3] |  |  |
| `planta` | str |  | no |  | RC, F&A |  |
| `proceso_modelo` | str |  | no |  |  |  |
| `kwh` | float | kWh | sí | [0, +inf] plausible [-inf, 30000] |  | reescalado: kwh_observado / cobertura |
| `kwh_observado` | float | kWh | no | [0, +inf] plausible [-inf, 30000] |  |  |
| `produccion` | float |  | no | plausible [0, +inf] |  | producción neta (kg o unidades según `unidad`). Puede ser negativa si un reverso se registra en un turno distinto al de la producción original; en filtros y ptari es la de refinación (supuesto) |
| `unidad` | str |  | no |  | kg, unidades |  |
| `n_transacciones` | int |  | no | [0, +inf] |  |  |
| `dia_semana` | int |  | no | [0, 6] |  |  |
| `es_fin_semana` | bin |  | no |  |  |  |
| `es_festivo` | bin |  | no |  |  |  |
| `operando` | bin |  | sí |  |  | inferido del mismo kwh: no usar como variable explicativa |
| `cobertura` | float |  | no | [0, 1] |  |  |
| `calidad_ok` | bin |  | no |  |  |  |

## `dataset_modelo_dia`

Energía y producción por proceso y día (solo días con los 3 turnos).

| propiedad | valor |
|---|---|
| clase de dato | derivado: tabla analítica derivada |
| fuente | dataset_modelo |
| script | `src/datos/03_dataset_modelo.py` |
| granularidad | día |
| clave | `fecha`, `proceso_modelo` |
| consumidores | Modelos |
| continuidad | sin huecos en `fecha` (paso: dias, por proceso_modelo) |

| columna | tipo | unidad | nulos | rango | valores permitidos | descripción |
|---|---|---|---|---|---|---|
| `fecha` | fecha |  | no |  |  |  |
| `planta` | str |  | no |  | RC, F&A |  |
| `proceso_modelo` | str |  | no |  |  |  |
| `kwh` | float | kWh | sí | [0, +inf] plausible [-inf, 90000] |  |  |
| `kwh_observado` | float | kWh | no | [0, +inf] plausible [-inf, 90000] |  |  |
| `produccion` | float |  | no | plausible [0, +inf] |  | producción neta; puede ser negativa si un reverso cae en otro periodo que la producción original |
| `unidad` | str |  | no |  | kg, unidades |  |
| `n_transacciones` | int |  | no | [0, +inf] |  |  |
| `dia_semana` | int |  | no | [0, 6] |  |  |
| `es_fin_semana` | bin |  | no |  |  |  |
| `es_festivo` | bin |  | no |  |  |  |
| `pct_turnos_operando` | float |  | sí | [0, 1] |  |  |
| `cobertura` | float |  | no | [0, 1] |  |  |
| `calidad_ok` | bin |  | no |  |  |  |

## `dataset_modelo_semana`

Energía y producción por proceso y semana de lunes a domingo (solo semanas completas de 21 turnos).

| propiedad | valor |
|---|---|
| clase de dato | derivado: tabla analítica derivada |
| fuente | dataset_modelo |
| script | `src/datos/03_dataset_modelo.py` |
| granularidad | semana |
| clave | `semana_inicio`, `proceso_modelo` |
| consumidores | Modelos |
| continuidad | sin huecos en `semana_inicio` (paso: semanas, por proceso_modelo) |

| columna | tipo | unidad | nulos | rango | valores permitidos | descripción |
|---|---|---|---|---|---|---|
| `semana_inicio` | fecha |  | no |  |  |  |
| `planta` | str |  | no |  | RC, F&A |  |
| `proceso_modelo` | str |  | no |  |  |  |
| `kwh` | float | kWh | sí | [0, +inf] |  |  |
| `kwh_observado` | float | kWh | no | [0, +inf] |  |  |
| `produccion` | float |  | no | plausible [0, +inf] |  | producción neta; puede ser negativa si un reverso cae en otro periodo que la producción original |
| `unidad` | str |  | no |  | kg, unidades |  |
| `n_transacciones` | int |  | no | [0, +inf] |  |  |
| `dias_festivos` | int |  | no | [0, 7] |  |  |
| `pct_turnos_operando` | float |  | sí | [0, 1] |  |  |
| `cobertura` | float |  | no | [0, 1] |  |  |
| `calidad_ok` | bin |  | no |  |  |  |

## `gas_dia`

Consumo diario de gas de refinación de RC, de medianoche a medianoche.

| propiedad | valor |
|---|---|
| clase de dato | depurado: datos depurados (derivados de una fuente original sin cambiar su significado) |
| fuente | SCADA Gas RC (acumulado en m3, se reinicia) |
| script | `src/datos/06_gas.py` |
| granularidad | día |
| clave | `fecha` |
| consumidores | Dashboard, Modelos |
| continuidad | sin huecos en `fecha` (paso: dias) |

| columna | tipo | unidad | nulos | rango | valores permitidos | descripción |
|---|---|---|---|---|---|---|
| `fecha` | fecha |  | no |  |  |  |
| `m3` | float | m3 | no | [0, +inf] plausible [-inf, 10000] |  |  |
| `calidad` | str |  | no |  | ok, estimado, reinicio |  |

## `dataset_modelo_gas_dia`

Gas diario con la producción diaria de horno y refinación.

| propiedad | valor |
|---|---|
| clase de dato | derivado: tabla analítica derivada |
| fuente | gas_dia, dataset_modelo_dia |
| script | `src/datos/06_gas.py` |
| granularidad | día |
| clave | `fecha` |
| consumidores | Modelos |
| continuidad | sin huecos en `fecha` (paso: dias) |

| columna | tipo | unidad | nulos | rango | valores permitidos | descripción |
|---|---|---|---|---|---|---|
| `fecha` | fecha |  | no |  |  |  |
| `m3` | float | m3 | no | [0, +inf] |  |  |
| `calidad` | str |  | no |  | ok, estimado, reinicio |  |
| `produccion_horno_kg` | float | kg | sí | [0, +inf] |  |  |
| `produccion_refinacion_kg` | float | kg | sí | [0, +inf] |  |  |
| `dia_semana` | int |  | no | [0, 6] |  |  |
| `es_fin_semana` | bin |  | no |  |  |  |
| `es_festivo` | bin |  | no |  |  |  |
| `calidad_ok` | bin |  | no |  |  |  |

## `base_mensual_plantas`

Series mensuales de Ensamble, OREC, F&A y RC de la base de Clarios (fechas reconstruidas por secuencia).

| propiedad | valor |
|---|---|
| clase de dato | referencia_clarios: cifras de referencia suministradas por Clarios (no recalculadas) |
| fuente | Base de datos.xlsx |
| script | `src/datos/08_base_mensual.py` |
| granularidad | mes |
| clave | `planta`, `mes` |
| consumidores | Dashboard, Modelos |
| continuidad | sin huecos en `mes` (paso: meses, por planta) |

| columna | tipo | unidad | nulos | rango | valores permitidos | descripción |
|---|---|---|---|---|---|---|
| `planta` | str |  | no |  | Ensamble, OREC, F&A, RC |  |
| `mes` | fecha |  | no |  |  |  |
| `kwh` | float | kWh | sí | [0, +inf] |  |  |
| `produccion_equivalente` | float |  | sí | [0, +inf] |  |  |
| `kwh_por_eq` | float |  | sí | [0, +inf] |  |  |
| `kwh_por_eq_presupuesto` | float |  | sí | [0, +inf] |  |  |
| `costo_kwh_cop` | float | COP/kWh | sí | [100, 2000] |  |  |
| `costo_total_cop` | float | COP | sí | [0, +inf] |  |  |

## `base_mensual_gas_rc`

Gas mensual de RC de la base de Clarios.

| propiedad | valor |
|---|---|
| clase de dato | referencia_clarios: cifras de referencia suministradas por Clarios (no recalculadas) |
| fuente | Base de datos.xlsx (hoja RC GAS) |
| script | `src/datos/08_base_mensual.py` |
| granularidad | mes |
| clave | `mes` |
| consumidores | Dashboard |
| continuidad | sin huecos en `mes` (paso: meses) |

| columna | tipo | unidad | nulos | rango | valores permitidos | descripción |
|---|---|---|---|---|---|---|
| `mes` | fecha |  | no |  |  |  |
| `m3` | float | m3 | sí | [0, +inf] |  |  |
| `produccion_equivalente` | float |  | sí | [0, +inf] |  |  |
| `m3_por_eq` | float |  | sí | [0, +inf] |  |  |
| `costo_m3_cop` | float | COP/m3 | sí | [0, +inf] |  |  |
| `costo_total_cop` | float | COP | sí | [0, +inf] |  |  |

## `tarifa_kwh_mensual`

Tarifa mensual del kWh reportada por Clarios (igual para todas las plantas). Tiene meses sin dato.

| propiedad | valor |
|---|---|
| clase de dato | referencia_clarios: cifras de referencia suministradas por Clarios (no recalculadas) |
| fuente | Base de datos.xlsx |
| script | `src/datos/08_base_mensual.py` |
| granularidad | mes |
| clave | `mes` |
| consumidores | Dashboard, Modelos |

| columna | tipo | unidad | nulos | rango | valores permitidos | descripción |
|---|---|---|---|---|---|---|
| `mes` | fecha |  | no |  |  |  |
| `costo_kwh_cop` | float | COP/kWh | no | [100, 2000] |  |  |

## `metas_clarios`

Presupuesto de kWh por equivalente de Clarios por planta y mes (la base trae también presupuestos por línea o proceso que no se guardan aquí, ver G6 de documentacion/11; no hay por turno).

| propiedad | valor |
|---|---|
| clase de dato | referencia_clarios: cifras de referencia suministradas por Clarios (no recalculadas) |
| fuente | Base de datos.xlsx |
| script | `src/datos/08_base_mensual.py` |
| granularidad | planta, periodo de vigencia |
| clave | `planta`, `vigente_desde` |
| consumidores | Dashboard, Modelos |

| columna | tipo | unidad | nulos | rango | valores permitidos | descripción |
|---|---|---|---|---|---|---|
| `planta` | str |  | no |  | Ensamble, OREC, F&A, RC |  |
| `kwh_por_eq_meta` | float | kWh/EQ | no | [0, +inf] |  |  |
| `vigente_desde` | fecha |  | no |  |  |  |
| `vigente_hasta` | fecha |  | no |  |  |  |
| `meses` | int |  | no | [1, +inf] |  |  |
| `fuente` | str |  | no |  |  |  |

## `regimen_operacion_rc`

Régimen de cada turno según un KMeans (k=4) sobre el consumo de los 5 procesos. Exploratorio; no es una categoría de Clarios.

| propiedad | valor |
|---|---|
| clase de dato | exploratorio: resultado exploratorio, no oficial |
| fuente | dataset_modelo |
| script | `src/datos/04_eda_rc.py` |
| granularidad | turno |
| clave | `fecha_turno`, `turno` |
| consumidores | Auditoría |

| columna | tipo | unidad | nulos | rango | valores permitidos | descripción |
|---|---|---|---|---|---|---|
| `fecha_turno` | fecha |  | no |  |  |  |
| `turno` | int |  | no | [1, 3] |  |  |
| `regimen` | str |  | no |  | parada, reducido, normal, alto |  |

## `anomalias_candidatas_rc`

Turnos más atípicos según desviación robusta (mediana y MAD por proceso, turno y día de la semana). Candidatas sin confirmar.

| propiedad | valor |
|---|---|
| clase de dato | exploratorio: resultado exploratorio, no oficial |
| fuente | dataset_modelo |
| script | `src/datos/04_eda_rc.py` |
| granularidad | sin granularidad temporal fija |
| clave | sin clave definida |
| consumidores | Auditoría |

| columna | tipo | unidad | nulos | rango | valores permitidos | descripción |
|---|---|---|---|---|---|---|
| `fecha_turno` | fecha |  | no |  |  |  |
| `turno` | int |  | no | [1, 3] |  |  |
| `proceso` | str |  | no |  |  |  |
| `kwh` | float | kWh | no | [0, +inf] |  |  |
| `kwh_tipico` | float | kWh | no | [0, +inf] |  |  |
| `z_robusto` | float |  | no |  |  |  |

## `calidad_energia_rc`

Resumen de calidad por medidor de RC (reinicios, saltos, horas por calidad).

| propiedad | valor |
|---|---|
| clase de dato | auditoria: tabla de auditoría de calidad |
| fuente | SCADA Energía RC |
| script | `src/datos/01_energia_scada.py` |
| granularidad | sin granularidad temporal fija |
| clave | `medidor` |
| consumidores | Auditoría |

| columna | tipo | unidad | nulos | rango | valores permitidos | descripción |
|---|---|---|---|---|---|---|
| `medidor` | str |  | no |  |  |  |
| `lecturas` | int |  | no | [0, +inf] |  |  |
| `reinicios` | int |  | no | [0, +inf] |  |  |
| `saltos` | int |  | no | [0, +inf] |  |  |
| `huecos_largos` | int |  | no | [0, +inf] |  |  |
| `huecos_interpolados` | int |  | no | [0, +inf] |  |  |
| `congelamientos_repartidos` | int |  | no | [0, +inf] |  |  |
| `umbral_salto_wh_por_intervalo` | float |  | sí | [0, +inf] |  |  |
| `horas_ok` | int |  | no | [0, +inf] |  |  |
| `horas_interpolado` | int |  | no | [0, +inf] |  |  |
| `horas_estimado` | int |  | no | [0, +inf] |  |  |
| `horas_faltante` | int |  | no | [0, +inf] |  |  |
| `horas_salto` | int |  | no | [0, +inf] |  |  |
| `horas_reinicio` | int |  | no | [0, +inf] |  |  |
| `horas_total` | int |  | no | [0, +inf] |  |  |
| `pct_horas_ok_o_interpoladas` | float |  | no | [0, 100] |  |  |

## `calidad_energia_fa`

Resumen de calidad por medidor de F&A.

| propiedad | valor |
|---|---|
| clase de dato | auditoria: tabla de auditoría de calidad |
| fuente | SCADA F&A |
| script | `src/datos/05_energia_fa.py` |
| granularidad | sin granularidad temporal fija |
| clave | `medidor` |
| consumidores | Auditoría |

| columna | tipo | unidad | nulos | rango | valores permitidos | descripción |
|---|---|---|---|---|---|---|
| `medidor` | str |  | no |  |  |  |
| `lecturas` | int |  | no | [0, +inf] |  |  |
| `reinicios` | int |  | no | [0, +inf] |  |  |
| `saltos` | int |  | no | [0, +inf] |  |  |
| `huecos_largos` | int |  | no | [0, +inf] |  |  |
| `huecos_interpolados` | int |  | no | [0, +inf] |  |  |
| `congelamientos_repartidos` | int |  | no | [0, +inf] |  |  |
| `umbral_salto_wh_por_intervalo` | float |  | sí | [0, +inf] |  |  |
| `horas_ok` | int |  | no | [0, +inf] |  |  |
| `horas_interpolado` | int |  | no | [0, +inf] |  |  |
| `horas_estimado` | int |  | no | [0, +inf] |  |  |
| `horas_faltante` | int |  | no | [0, +inf] |  |  |
| `horas_salto` | int |  | no | [0, +inf] |  |  |
| `horas_reinicio` | int |  | no | [0, +inf] |  |  |
| `horas_total` | int |  | no | [0, +inf] |  |  |
| `pct_horas_ok_o_interpoladas` | float |  | no | [0, 100] |  |  |

## `calidad_produccion_erp`

Por línea del ERP, transacciones, reversos, fechas ajustadas y filas sin categoría.

| propiedad | valor |
|---|---|
| clase de dato | auditoria: tabla de auditoría de calidad |
| fuente | ERP |
| script | `src/datos/02_produccion_erp.py` |
| granularidad | sin granularidad temporal fija |
| clave | `planta`, `linea_erp` |
| consumidores | Auditoría |

| columna | tipo | unidad | nulos | rango | valores permitidos | descripción |
|---|---|---|---|---|---|---|
| `planta` | str |  | no |  | RC, F&A, OREC, Ensamble, Componentes, Sin_planta |  |
| `linea_erp` | str |  | no |  |  |  |
| `transacciones` | int |  | no | [1, +inf] |  |  |
| `cantidad_neta` | float |  | no |  |  |  |
| `reversos` | int |  | no | [0, +inf] |  |  |
| `fecha_ajustada` | int |  | no | [0, +inf] |  |  |
| `sin_categoria` | int |  | no | [0, +inf] |  |  |

## `congelamientos_energia_rc`

Periodos en que los 7 medidores de proceso de RC no cambian a la vez durante 3 horas o más.

| propiedad | valor |
|---|---|
| clase de dato | auditoria: tabla de auditoría de calidad |
| fuente | SCADA Energía RC |
| script | `src/datos/01_energia_scada.py` |
| granularidad | sin granularidad temporal fija |
| clave | sin clave definida |
| consumidores | Auditoría, Dashboard |

| columna | tipo | unidad | nulos | rango | valores permitidos | descripción |
|---|---|---|---|---|---|---|
| `inicio` | fechahora |  | no |  |  |  |
| `fin` | fechahora |  | sí |  |  |  |
| `horas` | float |  | no | [0, +inf] |  |  |
| `consumo_acumulado_kwh` | float | kWh | sí | [0, +inf] |  |  |

## `congelamientos_energia_fa`

Periodos en que los 3 rectificadores de F&A no cambian a la vez durante 3 horas o más.

| propiedad | valor |
|---|---|
| clase de dato | auditoria: tabla de auditoría de calidad |
| fuente | SCADA F&A |
| script | `src/datos/05_energia_fa.py` |
| granularidad | sin granularidad temporal fija |
| clave | sin clave definida |
| consumidores | Auditoría, Dashboard |

| columna | tipo | unidad | nulos | rango | valores permitidos | descripción |
|---|---|---|---|---|---|---|
| `inicio` | fechahora |  | no |  |  |  |
| `fin` | fechahora |  | sí |  |  |  |
| `horas` | float |  | no | [0, +inf] |  |  |
| `consumo_acumulado_kwh` | float | kWh | sí | [0, +inf] |  |  |

## `rachas_constantes_energia`

Rachas de 3 intervalos o más en que el contador de un medidor de proceso no cambia, clasificadas por lo que ocurre después (la energía reaparece, la planta está parada o el medidor queda aislado), con su nivel de confianza y su tratamiento.

| propiedad | valor |
|---|---|
| clase de dato | auditoria: tabla de auditoría de calidad |
| fuente | SCADA Energía RC y SCADA F&A |
| script | `src/datos/01_energia_scada.py y src/datos/05_energia_fa.py` |
| granularidad | sin granularidad temporal fija |
| clave | `planta`, `medidor`, `inicio` |
| consumidores | Auditoría, Dashboard |

| columna | tipo | unidad | nulos | rango | valores permitidos | descripción |
|---|---|---|---|---|---|---|
| `planta` | str |  | no |  | RC, F&A |  |
| `medidor` | str |  | no |  |  |  |
| `inicio` | fechahora |  | no |  |  | última lectura antes de la racha |
| `fin` | fechahora |  | no |  |  | última lectura sin cambio (la lectura siguiente es la que muestra si la energía reaparece) |
| `horas` | float |  | no | [0, +inf] |  |  |
| `n_intervalos` | int |  | no | [1, +inf] |  |  |
| `kwh_tipico_hora` | float | kWh | sí | [0, +inf] |  | consumo promedio por intervalo del medidor en la ventana de referencia, sin contar la racha |
| `kwh_esperado_periodo` | float | kWh | sí | [0, +inf] |  | kwh_tipico_hora x (n_intervalos + 1): orden de magnitud, el promedio incluye horas de paro |
| `kwh_reaparecido` | float | kWh | sí |  |  | incremento del contador en el intervalo siguiente a la racha; vacío si la racha llega al final del archivo |
| `razon_reaparicion` | float |  | sí |  |  | kwh_reaparecido / kwh_esperado_periodo |
| `medidores_quietos_pct` | float |  | no | [0, 1] |  | fracción de los medidores de proceso de la planta sin cambio durante toda la racha |
| `actividad_otros` | float |  | sí | [0, +inf] |  | mediana, entre los demás medidores, de su energía en la racha sobre lo típico (0 = parados, 1 = normales) |
| `pct_horas_no_laborales` | float |  | no | [0, 1] |  | fracción de la racha en sábado, domingo o festivo (evidencia, no entra en la decisión) |
| `clasificacion` | str |  | no |  | congelamiento_scada_planta, congelamiento_scada_medidor, sin_consumo_planta, sin_consumo_parcial, constante_bajo_consumo, sin_variacion_planta_activa, sin_dato_posterior |  |
| `confianza` | str |  | no |  | alta, media, baja |  |
| `tratamiento` | str |  | no |  | medido, estimado_planta, estimado_medidor, estimado_parcial | medido: las horas quedan como están; estimado_planta y estimado_medidor: toda la racha se marca `estimado` y la energía acumulada se reparte; estimado_parcial: solo una parte de la racha cae en un congelamiento de planta y el resto queda como medido |
| `evidencia` | str |  | no |  |  |  |

## `cobertura_energia_mensual`

Cobertura temporal y de energía por planta, mes y medidor. La temporal cuenta horas medidas; la de energía solo compara la energía medida con la estimada (no extrapola las horas sin energía conocida).

| propiedad | valor |
|---|---|
| clase de dato | auditoria: tabla de auditoría de calidad |
| fuente | energia_hora |
| script | `src/datos/01_energia_scada.py y src/datos/05_energia_fa.py` |
| granularidad | mes |
| clave | `planta`, `mes`, `medidor` |
| consumidores | Auditoría, Dashboard |

| columna | tipo | unidad | nulos | rango | valores permitidos | descripción |
|---|---|---|---|---|---|---|
| `planta` | str |  | no |  | RC, F&A |  |
| `mes` | mes |  | no |  |  |  |
| `medidor` | str |  | no |  |  |  |
| `horas_posibles` | int |  | no | [672, 744] |  |  |
| `horas_con_dato` | int |  | no | [0, 744] |  |  |
| `horas_medidas` | int |  | no | [0, +inf] |  | calidad ok o interpolado |
| `horas_estimadas` | int |  | no | [0, +inf] |  | energía repartida tras un congelamiento |
| `horas_sin_energia` | int |  | no | [0, +inf] |  | faltante, salto o reinicio: la energía de esas horas no se conoce |
| `kwh_medido` | float | kWh | no | [0, +inf] |  |  |
| `kwh_estimado` | float | kWh | no | [0, +inf] |  |  |
| `cobertura_temporal` | float |  | no | [0, 1] |  | horas_medidas / horas_posibles |
| `fraccion_energia_medida` | float |  | sí | [0, 1] |  | kwh_medido / (kwh_medido + kwh_estimado); no incluye la energía de las horas sin energía conocida |

## `resultados_modelo`

Resultado del modelo de consumo esperado por turno y proceso (frente de Modelos). Solo turnos con calidad suficiente en dataset_modelo.

| propiedad | valor |
|---|---|
| clase de dato | derivado: tabla analítica derivada |
| fuente | dataset_modelo, tarifa_kwh_mensual y modelos de Joshua |
| script | `src/modelos/run_pipeline.py` |
| granularidad | sin granularidad temporal fija |
| clave | `fecha_turno`, `turno`, `proceso_modelo` |
| consumidores | Dashboard, Presentación |

| columna | tipo | unidad | nulos | rango | valores permitidos | descripción |
|---|---|---|---|---|---|---|
| `fecha_turno` | fecha |  | no |  |  |  |
| `turno` | int |  | no | [1, 3] |  |  |
| `planta` | str |  | no |  | RC, F&A |  |
| `proceso_modelo` | str |  | no |  |  |  |
| `kwh_real` | float | kWh | no | [0, +inf] |  | igual al `kwh` de dataset_modelo (reescalado a cobertura completa) |
| `kwh_esperado` | float | kWh | no | [0, +inf] |  | lo que debió consumir según la producción |
| `exceso_kwh` | float | kWh | no |  |  | real menos esperado; puede ser negativo |
| `exceso_pct` | float |  | sí |  |  | exceso sobre lo esperado, acotado a -100 y 200; vacío si lo esperado es cero |
| `puntaje_anomalia` | float |  | no | [0, 1] |  |  |
| `es_anomalia` | bin |  | no |  |  |  |
| `severidad` | str |  | no |  | baja, media, alta |  |
| `costo_exceso_cop` | float | COP | no | [0, +inf] |  | max(exceso_kwh, 0) por la tarifa del mes |
| `confianza_modelo` | str |  | no |  | alta, media, baja | qué tanto confiar en kwh_esperado de este proceso: alta si el modelo supera la línea base con R² de prueba de 0.5 o más, media si la iguala (a 0.05) con R² positivo, baja en otro caso |

## `pronostico`

Pronóstico de consumo por proceso y escenario de producción (frente de Modelos).

| propiedad | valor |
|---|---|
| clase de dato | derivado: tabla analítica derivada |
| fuente | modelos de Joshua |
| script | `src/modelos/run_pronostico_v2.py` |
| granularidad | sin granularidad temporal fija |
| clave | `fecha`, `proceso_modelo`, `escenario` |
| consumidores | Dashboard, Presentación |

| columna | tipo | unidad | nulos | rango | valores permitidos | descripción |
|---|---|---|---|---|---|---|
| `fecha` | fecha |  | no |  |  |  |
| `planta` | str |  | no |  | RC, F&A |  |
| `proceso_modelo` | str |  | no |  |  |  |
| `escenario` | str |  | no |  | base, bajo, alto, plan |  |
| `produccion_supuesta` | float |  | no | [0, +inf] |  |  |
| `kwh_pronosticado` | float | kWh | no | [0, +inf] |  |  |
| `kwh_inferior` | float | kWh | no | [0, +inf] |  |  |
| `kwh_superior` | float | kWh | no | [0, +inf] |  |  |

## `pronostico_mensual_plantas`

Pronóstico mensual de consumo por planta contra el presupuesto de kWh por equivalente de Clarios (frente de Modelos).

| propiedad | valor |
|---|---|
| clase de dato | derivado: tabla analítica derivada |
| fuente | base_mensual_plantas, metas_clarios y modelos de Joshua |
| script | `src/modelos/run_ensamble_orec.py` |
| granularidad | mes |
| clave | `planta`, `mes_pronosticado` |
| consumidores | Dashboard, Presentación |

| columna | tipo | unidad | nulos | rango | valores permitidos | descripción |
|---|---|---|---|---|---|---|
| `planta` | str |  | no |  |  |  |
| `mes_pronosticado` | fecha |  | no |  |  | primer día del mes pronosticado |
| `kwh_pronosticado` | float | kWh | no | [0, +inf] |  |  |
| `kwh_por_eq_pronosticado` | float |  | sí | [0, +inf] |  |  |
| `presupuesto_kwh_por_eq` | float |  | sí | [0, +inf] |  |  |
| `cumple_pronostico` | str |  | no |  | Sí, Si, No |  |

## `metas`

Metas de kWh por unidad producida por proceso (frente de Modelos); percentil 25 histórico cuando Clarios no definió una.

| propiedad | valor |
|---|---|
| clase de dato | derivado: tabla analítica derivada |
| fuente | dataset_modelo y modelos de Joshua |
| script | `src/modelos/run_pronostico_v2.py` |
| granularidad | sin granularidad temporal fija |
| clave | `planta`, `proceso_modelo`, `vigente_desde` |
| consumidores | Dashboard, Presentación |

| columna | tipo | unidad | nulos | rango | valores permitidos | descripción |
|---|---|---|---|---|---|---|
| `planta` | str |  | no |  | RC, F&A |  |
| `proceso_modelo` | str |  | no |  |  |  |
| `meta_kwh_por_unidad` | float |  | no | [0, +inf] |  |  |
| `fuente` | str |  | no |  | clarios, historico_p25 |  |
| `vigente_desde` | fecha |  | no |  |  |  |

## `validacion_energia_rc_mensual`

Totales mensuales del SCADA de RC contra la base de Clarios.

| propiedad | valor |
|---|---|
| clase de dato | auditoria: tabla de auditoría de calidad |
| fuente | energia_hora, base de Clarios |
| script | `src/datos/01_energia_scada.py` |
| granularidad | mes |
| clave | `mes` |
| consumidores | Auditoría |

| columna | tipo | unidad | nulos | rango | valores permitidos | descripción |
|---|---|---|---|---|---|---|
| `mes` | mes |  | no |  |  |  |
| `kwh_scada_7_procesos` | float | kWh | no | [0, +inf] |  |  |
| `kwh_estimado_por_cobertura` | float | kWh | sí | [0, +inf] |  |  |
| `horas_validas` | int |  | no | [0, +inf] |  |  |
| `horas_total` | int |  | no | [0, +inf] |  |  |
| `cobertura` | float |  | no | [0, 1] |  |  |
| `horas_estimadas_por_congelamiento` | int |  | no | [0, +inf] |  |  |
| `kwh_emcali_si_contador_en_wh` | float |  | sí | [0, +inf] |  |  |
| `kwh_edif_admon_si_contador_en_wh` | float |  | sí | [0, +inf] |  |  |
| `kwh_base_clarios` | float | kWh | sí | [0, +inf] |  |  |
| `ratio_scada_vs_base` | float |  | sí | [0, +inf] |  |  |
| `ratio_estimado_vs_base` | float |  | sí | [0, +inf] |  |  |
| `mes_completo` | bool |  | no |  |  |  |

## `validacion_energia_fa_mensual`

Totales mensuales del SCADA de F&A contra la base de Clarios (el único mes común es julio de 2026).

| propiedad | valor |
|---|---|
| clase de dato | auditoria: tabla de auditoría de calidad |
| fuente | energia_hora, base de Clarios |
| script | `src/datos/05_energia_fa.py` |
| granularidad | mes |
| clave | `mes` |
| consumidores | Auditoría |

| columna | tipo | unidad | nulos | rango | valores permitidos | descripción |
|---|---|---|---|---|---|---|
| `mes` | mes |  | no |  |  |  |
| `kwh_scada_3_rectificadores` | float | kWh | no | [0, +inf] |  |  |
| `horas_validas` | int |  | no | [0, +inf] |  |  |
| `horas_total` | int |  | no | [0, +inf] |  |  |
| `cobertura` | float |  | no | [0, 1] |  |  |
| `kwh_base_clarios` | float | kWh | sí | [0, +inf] |  |  |

