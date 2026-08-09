"""Lectura y normalización de las tablas de viajes del DTPM.

Un viaje encadena hasta cuatro etapas. El DTPM ha publicado ese mismo contenido
bajo tres esquemas distintos a lo largo de los años, y este módulo los lleva a
uno solo, con las etapas en columnas numeradas de 1 a 4.

Esquemas de origen
------------------
1. ADATRAP antiguo: `correlativo_viajes`, nombres con guion bajo
   (`parada_subida_1era`).
2. Intermedio: nombres compuestos sin guion bajo (`paraderosubida_1era`),
   prefijo `zona777`, identificador en `id`. No trae zona de inicio ni de fin.
3. APTTO y QR: `id_tarjeta`, nombres ya numerados.

Los archivos de transparencia previos a 2019 siguen el esquema 2 pero no traen
identificador de tarjeta, así que `id_tarjeta` queda nulo.
"""

import gc
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

# El motor pyarrow lee estos CSV unas cuatro veces más rápido que el motor C de
# pandas y respeta el encoding declarado.
MOTOR_CSV = "pyarrow"

# zstd comprime unas tres veces más rápido que brotli con un tamaño similar.
COMPRESION = "zstd"

COLUMNAS_SALIDA = [
    "year",
    "month",
    "day",
    "comuna_fin_viaje",
    "comuna_inicio_viaje",
    "contrato",
    "distancia_eucl",
    "distancia_ruta",
    "factor_expansion",
    "id_tarjeta",
    "n_etapas",
    "paradero_bajada_1",
    "paradero_bajada_2",
    "paradero_bajada_3",
    "paradero_bajada_4",
    "paradero_fin_viaje",
    "paradero_inicio_viaje",
    "paradero_subida_1",
    "paradero_subida_2",
    "paradero_subida_3",
    "paradero_subida_4",
    "proposito",
    "srv_1",
    "srv_2",
    "srv_3",
    "srv_4",
    "tiempo_bajada_1",
    "tiempo_bajada_2",
    "tiempo_bajada_3",
    "tiempo_bajada_4",
    "tiempo_fin_viaje",
    "tiempo_inicio_viaje",
    "tiempo_subida_1",
    "tiempo_subida_2",
    "tiempo_subida_3",
    "tiempo_subida_4",
    "zona_bajada_1",
    "zona_bajada_2",
    "zona_bajada_3",
    "zona_bajada_4",
    "zona_fin_viaje",
    "zona_inicio_viaje",
    "zona_subida_1",
    "zona_subida_2",
    "zona_subida_3",
    "zona_subida_4",
    "tipo_transporte_1",
    "tipo_transporte_2",
    "tipo_transporte_3",
    "tipo_transporte_4",
]

_RENOMBRE_ADATRAP = {
    "cantidad_etapas": "n_etapas",
    "comuna_bajada": "comuna_fin_viaje",
    "comuna_subida": "comuna_inicio_viaje",
    "dist_viaje_en_ruta_mts": "distancia_ruta",
    "dist_viaje_euclidiana_mts": "distancia_eucl",
    "parada_bajada": "paradero_fin_viaje",
    "parada_bajada_1era": "paradero_bajada_1",
    "parada_bajada_2da": "paradero_bajada_2",
    "parada_bajada_3era": "paradero_bajada_3",
    "parada_bajada_4ta": "paradero_bajada_4",
    "parada_subida": "paradero_inicio_viaje",
    "parada_subida_1era": "paradero_subida_1",
    "parada_subida_2da": "paradero_subida_2",
    "parada_subida_3era": "paradero_subida_3",
    "parada_subida_4ta": "paradero_subida_4",
    "serv_1era_etapa": "srv_1",
    "serv_2da_etapa": "srv_2",
    "serv_3era_etapa": "srv_3",
    "serv_4ta_etapa": "srv_4",
    "tiempo_bajada": "tiempo_fin_viaje",
    "tiempo_bajada_1era": "tiempo_bajada_1",
    "tiempo_bajada_2da": "tiempo_bajada_2",
    "tiempo_bajada_3era": "tiempo_bajada_3",
    "tiempo_bajada_4ta": "tiempo_bajada_4",
    "tiempo_subida": "tiempo_inicio_viaje",
    "tiempo_subida_1era": "tiempo_subida_1",
    "tiempo_subida_2da": "tiempo_subida_2",
    "tiempo_subida_3era": "tiempo_subida_3",
    "tiempo_subida_4ta": "tiempo_subida_4",
    "tipo_transporte_1era": "tipo_transporte_1",
    "tipo_transporte_2da": "tipo_transporte_2",
    "tipo_transporte_3era": "tipo_transporte_3",
    "tipo_transporte_4ta": "tipo_transporte_4",
    "zona_bajada": "zona_fin_viaje",
    "zona_bajada_1era": "zona_bajada_1",
    "zona_bajada_2da": "zona_bajada_2",
    "zona_bajada_3era": "zona_bajada_3",
    "zona_bajada_4ta": "zona_bajada_4",
    "zona_subida": "zona_inicio_viaje",
    "zona_subida_1era": "zona_subida_1",
    "zona_subida_2da": "zona_subida_2",
    "zona_subida_3era": "zona_subida_3",
    "zona_subida_4ta": "zona_subida_4",
}

_RENOMBRE_INTERMEDIO = {
    "id": "id_tarjeta",
    "etapas": "n_etapas",
    "netapa": "n_etapas",
    "comunabajada": "comuna_fin_viaje",
    "comunasubida": "comuna_inicio_viaje",
    "dviajeenruta_mts": "distancia_ruta",
    "dviajeeuclidiana_mts": "distancia_eucl",
    "factorexpansion": "factor_expansion",
    "paraderobajada": "paradero_fin_viaje",
    "paraderobajada_1era": "paradero_bajada_1",
    "paraderobajada_2da": "paradero_bajada_2",
    "paraderobajada_3era": "paradero_bajada_3",
    "paraderobajada_4ta": "paradero_bajada_4",
    "paraderosubida": "paradero_inicio_viaje",
    "paraderosubida_1era": "paradero_subida_1",
    "paraderosubida_2da": "paradero_subida_2",
    "paraderosubida_3era": "paradero_subida_3",
    "paraderosubida_4ta": "paradero_subida_4",
    "serv_1era_etapa": "srv_1",
    "serv_2da_etapa": "srv_2",
    "serv_3era_etapa": "srv_3",
    "serv_4ta_etapa": "srv_4",
    "tiempobajada": "tiempo_fin_viaje",
    "tiempobajada_1era": "tiempo_bajada_1",
    "tiempobajada_2da": "tiempo_bajada_2",
    "tiempobajada_3era": "tiempo_bajada_3",
    "tiempobajada_4ta": "tiempo_bajada_4",
    "tiemposubida": "tiempo_inicio_viaje",
    "tiemposubida_1era": "tiempo_subida_1",
    "tiemposubida_2da": "tiempo_subida_2",
    "tiemposubida_3era": "tiempo_subida_3",
    "tiemposubida_4ta": "tiempo_subida_4",
    "tipotransporte_1era": "tipo_transporte_1",
    "tipotransporte_2da": "tipo_transporte_2",
    "tipotransporte_3era": "tipo_transporte_3",
    "tipotransporte_4ta": "tipo_transporte_4",
    "zona777bajada_1era": "zona_bajada_1",
    "zona777bajada_2da": "zona_bajada_2",
    "zona777bajada_3era": "zona_bajada_3",
    "zona777bajada_4ta": "zona_bajada_4",
    "zona777subida_1era": "zona_subida_1",
    "zona777subida_2da": "zona_subida_2",
    "zona777subida_3era": "zona_subida_3",
    "zona777subida_4ta": "zona_subida_4",
}

# Algunas entregas codifican el modo y la comuna como enteros. Ambos
# diccionarios se derivaron de los propios datos: el modo, revisando el
# servicio y el paradero asociados a cada código (2 aparece con srv "L1" y
# paradero "LOS LEONES"; 4 con srv "METROTREN"); la comuna, cruzando el
# paradero de subida contra las entregas que traen el nombre escrito. El
# código -1 marca la comuna no determinada.
TIPO_TRANSPORTE_CODIGO = {1: "BUS", 2: "METRO", 3: "ZP", 4: "METROTREN"}

COMUNA_CODIGO = {
    0: "LAMPA",
    2: "LO BARNECHEA",
    3: "LAS CONDES",
    4: "PENALOLEN",
    5: "LA FLORIDA",
    6: "PUENTE ALTO",
    8: "SAN BERNARDO",
    13: "PADRE HURTADO",
    14: "MAIPU",
    15: "PUDAHUEL",
    16: "ESTACION CENTRAL",
    17: "LO PRADO",
    18: "CERRO NAVIA",
    19: "RENCA",
    20: "QUILICURA",
    21: "HUECHURABA",
    22: "VITACURA",
    23: "PROVIDENCIA",
    24: "LA REINA",
    25: "NUNOA",
    26: "MACUL",
    27: "SAN JOAQUIN",
    28: "LA GRANJA",
    29: "LA PINTANA",
    30: "EL BOSQUE",
    31: "LO ESPEJO",
    32: "CERRILLOS",
    33: "PEDRO AGUIRRE CERDA",
    34: "SANTIAGO",
    35: "QUINTA NORMAL",
    36: "INDEPENDENCIA",
    37: "CONCHALI",
    38: "RECOLETA",
    39: "SAN MIGUEL",
    40: "SAN RAMON",
    41: "LA CISTERNA",
}


def leer_csv(ruta, sep: str = "|", na_values: str = "-", **kwargs):
    """Lee un CSV del DTPM con el motor rápido, cayendo al motor C si falla."""
    try:
        return pd.read_csv(
            ruta, sep=sep, na_values=na_values, engine=MOTOR_CSV, **kwargs
        )
    except Exception as e:
        print(f"  motor {MOTOR_CSV} falló ({type(e).__name__}), se usa el motor C")
        return pd.read_csv(ruta, sep=sep, na_values=na_values, **kwargs)


def a_datetime(serie):
    """Parsea a datetime en microsegundos.

    El motor pyarrow infiere milisegundos, así que la unidad se fija de forma
    explícita para que todos los archivos compartan el mismo tipo.
    """
    return pd.to_datetime(serie).astype("datetime64[us]")


def decodificar_categorias(df):
    """Traduce modo y comuna a texto cuando vienen como códigos numéricos.

    Las columnas que ya están en texto pasan sin cambios, de modo que todas las
    entregas terminen con los mismos valores.
    """
    if "tipo_transporte_1" in df.columns and pd.api.types.is_numeric_dtype(
        df["tipo_transporte_1"]
    ):
        for i in range(1, 5):
            col = f"tipo_transporte_{i}"
            if col in df.columns:
                df[col] = df[col].map(TIPO_TRANSPORTE_CODIGO).astype("object")

    for col in ("comuna_inicio_viaje", "comuna_fin_viaje"):
        if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
            df[col] = df[col].map(COMUNA_CODIGO).astype("object")

    return df


def _fecha_desde_nombre(ruta) -> tuple[int, int, int] | None:
    """Extrae (año, mes, día) de un nombre tipo `2026-04-11.viajes.csv.gz`."""
    partes = Path(ruta).name.split(".")[0].split("-")
    if len(partes) < 3:
        return None
    try:
        return int(partes[0]), int(partes[1]), int(partes[2])
    except ValueError:
        return None


def leer_viajes(ruta, crudo: bool = False, **kwargs):
    """Lee un archivo de viajes y lo devuelve en el esquema unificado.

    Con `crudo=True` devuelve el DataFrame sin normalizar, útil para inspeccionar
    una entrega nueva. La fecha sale del nombre del archivo, que en las entregas
    diarias del DTPM empieza con `YYYY-MM-DD`.
    """
    df = leer_csv(ruta, **kwargs)
    if crudo:
        return df

    if "correlativo_viajes" in df.columns:
        df = df.rename(columns=_RENOMBRE_ADATRAP)
    elif "paraderosubida_1era" in df.columns:
        df = df.rename(columns=_RENOMBRE_INTERMEDIO)
        # Este esquema no distingue zona de inicio ni de fin del viaje.
        df["zona_inicio_viaje"] = None
        df["zona_fin_viaje"] = None

    if "id_tarjeta" not in df.columns:
        if "id_viaje" in df.columns:
            df = df.rename(columns={"id_viaje": "id_tarjeta"})
        else:
            # Las entregas de transparencia describen viajes anónimos.
            df["id_tarjeta"] = None

    df = decodificar_categorias(df)

    for i in range(1, 5):
        df[f"tiempo_subida_{i}"] = a_datetime(df[f"tiempo_subida_{i}"])
        df[f"tiempo_bajada_{i}"] = a_datetime(df[f"tiempo_bajada_{i}"])
    df["tiempo_inicio_viaje"] = a_datetime(df["tiempo_inicio_viaje"])
    df["tiempo_fin_viaje"] = a_datetime(df["tiempo_fin_viaje"])

    fecha = _fecha_desde_nombre(ruta)
    if fecha is not None:
        df["year"], df["month"], df["day"] = fecha
    else:
        df["year"] = df["tiempo_inicio_viaje"].dt.year
        df["month"] = df["tiempo_inicio_viaje"].dt.month
        df["day"] = df["tiempo_inicio_viaje"].dt.day

    for col in COLUMNAS_SALIDA:
        if col not in df.columns:
            df[col] = None

    return df[COLUMNAS_SALIDA]


def _convertir_uno(ruta, destino, procesar, compression):
    """Convierte un archivo diario a parquet. Corre en un proceso worker."""
    df = procesar(ruta)
    filas = len(df)
    df.to_parquet(destino, engine="pyarrow", compression=compression)
    del df
    gc.collect()
    return filas


def convertir_archivos(
    archivos,
    directorio_salida,
    procesar=leer_viajes,
    workers: int = 1,
    overwrite: bool = False,
    compression: str = COMPRESION,
):
    """Convierte archivos diarios a parquet, uno por día.

    Es reanudable: los días cuyo parquet ya existe se saltan, salvo `overwrite`.
    Cada día es independiente, así que el paralelismo es por archivo. Conviene
    ajustar `workers` al RAM disponible, porque el pico de memoria escala con
    ese número, y a la velocidad del disco de origen, que suele ser el límite
    real al reprocesar volúmenes grandes.
    """
    directorio_salida = Path(directorio_salida)
    directorio_salida.mkdir(parents=True, exist_ok=True)

    pendientes = []
    for ruta in sorted(map(str, archivos)):
        fecha = Path(ruta).name.split(".")[0]
        destino = directorio_salida / f"{fecha}.parquet"
        if destino.exists() and not overwrite:
            continue
        pendientes.append((ruta, destino))

    print(
        f"{len(pendientes)} archivo(s) por convertir, "
        f"{workers} worker(s), compresión {compression}"
    )

    resultados = {}
    if workers <= 1:
        for ruta, destino in pendientes:
            print(f"{ruta} -> {destino}")
            try:
                resultados[destino] = _convertir_uno(
                    ruta, destino, procesar, compression
                )
                print(f"  {resultados[destino]:,} filas")
            except (EOFError, UnicodeDecodeError) as e:
                print(f"  archivo ilegible, se omite: {e}")
        return resultados

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futuros = {
            pool.submit(_convertir_uno, r, d, procesar, compression): (r, d)
            for r, d in pendientes
        }
        for i, futuro in enumerate(as_completed(futuros), 1):
            ruta, destino = futuros[futuro]
            try:
                resultados[destino] = futuro.result()
                print(f"[{i}/{len(pendientes)}] {destino}: {resultados[destino]:,} filas")
            except (EOFError, UnicodeDecodeError) as e:
                print(f"[{i}/{len(pendientes)}] {ruta} ilegible, se omite: {e}")

    return resultados
