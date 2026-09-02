# palomatrix

Ingesta y normalización de los datos abiertos de movilidad de Santiago. Cubre
dos fuentes: los datos del sistema Red que publica el DTPM (viajes, etapas,
catálogo de paradas y GTFS) y la Encuesta Origen-Destino 2012 de SECTRA.

Las dos fuentes se complementan. Las tarjetas bip! registran cada transacción
del transporte público, pero no ven los viajes en auto, a pie ni en bicicleta,
y no preguntan para qué se viaja. La encuesta cubre esos viajes y ese
propósito, con una muestra de 18.264 hogares y un solo día de registro por
persona. Ambas fuentes usan la zonificación de 866 zonas EOD, que es la unidad
en la que se pueden comparar.

## Instalación

El paquete no está publicado en PyPI, así que se instala desde el repositorio
con `uv`:

```bash
uv add "palomatrix @ git+https://github.com/PLUMAS-research/palomatrix-dtpm"                      # ingesta y normalización
uv add "palomatrix[consolidado] @ git+https://github.com/PLUMAS-research/palomatrix-dtpm"          # además, consolidación anual (dask)
uv add "palomatrix[diagnosticos] @ git+https://github.com/PLUMAS-research/palomatrix-dtpm"         # además, gráficos (matplotlib)
```

Para extraer los archivos comprimidos del DTPM se necesita `unrar` y `7z` en el
sistema. La encuesta no los necesita.

## Datos del DTPM

El problema que resuelve es la heterogeneidad de las entregas. A lo largo de los
años el DTPM ha publicado el mismo contenido bajo tres esquemas de columnas, en
`.rar` y en `.zip`, con separadores y codificaciones distintas, a veces con un
archivo por día y a veces con un CSV mensual de más de 10 GB, y con el modo de
transporte y la comuna escritos unas veces como texto y otras como código
numérico. `palomatrix` lleva todo eso a un esquema único para poder analizar la
serie completa.

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

### Esquema de viajes

Un viaje encadena hasta cuatro etapas, que quedan en columnas numeradas de 1 a
4: `paradero_subida_i`, `paradero_bajada_i`, `tiempo_subida_i`,
`tiempo_bajada_i`, `zona_subida_i`, `zona_bajada_i`, `srv_i` y
`tipo_transporte_i`. A nivel de viaje están `id_tarjeta`, `n_etapas`,
`factor_expansion`, `contrato`, `proposito`, las distancias, y el origen y
destino con su paradero, comuna, zona y hora.

`convertir_archivos` es reanudable: salta los días cuyo parquet ya existe. Con
`workers` mayor que 1 procesa varios días en paralelo, aunque conviene medir
antes, porque en discos externos el límite suele ser la lectura y no la CPU.

## Encuesta Origen-Destino 2012

La EOD 2012 es la última encuesta de movilidad de hogares del Gran Santiago que
levantó SECTRA. Su diseño es relacional: 18.264 hogares, 60.054 personas,
113.591 viajes y 133.444 etapas, con factores de expansión por tipo de día.

```python
from palomatrix import eod

viajes = eod.leer_viajes_personas()
viajes["Grupo"] = eod.agrupar_propositos(viajes["Proposito"])

zonas = eod.leer_zonas()
```

Las tablas vienen dentro del paquete en parquet, así que leerlas no descarga
nada ni necesita archivos externos. Con el argumento `ruta` los lectores usan
los CSV originales de la encuesta en vez de esas copias, por si se necesita
otra entrega: `eod.leer_viajes("mis_datos/EOD_STGO")`.

Los nombres de columna son los de la encuesta (`Persona`, `Proposito`,
`HoraIni`), no la convención del resto del paquete. La encuesta tiene un solo
esquema, estable y documentado por SECTRA, así que renombrarlo solo alejaría
las tablas de su documentación oficial.

### Lo que viene en el paquete

La encuesta completa, en 9,4 MB de parquet: las cinco tablas de datos (viajes,
personas, hogares, etapas y vehículos), las 58 tablas de códigos con sus 1.200
entradas y la geometría de las 866 zonas.

Las tablas de datos se guardan sin decodificar ni filtrar, de modo que las
opciones de cada lector siguen disponibles y `crudo("viajes")` devuelve la
tabla tal como viene. Los diccionarios de códigos originales están repartidos
en 61 CSV que mezclan separador `;` y `,`, codificación utf-8 e iso-8859-1,
encabezados sin convención y columnas de relleno, además de valores con
espacios sobrantes que hacían que `Taxi ` y `Taxi` fueran categorías distintas.

```python
eod.tablas()                      # nombres de las tablas de códigos
eod.tabla("Proposito")            # una tabla, como serie de id a valor
eod.decodificar(serie, "Sexo")    # traduce una columna cualquiera
eod.crudo("viajes")               # tabla base, sin decodificar ni filtrar
```

`herramientas/construir_datos_eod.py` regenera todos esos archivos desde la
entrega original de la encuesta.

### Respuestas de opción múltiple

Varias columnas guardan más de un código en un solo campo, separados por `;`:
`Actividad`, `LicenciaConducir` y `NoUsaTransantiago` en personas, `Autopistas`
y `EstacionMetroCambio` en etapas. `desglosar` devuelve una fila por valor
declarado, ya decodificada.

```python
personas = eod.leer_personas()
actividades = eod.desglosar(personas, "Actividad", clave="Persona", tabla="Actividad")
```

`leer_uso_transantiago` es el mismo desglose para las razones declaradas para
no usar el sistema.

### Factores de expansión

La encuesta trae tres factores y no son intercambiables:

- `FactorExpansion`, en la tabla de viajes, corrige el viaje dentro de su tipo
  de día y ronda 1. Sumarlo no da viajes de la ciudad.
- `FactorPersona` expande la persona a la población total.
- `FactorPersonaTipoDia` expande dentro del día que esa persona registró, de
  modo que un domingo pesa mucho más que un día laboral.

`leer_viajes_personas` une ambas tablas y deja en `Peso` el producto
`FactorExpansion * FactorPersona`, que es lo que hay que sumar para obtener
viajes y no filas de la muestra. `TipoDia` indica el día registrado.

### Propósitos

`GRUPOS_PROPOSITOS` agrega los 14 propósitos de la encuesta en cuatro
categorías: Cuidado, Empleo/Estudio, Personal y Hogar. La encuesta reparte la
movilidad del cuidado entre compras, trámites, salud y acompañamiento, así que
medirla exige agregarla de forma explícita (Sánchez de Madariaga, 2013).
`agrupar_propositos` aplica esa agregación sobre la columna ya decodificada.

### Cruce con los datos del DTPM

Las columnas de zona de las tablas de viajes del DTPM usan la zonificación EOD
2012. En una entrega de noviembre de 2023, las 792 zonas presentes son un
subconjunto de las 866 de la encuesta, y cubren el 100% de los viajes con zona
asignada.

```python
import pandas as pd
from palomatrix import eod

viajes = pd.read_parquet("data/viajes/2023-11-01.parquet")
zonas = eod.leer_zonas()

# Las zonas del DTPM vienen como texto o como float, según la entrega.
viajes["zona"] = pd.to_numeric(viajes["zona_inicio_viaje"], errors="coerce").astype("Int64")
viajes = viajes.merge(zonas, on="zona", how="left")
```

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

**Los diccionarios de códigos del DTPM se derivaron de los propios datos**, no
de documentación oficial: el modo, revisando el servicio y la parada asociados a
cada código; la comuna, cruzando la parada de subida contra las entregas que
traen el nombre escrito.

**La encuesta descarta viajes por defecto.** `leer_viajes` deja fuera los que no
tienen hora de inicio, los imputados y los que no tienen distancia calculada,
con lo que quedan 89.775 de 113.591. `filtrar_invalidos=False` los conserva.

**La columna `Discapacidad` no se puede decodificar.** Los datos usan letras y
su diccionario usa números, sin correspondencia declarada en la entrega, así
que el paquete deja los códigos como vienen. Lo mismo ocurre con los códigos de
"sin dato" que ninguna tabla lista, como el 0 de `TramoIngreso` o el 999 de las
comunas de etapas: quedan nulos tras decodificar.

**Las coordenadas de la encuesta son centroides de manzana**, no direcciones, y
están en UTM 19 Sur (EPSG:32719). `georreferenciar` construye la geometría y
reproyecta si se le pide otro sistema.

**La encuesta es una foto de 2012 y de un solo día por persona.** No captura la
variación entre días ni el cambio de la ciudad desde entonces, y depende de lo
que cada persona declara, con subreporte conocido de los viajes cortos, a pie y
de cuidado.

## Licencia

El código está bajo licencia MIT.

Los datos que vienen en `src/palomatrix/eod/datos/` son la Encuesta
Origen-Destino de Santiago 2012, un dato público levantado por SECTRA
(Ministerio de Transportes y Telecomunicaciones). El paquete los redistribuye
convertidos a parquet, sin modificar su contenido. Los datos del DTPM no se
redistribuyen: se descargan de su sitio con las funciones del paquete.

## Financiamiento

Este trabajo fue financiado por el proyecto LOICA, ANID Fondecyt Regular
#1261835.
