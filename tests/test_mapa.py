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
        cls.mapa = preparar_datos_mapa(datos, RAIZ / "config" / "ambulancias.json")

    def test_incluye_bases_ambulancias_y_rutas_dirigidas(self) -> None:
        self.assertEqual(6, len(self.mapa["bases"]))
        self.assertEqual(6, len(self.mapa["ambulancias"]))
        self.assertEqual(30, len(self.mapa["rutas"]))
        self.assertTrue(self.mapa["datos_simulados"])

    def test_incluye_los_cuatro_establecimientos_de_destino(self) -> None:
        self.assertEqual(4, len(self.mapa["establecimientos"]))
        self.assertEqual(
            {"GUARDIA-1", "GUARDIA-2", "GUARDIA-3", "GUARDIA-4"},
            {e["base_id"] for e in self.mapa["establecimientos"]},
        )

    def test_incluye_las_cinco_emergencias_y_sus_gravedades(self) -> None:
        self.assertEqual(5, len(self.mapa["emergencias"]))
        self.assertEqual({1, 2, 3}, {e["gravedad"] for e in self.mapa["emergencias"]})
        self.assertTrue(all(e["datos_simulados"] for e in self.mapa["emergencias"]))

    def test_incluye_alternativas_y_solo_cincuenta_rutas_reutilizables(self) -> None:
        self.assertEqual(120, len(self.mapa["alternativas"]))
        self.assertEqual(30, len(self.mapa["rutas_ambulancia_emergencia"]))
        self.assertEqual(20, len(self.mapa["rutas_emergencia_establecimiento"]))

    def test_incluye_reduccion_heuristica_y_orden_de_emergencias(self) -> None:
        reduccion = self.mapa["reduccion"]
        self.assertEqual(1, reduccion["parametros"]["nivel"])
        self.assertEqual(3, reduccion["parametros"]["k"])
        self.assertEqual(2, reduccion["parametros"]["h"])
        self.assertEqual(120, reduccion["estadisticas"]["alternativas_originales"])
        self.assertEqual(30, reduccion["estadisticas"]["alternativas_reducidas"])
        self.assertEqual(30, len(reduccion["alternativas_reducidas"]))
        self.assertEqual(
            ["E2", "E1", "E3", "E4", "E5"],
            [item["emergencia_id"] for item in reduccion["orden_emergencias"]],
        )
        self.assertEqual(
            ["A1", "A2", "A3"],
            [
                candidato["ambulancia_id"]
                for candidato in reduccion["selecciones"]["E1"]["ambulancias"]
                if candidato["conservada"]
            ],
        )
        self.assertEqual(
            ["GUARDIA-2", "GUARDIA-3"],
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
        self.assertEqual(120, original["alternativas_candidatas"])
        for nivel in range(1, 5):
            asignacion = asignaciones[f"nivel-{nivel}"]
            self.assertEqual(nivel, asignacion["parametros"]["nivel"])
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
        self.assertEqual(1, comparacion["nivel_recomendado"])
        self.assertFalse(comparacion["perdida_por_heuristica"])
        self.assertEqual([], comparacion["niveles_con_perdida"])
        self.assertEqual({}, comparacion["diferencias"])

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
            [120, 30, 60, 100, 120],
            [
                metricas["alternativas_conservadas"]
                for metricas in evaluacion["escenarios"]
            ],
        )
        self.assertEqual(
            [30, 15, 20, 25, 30],
            [
                metricas["alternativas_evaluadas"]
                for metricas in evaluacion["escenarios"]
            ],
        )
        self.assertEqual(
            [0.0, 75.0, 50.0, 16.67, 0.0],
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

        self.assertEqual(1, evaluacion["nivel_recomendado"])
        self.assertFalse(evaluacion["perdida_por_heuristica"])
        self.assertEqual([], evaluacion["niveles_con_perdida"])
        self.assertTrue(evaluacion["todos_mismos_resultados"])
        self.assertTrue(evaluacion["todos_mismos_costos"])

    def test_simulacion_conserva_tramos_costos_y_estados(self) -> None:
        simulacion = self.mapa["simulaciones"]["nivel-1"]
        asignacion = self.mapa["asignaciones"]["nivel-1"]

        self.assertEqual(5, simulacion["cantidad_atenciones"])
        self.assertEqual(5, simulacion["cantidad_completadas"])
        self.assertEqual(0, simulacion["cantidad_sin_asignar"])
        self.assertTrue(simulacion["es_completa"])
        self.assertAlmostEqual(
            27017.174000000003, simulacion["costo_total"]
        )
        self.assertAlmostEqual(
            24017.174000000003, simulacion["distancia_total"]
        )
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
        self.assertIn("No recibe pacientes", html)
        self.assertIn("emergencia-icon", html)
        self.assertIn("Emergencias simuladas", html)
        self.assertIn("Gravedad alta/crítica", html)
        self.assertIn("Complejidad requerida", html)
        self.assertIn('id="alternativa-ambulancia"', html)
        self.assertIn('id="alternativa-emergencia"', html)
        self.assertIn('id="alternativa-establecimiento"', html)
        self.assertIn("Distancia física total", html)
        self.assertIn("Tramo ambulancia → emergencia", html)
        self.assertIn("Tramo emergencia → establecimiento", html)
        self.assertIn('id="heuristica-emergencia"', html)
        self.assertIn('id="heuristica-alternativa"', html)
        self.assertIn('id="resultado-heuristica"', html)
        self.assertIn("Reducción de candidatos", html)
        self.assertIn("Ambulancia conservada", html)
        self.assertIn("Ambulancia descartada", html)
        self.assertIn("Establecimiento conservado", html)
        self.assertIn("Establecimiento excluido", html)
        self.assertIn("alternativasReducidasPorEmergencia", html)
        self.assertIn("datos.reduccion", html)
        self.assertIn('id="asignacion-conjunto"', html)
        self.assertIn('id="resultado-asignacion"', html)
        self.assertIn("Asignación global — Etapa 7", html)
        self.assertIn("Alternativas originales", html)
        self.assertIn("Nivel ${nivel} (recomendado)", html)
        self.assertIn("Emergencia atendida", html)
        self.assertIn("Emergencia sin asignar", html)
        self.assertIn("Ambulancia utilizada", html)
        self.assertIn("Establecimiento elegido", html)
        self.assertIn("datos.asignaciones", html)
        self.assertIn("datos.comparacion_asignaciones", html)
        self.assertIn("capaAsignacionRutas", html)
        self.assertIn("aplicarAsignacion", html)
        self.assertIn("Óptima dentro del conjunto", html)
        self.assertIn("Nivel recomendado", html)
        self.assertIn("Niveles con pérdida", html)

    def test_exporta_controles_de_simulacion(self) -> None:
        with tempfile.TemporaryDirectory() as directorio:
            salida = Path(directorio) / "mapa.html"
            exportar_mapa(
                RAIZ / "data" / "pergamino.json",
                RAIZ / "config" / "ambulancias.json",
                salida,
            )
            html = salida.read_text(encoding="utf-8")

        self.assertIn("Simulación — Etapa 8", html)
        self.assertIn('id="simulacion-etapa"', html)
        self.assertIn('id="simulacion-emergencia"', html)
        self.assertIn('id="resultado-simulacion"', html)
        self.assertIn("Etapa lógica", html)
        self.assertIn("Todas las emergencias", html)
        self.assertIn("datos.simulaciones", html)
        self.assertIn("datos.etapas_simulacion", html)
        self.assertIn("selectorSimulacionEtapa", html)
        self.assertIn("selectorSimulacionEmergencia", html)
        self.assertIn("aplicarAsignacion", html)
        self.assertIn("estiloTramo", html)
        self.assertIn("Emergencia seleccionada", html)
        self.assertIn("Estado de emergencias", html)
        self.assertIn("Estado de ambulancias", html)
        self.assertIn("lógica por etapas, sin tiempos reales", html)
        self.assertIn("Penalizaciones", html)

    def test_exporta_panel_de_evaluacion(self) -> None:
        with tempfile.TemporaryDirectory() as directorio:
            salida = Path(directorio) / "mapa.html"
            exportar_mapa(
                RAIZ / "data" / "pergamino.json",
                RAIZ / "config" / "ambulancias.json",
                salida,
            )
            html = salida.read_text(encoding="utf-8")

        self.assertIn("Evaluación comparativa — Etapa 9", html)
        self.assertIn('id="resultado-evaluacion"', html)
        self.assertIn("datos.evaluacion", html)
        self.assertIn("mostrarEvaluacion", html)
        self.assertIn("tabla-evaluacion", html)
        self.assertIn("Conservadas / generadas", html)
        self.assertIn("Reducción", html)
        self.assertIn("Nivel recomendado", html)
        self.assertIn("mismos resultados", html)
        self.assertIn("mismos costos", html)
        self.assertIn("barra-reduccion", html)

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
