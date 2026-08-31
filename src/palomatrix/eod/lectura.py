"""Lectura de la Encuesta Origen-Destino de Santiago 2012.

La EOD 2012 es una encuesta de hogares que levantó SECTRA con un diseño
relacional: hogares, personas, viajes y etapas, con factores de expansión por
tipo de día. Este módulo la lleva a DataFrames con los códigos ya traducidos.

Las tablas vienen dentro del paquete en parquet, así que leerlas no requiere
descargar nada. Con el argumento `ruta` los lectores usan los CSV originales
de la encuesta en vez de esas copias, por si se necesita otra entrega.

Los nombres de columna son los de la encuesta (`Persona`, `Proposito`,
`HoraIni`), no la convención del resto de `palomatrix`. La encuesta tiene un
solo esquema, estable y documentado por el organismo que la publica, así que
renombrar solo alejaría las tablas de su documentación oficial.
"""

import codecs
from pathlib import Path

import geopandas as gpd
import pandas as pd

from . import codigos

RUTA_DATOS = Path(__file__).parent / "datos"

# Coordenadas de la encuesta: UTM 19 Sur.
CRS_EOD = "EPSG:32719"

# Columnas de viajes que guardan códigos, y la tabla que las traduce. Los
# sectores y las comunas se repiten en origen y destino contra la misma tabla.
CODIGOS_VIAJES = {
    "ActividadDestino": "ActividadDestino",
    "CodigoTiempo": "CodigoTiempo",
    "ComunaDestino": "Comunas",
    "ComunaOrigen": "Comunas",
    "ModoAgregado": "ModoAgregado",
    "ModoDifusion": "ModoDifusion",
    "ModoMotor": "ModoMotor",
    "ModoPriPub": "ModoPriPub",
    "Periodo": "Periodo",
    "Proposito": "Proposito",
    "PropositoAgregado": "PropositoAgregado",
    "SectorDestino": "Sector",
    "SectorOrigen": "Sector",
    "TiempoMedio": "TiempoMedio",
}

CODIGOS_PERSONAS = {
    "ActividadEmpresa": "ActividadEmpresa",
    "AdultoMayor": "AdultoMayor",
    "DondeEstudia": "DondeEstudia",
    "Estudios": "Estudios",
    "IngresoImputado": "IngresoImputado",
    "JornadaTrabajo": "JornadaTrabajo",
    "NoViaja": "NoViaja",
    "Ocupacion": "Ocupacion",
    "PaseEscolar": "PaseEscolar",
    "Relacion": "Relacion",
    "Sexo": "Sexo",
    "TieneIngresos": "TieneIngresos",
    "TramoIngreso": "TramoIngreso",
    "TramoIngresoFinal": "TramoIngreso",
}

# `Hogares.csv` escribe la comuna con letras, así que no se decodifica.
CODIGOS_HOGARES = {
    "Propiedad": "Propiedad",
    "Sector": "Sector",
    "Temporada": "Temporada",
    "TipoDia": "TipoDia",
}

CODIGOS_ETAPAS = {
    "CirculacionBicicleta": "CirculacionBicicleta",
    "ComunaDestino": "Comunas",
    "ComunaOrigen": "Comunas",
    "Estaciona": "Estaciona",
    "EstacionaBicicleta": "EstacionaBicicleta",
    "FormaPago": "Formapago",
    "HorarioMetro": "HorarioMetro",
    "Modo": "Modo",
    "ModoEstacionaBicicleta": "ModoestacionaBicicleta",
    "PropiedadBicicleta": "PropiedadBicicleta",
    "UsaCiclovia": "UsaCiclovia",
    "UsoHabitualBicicleta": "UsoHabitualBicicleta",
}

CODIGOS_VEHICULOS = {
    "Combustible": "Combustible",
    "EdadVehiculo": "EdadVehiculo",
    "Propiedad": "Propiedad",
    "SelloVerde": "SelloVerde",
    "TipoVeh": "TipoVeh",
}

# Columnas que guardan varios códigos en un solo campo, separados por `;`. No
# se decodifican en línea porque `A;B` no es un código: hay que desglosarlas
# con `desglosar`, que devuelve una fila por valor. `Discapacidad` es la
# excepción que no se puede traducir: sus datos usan letras y su diccionario,
# números, sin correspondencia declarada.
MULTIVALUADAS = {
    "Actividad",
    "Autopistas",
    "Discapacidad",
    "EstacionMetroCambio",
    "LicenciaConducir",
    "MediosUsados",
    "NoUsaAutopistas",
    "NoUsaTransantiago",
}

# Orden de prioridad con que se busca el factor de expansión. La tabla de
# viajes escribe estos nombres sin guion bajo y la de personas con guion bajo,
# así que la búsqueda ignora ese carácter.
FACTORES = {
    "FactorLaboralNormal": "Laboral",
    "FactorDomingoNormal": "Domingo",
    "FactorSabadoNormal": "Sábado",
    "FactorLaboralEstival": "LaboralEstival",
    "FactorFindesemanaEstival": "FindesemanaEstival",
}

HORAS = ["HoraIni", "HoraFin", "HoraMedia"]


def _encoding(ruta: Path) -> str:
    """Devuelve el encoding del archivo probando utf-8 y luego iso-8859-1.

    La encuesta mezcla ambos: `Etapas.csv` y `Vehiculo.csv` llevan acentos en
    iso-8859-1 y el resto es utf-8, sin que nada en el archivo lo declare.
    """
    decodificador = codecs.getincrementaldecoder("utf-8")()
    with open(ruta, "rb") as archivo:
        while bloque := archivo.read(1 << 20):
            try:
                decodificador.decode(bloque)
            except UnicodeDecodeError:
                return "iso-8859-1"
    return "utf-8"


def _leer_csv(ruta: Path, **kwargs) -> pd.DataFrame:
    """Lee un CSV de la encuesta: separador `;`, coma decimal, encoding variable."""
    kwargs.setdefault("encoding", _encoding(ruta))
    return pd.read_csv(ruta, sep=";", decimal=",", **kwargs)


def _viajes_csv(directorio: Path) -> pd.DataFrame:
    """Une las tres tablas en que la encuesta reparte los viajes."""
    return (
        _leer_csv(directorio / "viajes.csv")
        .join(_leer_csv(directorio / "ViajesDifusion.csv", index_col="Viaje"), on="Viaje")
        .join(_leer_csv(directorio / "DistanciaViaje.csv", index_col="Viaje"), on="Viaje")
    )


def _personas_csv(directorio: Path) -> pd.DataFrame:
    """Une las personas con su edad, que viene en un archivo aparte."""
    return _leer_csv(directorio / "personas.csv").join(
        _leer_csv(directorio / "Edadpersonas.csv", index_col="Persona"), on="Persona"
    )


# Tablas base y cómo se arman desde los CSV originales. Las copias en parquet
# que trae el paquete son el resultado de estas mismas funciones.
CRUDOS = {
    "viajes": _viajes_csv,
    "personas": _personas_csv,
    "hogares": lambda d: _leer_csv(d / "Hogares.csv"),
    "etapas": lambda d: _leer_csv(d / "Etapas.csv"),
    "vehiculos": lambda d: _leer_csv(d / "Vehiculo.csv"),
}


def crudo(nombre: str, ruta=None) -> pd.DataFrame:
    """Devuelve una tabla sin decodificar ni filtrar.

    Parameters
    ----------
    nombre : str
        Una de `viajes`, `personas`, `hogares`, `etapas` o `vehiculos`.
    ruta : str o Path, opcional
        Directorio con los CSV originales de la encuesta. Sin valor, usa la
        copia en parquet que trae el paquete.
    """
    if nombre not in CRUDOS:
        raise KeyError(f"No existe la tabla '{nombre}'. Disponibles: {sorted(CRUDOS)}")
    if ruta is None:
        return pd.read_parquet(RUTA_DATOS / f"{nombre}.parquet")

    directorio = Path(ruta)
    if not directorio.exists():
        raise FileNotFoundError(f"No existe el directorio {directorio}")
    return CRUDOS[nombre](directorio)


def _decodificar_columnas(df: pd.DataFrame, mapeo: dict) -> pd.DataFrame:
    for columna, tabla in mapeo.items():
        if columna in df.columns:
            df[columna] = codigos.decodificar(df[columna], tabla)
    return df


def _a_timedelta(serie: pd.Series) -> pd.Series:
    """Convierte una hora de reloj `H:MM` a timedelta desde la medianoche."""
    return pd.to_timedelta(serie.astype("string") + ":00", errors="coerce")


def _columnas_factor(df: pd.DataFrame) -> dict:
    """Ubica las columnas de factor por tipo de día y las mapea a su etiqueta."""
    equivalencias = {c.replace("_", ""): c for c in df.columns}
    return {
        equivalencias[c]: etiqueta
        for c, etiqueta in FACTORES.items()
        if c in equivalencias
    }


def _tipo_dia_y_factor(df: pd.DataFrame, columna_factor: str) -> pd.DataFrame:
    """Agrega `TipoDia` y el factor del día registrado, en una sola columna.

    Cada registro trae un único factor no nulo: el del tipo de día que le tocó
    registrar a esa persona. Las columnas se recorren en el orden de
    `FACTORES`, que decide qué etiqueta gana si alguna vez hubiera más de una.
    """
    presentes = _columnas_factor(df)
    if not presentes:
        return df

    factores = df[list(presentes)]
    ocupadas = factores.notna()
    primera = ocupadas.idxmax(axis=1).where(ocupadas.any(axis=1))

    df["TipoDia"] = pd.Categorical(
        primera.map(presentes), categories=list(FACTORES.values())
    )
    df[columna_factor] = factores.bfill(axis=1).iloc[:, 0]
    return df


def leer_viajes(ruta=None, decodificar=True, filtrar_invalidos=True, horas_a_timedelta=True):
    """Lee la tabla de viajes con su modo de difusión y sus distancias.

    Parameters
    ----------
    ruta : str o Path, opcional
        Directorio con los CSV originales. Sin valor, usa la copia que trae el
        paquete.
    decodificar : bool
        Traduce los códigos de modo, propósito, comuna, sector y período.
    filtrar_invalidos : bool
        Descarta los viajes sin hora de inicio, los imputados y los que no
        tienen distancia calculada.
    horas_a_timedelta : bool
        Convierte `HoraIni`, `HoraFin` y `HoraMedia` a timedelta desde la
        medianoche.

    Returns
    -------
    pd.DataFrame
        Un viaje por fila, con `TipoDia` y `FactorExpansion` derivados de los
        cinco factores de expansión de la encuesta.
    """
    df = crudo("viajes", ruta)

    if filtrar_invalidos:
        antes = len(df)
        df = df[df["HoraIni"].notna() & (df["Imputada"] == 0) & (df["DistManhattan"] != -1)]
        df = df.copy()
        print(f"VIAJES: {len(df)} válidos de {antes} ({antes - len(df)} descartados)")

    if decodificar:
        df = _decodificar_columnas(df, CODIGOS_VIAJES)

    if horas_a_timedelta:
        for columna in HORAS:
            df[columna] = _a_timedelta(df[columna])

    return _tipo_dia_y_factor(df, "FactorExpansion")


def leer_etapas(ruta=None, decodificar=True):
    """Lee las etapas de los viajes, con una fila por etapa.

    La encuesta descompone cada viaje en las etapas que lo forman, con su modo,
    zonas de origen y destino, y los tiempos de espera y las tarifas
    declaradas. Es la tabla comparable con las etapas del sistema Red.
    """
    df = crudo("etapas", ruta)

    if decodificar:
        df = _decodificar_columnas(df, CODIGOS_ETAPAS)

    return df


def leer_personas(ruta=None, decodificar=True):
    """Lee la tabla de personas encuestadas, con su edad ya incorporada.

    La encuesta trae dos factores por persona, y no son iguales. `Factor`, que
    aquí queda como `FactorPersona`, expande a la población total y es el que
    se usa para ponderar viajes. Los cinco factores por tipo de día expanden
    dentro del día que la persona registró, y quedan resumidos en
    `FactorPersonaTipoDia`, junto con la etiqueta `TipoDia`.
    """
    df = crudo("personas", ruta).rename(columns={"Factor": "FactorPersona"})

    if decodificar:
        df = _decodificar_columnas(df, CODIGOS_PERSONAS)

    return _tipo_dia_y_factor(df, "FactorPersonaTipoDia")


def leer_hogares(ruta=None, decodificar=True):
    """Lee la tabla de hogares. El factor de expansión queda en `FactorHogar`."""
    df = crudo("hogares", ruta).rename(columns={"Factor": "FactorHogar"})

    if decodificar:
        df = _decodificar_columnas(df, CODIGOS_HOGARES)

    return df


# Columnas del hogar que chocan con las de viajes o con las derivadas, y el
# nombre con que se llevan a la tabla unida.
RENOMBRE_HOGAR = {
    "Sector": "SectorHogar",
    "Zona": "ZonaHogar",
    "Comuna": "ComunaHogar",
    "DirCoordX": "HogarCoordX",
    "DirCoordY": "HogarCoordY",
    "TipoDia": "TipoDiaHogar",
}


def leer_viajes_personas(ruta=None, con_hogares=True, **kwargs):
    """Une viajes, personas y hogares, y calcula el peso expandido del viaje.

    Ponderar un viaje exige las dos tablas: `FactorExpansion` corrige el viaje
    dentro de su tipo de día y ronda 1, mientras que `FactorPersona` expande a
    la población. El producto queda en `Peso`, y es lo que hay que sumar para
    obtener viajes de la ciudad, no filas de la muestra.

    Parameters
    ----------
    ruta : str o Path, opcional
        Directorio con los CSV originales.
    con_hogares : bool
        Agrega los atributos del hogar. Las columnas que chocan con las de
        viaje llevan el sufijo `Hogar` (`ZonaHogar`, `ComunaHogar`).
    **kwargs
        Se pasan a `leer_viajes`.

    Returns
    -------
    pd.DataFrame
        Un viaje por fila, con los atributos de quien lo hizo y de su hogar.
    """
    viajes = leer_viajes(ruta, **kwargs)
    personas = leer_personas(ruta)

    # `Hogar` y `TipoDia` ya vienen en viajes, y los factores por tipo de día
    # quedaron resumidos en `FactorPersonaTipoDia`.
    repetidas = ["Hogar", "TipoDia", *_columnas_factor(personas)]
    personas = personas.drop(columns=[c for c in repetidas if c in personas.columns])

    df = viajes.merge(personas, on="Persona", how="left", validate="many_to_one")
    df["Peso"] = df["FactorExpansion"] * df["FactorPersona"]

    if con_hogares:
        hogares = leer_hogares(ruta).rename(columns=RENOMBRE_HOGAR)
        df = df.merge(hogares, on="Hogar", how="left", validate="many_to_one")

    print(f"VIAJES EXPANDIDOS: {df['Peso'].sum():,.0f} desde {len(df)} registros")
    return df


def leer_vehiculos(ruta=None, decodificar=True):
    """Lee los vehículos declarados por los hogares."""
    df = crudo("vehiculos", ruta)

    if decodificar:
        df = _decodificar_columnas(df, CODIGOS_VEHICULOS)

    return df


def leer_uso_transantiago(ruta=None, decodificar=True):
    """Razones declaradas para no usar Transantiago, una fila por razón.

    La encuesta guarda varias razones en un solo campo separadas por `;`, así
    que una persona puede aparecer en más de una fila.
    """
    return codigos.desglosar(
        crudo("personas", ruta),
        "NoUsaTransantiago",
        clave="Persona",
        tabla="NoUsaTransantiago" if decodificar else None,
    )


def leer_zonas() -> gpd.GeoDataFrame:
    """Devuelve las 866 zonas EOD 2012 con su geometría, en EPSG:32719.

    Es la misma zonificación que usan las columnas de zona de las tablas de
    viajes del DTPM, de modo que sirve para llevar ambas fuentes a la misma
    unidad espacial.
    """
    return gpd.read_parquet(RUTA_DATOS / "zonificacion.parquet")


def georreferenciar(df, col_x, col_y, crs_destino=None) -> gpd.GeoDataFrame:
    """Construye un GeoDataFrame a partir de un par de columnas de coordenadas.

    Las coordenadas de la encuesta están en UTM 19 Sur y corresponden al
    centroide de la manzana, no a la dirección exacta.

    Parameters
    ----------
    df : DataFrame
    col_x, col_y : str
        Columnas con las coordenadas, por ejemplo `OrigenCoordX` y
        `OrigenCoordY`.
    crs_destino : str, opcional
        Sistema de coordenadas de salida. Sin valor, mantiene UTM 19 Sur.
    """
    coordenadas = df[[col_x, col_y]].apply(pd.to_numeric, errors="coerce")
    geo = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(coordenadas[col_x], coordenadas[col_y]),
        crs=CRS_EOD,
    )
    return geo.to_crs(crs_destino) if crs_destino else geo
