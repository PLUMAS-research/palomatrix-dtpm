"""Conversión de la tabla de etapas del DTPM al esquema de viajes.

Cada fila del archivo de etapas es una etapa; un viaje agrupa hasta cuatro.
Este módulo las pivotea al mismo esquema que produce `palomatrix.viajes`, lo que
sirve cuando una fecha solo se publicó como etapas, o cuando conviene la
metadata de las etapas porque trae el número de etapas ya calculado.

`proposito` no existe en la tabla de etapas y queda nulo.
"""

from pathlib import Path

import pandas as pd

from .viajes import COLUMNAS_SALIDA, a_datetime, leer_csv

_RENOMBRE_ANTIGUO = {
    "id": "id_etapa",
    "nviaje": "correlativo_viajes",
    "netapa": "correlativo_etapas",
    "t_subida": "tiempo_subida",
    "t_bajada": "tiempo_bajada",
    "t_etapa": "tiempo_etapa",
    "par_subida": "parada_subida",
    "par_bajada": "parada_bajada",
}


def etapas_a_viajes(ruta, **kwargs):
    """Lee un archivo de etapas y devuelve viajes en el esquema unificado."""
    df = leer_csv(ruta, encoding="ISO-8859-1", **kwargs)

    if "netapa" in df.columns:
        df = df.rename(columns=_RENOMBRE_ANTIGUO)

    df = df[df["correlativo_etapas"] <= 4]
    claves = ["id_etapa", "correlativo_viajes"]

    # Cada etapa pasa a columnas con sufijo 1 a 4.
    pivotes = []
    for i in range(1, 5):
        renombre = {
            "servicio_subida": f"srv_{i}",
            "parada_subida": f"paradero_subida_{i}",
            "parada_bajada": f"paradero_bajada_{i}",
            "tiempo_subida": f"tiempo_subida_{i}",
            "tiempo_bajada": f"tiempo_bajada_{i}",
            "zona_subida": f"zona_subida_{i}",
            "zona_bajada": f"zona_bajada_{i}",
            "tipo_transporte": f"tipo_transporte_{i}",
        }
        etapa = df[df["correlativo_etapas"] == i].set_index(claves)
        pivotes.append(etapa[list(renombre)].rename(columns=renombre))

    primera = (
        df[df["correlativo_etapas"] == 1]
        .set_index(claves)[
            [
                "parada_subida",
                "comuna_subida",
                "zona_subida",
                "tiempo_subida",
                "fExpansionServicioPeriodoTS",
            ]
        ]
        .rename(
            columns={
                "parada_subida": "paradero_inicio_viaje",
                "comuna_subida": "comuna_inicio_viaje",
                "zona_subida": "zona_inicio_viaje",
                "tiempo_subida": "tiempo_inicio_viaje",
                "fExpansionServicioPeriodoTS": "factor_expansion",
            }
        )
    )

    ultima = (
        df.sort_values("correlativo_etapas")
        .groupby(claves)
        .last()[["parada_bajada", "comuna_bajada", "zona_bajada", "tiempo_bajada"]]
        .rename(
            columns={
                "parada_bajada": "paradero_fin_viaje",
                "comuna_bajada": "comuna_fin_viaje",
                "zona_bajada": "zona_fin_viaje",
                "tiempo_bajada": "tiempo_fin_viaje",
            }
        )
    )

    agregados = df.groupby(claves).agg(
        distancia_ruta=("dist_ruta_paraderos", "sum"),
        distancia_eucl=("dist_eucl_paraderos", "sum"),
        n_etapas=("correlativo_etapas", "max"),
    )

    if "contrato" in df.columns:
        contrato = df[df["correlativo_etapas"] == 1].set_index(claves)[["contrato"]]
    else:
        contrato = pd.DataFrame(index=primera.index, columns=["contrato"])

    viajes = primera.join([ultima, agregados, contrato] + pivotes, how="left")
    viajes = viajes.reset_index().rename(columns={"id_etapa": "id_tarjeta"})

    for i in range(1, 5):
        viajes[f"tiempo_subida_{i}"] = a_datetime(viajes[f"tiempo_subida_{i}"])
        viajes[f"tiempo_bajada_{i}"] = a_datetime(viajes[f"tiempo_bajada_{i}"])
    viajes["tiempo_inicio_viaje"] = a_datetime(viajes["tiempo_inicio_viaje"])
    viajes["tiempo_fin_viaje"] = a_datetime(viajes["tiempo_fin_viaje"])

    anio, mes, dia = Path(ruta).name.split(".")[0].split("-")[:3]
    viajes["year"], viajes["month"], viajes["day"] = int(anio), int(mes), int(dia)

    viajes["proposito"] = None

    return viajes[COLUMNAS_SALIDA]
