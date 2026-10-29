import json
import tempfile
import unittest
from pathlib import Path

from ambulancias_pergamino.establecimientos import (
    calcular_costo_destino,
    cargar_establecimientos,
    es_compatible_con_complejidad,
)


RAIZ = Path(__file__).resolve().parents[1]
DATOS = RAIZ / "data" / "pergamino.json"
CONFIGURACION = RAIZ / "config" / "establecimientos.json"


class EstablecimientosTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        datos = json.loads(DATOS.read_text(encoding="utf-8"))
        cls.bases = datos["bases_ambulancias"]

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
        return cargar_establecimientos(self.guardar(), self.bases)

    def test_carga_los_cuatro_destinos_enriquecidos_desde_las_bases(self) -> None:
        establecimientos = cargar_establecimientos(CONFIGURACION, self.bases)

        self.assertEqual(4, len(establecimientos))
        self.assertEqual(
            ["GUARDIA-1", "GUARDIA-2", "GUARDIA-3", "GUARDIA-4"],
            [e.id for e in establecimientos],
        )
        self.assertTrue(all(e.habilitado_destino for e in establecimientos))
        self.assertTrue(all(e.datos_simulados for e in establecimientos))
        self.assertEqual("Hospital Interzonal San José", establecimientos[0].nombre)
        self.assertEqual("-60.5855184,-33.9115160", establecimientos[0].nodo_id)

    def test_san_jose_tiene_prioridad_uno_y_sin_penalizacion(self) -> None:
        san_jose = cargar_establecimientos(CONFIGURACION, self.bases)[0]

        self.assertEqual(1, san_jose.prioridad)
        self.assertEqual(0, san_jose.penalizacion_metros)
        self.assertEqual(3, san_jose.complejidad_maxima)

    def test_las_clinicas_tienen_penalizacion_de_mil_metros(self) -> None:
        establecimientos = cargar_establecimientos(CONFIGURACION, self.bases)

        self.assertEqual([1000, 1000, 1000], [e.penalizacion_metros for e in establecimientos[1:]])

    def test_same_no_puede_habilitarse_como_destino(self) -> None:
        self.configuracion["establecimientos"].append(
            {
                "id": "DESTINO-SAME", "base_id": "SAME", "habilitado_destino": True,
                "prioridad": 3, "penalizacion_metros": 0,
                "complejidad_maxima": 1, "especialidades": [],
            }
        )

        with self.assertRaisesRegex(ValueError, "SAME no puede"):
            self.cargar()

    def test_medicar_no_puede_habilitarse_como_destino(self) -> None:
        self.configuracion["establecimientos"].append(
            {
                "id": "DESTINO-MEDICAR", "base_id": "GUARDIA-5", "habilitado_destino": True,
                "prioridad": 3, "penalizacion_metros": 0,
                "complejidad_maxima": 1, "especialidades": [],
            }
        )

        with self.assertRaisesRegex(ValueError, "Medicar no puede"):
            self.cargar()

    def test_rechaza_ids_duplicados(self) -> None:
        self.configuracion["establecimientos"][1]["id"] = self.configuracion["establecimientos"][0]["id"]

        with self.assertRaisesRegex(ValueError, "ID de establecimiento duplicado"):
            self.cargar()

    def test_rechaza_base_inexistente(self) -> None:
        self.configuracion["establecimientos"][0]["base_id"] = "INEXISTENTE"

        with self.assertRaisesRegex(ValueError, "base inexistente"):
            self.cargar()

    def test_rechaza_dos_configuraciones_para_la_misma_base(self) -> None:
        self.configuracion["establecimientos"][1]["base_id"] = "GUARDIA-1"

        with self.assertRaisesRegex(ValueError, "más de una configuración"):
            self.cargar()

    def test_rechaza_habilitado_destino_que_no_sea_booleano(self) -> None:
        self.configuracion["establecimientos"][0]["habilitado_destino"] = "sí"

        with self.assertRaisesRegex(ValueError, "habilitado_destino"):
            self.cargar()

    def test_rechaza_datos_simulados_que_no_sea_booleano(self) -> None:
        self.configuracion["datos_simulados"] = "sí"

        with self.assertRaisesRegex(ValueError, "datos_simulados"):
            self.cargar()

    def test_exige_exactamente_cuatro_destinos(self) -> None:
        self.configuracion["establecimientos"].pop()

        with self.assertRaisesRegex(ValueError, "exactamente cuatro"):
            self.cargar()

    def test_exige_prioridad_maxima_y_penalizacion_cero_para_san_jose(self) -> None:
        casos = (("prioridad", 2, "mayor prioridad"), ("penalizacion_metros", 1, "penalización cero"))
        for campo, valor, mensaje in casos:
            with self.subTest(campo=campo):
                self.setUp()
                self.configuracion["establecimientos"][0][campo] = valor
                with self.assertRaisesRegex(ValueError, mensaje):
                    self.cargar()

    def test_rechaza_valores_numericos_invalidos(self) -> None:
        casos = (
            ("prioridad", 0),
            ("prioridad", 1.5),
            ("penalizacion_metros", -1),
            ("penalizacion_metros", True),
            ("complejidad_maxima", 0),
            ("complejidad_maxima", 2.5),
        )
        for campo, valor in casos:
            with self.subTest(campo=campo, valor=valor):
                self.setUp()
                self.configuracion["establecimientos"][0][campo] = valor
                with self.assertRaisesRegex(ValueError, campo):
                    self.cargar()

    def test_rechaza_especialidades_que_no_sean_lista(self) -> None:
        self.configuracion["establecimientos"][0]["especialidades"] = "guardia"

        with self.assertRaisesRegex(ValueError, "especialidades"):
            self.cargar()

    def test_compatibilidad_por_complejidad(self) -> None:
        san_jose, clinica, *_ = cargar_establecimientos(CONFIGURACION, self.bases)

        self.assertTrue(es_compatible_con_complejidad(san_jose, 3))
        self.assertFalse(es_compatible_con_complejidad(clinica, 3))
        self.assertTrue(es_compatible_con_complejidad(clinica, 2))

    def test_costo_conserva_distancia_penalizacion_y_total(self) -> None:
        clinica = cargar_establecimientos(CONFIGURACION, self.bases)[1]

        costo = calcular_costo_destino(850.5, clinica)

        self.assertEqual(850.5, costo.distancia_real_metros)
        self.assertEqual(1000, costo.penalizacion_metros)
        self.assertEqual(1850.5, costo.costo_seleccion_metros)

    def test_san_jose_puede_ser_preferido_con_diferencia_menor_a_mil(self) -> None:
        san_jose, clinica, *_ = cargar_establecimientos(CONFIGURACION, self.bases)

        costo_san_jose = calcular_costo_destino(1800, san_jose)
        costo_clinica = calcular_costo_destino(1000, clinica)

        self.assertLess(costo_san_jose.costo_seleccion_metros, costo_clinica.costo_seleccion_metros)

    def test_clinica_puede_ser_preferida_si_san_jose_supera_mil_metros_adicionales(self) -> None:
        san_jose, clinica, *_ = cargar_establecimientos(CONFIGURACION, self.bases)

        costo_san_jose = calcular_costo_destino(2101, san_jose)
        costo_clinica = calcular_costo_destino(1000, clinica)

        self.assertLess(costo_clinica.costo_seleccion_metros, costo_san_jose.costo_seleccion_metros)


if __name__ == "__main__":
    unittest.main()
