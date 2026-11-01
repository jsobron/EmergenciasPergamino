from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .alternativas import Alternativa, ResultadoAlternativas
from .ambulancias import Ambulancia
from .emergencias import Emergencia
from .establecimientos import Establecimiento, calcular_costo_destino


NIVELES_CANDIDATOS: dict[int, tuple[int, int]] = {
    1: (3, 2),
    2: (4, 3),
    3: (5, 4),
    4: (6, 4),
}

MOTIVO_FUERA_DE_K = "fuera_de_las_k_mas_cercanas"
MOTIVO_FUERA_DE_H = "fuera_de_los_h_mas_convenientes"


@dataclass(frozen=True)
class ParametrosCandidatos:
    nivel: int
    k: int
    h: int

    def __post_init__(self) -> None:
        for campo in ("nivel", "k", "h"):
            valor = getattr(self, campo)
            if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
                raise ValueError(f"{campo} debe ser un entero mayor que cero")

    @classmethod
    def desde_nivel(cls, nivel: int) -> "ParametrosCandidatos":
        if isinstance(nivel, bool) or not isinstance(nivel, int) or nivel not in NIVELES_CANDIDATOS:
            disponibles = ", ".join(str(numero) for numero in sorted(NIVELES_CANDIDATOS))
            raise ValueError(f"Nivel de candidatos inexistente: {nivel!r} (disponibles: {disponibles})")
        k, h = NIVELES_CANDIDATOS[nivel]
        return cls(nivel=nivel, k=k, h=h)


@dataclass(frozen=True)
class CandidatoAmbulancia:
    ambulancia_id: str
    distancia_m: float | None
    conservada: bool
    motivos_exclusion: list[str]


@dataclass(frozen=True)
class CandidatoEstablecimiento:
    establecimiento_id: str
    distancia_m: float | None
    penalizacion_m: float
    criterio_m: float | None
    conservado: bool
    motivos_exclusion: list[str]


@dataclass(frozen=True)
class SeleccionEmergencia:
    emergencia_id: str
    ambulancias: list[CandidatoAmbulancia]
    establecimientos: list[CandidatoEstablecimiento]

    @property
    def ambulancias_conservadas(self) -> list[CandidatoAmbulancia]:
        return [candidato for candidato in self.ambulancias if candidato.conservada]

    @property
    def ambulancias_excluidas(self) -> list[CandidatoAmbulancia]:
        return [candidato for candidato in self.ambulancias if not candidato.conservada]

    @property
    def establecimientos_conservados(self) -> list[CandidatoEstablecimiento]:
        return [
            candidato
            for candidato in self.establecimientos
            if candidato.conservado
        ]

    @property
    def establecimientos_excluidos(self) -> list[CandidatoEstablecimiento]:
        return [
            candidato
            for candidato in self.establecimientos
            if not candidato.conservado
        ]


@dataclass(frozen=True)
class OrdenEmergencia:
    emergencia_id: str
    gravedad: int
    ambulancias_compatibles: int
    minutos_espera: float


@dataclass(frozen=True)
class EstadisticasReduccion:
    alternativas_originales: int
    alternativas_factibles: int
    alternativas_no_factibles: int
    alternativas_tras_ambulancias: int
    alternativas_tras_establecimientos: int
    alternativas_reducidas: int
    descartadas_por_ambulancias: int
    descartadas_por_establecimientos: int
    porcentaje_reduccion: float
    motivos_no_factibles: dict[str, int]


@dataclass(frozen=True)
class ResultadoReduccion:
    parametros: ParametrosCandidatos
    selecciones: dict[str, SeleccionEmergencia]
    orden_emergencias: list[OrdenEmergencia]
    alternativas_originales: list[Alternativa]
    alternativas_factibles: list[Alternativa]
    alternativas_reducidas: list[Alternativa]
    estadisticas: EstadisticasReduccion


def _ruta_ambulancia(
    resultado: ResultadoAlternativas, ambulancia: Ambulancia, emergencia: Emergencia
) -> float | None:
    ruta = resultado.rutas_ambulancia_emergencia.get(
        f"{ambulancia.id}|{emergencia.id}"
    )
    return None if ruta is None else ruta.distancia_m


def _ruta_establecimiento(
    resultado: ResultadoAlternativas,
    emergencia: Emergencia,
    establecimiento: Establecimiento,
) -> float | None:
    ruta = resultado.rutas_emergencia_establecimiento.get(
        f"{emergencia.id}|{establecimiento.id}"
    )
    return None if ruta is None else ruta.distancia_m


def _motivos_ambulancia(
    ambulancia: Ambulancia, emergencia: Emergencia, distancia_m: float | None
) -> list[str]:
    motivos: list[str] = []
    if not ambulancia.disponible:
        motivos.append("ambulancia_no_disponible")
    if ambulancia.complejidad < emergencia.complejidad_requerida:
        motivos.append("complejidad_ambulancia_insuficiente")
    if ambulancia.capacidad_pacientes < emergencia.cantidad_pacientes:
        motivos.append("capacidad_ambulancia_insuficiente")
    if not all(
        equipo in ambulancia.equipamiento
        for equipo in emergencia.equipamiento_requerido
    ):
        motivos.append("equipamiento_faltante")
    if distancia_m is None:
        motivos.append("sin_ruta_hasta_emergencia")
    return motivos


def _motivos_establecimiento(
    establecimiento: Establecimiento,
    emergencia: Emergencia,
    distancia_m: float | None,
) -> list[str]:
    motivos: list[str] = []
    if not establecimiento.habilitado_destino:
        motivos.append("establecimiento_no_habilitado")
    if establecimiento.complejidad_maxima < emergencia.complejidad_requerida:
        motivos.append("complejidad_establecimiento_insuficiente")
    if distancia_m is None:
        motivos.append("sin_ruta_hasta_establecimiento")
    return motivos


def _clave_ambulancia(candidato: CandidatoAmbulancia) -> tuple[bool, float, str]:
    return (
        candidato.distancia_m is None,
        candidato.distancia_m if candidato.distancia_m is not None else 0.0,
        candidato.ambulancia_id,
    )


def _clave_establecimiento(
    candidato: CandidatoEstablecimiento,
) -> tuple[bool, float, str]:
    return (
        candidato.criterio_m is None,
        candidato.criterio_m if candidato.criterio_m is not None else 0.0,
        candidato.establecimiento_id,
    )


def _seleccionar_ambulancias(
    emergencia: Emergencia,
    ambulancias: list[Ambulancia],
    resultado: ResultadoAlternativas,
    k: int,
) -> list[CandidatoAmbulancia]:
    evaluados: list[CandidatoAmbulancia] = []
    for ambulancia in ambulancias:
        distancia = _ruta_ambulancia(resultado, ambulancia, emergencia)
        motivos = _motivos_ambulancia(ambulancia, emergencia, distancia)
        evaluados.append(
            CandidatoAmbulancia(
                ambulancia_id=ambulancia.id,
                distancia_m=distancia,
                conservada=False,
                motivos_exclusion=motivos,
            )
        )

    compatibles = sorted(
        (candidato for candidato in evaluados if not candidato.motivos_exclusion),
        key=_clave_ambulancia,
    )
    conservadas = {candidato.ambulancia_id for candidato in compatibles[:k]}

    resultado_candidatos: list[CandidatoAmbulancia] = []
    for candidato in evaluados:
        if candidato.ambulancia_id in conservadas:
            resultado_candidatos.append(
                CandidatoAmbulancia(
                    ambulancia_id=candidato.ambulancia_id,
                    distancia_m=candidato.distancia_m,
                    conservada=True,
                    motivos_exclusion=[],
                )
            )
        elif not candidato.motivos_exclusion:
            resultado_candidatos.append(
                CandidatoAmbulancia(
                    ambulancia_id=candidato.ambulancia_id,
                    distancia_m=candidato.distancia_m,
                    conservada=False,
                    motivos_exclusion=[MOTIVO_FUERA_DE_K],
                )
            )
        else:
            resultado_candidatos.append(candidato)

    resultado_candidatos.sort(key=_clave_ambulancia)
    return resultado_candidatos


def _seleccionar_establecimientos(
    emergencia: Emergencia,
    establecimientos: list[Establecimiento],
    resultado: ResultadoAlternativas,
    h: int,
) -> list[CandidatoEstablecimiento]:
    evaluados: list[CandidatoEstablecimiento] = []
    for establecimiento in establecimientos:
        distancia = _ruta_establecimiento(resultado, emergencia, establecimiento)
        motivos = _motivos_establecimiento(establecimiento, emergencia, distancia)
        criterio = None
        if distancia is not None:
            criterio = calcular_costo_destino(
                distancia, establecimiento
            ).costo_seleccion_metros
        evaluados.append(
            CandidatoEstablecimiento(
                establecimiento_id=establecimiento.id,
                distancia_m=distancia,
                penalizacion_m=establecimiento.penalizacion_metros,
                criterio_m=criterio,
                conservado=False,
                motivos_exclusion=motivos,
            )
        )

    compatibles = sorted(
        (candidato for candidato in evaluados if not candidato.motivos_exclusion),
        key=_clave_establecimiento,
    )
    conservados = {
        candidato.establecimiento_id for candidato in compatibles[:h]
    }

    resultado_candidatos: list[CandidatoEstablecimiento] = []
    for candidato in evaluados:
        if candidato.establecimiento_id in conservados:
            resultado_candidatos.append(
                CandidatoEstablecimiento(
                    establecimiento_id=candidato.establecimiento_id,
                    distancia_m=candidato.distancia_m,
                    penalizacion_m=candidato.penalizacion_m,
                    criterio_m=candidato.criterio_m,
                    conservado=True,
                    motivos_exclusion=[],
                )
            )
        elif not candidato.motivos_exclusion:
            resultado_candidatos.append(
                CandidatoEstablecimiento(
                    establecimiento_id=candidato.establecimiento_id,
                    distancia_m=candidato.distancia_m,
                    penalizacion_m=candidato.penalizacion_m,
                    criterio_m=candidato.criterio_m,
                    conservado=False,
                    motivos_exclusion=[MOTIVO_FUERA_DE_H],
                )
            )
        else:
            resultado_candidatos.append(candidato)

    resultado_candidatos.sort(key=_clave_establecimiento)
    return resultado_candidatos


def ordenar_emergencias(
    emergencias: list[Emergencia],
    ambulancias: list[Ambulancia],
    resultado: ResultadoAlternativas,
) -> list[OrdenEmergencia]:
    orden: list[OrdenEmergencia] = []
    for emergencia in emergencias:
        compatibles = sum(
            not _motivos_ambulancia(
                ambulancia,
                emergencia,
                _ruta_ambulancia(resultado, ambulancia, emergencia),
            )
            for ambulancia in ambulancias
        )
        orden.append(
            OrdenEmergencia(
                emergencia_id=emergencia.id,
                gravedad=emergencia.gravedad,
                ambulancias_compatibles=compatibles,
                minutos_espera=emergencia.minutos_espera,
            )
        )
    orden.sort(
        key=lambda item: (
            -item.gravedad,
            item.ambulancias_compatibles,
            -item.minutos_espera,
            item.emergencia_id,
        )
    )
    return orden


def reducir_alternativas(
    resultado: ResultadoAlternativas,
    ambulancias: list[Ambulancia],
    emergencias: list[Emergencia],
    establecimientos: list[Establecimiento],
    parametros: ParametrosCandidatos | None = None,
) -> ResultadoReduccion:
    parametros = parametros or ParametrosCandidatos.desde_nivel(1)
    selecciones = {
        emergencia.id: SeleccionEmergencia(
            emergencia_id=emergencia.id,
            ambulancias=_seleccionar_ambulancias(
                emergencia, ambulancias, resultado, parametros.k
            ),
            establecimientos=_seleccionar_establecimientos(
                emergencia, establecimientos, resultado, parametros.h
            ),
        )
        for emergencia in emergencias
    }

    factibles = [
        alternativa
        for alternativa in resultado.alternativas
        if alternativa.es_factible
    ]

    ambulancias_conservadas = {
        seleccion.emergencia_id: {
            candidato.ambulancia_id
            for candidato in seleccion.ambulancias_conservadas
        }
        for seleccion in selecciones.values()
    }
    establecimientos_conservados = {
        seleccion.emergencia_id: {
            candidato.establecimiento_id
            for candidato in seleccion.establecimientos_conservados
        }
        for seleccion in selecciones.values()
    }

    tras_ambulancias = [
        alternativa
        for alternativa in factibles
        if alternativa.ambulancia_id
        in ambulancias_conservadas.get(alternativa.emergencia_id, set())
    ]
    tras_establecimientos = [
        alternativa
        for alternativa in tras_ambulancias
        if alternativa.establecimiento_id
        in establecimientos_conservados.get(alternativa.emergencia_id, set())
    ]

    originales = len(resultado.alternativas)
    reducidas = len(tras_establecimientos)
    porcentaje = (
        0.0 if originales == 0 else (originales - reducidas) / originales * 100
    )
    motivos_no_factibles = Counter(
        motivo
        for alternativa in resultado.alternativas
        if not alternativa.es_factible
        for motivo in alternativa.motivos_descarte
    )
    estadisticas = EstadisticasReduccion(
        alternativas_originales=originales,
        alternativas_factibles=len(factibles),
        alternativas_no_factibles=originales - len(factibles),
        alternativas_tras_ambulancias=len(tras_ambulancias),
        alternativas_tras_establecimientos=len(tras_establecimientos),
        alternativas_reducidas=reducidas,
        descartadas_por_ambulancias=len(factibles) - len(tras_ambulancias),
        descartadas_por_establecimientos=(
            len(tras_ambulancias) - len(tras_establecimientos)
        ),
        porcentaje_reduccion=porcentaje,
        motivos_no_factibles=dict(sorted(motivos_no_factibles.items())),
    )

    return ResultadoReduccion(
        parametros=parametros,
        selecciones=selecciones,
        orden_emergencias=ordenar_emergencias(
            emergencias, ambulancias, resultado
        ),
        alternativas_originales=list(resultado.alternativas),
        alternativas_factibles=factibles,
        alternativas_reducidas=tras_establecimientos,
        estadisticas=estadisticas,
    )
