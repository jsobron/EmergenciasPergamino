import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ambulancias_pergamino.cli import (
    comparar_asignaciones,
    listar_asignacion,
    main,
    resumir_asignacion,
)


RAIZ = Path(__file__).resolve().parents[1]
ENTRADA = RAIZ / "data/pergamino.json"
AMBULANCIAS = RAIZ / "config/ambulancias.json"
EMERGENCIAS = RAIZ / "config/emergencias.json"
ESTABLECIMIENTOS = RAIZ / "config/establecimientos.json"


class CliAsignacionTest(unittest.TestCase):
    def ejecutar(self, funcion, *argumentos):
        salida = io.StringIO()
        with redirect_stdout(salida):
            funcion(*argumentos)
        return salida.getvalue()

    def test_resumen_nivel1_informa_asignacion_completa(self) -> None:
        texto = self.ejecutar(
            resumir_asignacion,
            ENTRADA, AMBULANCIAS, EMERGENCIAS, ESTABLECIMIENTOS,
        )

        self.assertIn("Resumen de la asignación global:", texto)
        self.assertIn("Conjunto de alternativas: nivel 1 (k=3, h=2)", texto)
        self.assertIn("Alternativas candidatas: 30", texto)
        self.assertIn("Alternativas evaluadas tras dominancia: 15", texto)
        self.assertIn("Emergencias atendidas: 5", texto)
        self.assertIn("Emergencias sin asignar: 0", texto)
        self.assertIn("Asignación completa: sí", texto)
        self.assertIn("Óptima dentro del conjunto: sí", texto)
        self.assertIn("Costo total: 27017 m", texto)
        self.assertIn("Ambulancias utilizadas: A1, A2, A4, A5, A6", texto)
        self.assertIn(
            "Establecimientos seleccionados: "
            "GUARDIA-1, GUARDIA-2, GUARDIA-3",
            texto,
        )
        self.assertIn(
            "Emergencias atendidas (orden de prioridad): E2, E1, E3, E4, E5",
            texto,
        )
        self.assertIn("E2 -> A6 -> GUARDIA-3 (7569 m)", texto)
        self.assertIn("Emergencias sin asignar: ninguna", texto)

    def test_resumen_original_usa_todas_las_alternativas(self) -> None:
        texto = self.ejecutar(
            resumir_asignacion,
            ENTRADA, AMBULANCIAS, EMERGENCIAS, ESTABLECIMIENTOS,
            1, True,
        )

        self.assertIn("Conjunto de alternativas: original", texto)
        self.assertIn("Alternativas candidatas: 120", texto)
        self.assertIn("Alternativas evaluadas tras dominancia: 30", texto)
        self.assertIn("Asignación completa: sí", texto)

    def test_listar_asignacion_muestra_detalle_y_sin_asignar(self) -> None:
        texto = self.ejecutar(
            listar_asignacion,
            ENTRADA, AMBULANCIAS, EMERGENCIAS, ESTABLECIMIENTOS,
        )

        self.assertIn(
            "Detalle de la asignación (nivel 1 (k=3, h=2)):", texto
        )
        self.assertIn("Emergencia  Ambulancia  Establecimiento", texto)
        self.assertIn("E2", texto)
        self.assertIn("A6", texto)
        self.assertIn("GUARDIA-3", texto)
        self.assertIn("Emergencias sin asignar: ninguna", texto)

    def test_listar_asignacion_original(self) -> None:
        texto = self.ejecutar(
            listar_asignacion,
            ENTRADA, AMBULANCIAS, EMERGENCIAS, ESTABLECIMIENTOS,
            1, True,
        )

        self.assertIn("Detalle de la asignación (original):", texto)
        self.assertIn("E5", texto)

    def test_comparacion_informa_todos_los_niveles_y_la_recomendacion(self) -> None:
        texto = self.ejecutar(
            comparar_asignaciones,
            ENTRADA, AMBULANCIAS, EMERGENCIAS, ESTABLECIMIENTOS,
        )

        self.assertIn("Conjunto original:", texto)
        self.assertIn("Alternativas candidatas: 120", texto)
        for nivel, k, h, candidatas in (
            (1, 3, 2, 30),
            (2, 4, 3, 60),
            (3, 5, 4, 100),
            (4, 6, 4, 120),
        ):
            self.assertIn(f"Nivel {nivel} (k={k}, h={h}):", texto)
            self.assertIn(f"Alternativas candidatas: {candidatas}", texto)
        self.assertIn("Mejor nivel reducido: 1", texto)
        self.assertIn(
            "¿Alguna heurística perdió optimalidad frente al original?: no",
            texto,
        )
        self.assertIn("Niveles con pérdida: ninguno", texto)
        self.assertIn(
            "Todos los niveles alcanzan la misma solución que el conjunto original.",
            texto,
        )

    def test_rechaza_nivel_inexistente(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "Nivel de candidatos inexistente"
        ):
            resumir_asignacion(
                ENTRADA, AMBULANCIAS, EMERGENCIAS, ESTABLECIMIENTOS, 99
            )

    def test_nivel_y_original_son_mutuamente_excluyentes(self) -> None:
        with patch(
            "sys.argv",
            [
                "ambulancias_pergamino",
                "resumir-asignacion",
                "--nivel",
                "2",
                "--original",
            ],
        ), redirect_stderr(io.StringIO()) as error:
            with self.assertRaises(SystemExit) as salida:
                main()
        self.assertEqual(2, salida.exception.code)
        self.assertIn("not allowed with argument", error.getvalue())


if __name__ == "__main__":
    unittest.main()
