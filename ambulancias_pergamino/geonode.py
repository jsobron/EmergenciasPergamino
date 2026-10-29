from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


WFS_URL = "https://geonode.pergamino.gob.ar/geoserver/ows"


def descargar_geojson(
    capa: str,
    *,
    filtro_cql: str | None = None,
    timeout: int = 180,
) -> dict[str, Any]:
    """Descarga una capa publica de la IDE Pergamino como GeoJSON."""
    parametros = {
        "service": "WFS",
        "version": "1.0.0",
        "request": "GetFeature",
        "typeName": capa,
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
    }
    if filtro_cql:
        parametros["CQL_FILTER"] = filtro_cql

    request = Request(
        f"{WFS_URL}?{urlencode(parametros)}",
        headers={"User-Agent": "ambulancias-pergamino/0.1"},
    )
    with urlopen(request, timeout=timeout) as respuesta:
        return json.load(respuesta)

