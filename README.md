# palomatrix

Ingesta y normalización de los datos abiertos de transporte público de Santiago
que publica el DTPM: las tablas de viajes y etapas del sistema Red, el catálogo
de paradas y el GTFS.

El problema que resuelve es la heterogeneidad de las entregas. A lo largo de los
años el DTPM ha publicado el mismo contenido bajo tres esquemas de columnas, en
`.rar` y en `.zip`, con separadores y codificaciones distintas, a veces con un
archivo por día y a veces con un CSV mensual de más de 10 GB, y con el modo de
transporte y la comuna escritos unas veces como texto y otras como código
numérico. `palomatrix` lleva todo eso a un esquema único para poder analizar la
serie completa.

## Instalación

```bash
pip install palomatrix                      # ingesta y normalización
pip install "palomatrix[consolidado]"       # además, consolidación anual (dask)
pip install "palomatrix[diagnosticos]"      # además, gráficos (matplotlib)
```

Para extraer los archivos comprimidos se necesita `unrar` y `7z` en el sistema.

## Uso

Convertir un directorio de entregas diarias a parquet, un archivo por día:

```python
from pathlib import Path
from palomatrix import convertir_archivos

convertir_archivos(sorted(Path("crudos").glob("*.gz")), "data/viajes/")
```

Cuando la fecha solo se publicó como etapas:

```python
from palomatrix import convertir_archivos, etapas_a_viajes

convertir_archivos(archivos, "data/viajes/", procesar=etapas_a_viajes)
```

Construir el catálogo de paradas y ubicar los paraderos de una tabla de viajes:

```python
import pandas as pd
from palomatrix import construir_catalogo, geolocalizar

catalogo = construir_catalogo("data/crudos/")
viajes = pd.read_parquet("data/viajes/2026-04-15.parquet")
xy = geolocalizar(viajes["paradero_inicio_viaje"], catalogo)
```

Revisar la cobertura de una serie ya construida:

```python
from palomatrix import inventario, resumen

print(resumen(inventario("data/viajes/")))
```

## Esquema de viajes

Un viaje encadena hasta cuatro etapas, que quedan en columnas numeradas de 1 a
4: `paradero_subida_i`, `paradero_bajada_i`, `tiempo_subida_i`,
`tiempo_bajada_i`, `zona_subida_i`, `zona_bajada_i`, `srv_i` y
`tipo_transporte_i`. A nivel de viaje están `id_tarjeta`, `n_etapas`,
`factor_expansion`, `contrato`, `proposito`, las distancias, y el origen y
destino con su paradero, comuna, zona y hora.

`convertir_archivos` es reanudable: salta los días cuyo parquet ya existe. Con
`workers` mayor que 1 procesa varios días en paralelo, aunque conviene medir
antes, porque en discos externos el límite suele ser la lectura y no la CPU.

## Advertencias sobre los datos

**Las entregas de transparencia anteriores a 2019 no traen identificador de
tarjeta.** Su esquema describe viajes anónimos, sin clave que los enlace a una
persona, de modo que sirven para matrices de origen y destino agregadas, pero no
para análisis por individuo ni para unir con otras fuentes. El conjunto
`SIN_IDENTIFICADOR` lista los años afectados.

**El catálogo de paradas es una foto del presente.** Las entregas antiguas
mencionan paradas que ya no existen, así que la cobertura decae hacia atrás: los
embarques cuya parada no está en el catálogo van de 0% en 2026 a cerca de 15% en
2019. Además, las entregas antiguas escriben las estaciones de varias maneras,
con la línea al final en las combinaciones (`BAQUEDANO L1`), con capitalización
de título en el metrotren (`Estacion Lo Espejo`) o con espacios sobrantes.
`normalizar_paradero` resuelve esas variantes y `geolocalizar` la aplica a ambos
lados de la unión.

**Los diccionarios de códigos se derivaron de los propios datos**, no de
documentación oficial: el modo, revisando el servicio y la parada asociados a
cada código; la comuna, cruzando la parada de subida contra las entregas que
traen el nombre escrito.

## Alcance

El paquete trabaja solo con datos abiertos. Los atributos demográficos asociados
a tarjetas identificadas quedan fuera, y su tratamiento corresponde a los
proyectos que cuenten con la autorización correspondiente.

## Licencia

MIT.
