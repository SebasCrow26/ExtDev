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

Esto abre el dashboard con las siete secciones y, al final del menú, **Monitoreo en vivo** (también se puede abrir sola con `streamlit run dashboard/pagina_monitoreo.py`).

En el monitoreo en vivo, **Iniciar** hace que cada 5 segundos lleguen las lecturas de una o más horas del SCADA (inventadas). Se limpian con las reglas del proyecto (reinicios y congelamientos), se cierra cada turno, se compara con el consumo esperado del modelo y se actualizan el semáforo y las alertas. Permite inyectar excesos, paradas, congelamientos y reinicios, o usar el guion de la demostración.

### Con datos reales (solo en local)

Para ver las tablas reales de Clarios, se apunta la variable `CLARIOS_DATOS_REALES` a la carpeta con las tablas y se corre el dashboard:

```powershell
$env:CLARIOS_DATOS_REALES = "C:uta\las	ablas"
uta\las	ablas"
streamlit run dashboard/app.py
```

Las pantallas muestran entonces los datos reales y el monitoreo en vivo parte de la historia real; lo que llega después sigue siendo simulado. Un aviso arriba indica la fuente activa. Esa ventana no se debe compartir ni desplegar.

## Datos y privacidad

- Por defecto, y en cualquier despliegue público, el lector de tablas carga solo `dashboard/datos_simulados/`. Solo lee otra carpeta si se define `CLARIOS_DATOS_REALES` en la máquina local; las tablas reales no están en este repositorio.
- `.gitignore` excluye carpetas locales de datos, secretos y archivos temporales.
- Las pantallas usan las tablas sintéticas como datos de entrada y cargan el estimador versionado en `modelos/modelos.pkl`. Ese artefacto fue entrenado previamente con datos de Clarios; contiene parámetros del modelo, no las tablas originales.
- Con los datos simulados, los valores, fechas y eventos son demostrativos y no representan consumos, costos ni metas reales de Clarios.

Consulta [la guía sintética del dashboard](documentacion/17_guia_dashboard_sintetico.md) y [los supuestos de la demo](documentacion/04_supuestos_y_limitaciones.md).
