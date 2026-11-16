import json
import unittest
from dataclasses import replace
from pathlib import Path

from ambulancias_pergamino.alternativas import Alternativa, construir_alternativas
from ambulancias_pergamino.ambulancias import cargar_ambulancias
from ambulancias_pergamino.emergencias import cargar_emergencias
from ambulancias_pergamino.establecimientos import cargar_establecimientos
from ambulancias_pergamino.grafo import Grafo


RAIZ = Path(__file__).resolve().parents[1]


class AlternativasTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        datos = json.loads((RAIZ / "data/pergamino.json").read_text(encoding="utf-8"))
        cls.grafo = Grafo.deserializar(datos["grafo"])
        cls.ambulancias = cargar_ambulancias(
            RAIZ / "config/ambulancias.json", datos["bases_ambulancias"]
        )
        cls.emergencias = cargar_emergencias(
            RAIZ / "config/emergencias.json", cls.grafo
        )
        cls.establecimientos = cargar_establecimientos(
            RAIZ / "config/establecimientos.json", datos["bases_ambulancias"]
        )
        cls.resultado = construir_alternativas(
            cls.ambulancias, cls.emergencias, cls.establecimientos, cls.grafo
        )

    def construir_una(self, ambulancia=None, emergencia=None, establecimiento=None, grafo=None):
        return construir_alternativas(
            [ambulancia or self.ambulancias[0]],
            [emergencia or self.emergencias[0]],
            [establecimiento or self.establecimientos[0]],
            grafo or self.grafo,
        ).alternativas[0]

    def test_genera_exactamente_100_alternativas(self) -> None:
        self.assertEqual(100, len(self.resultado.alternativas))
        factibles = [a for a in self.resultado.alternativas if a.es_factible]
        no_factibles = [a for a in self.resultado.alternativas if not a.es_factible]
        self.assertEqual(44, len(factibles))
        self.assertEqual(56, len(no_factibles))
        motivos = [
            motivo for a in no_factibles for motivo in a.motivos_descarte
        ]
        self.assertEqual(
            12, motivos.count("ambulancia_de_reserva_solo_gravedad_3")
        )
        self.assertEqual(50, motivos.count("establecimiento_no_habilitado"))
        self.assertTrue(all(
            "establecimiento_no_habilitado" in a.motivos_descarte
            or "ambulancia_de_reserva_solo_gravedad_3" in a.motivos_descarte
            for a in no_factibles
        ))

    def test_cada_emergencia_tiene_20_alternativas(self) -> None:
        for emergencia in self.emergencias:
            cantidad = sum(a.emergencia_id == emergencia.id for a in self.resultado.alternativas)
            self.assertEqual(20, cantidad)

    def test_cada_combinacion_es_unica(self) -> None:
        claves = {
            (a.ambulancia_id, a.emergencia_id, a.establecimiento_id)
            for a in self.resultado.alternativas
        }
        self.assertEqual(100, len(claves))

    def test_reutiliza_25_mas_20_rutas(self) -> None:
        self.assertEqual(25, len(self.resultado.rutas_ambulancia_emergencia))
        self.assertEqual(20, len(self.resultado.rutas_emergencia_establecimiento))
        self.assertEqual(30, self.resultado.rutas_unicas_calculadas)

    def test_conserva_tramos_total_penalizacion_y_costo(self) -> None:
        for alternativa in self.resultado.alternativas:
            self.assertEqual(
                alternativa.distancia_ambulancia_emergencia_m
                + alternativa.distancia_emergencia_establecimiento_m,
                alternativa.distancia_total_m,
            )
            self.assertEqual(
                alternativa.distancia_total_m + alternativa.penalizacion_establecimiento_m,
                alternativa.costo_seleccion,
            )

    def test_penalizaciones_actuales(self) -> None:
        san_jose = [a for a in self.resultado.alternativas if a.establecimiento_id == "GUARDIA-1"]
        clinicas = [a for a in self.resultado.alternativas if a.establecimiento_id != "GUARDIA-1"]
        self.assertTrue(all(a.penalizacion_establecimiento_m == 0 for a in san_jose))
        self.assertTrue(all(a.penalizacion_establecimiento_m == 1000 for a in clinicas))

    def test_guardias_tres_y_cuatro_no_reciben_ambulancias(self) -> None:
        inactivas = [
            a for a in self.resultado.alternativas
            if a.establecimiento_id in {"GUARDIA-3", "GUARDIA-4"}
        ]
        self.assertTrue(inactivas)
        self.assertTrue(all(not a.es_factible for a in inactivas))
        self.assertTrue(all(
            "establecimiento_no_habilitado" in a.motivos_descarte
            for a in inactivas
        ))

    def test_ambulancia_no_disponible(self) -> None:
        alternativa = self.construir_una(ambulancia=replace(self.ambulancias[0], disponible=False))
        self.assertFalse(alternativa.es_factible)
        self.assertIn("ambulancia_no_disponible", alternativa.motivos_descarte)

    def test_complejidad_ambulancia_insuficiente(self) -> None:
        ambulancia = replace(self.ambulancias[0], complejidad=2)
        emergencia = replace(self.emergencias[0], complejidad_requerida=3)
        alternativa = self.construir_una(
            ambulancia=ambulancia, emergencia=emergencia
        )
        self.assertIn("complejidad_ambulancia_insuficiente", alternativa.motivos_descarte)

    def test_ambulancia_de_reserva_solo_para_gravedad_3(self) -> None:
        ambulancia = replace(self.ambulancias[0], reserva=True, nombre="Reserva")

        grave = self.construir_una(
            ambulancia=ambulancia,
            emergencia=replace(self.emergencias[0], gravedad=3),
        )
        self.assertTrue(grave.es_factible)
        self.assertNotIn("ambulancia_de_reserva_solo_gravedad_3", grave.motivos_descarte)

        for gravedad in (1, 2):
            with self.subTest(gravedad=gravedad):
                alternativa = self.construir_una(
                    ambulancia=ambulancia,
                    emergencia=replace(self.emergencias[0], gravedad=gravedad),
                )
                self.assertFalse(alternativa.es_factible)
                self.assertIn(
                    "ambulancia_de_reserva_solo_gravedad_3",
                    alternativa.motivos_descarte,
                )

    def test_capacidad_ambulancia_insuficiente(self) -> None:
        emergencia = replace(self.emergencias[0], cantidad_pacientes=2)
        alternativa = self.construir_una(emergencia=emergencia)
        self.assertIn("capacidad_ambulancia_insuficiente", alternativa.motivos_descarte)

    def test_equipamiento_faltante(self) -> None:
        emergencia = replace(self.emergencias[0], equipamiento_requerido=["DEA"])
        alternativa = self.construir_una(emergencia=emergencia)
        self.assertIn("equipamiento_faltante", alternativa.motivos_descarte)

    def test_establecimiento_no_habilitado(self) -> None:
        establecimiento = replace(self.establecimientos[0], habilitado_destino=False)
        alternativa = self.construir_una(establecimiento=establecimiento)
        self.assertIn("establecimiento_no_habilitado", alternativa.motivos_descarte)

    def test_complejidad_establecimiento_insuficiente(self) -> None:
        emergencia = replace(self.emergencias[0], complejidad_requerida=3)
        establecimiento = replace(self.establecimientos[0], complejidad_maxima=2)
        alternativa = self.construir_una(emergencia=emergencia, establecimiento=establecimiento)
        self.assertIn("complejidad_establecimiento_insuficiente", alternativa.motivos_descarte)

    def test_ruta_inexistente_conserva_motivo_y_no_infinito(self) -> None:
        grafo = Grafo(
            nodos=dict(self.grafo.nodos),
            adyacencia={nodo: list(aristas) for nodo, aristas in self.grafo.adyacencia.items()},
        )
        aislado = grafo.agregar_nodo((-61.0, -34.0))
        ambulancia = replace(self.ambulancias[0], nodo_id=aislado)
        alternativa = self.construir_una(ambulancia=ambulancia, grafo=grafo)
        self.assertIn("sin_ruta_hasta_emergencia", alternativa.motivos_descarte)
        self.assertIsNone(alternativa.distancia_ambulancia_emergencia_m)
        self.assertIsNone(alternativa.distancia_total_m)
        self.assertIsNone(alternativa.costo_seleccion)

    def test_ruta_inexistente_hasta_establecimiento(self) -> None:
        grafo = Grafo(
            nodos=dict(self.grafo.nodos),
            adyacencia={nodo: list(aristas) for nodo, aristas in self.grafo.adyacencia.items()},
        )
        aislado = grafo.agregar_nodo((-61.0, -34.0))
        establecimiento = replace(self.establecimientos[0], nodo_id=aislado)
        alternativa = self.construir_una(establecimiento=establecimiento, grafo=grafo)
        self.assertIn("sin_ruta_hasta_establecimiento", alternativa.motivos_descarte)
        self.assertIsNone(alternativa.distancia_emergencia_establecimiento_m)

    def test_conserva_multiples_motivos(self) -> None:
        ambulancia = replace(
            self.ambulancias[0], disponible=False, complejidad=1,
            capacidad_pacientes=1, equipamiento=[]
        )
        emergencia = replace(
            self.emergencias[0], complejidad_requerida=3,
            cantidad_pacientes=2, equipamiento_requerido=["DEA"]
        )
        establecimiento = replace(
            self.establecimientos[0], habilitado_destino=False, complejidad_maxima=1
        )
        alternativa = self.construir_una(ambulancia, emergencia, establecimiento)
        self.assertEqual(6, len(alternativa.motivos_descarte))

    def test_rechaza_costos_no_finitos_o_negativos(self) -> None:
        base = dict(
            ambulancia_id="A", emergencia_id="E", establecimiento_id="H",
            distancia_ambulancia_emergencia_m=1.0,
            distancia_emergencia_establecimiento_m=2.0,
            distancia_total_m=3.0, penalizacion_establecimiento_m=0.0,
            costo_seleccion=3.0, es_factible=True, motivos_descarte=[],
        )
        for campo, valor in (
            ("distancia_total_m", -1), ("costo_seleccion", float("nan")),
            ("penalizacion_establecimiento_m", float("inf")),
        ):
            with self.subTest(campo=campo):
                datos = base | {campo: valor}
                with self.assertRaisesRegex(ValueError, campo):
                    Alternativa(**datos)


if __name__ == "__main__":
    unittest.main()
