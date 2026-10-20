"""Paso 4 (Datos): EDA y minería de datos de RC.

Requiere 01, 02 y 03. Genera figuras en documentacion/figuras/eda_rc/ y tablas auxiliares en data/clean:
  regimen_operacion_rc  (régimen de cada turno por clustering)
  anomalias_candidatas_rc (turnos que se alejan del patrón normal)
Imprime los números que se usan en documentacion/09_eda_rc.md.

Uso (desde la raíz del repositorio):  python src/datos/04_eda_rc.py
"""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import IsolationForest
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
from src.comun.config import cargar_config, mapa_procesos  # noqa: E402

CLEAN = RAIZ / "data" / "clean"
FIG = RAIZ / "documentacion" / "figuras" / "eda_rc"
FIG.mkdir(parents=True, exist_ok=True)

CFG = cargar_config()
PROCESOS = [p["proceso_modelo"] for p in mapa_procesos(CFG) if p["planta"] == "RC" and p["modelar"]]
MEDIDOR_A_PROCESO = {m: p["proceso_modelo"] for p in mapa_procesos(CFG) if p["planta"] == "RC" and p["modelar"] for m in p["medidores_scada"]}
EDA = CFG["eda"]
COLOR = {"triturado": "#4C78A8", "horno": "#E45756", "refinacion": "#F58518", "filtros": "#54A24B", "ptari": "#72B7B2"}
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
plt.rcParams.update({"figure.dpi": 110, "axes.spines.top": False, "axes.spines.right": False, "font.size": 9})


def guardar(nombre):
    plt.tight_layout()
    plt.savefig(FIG / f"{nombre}.png")
    plt.close()


def titulo(t):
    print(f"\n===== {t} =====")


def main():
    eh = pd.read_csv(CLEAN / "energia_hora.csv", parse_dates=["hora_inicio"])
    eh["proceso"] = eh["medidor"].map(MEDIDOR_A_PROCESO)
    eh = eh.dropna(subset=["proceso"])
    et = pd.read_csv(CLEAN / "energia_turno.csv", parse_dates=["fecha_turno"])
    et["proceso"] = et["medidor"].map(MEDIDOR_A_PROCESO)
    et = et.dropna(subset=["proceso"])
    dm = pd.read_csv(CLEAN / "dataset_modelo.csv", parse_dates=["fecha_turno"])
    dd = pd.read_csv(CLEAN / "dataset_modelo_dia.csv", parse_dates=["fecha"])
    ds = pd.read_csv(CLEAN / "dataset_modelo_semana.csv", parse_dates=["semana_inicio"])

    # ---------- 1. Consumo mensual por proceso (3 años) ----------
    titulo("1. Consumo mensual por proceso (kWh, meses completos, incluye horas estimadas por congelamiento)")
    eh["mes"] = eh["hora_inicio"].dt.to_period("M")
    mens = eh.groupby(["mes", "proceso"])["kwh"].sum().unstack()[PROCESOS]
    mens = mens.iloc[1:-1]
    mens["total"] = mens.sum(axis=1)
    print(mens.round(0).astype(int).to_string())
    part = mens[PROCESOS].sum() / mens[PROCESOS].sum().sum()
    print("\nParticipación en el consumo total de RC (7 medidores de proceso):\n", (100 * part).round(1).to_string())
    fig, ax = plt.subplots(figsize=(10, 4))
    base = np.zeros(len(mens))
    for p in PROCESOS:
        ax.bar(mens.index.astype(str), mens[p] / 1000, bottom=base / 1000, label=p, color=COLOR[p])
        base += mens[p].to_numpy()
    ax.set_ylabel("MWh por mes")
    ax.set_title("Consumo mensual de RC por proceso (SCADA, 7 medidores de proceso)")
    ax.tick_params(axis="x", rotation=90, labelsize=7)
    ax.legend(ncol=5, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.02))
    guardar("01_consumo_mensual_por_proceso")

    # ---------- 2. Patrón por día de la semana y turno ----------
    titulo("2. kWh medio por turno según día de la semana y turno (año fiscal 2026)")
    ok = dm[dm["calidad_ok"] == 1]
    fig, axs = plt.subplots(1, 5, figsize=(13, 2.8))
    for ax, p in zip(axs, PROCESOS):
        h = ok[ok["proceso_modelo"] == p].pivot_table(index="turno", columns="dia_semana", values="kwh", aggfunc="mean")
        im = ax.imshow(h.to_numpy(), cmap="YlOrRd", aspect="auto")
        ax.set_xticks(range(7), DIAS)
        ax.set_yticks(range(3), ["T1", "T2", "T3"])
        ax.set_title(p)
        for i in range(h.shape[0]):
            for j in range(h.shape[1]):
                ax.text(j, i, f"{h.iloc[i, j]:.0f}", ha="center", va="center", fontsize=7)
        print(f"\n{p}:\n", h.round(0).to_string())
    guardar("02_patron_dia_turno")

    # ---------- 3. Perfil por hora del día ----------
    titulo("3. Perfil horario (kWh por hora, solo horas ok): laborable vs fin de semana")
    e_ok = eh[eh["calidad"] == "ok"].groupby(["hora_inicio", "proceso"])["kwh"].sum().reset_index()
    e_ok["hora"] = e_ok["hora_inicio"].dt.hour
    e_ok["finde"] = e_ok["hora_inicio"].dt.dayofweek >= 5
    fig, axs = plt.subplots(1, 5, figsize=(13, 2.6), sharex=True)
    for ax, p in zip(axs, PROCESOS):
        s = e_ok[e_ok["proceso"] == p].groupby(["finde", "hora"])["kwh"].mean().unstack(0)
        ax.plot(s.index, s[False], label="laborable", color=COLOR[p])
        ax.plot(s.index, s[True], label="sáb-dom", color="gray", ls="--")
        ax.set_title(p)
        ax.set_xlabel("hora")
        for turno_h in (6, 14, 22):
            ax.axvline(turno_h, color="k", alpha=0.15)
    axs[0].legend(frameon=False, fontsize=7)
    guardar("03_perfil_horario")

    # ---------- 4. Distribución por turno ----------
    titulo("4. Distribución de kWh por turno (percentiles) y fracción de turnos con consumo bajo")
    q = ok.groupby("proceso_modelo")["kwh"].quantile([.05, .25, .5, .75, .95]).unstack().round(0)
    print(q.to_string())
    fig, axs = plt.subplots(1, 5, figsize=(13, 2.6))
    for ax, p in zip(axs, PROCESOS):
        ax.hist(ok[ok["proceso_modelo"] == p]["kwh"].dropna(), bins=40, color=COLOR[p])
        ax.set_title(p)
        ax.set_xlabel("kWh por turno")
    guardar("04_distribucion_por_turno")

    # ---------- 5. Energía vs producción (semana) ----------
    titulo("5. Regresión semanal kWh = base + pendiente x kg (año fiscal 2026)")
    filas = []
    fig, axs = plt.subplots(1, 3, figsize=(11, 3.2))
    for ax, p in zip(axs, ["horno", "refinacion", "triturado"]):
        s = ds[(ds["proceso_modelo"] == p) & (ds["calidad_ok"] == 1)]
        x, y = s["produccion"].to_numpy() / 1000, s["kwh"].to_numpy()
        b, a = np.polyfit(x, y, 1)
        r2 = np.corrcoef(x, y)[0, 1] ** 2
        filas.append({"proceso": p, "semanas": len(s), "base_kwh_por_semana": round(a), "kwh_por_tonelada": round(b, 1), "R2": round(r2, 2),
                      "consumo_semanal_medio": round(y.mean()), "base_como_pct_del_consumo": round(100 * a / y.mean(), 0)})
        ax.scatter(x, y, s=14, color=COLOR[p])
        xs = np.linspace(x.min(), x.max(), 20)
        ax.plot(xs, a + b * xs, color="k", lw=1)
        ax.set_title(f"{p}: R²={r2:.2f}")
        ax.set_xlabel("producción semanal (toneladas)")
        ax.set_ylabel("kWh por semana")
    print(pd.DataFrame(filas).to_string(index=False))
    guardar("05_energia_vs_produccion_semanal")

    # ---------- 6. Desfase entre producción y energía (días) ----------
    titulo("6. Correlación diaria entre kWh(t) y producción(t + desfase). Desfase positivo = la producción se reporta DESPUÉS")
    lags = range(-4, 6)
    res = {}
    fig, ax = plt.subplots(figsize=(6, 3))
    for p in ["horno", "refinacion", "triturado"]:
        s = dd[(dd["proceso_modelo"] == p) & (dd["calidad_ok"] == 1)].set_index("fecha")
        e = s["kwh"].reindex(pd.date_range(s.index.min(), s.index.max()))
        pr = s["produccion"].reindex(e.index)
        res[p] = [round(e.corr(pr.shift(-l)), 3) for l in lags]
        ax.plot(list(lags), res[p], marker="o", label=p, color=COLOR[p])
    ax.set_xlabel("desfase en días (producción posterior a la energía)")
    ax.set_ylabel("correlación")
    ax.legend(frameon=False)
    ax.set_title("¿Se reporta la producción antes o después del consumo?")
    guardar("06_desfase_produccion_energia")
    print(pd.DataFrame(res, index=list(lags)).to_string())

    # ---------- 7. Regímenes de operación (clustering) ----------
    titulo("7. Regímenes de operación por clustering (KMeans sobre el consumo de los 5 procesos por turno)")
    W = ok.pivot_table(index=["fecha_turno", "turno"], columns="proceso_modelo", values="kwh")[PROCESOS].dropna()
    X = StandardScaler().fit_transform(W)
    sil = {}
    for k in range(2, 7):
        sil[k] = round(silhouette_score(X, KMeans(n_clusters=k, n_init=10, random_state=EDA["semilla"]).fit_predict(X), sample_size=1000, random_state=EDA["semilla"]), 3)
    print("Silhouette por k:", sil)
    k = EDA["kmeans_k"]
    if k != 4:
        raise SystemExit("Los nombres de régimen (parada, reducido, normal, alto) suponen kmeans_k = 4 en config.yaml")
    km = KMeans(n_clusters=k, n_init=20, random_state=EDA["semilla"]).fit(X)
    W["cluster"] = km.labels_
    centros = W.groupby("cluster")[PROCESOS].mean()
    orden = centros.sum(axis=1).sort_values().index
    nombre = dict(zip(orden, ["parada", "reducido", "normal", "alto"]))
    W["regimen"] = W["cluster"].map(nombre)
    centros.index = centros.index.map(nombre)
    centros = centros.loc[["parada", "reducido", "normal", "alto"]]
    centros["turnos"] = W["regimen"].value_counts()
    centros["pct"] = (100 * centros["turnos"] / len(W)).round(1)
    print("\nCentros (kWh medio por turno) y tamaño:\n", centros.round(0).to_string())
    r = W.reset_index()
    r["dow"] = r["fecha_turno"].dt.dayofweek
    print("\n% de turnos de cada régimen por día de la semana:")
    print((100 * pd.crosstab(r["dow"], r["regimen"], normalize="index")[["parada", "reducido", "normal", "alto"]]).round(0).rename(index=dict(enumerate(DIAS))).to_string())
    print("\n% de turnos de cada régimen por turno:")
    print((100 * pd.crosstab(r["turno"], r["regimen"], normalize="index")[["parada", "reducido", "normal", "alto"]]).round(0).to_string())
    r = r.sort_values(["fecha_turno", "turno"]).reset_index(drop=True)
    corridas = (r["regimen"] != r["regimen"].shift()).cumsum()
    dur = r.groupby(corridas).agg(reg=("regimen", "first"), turnos=("regimen", "size"))
    print("\nDuración típica de una racha del mismo régimen (turnos seguidos): mediana y p90")
    print(dur.groupby("reg")["turnos"].quantile([.5, .9]).unstack().round(0).to_string())
    r[["fecha_turno", "turno", "regimen"]].assign(fecha_turno=lambda d: d["fecha_turno"].dt.date).to_csv(CLEAN / "regimen_operacion_rc.csv", index=False)
    fig, axs = plt.subplots(1, 2, figsize=(11, 3.2))
    centros[PROCESOS].plot(kind="bar", stacked=True, ax=axs[0], color=[COLOR[p] for p in PROCESOS], legend=False)
    axs[0].set_title("Consumo medio por turno de cada régimen")
    axs[0].set_ylabel("kWh por turno")
    axs[0].set_xlabel("")
    axs[0].tick_params(axis="x", rotation=0)
    axs[0].legend(PROCESOS, frameon=False, fontsize=7, ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    mo = r.assign(mes=r["fecha_turno"].dt.to_period("M").astype(str)).pivot_table(index="mes", columns="regimen", values="turno", aggfunc="size", fill_value=0)
    mo = mo.div(mo.sum(axis=1), axis=0)[["parada", "reducido", "normal", "alto"]]
    mo.plot(kind="bar", stacked=True, ax=axs[1], color=["#bbbbbb", "#f2cf5b", "#6fb36f", "#d9534f"], legend=True)
    axs[1].set_title("Mezcla de regímenes por mes")
    axs[1].tick_params(axis="x", rotation=90, labelsize=7)
    axs[1].set_xlabel("")
    axs[1].legend(frameon=False, fontsize=7, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.32))
    guardar("07_regimenes_de_operacion")
    print("\nMezcla de regímenes por mes (%):")
    print((100 * mo).round(0).to_string())

    # ---------- 8. Intensidad energética semanal ----------
    titulo("8. Intensidad semanal kWh por tonelada (semanas con producción) — media, desviación y semanas más altas")
    fig, ax = plt.subplots(figsize=(9, 3.2))
    for p in ["horno", "refinacion", "triturado"]:
        s = ds[(ds["proceso_modelo"] == p) & (ds["calidad_ok"] == 1) & (ds["produccion"] > 0)].copy()
        s["kwh_t"] = s["kwh"] / (s["produccion"] / 1000)
        ax.plot(s["semana_inicio"], s["kwh_t"], marker=".", label=p, color=COLOR[p])
        print(f"{p}: media={s['kwh_t'].mean():.1f} kWh/t, desv={s['kwh_t'].std():.1f}, p10={s['kwh_t'].quantile(.1):.1f}, p90={s['kwh_t'].quantile(.9):.1f}")
        print("  semanas más altas:", s.nlargest(3, "kwh_t")[["semana_inicio", "kwh_t", "produccion"]].round(1).assign(semana_inicio=lambda d: d["semana_inicio"].dt.date).to_dict("records"))
    ax.set_ylabel("kWh por tonelada")
    ax.legend(frameon=False)
    ax.set_title("Intensidad energética semanal")
    guardar("08_intensidad_semanal")

    # ---------- 9. Deriva del consumo base (3 años) ----------
    titulo("9. Mediana mensual de kWh por turno (energía de 3 años), turnos con cobertura completa")
    full = et[et["cobertura"] >= 1].groupby(["fecha_turno", "turno", "proceso"])["kwh"].sum().reset_index()
    full["mes"] = full["fecha_turno"].dt.to_period("M")
    med = full.groupby(["mes", "proceso"])["kwh"].median().unstack()[PROCESOS].iloc[1:-1]
    print(med.round(0).to_string())
    fig, ax = plt.subplots(figsize=(10, 3.4))
    for p in PROCESOS:
        ax.plot(med.index.astype(str), med[p], label=p, color=COLOR[p])
    ax.tick_params(axis="x", rotation=90, labelsize=7)
    ax.set_ylabel("kWh por turno (mediana mensual)")
    ax.legend(ncol=5, frameon=False)
    ax.set_title("Evolución del consumo típico por turno")
    guardar("09_deriva_consumo_base")

    # ---------- 10. Anomalías candidatas ----------
    titulo("10. Turnos candidatos a anomalía (desviación robusta frente a la mediana de su proceso, turno y día de la semana)")
    z = ok.copy()
    g = z.groupby(["proceso_modelo", "turno", "dia_semana"])["kwh"]
    z["mediana"] = g.transform("median")
    z["mad"] = g.transform(lambda s: (s - s.median()).abs().median())
    z["z"] = (z["kwh"] - z["mediana"]) / (1.4826 * z["mad"] + EDA["piso_mad_kwh"])
    cand = z.reindex(z["z"].abs().sort_values(ascending=False).index).head(EDA["n_anomalias_candidatas"])
    out = cand[["fecha_turno", "turno", "proceso_modelo", "kwh", "mediana", "z"]].copy()
    out.columns = ["fecha_turno", "turno", "proceso", "kwh", "kwh_tipico", "z_robusto"]
    out["fecha_turno"] = out["fecha_turno"].dt.date
    out = out.round(1)
    out.to_csv(CLEAN / "anomalias_candidatas_rc.csv", index=False)
    print(out.to_string(index=False))
    iso = IsolationForest(n_estimators=300, contamination=EDA["contaminacion_isolation_forest"], random_state=EDA["semilla"]).fit(X)
    W["iso"] = iso.predict(X)
    an = W[W["iso"] == -1].reset_index()
    print(f"\nIsolationForest ({100 * EDA['contaminacion_isolation_forest']:.0f}%): {len(an)} turnos. Meses con más turnos anómalos:")
    print(an["fecha_turno"].dt.to_period("M").astype(str).value_counts().head(6).to_string())

    # ---------- 10b. Efecto de los festivos ----------
    titulo("10b. Festivos de Colombia: kWh medio por turno y % de turnos en régimen de parada (lunes a viernes, año fiscal 2026)")
    fer = ok.merge(r[["fecha_turno", "turno", "regimen"]], on=["fecha_turno", "turno"], how="left")
    lab = fer[fer["dia_semana"] < 5]
    tabla = lab.groupby(["proceso_modelo", "es_festivo"])["kwh"].mean().unstack().round(0)
    tabla.columns = ["laborable", "festivo"]
    print(tabla.to_string())
    pr = lab.drop_duplicates(["fecha_turno", "turno"]).groupby("es_festivo")["regimen"].apply(lambda s: round(100 * (s == "parada").mean(), 1))
    print("\n% de turnos en 'parada' (laborables normales vs festivos):", pr.to_dict())
    nav = fer[(fer["fecha_turno"] >= "2025-12-20") & (fer["fecha_turno"] <= "2026-01-06")].drop_duplicates(["fecha_turno", "turno"])
    print("Turnos entre 20-dic y 6-ene en parada:", f"{100 * (nav['regimen'] == 'parada').mean():.0f}%")
    sem_s = fer[(fer["fecha_turno"] >= "2026-03-29") & (fer["fecha_turno"] <= "2026-04-05")].drop_duplicates(["fecha_turno", "turno"])
    print("Turnos de Semana Santa (29-mar a 5-abr) en parada:", f"{100 * (sem_s['regimen'] == 'parada').mean():.0f}%")

    # ---------- 11. Correlación entre procesos ----------
    titulo("11. Correlación entre procesos (kWh por turno)")
    print(W[PROCESOS].corr().round(2).to_string())
    print("\nFiguras en", FIG)


if __name__ == "__main__":
    main()
