"""Descarga y extracción de los archivos publicados por el DTPM.

El DTPM publica los datos de viajes en formatos que cambian con los años: `.rar`
para los períodos antiguos, `.zip` para los recientes, a veces con archivos
anidados dentro. Los CSV varían en separador y en codificación. Este módulo
resuelve esas diferencias para que el resto del paquete reciba archivos planos.

Requisitos de sistema: `unrar` para los `.rar`, `7z` o `unzip` para los `.zip`.
"""

import csv
import subprocess
import urllib.request
from pathlib import Path

# Año a lista de URLs publicadas. Varios años reparten los datos en más de un
# archivo, por tipo de día o por semana. Verificado en agosto de 2026: todas
# responden salvo la de noviembre de 2021, que devuelve 404.
MAPEO_DTPM = {
    "2014": ["https://www.dtpm.cl/descargas/tablas/viajes201405_transparencia.rar"],
    "2015": ["https://www.dtpm.cl/descargas/tablas/viajes201504_transparencia.rar"],
    "2016": ["https://www.dtpm.cl/descargas/tablas/viajes201605_transparencia.rar"],
    "2017": [
        "https://www.dtpm.cl/descargas/tablas/viajes201704_laboral_transparencia.rar"
    ],
    "2018": [
        "https://www.dtpm.cl/descargas/tablas/viajes201804_laboral_transparencia.rar",
        "https://www.dtpm.cl/descargas/tablas/viajes_octubre_18.zip",
    ],
    "2019": [
        "https://www.dtpm.cl/descargas/tablas/tabla-viajes.rar",
        "https://www.dtpm.cl/descargas/tablas/viajes_19.zip",
    ],
    "2020": [
        # Semana del 9 al 12 de marzo (lunes a jueves) más el domingo 8. El
        # viernes no está en el dataset de origen.
        "https://www.dtpm.cl/descargas/modelos_y_matrices/viajes202003_laboral_transparencia.zip",
        "https://www.dtpm.cl/descargas/modelos_y_matrices/viajes202003_sab_dom_transparencia.zip",
        "https://www.dtpm.cl/descargas/modelos_y_matrices/nov21/viajes202011_transparencia_9al15.zip",
    ],
    "2021": [
        "https://www.dtpm.cl/descargas/modelos_y_matrices/viajes202104_transparencia.zip",
    ],
    "2022": [
        "https://www.dtpm.cl/descargas/modelos_y_matrices/viajes202204_abril_4al10_transparencia-.zip",
        "https://www.dtpm.cl/descargas/modelos_y_matrices/viajes082022_8al14_transparencia.zip",
    ],
    "2023": [
        "https://www.dtpm.cl/descargas/modelos_y_matrices/viajes_042023_17al23_transparencia.zip",
        "https://www.dtpm.cl/descargas/modelos_y_matrices/viajes_082023_7al13-.zip",
        "https://www.dtpm.cl/descargas/modelos_y_matrices/viajes_112023_6al12.zip",
    ],
    "2024": [
        "https://www.dtpm.cl/descargas/modelos_y_matrices/viajes202404_transparencia_15al21.zip",
        "https://www.dtpm.cl/descargas/modelos_y_matrices/Tabla-de-Viajes-Nov-24.zip",
    ],
    "2025": [
        "https://www.dtpm.cl/descargas/modelos_y_matrices/Tabla-de-viajes-011025.zip",
        "https://www.dtpm.cl/descargas/modelos_y_matrices/Tablas_viajes_NOV_2025.zip",
    ],
    "2026": [
        "https://www.dtpm.cl/descargas/modelos_y_matrices/Etapas-2026-04.zip",
    ],
}

# Catálogo de paradas y GTFS vigentes. Cambian cuando el DTPM publica una
# versión nueva, así que las funciones que los usan aceptan otra URL.
URL_PARADEROS = "https://www.dtpm.cl/descargas/pops26/2026-03-21_consolidado_Registro-Paradas_anual.xlsx"
URL_GTFS = "https://www.dtpm.cl/descargas/gtfs/GTFS_20260321_v3.zip"

# Los archivos de transparencia (2014 a 2018) no traen identificador de tarjeta:
# su esquema describe viajes anónimos, sin clave que los enlace a una persona.
# Sirven para matrices de origen-destino agregadas, no para análisis por
# individuo ni para unir con otras fuentes por tarjeta.
SIN_IDENTIFICADOR = frozenset({"2014", "2015", "2016", "2017", "2018"})


def descargar(url: str, destino: Path, minimo_bytes: int = 1024) -> Path | None:
    """Descarga una URL si el destino no existe. Devuelve la ruta o None.

    Un archivo previo menor que `minimo_bytes` se considera una descarga
    interrumpida y se reemplaza.
    """
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)

    if destino.exists() and destino.stat().st_size < minimo_bytes:
        print(f"  INCOMPLETO: {destino.name}, se descarga de nuevo")
        destino.unlink()

    if destino.exists():
        print(f"  LOCAL: {destino.name} ({destino.stat().st_size / 1e6:.1f} MB)")
        return destino

    print(f"  DESCARGANDO: {url}")
    try:
        urllib.request.urlretrieve(url, destino)
    except Exception as e:
        print(f"  ERROR ({url}): {e}")
        if destino.exists():
            destino.unlink()
        return None

    print(f"  LISTO: {destino.name} ({destino.stat().st_size / 1e6:.1f} MB)")
    return destino


def extraer(archivo: Path, destino: Path, recursivo: bool = True) -> list[Path]:
    """Extrae un `.rar` o `.zip` y devuelve los archivos de datos resultantes.

    Con `recursivo`, también extrae los comprimidos anidados: varios años del
    DTPM entregan un `.rar` que contiene `.zip` por semana, que a su vez
    contienen los CSV.
    """
    archivo, destino = Path(archivo), Path(destino)
    destino.mkdir(parents=True, exist_ok=True)

    if archivo.suffix.lower() == ".rar":
        cmd = ["unrar", "x", "-y", str(archivo), f"{destino}/"]
    else:
        cmd = ["7z", "x", str(archivo), f"-o{destino}", "-y"]

    resultado = subprocess.run(cmd, capture_output=True, text=True)
    if resultado.returncode != 0 and not list(destino.rglob("*")):
        raise RuntimeError(f"No se pudo extraer {archivo.name}: {resultado.stderr}")

    if recursivo:
        for anidado in list(destino.rglob("*.zip")) + list(destino.rglob("*.rar")):
            print(f"  ANIDADO: {anidado.name}")
            extraer(anidado, anidado.parent, recursivo=False)
            anidado.unlink()
        for gz in list(destino.rglob("*.gz")):
            subprocess.run(["gunzip", "-f", str(gz)], capture_output=True)

    return sorted(
        p for p in destino.rglob("*") if p.suffix.lower() in {".csv", ".txt"}
    )


def detectar_encoding(ruta: Path) -> str:
    """Devuelve el encoding del archivo según tenga o no BOM UTF-8."""
    with open(ruta, "rb") as f:
        return "utf-8-sig" if f.read(3) == b"\xef\xbb\xbf" else "latin-1"


def detectar_separador(ruta: Path, encoding: str | None = None) -> str:
    """Detecta el delimitador leyendo las primeras líneas del archivo."""
    encoding = encoding or detectar_encoding(ruta)
    with open(ruta, "r", encoding=encoding) as f:
        muestra = f.readline() + f.readline()

    try:
        return csv.Sniffer().sniff(muestra, delimiters=",;|\t").delimiter
    except csv.Error:
        for sep in ("|", ";", ",", "\t"):
            if sep in muestra:
                return sep
        return ","
