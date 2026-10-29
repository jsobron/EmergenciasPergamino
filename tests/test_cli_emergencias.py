import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from ambulancias_pergamino.cli import listar_emergencias, verificar_emergencias


RAIZ = Path(__file__).resolve().parents[1]


class CliEmergenciasTest(unittest.TestCase):
    def test_listar_emergencias_muestra_campos_calculados_y_simulados(self) -> None:
        salida = io.StringIO()

        with redirect_stdout(salida):
            listar_emergencias(
                RAIZ / "data" / "pergamino.json",
                RAIZ / "config" / "emergencias.json",
            )

        texto = salida.getvalue()
        self.assertIn("ID", texto)
        self.assertIn("Nodo", texto)
        self.assertIn("Distancia", texto)
        self.assertIn("Simulado", texto)
        self.assertIn("E1", texto)
        self.assertIn("E5", texto)

    def test_verificar_emergencias_informa_bases_y_destinos_sin_asignar(self) -> None:
        salida = io.StringIO()

        with redirect_stdout(salida):
            verificar_emergencias(
                RAIZ / "data" / "pergamino.json",
                RAIZ / "config" / "emergencias.json",
                RAIZ / "config" / "establecimientos.json",
            )

        texto = salida.getvalue()
        self.assertEqual(5, texto.count("Bases alcanzables (6)"))
        self.assertEqual(5, texto.count("Destinos alcanzables (4)"))
        self.assertNotIn("ADVERTENCIA", texto)
        self.assertNotIn("ambulancia elegida", texto.lower())


if __name__ == "__main__":
    unittest.main()
