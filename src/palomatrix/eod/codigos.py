"""Diccionarios de códigos de la EOD 2012.

La encuesta guarda casi todas sus variables como identificadores numéricos y
reparte los diccionarios en 61 CSV con separadores, codificaciones y nombres de
columna que no siguen una convención única. Este módulo los sirve desde una
tabla ya normalizada que viene con el paquete, así que decodificar no depende
de tener `Tablas_parametros/` en disco.
"""

from functools import cache, lru_cache
from pathlib import Path

import pandas as pd

RUTA_CODIGOS = Path(__file__).parent / "datos" / "codigos.parquet"

# Agrupación de los 14 propósitos de la encuesta en cuatro categorías. La EOD
# reparte la movilidad del cuidado entre compras, trámites y acompañamiento,
# de modo que medirla exige agregarlos de forma explícita (Sánchez de
# Madariaga, 2013). "Hogar" queda separado porque el retorno a casa no es una
# actividad en sí y suele excluirse del análisis.
GRUPOS_PROPOSITOS = {
    "De salud": "Cuidado",
    "Visitar a alguien": "Cuidado",
    "Buscar o Dejar a alguien": "Cuidado",
    "Buscar o dejar algo": "Cuidado",
    "De compras": "Cuidado",
    "Trámites": "Cuidado",
    "Al trabajo": "Empleo/Estudio",
    "Por trabajo": "Empleo/Estudio",
    "Al estudio": "Empleo/Estudio",
    "Por estudio": "Empleo/Estudio",
    "Recreación": "Personal",
    "Comer o Tomar algo": "Personal",
    "Otra actividad (especifique)": "Personal",
    "volver a casa": "Hogar",
}

PROPOSITOS = ["Cuidado", "Empleo/Estudio", "Personal", "Hogar"]


@lru_cache(maxsize=1)
def _codigos() -> pd.DataFrame:
    return pd.read_parquet(RUTA_CODIGOS)


def tablas() -> list[str]:
    """Nombres de las tablas de códigos disponibles."""
    return sorted(_codigos()["tabla"].unique())


@cache
def tabla(nombre: str) -> pd.Series:
    """Devuelve una tabla de códigos como serie de id a valor."""
    codigos = _codigos()
    seleccion = codigos[codigos["tabla"] == nombre]
    if seleccion.empty:
        raise KeyError(f"No existe la tabla '{nombre}'. Disponibles: {tablas()}")
    return seleccion.set_index("id")["valor"]


def _claves(serie: pd.Series) -> pd.Series:
    """Lleva una columna de códigos a texto comparable con la tabla.

    Los identificadores son enteros, pero pandas los lee como float cuando la
    columna tiene nulos, y entonces `1` se escribe `1.0`. Unos pocos códigos
    son letras (las razones para no usar Transantiago), así que la comparación
    se hace siempre sobre texto.
    """
    if pd.api.types.is_numeric_dtype(serie):
        return serie.astype("Float64").astype("Int64").astype("string")
    return serie.astype("string").str.strip()


def decodificar(serie: pd.Series, nombre: str) -> pd.Series:
    """Reemplaza los códigos de una columna por su significado.

    Parameters
    ----------
    serie : pd.Series
        Columna con los identificadores.
    nombre : str
        Tabla de códigos, por ejemplo `Proposito` o `Sexo`. `tablas()` lista
        las disponibles.

    Returns
    -------
    pd.Series
        Serie categórica con los valores decodificados. Los códigos que no
        estén en la tabla quedan nulos.
    """
    decodificada = _claves(serie).map(tabla(nombre))
    return decodificada.astype("category")


def desglosar(df, columna: str, clave: str, tabla: str | None = None, sep: str = ";"):
    """Explota una columna que guarda varios códigos en un solo campo.

    La encuesta escribe algunas respuestas de opción múltiple como `A;B`, de
    modo que decodificarlas exige separarlas antes. Ocurre en `Actividad`,
    `LicenciaConducir` y `NoUsaTransantiago` de personas, y en `Autopistas` y
    `EstacionMetroCambio` de etapas.

    Parameters
    ----------
    df : DataFrame
        Tabla de origen, por ejemplo la que devuelve `leer_personas`.
    columna : str
        Columna multivaluada.
    clave : str
        Identificador que se conserva, por ejemplo `Persona` o `Viaje`.
    tabla : str, opcional
        Tabla de códigos con que traducir el resultado. Sin valor, devuelve
        los códigos.
    sep : str
        Separador entre valores.

    Returns
    -------
    pd.DataFrame
        Dos columnas, `clave` y `columna`, con una fila por valor declarado.
        Las filas sin respuesta quedan fuera.
    """
    valores = (
        df.set_index(clave)[columna]
        .dropna()
        .astype("string")
        .str.split(sep)
        .explode()
        .str.strip()
    )
    resultado = valores[valores != ""].reset_index()

    if tabla is not None:
        resultado[columna] = decodificar(resultado[columna], tabla)

    return resultado


def agrupar_propositos(serie: pd.Series) -> pd.Series:
    """Agrupa los propósitos de viaje en Cuidado, Empleo/Estudio, Personal y Hogar.

    Recibe la columna `Proposito` ya decodificada. Los valores fuera de los 14
    propósitos de la encuesta quedan nulos.
    """
    agrupada = serie.astype("string").map(GRUPOS_PROPOSITOS)
    return pd.Categorical(agrupada, categories=PROPOSITOS, ordered=False)
