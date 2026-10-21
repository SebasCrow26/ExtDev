# Guia del dashboard sintetico

## Iniciar

Desde la raiz del repositorio instala `dashboard/requirements.txt` y ejecuta `streamlit run dashboard/app.py`. Para la simulacion de monitoreo en vivo usa `streamlit run dashboard/pagina_monitoreo.py`.

## Datos

Ambas aplicaciones consultan los CSV de `dashboard/datos_simulados/`. Los filtros cambian las vistas sobre ese conjunto; las predicciones usan `modelos/modelos.pkl` a través de `modelo_esperado_api.py`. Las tablas de entrada son sintéticas; el artefacto se entrenó previamente con datos de Clarios. No se busca una carpeta local de datos.

Todas las cifras, metas, tarifas, fechas y alertas son ficticias y sirven para demostrar la interfaz. No deben usarse para describir o tomar decisiones sobre una operacion real.