"""Funciones compartidas: contadores acumulados del SCADA -> kWh por hora y por turno, con marcas de calidad.

Las usan 01_energia_scada.py (RC) y 05_energia_fa.py (F&A).

Calidad de cada hora de cada medidor:
  ok           consumo medido normalmente
  interpolado  hueco corto (de umbral_hueco_interpolable_horas a max_horas_interpolar) repartido linealmente
  estimado     el SCADA estuvo congelado (todos los medidores sin cambio) y el consumo acumulado
               se repartió de forma uniforme en el periodo. Sirve para totales diarios o mensuales,
               NO para análisis por hora o por turno.
  faltante     hueco largo sin lecturas
  salto        el contador subió de golpe más de umbral_salto_x_p99 veces lo normal
  reinicio     el contador bajó
"""
import math
from pathlib import Path

import numpy as np
import pandas as pd

from src.comun.turnos import horas_por_turno, turno_y_fecha

RAIZ = Path(__file__).resolve().parents[2]
CLEAN = RAIZ / "data" / "clean"
ORIGEN = pd.Timestamp("2020-01-01")
CALIDAD = {0: "ok", 1: "interpolado", 2: "estimado", 3: "faltante", 4: "salto", 5: "reinicio"}
MESES = {"ene": 1, "jan": 1, "feb": 2, "mar": 3, "abr": 4, "apr": 4, "may": 5, "jun": 6, "jul": 7,
         "ago": 8, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12, "dec": 12}


def detectar_congelamientos(df, cols, min_intervalos):
    """Periodos en que TODOS los medidores de proceso no cambian a la vez (SCADA sin actualizar).

    Devuelve (ventanas, filas_a_quitar). Cada ventana va de la última lectura antes del congelamiento
    a la primera lectura después, y a las lecturas intermedias (idénticas) se les quita.
    """
    quieto = (df[cols].diff() == 0).all(axis=1).to_numpy()
    ventanas, quitar, i, n = [], [], 1, len(df)
    t = df["t"].to_numpy()
    while i < n:
        if quieto[i]:
            j = i
            while j + 1 < n and quieto[j + 1]:
                j += 1
            if j - i + 1 >= min_intervalos:
                fin = j + 1 if j + 1 < n else None
                ventanas.append({"inicio": pd.Timestamp(t[i - 1]), "fin": pd.Timestamp(t[fin]) if fin is not None else pd.NaT,
                                 "horas": (pd.Timestamp(t[j]) - pd.Timestamp(t[i - 1])).total_seconds() / 3600,
                                 "idx_inicio": i - 1, "idx_fin": fin})
                quitar.extend(range(i, j + 1))
            i = j + 1
        else:
            i += 1
    return ventanas, quitar


PERCENTIL_REAPARICION = 0.99
COLUMNAS_RACHAS = ["planta", "medidor", "inicio", "fin", "horas", "n_intervalos", "kwh_tipico_hora", "kwh_esperado_periodo",
                   "kwh_reaparecido", "razon_reaparicion", "medidores_quietos_pct", "actividad_otros", "pct_horas_no_laborales",
                   "clasificacion", "confianza", "tratamiento", "evidencia"]


def _tipico(D, ok, t_sec, a, b, dias):
    """Consumo típico por intervalo de un medidor alrededor de la racha (índices a..b), sin contar la racha."""
    lo = np.searchsorted(t_sec, t_sec[a] - dias * 86400.0)
    hi = np.searchsorted(t_sec, t_sec[min(b, len(t_sec) - 1)] + dias * 86400.0, side="right")
    idx = np.arange(lo, hi)
    idx = idx[(idx < a) | (idx > b)]
    idx = idx[ok[idx]]
    return float(D[idx].mean()) if len(idx) else np.nan


def analizar_rachas(df, medidores_proceso, cal, rachas, k, quitar, pais_festivos=None, planta=""):
    """Rachas de contador sin cambio por medidor, clasificadas con evidencia y nivel de confianza.

    Un contador acumulado de energía puede quedar sin cambio por tres razones, que se distinguen por lo que pasa DESPUÉS:
      - la energía reaparece de golpe -> el SCADA se congeló y el medidor siguió contando (la energía existió);
      - no reaparece y los demás medidores también están quietos -> la planta estuvo sin consumo;
      - no reaparece y los demás consumen normal -> medidor aislado sin variación (cero real, apagado o atascado: indeterminado).

    `df`: lecturas (columna `t` y un contador por medidor) ya sin filas con todo en cero. `quitar`: índices de las filas
    que el detector de congelamiento de planta quita. Devuelve (tabla de rachas, ventanas por medidor, filas a quitar por medidor);
    las dos últimas solo se llenan para las rachas que se corrigen (`corregir_congelamiento_por_medidor`).
    """
    n = len(df)
    t = pd.to_datetime(df["t"]).to_numpy()
    t_sec = (df["t"] - ORIGEN).dt.total_seconds().to_numpy()
    dt_h = np.concatenate([[np.nan], np.diff(t_sec) / 3600.0])
    min_int, hueco_h = cal["min_intervalos_congelado"], cal["umbral_hueco_interpolable_horas"]
    V = {m: df[m].to_numpy(float) for m in medidores_proceso}
    D = {m: np.concatenate([[np.nan], np.diff(V[m])]) * k for m in medidores_proceso}
    quieto, ok, p99 = {}, {}, {}
    for m in medidores_proceso:
        pos = D[m][(dt_h <= hueco_h) & (D[m] > 0)]
        p99[m] = float(np.quantile(pos, PERCENTIL_REAPARICION)) if len(pos) else np.inf
        thr = float(np.quantile(pos, cal["percentil_salto"])) * cal["umbral_salto_x_p99"] if len(pos) else np.inf
        quieto[m] = np.concatenate([[False], (np.diff(V[m]) == 0) & (V[m][1:] > 0)])
        ok[m] = (dt_h <= hueco_h) & (D[m] >= 0) & (D[m] <= thr)
    en_global = np.zeros(n, dtype=bool)
    en_global[list(quitar)] = True
    festivos = None
    if pais_festivos:
        import holidays
        festivos = holidays.country_holidays(pais_festivos, years=range(pd.Timestamp(t[0]).year, pd.Timestamp(t[-1]).year + 1))

    filas, ventanas, quitar_local = [], {m: [] for m in medidores_proceso}, {m: [] for m in medidores_proceso}
    for m in medidores_proceso:
        q, i = quieto[m], 1
        while i < n:
            if not q[i]:
                i += 1
                continue
            j = i
            while j + 1 < n and q[j + 1]:
                j += 1
            n_int = j - i + 1
            if n_int >= min_int:
                fin = j + 1 if j + 1 < n else None
                horas = (t_sec[j] - t_sec[i - 1]) / 3600.0
                tip = _tipico(D[m], ok[m], t_sec, i - 1, j + 1, rachas["ventana_referencia_dias"])
                post = D[m][fin] if fin is not None else np.nan
                esperado = tip * (n_int + 1) if tip == tip else np.nan
                razon = post / esperado if esperado and esperado > 0 else np.nan
                reaparece = bool(fin is not None and post > rachas["factor_recuperacion_p99"] * p99[m])
                quietos = sum(bool(quieto[x][i:j + 1].all()) for x in medidores_proceso)
                pct_quietos = quietos / len(medidores_proceso)
                rel = []
                for x in medidores_proceso:
                    if x == m:
                        continue
                    tx = _tipico(D[x], ok[x], t_sec, i - 1, j + 1, rachas["ventana_referencia_dias"])
                    if tx == tx and tx > 0:
                        rel.append(max(V[x][j] - V[x][i - 1], 0.0) * k / (tx * n_int))
                actividad = float(np.median(rel)) if rel else np.nan
                dias = pd.DatetimeIndex(t[i:j + 1])
                no_lab = np.mean([(d.dayofweek >= 5) or (festivos is not None and d.date() in festivos) for d in dias])
                frac_global = float(en_global[i:j + 1].mean())

                if fin is None:
                    clase, conf = "sin_dato_posterior", "baja"
                    ev = "la racha llega al final del archivo: no hay lectura posterior para saber si la energía reaparece"
                elif reaparece:
                    alcance = "planta" if pct_quietos >= rachas["fraccion_medidores_quietos"] else "medidor"
                    clase = f"congelamiento_scada_{alcance}"
                    alta = razon == razon and rachas["razon_recuperacion_alta_min"] <= razon <= rachas["razon_recuperacion_alta_max"]
                    conf = "alta" if alta else "media"
                    ev = (f"reaparecen {post:,.1f} kWh en el intervalo siguiente ({post / p99[m]:.1f} veces el percentil 99 horario del medidor)"
                          f"; {quietos} de {len(medidores_proceso)} medidores sin cambio")
                elif pct_quietos >= rachas["fraccion_medidores_quietos"]:
                    clase, conf = "sin_consumo_planta", "alta"
                    ev = (f"{quietos} de {len(medidores_proceso)} medidores sin cambio y la energía no reaparece "
                          f"({post:,.1f} kWh en el intervalo siguiente)")
                elif tip == tip and tip < rachas["umbral_bajo_consumo_kwh_h"] and horas <= rachas["max_horas_bajo_consumo"]:
                    clase, conf = "constante_bajo_consumo", "media"
                    ev = (f"medidor de consumo típico {tip:.2f} kWh/h (menor a {rachas['umbral_bajo_consumo_kwh_h']:g}): "
                          f"puede no cambiar por la resolución del contador o consumo de reposo")
                elif actividad == actividad and actividad >= rachas["actividad_planta_activa"]:
                    clase, conf = "sin_variacion_planta_activa", "baja"
                    ev = (f"la energía no reaparece y los demás medidores consumen el {actividad:.0%} de lo típico: "
                          f"cero real, medidor apagado o atascado (indeterminado)")
                else:
                    clase, conf = "sin_consumo_parcial", "media"
                    ev = (f"la energía no reaparece y los demás medidores consumen solo el {actividad:.0%} de lo típico"
                          if actividad == actividad else "la energía no reaparece")
                filas.append({"_i": i, "_j": j, "_fin": fin, "_frac_global": frac_global, "_pct": pct_quietos,
                              "planta": planta, "medidor": m, "inicio": pd.Timestamp(t[i - 1]), "fin": pd.Timestamp(t[j]),
                              "horas": round(horas, 1), "n_intervalos": n_int, "kwh_tipico_hora": tip, "kwh_esperado_periodo": esperado,
                              "kwh_reaparecido": post, "razon_reaparicion": razon, "medidores_quietos_pct": round(pct_quietos, 3),
                              "actividad_otros": actividad, "pct_horas_no_laborales": round(float(no_lab), 3),
                              "clasificacion": clase, "confianza": conf, "tratamiento": "medido", "evidencia": ev})
            i = j + 1

    # un congelamiento del SCADA afecta a la planta en el mismo periodo: si algún medidor del evento recupera su energía,
    # los demás medidores quietos del mismo periodo se tratan como parte del congelamiento (con confianza media)
    por_evento = {}
    for f in filas:
        por_evento.setdefault((f["inicio"], f["fin"]), []).append(f)
    for grupo in por_evento.values():
        con_reaparicion = [f for f in grupo if f["clasificacion"].startswith("congelamiento")]
        if not con_reaparicion:
            continue
        for f in grupo:
            if f["clasificacion"] in ("sin_consumo_planta", "constante_bajo_consumo", "sin_consumo_parcial") and f["_pct"] >= rachas["fraccion_medidores_quietos"]:
                f["clasificacion"], f["confianza"] = "congelamiento_scada_planta", "media"
                f["evidencia"] = (f"su propia energía no reaparece de forma clara, pero {len(con_reaparicion)} de {len(grupo)} medidores quietos "
                                  f"del mismo periodo sí la recuperan: se trata como parte del mismo congelamiento")
    for f in filas:
        if f["_frac_global"] >= 0.99:
            f["tratamiento"] = "estimado_planta"
        elif f["_frac_global"] > 0:
            f["tratamiento"] = "estimado_parcial"
        elif f["clasificacion"].startswith("congelamiento") and f["_fin"] is not None and rachas["corregir_congelamiento_por_medidor"]:
            f["tratamiento"] = "estimado_medidor"
            ventanas[f["medidor"]].append((t_sec[f["_i"] - 1], t_sec[f["_fin"]]))
            quitar_local[f["medidor"]].extend(t[f["_i"]:f["_j"] + 1])
    for f in filas:
        for c in ("_i", "_j", "_fin", "_frac_global", "_pct"):
            del f[c]
    tabla = pd.DataFrame(filas, columns=COLUMNAS_RACHAS)
    if len(tabla):
        tabla = tabla.sort_values(["inicio", "medidor"], kind="stable").reset_index(drop=True)
        tabla[["kwh_tipico_hora", "kwh_esperado_periodo", "kwh_reaparecido"]] = tabla[["kwh_tipico_hora", "kwh_esperado_periodo", "kwh_reaparecido"]].round(2)
        tabla[["razon_reaparicion", "actividad_otros"]] = tabla[["razon_reaparicion", "actividad_otros"]].round(3)
    return tabla, ventanas, quitar_local


def procesar_medidor(t, v, thr_x, max_h, ventanas, pct, hueco_h):
    """Contador acumulado -> consumo (Wh) por hora, con marca de calidad."""
    s = pd.DataFrame({"t": t.values, "v": v.values}).dropna()
    s = s[s["v"] > 0].sort_values("t").drop_duplicates("t", keep="last").reset_index(drop=True)
    if len(s) < 2:
        return None, {}
    sec = (s["t"] - ORIGEN).dt.total_seconds().to_numpy()
    val = s["v"].to_numpy(float)
    dt_h = np.diff(sec) / 3600.0
    d = np.diff(val)

    est = np.zeros(len(d), dtype=bool)
    for a, b in ventanas:
        est |= (np.abs(sec[:-1] - a) < 1) & (np.abs(sec[1:] - b) < 1)

    largo = (dt_h > max_h) & ~est
    pos = d[(dt_h <= hueco_h) & (d > 0)]
    thr = np.quantile(pos, pct) * thr_x if len(pos) else np.inf
    reinicio = (d < 0) & ~largo
    est_ok = est & ~reinicio
    salto = (d > thr) & ~largo & ~reinicio & ~est
    interp = (dt_h > hueco_h) & ~largo & ~reinicio & ~salto & ~est
    valido = ~(largo | reinicio | salto)

    cv = np.concatenate([[0.0], np.cumsum(np.where(valido, d, 0.0))])
    h0, h1 = math.ceil(sec[0] / 3600), math.floor(sec[-1] / 3600)
    if h1 <= h0:
        return None, {}
    marcas = np.arange(h0, h1 + 1) * 3600.0
    wh = np.diff(np.interp(marcas, sec, cv))
    n = len(wh)
    codigo = np.zeros(n, dtype=int)

    def marcar(mascara, c):
        for i in np.flatnonzero(mascara):
            lo = max(int(np.floor(sec[i] / 3600)) - h0, 0)
            hi = min(int(np.ceil(sec[i + 1] / 3600)) - 1 - h0, n - 1)
            if hi >= lo:
                codigo[lo:hi + 1] = c

    marcar(interp, 1)
    marcar(est_ok, 2)
    marcar(largo, 3)
    marcar(salto, 4)
    marcar(reinicio, 5)
    wh = np.where(codigo >= 3, np.nan, wh)

    horas = ORIGEN + pd.to_timedelta(marcas[:-1], unit="s")
    out = pd.DataFrame({"hora_inicio": horas, "wh": wh, "calidad": pd.Series(codigo).map(CALIDAD).to_numpy()})
    stats = {"lecturas": len(s), "reinicios": int(reinicio.sum()), "saltos": int(salto.sum()),
             "huecos_largos": int(largo.sum()), "huecos_interpolados": int(interp.sum()),
             "congelamientos_repartidos": int(est_ok.sum()), "umbral_salto_wh_por_intervalo": float(thr)}
    return out, stats


def procesar_planta(df, planta, medidores_proceso, cal, k, rachas=None, pais_festivos=None):
    """df: columna `t` y una columna por medidor (contadores acumulados).

    Devuelve (hora, resumen, congelamientos, filas_todo_cero, rachas). `hora` tiene una fila por medidor y hora.
    `rachas` (parámetros de config.yaml, grupo `rachas`) activa la clasificación de rachas sin cambio por medidor y, si
    `corregir_congelamiento_por_medidor` vale 1, el reparto de las que tienen reaparición de energía; sin él la tabla sale vacía.
    """
    medidores = [c for c in df.columns if c != "t"]
    df = df.sort_values("t").reset_index(drop=True)
    todo_cero = (df[medidores] == 0).all(axis=1)
    df = df[~todo_cero].reset_index(drop=True)

    vent, quitar = detectar_congelamientos(df, medidores_proceso, cal["min_intervalos_congelado"])
    cong = pd.DataFrame(vent)
    if len(cong):
        cong["consumo_acumulado_kwh"] = [
            round(sum(df.loc[r["idx_fin"], m] - df.loc[r["idx_inicio"], m] for m in medidores_proceso) * k, 1)
            if r["idx_fin"] is not None else np.nan for r in vent]
        cong = cong.drop(columns=["idx_inicio", "idx_fin"]).round({"horas": 1})
    ventanas_sec = [((pd.Timestamp(r["inicio"]) - ORIGEN).total_seconds(), (pd.Timestamp(r["fin"]) - ORIGEN).total_seconds())
                    for r in vent if r["idx_fin"] is not None]
    df_proc = df.drop(index=quitar).reset_index(drop=True)

    tabla_rachas, vent_local, quitar_local = pd.DataFrame(columns=COLUMNAS_RACHAS), {}, {}
    if rachas is not None:
        tabla_rachas, vent_local, quitar_local = analizar_rachas(df, medidores_proceso, cal, rachas, k, quitar, pais_festivos, planta)

    frames, resumen = [], []
    for m in medidores:
        t_m, v_m = df_proc["t"], df_proc[m]
        if quitar_local.get(m):
            sin = ~t_m.isin(pd.DatetimeIndex(quitar_local[m]))
            t_m, v_m = t_m[sin], v_m[sin]
        out, st = procesar_medidor(t_m, v_m, cal["umbral_salto_x_p99"], cal["max_horas_interpolar"], ventanas_sec + vent_local.get(m, []),
                                    cal["percentil_salto"], cal["umbral_hueco_interpolable_horas"])
        if out is None:
            print(f"  {m}: sin datos suficientes")
            continue
        out["medidor"] = m
        out["kwh"] = out["wh"] * k
        frames.append(out)
        conteo = out["calidad"].value_counts()
        resumen.append({"medidor": m, **st, **{f"horas_{c}": int(conteo.get(c, 0)) for c in CALIDAD.values()},
                        "horas_total": len(out),
                        "pct_horas_ok_o_interpoladas": round(100 * out["calidad"].isin(["ok", "interpolado"]).mean(), 1)})
    hora = pd.concat(frames, ignore_index=True)
    hora["planta"] = planta
    hora["turno"], hora["fecha_turno"] = turno_y_fecha(hora["hora_inicio"])
    hora["valida"] = hora["calidad"].isin(["ok", "interpolado"]) & hora["kwh"].notna()
    hora["valida_total"] = hora["calidad"].isin(["ok", "interpolado", "estimado"]) & hora["kwh"].notna()
    hora["kwh_v"] = hora["kwh"].where(hora["valida"])
    hora["kwh_t"] = hora["kwh"].where(hora["valida_total"])
    return hora, pd.DataFrame(resumen), cong, int(todo_cero.sum()), tabla_rachas


def tabla_cobertura_mensual(hora):
    """Cobertura temporal y de energía por planta, mes y medidor.

    cobertura_temporal: horas medidas (ok o interpoladas) sobre las horas posibles del mes.
    fraccion_energia_medida: kWh medidos sobre kWh medidos + kWh estimados (repartidos tras un congelamiento). Solo cuenta la energía
    que se conoce: las horas faltantes, saltos y reinicios no tienen energía conocida (no se extrapola), por eso se informan aparte
    en horas_sin_energia. No equivale a la cobertura temporal.
    """
    h = hora.copy()
    h["kwh"] = h["kwh"].round(3)  # igual que energia_hora, para que las sumas cuadren
    h["mes"] = h["hora_inicio"].dt.to_period("M")
    h["medida"] = h["calidad"].isin(["ok", "interpolado"])
    h["estimada"] = h["calidad"].eq("estimado")
    h["sin_energia"] = h["calidad"].isin(["faltante", "salto", "reinicio"])
    h["kwh_med"] = h["kwh"].where(h["medida"])
    h["kwh_est"] = h["kwh"].where(h["estimada"])
    c = (h.groupby(["planta", "mes", "medidor"])
         .agg(horas_con_dato=("calidad", "size"), horas_medidas=("medida", "sum"), horas_estimadas=("estimada", "sum"),
              horas_sin_energia=("sin_energia", "sum"), kwh_medido=("kwh_med", "sum"), kwh_estimado=("kwh_est", "sum")).reset_index())
    c["horas_posibles"] = c["mes"].dt.days_in_month * 24
    c["cobertura_temporal"] = (c["horas_medidas"] / c["horas_posibles"]).round(3)
    c["fraccion_energia_medida"] = (c["kwh_medido"] / (c["kwh_medido"] + c["kwh_estimado"]).replace(0, np.nan)).round(3)
    for col in ["horas_con_dato", "horas_medidas", "horas_estimadas", "horas_sin_energia"]:
        c[col] = c[col].astype(int)
    c[["kwh_medido", "kwh_estimado"]] = c[["kwh_medido", "kwh_estimado"]].round(3)
    c["mes"] = c["mes"].astype(str)
    return c[["planta", "mes", "medidor", "horas_posibles", "horas_con_dato", "horas_medidas", "horas_estimadas", "horas_sin_energia",
              "kwh_medido", "kwh_estimado", "cobertura_temporal", "fraccion_energia_medida"]]


def tablas_energia(hora):
    """energia_hora y energia_turno del contrato, a partir del resultado de procesar_planta."""
    eh = hora[["hora_inicio", "planta", "medidor", "kwh", "calidad"]].sort_values(["hora_inicio", "medidor"]).copy()
    eh["kwh"] = eh["kwh"].round(3)
    et = (hora.groupby(["fecha_turno", "turno", "planta", "medidor"])
          .agg(kwh=("kwh_v", "sum"), horas_validas=("valida", "sum")).reset_index())
    et["horas_validas"] = et["horas_validas"].astype(int)
    et["cobertura"] = (et["horas_validas"] / et["turno"].map(horas_por_turno())).round(2)
    et.loc[et["horas_validas"] == 0, "kwh"] = np.nan
    et["kwh"] = et["kwh"].round(3)
    et["fecha_turno"] = et["fecha_turno"].dt.date
    return eh, et


def actualizar_tabla(nombre, nueva, planta, columna_orden):
    """Reemplaza en data/clean/<nombre>.csv las filas de `planta` por `nueva` (conserva las demás plantas)."""
    ruta = CLEAN / f"{nombre}.csv"
    if ruta.exists():
        vieja = pd.read_csv(ruta)
        vieja = vieja[vieja["planta"] != planta]
        nueva = pd.concat([vieja, nueva.astype({c: str(vieja[c].dtype) for c in vieja.columns if c in nueva.columns and c in ("turno", "horas_validas")}, errors="ignore")], ignore_index=True)
    nueva = nueva.sort_values(columna_orden, kind="stable")
    nueva.to_csv(ruta, index=False)
    return nueva


def cargar_base_mensual(hoja, proceso):
    """Serie mensual (kWh) de la base de Clarios para un proceso de una hoja (por ejemplo 'RC Energia', 'RC')."""
    raw = RAIZ / "data" / "raw" / "Base de datos.xlsx"
    b = pd.read_excel(raw, sheet_name=hoja, header=1, engine="calamine")
    b.columns = [str(c).strip() for c in b.columns]
    b = b[b["Proceso"].astype(str).str.strip() == proceso].copy()
    b["mes"] = [pd.Period(year=int(a), month=MESES[str(m).strip().lower()[:3]], freq="M") for a, m in zip(b["Año"], b["Mes"])]
    return b.set_index("mes")["KWH"].astype(float).rename("kwh_base_clarios")
