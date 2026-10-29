import json
import tempfile
import unittest
from pathlib import Path

from ambulancias_pergamino.emergencias import (
    analizar_conectividad,
    cargar_emergencias,
)
from ambulancias_pergamino.establecimientos import cargar_establecimientos
from ambulancias_pergamino.grafo import Grafo


RAIZ = Path(__file__).resolve().parents[1]
DATOS = RAIZ / "data" / "pergamino.json"
CONFIGURACION = RAIZ / "config" / "emergencias.json"


class EmergenciasTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.datos = json.loads(DATOS.read_text(encoding="utf-8"))
        cls.grafo = Grafo.deserializar(cls.datos["grafo"])
        cls.bases = cls.datos["bases_ambulancias"]
        cls.establecimientos = cargar_establecimientos(
            RAIZ / "config" / "establecimientos.json", cls.bases
        )

    def setUp(self) -> None:
        self.configuracion = json.loads(CONFIGURACION.read_text(encoding="utf-8"))

    def guardar(self) -> Path:
        archivo = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", encoding="utf-8", delete=False
        )
        with archivo:
            json.dump(self.configuracion, archivo, ensure_ascii=False)
        self.addCleanup(Path(archivo.name).unlink, missing_ok=True)
        return Path(archivo.name)

    def cargar(self):
        return cargar_emergencias(self.guardar(), self.grafo)

    def test_carga_las_cinco_emergencias_simuladas(self) -> None:
        emergencias = cargar_emergencias(CONFIGURACION, self.grafo)

        self.assertEqual(["E1", "E2", "E3", "E4", "E5"], [e.id for e in emergencias])
        self.assertTrue(all(e.datos_simulados for e in emergencias))
        self.assertTrue(all(e.nodo_id in self.grafo.nodos for e in emergencias))
        self.assertTrue(all(e.distancia_al_nodo_m > 0 for e in emergencias))

    def test_conserva_gravedad_y_complejidad_como_dimensiones_independientes(self) -> None:
        emergencia = cargar_emergencias(CONFIGURACION, self.grafo)[0]

        self.assertEqual(3, emergencia.gravedad)
        self.assertEqual(2, emergencia.complejidad_requerida)

    def test_rechaza_id_vacio_o_duplicado(self) -> None:
        casos = (("", "no vacío"), ("E2", "duplicado"))
        for valor, mensaje in casos:
            with self.subTest(valor=valor):
                self.setUp()
                self.configuracion["emergencias"][0]["id"] = valor
                with self.assertRaisesRegex(ValueError, mensaje):
                    self.cargar()

    def test_rechaza_coordenadas_no_numericas_o_booleanas(self) -> None:
        for campo, valor in (("latitud", "sur"), ("longitud", True)):
            with self.subTest(campo=campo):
                self.setUp()
                self.configuracion["emergencias"][0][campo] = valor
                with self.assertRaisesRegex(ValueError, campo):
                    self.cargar()

    def test_rechaza_coordenadas_fuera_de_los_limites_del_grafo(self) -> None:
        self.configuracion["emergencias"][0]["latitud"] = 0

        with self.assertRaisesRegex(ValueError, "límites del grafo"):
            self.cargar()

    def test_acepta_gravedad_y_complejidad_entre_uno_y_tres(self) -> None:
        for gravedad in (1, 2, 3):
            for complejidad in (1, 2, 3):
                with self.subTest(gravedad=gravedad, complejidad=complejidad):
                    self.setUp()
                    crudo = self.configuracion["emergencias"][0]
                    crudo["gravedad"] = gravedad
                    crudo["complejidad_requerida"] = complejidad
                    self.assertEqual(gravedad, self.cargar()[0].gravedad)

    def test_rechaza_gravedad_o_complejidad_fuera_de_escala(self) -> None:
        casos = (
            ("gravedad", 0), ("gravedad", 4), ("gravedad", 1.5),
            ("complejidad_requerida", 0), ("complejidad_requerida", 4),
            ("complejidad_requerida", True),
        )
        for campo, valor in casos:
            with self.subTest(campo=campo, valor=valor):
                self.setUp()
                self.configuracion["emergencias"][0][campo] = valor
                with self.assertRaisesRegex(ValueError, campo):
                    self.cargar()

    def test_rechaza_cantidad_de_pacientes_no_positiva(self) -> None:
        for valor in (0, -1, 1.5, True):
            with self.subTest(valor=valor):
                self.setUp()
                self.configuracion["emergencias"][0]["cantidad_pacientes"] = valor
                with self.assertRaisesRegex(ValueError, "cantidad_pacientes"):
                    self.cargar()

    def test_rechaza_equipamiento_que_no_sea_lista(self) -> None:
        self.configuracion["emergencias"][0]["equipamiento_requerido"] = "oxígeno"

        with self.assertRaisesRegex(ValueError, "equipamiento_requerido"):
            self.cargar()

    def test_rechaza_minutos_de_espera_negativos_o_no_numericos(self) -> None:
        for valor in (-1, "diez", True, float("nan"), float("inf")):
            with self.subTest(valor=valor):
                self.setUp()
                self.configuracion["emergencias"][0]["minutos_espera"] = valor
                with self.assertRaisesRegex(ValueError, "minutos_espera"):
                    self.cargar()

    def test_rechaza_estado_distinto_de_pendiente(self) -> None:
        self.configuracion["emergencias"][0]["estado"] = "asignada"

        with self.assertRaisesRegex(ValueError, "estado"):
            self.cargar()

    def test_rechaza_datos_simulados_que_no_sea_booleano(self) -> None:
        self.configuracion["emergencias"][0]["datos_simulados"] = "sí"

        with self.assertRaisesRegex(ValueError, "datos_simulados"):
            self.cargar()

    def test_no_impone_un_maximo_de_emergencias(self) -> None:
        sexta = dict(self.configuracion["emergencias"][0])
        sexta["id"] = "E6"
        self.configuracion["emergencias"].append(sexta)

        self.assertEqual(6, len(self.cargar()))

    def test_todas_tienen_conectividad_operativa(self) -> None:
        emergencias = cargar_emergencias(CONFIGURACION, self.grafo)

        informes = analizar_conectividad(
            emergencias, self.bases, self.establecimientos, self.grafo
        )

        self.assertEqual(5, len(informes))
        for informe in informes:
            self.assertEqual(6, len(informe.bases_alcanzables))
            self.assertEqual(4, len(informe.establecimientos_alcanzables))
            self.assertEqual([], informe.advertencias)


if __name__ == "__main__":
    unittest.main()
