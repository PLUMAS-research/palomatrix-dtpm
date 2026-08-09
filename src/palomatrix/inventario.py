"""Cobertura y diagnóstico de una serie de parquets diarios.

Sirve para saber qué días hay, cuáles faltan y cómo se distribuyen los viajes,
sin cargar la serie completa: el inventario lee solo los metadatos de cada
archivo, y el escaneo diario guarda sus resultados para no repetir el trabajo
cuando se agregan días nuevos.
"""

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

COLUMNAS_HORA = [f"hora_{h}" for h in range(24)]


def inventario(directorio) -> pd.DataFrame:
    """Un registro por día con filas y tamaño, leyendo solo metadatos."""
    registros = []
    for archivo in sorted(Path(directorio).glob("*.parquet")):
        registros.append(
            {
                "fecha": pd.Timestamp(archivo.stem),
                "archivo": archivo.name,
                "filas": pq.read_metadata(archivo).num_rows,
                "mb": archivo.stat().st_size / 1e6,
            }
        )
    return pd.DataFrame(registros).sort_values("fecha").reset_index(drop=True)


def dias_faltantes(inv: pd.DataFrame) -> pd.DatetimeIndex:
    """Días sin datos dentro del rango cubierto por el inventario."""
    if inv.empty:
        return pd.DatetimeIndex([])
    rango = pd.date_range(inv["fecha"].min(), inv["fecha"].max(), freq="D")
    return rango.difference(inv["fecha"])


def resumen(inv: pd.DataFrame) -> str:
    """Texto con el estado de la serie: rango, volumen y cobertura."""
    if inv.empty:
        return "Sin archivos."

    faltantes = dias_faltantes(inv)
    rango = pd.date_range(inv["fecha"].min(), inv["fecha"].max(), freq="D")
    mensual = inv.assign(mes=inv["fecha"].dt.to_period("M")).groupby("mes").agg(
        dias=("fecha", "count"), filas=("filas", "sum"), mb=("mb", "sum")
    )

    lineas = [
        f"Archivos:        {len(inv):,}",
        f"Rango:           {inv['fecha'].min():%Y-%m-%d} a {inv['fecha'].max():%Y-%m-%d}",
        f"Filas:           {inv['filas'].sum():,}",
        f"Tamaño:          {inv['mb'].sum() / 1e3:.1f} GB",
        f"Días del rango:  {len(rango):,}",
        f"Días sin datos:  {len(faltantes):,}",
        "",
        "Por mes:",
    ]
    for mes, fila in mensual.iterrows():
        lineas.append(
            f"  {mes}  {int(fila['dias']):>3} días  {int(fila['filas']):>14,} filas"
            f"  {fila['mb'] / 1e3:>6.1f} GB"
        )
    return "\n".join(lineas)


def escanear_dias(directorio, cache: pd.DataFrame | None = None) -> pd.DataFrame:
    """Viajes, tarjetas distintas y distribución horaria por día.

    Los días presentes en `cache` no se vuelven a leer, así que agregar un mes
    cuesta solo ese mes.
    """
    archivos = sorted(Path(directorio).glob("*.parquet"))
    if cache is not None and not cache.empty:
        vistos = set(cache["fecha"])
        archivos = [a for a in archivos if pd.Timestamp(a.stem) not in vistos]
        print(f"  {len(vistos):,} día(s) en caché, {len(archivos):,} por escanear")

    registros = []
    for i, archivo in enumerate(archivos, 1):
        if i % 100 == 0 or i == len(archivos):
            print(f"  {i}/{len(archivos)}")
        df = pq.read_table(
            archivo, columns=["id_tarjeta", "tiempo_inicio_viaje"]
        ).to_pandas()

        # El índice de value_counts es float si la columna trae nulos, así que
        # la hora se castea para no crear columnas paralelas.
        conteo = dict.fromkeys(COLUMNAS_HORA, 0)
        for hora, n in df["tiempo_inicio_viaje"].dt.hour.value_counts().items():
            if pd.notna(hora):
                conteo[f"hora_{int(hora)}"] = int(n)

        registros.append(
            {
                "fecha": pd.Timestamp(archivo.stem),
                "viajes": len(df),
                "tarjetas": df["id_tarjeta"].nunique(),
                **conteo,
            }
        )

    nuevos = pd.DataFrame(registros)
    if cache is not None and not cache.empty:
        nuevos = pd.concat([cache, nuevos], ignore_index=True)
    return nuevos.sort_values("fecha").reset_index(drop=True)
