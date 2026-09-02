"""palomatrix: datos abiertos de movilidad de Santiago.

El paquete cubre dos fuentes. El DTPM publica las tablas de viajes y etapas del
sistema Red, el catálogo de paradas y el GTFS, en formatos que han cambiado a
lo largo de los años, y `palomatrix` los lleva a un esquema único para analizar
la serie completa. SECTRA publica la Encuesta Origen-Destino 2012, que está en
el subpaquete `palomatrix.eod` y aporta los viajes que las tarjetas bip! no
registran, con su propósito declarado.

Las dos fuentes comparten la zonificación de 866 zonas EOD, que es la unidad
espacial en la que se pueden comparar.

Uso típico
----------
    from palomatrix import leer_viajes, convertir_archivos, eod

    convertir_archivos(sorted(Path("crudos").glob("*.gz")), "salida/")
    viajes_encuesta = eod.leer_viajes()

El paquete trabaja solo con los datos que ambos organismos publican de forma
abierta.
"""

from . import eod
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
    "eod",
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
