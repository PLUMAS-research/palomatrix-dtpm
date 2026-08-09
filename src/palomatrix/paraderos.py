"""Catálogo de paradas de bus y estaciones de metro y metrotren.

El DTPM publica las paradas de bus en una planilla y las estaciones solo en el
GTFS, así que el catálogo se arma juntando ambas fuentes en un GeoParquet con
geometría en EPSG:32719 (UTM 19S).

La clave para unir con las tablas de viajes es `codigo_usuario`: el código
visible en el caso de los buses, el nombre normalizado en el de las estaciones.
"""

import unicodedata
import zipfile
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import pandas as pd

from .descarga import URL_GTFS, URL_PARADEROS, descargar

CRS_UTM19S = "EPSG:32719"
CRS_WGS84 = "EPSG:4326"

COLUMNAS_SALIDA = [
    "codigo_ts",
    "codigo_usuario",
    "nombre",
    "zona_paga",
    "comuna",
    "eje",
    "desde",
    "hacia",
    "modo",
    "geometry",
]

# La planilla usa encabezados con espacios dobles y mayúsculas variables.
COLUMNAS_PLANILLA = {
    "Código paradero TS": "codigo_ts",
    "Código  paradero Usuario": "codigo_usuario",
    "Nombre Paradero": "nombre",
    "Operación con Zona Paga": "zona_paga",
    "Comuna": "comuna",
    "Eje": "eje",
    "Desde ( Cruce 1)": "desde",
    "Hacia ( Cruce 2)": "hacia",
}

# Estaciones cuyo nombre en el GTFS no coincide con el que usan las tablas de
# viajes. La clave incluye el modo porque ESTACION CENTRAL existe en ambos y
# solo la del tren se llama ALAMEDA en los viajes.
ALIAS_VIAJES = {
    ("METRO", "PUENTE CAL Y CANTO"): "CAL Y CANTO",
    ("METRO", "PARQUE O'HIGGINS"): "PARQUE OHIGGINS",
    ("METRO", "PRESIDENTE PEDRO AGUIRRE CERDA"): "PDTE PEDRO AGUIRRE CERDA",
    ("METRO", "PLAZA DE MAIPU"): "PLAZA MAIPU",
    ("METRO", "RONDIZZONI"): "RONDIZONNI",
    ("METRO", "UNION LATINOAMERICANA"): "UNION LATINO AMERICANA",
    ("METROTREN", "ESTACION CENTRAL"): "ESTACION ALAMEDA",
}

# Formas alternativas con que las entregas antiguas escriben una estación.
# Se aplican después de normalizar mayúsculas, acentos y espacios.
_EQUIVALENCIAS = {
    "PLAZA PUENTE ALTO": "PLAZA DE PUENTE ALTO",
    "PLAZA MAIPU": "PLAZA DE MAIPU",
    "CAL Y CANTO": "PUENTE CAL Y CANTO",
    "PARQUE OHIGGINS": "PARQUE O'HIGGINS",
    "PDTE PEDRO AGUIRRE CERDA": "PRESIDENTE PEDRO AGUIRRE CERDA",
    "RONDIZONNI": "RONDIZZONI",
    "UNION LATINO AMERICANA": "UNION LATINOAMERICANA",
}


def normalizar_nombre(valor) -> str | None:
    """Mayúsculas sin acentos, sin espacios repetidos."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    texto = unicodedata.normalize("NFKD", str(valor).strip())
    texto = texto.encode("ASCII", "ignore").decode("ASCII").upper()
    return " ".join(texto.split())


def normalizar_paradero(valor) -> str | None:
    """Lleva un código de paradero de los viajes a su forma canónica.

    Las entregas antiguas escriben las estaciones de varias maneras: con la
    línea al final en las combinaciones (`BAQUEDANO L1`), con capitalización de
    título en el metrotren (`Estacion Lo Espejo`) y con espacios sobrantes
    (`IRARRAZAVAL `). Los códigos de bus pasan sin cambios más allá de las
    mayúsculas.
    """
    texto = normalizar_nombre(valor)
    if texto is None:
        return None

    # Sufijo de línea en estaciones de combinación: L1, L4A, L5.
    partes = texto.rsplit(" ", 1)
    if len(partes) == 2 and len(partes[1]) >= 2 and partes[1][0] == "L":
        resto = partes[1][1:]
        if resto[:1].isdigit() and resto[1:].isalpha() or resto.isdigit():
            texto = partes[0]

    return _EQUIVALENCIAS.get(texto, texto)


def cargar_paradas_bus(ruta_planilla) -> gpd.GeoDataFrame:
    """Lee todas las hojas de la planilla de paradas y las deja como puntos."""
    print(f"Leyendo planilla de paradas: {ruta_planilla}")
    planilla = pd.ExcelFile(ruta_planilla)
    hojas = [
        pd.read_excel(ruta_planilla, sheet_name=hoja, dtype=str)
        for hoja in planilla.sheet_names
    ]
    df = pd.concat(hojas, ignore_index=True)
    print(f"  {len(df):,} filas antes de deduplicar")

    # Algunas filas traen "POR DEFINIR" en vez de coordenadas.
    df["x"] = pd.to_numeric(df["x"], errors="coerce")
    df["y"] = pd.to_numeric(df["y"], errors="coerce")
    sin_coordenadas = df[["x", "y"]].isna().any(axis=1).sum()
    if sin_coordenadas:
        print(f"  {sin_coordenadas:,} filas sin coordenadas, se descartan")
    df = df.dropna(subset=["x", "y"])

    gdf = gpd.GeoDataFrame(
        df.rename(columns=COLUMNAS_PLANILLA),
        geometry=gpd.points_from_xy(df["x"], df["y"]),
        crs=CRS_UTM19S,
    )
    gdf["modo"] = "BUS"
    gdf = gdf.drop_duplicates(subset="codigo_ts")

    for col in ("zona_paga", "comuna", "eje", "desde", "hacia"):
        if col not in gdf.columns:
            gdf[col] = None

    print(f"  {len(gdf):,} paradas de bus únicas")
    return gdf[COLUMNAS_SALIDA]


def cargar_estaciones_gtfs(ruta_gtfs) -> gpd.GeoDataFrame:
    """Extrae estaciones de metro y metrotren desde el GTFS.

    En metro se usan las estaciones padre, para no repetir un registro por
    andén. Los stops de metrotren no tienen estación padre, así que se
    deduplican por nombre después de quitar el sufijo de andén.
    """
    print(f"Leyendo GTFS: {ruta_gtfs}")
    with zipfile.ZipFile(ruta_gtfs) as zf:
        routes = pd.read_csv(zf.open("routes.txt"), dtype=str)
        trips = pd.read_csv(zf.open("trips.txt"), dtype=str)
        stop_times = pd.read_csv(zf.open("stop_times.txt"), dtype=str)
        stops = pd.read_csv(zf.open("stops.txt"), dtype=str)

    rutas_metro = set(routes.loc[routes["route_type"] == "1", "route_id"])
    rutas_metrotren = set(routes.loc[routes["route_type"] == "0", "route_id"])
    rutas = rutas_metro | rutas_metrotren

    trip_route = dict(
        zip(
            trips.loc[trips["route_id"].isin(rutas), "trip_id"],
            trips.loc[trips["route_id"].isin(rutas), "route_id"],
        )
    )

    stop_rutas = defaultdict(set)
    mask = stop_times["trip_id"].isin(trip_route)
    for sid, tid in zip(stop_times.loc[mask, "stop_id"], stop_times.loc[mask, "trip_id"]):
        stop_rutas[sid].add(trip_route[tid])

    stops_idx = stops.set_index("stop_id")
    partes = []

    padres = set()
    for sid, sus_rutas in stop_rutas.items():
        if sus_rutas & rutas_metro:
            padre = stops_idx.at[sid, "parent_station"]
            if isinstance(padre, str) and padre:
                padres.add(padre)
    metro = stops_idx.loc[stops_idx.index.isin(padres)].copy()
    metro["modo"] = "METRO"
    partes.append(metro)
    print(f"  {len(metro)} estaciones de metro")

    ids_mt = [sid for sid, r in stop_rutas.items() if r & rutas_metrotren]
    metrotren = stops_idx.loc[stops_idx.index.isin(ids_mt)].copy()
    metrotren["stop_name"] = metrotren["stop_name"].str.replace(
        r"\s*\(Anden\d+\)\s*$", "", regex=True
    )
    metrotren = metrotren.drop_duplicates(subset="stop_name")
    metrotren["modo"] = "METROTREN"
    partes.append(metrotren)
    print(f"  {len(metrotren)} estaciones de metrotren")

    estaciones = pd.concat(partes)
    estaciones["stop_lat"] = pd.to_numeric(estaciones["stop_lat"])
    estaciones["stop_lon"] = pd.to_numeric(estaciones["stop_lon"])

    gdf = gpd.GeoDataFrame(
        estaciones.reset_index(),
        geometry=gpd.points_from_xy(estaciones["stop_lon"], estaciones["stop_lat"]),
        crs=CRS_WGS84,
    ).to_crs(CRS_UTM19S)

    # codigo_usuario sale del nombre, que es lo que aparece en los viajes. No se
    # usa stop_code porque en metrotren es un código interno (PT0101) ausente de
    # las tablas de viajes.
    nombres = gdf["stop_name"].apply(normalizar_nombre)
    gdf = gdf.rename(columns={"stop_id": "codigo_ts", "stop_name": "nombre"})
    gdf["codigo_usuario"] = [
        ALIAS_VIAJES.get((modo, nombre), nombre)
        for modo, nombre in zip(gdf["modo"], nombres)
    ]
    for col in ("zona_paga", "comuna", "eje", "desde", "hacia"):
        gdf[col] = None

    return gdf[COLUMNAS_SALIDA]


def construir_catalogo(
    directorio_crudos,
    url_paraderos: str = URL_PARADEROS,
    url_gtfs: str = URL_GTFS,
) -> gpd.GeoDataFrame:
    """Descarga las fuentes si faltan y devuelve el catálogo consolidado."""
    directorio_crudos = Path(directorio_crudos)
    ruta_planilla = descargar(url_paraderos, directorio_crudos / "paraderos.xlsx")
    ruta_gtfs = descargar(url_gtfs, directorio_crudos / "gtfs.zip")
    if ruta_planilla is None or ruta_gtfs is None:
        raise RuntimeError("Faltan archivos fuente para construir el catálogo")

    catalogo = gpd.GeoDataFrame(
        pd.concat(
            [cargar_paradas_bus(ruta_planilla), cargar_estaciones_gtfs(ruta_gtfs)],
            ignore_index=True,
        ),
        geometry="geometry",
        crs=CRS_UTM19S,
    ).drop_duplicates(subset="codigo_ts")

    print(f"Total: {len(catalogo):,} registros")
    print(catalogo["modo"].value_counts().to_string())
    return catalogo


def geolocalizar(codigos, catalogo: gpd.GeoDataFrame) -> pd.DataFrame:
    """Ubica una serie de códigos de paradero contra el catálogo.

    Primero busca por `codigo_usuario` (nombres de estación y códigos visibles
    de bus) y completa con `codigo_ts` (códigos técnicos). Ambos lados pasan por
    `normalizar_paradero`, lo que resuelve las variantes de escritura de las
    entregas antiguas. Devuelve x e y en el CRS del catálogo, con nulos donde no
    hubo coincidencia.
    """
    catalogo = catalogo.copy()
    catalogo["x"] = catalogo.geometry.x
    catalogo["y"] = catalogo.geometry.y

    por_usuario = (
        catalogo.assign(clave=catalogo["codigo_usuario"].apply(normalizar_paradero))
        .dropna(subset=["clave"])
        .drop_duplicates("clave")
        .set_index("clave")[["x", "y"]]
    )
    por_ts = (
        catalogo.assign(clave=catalogo["codigo_ts"].apply(normalizar_paradero))
        .dropna(subset=["clave"])
        .drop_duplicates("clave")
        .set_index("clave")[["x", "y"]]
    )

    claves = pd.Series(codigos).apply(normalizar_paradero)
    ubicacion = por_usuario.reindex(claves.values)
    ubicacion.index = claves.index

    faltan = ubicacion["x"].isna()
    if faltan.any():
        respaldo = por_ts.reindex(claves.values[faltan.values])
        respaldo.index = ubicacion.index[faltan]
        ubicacion.loc[faltan, ["x", "y"]] = respaldo[["x", "y"]]

    return ubicacion
