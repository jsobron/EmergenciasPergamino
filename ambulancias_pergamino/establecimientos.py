from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BASE_SAN_JOSE = "GUARDIA-1"
BASE_MEDICAR = "GUARDIA-5"
BASE_SAME = "SAME"
BASES_DESTINO = {"GUARDIA-1", "GUARDIA-2", "GUARDIA-3", "GUARDIA-4"}


@dataclass(frozen=True)
class Establecimiento:
    id: str
    base_id: str
    nombre: str
    nodo_id: str
    longitud: float
    latitud: float
    habilitado_destino: bool
    prioridad: int
    penalizacion_metros: float
    complejidad_maxima: int
    especialidades: list[Any]
    datos_simulados: bool


@dataclass(frozen=True)
class CostoDestino:
    distancia_real_metros: float
    penalizacion_metros: float
    costo_seleccion_metros: float


def _entero_positivo(valor: Any, campo: str, establecimiento_id: str) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
        raise ValueError(
            f"Establecimiento {establecimiento_id}: {campo} debe ser un entero mayor que cero"
        )
    return valor


def cargar_establecimientos(
    configuracion: Path, bases: list[dict[str, Any]]
) -> list[Establecimiento]:
    datos = json.loads(configuracion.read_text(encoding="utf-8"))
    datos_simulados = datos.get("datos_simulados")
    if not isinstance(datos_simulados, bool):
        raise ValueError("datos_simulados debe ser booleano")

    crudos = datos.get("establecimientos")
    if not isinstance(crudos, list):
        raise ValueError("establecimientos debe ser una lista")

    bases_por_id = {base["id"]: base for base in bases}
    ids_vistos: set[str] = set()
    bases_vistas: set[str] = set()
    establecimientos: list[Establecimiento] = []

    for crudo in crudos:
        if not isinstance(crudo, dict):
            raise ValueError("Cada establecimiento debe ser un objeto")
        establecimiento_id = crudo.get("id")
        if not isinstance(establecimiento_id, str) or not establecimiento_id.strip():
            raise ValueError("Cada establecimiento debe tener un ID de texto no vacío")
        if establecimiento_id in ids_vistos:
            raise ValueError(f"ID de establecimiento duplicado: {establecimiento_id}")
        ids_vistos.add(establecimiento_id)

        base_id = crudo.get("base_id")
        if base_id not in bases_por_id:
            raise ValueError(
                f"Establecimiento {establecimiento_id}: base inexistente {base_id!r}"
            )
        if base_id in bases_vistas:
            raise ValueError(f"Base {base_id}: tiene más de una configuración")
        bases_vistas.add(base_id)

        habilitado = crudo.get("habilitado_destino")
        if not isinstance(habilitado, bool):
            raise ValueError(
                f"Establecimiento {establecimiento_id}: habilitado_destino debe ser booleano"
            )
        if habilitado and base_id == BASE_MEDICAR:
            raise ValueError("Medicar no puede habilitarse como destino")
        if habilitado and base_id == BASE_SAME:
            raise ValueError("SAME no puede habilitarse como destino")

        penalizacion = crudo.get("penalizacion_metros")
        if (
            isinstance(penalizacion, bool)
            or not isinstance(penalizacion, (int, float))
            or penalizacion < 0
        ):
            raise ValueError(
                f"Establecimiento {establecimiento_id}: penalizacion_metros debe ser numérica y no negativa"
            )
        especialidades = crudo.get("especialidades")
        if not isinstance(especialidades, list):
            raise ValueError(
                f"Establecimiento {establecimiento_id}: especialidades debe ser una lista"
            )

        base = bases_por_id[base_id]
        establecimientos.append(
            Establecimiento(
                id=establecimiento_id,
                base_id=base_id,
                nombre=base["nombre"],
                nodo_id=base["nodo_id"],
                longitud=float(base["longitud"]),
                latitud=float(base["latitud"]),
                habilitado_destino=habilitado,
                prioridad=_entero_positivo(
                    crudo.get("prioridad"), "prioridad", establecimiento_id
                ),
                penalizacion_metros=penalizacion,
                complejidad_maxima=_entero_positivo(
                    crudo.get("complejidad_maxima"),
                    "complejidad_maxima",
                    establecimiento_id,
                ),
                especialidades=especialidades.copy(),
                datos_simulados=datos_simulados,
            )
        )

    habilitados = [e for e in establecimientos if e.habilitado_destino]
    if len(habilitados) != 4:
        raise ValueError("Debe haber exactamente cuatro establecimientos habilitados como destino")
    if {e.base_id for e in habilitados} != BASES_DESTINO:
        raise ValueError("Las cuatro bases de destino configuradas no son las esperadas")

    san_jose = next(e for e in habilitados if e.base_id == BASE_SAN_JOSE)
    if san_jose.penalizacion_metros != 0:
        raise ValueError("Hospital Interzonal San José debe tener penalización cero")
    if any(san_jose.prioridad >= e.prioridad for e in habilitados if e != san_jose):
        raise ValueError("Hospital Interzonal San José debe tener la mayor prioridad")
    return establecimientos


def es_compatible_con_complejidad(
    establecimiento: Establecimiento, complejidad_requerida: int
) -> bool:
    return complejidad_requerida <= establecimiento.complejidad_maxima


def calcular_costo_destino(
    distancia_real_metros: float, establecimiento: Establecimiento
) -> CostoDestino:
    if isinstance(distancia_real_metros, bool) or not isinstance(
        distancia_real_metros, (int, float)
    ):
        raise ValueError("distancia_real_metros debe ser numérica")
    if distancia_real_metros < 0:
        raise ValueError("distancia_real_metros no puede ser negativa")
    return CostoDestino(
        distancia_real_metros=distancia_real_metros,
        penalizacion_metros=establecimiento.penalizacion_metros,
        costo_seleccion_metros=(
            distancia_real_metros + establecimiento.penalizacion_metros
        ),
    )
