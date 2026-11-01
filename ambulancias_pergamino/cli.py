from __future__ import annotations

import argparse
import json
from itertools import permutations
from math import isinf
from pathlib import Path

from .datos import construir_bases
from .ambulancias import Ambulancia, cargar_ambulancias
from .alternativas import Alternativa, ResultadoAlternativas, construir_alternativas
from .asignacion import (
    ComparacionAsignaciones,
    ResultadoAsignacion,
    asignar_con_nivel,
    asignar_original,
    comparar_niveles,
)
from .establecimientos import Establecimiento, cargar_establecimientos
from .emergencias import Emergencia, analizar_conectividad, cargar_emergencias
from .evaluacion import EvaluacionEscenarios, evaluar_escenarios as calcular_evaluacion
from .geonode import descargar_geojson
from .grafo import Grafo, construir_grafo
from .heuristicas import (
    ParametrosCandidatos,
    ResultadoReduccion,
    reducir_alternativas,
)
from .mapa import exportar_mapa
from .simulacion import (
    ETAPAS_SIMULACION,
    PASO_FINAL,
    ResultadoSimulacion,
    Simulacion,
    crear_simulacion,
)


FILTRO_CALLEJERO = "localidad='Pergamino' AND transitable='si'"


def construir(salida: Path) -> None:
    print("Descargando callejero de Pergamino...")
    callejero = descargar_geojson("geonode:callejero", filtro_cql=FILTRO_CALLEJERO)
    print(f"Tramos recibidos: {len(callejero.get('features', []))}")

    grafo, advertencias = construir_grafo(callejero)
    print(
        f"Grafo construido: {len(grafo.nodos)} nodos y "
        f"{sum(map(len, grafo.adyacencia.values()))} aristas"
    )

    print("Descargando guardias medicas...")
    guardias = descargar_geojson("geonode:guardias_medicas")
    bases = construir_bases(guardias, grafo)

    resultado = {
        "fuente": {
            "wfs": "https://geonode.pergamino.gob.ar/geoserver/ows",
            "filtro_callejero": FILTRO_CALLEJERO,
        },
        "resumen": {
            "tramos": len(callejero.get("features", [])),
            "nodos": len(grafo.nodos),
            "aristas": sum(map(len, grafo.adyacencia.values())),
            "bases": len(bases),
            "advertencias": len(advertencias),
        },
        "advertencias": advertencias,
        "grafo": grafo.serializar(),
        "bases_ambulancias": bases,
    }
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(resultado, ensure_ascii=False), encoding="utf-8")
    print(f"Datos guardados en {salida}")
    for base in bases:
        print(
            f"- {base['nombre']}: nodo {base['nodo_id']} "
            f"({base['distancia_al_grafo_metros']} m del grafo)"
        )


def verificar_rutas(entrada: Path) -> None:
    datos = json.loads(entrada.read_text(encoding="utf-8"))
    grafo = Grafo.deserializar(datos["grafo"])
    bases = datos["bases_ambulancias"]
    fallas = 0
    for origen, destino in permutations(bases, 2):
        distancia, camino = grafo.camino_minimo(origen["nodo_id"], destino["nodo_id"])
        if isinf(distancia):
            fallas += 1
            print(f"SIN RUTA: {origen['nombre']} -> {destino['nombre']}")
        else:
            print(
                f"{origen['nombre']} -> {destino['nombre']}: "
                f"{distancia:.0f} m, {len(camino)} nodos"
            )
    if fallas:
        raise SystemExit(f"Se encontraron {fallas} pares sin ruta")


def listar_ambulancias(entrada: Path, configuracion: Path) -> None:
    datos = json.loads(entrada.read_text(encoding="utf-8"))
    bases = datos["bases_ambulancias"]
    bases_por_id = {base["id"]: base for base in bases}
    ambulancias = cargar_ambulancias(configuracion, bases)
    filas = [
        (
            ambulancia.id,
            bases_por_id[ambulancia.base_id]["nombre"],
            ambulancia.nodo_id,
            "sí" if ambulancia.disponible else "no",
            str(ambulancia.complejidad),
            str(ambulancia.capacidad_pacientes),
        )
        for ambulancia in ambulancias
    ]
    encabezados = ("ID", "Base", "Nodo", "Disponible", "Complejidad", "Capacidad")
    anchos = [max(len(encabezados[i]), *(len(fila[i]) for fila in filas)) for i in range(6)]
    formato = "  ".join(f"{{:<{ancho}}}" for ancho in anchos)
    print("Datos simulados: sí")
    print(formato.format(*encabezados))
    print(formato.format(*(guion * ancho for guion, ancho in zip("------", anchos))))
    for fila in filas:
        print(formato.format(*fila))


def listar_establecimientos(entrada: Path, configuracion: Path) -> None:
    datos = json.loads(entrada.read_text(encoding="utf-8"))
    establecimientos = cargar_establecimientos(
        configuracion, datos["bases_ambulancias"]
    )
    filas = [
        (
            establecimiento.id,
            establecimiento.nombre,
            establecimiento.base_id,
            establecimiento.nodo_id,
            "sí" if establecimiento.habilitado_destino else "no",
            str(establecimiento.prioridad),
            f"{establecimiento.penalizacion_metros:g} m",
            str(establecimiento.complejidad_maxima),
            "sí" if establecimiento.datos_simulados else "no",
        )
        for establecimiento in establecimientos
    ]
    encabezados = (
        "ID",
        "Nombre",
        "Base",
        "Nodo",
        "Destino",
        "Prioridad",
        "Penalización",
        "Complejidad",
        "Simulado",
    )
    anchos = [
        max(len(encabezados[i]), *(len(fila[i]) for fila in filas))
        for i in range(len(encabezados))
    ]
    formato = "  ".join(f"{{:<{ancho}}}" for ancho in anchos)
    print(formato.format(*encabezados))
    print(formato.format(*("-" * ancho for ancho in anchos)))
    for fila in filas:
        print(formato.format(*fila))


def listar_emergencias(entrada: Path, configuracion: Path) -> None:
    datos = json.loads(entrada.read_text(encoding="utf-8"))
    grafo = Grafo.deserializar(datos["grafo"])
    emergencias = cargar_emergencias(configuracion, grafo)
    filas = [
        (
            emergencia.id,
            str(emergencia.gravedad),
            str(emergencia.complejidad_requerida),
            str(emergencia.cantidad_pacientes),
            f"{emergencia.minutos_espera:g}",
            emergencia.estado,
            f"{emergencia.latitud:.7f}",
            f"{emergencia.longitud:.7f}",
            emergencia.nodo_id,
            f"{emergencia.distancia_al_nodo_m:.1f} m",
            "sí" if emergencia.datos_simulados else "no",
        )
        for emergencia in emergencias
    ]
    encabezados = (
        "ID", "Gravedad", "Complejidad", "Pacientes", "Espera (min)",
        "Estado", "Latitud", "Longitud", "Nodo", "Distancia", "Simulado",
    )
    anchos = [
        max(len(encabezados[i]), *(len(fila[i]) for fila in filas))
        for i in range(len(encabezados))
    ]
    formato = "  ".join(f"{{:<{ancho}}}" for ancho in anchos)
    print(formato.format(*encabezados))
    print(formato.format(*(guion * ancho for guion, ancho in zip("-" * len(anchos), anchos))))
    for fila in filas:
        print(formato.format(*fila))


def verificar_emergencias(
    entrada: Path, configuracion: Path, configuracion_establecimientos: Path
) -> None:
    datos = json.loads(entrada.read_text(encoding="utf-8"))
    grafo = Grafo.deserializar(datos["grafo"])
    bases = datos["bases_ambulancias"]
    emergencias = cargar_emergencias(configuracion, grafo)
    establecimientos = cargar_establecimientos(
        configuracion_establecimientos, bases
    )
    informes = analizar_conectividad(emergencias, bases, establecimientos, grafo)
    for informe in informes:
        print(f"{informe.emergencia_id}:")
        print(
            f"  Bases alcanzables ({len(informe.bases_alcanzables)}): "
            + ", ".join(informe.bases_alcanzables)
        )
        print(
            f"  Destinos alcanzables ({len(informe.establecimientos_alcanzables)}): "
            + ", ".join(informe.establecimientos_alcanzables)
        )
        for advertencia in informe.advertencias:
            print(f"  ADVERTENCIA: {advertencia}")


def _cargar_modelo(
    entrada: Path, configuracion_ambulancias: Path,
    configuracion_emergencias: Path, configuracion_establecimientos: Path,
) -> tuple[
    ResultadoAlternativas,
    list[Ambulancia],
    list[Emergencia],
    list[Establecimiento],
]:
    datos = json.loads(entrada.read_text(encoding="utf-8"))
    grafo = Grafo.deserializar(datos["grafo"])
    bases = datos["bases_ambulancias"]
    ambulancias = cargar_ambulancias(configuracion_ambulancias, bases)
    emergencias = cargar_emergencias(configuracion_emergencias, grafo)
    establecimientos = cargar_establecimientos(configuracion_establecimientos, bases)
    resultado = construir_alternativas(
        ambulancias, emergencias, establecimientos, grafo
    )
    return resultado, ambulancias, emergencias, establecimientos


def _cargar_alternativas(
    entrada: Path, configuracion_ambulancias: Path,
    configuracion_emergencias: Path, configuracion_establecimientos: Path,
) -> tuple[ResultadoAlternativas, int, int, int]:
    resultado, ambulancias, emergencias, establecimientos = _cargar_modelo(
        entrada, configuracion_ambulancias,
        configuracion_emergencias, configuracion_establecimientos,
    )
    return resultado, len(ambulancias), len(emergencias), len(establecimientos)


def _cargar_reduccion(
    entrada: Path, configuracion_ambulancias: Path,
    configuracion_emergencias: Path, configuracion_establecimientos: Path,
    nivel: int = 1,
) -> tuple[ResultadoReduccion, int, int, int]:
    parametros = ParametrosCandidatos.desde_nivel(nivel)
    resultado, ambulancias, emergencias, establecimientos = _cargar_modelo(
        entrada, configuracion_ambulancias,
        configuracion_emergencias, configuracion_establecimientos,
    )
    reduccion = reducir_alternativas(
        resultado, ambulancias, emergencias, establecimientos, parametros
    )
    return reduccion, len(ambulancias), len(emergencias), len(establecimientos)


def resumir_alternativas(
    entrada: Path, configuracion_ambulancias: Path,
    configuracion_emergencias: Path, configuracion_establecimientos: Path,
) -> None:
    resultado, cantidad_ambulancias, cantidad_emergencias, cantidad_destinos = (
        _cargar_alternativas(
            entrada, configuracion_ambulancias,
            configuracion_emergencias, configuracion_establecimientos,
        )
    )
    factibles = sum(a.es_factible for a in resultado.alternativas)
    print(f"Ambulancias: {cantidad_ambulancias}")
    print(f"Emergencias: {cantidad_emergencias}")
    print(f"Destinos: {cantidad_destinos}")
    print(f"Alternativas generadas: {len(resultado.alternativas)}")
    print(f"Alternativas factibles: {factibles}")
    print(f"Alternativas no factibles: {len(resultado.alternativas) - factibles}")
    print(
        "Rutas únicas calculadas/reutilizadas: "
        f"{resultado.rutas_unicas_calculadas}"
    )
    print("Alternativas por emergencia:")
    for emergencia_id in sorted({a.emergencia_id for a in resultado.alternativas}):
        cantidad = sum(a.emergencia_id == emergencia_id for a in resultado.alternativas)
        print(f"  {emergencia_id}: {cantidad}")


def _metros(valor: float | None) -> str:
    return "sin ruta" if valor is None else f"{valor:.0f} m"


def _imprimir_alternativas(
    alternativas: list[Alternativa], titulo: str
) -> None:
    alternativas.sort(
        key=lambda a: float("inf") if a.costo_seleccion is None else a.costo_seleccion
    )
    encabezados = (
        "Ambulancia", "Establecimiento", "Hasta emergencia", "Hasta destino",
        "Total", "Penalización", "Costo", "Factible", "Motivos",
    )
    filas = [
        (
            a.ambulancia_id, a.establecimiento_id,
            _metros(a.distancia_ambulancia_emergencia_m),
            _metros(a.distancia_emergencia_establecimiento_m),
            _metros(a.distancia_total_m), _metros(a.penalizacion_establecimiento_m),
            _metros(a.costo_seleccion), "sí" if a.es_factible else "no",
            ", ".join(a.motivos_descarte) or "—",
        )
        for a in alternativas
    ]
    anchos = [max(len(encabezados[i]), *(len(f[i]) for f in filas)) for i in range(len(encabezados))]
    formato = "  ".join(f"{{:<{ancho}}}" for ancho in anchos)
    print(f"{titulo}: {len(filas)}")
    print(formato.format(*encabezados))
    print(formato.format(*("-" * ancho for ancho in anchos)))
    for fila in filas:
        print(formato.format(*fila))


def listar_alternativas(
    emergencia_id: str, entrada: Path, configuracion_ambulancias: Path,
    configuracion_emergencias: Path, configuracion_establecimientos: Path,
) -> None:
    resultado, _, _, _ = _cargar_alternativas(
        entrada, configuracion_ambulancias,
        configuracion_emergencias, configuracion_establecimientos,
    )
    alternativas = [
        a for a in resultado.alternativas if a.emergencia_id == emergencia_id
    ]
    if not alternativas:
        raise ValueError(f"Emergencia inexistente: {emergencia_id}")
    _imprimir_alternativas(alternativas, f"Alternativas para {emergencia_id}")


def resumir_heuristicas(
    entrada: Path, configuracion_ambulancias: Path,
    configuracion_emergencias: Path, configuracion_establecimientos: Path,
    nivel: int = 1,
) -> None:
    reduccion, cantidad_ambulancias, cantidad_emergencias, cantidad_destinos = (
        _cargar_reduccion(
            entrada, configuracion_ambulancias,
            configuracion_emergencias, configuracion_establecimientos, nivel,
        )
    )
    parametros = reduccion.parametros
    estadisticas = reduccion.estadisticas
    print(f"Nivel de candidatos: {parametros.nivel}")
    print(f"Ambulancias por emergencia (k): {parametros.k}")
    print(f"Establecimientos por emergencia (h): {parametros.h}")
    print(f"Ambulancias: {cantidad_ambulancias}")
    print(f"Emergencias: {cantidad_emergencias}")
    print(f"Destinos: {cantidad_destinos}")
    print(f"Alternativas originales: {estadisticas.alternativas_originales}")
    print(f"Alternativas factibles: {estadisticas.alternativas_factibles}")
    print(
        "Alternativas no factibles excluidas: "
        f"{estadisticas.alternativas_no_factibles}"
    )
    for motivo, cantidad in estadisticas.motivos_no_factibles.items():
        print(f"  Motivo {motivo}: {cantidad}")
    print(
        "Alternativas tras filtrar ambulancias: "
        f"{estadisticas.alternativas_tras_ambulancias}"
    )
    print(
        "Alternativas tras filtrar establecimientos: "
        f"{estadisticas.alternativas_tras_establecimientos}"
    )
    print(f"Alternativas reducidas: {estadisticas.alternativas_reducidas}")
    print(
        "Alternativas descartadas por ambulancias: "
        f"{estadisticas.descartadas_por_ambulancias}"
    )
    print(
        "Alternativas descartadas por establecimientos: "
        f"{estadisticas.descartadas_por_establecimientos}"
    )
    print(f"Reducción: {estadisticas.porcentaje_reduccion:.1f}%")
    print("Orden de atención de emergencias:")
    for posicion, item in enumerate(reduccion.orden_emergencias, 1):
        print(
            f"  {posicion}. {item.emergencia_id} "
            f"(gravedad {item.gravedad}, "
            f"ambulancias compatibles {item.ambulancias_compatibles}, "
            f"espera {item.minutos_espera:g} min)"
        )


def listar_candidatos(
    emergencia_id: str | None, entrada: Path, configuracion_ambulancias: Path,
    configuracion_emergencias: Path, configuracion_establecimientos: Path,
    nivel: int = 1,
) -> None:
    reduccion, _, _, _ = _cargar_reduccion(
        entrada, configuracion_ambulancias,
        configuracion_emergencias, configuracion_establecimientos, nivel,
    )
    if emergencia_id is not None and emergencia_id not in reduccion.selecciones:
        raise ValueError(f"Emergencia inexistente: {emergencia_id}")
    ids = (
        [emergencia_id]
        if emergencia_id is not None
        else list(reduccion.selecciones)
    )
    for indice, actual in enumerate(ids):
        seleccion = reduccion.selecciones[actual]
        if indice:
            print()
        print(f"Emergencia {actual}:")
        conservadas = seleccion.ambulancias_conservadas
        print(f"  Ambulancias conservadas ({len(conservadas)}):")
        for candidato in conservadas:
            print(
                f"    {candidato.ambulancia_id}: "
                f"{_metros(candidato.distancia_m)}"
            )
        excluidas = seleccion.ambulancias_excluidas
        print(f"  Ambulancias excluidas ({len(excluidas)}):")
        for candidato in excluidas:
            motivos = ", ".join(candidato.motivos_exclusion)
            print(
                f"    {candidato.ambulancia_id}: "
                f"{_metros(candidato.distancia_m)} — {motivos}"
            )
        conservados = seleccion.establecimientos_conservados
        print(f"  Establecimientos conservados ({len(conservados)}):")
        for candidato in conservados:
            print(
                f"    {candidato.establecimiento_id}: "
                f"criterio {_metros(candidato.criterio_m)} "
                f"(distancia {_metros(candidato.distancia_m)} + "
                f"penalización {_metros(candidato.penalizacion_m)})"
            )
        excluidos = seleccion.establecimientos_excluidos
        print(f"  Establecimientos excluidos ({len(excluidos)}):")
        for candidato in excluidos:
            motivos = ", ".join(candidato.motivos_exclusion)
            print(
                f"    {candidato.establecimiento_id}: "
                f"criterio {_metros(candidato.criterio_m)} — {motivos}"
            )


def listar_alternativas_reducidas(
    emergencia_id: str | None, entrada: Path, configuracion_ambulancias: Path,
    configuracion_emergencias: Path, configuracion_establecimientos: Path,
    nivel: int = 1,
) -> None:
    reduccion, _, _, _ = _cargar_reduccion(
        entrada, configuracion_ambulancias,
        configuracion_emergencias, configuracion_establecimientos, nivel,
    )
    if emergencia_id is not None and emergencia_id not in reduccion.selecciones:
        raise ValueError(f"Emergencia inexistente: {emergencia_id}")
    ids = (
        [emergencia_id]
        if emergencia_id is not None
        else [item.emergencia_id for item in reduccion.orden_emergencias]
    )
    for indice, actual in enumerate(ids):
        alternativas = [
            alternativa
            for alternativa in reduccion.alternativas_reducidas
            if alternativa.emergencia_id == actual
        ]
        if indice:
            print()
        _imprimir_alternativas(
            alternativas, f"Alternativas reducidas para {actual}"
        )


def _etiqueta_conjunto(asignacion: ResultadoAsignacion) -> str:
    if asignacion.parametros is None:
        return "original"
    parametros = asignacion.parametros
    return f"nivel {parametros.nivel} (k={parametros.k}, h={parametros.h})"


def _imprimir_resumen_asignacion(asignacion: ResultadoAsignacion) -> None:
    print(f"Conjunto de alternativas: {_etiqueta_conjunto(asignacion)}")
    print(f"Alternativas candidatas: {asignacion.alternativas_candidatas}")
    print(
        "Alternativas evaluadas tras dominancia: "
        f"{asignacion.alternativas_evaluadas}"
    )
    print(f"Emergencias: {asignacion.cantidad_emergencias}")
    print(f"Emergencias atendidas: {asignacion.cantidad_atendidas}")
    print(f"Emergencias sin asignar: {asignacion.cantidad_sin_asignar}")
    print(f"Asignación completa: {'sí' if asignacion.es_completa else 'no'}")
    print(f"Óptima dentro del conjunto: {'sí' if asignacion.es_optima else 'no'}")
    print(f"Costo total: {_metros(asignacion.costo_total)}")
    print(
        "Ambulancias utilizadas: "
        + (", ".join(asignacion.ambulancias_utilizadas) or "ninguna")
    )
    print(
        "Establecimientos seleccionados: "
        + (", ".join(asignacion.establecimientos_seleccionados) or "ninguno")
    )
    print(
        "Emergencias atendidas (orden de prioridad): "
        + (", ".join(asignacion.emergencias_atendidas) or "ninguna")
    )
    if not asignacion.alternativas:
        print("Asignaciones: ninguna")
    else:
        print("Asignaciones:")
        for alternativa in asignacion.alternativas:
            print(
                f"  {alternativa.emergencia_id} -> "
                f"{alternativa.ambulancia_id} -> "
                f"{alternativa.establecimiento_id} "
                f"({_metros(alternativa.costo_seleccion)})"
            )
    if not asignacion.emergencias_sin_asignar:
        print("Emergencias sin asignar: ninguna")
    else:
        print("Emergencias sin asignar:")
        for emergencia_id in asignacion.emergencias_sin_asignar:
            motivo = asignacion.motivos_sin_asignar.get(
                emergencia_id, "motivo_desconocido"
            )
            print(f"  {emergencia_id}: {motivo}")


def _imprimir_detalle_asignacion(asignacion: ResultadoAsignacion) -> None:
    print(f"Detalle de la asignación ({_etiqueta_conjunto(asignacion)}):")
    if not asignacion.alternativas:
        print("  Sin alternativas seleccionadas")
    else:
        encabezados = (
            "Emergencia", "Ambulancia", "Establecimiento",
            "Hasta emergencia", "Hasta destino", "Total", "Penalización",
            "Costo", "Factible", "Motivos",
        )
        filas = [
            (
                a.emergencia_id, a.ambulancia_id, a.establecimiento_id,
                _metros(a.distancia_ambulancia_emergencia_m),
                _metros(a.distancia_emergencia_establecimiento_m),
                _metros(a.distancia_total_m),
                _metros(a.penalizacion_establecimiento_m),
                _metros(a.costo_seleccion),
                "sí" if a.es_factible else "no",
                ", ".join(a.motivos_descarte) or "—",
            )
            for a in asignacion.alternativas
        ]
        anchos = [
            max(len(encabezados[i]), *(len(fila[i]) for fila in filas))
            for i in range(len(encabezados))
        ]
        formato = "  ".join(f"{{:<{ancho}}}" for ancho in anchos)
        print(formato.format(*encabezados))
        print(formato.format(*("-" * ancho for ancho in anchos)))
        for fila in filas:
            print(formato.format(*fila))
    if not asignacion.emergencias_sin_asignar:
        print("Emergencias sin asignar: ninguna")
    else:
        print("Emergencias sin asignar:")
        for emergencia_id in asignacion.emergencias_sin_asignar:
            motivo = asignacion.motivos_sin_asignar.get(
                emergencia_id, "motivo_desconocido"
            )
            print(f"  {emergencia_id}: {motivo}")


def _cargar_asignacion(
    entrada: Path, configuracion_ambulancias: Path,
    configuracion_emergencias: Path, configuracion_establecimientos: Path,
    nivel: int = 1, original: bool = False,
) -> ResultadoAsignacion:
    resultado, ambulancias, emergencias, establecimientos = _cargar_modelo(
        entrada, configuracion_ambulancias,
        configuracion_emergencias, configuracion_establecimientos,
    )
    if original:
        return asignar_original(resultado, ambulancias, emergencias)
    return asignar_con_nivel(
        resultado, ambulancias, emergencias, establecimientos, nivel
    )


def _validar_etapa_simulacion(etapa: int) -> None:
    if (
        isinstance(etapa, bool)
        or not isinstance(etapa, int)
        or etapa < 0
        or etapa > PASO_FINAL
    ):
        raise ValueError(
            f"Etapa de simulación inexistente: {etapa} "
            f"(válidas: 0 a {PASO_FINAL})"
        )


def _cargar_simulacion(
    entrada: Path, configuracion_ambulancias: Path,
    configuracion_emergencias: Path, configuracion_establecimientos: Path,
    nivel: int = 1, original: bool = False, etapa: int = 0,
) -> Simulacion:
    _validar_etapa_simulacion(etapa)
    resultado, ambulancias, emergencias, establecimientos = _cargar_modelo(
        entrada, configuracion_ambulancias,
        configuracion_emergencias, configuracion_establecimientos,
    )
    asignacion = (
        asignar_original(resultado, ambulancias, emergencias)
        if original
        else asignar_con_nivel(
            resultado, ambulancias, emergencias, establecimientos, nivel
        )
    )
    simulacion = crear_simulacion(
        asignacion, resultado, ambulancias, emergencias, establecimientos
    )
    if etapa:
        simulacion.avanzar(etapa)
    return simulacion


def _imprimir_resumen_simulacion(resultado: ResultadoSimulacion) -> None:
    print("Simulación lógica — Etapa 8")
    print(f"Asignación de origen: {resultado.etiqueta_asignacion}")
    print(
        f"Etapa: {resultado.paso}/{resultado.total_pasos} — "
        f"{resultado.nombre_etapa}"
    )
    print("Tipo: lógica por etapas (sin tiempos reales)")
    print(f"Atenciones: {resultado.cantidad_atenciones}")
    print(f"Completadas: {resultado.cantidad_completadas}")
    print(f"Emergencias sin asignar: {resultado.cantidad_sin_asignar}")
    print(f"Cobertura completa: {'sí' if resultado.es_completa else 'no'}")
    print(f"Costo total: {_metros(resultado.costo_total)}")
    print(f"Distancia total: {_metros(resultado.distancia_total)}")
    print(f"Penalizaciones: {_metros(resultado.penalizacion_total)}")
    if not resultado.atenciones:
        print("Atenciones: ninguna")
    else:
        print("Atenciones:")
        for atencion in resultado.atenciones:
            print(
                f"  {atencion.emergencia_id} -> "
                f"{atencion.ambulancia_id} (base {atencion.base_id}) -> "
                f"{atencion.establecimiento_id}: "
                f"emergencia {atencion.estado_emergencia}, "
                f"ambulancia {atencion.estado_ambulancia}, "
                f"{_metros(atencion.costo_seleccion)}"
            )
    if not resultado.emergencias_sin_asignar:
        print("Emergencias sin asignar: ninguna")
    else:
        print("Emergencias sin asignar:")
        for emergencia_id in resultado.emergencias_sin_asignar:
            print(
                f"  {emergencia_id}: "
                f"{resultado.motivos_sin_asignar[emergencia_id]}"
            )
    print("Estados de emergencias:")
    for emergencia in resultado.emergencias:
        print(f"  {emergencia.emergencia_id}: {emergencia.estado}")
    print("Estados de ambulancias:")
    for ambulancia in resultado.ambulancias:
        print(f"  {ambulancia.ambulancia_id}: {ambulancia.estado}")


def _imprimir_detalle_simulacion(resultado: ResultadoSimulacion) -> None:
    print(f"Detalle de la simulación ({resultado.etiqueta_asignacion}):")
    print(
        f"Etapa: {resultado.paso}/{resultado.total_pasos} — "
        f"{resultado.nombre_etapa}"
    )
    encabezados = (
        "Emergencia", "Estado", "Ambulancia", "Estado amb.", "Base",
        "Destino", "Hacia emergencia", "Hacia destino", "Total",
        "Penalización", "Costo", "Completada",
    )
    filas = [
        (
            atencion.emergencia_id, atencion.estado_emergencia,
            atencion.ambulancia_id, atencion.estado_ambulancia,
            atencion.base_id, atencion.establecimiento_id,
            _metros(atencion.distancia_ambulancia_emergencia_m),
            _metros(atencion.distancia_emergencia_establecimiento_m),
            _metros(atencion.distancia_total_m),
            _metros(atencion.penalizacion_establecimiento_m),
            _metros(atencion.costo_seleccion),
            "sí" if atencion.completada else "no",
        )
        for atencion in resultado.atenciones
    ]
    if not filas:
        print("Atenciones: ninguna")
    else:
        anchos = [
            max(len(encabezados[i]), *(len(fila[i]) for fila in filas))
            for i in range(len(encabezados))
        ]
        formato = "  ".join(f"{{:<{ancho}}}" for ancho in anchos)
        print(formato.format(*encabezados))
        print(formato.format(*("-" * ancho for ancho in anchos)))
        for fila in filas:
            print(formato.format(*fila))
    if not resultado.emergencias_sin_asignar:
        print("Emergencias sin asignar: ninguna")
    else:
        print("Emergencias sin asignar:")
        for emergencia_id in resultado.emergencias_sin_asignar:
            print(
                f"  {emergencia_id}: "
                f"{resultado.motivos_sin_asignar[emergencia_id]}"
            )
    print("Estados de emergencias:")
    for emergencia in resultado.emergencias:
        print(
            f"  {emergencia.emergencia_id}: {emergencia.estado}"
            + (
                f" (ambulancia {emergencia.ambulancia_id}, "
                f"destino {emergencia.establecimiento_id})"
                if emergencia.ambulancia_id
                else ""
            )
        )
    print("Estados de ambulancias:")
    for ambulancia in resultado.ambulancias:
        print(
            f"  {ambulancia.ambulancia_id}: {ambulancia.estado}"
            + (
                f" (emergencia {ambulancia.emergencia_id})"
                if ambulancia.emergencia_id
                else ""
            )
        )


def iniciar_simulacion(
    entrada: Path, configuracion_ambulancias: Path,
    configuracion_emergencias: Path, configuracion_establecimientos: Path,
    nivel: int = 1, original: bool = False,
) -> None:
    simulacion = _cargar_simulacion(
        entrada, configuracion_ambulancias,
        configuracion_emergencias, configuracion_establecimientos,
        nivel, original, 0,
    )
    _imprimir_resumen_simulacion(simulacion.resultado())


def resumir_simulacion(
    entrada: Path, configuracion_ambulancias: Path,
    configuracion_emergencias: Path, configuracion_establecimientos: Path,
    nivel: int = 1, original: bool = False, etapa: int = PASO_FINAL,
) -> None:
    simulacion = _cargar_simulacion(
        entrada, configuracion_ambulancias,
        configuracion_emergencias, configuracion_establecimientos,
        nivel, original, etapa,
    )
    _imprimir_resumen_simulacion(simulacion.resultado())


def listar_simulacion(
    entrada: Path, configuracion_ambulancias: Path,
    configuracion_emergencias: Path, configuracion_establecimientos: Path,
    nivel: int = 1, original: bool = False, etapa: int = PASO_FINAL,
) -> None:
    simulacion = _cargar_simulacion(
        entrada, configuracion_ambulancias,
        configuracion_emergencias, configuracion_establecimientos,
        nivel, original, etapa,
    )
    _imprimir_detalle_simulacion(simulacion.resultado())


def avanzar_simulacion(
    entrada: Path, configuracion_ambulancias: Path,
    configuracion_emergencias: Path, configuracion_establecimientos: Path,
    nivel: int = 1, original: bool = False,
    pasos: int = 1, hasta_final: bool = False,
) -> None:
    simulacion = _cargar_simulacion(
        entrada, configuracion_ambulancias,
        configuracion_emergencias, configuracion_establecimientos,
        nivel, original, 0,
    )
    if hasta_final:
        simulacion.avanzar_hasta_final()
    else:
        simulacion.avanzar(pasos)
    _imprimir_resumen_simulacion(simulacion.resultado())


def ver_simulacion(
    entrada: Path, configuracion_ambulancias: Path,
    configuracion_emergencias: Path, configuracion_establecimientos: Path,
    nivel: int = 1, original: bool = False, etapa: int = PASO_FINAL,
    emergencia_id: str | None = None, ambulancia_id: str | None = None,
) -> None:
    if (emergencia_id is None) == (ambulancia_id is None):
        raise ValueError("Indicá exactamente una emergencia o una ambulancia")
    simulacion = _cargar_simulacion(
        entrada, configuracion_ambulancias,
        configuracion_emergencias, configuracion_establecimientos,
        nivel, original, etapa,
    )
    resultado = simulacion.resultado()

    if emergencia_id is not None:
        estado = next(
            (
                emergencia
                for emergencia in resultado.emergencias
                if emergencia.emergencia_id == emergencia_id
            ),
            None,
        )
        if estado is None:
            raise ValueError(f"Emergencia inexistente: {emergencia_id}")
        print(f"Emergencia {emergencia_id}:")
        print(f"  Estado: {estado.estado}")
        print(f"  Completada: {'sí' if estado.completada else 'no'}")
        if estado.ambulancia_id is None:
            print(
                "  Sin asignación: "
                f"{estado.motivo_sin_asignar or 'motivo_no_informado'}"
            )
            return
        atencion = next(
            atencion
            for atencion in resultado.atenciones
            if atencion.emergencia_id == emergencia_id
        )
        print(
            f"  Ambulancia: {atencion.ambulancia_id} "
            f"(base {atencion.base_id}, estado {atencion.estado_ambulancia})"
        )
        print(f"  Destino: {atencion.establecimiento_id}")
        print(
            "  Tramo ambulancia -> emergencia: "
            f"{_metros(atencion.distancia_ambulancia_emergencia_m)} "
            f"({len(atencion.tramo_ambulancia_emergencia.camino)} nodos)"
        )
        print(
            "  Tramo emergencia -> destino: "
            f"{_metros(atencion.distancia_emergencia_establecimiento_m)} "
            f"({len(atencion.tramo_emergencia_establecimiento.camino)} nodos)"
        )
        print(f"  Distancia total: {_metros(atencion.distancia_total_m)}")
        print(
            "  Penalización: "
            f"{_metros(atencion.penalizacion_establecimiento_m)}"
        )
        print(f"  Costo: {_metros(atencion.costo_seleccion)}")
        return

    estado = next(
        (
            ambulancia
            for ambulancia in resultado.ambulancias
            if ambulancia.ambulancia_id == ambulancia_id
        ),
        None,
    )
    if estado is None:
        raise ValueError(f"Ambulancia inexistente: {ambulancia_id}")
    print(f"Ambulancia {ambulancia_id}:")
    print(f"  Base: {estado.base_id}")
    print(f"  Estado: {estado.estado}")
    if estado.emergencia_id is None:
        print("  Sin emergencia asignada")
        return
    atencion = next(
        atencion
        for atencion in resultado.atenciones
        if atencion.ambulancia_id == ambulancia_id
    )
    print(f"  Emergencia: {atencion.emergencia_id}")
    print(f"  Destino: {atencion.establecimiento_id}")
    print(f"  Estado de la emergencia: {atencion.estado_emergencia}")
    print(
        "  Tramo ambulancia -> emergencia: "
        f"{_metros(atencion.distancia_ambulancia_emergencia_m)}"
    )
    print(
        "  Tramo emergencia -> destino: "
        f"{_metros(atencion.distancia_emergencia_establecimiento_m)}"
    )
    print(f"  Costo: {_metros(atencion.costo_seleccion)}")


def _imprimir_evaluacion(evaluacion: EvaluacionEscenarios) -> None:
    print("Evaluación de escenarios — Etapa 9")
    print(
        "Comparación dinámica entre la asignación original y los niveles "
        "1 a 4."
    )
    print(
        "La simulación asociada es lógica por etapas, sin tiempos reales."
    )
    encabezados = (
        "Escenario",
        "Generadas",
        "Factibles",
        "Conservadas",
        "Evaluadas",
        "Reducción",
        "Atendidas",
        "Sin asignar",
        "Costo",
        "Distancia",
        "Penalizaciones",
    )
    filas = [
        (
            metricas.etiqueta,
            str(metricas.alternativas_generadas),
            str(metricas.alternativas_factibles),
            str(metricas.alternativas_conservadas),
            str(metricas.alternativas_evaluadas),
            f"{metricas.porcentaje_reduccion:.2f} %",
            str(metricas.emergencias_atendidas),
            str(metricas.emergencias_sin_asignar),
            _metros(metricas.costo_total),
            _metros(metricas.distancia_total),
            _metros(metricas.penalizacion_total),
        )
        for metricas in evaluacion.escenarios
    ]
    anchos = [
        max(len(encabezados[i]), *(len(fila[i]) for fila in filas))
        for i in range(len(encabezados))
    ]
    formato = "  ".join(f"{{:<{ancho}}}" for ancho in anchos)
    print(formato.format(*encabezados))
    print(formato.format(*("-" * ancho for ancho in anchos)))
    for fila in filas:
        print(formato.format(*fila))

    print("Asignaciones por escenario:")
    for metricas in evaluacion.escenarios:
        print(f"  {metricas.etiqueta}:")
        if not metricas.asignaciones:
            print("    Ninguna")
        for asignacion in metricas.asignaciones:
            print(
                f"    {asignacion.emergencia_id} -> "
                f"{asignacion.ambulancia_id} "
                f"(base {asignacion.base_id}) -> "
                f"{asignacion.establecimiento_id}: "
                f"{_metros(asignacion.costo_seleccion)}"
            )
        if metricas.diferencias_respecto_original:
            print("    Diferencias respecto del original:")
            for diferencia in metricas.diferencias_respecto_original:
                print(
                    f"      {diferencia.emergencia_id}: "
                    f"{diferencia.original or 'sin asignación'} -> "
                    f"{diferencia.escenario or 'sin asignación'} "
                    f"({diferencia.tipo})"
                )
        else:
            print(
                "    Sin diferencias de asignación respecto del original."
            )
        if metricas.motivos_sin_asignar:
            print("    Motivos de emergencias sin asignar:")
            for emergencia_id, motivo in metricas.motivos_sin_asignar.items():
                print(f"      {emergencia_id}: {motivo}")

    print("Estados finales de la simulación:")
    for metricas in evaluacion.escenarios:
        print(f"  {metricas.etiqueta}:")
        print(
            "    Emergencias: "
            + ", ".join(
                f"{emergencia_id}={estado}"
                for emergencia_id, estado
                in metricas.estados_finales_emergencias.items()
            )
        )
        print(
            "    Ambulancias: "
            + ", ".join(
                f"{ambulancia_id}={estado}"
                for ambulancia_id, estado
                in metricas.estados_finales_ambulancias.items()
            )
        )

    print("Resumen:")
    print(
        "  Nivel recomendado: "
        f"{evaluacion.nivel_recomendado if evaluacion.nivel_recomendado is not None else '—'}"
    )
    print(
        "  Pérdida por heurística: "
        f"{'sí' if evaluacion.perdida_por_heuristica else 'no'}"
    )
    print(
        "  Niveles con pérdida: "
        + (
            ", ".join(str(nivel) for nivel in evaluacion.niveles_con_perdida)
            if evaluacion.niveles_con_perdida
            else "ninguno"
        )
    )
    print(
        "  Mismos resultados de asignación: "
        f"{'sí' if evaluacion.todos_mismos_resultados else 'no'}"
    )
    print(
        "  Mismos costos: "
        f"{'sí' if evaluacion.todos_mismos_costos else 'no'}"
    )


def evaluar_escenarios(
    entrada: Path, configuracion_ambulancias: Path,
    configuracion_emergencias: Path, configuracion_establecimientos: Path,
) -> None:
    resultado, ambulancias, emergencias, establecimientos = _cargar_modelo(
        entrada, configuracion_ambulancias,
        configuracion_emergencias, configuracion_establecimientos,
    )
    evaluacion = calcular_evaluacion(
        resultado, ambulancias, emergencias, establecimientos
    )
    _imprimir_evaluacion(evaluacion)


def resumir_asignacion(
    entrada: Path, configuracion_ambulancias: Path,
    configuracion_emergencias: Path, configuracion_establecimientos: Path,
    nivel: int = 1, original: bool = False,
) -> None:
    asignacion = _cargar_asignacion(
        entrada, configuracion_ambulancias,
        configuracion_emergencias, configuracion_establecimientos,
        nivel, original,
    )
    print("Resumen de la asignación global:")
    _imprimir_resumen_asignacion(asignacion)


def listar_asignacion(
    entrada: Path, configuracion_ambulancias: Path,
    configuracion_emergencias: Path, configuracion_establecimientos: Path,
    nivel: int = 1, original: bool = False,
) -> None:
    asignacion = _cargar_asignacion(
        entrada, configuracion_ambulancias,
        configuracion_emergencias, configuracion_establecimientos,
        nivel, original,
    )
    _imprimir_detalle_asignacion(asignacion)


def _imprimir_comparacion(comparacion: ComparacionAsignaciones) -> None:
    print("Conjunto original:")
    _imprimir_resumen_asignacion(comparacion.original)
    for nivel in comparacion.niveles:
        print()
        print(
            f"Nivel {nivel.parametros.nivel} "
            f"(k={nivel.parametros.k}, h={nivel.parametros.h}):"
        )
        _imprimir_resumen_asignacion(nivel)
    print()
    print(f"Mejor nivel reducido: {comparacion.nivel_recomendado}")
    print(
        "¿Alguna heurística perdió optimalidad frente al original?: "
        f"{'sí' if comparacion.perdida_por_heuristica else 'no'}"
    )
    if comparacion.niveles_con_perdida:
        print(
            "Niveles con pérdida: "
            + ", ".join(str(nivel) for nivel in comparacion.niveles_con_perdida)
        )
    else:
        print("Niveles con pérdida: ninguno")
    if comparacion.diferencias:
        print("Diferencias frente al conjunto original:")
        for nivel, descripcion in sorted(comparacion.diferencias.items()):
            print(f"  Nivel {nivel}: {descripcion}")
    else:
        print(
            "Todos los niveles alcanzan la misma solución que el conjunto original."
        )


def comparar_asignaciones(
    entrada: Path, configuracion_ambulancias: Path,
    configuracion_emergencias: Path, configuracion_establecimientos: Path,
) -> None:
    resultado, ambulancias, emergencias, establecimientos = _cargar_modelo(
        entrada, configuracion_ambulancias,
        configuracion_emergencias, configuracion_establecimientos,
    )
    comparacion = comparar_niveles(
        resultado, ambulancias, emergencias, establecimientos
    )
    _imprimir_comparacion(comparacion)


def main() -> None:
    parser = argparse.ArgumentParser(prog="ambulancias_pergamino")
    subparsers = parser.add_subparsers(dest="comando", required=True)

    construir_parser = subparsers.add_parser("construir")
    construir_parser.add_argument("--salida", type=Path, default=Path("data/pergamino.json"))

    rutas_parser = subparsers.add_parser("verificar-rutas")
    rutas_parser.add_argument("--entrada", type=Path, default=Path("data/pergamino.json"))

    ambulancias_parser = subparsers.add_parser("listar-ambulancias")
    ambulancias_parser.add_argument(
        "--entrada", type=Path, default=Path("data/pergamino.json")
    )
    ambulancias_parser.add_argument(
        "--ambulancias", type=Path, default=Path("config/ambulancias.json")
    )

    establecimientos_parser = subparsers.add_parser("listar-establecimientos")
    establecimientos_parser.add_argument(
        "--entrada", type=Path, default=Path("data/pergamino.json")
    )
    establecimientos_parser.add_argument(
        "--establecimientos",
        type=Path,
        default=Path("config/establecimientos.json"),
    )

    emergencias_parser = subparsers.add_parser("listar-emergencias")
    emergencias_parser.add_argument(
        "--entrada", type=Path, default=Path("data/pergamino.json")
    )
    emergencias_parser.add_argument(
        "--emergencias", type=Path, default=Path("config/emergencias.json")
    )

    verificar_emergencias_parser = subparsers.add_parser("verificar-emergencias")
    verificar_emergencias_parser.add_argument(
        "--entrada", type=Path, default=Path("data/pergamino.json")
    )
    verificar_emergencias_parser.add_argument(
        "--emergencias", type=Path, default=Path("config/emergencias.json")
    )
    verificar_emergencias_parser.add_argument(
        "--establecimientos",
        type=Path,
        default=Path("config/establecimientos.json"),
    )

    resumen_parser = subparsers.add_parser("resumir-alternativas")
    listado_parser = subparsers.add_parser("listar-alternativas")
    listado_parser.add_argument("--emergencia", required=True)
    for subparser in (resumen_parser, listado_parser):
        subparser.add_argument("--entrada", type=Path, default=Path("data/pergamino.json"))
        subparser.add_argument("--ambulancias", type=Path, default=Path("config/ambulancias.json"))
        subparser.add_argument("--emergencias", type=Path, default=Path("config/emergencias.json"))
        subparser.add_argument(
            "--establecimientos", type=Path,
            default=Path("config/establecimientos.json"),
        )

    resumen_heuristicas_parser = subparsers.add_parser("resumir-heuristicas")
    candidatos_parser = subparsers.add_parser("listar-candidatos")
    candidatos_parser.add_argument("--emergencia")
    reducidas_parser = subparsers.add_parser("listar-alternativas-reducidas")
    reducidas_parser.add_argument("--emergencia")
    for subparser in (
        resumen_heuristicas_parser, candidatos_parser, reducidas_parser
    ):
        subparser.add_argument("--entrada", type=Path, default=Path("data/pergamino.json"))
        subparser.add_argument("--ambulancias", type=Path, default=Path("config/ambulancias.json"))
        subparser.add_argument("--emergencias", type=Path, default=Path("config/emergencias.json"))
        subparser.add_argument(
            "--establecimientos", type=Path,
            default=Path("config/establecimientos.json"),
        )
        subparser.add_argument("--nivel", type=int, default=1)

    resumen_asignacion_parser = subparsers.add_parser("resumir-asignacion")
    listado_asignacion_parser = subparsers.add_parser("listar-asignacion")
    for subparser in (resumen_asignacion_parser, listado_asignacion_parser):
        subparser.add_argument("--entrada", type=Path, default=Path("data/pergamino.json"))
        subparser.add_argument("--ambulancias", type=Path, default=Path("config/ambulancias.json"))
        subparser.add_argument("--emergencias", type=Path, default=Path("config/emergencias.json"))
        subparser.add_argument(
            "--establecimientos", type=Path,
            default=Path("config/establecimientos.json"),
        )
        grupo_conjunto = subparser.add_mutually_exclusive_group()
        grupo_conjunto.add_argument("--nivel", type=int, default=1)
        grupo_conjunto.add_argument("--original", action="store_true")

    comparacion_asignaciones_parser = subparsers.add_parser(
        "comparar-asignaciones"
    )
    comparacion_asignaciones_parser.add_argument(
        "--entrada", type=Path, default=Path("data/pergamino.json")
    )
    comparacion_asignaciones_parser.add_argument(
        "--ambulancias", type=Path, default=Path("config/ambulancias.json")
    )
    comparacion_asignaciones_parser.add_argument(
        "--emergencias", type=Path, default=Path("config/emergencias.json")
    )
    comparacion_asignaciones_parser.add_argument(
        "--establecimientos",
        type=Path,
        default=Path("config/establecimientos.json"),
    )

    ayudas_simulacion = {
        "iniciar-simulacion": (
            "Muestra el estado inicial de la simulación lógica"
        ),
        "resumir-simulacion": (
            "Resume estados, atenciones y costos de la simulación"
        ),
        "listar-simulacion": (
            "Lista el detalle de cada atención simulada"
        ),
        "avanzar-simulacion": (
            "Avanza la simulación desde la etapa inicial"
        ),
        "ver-simulacion": (
            "Consulta una emergencia o una ambulancia simulada"
        ),
    }
    simulacion_parsers = {
        nombre: subparsers.add_parser(
            nombre,
            help=ayuda,
            description=ayuda + ". La simulación es lógica por etapas, sin tiempos reales.",
        )
        for nombre, ayuda in ayudas_simulacion.items()
    }
    for nombre, subparser in simulacion_parsers.items():
        subparser.add_argument(
            "--entrada",
            type=Path,
            default=Path("data/pergamino.json"),
            help="Grafo y bases de ambulancias",
        )
        subparser.add_argument(
            "--ambulancias",
            type=Path,
            default=Path("config/ambulancias.json"),
            help="Configuración de ambulancias",
        )
        subparser.add_argument(
            "--emergencias",
            type=Path,
            default=Path("config/emergencias.json"),
            help="Configuración de emergencias",
        )
        subparser.add_argument(
            "--establecimientos",
            type=Path,
            default=Path("config/establecimientos.json"),
            help="Configuración de establecimientos de destino",
        )
        grupo_conjunto = subparser.add_mutually_exclusive_group()
        grupo_conjunto.add_argument(
            "--nivel",
            type=int,
            default=1,
            help="Nivel de reducción heurística usado para asignar (1 a 4)",
        )
        grupo_conjunto.add_argument(
            "--original",
            action="store_true",
            help="Usar el conjunto completo de alternativas originales",
        )
        if nombre not in {"iniciar-simulacion", "avanzar-simulacion"}:
            subparser.add_argument(
                "--etapa",
                type=int,
                default=PASO_FINAL,
                help=f"Etapa lógica a consultar (0 a {PASO_FINAL})",
            )

    avanzar_parser = simulacion_parsers["avanzar-simulacion"]
    grupo_avance = avanzar_parser.add_mutually_exclusive_group()
    grupo_avance.add_argument(
        "--pasos",
        type=int,
        default=1,
        help="Cantidad de etapas lógicas a avanzar",
    )
    grupo_avance.add_argument(
        "--hasta-final",
        action="store_true",
        help="Avanzar directamente hasta la etapa final",
    )

    ver_parser = simulacion_parsers["ver-simulacion"]
    grupo_entidad = ver_parser.add_mutually_exclusive_group(required=True)
    grupo_entidad.add_argument(
        "--emergencia", help="Identificador de la emergencia a consultar"
    )
    grupo_entidad.add_argument(
        "--ambulancia", help="Identificador de la ambulancia a consultar"
    )

    evaluacion_parser = subparsers.add_parser(
        "evaluar-escenarios",
        help="Compara el escenario original con los niveles heurísticos 1 a 4",
        description=(
            "Compara alternativas, asignaciones, costos, distancias, "
            "penalizaciones y estados finales de la simulación para el "
            "escenario original y los niveles 1 a 4."
        ),
    )
    evaluacion_parser.add_argument(
        "--entrada",
        type=Path,
        default=Path("data/pergamino.json"),
        help="Grafo y bases de ambulancias",
    )
    evaluacion_parser.add_argument(
        "--ambulancias",
        type=Path,
        default=Path("config/ambulancias.json"),
        help="Configuración de ambulancias",
    )
    evaluacion_parser.add_argument(
        "--emergencias",
        type=Path,
        default=Path("config/emergencias.json"),
        help="Configuración de emergencias",
    )
    evaluacion_parser.add_argument(
        "--establecimientos",
        type=Path,
        default=Path("config/establecimientos.json"),
        help="Configuración de establecimientos de destino",
    )

    mapa_parser = subparsers.add_parser("exportar-mapa")
    mapa_parser.add_argument("--entrada", type=Path, default=Path("data/pergamino.json"))
    mapa_parser.add_argument(
        "--ambulancias", type=Path, default=Path("config/ambulancias.json")
    )
    mapa_parser.add_argument(
        "--salida", type=Path, default=Path("data/mapa_pergamino.html")
    )
    mapa_parser.add_argument(
        "--establecimientos",
        type=Path,
        default=Path("config/establecimientos.json"),
    )
    mapa_parser.add_argument(
        "--emergencias", type=Path, default=Path("config/emergencias.json")
    )

    argumentos = parser.parse_args()
    if argumentos.comando == "construir":
        construir(argumentos.salida)
    elif argumentos.comando == "verificar-rutas":
        verificar_rutas(argumentos.entrada)
    elif argumentos.comando == "listar-ambulancias":
        listar_ambulancias(argumentos.entrada, argumentos.ambulancias)
    elif argumentos.comando == "listar-establecimientos":
        listar_establecimientos(argumentos.entrada, argumentos.establecimientos)
    elif argumentos.comando == "listar-emergencias":
        listar_emergencias(argumentos.entrada, argumentos.emergencias)
    elif argumentos.comando == "verificar-emergencias":
        verificar_emergencias(
            argumentos.entrada,
            argumentos.emergencias,
            argumentos.establecimientos,
        )
    elif argumentos.comando == "resumir-alternativas":
        resumir_alternativas(
            argumentos.entrada, argumentos.ambulancias,
            argumentos.emergencias, argumentos.establecimientos,
        )
    elif argumentos.comando == "listar-alternativas":
        try:
            listar_alternativas(
                argumentos.emergencia, argumentos.entrada, argumentos.ambulancias,
                argumentos.emergencias, argumentos.establecimientos,
            )
        except ValueError as error:
            parser.error(str(error))
    elif argumentos.comando == "resumir-heuristicas":
        try:
            resumir_heuristicas(
                argumentos.entrada, argumentos.ambulancias,
                argumentos.emergencias, argumentos.establecimientos,
                argumentos.nivel,
            )
        except ValueError as error:
            parser.error(str(error))
    elif argumentos.comando == "listar-candidatos":
        try:
            listar_candidatos(
                argumentos.emergencia, argumentos.entrada,
                argumentos.ambulancias, argumentos.emergencias,
                argumentos.establecimientos, argumentos.nivel,
            )
        except ValueError as error:
            parser.error(str(error))
    elif argumentos.comando == "listar-alternativas-reducidas":
        try:
            listar_alternativas_reducidas(
                argumentos.emergencia, argumentos.entrada,
                argumentos.ambulancias, argumentos.emergencias,
                argumentos.establecimientos, argumentos.nivel,
            )
        except ValueError as error:
            parser.error(str(error))
    elif argumentos.comando == "resumir-asignacion":
        try:
            resumir_asignacion(
                argumentos.entrada, argumentos.ambulancias,
                argumentos.emergencias, argumentos.establecimientos,
                argumentos.nivel, argumentos.original,
            )
        except ValueError as error:
            parser.error(str(error))
    elif argumentos.comando == "listar-asignacion":
        try:
            listar_asignacion(
                argumentos.entrada, argumentos.ambulancias,
                argumentos.emergencias, argumentos.establecimientos,
                argumentos.nivel, argumentos.original,
            )
        except ValueError as error:
            parser.error(str(error))
    elif argumentos.comando == "comparar-asignaciones":
        try:
            comparar_asignaciones(
                argumentos.entrada, argumentos.ambulancias,
                argumentos.emergencias, argumentos.establecimientos,
            )
        except ValueError as error:
            parser.error(str(error))
    elif argumentos.comando == "iniciar-simulacion":
        try:
            iniciar_simulacion(
                argumentos.entrada, argumentos.ambulancias,
                argumentos.emergencias, argumentos.establecimientos,
                argumentos.nivel, argumentos.original,
            )
        except ValueError as error:
            parser.error(str(error))
    elif argumentos.comando == "resumir-simulacion":
        try:
            resumir_simulacion(
                argumentos.entrada, argumentos.ambulancias,
                argumentos.emergencias, argumentos.establecimientos,
                argumentos.nivel, argumentos.original, argumentos.etapa,
            )
        except ValueError as error:
            parser.error(str(error))
    elif argumentos.comando == "listar-simulacion":
        try:
            listar_simulacion(
                argumentos.entrada, argumentos.ambulancias,
                argumentos.emergencias, argumentos.establecimientos,
                argumentos.nivel, argumentos.original, argumentos.etapa,
            )
        except ValueError as error:
            parser.error(str(error))
    elif argumentos.comando == "avanzar-simulacion":
        try:
            avanzar_simulacion(
                argumentos.entrada, argumentos.ambulancias,
                argumentos.emergencias, argumentos.establecimientos,
                argumentos.nivel, argumentos.original,
                argumentos.pasos, argumentos.hasta_final,
            )
        except ValueError as error:
            parser.error(str(error))
    elif argumentos.comando == "ver-simulacion":
        try:
            ver_simulacion(
                argumentos.entrada, argumentos.ambulancias,
                argumentos.emergencias, argumentos.establecimientos,
                argumentos.nivel, argumentos.original, argumentos.etapa,
                argumentos.emergencia, argumentos.ambulancia,
            )
        except ValueError as error:
            parser.error(str(error))
    elif argumentos.comando == "evaluar-escenarios":
        try:
            evaluar_escenarios(
                argumentos.entrada, argumentos.ambulancias,
                argumentos.emergencias, argumentos.establecimientos,
            )
        except ValueError as error:
            parser.error(str(error))
    elif argumentos.comando == "exportar-mapa":
        exportar_mapa(
            argumentos.entrada,
            argumentos.ambulancias,
            argumentos.salida,
            argumentos.establecimientos,
            argumentos.emergencias,
        )
        print(f"Mapa guardado en {argumentos.salida}")


if __name__ == "__main__":
    main()

