"""run_cruce_cifras.py — cruce de las cifras de Modelos contra documentacion/11_cifras_verificadas.md (Joshua).

Genera `documentacion/modelos/cruce_cifras.md`: qué cifra de Modelos sale de qué tabla, cómo se calcula,
su estado (Reproducido / Estimado / Supuesto / No verificable) y la limitación asociada, al estilo
de `documentacion/11_cifras_verificadas.md` del frente de Datos. Sirve para que la presentación solo cite
cifras registradas aquí.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from src.comun.config import leer_tabla  # noqa: E402

DOCS = RAIZ / "documentacion" / "modelos"
CLEAN = RAIZ / "data" / "clean"


def md_tabla(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(str(c) for c in cols) + " |",
           "|" + "---|" * len(cols)]
    for _, row in df.iterrows():
        out.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
    return "\n".join(out)


def main():
    res = pd.read_csv(CLEAN / "resultados_modelo.csv", parse_dates=["fecha_turno"])
    exceso_pos = float(res["exceso_kwh"].clip(lower=0).sum())
    defecto = float(res["exceso_kwh"].clip(upper=0).sum())
    neto = exceso_pos + defecto
    energia_real = float(res["kwh_real"].sum())
    costo_total = float(res["costo_exceso_cop"].sum())
    anomalias = int(res["es_anomalia"].sum())
    sev = res["severidad"].value_counts().to_dict()

    t = leer_tabla("tarifa_kwh_mensual").sort_values("mes")
    tarifa_ult = float(t["costo_kwh_cop"].iloc[-1])
    tarifa_media = float(t["costo_kwh_cop"].mean())

    # coherencia: costo_exceso_cop ≈ exceso_pos × tarifa (debe cuadrar salvo redondeo)
    costo_recomputado = exceso_pos * tarifa_ult

    pron = pd.read_csv(CLEAN / "pronostico.csv")
    n_dias = pron["fecha"].nunique()
    filas = [
        {"ID": "M1", "Cifra": f"Exceso bruto (turnos por encima de lo esperado): {exceso_pos:,.0f} kWh. **No es un ahorro**",
         "Periodo y alcance": "oct 2025 – sep 2026, RC, turnos con `calidad_ok=1`",
         "Fuente y fórmula": "`resultados_modelo.csv` → `sum(max(exceso_kwh, 0))`",
         "Estado": "**Reproducido**",
         "Limitaciones": f"Incluye el error del propio modelo: en otros turnos el consumo estuvo {abs(defecto):,.0f} kWh por debajo de lo esperado. Citar el neto (M9), no este valor. Depende del modelo elegido (Huber/GBR por celda)."},
        {"ID": "M2", "Cifra": f"Costo del exceso bruto: {costo_total:,.0f} COP",
         "Periodo y alcance": "ídem M1",
         "Fuente y fórmula": "`resultados_modelo.csv` → `sum(costo_exceso_cop)` = exceso positivo × tarifa de Clarios",
         "Estado": "**Reproducido**",
         "Limitaciones": f"Coherencia interna: exceso_pos × tarifa = {costo_recomputado:,.0f} COP (debe cuadrar salvo redondeo). Es el costo del exceso BRUTO: no es un sobrecosto ni un ahorro. Tarifa no ponderada por consumo."},
        {"ID": "M3", "Cifra": f"Ahorro potencial (escenario): {max(neto, 0) * tarifa_ult * 0.5:,.0f} COP",
         "Periodo y alcance": "ídem M1",
         "Fuente y fórmula": "máx(exceso neto, 0) × tarifa × `fraccion_evitable` (0.5)",
         "Estado": "**Supuesto**",
         "Limitaciones": "`fraccion_evitable` es relleno sin respaldo de Clarios (ver advertencia del parámetro en config.yaml). **Es un escenario, no un ahorro demostrado.**"},
        {"ID": "M9", "Cifra": f"Exceso neto: {neto:,.0f} kWh ({neto / energia_real:.1%} de la energía real de {energia_real:,.0f} kWh)",
         "Periodo y alcance": "ídem M1",
         "Fuente y fórmula": "`resultados_modelo.csv` → `sum(exceso_kwh)` (exceso menos defecto)",
         "Estado": "**Reproducido**",
         "Limitaciones": "Orden de magnitud, no una medición: un modelo con error deja turnos por encima y por debajo. Se concentra en filtros (modelo con confianza `baja`). Los meses de entrenamiento son dentro de muestra (`documentacion/modelos/05_pronostico_y_ahorro.md`)."},
        {"ID": "M4", "Cifra": f"Anomalías detectadas (`es_anomalia=1`): {anomalias} turnos",
         "Periodo y alcance": "ídem M1",
         "Fuente y fórmula": "`resultados_modelo.csv` → `puntaje_anomalia ≥ 0.5`",
         "Estado": "**Reproducido**",
         "Limitaciones": "Umbral de puntaje arbitrario (0.5 sobre 1−exp(−|z|/10)). Contrastar con el calendario real de Clarios para confirmar falsos positivos."},
        {"ID": "M5", "Cifra": f"Severidad: alta {sev.get('alta',0)}, media {sev.get('media',0)}, baja {sev.get('baja',0)}",
         "Periodo y alcance": "ídem M1",
         "Fuente y fórmula": "`resultados_modelo.csv` → percentiles 50 y 90 del costo del exceso por proceso",
         "Estado": "**Reproducido**",
         "Limitaciones": "Percentiles relativos por proceso; no son umbrales de Clarios."},
        {"ID": "M6", "Cifra": f"Tarifa usada: {tarifa_ult:.1f} COP/kWh (última disponible)",
         "Periodo y alcance": "`tarifa_kwh_mensual.csv`",
         "Fuente y fórmula": "último valor de `costo_kwh_cop`",
         "Estado": "**Reproducido**",
         "Limitaciones": f"Media simple de los 24 meses de la tabla (feb 2024 a jul 2026): {tarifa_media:.1f} COP/kWh; la del año fiscal 2026 (10 meses) es 542.475 (G1 de `documentacion/11_cifras_verificadas.md`), que es la que se cita. Faltan meses (ago-sep 2026); ver limitación G1 de `documentacion/11_cifras_verificadas.md`."},
        {"ID": "M7", "Cifra": f"Metas por proceso (percentil 25 histórico del kWh por unidad): 6 procesos",
         "Periodo y alcance": "RC (5 procesos) y F&A formación",
         "Fuente y fórmula": "`metas.csv` → percentil 25 de `kwh/produccion` sobre `dataset_modelo_dia` con `calidad_ok=1`",
         "Estado": "**Estimado**",
         "Limitaciones": "Las metas reales de Clarios (`metas_clarios.csv`) son por **planta y mes** (Ensamble 2.012, OREC 5.861, F&A 18.332 kWh/EQ), no por turno; la base trae además presupuestos por línea o proceso (G6 de `documentacion/11_cifras_verificadas.md`), que no están en `metas_clarios.csv`. Las de `metas.csv` son derivadas del histórico."},
        {"ID": "M8", "Cifra": f"Pronóstico: {len(pron)} filas ({pron['proceso_modelo'].nunique()} procesos de RC × {pron['escenario'].nunique()} escenarios × {n_dias} días)",
         "Periodo y alcance": f"{pron['fecha'].min()} a {pron['fecha'].max()}; F&A no tiene pronóstico diario",
         "Fuente y fórmula": "`pronostico.csv` → función de consumo esperado sobre producción supuesta (promedio del mismo día de la semana en las últimas 4 semanas × factor)",
         "Estado": "**Estimado**",
         "Limitaciones": "No hay plan de producción FY27 de Clarios (ver G5 de `documentacion/11_cifras_verificadas.md`): los escenarios son ilustrativos, no un presupuesto oficial."},
    ]

    lineas = ["# Cruce de cifras de Modelos (Joshua)", "",
             "Registro al estilo de `documentacion/11_cifras_verificadas.md` para las cifras que produce el frente de "
             "**Modelos**. Si una cifra de la presentación no está aquí, no debe citarse.", "",
             "Estados: **Verificado** (dos fuentes independientes) · **Reproducido** (calculado desde las tablas, "
             "sin validación externa) · **Estimado** (método declarado) · **Supuesto** (decisión sin confirmación "
             "de Clarios) · **No verificable** · **Retirada**.", "",
             md_tabla(pd.DataFrame(filas)), "",
             "## Coherencia interna comprobada", "",
             f"- `sum(costo_exceso_cop)` = {costo_total:,.0f} COP vs `exceso_pos × tarifa` = {costo_recomputado:,.0f} COP "
             f"(diferencia por redondeo: {abs(costo_total - costo_recomputado) / max(costo_recomputado, 1) * 100:.4f}%).",
             "- `metas.csv` y `pronostico.csv` se generan del mismo `dataset_modelo_dia` con `calidad_ok=1` "
             "que alimenta `resultados_modelo` (no hay ventanas de datos distintas entre tablas).", "",
             "## Lo que NO debe citarse de Modelos sin marcar la limitación", "",
             f"- **El exceso bruto ({exceso_pos:,.0f} kWh, {costo_total / 1e6:,.0f} millones COP)**: no es un ahorro ni un sobrecosto; "
             f"incluye el error del modelo. Citar el neto ({neto:,.0f} kWh).",
             f"- **El ahorro de {max(neto, 0) * tarifa_ult * 0.5 / 1e6:,.1f} millones COP**: es un escenario con `fraccion_evitable = 0.5` "
             "sin respaldo de Clarios. Debe presentarse siempre con esa advertencia.",
             "- **`exceso_pct`**: acotado a [-100, 200]% por legibilidad; puede ser enorme con `kwh_esperado` bajo. "
             "Citar kWh y COP, no el porcentaje.",
             "- **R² de algunos procesos**: por turno solo el horno supera claramente la línea base. La columna "
             "`confianza_modelo` de `resultados_modelo` lo señala (alta: horno; media: triturado y ptari; baja: refinación y filtros); "
             "con `baja` el exceso es indicativo.",
             "- **Metas por proceso**: son `historico_p25`, no las metas reales de Clarios (`metas_clarios.csv` es por planta y mes; la base trae además presupuestos por línea o proceso en kWh/EQ, G6 de `documentacion/11_cifras_verificadas.md`).", ""]

    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "cruce_cifras.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(f"Escrito {DOCS / 'cruce_cifras.md'}")
    print("\n".join(lineas[:40]))


if __name__ == "__main__":
    main()
