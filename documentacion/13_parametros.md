# Parametros de la demostracion sintetica

La configuracion de `dashboard/config.yaml` contiene supuestos tecnicos y valores ilustrativos para ejecutar las vistas con las tablas incluidas en `dashboard/datos_simulados/`.

Las tarifas, metas, umbrales, turnos y factores de conversion de esta copia son ficticios o metodologicos. No son parametros operativos ni financieros de Clarios. Cambiarlos solo afecta la demostracion sintetica.

El cargador del dashboard lee por defecto la carpeta `dashboard/datos_simulados/`. Solo en una maquina local, la variable de entorno `CLARIOS_DATOS_REALES` puede apuntar a otra carpeta con las tablas reales. No agregues al repositorio archivos de datos reales, exportaciones de planta ni credenciales. El unico artefacto entrenado con informacion de Clarios es `modelos/modelos.pkl`, que contiene parametros del modelo y no las filas originales.

## Ejecutar

Desde la raiz del repositorio:

```powershell
pip install -r dashboard/requirements.txt
streamlit run dashboard/app.py
```

La pagina de monitoreo en vivo se inicia por separado con `streamlit run dashboard/pagina_monitoreo.py`.