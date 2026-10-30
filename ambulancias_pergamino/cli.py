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
from .geonode import descargar_geojson
from .grafo import Grafo, construir_grafo
from .heuristicas import (
    ParametrosCandidatos,
    ResultadoReduccion,
    reducir_alternativas,
)
from .mapa import exportar_mapa


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

