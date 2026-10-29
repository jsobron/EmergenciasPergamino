from __future__ import annotations

import json
from dataclasses import dataclass
from math import isfinite, isinf
from pathlib import Path
from typing import Any

from .establecimientos import Establecimiento
from .grafo import Grafo


@dataclass(frozen=True)
class Emergencia:
    id: str
    latitud: float
    longitud: float
    nodo_id: str
    distancia_al_nodo_m: float
    gravedad: int
    complejidad_requerida: int
    cantidad_pacientes: int
    equipamiento_requerido: list[Any]
    minutos_espera: float
    estado: str
    datos_simulados: bool


@dataclass(frozen=True)
class ConectividadEmergencia:
    emergencia_id: str
    bases_alcanzables: list[str]
    establecimientos_alcanzables: list[str]
    advertencias: list[str]


def _numero(valor: Any, campo: str, emergencia_id: str) -> float:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ValueError(f"Emergencia {emergencia_id}: {campo} debe ser numérico finito")
    numero = float(valor)
    if not isfinite(numero):
        raise ValueError(f"Emergencia {emergencia_id}: {campo} debe ser numérico finito")
    return numero


def _entero_en_escala(valor: Any, campo: str, emergencia_id: str) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int) or valor not in {1, 2, 3}:
        raise ValueError(
            f"Emergencia {emergencia_id}: {campo} debe ser un entero entre 1 y 3"
        )
    return valor


def cargar_emergencias(configuracion: Path, grafo: Grafo) -> list[Emergencia]:
    datos = json.loads(configuracion.read_text(encoding="utf-8"))
    crudos = datos.get("emergencias")
    if not isinstance(crudos, list):
        raise ValueError("emergencias debe ser una lista")
    if not grafo.nodos:
        raise ValueError("No se pueden ubicar emergencias: el grafo no tiene nodos")

    longitudes = [coordenada[0] for coordenada in grafo.nodos.values()]
    latitudes = [coordenada[1] for coordenada in grafo.nodos.values()]
    longitud_minima, longitud_maxima = min(longitudes), max(longitudes)
    latitud_minima, latitud_maxima = min(latitudes), max(latitudes)

    ids_vistos: set[str] = set()
    emergencias: list[Emergencia] = []
    for crudo in crudos:
        if not isinstance(crudo, dict):
            raise ValueError("Cada emergencia debe ser un objeto")

        emergencia_id = crudo.get("id")
        if not isinstance(emergencia_id, str) or not emergencia_id.strip():
            raise ValueError("Cada emergencia debe tener un ID de texto no vacío")
        if emergencia_id in ids_vistos:
            raise ValueError(f"ID de emergencia duplicado: {emergencia_id}")
        ids_vistos.add(emergencia_id)

        latitud = _numero(crudo.get("latitud"), "latitud", emergencia_id)
        longitud = _numero(crudo.get("longitud"), "longitud", emergencia_id)
        if not (
            latitud_minima <= latitud <= latitud_maxima
            and longitud_minima <= longitud <= longitud_maxima
        ):
            raise ValueError(
                f"Emergencia {emergencia_id}: coordenadas fuera de los límites del grafo"
            )

        cantidad_pacientes = crudo.get("cantidad_pacientes")
        if (
            isinstance(cantidad_pacientes, bool)
            or not isinstance(cantidad_pacientes, int)
            or cantidad_pacientes <= 0
        ):
            raise ValueError(
                f"Emergencia {emergencia_id}: cantidad_pacientes debe ser un entero mayor que cero"
            )

        equipamiento = crudo.get("equipamiento_requerido")
        if not isinstance(equipamiento, list):
            raise ValueError(
                f"Emergencia {emergencia_id}: equipamiento_requerido debe ser una lista"
            )

        minutos_espera = _numero(
            crudo.get("minutos_espera"), "minutos_espera", emergencia_id
        )
        if minutos_espera < 0:
            raise ValueError(
                f"Emergencia {emergencia_id}: minutos_espera no puede ser negativo"
            )

        estado = crudo.get("estado")
        if estado != "pendiente":
            raise ValueError(
                f"Emergencia {emergencia_id}: estado debe ser 'pendiente' en esta etapa"
            )
        datos_simulados = crudo.get("datos_simulados")
        if not isinstance(datos_simulados, bool):
            raise ValueError(
                f"Emergencia {emergencia_id}: datos_simulados debe ser booleano"
            )

        nodo_id, distancia = grafo.nodo_mas_cercano((longitud, latitud))
        emergencias.append(
            Emergencia(
                id=emergencia_id,
                latitud=latitud,
                longitud=longitud,
                nodo_id=nodo_id,
                distancia_al_nodo_m=round(distancia, 3),
                gravedad=_entero_en_escala(
                    crudo.get("gravedad"), "gravedad", emergencia_id
                ),
                complejidad_requerida=_entero_en_escala(
                    crudo.get("complejidad_requerida"),
                    "complejidad_requerida",
                    emergencia_id,
                ),
                cantidad_pacientes=cantidad_pacientes,
                equipamiento_requerido=equipamiento.copy(),
                minutos_espera=minutos_espera,
                estado=estado,
                datos_simulados=datos_simulados,
            )
        )
    return emergencias


def analizar_conectividad(
    emergencias: list[Emergencia],
    bases: list[dict[str, Any]],
    establecimientos: list[Establecimiento],
    grafo: Grafo,
) -> list[ConectividadEmergencia]:
    informes: list[ConectividadEmergencia] = []
    destinos = [e for e in establecimientos if e.habilitado_destino]
    for emergencia in emergencias:
        bases_alcanzables = [
            base["nombre"]
            for base in bases
            if not isinf(
                grafo.camino_minimo(base["nodo_id"], emergencia.nodo_id)[0]
            )
        ]
        establecimientos_alcanzables = [
            establecimiento.nombre
            for establecimiento in destinos
            if not isinf(
                grafo.camino_minimo(
                    emergencia.nodo_id, establecimiento.nodo_id
                )[0]
            )
        ]
        advertencias: list[str] = []
        if not bases_alcanzables:
            advertencias.append("ninguna base puede llegar a la emergencia")
        if not establecimientos_alcanzables:
            advertencias.append(
                "no hay establecimientos de destino alcanzables desde la emergencia"
            )
        informes.append(
            ConectividadEmergencia(
                emergencia_id=emergencia.id,
                bases_alcanzables=bases_alcanzables,
                establecimientos_alcanzables=establecimientos_alcanzables,
                advertencias=advertencias,
            )
        )
    return informes
