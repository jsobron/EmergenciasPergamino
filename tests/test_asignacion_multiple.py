import unittest
from dataclasses import replace

from tests.test_asignacion import AsignacionTest as Escenario
from ambulancias_pergamino.asignacion import asignar_global, asignar_original, asignar_con_nivel
from ambulancias_pergamino.alternativas import construir_alternativas
from ambulancias_pergamino.simulacion import crear_simulacion
from ambulancias_pergamino.evaluacion import _mapa_asignaciones


class AsignacionMultipleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Escenario.setUpClass()

    def escenario(self, pacientes=2, unidades=1):
        e = replace(Escenario.emergencia_base, cantidad_pacientes=pacientes,
                    ambulancias_requeridas=unidades, gravedad=3)
        alternativas = construir_alternativas(Escenario.ambulancias, [e],
                                               Escenario.establecimientos, Escenario.grafo)
        return e, alternativas

    def test_suma_capacidades_y_no_reutiliza_unidades(self):
        e, alternativas = self.escenario(3)
        r = asignar_original(alternativas, Escenario.ambulancias, [e])
        self.assertTrue(r.es_completa)
        self.assertEqual(3, len(r.alternativas))
        self.assertEqual(3, len(set(r.ambulancias_utilizadas)))
        self.assertEqual(3, sum(a.pacientes_asignados for a in r.alternativas))
        self.assertTrue(all(a.pacientes_asignados <= a.capacidad_pacientes for a in r.alternativas))

    def test_minimo_manual_agrega_unidad_de_apoyo(self):
        e, alternativas = self.escenario(1, 2)
        r = asignar_original(alternativas, Escenario.ambulancias, [e])
        self.assertEqual(2, len(r.alternativas))
        self.assertEqual([0, 1], sorted(a.pacientes_asignados for a in r.alternativas))

    def test_demanda_imposible_no_se_declara_completa(self):
        e, alternativas = self.escenario(6)
        r = asignar_original(alternativas, Escenario.ambulancias, [e])
        self.assertFalse(r.es_completa)
        self.assertEqual([e.id], r.emergencias_sin_asignar)

    def test_hospital_obligatorio_y_clinica_solo_sin_lugar(self):
        e, alternativas = self.escenario(1)
        hospital = asignar_original(alternativas, Escenario.ambulancias, [e])
        self.assertEqual(['GUARDIA-1'], hospital.establecimientos_seleccionados)
        clinica = asignar_original(alternativas, Escenario.ambulancias, [e], hospital_disponible=False)
        self.assertTrue(clinica.es_completa)
        self.assertEqual(['GUARDIA-2'], clinica.establecimientos_seleccionados)

    def test_reserva_sigue_excluida_en_gravedad_baja(self):
        e, _ = self.escenario(5)
        e = replace(e, gravedad=2)
        alternativas = construir_alternativas(Escenario.ambulancias, [e], Escenario.establecimientos, Escenario.grafo)
        r = asignar_original(alternativas, Escenario.ambulancias, [e])
        self.assertNotIn('A3', r.ambulancias_utilizadas)
        self.assertFalse(r.es_completa)

    def test_simulacion_y_evaluacion_conservan_todas_las_unidades(self):
        e, alternativas = self.escenario(2, 2)
        r = asignar_con_nivel(alternativas, Escenario.ambulancias, [e], Escenario.establecimientos, 1)
        s = crear_simulacion(r, alternativas, Escenario.ambulancias, [e], Escenario.establecimientos)
        s.avanzar_hasta_final()
        estado = s.resultado()
        self.assertEqual(2, len(estado.atenciones))
        self.assertEqual(2, len(estado.emergencias[0].ambulancia_ids))
        self.assertTrue(estado.emergencias[0].completada)
        resumen = _mapa_asignaciones(r)[e.id]
        for a in r.alternativas:
            self.assertIn(a.ambulancia_id, resumen)


def load_tests(loader, tests, pattern):
    # El escenario importado aporta fixtures, no otra ejecución de sus tests.
    return loader.loadTestsFromTestCase(AsignacionMultipleTest)
