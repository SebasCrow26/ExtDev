"""Genera documentacion/12_diccionario_datos.md (desde config/contrato_datos.yaml) y documentacion/13_parametros.md (desde config/config.yaml).

Los archivos de configuración son la única fuente: los documentos no se editan a mano. El validador comprueba que estén al día.

Uso (desde la raíz del repositorio):  python tools/generar_diccionario.py
"""
import json
import sys
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1]
CONTRATO = RAIZ / "config" / "contrato_datos.yaml"
SALIDA = RAIZ / "documentacion" / "12_diccionario_datos.md"
SALIDA_PARAMETROS = RAIZ / "documentacion" / "13_parametros.md"
TIPOS_PARAMETRO = {"dato_clarios": "dato de Clarios", "supuesto": "SUPUESTO", "metodologico": "metodológico", "tecnico": "técnico"}

NIVELES = {"depurado": "datos depurados (derivados de una fuente original sin cambiar su significado)",
           "agregado": "datos agregados (suma por turno u otro nivel)", "derivado": "tabla analítica derivada",
           "referencia_clarios": "cifras de referencia suministradas por Clarios (no recalculadas)",
           "auditoria": "tabla de auditoría de calidad", "exploratorio": "resultado exploratorio, no oficial"}


def rango(e):
    partes = []
    if "min" in e or "max" in e:
        partes.append(f"[{e.get('min', '-inf')}, {e.get('max', '+inf')}]")
    if "plausible_min" in e or "plausible_max" in e:
        partes.append(f"plausible [{e.get('plausible_min', '-inf')}, {e.get('plausible_max', '+inf')}]")
    return " ".join(partes) or ""


def render(contrato):
    L = ["# Diccionario de datos", "",
         "**Generado automáticamente desde `config/contrato_datos.yaml` con `python tools/generar_diccionario.py`. No se edita a mano.**",
         "El contrato narrativo y las reglas de uso están en `documentacion/01_contrato_datos.md`; las cifras y su estado de validación, en `documentacion/11_cifras_verificadas.md`.", "",
         f"**Zona horaria:** {contrato['zona_horaria']}", "",
         "Tipos: `str` texto, `int` entero, `float` decimal, `bin` 0 o 1, `fecha` AAAA-MM-DD, `fechahora` AAAA-MM-DD HH:MM:SS, `mes` AAAA-MM, `bool` True o False.",
         "Rango entre corchetes = límite duro (un valor fuera es un error); \"plausible\" = advertencia.", ""]
    for nombre, t in contrato["tablas"].items():
        L += [f"## `{nombre}`", "", t["descripcion"], "",
              "| propiedad | valor |", "|---|---|",
              f"| clase de dato | {t['nivel']}: {NIVELES.get(t['nivel'], '')} |",
              f"| fuente | {t.get('fuente', '')} |", f"| script | `{t.get('script', '')}` |",
              f"| granularidad | {t.get('granularidad', 'sin granularidad temporal fija')} |",
              f"| clave | {', '.join(f'`{c}`' for c in t.get('clave', [])) or 'sin clave definida'} |",
              f"| consumidores | {', '.join(t.get('consumidores', []))} |"]
        if "continuidad" in t:
            c = t["continuidad"]
            L.append(f"| continuidad | sin huecos en `{c['columna']}` (paso: {c['paso']}" + (f", por {', '.join(c['agrupar_por'])}" if c.get("agrupar_por") else "") + ") |")
        if "nulo_condicionado" in t:
            n = t["nulo_condicionado"]
            L.append(f"| nulos condicionados | `{n['columna']}` es nulo solo si `{n['si']}` está en {n['valores_nulos']} |")
        L += ["", "| columna | tipo | unidad | nulos | rango | valores permitidos | descripción |", "|---|---|---|---|---|---|---|"]
        for c, e in t["columnas"].items():
            L.append(f"| `{c}` | {e['tipo']} | {e.get('unidad', '')} | {'sí' if e.get('nulo') else 'no'} | {rango(e)} | "
                     f"{', '.join(str(p) for p in e.get('permitidos', []))} | {e.get('descripcion', '')} |")
        L.append("")
    return "\n".join(L) + "\n"


def _valor(v):
    texto = json.dumps(v, ensure_ascii=False)
    return "ver `config/config.yaml`" if len(texto) > 160 else f"`{texto}`"


def _celda(t):
    return str(t).replace("|", "/").replace("\n", " ")


def render_parametros(catalogo):
    """Tabla legible de los parámetros de config/config.yaml, agrupados por sección."""
    L = ["# Parámetros del proyecto", "",
         "**Generado automáticamente desde `config/config.yaml` con `python tools/generar_diccionario.py`. No se edita a mano: se cambia el valor en `config/config.yaml`.**", "",
         "Tipos de parámetro: **dato de Clarios** (viene de Clarios), **SUPUESTO** (decisión sin confirmación de Clarios; trae una advertencia de lo que no se puede concluir), "
         "**metodológico** (decisión técnica de análisis) y **técnico** (ruta o formato).", "",
         "Los **supuestos** son lo primero que hay que revisar si Clarios aporta información nueva:", ""]
    for p in catalogo:
        if p["tipo"] == "supuesto":
            L.append(f"- `{p['nombre']}`: {p['advertencia']}")
    secciones = {}
    for p in catalogo:
        secciones.setdefault(p["nombre"].split(".")[0], []).append(p)
    for sec, ps in secciones.items():
        L += ["", f"## {sec}", "", "| parámetro | valor | unidad | tipo | descripción | justificación | advertencia |", "|---|---|---|---|---|---|---|"]
        for p in ps:
            L.append(f"| `{p['nombre']}` | {_valor(p['valor'])} | {_celda(p['unidad'])} | {TIPOS_PARAMETRO.get(p['tipo'], p['tipo'])} | "
                     f"{_celda(p['descripcion'])} | {_celda(p['justificacion'])} | {_celda(p['advertencia'])} |")
    return "\n".join(L) + "\n"


def main():
    sys.path.insert(0, str(RAIZ))
    from src.comun.config import catalogo
    contrato = yaml.safe_load(CONTRATO.read_text(encoding="utf-8"))
    SALIDA.write_text(render(contrato), encoding="utf-8", newline="\n")
    print(f"escrito {SALIDA.relative_to(RAIZ)} ({len(contrato['tablas'])} tablas)")
    cat = catalogo()
    SALIDA_PARAMETROS.write_text(render_parametros(cat), encoding="utf-8", newline="\n")
    print(f"escrito {SALIDA_PARAMETROS.relative_to(RAIZ)} ({len(cat)} parámetros)")


if __name__ == "__main__":
    sys.exit(main())
