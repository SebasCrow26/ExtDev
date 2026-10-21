"""Utilidades de orden para los turnos usados por las páginas del dashboard."""

from dashboard.configuracion import cargar_config


def orden_turnos_cronologico(cfg=None):
    """Devuelve el índice cronológico de cada turno según config.yaml."""
    turnos = (cfg or cargar_config())["turnos"]
    ordenados = sorted(turnos.items(), key=lambda par: par[1]["inicio"])
    return {int(numero): indice for indice, (numero, _) in enumerate(ordenados)}
