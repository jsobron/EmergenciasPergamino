from __future__ import annotations

from dataclasses import dataclass

from .alternativas import Alternativa, ResultadoAlternativas
from .ambulancias import Ambulancia
from .emergencias import Emergencia
from .establecimientos import Establecimiento
from .heuristicas import (
    ParametrosCandidatos,
    ordenar_emergencias,
    reducir_alternativas,
)


MOTIVO_SIN_ALTERNATIVAS = "sin_alternativas_factibles"
MOTIVO_AMBULANCIAS_USADAS = "ambulancias_candidatas_ya_utilizadas"
MOTIVO_SIN_COMBINACION = "sin_combinacion_compatible"


@dataclass(frozen=True)
class ResultadoAsignacion:
    etiqueta: str
    parametros: ParametrosCandidatos | None
    alternativas: list[Alternativa]
    emergencias_atendidas: list[str]
    emergencias_sin_asignar: list[str]
    motivos_sin_asignar: dict[str, str]
    ambulancias_utilizadas: list[str]
    establecimientos_seleccionados: list[str]
    costo_total: float
    es_completa: bool
    es_optima: bool
    alternativas_candidatas: int
    alternativas_evaluadas: int
    emergencias_con_candidatos: int
    orden_prioridad: list[str]

    @property
    def cantidad_atendidas(self) -> int:
        return len(self.emergencias_atendidas)

    @property
    def cantidad_sin_asignar(self) -> int:
        return len(self.emergencias_sin_asignar)

    @property
    def cantidad_emergencias(self) -> int:
        return len(self.orden_prioridad)


@dataclass(frozen=True)
class ComparacionAsignaciones:
    original: ResultadoAsignacion
    niveles: list[ResultadoAsignacion]
    nivel_recomendado: int | None
    perdida_por_heuristica: bool
    niveles_con_perdida: list[int]
    diferencias: dict[int, str]


def _normalizar_prioridad(
    emergencias: list[Emergencia], orden_prioridad: list[str]
) -> list[str]:
    ids = [emergencia.id for emergencia in emergencias]
    validos = set(ids)
    orden: list[str] = []
    vistos: set[str] = set()
    for emergencia_id in orden_prioridad:
        if emergencia_id in validos and emergencia_id not in vistos:
            orden.append(emergencia_id)
            vistos.add(emergencia_id)
    orden.extend(sorted(validos - vistos))
    return orden


def _preferencia_alternativa(alternativa: Alternativa) -> tuple[float, str]:
    costo = (
        float("inf")
        if alternativa.costo_seleccion is None
        else alternativa.costo_seleccion
    )
    return (costo, alternativa.establecimiento_id)


def _candidatos_por_emergencia(
    alternativas: list[Alternativa], orden: list[str]
) -> tuple[list[Alternativa], dict[str, list[Alternativa]]]:
    ids = set(orden)
    factibles = [
        alternativa
        for alternativa in alternativas
        if alternativa.es_factible
        and alternativa.costo_seleccion is not None
        and alternativa.emergencia_id in ids
    ]
    por_emergencia: dict[str, dict[str, Alternativa]] = {
        emergencia_id: {} for emergencia_id in orden
    }
    for alternativa in factibles:
        por_ambulancia = por_emergencia[alternativa.emergencia_id]
        actual = por_ambulancia.get(alternativa.ambulancia_id)
        if (
            actual is None
            or _preferencia_alternativa(alternativa)
            < _preferencia_alternativa(actual)
        ):
            por_ambulancia[alternativa.ambulancia_id] = alternativa

    candidatos = {
        emergencia_id: sorted(
            por_ambulancia.values(),
            key=lambda alternativa: (
                _preferencia_alternativa(alternativa),
                alternativa.ambulancia_id,
            ),
        )
        for emergencia_id, por_ambulancia in por_emergencia.items()
    }
    return factibles, candidatos


def clave_optimizacion(resultado: ResultadoAsignacion) -> tuple[int, tuple[int, ...], float]:
    atendidas = set(resultado.emergencias_atendidas)
    prioridad = tuple(
        1 if emergencia_id in atendidas else 0
        for emergencia_id in resultado.orden_prioridad
    )
    return (
        len(atendidas),
        prioridad,
        -round(resultado.costo_total, 6),
    )


def clave_identificadores(resultado: ResultadoAsignacion) -> tuple[tuple[str, str, str], ...]:
    return tuple(
        sorted(
            (
                alternativa.emergencia_id,
                alternativa.ambulancia_id,
                alternativa.establecimiento_id,
            )
            for alternativa in resultado.alternativas
        )
    )


def es_mejor_asignacion(
    candidata: ResultadoAsignacion, actual: ResultadoAsignacion
) -> bool:
    clave_candidata = clave_optimizacion(candidata)
    clave_actual = clave_optimizacion(actual)
    if clave_candidata != clave_actual:
        return clave_candidata > clave_actual
    return clave_identificadores(candidata) < clave_identificadores(actual)


def _clave_parcial(
    seleccionadas: list[Alternativa], orden: list[str]
) -> tuple[tuple[int, tuple[int, ...], float], tuple[tuple[str, str, str], ...]]:
    atendidas = {alternativa.emergencia_id for alternativa in seleccionadas}
    prioridad = tuple(
        1 if emergencia_id in atendidas else 0 for emergencia_id in orden
    )
    costo = sum(
        alternativa.costo_seleccion or 0.0 for alternativa in seleccionadas
    )
    identificadores = tuple(
        sorted(
            (
                alternativa.emergencia_id,
                alternativa.ambulancia_id,
                alternativa.establecimiento_id,
            )
            for alternativa in seleccionadas
        )
    )
    return (len(atendidas), prioridad, -round(costo, 6)), identificadores


def _buscar_mejor_asignacion(
    candidatos: dict[str, list[Alternativa]], orden: list[str]
) -> list[Alternativa]:
    mejor_seleccion: list[Alternativa] = []
    mejor_clave: tuple[int, tuple[int, ...], float] | None = None
    mejor_identificadores: tuple[tuple[str, str, str], ...] | None = None
    seleccionadas: list[Alternativa] = []
    usadas: set[str] = set()

    def evaluar() -> None:
        nonlocal mejor_seleccion, mejor_clave, mejor_identificadores
        clave, identificadores = _clave_parcial(seleccionadas, orden)
        if (
            mejor_clave is None
            or clave > mejor_clave
            or (clave == mejor_clave and identificadores < mejor_identificadores)
        ):
            mejor_clave = clave
            mejor_identificadores = identificadores
            mejor_seleccion = list(seleccionadas)

    def explorar(indice: int) -> None:
        if (
            mejor_clave is not None
            and len(seleccionadas) + (len(orden) - indice) < mejor_clave[0]
        ):
            return
        if indice == len(orden):
            evaluar()
            return

        emergencia_id = orden[indice]
        for alternativa in candidatos.get(emergencia_id, []):
            if alternativa.ambulancia_id in usadas:
                continue
            usadas.add(alternativa.ambulancia_id)
            seleccionadas.append(alternativa)
            explorar(indice + 1)
            seleccionadas.pop()
            usadas.remove(alternativa.ambulancia_id)
        explorar(indice + 1)

    explorar(0)
    return mejor_seleccion


def _motivo_sin_asignar(
    emergencia_id: str,
    candidatos: dict[str, list[Alternativa]],
    ambulancias_utilizadas: set[str],
) -> str:
    candidatas = candidatos.get(emergencia_id, [])
    if not candidatas:
        return MOTIVO_SIN_ALTERNATIVAS
    ambulancias_candidatas = {
        alternativa.ambulancia_id for alternativa in candidatas
    }
    if ambulancias_candidatas <= ambulancias_utilizadas:
        return MOTIVO_AMBULANCIAS_USADAS
    return MOTIVO_SIN_COMBINACION


def asignar_global(
    alternativas: list[Alternativa],
    emergencias: list[Emergencia],
    orden_prioridad: list[str],
    etiqueta: str = "asignacion",
    parametros: ParametrosCandidatos | None = None,
) -> ResultadoAsignacion:
    orden = _normalizar_prioridad(emergencias, orden_prioridad)
    factibles, candidatos = _candidatos_por_emergencia(alternativas, orden)
    seleccionadas = _buscar_mejor_asignacion(candidatos, orden)

    atendidas_set = {alternativa.emergencia_id for alternativa in seleccionadas}
    atendidas = [
        emergencia_id for emergencia_id in orden if emergencia_id in atendidas_set
    ]
    sin_asignar = [
        emergencia_id
        for emergencia_id in orden
        if emergencia_id not in atendidas_set
    ]
    ambulancias_utilizadas = sorted(
        {alternativa.ambulancia_id for alternativa in seleccionadas}
    )
    establecimientos_seleccionados = sorted(
        {alternativa.establecimiento_id for alternativa in seleccionadas}
    )
    motivos = {
        emergencia_id: _motivo_sin_asignar(
            emergencia_id, candidatos, set(ambulancias_utilizadas)
        )
        for emergencia_id in sin_asignar
    }

    return ResultadoAsignacion(
        etiqueta=etiqueta,
        parametros=parametros,
        alternativas=seleccionadas,
        emergencias_atendidas=atendidas,
        emergencias_sin_asignar=sin_asignar,
        motivos_sin_asignar=motivos,
        ambulancias_utilizadas=ambulancias_utilizadas,
        establecimientos_seleccionados=establecimientos_seleccionados,
        costo_total=sum(
            alternativa.costo_seleccion or 0.0
            for alternativa in seleccionadas
        ),
        es_completa=len(atendidas) == len(orden),
        es_optima=True,
        alternativas_candidatas=len(factibles),
        alternativas_evaluadas=sum(
            len(candidatas) for candidatas in candidatos.values()
        ),
        emergencias_con_candidatos=sum(
            1 for candidatas in candidatos.values() if candidatas
        ),
        orden_prioridad=orden,
    )


def asignar_con_nivel(
    resultado: ResultadoAlternativas,
    ambulancias: list[Ambulancia],
    emergencias: list[Emergencia],
    establecimientos: list[Establecimiento],
    nivel: int,
) -> ResultadoAsignacion:
    parametros = ParametrosCandidatos.desde_nivel(nivel)
    reduccion = reducir_alternativas(
        resultado, ambulancias, emergencias, establecimientos, parametros
    )
    orden = [item.emergencia_id for item in reduccion.orden_emergencias]
    return asignar_global(
        reduccion.alternativas_reducidas,
        emergencias,
        orden,
        etiqueta=f"nivel {nivel}",
        parametros=parametros,
    )


def asignar_original(
    resultado: ResultadoAlternativas,
    ambulancias: list[Ambulancia],
    emergencias: list[Emergencia],
) -> ResultadoAsignacion:
    orden = [
        item.emergencia_id
        for item in ordenar_emergencias(emergencias, ambulancias, resultado)
    ]
    return asignar_global(
        resultado.alternativas,
        emergencias,
        orden,
        etiqueta="original",
    )


def _describir_diferencia(
    resultado: ResultadoAsignacion, original: ResultadoAsignacion
) -> str | None:
    if not es_mejor_asignacion(original, resultado):
        return None
    if resultado.cantidad_atendidas != original.cantidad_atendidas:
        return (
            f"atiende {resultado.cantidad_atendidas} emergencias; "
            f"el conjunto original atiende {original.cantidad_atendidas}"
        )
    if (
        clave_optimizacion(resultado)[1]
        != clave_optimizacion(original)[1]
    ):
        return (
            "atiende la misma cantidad de emergencias, pero con un "
            "conjunto de menor prioridad"
        )
    if round(resultado.costo_total, 6) > round(original.costo_total, 6):
        return (
            f"costo total {resultado.costo_total:.0f} m mayor que el "
            f"original ({original.costo_total:.0f} m)"
        )
    return "diferencia determinada por los identificadores de la asignación"


def comparar_niveles(
    resultado: ResultadoAlternativas,
    ambulancias: list[Ambulancia],
    emergencias: list[Emergencia],
    establecimientos: list[Establecimiento],
    niveles: tuple[int, ...] = (1, 2, 3, 4),
) -> ComparacionAsignaciones:
    original = asignar_original(resultado, ambulancias, emergencias)
    resultados = [
        asignar_con_nivel(
            resultado, ambulancias, emergencias, establecimientos, nivel
        )
        for nivel in niveles
    ]

    mejor = resultados[0] if resultados else None
    for resultado_nivel in resultados[1:]:
        if es_mejor_asignacion(resultado_nivel, mejor):
            mejor = resultado_nivel
    nivel_recomendado = (
        mejor.parametros.nivel
        if mejor is not None and mejor.parametros is not None
        else None
    )

    niveles_con_perdida = [
        resultado_nivel.parametros.nivel
        for resultado_nivel in resultados
        if resultado_nivel.parametros is not None
        and es_mejor_asignacion(original, resultado_nivel)
    ]
    diferencias = {
        resultado_nivel.parametros.nivel: descripcion
        for resultado_nivel in resultados
        if resultado_nivel.parametros is not None
        and (
            descripcion := _describir_diferencia(resultado_nivel, original)
        )
        is not None
    }

    return ComparacionAsignaciones(
        original=original,
        niveles=resultados,
        nivel_recomendado=nivel_recomendado,
        perdida_por_heuristica=bool(niveles_con_perdida),
        niveles_con_perdida=niveles_con_perdida,
        diferencias=diferencias,
    )
