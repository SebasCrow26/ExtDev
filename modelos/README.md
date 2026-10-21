# Modelos

`modelos.pkl` trae los modelos de consumo esperado ya entrenados (uno por proceso y nivel: turno, día y semana; Huber o GradientBoosting, el que mejor resultó en la prueba), con el intervalo de cada uno. Se entrenaron una sola vez con los datos de Clarios y **no se reentrenan**.

`modelo_esperado_api.py` los usa:

```python
from modelos.modelo_esperado_api import predecir     # con la raíz del repositorio en el path
predecir("horno", 65000, planta="RC", nivel="dia", fecha="2026-10-01", produccion_t1=74000, produccion_t2=70000)
# -> {'kwh_esperado': ..., 'kwh_inferior': ..., 'kwh_superior': ..., 'modelo': ..., ...}
```

Procesos de RC: triturado, horno, refinacion, filtros y ptari. Si no se indican `produccion_t1` y `produccion_t2`, se asume que fueron iguales a `produccion`. El modelo no usa `operando` ni el régimen de operación (se calculan con el mismo consumo que se quiere explicar).
