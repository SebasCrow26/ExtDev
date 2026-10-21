# Entregables Clarios – Catch Consulting

Dashboard, presentación, documentación y modelos del reto de consumo de energía de Clarios.

| Carpeta | Qué hay |
|---|---|
| `dashboard/` | Dashboard en Streamlit con la página de **monitoreo en vivo**, sus tablas de datos simulados (`datos_simulados/`) y su configuración (`config.yaml`). |
| `modelos/` | Modelos de consumo esperado ya entrenados (`modelos.pkl`) y la función `predecir`. |
| `documentacion/` | Contrato de datos, diccionario, parámetros, glosario, supuestos y limitaciones. |
| `presentacion/` | Material de la presentación. |

## Cómo correr el dashboard

```bash
pip install -r dashboard/requirements.txt
streamlit run dashboard/pagina_monitoreo.py
```

Con **Iniciar**, cada 5 segundos llegan las lecturas de una o más horas del SCADA (inventadas). Se limpian con las reglas del proyecto (reinicios de contador y congelamientos), se cierra cada turno, se compara con el consumo esperado del modelo y se actualizan el semáforo y las alertas. Se pueden inyectar eventos (exceso sostenido, parada, congelamiento, reinicio) o usar el guion de la demostración.

## Datos

Las tablas de `dashboard/datos_simulados/` son **simuladas**: tienen el mismo esquema que las de Clarios, pero son inventadas. Los datos reales no están en este repositorio. Para verlos en local se copian las tablas a `dashboard/data/clean/` (carpeta ignorada por Git) y el dashboard las usa en lugar de las simuladas.

Los modelos se entrenaron una sola vez con los datos de Clarios y no se reentrenan.

## Uso de IA

Parte del código y de los documentos se desarrolló con ayuda de Claude (Anthropic). El equipo lo revisó y lo probó.

## Pendiente de confirmar con Clarios

Las unidades de los contadores y el calendario de turnos (ver `documentacion/04_supuestos_y_limitaciones.md`).
