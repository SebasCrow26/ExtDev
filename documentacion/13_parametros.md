# Parametros de la demostracion sintetica

La configuracion de `dashboard/config.yaml` contiene supuestos tecnicos y valores ilustrativos para ejecutar las vistas con las tablas incluidas en `dashboard/datos_simulados/`.

Las tarifas, metas, umbrales, turnos y factores de conversion de esta copia son ficticios o metodologicos. No son parametros operativos ni financieros de Clarios. Cambiarlos solo afecta la demostracion sintetica.

El cargador del dashboard lee exclusivamente la carpeta `dashboard/datos_simulados/`. No agregues aqui archivos de `data/clean/`, exportaciones de planta, credenciales ni modelos serializados entrenados con informacion real.

## Ejecutar

Desde la raiz del repositorio:

```powershell
pip install -r dashboard/requirements.txt
streamlit run dashboard/app.py
```

La pagina de monitoreo en vivo se inicia por separado con `streamlit run dashboard/pagina_monitoreo.py`.