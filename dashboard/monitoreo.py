"""Motor del monitoreo en vivo (simulado).

Imita lo que pasaría en planta: cada hora llega la lectura de los contadores acumulados del SCADA (en Wh), se limpia con las mismas
reglas del proyecto (reinicios, congelamientos), se arma el consumo de cada turno, se compara con el esperado del modelo entrenado
y se evalúan el semáforo y las alertas (reglas de la guía del dashboard).

No usa Streamlit. La página está en `pagina_monitoreo.py`.
Los datos de partida son `resultados_modelo` y `dataset_modelo`: los reales si CLARIOS_DATOS_REALES apunta a su carpeta (solo en local), si no
los sintéticos de dashboard/datos_simulados. Los modelos son los de `modelos/modelos.pkl`. Los datos que "llegan" son siempre inventados.
"""
from __future__ import annotations

import sys
from pathlib import Path

import holidays
import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent          # dashboard/
RAIZ = AQUI.parent                               # raíz del repositorio (ahí está modelos/)
for ruta in (str(AQUI), str(RAIZ)):
    if ruta not in sys.path:
        sys.path.insert(0, ruta)

from configuracion import cargar_config, leer_tabla  # noqa: E402
from modelos.modelo_esperado_api import cargar_modelos, features, predecir_modelo  # noqa: E402

PROCESOS = ["triturado", "horno", "refinacion", "filtros", "ptari"]
MEDIDORES = {"triturado": {"TRITURADO": 1.0}, "horno": {"HORNO": 1.0}, "refinacion": {"REFINO_1": 0.97, "REFINO_2": 0.03},
             "filtros": {"FILTRO_1": 0.74, "FILTRO_2": 0.26}, "ptari": {"PTARI": 1.0}}
INICIO_TURNO = {1: 6, 2: 14, 3: 22}
HORAS_TURNO = 8
TIPOS_EVENTO = ("exceso", "parada", "congelamiento", "reinicio")

# Valores de la guía del dashboard (docs/17, sección 5). Son parámetros editables en la interfaz.
PARAMETROS = {"alerta_turnos": 3, "alerta_pct": 10.0, "alerta_costo_cop": 100_000.0, "semaforo_amarillo": 5.0, "semaforo_rojo": 10.0,
              "ventana_semaforo_turnos": 21, "cobertura_minima": 0.75, "min_horas_congelamiento": 3, "tarifa": 529.6}


def turno_y_fecha(ts: pd.Timestamp) -> tuple[pd.Timestamp, int]:
    """Turno al que pertenece la hora que empieza en `ts`; la fecha del turno es la de su inicio."""
    h = ts.hour
    if 6 <= h < 14:
        return ts.normalize(), 1
    if 14 <= h < 22:
        return ts.normalize(), 2
    return (ts.normalize() if h >= 22 else ts.normalize() - pd.Timedelta(days=1)), 3


def _inicio_turno(fecha: pd.Timestamp, turno: int) -> pd.Timestamp:
    return fecha + pd.Timedelta(hours=INICIO_TURNO[turno])


class MotorEnVivo:
    def __init__(self, semilla: int = 2026, inicio: pd.Timestamp | None = None, dias_contexto: int = 14, parametros: dict | None = None,
                 guion: bool = False):
        self.rng = np.random.default_rng(semilla)
        self.p = {**PARAMETROS, **(parametros or {})}
        cfg = cargar_config()
        self.p["tarifa"] = float((parametros or {}).get("tarifa", cfg["tarifas"]["tarifa_kwh_cop"]))
        self.p["cobertura_minima"] = float((parametros or {}).get("cobertura_minima", cfg["calidad"]["cobertura_minima"]))
        self.p["min_horas_congelamiento"] = int((parametros or {}).get("min_horas_congelamiento", cfg["calidad"]["min_intervalos_congelado"]))
        self.modelos = cargar_modelos()
        self.festivos = holidays.country_holidays(cfg["calendario"]["pais_festivos"], years=range(2025, 2028))

        res = leer_tabla("resultados_modelo")
        self.fuente = "datos reales de Clarios" if res.attrs.get("fuente") == "real" else "datos sintéticos"
        dm = leer_tabla("dataset_modelo")
        dm = dm[dm["proceso_modelo"].isin(PROCESOS) & (dm["calidad_ok"] == 1)]
        ultima = res["fecha_turno"].max()
        self.inicio = pd.Timestamp(inicio) if inicio is not None else ultima + pd.Timedelta(days=1)
        self.ahora = self.inicio.normalize() + pd.Timedelta(hours=6)  # la simulación arranca al comenzar el turno 1

        # historia: residuos para el z robusto, confianza por proceso y contexto reciente
        self.confianza = res.groupby("proceso_modelo")["confianza_modelo"].first().to_dict()
        r = res[res["kwh_esperado"].notna()]
        resid = (r["kwh_real"] - r["kwh_esperado"]).groupby(r["proceso_modelo"])
        self.mediana_res = resid.median().to_dict()
        self.mad_res = resid.apply(lambda s: float((s - s.median()).abs().median()) or 1.0).to_dict()
        self.p90_costo = r.groupby("proceso_modelo")["costo_exceso_cop"].quantile(0.9).to_dict()
        contexto = res[res["fecha_turno"] > ultima - pd.Timedelta(days=dias_contexto)].copy()
        contexto["calidad_ok"] = 1
        contexto["cobertura"] = 1.0
        contexto["estado"] = "historico"
        contexto["costo_exceso_cop"] = contexto["costo_exceso_cop"].astype(float)
        self.turnos = contexto.rename(columns={"proceso_modelo": "proceso"})[
            ["fecha_turno", "turno", "proceso", "kwh_real", "kwh_esperado", "exceso_kwh", "exceso_pct", "puntaje_anomalia", "es_anomalia",
             "severidad", "costo_exceso_cop", "confianza_modelo", "cobertura", "calidad_ok", "estado"]].reset_index(drop=True)

        # producción típica por día de la semana y turno (últimas 8 semanas) y últimos dos turnos reales para los rezagos
        reciente = dm[dm["fecha_turno"] > ultima - pd.Timedelta(weeks=8)]
        self.prod_tipica = reciente.groupby(["proceso_modelo", "dia_semana", "turno"])["produccion"].mean().clip(lower=0).to_dict()
        self.prod_hist = {p: list(dm[dm["proceso_modelo"] == p].sort_values(["fecha_turno", "turno"])["produccion"].clip(lower=0).tail(2))
                          for p in PROCESOS}
        while any(len(v) < 2 for v in self.prod_hist.values()):
            for v in self.prod_hist.values():
                v.insert(0, 0.0)

        # contadores: lectura que ve el SCADA y valor real del contador (difieren mientras está congelado)
        self.real_wh = {m: float(self.rng.integers(2e8, 9e8)) for p in PROCESOS for m in MEDIDORES[p]}
        self.lectura_wh = dict(self.real_wh)
        self._anterior = dict(self.lectura_wh)
        self.horas: dict[tuple[str, pd.Timestamp], tuple[float, str]] = {}   # (medidor, hora_inicio) -> (kWh, calidad)
        self.congelado_desde: pd.Timestamp | None = None
        self.hora_congelamiento: list[pd.Timestamp] = []
        self.plan: dict[tuple, dict] = {}
        self.eventos_activos: list[dict] = []
        self.programados: list[tuple[int, str, str | None, int]] = []
        self.bitacora: list[dict] = []
        self.horas_simuladas = 0
        if guion:
            self.programar_guion()
        self._planear_turno(*turno_y_fecha(self.ahora))

    # ------------------------------------------------------------------ plan del turno (producción y esperado)
    def _calendario(self, fecha: pd.Timestamp) -> dict:
        return {"dia_semana": fecha.dayofweek, "es_fin_semana": int(fecha.dayofweek >= 5), "es_festivo": int(fecha.date() in self.festivos)}

    def _planear_turno(self, fecha: pd.Timestamp, turno: int) -> None:
        cal = self._calendario(fecha)
        for p in PROCESOS:
            if (fecha, turno, p) in self.plan:
                continue
            tip = self.prod_tipica.get((p, cal["dia_semana"], turno), 0.0)
            prod = float(max(tip * self.rng.lognormal(0, 0.12), 0.0)) if tip > 0 else 0.0
            h = self.prod_hist[p]
            tab = pd.DataFrame({"proceso_modelo": p, "produccion": [h[-2], h[-1], prod], "turno": [turno] * 3,
                                "dia_semana": cal["dia_semana"], "es_fin_semana": cal["es_fin_semana"], "es_festivo": cal["es_festivo"]})
            esperado = float(np.clip(predecir_modelo(self.modelos[f"turno|{p}"]["mejor"], features(tab, "turno")), 0, None)[-1])
            sd = 1.4826 * self.mad_res.get(p, 5.0)
            base = max(esperado + self.mediana_res.get(p, 0.0) + float(self.rng.normal(0, sd)), 0.0)
            perfil = np.clip(1 + self.rng.normal(0, 0.06, HORAS_TURNO), 0.5, None)
            self.plan[(fecha, turno, p)] = {"produccion": prod, "esperado": esperado, "base": base, "perfil": perfil / perfil.sum()}
            self.prod_hist[p].append(prod)

    # ------------------------------------------------------------------ eventos
    def inyectar(self, tipo: str, proceso: str | None = None, horas: int | None = None) -> dict:
        """Eventos para la demostración: exceso sostenido, parada inesperada, congelamiento del SCADA o reinicio de un contador."""
        if tipo not in TIPOS_EVENTO:
            raise ValueError(f"tipo de evento desconocido: {tipo}")
        ev = {"tipo": tipo, "proceso": proceso, "desde": self.ahora, "hasta": self.ahora + pd.Timedelta(hours=horas or {"exceso": 24, "parada": 4, "congelamiento": 4, "reinicio": 1}[tipo])}
        if tipo == "reinicio":
            proceso = proceso or "refinacion"
            ev["proceso"] = proceso
            medidor = next(iter(MEDIDORES[proceso]))
            self.real_wh[medidor] = float(self.rng.integers(1e5, 6e5))   # el contador vuelve casi a cero
        self.eventos_activos.append(ev)
        self.bitacora.append({"hora": self.ahora, "evento": {"exceso": "Exceso de consumo sostenido", "parada": "Parada inesperada", "congelamiento": "Congelamiento del SCADA", "reinicio": "Reinicio de contador"}[tipo],
                              "detalle": f"{proceso or 'toda la planta'}" + (f", {horas or ''} h" if tipo != "reinicio" else ""), "origen": "inyectado"})
        return ev

    def programar(self, en_horas: int, tipo: str, proceso: str | None = None, horas: int | None = None) -> None:
        self.programados.append((en_horas, tipo, proceso, horas or 0))

    def programar_guion(self) -> None:
        """Guion fijo para la presentación: un congelamiento, un exceso sostenido en el horno, un reinicio y una parada."""
        self.programar(5, "congelamiento", None, 5)
        self.programar(14, "exceso", "horno", 30)
        self.programar(40, "reinicio", "refinacion", 1)
        self.programar(52, "parada", "triturado", 4)

    def _multiplicador(self, proceso: str, hora: pd.Timestamp) -> float:
        m = 1.0
        for ev in self.eventos_activos:
            if ev["proceso"] == proceso and ev["desde"] <= hora < ev["hasta"]:
                if ev["tipo"] == "exceso":
                    m *= 1.45
                elif ev["tipo"] == "parada":
                    m *= 0.03
        return m

    def _congelado(self, hora: pd.Timestamp) -> bool:
        return any(ev["tipo"] == "congelamiento" and ev["desde"] <= hora < ev["hasta"] for ev in self.eventos_activos)

    # ------------------------------------------------------------------ avance de la simulación
    def avanzar(self, horas: int = 1) -> None:
        for _ in range(int(horas)):
            self._una_hora()

    def _una_hora(self) -> None:
        for en, tipo, proceso, h in [x for x in self.programados if x[0] <= self.horas_simuladas]:
            self.programados.remove((en, tipo, proceso, h))
            self.inyectar(tipo, proceso, h or None)
        inicio_hora = self.ahora
        fecha, turno = turno_y_fecha(inicio_hora)
        self._planear_turno(fecha, turno)
        idx = int((inicio_hora - _inicio_turno(fecha, turno)) / pd.Timedelta(hours=1))
        congelado = self._congelado(inicio_hora + pd.Timedelta(hours=1))
        kwh_hora = {}
        for p in PROCESOS:
            plan = self.plan[(fecha, turno, p)]
            kwh_hora[p] = plan["base"] * plan["perfil"][idx] * self._multiplicador(p, inicio_hora)
            for m, parte in MEDIDORES[p].items():
                self.real_wh[m] += kwh_hora[p] * parte * 1000.0
                if not congelado:
                    self.lectura_wh[m] = self.real_wh[m]
        self.ahora = inicio_hora + pd.Timedelta(hours=1)
        self._limpiar(inicio_hora, congelado)
        self.horas_simuladas += 1
        # cierre de turno
        if self.ahora.hour in (6, 14, 22):
            fecha_c, turno_c = turno_y_fecha(inicio_hora)
            self._cerrar_turno(fecha_c, turno_c)
            self._planear_turno(*turno_y_fecha(self.ahora))

    def _limpiar(self, hora: pd.Timestamp, congelado: bool) -> None:
        """Convierte la lectura acumulada en kWh por hora con las reglas del proyecto: reinicio -> sin consumo, congelamiento -> se reparte."""
        dif = {m: (self.lectura_wh[m] - self._anterior[m]) for m in self.lectura_wh}
        if all(d == 0 for d in dif.values()):                      # nada se movió: SCADA congelado (los filtros nunca paran)
            if self.congelado_desde is None:
                self.congelado_desde = hora
            self.hora_congelamiento.append(hora)
            for m in dif:
                self.horas[(m, hora)] = (np.nan, "congelado")
        else:
            for m, d in dif.items():
                if d < 0:
                    self.horas[(m, hora)] = (np.nan, "reinicio")   # no se inventa lo que se perdió
                    self.bitacora.append({"hora": hora, "evento": "Reinicio de contador detectado", "detalle": f"{m}: la lectura bajó; esa hora queda sin consumo", "origen": "limpieza"})
                else:
                    self.horas[(m, hora)] = (d / 1000.0, "ok")
            if self.congelado_desde is not None:                    # reaparece la energía: se reparte pareja
                n = len(self.hora_congelamiento) + 1
                for m, d in dif.items():
                    if d > 0:
                        for h in self.hora_congelamiento + [hora]:
                            self.horas[(m, h)] = (d / 1000.0 / n, "estimado")
                largo = len(self.hora_congelamiento)
                self.bitacora.append({"hora": hora, "evento": "Congelamiento del SCADA corregido" if largo >= self.p["min_horas_congelamiento"] else "Lectura atrasada corregida",
                                      "detalle": f"{largo} h sin cambio; la energía acumulada se repartió pareja y esas horas quedan como estimadas", "origen": "limpieza"})
                afectados = {turno_y_fecha(h) for h in self.hora_congelamiento + [hora]}
                self.congelado_desde, self.hora_congelamiento = None, []
                for f, t in sorted(afectados):
                    if ((self.turnos["fecha_turno"] == f) & (self.turnos["turno"] == t)).any():
                        self._cerrar_turno(f, t)                    # recalcula el turno que quedó provisional
        self._anterior = dict(self.lectura_wh)
        if self.congelado_desde is not None and len(self.hora_congelamiento) == self.p["min_horas_congelamiento"]:
            self.bitacora.append({"hora": hora, "evento": "Congelamiento del SCADA detectado", "detalle": "todos los medidores sin cambio; el consumo se estimará cuando vuelva la señal", "origen": "limpieza"})

    # ------------------------------------------------------------------ cierre de turno
    def _kwh_proceso(self, p: str, hora: pd.Timestamp):
        vals = [self.horas.get((m, hora), (np.nan, "faltante")) for m in MEDIDORES[p]]
        if any(np.isnan(v[0]) for v in vals):
            return np.nan, vals[0][1] if all(v[1] == vals[0][1] for v in vals) else "faltante"
        return float(sum(v[0] for v in vals)), ("estimado" if any(v[1] == "estimado" for v in vals) else "ok")

    def _z_puntaje(self, p: str, residuo: float) -> float:
        z = abs((residuo - self.mediana_res.get(p, 0.0)) / (1.4826 * self.mad_res.get(p, 5.0)))
        return float(np.clip(1 - np.exp(-z / 10), 0, 1))

    def _cerrar_turno(self, fecha: pd.Timestamp, turno: int) -> None:
        ini = _inicio_turno(fecha, turno)
        nuevas = []
        for p in PROCESOS:
            plan = self.plan[(fecha, turno, p)]
            medidas = [self._kwh_proceso(p, ini + pd.Timedelta(hours=i)) for i in range(HORAS_TURNO)]
            validas = [k for k, c in medidas if not np.isnan(k)]
            cobertura = len(validas) / HORAS_TURNO
            pendiente = any(c == "congelado" for _, c in medidas)
            ok = cobertura >= self.p["cobertura_minima"] and not pendiente
            fila = {"fecha_turno": fecha, "turno": turno, "proceso": p, "kwh_esperado": plan["esperado"], "cobertura": cobertura,
                    "confianza_modelo": self.confianza.get(p, "baja"), "calidad_ok": int(ok), "estado": "final",
                    "kwh_real": np.nan, "exceso_kwh": np.nan, "exceso_pct": np.nan, "puntaje_anomalia": 0.0, "es_anomalia": 0, "severidad": "baja", "costo_exceso_cop": 0.0}
            if pendiente:
                fila["estado"] = "provisional"
            if ok:
                kwh = sum(validas) / cobertura               # igual que el proyecto: se reescala por la cobertura
                exceso = kwh - plan["esperado"]
                pct = float(np.clip(100 * exceso / plan["esperado"], -100, 200)) if plan["esperado"] > 0 else np.nan
                punt = self._z_puntaje(p, exceso)
                costo = max(exceso, 0) * self.p["tarifa"]
                es_anom = int(punt >= 0.5)
                fila.update({"kwh_real": kwh, "exceso_kwh": exceso, "exceso_pct": pct, "puntaje_anomalia": punt, "es_anomalia": es_anom, "costo_exceso_cop": costo,
                             "severidad": "alta" if es_anom else ("media" if costo >= self.p90_costo.get(p, np.inf) else "baja")})
            nuevas.append(fila)
        mascara = (self.turnos["fecha_turno"] == fecha) & (self.turnos["turno"] == turno)
        self.turnos = pd.concat([self.turnos[~mascara], pd.DataFrame(nuevas)], ignore_index=True).sort_values(["fecha_turno", "turno", "proceso"]).reset_index(drop=True)

    # ------------------------------------------------------------------ lo que ve el dashboard
    def turno_en_curso(self) -> pd.DataFrame:
        """Avance del turno actual: consumo acumulado contra el esperado prorrateado a las horas transcurridas."""
        fecha, turno = turno_y_fecha(self.ahora)
        ini = _inicio_turno(fecha, turno)
        n = int((self.ahora - ini) / pd.Timedelta(hours=1))
        filas = []
        for p in PROCESOS:
            plan = self.plan[(fecha, turno, p)]
            acum = [self._kwh_proceso(p, ini + pd.Timedelta(hours=i)) for i in range(n)]
            validas = [k for k, _ in acum if not np.isnan(k)]
            esperado_h = plan["esperado"] * n / HORAS_TURNO
            filas.append({"proceso": p, "fecha_turno": fecha, "turno": turno, "horas": n, "kwh_acumulado": float(sum(validas)),
                          "esperado_acumulado": esperado_h, "esperado_turno": plan["esperado"],
                          "horas_sin_dato": sum(np.isnan(k) for k, _ in acum),
                          "razon": float(sum(validas) / esperado_h) if esperado_h > 5 and validas else np.nan})
        return pd.DataFrame(filas)

    def serie_horaria(self, horas: int = 48) -> pd.DataFrame:
        """kWh por hora y proceso de las últimas `horas`, con el esperado horario y la calidad."""
        filas = []
        for k in range(1, horas + 1):
            h = self.ahora - pd.Timedelta(hours=k)
            if self.horas_simuladas - k < 0:
                break
            fecha, turno = turno_y_fecha(h)
            idx = int((h - _inicio_turno(fecha, turno)) / pd.Timedelta(hours=1))
            for p in PROCESOS:
                kwh, cal = self._kwh_proceso(p, h)
                plan = self.plan.get((fecha, turno, p))
                filas.append({"hora": h, "proceso": p, "kwh": kwh, "calidad": cal,
                              "esperado": plan["esperado"] * plan["perfil"][idx] if plan else np.nan})
        out = pd.DataFrame(filas, columns=["hora", "proceso", "kwh", "calidad", "esperado"])
        return out.sort_values(["proceso", "hora"]).reset_index(drop=True)

    def semaforo(self) -> pd.DataFrame:
        """Semáforo por proceso sobre las sumas de los últimos turnos (docs/17, sección 4)."""
        filas = []
        for p in PROCESOS:
            d = self.turnos[self.turnos["proceso"] == p].tail(self.p["ventana_semaforo_turnos"])
            validos = d[d["calidad_ok"] == 1]
            esperado = validos["kwh_esperado"].sum()
            pct = 100 * (validos["kwh_real"].sum() - esperado) / esperado if esperado > 0 else np.nan
            if len(d) == 0 or d["calidad_ok"].mean() < self.p["cobertura_minima"]:
                color = "gris"
            elif (validos["severidad"] == "alta").any() or pct > self.p["semaforo_rojo"]:
                color = "rojo"
            elif pct > self.p["semaforo_amarillo"]:
                color = "amarillo"
            else:
                color = "verde"
            filas.append({"proceso": p, "color": color, "exceso_pct": pct, "exceso_kwh": validos["kwh_real"].sum() - esperado,
                          "costo_cop": max(validos["kwh_real"].sum() - esperado, 0) * self.p["tarifa"],
                          "turnos_validos": float(d["calidad_ok"].mean()) if len(d) else np.nan,
                          "indicativo": self.confianza.get(p, "baja") == "baja", "confianza_modelo": self.confianza.get(p, "baja")})
        return pd.DataFrame(filas)

    def alertas(self) -> pd.DataFrame:
        """Alertas con las reglas de docs/17 (sección 5), sobre lo que va cerrado. Las de confianza `baja` salen como indicativas."""
        filas = []
        t = self.turnos
        for p in PROCESOS:
            d = t[t["proceso"] == p].sort_values(["fecha_turno", "turno"]).reset_index(drop=True)
            conf = self.confianza.get(p, "baja")
            ind = conf == "baja"
            # 1. exceso sostenido: rachas de turnos válidos con exceso > pct % del esperado
            sobre = (d["calidad_ok"] == 1) & (d["kwh_esperado"] > 0) & (d["exceso_kwh"] > self.p["alerta_pct"] / 100 * d["kwh_esperado"])
            i = 0
            while i < len(d):
                if sobre[i]:
                    j = i
                    while j + 1 < len(d) and sobre[j + 1]:
                        j += 1
                    racha = d.iloc[i:j + 1]
                    costo = racha["costo_exceso_cop"].sum()
                    if len(racha) >= self.p["alerta_turnos"] and costo >= self.p["alerta_costo_cop"]:
                        filas.append({"tipo": "Exceso sostenido", "fecha_turno": racha["fecha_turno"].iloc[-1], "turno": int(racha["turno"].iloc[-1]), "proceso": p,
                                      "detalle": f"{len(racha)} turnos seguidos por encima del esperado", "exceso_kwh": racha["exceso_kwh"].sum(), "costo_cop": costo,
                                      "severidad": "alta" if not ind else "baja", "confianza_modelo": conf, "indicativa": ind,
                                      "nueva": racha["estado"].iloc[-1] != "historico"})
                    i = j + 1
                else:
                    i += 1
            # 2. anomalía puntual
            for r in d[(d["es_anomalia"] == 1) & (d["calidad_ok"] == 1)].itertuples():
                filas.append({"tipo": "Anomalía puntual", "fecha_turno": r.fecha_turno, "turno": int(r.turno), "proceso": p, "detalle": f"{r.kwh_real:,.0f} kWh contra {r.kwh_esperado:,.0f} esperados",
                              "exceso_kwh": r.exceso_kwh, "costo_cop": r.costo_exceso_cop, "severidad": r.severidad, "confianza_modelo": conf, "indicativa": ind, "nueva": r.estado != "historico"})
            # 3b. parada inesperada: casi cero donde lo esperado es alto
            para = d[(d["calidad_ok"] == 1) & (d["kwh_esperado"] > 100) & (d["kwh_real"] < 0.15 * d["kwh_esperado"])]
            for r in para.itertuples():
                filas.append({"tipo": "Parada inesperada", "fecha_turno": r.fecha_turno, "turno": int(r.turno), "proceso": p, "detalle": f"{r.kwh_real:,.0f} kWh donde se esperaban {r.kwh_esperado:,.0f}",
                              "exceso_kwh": r.exceso_kwh, "costo_cop": 0.0, "severidad": "media", "confianza_modelo": conf, "indicativa": ind, "nueva": r.estado != "historico"})
            # 4. dato incompleto
            for r in d[d["calidad_ok"] == 0].itertuples():
                filas.append({"tipo": "Dato incompleto", "fecha_turno": r.fecha_turno, "turno": int(r.turno), "proceso": p,
                              "detalle": ("congelamiento del SCADA en curso" if r.estado == "provisional" else f"cobertura {r.cobertura:.0%}"), "exceso_kwh": np.nan, "costo_cop": 0.0,
                              "severidad": "aviso", "confianza_modelo": conf, "indicativa": False, "nueva": True})
        out = pd.DataFrame(filas, columns=["tipo", "fecha_turno", "turno", "proceso", "detalle", "exceso_kwh", "costo_cop", "severidad", "confianza_modelo", "indicativa", "nueva"])
        return out.sort_values(["costo_cop", "fecha_turno"], ascending=[False, False]).reset_index(drop=True)

    def bitacora_df(self) -> pd.DataFrame:
        return pd.DataFrame(self.bitacora, columns=["hora", "evento", "detalle", "origen"]).iloc[::-1].reset_index(drop=True)
