"""Encuesta Origen-Destino de Santiago 2012.

La EOD 2012 es la última encuesta de hogares de movilidad del Gran Santiago
que levantó SECTRA. Cubre lo que las tarjetas bip! no ven (viajes a pie, en
bicicleta y en auto, el propósito declarado y los atributos del hogar) y usa la
misma zonificación de 866 zonas que las tablas de viajes del DTPM, de modo que
ambas fuentes se pueden llevar a una unidad espacial común.

Uso típico
----------
    from palomatrix import eod

    viajes = eod.leer_viajes_personas()
    viajes["Grupo"] = eod.agrupar_propositos(viajes["Proposito"])
    zonas = eod.leer_zonas()

Los datos vienen dentro del paquete, así que nada de esto descarga nada ni
necesita archivos externos. `herramientas/construir_datos_eod.py` los regenera
desde la entrega original de la encuesta.
"""

from .codigos import (
    GRUPOS_PROPOSITOS,
    PROPOSITOS,
    agrupar_propositos,
    decodificar,
    desglosar,
    tabla,
    tablas,
)
from .lectura import (
    CRS_EOD,
    crudo,
    georreferenciar,
    leer_etapas,
    leer_hogares,
    leer_personas,
    leer_uso_transantiago,
    leer_vehiculos,
    leer_viajes,
    leer_viajes_personas,
    leer_zonas,
)

__all__ = [
    "CRS_EOD",
    "GRUPOS_PROPOSITOS",
    "PROPOSITOS",
    "agrupar_propositos",
    "crudo",
    "decodificar",
    "desglosar",
    "georreferenciar",
    "leer_etapas",
    "leer_hogares",
    "leer_personas",
    "leer_uso_transantiago",
    "leer_vehiculos",
    "leer_viajes",
    "leer_viajes_personas",
    "leer_zonas",
    "tabla",
    "tablas",
]
