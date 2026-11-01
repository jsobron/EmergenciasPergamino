import json
import unittest
from dataclasses import replace
from pathlib import Path

from ambulancias_pergamino.alternativas import (
    Alternativa,
    ResultadoAlternativas,
    RutaAlternativa,
    construir_alternativas,
)
from ambulancias_pergamino.ambulancias import cargar_ambulancias
from ambulancias_pergamino.asignacion import (
    MOTIVO_AMBULANCIAS_USADAS,
    MOTIVO_SIN_ALTERNATIVAS,
    asignar_con_nivel,
    asignar_global,
    asignar_original,
    comparar_niveles,
)
from ambulancias_pergamino.emergencias import cargar_emergencias
from ambulancias_pergamino.establecimientos import cargar_establecimientos
from ambulancias_pergamino.grafo import Grafo


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


class AsignacionTest(unittest.TestCase):
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
        cls.emergencia_base = cls.emergencias[0]
        cls.ambulancia_base = cls.ambulancias[0]
        cls.establecimiento_base = cls.establecimientos[0]

    @staticmethod
    def alternativa(
        emergencia_id,
        ambulancia_id,
        establecimiento_id="S1",
        costo=100.0,
        factible=True,
        motivos=None,
    ):
        return Alternativa(
            ambulancia_id=ambulancia_id,
            emergencia_id=emergencia_id,
            establecimiento_id=establecimiento_id,
            distancia_ambulancia_emergencia_m=costo,
            distancia_emergencia_establecimiento_m=0.0,
            distancia_total_m=costo,
            penalizacion_establecimiento_m=0.0,
            costo_seleccion=costo,
            es_factible=factible,
            motivos_descarte=list(
                motivos if motivos is not None else ([] if factible else ["no_factible"])
            ),
        )

    def emergencia(self, emergencia_id, gravedad=1, espera=0.0):
        return replace(
            self.emergencia_base,
            id=emergencia_id,
            gravedad=gravedad,
            minutos_espera=espera,
        )

    def test_asignacion_original_completa_y_optima(self):
        resultado = asignar_original(
            self.resultado, self.ambulancias, self.emergencias
        )

        self.assertTrue(resultado.es_completa)
        self.assertTrue(resultado.es_optima)
        self.assertEqual(5, resultado.cantidad_atendidas)
        self.assertEqual(0, resultado.cantidad_sin_asignar)
        self.assertEqual(
            ["E2", "E1", "E3", "E4", "E5"], resultado.orden_prioridad
        )
        self.assertEqual(
            ["E2", "E1", "E3", "E4", "E5"],
            resultado.emergencias_atendidas,
        )
        self.assertAlmostEqual(27017.174, resultado.costo_total, places=6)
        self.assertEqual(120, resultado.alternativas_candidatas)
        self.assertEqual(30, resultado.alternativas_evaluadas)
        self.assertEqual(
            len(resultado.emergencias_atendidas),
            len(set(resultado.emergencias_atendidas)),
        )
        self.assertEqual(
            len(resultado.ambulancias_utilizadas),
            len(set(resultado.ambulancias_utilizadas)),
        )

    def test_nivel1_alcanza_la_misma_asignacion_que_el_original(self):
        nivel1 = asignar_con_nivel(
            self.resultado,
            self.ambulancias,
            self.emergencias,
            self.establecimientos,
            1,
        )
        original = asignar_original(
            self.resultado, self.ambulancias, self.emergencias
        )

        self.assertTrue(nivel1.es_completa)
        self.assertTrue(nivel1.es_optima)
        self.assertEqual(30, nivel1.alternativas_candidatas)
        self.assertEqual(15, nivel1.alternativas_evaluadas)
        self.assertEqual(original.emergencias_atendidas, nivel1.emergencias_atendidas)
        self.assertEqual(
            original.ambulancias_utilizadas, nivel1.ambulancias_utilizadas
        )
        self.assertAlmostEqual(original.costo_total, nivel1.costo_total, places=6)

    def test_maximiza_cantidad_ante_una_ambulancia_compartida(self):
        emergencias = [self.emergencia("E1"), self.emergencia("E2")]
        alternativas = [
            self.alternativa("E1", "A1", costo=100.0),
            self.alternativa("E2", "A1", costo=200.0),
        ]

        for orden, esperada, sin_asignar in (
            (["E1", "E2"], "E1", "E2"),
            (["E2", "E1"], "E2", "E1"),
        ):
            with self.subTest(orden=orden):
                resultado = asignar_global(alternativas, emergencias, orden)
                self.assertEqual(1, resultado.cantidad_atendidas)
                self.assertEqual([esperada], resultado.emergencias_atendidas)
                self.assertEqual([sin_asignar], resultado.emergencias_sin_asignar)
                self.assertEqual(
                    MOTIVO_AMBULANCIAS_USADAS,
                    resultado.motivos_sin_asignar[sin_asignar],
                )
                self.assertFalse(resultado.es_completa)

    def test_decision_global_supera_la_eleccion_local(self):
        emergencias = [self.emergencia("E1"), self.emergencia("E2")]
        alternativas = [
            self.alternativa("E1", "A1", costo=10.0),
            self.alternativa("E1", "A2", costo=20.0),
            self.alternativa("E2", "A1", costo=15.0),
            self.alternativa("E2", "A2", costo=100.0),
        ]

        resultado = asignar_global(
            alternativas, emergencias, ["E1", "E2"]
        )
        pares = {
            alternativa.emergencia_id: alternativa.ambulancia_id
            for alternativa in resultado.alternativas
        }

        self.assertEqual({"E1": "A2", "E2": "A1"}, pares)
        self.assertAlmostEqual(35.0, resultado.costo_total)

    def test_asignacion_parcial_maximiza_la_cantidad_atendida(self):
        emergencias = [
            self.emergencia("E1"),
            self.emergencia("E2"),
            self.emergencia("E3"),
        ]
        alternativas = [
            self.alternativa(emergencia_id, ambulancia_id)
            for emergencia_id in ("E1", "E2", "E3")
            for ambulancia_id in ("A1", "A2")
        ]

        resultado = asignar_global(
            alternativas, emergencias, ["E1", "E2", "E3"]
        )

        self.assertEqual(2, resultado.cantidad_atendidas)
        self.assertEqual(["E1", "E2"], resultado.emergencias_atendidas)
        self.assertEqual(["E3"], resultado.emergencias_sin_asignar)
        self.assertEqual(
            MOTIVO_AMBULANCIAS_USADAS,
            resultado.motivos_sin_asignar["E3"],
        )
        self.assertFalse(resultado.es_completa)

    def test_no_reutiliza_ambulancias_ni_emergencias(self):
        resultado = asignar_original(
            self.resultado, self.ambulancias, self.emergencias
        )

        emergencias = [a.emergencia_id for a in resultado.alternativas]
        ambulancias = [a.ambulancia_id for a in resultado.alternativas]
        self.assertEqual(len(emergencias), len(set(emergencias)))
        self.assertEqual(len(ambulancias), len(set(ambulancias)))

    def test_excluye_alternativas_no_factibles(self):
        emergencias = [self.emergencia("E1")]
        alternativas = [
            self.alternativa(
                "E1",
                "A1",
                costo=1.0,
                factible=False,
                motivos=["complejidad_ambulancia_insuficiente"],
            ),
            self.alternativa("E1", "A2", costo=10.0),
        ]

        resultado = asignar_global(alternativas, emergencias, ["E1"])
        self.assertEqual(["A2"], resultado.ambulancias_utilizadas)
        self.assertAlmostEqual(10.0, resultado.costo_total)

        solo_infactible = asignar_global(alternativas[:1], emergencias, ["E1"])
        self.assertEqual(["E1"], solo_infactible.emergencias_sin_asignar)
        self.assertEqual(
            MOTIVO_SIN_ALTERNATIVAS,
            solo_infactible.motivos_sin_asignar["E1"],
        )
        self.assertEqual(0, solo_infactible.alternativas_candidatas)

    def test_respeta_complejidad_y_equipamiento(self):
        casos = (
            ("complejidad", {"complejidad_requerida": 3}),
            ("equipamiento", {"equipamiento_requerido": ["DEA"]}),
        )
        for nombre, cambios in casos:
            with self.subTest(restriccion=nombre):
                emergencia = replace(self.emergencia_base, id="E1", **cambios)
                resultado = construir_alternativas(
                    self.ambulancias,
                    [emergencia],
                    self.establecimientos,
                    self.grafo,
                )
                asignacion = asignar_original(
                    resultado, self.ambulancias, [emergencia]
                )
                self.assertEqual(["E1"], asignacion.emergencias_sin_asignar)
                self.assertEqual(
                    MOTIVO_SIN_ALTERNATIVAS,
                    asignacion.motivos_sin_asignar["E1"],
                )
                self.assertFalse(asignacion.es_completa)

    def test_respeta_restricciones_de_establecimiento(self):
        emergencia = replace(self.emergencia_base, id="E1")
        establecimiento = replace(
            self.establecimiento_base,
            id="S1",
            habilitado_destino=False,
        )
        resultado = construir_alternativas(
            self.ambulancias,
            [emergencia],
            [establecimiento],
            self.grafo,
        )
        asignacion = asignar_original(
            resultado, self.ambulancias, [emergencia]
        )

        self.assertEqual(["E1"], asignacion.emergencias_sin_asignar)
        self.assertEqual(
            MOTIVO_SIN_ALTERNATIVAS,
            asignacion.motivos_sin_asignar["E1"],
        )

    def test_desempate_determinista(self):
        emergencias = [self.emergencia("E1")]
        alternativas = [
            self.alternativa("E1", "A1", "S2", costo=10.0),
            self.alternativa("E1", "A1", "S1", costo=10.0),
            self.alternativa("E1", "A2", "S1", costo=10.0),
        ]

        resultado = asignar_global(alternativas, emergencias, ["E1"])
        self.assertEqual("A1", resultado.alternativas[0].ambulancia_id)
        self.assertEqual("S1", resultado.alternativas[0].establecimiento_id)

        emergencias = [self.emergencia("E1"), self.emergencia("E2")]
        alternativas = [
            self.alternativa(emergencia_id, ambulancia_id, costo=10.0)
            for emergencia_id in ("E1", "E2")
            for ambulancia_id in ("A1", "A2")
        ]
        resultado = asignar_global(alternativas, emergencias, ["E1", "E2"])
        pares = {
            alternativa.emergencia_id: alternativa.ambulancia_id
            for alternativa in resultado.alternativas
        }
        self.assertEqual({"E1": "A1", "E2": "A2"}, pares)

    def test_costo_total_es_la_suma_de_las_alternativas(self):
        emergencias = [self.emergencia("E1"), self.emergencia("E2")]
        alternativas = [
            self.alternativa("E1", "A1", costo=12.5),
            self.alternativa("E2", "A2", costo=7.5),
        ]

        resultado = asignar_global(alternativas, emergencias, ["E1", "E2"])
        self.assertAlmostEqual(
            sum(a.costo_seleccion for a in resultado.alternativas),
            resultado.costo_total,
        )

    def test_comparacion_de_niveles_frente_al_original(self):
        comparacion = comparar_niveles(
            self.resultado,
            self.ambulancias,
            self.emergencias,
            self.establecimientos,
        )

        self.assertEqual(4, len(comparacion.niveles))
        self.assertEqual([1, 2, 3, 4], [
            resultado.parametros.nivel for resultado in comparacion.niveles
        ])
        self.assertEqual(
            [30, 60, 100, 120],
            [
                resultado.alternativas_candidatas
                for resultado in comparacion.niveles
            ],
        )
        self.assertEqual(
            [15, 20, 25, 30],
            [
                resultado.alternativas_evaluadas
                for resultado in comparacion.niveles
            ],
        )
        self.assertEqual(1, comparacion.nivel_recomendado)
        self.assertFalse(comparacion.perdida_por_heuristica)
        self.assertEqual([], comparacion.niveles_con_perdida)
        self.assertEqual({}, comparacion.diferencias)
        for resultado in comparacion.niveles:
            self.assertTrue(resultado.es_completa)
            self.assertAlmostEqual(
                comparacion.original.costo_total,
                resultado.costo_total,
                places=6,
            )

    def test_comparacion_detecta_perdida_por_heuristica(self):
        ambulancias = [
            replace(
                self.ambulancia_base,
                id=f"A{indice}",
                disponible=True,
                complejidad=2,
                capacidad_pacientes=1,
                equipamiento=[],
            )
            for indice in range(1, 5)
        ]
        emergencias = [
            replace(
                self.emergencia_base,
                id=f"E{indice}",
                gravedad=1,
                complejidad_requerida=1,
                cantidad_pacientes=1,
                equipamiento_requerido=[],
                minutos_espera=0.0,
            )
            for indice in range(1, 5)
        ]
        establecimientos = [
            replace(
                self.establecimiento_base,
                id="S1",
                base_id="S1",
                penalizacion_metros=0.0,
                complejidad_maxima=3,
                habilitado_destino=True,
            )
        ]
        distancias_ae = {
            f"A{ambulancia}|E{emergencia}": distancia
            for emergencia in range(1, 5)
            for ambulancia, distancia in (
                (1, 100.0),
                (2, 110.0),
                (3, 120.0),
                (4, 200.0),
            )
        }
        distancias_es = {
            f"E{emergencia}|S1": 0.0 for emergencia in range(1, 5)
        }
        alternativas = [
            self.alternativa(
                f"E{emergencia}",
                f"A{ambulancia}",
                "S1",
                costo=distancia,
            )
            for emergencia in range(1, 5)
            for ambulancia, distancia in (
                (1, 100.0),
                (2, 110.0),
                (3, 120.0),
                (4, 200.0),
            )
        ]
        resultado = resultado_sintetico(
            ambulancias,
            emergencias,
            establecimientos,
            distancias_ae=distancias_ae,
            distancias_es=distancias_es,
            alternativas=alternativas,
        )

        comparacion = comparar_niveles(
            resultado, ambulancias, emergencias, establecimientos
        )
        nivel1 = comparacion.niveles[0]

        self.assertEqual(4, comparacion.original.cantidad_atendidas)
        self.assertTrue(comparacion.original.es_completa)
        self.assertEqual(3, nivel1.cantidad_atendidas)
        self.assertFalse(nivel1.es_completa)
        self.assertEqual(12, nivel1.alternativas_candidatas)
        self.assertTrue(comparacion.perdida_por_heuristica)
        self.assertEqual([1], comparacion.niveles_con_perdida)
        self.assertEqual(2, comparacion.nivel_recomendado)
        self.assertIn(1, comparacion.diferencias)
        self.assertIn("3", comparacion.diferencias[1])
        self.assertIn("4", comparacion.diferencias[1])
        for resultado_nivel in comparacion.niveles[1:]:
            self.assertTrue(resultado_nivel.es_completa)
            self.assertAlmostEqual(
                comparacion.original.costo_total,
                resultado_nivel.costo_total,
                places=6,
            )

    def test_sin_emergencias(self):
        resultado = asignar_global([], [], [], etiqueta="vacio")

        self.assertTrue(resultado.es_completa)
        self.assertEqual(0, resultado.cantidad_emergencias)
        self.assertEqual(0, resultado.cantidad_atendidas)
        self.assertEqual(0, resultado.costo_total)
        self.assertEqual([], resultado.alternativas)
        self.assertEqual([], resultado.emergencias_sin_asignar)

    def test_sin_alternativas_factibles(self):
        emergencias = [self.emergencia("E1")]
        resultado = asignar_global([], emergencias, ["E1"])

        self.assertFalse(resultado.es_completa)
        self.assertEqual(["E1"], resultado.emergencias_sin_asignar)
        self.assertEqual(
            MOTIVO_SIN_ALTERNATIVAS,
            resultado.motivos_sin_asignar["E1"],
        )

    def test_no_muta_los_datos_de_entrada(self):
        alternativas_originales = list(self.resultado.alternativas)
        ambulancias_originales = list(self.ambulancias)
        establecimientos_originales = list(self.establecimientos)
        emergencias_originales = list(self.emergencias)

        asignar_original(self.resultado, self.ambulancias, self.emergencias)
        comparar_niveles(
            self.resultado,
            self.ambulancias,
            self.emergencias,
            self.establecimientos,
        )

        self.assertEqual(alternativas_originales, self.resultado.alternativas)
        self.assertEqual(ambulancias_originales, self.ambulancias)
        self.assertEqual(establecimientos_originales, self.establecimientos)
        self.assertEqual(emergencias_originales, self.emergencias)

    def test_no_reserva_ni_modifica_ambulancias(self):
        disponibilidad = {
            ambulancia.id: ambulancia.disponible
            for ambulancia in self.ambulancias
        }

        asignar_original(self.resultado, self.ambulancias, self.emergencias)
        comparar_niveles(
            self.resultado,
            self.ambulancias,
            self.emergencias,
            self.establecimientos,
        )

        self.assertEqual(
            disponibilidad,
            {
                ambulancia.id: ambulancia.disponible
                for ambulancia in self.ambulancias
            },
        )


if __name__ == "__main__":
    unittest.main()
