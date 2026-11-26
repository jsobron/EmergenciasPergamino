# Asignación de varias ambulancias y disponibilidad del hospital

## Uso

Ejecutar ` .\abrir-mapa.cmd` desde el proyecto. El lanzador regenera el HTML.

El operador selecciona «Hospital con lugar» o «Hospital sin lugar: habilitar clínicas».
La primera opción permite nuevos despachos solamente al Hospital San José; la
segunda permite solamente clínicas habilitadas y compatibles con la complejidad.
Cambiarla conserva los servicios ya iniciados. No se descuentan camas automáticamente.

Al agregar una urgencia se informa la cantidad de pacientes y el mínimo de ambulancias.
En cada despacho se indica cuántos pacientes trasladará esa unidad. Se permite cero
para una unidad de apoyo. La cantidad no puede superar su capacidad ni los pacientes
que todavía no tienen transporte asignado.

Una urgencia permanece seleccionable para incorporar refuerzos. Cada unidad tiene
su botón «Finalizar esta unidad» y su reloj de liberación independientes. La cobertura
es parcial mientras falten pacientes por distribuir o unidades para alcanzar el mínimo.
Solo se muestra atendida cuando se cumple la cobertura y finalizaron todas las unidades.
La reserva conserva la restricción de gravedad 3; no significa uso exclusivo cuando
las otras unidades estén ocupadas.

El estado operativo del mapa vive en la pestaña: recargar reinicia los despachos y la
disponibilidad indicada. No hay almacenamiento compartido entre operadores.

## Cálculo automático

`ambulancias_requeridas` es opcional en `config/emergencias.json`, con valor inicial 1.
El optimizador selecciona grupos que cumplan ese mínimo y la capacidad total de pacientes,
sin compartir unidades entre emergencias. Conserva el criterio: maximizar emergencias
completamente cubiertas, luego prioridad y después minimizar costo. Si no alcanza la flota,
deja la emergencia sin asignación; el operador puede realizar un despacho parcial en el mapa.
Se amplía el conjunto de ambulancias candidatas ante demandas múltiples.

Las funciones Python `asignar_original`, `asignar_con_nivel` y `asignar_global` aceptan
`hospital_disponible=False`. Por defecto consideran que tiene lugar. El control del mapa
afecta el despacho manual de esa pestaña, no vuelve a ejecutar los informes CLI.

## Pruebas automáticas

Requieren Python y Node.js (para ejecutar la lógica JavaScript y comprobar su sintaxis).

```powershell
python -m unittest discover -v
python -m ambulancias_pergamino exportar-mapa
```

## Pruebas manuales

1. Agregar U1 con gravedad 2, dos pacientes y dos ambulancias mínimas, eligiendo una ubicación.
2. Con hospital con lugar, intentar un despacho a una clínica: debe rechazarse. Despachar
   una unidad al hospital con un paciente: U1 debe mostrar cobertura parcial.
3. Despachar otra unidad disponible a U1 con un paciente: ambas deben aparecer en uso.
4. Intentar asignar una unidad ocupada a otra urgencia: no debe estar disponible.
5. Finalizar una unidad: la otra sigue ocupada y U1 no aparece como atendida.
6. Finalizar la segunda: U1 aparece atendida y ambas unidades vuelven a estar disponibles.
7. Agregar una urgencia de un paciente y dos unidades mínimas. Asignar una con un paciente
   y otra con cero pacientes de apoyo. Comprobar la cobertura y las liberaciones independientes.
8. Intentar cantidades negativas, decimales, superiores a la capacidad y superiores a los
   pacientes pendientes: deben rechazarse.
9. Cambiar a hospital sin lugar: el hospital debe rechazar nuevos despachos y una clínica
   habilitada debe permitirlos cuando la complejidad sea compatible. Los despachos anteriores
   deben conservarse. Cambiar nuevamente a con lugar y comprobar la regla inversa.
10. Intentar despachar la reserva a gravedad 1 y 2: debe rechazarse. En gravedad 3 debe
    admitirse si cumple las demás restricciones.
11. Mantener dos unidades activas y comprobar que cada reloj libera solamente su servicio.
12. Intentar quitar una urgencia agregada mientras tenga alguna unidad en uso: debe impedirse.
    Tras finalizar todas las unidades, debe poder quitarse.

Los costos de los escenarios anteriores cambian porque las clínicas dejaron de competir
por distancia cuando el hospital tiene lugar. Los tests existentes reflejan esa regla.
