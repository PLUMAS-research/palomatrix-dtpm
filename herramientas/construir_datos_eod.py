"""Genera los archivos de la EOD 2012 que `palomatrix.eod` trae empaquetados.

Produce tres cosas a partir de la entrega original de la encuesta:

1. `codigos.parquet`, con las 61 tablas de parámetros normalizadas a una sola
   tabla larga. Vienen con separadores y codificaciones mezcladas, encabezados
   inconsistentes y columnas de relleno.
2. `zonificacion.parquet`, el shapefile de las 866 zonas convertido a
   geoparquet.
3. Una copia en parquet de cada tabla de datos (viajes, personas, hogares,
   etapas y vehículos), tal como las arma `palomatrix.eod.lectura`, sin
   decodificar ni filtrar.

Uso:
    uv run python herramientas/construir_datos_eod.py [ruta_eod]

Sin argumento descarga la entrega a un directorio temporal.
"""

# %%
import sys
import tarfile
import tempfile
import urllib.request
from io import StringIO
from pathlib import Path

import geopandas as gpd
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "src" / "palomatrix" / "eod" / "datos"

# Entrega de la encuesta con los microdatos, la zonificación y las tablas de
# parámetros. Solo se usa aquí: el paquete no descarga nada.
URL_EOD = "https://dcc.uchile.cl/~egraells/gds-data/eod2012.tgz"

# Nivel de compresión alto, porque estos archivos se escriben una vez y se
# distribuyen dentro del paquete.
COMPRESION = {"compression": "zstd", "compression_level": 19}

# Nombres que algunas tablas usan para una columna de relleno al final.
RELLENO = {"campo1", "campo2"}

# Archivos que no son tablas de código: copias de trabajo del organismo y una
# lista de combinaciones de modos que no sigue el formato id-valor.
IGNORAR = {"Relacion.csvtest", "Modo - copia.csv", "MediosUsados.csv"}


def leer_texto(ruta: Path) -> str:
    """Devuelve el contenido del archivo probando utf-8 y luego iso-8859-1."""
    datos = ruta.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "iso-8859-1"):
        try:
            return datos.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"No se pudo decodificar {ruta.name}")


def normalizar_nombre_tabla(ruta: Path) -> str:
    """`Donde Estudia.csv` pasa a `DondeEstudia`."""
    return ruta.stem.replace(" ", "")


def leer_tabla_codigos(ruta: Path) -> pd.DataFrame | None:
    """Lee un CSV de códigos y lo deja como (id, valor), o None si no aplica."""
    texto = leer_texto(ruta)
    encabezado = texto.splitlines()[0]
    sep = ";" if encabezado.count(";") >= encabezado.count(",") else ","

    df = pd.read_csv(StringIO(texto), sep=sep, dtype=str).rename(columns=str.strip)

    # Algunas tablas traen una columna de relleno al final, y otras guardan el
    # valor bajo ese mismo nombre. Se descarta solo cuando sobra.
    utiles = [c for c in df.columns if c.strip().lower() not in RELLENO]
    if len(utiles) < 2:
        utiles = list(df.columns)

    if len(utiles) < 2:
        print(f"  OMITIDO: {ruta.name} tiene {len(utiles)} columna(s)")
        return None

    df = df.loc[:, utiles[:2]]
    df.columns = ["id", "valor"]
    df = df.dropna(subset=["id"])
    df["id"] = df["id"].str.strip()
    df["valor"] = df["valor"].str.strip()

    # Los ids numéricos se guardan sin decimales para que `decodificar` pueda
    # comparar contra columnas que pandas lee como float.
    numericos = pd.to_numeric(df["id"], errors="coerce")
    df["id"] = df["id"].mask(
        numericos.notna(), numericos.astype("Float64").astype("Int64").astype(str)
    )

    return df.drop_duplicates(subset="id")


def construir_codigos(directorio: Path) -> pd.DataFrame:
    """Une las tablas de parámetros en una tabla larga (tabla, id, valor)."""
    origen = directorio / "Tablas_parametros"
    print(f"CÓDIGOS: leyendo {origen}")

    partes = []
    for ruta in sorted(origen.iterdir()):
        if ruta.name in IGNORAR or not ruta.is_file():
            continue
        tabla = leer_tabla_codigos(ruta)
        if tabla is None:
            continue
        tabla.insert(0, "tabla", normalizar_nombre_tabla(ruta))
        partes.append(tabla)

    codigos = pd.concat(partes, ignore_index=True)
    print(f"  {codigos['tabla'].nunique()} tablas, {len(codigos)} códigos")
    return codigos


def construir_zonificacion(directorio: Path) -> gpd.GeoDataFrame:
    """Convierte el shapefile de las 866 zonas EOD a geoparquet."""
    origen = directorio / "Zonificacion_EOD2012"
    print(f"ZONAS: leyendo {origen}")

    zonas = gpd.read_file(origen)
    zonas = zonas.rename(
        columns={
            "Zona": "zona",
            "Comuna": "comuna",
            "Com": "codigo_comuna",
            "AREA": "area",
        }
    )
    zonas["zona"] = zonas["zona"].astype("Int64")
    zonas["codigo_comuna"] = zonas["codigo_comuna"].astype("Int64")
    zonas = zonas[["zona", "comuna", "codigo_comuna", "area", "geometry"]]

    print(f"  {len(zonas)} zonas, CRS {zonas.crs}")
    return zonas.sort_values("zona").reset_index(drop=True)


def construir_tablas(directorio: Path) -> None:
    """Copia a parquet cada tabla de datos, sin decodificar ni filtrar."""
    sys.path.insert(0, str(RAIZ / "src"))
    from palomatrix.eod.lectura import CRUDOS

    print(f"TABLAS: leyendo {directorio}")
    for nombre, leer in CRUDOS.items():
        df = leer(directorio)
        df.to_parquet(DESTINO / f"{nombre}.parquet", index=False, **COMPRESION)
        print(f"  {nombre}: {df.shape[0]} filas, {df.shape[1]} columnas")


def descargar_entrega() -> Path:
    """Baja y extrae la entrega de la encuesta en un directorio temporal."""
    temporal = Path(tempfile.mkdtemp(prefix="palomatrix-eod-"))
    comprimido = temporal / "eod2012.tgz"

    print(f"DESCARGANDO: {URL_EOD}")
    urllib.request.urlretrieve(URL_EOD, comprimido)
    with tarfile.open(comprimido) as tar:
        tar.extractall(temporal, filter="data")

    return temporal / "eod2012" / "EOD_STGO"


# %%
def main(ruta: str | None = None) -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    directorio = Path(ruta) if ruta else descargar_entrega()

    codigos = construir_codigos(directorio)
    codigos.to_parquet(DESTINO / "codigos.parquet", index=False, **COMPRESION)

    zonas = construir_zonificacion(directorio)
    zonas.to_parquet(DESTINO / "zonificacion.parquet", index=False, **COMPRESION)

    construir_tablas(directorio)

    total = 0
    for archivo in sorted(DESTINO.glob("*.parquet")):
        kb = archivo.stat().st_size / 1024
        total += kb
        print(f"ESCRITO: {archivo.name} ({kb:.0f} KB)")
    print(f"TOTAL: {total / 1024:.1f} MB")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
