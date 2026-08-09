"""Dataset consolidado por año, pensado para análisis y docencia.

Mientras `palomatrix.viajes` conserva el detalle de las cuatro etapas, aquí se
produce una tabla más angosta y ya tipada, con la fecha desagregada y banderas
de modo, que es lo que suele necesitar un análisis exploratorio.

Requiere el extra `consolidado` (dask), porque un año no cabe en memoria.

Columnas de salida
------------------
anio, fecha, dia_semana (0 es lunes), tipodia, ts_inicio, ts_fin, hora_inicio,
minuto_inicio, hora_fin, tviaje_min, dist_ruta_mts, factor, proposito,
contiene_metro, contiene_bus, paradero, paradero_destino, comuna, n_etapas.
"""

import tempfile
from pathlib import Path

import pandas as pd

from .descarga import MAPEO_DTPM, descargar, detectar_encoding, detectar_separador, extraer

TIPODIA = {"0": "LABORAL", "1": "SABADO", "2": "DOMINGO"}
PROPOSITO = {"SIN_BAJADA": "SINBAJADA", "ACTIVIDAD1MINUTO": "MENOS1MINUTO"}

# El modo aparece como texto en unos años y como código en otros, así que se
# comparan ambas formas: 1 es bus, 2 metro, 3 zona paga y 4 metrotren.
_MODOS_METRO = {"METRO", "METROTREN", "2", "4"}
_MODOS_BUS = {"BUS", "1"}

_COLUMNAS_TRANSPORTE = [
    "tipotransporte_1era",
    "tipotransporte_2da",
    "tipotransporte_3era",
    "tipotransporte_4ta",
    "tipo_transporte_1",
    "tipo_transporte_2",
    "tipo_transporte_3",
    "tipo_transporte_4",
]

# Normalización de los esquemas antiguo e intermedio al vocabulario reciente.
_NORMALIZACION = {
    "tiemposubida": "tiempo_inicio_viaje",
    "tiempobajada": "tiempo_fin_viaje",
    "factorexpansion": "factor_expansion",
    "netapa": "n_etapas",
    "paraderosubida": "paradero_inicio_viaje",
    "paraderobajada": "paradero_fin_viaje",
    "comunasubida": "comuna_inicio_viaje",
    "comunabajada": "comuna_fin_viaje",
    "dviajeenruta_mts": "distancia_ruta",
    "dviajeeuclidiana_mts": "distancia_eucl",
    "tipotransporte_1era": "tipo_transporte_1",
    "tipotransporte_2da": "tipo_transporte_2",
    "tipotransporte_3era": "tipo_transporte_3",
    "tipotransporte_4ta": "tipo_transporte_4",
    "tiempo_inicio": "tiempo_inicio_viaje",
    "tiempo_fin": "tiempo_fin_viaje",
    "paradero_inicio": "paradero_inicio_viaje",
    "paradero_fin": "paradero_fin_viaje",
    "comuna_inicio": "comuna_inicio_viaje",
    "comuna_fin": "comuna_fin_viaje",
    "tipotransporte_1": "tipo_transporte_1",
    "tipotransporte_2": "tipo_transporte_2",
    "tipotransporte_3": "tipo_transporte_3",
    "tipotransporte_4": "tipo_transporte_4",
}

ORDEN_COLUMNAS = [
    "anio",
    "fecha",
    "dia_semana",
    "tipodia",
    "ts_inicio",
    "ts_fin",
    "hora_inicio",
    "minuto_inicio",
    "hora_fin",
    "tviaje_min",
    "dist_ruta_mts",
    "factor",
    "proposito",
    "contiene_metro",
    "contiene_bus",
    "paradero",
    "paradero_destino",
    "comuna",
    "n_etapas",
]


def _dask():
    try:
        import dask.dataframe as dd
    except ImportError as e:
        raise ImportError(
            "consolidar_anio necesita dask: instala palomatrix[consolidado]"
        ) from e
    return dd


def descargar_anio(anio: str, directorio_crudos, urls=None) -> list[Path]:
    """Descarga los archivos publicados de un año. Omite los que fallen."""
    urls = urls if urls is not None else MAPEO_DTPM.get(str(anio), [])
    directorio_crudos = Path(directorio_crudos)

    rutas = []
    for indice, url in enumerate(urls):
        url = url.strip()
        extension = url.split(".")[-1].lower()
        sufijo = "" if indice == 0 else f"_{indice}"
        ruta = descargar(url, directorio_crudos / f"viajes_{anio}{sufijo}.{extension}")
        if ruta is not None:
            rutas.append(ruta)
    return rutas


def anio_a_parquet(anio: str, directorio_crudos, directorio_salida, dir_temp=None):
    """Extrae los archivos de un año y los deja como un parquet crudo.

    Idempotente: no hace nada si el parquet ya existe. Agrupa los CSV por
    encoding y separador, porque un mismo año puede mezclar ambos.
    """
    dd = _dask()
    directorio_salida = Path(directorio_salida)
    directorio_salida.mkdir(parents=True, exist_ok=True)
    ruta_parquet = directorio_salida / f"dtpm-{anio}.parquet"

    if ruta_parquet.exists():
        print(f"OMITIDO: {anio} ya procesado")
        return ruta_parquet

    rutas = descargar_anio(anio, directorio_crudos)
    if not rutas:
        print(f"Sin archivos disponibles para {anio}")
        return None

    if dir_temp is not None:
        Path(dir_temp).mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=dir_temp) as temporal:
        archivos = []
        for ruta in rutas:
            archivos.extend(extraer(ruta, Path(temporal)))

        if not archivos:
            print(f"No se hallaron datos para {anio}")
            return None

        grupos = {}
        for archivo in archivos:
            enc = detectar_encoding(archivo)
            sep = detectar_separador(archivo, encoding=enc)
            grupos.setdefault((enc, sep), []).append(archivo)

        partes = []
        for (enc, sep), rutas_grupo in grupos.items():
            print(f"LEYENDO: {len(rutas_grupo)} archivo(s) (enc={enc}, sep='{sep}')")
            parte = dd.read_csv(
                rutas_grupo, sep=sep, encoding=enc, dtype=str, on_bad_lines="skip"
            )
            limpias = {c: c.strip().strip('"') for c in parte.columns}
            parte = parte.rename(
                columns={o: _NORMALIZACION.get(v, v) for o, v in limpias.items()}
            )
            partes.append(parte)

        df = partes[0] if len(partes) == 1 else dd.concat(partes, join="outer")
        print(f"CONVIRTIENDO: {len(archivos)} archivo(s) a {ruta_parquet.name}")
        df.to_parquet(ruta_parquet, engine="pyarrow", compression="zstd")

    return ruta_parquet


def consolidar_anio(anio: str, directorio_crudo, directorio_salida):
    """Normaliza el parquet crudo de un año al esquema de análisis."""
    dd = _dask()
    ruta_entrada = Path(directorio_crudo) / f"dtpm-{anio}.parquet"
    directorio_salida = Path(directorio_salida)
    ruta_salida = directorio_salida / f"dtpm-{anio}.parquet"

    if ruta_salida.exists():
        print(f"OMITIDO: {anio} ya consolidado")
        return ruta_salida
    if not ruta_entrada.exists():
        print(f"OMITIDO: {anio} sin datos crudos")
        return None

    print(f"CONSOLIDANDO {anio}", end=" ", flush=True)
    directorio_salida.mkdir(parents=True, exist_ok=True)
    df = dd.read_parquet(ruta_entrada)

    columnas_modo = [c for c in _COLUMNAS_TRANSPORTE if c in df.columns]
    nuevo = "tiempo_inicio_viaje" in df.columns
    df = df.rename(
        columns={
            ("tiempo_inicio_viaje" if nuevo else "tiemposubida"): "tiempo",
            ("tiempo_fin_viaje" if nuevo else "tiempobajada"): "t_fin",
            ("factor_expansion" if nuevo else "factorexpansion"): "factor",
            ("paradero_inicio_viaje" if nuevo else "paraderosubida"): "paradero",
            (
                "paradero_fin_viaje" if nuevo else "paraderobajada"
            ): "paradero_destino",
            ("comuna_inicio_viaje" if nuevo else "comunasubida"): "comuna",
            ("n_etapas" if nuevo else "netapa"): "n_etapas",
            ("distancia_ruta" if nuevo else "dviajeenruta_mts"): "dist_ruta",
        }
    )

    base = [
        "tiempo",
        "t_fin",
        "tipodia",
        "factor",
        "proposito",
        "paradero",
        "paradero_destino",
        "comuna",
        "n_etapas",
        "dist_ruta",
    ]
    df = df[[c for c in base if c in df.columns] + columnas_modo]

    # Un viaje contiene metro o bus si alguna de sus etapas usa ese modo.
    if columnas_modo:
        metro = df[columnas_modo[0]].isin(_MODOS_METRO)
        bus = df[columnas_modo[0]].isin(_MODOS_BUS)
        for col in columnas_modo[1:]:
            metro = metro | df[col].isin(_MODOS_METRO)
            bus = bus | df[col].isin(_MODOS_BUS)
        df["contiene_metro"] = metro
        df["contiene_bus"] = bus
    else:
        df["contiene_metro"] = False
        df["contiene_bus"] = False
    df = df.drop(columns=columnas_modo)

    a_numero = lambda s: pd.to_numeric(s, errors="coerce")  # noqa: E731
    df["factor"] = (
        df["factor"]
        .map_partitions(a_numero, meta=("factor", "float64"))
        .fillna(0)
        .astype("float32")
    )
    df["tipodia"] = df["tipodia"].replace(TIPODIA)
    df["proposito"] = df["proposito"].replace(PROPOSITO)
    df["paradero_destino"] = df["paradero_destino"].replace({"-": None})

    for origen, destino in (("tiempo", "ts_inicio"), ("t_fin", "ts_fin")):
        df[destino] = df[origen].map_partitions(
            lambda s: pd.to_datetime(s, format="ISO8601", errors="coerce"),
            meta=(destino, "datetime64[ns]"),
        )
    df = df.drop(columns=["tiempo", "t_fin"])

    total = len(df)
    sin_hora = df["ts_inicio"].isnull().sum().compute()
    df = df[df["ts_inicio"].notnull()]
    print(f"({sin_hora:,} filas sin hora de {total:,})", end=" ", flush=True)

    df["fecha"] = df["ts_inicio"].dt.strftime("%Y-%m-%d")
    df["anio"] = df["ts_inicio"].dt.year.astype("int16")
    df["dia_semana"] = df["ts_inicio"].dt.dayofweek.astype("int8")
    df["hora_inicio"] = df["ts_inicio"].dt.hour.astype("int8")
    df["minuto_inicio"] = df["ts_inicio"].dt.minute.astype("int8")
    df["hora_fin"] = df["ts_fin"].dt.hour.astype("float32")
    df["tviaje_min"] = (
        (df["ts_fin"] - df["ts_inicio"]).dt.total_seconds() / 60
    ).astype("float32")

    if "dist_ruta" in df.columns:
        df["dist_ruta_mts"] = (
            df["dist_ruta"]
            .map_partitions(a_numero, meta=("dist_ruta_mts", "float64"))
            .astype("float32")
        )
        df = df.drop(columns=["dist_ruta"])

    if "n_etapas" in df.columns:
        df["n_etapas"] = (
            df["n_etapas"]
            .map_partitions(a_numero, meta=("n_etapas", "float64"))
            .fillna(0)
            .astype("int8")
        )

    df = df[[c for c in ORDEN_COLUMNAS if c in df.columns]]
    df.to_parquet(ruta_salida, engine="pyarrow", compression="zstd")
    print("listo")
    return ruta_salida
