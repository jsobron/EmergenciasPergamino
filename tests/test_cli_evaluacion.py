import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ambulancias_pergamino.cli import evaluar_escenarios, main


RAIZ = Path(__file__).resolve().parents[1]
ENTRADA = RAIZ / "data/pergamino.json"
AMBULANCIAS = RAIZ / "config/ambulancias.json"
EMERGENCIAS = RAIZ / "config/emergencias.json"
ESTABLECIMIENTOS = RAIZ / "config/establecimientos.json"


class CliEvaluacionTest(unittest.TestCase):
    def ejecutar(self, funcion, *argumentos):
        salida = io.StringIO()
        with redirect_stdout(salida):
            funcion(*argumentos)
        return salida.getvalue()

    def test_evaluar_escenarios_informa_tabla_y_resumen(self) -> None:
        texto = self.ejecutar(
            evaluar_escenarios,
            ENTRADA, AMBULANCIAS, EMERGENCIAS, ESTABLECIMIENTOS,
        )

        self.assertIn("Evaluación de escenarios — Etapa 9", texto)
        self.assertIn("original", texto)
        self.assertIn("nivel 1", texto)
        self.assertIn("nivel 4", texto)
        self.assertIn("Generadas", texto)
        self.assertIn("Factibles", texto)
        self.assertIn("Conservadas", texto)
        self.assertIn("Evaluadas", texto)
        self.assertIn("75.00 %", texto)
        self.assertIn("50.00 %", texto)
        self.assertIn("16.67 %", texto)
        self.assertIn("27017 m", texto)
        self.assertIn("24017 m", texto)
        self.assertIn("3000 m", texto)
        self.assertIn("E2 -> A6 (base SAME) -> GUARDIA-3: 7569 m", texto)
        self.assertIn("Nivel recomendado: 1", texto)
        self.assertIn("Pérdida por heurística: no", texto)
        self.assertIn("Mismos resultados de asignación: sí", texto)
        self.assertIn("Mismos costos: sí", texto)

    def test_evaluar_escenarios_informa_estados_finales(self) -> None:
        texto = self.ejecutar(
            evaluar_escenarios,
            ENTRADA, AMBULANCIAS, EMERGENCIAS, ESTABLECIMIENTOS,
        )

        self.assertIn(
            "Emergencias: E1=finalizada, E2=finalizada, "
            "E3=finalizada, E4=finalizada, E5=finalizada",
            texto,
        )
        self.assertIn(
            "Ambulancias: A1=finalizada, A2=finalizada, A3=disponible, "
            "A4=finalizada, A5=finalizada, A6=finalizada",
            texto,
        )
        self.assertIn(
            "Sin diferencias de asignación respecto del original.", texto
        )

    def test_comando_disponible_y_conserva_los_anteriores(self) -> None:
        salida = io.StringIO()
        with patch("sys.argv", ["ambulancias_pergamino", "--help"]):
            with redirect_stdout(salida):
                with self.assertRaises(SystemExit) as contexto:
                    main()
        self.assertEqual(0, contexto.exception.code)
        texto = salida.getvalue()
        for comando in (
            "evaluar-escenarios",
            "resumir-asignacion",
            "comparar-asignaciones",
            "resumir-simulacion",
            "exportar-mapa",
        ):
            self.assertIn(comando, texto)

    def test_ayuda_del_comando(self) -> None:
        salida = io.StringIO()
        with patch(
            "sys.argv",
            ["ambulancias_pergamino", "evaluar-escenarios", "--help"],
        ):
            with redirect_stdout(salida):
                with self.assertRaises(SystemExit) as contexto:
                    main()
        self.assertEqual(0, contexto.exception.code)
        texto = salida.getvalue()
        self.assertIn("Compara alternativas, asignaciones", texto)
        self.assertIn("--entrada", texto)
        self.assertIn("--ambulancias", texto)
        self.assertIn("--emergencias", texto)
        self.assertIn("--establecimientos", texto)


if __name__ == "__main__":
    unittest.main()
