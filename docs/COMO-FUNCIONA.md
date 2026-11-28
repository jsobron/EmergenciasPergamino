# Cómo funciona URGENCIAS Pergamino

Este documento explica el recorrido completo del sistema: desde el callejero de
Pergamino hasta el mapa interactivo. Está escrito para responder tres preguntas:

1. ¿de dónde salen los datos?
2. ¿cómo se eligen los caminos de las ambulancias?
3. ¿cómo se decide qué ambulancia atiende cada urgencia y adónde la traslada?

El proyecto es **académico y reproducible**. Los datos de ambulancias,
emergencias y establecimientos son simulados; no es un sistema real de despacho.

---

## 1. Vista general

El flujo es una cadena de transformaciones:

```text
Callejero WFS
    ↓
Grafo vial dirigido (nodos + aristas con distancias)
    ↓
Puntos de interés pegados al nodo más cercano
    ↓
Dijkstra: rutas entre bases, emergencias y destinos
    ↓
Alternativas: ambulancia → emergencia → establecimiento
    ↓
Heurísticas: reducer candidate set (k ambulancias, h destinos)
    ↓
Asignación global: elegir grupos de ambulancias y destino
    ↓
Simulación lógica + evaluación de cinco escenarios
    ↓
Mapa HTML interactivo con despacho manual y fases por tiempo
```

Hay dos "mundos" que conviene no confundir:

| Mundo | Dónde | Qué hace |
| --- | --- | --- |
| **Modelo Python / CLI** | módulos `ambulancias_pergamino/*.py` | Construye el grafo, calcula rutas, genera alternativas, reduce candidatos, resuelve la asignación global, simula por etapas lógicas y evalúa. |
| **Mapa del navegador** | `ambulancias_pergamino/mapa.py` genera `data/mapa_pergamino.html` | Permite elegir manualmente una alternativa, despachar unidades, ver fases por tiempo, liberarlas y agregar urgencias nuevas. |

El mapa **no vuelve a resolver** la asignación global: toma los datos exportados
y opera sobre ellos. Para las urgencias creadas dentro del navegador sí calcula
rutas locales con la misma idea que Python.

---

## 2. Datos de entrada

### 2.1 Calles

El callejero se descarga por WFS desde GeoNode y se filtra con:

```text
localidad = 'Pergamino'
transitable = 'si'
```

Cada tramo tiene:

- `id` o `tramo_id`: identificador del tramo;
- `nombre_completo` o `nombre`: nombre de la calle;
- `sentido`: dirección permitida;
- una geometría `LineString` o `MultiLineString`.

### 2.2 Sentido de las calles

`sentido` se interpreta así:

| Valor | Aristas creadas |
| --- | --- |
| `0` | ida y vuelta |
| `1` | sentido de digitalización de la geometría |
| `-1` | sentido inverso a la digitalización |
| vacío o desconocido | ida y vuelta, con aviso |

Esto produce un **grafo dirigido**: una calle de mano única no se puede recorrer
en sentido prohibido.

### 2.3 Bases y ambulancias

`config/ambulancias.json` define la flota. Cada ambulancia tiene:

- `id`, `nombre`, `base_id`;
- `disponible`, `reserva`;
- `complejidad`, `capacidad_pacientes`, `equipamiento`.

La base determina el nodo inicial de la ambulancia. En los datos actuales hay
cinco unidades Clase C, complejidad 3 y capacidad 1; `A3` es de reserva.

La ambulancia de reserva solo puede atender emergencias de **gravedad 3**. En
gravedad 1 o 2 se descarta con el motivo
`ambulancia_de_reserva_solo_gravedad_3`.

### 2.4 Emergencias

`config/emergencias.json` define cada urgencia con:

- coordenadas;
- `gravedad` y `complejidad_requerida` (escala 1 a 3, dimensiones independientes);
- `cantidad_pacientes`;
- `equipamiento_requerido`;
- `minutos_espera`;
- `estado` y `datos_simulados`.

Toda emergencia debe caer dentro del bounding box del grafo y se asocia al nodo
vial más cercano.

### 2.5 Establecimientos de destino

`config/establecimientos.json` define hospitales y clínicas con:

- `habilitado_destino`;
- `prioridad`;
- `penalizacion_metros`;
- `complejidad_maxima`;
- `base_id`.

Con los datos actuales:

| Destino | Estado | Prioridad | Penalización |
| --- | --- | --- | --- |
| `GUARDIA-1` Hospital Interzonal San José | habilitado | 1 | 0 m |
| `GUARDIA-2` Clínica Pergamino | habilitado | 2 | 1000 m |
| `GUARDIA-3` Clínica Centro | inactivo | 2 | 1000 m |
| `GUARDIA-4` Clínica General Paz | inactivo | 2 | 1000 m |

`SAME` y `Medicar` son bases: pueden originar ambulancias, pero no reciben
pacientes.

La **prioridad** se valida y se muestra, pero no entra en la fórmula de costo.
La decisión entre destinos usa distancia más penalización. La penalización es
una preferencia simulada, no un obstáculo ni un cambio de ruta.

---

## 3. Cómo se eligen los caminos

Esta es la parte central. El sistema no "traza una línea recta": calcula el
**camino mínimo sobre el grafo vial dirigido**.

### 3.1 Nodos

Un nodo se identifica con la cadena `"longitud,latitud"` redondeada a 7
decimales. Dos coordenadas iguales a esa precisión se fusionan en el mismo nodo.

Las bases, emergencias y establecimientos se vinculan al nodo más cercano mediante
una búsqueda lineal sobre todos los nodos con distancia Haversine. Es **el nodo
más cercano**, no la proyección sobre una calle.

La distancia entre el punto original y su nodo se guarda como dato
(`distancia_al_nodo_m`), pero **no se suma** a las rutas viales para evitar
contar dos veces ese acercamiento.

### 3.2 Pesos de las aristas

Cada arista vale la distancia georreferenciada entre sus dos vértices, calculada
con Haversine y redondeada a 3 decimales:

```text
radio terrestre = 6.371.008,8 m
peso_arista = distancia_haversine(vértice_actual, vértice_siguiente)
```

No hay tráfico, velocidades por calle, semáforos ni restricciones horarias en el
grafo. Solo distancia y sentido.

### 3.3 Dijkstra

`ambulancias_pergamino/grafo.py` implementa Dijkstra con una cola de prioridad:

```text
heap de (distancia_acumulada, id_nodo)
```

- Se descartan entradas viejas de la cola.
- Se relaja una arista solo si mejora estrictamente: `nueva < mejor_actual`.
- Si hay dos caminos de igual distancia, se conserva el primer predecessor
  encontrado; no se reemplaza por el otro.
- El destino alcanzado se devuelve como `(distancia_m, [nodos...])`.
- Si no hay camino, se devuelve `(inf, [])`.

En el mapa del navegador existe una implementación equivalente para las
urgencias agregadas en vivo. La lógica es la misma: grafo dirigido, pesos en
metros y distancia mínima.

### 3.4 Qué rutas se calculan

Para cada alternativa completa se necesitan dos tramos:

```text
A) base de la ambulancia → nodo de la emergencia
B) nodo de la emergencia → nodo del establecimiento
```

Ejemplo con `A1`, `E1` y Hospital San José:

```text
A1 (base SAME) ──Dijkstra──▶ E1 ──Dijkstra──▶ GUARDIA-1
     d1                         d2
```

Se calculan primero todas las rutas `ambulancia → emergencia` y todas las rutas
`emergencia → establecimiento`, y luego se reutilizan. El caché se indexa por el
par de nodos `(origen, destino)`, no por el nombre de la ambulancia.

Con los datos actuales:

```text
5 ambulancias × 5 emergencias × 4 destinos = 100 alternativas
25 rutas únicas ambulancia → emergencia
20 rutas únicas emergencia → establecimiento
30 ejecuciones únicas de Dijkstra
```

Las 30 ejecuciones únicas son menos que 45 porque varias ambulancias comparten
base: `A1`, `A2` y `A3` salen del mismo nodo SAME, y `A4`, `A5` salen del mismo
nodo Medicar.

### 3.5 Distancia, penalización y costo

Para una alternativa:

```text
distancia_total_m = d1 + d2

costo_seleccion = distancia_total_m + penalizacion_establecimiento_m
```

Si falta alguno de los dos tramos, la alternativa no tiene distancia total y se
descarta por `sin_ruta_hasta_emergencia` o `sin_ruta_hasta_establecimiento`.

La penalización **no modifica el grafo ni la trayectoria**. Solo cambia el costo
con el que se compara un destino frente a otro. El Hospital San José suma 0; la
Clínica Pergamino suma 1000 m.

### 3.6 Regreso a la base en el mapa

La optimización Python termina cuando el paciente llega al destino: no modela el
regreso ni la reutilización de la unidad.

El mapa sí agrega un tercer tramo para estimar disponibilidad:

```text
base del establecimiento → base de la ambulancia
```

también con Dijkstra sobre el mismo grafo dirigido. Ese tramo se usa solo para el
reloj y para la fase `Regresando a la base`; no cambia la ruta elegida ni el
costo de la alternativa.

---

## 4. Alternativas

Una alternativa es la combinación completa:

```text
ambulancia → emergencia → establecimiento
```

Guarda:

- ambos tramos con sus nodos y distancias;
- `distancia_total_m`;
- `penalizacion_establecimiento_m`;
- `costo_seleccion`;
- `pacientes_asignados`, `capacidad_pacientes`;
- `motivos_descarte`;
- `es_factible`.

### 4.1 Filtros de factibilidad

Una alternativa es factible si no tiene motivos de descarte. Los motivos son:

| Motivo | Cuándo aparece |
| --- | --- |
| `ambulancia_no_disponible` | La unidad está marcada como no disponible. |
| `ambulancia_de_reserva_solo_gravedad_3` | Se intenta usar la reserva en gravedad 1 o 2. |
| `complejidad_ambulancia_insuficiente` | La ambulancia no cubre la complejidad requerida. |
| `equipamiento_faltante` | Falta algún elemento exigido por la emergencia. |
| `sin_ruta_hasta_emergencia` | No hay camino desde la base hasta la urgencia. |
| `establecimiento_no_habilitado` | El destino está inactivo. |
| `complejidad_establecimiento_insuficiente` | El destino no puede atender esa complejidad. |
| `sin_ruta_hasta_establecimiento` | No hay camino desde la urgencia hasta el destino. |

Con los datos actuales se generan 100 alternativas: 44 factibles y 56
descartadas.

---

## 5. Reducción heurística

La asignación exacta sobre las 44 alternativas factibles es viable, pero el
proyecto también estudia cómo reducir el espacio de búsqueda.

Para cada emergencia se conservan:

- las `k` ambulancias compatibles más cercanas;
- los `h` destinos compatibles con menor
  `distancia(emergencia, destino) + penalización`.

Niveles:

| Nivel | k | h |
| --- | --- | --- |
| 1 | 3 | 2 |
| 2 | 4 | 3 |
| 3 | 5 | 4 |
| 4 | 6 | 4 |

Las alternativas excluidas conservan el motivo, por ejemplo
`fuera_de_las_k_mas_cercanas` o `fuera_de_los_h_mas_convenientes`. La reducción
no reasigna recursos ni modifica las alternativas originales.

El orden de prioridad de emergencias es:

```text
gravedad descendente
→ menor cantidad de ambulancias compatibles
→ minutos de espera descendente
→ id de emergencia
```

Cuando una urgencia pide más de una unidad o más de un paciente, el nivel se
amplía automáticamente para considerar todas las ambulancias compatibles.

---

## 6. Asignación global

La asignación responde: para cada urgencia, qué grupo de ambulancias se usa y a
qué establecimiento se traslada.

Restricciones:

- cada ambulancia se usa como máximo una vez;
- cada emergencia aparece como máximo una vez;
- el grupo debe tener al menos `ambulancias_requeridas` unidades;
- la suma de capacidades debe cubrir `cantidad_pacientes`;
- se evitan grupos redundantes que no mejoran la cobertura.

Para cada par `(emergencia, ambulancia)` se conserva solo la alternativa
factible de menor costo. Como no se modela capacidad compartida de hospitales,
esa dominancia es válida en este modelo.

El objetivo es lexicográfico:

1. maximizar la cantidad de emergencias atendidas;
2. maximizar el vector de prioridad según el orden de la sección anterior;
3. minimizar el costo total;
4. desempatar por identificadores menores.

El algoritmo es backtracking determinista con podas. Las urgencias sin
asignación conservan motivos como `sin_alternativas_factibles`,
`ambulancias_candidatas_ya_utilizadas` o `sin_combinacion_compatible`.

Existe un parámetro de backend `hospital_disponible`: si es `True`, se prefieren
alternativas con `GUARDIA-1`; si es `False`, se usan las demás. El mapa **no
expone** ese control: el destino lo elige el operador entre los habilitados.

---

## 7. Simulación lógica (Python)

La simulación de la CLI no usa tiempos reales. Recorre cinco etapas lógicas:

| Paso | Etapa | Ambulancia | Significado |
| --- | --- | --- | --- |
| 0 | `asignada` | `asignada` | Ya se eligieron unidad y destino. |
| 1 | `en_camino` | `en_camino` | Viaja hacia la emergencia. |
| 2 | `en_atencion` | `en_atencion` | Está en el lugar. |
| 3 | `trasladando` | `trasladando` | Va al establecimiento con el paciente. |
| 4 | `finalizada` | `finalizada` | Atención y traslado completados. |

La simulación **reutiliza** las rutas ya calculadas: no vuelve a correr Dijkstra
y verifica que distancias y costos coincidan con la asignación.

No modela regreso a la base ni reutilización de unidades. Esas dos cosas sí
aparecen en el mapa.

---

## 8. Evaluación

`evaluar-escenarios` compara cinco escenarios: original y niveles 1 a 4.
Calcula:

- alternativas generadas, factibles, conservadas y evaluadas;
- porcentaje de reducción;
- urgencias atendidas y sin asignar;
- ambulancias y destinos usados;
- costos, distancias y penalizaciones;
- diferencias contra el original;
- estados finales;
- nivel recomendado y pérdida por heurística.

Los valores se obtienen de las asignaciones y simulaciones; no son constantes.

---

## 9. Mapa interactivo

El HTML se genera con:

```powershell
py -3 -m ambulancias_pergamino exportar-mapa
```

y se abre con `.\abrir-mapa.cmd`. El archivo `data/mapa_pergamino.html` es
generado y no se versiona.

### 9.1 Qué se ve

- carreteras, bases, ambulancias, destinos, urgencias y rutas;
- tres selectores: ambulancia, urgencia y establecimiento;
- distancias de ambos tramos, penalización, costo, factibilidad y motivos;
- botón **Poner ambulancia en uso**, habilitado solo para alternativas factibles;
- panel **Liberación de ambulancias**;
- panel **Urgencias y grados**;
- panel **Urgencias atendidas**.

Los paneles de heurísticas, asignación, simulación y evaluación ya no se
muestran en el mapa, aunque sus datos siguen exportados.

### 9.2 Despacho manual

Al elegir una combinación factible y pulsar **Poner ambulancia en uso**:

1. la alternativa se guarda en `despachos`, claveada por ambulancia;
2. se registra `inicioEn`, `liberacionEn`, tiempos y pacientes;
3. cada unidad traslada como máximo un paciente pendiente;
4. las unidades adicionales quedan como apoyo sin pacientes;
5. la ambulancia usada sale del selector;
6. la urgencia sigue seleccionable mientras falte cobertura;
7. se limpia el destino anterior y se redibuja el visor.

La cobertura se considera completa cuando:

```text
unidades asignadas ≥ ambulancias_requeridas
pacientes trasladados ≥ cantidad_pacientes
```

### 9.3 Fases del viaje

El mapa usa tiempo real simulado con dos supuestos:

```text
velocidad = 40 km/h
atención en escena = 10 minutos
```

El tiempo hasta quedar disponible es:

```text
(recorrido_asignado_m + regreso_a_la_base_m) / 1000 / 40 * 60 + 10
```

Con esos mismos cálculos se muestran cuatro fases:

| Fase | Cuándo se muestra |
| --- | --- |
| `En camino al accidente` | Antes de llegar al nodo de la urgencia. |
| `En escena` | Los 10 minutos fijos de atención en el lugar. |
| `Camino al hospital` | Desde que se deja la escena hasta llegar al destino. |
| `Regresando a la base` | Desde el destino hasta la base de la ambulancia. |

El reloj se actualiza cada segundo. Al vencerse, la unidad se libera sola. El
botón **Finalizar esta unidad** permite adelantar ese momento.

### 9.4 Urgencias atendidas

Una urgencia pasa al cuadro **Urgencias atendidas** solo cuando:

- no queda ninguna unidad activa en esa urgencia;
- hay al menos un registro de atención finalizada;
- la cobertura está completa.

En ese momento su marcador desaparece del mapa. Si la cobertura es parcial, la
urgencia permanece en el listado de pendientes para permitir refuerzos.

### 9.5 Urgencias creadas en el navegador

El formulario permite crear urgencias indicando:

- cantidad de pacientes;
- mínimo de ambulancias;
- ID;
- grado 1 a 3;
- calle y número, o ubicación elegida haciendo clic en el mapa.

La dirección se busca en el índice de direcciones exportado. La ubicación
elegida se conecta al nodo vial más cercano. La complejidad requerida se toma como
`min(gravedad, 2)` y en el navegador se calculan las rutas y la factibilidad con
la misma lógica del backend.

El estado del mapa vive solo en la pestaña: recargar la página reinicia los
despachos y quita las urgencias agregadas.

---

## 10. Comandos principales

Se invocan como `py -3 -m ambulancias_pergamino <comando>` en Windows, o
`python -m ambulancias_pergamino <comando>` donde `python` apunte a Python 3.11+.

```text
construir                    Descarga el callejero, construye el grafo y guarda data/pergamino.json.
construir-direcciones        Genera solo el índice de direcciones.
verificar-rutas              Prueba caminos mínimos entre todas las bases.
listar-ambulancias           Muestra la flota configurada.
listar-establecimientos      Muestra destinos, prioridades y penalizaciones.
listar-emergencias           Muestra las urgencias configuradas.
verificar-emergencias        Informa alcance y advertencias por urgencia.
resumir-alternativas         Resumen de generadas, factibles y rutas reutilizadas.
listar-alternativas          Detalle por emergencia.
resumir-heuristicas          Resumen de reducción por nivel.
listar-candidatos            Ambulancias y destinos conservados o excluidos.
listar-alternativas-reducidas Alternativas que sobreviven al filtro.
resumir-asignacion           Resumen de la asignación global.
listar-asignacion            Tabla detallada de la asignación.
comparar-asignaciones        Compara original contra niveles 1 a 4.
iniciar-simulacion           Estado lógico inicial.
resumir-simulacion           Resumen por etapa.
listar-simulacion            Detalle por atención.
avanzar-simulacion           Avanza etapas o hasta el final.
ver-simulacion               Inspecta una emergencia o ambulancia.
evaluar-escenarios           Tabla final de métricas y recomendación.
exportar-mapa                Genera data/mapa_pergamino.html.
```

Ayuda completa:

```powershell
py -3 -m ambulancias_pergamino --help
```

---

## 11. Pruebas

```powershell
py -3 -m unittest discover -v
```

La suite cubre grafo, modelos, alternativas, heurísticas, asignación,
simulación, evaluación, CLI y mapa. Las pruebas de JavaScript del mapa requieren
Node.js; el resto usa solo la biblioteca estándar de Python.

En Windows conviene usar `py -3` porque el alias `python` puede corresponder al
Microsoft Store.

---

## 12. Supuestos y límites

- El callejero se filtra por `localidad = 'Pergamino'` y `transitable = 'si'`.
- No hay tráfico, velocidades variables ni restricciones horarias.
- Los puntos se conectan al nodo más cercano, no al tramo más cercano.
- La penalización de destino no cambia la trayectoria; solo el costo.
- No se modela capacidad compartida de hospitales.
- La simulación Python es lógica; el mapa es el único lugar con tiempos y fases.
- El mapa supone 40 km/h y 10 minutos de atención.
- El estado del mapa no se comparte ni persiste entre recargas.
- Los datos son simulados y el proyecto no debe usarse para despacho real.

---

## 13. Mapa rápido de código

| Archivo | Responsabilidad principal |
| --- | --- |
| `ambulancias_pergamino/geonode.py` | Descarga capas WFS. |
| `ambulancias_pergamino/grafo.py` | Grafo dirigido, pesos, Dijkstra, `nodo_mas_cercano`. |
| `ambulancias_pergamino/datos.py` | Bases y preparación general de datos. |
| `ambulancias_pergamino/ambulancias.py` | Carga y validación de la flota. |
| `ambulancias_pergamino/emergencias.py` | Carga y validación de urgencias. |
| `ambulancias_pergamino/establecimientos.py` | Destinos, prioridades y penalizaciones. |
| `ambulancias_pergamino/alternativas.py` | Caché de rutas y construcción de alternativas. |
| `ambulancias_pergamino/heuristicas.py` | Reducción `k`/`h` y orden de prioridad. |
| `ambulancias_pergamino/asignacion.py` | Asignación global y comparación de niveles. |
| `ambulancias_pergamino/simulacion.py` | Etapas lógicas 0 a 4. |
| `ambulancias_pergamino/evaluacion.py` | Métricas de los cinco escenarios. |
| `ambulancias_pergamino/mapa.py` | HTML, Dijkstra en navegador, despacho manual y fases. |
| `ambulancias_pergamino/cli.py` | Comandos y salidas por terminal. |
| `docs/PRUEBAS-asignacion-multiple.md` | Pruebas manuales del despacho múltiple. |
