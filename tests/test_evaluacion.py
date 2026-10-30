import json
import unittest
from dataclasses import asdict
from math import isclose
from pathlib import Path

from ambulancias_pergamino.alternativas import (
    ResultadoAlternativas,
    construir_alternativas,
)
from ambulancias_pergamino.ambulancias import cargar_ambulancias
from ambulancias_pergamino.asignacion import asignar_con_nivel
from ambulancias_pergamino.emergencias import cargar_emergencias
from ambulancias_pergamino.establecimientos import cargar_establecimientos
from ambulancias_pergamino.evaluacion import (
    _diferencias_respecto_original,
    evaluar_escenarios,
)
from ambulancias_pergamino.grafo import Grafo


RAIZ = Path(__file__).resolve().parents[1]


def cargar_escenario():
    datos = json.loads(
        (RAIZ / "data" / "pergamino.json").read_text(encoding="utf-8")
    )
    grafo = Grafo.deserializar(datos["grafo"])
    bases = datos["bases_ambulancias"]
    ambulancias = cargar_ambulancias(RAIZ / "config/ambulancias.json", bases)
    emergencias = cargar_emergencias(RAIZ / "config/emergencias.json", grafo)
    establecimientos = cargar_establecimientos(
        RAIZ / "config/establecimientos.json", bases
    )
    resultado = construir_alternativas(
        ambulancias, emergencias, establecimientos, grafo
    )
    return resultado, ambulancias, emergencias, establecimientos


class EvaluacionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        (
            cls.resultado,
            cls.ambulancias,
            cls.emergencias,
            cls.establecimientos,
        ) = cargar_escenario()
        cls.evaluacion = evaluar_escenarios(
            cls.resultado,
            cls.ambulancias,
            cls.emergencias,
            cls.establecimientos,
        )

    def test_evalua_original_y_cuatro_niveles(self) -> None:
        self.assertEqual(
            ["original", "nivel 1", "nivel 2", "nivel 3", "nivel 4"],
            [metricas.etiqueta for metricas in self.evaluacion.escenarios],
        )
        self.assertEqual(
            [None, 1, 2, 3, 4],
            [metricas.nivel for metricas in self.evaluacion.escenarios],
        )
        self.assertEqual(self.evaluacion.escenarios[0], self.evaluacion.original)
        self.assertEqual(
            self.evaluacion.escenarios[1:], self.evaluacion.niveles
        )

    def test_metricas_de_reduccion_coinciden_con_los_niveles(self) -> None:
        self.assertEqual(
            [120, 120, 120, 120, 120],
            [metricas.alternativas_generadas for metricas in self.evaluacion.escenarios],
        )
        self.assertEqual(
            [120, 120, 120, 120, 120],
            [metricas.alternativas_factibles for metricas in self.evaluacion.escenarios],
        )
        self.assertEqual(
            [120, 30, 60, 100, 120],
            [metricas.alternativas_conservadas for metricas in self.evaluacion.escenarios],
        )
        self.assertEqual(
            [30, 15, 20, 25, 30],
            [metricas.alternativas_evaluadas for metricas in self.evaluacion.escenarios],
        )
        self.assertEqual(
            [0.0, 75.0, 50.0, 16.67, 0.0],
            [metricas.porcentaje_reduccion for metricas in self.evaluacion.escenarios],
        )

        for nivel, metricas in zip((1, 2, 3, 4), self.evaluacion.niveles):
            asignacion = asignar_con_nivel(
                self.resultado,
                self.ambulancias,
                self.emergencias,
                self.establecimientos,
                nivel,
            )
            self.assertEqual(
                asignacion.alternativas_candidatas,
                metricas.alternativas_conservadas,
            )
            self.assertEqual(
                asignacion.alternativas_evaluadas,
                metricas.alternativas_evaluadas,
            )

    def test_costos_distancias_y_penalizaciones_coinciden(self) -> None:
        for nivel, metricas in zip((1, 2, 3, 4), self.evaluacion.niveles):
            asignacion = asignar_con_nivel(
                self.resultado,
                self.ambulancias,
                self.emergencias,
                self.establecimientos,
                nivel,
            )
            self.assertTrue(
                isclose(
                    asignacion.costo_total,
                    metricas.costo_total,
                    rel_tol=1e-9,
                    abs_tol=1e-6,
                )
            )
            self.assertEqual(
                len(asignacion.emergencias_atendidas),
                metricas.emergencias_atendidas,
            )
            self.assertEqual(
                len(asignacion.emergencias_sin_asignar),
                metricas.emergencias_sin_asignar,
            )
            self.assertEqual(
                tuple(asignacion.ambulancias_utilizadas),
                metricas.ambulancias_utilizadas,
            )
            self.assertEqual(
                tuple(asignacion.establecimientos_seleccionados),
                metricas.establecimientos_seleccionados,
            )

        for metricas in self.evaluacion.escenarios:
            self.assertAlmostEqual(
                metricas.costo_total,
                metricas.distancia_total + metricas.penalizacion_total,
            )
            distancia = 0.0
            for asignacion in metricas.asignaciones:
                alternativa = next(
                    alternativa
                    for alternativa in self.resultado.alternativas
                    if alternativa.emergencia_id
                    == asignacion.emergencia_id
                    and alternativa.ambulancia_id
                    == asignacion.ambulancia_id
                    and alternativa.establecimiento_id
                    == asignacion.establecimiento_id
                )
                distancia += alternativa.distancia_total_m
            self.assertAlmostEqual(metricas.distancia_total, distancia)

    def test_asignaciones_y_diferencias_respecto_del_original(self) -> None:
        esperadas = {
            "E2": ("A6", "GUARDIA-3"),
            "E1": ("A1", "GUARDIA-2"),
            "E3": ("A2", "GUARDIA-3"),
            "E4": ("A4", "GUARDIA-1"),
            "E5": ("A5", "GUARDIA-1"),
        }
        for metricas in self.evaluacion.escenarios:
            obtenidas = {
                asignacion.emergencia_id: (
                    asignacion.ambulancia_id,
                    asignacion.establecimiento_id,
                )
                for asignacion in metricas.asignaciones
            }
            self.assertEqual(esperadas, obtenidas)
            self.assertEqual((), metricas.diferencias_respecto_original)
        self.assertTrue(self.evaluacion.todos_mismos_resultados)
        self.assertTrue(self.evaluacion.todos_mismos_costos)
        self.assertEqual(1, self.evaluacion.nivel_recomendado)
        self.assertFalse(self.evaluacion.perdida_por_heuristica)
        self.assertEqual((), self.evaluacion.niveles_con_perdida)

    def test_estados_finales_de_la_simulacion(self) -> None:
        for metricas in self.evaluacion.escenarios:
            self.assertEqual(5, metricas.emergencias_atendidas)
            self.assertEqual(0, metricas.emergencias_sin_asignar)
            self.assertEqual(5, metricas.cantidad_completadas)
            self.assertTrue(metricas.es_completa)
            self.assertTrue(metricas.es_optima)
            self.assertEqual(
                {"finalizada"},
                set(metricas.estados_finales_emergencias.values()),
            )
            self.assertEqual(
                "disponible",
                metricas.estados_finales_ambulancias["A3"],
            )
            for ambulancia_id, estado in metricas.estados_finales_ambulancias.items():
                if ambulancia_id == "A3":
                    continue
                self.assertEqual("finalizada", estado)

    def test_evaluacion_es_determinista_y_no_muta_los_datos(self) -> None:
        antes = {
            "ambulancias": [asdict(ambulancia) for ambulancia in self.ambulancias],
            "emergencias": [asdict(emergencia) for emergencia in self.emergencias],
            "establecimientos": [
                asdict(establecimiento)
                for establecimiento in self.establecimientos
            ],
            "alternativas": [
                asdict(alternativa) for alternativa in self.resultado.alternativas
            ],
        }
        segunda = evaluar_escenarios(
            self.resultado,
            self.ambulancias,
            self.emergencias,
            self.establecimientos,
        )
        despues = {
            "ambulancias": [asdict(ambulancia) for ambulancia in self.ambulancias],
            "emergencias": [asdict(emergencia) for emergencia in self.emergencias],
            "establecimientos": [
                asdict(establecimiento)
                for establecimiento in self.establecimientos
            ],
            "alternativas": [
                asdict(alternativa) for alternativa in self.resultado.alternativas
            ],
        }

        self.assertEqual(antes, despues)
        self.assertEqual(
            [asdict(metricas) for metricas in self.evaluacion.escenarios],
            [asdict(metricas) for metricas in segunda.escenarios],
        )

    def test_escenario_vacio(self) -> None:
        resultado_vacio = ResultadoAlternativas(
            alternativas=[],
            rutas_ambulancia_emergencia={},
            rutas_emergencia_establecimiento={},
            rutas_unicas_calculadas=0,
        )
        evaluacion = evaluar_escenarios(resultado_vacio, [], [], [])

        self.assertEqual(5, len(evaluacion.escenarios))
        for metricas in evaluacion.escenarios:
            self.assertEqual(0, metricas.alternativas_generadas)
            self.assertEqual(0, metricas.alternativas_factibles)
            self.assertEqual(0, metricas.alternativas_conservadas)
            self.assertEqual(0, metricas.alternativas_evaluadas)
            self.assertEqual(0.0, metricas.porcentaje_reduccion)
            self.assertEqual(0, metricas.emergencias_atendidas)
            self.assertEqual(0, metricas.emergencias_sin_asignar)
            self.assertEqual(0.0, metricas.costo_total)
            self.assertEqual(0.0, metricas.distancia_total)
            self.assertEqual(0.0, metricas.penalizacion_total)
            self.assertEqual((), metricas.asignaciones)
            self.assertEqual({}, metricas.estados_finales_emergencias)
            self.assertEqual({}, metricas.estados_finales_ambulancias)
        self.assertTrue(evaluacion.todos_mismos_resultados)
        self.assertTrue(evaluacion.todos_mismos_costos)

    def test_detecta_diferencias_de_asignacion(self) -> None:
        diferencias = _diferencias_respecto_original(
            {
                "E1": "A1 -> GUARDIA-2",
                "E2": "A6 -> GUARDIA-3",
            },
            {
                "E1": "A2 -> GUARDIA-3",
                "E2": "A6 -> GUARDIA-3",
                "E3": "A4 -> GUARDIA-1",
            },
        )

        self.assertEqual(
            ["E1", "E3"],
            [diferencia.emergencia_id for diferencia in diferencias],
        )
        self.assertEqual("cambiada", diferencias[0].tipo)
        self.assertEqual("A1 -> GUARDIA-2", diferencias[0].original)
        self.assertEqual("A2 -> GUARDIA-3", diferencias[0].escenario)
        self.assertEqual("asignada_en_escenario", diferencias[1].tipo)
        self.assertIsNone(diferencias[1].original)

        sin_asignar = _diferencias_respecto_original(
            {"E4": "A4 -> GUARDIA-1"},
            {},
        )
        self.assertEqual("sin_asignar_en_escenario", sin_asignar[0].tipo)
        self.assertEqual("A4 -> GUARDIA-1", sin_asignar[0].original)
        self.assertIsNone(sin_asignar[0].escenario)


if __name__ == "__main__":
    unittest.main()
