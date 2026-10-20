"""Paso 7 (Datos): EDA de F&A (formación) y del gas de RC. Genera figuras en documentacion/figuras/eda_fa_gas/ e imprime las cifras
que se usan en documentacion/10_eda_fa_gas.md.

Requiere 03, 05 y 06. Uso (desde la raíz del repositorio):  python src/datos/07_eda_fa_gas.py
"""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
CLEAN = RAIZ / "data" / "clean"
FIG = RAIZ / "documentacion" / "figuras" / "eda_fa_gas"
FIG.mkdir(parents=True, exist_ok=True)
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
plt.rcParams.update({"figure.dpi": 110, "axes.spines.top": False, "axes.spines.right": False, "font.size": 9})


def guardar(nombre):
    plt.tight_layout()
    plt.savefig(FIG / f"{nombre}.png")
    plt.close()


def titulo(t):
    print(f"\n===== {t} =====")


def ajuste(x, y):
    b, a = np.polyfit(x, y, 1)
    return a, b, np.corrcoef(x, y)[0, 1] ** 2


def main():
    dm = pd.read_csv(CLEAN / "dataset_modelo.csv", parse_dates=["fecha_turno"])
    dd = pd.read_csv(CLEAN / "dataset_modelo_dia.csv", parse_dates=["fecha"])
    ds = pd.read_csv(CLEAN / "dataset_modelo_semana.csv", parse_dates=["semana_inicio"])
    eh = pd.read_csv(CLEAN / "energia_hora.csv", parse_dates=["hora_inicio"])
    cong = pd.read_csv(CLEAN / "congelamientos_energia_fa.csv") if (CLEAN / "congelamientos_energia_fa.csv").exists() else pd.DataFrame()

    # ================= F&A =================
    fa = dm[(dm["proceso_modelo"] == "formacion") & (dm["calidad_ok"] == 1)].copy()
    titulo("F&A 1. Consumo de formación por turno (kWh) y unidades formadas por turno")
    print(fa[["kwh", "produccion"]].describe().round(0).loc[["count", "mean", "std", "min", "25%", "50%", "75%", "max"]].to_string())
    h = fa.pivot_table(index="turno", columns="dia_semana", values="kwh", aggfunc="mean")
    pivote_prod = fa.pivot_table(index="turno", columns="dia_semana", values="produccion", aggfunc="mean")
    print("\nkWh medio por turno según día de la semana:\n", h.round(0).to_string())
    print("\nUnidades formadas por turno, medias:\n", pivote_prod.round(0).to_string())

    titulo("F&A 2. Regresión energía-producción (formación)")
    filas = []
    fig, axs = plt.subplots(1, 3, figsize=(12, 3.2))
    for ax, (nombre, t) in zip(axs, [("turno", fa), ("día", dd[(dd["proceso_modelo"] == "formacion") & (dd["calidad_ok"] == 1)]),
                                    ("semana", ds[(ds["proceso_modelo"] == "formacion") & (ds["calidad_ok"] == 1)])]):
        a, b, r2 = ajuste(t["produccion"], t["kwh"])
        filas.append({"nivel": nombre, "n": len(t), "base_kwh": round(a), "kwh_por_unidad": round(b, 2), "R2": round(r2, 2),
                      "consumo_medio": round(t["kwh"].mean()), "base_pct": round(100 * a / t["kwh"].mean())})
        ax.scatter(t["produccion"], t["kwh"], s=10, color="#7a5195")
        xs = np.linspace(t["produccion"].min(), t["produccion"].max(), 20)
        ax.plot(xs, a + b * xs, color="k", lw=1)
        ax.set_title(f"formación por {nombre}: R²={r2:.2f}")
        ax.set_xlabel("unidades formadas")
        ax.set_ylabel("kWh")
    print(pd.DataFrame(filas).to_string(index=False))
    guardar("01_formacion_energia_vs_produccion")

    titulo("F&A 3. Desfase diario entre producción y energía (positivo = producción reportada después)")
    s = dd[(dd["proceso_modelo"] == "formacion") & (dd["calidad_ok"] == 1)].set_index("fecha")
    e = s["kwh"].reindex(pd.date_range(s.index.min(), s.index.max()))
    pr = s["produccion"].reindex(e.index)
    print({l: round(e.corr(pr.shift(-l)), 3) for l in range(-3, 4)})

    titulo("F&A 4. Patrón por día y turno, y perfil horario")
    fig, axs = plt.subplots(1, 3, figsize=(13, 2.8))
    im = axs[0].imshow(h.to_numpy(), cmap="YlOrRd", aspect="auto")
    axs[0].set_xticks(range(7), DIAS)
    axs[0].set_yticks(range(3), ["T1", "T2", "T3"])
    axs[0].set_title("kWh medio por turno")
    for i in range(h.shape[0]):
        for j in range(h.shape[1]):
            axs[0].text(j, i, f"{h.iloc[i, j]:.0f}", ha="center", va="center", fontsize=7)
    f = eh[(eh["planta"] == "F&A") & (eh["calidad"] == "ok")].groupby("hora_inicio")["kwh"].sum().reset_index()
    f["hora"], f["finde"] = f["hora_inicio"].dt.hour, f["hora_inicio"].dt.dayofweek >= 5
    for finde, c, lab in [(False, "#7a5195", "laborable"), (True, "gray", "sáb-dom")]:
        p = f[f["finde"] == finde].groupby("hora")["kwh"].mean()
        axs[1].plot(p.index, p.values, color=c, label=lab, ls="--" if finde else "-")
    axs[1].set_title("Perfil por hora (3 rectificadores)")
    axs[1].set_xlabel("hora")
    axs[1].legend(frameon=False)
    for turno_h in (6, 14, 22):
        axs[1].axvline(turno_h, color="k", alpha=0.15)
    cuota = eh[(eh["planta"] == "F&A") & eh["kwh"].notna()].groupby("medidor")["kwh"].sum()
    axs[2].bar([m.replace("RECTIFICADOR_", "R") for m in cuota.index], cuota.values / 1000, color="#7a5195")
    axs[2].set_title("MWh por rectificador (jul-sep 2026)")
    guardar("02_formacion_patrones")
    print("\nParticipación de cada rectificador:", (100 * cuota / cuota.sum()).round(1).to_dict())
    print("Perfil horario laborable: mín", round(f[~f["finde"]].groupby("hora")["kwh"].mean().min()), "máx", round(f[~f["finde"]].groupby("hora")["kwh"].mean().max()), "kWh/h")

    titulo("F&A 5. Intensidad semanal (kWh por unidad formada) y semanas extremas")
    sw = ds[(ds["proceso_modelo"] == "formacion") & (ds["calidad_ok"] == 1)].copy()
    sw["kwh_u"] = sw["kwh"] / sw["produccion"]
    print(sw[["semana_inicio", "kwh", "produccion", "kwh_u", "dias_festivos"]].round(2).assign(semana_inicio=lambda d: d["semana_inicio"].dt.date).to_string(index=False))
    fig, ax = plt.subplots(figsize=(6.5, 3))
    ax.plot(sw["semana_inicio"], sw["kwh_u"], marker="o", color="#7a5195")
    ax.set_ylabel("kWh por unidad formada")
    ax.set_title("Intensidad semanal de formación")
    guardar("03_formacion_intensidad_semanal")

    titulo("F&A 6. Festivos y consumo bajo")
    fer = fa.groupby("es_festivo")["kwh"].agg(["mean", "count"]).round(0)
    print(fer.to_string())
    bajos = fa[fa["kwh"] < 0.5 * fa["kwh"].median()].sort_values("fecha_turno")
    print(f"\nTurnos con consumo menor a la mitad de la mediana ({0.5 * fa['kwh'].median():.0f} kWh): {len(bajos)}")
    print(bajos[["fecha_turno", "turno", "kwh", "produccion", "es_festivo"]].head(12).round(0).assign(fecha_turno=lambda d: d["fecha_turno"].dt.date).to_string(index=False))
    if len(cong):
        print("\nCongelamientos del SCADA en F&A:\n", cong.to_string(index=False))

    # ================= GAS =================
    g = pd.read_csv(CLEAN / "dataset_modelo_gas_dia.csv", parse_dates=["fecha"])
    gok = g[g["calidad_ok"] == 1].copy()
    titulo("GAS 1. Consumo diario de gas de refinación (m3)")
    print(gok["m3"].describe().round(0).to_string())
    print("\nPor día de la semana (días ok):\n", gok.groupby("dia_semana")["m3"].agg(["mean", "count"]).round(0).rename(index=dict(enumerate(DIAS))).to_string())

    titulo("GAS 2. Relación con la producción y la energía de RC (días ok)")
    en = dd[dd["planta"] == "RC"].pivot_table(index="fecha", columns="proceso_modelo", values="kwh")
    en.columns = [f"kwh_{c}" for c in en.columns]
    pro = dd[dd["planta"] == "RC"].pivot_table(index="fecha", columns="proceso_modelo", values="produccion")
    pro.columns = [f"kg_{c}" for c in pro.columns]
    X = gok.set_index("fecha")[["m3"]].join(en).join(pro)
    print(X.corr()["m3"].drop("m3").round(2).to_string())
    print("\nCorrelación m3(t) con producción de refinación(t+desfase), días ok:")
    gs = g.set_index("fecha")["m3"].where(g.set_index("fecha")["calidad_ok"] == 1)
    for nombre in ["kg_refinacion", "kg_horno", "kwh_horno"]:
        ser = (pro if nombre.startswith("kg_") else en)[nombre].reindex(gs.index)
        print(nombre, {l: round(gs.corr(ser.shift(-l)), 2) for l in range(-2, 4)})

    fig, axs = plt.subplots(1, 3, figsize=(13, 3.2))
    col = g["calidad"].map({"ok": "#4C78A8", "estimado": "#F58518", "reinicio": "#E45756"})
    axs[0].bar(g["fecha"], g["m3"], color=col)
    axs[0].set_title("Gas diario (azul ok, naranja estimado, rojo reinicio)")
    axs[0].set_ylabel("m³")
    axs[0].tick_params(axis="x", rotation=45)
    for ax, (c, etq) in zip(axs[1:], [("kg_refinacion", "producción de refinación (kg)"), ("kwh_horno", "energía del horno (kWh)")]):
        ax.scatter(X[c], X["m3"], s=12, color="#4C78A8")
        ok_ = X[[c, "m3"]].dropna()
        if len(ok_) > 3:
            a, b, r2 = ajuste(ok_[c], ok_["m3"])
            xs = np.linspace(ok_[c].min(), ok_[c].max(), 20)
            ax.plot(xs, a + b * xs, color="k", lw=1)
            ax.set_title(f"m³ vs {etq}: R²={r2:.2f}")
        ax.set_xlabel(etq)
        ax.set_ylabel("m³ por día")
    guardar("04_gas_diario")
    print("\nFiguras en", FIG)


if __name__ == "__main__":
    main()
