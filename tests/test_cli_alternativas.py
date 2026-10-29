import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from ambulancias_pergamino.cli import listar_alternativas, resumir_alternativas


RAIZ = Path(__file__).resolve().parents[1]


class CliAlternativasTest(unittest.TestCase):
    def test_resumen_informa_120_factibles_y_50_rutas(self) -> None:
        salida = io.StringIO()
        with redirect_stdout(salida):
            resumir_alternativas(
                RAIZ / "data/pergamino.json", RAIZ / "config/ambulancias.json",
                RAIZ / "config/emergencias.json", RAIZ / "config/establecimientos.json",
            )
        texto = salida.getvalue()
        self.assertIn("Alternativas generadas: 120", texto)
        self.assertIn("Alternativas factibles: 120", texto)
        self.assertIn("Alternativas no factibles: 0", texto)
        self.assertIn("Rutas únicas calculadas/reutilizadas: 50", texto)
        self.assertIn("E1: 24", texto)

    def test_listado_de_e1_contiene_24_alternativas(self) -> None:
        salida = io.StringIO()
        with redirect_stdout(salida):
            listar_alternativas(
                "E1", RAIZ / "data/pergamino.json", RAIZ / "config/ambulancias.json",
                RAIZ / "config/emergencias.json", RAIZ / "config/establecimientos.json",
            )
        lineas = [
            linea for linea in salida.getvalue().splitlines()
            if len(linea) > 1 and linea[0] == "A" and linea[1].isdigit()
        ]
        self.assertEqual(24, len(lineas))

    def test_rechaza_emergencia_inexistente(self) -> None:
        with self.assertRaisesRegex(ValueError, "Emergencia inexistente"):
            listar_alternativas(
                "E99", RAIZ / "data/pergamino.json", RAIZ / "config/ambulancias.json",
                RAIZ / "config/emergencias.json", RAIZ / "config/establecimientos.json",
            )


if __name__ == "__main__":
    unittest.main()
