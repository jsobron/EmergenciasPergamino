from __future__ import annotations

from typing import Any

from .geometria import Coordenada
from .grafo import Grafo


# Ubicacion interpolada de Tucuman 150 sobre el tramo 100-198 del callejero.
# Se conserva la fuente para poder sustituirla por una capa oficial futura.
SAME_PERGAMINO = {
    "id": "SAME",
    "nombre": "SAME Pergamino",
    "direccion": "Tucuman 150, entre Avellaneda y Corrientes",
    "longitud": -60.56163030,
    "latitud": -33.89072180,
    "fuente": "configuracion_complementaria",
}


def _extraer_punto(geometria: dict[str, Any]) -> Coordenada:
    tipo = geometria.get("type")
    coordenadas = geometria.get("coordinates")
    if tipo == "Point":
        lon, lat = coordenadas[:2]
    elif tipo == "MultiPoint" and coordenadas:
        lon, lat = coordenadas[0][:2]
    else:
        raise ValueError(f"Geometria de establecimiento no soportada: {tipo}")
    return float(lon), float(lat)


def construir_bases(guardias: dict[str, Any], grafo: Grafo) -> list[dict[str, Any]]:
    bases: list[dict[str, Any]] = []
    for feature in guardias.get("features", []):
        propiedades = feature["properties"]
        coordenada = _extraer_punto(feature["geometry"])
        nodo_id, distancia = grafo.nodo_mas_cercano(coordenada)
        bases.append(
            {
                "id": f"GUARDIA-{propiedades['id']}",
                "nombre": propiedades["nombre"],
                "direccion": propiedades.get("ubicacion", "").strip(),
                "longitud": coordenada[0],
                "latitud": coordenada[1],
                "nodo_id": nodo_id,
                "distancia_al_grafo_metros": round(distancia, 2),
                "fuente": "geonode:guardias_medicas",
            }
        )

    coordenada_same = (SAME_PERGAMINO["longitud"], SAME_PERGAMINO["latitud"])
    nodo_id, distancia = grafo.nodo_mas_cercano(coordenada_same)
    bases.append(
        {
            **SAME_PERGAMINO,
            "nodo_id": nodo_id,
            "distancia_al_grafo_metros": round(distancia, 2),
        }
    )
    return bases

