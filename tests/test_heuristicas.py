import json
import unittest
from dataclasses import replace
from pathlib import Path

from ambulancias_pergamino.alternativas import (
    ResultadoAlternativas,
    RutaAlternativa,
    construir_alternativas,
)
from ambulancias_pergamino.ambulancias import cargar_ambulancias
from ambulancias_pergamino.emergencias import cargar_emergencias
from ambulancias_pergamino.establecimientos import cargar_establecimientos
from ambulancias_pergamino.grafo import Grafo
from ambulancias_pergamino.heuristicas import (
    MOTIVO_FUERA_DE_H,
    MOTIVO_FUERA_DE_K,
    NIVELES_CANDIDATOS,
    ParametrosCandidatos,
    ordenar_emergencias,
    reducir_alternativas,
)


RAIZ = Path(__file__).resolve().parents[1]


def resultado_sintetico(
    ambulancias,
    emergencias,
    establecimientos,
    distancias_ae=None,
    distancias_es=None,
    alternativas=None,
):
    def distancia(mapa, clave, por_defecto=100.0):
        if mapa is None:
            return por_defecto
        return mapa.get(clave, por_defecto)

    rutas_ae = {
        f"{ambulancia.id}|{emergencia.id}": RutaAlternativa(
            distancia_m=distancia(
                distancias_ae, f"{ambulancia.id}|{emergencia.id}"
            ),
            camino=[],
        )
        for ambulancia in ambulancias
        for emergencia in emergencias
    }
    rutas_es = {
        f"{emergencia.id}|{establecimiento.id}": RutaAlternativa(
            distancia_m=distancia(
                distancias_es, f"{emergencia.id}|{establecimiento.id}"
            ),
            camino=[],
        )
        for emergencia in emergencias
        for establecimiento in establecimientos
    }
    return ResultadoAlternativas(
        alternativas=list(alternativas or []),
        rutas_ambulancia_emergencia=rutas_ae,
        rutas_emergencia_establecimiento=rutas_es,
        rutas_unicas_calculadas=len(rutas_ae) + len(rutas_es),
    )


class HeuristicasTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        datos = json.loads((RAIZ / "data/pergamino.json").read_text(encoding="utf-8"))
        cls.grafo = Grafo.deserializar(datos["grafo"])
        cls.bases = datos["bases_ambulancias"]
        cls.ambulancias = cargar_ambulancias(
            RAIZ / "config/ambulancias.json", cls.bases
        )
        cls.emergencias = cargar_emergencias(
            RAIZ / "config/emergencias.json", cls.grafo
        )
        cls.establecimientos = cargar_establecimientos(
            RAIZ / "config/establecimientos.json", cls.bases
        )
        cls.resultado = construir_alternativas(
            cls.ambulancias, cls.emergencias, cls.establecimientos, cls.grafo
        )
        cls.reduccion = reducir_alternativas(
            cls.resultado,
            cls.ambulancias,
            cls.emergencias,
            cls.establecimientos,
        )

    def test_parametros_de_los_cuatro_niveles(self) -> None:
        self.assertEqual({1: (3, 2), 2: (4, 3), 3: (5, 4), 4: (6, 4)}, NIVELES_CANDIDATOS)
        for nivel, (k, h) in NIVELES_CANDIDATOS.items():
            with self.subTest(nivel=nivel):
                parametros = ParametrosCandidatos.desde_nivel(nivel)
                self.assertEqual(nivel, parametros.nivel)
                self.assertEqual(k, parametros.k)
                self.assertEqual(h, parametros.h)

    def test_rechaza_nivel_y_parametros_invalidos(self) -> None:
        with self.assertRaisesRegex(ValueError, "Nivel de candidatos inexistente"):
            ParametrosCandidatos.desde_nivel(9)
        with self.assertRaisesRegex(ValueError, "k debe ser"):
            ParametrosCandidatos(nivel=1, k=0, h=2)
        with self.assertRaisesRegex(ValueError, "h debe ser"):
            ParametrosCandidatos(nivel=1, k=3, h=-1)

    def test_reduccion_inicial_120_a_30_y_75_por_ciento(self) -> None:
        estadisticas = self.reduccion.estadisticas
        self.assertEqual(120, estadisticas.alternativas_originales)
        self.assertEqual(120, estadisticas.alternativas_factibles)
        self.assertEqual(0, estadisticas.alternativas_no_factibles)
        self.assertEqual({}, estadisticas.motivos_no_factibles)
        self.assertEqual(60, estadisticas.alternativas_tras_ambulancias)
        self.assertEqual(30, estadisticas.alternativas_tras_establecimientos)
        self.assertEqual(30, estadisticas.alternativas_reducidas)
        self.assertEqual(60, estadisticas.descartadas_por_ambulancias)
        self.assertEqual(30, estadisticas.descartadas_por_establecimientos)
        self.assertAlmostEqual(75.0, estadisticas.porcentaje_reduccion)
        self.assertEqual(30, len(self.reduccion.alternativas_reducidas))

    def test_excluye_alternativas_no_factibles(self) -> None:
        clave = ("A1", "E1", "GUARDIA-2")
        alternativas = []
        for alternativa in self.resultado.alternativas:
            if (
                alternativa.ambulancia_id,
                alternativa.emergencia_id,
                alternativa.establecimiento_id,
            ) == clave:
                alternativa = replace(
                    alternativa,
                    es_factible=False,
                    motivos_descarte=["prueba_no_factible"],
                )
            alternativas.append(alternativa)
        resultado = ResultadoAlternativas(
            alternativas=alternativas,
            rutas_ambulancia_emergencia=self.resultado.rutas_ambulancia_emergencia,
            rutas_emergencia_establecimiento=(
                self.resultado.rutas_emergencia_establecimiento
            ),
            rutas_unicas_calculadas=self.resultado.rutas_unicas_calculadas,
        )
        reduccion = reducir_alternativas(
            resultado, self.ambulancias, self.emergencias, self.establecimientos
        )
        self.assertEqual(1, reduccion.estadisticas.alternativas_no_factibles)
        self.assertEqual(
            {"prueba_no_factible": 1},
            reduccion.estadisticas.motivos_no_factibles,
        )
        self.assertEqual(119, reduccion.estadisticas.alternativas_factibles)
        self.assertEqual(29, reduccion.estadisticas.alternativas_reducidas)
        self.assertNotIn(
            clave,
            {
                (
                    alternativa.ambulancia_id,
                    alternativa.emergencia_id,
                    alternativa.establecimiento_id,
                )
                for alternativa in reduccion.alternativas_reducidas
            },
        )

    def test_conserva_las_tres_ambulancias_mas_cercanas(self) -> None:
        seleccion = self.reduccion.selecciones["E1"]
        self.assertEqual(
            ["A1", "A2", "A3"],
            [c.ambulancia_id for c in seleccion.ambulancias_conservadas],
        )
        distancias = [c.distancia_m for c in seleccion.ambulancias_conservadas]
        self.assertEqual(sorted(distancias), distancias)

    def test_excluye_ambulancias_lejanas_con_motivo(self) -> None:
        seleccion = self.reduccion.selecciones["E1"]
        excluidas = {
            c.ambulancia_id: c.motivos_exclusion
            for c in seleccion.ambulancias_excluidas
        }
        self.assertEqual({"A4", "A5", "A6"}, set(excluidas))
        for motivos in excluidas.values():
            self.assertEqual([MOTIVO_FUERA_DE_K], motivos)

    def test_desempate_de_ambulancias_por_identificador(self) -> None:
        ambulancias = [
            replace(self.ambulancias[0], id="A2"),
            replace(self.ambulancias[0], id="A1"),
        ]
        resultado = resultado_sintetico(
            ambulancias,
            [self.emergencias[0]],
            self.establecimientos,
            distancias_ae={
                "A2|E1": 500.0,
                "A1|E1": 500.0,
            },
        )
        reduccion = reducir_alternativas(
            resultado,
            ambulancias,
            [self.emergencias[0]],
            self.establecimientos,
            ParametrosCandidatos(nivel=1, k=1, h=2),
        )
        seleccion = reduccion.selecciones["E1"]
        self.assertEqual(
            ["A1"], [c.ambulancia_id for c in seleccion.ambulancias_conservadas]
        )
        self.assertEqual(
            [MOTIVO_FUERA_DE_K],
            seleccion.ambulancias_excluidas[0].motivos_exclusion,
        )

    def test_conserva_todas_si_hay_menos_de_k_ambulancias(self) -> None:
        ambulancias = [
            replace(self.ambulancias[0], id="A1"),
            replace(self.ambulancias[0], id="A2"),
            replace(self.ambulancias[0], id="A3", disponible=False),
        ]
        resultado = resultado_sintetico(
            ambulancias, [self.emergencias[0]], self.establecimientos
        )
        reduccion = reducir_alternativas(
            resultado, ambulancias, [self.emergencias[0]], self.establecimientos
        )
        seleccion = reduccion.selecciones["E1"]
        self.assertEqual(
            ["A1", "A2"],
            [c.ambulancia_id for c in seleccion.ambulancias_conservadas],
        )
        self.assertEqual(
            ["ambulancia_no_disponible"],
            seleccion.ambulancias_excluidas[0].motivos_exclusion,
        )

    def test_excluye_establecimientos_incompatibles(self) -> None:
        emergencia = replace(self.emergencias[0], complejidad_requerida=3)
        reduccion = reducir_alternativas(
            self.resultado,
            self.ambulancias,
            [emergencia],
            self.establecimientos,
        )
        seleccion = reduccion.selecciones["E1"]
        self.assertEqual(
            ["GUARDIA-1"],
            [c.establecimiento_id for c in seleccion.establecimientos_conservados],
        )
        incompatibles = {
            c.establecimiento_id: c.motivos_exclusion
            for c in seleccion.establecimientos_excluidos
        }
        for establecimiento_id in ("GUARDIA-2", "GUARDIA-3", "GUARDIA-4"):
            self.assertIn(
                "complejidad_establecimiento_insuficiente",
                incompatibles[establecimiento_id],
            )

    def test_conserva_los_dos_establecimientos_mas_convenientes(self) -> None:
        seleccion = self.reduccion.selecciones["E1"]
        self.assertEqual(
            ["GUARDIA-2", "GUARDIA-3"],
            [
                c.establecimiento_id
                for c in seleccion.establecimientos_conservados
            ],
        )
        criterios = [c.criterio_m for c in seleccion.establecimientos_conservados]
        self.assertEqual(sorted(criterios), criterios)

    def test_criterio_es_distancia_mas_penalizacion(self) -> None:
        seleccion = self.reduccion.selecciones["E1"]
        candidatos = {c.establecimiento_id: c for c in seleccion.establecimientos}
        for establecimiento_id, candidato in candidatos.items():
            self.assertIsNotNone(candidato.distancia_m)
            self.assertIsNotNone(candidato.criterio_m)
            self.assertAlmostEqual(
                candidato.distancia_m + candidato.penalizacion_m,
                candidato.criterio_m,
            )
        self.assertEqual(1000.0, candidatos["GUARDIA-2"].penalizacion_m)
        self.assertEqual(0.0, candidatos["GUARDIA-1"].penalizacion_m)

    def test_desempate_de_establecimientos_por_identificador(self) -> None:
        establecimientos = self.establecimientos[:2]
        ambulancias = [replace(self.ambulancias[0], id="A1")]
        resultado = resultado_sintetico(
            ambulancias,
            [self.emergencias[0]],
            establecimientos,
            distancias_es={
                "E1|GUARDIA-1": 2000.0,
                "E1|GUARDIA-2": 1000.0,
            },
        )
        reduccion = reducir_alternativas(
            resultado,
            ambulancias,
            [self.emergencias[0]],
            establecimientos,
            ParametrosCandidatos(nivel=1, k=3, h=1),
        )
        seleccion = reduccion.selecciones["E1"]
        self.assertEqual(
            ["GUARDIA-1"],
            [
                c.establecimiento_id
                for c in seleccion.establecimientos_conservados
            ],
        )
        self.assertEqual(
            [MOTIVO_FUERA_DE_H],
            seleccion.establecimientos_excluidos[0].motivos_exclusion,
        )

    def test_conserva_todos_si_hay_menos_de_h_establecimientos(self) -> None:
        emergencia = replace(self.emergencias[0], complejidad_requerida=3)
        reduccion = reducir_alternativas(
            self.resultado,
            self.ambulancias,
            [emergencia],
            self.establecimientos,
        )
        seleccion = reduccion.selecciones["E1"]
        self.assertEqual(1, len(seleccion.establecimientos_conservados))
        self.assertEqual(3, len(seleccion.establecimientos_excluidos))

    def test_conserva_datos_de_la_alternativa_original(self) -> None:
        originales = {
            (a.ambulancia_id, a.emergencia_id, a.establecimiento_id): a
            for a in self.resultado.alternativas
        }
        for reducida in self.reduccion.alternativas_reducidas:
            original = originales[
                (
                    reducida.ambulancia_id,
                    reducida.emergencia_id,
                    reducida.establecimiento_id,
                )
            ]
            self.assertEqual(original, reducida)
            self.assertEqual(
                original.distancia_ambulancia_emergencia_m,
                reducida.distancia_ambulancia_emergencia_m,
            )
            self.assertEqual(
                original.distancia_emergencia_establecimiento_m,
                reducida.distancia_emergencia_establecimiento_m,
            )
            self.assertEqual(original.distancia_total_m, reducida.distancia_total_m)
            self.assertEqual(
                original.penalizacion_establecimiento_m,
                reducida.penalizacion_establecimiento_m,
            )
            self.assertEqual(original.costo_seleccion, reducida.costo_seleccion)
            self.assertEqual(original.es_factible, reducida.es_factible)

    def test_alternativas_reducidas_son_subconjunto_de_las_factibles(self) -> None:
        claves_factibles = {
            (a.ambulancia_id, a.emergencia_id, a.establecimiento_id)
            for a in self.reduccion.alternativas_factibles
        }
        claves_reducidas = {
            (a.ambulancia_id, a.emergencia_id, a.establecimiento_id)
            for a in self.reduccion.alternativas_reducidas
        }
        self.assertTrue(claves_reducidas <= claves_factibles)
        self.assertEqual(30, len(claves_reducidas))

    def test_no_modifica_las_alternativas_originales(self) -> None:
        copia = list(self.resultado.alternativas)
        reduccion = reducir_alternativas(
            self.resultado,
            self.ambulancias,
            self.emergencias,
            self.establecimientos,
        )
        self.assertEqual(copia, self.resultado.alternativas)
        self.assertEqual(copia, reduccion.alternativas_originales)
        self.assertIsNot(copia, reduccion.alternativas_originales)

    def test_no_asigna_ni_reserva_ambulancias(self) -> None:
        copia = list(self.ambulancias)
        reduccion = reducir_alternativas(
            self.resultado,
            self.ambulancias,
            self.emergencias,
            self.establecimientos,
        )
        self.assertEqual(copia, self.ambulancias)
        self.assertTrue(all(ambulancia.disponible for ambulancia in self.ambulancias))
        self.assertFalse(hasattr(reduccion, "asignaciones"))
        self.assertFalse(hasattr(reduccion, "ambulancias_reservadas"))

    def test_orden_de_emergencias_por_gravedad_espera_e_id(self) -> None:
        self.assertEqual(
            ["E2", "E1", "E3", "E4", "E5"],
            [item.emergencia_id for item in self.reduccion.orden_emergencias],
        )
        self.assertEqual(
            [3, 3, 2, 2, 1],
            [item.gravedad for item in self.reduccion.orden_emergencias],
        )

    def test_orden_prioriza_menos_ambulancias_compatibles(self) -> None:
        emergencias = [
            replace(self.emergencias[0], id="E1", gravedad=2, minutos_espera=10),
            replace(self.emergencias[0], id="E2", gravedad=2, minutos_espera=10),
        ]
        ambulancias = [
            replace(self.ambulancias[0], id="A1"),
            replace(self.ambulancias[0], id="A2"),
            replace(self.ambulancias[0], id="A3"),
        ]
        resultado = resultado_sintetico(
            ambulancias,
            emergencias,
            self.establecimientos,
            distancias_ae={
                "A1|E1": 100.0,
                "A2|E1": None,
                "A3|E1": None,
                "A1|E2": 100.0,
                "A2|E2": 100.0,
                "A3|E2": 100.0,
            },
        )
        orden = ordenar_emergencias(emergencias, ambulancias, resultado)
        self.assertEqual(["E1", "E2"], [item.emergencia_id for item in orden])
        self.assertEqual(1, orden[0].ambulancias_compatibles)
        self.assertEqual(3, orden[1].ambulancias_compatibles)

    def test_orden_desempata_por_identificador(self) -> None:
        emergencias = [
            replace(self.emergencias[0], id="E2", gravedad=2, minutos_espera=10),
            replace(self.emergencias[0], id="E1", gravedad=2, minutos_espera=10),
        ]
        ambulancias = [replace(self.ambulancias[0], id="A1")]
        resultado = resultado_sintetico(
            ambulancias, emergencias, self.establecimientos
        )
        orden = ordenar_emergencias(emergencias, ambulancias, resultado)
        self.assertEqual(["E1", "E2"], [item.emergencia_id for item in orden])

    def test_sin_candidatos_no_falla_y_no_reduce_a_la_fuerza(self) -> None:
        emergencia = replace(self.emergencias[0], complejidad_requerida=3)
        reduccion = reducir_alternativas(
            self.resultado,
            self.ambulancias,
            [emergencia],
            self.establecimientos,
        )
        seleccion = reduccion.selecciones["E1"]
        self.assertEqual([], seleccion.ambulancias_conservadas)
        self.assertEqual(6, len(seleccion.ambulancias_excluidas))
        self.assertEqual(0, reduccion.estadisticas.alternativas_reducidas)
        self.assertEqual(0, reduccion.orden_emergencias[0].ambulancias_compatibles)

    def test_datos_incompletos_de_rutas_se_excluyen_con_motivo(self) -> None:
        resultado = resultado_sintetico(
            self.ambulancias,
            [self.emergencias[0]],
            self.establecimientos,
            distancias_ae={f"{a.id}|E1": None for a in self.ambulancias},
            distancias_es={f"E1|{e.id}": None for e in self.establecimientos},
        )
        reduccion = reducir_alternativas(
            resultado, self.ambulancias, [self.emergencias[0]], self.establecimientos
        )
        seleccion = reduccion.selecciones["E1"]
        self.assertEqual([], seleccion.ambulancias_conservadas)
        self.assertEqual([], seleccion.establecimientos_conservados)
        for candidato in seleccion.ambulancias:
            self.assertIn(
                "sin_ruta_hasta_emergencia", candidato.motivos_exclusion
            )
        for candidato in seleccion.establecimientos:
            self.assertIn(
                "sin_ruta_hasta_establecimiento", candidato.motivos_exclusion
            )

    def test_niveles_de_expansion_configurables(self) -> None:
        esperados = {
            2: (80, 60),
            3: (100, 100),
            4: (120, 120),
        }
        for nivel, (tras_ambulancias, reducidas) in esperados.items():
            with self.subTest(nivel=nivel):
                reduccion = reducir_alternativas(
                    self.resultado,
                    self.ambulancias,
                    self.emergencias,
                    self.establecimientos,
                    ParametrosCandidatos.desde_nivel(nivel),
                )
                self.assertEqual(
                    nivel, reduccion.parametros.nivel
                )
                self.assertEqual(
                    tras_ambulancias,
                    reduccion.estadisticas.alternativas_tras_ambulancias,
                )
                self.assertEqual(
                    reducidas, reduccion.estadisticas.alternativas_reducidas
                )


if __name__ == "__main__":
    unittest.main()
