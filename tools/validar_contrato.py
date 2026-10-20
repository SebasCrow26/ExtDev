"""Validador del contrato de datos del frente de Datos (solo lectura, determinista).

Comprueba que las tablas de data/clean cumplen config/contrato_datos.yaml y que son coherentes entre sí y con
las fuentes de referencia. No modifica ningún archivo ni corrige datos.

Uso (desde la raíz del repositorio):
    python tools/validar_contrato.py                  resumen en pantalla
    python tools/validar_contrato.py --json informe.json
    python tools/validar_contrato.py --estricto       trata también las advertencias como errores
    python tools/validar_contrato.py --sin-raw        omite la verificación de los archivos originales (SHA-256)
    python tools/validar_contrato.py --raiz RUTA      valida otra copia del repositorio (config, docs, data)

Severidades:
    crítico, alto   -> bloqueantes (código de salida 1)
    medio, bajo     -> advertencias (código de salida 0, o 1 con --estricto)
Código de salida 2: error de uso o de configuración (por ejemplo, falta el contrato).

Qué verifica (ver config/contrato_datos.yaml y documentacion/01_contrato_datos.md):
    1 entradas obligatorias (archivos originales por SHA-256 y tablas declaradas)   2 esquema y columnas
    3 tipos   4 unidades declaradas   5 claves y duplicados   6 nulos   7 rangos plausibles
    8 integridad temporal (continuidad y orden)   9 granularidad y agregaciones (hora -> turno -> día -> semana)
    10 consistencia entre fuentes   11 coherencia entre el contrato y las tablas   12 documentación de limitaciones
Lo que no se puede comprobar con los datos disponibles se declara en la sección "NO VERIFICABLE".
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

RAIZ_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ_REPO))
sys.path.insert(0, str(RAIZ_REPO / "tools"))
from src.comun.config import cargar_config, catalogo  # noqa: E402
from src.comun.turnos import horas_por_turno  # noqa: E402

TIPOS_PARAMETRO = ("dato_clarios", "supuesto", "metodologico", "tecnico")

ORDEN = {"critico": 0, "alto": 1, "medio": 2, "bajo": 3}
BLOQUEANTES = ("critico", "alto")
NOMBRE_SEV = {"critico": "CRÍTICO", "alto": "ALTO", "medio": "MEDIO", "bajo": "BAJO"}


class Informe:
    def __init__(self):
        self.pruebas, self.incidencias, self.no_verificables, self.supuestos = [], [], [], []

    def prueba(self, categoria, nombre, tabla, evaluados, problemas=()):
        """Registra una comprobación. `problemas`: lista de (severidad, detalle, n_registros_afectados)."""
        problemas = list(problemas)
        self.pruebas.append({"categoria": categoria, "prueba": nombre, "tabla": tabla, "evaluados": int(evaluados),
                             "resultado": "falla" if problemas else "ok"})
        for sev, detalle, n in problemas:
            self.incidencias.append({"id": f"I{len(self.incidencias) + 1:03d}", "severidad": sev, "categoria": categoria,
                                     "prueba": nombre, "tabla": tabla, "detalle": detalle, "n": int(n),
                                     "pct": round(100 * n / evaluados, 3) if evaluados else None, "estado": "abierta"})

    def no_verificable(self, nombre, razon):
        self.no_verificables.append({"prueba": nombre, "razon": razon})

    def bloqueantes(self):
        return [i for i in self.incidencias if i["severidad"] in BLOQUEANTES]


def convertir(s, tipo):
    """Convierte una columna leída como texto. Devuelve (serie tipada, máscara de valores inválidos, máscara de vacíos)."""
    vacio = s == ""
    nulo = pd.Series(False, index=s.index)
    if tipo == "str":
        return s.where(~vacio), nulo, vacio
    if tipo in ("int", "bin", "float"):
        x = pd.to_numeric(s.where(~vacio), errors="coerce")
        invalido = (~vacio) & (x.isna() | np.isinf(x))
        if tipo in ("int", "bin"):
            invalido |= x.notna() & (x != np.floor(x.fillna(0)))
        return x, invalido, vacio
    if tipo == "fecha":
        x = pd.to_datetime(s.where(~vacio), format="%Y-%m-%d", errors="coerce")
        return x, (~vacio) & x.isna(), vacio
    if tipo == "mes":
        x = pd.to_datetime(s.where(~vacio), format="%Y-%m", errors="coerce")
        return x, (~vacio) & x.isna(), vacio
    if tipo == "fechahora":
        x = pd.to_datetime(s.where(~vacio), format="ISO8601", errors="coerce")
        return x, (~vacio) & x.isna(), vacio
    if tipo == "bool":
        x = s.map({"True": True, "False": False})
        return x, (~vacio) & x.isna(), vacio
    raise ValueError(f"tipo desconocido en el contrato: {tipo}")


def ejemplo(mask, df, cols, k=2):
    sub = df.loc[mask, [c for c in cols if c in df.columns]].head(k)
    return "; ".join(" | ".join(str(v) for v in fila) for fila in sub.itertuples(index=False))  # str(v) también aguanta los NaN


def validar_tabla(nombre, spec, clean, inf):
    ruta = clean / f"{nombre}.csv"
    if not ruta.exists():
        inf.prueba("estructura", "existencia del archivo", nombre, 1, [("critico", f"no existe {ruta.name}", 1)])
        return None
    inf.prueba("estructura", "existencia del archivo", nombre, 1)
    crudo = pd.read_csv(ruta, dtype=str, keep_default_na=False)
    n = len(crudo)
    inf.prueba("estructura", "la tabla no está vacía", nombre, 1, [("critico", "sin filas", 1)] if n == 0 else [])
    cols = spec["columnas"]
    faltan = [c for c in cols if c not in crudo.columns]
    sobran = [c for c in crudo.columns if c not in cols]
    inf.prueba("esquema", "columnas obligatorias presentes", nombre, len(cols), [("critico", f"faltan columnas: {faltan}", len(faltan))] if faltan else [])
    inf.prueba("esquema", "sin columnas no declaradas (cambio de esquema)", nombre, len(crudo.columns),
               [("medio", f"columnas no declaradas en el contrato: {sobran}", len(sobran))] if sobran else [])
    if faltan or n == 0:
        return None

    df = pd.DataFrame(index=crudo.index)
    vacios = {}
    for c, e in cols.items():
        x, inval, vac = convertir(crudo[c], e["tipo"])
        df[c] = x
        vacios[c] = vac
        inf.prueba("tipos", f"tipo {e['tipo']} válido en `{c}`", nombre, n,
                   [("critico", f"valores no válidos para {e['tipo']}. Ej.: {ejemplo(inval, crudo, [c])}", int(inval.sum()))] if inval.any() else [])

    clave = spec.get("clave", [])
    for c, e in cols.items():
        if e.get("nulo", False):
            continue
        k = int(vacios[c].sum())
        sev = "critico" if c in clave else "alto"
        inf.prueba("nulos", f"`{c}` sin nulos", nombre, n, [(sev, f"{k} valores vacíos. Ej.: {ejemplo(vacios[c], crudo, clave[:3] + [c])}", k)] if k else [])

    nc = spec.get("nulo_condicionado")
    if nc:
        col, cond, vals = nc["columna"], nc["si"], nc["valores_nulos"]
        debe_ser_nulo = crudo[cond].isin(vals)
        a = vacios[col] & ~debe_ser_nulo
        b = ~vacios[col] & debe_ser_nulo
        inf.prueba("nulos", f"`{col}` nulo solo si `{cond}` es {vals}", nombre, n,
                   [p for p in [("alto", f"{int(a.sum())} nulos con {cond} válido. Ej.: {ejemplo(a, crudo, clave)}", int(a.sum())) if a.any() else None,
                                ("alto", f"{int(b.sum())} valores presentes con {cond} en {vals}", int(b.sum())) if b.any() else None] if p])

    for c, e in cols.items():
        x, ok = df[c], ~vacios[c]
        if "permitidos" in e:
            malos = ok & ~crudo[c].isin([str(v) for v in e["permitidos"]])
            inf.prueba("valores", f"`{c}` dentro de los valores permitidos {e['permitidos']}", nombre, int(ok.sum()),
                       [("alto", f"valores fuera de la lista. Ej.: {ejemplo(malos, crudo, [c])}", int(malos.sum()))] if malos.any() else [])
        if e["tipo"] in ("int", "bin", "float"):
            lo, hi = e.get("min", -np.inf), e.get("max", np.inf)
            if e["tipo"] == "bin":
                lo, hi = 0, 1
            malos = ok & x.notna() & ((x < lo) | (x > hi))
            if "min" in e or "max" in e or e["tipo"] == "bin":
                inf.prueba("rangos", f"`{c}` dentro del rango [{lo}, {hi}]", nombre, int(ok.sum()),
                           [("alto", f"fuera de rango imposible. Ej.: {ejemplo(malos, crudo, clave[:2] + [c])}", int(malos.sum()))] if malos.any() else [])
            plo, phi = e.get("plausible_min", -np.inf), e.get("plausible_max", np.inf)
            if "plausible_min" in e or "plausible_max" in e:
                raros = ok & x.notna() & ((x < plo) | (x > phi))
                inf.prueba("rangos", f"`{c}` dentro del rango plausible [{plo}, {phi}]", nombre, int(ok.sum()),
                           [("medio", f"fuera de lo plausible. Ej.: {ejemplo(raros, crudo, clave[:2] + [c])}", int(raros.sum()))] if raros.any() else [])

    if clave:
        dup = crudo.duplicated(clave, keep=False)
        inf.prueba("claves", f"clave única {clave}", nombre, n,
                   [("critico", f"{int(dup.sum())} filas con clave repetida. Ej.: {ejemplo(dup, crudo, clave)}", int(dup.sum()))] if dup.any() else [])

    cont = spec.get("continuidad")
    if cont:
        problemas, evaluados = continuidad(df, cont, clave)
        inf.prueba("temporal", f"continuidad sin huecos ({cont['paso']})", nombre, evaluados, problemas)
        grupos = cont.get("agrupar_por", [])
        col = cont["columna"]
        desorden = 0
        orden = df.dropna(subset=[col] + list(grupos))
        for _, g in (orden.groupby(grupos, dropna=False) if grupos else [(None, orden)]):
            if not g[col].is_monotonic_increasing:
                desorden += 1
        inf.prueba("temporal", "registros en orden cronológico", nombre, max(1, df[grupos].drop_duplicates().shape[0] if grupos else 1),
                   [("bajo", f"{desorden} series con registros fuera de orden", desorden)] if desorden else [])
    return df


def continuidad(df, cont, clave):
    col, paso, grupos = cont["columna"], cont["paso"], cont.get("agrupar_por", [])
    obligatorias = [col] + (["turno"] if paso == "turnos" else []) + list(grupos)
    df = df.dropna(subset=obligatorias)  # las filas con fecha, turno o grupo vacíos o inválidos ya se reportan en tipos y nulos
    problemas, evaluados, huecos = [], 0, 0
    ejemplos = []
    for g, d in (df.groupby(grupos, dropna=False) if grupos else [(None, df)]):
        if paso == "turnos":
            t = d[col].dt.normalize().map(pd.Timestamp.toordinal) * 3 + (d["turno"].astype(int) - 1)
        elif paso == "horas":
            t = (d[col] - pd.Timestamp("2000-01-01")).dt.total_seconds() / 3600
        elif paso == "dias":
            t = d[col].map(pd.Timestamp.toordinal)
        elif paso == "semanas":
            t = d[col].map(pd.Timestamp.toordinal) / 7
        elif paso == "meses":
            t = d[col].dt.year * 12 + d[col].dt.month
        else:
            raise ValueError(f"paso de continuidad desconocido: {paso}")
        dif = np.diff(np.sort(t.unique().astype(float)))
        evaluados += len(dif)
        mal = dif != 1
        huecos += int(mal.sum())
        if mal.any() and len(ejemplos) < 2:
            ejemplos.append(f"{g}: {int(mal.sum())} saltos (mayor {dif.max():g} pasos)")
    if huecos:
        problemas.append(("alto", f"{huecos} huecos o duplicados de intervalo. Ej.: {'; '.join(ejemplos)}", huecos))
    return problemas, evaluados


def tiene(tablas, *nombres):
    return all(tablas.get(n) is not None for n in nombres)


def cruzadas(tablas, cfg, contrato, inf, minc, raiz):
    v = contrato["validaciones"]
    n_turnos = len(horas_por_turno(cfg))
    tolk, tolp = v["tolerancia_kwh_agregacion"], v["tolerancia_produccion_agregacion"]

    # unidades declaradas: la unidad de producción debe coincidir con el mapa de procesos
    if tiene(tablas, "mapa_procesos", "dataset_modelo"):
        u = tablas["mapa_procesos"].set_index("proceso_modelo")["unidad_produccion"]
        dm = tablas["dataset_modelo"]
        esperado = dm["proceso_modelo"].map(u)
        malos = esperado.notna() & (esperado != dm["unidad"])
        inf.prueba("unidades", "unidad de dataset_modelo = unidad del mapa de procesos", "dataset_modelo", len(dm),
                   [("alto", f"{int(malos.sum())} filas con unidad distinta a la del proceso. Ej.: {ejemplo(malos, dm, ['proceso_modelo', 'unidad'])}", int(malos.sum()))] if malos.any() else [])
    if tiene(tablas, "mapa_procesos", "produccion_turno"):
        u = tablas["mapa_procesos"].set_index("proceso_modelo")["unidad_produccion"]
        pt = tablas["produccion_turno"]
        con = pt["proceso_modelo"].notna()
        esperado = pt["proceso_modelo"].map(u)
        mapeado_unidad = {"kg": "kg", "unidades": "unidades"}
        malos = con & esperado.notna() & (esperado.map(mapeado_unidad) != pt["unidad"])
        inf.prueba("unidades", "unidad de produccion_turno = unidad del proceso del mapa", "produccion_turno", int(con.sum()),
                   [("alto", f"{int(malos.sum())} filas con unidad distinta. Ej.: {ejemplo(malos, pt, ['linea_erp', 'proceso_modelo', 'unidad'])}", int(malos.sum()))] if malos.any() else [])

    # medidores del SCADA frente al mapa de procesos
    if tiene(tablas, "mapa_procesos", "energia_turno"):
        mapeados = set(m for s in tablas["mapa_procesos"]["medidores_scada"].dropna() for m in str(s).split(";") if m)
        vistos = set(tablas["energia_turno"]["medidor"].unique())
        sin_mapa = sorted(vistos - mapeados)
        inf.prueba("coherencia", "todo medidor con energía está en el mapa de procesos", "mapa_procesos", len(vistos),
                   [("alto", f"medidores sin proceso en el mapa: {sin_mapa}", len(sin_mapa))] if sin_mapa else [])

    # hora -> turno
    if tiene(tablas, "energia_hora", "energia_turno"):
        from src.comun.turnos import turno_y_fecha
        eh, et = tablas["energia_hora"].copy(), tablas["energia_turno"]
        eh["turno"], eh["fecha_turno"] = turno_y_fecha(eh["hora_inicio"])
        valida = eh["calidad"].isin(["ok", "interpolado"]) & eh["kwh"].notna()
        eh["kwh_v"], eh["valida"] = eh["kwh"].where(valida), valida
        agg = eh.groupby(["planta", "medidor", "fecha_turno", "turno"]).agg(kwh_re=("kwh_v", "sum"), horas_re=("valida", "sum")).reset_index()
        m = et.merge(agg, on=["planta", "medidor", "fecha_turno", "turno"], how="outer", indicator=True)
        solo = m["_merge"] != "both"
        inf.prueba("agregaciones", "turnos de energia_turno = turnos reagregados desde energia_hora", "energia_turno", len(m),
                   [("critico", f"{int(solo.sum())} turnos presentes en una sola de las dos tablas. Ej.: {ejemplo(solo, m, ['planta', 'medidor', 'fecha_turno', 'turno'])}", int(solo.sum()))] if solo.any() else [])
        both = m[~solo]
        dk = (both["kwh"].fillna(0) - both["kwh_re"]).abs() > tolk
        inf.prueba("agregaciones", "kWh por turno = suma de horas válidas", "energia_turno", len(both),
                   [("critico", f"{int(dk.sum())} turnos con diferencia mayor a {tolk} kWh. Ej.: {ejemplo(dk, both, ['medidor', 'fecha_turno', 'turno', 'kwh', 'kwh_re'])}", int(dk.sum()))] if dk.any() else [])
        dh = both["horas_validas"] != both["horas_re"]
        inf.prueba("agregaciones", "horas_validas = horas válidas reagregadas", "energia_turno", len(both),
                   [("critico", f"{int(dh.sum())} turnos con horas distintas", int(dh.sum()))] if dh.any() else [])
        dc = (both["cobertura"] - both["horas_validas"] / 8).abs() > 0.006
        inf.prueba("agregaciones", "cobertura = horas_validas / 8", "energia_turno", len(both),
                   [("medio", f"{int(dc.sum())} filas con cobertura inconsistente", int(dc.sum()))] if dc.any() else [])
    else:
        inf.no_verificable("hora -> turno", "faltan energia_hora o energia_turno")

    # dataset_modelo frente a sus fuentes: la energía de los medidores del proceso y la producción de sus líneas
    if tiene(tablas, "dataset_modelo", "mapa_procesos", "energia_turno"):
        dm, mp, et = tablas["dataset_modelo"], tablas["mapa_procesos"], tablas["energia_turno"]
        partes = []
        for r in mp.dropna(subset=["medidores_scada"]).itertuples():
            meds = [x for x in str(r.medidores_scada).split(";") if x]
            e = et[et["medidor"].isin(meds)].groupby(["fecha_turno", "turno"]).agg(esperado=("kwh", "sum"), n=("medidor", "nunique")).reset_index()
            partes.append(e[e["n"] == len(meds)].assign(proceso_modelo=r.proceso_modelo)[["fecha_turno", "turno", "proceso_modelo", "esperado"]])
        esp = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=["fecha_turno", "turno", "proceso_modelo", "esperado"])
        m = dm[["fecha_turno", "turno", "proceso_modelo", "kwh_observado"]].merge(esp, on=["fecha_turno", "turno", "proceso_modelo"], how="left")
        sin = m["esperado"].isna()
        d = ~sin & ((m["kwh_observado"] - m["esperado"]).abs() > tolk)
        inf.prueba("agregaciones", "kwh_observado de dataset_modelo = suma de energia_turno de los medidores del proceso", "dataset_modelo", len(m),
                   [p for p in [("alto", f"{int(sin.sum())} turnos sin energía de origen en energia_turno. Ej.: {ejemplo(sin, m, ['fecha_turno', 'turno', 'proceso_modelo'])}", int(sin.sum())) if sin.any() else None,
                                ("alto", f"{int(d.sum())} turnos con kwh_observado distinto de energia_turno. Ej.: {ejemplo(d, m, ['fecha_turno', 'turno', 'proceso_modelo', 'kwh_observado', 'esperado'])}", int(d.sum())) if d.any() else None] if p])
    else:
        inf.no_verificable("dataset_modelo contra energia_turno", "faltan dataset_modelo, mapa_procesos o energia_turno")
    if tiene(tablas, "dataset_modelo", "mapa_procesos", "produccion_turno"):
        dm, mp, pt = tablas["dataset_modelo"], tablas["mapa_procesos"], tablas["produccion_turno"]
        asoc = cfg["modelado"]["procesos_asociados"]
        lineas = {r.proceso_modelo: ([x for x in str(r.lineas_erp).split(";") if x] if pd.notna(r.lineas_erp) else []) for r in mp.itertuples()}
        partes = []
        for proc in dm["proceso_modelo"].unique():
            ls = lineas.get(asoc.get(proc, proc), [])
            p_ = pt[pt["linea_erp"].isin(ls)].groupby(["fecha_turno", "turno"])["cantidad"].sum().reset_index().rename(columns={"cantidad": "esperada"})
            partes.append(p_.assign(proceso_modelo=proc))
        esp = pd.concat(partes, ignore_index=True)
        m = dm[["fecha_turno", "turno", "proceso_modelo", "produccion"]].merge(esp, on=["fecha_turno", "turno", "proceso_modelo"], how="left")
        m["esperada"] = m["esperada"].fillna(0)
        d = (m["produccion"] - m["esperada"]).abs() > tolp
        inf.prueba("agregaciones", "produccion de dataset_modelo = suma de produccion_turno de las líneas del proceso", "dataset_modelo", len(m),
                   [("alto", f"{int(d.sum())} turnos con producción distinta de produccion_turno. Ej.: {ejemplo(d, m, ['fecha_turno', 'turno', 'proceso_modelo', 'produccion', 'esperada'])}", int(d.sum()))] if d.any() else [])
    else:
        inf.no_verificable("dataset_modelo contra produccion_turno", "faltan dataset_modelo, mapa_procesos o produccion_turno")

    # rachas por medidor y cobertura frente a energia_hora
    if tiene(tablas, "rachas_constantes_energia", "energia_hora"):
        rc_, eh = tablas["rachas_constantes_energia"], tablas["energia_hora"]
        corr = rc_[rc_["tratamiento"].isin(["estimado_planta", "estimado_medidor"])]
        h = eh.assign(estim=eh["calidad"].eq("estimado")).set_index(["planta", "medidor", "hora_inicio"])["estim"]
        malas = []
        for r in corr.itertuples():
            horas = pd.date_range(r.inicio.ceil("h"), r.fin.floor("h"), freq="h", inclusive="left")
            if len(horas) == 0:
                continue
            idx = pd.MultiIndex.from_arrays([[r.planta] * len(horas), [r.medidor] * len(horas), horas])
            frac = h.reindex(idx).fillna(False).mean()
            if frac < 0.99:
                malas.append(f"{r.planta}/{r.medidor} {r.inicio:%Y-%m-%d %H:%M} ({frac:.0%} de sus horas estimadas)")
        inf.prueba("coherencia", "toda racha corregida tiene sus horas marcadas `estimado` en energia_hora", "rachas_constantes_energia", len(corr),
                   [("alto", f"{len(malas)} rachas tratadas como estimadas sin sus horas estimadas. Ej.: {malas[:2]}", len(malas))] if malas else [])
        sin_corr = rc_[(rc_["tratamiento"] == "medido") & rc_["clasificacion"].str.startswith("congelamiento")]
        activa = bool(cfg["rachas"]["corregir_congelamiento_por_medidor"])
        inf.prueba("coherencia", "ningún congelamiento del SCADA queda sin tratar como estimado (si la corrección por medidor está activa)", "rachas_constantes_energia", len(rc_),
                   [("alto", f"{len(sin_corr)} congelamientos con tratamiento `medido`", len(sin_corr))] if len(sin_corr) and activa else [])
    else:
        inf.no_verificable("rachas -> energia_hora", "faltan rachas_constantes_energia o energia_hora")
    if tiene(tablas, "cobertura_energia_mensual", "energia_hora"):
        cv, eh = tablas["cobertura_energia_mensual"], tablas["energia_hora"].copy()
        eh["mes"] = eh["hora_inicio"].dt.to_period("M").dt.to_timestamp()
        eh["medida"] = eh["calidad"].isin(["ok", "interpolado"])
        eh["kwh_med"] = eh["kwh"].where(eh["medida"])
        g = eh.groupby(["planta", "mes", "medidor"]).agg(hm=("medida", "sum"), n=("calidad", "size"), km=("kwh_med", "sum")).reset_index()
        m = cv.merge(g, on=["planta", "mes", "medidor"], how="outer", indicator=True)
        solo = m["_merge"] != "both"
        inf.prueba("agregaciones", "cobertura mensual: mismas combinaciones planta-mes-medidor que energia_hora", "cobertura_energia_mensual", len(m),
                   [("critico", f"{int(solo.sum())} combinaciones en una sola tabla. Ej.: {ejemplo(solo, m, ['planta', 'mes', 'medidor'])}", int(solo.sum()))] if solo.any() else [])
        b = m[~solo]
        d1 = (b["horas_medidas"] != b["hm"]) | (b["horas_con_dato"] != b["n"])
        d2 = (b["kwh_medido"] - b["km"]).abs() > tolk
        d3 = (b["horas_medidas"] + b["horas_estimadas"] + b["horas_sin_energia"]) != b["horas_con_dato"]
        for nom, d, sev in [("horas = horas de energia_hora", d1, "critico"), ("kWh medido = suma de horas medidas de energia_hora", d2, "critico"),
                            ("horas medidas + estimadas + sin energía = horas con dato", d3, "alto")]:
            inf.prueba("agregaciones", f"cobertura mensual: {nom}", "cobertura_energia_mensual", len(b),
                       [(sev, f"{int(d.sum())} filas inconsistentes. Ej.: {ejemplo(d, b, ['planta', 'mes', 'medidor'])}", int(d.sum()))] if d.any() else [])
        dc = (b["cobertura_temporal"] - b["horas_medidas"] / b["horas_posibles"]).abs() > 0.001
        inf.prueba("agregaciones", "cobertura temporal = horas medidas / horas posibles del mes", "cobertura_energia_mensual", len(b),
                   [("medio", f"{int(dc.sum())} filas con cobertura inconsistente", int(dc.sum()))] if dc.any() else [])
    else:
        inf.no_verificable("cobertura mensual -> energia_hora", "faltan cobertura_energia_mensual o energia_hora")

    # resultados del frente de Modelos frente a las tablas de Datos
    if tiene(tablas, "resultados_modelo", "dataset_modelo"):
        rm, dm = tablas["resultados_modelo"], tablas["dataset_modelo"]
        m = rm.merge(dm[["fecha_turno", "turno", "proceso_modelo", "kwh", "calidad_ok"]], on=["fecha_turno", "turno", "proceso_modelo"], how="left")
        sin = m["kwh"].isna()
        inf.prueba("coherencia", "todo resultado del modelo tiene su turno con energía en dataset_modelo", "resultados_modelo", len(m),
                   [("alto", f"{int(sin.sum())} resultados sin turno válido en dataset_modelo. Ej.: {ejemplo(sin, m, ['fecha_turno', 'turno', 'proceso_modelo'])}", int(sin.sum()))] if sin.any() else [])
        b = m[~sin]
        d1 = (b["kwh_real"] - b["kwh"]).abs() > tolk
        inf.prueba("coherencia", "kwh_real del modelo = kwh de dataset_modelo (el modelo usa los datos vigentes)", "resultados_modelo", len(b),
                   [("alto", f"{int(d1.sum())} turnos con kwh_real distinto de dataset_modelo (¿modelo entrenado con una versión anterior de las tablas?). Ej.: {ejemplo(d1, b, ['fecha_turno', 'turno', 'proceso_modelo', 'kwh_real', 'kwh'])}", int(d1.sum()))] if d1.any() else [])
        d2 = (rm["exceso_kwh"] - (rm["kwh_real"] - rm["kwh_esperado"])).abs() > 0.01
        inf.prueba("agregaciones", "exceso_kwh = kwh_real - kwh_esperado", "resultados_modelo", len(rm),
                   [("medio", f"{int(d2.sum())} filas con exceso inconsistente. Ej.: {ejemplo(d2, rm, ['fecha_turno', 'turno', 'proceso_modelo', 'exceso_kwh'])}", int(d2.sum()))] if d2.any() else [])
        d3 = ((rm["kwh_real"] - rm["kwh_esperado"]) <= 0.01) & (rm["costo_exceso_cop"] > 10)  # tolera el redondeo (0.01 kWh, unos 5 COP)
        inf.prueba("coherencia", "costo_exceso_cop es cero cuando no hay exceso", "resultados_modelo", len(rm),
                   [("medio", f"{int(d3.sum())} filas con costo sin exceso", int(d3.sum()))] if d3.any() else [])
    else:
        inf.no_verificable("resultados del modelo contra dataset_modelo", "faltan resultados_modelo o dataset_modelo")
    if tiene(tablas, "pronostico"):
        pr = tablas["pronostico"]
        d = (pr["kwh_inferior"] > pr["kwh_pronosticado"] + 0.01) | (pr["kwh_pronosticado"] > pr["kwh_superior"] + 0.01)
        inf.prueba("coherencia", "pronóstico: kwh_inferior <= kwh_pronosticado <= kwh_superior", "pronostico", len(pr),
                   [("medio", f"{int(d.sum())} filas con intervalo incoherente. Ej.: {ejemplo(d, pr, ['fecha', 'proceso_modelo', 'escenario'])}", int(d.sum()))] if d.any() else [])

    # turno -> día -> semana
    if tiene(tablas, "dataset_modelo", "dataset_modelo_dia"):
        dm, dd = tablas["dataset_modelo"], tablas["dataset_modelo_dia"]
        g = dm.groupby(["fecha_turno", "proceso_modelo"]).agg(ko=("kwh_observado", "sum"), pr=("produccion", "sum"), nt=("n_transacciones", "sum"), nturnos=("turno", "size")).reset_index().rename(columns={"fecha_turno": "fecha"})
        m = dd.merge(g, on=["fecha", "proceso_modelo"], how="left")
        sin = m["nturnos"].isna()
        inf.prueba("agregaciones", "cada día del dataset diario existe en el dataset por turno", "dataset_modelo_dia", len(m),
                   [("critico", f"{int(sin.sum())} días sin turnos de origen", int(sin.sum()))] if sin.any() else [])
        m = m[~sin]
        inc = m["nturnos"] != n_turnos
        inf.prueba("granularidad", f"los días del dataset diario tienen sus {n_turnos} turnos", "dataset_modelo_dia", len(m),
                   [("alto", f"{int(inc.sum())} días con menos de {n_turnos} turnos (intervalo incompleto)", int(inc.sum()))] if inc.any() else [])
        d1 = (m["kwh_observado"] - m["ko"]).abs() > tolk
        d2 = (m["produccion"] - m["pr"]).abs() > tolp
        d3 = m["n_transacciones"] != m["nt"]
        for nom, d, col in [("kWh observado", d1, "kwh_observado"), ("producción", d2, "produccion"), ("n_transacciones", d3, "n_transacciones")]:
            inf.prueba("agregaciones", f"día = suma de sus turnos ({nom})", "dataset_modelo_dia", len(m),
                       [("critico", f"{int(d.sum())} días no suman. Ej.: {ejemplo(d, m, ['fecha', 'proceso_modelo', col])}", int(d.sum()))] if d.any() else [])
        completos = g[g["nturnos"] == n_turnos].merge(dd[["fecha", "proceso_modelo"]], on=["fecha", "proceso_modelo"], how="left", indicator=True)
        falt = completos["_merge"] == "left_only"
        inf.prueba("agregaciones", "todo día completo del dataset por turno está en el dataset diario", "dataset_modelo_dia", len(completos),
                   [("alto", f"{int(falt.sum())} días completos ausentes del dataset diario", int(falt.sum()))] if falt.any() else [])
    else:
        inf.no_verificable("turno -> día", "faltan dataset_modelo o dataset_modelo_dia")
    if tiene(tablas, "dataset_modelo_dia", "dataset_modelo_semana"):
        dd, ds = tablas["dataset_modelo_dia"].copy(), tablas["dataset_modelo_semana"]
        dd["semana_inicio"] = dd["fecha"] - pd.to_timedelta(dd["fecha"].dt.dayofweek, unit="D")
        g = dd.groupby(["semana_inicio", "proceso_modelo"]).agg(ko=("kwh_observado", "sum"), pr=("produccion", "sum"), nt=("n_transacciones", "sum"),
                                                              nf=("es_festivo", "sum"), ndias=("fecha", "size")).reset_index()
        m = ds.merge(g, on=["semana_inicio", "proceso_modelo"], how="left")
        sin = m["ndias"].isna()
        inf.prueba("agregaciones", "cada semana del dataset semanal existe en el dataset diario", "dataset_modelo_semana", len(m),
                   [("critico", f"{int(sin.sum())} semanas sin días de origen", int(sin.sum()))] if sin.any() else [])
        m = m[~sin]
        inc = m["ndias"] != 7
        inf.prueba("granularidad", "las semanas del dataset semanal tienen sus 7 días", "dataset_modelo_semana", len(m),
                   [("alto", f"{int(inc.sum())} semanas incompletas", int(inc.sum()))] if inc.any() else [])
        for nom, d, col in [("kWh observado", (m["kwh_observado"] - m["ko"]).abs() > tolk, "kwh_observado"), ("producción", (m["produccion"] - m["pr"]).abs() > tolp, "produccion"),
                            ("n_transacciones", m["n_transacciones"] != m["nt"], "n_transacciones"), ("días festivos", m["dias_festivos"] != m["nf"], "dias_festivos")]:
            inf.prueba("agregaciones", f"semana = suma de sus días ({nom})", "dataset_modelo_semana", len(m),
                       [("critico", f"{int(d.sum())} semanas no suman. Ej.: {ejemplo(d, m, ['semana_inicio', 'proceso_modelo', col])}", int(d.sum()))] if d.any() else [])
    else:
        inf.no_verificable("día -> semana", "faltan dataset_modelo_dia o dataset_modelo_semana")

    # reescalado por cobertura y calidad_ok
    for nombre in ("dataset_modelo", "dataset_modelo_dia", "dataset_modelo_semana"):
        if not tiene(tablas, nombre):
            continue
        t = tablas[nombre]
        ok = t["cobertura"] >= minc
        esperado = np.where(ok, t["kwh_observado"] / t["cobertura"].replace(0, np.nan), np.nan)
        mal_nulo = (~ok & t["kwh"].notna()) | (ok & t["kwh"].isna())
        mal_valor = ok & t["kwh"].notna() & (np.abs(t["kwh"] - esperado) > 0.01)
        inf.prueba("agregaciones", f"kwh = kwh_observado / cobertura (cobertura mínima {minc})", nombre, len(t),
                   [p for p in [("alto", f"{int(mal_nulo.sum())} filas con kwh nulo o presente contra la regla de cobertura", int(mal_nulo.sum())) if mal_nulo.any() else None,
                                ("alto", f"{int(mal_valor.sum())} filas con kwh mal reescalado", int(mal_valor.sum())) if mal_valor.any() else None] if p])
        dq = (t["calidad_ok"] == 1) != ok
        inf.prueba("coherencia", f"calidad_ok = (cobertura >= {minc})", nombre, len(t),
                   [("alto", f"{int(dq.sum())} filas con calidad_ok incoherente", int(dq.sum()))] if dq.any() else [])
    if tiene(tablas, "calendario_operacion", "dataset_modelo"):
        m = tablas["dataset_modelo"].merge(tablas["calendario_operacion"], on=["fecha_turno", "turno", "proceso_modelo"], how="outer", suffixes=("", "_cal"), indicator=True)
        solo = m["_merge"] != "both"
        dif = (m["_merge"] == "both") & (m["operando"].fillna(-1) != m["operando_cal"].fillna(-1))
        inf.prueba("coherencia", "calendario_operacion coincide con dataset_modelo", "calendario_operacion", len(m),
                   [p for p in [("alto", f"{int(solo.sum())} turnos en una sola tabla", int(solo.sum())) if solo.any() else None,
                                ("alto", f"{int(dif.sum())} turnos con `operando` distinto", int(dif.sum())) if dif.any() else None] if p])

    # consistencia entre fuentes
    if tiene(tablas, "produccion_turno", "base_mensual_plantas"):
        pt, bm = tablas["produccion_turno"], tablas["base_mensual_plantas"]
        ref = pt[pt["linea_erp"].isin(["RCREFI01", "RCREFI02", "RCREFI03"])].copy()
        ref["mes"] = ref["fecha_turno"].dt.to_period("M").dt.to_timestamp()
        erp = (ref.groupby("mes")["cantidad"].sum() / 1000).rename("erp_t")
        base = bm[bm["planta"] == "RC"].set_index("mes")["produccion_equivalente"].rename("base_t")
        j = pd.concat([erp, base], axis=1, sort=True).dropna()
        j = j[j.index >= erp.index.min()]
        if len(j) == 0:
            inf.no_verificable("producción del ERP contra producción equivalente de RC", "no hay meses en común")
        else:
            tol = v["tolerancia_toneladas_produccion_rc"]
            d = (j["erp_t"] - j["base_t"]).abs() > tol
            inf.prueba("fuentes", f"refinación del ERP (t) = producción equivalente de RC de la base (tolerancia {tol} t)", "produccion_turno", len(j),
                       [("alto", f"{int(d.sum())} meses con diferencia mayor a {tol} t. Ej.: {j[d].round(2).head(2).to_dict('index')}", int(d.sum()))] if d.any() else [])
    if tiene(tablas, "metas_clarios", "base_mensual_plantas"):
        mt, bm = tablas["metas_clarios"], tablas["base_mensual_plantas"]
        malos = 0
        for _, r in mt.iterrows():
            b = bm[(bm["planta"] == r["planta"]) & (bm["mes"] >= r["vigente_desde"]) & (bm["mes"] <= r["vigente_hasta"])]["kwh_por_eq_presupuesto"].dropna()
            if len(b) == 0 or (b - r["kwh_por_eq_meta"]).abs().max() > 0.01:
                malos += 1
        inf.prueba("fuentes", "metas_clarios = presupuesto de la base mensual", "metas_clarios", len(mt),
                   [("alto", f"{malos} metas que no coinciden con la base", malos)] if malos else [])
    if tiene(tablas, "tarifa_kwh_mensual", "base_mensual_plantas"):
        tf, bm = tablas["tarifa_kwh_mensual"], tablas["base_mensual_plantas"]
        media = bm.dropna(subset=["costo_kwh_cop"]).groupby("mes")["costo_kwh_cop"].mean()
        m = tf.set_index("mes")["costo_kwh_cop"].to_frame().join(media.rename("base"), how="outer")
        malos = (m["costo_kwh_cop"] - m["base"]).abs().fillna(np.inf) > 0.01
        inf.prueba("fuentes", "tarifa mensual = promedio de la base de Clarios", "tarifa_kwh_mensual", len(m),
                   [("alto", f"{int(malos.sum())} meses distintos", int(malos.sum()))] if malos.any() else [])
    rmin, rmax = v["razon_energia_vs_base"]["minimo"], v["razon_energia_vs_base"]["maximo"]
    if tiene(tablas, "validacion_energia_rc_mensual"):
        t = tablas["validacion_energia_rc_mensual"]
        t = t[(t["mes_completo"] == True) & t["ratio_scada_vs_base"].notna()]
        fuera = (t["ratio_scada_vs_base"] < rmin) | (t["ratio_scada_vs_base"] > rmax)
        inf.prueba("fuentes", f"energía SCADA de RC / base de Clarios dentro de [{rmin}, {rmax}] (meses completos)", "validacion_energia_rc_mensual", len(t),
                   [("medio", f"{int(fuera.sum())} meses fuera del rango. Ej.: {ejemplo(fuera, t.astype(str), ['mes', 'ratio_scada_vs_base'])}", int(fuera.sum()))] if fuera.any() else [])
    if tiene(tablas, "validacion_energia_fa_mensual"):
        t = tablas["validacion_energia_fa_mensual"]
        t = t[t["kwh_base_clarios"].notna() & (t["cobertura"] >= 0.95)]
        if len(t) == 0:
            inf.no_verificable("energía SCADA de F&A contra la base de Clarios", "ningún mes completo coincide con la base (solo julio de 2026, parcial)")
        else:
            r = t["kwh_scada_3_rectificadores"] / t["kwh_base_clarios"]
            fuera = (r < rmin) | (r > rmax)
            inf.prueba("fuentes", f"energía SCADA de F&A / base de Clarios dentro de [{rmin}, {rmax}]", "validacion_energia_fa_mensual", len(t),
                       [("medio", f"{int(fuera.sum())} meses fuera del rango", int(fuera.sum()))] if fuera.any() else [])
    if tiene(tablas, "gas_dia", "base_mensual_gas_rc"):
        g = tablas["gas_dia"].assign(mes=lambda d: d["fecha"].dt.to_period("M").dt.to_timestamp()).groupby("mes")["m3"].sum()
        b = tablas["base_mensual_gas_rc"].set_index("mes")["m3"].dropna()
        comun = g.index.intersection(b.index)
        if len(comun) == 0:
            inf.no_verificable("gas del SCADA contra la base de Clarios", f"no hay mes común (SCADA {g.index.min():%Y-%m} a {g.index.max():%Y-%m}; base hasta {b.index.max():%Y-%m})")
        else:
            r = g.loc[comun] / b.loc[comun]
            fuera = (r < rmin) | (r > rmax)
            inf.prueba("fuentes", f"gas SCADA / base de Clarios dentro de [{rmin}, {rmax}]", "gas_dia", len(comun),
                       [("medio", f"{int(fuera.sum())} meses fuera del rango", int(fuera.sum()))] if fuera.any() else [])

    # archivos originales
    # (se evalúa en main, porque puede omitirse con --sin-raw)


def documentacion(contrato, contrato_tablas, raiz, inf):
    v = contrato["validaciones"]
    narr = raiz / v["documentacion_contrato"]
    if narr.exists():
        texto = narr.read_text(encoding="utf-8")
        sin_tabla = [t for t in contrato_tablas if t not in texto and f"`{t}`" not in texto]
        inf.prueba("documentacion", "el contrato narrativo menciona cada tabla", "documentacion/01_contrato_datos.md", len(contrato_tablas),
                   [("medio", f"tablas sin documentar en el contrato narrativo: {sin_tabla}", len(sin_tabla))] if sin_tabla else [])
        dic = raiz / v["diccionario"]
        if dic.exists():
            from generar_diccionario import render
            al_dia = dic.read_text(encoding="utf-8") == render(contrato)
            inf.prueba("documentacion", "el diccionario de datos está al día con el contrato (cada tabla y columna)", v["diccionario"], 1,
                       [] if al_dia else [("medio", "documentacion/12_diccionario_datos.md no coincide con el contrato: ejecute `python tools/generar_diccionario.py`", 1)])
        else:
            inf.prueba("documentacion", "existe el diccionario de datos", v["diccionario"], 1, [("medio", f"no existe {dic}: ejecute `python tools/generar_diccionario.py`", 1)])
    else:
        inf.prueba("documentacion", "existe el contrato narrativo", "documentacion/01_contrato_datos.md", 1, [("alto", f"no existe {narr}", 1)])
    lim = v["limitaciones_documentadas"]
    arch = raiz / lim["archivo"]
    if arch.exists():
        texto = arch.read_text(encoding="utf-8").lower()
        faltan = [f for f in lim["frases"] if f.lower() not in texto]
        inf.prueba("documentacion", "limitaciones críticas documentadas", lim["archivo"], len(lim["frases"]),
                   [("alto", f"frases ausentes en {lim['archivo']}: {faltan}", len(faltan))] if faltan else [])
    else:
        inf.prueba("documentacion", "limitaciones críticas documentadas", lim["archivo"], 1, [("alto", f"no existe {arch}", 1)])


def config_requerida(cfg, contrato, inf):
    faltan = []
    for clave in contrato["validaciones"]["config_requerida"]:
        x = cfg
        for parte in clave.split("."):
            x = x.get(parte) if isinstance(x, dict) else None
        if x is None:
            faltan.append(clave)
    inf.prueba("configuracion", "parámetros requeridos en config/config.yaml", "config.yaml", len(contrato["validaciones"]["config_requerida"]),
               [("alto", f"faltan parámetros: {faltan}", len(faltan))] if faltan else [])
    if "turnos" in cfg:
        horas = np.zeros(24, dtype=int)
        for v in cfg["turnos"].values():
            ini, fin = int(v["inicio"][:2]), int(v["fin"][:2])
            idx = list(range(ini, fin)) if ini < fin else list(range(ini, 24)) + list(range(0, fin))
            horas[idx] += 1
        mal = int((horas != 1).sum())
        inf.prueba("configuracion", "los turnos cubren las 24 horas sin solaparse", "config.yaml", 24,
                   [("alto", f"{mal} horas del día cubiertas 0 o más de 1 vez", mal)] if mal else [])
    if "turnos" in cfg:
        largos = {t: h for t, h in horas_por_turno(cfg).items() if h != 8}
        inf.prueba("configuracion", "los turnos duran 8 horas (el contrato de datos lo supone)", "config.yaml", len(cfg["turnos"]),
                   [("alto", f"turnos que no duran 8 horas: {largos}. Cambie también el contrato (horas_validas) y las reglas de cobertura", len(largos))] if largos else [])
    minc = cfg.get("calidad", {}).get("cobertura_minima")
    inf.prueba("configuracion", "cobertura_minima entre 0 y 1", "config.yaml", 1,
               [("alto", f"cobertura_minima inválida: {minc}", 1)] if not isinstance(minc, (int, float)) or not 0 <= minc <= 1 else [])


def parametros(cat, raiz, inf):
    """Catálogo de parámetros: cada uno con descripción y justificación; todo supuesto con su advertencia; documentacion/13 al día."""
    n = len(cat)
    mal_tipo = [p["nombre"] for p in cat if p["tipo"] not in TIPOS_PARAMETRO]
    inf.prueba("parametros", f"cada parámetro tiene un tipo válido {TIPOS_PARAMETRO}", "config.yaml", n,
               [("alto", f"tipo inválido o ausente: {mal_tipo}", len(mal_tipo))] if mal_tipo else [])
    sin_adv = [p["nombre"] for p in cat if p["tipo"] == "supuesto" and not str(p["advertencia"]).strip()]
    inf.prueba("parametros", "todo supuesto declara su advertencia", "config.yaml", sum(p["tipo"] == "supuesto" for p in cat),
               [("alto", f"supuestos sin advertencia: {sin_adv}", len(sin_adv))] if sin_adv else [])
    sin_txt = [p["nombre"] for p in cat if not str(p["descripcion"]).strip() or not str(p["justificacion"]).strip()]
    inf.prueba("parametros", "todo parámetro tiene descripción y justificación", "config.yaml", n,
               [("medio", f"sin descripción o justificación: {sin_txt}", len(sin_txt))] if sin_txt else [])
    sin_unidad = [p["nombre"] for p in cat if not str(p["unidad"]).strip()]
    inf.prueba("parametros", "todo parámetro declara su unidad", "config.yaml", n,
               [("bajo", f"sin unidad: {sin_unidad}", len(sin_unidad))] if sin_unidad else [])
    doc = raiz / "documentacion" / "13_parametros.md"
    from generar_diccionario import render_parametros
    if doc.exists():
        al_dia = doc.read_text(encoding="utf-8") == render_parametros(cat)
        inf.prueba("parametros", "documentacion/13_parametros.md está al día con config.yaml", "documentacion/13_parametros.md", 1,
                   [] if al_dia else [("medio", "documentacion/13 no coincide con config.yaml: ejecute `python tools/generar_diccionario.py`", 1)])
    else:
        inf.prueba("parametros", "existe documentacion/13_parametros.md", "documentacion/13_parametros.md", 1, [("medio", "no existe: ejecute `python tools/generar_diccionario.py`", 1)])


NO_VERIFICABLES_FIJOS = [
    ("Calendario real de turnos y de paradas programadas de Clarios", "no fue suministrado: los turnos 6-14-22 son un supuesto y `operando` es inferido del consumo"),
    ("Unidad original de los contadores del SCADA (Wh)", "sin confirmación externa; evidencia indirecta, ver documentacion/04_supuestos_y_limitaciones.md"),
    ("Alcance de la base mensual de RC y de EMCALI", "no está documentado por Clarios: la razón SCADA / base no es una cobertura"),
    ("Plan de producción y presupuesto FY27", "no fue suministrado"),
]


def seguro(inf, nombre, tabla, fn, *args):
    """Ejecuta una comprobación. Si falla por un error inesperado, lo registra como incidencia crítica y sigue."""
    try:
        return fn(*args)
    except Exception as e:  # noqa: BLE001
        inf.prueba("ejecucion", f"la prueba {nombre} se pudo ejecutar", tabla, 1, [("critico", f"error inesperado: {type(e).__name__}: {e}", 1)])
        return None


def ejecutar(raiz, sin_raw=False):
    raiz = Path(raiz)
    inf = Informe()
    ruta_contrato = raiz / "config" / "contrato_datos.yaml"
    ruta_cfg = raiz / "config" / "config.yaml"
    if not ruta_contrato.exists() or not ruta_cfg.exists():
        raise SystemExit(f"Error de configuración: falta {ruta_contrato if not ruta_contrato.exists() else ruta_cfg}")
    contrato = yaml.safe_load(ruta_contrato.read_text(encoding="utf-8"))
    cfg = cargar_config(ruta_cfg)
    cat = catalogo(ruta_cfg)
    clean = raiz / "data" / "clean"
    if not clean.exists():
        clean = raiz / "datos_simulados"
    minc = cfg.get("calidad", {}).get("cobertura_minima", 0.75)

    # 1. entradas obligatorias
    if sin_raw:
        inf.no_verificable("integridad de los archivos originales (SHA-256)", "omitida con --sin-raw")
    else:
        try:
            from verificar_datos import comparar
            res = comparar(raiz / "data" / "raw")
            malos = [(a, e) for a, e in res if e != "OK"]
            inf.prueba("entradas", "archivos originales idénticos al manifiesto (SHA-256)", "data/raw", len(res),
                       [("critico", f"{len(malos)} archivos con problemas: {malos}", len(malos))] if malos else [])
        except FileNotFoundError:
            inf.prueba("entradas", "archivos originales idénticos al manifiesto (SHA-256)", "data/raw", 1, [("critico", "no existe data/raw/MANIFIESTO.csv", 1)])

    tablas = {nombre: seguro(inf, f"validación de la tabla {nombre}", nombre, validar_tabla, nombre, spec, clean, inf)
              for nombre, spec in contrato["tablas"].items()}
    declaradas = set(contrato["tablas"])
    en_disco = {p.stem for p in clean.glob("*.csv")} if clean.exists() else set()
    sin_contrato = sorted(en_disco - declaradas)
    inf.prueba("coherencia", "toda tabla de data/clean tiene contrato", "data/clean", len(en_disco),
               [("medio", f"tablas sin declarar en config/contrato_datos.yaml: {sin_contrato}", len(sin_contrato))] if sin_contrato else [])

    seguro(inf, "de consistencia entre tablas y fuentes", "-", cruzadas, tablas, cfg, contrato, inf, minc, raiz)
    seguro(inf, "de documentación", "documentacion", documentacion, contrato, contrato["tablas"], raiz, inf)
    seguro(inf, "de configuración", "config.yaml", config_requerida, cfg, contrato, inf)
    seguro(inf, "de parámetros", "config.yaml", parametros, cat, raiz, inf)
    inf.supuestos = [{"parametro": p["nombre"], "valor": p["valor"], "advertencia": p["advertencia"]} for p in cat if p["tipo"] == "supuesto"]
    for nombre, razon in NO_VERIFICABLES_FIJOS:
        inf.no_verificable(nombre, razon)
    return inf


def imprimir(inf, estricto):
    n_ok = sum(p["resultado"] == "ok" for p in inf.pruebas)
    n_falla = len(inf.pruebas) - n_ok
    print("=" * 78)
    print("VALIDACIÓN DEL CONTRATO DE DATOS")
    print("=" * 78)
    print(f"Pruebas ejecutadas: {len(inf.pruebas)} | correctas: {n_ok} | con incidencias: {n_falla} | registros evaluados (suma): {sum(p['evaluados'] for p in inf.pruebas):,}")
    conteo = {s: sum(i["severidad"] == s for i in inf.incidencias) for s in ORDEN}
    print("Incidencias: " + " | ".join(f"{NOMBRE_SEV[s]}: {conteo[s]}" for s in ORDEN))
    for s in ORDEN:
        sel = sorted([i for i in inf.incidencias if i["severidad"] == s], key=lambda i: i["id"])
        if not sel:
            continue
        print(f"\n--- {NOMBRE_SEV[s]} ({'bloqueante' if s in BLOQUEANTES else 'advertencia'}) ---")
        for i in sel:
            pct = f" ({i['pct']}%)" if i["pct"] is not None else ""
            print(f"[{i['id']}] {i['tabla']}: {i['prueba']}\n        {i['detalle']}  [n={i['n']}{pct}]")
    print("\n--- SUPUESTOS EN USO (config/config.yaml: lo que NO está confirmado por Clarios) ---")
    for s in inf.supuestos:
        print(f"* {s['parametro']}: {s['advertencia']}")
    print("\n--- NO VERIFICABLE con los datos disponibles ---")
    for nv in inf.no_verificables:
        print(f"* {nv['prueba']}: {nv['razon']}")
    bloq = inf.bloqueantes()
    adv = [i for i in inf.incidencias if i["severidad"] not in BLOQUEANTES]
    fallo = bool(bloq) or (estricto and bool(adv))
    print("\n" + "=" * 78)
    print("RESULTADO: " + ("NO APTO. Hay incidencias bloqueantes." if bloq else ("NO APTO (modo estricto): hay advertencias." if fallo else "APTO. Sin incidencias bloqueantes" + (f" ({len(adv)} advertencias)." if adv else "."))))
    print("Una prueba sin incidencias solo significa que esa regla se cumple; no certifica lo que el contrato no cubre.")
    return 1 if fallo else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Valida las tablas de data/clean contra config/contrato_datos.yaml (solo lectura).")
    ap.add_argument("--raiz", default=str(RAIZ_REPO), help="carpeta raíz del repositorio a validar (por defecto, este repositorio)")
    ap.add_argument("--sin-raw", action="store_true", help="omite la verificación SHA-256 de data/raw")
    ap.add_argument("--estricto", action="store_true", help="las advertencias también hacen fallar (código 1)")
    ap.add_argument("--json", metavar="ARCHIVO", help="guarda el informe completo en JSON")
    args = ap.parse_args(argv)
    try:
        inf = ejecutar(args.raiz, args.sin_raw)
    except SystemExit as e:
        print(e)
        return 2
    if args.json:
        Path(args.json).write_text(json.dumps({"pruebas": inf.pruebas, "incidencias": inf.incidencias, "no_verificables": inf.no_verificables, "supuestos_en_uso": inf.supuestos},
                                              ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return imprimir(inf, args.estricto)


if __name__ == "__main__":
    sys.exit(main())
