# Asignación de varias ambulancias en el mapa

## Uso

Ejecutar ` .\abrir-mapa.cmd` desde el proyecto. El lanzador regenera el HTML.

El operador elige la ambulancia, la urgencia y el establecimiento de destino entre
los habilitados. No hay un control de disponibilidad del hospital: la elección del
destino es libre dentro de las alternativas factibles.

Al agregar una urgencia se informa la cantidad de pacientes y el mínimo de ambulancias.
Todos los campos del formulario comparten el mismo formato, incluido el ID de urgencia.
Cada despacho traslada automáticamente un paciente pendiente, siempre que la unidad
tenga capacidad para él. Las unidades adicionales quedan como apoyo sin pacientes.

Una urgencia permanece seleccionable para incorporar refuerzos. Cada unidad tiene
su botón «Finalizar esta unidad» y su reloj de liberación independientes. La cobertura
es parcial mientras falten pacientes por distribuir o unidades para alcanzar el mínimo.
El panel muestra la fase calculada con las distancias de la trayectoria a 40 km/h:
«En camino al accidente», «En escena» (10 minutos), «Camino al hospital» y
«Regresando a la base» hasta la liberación automática.
Solo pasa al cuadro «Urgencias atendidas» cuando se cumple la cobertura y finalizaron
todas las unidades; en ese momento su marcador desaparece del mapa.
La reserva conserva la restricción de gravedad 3; no significa uso exclusivo cuando
las otras unidades estén ocupadas.

El estado operativo del mapa vive en la pestaña: recargar reinicia los despachos y
las urgencias agregadas. No hay almacenamiento compartido entre operadores.

## Cálculo automático

`ambulancias_requeridas` es opcional en `config/emergencias.json`, con valor inicial 1.
El optimizador selecciona grupos que cumplan ese mínimo y la capacidad total de pacientes,
sin compartir unidades entre emergencias. Conserva el criterio: maximizar emergencias
completamente cubiertas, luego prioridad y después minimizar costo. Si no alcanza la flota,
deja la emergencia sin asignación; el operador puede realizar un despacho parcial en el mapa.
Se amplía el conjunto de ambulancias candidatas ante demandas múltiples.

## Pruebas automáticas

Requieren Python y Node.js (para ejecutar la lógica JavaScript y comprobar su sintaxis).

```powershell
python -m unittest discover -v
python -m ambulancias_pergamino exportar-mapa
```

## Pruebas manuales

1. Agregar U1 con gravedad 2, dos pacientes y una ambulancia mínima, eligiendo una ubicación.
2. Despachar una unidad al hospital: debe trasladar un paciente y U1 debe seguir seleccionable.
3. Despachar otra unidad disponible a una clínica habilitada: traslada el segundo paciente,
   ambas deben aparecer en uso y U1 completa.
4. Intentar asignar una unidad ocupada a otra urgencia: no debe estar disponible.
5. Finalizar una unidad: la otra sigue ocupada y U1 no aparece como atendida.
6. Finalizar la segunda: U1 pasa al cuadro «Urgencias atendidas», su marcador desaparece
   del mapa y ambas unidades vuelven a estar disponibles.
7. Agregar una urgencia de un paciente y dos unidades mínimas. Despachar una unidad, que toma
   el paciente, y otra, que queda como apoyo sin pacientes. Comprobar cobertura y liberaciones.
8. Comprobar que el destino lo elige el operador: hospital y clínicas habilitadas deben ser
   seleccionables sin cambiar ningún control de disponibilidad.
9. Intentar despachar la reserva a gravedad 1 y 2: debe rechazarse. En gravedad 3 debe
   admitirse si cumple las demás restricciones.
10. Mantener dos unidades activas y comprobar que cada reloj libera solamente su servicio.
11. Intentar quitar una urgencia agregada mientras tenga alguna unidad en uso: debe impedirse.
    Tras finalizar todas las unidades, debe poder quitarse.

El destino del mapa depende únicamente de la elección del operador entre los
establecimientos habilitados.
