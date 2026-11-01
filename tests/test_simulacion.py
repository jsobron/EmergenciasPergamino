import json
import unittest
from dataclasses import asdict, replace
from pathlib import Path

from ambulancias_pergamino.alternativas import (
    ResultadoAlternativas,
    construir_alternativas,
)
from ambulancias_pergamino.ambulancias import cargar_ambulancias
from ambulancias_pergamino.asignacion import ResultadoAsignacion, asignar_con_nivel
from ambulancias_pergamino.emergencias import cargar_emergencias
from ambulancias_pergamino.establecimientos import cargar_establecimientos
from ambulancias_pergamino.grafo import Grafo
from ambulancias_pergamino.simulacion import (
    ESTADO_AMBULANCIA_DISPONIBLE,
    ESTADO_AMBULANCIA_FINALIZADA,
    ESTADO_EMERGENCIA_FINALIZADA,
    ESTADO_EMERGENCIA_SIN_ASIGNACION,
    PASO_FINAL,
    crear_simulacion,
)


RAIZ = Path(__file__).resolve().parents[1]


def cargar_escenario():
    datos = json.loads((RAIZ / "data" / "pergamino.json").read_text(encoding="utf-8"))
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
    asignacion = asignar_con_nivel(
        resultado, ambulancias, emergencias, establecimientos, 1
    )
    return resultado, asignacion, ambulancias, emergencias, establecimientos


class SimulacionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        (
            cls.resultado,
            cls.asignacion,
            cls.ambulancias,
            cls.emergencias,
            cls.establecimientos,
        ) = cargar_escenario()

    def crear(self, asignacion: ResultadoAsignacion | None = None):
        return crear_simulacion(
            asignacion or self.asignacion,
            self.resultado,
            self.ambulancias,
            self.emergencias,
            self.establecimientos,
        )

    def test_creacion_e_inicializacion_de_estados(self) -> None:
        simulacion = self.crear()
        resultado = simulacion.resultado()

        self.assertEqual(0, resultado.paso)
        self.assertEqual("asignada", resultado.etapa)
        self.assertEqual(PASO_FINAL, resultado.total_pasos)
        self.assertEqual(5, resultado.cantidad_atenciones)
        self.assertEqual(0, resultado.cantidad_completadas)
        self.assertEqual(0, resultado.cantidad_sin_asignar)
        self.assertTrue(resultado.es_completa)
        self.assertFalse(resultado.es_final)

        atendidas = set(self.asignacion.emergencias_atendidas)
        for emergencia in resultado.emergencias:
            if emergencia.emergencia_id in atendidas:
                self.assertEqual("asignada", emergencia.estado)
                self.assertIsNotNone(emergencia.ambulancia_id)
                self.assertIsNotNone(emergencia.establecimiento_id)
            else:
                self.assertEqual(ESTADO_EMERGENCIA_SIN_ASIGNACION, emergencia.estado)

        utilizadas = set(self.asignacion.ambulancias_utilizadas)
        for ambulancia in resultado.ambulancias:
            if ambulancia.ambulancia_id in utilizadas:
                self.assertEqual("asignada", ambulancia.estado)
                self.assertIsNotNone(ambulancia.emergencia_id)
            else:
                self.assertEqual(ESTADO_AMBULANCIA_DISPONIBLE, ambulancia.estado)
                self.assertIsNone(ambulancia.emergencia_id)

    def test_avance_controlado_entre_etapas(self) -> None:
        simulacion = self.crear()

        simulacion.avanzar()
        resultado = simulacion.resultado()
        self.assertEqual(1, resultado.paso)
        self.assertEqual("en_camino", resultado.etapa)
        self.assertTrue(
            all(
                atencion.estado_ambulancia == "en_camino"
                for atencion in resultado.atenciones
            )
        )

        simulacion.avanzar()
        resultado = simulacion.resultado()
        self.assertEqual(2, resultado.paso)
        self.assertEqual("en_atencion", resultado.etapa)
        self.assertTrue(
            all(
                atencion.estado_emergencia == "en_atencion"
                for atencion in resultado.atenciones
            )
        )

        simulacion.avanzar()
        resultado = simulacion.resultado()
        self.assertEqual(3, resultado.paso)
        self.assertEqual("trasladando", resultado.etapa)
        self.assertTrue(
            all(
                atencion.estado_emergencia == "trasladada"
                for atencion in resultado.atenciones
            )
        )

        simulacion.avanzar()
        resultado = simulacion.resultado()
        self.assertEqual(4, resultado.paso)
        self.assertEqual("finalizada", resultado.etapa)
        self.assertTrue(resultado.es_final)
        self.assertEqual(5, resultado.cantidad_completadas)
        self.assertTrue(all(atencion.completada for atencion in resultado.atenciones))
        self.assertTrue(
            all(
                atencion.estado_emergencia == ESTADO_EMERGENCIA_FINALIZADA
                for atencion in resultado.atenciones
            )
        )

    def test_bases_de_ambulancias_coinciden_con_la_configuracion(self) -> None:
        datos = json.loads(
            (RAIZ / "data" / "pergamino.json").read_text(encoding="utf-8")
        )
        bases = {base["id"]: base for base in datos["bases_ambulancias"]}
        configuracion = json.loads(
            (RAIZ / "config" / "ambulancias.json").read_text(encoding="utf-8")
        )
        bases_configuradas = {
            ambulancia["id"]: ambulancia["base_id"]
            for ambulancia in configuracion["ambulancias"]
        }

        for ambulancia in self.ambulancias:
            self.assertEqual(
                bases_configuradas[ambulancia.id], ambulancia.base_id
            )
            self.assertEqual(
                bases[ambulancia.base_id]["nodo_id"], ambulancia.nodo_id
            )

        asignaciones = {
            alternativa.emergencia_id: alternativa.ambulancia_id
            for alternativa in self.asignacion.alternativas
        }
        bases_por_ambulancia = {
            ambulancia.id: ambulancia.base_id for ambulancia in self.ambulancias
        }
        resultado = self.crear().resultado()
        for emergencia_id, ambulancia_id in asignaciones.items():
            atencion = next(
                atencion
                for atencion in resultado.atenciones
                if atencion.emergencia_id == emergencia_id
            )
            self.assertEqual(
                bases_por_ambulancia[ambulancia_id], atencion.base_id
            )

    def test_paso_3_representa_un_traslado_en_curso(self) -> None:
        simulacion = self.crear()
        simulacion.avanzar(3)
        resultado = simulacion.resultado()

        self.assertEqual("trasladando", resultado.etapa)
        self.assertFalse(resultado.es_final)
        self.assertEqual(0, resultado.cantidad_completadas)
        for atencion in resultado.atenciones:
            self.assertEqual("trasladada", atencion.estado_emergencia)
            self.assertEqual("trasladando", atencion.estado_ambulancia)
            self.assertFalse(atencion.completada)

        simulacion.avanzar()
        final = simulacion.resultado()
        self.assertTrue(final.es_final)
        self.assertEqual(5, final.cantidad_completadas)
        for atencion in final.atenciones:
            self.assertEqual("finalizada", atencion.estado_emergencia)
            self.assertEqual("finalizada", atencion.estado_ambulancia)
            self.assertTrue(atencion.completada)

    def test_rechaza_transiciones_invalidas(self) -> None:
        for pasos in (-1, 0, 5, True, "1"):
            simulacion = self.crear()
            with self.assertRaises(ValueError):
                simulacion.avanzar(pasos)
            self.assertEqual(0, simulacion.paso_actual)

        simulacion = self.crear()
        simulacion.avanzar_hasta_final()
        with self.assertRaises(ValueError):
            simulacion.avanzar()
        self.assertEqual(PASO_FINAL, simulacion.paso_actual)

    def test_finalizacion_de_todas_las_atenciones(self) -> None:
        simulacion = self.crear()
        simulacion.avanzar_hasta_final()
        resultado = simulacion.resultado()

        self.assertTrue(resultado.es_final)
        self.assertEqual(5, resultado.cantidad_completadas)
        self.assertEqual(5, resultado.cantidad_atenciones)
        self.assertTrue(
            all(
                ambulancia.estado == ESTADO_AMBULANCIA_FINALIZADA
                for ambulancia in resultado.ambulancias
                if ambulancia.emergencia_id is not None
            )
        )
        self.assertEqual(
            1,
            sum(
                1
                for ambulancia in resultado.ambulancias
                if ambulancia.estado == ESTADO_AMBULANCIA_DISPONIBLE
            ),
        )

    def test_conserva_tramos_distancias_penalizaciones_y_costos(self) -> None:
        resultado = self.crear().resultado()

        for atencion in resultado.atenciones:
            alternativa = next(
                alternativa
                for alternativa in self.asignacion.alternativas
                if alternativa.emergencia_id == atencion.emergencia_id
            )
            ruta_inicial = self.resultado.rutas_ambulancia_emergencia[
                f"{atencion.ambulancia_id}|{atencion.emergencia_id}"
            ]
            ruta_destino = self.resultado.rutas_emergencia_establecimiento[
                f"{atencion.emergencia_id}|{atencion.establecimiento_id}"
            ]

            self.assertEqual(tuple(ruta_inicial.camino), atencion.tramo_ambulancia_emergencia.camino)
            self.assertEqual(tuple(ruta_destino.camino), atencion.tramo_emergencia_establecimiento.camino)
            self.assertAlmostEqual(
                ruta_inicial.distancia_m,
                atencion.tramo_ambulancia_emergencia.distancia_m,
            )
            self.assertAlmostEqual(
                ruta_destino.distancia_m,
                atencion.tramo_emergencia_establecimiento.distancia_m,
            )
            self.assertAlmostEqual(
                alternativa.distancia_ambulancia_emergencia_m,
                atencion.distancia_ambulancia_emergencia_m,
            )
            self.assertAlmostEqual(
                alternativa.distancia_emergencia_establecimiento_m,
                atencion.distancia_emergencia_establecimiento_m,
            )
            self.assertAlmostEqual(
                atencion.distancia_total_m,
                atencion.distancia_ambulancia_emergencia_m
                + atencion.distancia_emergencia_establecimiento_m,
            )
            self.assertAlmostEqual(
                alternativa.penalizacion_establecimiento_m,
                atencion.penalizacion_establecimiento_m,
            )
            self.assertAlmostEqual(
                atencion.costo_seleccion,
                atencion.distancia_total_m
                + atencion.penalizacion_establecimiento_m,
            )

        self.assertAlmostEqual(self.asignacion.costo_total, resultado.costo_total)
        self.assertAlmostEqual(
            resultado.costo_total,
            sum(atencion.costo_seleccion for atencion in resultado.atenciones),
        )
        self.assertAlmostEqual(
            resultado.distancia_total,
            sum(atencion.distancia_total_m for atencion in resultado.atenciones),
        )
        self.assertAlmostEqual(
            resultado.penalizacion_total,
            sum(
                atencion.penalizacion_establecimiento_m
                for atencion in resultado.atenciones
            ),
        )

    def test_emergencia_sin_asignacion_conserva_motivo(self) -> None:
        restantes = [
            alternativa
            for alternativa in self.asignacion.alternativas
            if alternativa.emergencia_id != "E5"
        ]
        parcial = replace(
            self.asignacion,
            alternativas=restantes,
            emergencias_atendidas=[
                emergencia_id
                for emergencia_id in self.asignacion.emergencias_atendidas
                if emergencia_id != "E5"
            ],
            emergencias_sin_asignar=["E5"],
            motivos_sin_asignar={"E5": "ambulancias_candidatas_ya_utilizadas"},
            ambulancias_utilizadas=sorted(
                {alternativa.ambulancia_id for alternativa in restantes}
            ),
            establecimientos_seleccionados=sorted(
                {alternativa.establecimiento_id for alternativa in restantes}
            ),
            costo_total=sum(
                alternativa.costo_seleccion or 0.0 for alternativa in restantes
            ),
            es_completa=False,
        )
        simulacion = self.crear(parcial)
        resultado = simulacion.resultado()

        e5 = next(
            emergencia
            for emergencia in resultado.emergencias
            if emergencia.emergencia_id == "E5"
        )
        self.assertEqual(ESTADO_EMERGENCIA_SIN_ASIGNACION, e5.estado)
        self.assertIsNone(e5.ambulancia_id)
        self.assertIsNone(e5.establecimiento_id)
        self.assertEqual(
            "ambulancias_candidatas_ya_utilizadas", e5.motivo_sin_asignar
        )
        self.assertIn("E5", resultado.emergencias_sin_asignar)
        self.assertFalse(resultado.es_completa)
        self.assertEqual(4, resultado.cantidad_atenciones)

        simulacion.avanzar_hasta_final()
        resultado = simulacion.resultado()
        e5 = next(
            emergencia
            for emergencia in resultado.emergencias
            if emergencia.emergencia_id == "E5"
        )
        self.assertEqual(ESTADO_EMERGENCIA_SIN_ASIGNACION, e5.estado)
        self.assertFalse(e5.completada)
        self.assertEqual(4, resultado.cantidad_completadas)
        self.assertEqual(1, resultado.cantidad_sin_asignar)

    def test_escenario_vacio(self) -> None:
        asignacion_vacia = replace(
            self.asignacion,
            etiqueta="vacia",
            parametros=None,
            alternativas=[],
            emergencias_atendidas=[],
            emergencias_sin_asignar=[],
            motivos_sin_asignar={},
            ambulancias_utilizadas=[],
            establecimientos_seleccionados=[],
            costo_total=0.0,
            es_completa=True,
            orden_prioridad=[],
        )
        resultado_vacio = ResultadoAlternativas(
            alternativas=[],
            rutas_ambulancia_emergencia={},
            rutas_emergencia_establecimiento={},
            rutas_unicas_calculadas=0,
        )
        simulacion = crear_simulacion(
            asignacion_vacia, resultado_vacio, [], [], []
        )
        resultado = simulacion.resultado()

        self.assertEqual(0, resultado.cantidad_atenciones)
        self.assertEqual(0, resultado.cantidad_completadas)
        self.assertEqual(0, resultado.cantidad_sin_asignar)
        self.assertEqual(0.0, resultado.costo_total)
        self.assertEqual(0.0, resultado.distancia_total)
        self.assertTrue(resultado.es_completa)

        simulacion.avanzar_hasta_final()
        resultado = simulacion.resultado()
        self.assertTrue(resultado.es_final)
        self.assertEqual(0, resultado.cantidad_completadas)

    def test_rechaza_asignaciones_duplicadas(self) -> None:
        duplicada = replace(
            self.asignacion,
            alternativas=[
                self.asignacion.alternativas[0],
                self.asignacion.alternativas[0],
            ],
        )
        with self.assertRaisesRegex(ValueError, "más de una asignación"):
            self.crear(duplicada)

    def test_rechaza_ruta_faltante(self) -> None:
        rutas = dict(self.resultado.rutas_ambulancia_emergencia)
        del rutas["A6|E2"]
        resultado_sin_ruta = replace(
            self.resultado, rutas_ambulancia_emergencia=rutas
        )
        with self.assertRaisesRegex(ValueError, "Falta la ruta"):
            crear_simulacion(
                self.asignacion,
                resultado_sin_ruta,
                self.ambulancias,
                self.emergencias,
                self.establecimientos,
            )

    def test_rechaza_costo_inconsistente(self) -> None:
        alternativa = self.asignacion.alternativas[0]
        alternativa_inconsistente = replace(
            alternativa,
            costo_seleccion=(alternativa.costo_seleccion or 0.0) + 1,
        )
        asignacion_inconsistente = replace(
            self.asignacion,
            alternativas=[
                alternativa_inconsistente,
                *self.asignacion.alternativas[1:],
            ],
        )
        with self.assertRaisesRegex(ValueError, "costo"):
            self.crear(asignacion_inconsistente)

    def test_no_modifica_datos_originales(self) -> None:
        antes = {
            "ambulancias": [asdict(ambulancia) for ambulancia in self.ambulancias],
            "emergencias": [asdict(emergencia) for emergencia in self.emergencias],
            "establecimientos": [
                asdict(establecimiento)
                for establecimiento in self.establecimientos
            ],
            "asignacion": asdict(self.asignacion),
        }

        simulacion = self.crear()
        simulacion.avanzar(2)
        simulacion.resultado()
        simulacion.avanzar_hasta_final()

        despues = {
            "ambulancias": [asdict(ambulancia) for ambulancia in self.ambulancias],
            "emergencias": [asdict(emergencia) for emergencia in self.emergencias],
            "establecimientos": [
                asdict(establecimiento)
                for establecimiento in self.establecimientos
            ],
            "asignacion": asdict(self.asignacion),
        }
        self.assertEqual(antes, despues)

    def test_repeticion_determinista_y_simulaciones_independientes(self) -> None:
        primera = self.crear()
        segunda = self.crear()
        primera.avanzar(2)
        segunda.avanzar(2)
        self.assertEqual(
            asdict(primera.resultado()), asdict(segunda.resultado())
        )

        primera.avanzar_hasta_final()
        tercera = self.crear()
        self.assertEqual(0, tercera.paso_actual)
        self.assertEqual(
            "asignada", tercera.resultado().atenciones[0].estado_emergencia
        )
        self.assertEqual(
            ESTADO_AMBULANCIA_FINALIZADA,
            primera.resultado().atenciones[0].estado_ambulancia,
        )


if __name__ == "__main__":
    unittest.main()
