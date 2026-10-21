# Contrato de datos

**El contrato legible por máquina es `contrato_datos.yaml` (repositorio de trabajo)** (tipos, unidades, claves, rangos, continuidad, procedencia y consumidores de cada tabla). De él se genera `documentacion/12_diccionario_datos.md` (`python tools/generar_diccionario.py`, que también genera `documentacion/13_parametros.md` desde `dashboard/config.yaml`) y lo usa el validador (`python tools/validar_contrato.py`, con pruebas en `tests/`). Este documento es la guía narrativa.

Este documento fija el formato de todas las tablas. "Datos" las produce en `dashboard/data/clean/`. "Modelos" y "Dashboard" las consumen. Los ejemplos sintéticos en `data/ejemplo/` ya cumplen este formato.

Formato de archivo: CSV UTF-8, separador coma, decimal con punto, fechas ISO, sin índice.

## Convenciones

- **Turnos (provisionales, por confirmar con Clarios):** turno 1 = 06:00 a 14:00, turno 2 = 14:00 a 22:00, turno 3 = 22:00 a 06:00. `fecha_turno` es la fecha en que **inicia** el turno (una transacción a las 03:00 del día 10 pertenece al turno 3 del día 9).
- **Unidades:** energía en **kWh**, gas en **m³**.
- **Moneda:** pesos colombianos (COP).
- **Hora local** de la planta. No hay cambio de horario de verano en Colombia.
- **Plantas:** `RC` (recicladora) y `F&A` (formación y acabado). Ensamble y OREC solo existen a nivel mensual en la base de Clarios.

## Tablas de entrada (las produce Datos)

### `mapa_procesos`
Relaciona medidores del SCADA con líneas del ERP.

| columna | tipo | descripción |
|---|---|---|
| planta | texto | RC o F&A |
| proceso_modelo | texto | triturado, horno, refinacion, filtros, ptari, formacion |
| medidores_scada | texto | medidores que se suman (separados por `;`) |
| lineas_erp | texto | líneas de producción que se suman (separadas por `;`) |
| unidad_produccion | texto | kg o unidades |
| nota | texto | supuesto o aclaración |

### `energia_hora`
Consumo por hora y medidor, ya convertido de contador acumulado a kWh.

| columna | tipo | descripción |
|---|---|---|
| hora_inicio | fecha-hora | inicio de la hora (`2026-03-15 07:00:00`) |
| planta | texto | |
| medidor | texto | nombre normalizado, por ejemplo TRITURADO, REFINO_1, RECTIFICADOR_1 |
| kwh | número | consumo de esa hora (vacío si el dato no es confiable) |
| calidad | texto | `ok`, `interpolado`, `estimado`, `faltante`, `salto` o `reinicio` |

Significado de `calidad`: **ok** = medido normalmente; **interpolado** = hueco corto repartido linealmente; **estimado** = el SCADA estuvo congelado (todos los medidores sin cambio) y el consumo acumulado se repartió de forma uniforme en el periodo (sirve para totales diarios o mensuales, **no** para análisis por hora o turno); **faltante** = hueco largo sin lecturas; **salto** = el contador subió de golpe más de lo normal; **reinicio** = el contador bajó. `kwh` va vacío en faltante, salto y reinicio.

### `energia_turno`
Igual que la anterior, agregada por turno. Solo suma horas `ok` e `interpolado` (las `estimado` no entran, para no meter en un turno consumo que en realidad se repartió de forma uniforme); por eso un turno dentro de un congelamiento sale con cobertura 0.

| columna | tipo | descripción |
|---|---|---|
| fecha_turno | fecha | |
| turno | entero | 1, 2 o 3 |
| planta | texto | |
| medidor | texto | |
| kwh | número | suma de horas válidas |
| horas_validas | entero | de 0 a 8 |
| cobertura | número | `horas_validas / 8` |

### `produccion_turno`
Producción neta del ERP (transacciones RCT-WO, descontando reversos).

| columna | tipo | descripción |
|---|---|---|
| fecha_turno | fecha | |
| turno | entero | |
| planta | texto | |
| linea_erp | texto | por ejemplo RCTRIT01, FAFORM02, ENSLIN01 |
| proceso_modelo | texto | vacío si la línea no tiene medidor |
| categoria_equs | texto | categoría de equivalente (SLI-S, TRUCK-B, etc.) |
| cantidad | número | producción neta |
| unidad | texto | kg o unidades |
| n_transacciones | entero | |
| n_fecha_ajustada | entero | transacciones registradas con 2 o más días de diferencia respecto a su fecha efectiva (se asignan a la fecha efectiva) |

La fecha y hora de la transacción es `Fecha` + `Tiempo` (no la fecha efectiva, porque el ERP pone como fecha efectiva el día siguiente a las transacciones de la noche). Los reversos (cantidad negativa) se restan en `cantidad`.

### `gas_dia`

| columna | tipo | descripción |
|---|---|---|
| fecha | fecha | |
| m3 | número | consumo del día |
| calidad | texto | `ok`, `estimado` o `reinicio` |

Es el gas de **refinación de RC**, de medianoche a medianoche. `ok` = medido entre dos lecturas válidas; `estimado` = el día cae en un hueco de más de 36 horas y se repartió de forma uniforme; `reinicio` = el acumulado se reinició ese día y solo se informa lo contado después (límite inferior). Empieza el 2 de agosto de 2026.

### `calendario_operacion`
Si el proceso estaba operando (inferido de producción y consumo, hasta que Clarios entregue el calendario real).

| columna | tipo | descripción |
|---|---|---|
| fecha_turno | fecha | |
| turno | entero | |
| planta | texto | |
| proceso_modelo | texto | |
| operando | 0 o 1 | |
| fuente | texto | `inferido` o `programado` |

### `dataset_modelo`
Tabla unificada: la que usa Modelos.

| columna | tipo | descripción |
|---|---|---|
| fecha_turno, turno, planta, proceso_modelo | | llaves |
| kwh | número | consumo del proceso (suma de sus medidores), **reescalado a cobertura completa** (`kwh_observado / cobertura`). Vacío si la cobertura es menor a `calidad.cobertura_minima` |
| kwh_observado | número | suma de las horas válidas, sin reescalar |
| produccion | número | producción neta asociada (kg para RC). 0 si no hubo transacciones |
| unidad | texto | |
| n_transacciones | entero | transacciones de producción en el turno |
| dia_semana | entero | 0 = lunes |
| es_fin_semana | 0 o 1 | |
| es_festivo | 0 o 1 | festivo en Colombia (librería `holidays`) |
| operando | 0 o 1 | **inferido de la energía** (no hay calendario real de Clarios): consumo del turno mayor a `max(3 x p5, 0.1 x p95)` del proceso. **No usar como variable explicativa del consumo** (se calcula con el mismo `kwh`) |
| cobertura | número | 0 a 1 (horas válidas de todos los medidores del proceso / 8) |
| calidad_ok | 0 o 1 | 1 si la cobertura es suficiente para modelar |

**Producción repetida:** en `filtros` y `ptari` la `produccion` es la de refinación (supuesto). No sumar `produccion` entre procesos.

**Tres niveles de agregación.** La producción de RC se reporta por lotes: en 60 a 80% de los turnos no hay transacciones. Por eso la relación entre energía y producción es débil por turno y fuerte por semana (ver `documentacion/03_especificacion_modelos.md`). Se entregan:

- `dataset_modelo`: por turno (`fecha_turno`, `turno`).
- `dataset_modelo_dia`: por día (`fecha`). Solo días con los 3 turnos.
- `dataset_modelo_semana`: por semana de lunes a domingo (`semana_inicio`). Solo semanas completas (21 turnos) dentro del periodo con producción (1 oct 2025 a 30 sep 2026).

Las tablas de día y semana traen `kwh`, `kwh_observado`, `produccion`, `unidad`, `n_transacciones`, `pct_turnos_operando`, `cobertura` y `calidad_ok`; la de día agrega `dia_semana`, `es_fin_semana` y `es_festivo`, y la de semana `dias_festivos` (cantidad de festivos en la semana).

### Tablas auxiliares de calidad (las produce Datos)

- `calidad_energia_rc`: por medidor, reinicios, saltos, congelamientos y horas por calidad.
- `congelamientos_energia_rc`: periodos en que el SCADA estuvo congelado (inicio, fin, horas y consumo acumulado).
- `validacion_energia_rc_mensual`: totales mensuales del SCADA contra la base mensual de Clarios.
- `calidad_energia_fa`, `congelamientos_energia_fa` y `validacion_energia_fa_mensual`: lo mismo para F&A (rectificadores).
- `rachas_constantes_energia`: rachas de 3 o más intervalos con el contador de un medidor sin cambio, clasificadas por lo que pasa después (la energía reaparece, la planta está parada o el medidor queda aislado), con confianza, evidencia y tratamiento (RC y F&A).
- `cobertura_energia_mensual`: por planta, mes y medidor, cobertura temporal (horas medidas) y fracción de energía medida frente a estimada; no extrapola las horas sin energía conocida.
- `dataset_modelo_gas_dia`: gas diario de refinación con la producción diaria de horno y refinación, día de la semana, festivo y `calidad_ok` (1 si el día es `ok`).
- `base_mensual_plantas`: series mensuales de Ensamble, OREC, F&A y RC desde la base de Clarios (kWh, producción equivalente, kWh por equivalente real y presupuesto, tarifa y costo total). Única fuente para Ensamble y OREC. Fechas corregidas por secuencia.
- `base_mensual_gas_rc`: gas mensual de RC de la base de Clarios.
- `tarifa_kwh_mensual`: costo del kWh de Clarios por mes (igual para todas las plantas).
- `metas_clarios`: presupuesto de kWh por equivalente de Clarios (Ensamble, OREC y F&A, año fiscal 2026).
- `regimen_operacion_rc`: régimen de operación de cada turno (parada, reducido, normal o alto), por clustering.
- `anomalias_candidatas_rc`: los 25 turnos más atípicos frente al patrón de su proceso, turno y día de la semana (desviación robusta).
- `calidad_produccion_erp`: por línea del ERP, transacciones, reversos, fechas ajustadas y filas sin categoría.

## Tablas de salida (las produce Modelos, las lee Dashboard)

### `resultados_modelo`

| columna | tipo | descripción |
|---|---|---|
| fecha_turno, turno, planta, proceso_modelo | | llaves |
| kwh_real | número | |
| kwh_esperado | número | lo que debió consumir según la producción |
| exceso_kwh | número | real menos esperado (puede ser negativo) |
| exceso_pct | número | exceso sobre lo esperado |
| puntaje_anomalia | número | de 0 a 1 |
| es_anomalia | 0 o 1 | |
| severidad | texto | `baja`, `media` o `alta` |
| costo_exceso_cop | número | `max(exceso_kwh, 0)` por la tarifa |
| confianza_modelo | texto | `alta`, `media` o `baja`: qué tanto confiar en `kwh_esperado` de ese proceso (ver `documentacion/modelos/03_modelo_esperado.md`). Con `baja`, tomar el exceso como indicativo |

### `pronostico`

| columna | tipo | descripción |
|---|---|---|
| fecha | fecha | |
| planta, proceso_modelo | | |
| escenario | texto | `base`, `bajo`, `alto` o `plan` |
| produccion_supuesta | número | |
| kwh_pronosticado | número | |
| kwh_inferior, kwh_superior | número | intervalo |

### `metas`

| columna | tipo | descripción |
|---|---|---|
| planta, proceso_modelo | | |
| meta_kwh_por_unidad | número | |
| fuente | texto | `clarios` o `historico_p25` |
| vigente_desde | fecha | |

### `pronostico_mensual_plantas`

Pronóstico mensual de consumo por planta contra el presupuesto de kWh por equivalente de Clarios (Ensamble y OREC, que solo existen a nivel mensual). Columnas: `planta`, `mes_pronosticado` (primer día del mes), `kwh_pronosticado`, `kwh_por_eq_pronosticado`, `presupuesto_kwh_por_eq` y `cumple_pronostico` (`Sí` o `No`).

## Entrega por etapas

1. **Día 1:** este contrato y los datos de ejemplo (listos).
2. **Día 2 o 3:** RC real (`energia_*`, `produccion_turno`, `dataset_modelo`).
3. **Después:** F&A y gas.
