from __future__ import annotations

from math import asin, cos, radians, sin, sqrt


Coordenada = tuple[float, float]  # longitud, latitud
RADIO_TIERRA_METROS = 6_371_008.8


def distancia_haversine(a: Coordenada, b: Coordenada) -> float:
    """Calcula la distancia aproximada sobre la superficie terrestre."""
    lon1, lat1 = map(radians, a)
    lon2, lat2 = map(radians, b)
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * RADIO_TIERRA_METROS * asin(sqrt(h))


def clave_coordenada(coordenada: Coordenada, decimales: int = 7) -> str:
    lon, lat = coordenada
    return f"{round(lon, decimales):.{decimales}f},{round(lat, decimales):.{decimales}f}"

