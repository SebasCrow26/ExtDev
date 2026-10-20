# Parámetros del proyecto

**Generado automáticamente desde `config/config.yaml` con `python tools/generar_diccionario.py`. No se edita a mano: se cambia el valor en `config/config.yaml`.**

Tipos de parámetro: **dato de Clarios** (viene de Clarios), **SUPUESTO** (decisión sin confirmación de Clarios; trae una advertencia de lo que no se puede concluir), **metodológico** (decisión técnica de análisis) y **técnico** (ruta o formato).

Los **supuestos** son lo primero que hay que revisar si Clarios aporta información nueva:

- `turnos`: Clarios no entregó el calendario de turnos ni el de paradas. Toda cifra por turno depende de este supuesto. Los tres turnos deben durar 8 horas (el contrato de datos lo supone).
- `unidades.contador_energia_a_kwh`: La unidad de los contadores no está confirmada por Clarios. Las razones frente a la base en RC (0.49 a 1.24) no la confirman por sí solas.
- `calendario.pais_festivos`: Es el calendario oficial del país, no el calendario laboral de Clarios (puede haber puentes, paradas o jornadas distintas).
- `modelado.procesos_asociados`: La producción de refinación queda repetida en tres procesos: no sumar producción entre procesos. Es solo una referencia; la relación estadística es débil (0.33 y 0.20 por semana).
- `modelado.operando_multiplo_p5`: Sin calendario de Clarios, `operando` se infiere del propio consumo: no usarlo como variable explicativa del consumo (fuga de información).
- `modelado.operando_fraccion_p95`: Igual que `operando_multiplo_p5`.
- `mapa_procesos`: La correspondencia exacta entre medidores y líneas no fue confirmada por Clarios. Los medidores de RC cubren entre el 49 % y el 124 % de lo que reporta la base mensual (mediana 62 %), así que no son todo el consumo de la planta.
- `semaforo.verde_hasta_pct`: Clarios no definió umbrales. Ajustar con el criterio de Clarios.
- `semaforo.amarillo_hasta_pct`: Clarios no definió umbrales. Ajustar con el criterio de Clarios.
- `alertas.turnos_consecutivos_exceso`: Umbral provisional del equipo, sin respaldo de Clarios.
- `modelos.fraccion_evitable`: No hay base para este valor. Cualquier ahorro calculado con él es un escenario, no un ahorro demostrado.

## turnos

| parámetro | valor | unidad | tipo | descripción | justificación | advertencia |
|---|---|---|---|---|---|---|
| `turnos` | `{"1": {"inicio": "06:00", "fin": "14:00"}, "2": {"inicio": "14:00", "fin": "22:00"}, "3": {"inicio": "22:00", "fin": "06:00"}}` | hora del día (HH:MM); la fecha de cada turno es la de su inicio | SUPUESTO | Horario de los tres turnos con que se agregan energía y producción. | El triturado arranca de golpe a las 6:00 y el ERP concentra los registros de producción a las 5, 13 y 21 horas, al cierre de cada turno. | Clarios no entregó el calendario de turnos ni el de paradas. Toda cifra por turno depende de este supuesto. Los tres turnos deben durar 8 horas (el contrato de datos lo supone). |

## tarifas

| parámetro | valor | unidad | tipo | descripción | justificación | advertencia |
|---|---|---|---|---|---|---|
| `tarifas.tarifa_kwh_cop` | `542.475` | COP por kWh | dato de Clarios | Costo del kWh para convertir energía en pesos. | Media simple de la tarifa mensual de Clarios de octubre de 2025 a julio de 2026 (10 meses, rango 523.28 a 568.46; data/clean/tarifa_kwh_mensual.csv). | No está ponderada por consumo y faltan agosto y septiembre de 2026. Solo se debe aplicar a energía del mismo alcance y periodo que la tarifa. |
| `tarifas.gas_cop_m3` | `1799.419` | COP por m3 | dato de Clarios | Costo del gas para convertir m3 en pesos. | Costo de la base de Clarios (hoja RC GAS) de enero a junio de 2026; de octubre a diciembre de 2025 fue 1681.7. | El gas del SCADA no es conciliable con la base de Clarios; no usar este costo para el gas total de la planta. |

## unidades

| parámetro | valor | unidad | tipo | descripción | justificación | advertencia |
|---|---|---|---|---|---|---|
| `unidades.contador_energia_a_kwh` | `0.001` | kWh por unidad del contador (1/1000, es decir, Wh a kWh) | SUPUESTO | Factor para convertir el acumulado de los contadores del SCADA a kWh. | Evidencia indirecta. En F&A, julio de 2026 da una razón de 0.95 a 0.97 frente a la base de Clarios. Si fuera GW (como informó Gabriel Castro), el consumo mensual sería unas 10^6 veces mayor. | La unidad de los contadores no está confirmada por Clarios. Las razones frente a la base en RC (0.49 a 1.24) no la confirman por sí solas. |
| `unidades.erp_a_normalizada` | `{"UN": "unidades", "KG": "kg", "L": "litros", "M3": "m3"}` | código de unidad del ERP a unidad normalizada | metodológico | Traducción de las unidades de medida del ERP a las unidades de las tablas. | Son los códigos que aparecen en el archivo de transacciones del ERP. |  |

## calidad

| parámetro | valor | unidad | tipo | descripción | justificación | advertencia |
|---|---|---|---|---|---|---|
| `calidad.cobertura_minima` | `0.75` | fracción de las horas del turno con dato válido | metodológico | Por debajo de esta cobertura el consumo del turno no se modela ni se reescala. | Permite hasta 2 horas inválidas en un turno de 8; con menos datos, reescalar a cobertura completa añade demasiado sesgo. |  |
| `calidad.umbral_salto_x_p99` | `20` | veces el percentil indicado del consumo horario del medidor | metodológico | Un incremento del contador mayor a este múltiplo se trata como salto (dato no confiable). | Deja pasar variaciones normales del proceso y marca saltos de un orden de magnitud; no se han visto saltos entre 5 y 20 veces. |  |
| `calidad.percentil_salto` | `0.99` | fracción (percentil) | metodológico | Percentil de los incrementos horarios positivos sobre el que se mide el umbral de salto. | Robusto a unos pocos valores extremos. |  |
| `calidad.umbral_hueco_interpolable_horas` | `1.5` | horas entre lecturas | metodológico | Un intervalo entre lecturas mayor a este valor se marca como hueco (interpolado, estimado o faltante). | El paso nominal del SCADA es 1 hora; 1.5 deja tolerancia por el corrimiento del minuto de lectura. |  |
| `calidad.max_horas_interpolar` | `6` | horas | metodológico | Los huecos de lectura más largos que esto quedan como faltantes en lugar de repartirse linealmente. | Un reparto lineal de hasta 6 horas distorsiona poco un turno; más allá se perdería la forma del consumo. |  |
| `calidad.min_intervalos_congelado` | `3` | intervalos horarios seguidos | metodológico | Horas seguidas con TODOS los medidores de proceso sin cambiar para declarar el SCADA congelado. | Con medidores acumulados de energía, que ninguno cambie durante 3 horas seguidas es muy improbable en operación normal. |  |
| `calidad.cobertura_mes_completo` | `0.98` | fracción de las horas posibles del mes | metodológico | Un mes se considera completo para conciliar con la base de Clarios si tiene al menos esta fracción de horas. | Excluye los meses de los extremos del archivo, que están incompletos. |  |

## rachas

| parámetro | valor | unidad | tipo | descripción | justificación | advertencia |
|---|---|---|---|---|---|---|
| `rachas.factor_recuperacion_p99` | `1.5` | veces el percentil 99 del consumo horario del medidor | metodológico | Tras una racha sin cambio, si el primer incremento del contador supera este múltiplo, la energía acumulada reapareció de golpe: el SCADA se congeló y el medidor siguió contando. | Una sola hora de operación normal no supera el percentil 99 del propio medidor; los incrementos de reaparición observados son de 4 a 30 veces ese percentil, así que 1.5 deja un margen amplio sin confundir una reanudación normal. | Si el incremento posterior es menor que este umbral no se puede distinguir un congelamiento corto de un paro real: la racha queda sin corregir. |
| `rachas.corregir_congelamiento_por_medidor` | `1` | 1 = sí, 0 = no | metodológico | Si vale 1, una racha de un medidor con reaparición de energía se marca como estimada y se reparte (igual que el congelamiento de toda la planta); si vale 0 solo se clasifica. | Sin esta corrección, las horas congeladas salen con consumo cero marcado como válido y toda la energía acumulada cae en una o dos horas posteriores. | El reparto es uniforme en el periodo: sirve para totales diarios o mensuales, no para análisis por hora o por turno (las horas estimadas se excluyen de los turnos). |
| `rachas.razon_recuperacion_alta_min` | `0.5` | fracción de la energía esperada en el periodo | metodológico | Confianza alta en un congelamiento: la energía que reaparece es al menos esta fracción de lo que consumiría el medidor, en promedio, en el mismo periodo. | Si reaparece una parte importante de lo esperado, el contador sí siguió acumulando. El valor de referencia (promedio de ±14 días) incluye paros, por eso se acepta desde 0.5. |  |
| `rachas.razon_recuperacion_alta_max` | `2.0` | veces la energía esperada en el periodo | metodológico | Confianza alta en un congelamiento: la energía que reaparece no excede este múltiplo de lo esperado. | Una reaparición mucho mayor a lo esperado sugiere que además hubo un salto o un reinicio, y la confianza baja a media. |  |
| `rachas.fraccion_medidores_quietos` | `0.8` | fracción de los medidores de proceso de la planta | metodológico | Una racha afecta a toda la planta si al menos esta fracción de los medidores de proceso estuvo sin cambio durante la racha. | Con 7 medidores en RC, 0.8 exige 6; con 3 en F&A exige 3. Permite que un medidor de consumo mínimo se mueva sin ocultar un congelamiento general. |  |
| `rachas.actividad_planta_activa` | `0.5` | fracción del consumo típico de los demás medidores | metodológico | Sin reaparición de energía, si los demás medidores consumen al menos esta fracción de lo típico, la planta estaba operando y la racha de un medidor es sospechosa. | Separa un paro real de la planta (todos bajan) de un medidor aislado sin variación (apagado, atascado o sin transmitir). | Con un contador acumulado no se puede distinguir un consumo cero real de un medidor atascado sin reaparición posterior; se reporta como indeterminado. |
| `rachas.umbral_bajo_consumo_kwh_h` | `5` | kWh por hora (promedio típico del medidor) | metodológico | Un medidor cuyo consumo horario típico es menor a este valor puede quedar sin cambio varias horas por la resolución del contador o consumo de reposo. | REFINO_2 promedia 0.2 a 1.2 kWh/h (percentil 95: 2.8) frente a 14 kWh/h o más en los demás medidores de RC; 49 de sus 51 rachas de 6 h o más duran menos de 48 horas. | Es un criterio por orden de magnitud y no por especificación del medidor; la resolución real del contador no está confirmada por Clarios. |
| `rachas.max_horas_bajo_consumo` | `48` | horas | metodológico | Las rachas sin cambio de un medidor de bajo consumo que duran más que esto se tratan como sospechosas, no como comportamiento normal. | El comportamiento normal observado de REFINO_2 llega a 44 horas; una racha de 559 horas (23 días) no se explica por la resolución del contador. |  |
| `rachas.ventana_referencia_dias` | `14` | días a cada lado de la racha | metodológico | Ventana para calcular el consumo típico del medidor alrededor de una racha (sin contar la racha). | Dos semanas a cada lado cubren dos ciclos semanales de operación y paros. | El promedio incluye horas de paro, así que subestima el consumo en operación; la razón de reaparición se interpreta como orden de magnitud. |

## produccion

| parámetro | valor | unidad | tipo | descripción | justificación | advertencia |
|---|---|---|---|---|---|---|
| `produccion.dias_desfase_fecha_efectiva` | `2` | días | metodológico | Una transacción registrada con esta diferencia o más respecto de su fecha efectiva se asigna a la fecha efectiva. | El 83 % de las diferencias es de un día y corresponde a transacciones de la noche (el ERP les pone el día siguiente); los registros tardíos reales son de 2 días o más. |  |
| `produccion.prefijos_planta` | ver `config/config.yaml` | prefijo del código de línea a planta | metodológico | Planta de las líneas que no están en el mapa de líneas de Clarios. | Replica la convención de nombres de los códigos de línea del ERP. El mapa de Clarios tiene prioridad. |  |

## gas

| parámetro | valor | unidad | tipo | descripción | justificación | advertencia |
|---|---|---|---|---|---|---|
| `gas.hueco_estimado_horas` | `36` | horas entre lecturas | metodológico | Un hueco de lecturas de gas mayor a esto marca los días de su interior como estimados. | Las lecturas son diarias; 36 horas permite un día de retraso sin marcar estimación. |  |
| `gas.tolerancia_medianoche_s` | `5` | segundos | metodológico | Las lecturas diarias caen unos segundos antes o después de la medianoche; se tratan como si fueran a la medianoche. | Las lecturas del SCADA llegan hasta 3 segundos de diferencia con la medianoche. |  |

## calendario

| parámetro | valor | unidad | tipo | descripción | justificación | advertencia |
|---|---|---|---|---|---|---|
| `calendario.pais_festivos` | `"CO"` | código de país de la librería holidays | SUPUESTO | Calendario de festivos con que se calcula `es_festivo`. | Las plantas están en Colombia. | Es el calendario oficial del país, no el calendario laboral de Clarios (puede haber puentes, paradas o jornadas distintas). |

## modelado

| parámetro | valor | unidad | tipo | descripción | justificación | advertencia |
|---|---|---|---|---|---|---|
| `modelado.procesos_asociados` | `{"filtros": "refinacion", "ptari": "refinacion"}` | proceso sin línea de producción propia a proceso cuya producción se le asocia | SUPUESTO | Los procesos de apoyo sin línea en el ERP reciben la producción de refinación. | No tienen línea propia en el mapa de Clarios; su consumo es casi constante. | La producción de refinación queda repetida en tres procesos: no sumar producción entre procesos. Es solo una referencia; la relación estadística es débil (0.33 y 0.20 por semana). |
| `modelado.operando_multiplo_p5` | `3` | veces el percentil 5 del consumo del proceso | SUPUESTO | Primer criterio de `operando`; el consumo del turno debe superar el mayor entre este criterio y el siguiente. | Separa el consumo en reposo del consumo en operación en los procesos que se apagan. | Sin calendario de Clarios, `operando` se infiere del propio consumo: no usarlo como variable explicativa del consumo (fuga de información). |
| `modelado.operando_fraccion_p95` | `0.1` | fracción del percentil 95 del consumo del proceso | SUPUESTO | Segundo criterio de `operando`. | Evita tomar como operación un consumo residual cuando el percentil 5 es casi cero. | Igual que `operando_multiplo_p5`. |

## eda

| parámetro | valor | unidad | tipo | descripción | justificación | advertencia |
|---|---|---|---|---|---|---|
| `eda.kmeans_k` | `4` | número de regímenes | metodológico | Grupos del clustering exploratorio de regímenes de operación. | Con 4 grupos se obtiene una lectura clara (parada, reducido, normal, alto); el silhouette es moderado (0.31). |  |
| `eda.semilla` | `0` | semilla aleatoria | técnico | Semilla de las partes aleatorias del análisis exploratorio, para que sea reproducible. | Resultados idénticos en cada ejecución. |  |
| `eda.contaminacion_isolation_forest` | `0.02` | fracción de turnos marcados como anómalos | metodológico | Proporción esperada de anomalías del Isolation Forest. | Marca los turnos más extremos sin llenar el informe de falsos positivos. |  |
| `eda.n_anomalias_candidatas` | `25` | turnos | metodológico | Cuántos turnos candidatos a anomalía se listan. | Lista corta y revisable a mano. |  |
| `eda.piso_mad_kwh` | `1.0` | kWh | metodológico | Constante sumada a la desviación absoluta mediana para no dividir por cero en procesos casi constantes. | Un kWh es despreciable frente a los consumos de los procesos. |  |

## mapa_procesos

| parámetro | valor | unidad | tipo | descripción | justificación | advertencia |
|---|---|---|---|---|---|---|
| `mapa_procesos` | ver `config/config.yaml` | relación entre proceso, medidores del SCADA y líneas del ERP | SUPUESTO | Mapa de procesos de modelado. Los nombres de líneas salen del mapa de Clarios; la relación con los medidores es una decisión del equipo. | Cada medidor de proceso se asocia al proceso que lo nombra. Refinación suma dos medidores y tres líneas. | La correspondencia exacta entre medidores y líneas no fue confirmada por Clarios. Los medidores de RC cubren entre el 49 % y el 124 % de lo que reporta la base mensual (mediana 62 %), así que no son todo el consumo de la planta. |

## semaforo

| parámetro | valor | unidad | tipo | descripción | justificación | advertencia |
|---|---|---|---|---|---|---|
| `semaforo.verde_hasta_pct` | `5` | porcentaje de exceso sobre lo esperado | SUPUESTO | Hasta este exceso el indicador del dashboard es verde. | Umbral provisional del equipo. | Clarios no definió umbrales. Ajustar con el criterio de Clarios. |
| `semaforo.amarillo_hasta_pct` | `10` | porcentaje de exceso sobre lo esperado | SUPUESTO | Hasta este exceso es amarillo; por encima, rojo. | Umbral provisional del equipo. | Clarios no definió umbrales. Ajustar con el criterio de Clarios. |

## alertas

| parámetro | valor | unidad | tipo | descripción | justificación | advertencia |
|---|---|---|---|---|---|---|
| `alertas.turnos_consecutivos_exceso` | `2` | turnos seguidos | SUPUESTO | Turnos seguidos con exceso para disparar la alerta de exceso sostenido. | Evita alertar por un solo turno atípico. | Umbral provisional del equipo, sin respaldo de Clarios. |

## modelos

| parámetro | valor | unidad | tipo | descripción | justificación | advertencia |
|---|---|---|---|---|---|---|
| `modelos.inicio_entrenamiento` | `"2025-10-01"` | fecha | metodológico | Inicio del periodo de entrenamiento de los modelos. | Primer día con producción del ERP. |  |
| `modelos.fin_entrenamiento` | `"2026-06-30"` | fecha | metodológico | Fin del periodo de entrenamiento. | Reserva julio a septiembre de 2026 para probar con datos que el modelo no vio. |  |
| `modelos.inicio_prueba` | `"2026-07-01"` | fecha | metodológico | Inicio del periodo de prueba. | Separación por tiempo, nunca aleatoria. |  |
| `modelos.fin_prueba` | `"2026-09-30"` | fecha | metodológico | Fin del periodo de prueba. | Último día con producción del ERP. |  |
| `modelos.fraccion_evitable` | `0.5` | fracción del exceso | SUPUESTO | Parte del exceso de consumo que se considera evitable para estimar ahorro potencial. | Relleno sin respaldo; solo permite construir un escenario. | No hay base para este valor. Cualquier ahorro calculado con él es un escenario, no un ahorro demostrado. |
| `modelos.percentil_meta` | `25` | percentil del kWh por unidad | metodológico | Percentil histórico que se usa como meta cuando Clarios no entrega una. | Representa un buen desempeño alcanzable según el propio historial. |  |
| `modelos.horizonte_pronostico_dias` | `7` | días después del último dato | metodológico | Cuántos días hacia adelante se pronostica el consumo por proceso y escenario. | Una semana cubre los dos días de fin de semana y alcanza para el tablero; más allá, sin un plan de producción de Clarios, solo se repetiría el supuesto. | La producción supuesta de cada día es el promedio del mismo día de la semana en las últimas 4 semanas por un factor de escenario (0.85, 1.0, 1.15); no es un plan de Clarios. |

## rutas

| parámetro | valor | unidad | tipo | descripción | justificación | advertencia |
|---|---|---|---|---|---|---|
| `rutas.datos_reales` | `"data/clean"` | ruta relativa a la raíz del repositorio | técnico | Carpeta de las tablas limpias. | Convención del proyecto. |  |
| `rutas.datos_ejemplo` | `"datos_simulados"` | ruta relativa a la raíz del repositorio | técnico | Carpeta de los datos de ejemplo (sintéticos). | Convención del proyecto. |  |
