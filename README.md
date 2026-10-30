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
python -m ambulancias_pergamino listar-ambulancias
python -m ambulancias_pergamino exportar-mapa
```

El segundo comando genera `data/mapa_pergamino.html`. El grafo, las bases, las
ambulancias y las rutas estan embebidos; Leaflet y las teselas de OpenStreetMap
se cargan desde Internet mediante CDN.

En Windows, la forma recomendada de abrirlo es ejecutar `abrir-mapa.cmd` con
doble clic, o desde PowerShell:

```powershell
.\abrir-mapa.cmd
```

El script genera el mapa si no existe, inicia un servidor local en segundo plano
y abre `http://127.0.0.1:8765/mapa_pergamino.html` en el navegador. Si el puerto
esta ocupado, prueba los siguientes. No conviene abrir el HTML directamente con
`file://`, porque OpenStreetMap puede bloquear las teselas al no recibir un
`Referer` HTTP valido.

Tambien se puede iniciar el servidor manualmente:

```powershell
python -m http.server 8765 --directory data
```

Y luego abrir `http://127.0.0.1:8765/mapa_pergamino.html`. Para detener el
servidor iniciado por el script:

```powershell
Get-NetTCPConnection -LocalPort 8765 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess }
```

## Establecimientos de destino simulados

La configuracion `config/establecimientos.json` habilita como destinos al
Hospital Interzonal San Jose y a tres clinicas. El hospital no tiene
penalizacion; las clinicas suman 1000 metros simulados al comparar destinos.
La distancia vial real y la penalizacion se conservan por separado, y no se
modifican los pesos del grafo ni el resultado de Dijkstra.

```bash
python -m ambulancias_pergamino listar-establecimientos
python -m ambulancias_pergamino exportar-mapa
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
python -m ambulancias_pergamino listar-emergencias
python -m ambulancias_pergamino verificar-emergencias
python -m ambulancias_pergamino exportar-mapa
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
python -m ambulancias_pergamino resumir-alternativas
python -m ambulancias_pergamino listar-alternativas --emergencia E1
python -m ambulancias_pergamino exportar-mapa
```

El mapa permite elegir manualmente los tres elementos y dibuja ambos tramos.
La Etapa 5 no incluye seleccion automatica, asignacion global, heuristicas,
backtracking ni cambios de estado.

## Reduccion heuristica de alternativas (Etapa 6)

La Etapa 6 no asigna ambulancias ni reserva recursos: reduce el espacio de
busqueda a partir de las alternativas de la Etapa 5 y deja los datos listos
para una asignacion posterior.

1. Se excluyen las alternativas con `es_factible = false`, conservando la
   definicion de factibilidad existente.
2. Para cada emergencia se conservan las `k = 3` ambulancias compatibles mas
   cercanas a la emergencia (distancia ambulancia -> emergencia). Los empates
   se resuelven por identificador.
3. Para cada emergencia se conservan los `h = 2` establecimientos compatibles
   con menor `distancia(emergencia, establecimiento) + penalizacion`. La
   penalizacion sigue siendo el mecanismo que prefiere al Hospital San Jose;
   los empates se resuelven por identificador.
4. Las alternativas reducidas solo combinan ambulancias y establecimientos
   conservados que ademas sean factibles. Las alternativas originales no se
   modifican y siguen disponibles para comparar.

Con los datos actuales se pasa de 120 a 30 alternativas (75 % de reduccion):
60 tras el filtro de ambulancias y 30 tras el filtro de establecimientos.

El orden de atencion calculado (solo informativo) es: mayor gravedad, menor
cantidad de ambulancias compatibles disponibles, mayor tiempo de espera e
identificador como desempate. Para los datos actuales: E2, E1, E3, E4, E5.

Los niveles configurables de expansion de candidatos son:

| Nivel | k | h |
| --- | --- | --- |
| 1 | 3 | 2 |
| 2 | 4 | 3 |
| 3 | 5 | 4 |
| 4 | 6 | 4 |

```bash
python -m ambulancias_pergamino resumir-heuristicas
python -m ambulancias_pergamino resumir-heuristicas --nivel 2
python -m ambulancias_pergamino listar-candidatos --emergencia E1
python -m ambulancias_pergamino listar-alternativas-reducidas --emergencia E1
python -m ambulancias_pergamino exportar-mapa
```

`listar-candidatos` informa ambulancias y establecimientos conservados y
excluidos, sus distancias, criterios y motivos. `listar-alternativas-reducidas`
permite consultar todas las emergencias o una en particular. Los motivos de
exclusion por heuristica son `fuera_de_las_k_mas_cercanas` y
`fuera_de_los_h_mas_convenientes`.

El mapa incorpora un selector de emergencia que atenua las ambulancias
descartadas, resalta los establecimientos conservados, muestra la cantidad de
candidatos antes y despues, y permite dibujar los dos tramos de cada
alternativa reducida. El visor manual de la Etapa 5 sigue funcionando.

Esta etapa no implementa asignacion global, reserva de ambulancias, cambios de
disponibilidad ni expansion automatica entre niveles. Esa validacion queda para
la etapa siguiente.

## Asignacion global de ambulancias (Etapa 7)

La Etapa 7 elige, como maximo, una alternativa factible por emergencia y usa
cada ambulancia a lo sumo una vez. No reserva ambulancias ni modifica su
disponibilidad: solo construye una asignacion sobre los datos recibidos.

La comparacion entre asignaciones es lexicografica:

1. maximizar la cantidad de emergencias atendidas;
2. maximizar el vector de prioridad, siguiendo el orden de la Etapa 6
   (gravedad, menor cantidad de ambulancias compatibles, espera e
   identificador);
3. minimizar el costo total `sum(costo_seleccion)`;
4. elegir la asignacion con identificadores lexicograficamente menores como
   desempate determinista.

El algoritmo es backtracking determinista con dos podas seguras:

- para cada par `(emergencia, ambulancia)` se conserva solo la alternativa
  factible de menor costo; los empates se resuelven por establecimiento;
- se descartan las ramas que no pueden superar la mayor cantidad de
  emergencias atendidas ya encontrada.

La dominancia por establecimiento es valida con el modelo actual porque la
capacidad de los establecimientos no es un recurso compartido. La marca
`es_optima` significa que la solucion es optima dentro del conjunto de
alternativas evaluado (original o reducido), no necesariamente respecto de un
modelo con restricciones adicionales.

Con los datos actuales, los cuatro niveles reducidos y el conjunto original
alcanzan la misma solucion completa:

- emergencias atendidas: 5 de 5, en el orden E2, E1, E3, E4, E5;
- ambulancias utilizadas: A1, A2, A4, A5, A6;
- establecimientos seleccionados: GUARDIA-1, GUARDIA-2 y GUARDIA-3;
- costo total: 27017 m;
- nivel 1: 30 alternativas candidatas y 15 evaluadas tras dominancia;
- conjunto original: 120 alternativas candidatas y 30 evaluadas.

Por lo tanto, para estos datos el nivel 1 no pierde optimalidad frente al
conjunto original. La comparacion tambien informa si una reduccion elimina una
combinacion necesaria; esa situacion puede aparecer con otros datos aunque no
ocurra en el escenario actual.

```bash
python -m ambulancias_pergamino resumir-asignacion
python -m ambulancias_pergamino resumir-asignacion --original
python -m ambulancias_pergamino listar-asignacion --nivel 2
python -m ambulancias_pergamino comparar-asignaciones
```

`resumir-asignacion` informa el conjunto usado, la cantidad de alternativas
candidatas y evaluadas, las emergencias atendidas y sin asignar, los motivos,
el costo total, las ambulancias y establecimientos utilizados. `listar-asignacion`
muestra el detalle de cada alternativa seleccionada. `comparar-asignaciones`
compara el conjunto original con los niveles 1 a 4 e indica el nivel recomendado
y las diferencias detectadas.

El mapa incorpora un selector de conjunto (original o niveles 1 a 4) que dibuja
los dos tramos de todas las alternativas seleccionadas, atenua las ambulancias
no utilizadas y las emergencias sin asignar, y resalta los establecimientos
elegidos. El visor manual y la reduccion de candidatos de las etapas anteriores
siguen funcionando.

Esta etapa no implementa reserva efectiva, cambios de disponibilidad,
reoptimizacion dinamica, multiples ambulancias por emergencia ni capacidad
compartida de establecimientos. Tampoco reemplaza un sistema de despacho real.

## Fuente de datos

- WFS: `https://geonode.pergamino.gob.ar/geoserver/ows`
- Callejero: `geonode:callejero`
- Guardias medicas: `geonode:guardias_medicas`

