from __future__ import annotations

import json
from dataclasses import asdict
from itertools import permutations
from math import isinf
from pathlib import Path
from typing import Any

from .ambulancias import cargar_ambulancias
from .alternativas import construir_alternativas
from .establecimientos import cargar_establecimientos
from .emergencias import cargar_emergencias
from .grafo import Grafo


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
      grid-template-rows: auto auto 1fr;
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
    @media (max-width: 760px) {{
      header {{ grid-template-columns: 1fr; align-items: stretch; }}
      .controls {{ grid-template-columns: 1fr 1fr; }}
      #resultado {{ grid-column: 1 / -1; }}
      .alternative-controls {{ grid-template-columns: 1fr; }}
      .alternative-controls h2, #resultado-alternativa {{ grid-column: auto; }}
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
      L.marker([base.latitud, base.longitud], {{ icon: icono, title: base.nombre }})
        .bindPopup(contenido)
        .addTo(mapa);
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
      L.marker([emergencia.latitud, emergencia.longitud], {{
        icon: icono,
        title: `Emergencia ${{emergencia.id}} — gravedad ${{emergencia.gravedad}}`
      }}).bindPopup(contenido).addTo(mapa);
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
        <span class="leyenda-item"><i class="leyenda-linea tramo-destino"></i>Tramo emergencia → establecimiento</span>`;
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
    let capaHastaEmergencia = null;
    let capaHastaEstablecimiento = null;
    const mostrarMetros = (valor) => valor === null
      ? "Sin ruta"
      : `${{Math.round(valor).toLocaleString("es-AR")}} m`;
    function dibujarAlternativa() {{
      if (capaHastaEmergencia) {{ mapa.removeLayer(capaHastaEmergencia); capaHastaEmergencia = null; }}
      if (capaHastaEstablecimiento) {{ mapa.removeLayer(capaHastaEstablecimiento); capaHastaEstablecimiento = null; }}
      const ambulanciaId = selectorAmbulancia.value;
      const emergenciaId = selectorEmergencia.value;
      const establecimientoId = selectorEstablecimiento.value;
      if (!ambulanciaId || !emergenciaId || !establecimientoId) {{
        resultadoAlternativa.textContent = "Elegí los tres elementos para inspeccionar una alternativa.";
        return;
      }}
      const alternativa = alternativasPorClave[`${{ambulanciaId}}|${{emergenciaId}}|${{establecimientoId}}`];
      const rutaInicial = datos.rutas_ambulancia_emergencia[`${{ambulanciaId}}|${{emergenciaId}}`];
      const rutaDestino = datos.rutas_emergencia_establecimiento[`${{emergenciaId}}|${{establecimientoId}}`];
      const capas = [];
      if (rutaInicial.coordenadas.length) {{
        capaHastaEmergencia = L.polyline(rutaInicial.coordenadas, {{ color: "#7b2cbf", weight: 5, opacity: 0.92 }}).addTo(mapa);
        capas.push(capaHastaEmergencia);
      }}
      if (rutaDestino.coordenadas.length) {{
        capaHastaEstablecimiento = L.polyline(rutaDestino.coordenadas, {{ color: "#00875a", weight: 5, opacity: 0.92 }}).addTo(mapa);
        capas.push(capaHastaEstablecimiento);
      }}
      if (capas.length) mapa.fitBounds(L.featureGroup(capas).getBounds(), {{ padding: [36, 36], maxZoom: 16 }});
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
  </script>
</body>
</html>
"""
