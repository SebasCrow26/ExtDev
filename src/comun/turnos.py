"""Asignación de turnos según config/config.yaml."""
import pandas as pd

from src.comun.config import cargar_config


def _horas(v):
    ini, fin = int(v["inicio"][:2]), int(v["fin"][:2])
    return (fin - ini) % 24 or 24


def horas_por_turno(cfg=None):
    """Duración en horas de cada turno, según config.yaml: {1: 8, 2: 8, 3: 8}."""
    cfg = cfg or cargar_config()
    return {int(t): _horas(v) for t, v in cfg["turnos"].items()}


def turno_y_fecha(marca_tiempo):
    """Devuelve (turno, fecha_turno) para una serie de fechas-hora.

    `fecha_turno` es la fecha en que INICIA el turno: una marca a las 03:00 del día 10
    pertenece al turno 3 que empezó el día 9.
    """
    cfg = cargar_config()
    h = marca_tiempo.dt.hour
    turno = pd.Series(0, index=marca_tiempo.index)
    fecha = marca_tiempo.dt.normalize()
    for t, v in cfg["turnos"].items():
        ini, fin = int(v["inicio"][:2]), int(v["fin"][:2])
        if ini < fin:
            m = (h >= ini) & (h < fin)
        else:
            m = (h >= ini) | (h < fin)
            fecha = fecha.where(~(m & (h < fin)), fecha - pd.Timedelta(days=1))
        turno = turno.where(~m, int(t))
    return turno, fecha
