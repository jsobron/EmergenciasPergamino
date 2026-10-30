import json
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


if __name__ == "__main__":
    unittest.main()
