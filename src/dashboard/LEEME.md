# Carpeta de Dashboard y entrega (Gabriel)

**Objetivo:** construir el aplicativo que Clarios usaría a diario, y encargarse de la documentación técnica y la presentación.

**Lee antes de empezar:** `docs/02_indicadores_alertas_dashboard.md` (indicadores, semáforo, alertas y pantallas), `docs/01_contrato_datos.md` (tablas que lee el aplicativo) y tu sección en `docs/00_plan_de_trabajo.md`.

## Entradas
Tablas de `data/clean/` (consumo y calidad de Sebastián; `resultados_modelo`, `pronostico` y `metas` de Joshua). Mientras no lleguen, usa `data/ejemplo/`. La función `leer_tabla` de `src/comun/config.py` elige sola: usa las reales si existen y si no las de ejemplo.

## Salidas
- El aplicativo (propuesta: Streamlit).
- Documentación técnica (metodología, fuentes, supuestos, limitaciones, arquitectura, cómo ejecutar).
- La presentación y un plan B (capturas o video de la demostración).

## Archivos sugeridos
- `app.py`: punto de entrada del aplicativo.
- `paginas/` o secciones: resumen de planta, detalle por proceso y turno, alertas, pronóstico y escenarios, gas, calidad de datos y supuestos.
- `alertas.py`: reglas de alerta (exceso sostenido, anomalía, consumo en turno no operativo, dato incompleto).
- `indicadores.py`: cálculo de los indicadores del documento de indicadores.

## Checklist
- [ ] 12 oct: herramienta decidida, esqueleto con datos de ejemplo, pantallas 1 y 2
- [ ] 13 y 14 oct: alertas, filtros y parámetros editables
- [ ] 15 oct: integra resultados reales de RC
- [ ] 16 oct: pronóstico, gas y calidad de datos
- [ ] 17 oct: pulido y documentación técnica. **Se congelan funciones.**
- [ ] 18 y 19 oct: presentación y ensayos, plan B

Reglas: el aplicativo debe mostrar siempre real y esperado, el costo en pesos, y un aviso cuando el dato esté incompleto. Parámetros editables en la interfaz (tarifa, umbrales y turnos), con valores iniciales de `config/config.yaml`.
**No desplegar con datos reales en servicios públicos.**
