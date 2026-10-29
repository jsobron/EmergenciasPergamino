from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, isinf

from .ambulancias import Ambulancia
from .emergencias import Emergencia
from .establecimientos import Establecimiento
from .grafo import Grafo


@dataclass(frozen=True)
class RutaAlternativa:
    distancia_m: float | None
    camino: list[str]


@dataclass(frozen=True)
class Alternativa:
    ambulancia_id: str
    emergencia_id: str
    establecimiento_id: str
    distancia_ambulancia_emergencia_m: float | None
    distancia_emergencia_establecimiento_m: float | None
    distancia_total_m: float | None
    penalizacion_establecimiento_m: float
    costo_seleccion: float | None
    es_factible: bool
    motivos_descarte: list[str]

    def __post_init__(self) -> None:
        campos = (
            "distancia_ambulancia_emergencia_m",
            "distancia_emergencia_establecimiento_m",
            "distancia_total_m",
            "penalizacion_establecimiento_m",
            "costo_seleccion",
        )
        for campo in campos:
            valor = getattr(self, campo)
            if valor is None and campo != "penalizacion_establecimiento_m":
                continue
            if (
                isinstance(valor, bool)
                or not isinstance(valor, (int, float))
                or not isfinite(valor)
                or valor < 0
            ):
                raise ValueError(f"{campo} debe ser un número finito y no negativo")


@dataclass(frozen=True)
class ResultadoAlternativas:
    alternativas: list[Alternativa]
    rutas_ambulancia_emergencia: dict[str, RutaAlternativa]
    rutas_emergencia_establecimiento: dict[str, RutaAlternativa]
    rutas_unicas_calculadas: int


class _CacheRutas:
    def __init__(self, grafo: Grafo) -> None:
        self.grafo = grafo
        self._rutas: dict[tuple[str, str], RutaAlternativa] = {}

    def obtener(self, origen: str, destino: str) -> RutaAlternativa:
        clave = (origen, destino)
        if clave not in self._rutas:
            distancia, camino = self.grafo.camino_minimo(origen, destino)
            self._rutas[clave] = RutaAlternativa(
                distancia_m=None if isinf(distancia) else distancia,
                camino=camino,
            )
        return self._rutas[clave]

    @property
    def cantidad(self) -> int:
        return len(self._rutas)


def construir_alternativas(
    ambulancias: list[Ambulancia],
    emergencias: list[Emergencia],
    establecimientos: list[Establecimiento],
    grafo: Grafo,
) -> ResultadoAlternativas:
    cache = _CacheRutas(grafo)
    rutas_ambulancia_emergencia: dict[str, RutaAlternativa] = {}
    rutas_emergencia_establecimiento: dict[str, RutaAlternativa] = {}

    for ambulancia in ambulancias:
        for emergencia in emergencias:
            clave = f"{ambulancia.id}|{emergencia.id}"
            rutas_ambulancia_emergencia[clave] = cache.obtener(
                ambulancia.nodo_id, emergencia.nodo_id
            )
    for emergencia in emergencias:
        for establecimiento in establecimientos:
            clave = f"{emergencia.id}|{establecimiento.id}"
            rutas_emergencia_establecimiento[clave] = cache.obtener(
                emergencia.nodo_id, establecimiento.nodo_id
            )

    alternativas: list[Alternativa] = []
    for ambulancia in ambulancias:
        for emergencia in emergencias:
            ruta_inicial = rutas_ambulancia_emergencia[
                f"{ambulancia.id}|{emergencia.id}"
            ]
            for establecimiento in establecimientos:
                ruta_destino = rutas_emergencia_establecimiento[
                    f"{emergencia.id}|{establecimiento.id}"
                ]
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
                if ruta_inicial.distancia_m is None:
                    motivos.append("sin_ruta_hasta_emergencia")
                if not establecimiento.habilitado_destino:
                    motivos.append("establecimiento_no_habilitado")
                if (
                    establecimiento.complejidad_maxima
                    < emergencia.complejidad_requerida
                ):
                    motivos.append("complejidad_establecimiento_insuficiente")
                if ruta_destino.distancia_m is None:
                    motivos.append("sin_ruta_hasta_establecimiento")

                distancia_total = None
                costo_seleccion = None
                if (
                    ruta_inicial.distancia_m is not None
                    and ruta_destino.distancia_m is not None
                ):
                    distancia_total = (
                        ruta_inicial.distancia_m + ruta_destino.distancia_m
                    )
                    costo_seleccion = (
                        distancia_total + establecimiento.penalizacion_metros
                    )
                alternativas.append(
                    Alternativa(
                        ambulancia_id=ambulancia.id,
                        emergencia_id=emergencia.id,
                        establecimiento_id=establecimiento.id,
                        distancia_ambulancia_emergencia_m=ruta_inicial.distancia_m,
                        distancia_emergencia_establecimiento_m=ruta_destino.distancia_m,
                        distancia_total_m=distancia_total,
                        penalizacion_establecimiento_m=establecimiento.penalizacion_metros,
                        costo_seleccion=costo_seleccion,
                        es_factible=not motivos,
                        motivos_descarte=motivos,
                    )
                )
    return ResultadoAlternativas(
        alternativas=alternativas,
        rutas_ambulancia_emergencia=rutas_ambulancia_emergencia,
        rutas_emergencia_establecimiento=rutas_emergencia_establecimiento,
        rutas_unicas_calculadas=cache.cantidad,
    )
