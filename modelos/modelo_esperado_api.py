"""API pública de los modelos para el dashboard.

    from modelos.modelo_esperado_api import predecir      # con la raíz del repositorio en sys.path


Funciones reutilizables:
- `predecir(proceso, produccion, planta="RC", nivel="dia", **ctx)` -> dict con kwh esperado,
  intervalo y metadatos del modelo. Es la función que la especificación pide para el dashboard.
- `cargar_modelos()` -> dict de modelos ajustados por run_modelo_v6.py.
- `features(tab, nivel)` / `predecir_modelo(m, X)` -> inferencia reutilizada por 05 y por el dashboard.
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd

MODELOS = Path(__file__).resolve().parent   # carpeta modelos/
INTERIM = MODELOS


def ruta_modelos():
    """Los modelos entregados están en modelos/modelos.pkl."""
    for carpeta in (MODELOS, INTERIM):
        if (carpeta / "modelos.pkl").exists():
            return carpeta / "modelos.pkl"
    return MODELOS / "modelos.pkl"


def cargar_modelos():
    ruta = ruta_modelos()
    if not ruta.exists():
        raise FileNotFoundError(
            f"No existe {ruta}. Los modelos entrenados se entregan en modelos/modelos.pkl: "
            "el archivo tiene que estar en la carpeta modelos/.")
    with open(ruta, "rb") as f:
        return pickle.load(f)


def features(tab: pd.DataFrame, nivel: str) -> pd.DataFrame:
    f = pd.DataFrame(index=tab.index)
    f["produccion"] = tab["produccion"].clip(lower=0)
    f["produccion_t1"] = tab.groupby("proceso_modelo")["produccion"].shift(1).clip(lower=0) if "proceso_modelo" in tab else 0
    f["produccion_t2"] = tab.groupby("proceso_modelo")["produccion"].shift(2).clip(lower=0) if "proceso_modelo" in tab else 0
    for d in range(1, 7):
        f[f"dia_{d}"] = (tab["dia_semana"] == d).astype(float)
    f["es_fin_semana"] = tab["es_fin_semana"].astype(float)
    f["es_festivo"] = tab["es_festivo"].astype(float)
    if nivel == "turno" and "turno" in tab.columns:
        for t in (2, 3):
            f[f"turno_{t}"] = (tab["turno"] == t).astype(float)
    return f.fillna(0)


def predecir_modelo(m, X: pd.DataFrame) -> np.ndarray:
    if m["tipo"] in ("huber", "gbr"):
        return m["modelo"].predict(X[m["columnas"]])
    return np.c_[np.ones(len(X)), X[m["columnas"]].to_numpy()] @ np.r_[m["base"], m["coef"]]


def predecir(proceso: str, produccion: float, planta: str = "RC", nivel: str = "dia",
             fecha=None, dia_semana: int = 0, es_fin_semana: int | None = None, es_festivo: int | None = None,
             turno: int = 1, modelo=None, produccion_t1: float | None = None, produccion_t2: float | None = None) -> dict:
    """Predice el consumo esperado (kWh) de `proceso` para una `produccion` supuesta.

    Usa el MISMO modelo que `resultados_modelo` y `pronostico` (el elegido por proceso y nivel) y el mismo intervalo
    (cuantiles 10 y 90 de los residuos), así que con las mismas entradas da lo mismo que `pronostico.csv`.

    Calendario: pasa `fecha` (date, Timestamp o texto) y se deducen día de la semana, fin de semana y festivo; o pasa
    `dia_semana` (0 = lunes) y, si quieres, `es_festivo`. Rezagos: el modelo usa la producción de los dos periodos
    anteriores; si no se indican `produccion_t1` y `produccion_t2`, se asume que fueron iguales a `produccion`.

    Devuelve {proceso, planta, nivel, produccion, kwh_esperado, kwh_inferior, kwh_superior, modelo, intervalo}.
    """
    modelos = modelo or cargar_modelos()
    clave = f"{nivel}|{proceso}"
    if clave not in modelos:
        raise ValueError(f"No hay modelo ajustado para '{clave}'. Modelos disponibles: {sorted(modelos)}")
    celda = modelos[clave]
    m = celda["mejor"]
    if fecha is not None:
        f = pd.Timestamp(fecha)
        dia_semana = f.dayofweek
        if es_festivo is None:
            import holidays
            es_festivo = int(f.date() in holidays.country_holidays("CO", years=f.year))
    if es_fin_semana is None:
        es_fin_semana = int(dia_semana >= 5)
    es_festivo = int(es_festivo or 0)
    p1 = produccion if produccion_t1 is None else produccion_t1
    p2 = p1 if produccion_t2 is None else produccion_t2
    fila = pd.DataFrame({"produccion": [p2, p1, produccion], "proceso_modelo": proceso, "dia_semana": dia_semana,
                         "es_fin_semana": es_fin_semana, "es_festivo": es_festivo, "turno": turno})
    X = features(fila, nivel).iloc[[-1]]
    pred = float(np.clip(predecir_modelo(m, X)[0], 0, None))
    if "q10" in celda and "q90" in celda:
        inf, sup, intervalo = max(pred + celda["q10"], 0), pred + celda["q90"], "cuantiles 10 y 90 de los residuos"
    else:  # modelos guardados antes de que se registraran los residuos
        inf, sup, intervalo = max(pred * 0.9, 0), pred * 1.1, "aproximado, ±10 %"
    return {"proceso": proceso, "planta": planta, "nivel": nivel, "produccion": produccion,
            "kwh_esperado": round(pred, 2), "kwh_inferior": round(inf, 2), "kwh_superior": round(sup, 2),
            "modelo": celda["mejor_nombre"], "intervalo": intervalo}
