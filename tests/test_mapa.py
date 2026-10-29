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


if __name__ == "__main__":
    unittest.main()
