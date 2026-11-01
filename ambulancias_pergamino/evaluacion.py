from __future__ import annotations

from dataclasses import dataclass
from math import isclose

from .alternativas import Alternativa, ResultadoAlternativas
from .ambulancias import Ambulancia
from .asignacion import ResultadoAsignacion, comparar_niveles
from .emergencias import Emergencia
from .establecimientos import Establecimiento
from .simulacion import crear_simulacion


@dataclass(frozen=True)
class AsignacionResumen:
    emergencia_id: str
    ambulancia_id: str
    base_id: str
    establecimiento_id: str
    costo_seleccion: float


@dataclass(frozen=True)
class DiferenciaAsignacion:
    emergencia_id: str
    original: str | None
    escenario: str | None
    tipo: str


@dataclass(frozen=True)
class MetricasEscenario:
    etiqueta: str
    nivel: int | None
    alternativas_generadas: int
    alternativas_factibles: int
    alternativas_conservadas: int
    alternativas_evaluadas: int
    porcentaje_reduccion: float
    emergencias_atendidas: int
    emergencias_sin_asignar: int
    motivos_sin_asignar: dict[str, str]
    ambulancias_utilizadas: tuple[str, ...]
    establecimientos_seleccionados: tuple[str, ...]
    costo_total: float
    distancia_total: float
    penalizacion_total: float
    es_completa: bool
    es_optima: bool
    asignaciones: tuple[AsignacionResumen, ...]
    diferencias_respecto_original: tuple[DiferenciaAsignacion, ...]
    cantidad_completadas: int
    estados_finales_emergencias: dict[str, str]
    estados_finales_ambulancias: dict[str, str]


@dataclass(frozen=True)
class EvaluacionEscenarios:
    escenarios: tuple[MetricasEscenario, ...]
    original: MetricasEscenario
    niveles: tuple[MetricasEscenario, ...]
    nivel_recomendado: int | None
    perdida_por_heuristica: bool
    niveles_con_perdida: tuple[int, ...]
    todos_mismos_resultados: bool
    todos_mismos_costos: bool


def _texto_asignacion(alternativa: Alternativa) -> str:
    return f"{alternativa.ambulancia_id} -> {alternativa.establecimiento_id}"


def _mapa_asignaciones(
    asignacion: ResultadoAsignacion,
) -> dict[str, str]:
    return {
        alternativa.emergencia_id: _texto_asignacion(alternativa)
        for alternativa in asignacion.alternativas
    }


def _diferencias_respecto_original(
    original: dict[str, str],
    escenario: dict[str, str],
) -> tuple[DiferenciaAsignacion, ...]:
    diferencias: list[DiferenciaAsignacion] = []
    for emergencia_id in sorted(set(original) | set(escenario)):
        antes = original.get(emergencia_id)
        despues = escenario.get(emergencia_id)
        if antes == despues:
            continue
        if antes is None:
            tipo = "asignada_en_escenario"
        elif despues is None:
            tipo = "sin_asignar_en_escenario"
        else:
            tipo = "cambiada"
        diferencias.append(
            DiferenciaAsignacion(
                emergencia_id=emergencia_id,
                original=antes,
                escenario=despues,
                tipo=tipo,
            )
        )
    return tuple(diferencias)


def _firma_asignaciones(
    metricas: MetricasEscenario,
) -> tuple[tuple[str, str, str], ...]:
    return tuple(
        sorted(
            (
                asignacion.emergencia_id,
                asignacion.ambulancia_id,
                asignacion.establecimiento_id,
            )
            for asignacion in metricas.asignaciones
        )
    )


def _metricas_escenario(
    asignacion: ResultadoAsignacion,
    resultado_alternativas: ResultadoAlternativas,
    ambulancias: list[Ambulancia],
    emergencias: list[Emergencia],
    establecimientos: list[Establecimiento],
    alternativas_generadas: int,
    alternativas_factibles: int,
    original: dict[str, str],
) -> MetricasEscenario:
    simulacion = crear_simulacion(
        asignacion,
        resultado_alternativas,
        ambulancias,
        emergencias,
        establecimientos,
    )
    simulacion.avanzar_hasta_final()
    resultado = simulacion.resultado()

    if not isclose(
        resultado.costo_total,
        asignacion.costo_total,
        rel_tol=1e-9,
        abs_tol=1e-6,
    ):
        raise ValueError(
            f"El costo de la simulación de {asignacion.etiqueta} no coincide "
            "con el costo de la asignación"
        )

    conservadas = asignacion.alternativas_candidatas
    porcentaje_reduccion = (
        0.0
        if alternativas_factibles == 0
        else round(
            100.0 * (1.0 - conservadas / alternativas_factibles),
            2,
        )
    )
    asignaciones = tuple(
        AsignacionResumen(
            emergencia_id=atencion.emergencia_id,
            ambulancia_id=atencion.ambulancia_id,
            base_id=atencion.base_id,
            establecimiento_id=atencion.establecimiento_id,
            costo_seleccion=atencion.costo_seleccion,
        )
        for atencion in resultado.atenciones
    )
    return MetricasEscenario(
        etiqueta=asignacion.etiqueta,
        nivel=(
            None
            if asignacion.parametros is None
            else asignacion.parametros.nivel
        ),
        alternativas_generadas=alternativas_generadas,
        alternativas_factibles=alternativas_factibles,
        alternativas_conservadas=conservadas,
        alternativas_evaluadas=asignacion.alternativas_evaluadas,
        porcentaje_reduccion=porcentaje_reduccion,
        emergencias_atendidas=resultado.cantidad_atenciones,
        emergencias_sin_asignar=resultado.cantidad_sin_asignar,
        motivos_sin_asignar=dict(resultado.motivos_sin_asignar),
        ambulancias_utilizadas=tuple(asignacion.ambulancias_utilizadas),
        establecimientos_seleccionados=tuple(
            asignacion.establecimientos_seleccionados
        ),
        costo_total=resultado.costo_total,
        distancia_total=resultado.distancia_total,
        penalizacion_total=resultado.penalizacion_total,
        es_completa=resultado.es_completa,
        es_optima=asignacion.es_optima,
        asignaciones=asignaciones,
        diferencias_respecto_original=_diferencias_respecto_original(
            original, _mapa_asignaciones(asignacion)
        ),
        cantidad_completadas=resultado.cantidad_completadas,
        estados_finales_emergencias={
            emergencia.emergencia_id: emergencia.estado
            for emergencia in resultado.emergencias
        },
        estados_finales_ambulancias={
            ambulancia.ambulancia_id: ambulancia.estado
            for ambulancia in resultado.ambulancias
        },
    )


def evaluar_escenarios(
    resultado_alternativas: ResultadoAlternativas,
    ambulancias: list[Ambulancia],
    emergencias: list[Emergencia],
    establecimientos: list[Establecimiento],
    niveles: tuple[int, ...] = (1, 2, 3, 4),
) -> EvaluacionEscenarios:
    comparacion = comparar_niveles(
        resultado_alternativas,
        ambulancias,
        emergencias,
        establecimientos,
        niveles,
    )
    alternativas_generadas = len(resultado_alternativas.alternativas)
    alternativas_factibles = sum(
        1
        for alternativa in resultado_alternativas.alternativas
        if alternativa.es_factible
    )
    original = _mapa_asignaciones(comparacion.original)
    escenarios = tuple(
        _metricas_escenario(
            asignacion,
            resultado_alternativas,
            ambulancias,
            emergencias,
            establecimientos,
            alternativas_generadas,
            alternativas_factibles,
            original,
        )
        for asignacion in (comparacion.original, *comparacion.niveles)
    )
    metricas_original = escenarios[0]
    metricas_niveles = escenarios[1:]
    return EvaluacionEscenarios(
        escenarios=escenarios,
        original=metricas_original,
        niveles=metricas_niveles,
        nivel_recomendado=comparacion.nivel_recomendado,
        perdida_por_heuristica=comparacion.perdida_por_heuristica,
        niveles_con_perdida=tuple(comparacion.niveles_con_perdida),
        todos_mismos_resultados=all(
            _firma_asignaciones(metricas)
            == _firma_asignaciones(metricas_original)
            for metricas in escenarios
        ),
        todos_mismos_costos=all(
            isclose(
                metricas.costo_total,
                metricas_original.costo_total,
                rel_tol=1e-9,
                abs_tol=1e-6,
            )
            for metricas in escenarios
        ),
    )
