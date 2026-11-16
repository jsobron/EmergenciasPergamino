import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from ambulancias_pergamino.mapa import exportar_mapa, preparar_datos_mapa


RAIZ = Path(__file__).resolve().parents[1]


class DatosMapaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        datos = json.loads((RAIZ / "data" / "pergamino.json").read_text(encoding="utf-8"))
        direcciones = json.loads(
            (RAIZ / "data" / "direcciones.json").read_text(encoding="utf-8")
        )
        cls.mapa = preparar_datos_mapa(
            datos,
            RAIZ / "config" / "ambulancias.json",
            direcciones=direcciones,
        )

    def test_incluye_bases_ambulancias_y_rutas_dirigidas(self) -> None:
        self.assertEqual(6, len(self.mapa["bases"]))
        self.assertEqual(5, len(self.mapa["ambulancias"]))
        self.assertEqual(30, len(self.mapa["rutas"]))
        self.assertTrue(self.mapa["datos_simulados"])

    def test_incluye_grafo_para_calcular_rutas_en_el_navegador(self) -> None:
        grafo = self.mapa["grafo_js"]
        self.assertGreater(len(grafo["nodos"]), 5000)
        self.assertEqual(len(grafo["nodos"]), len(grafo["adyacencia"]))
        nodos_clave = {base["nodo_id"] for base in self.mapa["bases"]}
        nodos_clave.update(a["nodo_id"] for a in self.mapa["ambulancias"])
        nodos_clave.update(e["nodo_id"] for e in self.mapa["establecimientos"])
        nodos_clave.update(e["nodo_id"] for e in self.mapa["emergencias"])
        self.assertEqual(nodos_clave, set(grafo["indices"]))
        for indice in grafo["indices"].values():
            self.assertGreaterEqual(indice, 0)
            self.assertLess(indice, len(grafo["nodos"]))
        for aristas in grafo["adyacencia"]:
            for destino, distancia in aristas:
                self.assertGreaterEqual(destino, 0)
                self.assertLess(destino, len(grafo["nodos"]))
                self.assertGreater(distancia, 0)

    def test_incluye_indice_de_direcciones_para_buscar_por_calle(self) -> None:
        direcciones = self.mapa["direcciones"]
        self.assertGreater(len(direcciones), 4000)
        for entrada in direcciones[:20]:
            self.assertIn("calle", entrada)
            self.assertTrue(entrada["alias"])
            self.assertGreaterEqual(len(entrada["coords"]), 2)
        tucuman = [
            entrada
            for entrada in direcciones
            if "TUCUMAN" in entrada["alias"]
            and entrada["par"]
            and entrada["par"][0] <= 150 <= entrada["par"][1]
        ]
        self.assertTrue(tucuman)

    def test_incluye_los_cuatro_establecimientos_de_destino(self) -> None:
        self.assertEqual(4, len(self.mapa["establecimientos"]))
        self.assertEqual(
            {"GUARDIA-1", "GUARDIA-2", "GUARDIA-3", "GUARDIA-4"},
            {e["base_id"] for e in self.mapa["establecimientos"]},
        )
        self.assertEqual(
            {"GUARDIA-3", "GUARDIA-4"},
            {
                e["id"]
                for e in self.mapa["establecimientos"]
                if not e["habilitado_destino"]
            },
        )

    def test_incluye_las_cinco_emergencias_y_sus_gravedades(self) -> None:
        self.assertEqual(5, len(self.mapa["emergencias"]))
        self.assertEqual({1, 2, 3}, {e["gravedad"] for e in self.mapa["emergencias"]})
        self.assertTrue(all(e["datos_simulados"] for e in self.mapa["emergencias"]))

    def test_incluye_alternativas_y_rutas_reutilizables(self) -> None:
        self.assertEqual(100, len(self.mapa["alternativas"]))
        self.assertEqual(25, len(self.mapa["rutas_ambulancia_emergencia"]))
        self.assertEqual(20, len(self.mapa["rutas_emergencia_establecimiento"]))

    def test_incluye_reduccion_heuristica_y_orden_de_emergencias(self) -> None:
        reduccion = self.mapa["reduccion"]
        self.assertEqual(1, reduccion["parametros"]["nivel"])
        self.assertEqual(3, reduccion["parametros"]["k"])
        self.assertEqual(2, reduccion["parametros"]["h"])
        self.assertEqual(100, reduccion["estadisticas"]["alternativas_originales"])
        self.assertEqual(30, reduccion["estadisticas"]["alternativas_reducidas"])
        self.assertEqual(30, len(reduccion["alternativas_reducidas"]))
        self.assertEqual(
            ["E2", "E1", "E3", "E4", "E5"],
            [item["emergencia_id"] for item in reduccion["orden_emergencias"]],
        )
        self.assertEqual(
            ["A4", "A5", "A1"],
            [
                candidato["ambulancia_id"]
                for candidato in reduccion["selecciones"]["E1"]["ambulancias"]
                if candidato["conservada"]
            ],
        )
        self.assertEqual(
            ["GUARDIA-2", "GUARDIA-1"],
            [
                candidato["establecimiento_id"]
                for candidato in reduccion["selecciones"]["E1"]["establecimientos"]
                if candidato["conservado"]
            ],
        )
        for alternativa in reduccion["alternativas_reducidas"]:
            self.assertIn(
                f"{alternativa['ambulancia_id']}|{alternativa['emergencia_id']}",
                self.mapa["rutas_ambulancia_emergencia"],
            )
            self.assertIn(
                f"{alternativa['emergencia_id']}|{alternativa['establecimiento_id']}",
                self.mapa["rutas_emergencia_establecimiento"],
            )

    def test_incluye_asignaciones_original_y_por_nivel(self) -> None:
        asignaciones = self.mapa["asignaciones"]
        self.assertEqual(
            {"original", "nivel-1", "nivel-2", "nivel-3", "nivel-4"},
            set(asignaciones),
        )
        original = asignaciones["original"]
        self.assertEqual(5, len(original["emergencias_atendidas"]))
        self.assertEqual(0, len(original["emergencias_sin_asignar"]))
        self.assertTrue(original["es_completa"])
        self.assertTrue(original["es_optima"])
        self.assertEqual(44, original["alternativas_candidatas"])
        for nivel in range(1, 5):
            asignacion = asignaciones[f"nivel-{nivel}"]
            self.assertEqual(nivel, asignacion["parametros"]["nivel"])
            if nivel == 1:
                self.assertEqual(4, len(asignacion["emergencias_atendidas"]))
                self.assertEqual(["E5"], asignacion["emergencias_sin_asignar"])
                self.assertFalse(asignacion["es_completa"])
            else:
                self.assertEqual(5, len(asignacion["emergencias_atendidas"]))
                self.assertTrue(asignacion["es_completa"])
            for alternativa in asignacion["alternativas"]:
                self.assertIn(
                    f"{alternativa['ambulancia_id']}|"
                    f"{alternativa['emergencia_id']}",
                    self.mapa["rutas_ambulancia_emergencia"],
                )
                self.assertIn(
                    f"{alternativa['emergencia_id']}|"
                    f"{alternativa['establecimiento_id']}",
                    self.mapa["rutas_emergencia_establecimiento"],
                )
        comparacion = self.mapa["comparacion_asignaciones"]
        self.assertEqual(2, comparacion["nivel_recomendado"])
        self.assertTrue(comparacion["perdida_por_heuristica"])
        self.assertEqual([1], comparacion["niveles_con_perdida"])
        self.assertIn(1, comparacion["diferencias"])

    def test_incluye_simulaciones_para_cada_asignacion(self) -> None:
        self.assertEqual(
            set(self.mapa["asignaciones"]), set(self.mapa["simulaciones"])
        )
        self.assertEqual(
            [
                (0, "asignada", "Asignada"),
                (1, "en_camino", "En camino"),
                (2, "en_atencion", "En atención"),
                (3, "trasladando", "Trasladando"),
                (4, "finalizada", "Finalizada"),
            ],
            [
                (etapa["paso"], etapa["clave"], etapa["nombre"])
                for etapa in self.mapa["etapas_simulacion"]
            ],
        )

        for clave, simulacion in self.mapa["simulaciones"].items():
            asignacion = self.mapa["asignaciones"][clave]
            self.assertEqual(asignacion["etiqueta"], simulacion["etiqueta"])
            self.assertEqual(4, simulacion["total_pasos"])
            self.assertEqual(
                len(asignacion["alternativas"]),
                simulacion["cantidad_atenciones"],
            )
            self.assertAlmostEqual(
                asignacion["costo_total"], simulacion["costo_total"]
            )
            self.assertEqual(
                asignacion["emergencias_sin_asignar"],
                simulacion["emergencias_sin_asignar"],
            )
            self.assertEqual(
                asignacion["motivos_sin_asignar"],
                simulacion["motivos_sin_asignar"],
            )
            self.assertEqual(
                len(self.mapa["etapas_simulacion"]), len(simulacion["estados"])
            )

    def test_incluye_evaluacion_de_los_cinco_escenarios(self) -> None:
        evaluacion = self.mapa["evaluacion"]
        self.assertEqual(5, len(evaluacion["escenarios"]))
        self.assertEqual(
            ["original", "nivel 1", "nivel 2", "nivel 3", "nivel 4"],
            [metricas["etiqueta"] for metricas in evaluacion["escenarios"]],
        )
        self.assertEqual(
            [None, 1, 2, 3, 4],
            [metricas["nivel"] for metricas in evaluacion["escenarios"]],
        )
        self.assertEqual(
            [44, 30, 40, 44, 44],
            [
                metricas["alternativas_conservadas"]
                for metricas in evaluacion["escenarios"]
            ],
        )
        self.assertEqual(
            [22, 15, 20, 22, 22],
            [
                metricas["alternativas_evaluadas"]
                for metricas in evaluacion["escenarios"]
            ],
        )
        self.assertEqual(
            [0.0, 31.82, 9.09, 0.0, 0.0],
            [
                metricas["porcentaje_reduccion"]
                for metricas in evaluacion["escenarios"]
            ],
        )

        for metricas in evaluacion["escenarios"]:
            clave = (
                "original"
                if metricas["nivel"] is None
                else f"nivel-{metricas['nivel']}"
            )
            asignacion = self.mapa["asignaciones"][clave]
            simulacion = self.mapa["simulaciones"][clave]
            self.assertAlmostEqual(
                asignacion["costo_total"], metricas["costo_total"]
            )
            self.assertAlmostEqual(
                simulacion["costo_total"], metricas["costo_total"]
            )
            self.assertAlmostEqual(
                simulacion["distancia_total"], metricas["distancia_total"]
            )
            self.assertAlmostEqual(
                simulacion["penalizacion_total"],
                metricas["penalizacion_total"],
            )
            self.assertEqual(
                asignacion["emergencias_atendidas"],
                [item["emergencia_id"] for item in metricas["asignaciones"]],
            )
            self.assertEqual(
                asignacion["ambulancias_utilizadas"],
                list(metricas["ambulancias_utilizadas"]),
            )
            self.assertEqual(
                asignacion["establecimientos_seleccionados"],
                list(metricas["establecimientos_seleccionados"]),
            )
            final = simulacion["estados"][-1]
            for emergencia_id, estado in metricas[
                "estados_finales_emergencias"
            ].items():
                self.assertEqual(
                    final["emergencias"][emergencia_id]["estado"], estado
                )
            for ambulancia_id, estado in metricas[
                "estados_finales_ambulancias"
            ].items():
                self.assertEqual(
                    final["ambulancias"][ambulancia_id]["estado"], estado
                )

        self.assertEqual(2, evaluacion["nivel_recomendado"])
        self.assertTrue(evaluacion["perdida_por_heuristica"])
        self.assertEqual([1], evaluacion["niveles_con_perdida"])
        self.assertFalse(evaluacion["todos_mismos_resultados"])
        self.assertFalse(evaluacion["todos_mismos_costos"])

    def test_simulacion_conserva_tramos_costos_y_estados(self) -> None:
        simulacion = self.mapa["simulaciones"]["nivel-1"]
        asignacion = self.mapa["asignaciones"]["nivel-1"]

        self.assertEqual(4, simulacion["cantidad_atenciones"])
        self.assertEqual(4, simulacion["cantidad_completadas"])
        self.assertEqual(1, simulacion["cantidad_sin_asignar"])
        self.assertFalse(simulacion["es_completa"])
        self.assertAlmostEqual(24615.3, simulacion["costo_total"])
        self.assertAlmostEqual(21615.3, simulacion["distancia_total"])
        self.assertAlmostEqual(3000.0, simulacion["penalizacion_total"])

        for atencion in simulacion["atenciones"]:
            alternativa = next(
                alternativa
                for alternativa in asignacion["alternativas"]
                if alternativa["emergencia_id"] == atencion["emergencia_id"]
            )
            self.assertEqual(
                alternativa["ambulancia_id"], atencion["ambulancia_id"]
            )
            self.assertEqual(
                alternativa["establecimiento_id"],
                atencion["establecimiento_id"],
            )
            self.assertAlmostEqual(
                alternativa["distancia_ambulancia_emergencia_m"],
                atencion["distancia_ambulancia_emergencia_m"],
            )
            self.assertAlmostEqual(
                alternativa["distancia_emergencia_establecimiento_m"],
                atencion["distancia_emergencia_establecimiento_m"],
            )
            self.assertAlmostEqual(
                atencion["distancia_total_m"],
                atencion["distancia_ambulancia_emergencia_m"]
                + atencion["distancia_emergencia_establecimiento_m"],
            )
            self.assertAlmostEqual(
                atencion["costo_seleccion"],
                atencion["distancia_total_m"]
                + atencion["penalizacion_establecimiento_m"],
            )
            self.assertIn(
                atencion["ruta_ambulancia_emergencia"],
                self.mapa["rutas_ambulancia_emergencia"],
            )
            self.assertIn(
                atencion["ruta_emergencia_establecimiento"],
                self.mapa["rutas_emergencia_establecimiento"],
            )

        self.assertEqual(
            ["asignada", "en_camino", "en_atencion", "trasladando", "finalizada"],
            [estado["etapa"] for estado in simulacion["estados"]],
        )
        self.assertEqual(
            [0, 1, 2, 3, 4],
            [estado["paso"] for estado in simulacion["estados"]],
        )
        for estado in simulacion["estados"]:
            self.assertEqual(
                len(asignacion["emergencias_atendidas"])
                if estado["paso"] == 4
                else 0,
                estado["cantidad_completadas"],
            )
            for emergencia_id in asignacion["emergencias_atendidas"]:
                self.assertIn(emergencia_id, estado["emergencias"])
                self.assertIn(
                    estado["emergencias"][emergencia_id]["ambulancia_id"],
                    estado["ambulancias"],
                )
        final = simulacion["estados"][-1]
        for emergencia_id in asignacion["emergencias_atendidas"]:
            self.assertEqual(
                "finalizada", final["emergencias"][emergencia_id]["estado"]
            )
            self.assertTrue(final["emergencias"][emergencia_id]["completada"])
        self.assertEqual("disponible", final["ambulancias"]["A3"]["estado"])
        self.assertIsNone(final["ambulancias"]["A3"]["emergencia_id"])

    def test_simulacion_es_determinista_y_no_muta_la_asignacion(self) -> None:
        with tempfile.TemporaryDirectory() as directorio:
            datos = json.loads(
                (RAIZ / "data" / "pergamino.json").read_text(encoding="utf-8")
            )
            primero = preparar_datos_mapa(
                datos, RAIZ / "config" / "ambulancias.json"
            )
            segundo = preparar_datos_mapa(
                datos, RAIZ / "config" / "ambulancias.json"
            )
            self.assertEqual(
                primero["simulaciones"], segundo["simulaciones"]
            )
            self.assertEqual(
                primero["asignaciones"], segundo["asignaciones"]
            )
            salida = Path(directorio) / "mapa.html"
            exportar_mapa(
                RAIZ / "data" / "pergamino.json",
                RAIZ / "config" / "ambulancias.json",
                salida,
            )
            exportado = json.loads(
                re.search(
                    r'<script id="datos-mapa" type="application/json">(.*?)</script>',
                    salida.read_text(encoding="utf-8"),
                    re.DOTALL,
                ).group(1)
            )
        self.assertEqual(
            primero["simulaciones"], exportado["simulaciones"]
        )

    def test_deduplica_aristas_inversas_para_visualizar_calles(self) -> None:
        cantidad_original = 12237

        self.assertLess(len(self.mapa["tramos"]), cantidad_original)
        claves = {
            (tuple(sorted((tramo["origen"], tramo["destino"]))), tramo["tramo_id"])
            for tramo in self.mapa["tramos"]
        }
        self.assertEqual(len(claves), len(self.mapa["tramos"]))

    def test_cada_ruta_tiene_distancia_y_coordenadas(self) -> None:
        for ruta in self.mapa["rutas"].values():
            self.assertGreater(ruta["distancia_metros"], 0)
            self.assertGreaterEqual(len(ruta["coordenadas"]), 2)

    def test_exporta_recursos_cartograficos_validos(self) -> None:
        with tempfile.TemporaryDirectory() as directorio:
            salida = Path(directorio) / "mapa.html"
            exportar_mapa(
                RAIZ / "data" / "pergamino.json",
                RAIZ / "config" / "ambulancias.json",
                salida,
            )
            html = salida.read_text(encoding="utf-8")

        self.assertIn(
            "sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=", html
        )
        self.assertIn(
            'L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png"', html
        )
        self.assertIn('L.DomUtil.create("div", "leyenda")', html)
        self.assertIn("Destino prioritario", html)
        self.assertIn("Destino inactivo", html)
        self.assertIn("destinoHabilitado", html)
        self.assertIn("No recibe pacientes", html)
        self.assertIn("emergencia-icon", html)
        self.assertIn("Gravedad de emergencias", html)
        self.assertIn("Gravedad alta/crítica", html)
        self.assertNotIn("Emergencias simuladas", html)
        self.assertNotIn("6 bases", html)
        self.assertNotIn("rutas dirigidas", html)
        self.assertNotIn("Datos simulados", html)
        self.assertNotIn('id="origen"', html)
        self.assertNotIn('id="destino"', html)
        self.assertIn("Complejidad requerida", html)
        self.assertIn('id="alternativa-ambulancia"', html)
        self.assertIn('id="alternativa-emergencia"', html)
        self.assertIn('id="alternativa-establecimiento"', html)
        self.assertIn("Distancia física total", html)
        self.assertIn("Tramo ambulancia → emergencia", html)
        self.assertIn("Tramo emergencia → establecimiento", html)
        self.assertIn("panel-inferior", html)
        self.assertIn("Liberación de ambulancias", html)
        self.assertIn("Urgencias y grados", html)
        self.assertIn('id="alternativa-asignar"', html)
        self.assertIn('id="resultado-despacho"', html)
        self.assertIn('id="dashboard-resumen"', html)
        self.assertIn('id="dashboard-lista"', html)
        self.assertIn('id="form-urgencia"', html)
        self.assertIn('id="urgencia-id"', html)
        self.assertIn('id="urgencia-gravedad"', html)
        self.assertIn('id="urgencia-calle"', html)
        self.assertIn('id="urgencia-numero"', html)
        self.assertIn('id="urgencia-buscar"', html)
        self.assertIn('id="urgencia-elegir-mapa"', html)
        self.assertIn('id="resultado-urgencia"', html)
        self.assertIn('id="resultados-direccion"', html)
        self.assertIn('id="lista-urgencias"', html)
        self.assertNotIn('id="urgencia-latitud"', html)
        self.assertNotIn('id="urgencia-longitud"', html)
        self.assertIn("Buscar dirección", html)
        self.assertIn("normalizarCalle", html)
        self.assertIn("buscarDirecciones", html)
        self.assertIn("coordenadaEnBloque", html)
        self.assertIn("bloquesPorCalle", html)
        self.assertIn("datos.direcciones", html)
        self.assertIn("grafo_js", html)
        self.assertIn("nodoMasCercano", html)
        self.assertIn("caminoMinimo", html)
        self.assertIn("MonticuloMinimo", html)
        self.assertIn("coordenadasCamino", html)
        self.assertIn("tiempoHastaDisponible", html)
        self.assertIn("VELOCIDAD_KMH = 40", html)
        self.assertIn("TIEMPO_ATENCION_MIN = 10", html)
        self.assertIn("data-liberar", html)
        self.assertIn("liberacionEn", html)
        self.assertIn("liberarVencidos", html)
        self.assertIn("actualizarLiberaciones", html)
        self.assertIn("setInterval(actualizarLiberaciones", html)
        self.assertIn("liberación automática", html)
        self.assertIn("const atendidas = new Map()", html)
        self.assertIn("registrarAtendida", html)
        self.assertIn("refrescarSelectores", html)
        self.assertIn("prepararSiguienteDespacho", html)
        self.assertIn("estadoUrgencia", html)
        self.assertIn("Atendida por", html)
        self.assertIn("data-quitar-urgencia", html)
        self.assertIn(
            "No se puede quitar mientras la ambulancia está en uso", html
        )
        self.assertIn(
            "No se puede quitar una urgencia con la ambulancia en uso.", html
        )
        self.assertIn("agregarUrgencia", html)
        self.assertIn("renderUrgencias", html)
        self.assertIn("Disponible en", html)
        self.assertIn("regreso a la base", html)

    def test_mapa_no_expone_paneles_de_etapas_6_a_9(self) -> None:
        with tempfile.TemporaryDirectory() as directorio:
            salida = Path(directorio) / "mapa.html"
            exportar_mapa(
                RAIZ / "data" / "pergamino.json",
                RAIZ / "config" / "ambulancias.json",
                salida,
            )
            html = salida.read_text(encoding="utf-8")

        for texto in (
            "Reducción de candidatos",
            "Asignación global",
            "Simulación — Etapa 8",
            "Evaluación comparativa",
            'id="heuristica-emergencia"',
            'id="asignacion-conjunto"',
            'id="simulacion-etapa"',
            'id="resultado-evaluacion"',
            "datos.reduccion",
            "datos.asignaciones",
            "datos.simulaciones",
            "datos.evaluacion",
            "mostrarEvaluacion",
            "aplicarAsignacion",
        ):
            self.assertNotIn(texto, html)

    def test_javascript_generado_tiene_sintaxis_valida(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js no está disponible para validar el JavaScript")

        with tempfile.TemporaryDirectory() as directorio:
            salida = Path(directorio) / "mapa.html"
            exportar_mapa(
                RAIZ / "data" / "pergamino.json",
                RAIZ / "config" / "ambulancias.json",
                salida,
            )
            html = salida.read_text(encoding="utf-8")
            scripts = re.findall(r"<script>(.*?)</script>", html, re.DOTALL)
            self.assertEqual(1, len(scripts))
            script = Path(directorio) / "mapa.js"
            script.write_text(scripts[0], encoding="utf-8")
            resultado = subprocess.run(
                [node, "--check", str(script)],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

        self.assertEqual(0, resultado.returncode, resultado.stderr)


if __name__ == "__main__":
    unittest.main()
