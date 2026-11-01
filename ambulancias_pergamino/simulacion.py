from __future__ import annotations

from dataclasses import dataclass
from math import isclose

from .alternativas import Alternativa, ResultadoAlternativas
from .ambulancias import Ambulancia
from .asignacion import ResultadoAsignacion
from .emergencias import Emergencia
from .establecimientos import Establecimiento


ESTADO_EMERGENCIA_ASIGNADA = "asignada"
ESTADO_EMERGENCIA_EN_ATENCION = "en_atencion"
ESTADO_EMERGENCIA_TRASLADADA = "trasladada"
ESTADO_EMERGENCIA_FINALIZADA = "finalizada"
ESTADO_EMERGENCIA_SIN_ASIGNACION = "sin_asignacion"

ESTADO_AMBULANCIA_DISPONIBLE = "disponible"
ESTADO_AMBULANCIA_ASIGNADA = "asignada"
ESTADO_AMBULANCIA_EN_CAMINO = "en_camino"
ESTADO_AMBULANCIA_EN_ATENCION = "en_atencion"
ESTADO_AMBULANCIA_TRASLADANDO = "trasladando"
ESTADO_AMBULANCIA_FINALIZADA = "finalizada"

MOTIVO_NO_INFORMADO = "motivo_no_informado"


@dataclass(frozen=True)
class EtapaSimulacion:
    paso: int
    clave: str
    nombre: str


ETAPAS_SIMULACION = (
    EtapaSimulacion(0, "asignada", "Asignada"),
    EtapaSimulacion(1, "en_camino", "En camino"),
    EtapaSimulacion(2, "en_atencion", "En atención"),
    EtapaSimulacion(3, "trasladando", "Trasladando"),
    EtapaSimulacion(4, "finalizada", "Finalizada"),
)
PASO_INICIAL = 0
PASO_FINAL = ETAPAS_SIMULACION[-1].paso

_ESTADO_EMERGENCIA_POR_PASO = {
    0: ESTADO_EMERGENCIA_ASIGNADA,
    1: ESTADO_EMERGENCIA_ASIGNADA,
    2: ESTADO_EMERGENCIA_EN_ATENCION,
    3: ESTADO_EMERGENCIA_TRASLADADA,
    4: ESTADO_EMERGENCIA_FINALIZADA,
}
_ESTADO_AMBULANCIA_POR_PASO = {
    0: ESTADO_AMBULANCIA_ASIGNADA,
    1: ESTADO_AMBULANCIA_EN_CAMINO,
    2: ESTADO_AMBULANCIA_EN_ATENCION,
    3: ESTADO_AMBULANCIA_TRASLADANDO,
    4: ESTADO_AMBULANCIA_FINALIZADA,
}


@dataclass(frozen=True)
class TramoSimulado:
    origen_id: str
    destino_id: str
    origen_nodo_id: str
    destino_nodo_id: str
    distancia_m: float
    camino: tuple[str, ...]


@dataclass(frozen=True)
class AtencionSimulada:
    emergencia_id: str
    ambulancia_id: str
    base_id: str
    establecimiento_id: str
    distancia_ambulancia_emergencia_m: float
    distancia_emergencia_establecimiento_m: float
    distancia_total_m: float
    penalizacion_establecimiento_m: float
    costo_seleccion: float
    tramo_ambulancia_emergencia: TramoSimulado
    tramo_emergencia_establecimiento: TramoSimulado
    estado_emergencia: str
    estado_ambulancia: str
    completada: bool


@dataclass(frozen=True)
class EstadoEmergenciaSimulada:
    emergencia_id: str
    estado: str
    ambulancia_id: str | None
    establecimiento_id: str | None
    motivo_sin_asignar: str | None
    completada: bool


@dataclass(frozen=True)
class EstadoAmbulanciaSimulada:
    ambulancia_id: str
    base_id: str
    estado: str
    emergencia_id: str | None


@dataclass(frozen=True)
class ResultadoSimulacion:
    etiqueta_asignacion: str
    paso: int
    etapa: str
    nombre_etapa: str
    total_pasos: int
    es_final: bool
    atenciones: tuple[AtencionSimulada, ...]
    emergencias: tuple[EstadoEmergenciaSimulada, ...]
    ambulancias: tuple[EstadoAmbulanciaSimulada, ...]
    emergencias_sin_asignar: tuple[str, ...]
    motivos_sin_asignar: dict[str, str]
    costo_total: float
    distancia_total: float
    penalizacion_total: float
    cantidad_atenciones: int
    cantidad_completadas: int
    cantidad_sin_asignar: int
    es_completa: bool


@dataclass(frozen=True)
class _AtencionProgramada:
    emergencia_id: str
    ambulancia_id: str
    base_id: str
    establecimiento_id: str
    distancia_ambulancia_emergencia_m: float
    distancia_emergencia_establecimiento_m: float
    distancia_total_m: float
    penalizacion_establecimiento_m: float
    costo_seleccion: float
    tramo_ambulancia_emergencia: TramoSimulado
    tramo_emergencia_establecimiento: TramoSimulado


def _verificar_distancia(
    valor_ruta: float | None,
    valor_alternativa: float | None,
    descripcion: str,
) -> float:
    if valor_ruta is None or valor_alternativa is None:
        raise ValueError(f"{descripcion}: la ruta no tiene distancia")
    if not isclose(valor_ruta, valor_alternativa, rel_tol=1e-9, abs_tol=1e-6):
        raise ValueError(
            f"{descripcion}: la distancia de la ruta no coincide con la alternativa"
        )
    return valor_alternativa


def _verificar_costo(alternativa: Alternativa) -> tuple[float, float, float, float]:
    if not alternativa.es_factible:
        raise ValueError(
            f"La alternativa {alternativa.emergencia_id}|"
            f"{alternativa.ambulancia_id} no es factible"
        )
    if alternativa.distancia_ambulancia_emergencia_m is None:
        raise ValueError("El tramo ambulancia -> emergencia no tiene distancia")
    if alternativa.distancia_emergencia_establecimiento_m is None:
        raise ValueError("El tramo emergencia -> establecimiento no tiene distancia")
    if alternativa.distancia_total_m is None:
        raise ValueError("La alternativa no tiene distancia total")
    if alternativa.costo_seleccion is None:
        raise ValueError("La alternativa no tiene costo de selección")
    distancia_inicial = alternativa.distancia_ambulancia_emergencia_m
    distancia_destino = alternativa.distancia_emergencia_establecimiento_m
    if not isclose(
        distancia_inicial + distancia_destino,
        alternativa.distancia_total_m,
        rel_tol=1e-9,
        abs_tol=1e-6,
    ):
        raise ValueError("La distancia total no coincide con la suma de los tramos")
    if not isclose(
        alternativa.distancia_total_m + alternativa.penalizacion_establecimiento_m,
        alternativa.costo_seleccion,
        rel_tol=1e-9,
        abs_tol=1e-6,
    ):
        raise ValueError("El costo no coincide con distancia total más penalización")
    return (
        distancia_inicial,
        distancia_destino,
        alternativa.distancia_total_m,
        alternativa.costo_seleccion,
    )


def _crear_atencion_programada(
    alternativa: Alternativa,
    resultado_alternativas: ResultadoAlternativas,
    ambulancias_por_id: dict[str, Ambulancia],
    emergencias_por_id: dict[str, Emergencia],
    establecimientos_por_id: dict[str, Establecimiento],
) -> _AtencionProgramada:
    ambulancia = ambulancias_por_id.get(alternativa.ambulancia_id)
    emergencia = emergencias_por_id.get(alternativa.emergencia_id)
    establecimiento = establecimientos_por_id.get(alternativa.establecimiento_id)
    if ambulancia is None:
        raise ValueError(f"Ambulancia inexistente: {alternativa.ambulancia_id}")
    if emergencia is None:
        raise ValueError(f"Emergencia inexistente: {alternativa.emergencia_id}")
    if establecimiento is None:
        raise ValueError(
            f"Establecimiento inexistente: {alternativa.establecimiento_id}"
        )

    distancia_inicial, distancia_destino, distancia_total, costo = _verificar_costo(
        alternativa
    )
    ruta_inicial = resultado_alternativas.rutas_ambulancia_emergencia.get(
        f"{ambulancia.id}|{emergencia.id}"
    )
    ruta_destino = resultado_alternativas.rutas_emergencia_establecimiento.get(
        f"{emergencia.id}|{establecimiento.id}"
    )
    if ruta_inicial is None:
        raise ValueError(
            f"Falta la ruta {ambulancia.id}|{emergencia.id} en las alternativas"
        )
    if ruta_destino is None:
        raise ValueError(
            f"Falta la ruta {emergencia.id}|{establecimiento.id} en las alternativas"
        )
    distancia_inicial = _verificar_distancia(
        ruta_inicial.distancia_m,
        distancia_inicial,
        f"Ruta {ambulancia.id}|{emergencia.id}",
    )
    distancia_destino = _verificar_distancia(
        ruta_destino.distancia_m,
        distancia_destino,
        f"Ruta {emergencia.id}|{establecimiento.id}",
    )

    return _AtencionProgramada(
        emergencia_id=emergencia.id,
        ambulancia_id=ambulancia.id,
        base_id=ambulancia.base_id,
        establecimiento_id=establecimiento.id,
        distancia_ambulancia_emergencia_m=distancia_inicial,
        distancia_emergencia_establecimiento_m=distancia_destino,
        distancia_total_m=distancia_total,
        penalizacion_establecimiento_m=alternativa.penalizacion_establecimiento_m,
        costo_seleccion=costo,
        tramo_ambulancia_emergencia=TramoSimulado(
            origen_id=ambulancia.id,
            destino_id=emergencia.id,
            origen_nodo_id=ambulancia.nodo_id,
            destino_nodo_id=emergencia.nodo_id,
            distancia_m=distancia_inicial,
            camino=tuple(ruta_inicial.camino),
        ),
        tramo_emergencia_establecimiento=TramoSimulado(
            origen_id=emergencia.id,
            destino_id=establecimiento.id,
            origen_nodo_id=emergencia.nodo_id,
            destino_nodo_id=establecimiento.nodo_id,
            distancia_m=distancia_destino,
            camino=tuple(ruta_destino.camino),
        ),
    )


class Simulacion:
    def __init__(
        self,
        atenciones: tuple[_AtencionProgramada, ...],
        emergencias: tuple[Emergencia, ...],
        ambulancias: tuple[Ambulancia, ...],
        motivos_sin_asignar: dict[str, str],
        etiqueta_asignacion: str,
    ) -> None:
        self._atenciones = atenciones
        self._emergencias = emergencias
        self._ambulancias = ambulancias
        self._motivos_sin_asignar = dict(motivos_sin_asignar)
        self._etiqueta_asignacion = etiqueta_asignacion
        self._paso = PASO_INICIAL

    @property
    def paso_actual(self) -> int:
        return self._paso

    @property
    def total_pasos(self) -> int:
        return PASO_FINAL

    @property
    def es_final(self) -> bool:
        return self._paso == PASO_FINAL

    def avanzar(self, pasos: int = 1) -> None:
        if isinstance(pasos, bool) or not isinstance(pasos, int):
            raise ValueError("pasos debe ser un entero mayor que cero")
        if pasos <= 0:
            raise ValueError("pasos debe ser un entero mayor que cero")
        if self._paso + pasos > PASO_FINAL:
            raise ValueError(
                f"No se puede avanzar {pasos} paso(s): "
                f"la simulación está en el paso {self._paso} de {PASO_FINAL}"
            )
        self._paso += pasos

    def avanzar_hasta_final(self) -> None:
        self._paso = PASO_FINAL

    def resultado(self) -> ResultadoSimulacion:
        etapa = ETAPAS_SIMULACION[self._paso]
        atenciones = tuple(
            self._crear_atencion_simulada(atencion)
            for atencion in self._atenciones
        )
        emergencias = tuple(
            self._crear_estado_emergencia(emergencia)
            for emergencia in self._emergencias
        )
        ambulancias = tuple(
            self._crear_estado_ambulancia(ambulancia)
            for ambulancia in self._ambulancias
        )
        asignadas = {atencion.emergencia_id for atencion in self._atenciones}
        sin_asignar = tuple(
            emergencia.id
            for emergencia in self._emergencias
            if emergencia.id not in asignadas
        )
        motivos = {
            emergencia_id: self._motivos_sin_asignar.get(
                emergencia_id, MOTIVO_NO_INFORMADO
            )
            for emergencia_id in sin_asignar
        }
        costo_total = sum(
            atencion.costo_seleccion for atencion in self._atenciones
        )
        distancia_total = sum(
            atencion.distancia_total_m for atencion in self._atenciones
        )
        penalizacion_total = sum(
            atencion.penalizacion_establecimiento_m
            for atencion in self._atenciones
        )
        cantidad_completadas = sum(
            atencion.completada for atencion in atenciones
        )
        return ResultadoSimulacion(
            etiqueta_asignacion=self._etiqueta_asignacion,
            paso=self._paso,
            etapa=etapa.clave,
            nombre_etapa=etapa.nombre,
            total_pasos=PASO_FINAL,
            es_final=self.es_final,
            atenciones=atenciones,
            emergencias=emergencias,
            ambulancias=ambulancias,
            emergencias_sin_asignar=sin_asignar,
            motivos_sin_asignar=motivos,
            costo_total=costo_total,
            distancia_total=distancia_total,
            penalizacion_total=penalizacion_total,
            cantidad_atenciones=len(atenciones),
            cantidad_completadas=cantidad_completadas,
            cantidad_sin_asignar=len(sin_asignar),
            es_completa=not sin_asignar,
        )

    def _crear_atencion_simulada(
        self, atencion: _AtencionProgramada
    ) -> AtencionSimulada:
        return AtencionSimulada(
            emergencia_id=atencion.emergencia_id,
            ambulancia_id=atencion.ambulancia_id,
            base_id=atencion.base_id,
            establecimiento_id=atencion.establecimiento_id,
            distancia_ambulancia_emergencia_m=(
                atencion.distancia_ambulancia_emergencia_m
            ),
            distancia_emergencia_establecimiento_m=(
                atencion.distancia_emergencia_establecimiento_m
            ),
            distancia_total_m=atencion.distancia_total_m,
            penalizacion_establecimiento_m=(
                atencion.penalizacion_establecimiento_m
            ),
            costo_seleccion=atencion.costo_seleccion,
            tramo_ambulancia_emergencia=atencion.tramo_ambulancia_emergencia,
            tramo_emergencia_establecimiento=(
                atencion.tramo_emergencia_establecimiento
            ),
            estado_emergencia=_ESTADO_EMERGENCIA_POR_PASO[self._paso],
            estado_ambulancia=_ESTADO_AMBULANCIA_POR_PASO[self._paso],
            completada=self.es_final,
        )

    def _crear_estado_emergencia(
        self, emergencia: Emergencia
    ) -> EstadoEmergenciaSimulada:
        atencion = next(
            (
                atencion
                for atencion in self._atenciones
                if atencion.emergencia_id == emergencia.id
            ),
            None,
        )
        if atencion is None:
            return EstadoEmergenciaSimulada(
                emergencia_id=emergencia.id,
                estado=ESTADO_EMERGENCIA_SIN_ASIGNACION,
                ambulancia_id=None,
                establecimiento_id=None,
                motivo_sin_asignar=self._motivos_sin_asignar.get(
                    emergencia.id, MOTIVO_NO_INFORMADO
                ),
                completada=False,
            )
        return EstadoEmergenciaSimulada(
            emergencia_id=emergencia.id,
            estado=_ESTADO_EMERGENCIA_POR_PASO[self._paso],
            ambulancia_id=atencion.ambulancia_id,
            establecimiento_id=atencion.establecimiento_id,
            motivo_sin_asignar=None,
            completada=self.es_final,
        )

    def _crear_estado_ambulancia(
        self, ambulancia: Ambulancia
    ) -> EstadoAmbulanciaSimulada:
        atencion = next(
            (
                atencion
                for atencion in self._atenciones
                if atencion.ambulancia_id == ambulancia.id
            ),
            None,
        )
        if atencion is None:
            return EstadoAmbulanciaSimulada(
                ambulancia_id=ambulancia.id,
                base_id=ambulancia.base_id,
                estado=ESTADO_AMBULANCIA_DISPONIBLE,
                emergencia_id=None,
            )
        return EstadoAmbulanciaSimulada(
            ambulancia_id=ambulancia.id,
            base_id=ambulancia.base_id,
            estado=_ESTADO_AMBULANCIA_POR_PASO[self._paso],
            emergencia_id=atencion.emergencia_id,
        )


def crear_simulacion(
    asignacion: ResultadoAsignacion,
    resultado_alternativas: ResultadoAlternativas,
    ambulancias: list[Ambulancia],
    emergencias: list[Emergencia],
    establecimientos: list[Establecimiento],
) -> Simulacion:
    ambulancias_por_id = {ambulancia.id: ambulancia for ambulancia in ambulancias}
    emergencias_por_id = {emergencia.id: emergencia for emergencia in emergencias}
    establecimientos_por_id = {
        establecimiento.id: establecimiento
        for establecimiento in establecimientos
    }
    if len(ambulancias_por_id) != len(ambulancias):
        raise ValueError("Hay ambulancias duplicadas")
    if len(emergencias_por_id) != len(emergencias):
        raise ValueError("Hay emergencias duplicadas")
    if len(establecimientos_por_id) != len(establecimientos):
        raise ValueError("Hay establecimientos duplicados")

    emergencias_asignadas: set[str] = set()
    ambulancias_asignadas: set[str] = set()
    atenciones: list[_AtencionProgramada] = []
    for alternativa in asignacion.alternativas:
        if alternativa.emergencia_id in emergencias_asignadas:
            raise ValueError(
                f"La emergencia {alternativa.emergencia_id} tiene más de una asignación"
            )
        if alternativa.ambulancia_id in ambulancias_asignadas:
            raise ValueError(
                f"La ambulancia {alternativa.ambulancia_id} tiene más de una asignación"
            )
        emergencias_asignadas.add(alternativa.emergencia_id)
        ambulancias_asignadas.add(alternativa.ambulancia_id)
        atenciones.append(
            _crear_atencion_programada(
                alternativa,
                resultado_alternativas,
                ambulancias_por_id,
                emergencias_por_id,
                establecimientos_por_id,
            )
        )

    return Simulacion(
        atenciones=tuple(atenciones),
        emergencias=tuple(emergencias),
        ambulancias=tuple(ambulancias),
        motivos_sin_asignar=asignacion.motivos_sin_asignar,
        etiqueta_asignacion=asignacion.etiqueta,
    )
