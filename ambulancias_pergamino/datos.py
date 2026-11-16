from __future__ import annotations

import re
import unicodedata
from typing import Any

from .geometria import Coordenada
from .grafo import Grafo


PREFIJOS_CALLE = (
    "AVENIDA",
    "AVDA",
    "AV",
    "BOULEVARD",
    "BV",
    "CALLE",
    "PASAJE",
    "PJE",
    "RUTA",
    "R",
)

PALABRAS_IGNORADAS = {"DE", "DEL", "LA", "LAS", "LOS", "EL", "Y"}


def normalizar_nombre_calle(nombre: str | None) -> str:
    """Normaliza un nombre de calle para comparar busquedas."""
    if not nombre:
        return ""
    sin_acentos = (
        unicodedata.normalize("NFKD", str(nombre))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    limpio = re.sub(r"[^A-Za-z0-9]+", " ", sin_acentos).strip().upper()
    return " ".join(limpio.split())


def _alias_calle(propiedades: dict[str, Any]) -> list[str]:
    alias: set[str] = set()
    for clave in (
        "nombre",
        "nombre_completo",
        "nombre_corto",
        "nombre_alt",
        "etiqueta",
    ):
        normalizado = normalizar_nombre_calle(propiedades.get(clave))
        if not normalizado:
            continue
        alias.add(normalizado)
        palabras = normalizado.split()
        if palabras and palabras[0] in PREFIJOS_CALLE and len(palabras) > 1:
            alias.add(" ".join(palabras[1:]))
        sin_ignoradas = [palabra for palabra in palabras if palabra not in PALABRAS_IGNORADAS]
        if sin_ignoradas and len(sin_ignoradas) != len(palabras):
            alias.add(" ".join(sin_ignoradas))
    return sorted(alias)


def _rango_numeros(inicio: Any, fin: Any) -> list[int] | None:
    try:
        inicio_numero = int(inicio)
        fin_numero = int(fin)
    except (TypeError, ValueError):
        return None
    if inicio_numero == 0 and fin_numero == 0:
        return None
    if inicio_numero == fin_numero:
        return None
    return [min(inicio_numero, fin_numero), max(inicio_numero, fin_numero)]


def _coordenadas_calle(geometria: dict[str, Any]) -> list[list[float]]:
    tipo = geometria.get("type")
    if tipo == "LineString":
        lineas = [geometria.get("coordinates", [])]
    elif tipo == "MultiLineString":
        lineas = geometria.get("coordinates", [])
    else:
        return []
    coordenadas: list[list[float]] = []
    for linea in lineas:
        for punto in linea:
            if len(punto) < 2:
                continue
            coordenadas.append(
                [round(float(punto[0]), 7), round(float(punto[1]), 7)]
            )
    return coordenadas


def construir_indice_direcciones(callejero: dict[str, Any]) -> list[dict[str, Any]]:
    """Arma un indice compacto de calles y numeracion para el mapa."""
    indice: list[dict[str, Any]] = []
    for feature in callejero.get("features", []):
        propiedades = feature.get("properties", {})
        alias = _alias_calle(propiedades)
        if not alias:
            continue
        coordenadas = _coordenadas_calle(feature.get("geometry", {}))
        if not coordenadas:
            continue
        par = _rango_numeros(
            propiedades.get("par_ini"), propiedades.get("par_fin")
        )
        impar = _rango_numeros(
            propiedades.get("impar_ini"), propiedades.get("impar_fin")
        )
        if par is None and impar is None:
            continue
        nombre = (
            propiedades.get("nombre")
            or propiedades.get("nombre_completo")
            or propiedades.get("nombre_corto")
            or propiedades.get("etiqueta")
            or alias[0]
        )
        indice.append(
            {
                "calle": str(nombre).strip(),
                "alias": alias,
                "par": par,
                "impar": impar,
                "coords": coordenadas,
            }
        )
    return indice


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

