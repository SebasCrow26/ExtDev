# Modelos de consumo esperado

El dashboard reutiliza `modelos.pkl` mediante `modelo_esperado_api.py`. Hay un modelo por proceso y nivel temporal; `predecir()` devuelve el consumo esperado y su intervalo.

La demo carga las observaciones de `dashboard/datos_simulados/`, pero el artefacto versionado fue entrenado previamente con datos de Clarios. Contiene parámetros ajustados, no las filas originales. Por eso, los resultados combinan entradas sintéticas con un modelo histórico y deben presentarse como demostración, no como validación de desempeño con datos sintéticos.

Ejemplo desde la raíz del repositorio:

```python
from modelos.modelo_esperado_api import predecir

resultado = predecir("horno", 65000, planta="RC", nivel="dia", fecha="2026-10-01")
```