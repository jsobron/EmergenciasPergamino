from __future__ import annotations

from dataclasses import dataclass, field
from heapq import heappop, heappush
from math import inf
from typing import Any, Iterable

from .geometria import Coordenada, clave_coordenada, distancia_haversine


@dataclass(frozen=True)
class Arista:
    destino: str
    distancia_metros: float
    tramo_id: int | str | None
    calle: str | None


@dataclass
class Grafo:
    nodos: dict[str, Coordenada] = field(default_factory=dict)
    adyacencia: dict[str, list[Arista]] = field(default_factory=dict)

    def agregar_nodo(self, coordenada: Coordenada) -> str:
        nodo_id = clave_coordenada(coordenada)
        self.nodos.setdefault(nodo_id, coordenada)
        self.adyacencia.setdefault(nodo_id, [])
        return nodo_id

    def agregar_arista(
        self,
        origen: str,
        destino: str,
        distancia_metros: float,
        tramo_id: int | str | None,
        calle: str | None,
    ) -> None:
        self.adyacencia[origen].append(
            Arista(destino, round(distancia_metros, 3), tramo_id, calle)
        )

    def nodo_mas_cercano(self, coordenada: Coordenada) -> tuple[str, float]:
        if not self.nodos:
            raise ValueError("El grafo no tiene nodos")
        nodo, distancia = min(
            (
                (nodo_id, distancia_haversine(coordenada, ubicacion))
                for nodo_id, ubicacion in self.nodos.items()
            ),
            key=lambda item: item[1],
        )
        return nodo, distancia

    def camino_minimo(self, origen: str, destino: str) -> tuple[float, list[str]]:
        distancias = {origen: 0.0}
        anteriores: dict[str, str] = {}
        pendientes: list[tuple[float, str]] = [(0.0, origen)]

        while pendientes:
            distancia, actual = heappop(pendientes)
            if distancia != distancias.get(actual):
                continue
            if actual == destino:
                break
            for arista in self.adyacencia.get(actual, []):
                nueva = distancia + arista.distancia_metros
                if nueva < distancias.get(arista.destino, inf):
                    distancias[arista.destino] = nueva
                    anteriores[arista.destino] = actual
                    heappush(pendientes, (nueva, arista.destino))

        if destino not in distancias:
            return inf, []

        camino = [destino]
        while camino[-1] != origen:
            camino.append(anteriores[camino[-1]])
        camino.reverse()
        return distancias[destino], camino

    def serializar(self) -> dict[str, Any]:
        return {
            "nodos": [
                {"id": nodo_id, "longitud": lon, "latitud": lat}
                for nodo_id, (lon, lat) in self.nodos.items()
            ],
            "conexiones": [
                {
                    "origen": origen,
                    "destino": arista.destino,
                    "distancia_metros": arista.distancia_metros,
                    "tramo_id": arista.tramo_id,
                    "calle": arista.calle,
                }
                for origen, aristas in self.adyacencia.items()
                for arista in aristas
            ],
        }

    @classmethod
    def deserializar(cls, datos: dict[str, Any]) -> "Grafo":
        grafo = cls()
        for nodo in datos["nodos"]:
            grafo.nodos[nodo["id"]] = (nodo["longitud"], nodo["latitud"])
            grafo.adyacencia[nodo["id"]] = []
        for conexion in datos["conexiones"]:
            grafo.agregar_arista(
                conexion["origen"],
                conexion["destino"],
                conexion["distancia_metros"],
                conexion.get("tramo_id"),
                conexion.get("calle"),
            )
        return grafo


def _lineas_geometria(geometria: dict[str, Any]) -> Iterable[list[list[float]]]:
    tipo = geometria.get("type")
    if tipo == "LineString":
        yield geometria["coordinates"]
    elif tipo == "MultiLineString":
        yield from geometria["coordinates"]
    else:
        raise ValueError(f"Geometria vial no soportada: {tipo}")


def construir_grafo(callejero: dict[str, Any]) -> tuple[Grafo, list[str]]:
    """Convierte los tramos del callejero en un grafo dirigido."""
    grafo = Grafo()
    advertencias: list[str] = []

    for feature in callejero.get("features", []):
        propiedades = feature.get("properties", {})
        tramo_id = propiedades.get("id", feature.get("id"))
        calle = propiedades.get("nombre_completo") or propiedades.get("nombre")
        sentido = str(propiedades.get("sentido") or "").strip()

        if sentido not in {"-1", "0", "1", ""}:
            advertencias.append(
                f"Tramo {tramo_id}: sentido desconocido {sentido!r}; se trata como doble mano"
            )
            sentido = ""
        if not sentido:
            advertencias.append(
                f"Tramo {tramo_id}: sentido vacio; se trata como doble mano"
            )

        for linea in _lineas_geometria(feature["geometry"]):
            for crudo_a, crudo_b in zip(linea, linea[1:]):
                a: Coordenada = (float(crudo_a[0]), float(crudo_a[1]))
                b: Coordenada = (float(crudo_b[0]), float(crudo_b[1]))
                origen = grafo.agregar_nodo(a)
                destino = grafo.agregar_nodo(b)
                distancia = distancia_haversine(a, b)

                if sentido in {"0", "", "1"}:
                    grafo.agregar_arista(origen, destino, distancia, tramo_id, calle)
                if sentido in {"0", "", "-1"}:
                    grafo.agregar_arista(destino, origen, distancia, tramo_id, calle)

    return grafo, advertencias

