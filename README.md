# Entregables Clarios – Catch Consulting

Repositorio con lo que se entrega a Clarios: **dashboard, presentación, documentación y modelos**. Los datos de este repositorio son **simulados**. Los datos reales de Clarios no se suben a Git.

## Qué hay

| Carpeta | Contenido |
|---|---|
| `dashboard/` | Dashboard (Streamlit). Lee las tablas con `src/comun/config.py::leer_tabla`. |
| `modelos/` | `modelos.pkl`: modelos de consumo esperado ya entrenados (no se reentrenan). |
| `documentacion/` | Contrato de datos, diccionario, parámetros, glosario, supuestos y limitaciones. |
| `presentacion/` | Material de la presentación. |
| `datos_simulados/` | 29 tablas inventadas con el mismo esquema que las reales. |
| `src/`, `config/`, `tools/`, `tests/` | Código, parámetros, herramientas y pruebas. |

## Datos reales y datos simulados

`leer_tabla` usa `data/clean/` si existe (datos reales cargados en local, ignorada por Git) y si no, `datos_simulados/`. Para forzar los simulados: variable de entorno `CLARIOS_USAR_EJEMPLO=1`.

Los simulados se regeneran con la misma lógica de limpieza del proyecto y una semilla fija:

```bash
python tools/simular_datos.py --salida ruta/de/salida
```

## Comprobaciones

```bash
python tools/validar_contrato.py --sin-raw          # valida las tablas contra el contrato
python -m unittest discover -s tests                # 75 pruebas
python tools/verificar_sin_datos_reales.py          # ningún archivo del repo es copia de los datos reales
```

## Uso de IA

Parte del código, de las pruebas y de los documentos se desarrolló con ayuda de Claude (Anthropic). Todo se revisó y se probó por el equipo.

## Pendiente de confirmar con Clarios

Que los modelos entrenados con los datos reales puedan entregarse, y las unidades de los contadores y el calendario de turnos (ver `documentacion/04_supuestos_y_limitaciones.md`).
