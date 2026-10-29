# Asignacion de ambulancias en Pergamino

Primera version del proyecto para construir un grafo vial dirigido de la
ciudad de Pergamino a partir de los servicios WFS de la IDE municipal.

## Alcance inicial

- Solo se usan tramos de la localidad `Pergamino` con `transitable = si`.
- El peso de cada arista es su distancia geografica en metros.
- Los sentidos del callejero se interpretan de esta manera:
  - `0`: doble mano.
  - `1`: sentido de digitalizacion de la geometria.
  - `-1`: sentido contrario a la digitalizacion.
- Las cinco guardias medicas se importan desde GeoNode.
- SAME Pergamino se agrega como fuente complementaria en Tucuman 150.
- Cada establecimiento se vincula con el nodo vial mas cercano.

La interpretacion del campo `sentido` esta aislada en el constructor para
que pueda ajustarse si la Municipalidad confirma otra codificacion.

## Ejecucion

Requiere Python 3.11 o superior y no utiliza dependencias externas.

```bash
python -m ambulancias_pergamino construir --salida data/pergamino.json
```

El archivo generado contiene un resumen, el grafo y las seis bases de
ambulancias. Para inspeccionar las rutas entre todas las bases:

```bash
python -m ambulancias_pergamino verificar-rutas --entrada data/pergamino.json
```

## Ambulancias simuladas y mapa

La configuracion `config/ambulancias.json` define una ambulancia simulada por
base. El cargador valida la configuracion y obtiene la ubicacion inicial desde
el nodo asociado a cada base.

```bash
py -3.14 -m ambulancias_pergamino listar-ambulancias
py -3.14 -m ambulancias_pergamino exportar-mapa
```

El segundo comando genera `data/mapa_pergamino.html`, que puede abrirse
directamente desde el sistema de archivos. El grafo, las bases, las ambulancias
y las rutas estan embebidos; Leaflet y las teselas de OpenStreetMap se cargan
desde Internet mediante CDN.

## Establecimientos de destino simulados

La configuracion `config/establecimientos.json` habilita como destinos al
Hospital Interzonal San Jose y a tres clinicas. El hospital no tiene
penalizacion; las clinicas suman 1000 metros simulados al comparar destinos.
La distancia vial real y la penalizacion se conservan por separado, y no se
modifican los pesos del grafo ni el resultado de Dijkstra.

```bash
py -3.14 -m ambulancias_pergamino listar-establecimientos
py -3.14 -m ambulancias_pergamino exportar-mapa
```

Medicar y SAME Pergamino siguen funcionando como bases de ambulancias, pero no
reciben pacientes. El mapa diferencia el hospital prioritario, las clinicas y
las bases sin destino habilitado.

## Emergencias simuladas

La configuracion `config/emergencias.json` contiene cinco casos fijos y
reproducibles distribuidos en el area urbana. Gravedad (prioridad clinica) y
complejidad requerida (nivel de recursos) son dimensiones independientes en
una escala de 1 a 3. El cargador valida los datos, vincula cada coordenada con
el nodo vial mas cercano y conserva la distancia entre ambos.

```bash
py -3.14 -m ambulancias_pergamino listar-emergencias
py -3.14 -m ambulancias_pergamino verificar-emergencias
py -3.14 -m ambulancias_pergamino exportar-mapa
```

`verificar-emergencias` informa, para cada caso, que bases pueden alcanzarlo y
que establecimientos habilitados son alcanzables desde su nodo. Este informe
no elige ambulancias ni destinos. El mapa muestra las emergencias por gravedad,
pero tampoco realiza asignaciones ni modifica posiciones.

Esta etapa no implementa despacho, seleccion de destino, heuristicas ni
actualizacion del estado de las ambulancias.

## Alternativas de recorrido

Una alternativa representa una combinacion completa `ambulancia -> emergencia
-> establecimiento`. Con los datos actuales se construyen 120 alternativas
(6 ambulancias por 5 emergencias por 4 destinos), sin seleccionar ninguna.

La distancia fisica se conserva separada en sus dos tramos y se calcula como:

`distancia_total_m = distancia_ambulancia_emergencia_m + distancia_emergencia_establecimiento_m`

El costo de comparacion mantiene aparte la penalizacion configurada:

`costo_seleccion = distancia_total_m + penalizacion_establecimiento_m`

La penalizacion nunca modifica las aristas, las distancias viales ni Dijkstra.
Una alternativa es factible cuando la ambulancia esta disponible, tiene
complejidad, capacidad y equipamiento suficientes, existe ruta hasta la
emergencia, el establecimiento esta habilitado, posee complejidad suficiente y
existe ruta desde la emergencia hasta el establecimiento.

Los motivos estables de descarte son `ambulancia_no_disponible`,
`complejidad_ambulancia_insuficiente`, `capacidad_ambulancia_insuficiente`,
`equipamiento_faltante`, `sin_ruta_hasta_emergencia`,
`establecimiento_no_habilitado`, `complejidad_establecimiento_insuficiente` y
`sin_ruta_hasta_establecimiento`. Se conservan todos los motivos aplicables.

Las 120 combinaciones reutilizan 50 rutas: 30 de ambulancia a emergencia y 20
de emergencia a establecimiento.

```bash
py -3.14 -m ambulancias_pergamino resumir-alternativas
py -3.14 -m ambulancias_pergamino listar-alternativas --emergencia E1
py -3.14 -m ambulancias_pergamino exportar-mapa
```

El mapa permite elegir manualmente los tres elementos y dibuja ambos tramos.
Todavia no existe seleccion automatica, asignacion global, heuristicas,
backtracking ni cambios de estado.

## Fuente de datos

- WFS: `https://geonode.pergamino.gob.ar/geoserver/ows`
- Callejero: `geonode:callejero`
- Guardias medicas: `geonode:guardias_medicas`

