from __future__ import annotations

import argparse
import json
from itertools import permutations
from math import isinf
from pathlib import Path

from .datos import construir_bases
from .ambulancias import cargar_ambulancias
from .alternativas import ResultadoAlternativas, construir_alternativas
from .establecimientos import cargar_establecimientos
from .emergencias import analizar_conectividad, cargar_emergencias
from .geonode import descargar_geojson
from .grafo import Grafo, construir_grafo
from .mapa import exportar_mapa


FILTRO_CALLEJERO = "localidad='Pergamino' AND transitable='si'"


def construir(salida: Path) -> None:
    print("Descargando callejero de Pergamino...")
    callejero = descargar_geojson("geonode:callejero", filtro_cql=FILTRO_CALLEJERO)
    print(f"Tramos recibidos: {len(callejero.get('features', []))}")

    grafo, advertencias = construir_grafo(callejero)
    print(
        f"Grafo construido: {len(grafo.nodos)} nodos y "
        f"{sum(map(len, grafo.adyacencia.values()))} aristas"
    )

    print("Descargando guardias medicas...")
    guardias = descargar_geojson("geonode:guardias_medicas")
    bases = construir_bases(guardias, grafo)

    resultado = {
        "fuente": {
            "wfs": "https://geonode.pergamino.gob.ar/geoserver/ows",
            "filtro_callejero": FILTRO_CALLEJERO,
        },
        "resumen": {
            "tramos": len(callejero.get("features", [])),
            "nodos": len(grafo.nodos),
            "aristas": sum(map(len, grafo.adyacencia.values())),
            "bases": len(bases),
            "advertencias": len(advertencias),
        },
        "advertencias": advertencias,
        "grafo": grafo.serializar(),
        "bases_ambulancias": bases,
    }
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(resultado, ensure_ascii=False), encoding="utf-8")
    print(f"Datos guardados en {salida}")
    for base in bases:
        print(
            f"- {base['nombre']}: nodo {base['nodo_id']} "
            f"({base['distancia_al_grafo_metros']} m del grafo)"
        )


def verificar_rutas(entrada: Path) -> None:
    datos = json.loads(entrada.read_text(encoding="utf-8"))
    grafo = Grafo.deserializar(datos["grafo"])
    bases = datos["bases_ambulancias"]
    fallas = 0
    for origen, destino in permutations(bases, 2):
        distancia, camino = grafo.camino_minimo(origen["nodo_id"], destino["nodo_id"])
        if isinf(distancia):
            fallas += 1
            print(f"SIN RUTA: {origen['nombre']} -> {destino['nombre']}")
        else:
            print(
                f"{origen['nombre']} -> {destino['nombre']}: "
                f"{distancia:.0f} m, {len(camino)} nodos"
            )
    if fallas:
        raise SystemExit(f"Se encontraron {fallas} pares sin ruta")


def listar_ambulancias(entrada: Path, configuracion: Path) -> None:
    datos = json.loads(entrada.read_text(encoding="utf-8"))
    bases = datos["bases_ambulancias"]
    bases_por_id = {base["id"]: base for base in bases}
    ambulancias = cargar_ambulancias(configuracion, bases)
    filas = [
        (
            ambulancia.id,
            bases_por_id[ambulancia.base_id]["nombre"],
            ambulancia.nodo_id,
            "sí" if ambulancia.disponible else "no",
            str(ambulancia.complejidad),
            str(ambulancia.capacidad_pacientes),
        )
        for ambulancia in ambulancias
    ]
    encabezados = ("ID", "Base", "Nodo", "Disponible", "Complejidad", "Capacidad")
    anchos = [max(len(encabezados[i]), *(len(fila[i]) for fila in filas)) for i in range(6)]
    formato = "  ".join(f"{{:<{ancho}}}" for ancho in anchos)
    print("Datos simulados: sí")
    print(formato.format(*encabezados))
    print(formato.format(*(guion * ancho for guion, ancho in zip("------", anchos))))
    for fila in filas:
        print(formato.format(*fila))


def listar_establecimientos(entrada: Path, configuracion: Path) -> None:
    datos = json.loads(entrada.read_text(encoding="utf-8"))
    establecimientos = cargar_establecimientos(
        configuracion, datos["bases_ambulancias"]
    )
    filas = [
        (
            establecimiento.id,
            establecimiento.nombre,
            establecimiento.base_id,
            establecimiento.nodo_id,
            "sí" if establecimiento.habilitado_destino else "no",
            str(establecimiento.prioridad),
            f"{establecimiento.penalizacion_metros:g} m",
            str(establecimiento.complejidad_maxima),
            "sí" if establecimiento.datos_simulados else "no",
        )
        for establecimiento in establecimientos
    ]
    encabezados = (
        "ID",
        "Nombre",
        "Base",
        "Nodo",
        "Destino",
        "Prioridad",
        "Penalización",
        "Complejidad",
        "Simulado",
    )
    anchos = [
        max(len(encabezados[i]), *(len(fila[i]) for fila in filas))
        for i in range(len(encabezados))
    ]
    formato = "  ".join(f"{{:<{ancho}}}" for ancho in anchos)
    print(formato.format(*encabezados))
    print(formato.format(*("-" * ancho for ancho in anchos)))
    for fila in filas:
        print(formato.format(*fila))


def listar_emergencias(entrada: Path, configuracion: Path) -> None:
    datos = json.loads(entrada.read_text(encoding="utf-8"))
    grafo = Grafo.deserializar(datos["grafo"])
    emergencias = cargar_emergencias(configuracion, grafo)
    filas = [
        (
            emergencia.id,
            str(emergencia.gravedad),
            str(emergencia.complejidad_requerida),
            str(emergencia.cantidad_pacientes),
            f"{emergencia.minutos_espera:g}",
            emergencia.estado,
            f"{emergencia.latitud:.7f}",
            f"{emergencia.longitud:.7f}",
            emergencia.nodo_id,
            f"{emergencia.distancia_al_nodo_m:.1f} m",
            "sí" if emergencia.datos_simulados else "no",
        )
        for emergencia in emergencias
    ]
    encabezados = (
        "ID", "Gravedad", "Complejidad", "Pacientes", "Espera (min)",
        "Estado", "Latitud", "Longitud", "Nodo", "Distancia", "Simulado",
    )
    anchos = [
        max(len(encabezados[i]), *(len(fila[i]) for fila in filas))
        for i in range(len(encabezados))
    ]
    formato = "  ".join(f"{{:<{ancho}}}" for ancho in anchos)
    print(formato.format(*encabezados))
    print(formato.format(*(guion * ancho for guion, ancho in zip("-" * len(anchos), anchos))))
    for fila in filas:
        print(formato.format(*fila))


def verificar_emergencias(
    entrada: Path, configuracion: Path, configuracion_establecimientos: Path
) -> None:
    datos = json.loads(entrada.read_text(encoding="utf-8"))
    grafo = Grafo.deserializar(datos["grafo"])
    bases = datos["bases_ambulancias"]
    emergencias = cargar_emergencias(configuracion, grafo)
    establecimientos = cargar_establecimientos(
        configuracion_establecimientos, bases
    )
    informes = analizar_conectividad(emergencias, bases, establecimientos, grafo)
    for informe in informes:
        print(f"{informe.emergencia_id}:")
        print(
            f"  Bases alcanzables ({len(informe.bases_alcanzables)}): "
            + ", ".join(informe.bases_alcanzables)
        )
        print(
            f"  Destinos alcanzables ({len(informe.establecimientos_alcanzables)}): "
            + ", ".join(informe.establecimientos_alcanzables)
        )
        for advertencia in informe.advertencias:
            print(f"  ADVERTENCIA: {advertencia}")


def _cargar_alternativas(
    entrada: Path, configuracion_ambulancias: Path,
    configuracion_emergencias: Path, configuracion_establecimientos: Path,
) -> tuple[ResultadoAlternativas, int, int, int]:
    datos = json.loads(entrada.read_text(encoding="utf-8"))
    grafo = Grafo.deserializar(datos["grafo"])
    bases = datos["bases_ambulancias"]
    ambulancias = cargar_ambulancias(configuracion_ambulancias, bases)
    emergencias = cargar_emergencias(configuracion_emergencias, grafo)
    establecimientos = cargar_establecimientos(configuracion_establecimientos, bases)
    resultado = construir_alternativas(
        ambulancias, emergencias, establecimientos, grafo
    )
    return resultado, len(ambulancias), len(emergencias), len(establecimientos)


def resumir_alternativas(
    entrada: Path, configuracion_ambulancias: Path,
    configuracion_emergencias: Path, configuracion_establecimientos: Path,
) -> None:
    resultado, cantidad_ambulancias, cantidad_emergencias, cantidad_destinos = (
        _cargar_alternativas(
            entrada, configuracion_ambulancias,
            configuracion_emergencias, configuracion_establecimientos,
        )
    )
    factibles = sum(a.es_factible for a in resultado.alternativas)
    print(f"Ambulancias: {cantidad_ambulancias}")
    print(f"Emergencias: {cantidad_emergencias}")
    print(f"Destinos: {cantidad_destinos}")
    print(f"Alternativas generadas: {len(resultado.alternativas)}")
    print(f"Alternativas factibles: {factibles}")
    print(f"Alternativas no factibles: {len(resultado.alternativas) - factibles}")
    print(
        "Rutas únicas calculadas/reutilizadas: "
        f"{resultado.rutas_unicas_calculadas}"
    )
    print("Alternativas por emergencia:")
    for emergencia_id in sorted({a.emergencia_id for a in resultado.alternativas}):
        cantidad = sum(a.emergencia_id == emergencia_id for a in resultado.alternativas)
        print(f"  {emergencia_id}: {cantidad}")


def listar_alternativas(
    emergencia_id: str, entrada: Path, configuracion_ambulancias: Path,
    configuracion_emergencias: Path, configuracion_establecimientos: Path,
) -> None:
    resultado, _, _, _ = _cargar_alternativas(
        entrada, configuracion_ambulancias,
        configuracion_emergencias, configuracion_establecimientos,
    )
    alternativas = [
        a for a in resultado.alternativas if a.emergencia_id == emergencia_id
    ]
    if not alternativas:
        raise ValueError(f"Emergencia inexistente: {emergencia_id}")
    alternativas.sort(
        key=lambda a: float("inf") if a.costo_seleccion is None else a.costo_seleccion
    )
    def metros(valor: float | None) -> str:
        return "sin ruta" if valor is None else f"{valor:.0f} m"
    encabezados = (
        "Ambulancia", "Establecimiento", "Hasta emergencia", "Hasta destino",
        "Total", "Penalización", "Costo", "Factible", "Motivos",
    )
    filas = [
        (
            a.ambulancia_id, a.establecimiento_id,
            metros(a.distancia_ambulancia_emergencia_m),
            metros(a.distancia_emergencia_establecimiento_m),
            metros(a.distancia_total_m), metros(a.penalizacion_establecimiento_m),
            metros(a.costo_seleccion), "sí" if a.es_factible else "no",
            ", ".join(a.motivos_descarte) or "—",
        )
        for a in alternativas
    ]
    anchos = [max(len(encabezados[i]), *(len(f[i]) for f in filas)) for i in range(len(encabezados))]
    formato = "  ".join(f"{{:<{ancho}}}" for ancho in anchos)
    print(f"Alternativas para {emergencia_id}: {len(filas)}")
    print(formato.format(*encabezados))
    print(formato.format(*("-" * ancho for ancho in anchos)))
    for fila in filas:
        print(formato.format(*fila))


def main() -> None:
    parser = argparse.ArgumentParser(prog="ambulancias_pergamino")
    subparsers = parser.add_subparsers(dest="comando", required=True)

    construir_parser = subparsers.add_parser("construir")
    construir_parser.add_argument("--salida", type=Path, default=Path("data/pergamino.json"))

    rutas_parser = subparsers.add_parser("verificar-rutas")
    rutas_parser.add_argument("--entrada", type=Path, default=Path("data/pergamino.json"))

    ambulancias_parser = subparsers.add_parser("listar-ambulancias")
    ambulancias_parser.add_argument(
        "--entrada", type=Path, default=Path("data/pergamino.json")
    )
    ambulancias_parser.add_argument(
        "--ambulancias", type=Path, default=Path("config/ambulancias.json")
    )

    establecimientos_parser = subparsers.add_parser("listar-establecimientos")
    establecimientos_parser.add_argument(
        "--entrada", type=Path, default=Path("data/pergamino.json")
    )
    establecimientos_parser.add_argument(
        "--establecimientos",
        type=Path,
        default=Path("config/establecimientos.json"),
    )

    emergencias_parser = subparsers.add_parser("listar-emergencias")
    emergencias_parser.add_argument(
        "--entrada", type=Path, default=Path("data/pergamino.json")
    )
    emergencias_parser.add_argument(
        "--emergencias", type=Path, default=Path("config/emergencias.json")
    )

    verificar_emergencias_parser = subparsers.add_parser("verificar-emergencias")
    verificar_emergencias_parser.add_argument(
        "--entrada", type=Path, default=Path("data/pergamino.json")
    )
    verificar_emergencias_parser.add_argument(
        "--emergencias", type=Path, default=Path("config/emergencias.json")
    )
    verificar_emergencias_parser.add_argument(
        "--establecimientos",
        type=Path,
        default=Path("config/establecimientos.json"),
    )

    resumen_parser = subparsers.add_parser("resumir-alternativas")
    listado_parser = subparsers.add_parser("listar-alternativas")
    listado_parser.add_argument("--emergencia", required=True)
    for subparser in (resumen_parser, listado_parser):
        subparser.add_argument("--entrada", type=Path, default=Path("data/pergamino.json"))
        subparser.add_argument("--ambulancias", type=Path, default=Path("config/ambulancias.json"))
        subparser.add_argument("--emergencias", type=Path, default=Path("config/emergencias.json"))
        subparser.add_argument(
            "--establecimientos", type=Path,
            default=Path("config/establecimientos.json"),
        )

    mapa_parser = subparsers.add_parser("exportar-mapa")
    mapa_parser.add_argument("--entrada", type=Path, default=Path("data/pergamino.json"))
    mapa_parser.add_argument(
        "--ambulancias", type=Path, default=Path("config/ambulancias.json")
    )
    mapa_parser.add_argument(
        "--salida", type=Path, default=Path("data/mapa_pergamino.html")
    )
    mapa_parser.add_argument(
        "--establecimientos",
        type=Path,
        default=Path("config/establecimientos.json"),
    )
    mapa_parser.add_argument(
        "--emergencias", type=Path, default=Path("config/emergencias.json")
    )

    argumentos = parser.parse_args()
    if argumentos.comando == "construir":
        construir(argumentos.salida)
    elif argumentos.comando == "verificar-rutas":
        verificar_rutas(argumentos.entrada)
    elif argumentos.comando == "listar-ambulancias":
        listar_ambulancias(argumentos.entrada, argumentos.ambulancias)
    elif argumentos.comando == "listar-establecimientos":
        listar_establecimientos(argumentos.entrada, argumentos.establecimientos)
    elif argumentos.comando == "listar-emergencias":
        listar_emergencias(argumentos.entrada, argumentos.emergencias)
    elif argumentos.comando == "verificar-emergencias":
        verificar_emergencias(
            argumentos.entrada,
            argumentos.emergencias,
            argumentos.establecimientos,
        )
    elif argumentos.comando == "resumir-alternativas":
        resumir_alternativas(
            argumentos.entrada, argumentos.ambulancias,
            argumentos.emergencias, argumentos.establecimientos,
        )
    elif argumentos.comando == "listar-alternativas":
        try:
            listar_alternativas(
                argumentos.emergencia, argumentos.entrada, argumentos.ambulancias,
                argumentos.emergencias, argumentos.establecimientos,
            )
        except ValueError as error:
            parser.error(str(error))
    elif argumentos.comando == "exportar-mapa":
        exportar_mapa(
            argumentos.entrada,
            argumentos.ambulancias,
            argumentos.salida,
            argumentos.establecimientos,
            argumentos.emergencias,
        )
        print(f"Mapa guardado en {argumentos.salida}")


if __name__ == "__main__":
    main()

