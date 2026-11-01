# EmergenciasPergamino

## Presentacion

**EmergenciasPergamino** es un proyecto academico que modela el problema de
asignar ambulancias y establecimientos de destino a un conjunto de emergencias
urbanas en la ciudad de Pergamino.

El problema que busca resolver es decidir, para cada emergencia:

- que ambulancia la atiende;
- desde que base parte;
- a que establecimiento se traslada al paciente;
- que recorrido vial utiliza en cada tramo;
- cuanto cuesta esa decision en metros;
- como evoluciona la atencion en un escenario simulado.

El sistema construye un grafo vial dirigido a partir del callejero municipal,
calcula rutas minimas, genera alternativas completas, reduce candidatos con
heuristicas, resuelve una asignacion global y representa el resultado mediante
una simulacion logica y un mapa interactivo.

El alcance es **academico y reproducible**. No es un sistema operativo de
despacho de emergencias. Los datos de ambulancias, emergencias y
establecimientos son simulados, y los resultados dependen de los datos y
supuestos documentados en este README.

## Arquitectura

### Organizacion de los modulos

| Modulo | Responsabilidad |
| --- | --- |
| `ambulancias_pergamino/datos.py` | Prepara las bases de ambulancias a partir de los datos geograficos. |
| `ambulancias_pergamino/geonode.py` | Descarga capas WFS desde GeoNode. |
| `ambulancias_pergamino/geometria.py` | Funciones auxiliares de geometria y distancias. |
| `ambulancias_pergamino/grafo.py` | Modela el grafo vial dirigido y calcula caminos minimos con Dijkstra. |
| `ambulancias_pergamino/ambulancias.py` | Carga y valida las ambulancias simuladas. |
| `ambulancias_pergamino/emergencias.py` | Carga y valida emergencias; analiza conectividad. |
| `ambulancias_pergamino/establecimientos.py` | Carga destinos, prioridades, penalizaciones y costos de seleccion. |
| `ambulancias_pergamino/alternativas.py` | Construye las combinaciones ambulancia-emergencia-destino y reutiliza rutas. |
| `ambulancias_pergamino/heuristicas.py` | Reduce el espacio de busqueda con los niveles `k` y `h`. |
| `ambulancias_pergamino/asignacion.py` | Resuelve la asignacion global y compara escenarios. |
| `ambulancias_pergamino/simulacion.py` | Representa la atencion con etapas logicas y estados. |
| `ambulancias_pergamino/evaluacion.py` | Calcula metricas comparativas de los cinco escenarios. |
| `ambulancias_pergamino/mapa.py` | Genera el mapa HTML interactivo y exporta sus datos. |
| `ambulancias_pergamino/cli.py` | Implementa la interfaz de linea de comandos. |
| `ambulancias_pergamino/__main__.py` | Punto de entrada `python -m ambulancias_pergamino`. |

### Modelado del grafo

El grafo se construye con los tramos del callejero de Pergamino que cumplen
`localidad = 'Pergamino'` y `transitable = 'si'`.

- Cada arista tiene como peso la distancia geografica en metros.
- El sentido se interpreta como:
  - `0`: doble mano;
  - `1`: sentido de digitalizacion de la geometria;
  - `-1`: sentido contrario a la digitalizacion.
- Las bases, emergencias y establecimientos se vinculan al nodo vial mas
  cercano.
- La distancia entre el punto original y su nodo se conserva como dato, pero no
  se suma dos veces a las rutas viales.

### Algoritmo Dijkstra

`grafo.py` implementa Dijkstra sobre el grafo dirigido y devuelve la distancia
minima y el camino de nodos. Las rutas se calculan una sola vez por par de
interes y luego se reutilizan en las etapas siguientes. No se reimplementa
Dijkstra en alternativas, asignacion, simulacion ni evaluacion.

### Alternativas de rutas

Una alternativa completa combina:

```text
ambulancia -> emergencia -> establecimiento
```

Para cada combinacion se conservan dos tramos:

```text
distancia_total_m =
    distancia_ambulancia_emergencia_m
    + distancia_emergencia_establecimiento_m

costo_seleccion =
    distancia_total_m
    + penalizacion_establecimiento_m
```

La penalizacion no modifica el grafo ni las distancias viales. Se usa solamente
para comparar destinos. Una alternativa es factible cuando la ambulancia esta
disponible, tiene complejidad, capacidad y equipamiento suficientes, existe
ruta hasta la emergencia, el establecimiento esta habilitado, tiene complejidad
suficiente y existe ruta hasta el destino.

### Heuristicas

La reduccion heuristica conserva, para cada emergencia:

- las `k` ambulancias compatibles mas cercanas a la emergencia;
- los `h` establecimientos compatibles con menor
  `distancia(emergencia, establecimiento) + penalizacion`.

Los niveles configurados son:

| Nivel | k | h |
| --- | --- | --- |
| 1 | 3 | 2 |
| 2 | 4 | 3 |
| 3 | 5 | 4 |
| 4 | 6 | 4 |

La reduccion no asigna recursos ni modifica las alternativas originales. Las
alternativas descartadas quedan registradas con su motivo.

### Asignacion

La asignacion elige como maximo una alternativa por emergencia y usa cada
ambulancia a lo sumo una vez. El orden de comparacion es lexicografico:

1. maximizar la cantidad de emergencias atendidas;
2. maximizar el vector de prioridad, segun el orden de la Etapa 6
   (gravedad, menor cantidad de ambulancias compatibles, espera e
   identificador);
3. minimizar el costo total;
4. desempatar por identificadores lexicograficamente menores.

El algoritmo es backtracking determinista con dos podas:

- para cada par `(emergencia, ambulancia)` conserva solo la alternativa factible
  de menor costo;
- descarta ramas que no pueden superar la mayor cantidad de emergencias
  atendidas ya encontrada.

La dominancia por establecimiento es valida en el modelo actual porque la
capacidad de los establecimientos no se modela como recurso compartido.

### Simulacion

La simulacion es **logica por etapas**, no temporal. No usa velocidades,
duraciones de atencion ni tiempos de viaje porque el modelo no dispone de esos
datos.

Cada atencion conserva los dos tramos de la ruta original, sus distancias, la
penalizacion y el costo. La simulacion no vuelve a calcular rutas ni costos:
reutiliza las rutas de la Etapa 5 y verifica que los valores coincidan con la
asignacion de la Etapa 7.

### CLI y mapa interactivo

La CLI permite construir el grafo, inspeccionar datos, ejecutar alternativas,
heuristicas, asignaciones, simulaciones y la evaluacion final. El mapa HTML
embebe los datos y permite visualizar rutas, alternativas, reduccion de
candidatos, asignaciones, simulacion por etapas y la comparacion de escenarios.

## Funcionamiento

### 1. Construccion del grafo

```bash
python -m ambulancias_pergamino construir --salida data/pergamino.json
```

Descarga el callejero, normaliza los sentidos, construye el grafo dirigido y
guarda el resumen, el grafo y las bases de ambulancias.

### 2. Incorporacion de bases y ambulancias

`config/ambulancias.json` define una ambulancia simulada por base. El cargador
valida IDs, bases, disponibilidad, complejidad, capacidad y equipamiento, y
obtiene el nodo inicial desde la base correspondiente.

### 3. Definicion de destinos y prioridades

`config/establecimientos.json` habilita cuatro destinos. El Hospital Interzonal
San Jose tiene prioridad 1 y penalizacion 0; las clinicas tienen prioridad 2 y
una penalizacion simulada de 1000 metros. Medicar y SAME funcionan como bases de
ambulancias, pero no reciben pacientes.

### 4. Modelado de emergencias

`config/emergencias.json` contiene cinco casos simulados. Gravedad y complejidad
requerida son dimensiones independientes en escala 1 a 3. Cada emergencia se
vincula con su nodo vial mas cercano y conserva la distancia al nodo.

### 5. Construccion de alternativas

Con los datos actuales se generan 120 alternativas:

```text
6 ambulancias x 5 emergencias x 4 destinos = 120
```

Las 120 combinaciones reutilizan 50 rutas: 30 de ambulancia a emergencia y 20 de
emergencia a establecimiento.

### 6. Aplicacion de heuristicas

Cada nivel reduce el conjunto de alternativas factibles. La comparacion de
niveles se realiza sin modificar los datos originales y conserva las metricas de
cada escenario.

### 7. Asignacion de ambulancias y establecimientos

La asignacion global produce, para cada emergencia atendida, una ambulancia y un
establecimiento. Las emergencias que no pueden atenderse conservan un motivo
estable, por ejemplo `sin_alternativas_factibles`,
`ambulancias_candidatas_ya_utilizadas` o `sin_combinacion_compatible`.

### 8. Generacion de resultados y simulacion

La simulacion parte de la asignacion y recorre cinco etapas logicas:

| Paso | Etapa | Emergencia | Ambulancia | Significado |
| --- | --- | --- | --- | --- |
| 0 | `asignada` | `asignada` | `asignada` | La ambulancia y el destino ya fueron elegidos. |
| 1 | `en_camino` | `asignada` | `en_camino` | La ambulancia viaja hacia la emergencia. |
| 2 | `en_atencion` | `en_atencion` | `en_atencion` | La ambulancia esta en el lugar de la emergencia. |
| 3 | `trasladando` | `trasladada` | `trasladando` | El paciente ya fue retirado del lugar y la ambulancia viaja al destino. |
| 4 | `finalizada` | `finalizada` | `finalizada` | La atencion y el traslado se consideran completados. |

El paso 3 no significa que el traslado haya terminado: la emergencia figura
como `trasladada` porque el paciente ya esta fuera del lugar, y la ambulancia
figura como `trasladando` porque el viaje al establecimiento sigue en curso. La
finalizacion ocurre en el paso 4.

Una emergencia sin asignacion conserva `sin_asignacion` y su motivo. Una
ambulancia no utilizada permanece `disponible`. Las ambulancias utilizadas
terminan en `finalizada`; no se modela el regreso a la base ni la reutilizacion.

### 9. Evaluacion y metricas

La evaluacion compara el escenario original con los niveles 1 a 4 y calcula:

- alternativas generadas, factibles, conservadas y evaluadas;
- porcentaje de reduccion del espacio de busqueda;
- emergencias atendidas y sin asignar;
- ambulancias y destinos utilizados;
- costo total, distancia total y penalizaciones;
- diferencias de asignacion respecto del original;
- estados finales de emergencias y ambulancias.

Todos los valores se obtienen dinamicamente de las asignaciones y simulaciones.
No hay metricas hardcodeadas.

## Ejecucion

### Requisitos

- Python 3.11 o superior. El entorno verificado usa Python 3.12.10.
- No se requieren dependencias externas de Python.
- Node.js es opcional y solo se usa para validar la sintaxis del JavaScript del
  mapa en las pruebas.
- El mapa necesita Internet para cargar Leaflet y las teselas de OpenStreetMap.

### Pruebas

```bash
python -m unittest discover -v
```

La suite cubre construccion del grafo, modelos, alternativas, heuristicas,
asignacion, simulacion, evaluacion, CLI y mapa.

### CLI

```bash
python -m ambulancias_pergamino --help
```

Comandos principales:

```bash
# Datos y rutas
python -m ambulancias_pergamino construir --salida data/pergamino.json
python -m ambulancias_pergamino verificar-rutas
python -m ambulancias_pergamino listar-ambulancias
python -m ambulancias_pergamino listar-establecimientos
python -m ambulancias_pergamino listar-emergencias
python -m ambulancias_pergamino verificar-emergencias

# Alternativas y heuristicas
python -m ambulancias_pergamino resumir-alternativas
python -m ambulancias_pergamino listar-alternativas --emergencia E1
python -m ambulancias_pergamino resumir-heuristicas
python -m ambulancias_pergamino resumir-heuristicas --nivel 2
python -m ambulancias_pergamino listar-candidatos --emergencia E1
python -m ambulancias_pergamino listar-alternativas-reducidas --emergencia E1

# Asignacion
python -m ambulancias_pergamino resumir-asignacion
python -m ambulancias_pergamino resumir-asignacion --original
python -m ambulancias_pergamino listar-asignacion --nivel 2
python -m ambulancias_pergamino comparar-asignaciones

# Simulacion
python -m ambulancias_pergamino iniciar-simulacion
python -m ambulancias_pergamino resumir-simulacion
python -m ambulancias_pergamino resumir-simulacion --etapa 2
python -m ambulancias_pergamino listar-simulacion --nivel 2
python -m ambulancias_pergamino avanzar-simulacion --pasos 2
python -m ambulancias_pergamino avanzar-simulacion --hasta-final
python -m ambulancias_pergamino ver-simulacion --emergencia E2
python -m ambulancias_pergamino ver-simulacion --ambulancia A6 --etapa 2

# Evaluacion final
python -m ambulancias_pergamino evaluar-escenarios

# Mapa
python -m ambulancias_pergamino exportar-mapa
```

Los comandos de asignacion y simulacion aceptan `--nivel 1..4` o `--original`.
Los comandos de simulacion aceptan `--etapa 0..4` cuando corresponde.

### Mapa

```bash
python -m ambulancias_pergamino exportar-mapa
```

Genera `data/mapa_pergamino.html`. En Windows se recomienda abrirlo con:

```powershell
.\abrir-mapa.cmd
```

El script genera el mapa si no existe, inicia un servidor local y abre
`http://127.0.0.1:8765/mapa_pergamino.html`. Tambien se puede iniciar el servidor
manualmente:

```powershell
python -m http.server 8765 --directory data
```

No conviene abrir el HTML con `file://`, porque OpenStreetMap puede bloquear las
teselas al no recibir un `Referer` HTTP valido.

El mapa conserva:

- visor manual de alternativas;
- reduccion heuristica de candidatos;
- asignacion global por conjunto;
- simulacion logica por etapa y por emergencia;
- evaluacion comparativa de los cinco escenarios.

## Resultados

Los resultados siguientes se obtienen dinamicamente con los datos actuales y se
verifican en la suite de pruebas.

### Comparacion de escenarios

| Escenario | Generadas | Factibles | Conservadas | Evaluadas | Reduccion | Atendidas | Sin asignar | Costo | Distancia | Penalizaciones | Diferencias |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Original | 120 | 120 | 120 | 30 | 0.00 % | 5 | 0 | 27017.174 m | 24017.174 m | 3000 m | 0 |
| Nivel 1 | 120 | 120 | 30 | 15 | 75.00 % | 5 | 0 | 27017.174 m | 24017.174 m | 3000 m | 0 |
| Nivel 2 | 120 | 120 | 60 | 20 | 50.00 % | 5 | 0 | 27017.174 m | 24017.174 m | 3000 m | 0 |
| Nivel 3 | 120 | 120 | 100 | 25 | 16.67 % | 5 | 0 | 27017.174 m | 24017.174 m | 3000 m | 0 |
| Nivel 4 | 120 | 120 | 120 | 30 | 0.00 % | 5 | 0 | 27017.174 m | 24017.174 m | 3000 m | 0 |

Las ambulancias utilizadas son A1, A2, A4, A5 y A6. Los destinos seleccionados
son GUARDIA-1, GUARDIA-2 y GUARDIA-3. La ambulancia A3 no participa.

### Asignaciones

| Emergencia | Ambulancia | Base | Destino | Tramo inicial | Tramo al destino | Total | Penalizacion | Costo |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| E2 | A6 | SAME | GUARDIA-3 | 2445 m | 4124 m | 6569 m | 1000 m | 7569 m |
| E1 | A1 | GUARDIA-2 | GUARDIA-2 | 2667 m | 2675 m | 5342 m | 1000 m | 6342 m |
| E3 | A2 | GUARDIA-3 | GUARDIA-3 | 478 m | 696 m | 1174 m | 1000 m | 2174 m |
| E4 | A4 | GUARDIA-1 | GUARDIA-1 | 1769 m | 1700 m | 3468 m | 0 m | 3468 m |
| E5 | A5 | GUARDIA-5 | GUARDIA-1 | 3314 m | 4148 m | 7462 m | 0 m | 7462 m |

### Estados finales

En la etapa final:

- las cinco emergencias estan `finalizada`;
- las ambulancias A1, A2, A4, A5 y A6 estan `finalizada`;
- la ambulancia A3 permanece `disponible`;
- se completaron 5 atenciones de 5;
- no hay emergencias sin asignar.

## Evaluacion de las heuristicas

### Reduccion del espacio de busqueda

Los cuatro niveles reducen el conjunto de alternativas factibles:

- nivel 1: de 120 a 30 alternativas conservadas (75.00 % de reduccion);
- nivel 2: de 120 a 60 (50.00 %);
- nivel 3: de 120 a 100 (16.67 %);
- nivel 4: de 120 a 120 (0.00 %).

La cantidad de alternativas evaluadas tras la dominancia por
`(emergencia, ambulancia)` es 30 en el original, 15 en nivel 1, 20 en nivel 2,
25 en nivel 3 y 30 en nivel 4.

### Calidad de los resultados

Con los datos actuales:

- los cinco escenarios atienden las mismas 5 emergencias;
- no hay emergencias sin asignar;
- las asignaciones son identicas en los cinco escenarios;
- los costos, distancias y penalizaciones son identicos;
- no se detectaron diferencias de asignacion respecto del original;
- el nivel 1 es suficiente para obtener el mismo resultado que el original en
  este conjunto de datos.

Esto **no demuestra** que el nivel 1 sea siempre suficiente. Significa
unicamente que, para los datos actuales, la reduccion del nivel 1 conservo las
alternativas necesarias para alcanzar la misma solucion. Con otros datos podria
perder una alternativa relevante; `comparar-asignaciones` y
`evaluar-escenarios` informan si se detecta una perdida respecto del original.

### Alcance de la optimalidad

Hay que distinguir tres conceptos:

1. **Optimo dentro del conjunto original:** la asignacion original se resuelve
   sobre las 120 alternativas factibles. En el modelo actual, sin capacidad
   compartida de establecimientos, la dominancia por par
   `(emergencia, ambulancia)` es segura y el backtracking agota las
   combinaciones relevantes.
2. **Optimo dentro de un conjunto reducido:** cada nivel heuristico es optimo
   dentro de las alternativas que conservo, no necesariamente dentro de las 120
   originales.
3. **Optimo global del modelo completo:** solo puede afirmarse para el conjunto
   original evaluado. No se afirma optimalidad global frente a restricciones que
   el modelo no representa, como capacidad compartida, tiempos reales o reservas
   dinamicas.

La marca `es_optima` de una asignacion significa que es optima dentro del
conjunto evaluado. No es una garantia de optimalidad global del problema real.

## Auditoria de la Etapa 8

### Bases de las ambulancias

Se verifico que las bases informadas coinciden con la configuracion y con los
datos de las bases:

- A1: GUARDIA-2;
- A2: GUARDIA-3;
- A3: GUARDIA-4;
- A4: GUARDIA-1;
- A5: GUARDIA-5;
- A6: SAME.

Las coincidencias entre base de la ambulancia y destino elegido, como
`E1 -> A1 -> GUARDIA-2` o `E3 -> A2 -> GUARDIA-3`, son resultados validos de la
asignacion, no errores de construccion. No se modificaron datos para forzar
ninguna tabla.

### Estados del paso 3

Los estados `trasladada` y `trasladando` son coherentes con el modelo logico:

- `trasladada` describe la situacion de la emergencia: el paciente ya fue
  retirado del lugar;
- `trasladando` describe la actividad de la ambulancia: el vehiculo esta
  viajando hacia el establecimiento;
- la atencion recien se considera completada en el paso 4, cuando ambos estados
  pasan a `finalizada`.

No fue necesario cambiar las transiciones. Se agregaron pruebas que fijan esta
semantica y verifican que el paso 3 no se confunda con la finalizacion.

## Etapas implementadas

1. Construccion del grafo vial dirigido.
2. Incorporacion de bases y ambulancias simuladas.
3. Destinos, prioridades y penalizaciones.
4. Modelado de emergencias y conectividad.
5. Alternativas de recorrido con dos tramos.
6. Reduccion heuristica de candidatos.
7. Asignacion global de ambulancias y destinos.
8. Simulacion logica de la atencion.
9. Evaluacion comparativa, metricas y documentacion final.

## Pruebas

La suite actual contiene **164 pruebas**:

```text
python -m unittest discover -v
Ran 164 tests
OK
```

Las pruebas cubren, entre otros aspectos:

- construccion y validacion del grafo;
- modelos de ambulancias, emergencias y establecimientos;
- alternativas, rutas y costos;
- heuristicas y niveles de reduccion;
- asignacion global, empates y optimalidad dentro del conjunto;
- simulacion, transiciones y no mutacion de datos;
- evaluacion de los cinco escenarios y metricas;
- CLI y compatibilidad con comandos anteriores;
- exportacion del mapa, integridad de datos y sintaxis JavaScript.

La validacion del JavaScript se realiza con Node.js cuando esta disponible.

## Limitaciones

- La simulacion es **logica por etapas**, no temporal.
- No se modelan velocidades, tiempos de viaje, duraciones de atencion ni esperas
  adicionales.
- No se modela el regreso de la ambulancia a la base.
- No se modela la reutilizacion de una ambulancia despues de finalizar una
  atencion.
- No hay reservas reales ni cambios dinamicos de disponibilidad.
- La capacidad compartida de establecimientos no esta modelada: los destinos no
  se consumen entre emergencias.
- La optimalidad esta acotada al conjunto de alternativas evaluado. No se afirma
  optimalidad global frente a restricciones no representadas.
- Las heuristicas pueden descartar alternativas relevantes en otros conjuntos de
  datos. La comparacion detecta perdidas observadas, pero no garantiza que una
  reduccion sea siempre suficiente.
- El mapa depende de Internet para Leaflet y las teselas de OpenStreetMap.
- Los datos son simulados y el sistema es un modelo academico, no una
  herramienta operativa real de despacho.

## Fuente de datos

- WFS: `https://geonode.pergamino.gob.ar/geoserver/ows`
- Callejero: `geonode:callejero`
- Guardias medicas: `geonode:guardias_medicas`
- Datos locales:
  - `data/pergamino.json`
  - `config/ambulancias.json`
  - `config/emergencias.json`
  - `config/establecimientos.json`
