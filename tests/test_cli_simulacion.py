import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ambulancias_pergamino.cli import (
    avanzar_simulacion,
    iniciar_simulacion,
    listar_simulacion,
    main,
    resumir_simulacion,
    ver_simulacion,
)


RAIZ = Path(__file__).resolve().parents[1]
ENTRADA = RAIZ / "data/pergamino.json"
AMBULANCIAS = RAIZ / "config/ambulancias.json"
EMERGENCIAS = RAIZ / "config/emergencias.json"
ESTABLECIMIENTOS = RAIZ / "config/establecimientos.json"


class CliSimulacionTest(unittest.TestCase):
    def ejecutar(self, funcion, *argumentos, **opciones):
        salida = io.StringIO()
        with redirect_stdout(salida):
            funcion(*argumentos, **opciones)
        return salida.getvalue()

    def test_resumen_final_informa_estados_y_costos(self) -> None:
        texto = self.ejecutar(
            resumir_simulacion,
            ENTRADA, AMBULANCIAS, EMERGENCIAS, ESTABLECIMIENTOS,
        )

        self.assertIn("Simulación lógica — Etapa 8", texto)
        self.assertIn("Asignación de origen: nivel 1", texto)
        self.assertIn("Etapa: 4/4 — Finalizada", texto)
        self.assertIn("Tipo: lógica por etapas (sin tiempos reales)", texto)
        self.assertIn("Atenciones: 5", texto)
        self.assertIn("Completadas: 5", texto)
        self.assertIn("Costo total: 27017 m", texto)
        self.assertIn("Distancia total: 24017 m", texto)
        self.assertIn("Penalizaciones: 3000 m", texto)
        self.assertIn(
            "E2 -> A6 (base SAME) -> GUARDIA-3: "
            "emergencia finalizada, ambulancia finalizada, 7569 m",
            texto,
        )
        self.assertIn("E1: finalizada", texto)
        self.assertIn("A3: disponible", texto)

    def test_iniciar_simulacion_muestra_estado_inicial(self) -> None:
        texto = self.ejecutar(
            iniciar_simulacion,
            ENTRADA, AMBULANCIAS, EMERGENCIAS, ESTABLECIMIENTOS,
        )

        self.assertIn("Etapa: 0/4 — Asignada", texto)
        self.assertIn("Completadas: 0", texto)
        self.assertIn("emergencia asignada, ambulancia asignada", texto)
        self.assertIn("A6: asignada", texto)
        self.assertIn("A3: disponible", texto)

    def test_listar_simulacion_muestra_detalle_y_estados(self) -> None:
        texto = self.ejecutar(
            listar_simulacion,
            ENTRADA, AMBULANCIAS, EMERGENCIAS, ESTABLECIMIENTOS,
            etapa=2,
        )

        self.assertIn("Detalle de la simulación (nivel 1):", texto)
        self.assertIn("Etapa: 2/4 — En atención", texto)
        self.assertIn("Emergencia", texto)
        self.assertIn("Estado amb.", texto)
        self.assertIn("Hacia emergencia", texto)
        self.assertIn("E2", texto)
        self.assertIn("en_atencion", texto)
        self.assertIn("E1: en_atencion", texto)
        self.assertIn("A1: en_atencion", texto)

    def test_avanzar_simulacion_controla_los_pasos(self) -> None:
        texto = self.ejecutar(
            avanzar_simulacion,
            ENTRADA, AMBULANCIAS, EMERGENCIAS, ESTABLECIMIENTOS,
            pasos=2,
        )
        self.assertIn("Etapa: 2/4 — En atención", texto)

        texto = self.ejecutar(
            avanzar_simulacion,
            ENTRADA, AMBULANCIAS, EMERGENCIAS, ESTABLECIMIENTOS,
            hasta_final=True,
        )
        self.assertIn("Etapa: 4/4 — Finalizada", texto)
        self.assertIn("Completadas: 5", texto)

    def test_ver_emergencia_y_ambulancia(self) -> None:
        texto = self.ejecutar(
            ver_simulacion,
            ENTRADA, AMBULANCIAS, EMERGENCIAS, ESTABLECIMIENTOS,
            emergencia_id="E2",
        )
        self.assertIn("Emergencia E2:", texto)
        self.assertIn("Ambulancia: A6 (base SAME, estado finalizada)", texto)
        self.assertIn("Destino: GUARDIA-3", texto)
        self.assertIn("Tramo ambulancia -> emergencia: 2445 m", texto)
        self.assertIn("Tramo emergencia -> destino: 4124 m", texto)
        self.assertIn("Costo: 7569 m", texto)

        texto = self.ejecutar(
            ver_simulacion,
            ENTRADA, AMBULANCIAS, EMERGENCIAS, ESTABLECIMIENTOS,
            ambulancia_id="A6", etapa=2,
        )
        self.assertIn("Ambulancia A6:", texto)
        self.assertIn("Estado: en_atencion", texto)
        self.assertIn("Emergencia: E2", texto)
        self.assertIn("Destino: GUARDIA-3", texto)

    def test_rechaza_etapa_y_nivel_inexistentes(self) -> None:
        with self.assertRaisesRegex(ValueError, "Etapa de simulación inexistente"):
            resumir_simulacion(
                ENTRADA, AMBULANCIAS, EMERGENCIAS, ESTABLECIMIENTOS,
                etapa=99,
            )
        with self.assertRaisesRegex(ValueError, "Nivel de candidatos inexistente"):
            resumir_simulacion(
                ENTRADA, AMBULANCIAS, EMERGENCIAS, ESTABLECIMIENTOS,
                nivel=99,
            )

    def test_rechaza_entidades_inexistentes(self) -> None:
        with self.assertRaisesRegex(ValueError, "Emergencia inexistente"):
            ver_simulacion(
                ENTRADA, AMBULANCIAS, EMERGENCIAS, ESTABLECIMIENTOS,
                emergencia_id="E99",
            )
        with self.assertRaisesRegex(ValueError, "Ambulancia inexistente"):
            ver_simulacion(
                ENTRADA, AMBULANCIAS, EMERGENCIAS, ESTABLECIMIENTOS,
                ambulancia_id="A99",
            )
        with self.assertRaisesRegex(ValueError, "exactamente una"):
            ver_simulacion(
                ENTRADA, AMBULANCIAS, EMERGENCIAS, ESTABLECIMIENTOS,
            )

    def test_argumentos_invalidos_en_la_cli(self) -> None:
        casos = (
            (
                [
                    "ambulancias_pergamino",
                    "resumir-simulacion",
                    "--nivel", "2",
                    "--original",
                ],
                "not allowed with argument",
            ),
            (
                [
                    "ambulancias_pergamino",
                    "ver-simulacion",
                ],
                "one of the arguments",
            ),
            (
                [
                    "ambulancias_pergamino",
                    "avanzar-simulacion",
                    "--pasos", "0",
                ],
                "pasos debe ser un entero mayor que cero",
            ),
            (
                [
                    "ambulancias_pergamino",
                    "resumir-simulacion",
                    "--etapa", "99",
                ],
                "Etapa de simulación inexistente",
            ),
        )
        for argumentos, mensaje in casos:
            with patch("sys.argv", argumentos), redirect_stderr(
                io.StringIO()
            ) as error:
                with self.assertRaises(SystemExit) as salida:
                    main()
            self.assertEqual(2, salida.exception.code)
            self.assertIn(mensaje, error.getvalue())


if __name__ == "__main__":
    unittest.main()
