"""palomatrix: ingesta y normalización de datos abiertos del transporte de Santiago.

El DTPM publica las tablas de viajes y etapas del sistema Red, el catálogo de
paradas y el GTFS, en formatos que han cambiado a lo largo de los años. Este
paquete los lleva a un esquema único para poder analizar la serie completa.

Uso típico
----------
    from palomatrix import leer_viajes, convertir_archivos

    convertir_archivos(sorted(Path("crudos").glob("*.gz")), "salida/")

El paquete no incluye datos personales ni de tarjetas identificadas: trabaja
solo con los datos que el DTPM publica de forma abierta.
"""

from .consolidado import anio_a_parquet, consolidar_anio, descargar_anio
from .descarga import (
    MAPEO_DTPM,
    SIN_IDENTIFICADOR,
    URL_GTFS,
    URL_PARADEROS,
    descargar,
    detectar_encoding,
    detectar_separador,
    extraer,
)
from .etapas import etapas_a_viajes
from .inventario import dias_faltantes, escanear_dias, inventario, resumen
from .paraderos import (
    ALIAS_VIAJES,
    cargar_estaciones_gtfs,
    cargar_paradas_bus,
    construir_catalogo,
    geolocalizar,
    normalizar_nombre,
    normalizar_paradero,
)
from .viajes import (
    COLUMNAS_SALIDA,
    COMUNA_CODIGO,
    TIPO_TRANSPORTE_CODIGO,
    a_datetime,
    convertir_archivos,
    decodificar_categorias,
    leer_csv,
    leer_viajes,
)

__version__ = "0.1.0"

__all__ = [
    "ALIAS_VIAJES",
    "COLUMNAS_SALIDA",
    "COMUNA_CODIGO",
    "MAPEO_DTPM",
    "SIN_IDENTIFICADOR",
    "TIPO_TRANSPORTE_CODIGO",
    "URL_GTFS",
    "URL_PARADEROS",
    "a_datetime",
    "anio_a_parquet",
    "cargar_estaciones_gtfs",
    "cargar_paradas_bus",
    "consolidar_anio",
    "construir_catalogo",
    "convertir_archivos",
    "decodificar_categorias",
    "descargar",
    "descargar_anio",
    "detectar_encoding",
    "detectar_separador",
    "dias_faltantes",
    "escanear_dias",
    "etapas_a_viajes",
    "extraer",
    "geolocalizar",
    "inventario",
    "leer_csv",
    "leer_viajes",
    "normalizar_nombre",
    "normalizar_paradero",
    "resumen",
]
