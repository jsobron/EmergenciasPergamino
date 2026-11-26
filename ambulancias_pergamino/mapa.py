from __future__ import annotations

import json
from dataclasses import asdict
from itertools import permutations
from math import isinf
from pathlib import Path
from typing import Any

from .ambulancias import cargar_ambulancias
from .alternativas import construir_alternativas
from .asignacion import comparar_niveles
from .establecimientos import cargar_establecimientos
from .emergencias import cargar_emergencias
from .evaluacion import evaluar_escenarios
from .grafo import Grafo
from .heuristicas import reducir_alternativas
from .simulacion import ETAPAS_SIMULACION, crear_simulacion


def _datos_simulacion_mapa(
    asignacion: Any,
    resultado_alternativas: Any,
    ambulancias: Any,
    emergencias: Any,
    establecimientos: Any,
) -> dict[str, Any]:
    simulacion = crear_simulacion(
        asignacion,
        resultado_alternativas,
        ambulancias,
        emergencias,
        establecimientos,
    )
    resultados = []
    for paso in range(len(ETAPAS_SIMULACION)):
        if paso:
            simulacion.avanzar()
        resultados.append(simulacion.resultado())

    inicial = resultados[0]
    final = resultados[-1]
    return {
        "etiqueta": asignacion.etiqueta,
        "total_pasos": final.total_pasos,
        "costo_total": final.costo_total,
        "distancia_total": final.distancia_total,
        "penalizacion_total": final.penalizacion_total,
        "cantidad_atenciones": final.cantidad_atenciones,
        "cantidad_completadas": final.cantidad_completadas,
        "cantidad_sin_asignar": final.cantidad_sin_asignar,
        "es_completa": final.es_completa,
        "atenciones": [
            {
                "emergencia_id": atencion.emergencia_id,
                "ambulancia_id": atencion.ambulancia_id,
                "base_id": atencion.base_id,
                "establecimiento_id": atencion.establecimiento_id,
                "distancia_ambulancia_emergencia_m": (
                    atencion.distancia_ambulancia_emergencia_m
                ),
                "distancia_emergencia_establecimiento_m": (
                    atencion.distancia_emergencia_establecimiento_m
                ),
                "distancia_total_m": atencion.distancia_total_m,
                "penalizacion_establecimiento_m": (
                    atencion.penalizacion_establecimiento_m
                ),
                "costo_seleccion": atencion.costo_seleccion,
                "ruta_ambulancia_emergencia": (
                    f"{atencion.ambulancia_id}|{atencion.emergencia_id}"
                ),
                "ruta_emergencia_establecimiento": (
                    f"{atencion.emergencia_id}|{atencion.establecimiento_id}"
                ),
            }
            for atencion in inicial.atenciones
        ],
        "emergencias_sin_asignar": list(final.emergencias_sin_asignar),
        "motivos_sin_asignar": dict(final.motivos_sin_asignar),
        "estados": [
            {
                "paso": resultado.paso,
                "etapa": resultado.etapa,
                "nombre": resultado.nombre_etapa,
                "emergencias": {
                    emergencia.emergencia_id: asdict(emergencia)
                    for emergencia in resultado.emergencias
                },
                "ambulancias": {
                    ambulancia.ambulancia_id: asdict(ambulancia)
                    for ambulancia in resultado.ambulancias
                },
                "cantidad_completadas": resultado.cantidad_completadas,
            }
            for resultado in resultados
        ],
    }


def preparar_datos_mapa(
    datos: dict[str, Any],
    configuracion_ambulancias: Path,
    configuracion_establecimientos: Path = Path("config/establecimientos.json"),
    configuracion_emergencias: Path = Path("config/emergencias.json"),
    direcciones: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    grafo = Grafo.deserializar(datos["grafo"])
    bases = datos["bases_ambulancias"]
    ambulancias = cargar_ambulancias(configuracion_ambulancias, bases)
    establecimientos = cargar_establecimientos(configuracion_establecimientos, bases)
    emergencias = cargar_emergencias(configuracion_emergencias, grafo)
    resultado_alternativas = construir_alternativas(
        ambulancias, emergencias, establecimientos, grafo
    )
    reduccion = reducir_alternativas(
        resultado_alternativas, ambulancias, emergencias, establecimientos
    )
    comparacion_asignaciones = comparar_niveles(
        resultado_alternativas, ambulancias, emergencias, establecimientos
    )
    evaluacion = evaluar_escenarios(
        resultado_alternativas, ambulancias, emergencias, establecimientos
    )

    tramos: list[dict[str, Any]] = []
    vistos: set[tuple[str, str, int | str | None]] = set()
    for conexion in datos["grafo"]["conexiones"]:
        extremo_a, extremo_b = sorted((conexion["origen"], conexion["destino"]))
        clave = (extremo_a, extremo_b, conexion.get("tramo_id"))
        if clave in vistos:
            continue
        vistos.add(clave)
        tramos.append(
            {
                "origen": conexion["origen"],
                "destino": conexion["destino"],
                "tramo_id": conexion.get("tramo_id"),
                "coordenadas": [
                    list(reversed(grafo.nodos[conexion["origen"]])),
                    list(reversed(grafo.nodos[conexion["destino"]])),
                ],
            }
        )

    rutas: dict[str, dict[str, Any]] = {}
    for origen, destino in permutations(bases, 2):
        distancia, camino = grafo.camino_minimo(origen["nodo_id"], destino["nodo_id"])
        if isinf(distancia):
            continue
        rutas[f"{origen['id']}|{destino['id']}"] = {
            "distancia_metros": round(distancia, 3),
            "coordenadas": [list(reversed(grafo.nodos[nodo])) for nodo in camino],
        }

    nodos_grafo = list(grafo.nodos.items())
    indices_grafo = {
        nodo_id: indice
        for indice, (nodo_id, _) in enumerate(nodos_grafo)
    }
    nodos_js = [[lon, lat] for _, (lon, lat) in nodos_grafo]
    adyacencia_js = [
        [
            [indices_grafo[arista.destino], arista.distancia_metros]
            for arista in grafo.adyacencia[nodo_id]
        ]
        for nodo_id, _ in nodos_grafo
    ]
    nodos_clave = {base["nodo_id"] for base in bases}
    nodos_clave.update(ambulancia.nodo_id for ambulancia in ambulancias)
    nodos_clave.update(
        establecimiento.nodo_id for establecimiento in establecimientos
    )
    nodos_clave.update(emergencia.nodo_id for emergencia in emergencias)

    asignaciones = {
        "original": comparacion_asignaciones.original,
        **{
            f"nivel-{resultado_nivel.parametros.nivel}": resultado_nivel
            for resultado_nivel in comparacion_asignaciones.niveles
            if resultado_nivel.parametros is not None
        },
    }
    simulaciones = {
        clave: _datos_simulacion_mapa(
            asignacion,
            resultado_alternativas,
            ambulancias,
            emergencias,
            establecimientos,
        )
        for clave, asignacion in asignaciones.items()
    }

    return {
        "datos_simulados": True,
        "direcciones": direcciones or [],
        "tramos": tramos,
        "bases": bases,
        "ambulancias": [asdict(ambulancia) for ambulancia in ambulancias],
        "establecimientos": [
            asdict(establecimiento) for establecimiento in establecimientos
        ],
        "emergencias": [asdict(emergencia) for emergencia in emergencias],
        "alternativas": [
            asdict(alternativa) for alternativa in resultado_alternativas.alternativas
        ],
        "reduccion": {
            "parametros": asdict(reduccion.parametros),
            "estadisticas": asdict(reduccion.estadisticas),
            "orden_emergencias": [
                asdict(item) for item in reduccion.orden_emergencias
            ],
            "selecciones": {
                emergencia_id: asdict(seleccion)
                for emergencia_id, seleccion in reduccion.selecciones.items()
            },
            "alternativas_reducidas": [
                asdict(alternativa)
                for alternativa in reduccion.alternativas_reducidas
            ],
        },
        "asignaciones": {
            clave: asdict(asignacion)
            for clave, asignacion in asignaciones.items()
        },
        "simulaciones": simulaciones,
        "etapas_simulacion": [
            asdict(etapa) for etapa in ETAPAS_SIMULACION
        ],
        "evaluacion": {
            "escenarios": [
                asdict(metricas) for metricas in evaluacion.escenarios
            ],
            "nivel_recomendado": evaluacion.nivel_recomendado,
            "perdida_por_heuristica": evaluacion.perdida_por_heuristica,
            "niveles_con_perdida": list(evaluacion.niveles_con_perdida),
            "todos_mismos_resultados": evaluacion.todos_mismos_resultados,
            "todos_mismos_costos": evaluacion.todos_mismos_costos,
        },
        "comparacion_asignaciones": {
            "nivel_recomendado": comparacion_asignaciones.nivel_recomendado,
            "perdida_por_heuristica": (
                comparacion_asignaciones.perdida_por_heuristica
            ),
            "niveles_con_perdida": comparacion_asignaciones.niveles_con_perdida,
            "diferencias": comparacion_asignaciones.diferencias,
        },
        "rutas_ambulancia_emergencia": {
            clave: {
                "distancia_metros": ruta.distancia_m,
                "coordenadas": [list(reversed(grafo.nodos[nodo])) for nodo in ruta.camino],
            }
            for clave, ruta in resultado_alternativas.rutas_ambulancia_emergencia.items()
        },
        "rutas_emergencia_establecimiento": {
            clave: {
                "distancia_metros": ruta.distancia_m,
                "coordenadas": [list(reversed(grafo.nodos[nodo])) for nodo in ruta.camino],
            }
            for clave, ruta in resultado_alternativas.rutas_emergencia_establecimiento.items()
        },
        "rutas": rutas,
        "grafo_js": {
            "nodos": nodos_js,
            "adyacencia": adyacencia_js,
            "indices": {
                nodo_id: indices_grafo[nodo_id] for nodo_id in nodos_clave
            },
        },
    }


def _json_para_script(datos: dict[str, Any]) -> str:
    return json.dumps(datos, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def exportar_mapa(
    entrada: Path,
    configuracion_ambulancias: Path,
    salida: Path,
    configuracion_establecimientos: Path = Path("config/establecimientos.json"),
    configuracion_emergencias: Path = Path("config/emergencias.json"),
    direcciones_path: Path | None = None,
) -> None:
    datos = json.loads(entrada.read_text(encoding="utf-8"))
    if direcciones_path is None:
        direcciones_path = entrada.parent / "direcciones.json"
    direcciones = None
    if direcciones_path.exists():
        direcciones = json.loads(direcciones_path.read_text(encoding="utf-8"))
    datos_mapa = preparar_datos_mapa(
        datos,
        configuracion_ambulancias,
        configuracion_establecimientos,
        configuracion_emergencias,
        direcciones,
    )
    html = _plantilla_html(_json_para_script(datos_mapa))
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(html, encoding="utf-8")


def _plantilla_html(datos_json: str) -> str:
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>URGENCIAS Pergamino</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
        integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
  <style>
    :root {{
      color-scheme: light;
      --surface: #ffffff;
      --surface-muted: #eef3f8;
      --text: #172033;
      --text-muted: #607087;
      --border: #d9e2ec;
      --border-strong: #c5d2e0;
      --primary: #1769aa;
      --primary-dark: #124e7f;
      --prioritario: #c2413b;
      --destino: #1769aa;
      --solo-base: #64748b;
      --route: #1976d2;
      --route-first: #7c3aed;
      --route-second: #008a63;
      --gravedad-alta: #b42318;
      --gravedad-media: #d97706;
      --gravedad-baja: #eab308;
      --shadow: 0 0.4rem 1.4rem #1e3a5f14;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ min-height: 100%; margin: 0; }}
    body {{
      display: flex;
      flex-direction: column;
      gap: 0;
      min-height: 100vh;
      overflow-x: hidden;
      background: var(--surface-muted);
      color: var(--text);
      font: 15px/1.45 Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
    }}
    header {{
      display: grid;
      grid-template-columns: 1fr;
      align-items: center;
      gap: 1rem;
      padding: 0.8rem 1.25rem;
      background: #102a43;
      border-bottom: 1px solid #0e426b;
      color: #fff;
      z-index: 1000;
      box-shadow: 0 0.25rem 0.8rem #102a4333;
    }}
    h1 {{ margin: 0; font-size: clamp(1.25rem, 2vw, 1.65rem); line-height: 1.2; letter-spacing: -0.02em; }}
    .field, section, .workspace, .control-panel {{ min-width: 0; }}
    .field {{ display: grid; gap: 0.25rem; }}
    label {{ font-size: 0.75rem; font-weight: 700; color: var(--text-muted); }}
    header label {{ color: #d9efff; }}
    select,
    input[type="text"] {{
      width: 100%;
      min-height: 2.5rem;
      padding: 0.45rem 0.65rem;
      border: 1px solid var(--border);
      border-radius: 0.5rem;
      background: var(--surface);
      color: var(--text);
      font: inherit;
      box-shadow: 0 1px 2px #1e3a5f0d;
    }}
    select:hover,
    input[type="text"]:hover {{ border-color: #9eb4c9; }}
    select:focus-visible,
    input[type="text"]:focus-visible {{
      outline: 3px solid #78b9ff;
      outline-offset: 1px;
    }}
    section {{
      flex: 0 0 auto;
      margin: 0 0 1rem;
      padding: 0.8rem 1rem;
      border: 1px solid var(--border);
      border-radius: 0.75rem;
      background: var(--surface);
      box-shadow: var(--shadow);
    }}
    .workspace {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(22rem, 27rem);
      grid-template-areas: "map controls";
      gap: 0.9rem;
      min-height: 0;
      height: clamp(36rem, 72vh, 52rem);
      flex: 0 0 auto;
      padding: 0.9rem;
    }}
    .control-panel {{
      grid-area: controls;
      min-height: 0;
      overflow-y: auto;
      padding: 0.2rem 0.25rem 0.2rem 0;
    }}
    .control-panel section:last-child {{ margin-bottom: 0; }}
    .alternative-controls {{
      display: grid;
      grid-template-columns: repeat(3, minmax(10rem, 1fr));
      gap: 0.75rem;
      z-index: 900;
    }}
    .control-panel .alternative-controls {{
      grid-template-columns: minmax(0, 1fr);
    }}
    section h2 {{ color: var(--primary-dark); letter-spacing: -0.01em; }}
    .control-panel section {{
      margin-bottom: 0.75rem;
      padding: 0.85rem;
      border-radius: 0.6rem;
      box-shadow: 0 0.2rem 0.7rem #1e3a5f12;
    }}
    .control-panel section h2 {{
      margin: 0 0 0.75rem;
      padding-bottom: 0.55rem;
      border-bottom: 1px solid var(--border);
      font-size: 0.92rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .alternative-controls h2 {{ grid-column: 1 / -1; margin: 0; font-size: 1rem; }}
    #resultado-alternativa {{
      grid-column: 1 / -1;
      min-width: 0;
      min-height: 2.5rem;
      padding: 0.5rem 0.75rem;
      border: 1px solid #ddd0ff;
      border-left: 4px solid var(--route-first);
      border-radius: 0.5rem;
      background: #faf8ff;
    }}
    #resultado-alternativa dl {{ display: flex; flex-wrap: wrap; gap: 0.25rem 1rem; margin: 0; }}
    #resultado-alternativa div {{ display: flex; gap: 0.25rem; }}
    #resultado-alternativa dt {{ font-weight: 700; }}
    #resultado-alternativa dd {{ margin: 0; }}
    .alternative-actions {{
      grid-column: 1 / -1;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.5rem;
    }}
    .boton-primario,
    .boton-secundario {{
      min-height: 2.25rem;
      padding: 0.4rem 0.75rem;
      border-radius: 0.5rem;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
    }}
    .boton-primario {{
      border: 1px solid var(--primary);
      background: var(--primary);
      color: #fff;
    }}
    .boton-primario:hover:not(:disabled) {{ background: var(--primary-dark); }}
    .boton-primario:disabled {{ opacity: 0.45; cursor: not-allowed; }}
    .boton-secundario {{
      border: 1px solid var(--border-strong);
      background: var(--surface);
      color: var(--primary-dark);
    }}
    .boton-secundario:hover:not(:disabled) {{ border-color: var(--primary); }}
    .boton-secundario:disabled {{ opacity: 0.45; cursor: not-allowed; }}
    .boton-secundario.activo {{
      border-color: var(--primary);
      background: var(--primary);
      color: #fff;
    }}
    #resultado-despacho {{
      flex: 1 1 12rem;
      min-width: 0;
      color: var(--text-muted);
      font-size: 0.8125rem;
    }}
    .panel-inferior {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 0.9rem;
      padding: 0 0.9rem 0.9rem;
    }}
    .panel-cuadro {{
      margin: 0;
      padding: 0.9rem;
      border-radius: 0.6rem;
    }}
    .panel-cuadro h2 {{
      margin: 0 0 0.65rem;
      padding-bottom: 0.5rem;
      border-bottom: 1px solid var(--border);
      font-size: 0.92rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .form-urgencia {{
      display: grid;
      grid-template-columns: repeat(4, minmax(7rem, 1fr));
      align-items: end;
      gap: 0.5rem;
      margin-bottom: 0.6rem;
    }}
    .form-urgencia .field {{ min-width: 0; }}
    .form-acciones {{
      grid-column: 1 / -1;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.5rem;
    }}
    #resultado-urgencia {{
      flex: 1 1 14rem;
      min-height: 1.2rem;
      color: var(--text-muted);
      font-size: 0.8125rem;
    }}
    .resultados-direccion {{
      grid-column: 1 / -1;
      display: grid;
      gap: 0.35rem;
    }}
    .resultado-direccion-item {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 0.35rem 0.6rem;
      width: 100%;
      padding: 0.4rem 0.55rem;
      border: 1px solid var(--border);
      border-radius: 0.45rem;
      background: #f8fbfe;
      color: inherit;
      font: inherit;
      font-size: 0.8125rem;
      text-align: left;
      cursor: pointer;
    }}
    .resultado-direccion-item:hover {{
      border-color: var(--primary);
      background: #eef6ff;
    }}
    .resultado-direccion-item.seleccionado {{
      border-color: var(--primary-dark);
      background: #e3f0ff;
    }}
    .resultado-direccion-item .urgencia-badge {{ text-transform: none; }}
    .resultado-direccion-vacio {{
      color: var(--text-muted);
      font-size: 0.8125rem;
    }}
    .lista-urgencias {{
      display: grid;
      gap: 0.35rem;
      max-height: 15rem;
      margin: 0;
      padding: 0;
      overflow: auto;
      list-style: none;
    }}
    .urgencia-item {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 0.35rem 0.6rem;
      padding: 0.4rem 0.55rem;
      border: 1px solid var(--border);
      border-radius: 0.45rem;
      font-size: 0.8125rem;
    }}
    .urgencia-datos {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.35rem 0.6rem;
    }}
    .urgencia-grado {{ font-weight: 800; }}
    .urgencia-grado.gravedad-3 {{ color: var(--gravedad-alta); }}
    .urgencia-grado.gravedad-2 {{ color: var(--gravedad-media); }}
    .urgencia-grado.gravedad-1 {{ color: #8a6d00; }}
    .urgencia-badge {{
      padding: 0.05rem 0.4rem;
      border-radius: 999px;
      background: #eef3f8;
      color: var(--text-muted);
      font-size: 0.6875rem;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }}
    .urgencia-estado {{ color: var(--text-muted); }}
    .urgencia-estado.en-uso {{ color: #0b6b4f; font-weight: 700; }}
    .urgencia-estado.atendida {{ color: #1d4ed8; font-weight: 700; }}
    .urgencia-item.atendida {{ background: #f2f6ff; }}
    .urgencia-hora {{
      color: var(--text-muted);
      font-size: 0.75rem;
    }}
    .lista-urgencias .urgencia-vacia {{
      padding: 0.55rem 0.65rem;
      border: 1px dashed var(--border-strong);
      border-radius: 0.45rem;
      color: var(--text-muted);
      font-size: 0.8125rem;
    }}
    .dashboard-resumen {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.25rem 0.9rem;
      color: var(--text-muted);
      font-size: 0.8125rem;
    }}
    .dashboard-resumen strong {{ color: var(--primary-dark); }}
    .dashboard-lista {{
      display: grid;
      gap: 0.5rem;
      margin: 0;
      padding: 0;
      list-style: none;
    }}
    .dashboard-lista .dashboard-vacio {{
      padding: 0.6rem 0.75rem;
      border: 1px dashed var(--border-strong);
      border-radius: 0.5rem;
      color: var(--text-muted);
      font-size: 0.8125rem;
    }}
    .dashboard-item {{
      display: grid;
      gap: 0.2rem;
      padding: 0.55rem 0.65rem;
      border: 1px solid var(--border);
      border-left: 4px solid var(--route-second);
      border-radius: 0.5rem;
      background: #f7fbff;
    }}
    .dashboard-item-titulo {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.5rem;
    }}
    .dashboard-estado {{
      padding: 0.1rem 0.45rem;
      border-radius: 999px;
      background: #e5f6ee;
      color: #0b6b4f;
      font-size: 0.6875rem;
      font-weight: 800;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }}
    .dashboard-item-detalle,
    .dashboard-item-tramos {{
      color: var(--text-muted);
      font-size: 0.8125rem;
    }}
    .dashboard-item-tiempo {{ font-size: 0.875rem; }}
    .dashboard-auto {{
      color: var(--text-muted);
      font-size: 0.75rem;
      font-weight: 600;
    }}
    .dashboard-nota {{
      margin: 0;
      color: var(--text-muted);
      font-size: 0.75rem;
    }}
    #mapa {{
      grid-area: map;
      width: 100%;
      height: 100%;
      min-height: 0;
      margin: 0;
      overflow: hidden;
      border: 1px solid var(--border-strong);
      border-radius: 0.75rem;
      box-shadow: var(--shadow);
    }}
    .base-icon {{
      display: grid;
      place-items: center;
      width: 2rem;
      height: 2rem;
      border: 3px solid #fff;
      border-radius: 50%;
      background: var(--solo-base);
      box-shadow: 0 1px 4px #0008;
      color: #fff;
      font-weight: 800;
      font-size: 0.6875rem;
    }}
    .base-icon.prioritario {{ background: var(--prioritario); border-radius: 0.25rem; }}
    .base-icon.destino {{ background: var(--destino); }}
    .base-icon.solo-base {{ background: var(--solo-base); }}
    .base-icon.inactivo {{
      background: #9ca3af;
      border-style: dashed;
      opacity: 0.7;
    }}
    .base-icon.same {{ border-radius: 0.25rem; }}
    .emergencia-icon {{
      display: grid;
      place-items: center;
      width: 1.75rem;
      height: 1.75rem;
      transform: rotate(45deg);
      border: 3px solid #fff;
      background: var(--gravedad-baja);
      box-shadow: 0 1px 4px #0009;
      color: #111;
      font-weight: 900;
    }}
    .emergencia-icon span {{ transform: rotate(-45deg); }}
    .emergencia-icon.gravedad-3 {{ background: var(--gravedad-alta); color: #fff; }}
    .emergencia-icon.gravedad-2 {{ background: var(--gravedad-media); color: #fff; }}
    .emergencia-icon.gravedad-1 {{ background: var(--gravedad-baja); color: #111; }}
    .popup-title {{ margin: 0 0 0.375rem; font-size: 1rem; }}
    .popup-list {{ margin: 0; padding: 0; list-style: none; }}
    .popup-list li + li {{ margin-top: 0.1875rem; }}
    .leaflet-popup-content {{ min-width: 14rem; }}
    .leyenda {{
      max-height: min(32rem, calc(100vh - 2rem));
      overflow: auto;
      padding: 0.75rem 0.875rem;
      border: 1px solid var(--border);
      border-radius: 0.625rem;
      background: #fffffff5;
      box-shadow: 0 0.3rem 1rem #1e3a5f26;
      color: var(--text);
      line-height: 1.5;
      backdrop-filter: blur(6px);
    }}
    .leyenda strong {{ display: block; margin: 0.35rem 0 0.25rem; color: var(--primary-dark); }}
    .leyenda strong:first-child {{ margin-top: 0; }}
    .leyenda-item {{ display: flex; align-items: center; gap: 0.5rem; }}
    .leyenda-muestra {{
      width: 0.875rem;
      height: 0.875rem;
      border: 2px solid #fff;
      border-radius: 50%;
      box-shadow: 0 0 0 1px #0004;
    }}
    .leyenda-muestra.prioritario {{ background: var(--prioritario); border-radius: 0.125rem; }}
    .leyenda-muestra.destino {{ background: var(--destino); }}
    .leyenda-muestra.solo-base {{ background: var(--solo-base); }}
    .leyenda-muestra.inactivo {{ background: #9ca3af; }}
    .leyenda-muestra.emergencia {{
      transform: rotate(45deg);
      border-radius: 0;
    }}
    .leyenda-muestra.gravedad-3 {{ background: var(--gravedad-alta); }}
    .leyenda-muestra.gravedad-2 {{ background: var(--gravedad-media); }}
    .leyenda-muestra.gravedad-1 {{ background: var(--gravedad-baja); }}
    .leyenda-linea {{ width: 1.5rem; height: 0; border-top: 4px solid; }}
    .leyenda-linea.tramo-inicial {{ border-color: var(--route-first); }}
    .leyenda-linea.tramo-destino {{ border-color: var(--route-second); }}
    @media (max-width: 980px) {{
      header {{
        grid-template-columns: 1fr;
        align-items: stretch;
        gap: 0.75rem;
      }}
      .workspace {{
        grid-template-columns: minmax(18rem, 22rem) minmax(0, 1fr);
      }}
      .panel-inferior {{ grid-template-columns: 1fr; }}
      .form-urgencia {{ grid-template-columns: 1fr 1fr; }}
    }}
    @media (max-width: 760px) {{
      header {{ grid-template-columns: 1fr; align-items: stretch; }}
      .workspace {{
        display: flex;
        flex-direction: column;
        height: auto;
        padding: 0.75rem;
      }}
      #mapa {{
        order: 1;
        height: min(58vh, 32rem);
        min-height: 22rem;
        flex-basis: auto;
      }}
      .control-panel {{
        order: 2;
        overflow: visible;
        padding-right: 0;
      }}
      .alternative-controls {{ grid-template-columns: 1fr; }}
      .alternative-controls h2, #resultado-alternativa {{ grid-column: auto; }}
      .panel-inferior {{ padding: 0 0.75rem 0.75rem; }}
      .form-urgencia {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 480px) {{
      header {{ padding: 0.8rem; }}
      h1 {{ font-size: 1.2rem; }}
      .workspace {{ padding: 0.5rem; gap: 0.6rem; }}
      #mapa {{ height: 58vh; min-height: 20rem; }}
      .control-panel section {{ padding: 0.7rem; }}
      .panel-inferior {{ padding: 0 0.5rem 0.5rem; }}
      .panel-cuadro {{ padding: 0.7rem; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>URGENCIAS Pergamino</h1>
  </header>
  <div class="workspace">
    <aside class="control-panel" aria-label="Controles de análisis">
      <section class="alternative-controls" aria-labelledby="titulo-alternativas">
    <h2 id="titulo-alternativas">Visor manual de alternativas</h2>
    <div class="field"><label for="hospital-disponible">Disponibilidad del hospital</label><select id="hospital-disponible"><option value="si">Hospital con lugar</option><option value="no">Hospital sin lugar: habilitar clínicas</option></select></div>
    <p>La disponibilidad afecta los nuevos despachos. Los servicios en curso se conservan.</p>
    <div class="field"><label for="despacho-pacientes">Pacientes a trasladar en esta unidad</label><input id="despacho-pacientes" type="number" min="0" step="1" value="1"></div>
    <div class="field"><label for="alternativa-ambulancia">Ambulancia</label><select id="alternativa-ambulancia"></select></div>
    <div class="field"><label for="alternativa-emergencia">Emergencia</label><select id="alternativa-emergencia"></select></div>
    <div class="field"><label for="alternativa-establecimiento">Establecimiento</label><select id="alternativa-establecimiento"></select></div>
    <div id="resultado-alternativa" role="status" aria-live="polite">Elegí los tres elementos para inspeccionar una alternativa.</div>
    <div class="alternative-actions">
      <button type="button" id="alternativa-asignar" class="boton-primario" disabled>Poner ambulancia en uso</button>
      <span id="resultado-despacho" role="status" aria-live="polite">Elegí una alternativa factible para despacharla.</span>
    </div>
      </section>
    </aside>
    <main id="mapa" aria-label="Mapa vial de Pergamino"></main>
  </div>
  <div class="panel-inferior">
    <section class="panel-cuadro" aria-labelledby="titulo-dashboard">
      <h2 id="titulo-dashboard">Liberación de ambulancias</h2>
      <div id="dashboard-resumen" class="dashboard-resumen" role="status" aria-live="polite"></div>
      <ul id="dashboard-lista" class="dashboard-lista"></ul>
      <p class="dashboard-nota">Tiempo estimado hasta quedar disponible: recorrido asignado más regreso a la base a 40 km/h, más 10 minutos de atención. Al cumplirse ese tiempo la ambulancia se libera automáticamente; el botón <strong>Liberar</strong> permite adelantar la liberación.</p>
    </section>
    <section class="panel-cuadro" aria-labelledby="titulo-urgencias">
      <h2 id="titulo-urgencias">Urgencias y grados</h2>
      <form id="form-urgencia" class="form-urgencia">
        <div class="field"><label for="urgencia-pacientes">Pacientes</label><input id="urgencia-pacientes" type="number" min="1" step="1" value="1" required></div>
        <div class="field"><label for="urgencia-unidades">Mínimo de ambulancias</label><input id="urgencia-unidades" type="number" min="1" step="1" value="1" required></div>
        <div class="field">
          <label for="urgencia-id">ID de la urgencia</label>
          <input id="urgencia-id" type="text" maxlength="20" autocomplete="off" required>
        </div>
        <div class="field">
          <label for="urgencia-gravedad">Grado</label>
          <select id="urgencia-gravedad">
            <option value="1">1 - Baja</option>
            <option value="2" selected>2 - Media</option>
            <option value="3">3 - Alta</option>
          </select>
        </div>
        <div class="field">
          <label for="urgencia-calle">Calle</label>
          <input id="urgencia-calle" type="text" autocomplete="off"
                 placeholder="Ej.: Tucumán">
        </div>
        <div class="field">
          <label for="urgencia-numero">Número</label>
          <input id="urgencia-numero" type="text" inputmode="numeric"
                 autocomplete="off" placeholder="Ej.: 150">
        </div>
        <div class="form-acciones">
          <button type="button" id="urgencia-buscar" class="boton-secundario">Buscar dirección</button>
          <button type="button" id="urgencia-elegir-mapa" class="boton-secundario">Elegir en el mapa</button>
          <button type="submit" class="boton-primario">Agregar urgencia</button>
          <span id="resultado-urgencia" role="status" aria-live="polite"></span>
        </div>
        <div id="resultados-direccion" class="resultados-direccion" role="status" aria-live="polite"></div>
      </form>
      <p class="dashboard-nota">Buscá la dirección por <strong>calle y número</strong> o usá <strong>Elegir en el mapa</strong>. La urgencia se conecta al nodo vial más cercano; el grado se usa como gravedad y la complejidad requerida se limita a 2.</p>
      <ul id="lista-urgencias" class="lista-urgencias"></ul>
    </section>
  </div>
  <script id="datos-mapa" type="application/json">{datos_json}</script>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
          integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
  <script>
    "use strict";
    const datos = JSON.parse(document.getElementById("datos-mapa").textContent);
    const mapa = L.map("mapa", {{ preferCanvas: true, zoomControl: true }});
    mapa.fitBounds([[-33.935, -60.625], [-33.855, -60.515]]);
    L.tileLayer("https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    }}).addTo(mapa);

    const calles = L.layerGroup().addTo(mapa);
    datos.tramos.forEach((tramo) => {{
      L.polyline(tramo.coordenadas, {{
        color: "#698078", weight: 1.25, opacity: 0.58, interactive: false
      }}).addTo(calles);
    }});

    const escapar = (valor) => String(valor)
      .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;").replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
    const ambulanciasPorBase = datos.ambulancias.reduce((grupos, ambulancia) => {{
      (grupos[ambulancia.base_id] ||= []).push(ambulancia);
      return grupos;
    }}, {{}});
    const establecimientosPorBase = Object.fromEntries(
      datos.establecimientos.map((establecimiento) => [establecimiento.base_id, establecimiento])
    );
    const establecimientosPorId = Object.fromEntries(
      datos.establecimientos.map((establecimiento) => [establecimiento.id, establecimiento])
    );
    const ambulanciasPorId = Object.fromEntries(
      datos.ambulancias.map((ambulancia) => [ambulancia.id, ambulancia])
    );
    const nombreDeAmbulancia = (ambulanciaId) => {{
      const ambulancia = ambulanciasPorId[ambulanciaId];
      return ambulancia ? (ambulancia.nombre || ambulancia.id) : ambulanciaId;
    }};
    const marcadoresBase = {{}};
    const marcadoresEmergencia = {{}};

    const grafo = datos.grafo_js;
    const limitesGrafo = grafo.nodos.reduce(
      (limites, [lon, lat]) => ({{
        minLon: Math.min(limites.minLon, lon),
        maxLon: Math.max(limites.maxLon, lon),
        minLat: Math.min(limites.minLat, lat),
        maxLat: Math.max(limites.maxLat, lat)
      }}),
      {{ minLon: Infinity, maxLon: -Infinity, minLat: Infinity, maxLat: -Infinity }}
    );

    function distanciaHaversine(lonA, latA, lonB, latB) {{
      const radioTierra = 6371008.8;
      const aRadianes = Math.PI / 180;
      const lat1 = latA * aRadianes;
      const lat2 = latB * aRadianes;
      const dLat = (latB - latA) * aRadianes;
      const dLon = (lonB - lonA) * aRadianes;
      const h = Math.sin(dLat / 2) ** 2 +
        Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
      return 2 * radioTierra * Math.asin(Math.min(1, Math.sqrt(h)));
    }}

    function nodoMasCercano(lon, lat) {{
      let indice = -1;
      let distancia = Infinity;
      grafo.nodos.forEach(([nodoLon, nodoLat], posicion) => {{
        const actual = distanciaHaversine(lon, lat, nodoLon, nodoLat);
        if (actual < distancia) {{
          distancia = actual;
          indice = posicion;
        }}
      }});
      return {{ indice, distancia }};
    }}

    class MonticuloMinimo {{
      constructor() {{
        this.prioridades = [];
        this.valores = [];
      }}
      get tamano() {{
        return this.prioridades.length;
      }}
      insertar(prioridad, valor) {{
        this.prioridades.push(prioridad);
        this.valores.push(valor);
        let posicion = this.prioridades.length - 1;
        while (posicion > 0) {{
          const padre = Math.floor((posicion - 1) / 2);
          if (this.prioridades[padre] <= this.prioridades[posicion]) break;
          this.intercambiar(posicion, padre);
          posicion = padre;
        }}
      }}
      extraer() {{
        const prioridad = this.prioridades[0];
        const valor = this.valores[0];
        const ultimaPrioridad = this.prioridades.pop();
        const ultimoValor = this.valores.pop();
        if (this.prioridades.length) {{
          this.prioridades[0] = ultimaPrioridad;
          this.valores[0] = ultimoValor;
          let posicion = 0;
          const tamano = this.prioridades.length;
          while (true) {{
            const izquierda = posicion * 2 + 1;
            const derecha = izquierda + 1;
            let menor = posicion;
            if (
              izquierda < tamano &&
              this.prioridades[izquierda] < this.prioridades[menor]
            ) menor = izquierda;
            if (
              derecha < tamano &&
              this.prioridades[derecha] < this.prioridades[menor]
            ) menor = derecha;
            if (menor === posicion) break;
            this.intercambiar(posicion, menor);
            posicion = menor;
          }}
        }}
        return [prioridad, valor];
      }}
      intercambiar(a, b) {{
        [this.prioridades[a], this.prioridades[b]] =
          [this.prioridades[b], this.prioridades[a]];
        [this.valores[a], this.valores[b]] =
          [this.valores[b], this.valores[a]];
      }}
    }}

    function caminoMinimo(origen, destino) {{
      if (
        !Number.isInteger(origen) || !Number.isInteger(destino) ||
        origen < 0 || destino < 0
      ) {{
        return {{ distancia: null, camino: [] }};
      }}
      const totalNodos = grafo.nodos.length;
      const distancias = new Float64Array(totalNodos);
      distancias.fill(Infinity);
      const anteriores = new Int32Array(totalNodos);
      anteriores.fill(-1);
      const visitados = new Uint8Array(totalNodos);
      const pendientes = new MonticuloMinimo();
      distancias[origen] = 0;
      pendientes.insertar(0, origen);
      while (pendientes.tamano) {{
        const [distancia, actual] = pendientes.extraer();
        if (visitados[actual]) continue;
        visitados[actual] = 1;
        if (actual === destino) break;
        grafo.adyacencia[actual].forEach(([vecino, peso]) => {{
          const nueva = distancia + peso;
          if (nueva < distancias[vecino]) {{
            distancias[vecino] = nueva;
            anteriores[vecino] = actual;
            pendientes.insertar(nueva, vecino);
          }}
        }});
      }}
      if (!Number.isFinite(distancias[destino])) {{
        return {{ distancia: null, camino: [] }};
      }}
      const camino = [];
      let actual = destino;
      while (actual !== -1) {{
        camino.push(actual);
        if (actual === origen) break;
        actual = anteriores[actual];
      }}
      camino.reverse();
      return {{ distancia: distancias[destino], camino }};
    }}

    function coordenadasCamino(camino) {{
      return camino.map((indice) => [
        grafo.nodos[indice][1],
        grafo.nodos[indice][0]
      ]);
    }}

    datos.bases.forEach((base) => {{
      const ambulanciasBase = ambulanciasPorBase[base.id] || [];
      const establecimiento = establecimientosPorBase[base.id];
      const esSame = base.id === "SAME";
      const destinoHabilitado = Boolean(
        establecimiento && establecimiento.habilitado_destino
      );
      const tipo = destinoHabilitado
        ? (base.id === "GUARDIA-1" ? "prioritario" : "destino")
        : establecimiento ? "inactivo" : "solo-base";
      const etiquetaBase = base.id === "SAME"
        ? "SAME"
        : base.id === "GUARDIA-5" ? "MED" : base.id.replace("GUARDIA-", "G");
      const icono = L.divIcon({{
        className: "",
        html: `<div class="base-icon ${{tipo}} ${{esSame ? "same" : ""}}">${{escapar(etiquetaBase)}}</div>`,
        iconSize: [34, 32], iconAnchor: [17, 16], popupAnchor: [0, -18]
      }});
      const filasAmbulancias = ambulanciasBase.length
        ? ambulanciasBase.map((ambulancia) => {{
            const estado = ambulancia.reserva
              ? "reserva, solo gravedad 3"
              : ambulancia.disponible ? "disponible" : "no disponible";
            return `<li><strong>${{escapar(nombreDeAmbulancia(ambulancia.id))}}</strong>: ` +
              `complejidad ${{ambulancia.complejidad}}, ${{estado}}</li>`;
          }}).join("")
        : "<li><strong>Ambulancias:</strong> sin ambulancias asignadas</li>";
      const recibePacientes = destinoHabilitado ? "Sí" : "No";
      const detallesDestino = establecimiento ? `
          <li><strong>Destino:</strong> ${{destinoHabilitado ? "habilitado" : "inactivo"}}</li>
          <li><strong>Prioridad:</strong> ${{establecimiento.prioridad}}</li>
          <li><strong>Penalización:</strong> ${{establecimiento.penalizacion_metros.toLocaleString("es-AR")}} m</li>
          <li><strong>Complejidad máxima:</strong> ${{establecimiento.complejidad_maxima}}</li>` : "";
      const contenido = `
        <h2 class="popup-title">${{escapar(base.nombre)}}</h2>
        <ul class="popup-list">
          <li><strong>Recibe pacientes:</strong> ${{recibePacientes}}</li>
          ${{filasAmbulancias}}
          ${{detallesDestino}}
        </ul>`;
      marcadoresBase[base.id] = L.marker(
        [base.latitud, base.longitud], {{ icon: icono, title: base.nombre }}
      ).bindPopup(contenido).addTo(mapa);
    }});

    const descripcionGravedad = {{
      1: "Baja",
      2: "Media",
      3: "Alta/crítica"
    }};
    function crearMarcadorEmergencia(emergencia) {{
      const icono = L.divIcon({{
        className: "",
        html: `<div class="emergencia-icon gravedad-${{emergencia.gravedad}}"><span>!</span></div>`,
        iconSize: [28, 28], iconAnchor: [14, 14], popupAnchor: [0, -17]
      }});
      const equipamiento = emergencia.equipamiento_requerido.length
        ? emergencia.equipamiento_requerido.map(escapar).join(", ")
        : "Ninguno";
      const origen = emergencia.es_agregada
        ? "Agregada manualmente"
        : "Configuración inicial";
      const ubicacion = emergencia.es_agregada
        ? `${{escapar(emergencia.direccion || "Elegida en el mapa")}}`
        : `${{emergencia.latitud.toFixed(7)}}, ${{emergencia.longitud.toFixed(7)}}`;
      const contenido = `
        <h2 class="popup-title">Emergencia ${{escapar(emergencia.id)}}</h2>
        <ul class="popup-list">
          <li><strong>Gravedad:</strong> ${{emergencia.gravedad}} — ${{descripcionGravedad[emergencia.gravedad]}}</li>
          <li><strong>Complejidad requerida:</strong> ${{emergencia.complejidad_requerida}}</li>
          <li><strong>Pacientes:</strong> ${{emergencia.cantidad_pacientes}}</li>
          <li><strong>Equipamiento:</strong> ${{equipamiento}}</li>
          <li><strong>Espera:</strong> ${{emergencia.minutos_espera.toLocaleString("es-AR")}} min</li>
          <li><strong>Estado:</strong> ${{escapar(emergencia.estado)}}</li>
          <li><strong>Ubicación:</strong> ${{ubicacion}}</li>
          <li><strong>Nodo vial:</strong> ${{escapar(emergencia.nodo_id)}}</li>
          <li><strong>Distancia al nodo:</strong> ${{emergencia.distancia_al_nodo_m.toLocaleString("es-AR")}} m</li>
          <li><strong>Origen:</strong> ${{origen}}</li>
        </ul>`;
      marcadoresEmergencia[emergencia.id] = L.marker(
        [emergencia.latitud, emergencia.longitud], {{
          icon: icono,
          title: `Emergencia ${{emergencia.id}} — gravedad ${{emergencia.gravedad}}`
        }}
      ).bindPopup(contenido).addTo(mapa);
    }}
    datos.emergencias.forEach(crearMarcadorEmergencia);

    const leyenda = L.control({{ position: "bottomleft" }});
    leyenda.onAdd = () => {{
      const contenedor = L.DomUtil.create("div", "leyenda");
      contenedor.innerHTML = `
        <strong>Establecimientos</strong>
        <span class="leyenda-item"><i class="leyenda-muestra prioritario"></i>Destino prioritario</span>
        <span class="leyenda-item"><i class="leyenda-muestra destino"></i>Destino habilitado</span>
        <span class="leyenda-item"><i class="leyenda-muestra inactivo"></i>Destino inactivo</span>
        <span class="leyenda-item"><i class="leyenda-muestra solo-base"></i>No recibe pacientes</span>
        <strong>Gravedad de emergencias</strong>
        <span class="leyenda-item"><i class="leyenda-muestra emergencia gravedad-3"></i>Gravedad alta/crítica (3)</span>
        <span class="leyenda-item"><i class="leyenda-muestra emergencia gravedad-2"></i>Gravedad media (2)</span>
        <span class="leyenda-item"><i class="leyenda-muestra emergencia gravedad-1"></i>Gravedad baja (1)</span>
        <strong>Alternativa manual</strong>
        <span class="leyenda-item"><i class="leyenda-linea tramo-inicial"></i>Tramo ambulancia → emergencia</span>
        <span class="leyenda-item"><i class="leyenda-linea tramo-destino"></i>Tramo emergencia → establecimiento</span>`;
      return contenedor;
    }};
    leyenda.addTo(mapa);

    const selectorAmbulancia = document.getElementById("alternativa-ambulancia");
    const selectorEmergencia = document.getElementById("alternativa-emergencia");
    const selectorEstablecimiento = document.getElementById("alternativa-establecimiento");
    const resultadoAlternativa = document.getElementById("resultado-alternativa");
    function prepararSelector(selector, etiqueta, elementos, texto) {{
      const inicial = new Option(etiqueta, "", true, true);
      inicial.disabled = true;
      selector.add(inicial);
      elementos.forEach((elemento) => selector.add(new Option(texto(elemento), elemento.id)));
    }}
    prepararSelector(
      selectorAmbulancia,
      "Seleccionar ambulancia…",
      datos.ambulancias,
      (a) => `${{a.nombre || a.id}}${{a.reserva ? " (reserva)" : ""}}`
    );
    prepararSelector(
      selectorEmergencia,
      "Seleccionar emergencia…",
      datos.emergencias,
      (e) => `${{e.id}} — gravedad ${{e.gravedad}}`
    );
    prepararSelector(
      selectorEstablecimiento,
      "Seleccionar establecimiento…",
      datos.establecimientos.filter((e) => e.habilitado_destino),
      (e) => e.nombre
    );
    const alternativasPorClave = Object.fromEntries(datos.alternativas.map((a) => [
      `${{a.ambulancia_id}}|${{a.emergencia_id}}|${{a.establecimiento_id}}`, a
    ]));
    const mostrarMetros = (valor) => valor === null
      ? "Sin ruta"
      : `${{Math.round(valor).toLocaleString("es-AR")}} m`;
    function crearDibujadorTramos() {{
      let capaInicial = null;
      let capaDestino = null;
      function limpiar() {{
        if (capaInicial) {{ mapa.removeLayer(capaInicial); capaInicial = null; }}
        if (capaDestino) {{ mapa.removeLayer(capaDestino); capaDestino = null; }}
      }}
      function dibujar(ambulanciaId, emergenciaId, establecimientoId) {{
        limpiar();
        const rutaInicial = datos.rutas_ambulancia_emergencia[`${{ambulanciaId}}|${{emergenciaId}}`];
        const rutaDestino = datos.rutas_emergencia_establecimiento[`${{emergenciaId}}|${{establecimientoId}}`];
        const capas = [];
        if (rutaInicial && rutaInicial.coordenadas.length) {{
          capaInicial = L.polyline(rutaInicial.coordenadas, {{ color: "#7b2cbf", weight: 5, opacity: 0.92 }}).addTo(mapa);
          capas.push(capaInicial);
        }}
        if (rutaDestino && rutaDestino.coordenadas.length) {{
          capaDestino = L.polyline(rutaDestino.coordenadas, {{ color: "#00875a", weight: 5, opacity: 0.92 }}).addTo(mapa);
          capas.push(capaDestino);
        }}
        if (capas.length) mapa.fitBounds(L.featureGroup(capas).getBounds(), {{ padding: [36, 36], maxZoom: 16 }});
        return capas;
      }}
      return {{ limpiar, dibujar }};
    }}
    const dibujadorManual = crearDibujadorTramos();
    function dibujarAlternativa() {{
      dibujadorManual.limpiar();
      const ambulanciaId = selectorAmbulancia.value;
      const emergenciaId = selectorEmergencia.value;
      const establecimientoId = selectorEstablecimiento.value;
      if (!ambulanciaId || !emergenciaId || !establecimientoId) {{
        botonAsignar.disabled = true;
        resultadoAlternativa.textContent = "Elegí los tres elementos para inspeccionar una alternativa.";
        return;
      }}
      const alternativa = alternativasPorClave[`${{ambulanciaId}}|${{emergenciaId}}|${{establecimientoId}}`];
      if (!alternativa) {{
        botonAsignar.disabled = true;
        resultadoAlternativa.textContent =
          "No hay una alternativa registrada para esa combinación.";
        return;
      }}
      botonAsignar.disabled = !alternativa.es_factible || !destinoPermitido(alternativa);
      dibujadorManual.dibujar(ambulanciaId, emergenciaId, establecimientoId);
      const motivos = alternativa.motivos_descarte.length
        ? alternativa.motivos_descarte.map(escapar).join(", ")
        : "Ninguno";
      const tiempos = alternativa.es_factible ? tiempoHastaDisponible(alternativa) : null;
      const tiempoTexto = tiempos ? minutosTexto(tiempos.minutos) : "—";
      resultadoAlternativa.innerHTML = `<dl>
        <div><dt>Ambulancia → emergencia:</dt><dd>${{mostrarMetros(alternativa.distancia_ambulancia_emergencia_m)}}</dd></div>
        <div><dt>Emergencia → establecimiento:</dt><dd>${{mostrarMetros(alternativa.distancia_emergencia_establecimiento_m)}}</dd></div>
        <div><dt>Distancia física total:</dt><dd>${{mostrarMetros(alternativa.distancia_total_m)}}</dd></div>
        <div><dt>Penalización:</dt><dd>${{mostrarMetros(alternativa.penalizacion_establecimiento_m)}}</dd></div>
        <div><dt>Costo de selección:</dt><dd>${{mostrarMetros(alternativa.costo_seleccion)}}</dd></div>
        <div><dt>Factible:</dt><dd>${{alternativa.es_factible && destinoPermitido(alternativa) ? "Sí" : "No (revisar disponibilidad del hospital o restricciones)"}}</dd></div>
        <div><dt>Disponible en:</dt><dd>${{tiempoTexto}}</dd></div>
        <div><dt>Motivos:</dt><dd>${{motivos}}</dd></div>
      </dl>`;
    }}
    selectorAmbulancia.addEventListener("change", dibujarAlternativa);
    selectorEmergencia.addEventListener("change", dibujarAlternativa);
    selectorEstablecimiento.addEventListener("change", dibujarAlternativa);

    const botonAsignar = document.getElementById("alternativa-asignar");
    const resultadoDespacho = document.getElementById("resultado-despacho");
    const dashboardResumen = document.getElementById("dashboard-resumen");
    const dashboardLista = document.getElementById("dashboard-lista");
    const VELOCIDAD_KMH = 40;
    const TIEMPO_ATENCION_MIN = 10;
    const despachos = new Map();
    const atendidas = new Map();
    const hospitalDisponible = document.getElementById("hospital-disponible");
    const pacientesDespacho = document.getElementById("despacho-pacientes");
    function destinoPermitido(alternativa) {{
      return (alternativa.establecimiento_id === "GUARDIA-1") === (hospitalDisponible.value === "si");
    }}
    hospitalDisponible.addEventListener("change", () => {{
      [...selectorEstablecimiento.options].forEach((opcion) => {{
        if (!opcion.value) return;
        opcion.disabled = (opcion.value === "GUARDIA-1") !== (hospitalDisponible.value === "si");
      }});
      selectorEstablecimiento.value = "";
      dibujarAlternativa();
    }});
    function serviciosEmergencia(id) {{
      return [...despachos.values(), ...atendidas.values()].filter(item => item.alternativa.emergencia_id === id);
    }}
    function coberturaCompleta(id) {{
      const e = datos.emergencias.find(e => e.id === id);
      const servicios = serviciosEmergencia(id);
      return e && servicios.length >= (e.ambulancias_requeridas || 1) &&
        servicios.reduce((s, item) => s + item.pacientes, 0) >= e.cantidad_pacientes;
    }}

    function tiempoHastaDisponible(alternativa) {{
      const ida = alternativa.distancia_total_m;
      const ambulancia = ambulanciasPorId[alternativa.ambulancia_id];
      const establecimiento = establecimientosPorId[alternativa.establecimiento_id];
      const retorno = establecimiento && ambulancia
        ? datos.rutas[`${{establecimiento.base_id}}|${{ambulancia.base_id}}`]
        : null;
      const vuelta = retorno ? retorno.distancia_metros : 0;
      const total = (ida ?? 0) + vuelta;
      return {{
        ida: ida ?? 0,
        vuelta,
        minutos: ida === null
          ? null
          : (total / 1000) / VELOCIDAD_KMH * 60 + TIEMPO_ATENCION_MIN
      }};
    }}

    function minutosTexto(minutos) {{
      if (minutos === null) return "Sin ruta";
      const redondeado = Math.round(minutos * 10) / 10;
      return `${{redondeado.toLocaleString("es-AR")}} min`;
    }}

    function minutosRestantes(despacho) {{
      if (despacho.liberacionEn === null || despacho.liberacionEn === undefined) {{
        return despacho.tiempos.minutos;
      }}
      return Math.max(0, (despacho.liberacionEn - Date.now()) / 60000);
    }}

    function baseDeAmbulancia(ambulanciaId) {{
      const ambulancia = ambulanciasPorId[ambulanciaId];
      return ambulancia ? ambulancia.base_id : "—";
    }}

    function formatearHora(marca) {{
      if (!marca) return "";
      return new Date(marca).toLocaleTimeString("es-AR", {{
        hour: "2-digit",
        minute: "2-digit"
      }});
    }}

    function refrescarSelectorAmbulancias() {{
      const idsEnUso = new Set(
        [...despachos.values()].map((item) => item.alternativa.ambulancia_id)
      );
      const seleccionada = selectorAmbulancia.value;
      selectorAmbulancia.length = 0;
      const inicial = new Option("Seleccionar ambulancia…", "", true, true);
      inicial.disabled = true;
      selectorAmbulancia.add(inicial);
      datos.ambulancias.forEach((ambulancia) => {{
        if (idsEnUso.has(ambulancia.id)) return;
        const etiqueta = `${{ambulancia.nombre || ambulancia.id}}` +
          `${{ambulancia.reserva ? " (reserva, solo gravedad 3)" : ""}}`;
        selectorAmbulancia.add(new Option(etiqueta, ambulancia.id));
      }});
      const sigueDisponible = seleccionada &&
        [...selectorAmbulancia.options].some(
          (opcion) => opcion.value === seleccionada
        );
      selectorAmbulancia.value = sigueDisponible ? seleccionada : "";
    }}

    function refrescarSelectorEmergencias() {{
      const seleccionada = selectorEmergencia.value;
      selectorEmergencia.length = 0;
      const inicial = new Option("Seleccionar emergencia…", "", true, true);
      inicial.disabled = true;
      selectorEmergencia.add(inicial);
      datos.emergencias.forEach((emergencia) => {{
        selectorEmergencia.add(
          new Option(
            `${{emergencia.id}} — gravedad ${{emergencia.gravedad}}`,
            emergencia.id
          )
        );
      }});
      const sigueDisponible = seleccionada &&
        [...selectorEmergencia.options].some(
          (opcion) => opcion.value === seleccionada
        );
      selectorEmergencia.value = sigueDisponible ? seleccionada : "";
    }}

    function refrescarSelectores() {{
      refrescarSelectorAmbulancias();
      refrescarSelectorEmergencias();
    }}

    function prepararSiguienteDespacho() {{
      refrescarSelectores();
      selectorEstablecimiento.value = "";
      dibujarAlternativa();
    }}

    function registrarAtendida(emergenciaId, item) {{
      atendidas.set(`${{item.alternativa.emergencia_id}}|${{item.alternativa.ambulancia_id}}`, {{
        alternativa: item.alternativa,
        pacientes: item.pacientes,
        tiempos: item.tiempos,
        hora: Date.now()
      }});
    }}

    function renderDashboard() {{
      const enUso = [...despachos.values()].sort(
        (a, b) => a.alternativa.ambulancia_id.localeCompare(b.alternativa.ambulancia_id)
      );
      const idsEnUso = new Set(enUso.map((item) => item.alternativa.ambulancia_id));
      const disponibles = datos.ambulancias
        .filter((ambulancia) => !idsEnUso.has(ambulancia.id))
        .map((ambulancia) => escapar(nombreDeAmbulancia(ambulancia.id)));
      const detalleDisponibles = disponibles.length
        ? `: ${{disponibles.join(", ")}}`
        : "";
      dashboardResumen.innerHTML =
        `<span><strong>${{enUso.length}}</strong> en uso</span>` +
        `<span><strong>${{disponibles.length}}</strong> disponibles${{detalleDisponibles}}</span>`;
      if (!enUso.length) {{
        dashboardLista.innerHTML =
          '<li class="dashboard-vacio">Ninguna ambulancia en uso. Elegí una alternativa factible y usá “Poner ambulancia en uso”.</li>';
      }} else {{
        dashboardLista.innerHTML = enUso.map((item) => {{
          const alternativa = item.alternativa;
          const restante = minutosRestantes(item);
          return `<li class="dashboard-item">
            <div class="dashboard-item-titulo">
              <strong>${{escapar(nombreDeAmbulancia(alternativa.ambulancia_id))}} · ${{escapar(baseDeAmbulancia(alternativa.ambulancia_id))}}</strong>
              <span class="dashboard-estado">En uso</span>
            </div>
            <div class="dashboard-item-detalle">${{escapar(alternativa.emergencia_id)}} → ${{escapar(alternativa.establecimiento_id)}}</div>
            <div class="dashboard-item-tiempo">Disponible en <strong>${{minutosTexto(restante)}}</strong> <span class="dashboard-auto">· liberación automática</span></div>
            <div class="dashboard-item-tramos">Recorrido ${{mostrarMetros(item.tiempos.ida)}} + regreso ${{mostrarMetros(item.tiempos.vuelta)}}</div>
            <div>Pacientes: ${{item.pacientes}}</div>
            <button type="button" class="boton-secundario" data-liberar="${{escapar(alternativa.ambulancia_id)}}">Finalizar esta unidad</button>
          </li>`;
        }}).join("");
      }}
      renderUrgencias();
    }}

    botonAsignar.addEventListener("click", () => {{
      const alternativa = alternativasPorClave[
        `${{selectorAmbulancia.value}}|${{selectorEmergencia.value}}|${{selectorEstablecimiento.value}}`
      ];
      if (!alternativa || !alternativa.es_factible || !destinoPermitido(alternativa)) {{
        resultadoDespacho.textContent = "Elegí una alternativa factible para despacharla.";
        return;
      }}
      const emergenciaId = alternativa.emergencia_id;
      const ambulanciaId = alternativa.ambulancia_id;
      const pacientes = Number(pacientesDespacho.value);
      const emergencia = datos.emergencias.find(e => e.id === emergenciaId);
      const servicios = serviciosEmergencia(emergenciaId);
      const pendientes = emergencia.cantidad_pacientes - servicios.reduce((s, item) => s + item.pacientes, 0);
      if (!Number.isInteger(pacientes) || pacientes < 0 || pacientes > ambulanciasPorId[ambulanciaId].capacidad_pacientes || pacientes > pendientes) {{
        resultadoDespacho.textContent = "Revisá los pacientes: no superar la capacidad de la unidad ni los pacientes pendientes. Usá 0 para apoyo.";
        return;
      }}
      if (servicios.some(item => item.alternativa.ambulancia_id === ambulanciaId)) {{
        resultadoDespacho.textContent = "Esta unidad ya fue asignada a esta emergencia.";
        return;
      }}
      const ocupada = [...despachos.values()].find(
        (item) => item.alternativa.ambulancia_id === ambulanciaId
      );
      if (ocupada) {{
        resultadoDespacho.textContent =
          `La ambulancia ${{nombreDeAmbulancia(ambulanciaId)}} ya está en uso en ` +
          `${{ocupada.alternativa.emergencia_id}}.`;
        return;
      }}
      const tiempos = tiempoHastaDisponible(alternativa);
      const liberacionEn = tiempos.minutos === null
        ? null
        : Date.now() + tiempos.minutos * 60000;
      despachos.set(ambulanciaId, {{ alternativa, tiempos, liberacionEn, pacientes }});
      resultadoDespacho.textContent =
        `${{emergenciaId}} asignada a ${{nombreDeAmbulancia(ambulanciaId)}}. ` +
        `Disponible en ${{minutosTexto(tiempos.minutos)}} ` +
        "(se libera automáticamente). Ya podés elegir otra urgencia.";
      prepararSiguienteDespacho();
      renderDashboard();
    }});

    dashboardLista.addEventListener("click", (event) => {{
      const boton = event.target.closest("[data-liberar]");
      if (!boton) return;
      const emergenciaId = boton.getAttribute("data-liberar");
      const item = despachos.get(emergenciaId);
      if (!item) return;
      despachos.delete(emergenciaId);
      registrarAtendida(emergenciaId, item);
      resultadoDespacho.textContent =
        `Unidad finalizada en ${{item.alternativa.emergencia_id}}. ` +
        `${{nombreDeAmbulancia(item.alternativa.ambulancia_id)}} disponible.`;
      refrescarSelectores();
      renderDashboard();
    }});

    function liberarVencidos() {{
      const ahora = Date.now();
      const liberadas = [];
      [...despachos.entries()].forEach(([emergenciaId, item]) => {{
        if (item.liberacionEn === null || item.liberacionEn === undefined) return;
        if (ahora < item.liberacionEn) return;
        despachos.delete(emergenciaId);
        registrarAtendida(emergenciaId, item);
        liberadas.push({{
          emergenciaId: item.alternativa.emergencia_id,
          ambulanciaId: item.alternativa.ambulancia_id
        }});
      }});
      return liberadas;
    }}

    function actualizarLiberaciones() {{
      const liberadas = liberarVencidos();
      if (liberadas.length) {{
        resultadoDespacho.textContent = liberadas.map(
          (item) =>
            `Liberación automática: ${{item.emergenciaId}} atendida, ` +
            `${{nombreDeAmbulancia(item.ambulanciaId)}} disponible.`
        ).join(" ");
        refrescarSelectores();
        renderDashboard();
        return;
      }}
      if (despachos.size) renderDashboard();
    }}

    setInterval(actualizarLiberaciones, 1000);

    const formularioUrgencia = document.getElementById("form-urgencia");
    const entradaUrgenciaId = document.getElementById("urgencia-id");
    const selectorUrgenciaGravedad = document.getElementById("urgencia-gravedad");
    const entradaUrgenciaCalle = document.getElementById("urgencia-calle");
    const entradaUrgenciaNumero = document.getElementById("urgencia-numero");
    const botonBuscarDireccion = document.getElementById("urgencia-buscar");
    const botonElegirMapa = document.getElementById("urgencia-elegir-mapa");
    const resultadoUrgencia = document.getElementById("resultado-urgencia");
    const resultadosDireccion = document.getElementById("resultados-direccion");
    const listaUrgencias = document.getElementById("lista-urgencias");
    let eligiendoUbicacion = false;
    let marcadorUbicacion = null;
    let ubicacionUrgencia = null;
    let candidatosDireccion = [];

    const PREFIJOS_CALLE = [
      "AVENIDA", "AVDA", "AV", "BOULEVARD", "BV",
      "CALLE", "PASAJE", "PJE", "RUTA", "R"
    ];
    const PALABRAS_IGNORADAS = ["DE", "DEL", "LA", "LAS", "LOS", "EL", "Y"];

    function normalizarCalle(texto) {{
      return (texto || "")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .toUpperCase()
        .replace(/[^A-Z0-9]+/g, " ")
        .trim()
        .replace(/\s+/g, " ");
    }}

    function variantesCalle(consulta) {{
      const variantes = new Set([consulta]);
      const palabras = consulta.split(" ").filter(Boolean);
      if (palabras.length > 1 && PREFIJOS_CALLE.includes(palabras[0])) {{
        variantes.add(palabras.slice(1).join(" "));
      }}
      const sinIgnoradas = palabras.filter((palabra) => !PALABRAS_IGNORADAS.includes(palabra));
      if (sinIgnoradas.length && sinIgnoradas.length !== palabras.length) {{
        variantes.add(sinIgnoradas.join(" "));
      }}
      return [...variantes];
    }}

    function ubicacionValida(latitud, longitud) {{
      return Number.isFinite(latitud) && Number.isFinite(longitud) &&
        latitud >= limitesGrafo.minLat && latitud <= limitesGrafo.maxLat &&
        longitud >= limitesGrafo.minLon && longitud <= limitesGrafo.maxLon;
    }}

    function longitudPolilinea(coordenadas) {{
      let total = 0;
      for (let i = 1; i < coordenadas.length; i += 1) {{
        total += distanciaHaversine(
          coordenadas[i - 1][0], coordenadas[i - 1][1],
          coordenadas[i][0], coordenadas[i][1]
        );
      }}
      return total;
    }}

    function coordenadaEnBloque(bloque, numero, rango) {{
      const coordenadas = bloque.coords || [];
      if (!coordenadas.length) return null;
      if (coordenadas.length === 1) {{
        return {{ lat: coordenadas[0][1], lon: coordenadas[0][0] }};
      }}
      let fraccion = 0.5;
      if (numero !== null && rango && rango[1] > rango[0]) {{
        fraccion = (numero - rango[0]) / (rango[1] - rango[0]);
        fraccion = Math.min(1, Math.max(0, fraccion));
      }}
      const total = longitudPolilinea(coordenadas);
      if (total <= 0) {{
        return {{ lat: coordenadas[0][1], lon: coordenadas[0][0] }};
      }}
      const objetivo = fraccion * total;
      let recorrido = 0;
      for (let i = 1; i < coordenadas.length; i += 1) {{
        const [lonA, latA] = coordenadas[i - 1];
        const [lonB, latB] = coordenadas[i];
        const tramo = distanciaHaversine(lonA, latA, lonB, latB);
        if (recorrido + tramo >= objetivo) {{
          const proporcion = tramo === 0 ? 0 : (objetivo - recorrido) / tramo;
          return {{
            lat: latA + (latB - latA) * proporcion,
            lon: lonA + (lonB - lonA) * proporcion
          }};
        }}
        recorrido += tramo;
      }}
      const ultimo = coordenadas[coordenadas.length - 1];
      return {{ lat: ultimo[1], lon: ultimo[0] }};
    }}

    function bloquesPorCalle(consulta) {{
      const variantes = variantesCalle(consulta);
      const exactos = datos.direcciones.filter((bloque) =>
        variantes.some((variante) => bloque.alias.includes(variante))
      );
      if (exactos.length) return exactos;
      const prefijos = datos.direcciones.filter((bloque) =>
        variantes.some((variante) =>
          bloque.alias.some((alias) => alias.startsWith(variante))
        )
      );
      if (prefijos.length) return prefijos;
      return datos.direcciones.filter((bloque) =>
        variantes.some((variante) =>
          bloque.alias.some((alias) => alias.includes(variante))
        )
      );
    }}

    function buscarDirecciones(calle, numeroTexto) {{
      const consulta = normalizarCalle(calle);
      if (!consulta) return [];
      const variantes = variantesCalle(consulta);
      const textoNumero = String(numeroTexto || "").trim();
      const numero = /^\d+$/.test(textoNumero) ? Number(textoNumero) : null;
      const bloques = bloquesPorCalle(consulta);
      const resultados = bloques.map((bloque) => {{
        const exacto = variantes.some((variante) => bloque.alias.includes(variante));
        let rango = null;
        let distancia = 0;
        if (numero !== null) {{
          const paridad = numero % 2 === 0 ? bloque.par : bloque.impar;
          if (!paridad) {{
            distancia = 1000000;
          }} else {{
            rango = paridad;
            if (numero < paridad[0]) distancia = paridad[0] - numero;
            else if (numero > paridad[1]) distancia = numero - paridad[1];
            else distancia = 0;
          }}
        }}
        const punto = coordenadaEnBloque(bloque, numero, rango);
        return {{
          bloque,
          exacto,
          distancia,
          punto,
          calle: bloque.calle,
          numero,
          etiqueta: numero === null ? bloque.calle : `${{bloque.calle}} ${{numero}}`
        }};
      }}).filter((resultado) => resultado.punto);
      resultados.sort((a, b) =>
        (a.exacto === b.exacto ? 0 : a.exacto ? -1 : 1) ||
        (a.distancia - b.distancia) ||
        a.calle.localeCompare(b.calle, "es")
      );
      return resultados.slice(0, 5);
    }}

    function limpiarMarcadorUbicacion() {{
      if (marcadorUbicacion) {{
        mapa.removeLayer(marcadorUbicacion);
        marcadorUbicacion = null;
      }}
    }}

    function fijarUbicacionUrgencia(latitud, longitud, etiqueta) {{
      if (!ubicacionValida(latitud, longitud)) {{
        return false;
      }}
      ubicacionUrgencia = {{ latitud, longitud, etiqueta: etiqueta || null }};
      if (!marcadorUbicacion) {{
        marcadorUbicacion = L.circleMarker([latitud, longitud], {{
          radius: 8,
          color: "#124e7f",
          weight: 3,
          fillColor: "#78b9ff",
          fillOpacity: 0.85
        }}).addTo(mapa);
      }} else {{
        marcadorUbicacion.setLatLng([latitud, longitud]);
      }}
      marcadorUbicacion.bindPopup(
        etiqueta ? `Ubicación: ${{escapar(etiqueta)}}` : "Ubicación elegida en el mapa"
      );
      return true;
    }}

    function limpiarUbicacion() {{
      limpiarMarcadorUbicacion();
      ubicacionUrgencia = null;
      candidatosDireccion = [];
      entradaUrgenciaCalle.value = "";
      entradaUrgenciaNumero.value = "";
      resultadosDireccion.innerHTML = "";
    }}

    function renderResultadosDireccion() {{
      if (!candidatosDireccion.length) {{
        resultadosDireccion.innerHTML = "";
        return;
      }}
      resultadosDireccion.innerHTML = candidatosDireccion.map((resultado, indice) => {{
        const seleccionado = ubicacionUrgencia &&
          ubicacionUrgencia.etiqueta === resultado.etiqueta;
        return `<button type="button"
                        class="resultado-direccion-item${{seleccionado ? " seleccionado" : ""}}"
                        data-indice-direccion="${{indice}}">
          <span>${{escapar(resultado.etiqueta)}}${{resultado.exacto ? "" : " <em>(aproximada)</em>"}}</span>
          <span class="urgencia-badge">Elegir</span>
        </button>`;
      }}).join("");
    }}

    function seleccionarCandidato(indice) {{
      const resultado = candidatosDireccion[indice];
      if (!resultado) return;
      if (!fijarUbicacionUrgencia(
        resultado.punto.lat, resultado.punto.lon, resultado.etiqueta
      )) {{
        resultadoUrgencia.textContent = "La dirección quedó fuera del área del grafo vial.";
        return;
      }}
      entradaUrgenciaCalle.value = resultado.calle;
      entradaUrgenciaNumero.value = resultado.numero === null
        ? ""
        : String(resultado.numero);
      resultadoUrgencia.textContent = `Ubicación seleccionada: ${{resultado.etiqueta}}.`;
      renderResultadosDireccion();
    }}

    botonBuscarDireccion.addEventListener("click", () => {{
      const calle = entradaUrgenciaCalle.value.trim();
      const numero = entradaUrgenciaNumero.value.trim();
      if (!calle) {{
        resultadoUrgencia.textContent = "Ingresá el nombre de la calle.";
        entradaUrgenciaCalle.focus();
        return;
      }}
      if (!datos.direcciones.length) {{
        resultadoUrgencia.textContent =
          "No hay índice de direcciones disponible. Usá Elegir en el mapa.";
        return;
      }}
      candidatosDireccion = buscarDirecciones(calle, numero);
      if (!candidatosDireccion.length) {{
        limpiarMarcadorUbicacion();
        ubicacionUrgencia = null;
        resultadosDireccion.innerHTML =
          `<p class="resultado-direccion-vacio">No se encontró la dirección. Probá con otra calle o elegí la ubicación en el mapa.</p>`;
        resultadoUrgencia.textContent = "";
        return;
      }}
      seleccionarCandidato(0);
    }});

    resultadosDireccion.addEventListener("click", (event) => {{
      const boton = event.target.closest("[data-indice-direccion]");
      if (!boton) return;
      seleccionarCandidato(Number(boton.getAttribute("data-indice-direccion")));
    }});

    function cancelarSeleccionMapa() {{
      eligiendoUbicacion = false;
      botonElegirMapa.classList.remove("activo");
      botonElegirMapa.textContent = "Elegir en el mapa";
      mapa.getContainer().style.cursor = "";
    }}

    botonElegirMapa.addEventListener("click", () => {{
      eligiendoUbicacion = !eligiendoUbicacion;
      botonElegirMapa.classList.toggle("activo", eligiendoUbicacion);
      botonElegirMapa.textContent = eligiendoUbicacion
        ? "Cancelar selección"
        : "Elegir en el mapa";
      mapa.getContainer().style.cursor = eligiendoUbicacion ? "crosshair" : "";
      resultadoUrgencia.textContent = eligiendoUbicacion
        ? "Hacé clic en el mapa para fijar la ubicación de la urgencia."
        : "";
    }});

    mapa.on("click", (event) => {{
      if (!eligiendoUbicacion) return;
      const latitud = event.latlng.lat;
      const longitud = event.latlng.lng;
      if (!fijarUbicacionUrgencia(latitud, longitud, null)) {{
        resultadoUrgencia.textContent = "Ese punto está fuera del área del grafo vial.";
        return;
      }}
      candidatosDireccion = [];
      resultadosDireccion.innerHTML = "";
      entradaUrgenciaCalle.value = "";
      entradaUrgenciaNumero.value = "";
      cancelarSeleccionMapa();
      resultadoUrgencia.textContent = "Ubicación elegida en el mapa.";
    }});

    function invalidarUbicacionBuscada() {{
      if (ubicacionUrgencia && ubicacionUrgencia.etiqueta) {{
        limpiarMarcadorUbicacion();
        ubicacionUrgencia = null;
        candidatosDireccion = [];
        resultadosDireccion.innerHTML = "";
      }}
    }}

    entradaUrgenciaCalle.addEventListener("input", invalidarUbicacionBuscada);
    entradaUrgenciaNumero.addEventListener("input", invalidarUbicacionBuscada);

    function siguienteIdUrgencia() {{
      const usados = new Set(datos.emergencias.map((emergencia) => emergencia.id));
      let numero = 1;
      while (usados.has(`U${{numero}}`)) numero += 1;
      return `U${{numero}}`;
    }}

    function agregarUrgencia(id, gravedad, latitud, longitud, direccion) {{
      const pacientes = Number(document.getElementById("urgencia-pacientes").value);
      const unidades = Number(document.getElementById("urgencia-unidades").value);
      if (!Number.isInteger(pacientes) || pacientes < 1 || !Number.isInteger(unidades) || unidades < 1) {{
        throw new Error("Pacientes y mínimo de ambulancias deben ser enteros positivos.");
      }}
      const cercano = nodoMasCercano(longitud, latitud);
      if (cercano.indice < 0) {{
        throw new Error("El grafo vial no está disponible.");
      }}
      const [nodoLon, nodoLat] = grafo.nodos[cercano.indice];
      const complejidad = Math.min(gravedad, 2);
      const nueva = {{
        id,
        latitud,
        longitud,
        direccion: direccion || null,
        nodo_id: `${{nodoLon.toFixed(7)}},${{nodoLat.toFixed(7)}}`,
        distancia_al_nodo_m: Math.round(cercano.distancia * 1000) / 1000,
        gravedad,
        complejidad_requerida: complejidad,
        cantidad_pacientes: Number(document.getElementById("urgencia-pacientes").value),
        ambulancias_requeridas: Number(document.getElementById("urgencia-unidades").value),
        equipamiento_requerido: [],
        minutos_espera: 0,
        estado: "pendiente",
        datos_simulados: true,
        es_agregada: true
      }};
      datos.emergencias.push(nueva);

      const rutasIniciales = new Map();
      datos.ambulancias.forEach((ambulancia) => {{
        const ruta = caminoMinimo(
          grafo.indices[ambulancia.nodo_id],
          cercano.indice
        );
        datos.rutas_ambulancia_emergencia[`${{ambulancia.id}}|${{id}}`] = {{
          distancia_metros: ruta.distancia,
          coordenadas: coordenadasCamino(ruta.camino)
        }};
        rutasIniciales.set(ambulancia.id, ruta);
      }});

      const rutasDestino = new Map();
      datos.establecimientos.forEach((establecimiento) => {{
        const ruta = caminoMinimo(
          cercano.indice,
          grafo.indices[establecimiento.nodo_id]
        );
        datos.rutas_emergencia_establecimiento[`${{id}}|${{establecimiento.id}}`] = {{
          distancia_metros: ruta.distancia,
          coordenadas: coordenadasCamino(ruta.camino)
        }};
        rutasDestino.set(establecimiento.id, ruta);
      }});

      datos.ambulancias.forEach((ambulancia) => {{
        const rutaInicial = rutasIniciales.get(ambulancia.id) || {{
          distancia: null,
          camino: []
        }};
        datos.establecimientos.forEach((establecimiento) => {{
          const rutaDestino = rutasDestino.get(establecimiento.id) || {{
            distancia: null,
            camino: []
          }};
          const motivos = [];
          if (!ambulancia.disponible) motivos.push("ambulancia_no_disponible");
          if (ambulancia.reserva && nueva.gravedad < 3) {{
            motivos.push("ambulancia_de_reserva_solo_gravedad_3");
          }}
          if (ambulancia.complejidad < nueva.complejidad_requerida) {{
            motivos.push("complejidad_ambulancia_insuficiente");
          }}
          if (!nueva.equipamiento_requerido.every(
            (equipo) => ambulancia.equipamiento.includes(equipo)
          )) {{
            motivos.push("equipamiento_faltante");
          }}
          if (rutaInicial.distancia === null) {{
            motivos.push("sin_ruta_hasta_emergencia");
          }}
          if (!establecimiento.habilitado_destino) {{
            motivos.push("establecimiento_no_habilitado");
          }}
          if (establecimiento.complejidad_maxima < nueva.complejidad_requerida) {{
            motivos.push("complejidad_establecimiento_insuficiente");
          }}
          if (rutaDestino.distancia === null) {{
            motivos.push("sin_ruta_hasta_establecimiento");
          }}
          const distanciaTotal = rutaInicial.distancia !== null &&
            rutaDestino.distancia !== null
            ? rutaInicial.distancia + rutaDestino.distancia
            : null;
          const costo = distanciaTotal !== null
            ? distanciaTotal + establecimiento.penalizacion_metros
            : null;
          const alternativa = {{
            ambulancia_id: ambulancia.id,
            emergencia_id: id,
            establecimiento_id: establecimiento.id,
            distancia_ambulancia_emergencia_m: rutaInicial.distancia,
            distancia_emergencia_establecimiento_m: rutaDestino.distancia,
            distancia_total_m: distanciaTotal,
            penalizacion_establecimiento_m: establecimiento.penalizacion_metros,
            costo_seleccion: costo,
            es_factible: motivos.length === 0,
            motivos_descarte: motivos,
            es_agregada: true
          }};
          datos.alternativas.push(alternativa);
          alternativasPorClave[
            `${{ambulancia.id}}|${{id}}|${{establecimiento.id}}`
          ] = alternativa;
        }});
      }});

      crearMarcadorEmergencia(nueva);
      selectorEmergencia.add(new Option(`${{id}} — gravedad ${{gravedad}}`, id));
      return nueva;
    }}

    function estadoUrgencia(urgenciaId) {{
      if ([...despachos.values()].some(item => item.alternativa.emergencia_id === urgenciaId)) return "en-uso";
      if (coberturaCompleta(urgenciaId)) return "atendida";
      return "sin-asignar";
    }}

    function renderUrgencias() {{
      const ordenEstado = {{ "en-uso": 0, "sin-asignar": 1, "atendida": 2 }};
      const urgencias = [...datos.emergencias].sort((a, b) => {{
        const diferencia = ordenEstado[estadoUrgencia(a.id)] -
          ordenEstado[estadoUrgencia(b.id)];
        if (diferencia) return diferencia;
        if (Boolean(b.es_agregada) !== Boolean(a.es_agregada)) {{
          return b.es_agregada ? 1 : -1;
        }}
        return a.id.localeCompare(b.id, "es", {{ numeric: true }});
      }});
      listaUrgencias.innerHTML = urgencias.map((urgencia) => {{
        const activos = [...despachos.values()].filter(item => item.alternativa.emergencia_id === urgencia.id);
        const finalizados = [...atendidas.values()].filter(item => item.alternativa.emergencia_id === urgencia.id);
        const despacho = activos[0];
        const atencion = finalizados[0];
        let estado = "Sin asignar";
        let claseEstado = "urgencia-estado";
        if (despacho) {{
          estado = `En uso: ${{activos.map(item => escapar(nombreDeAmbulancia(item.alternativa.ambulancia_id))).join(", ")}}`;
          claseEstado += " en-uso";
        }} else if (atencion) {{
          estado = coberturaCompleta(urgencia.id) ? `Atendida por ${{finalizados.map(item => escapar(nombreDeAmbulancia(item.alternativa.ambulancia_id))).join(", ")}}` : "Cobertura parcial: faltan recursos o pacientes por trasladar";
          claseEstado += " atendida";
        }}
        const hora = atencion ? formatearHora(atencion.hora) : "";
        const servicios = serviciosEmergencia(urgencia.id);
        estado += ` · ${{servicios.length}}/${{urgencia.ambulancias_requeridas || 1}} unidades mínimas · ${{servicios.reduce((s, item) => s + item.pacientes, 0)}}/${{urgencia.cantidad_pacientes}} pacientes`;
        if (despacho && !coberturaCompleta(urgencia.id)) estado += " · Cobertura parcial";
        const referencia = urgencia.es_agregada
          ? `<span class="urgencia-badge">agregada</span><span>${{escapar(urgencia.direccion || "Ubicación elegida en el mapa")}}</span>`
          : "";
        const atributoQuitar = despacho
          ? ' disabled title="No se puede quitar mientras la ambulancia está en uso"'
          : "";
        const botonQuitar = urgencia.es_agregada
          ? `<button type="button" class="boton-secundario" data-quitar-urgencia="${{escapar(urgencia.id)}}"${{atributoQuitar}}>Quitar</button>`
          : "";
        return `<li class="urgencia-item${{atencion ? " atendida" : ""}}">
          <span class="urgencia-datos">
            <strong>${{escapar(urgencia.id)}}</strong>
            <span class="urgencia-grado gravedad-${{urgencia.gravedad}}">Grado ${{urgencia.gravedad}} (${{descripcionGravedad[urgencia.gravedad]}})</span>
            ${{referencia}}
          </span>
          <span class="urgencia-datos">
            <span class="${{claseEstado}}">${{estado}}</span>
            ${{hora ? `<span class="urgencia-hora">${{hora}}</span>` : ""}}
            ${{botonQuitar}}
          </span>
        </li>`;
      }}).join("");
    }}

    function quitarUrgencia(id) {{
      if ([...despachos.values()].some(item => item.alternativa.emergencia_id === id)) {{
        resultadoUrgencia.textContent =
          "No se puede quitar una urgencia con la ambulancia en uso.";
        return;
      }}
      const indice = datos.emergencias.findIndex(
        (emergencia) => emergencia.id === id && emergencia.es_agregada
      );
      if (indice < 0) return;
      const eraSeleccionada = selectorEmergencia.value === id;
      if (marcadoresEmergencia[id]) {{
        mapa.removeLayer(marcadoresEmergencia[id]);
        delete marcadoresEmergencia[id];
      }}
      const opcion = [...selectorEmergencia.options].find((item) => item.value === id);
      if (opcion) opcion.remove();
      datos.emergencias.splice(indice, 1);
      for (let i = datos.alternativas.length - 1; i >= 0; i -= 1) {{
        if (datos.alternativas[i].emergencia_id === id) datos.alternativas.splice(i, 1);
      }}
      Object.keys(alternativasPorClave).forEach((clave) => {{
        if (clave.split("|")[1] === id) delete alternativasPorClave[clave];
      }});
      Object.keys(datos.rutas_ambulancia_emergencia).forEach((clave) => {{
        if (clave.endsWith(`|${{id}}`)) delete datos.rutas_ambulancia_emergencia[clave];
      }});
      Object.keys(datos.rutas_emergencia_establecimiento).forEach((clave) => {{
        if (clave.startsWith(`${{id}}|`)) delete datos.rutas_emergencia_establecimiento[clave];
      }});
      despachos.delete(id);
      [...atendidas.entries()].forEach(([clave, item]) => {{ if (item.alternativa.emergencia_id === id) atendidas.delete(clave); }});
      refrescarSelectores();
      if (eraSeleccionada) {{
        selectorEmergencia.value = "";
        botonAsignar.disabled = true;
        resultadoAlternativa.textContent =
          "Elegí los tres elementos para inspeccionar una alternativa.";
        dibujadorManual.limpiar();
      }}
      entradaUrgenciaId.value = siguienteIdUrgencia();
      renderDashboard();
    }}

    formularioUrgencia.addEventListener("submit", (event) => {{
      event.preventDefault();
      const id = entradaUrgenciaId.value.trim();
      const gravedad = Number(selectorUrgenciaGravedad.value);
      if (!id) {{
        resultadoUrgencia.textContent = "Ingresá un ID para la urgencia.";
        entradaUrgenciaId.focus();
        return;
      }}
      if (!/^[A-Za-z0-9_-]+$/.test(id)) {{
        resultadoUrgencia.textContent =
          "Usá solo letras, números, guiones o guiones bajos.";
        entradaUrgenciaId.focus();
        return;
      }}
      if (datos.emergencias.some((emergencia) => emergencia.id === id)) {{
        resultadoUrgencia.textContent = `El ID ${{id}} ya existe. Elegí otro.`;
        entradaUrgenciaId.focus();
        return;
      }}
      if (!ubicacionUrgencia) {{
        resultadoUrgencia.textContent =
          "Buscá una dirección o elegí una ubicación en el mapa.";
        return;
      }}
      try {{
        const nueva = agregarUrgencia(
          id, gravedad, ubicacionUrgencia.latitud, ubicacionUrgencia.longitud,
          ubicacionUrgencia.etiqueta
        );
        const referencia = ubicacionUrgencia.etiqueta
          ? `Ubicación: ${{ubicacionUrgencia.etiqueta}}.`
          : "Ubicación elegida en el mapa.";
        resultadoUrgencia.textContent =
          `Urgencia ${{nueva.id}} agregada con grado ${{gravedad}}. ` +
          `${{referencia}}`;
        entradaUrgenciaId.value = siguienteIdUrgencia();
        limpiarUbicacion();
        selectorEmergencia.value = nueva.id;
        renderDashboard();
        dibujarAlternativa();
      }} catch (error) {{
        resultadoUrgencia.textContent = error.message;
      }}
    }});

    listaUrgencias.addEventListener("click", (event) => {{
      const boton = event.target.closest("[data-quitar-urgencia]");
      if (!boton) return;
      const id = boton.getAttribute("data-quitar-urgencia");
      quitarUrgencia(id);
      resultadoUrgencia.textContent = `Urgencia ${{id}} quitada.`;
    }});

    entradaUrgenciaId.value = siguienteIdUrgencia();
    renderDashboard();

  </script>
</body>
</html>
"""
