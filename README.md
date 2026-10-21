# Entregables Clarios – ExtDev

Repositorio de demostración con un dashboard ejecutivo y una vista de monitoreo en vivo. Las observaciones cargadas por ambas aplicaciones son sintéticas y están en `dashboard/datos_simulados/`. El dashboard reutiliza el modelo preentrenado ya versionado en `modelos/modelos.pkl`.

| Carpeta | Contenido |
|---|---|
| `dashboard/` | Aplicaciones Streamlit, configuración, estilos y tablas sintéticas. |
| `modelos/` | API y artefacto de los modelos que requiere el dashboard. |
| `documentacion/` | Contrato, diccionario, supuestos y guía del dashboard. |
| `presentacion/` | Material de presentación. |

## Ejecutar

Desde la raíz del repositorio:

```powershell
pip install -r dashboard/requirements.txt
streamlit run dashboard/app.py
```

Esto abre el dashboard ejecutivo con las siete secciones. La vista de monitoreo en vivo se ejecuta por separado:

```powershell
streamlit run dashboard/pagina_monitoreo.py
```

En el monitor en vivo, **Iniciar** avanza la simulación y permite inyectar excesos, paradas, congelamientos y reinicios ficticios.

## Datos y privacidad

- El lector de tablas carga solo `dashboard/datos_simulados/`; no busca ni acepta datos desde `data/clean/`.
- `.gitignore` excluye carpetas locales de datos, secretos y archivos temporales.
- Las pantallas usan las tablas sintéticas como datos de entrada y cargan el estimador versionado en `modelos/modelos.pkl`. Ese artefacto fue entrenado previamente con datos de Clarios; contiene parámetros del modelo, no las tablas originales.
- Los valores, fechas y eventos del dashboard son demostrativos; no representan consumos, costos ni metas reales de Clarios.

Consulta [la guía sintética del dashboard](documentacion/17_guia_dashboard_sintetico.md) y [los supuestos de la demo](documentacion/04_supuestos_y_limitaciones.md).
