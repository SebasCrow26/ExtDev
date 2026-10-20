"""Revisa que ningún archivo del repositorio sea una copia de los datos reales de Clarios.

Compara el SHA-256 de cada archivo del repositorio con el de los archivos de una carpeta de datos reales
(por defecto ../Reto-Clarios/data/raw y ../Reto-Clarios/data/clean). Si no encuentra esa carpeta, lo dice y falla.
Uso:  python tools/verificar_sin_datos_reales.py [carpeta_con_datos_reales ...]
"""
import hashlib
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
IGNORAR = {".git", "__pycache__", "data"}
PERMITIDOS = {"mapa_procesos.csv"}  # sale de config/config.yaml, no es un dato de Clarios


def huella(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def main(argv):
    carpetas = [Path(a) for a in argv] or [RAIZ.parent / "Reto-Clarios" / "data" / "raw", RAIZ.parent / "Reto-Clarios" / "data" / "clean"]
    reales = {}
    for c in carpetas:
        if not c.exists():
            print(f"No existe {c}")
            return 2
        for p in c.rglob("*"):
            if p.is_file() and p.stat().st_size:
                reales[huella(p)] = p
    repetidos = []
    n = 0
    for p in RAIZ.rglob("*"):
        if p.is_file() and not (set(p.relative_to(RAIZ).parts) & IGNORAR):
            n += 1
            if p.stat().st_size and p.name not in PERMITIDOS and huella(p) in reales:
                repetidos.append((p.relative_to(RAIZ), reales[huella(p)]))
    print(f"Archivos del repositorio revisados: {n} | archivos reales comparados: {len(reales)}")
    for a, b in repetidos:
        print(f"COPIA DE DATOS REALES: {a}  ==  {b}")
    print("RESULTADO: " + ("HAY COPIAS, no subir." if repetidos else "limpio, ningún archivo coincide con los datos reales."))
    return 1 if repetidos else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
