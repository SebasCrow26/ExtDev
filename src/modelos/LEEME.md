# Carpeta de Modelos (Joshua)

**Objetivo:** estimar cuánta energía debería consumir cada proceso en cada turno, medir el exceso y su costo, detectar anomalías, pronosticar según un plan de producción y estimar el ahorro.

**Lee antes de empezar:** `docs/03_especificacion_modelos.md` (enfoque, evaluación y trampas de los datos), `docs/01_contrato_datos.md` (tablas de entrada y salida) y tu sección en `docs/00_plan_de_trabajo.md`.

## Entradas
`dataset_modelo` (de Sebastián, en `data/clean/`) y, mientras no llegue, la base mensual de Clarios y el SCADA sin limpiar en `data/raw/`. Para probar código: `data/ejemplo/`.

## Salidas (a `data/clean/`)
`resultados_modelo`, `pronostico`, `metas` (formatos en el contrato) y una función `predecir(proceso, produccion)` que el dashboard pueda usar.

**Antes de usar `predecir` en una copia nueva del repositorio hay que correr `python src/modelos/run_pipeline.py` (unos 30 segundos):** los modelos entrenados quedan en `data/interim/modelos.pkl`, que no se sube a GitHub. Sin eso `predecir` avisa qué hacer.

## Qué cubre y qué no (para el dashboard)
- `resultados_modelo` y `pronostico` son **solo de RC** (triturado, horno, refinación, filtros y ptari). F&A (formación) no entra porque el modelo se entrena con oct 2025 a jun 2026 y F&A solo tiene jul a sep 2026; su análisis está en `docs/modelos/fa_encendido.md` y su meta en `metas.csv`.
- `pronostico` cubre los **7 días** siguientes al último dato (`modelos.horizonte_pronostico_dias`), con la producción supuesta del mismo día de la semana.
- `resultados_modelo.confianza_modelo` (`alta`, `media`, `baja`) dice qué tanto confiar en `kwh_esperado` de cada proceso: por turno solo el horno supera claramente la línea base. Con `baja` el exceso es indicativo.
- El exceso se cita **neto** (exceso menos defecto), no como suma de turnos por encima de lo esperado: ver `docs/modelos/05_pronostico_y_ahorro.md`.

## Cómo ejecutar la pipeline completa

```bash
python src/modelos/run_pipeline.py
```

Ejecuta en orden, con `PYTHONIOENCODING=utf-8`:

1. `run_linea_base.py` (si no existe `data/interim/linea_base.pkl`) — línea base (proceso × turno × día) con sus métricas.
2. `run_modelo_v6.py` — regresión robusta Huber y GradientBoosting por proceso y nivel (turno/día/semana), **elige automáticamente el mejor modelo (✓) por celda (proceso × nivel)** según R² de la prueba, y genera `data/clean/resultados_modelo.csv`.
3. `run_anomalias_v2.py` — residuos robustos (MAD) + IsolationForest, severidad por costo del exceso.
4. `run_pronostico_v2.py` — `data/clean/pronostico.csv` y `data/clean/metas.csv` + ahorro potencial.
5. `run_evaluar.py` — reporte consolidado de métricas (`docs/modelos/evaluar.md`).

También puedes ejecutar cada script por separado.

## Scripts

| Script | Qué hace | Salidas principales |
|---|---|---|
| `run_linea_base.py` | Línea base (promedio proceso × turno × día de la semana) | `docs/modelos/02_linea_base.md`, `data/interim/linea_base.pkl` |
| `run_modelo_v6.py` | Modelo esperado (Huber o GBR, el mejor por celda) y resultados por turno | `data/clean/resultados_modelo.csv`, `docs/modelos/03_modelo_esperado.md`, `data/interim/modelos.pkl` |
| `run_anomalias_v2.py` | Anomalías (MAD + IsolationForest) y severidad por costo | `docs/modelos/04_anomalias.md`, `data/interim/anomalias.pkl` |
| `run_pronostico_v2.py` | Pronóstico (escenarios), metas (percentil 25 histórico) y ahorro potencial | `data/clean/pronostico.csv`, `data/clean/metas.csv`, `docs/modelos/05_pronostico_y_ahorro.md` |
| `run_evaluar.py` | Reporte de métricas consolidado (línea base vs modelo elegido) | `docs/modelos/evaluar.md` |
| `01_exploracion.py` | Exploración kWh–producción, consumo base, efecto calendario, desfase de producción | `docs/modelos/01_exploracion.md` |
| `comun_modelos.py` | Funciones compartidas: features, métricas (MAE/WAPE/R²), split temporal, z robusto | (módulo) |
| `fix_agregar_dia_v2.py`, `fix_agregar_semana.py` | Wrappers de `comun_modelos.agregar_dia` / `agregar_semana` que añaden las columnas de calendario (`es_festivo`, `es_fin_semana`, `dia_semana`) que exige `modelo_esperado_api.features` | (módulos) |
| `modelo_esperado_api.py` | API reutilizable: `features(tab, nivel)`, `predecir_modelo(m, X)`, `predecir(proceso, produccion, ...)` | (módulo) |
| `predecir.py` / `api_predecir.py` | Fachada simple para el dashboard | `predecir(proceso, produccion, ...)` |
| `test_modelos.py` | Pruebas unitarias de `predecir()` | (pruebas) |

**Versiones anteriores:** los scripts que reemplazó otro (`run_modelo_v2` a `v5`, `run_anomalias`, `run_pronostico`, `02_linea_base*`, `03_modelo_esperado`, `04_anomalias`, `05_pronostico_y_ahorro`, `evaluar`, `ejecutar_modelos`, `fix_agregar_dia`, `run_modelo_esperado`) están en `src/modelos/archivo/` solo como referencia histórica. Ya no se ejecutan: el pipeline es `run_pipeline.py`.

## Checklist (actualizado 14–15 oct)

- [x] 12 oct: exploración, línea base y métricas definidas
- [x] 13 oct: primer ajuste con `dataset_modelo` de RC v1
- [x] 14 oct: `resultados_modelo` de RC v1 entregado a Gabriel
- [x] 15 oct: `pronostico` y `metas`, e integración
- [x] 16 oct: F&A, ahorro potencial, caso real y reporte de métricas
- [x] 17 oct: función `predecir` y ajustes finales

## Modelos elegidos por celda (✓ = el que se usa en `resultados_modelo`)

Ver la tabla completa en `docs/modelos/03_modelo_esperado.md`. En resumen:

- **horno y triturado (turno/día):** GradientBoosting gana a Huber en R² de prueba.
- **refinacion (turno/día):** Huber gana a GradientBoosting en algunos niveles, GBR en otros; se documenta celda por celda.
- **semana (RC):** Huber es más estable que GBR en triturado y refinación; en horno GBR.
- **filtros y ptari (todos los niveles):** GBR domina; su R² sigue siendo bajo o negativo frente a la línea base (el consumo es casi constante y no depende de producción, como advierte la especificación).
- **F&A formación:** se documenta en `03_modelo_esperado.md`; la especificación recomienda modelar primero encendido/apagado.

**Regla de oro:** cuando ningún modelo supera la línea base en R² de prueba, se recomienda usar la **línea base** para ese proceso (Plan B de `docs/00_plan_de_trabajo.md`).

Usa `from src.comun.config import cargar_config, leer_tabla`. Tarifa, fracción evitable y fechas de entrenamiento y prueba están en `config/config.yaml`.
