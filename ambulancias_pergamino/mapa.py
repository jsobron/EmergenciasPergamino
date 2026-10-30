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
    }


def _json_para_script(datos: dict[str, Any]) -> str:
    return json.dumps(datos, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def exportar_mapa(
    entrada: Path,
    configuracion_ambulancias: Path,
    salida: Path,
    configuracion_establecimientos: Path = Path("config/establecimientos.json"),
    configuracion_emergencias: Path = Path("config/emergencias.json"),
) -> None:
    datos = json.loads(entrada.read_text(encoding="utf-8"))
    datos_mapa = preparar_datos_mapa(
        datos,
        configuracion_ambulancias,
        configuracion_establecimientos,
        configuracion_emergencias,
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
  <title>Ambulancias de Pergamino — datos simulados</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
        integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
  <style>
    :root {{
      color-scheme: light;
      --surface: #ffffff;
      --surface-muted: #f4f7f6;
      --text: #17211d;
      --text-muted: #52615b;
      --border: #cbd6d1;
      --prioritario: #b42318;
      --destino: #075c9e;
      --solo-base: #5c6762;
      --route: #006bd6;
      --route-first: #7b2cbf;
      --route-second: #00875a;
      --gravedad-alta: #8b1e1e;
      --gravedad-media: #c2410c;
      --gravedad-baja: #d6a800;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ height: 100%; margin: 0; }}
    body {{
      display: grid;
      grid-template-rows: auto auto auto auto auto auto 1fr;
      min-height: 100%;
      background: var(--surface-muted);
      color: var(--text);
      font: 16px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif;
    }}
    header {{
      display: grid;
      grid-template-columns: minmax(14rem, 1fr) minmax(28rem, 2fr);
      align-items: end;
      gap: 1rem;
      padding: 0.75rem 1rem;
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      z-index: 1000;
    }}
    h1 {{ margin: 0; font-size: 1.25rem; line-height: 1.2; }}
    .subtitle {{ margin: 0.25rem 0 0; color: var(--text-muted); font-size: 0.875rem; }}
    .badge {{
      display: inline-block;
      margin-left: 0.375rem;
      padding: 0.125rem 0.375rem;
      border: 1px solid #b36b50;
      color: #793016;
      font-size: 0.75rem;
      font-weight: 700;
      letter-spacing: 0.02em;
      text-transform: uppercase;
    }}
    .controls {{ display: grid; grid-template-columns: 1fr 1fr minmax(11rem, auto); gap: 0.75rem; }}
    .field {{ display: grid; gap: 0.25rem; }}
    label {{ font-size: 0.75rem; font-weight: 700; color: var(--text-muted); }}
    select {{
      width: 100%;
      min-height: 2.5rem;
      padding: 0.375rem 0.5rem;
      border: 1px solid var(--border);
      border-radius: 0.25rem;
      background: var(--surface);
      color: var(--text);
      font: inherit;
    }}
    select:focus-visible {{ outline: 3px solid #78b9ff; outline-offset: 1px; }}
    #resultado {{
      align-self: end;
      min-height: 2.5rem;
      display: flex;
      align-items: center;
      padding: 0.375rem 0.75rem;
      border-left: 4px solid var(--route);
      background: #eaf4ff;
      font-weight: 700;
    }}
    .alternative-controls {{
      display: grid;
      grid-template-columns: repeat(3, minmax(10rem, 1fr));
      gap: 0.75rem;
      padding: 0.625rem 1rem;
      border-bottom: 1px solid var(--border);
      background: var(--surface);
      z-index: 900;
    }}
    .alternative-controls h2 {{ grid-column: 1 / -1; margin: 0; font-size: 1rem; }}
    #resultado-alternativa {{
      grid-column: 1 / -1;
      min-height: 2.5rem;
      padding: 0.5rem 0.75rem;
      border-left: 4px solid var(--route-first);
      background: #f5effb;
    }}
    #resultado-alternativa dl {{ display: flex; flex-wrap: wrap; gap: 0.25rem 1rem; margin: 0; }}
    #resultado-alternativa div {{ display: flex; gap: 0.25rem; }}
    #resultado-alternativa dt {{ font-weight: 700; }}
    #resultado-alternativa dd {{ margin: 0; }}
    .heuristic-controls {{
      display: grid;
      grid-template-columns: repeat(2, minmax(10rem, 1fr));
      gap: 0.75rem;
      padding: 0.625rem 1rem;
      border-bottom: 1px solid var(--border);
      background: var(--surface);
      z-index: 850;
    }}
    .heuristic-controls h2 {{ grid-column: 1 / -1; margin: 0; font-size: 1rem; }}
    #resultado-heuristica {{
      grid-column: 1 / -1;
      min-height: 2.5rem;
      padding: 0.5rem 0.75rem;
      border-left: 4px solid var(--route-second);
      background: #eaf7f1;
    }}
    .assignment-controls {{
      display: grid;
      grid-template-columns: minmax(12rem, 18rem) 1fr;
      gap: 0.75rem;
      padding: 0.625rem 1rem;
      border-bottom: 1px solid var(--border);
      background: var(--surface);
      z-index: 825;
    }}
    .assignment-controls h2 {{ grid-column: 1 / -1; margin: 0; font-size: 1rem; }}
    #resultado-asignacion {{
      grid-column: 1 / -1;
      max-height: 14rem;
      overflow: auto;
      min-height: 2.5rem;
      padding: 0.5rem 0.75rem;
      border-left: 4px solid var(--route);
      background: #eef4fb;
    }}
    #resultado-asignacion dl {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.25rem 1rem;
      margin: 0 0 0.5rem;
    }}
    #resultado-asignacion div {{ display: flex; gap: 0.25rem; }}
    #resultado-asignacion dt {{ font-weight: 700; }}
    #resultado-asignacion dd {{ margin: 0; }}
    .simulation-controls {{
      display: grid;
      grid-template-columns: minmax(10rem, 14rem) minmax(12rem, 18rem) 1fr;
      gap: 0.75rem;
      padding: 0.625rem 1rem;
      border-bottom: 1px solid var(--border);
      background: var(--surface);
      z-index: 800;
    }}
    .simulation-controls h2 {{ grid-column: 1 / -1; margin: 0; font-size: 1rem; }}
    #resultado-simulacion {{
      grid-column: 1 / -1;
      max-height: 16rem;
      overflow: auto;
      min-height: 2.5rem;
      padding: 0.5rem 0.75rem;
      border-left: 4px solid var(--route-second);
      background: #edf8f2;
    }}
    #resultado-simulacion dl {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.25rem 1rem;
      margin: 0 0 0.5rem;
    }}
    #resultado-simulacion div {{ display: flex; gap: 0.25rem; }}
    #resultado-simulacion dt {{ font-weight: 700; }}
    #resultado-simulacion dd {{ margin: 0; }}
    .evaluation-controls {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 0.75rem;
      padding: 0.625rem 1rem;
      border-bottom: 1px solid var(--border);
      background: var(--surface);
      z-index: 800;
    }}
    .evaluation-controls h2 {{ margin: 0; font-size: 1rem; }}
    #resultado-evaluacion {{
      max-height: 18rem;
      overflow: auto;
      min-height: 2.5rem;
      padding: 0.5rem 0.75rem;
      border-left: 4px solid var(--prioritario);
      background: #fdf2f1;
    }}
    #resultado-evaluacion p {{ margin: 0 0 0.5rem; }}
    .tabla-evaluacion {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.8125rem;
    }}
    .tabla-evaluacion th,
    .tabla-evaluacion td {{
      padding: 0.25rem 0.5rem;
      border-bottom: 1px solid var(--border);
      text-align: right;
      white-space: nowrap;
    }}
    .tabla-evaluacion th:first-child,
    .tabla-evaluacion td:first-child {{ text-align: left; }}
    .tabla-evaluacion thead th {{
      position: sticky;
      top: 0;
      background: var(--surface);
      font-weight: 700;
    }}
    .barra-reduccion {{
      display: inline-block;
      width: 4rem;
      height: 0.5rem;
      margin-right: 0.375rem;
      overflow: hidden;
      border-radius: 999px;
      background: #e3e8e5;
      vertical-align: middle;
    }}
    .barra-reduccion span {{
      display: block;
      height: 100%;
      background: var(--route-second);
    }}
    #mapa {{ width: 100%; min-height: 28rem; }}
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
      padding: 0.625rem 0.75rem;
      border: 1px solid var(--border);
      background: #fffffff2;
      box-shadow: 0 1px 4px #0003;
      color: var(--text);
      line-height: 1.5;
    }}
    .leyenda strong {{ display: block; margin-bottom: 0.25rem; }}
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
    .leyenda-muestra.ambulancia-conservada {{ background: var(--route-first); }}
    .leyenda-muestra.ambulancia-descartada {{ background: #8a8f8c; opacity: 0.45; }}
    .leyenda-muestra.establecimiento-conservado {{ background: var(--destino); }}
    .leyenda-muestra.establecimiento-excluido {{ background: #8a8f8c; opacity: 0.45; }}
    .leyenda-muestra.asignacion-atendida {{ background: var(--route-second); }}
    .leyenda-muestra.asignacion-sin-asignar {{ background: #8a8f8c; opacity: 0.45; }}
    @media (max-width: 760px) {{
      header {{ grid-template-columns: 1fr; align-items: stretch; }}
      .controls {{ grid-template-columns: 1fr 1fr; }}
      #resultado {{ grid-column: 1 / -1; }}
      .alternative-controls {{ grid-template-columns: 1fr; }}
      .alternative-controls h2, #resultado-alternativa {{ grid-column: auto; }}
      .heuristic-controls {{ grid-template-columns: 1fr; }}
      .heuristic-controls h2, #resultado-heuristica {{ grid-column: auto; }}
      .assignment-controls {{ grid-template-columns: 1fr; }}
      .assignment-controls h2, #resultado-asignacion {{ grid-column: auto; }}
      .simulation-controls {{ grid-template-columns: 1fr; }}
      .simulation-controls h2, #resultado-simulacion {{ grid-column: auto; }}
    }}
    @media (max-width: 480px) {{
      .controls {{ grid-template-columns: 1fr; }}
      #resultado {{ grid-column: auto; }}
    }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Red vial y ambulancias de Pergamino</h1>
      <p class="subtitle">6 bases, 5 emergencias y rutas dirigidas <span class="badge">Datos simulados</span></p>
    </div>
    <div class="controls" aria-label="Selección de recorrido">
      <div class="field">
        <label for="origen">Base de origen</label>
        <select id="origen"></select>
      </div>
      <div class="field">
        <label for="destino">Base de destino</label>
        <select id="destino"></select>
      </div>
      <div id="resultado" role="status" aria-live="polite"></div>
    </div>
  </header>
  <section class="alternative-controls" aria-labelledby="titulo-alternativas">
    <h2 id="titulo-alternativas">Visor manual de alternativas</h2>
    <div class="field"><label for="alternativa-ambulancia">Ambulancia</label><select id="alternativa-ambulancia"></select></div>
    <div class="field"><label for="alternativa-emergencia">Emergencia</label><select id="alternativa-emergencia"></select></div>
    <div class="field"><label for="alternativa-establecimiento">Establecimiento</label><select id="alternativa-establecimiento"></select></div>
    <div id="resultado-alternativa" role="status" aria-live="polite">Elegí los tres elementos para inspeccionar una alternativa.</div>
  </section>
  <section class="heuristic-controls" aria-labelledby="titulo-heuristicas">
    <h2 id="titulo-heuristicas">Reducción de candidatos — Etapa 6</h2>
    <div class="field"><label for="heuristica-emergencia">Emergencia</label><select id="heuristica-emergencia"></select></div>
    <div class="field"><label for="heuristica-alternativa">Alternativa reducida</label><select id="heuristica-alternativa"></select></div>
    <div id="resultado-heuristica" role="status" aria-live="polite">Elegí una emergencia para ver los candidatos conservados.</div>
  </section>
  <section class="assignment-controls" aria-labelledby="titulo-asignacion">
    <h2 id="titulo-asignacion">Asignación global — Etapa 7</h2>
    <div class="field"><label for="asignacion-conjunto">Conjunto de alternativas</label><select id="asignacion-conjunto"></select></div>
    <div id="resultado-asignacion" role="status" aria-live="polite">Elegí un conjunto para ver la asignación global.</div>
  </section>
  <section class="simulation-controls" aria-labelledby="titulo-simulacion">
    <h2 id="titulo-simulacion">Simulación — Etapa 8</h2>
    <div class="field"><label for="simulacion-etapa">Etapa lógica</label><select id="simulacion-etapa"></select></div>
    <div class="field"><label for="simulacion-emergencia">Emergencia</label><select id="simulacion-emergencia"></select></div>
    <div id="resultado-simulacion" role="status" aria-live="polite">Elegí un conjunto de asignación para ver la simulación.</div>
  </section>
  <section class="evaluation-controls" aria-labelledby="titulo-evaluacion">
    <h2 id="titulo-evaluacion">Evaluación comparativa — Etapa 9</h2>
    <div id="resultado-evaluacion" role="status" aria-live="polite">Cargando la comparación de escenarios…</div>
  </section>
  <main id="mapa" aria-label="Mapa vial de Pergamino"></main>

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
    const ambulanciasPorBase = Object.fromEntries(
      datos.ambulancias.map((ambulancia) => [ambulancia.base_id, ambulancia])
    );
    const establecimientosPorBase = Object.fromEntries(
      datos.establecimientos.map((establecimiento) => [establecimiento.base_id, establecimiento])
    );
    const establecimientosPorId = Object.fromEntries(
      datos.establecimientos.map((establecimiento) => [establecimiento.id, establecimiento])
    );
    const marcadoresBase = {{}};
    const marcadoresEmergencia = {{}};

    datos.bases.forEach((base) => {{
      const ambulancia = ambulanciasPorBase[base.id];
      const establecimiento = establecimientosPorBase[base.id];
      const esSame = base.id === "SAME";
      const tipo = base.id === "GUARDIA-1"
        ? "prioritario"
        : establecimiento ? "destino" : "solo-base";
      const icono = L.divIcon({{
        className: "",
        html: `<div class="base-icon ${{tipo}} ${{esSame ? "same" : ""}}">${{escapar(ambulancia.id)}}</div>`,
        iconSize: [32, 32], iconAnchor: [16, 16], popupAnchor: [0, -18]
      }});
      const disponibilidad = ambulancia.disponible ? "Disponible" : "No disponible";
      const recibePacientes = establecimiento ? "Sí" : "No";
      const detallesDestino = establecimiento ? `
          <li><strong>Prioridad:</strong> ${{establecimiento.prioridad}}</li>
          <li><strong>Penalización:</strong> ${{establecimiento.penalizacion_metros.toLocaleString("es-AR")}} m</li>
          <li><strong>Complejidad máxima:</strong> ${{establecimiento.complejidad_maxima}}</li>` : "";
      const contenido = `
        <h2 class="popup-title">${{escapar(base.nombre)}}</h2>
        <ul class="popup-list">
          <li><strong>Ambulancia:</strong> ${{escapar(ambulancia.id)}}</li>
          <li><strong>Complejidad:</strong> ${{ambulancia.complejidad}}</li>
          <li><strong>Capacidad:</strong> ${{ambulancia.capacidad_pacientes}} paciente</li>
          <li><strong>Estado:</strong> ${{disponibilidad}}</li>
          <li><strong>Recibe pacientes:</strong> ${{recibePacientes}}</li>
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
    datos.emergencias.forEach((emergencia) => {{
      const icono = L.divIcon({{
        className: "",
        html: `<div class="emergencia-icon gravedad-${{emergencia.gravedad}}"><span>!</span></div>`,
        iconSize: [28, 28], iconAnchor: [14, 14], popupAnchor: [0, -17]
      }});
      const equipamiento = emergencia.equipamiento_requerido.length
        ? emergencia.equipamiento_requerido.map(escapar).join(", ")
        : "Ninguno";
      const contenido = `
        <h2 class="popup-title">Emergencia ${{escapar(emergencia.id)}}</h2>
        <ul class="popup-list">
          <li><strong>Gravedad:</strong> ${{emergencia.gravedad}} — ${{descripcionGravedad[emergencia.gravedad]}}</li>
          <li><strong>Complejidad requerida:</strong> ${{emergencia.complejidad_requerida}}</li>
          <li><strong>Pacientes:</strong> ${{emergencia.cantidad_pacientes}}</li>
          <li><strong>Equipamiento:</strong> ${{equipamiento}}</li>
          <li><strong>Espera:</strong> ${{emergencia.minutos_espera.toLocaleString("es-AR")}} min</li>
          <li><strong>Estado:</strong> ${{escapar(emergencia.estado)}}</li>
          <li><strong>Ubicación:</strong> ${{emergencia.latitud.toFixed(7)}}, ${{emergencia.longitud.toFixed(7)}}</li>
          <li><strong>Nodo vial:</strong> ${{escapar(emergencia.nodo_id)}}</li>
          <li><strong>Distancia al nodo:</strong> ${{emergencia.distancia_al_nodo_m.toLocaleString("es-AR")}} m</li>
          <li><strong>Datos simulados:</strong> ${{emergencia.datos_simulados ? "Sí" : "No"}}</li>
        </ul>`;
      marcadoresEmergencia[emergencia.id] = L.marker(
        [emergencia.latitud, emergencia.longitud], {{
          icon: icono,
          title: `Emergencia ${{emergencia.id}} — gravedad ${{emergencia.gravedad}}`
        }}
      ).bindPopup(contenido).addTo(mapa);
    }});

    const leyenda = L.control({{ position: "bottomleft" }});
    leyenda.onAdd = () => {{
      const contenedor = L.DomUtil.create("div", "leyenda");
      contenedor.innerHTML = `
        <strong>Establecimientos</strong>
        <span class="leyenda-item"><i class="leyenda-muestra prioritario"></i>Destino prioritario</span>
        <span class="leyenda-item"><i class="leyenda-muestra destino"></i>Destino habilitado</span>
        <span class="leyenda-item"><i class="leyenda-muestra solo-base"></i>No recibe pacientes</span>
        <strong>Emergencias simuladas</strong>
        <span class="leyenda-item"><i class="leyenda-muestra emergencia gravedad-3"></i>Gravedad alta/crítica (3)</span>
        <span class="leyenda-item"><i class="leyenda-muestra emergencia gravedad-2"></i>Gravedad media (2)</span>
        <span class="leyenda-item"><i class="leyenda-muestra emergencia gravedad-1"></i>Gravedad baja (1)</span>
        <strong>Alternativa manual</strong>
        <span class="leyenda-item"><i class="leyenda-linea tramo-inicial"></i>Tramo ambulancia → emergencia</span>
        <span class="leyenda-item"><i class="leyenda-linea tramo-destino"></i>Tramo emergencia → establecimiento</span>
        <strong>Reducción de candidatos</strong>
        <span class="leyenda-item"><i class="leyenda-muestra ambulancia-conservada"></i>Ambulancia conservada</span>
        <span class="leyenda-item"><i class="leyenda-muestra ambulancia-descartada"></i>Ambulancia descartada</span>
        <span class="leyenda-item"><i class="leyenda-muestra establecimiento-conservado"></i>Establecimiento conservado</span>
        <span class="leyenda-item"><i class="leyenda-muestra establecimiento-excluido"></i>Establecimiento excluido</span>
        <strong>Asignación global</strong>
        <span class="leyenda-item"><i class="leyenda-muestra asignacion-atendida"></i>Emergencia atendida</span>
        <span class="leyenda-item"><i class="leyenda-muestra asignacion-sin-asignar"></i>Emergencia sin asignar</span>
        <span class="leyenda-item"><i class="leyenda-muestra ambulancia-conservada"></i>Ambulancia utilizada</span>
        <span class="leyenda-item"><i class="leyenda-muestra establecimiento-conservado"></i>Establecimiento elegido</span>`;
      return contenedor;
    }};
    leyenda.addTo(mapa);

    const origen = document.getElementById("origen");
    const destino = document.getElementById("destino");
    const resultado = document.getElementById("resultado");
    const opcionOrigen = new Option("Seleccionar base…", "", true, true);
    const opcionDestino = new Option("Seleccionar base…", "", true, true);
    opcionOrigen.disabled = true;
    opcionDestino.disabled = true;
    origen.add(opcionOrigen);
    destino.add(opcionDestino);
    datos.bases.forEach((base) => {{
      origen.add(new Option(base.nombre, base.id));
      destino.add(new Option(base.nombre, base.id));
    }});

    let capaRuta = null;
    function dibujarRuta() {{
      if (capaRuta) {{ mapa.removeLayer(capaRuta); capaRuta = null; }}
      if (!origen.value || !destino.value || origen.value === destino.value) {{
        resultado.textContent = "Elegí dos bases diferentes";
        return;
      }}
      const ruta = datos.rutas[`${{origen.value}}|${{destino.value}}`];
      if (!ruta) {{
        resultado.textContent = "No existe una ruta dirigida";
        return;
      }}
      capaRuta = L.polyline(ruta.coordenadas, {{
        color: "#006bd6", weight: 5, opacity: 0.9
      }}).addTo(mapa);
      capaRuta.bringToFront();
      mapa.fitBounds(capaRuta.getBounds(), {{ padding: [36, 36], maxZoom: 16 }});
      resultado.textContent = `${{Math.round(ruta.distancia_metros).toLocaleString("es-AR")}} m`;
    }}
    origen.addEventListener("change", dibujarRuta);
    destino.addEventListener("change", dibujarRuta);
    dibujarRuta();

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
    prepararSelector(selectorAmbulancia, "Seleccionar ambulancia…", datos.ambulancias, (a) => a.id);
    prepararSelector(selectorEmergencia, "Seleccionar emergencia…", datos.emergencias, (e) => e.id);
    prepararSelector(selectorEstablecimiento, "Seleccionar establecimiento…", datos.establecimientos, (e) => e.nombre);
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
        resultadoAlternativa.textContent = "Elegí los tres elementos para inspeccionar una alternativa.";
        return;
      }}
      const alternativa = alternativasPorClave[`${{ambulanciaId}}|${{emergenciaId}}|${{establecimientoId}}`];
      dibujadorManual.dibujar(ambulanciaId, emergenciaId, establecimientoId);
      const motivos = alternativa.motivos_descarte.length
        ? alternativa.motivos_descarte.map(escapar).join(", ")
        : "Ninguno";
      resultadoAlternativa.innerHTML = `<dl>
        <div><dt>Ambulancia → emergencia:</dt><dd>${{mostrarMetros(alternativa.distancia_ambulancia_emergencia_m)}}</dd></div>
        <div><dt>Emergencia → establecimiento:</dt><dd>${{mostrarMetros(alternativa.distancia_emergencia_establecimiento_m)}}</dd></div>
        <div><dt>Distancia física total:</dt><dd>${{mostrarMetros(alternativa.distancia_total_m)}}</dd></div>
        <div><dt>Penalización:</dt><dd>${{mostrarMetros(alternativa.penalizacion_establecimiento_m)}}</dd></div>
        <div><dt>Costo de selección:</dt><dd>${{mostrarMetros(alternativa.costo_seleccion)}}</dd></div>
        <div><dt>Factible:</dt><dd>${{alternativa.es_factible ? "Sí" : "No"}}</dd></div>
        <div><dt>Motivos:</dt><dd>${{motivos}}</dd></div>
      </dl>`;
    }}
    selectorAmbulancia.addEventListener("change", dibujarAlternativa);
    selectorEmergencia.addEventListener("change", dibujarAlternativa);
    selectorEstablecimiento.addEventListener("change", dibujarAlternativa);

    const selectorEmergenciaHeuristica = document.getElementById("heuristica-emergencia");
    const selectorAlternativaHeuristica = document.getElementById("heuristica-alternativa");
    const resultadoHeuristica = document.getElementById("resultado-heuristica");
    const capaCandidatosEstablecimientos = L.layerGroup().addTo(mapa);
    const dibujadorHeuristico = crearDibujadorTramos();
    const alternativasReducidasPorEmergencia = {{}};
    datos.reduccion.alternativas_reducidas.forEach((alternativa) => {{
      if (!alternativasReducidasPorEmergencia[alternativa.emergencia_id]) {{
        alternativasReducidasPorEmergencia[alternativa.emergencia_id] = [];
      }}
      alternativasReducidasPorEmergencia[alternativa.emergencia_id].push(alternativa);
    }});
    const opcionEmergenciaHeuristica = new Option("Seleccionar emergencia…", "", true, true);
    opcionEmergenciaHeuristica.disabled = true;
    selectorEmergenciaHeuristica.add(opcionEmergenciaHeuristica);
    datos.emergencias.forEach((emergencia) => {{
      selectorEmergenciaHeuristica.add(new Option(
        `${{emergencia.id}} — gravedad ${{emergencia.gravedad}}`, emergencia.id
      ));
    }});
    function reiniciarAlternativasHeuristicas() {{
      selectorAlternativaHeuristica.innerHTML = "";
      const inicial = new Option("Seleccionar alternativa…", "", true, true);
      inicial.disabled = true;
      selectorAlternativaHeuristica.add(inicial);
    }}
    function limpiarCapasHeuristicas() {{
      dibujadorHeuristico.limpiar();
      capaCandidatosEstablecimientos.clearLayers();
    }}
    function limpiarHeuristica() {{
      limpiarCapasHeuristicas();
      limpiarAsignacion();
      reiniciarAsignacionUI();
      Object.values(marcadoresBase).forEach((marcador) => marcador.setOpacity(1));
      Object.values(marcadoresEmergencia).forEach((marcador) => {{
        marcador.setOpacity(1);
        marcador.setZIndexOffset(0);
      }});
      reiniciarAlternativasHeuristicas();
    }}
    function dibujarAlternativaHeuristica() {{
      const clave = selectorAlternativaHeuristica.value;
      if (!clave) {{
        dibujadorHeuristico.limpiar();
        return;
      }}
      const [ambulanciaId, emergenciaId, establecimientoId] = clave.split("|");
      dibujadorHeuristico.dibujar(ambulanciaId, emergenciaId, establecimientoId);
    }}
    function aplicarHeuristica() {{
      limpiarHeuristica();
      const emergenciaId = selectorEmergenciaHeuristica.value;
      if (!emergenciaId) {{
        resultadoHeuristica.textContent = "Elegí una emergencia para ver los candidatos conservados.";
        return;
      }}
      const seleccion = datos.reduccion.selecciones[emergenciaId];
      const conservadas = new Set(
        seleccion.ambulancias.filter((candidato) => candidato.conservada)
          .map((candidato) => candidato.ambulancia_id)
      );
      datos.ambulancias.forEach((ambulancia) => {{
        const marcador = marcadoresBase[ambulancia.base_id];
        if (marcador) marcador.setOpacity(conservadas.has(ambulancia.id) ? 1 : 0.28);
      }});
      const marcadorEmergencia = marcadoresEmergencia[emergenciaId];
      if (marcadorEmergencia) marcadorEmergencia.setZIndexOffset(1000);
      seleccion.establecimientos.forEach((candidato) => {{
        const establecimiento = establecimientosPorId[candidato.establecimiento_id];
        if (!establecimiento) return;
        L.circleMarker([establecimiento.latitud, establecimiento.longitud], {{
          radius: candidato.conservado ? 19 : 12,
          color: candidato.conservado ? "#075c9e" : "#7f8783",
          weight: candidato.conservado ? 4 : 2,
          opacity: candidato.conservado ? 0.95 : 0.4,
          fillColor: candidato.conservado ? "#075c9e" : "#7f8783",
          fillOpacity: candidato.conservado ? 0.16 : 0.04,
          interactive: false
        }}).addTo(capaCandidatosEstablecimientos);
      }});
      const alternativas = alternativasReducidasPorEmergencia[emergenciaId] || [];
      alternativas.forEach((alternativa) => {{
        const clave = `${{alternativa.ambulancia_id}}|${{alternativa.emergencia_id}}|${{alternativa.establecimiento_id}}`;
        const etiqueta = `${{alternativa.ambulancia_id}} → ${{alternativa.establecimiento_id}} (${{mostrarMetros(alternativa.costo_seleccion)}})`;
        selectorAlternativaHeuristica.add(new Option(etiqueta, clave));
      }});
      const factiblesAntes = datos.alternativas.filter(
        (alternativa) => alternativa.emergencia_id === emergenciaId && alternativa.es_factible
      ).length;
      const conservadasCantidad = seleccion.ambulancias.filter((candidato) => candidato.conservada).length;
      const conservadosCantidad = seleccion.establecimientos.filter((candidato) => candidato.conservado).length;
      resultadoHeuristica.textContent =
        `${{emergenciaId}} — ambulancias: ${{seleccion.ambulancias.length}} → ${{conservadasCantidad}}; ` +
        `establecimientos: ${{seleccion.establecimientos.length}} → ${{conservadosCantidad}}; ` +
        `alternativas factibles: ${{factiblesAntes}} → ${{alternativas.length}}`;
      if (alternativas.length) {{
        selectorAlternativaHeuristica.selectedIndex = 1;
        dibujarAlternativaHeuristica();
      }} else {{
        resultadoHeuristica.textContent += " — sin alternativas reducidas";
      }}
    }}
    selectorEmergenciaHeuristica.addEventListener("change", aplicarHeuristica);
    selectorAlternativaHeuristica.addEventListener("change", dibujarAlternativaHeuristica);
    reiniciarAlternativasHeuristicas();

    const selectorAsignacion = document.getElementById("asignacion-conjunto");
    const selectorSimulacionEtapa = document.getElementById("simulacion-etapa");
    const selectorSimulacionEmergencia = document.getElementById("simulacion-emergencia");
    const resultadoAsignacion = document.getElementById("resultado-asignacion");
    const resultadoSimulacion = document.getElementById("resultado-simulacion");
    const capaAsignacionRutas = L.layerGroup().addTo(mapa);
    const capaAsignacionEstablecimientos = L.layerGroup().addTo(mapa);
    const opcionAsignacion = new Option("Seleccionar conjunto…", "", true, true);
    opcionAsignacion.disabled = true;
    selectorAsignacion.add(opcionAsignacion);
    selectorAsignacion.add(new Option("Alternativas originales", "original"));
    const nivelRecomendado = datos.comparacion_asignaciones.nivel_recomendado;
    [1, 2, 3, 4].forEach((nivel) => {{
      const etiqueta = nivel === nivelRecomendado
        ? `Nivel ${{nivel}} (recomendado)`
        : `Nivel ${{nivel}}`;
      selectorAsignacion.add(new Option(etiqueta, `nivel-${{nivel}}`));
    }});

    datos.etapas_simulacion.forEach((etapa) => {{
      selectorSimulacionEtapa.add(
        new Option(`${{etapa.paso}} — ${{etapa.nombre}}`, String(etapa.paso))
      );
    }});
    selectorSimulacionEmergencia.add(new Option("Todas las emergencias", ""));
    datos.emergencias.forEach((emergencia) => {{
      selectorSimulacionEmergencia.add(
        new Option(`${{emergencia.id}} — gravedad ${{emergencia.gravedad}}`, emergencia.id)
      );
    }});

    const etiquetasEstado = {{
      asignada: "asignada",
      en_camino: "en camino",
      en_atencion: "en atención",
      trasladada: "trasladada",
      trasladando: "trasladando",
      finalizada: "finalizada",
      sin_asignacion: "sin asignación",
      disponible: "disponible"
    }};
    const mostrarEstado = (estado) => etiquetasEstado[estado] || estado;

    function limpiarCapasAsignacion() {{
      capaAsignacionRutas.clearLayers();
      capaAsignacionEstablecimientos.clearLayers();
    }}

    function limpiarAsignacion() {{
      limpiarCapasAsignacion();
      Object.values(marcadoresBase).forEach((marcador) => marcador.setOpacity(1));
      Object.values(marcadoresEmergencia).forEach((marcador) => {{
        marcador.setOpacity(1);
        marcador.setZIndexOffset(0);
      }});
    }}

    function reiniciarSimulacionUI() {{
      selectorSimulacionEtapa.value = "0";
      selectorSimulacionEmergencia.value = "";
      resultadoSimulacion.textContent = "Elegí un conjunto de asignación para ver la simulación.";
    }}

    function reiniciarAsignacionUI() {{
      selectorAsignacion.selectedIndex = 0;
      resultadoAsignacion.textContent = "Elegí un conjunto para ver la asignación global.";
      reiniciarSimulacionUI();
    }}

    function estiloTramo(paso, tipo) {{
      if (tipo === "inicial") {{
        return paso <= 2
          ? {{ color: "#7b2cbf", weight: 5, opacity: 0.92 }}
          : {{ color: "#7b2cbf", weight: 4, opacity: 0.42 }};
      }}
      if (paso <= 2) {{
        return {{
          color: "#00875a", weight: 4, opacity: 0.4, dashArray: "8 8"
        }};
      }}
      return {{ color: "#00875a", weight: 5, opacity: 0.92 }};
    }}

    function aplicarAsignacion() {{
      limpiarAsignacion();
      limpiarCapasHeuristicas();
      selectorEmergenciaHeuristica.selectedIndex = 0;
      reiniciarAlternativasHeuristicas();
      resultadoHeuristica.textContent = "Elegí una emergencia para ver los candidatos conservados.";
      const clave = selectorAsignacion.value;
      if (!clave) {{
        resultadoAsignacion.textContent = "Elegí un conjunto para ver la asignación global.";
        reiniciarSimulacionUI();
        return;
      }}
      const asignacion = datos.asignaciones[clave];
      const simulacion = datos.simulaciones[clave];
      if (!asignacion || !simulacion) {{
        resultadoAsignacion.textContent = "El conjunto seleccionado no tiene datos.";
        reiniciarSimulacionUI();
        return;
      }}
      const paso = Number(selectorSimulacionEtapa.value || "0");
      const estadoSimulacion = simulacion.estados[paso] || simulacion.estados[0];
      const estadoEmergencias = estadoSimulacion.emergencias;
      const estadoAmbulancias = estadoSimulacion.ambulancias;
      const emergenciaFiltro = selectorSimulacionEmergencia.value;

      const usadas = new Set(asignacion.ambulancias_utilizadas);
      datos.ambulancias.forEach((ambulancia) => {{
        const marcador = marcadoresBase[ambulancia.base_id];
        if (marcador) marcador.setOpacity(usadas.has(ambulancia.id) ? 1 : 0.25);
      }});
      const atendidas = new Set(asignacion.emergencias_atendidas);
      datos.emergencias.forEach((emergencia) => {{
        const marcador = marcadoresEmergencia[emergencia.id];
        if (!marcador) return;
        marcador.setOpacity(atendidas.has(emergencia.id) ? 1 : 0.35);
        if (atendidas.has(emergencia.id)) marcador.setZIndexOffset(1000);
      }});
      if (emergenciaFiltro && marcadoresEmergencia[emergenciaFiltro]) {{
        marcadoresEmergencia[emergenciaFiltro].setZIndexOffset(2000);
      }}

      const elegidos = new Set(asignacion.establecimientos_seleccionados);
      datos.establecimientos.forEach((establecimiento) => {{
        const elegido = elegidos.has(establecimiento.id);
        L.circleMarker([establecimiento.latitud, establecimiento.longitud], {{
          radius: elegido ? 20 : 12,
          color: elegido ? "#075c9e" : "#7f8783",
          weight: elegido ? 4 : 2,
          opacity: elegido ? 0.95 : 0.35,
          fillColor: elegido ? "#075c9e" : "#7f8783",
          fillOpacity: elegido ? 0.18 : 0.03,
          interactive: false
        }}).addTo(capaAsignacionEstablecimientos);
      }});

      const alternativas = emergenciaFiltro
        ? asignacion.alternativas.filter(
            (alternativa) => alternativa.emergencia_id === emergenciaFiltro
          )
        : asignacion.alternativas;
      const capas = [];
      alternativas.forEach((alternativa) => {{
        const rutaInicial = datos.rutas_ambulancia_emergencia[
          `${{alternativa.ambulancia_id}}|${{alternativa.emergencia_id}}`
        ];
        const rutaDestino = datos.rutas_emergencia_establecimiento[
          `${{alternativa.emergencia_id}}|${{alternativa.establecimiento_id}}`
        ];
        if (rutaInicial && rutaInicial.coordenadas.length) {{
          capas.push(L.polyline(
            rutaInicial.coordenadas, estiloTramo(paso, "inicial")
          ).bindTooltip(
            `${{alternativa.ambulancia_id}} → ${{alternativa.emergencia_id}}`
          ).addTo(capaAsignacionRutas));
        }}
        if (rutaDestino && rutaDestino.coordenadas.length) {{
          capas.push(L.polyline(
            rutaDestino.coordenadas, estiloTramo(paso, "destino")
          ).bindTooltip(
            `${{alternativa.emergencia_id}} → ${{alternativa.establecimiento_id}}`
          ).addTo(capaAsignacionRutas));
        }}
      }});
      if (capas.length) {{
        mapa.fitBounds(L.featureGroup(capas).getBounds(), {{
          padding: [36, 36], maxZoom: 16
        }});
      }} else if (emergenciaFiltro) {{
        const emergencia = datos.emergencias.find(
          (item) => item.id === emergenciaFiltro
        );
        if (emergencia) mapa.setView([emergencia.latitud, emergencia.longitud], 15);
      }}

      const etiquetaConjunto = clave === "original"
        ? "originales"
        : `nivel ${{clave.replace("nivel-", "")}}`;
      const detalle = asignacion.alternativas.map((alternativa) => {{
        const estadoEmergencia = estadoEmergencias[alternativa.emergencia_id];
        const estadoAmbulancia = estadoAmbulancias[alternativa.ambulancia_id];
        return `<li>${{escapar(alternativa.emergencia_id)}} → ` +
          `${{escapar(alternativa.ambulancia_id)}} → ` +
          `${{escapar(alternativa.establecimiento_id)}} ` +
          `(${{mostrarMetros(alternativa.costo_seleccion)}})<br>` +
          `<span>Emergencia: ${{mostrarEstado(estadoEmergencia ? estadoEmergencia.estado : "—")}}; ` +
          `ambulancia: ${{mostrarEstado(estadoAmbulancia ? estadoAmbulancia.estado : "—")}}</span></li>`;
      }}).join("") || "<li>Ninguna</li>";
      const sinAsignar = asignacion.emergencias_sin_asignar.map(
        (emergenciaId) => (
          `<li>${{escapar(emergenciaId)}}: ` +
          `${{escapar(asignacion.motivos_sin_asignar[emergenciaId])}}</li>`
        )
      ).join("") || "<li>Ninguna</li>";
      const perdidaHeuristica = datos.comparacion_asignaciones
        .perdida_por_heuristica
        ? datos.comparacion_asignaciones.niveles_con_perdida.join(", ")
        : "ninguno";
      resultadoAsignacion.innerHTML = `<dl>
        <div><dt>Conjunto:</dt><dd>${{etiquetaConjunto}}</dd></div>
        <div><dt>Atendidas:</dt><dd>${{asignacion.emergencias_atendidas.length}} / ${{asignacion.orden_prioridad.length}}</dd></div>
        <div><dt>Sin asignar:</dt><dd>${{asignacion.emergencias_sin_asignar.length}}</dd></div>
        <div><dt>Costo total:</dt><dd>${{mostrarMetros(asignacion.costo_total)}}</dd></div>
        <div><dt>Completa:</dt><dd>${{asignacion.es_completa ? "Sí" : "No"}}</dd></div>
        <div><dt>Óptima dentro del conjunto:</dt><dd>${{asignacion.es_optima ? "Sí" : "No"}}</dd></div>
        <div><dt>Nivel recomendado:</dt><dd>${{nivelRecomendado ?? "—"}}</dd></div>
        <div><dt>Niveles con pérdida:</dt><dd>${{perdidaHeuristica}}</dd></div>
      </dl>
      <ul class="popup-list"><li><strong>Asignaciones</strong></li>${{detalle}}</ul>
      <ul class="popup-list"><li><strong>Sin asignar</strong></li>${{sinAsignar}}</ul>`;

      const estadosEmergencias = datos.emergencias.map((emergencia) => {{
        const estado = estadoEmergencias[emergencia.id];
        return `<li>${{escapar(emergencia.id)}}: ` +
          `${{mostrarEstado(estado ? estado.estado : "—")}}</li>`;
      }}).join("") || "<li>Ninguna</li>";
      const estadosAmbulancias = datos.ambulancias.map((ambulancia) => {{
        const estado = estadoAmbulancias[ambulancia.id];
        return `<li>${{escapar(ambulancia.id)}}: ` +
          `${{mostrarEstado(estado ? estado.estado : "—")}}</li>`;
      }}).join("") || "<li>Ninguna</li>";
      let detalleSeleccion = "";
      if (emergenciaFiltro) {{
        const estado = estadoEmergencias[emergenciaFiltro];
        const atencion = simulacion.atenciones.find(
          (item) => item.emergencia_id === emergenciaFiltro
        );
        if (atencion) {{
          detalleSeleccion = `<div><dt>Emergencia seleccionada:</dt>` +
            `<dd>${{escapar(emergenciaFiltro)}} — ${{mostrarEstado(estado.estado)}}; ` +
            `ambulancia ${{escapar(atencion.ambulancia_id)}} ` +
            `(${{mostrarEstado(estadoAmbulancias[atencion.ambulancia_id].estado)}})</dd></div>` +
            `<div><dt>Recorrido:</dt><dd>` +
            `${{mostrarMetros(atencion.distancia_ambulancia_emergencia_m)}} + ` +
            `${{mostrarMetros(atencion.distancia_emergencia_establecimiento_m)}} = ` +
            `${{mostrarMetros(atencion.distancia_total_m)}}; ` +
            `penalización ${{mostrarMetros(atencion.penalizacion_establecimiento_m)}}; ` +
            `costo ${{mostrarMetros(atencion.costo_seleccion)}}</dd></div>`;
        }} else {{
          detalleSeleccion = `<div><dt>Emergencia seleccionada:</dt>` +
            `<dd>${{escapar(emergenciaFiltro)}} — sin asignación (` +
            `${{escapar(estado.motivo_sin_asignar || "motivo_no_informado")}})</dd></div>`;
        }}
      }}
      resultadoSimulacion.innerHTML = `<dl>
        <div><dt>Tipo:</dt><dd>lógica por etapas, sin tiempos reales</dd></div>
        <div><dt>Etapa:</dt><dd>${{estadoSimulacion.paso}} / ${{simulacion.total_pasos}} — ${{escapar(estadoSimulacion.nombre)}}</dd></div>
        <div><dt>Atenciones:</dt><dd>${{simulacion.cantidad_atenciones}}</dd></div>
        <div><dt>Completadas:</dt><dd>${{estadoSimulacion.cantidad_completadas}}</dd></div>
        <div><dt>Sin asignar:</dt><dd>${{simulacion.cantidad_sin_asignar}}</dd></div>
        <div><dt>Costo total:</dt><dd>${{mostrarMetros(simulacion.costo_total)}}</dd></div>
        <div><dt>Distancia total:</dt><dd>${{mostrarMetros(simulacion.distancia_total)}}</dd></div>
        <div><dt>Penalizaciones:</dt><dd>${{mostrarMetros(simulacion.penalizacion_total)}}</dd></div>
        ${{detalleSeleccion}}
      </dl>
      <ul class="popup-list"><li><strong>Estado de emergencias</strong></li>${{estadosEmergencias}}</ul>
      <ul class="popup-list"><li><strong>Estado de ambulancias</strong></li>${{estadosAmbulancias}}</ul>`;
    }}

    function mostrarEvaluacion() {{
      const contenedor = document.getElementById("resultado-evaluacion");
      const evaluacion = datos.evaluacion;
      if (!evaluacion || !evaluacion.escenarios.length) {{
        contenedor.textContent = "No hay datos de evaluación disponibles.";
        return;
      }}
      const filas = evaluacion.escenarios.map((metricas) => {{
        const reduccion = Math.max(
          0, Math.min(100, Number(metricas.porcentaje_reduccion) || 0)
        );
        const diferencias = metricas.diferencias_respecto_original.length;
        return `<tr>
          <td>${{escapar(metricas.etiqueta)}}</td>
          <td>${{metricas.alternativas_conservadas}} / ${{metricas.alternativas_generadas}}</td>
          <td>${{metricas.alternativas_evaluadas}}</td>
          <td><span class="barra-reduccion"><span style="width:${{reduccion}}%"></span></span>${{reduccion.toFixed(2)}} %</td>
          <td>${{metricas.emergencias_atendidas}}</td>
          <td>${{metricas.emergencias_sin_asignar}}</td>
          <td>${{metricas.ambulancias_utilizadas.map(escapar).join(", ")}}</td>
          <td>${{metricas.establecimientos_seleccionados.map(escapar).join(", ")}}</td>
          <td>${{mostrarMetros(metricas.costo_total)}}</td>
          <td>${{mostrarMetros(metricas.distancia_total)}}</td>
          <td>${{mostrarMetros(metricas.penalizacion_total)}}</td>
          <td>${{diferencias ? `${{diferencias}} cambio(s)` : "sin diferencias"}}</td>
        </tr>`;
      }}).join("");
      const nivelesConPerdida = evaluacion.niveles_con_perdida.length
        ? evaluacion.niveles_con_perdida.join(", ")
        : "ninguno";
      contenedor.innerHTML = `<p>
        Comparación dinámica del escenario original y los niveles 1 a 4.
        Nivel recomendado: <strong>${{evaluacion.nivel_recomendado ?? "—"}}</strong>;
        pérdida por heurística: <strong>${{evaluacion.perdida_por_heuristica ? "sí" : "no"}}</strong>;
        niveles con pérdida: <strong>${{nivelesConPerdida}}</strong>;
        mismos resultados: <strong>${{evaluacion.todos_mismos_resultados ? "sí" : "no"}}</strong>;
        mismos costos: <strong>${{evaluacion.todos_mismos_costos ? "sí" : "no"}}</strong>.
      </p>
      <table class="tabla-evaluacion">
        <thead><tr>
          <th>Escenario</th>
          <th>Conservadas / generadas</th>
          <th>Evaluadas</th>
          <th>Reducción</th>
          <th>Atendidas</th>
          <th>Sin asignar</th>
          <th>Ambulancias</th>
          <th>Destinos</th>
          <th>Costo</th>
          <th>Distancia</th>
          <th>Penalizaciones</th>
          <th>Diferencias</th>
        </tr></thead>
        <tbody>${{filas}}</tbody>
      </table>`;
    }}

    selectorAsignacion.addEventListener("change", () => {{
      selectorSimulacionEtapa.value = "0";
      selectorSimulacionEmergencia.value = "";
      aplicarAsignacion();
    }});
    selectorSimulacionEtapa.addEventListener("change", aplicarAsignacion);
    selectorSimulacionEmergencia.addEventListener("change", aplicarAsignacion);
    aplicarAsignacion();
    mostrarEvaluacion();
  </script>
</body>
</html>
"""
