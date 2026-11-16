import json
import tempfile
import unittest
from pathlib import Path

from ambulancias_pergamino.ambulancias import cargar_ambulancias


RAIZ = Path(__file__).resolve().parents[1]
DATOS = RAIZ / "data" / "pergamino.json"
CONFIGURACION = RAIZ / "config" / "ambulancias.json"


class CargaAmbulanciasTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.datos = json.loads(DATOS.read_text(encoding="utf-8"))
        cls.bases = cls.datos["bases_ambulancias"]

    def guardar_configuracion(self, ambulancias: list[dict]) -> Path:
        archivo = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", encoding="utf-8", delete=False
        )
        with archivo:
            json.dump(
                {"datos_simulados": True, "ambulancias": ambulancias},
                archivo,
                ensure_ascii=False,
            )
        self.addCleanup(Path(archivo.name).unlink, missing_ok=True)
        return Path(archivo.name)

    def configuracion_valida(self) -> list[dict]:
        return json.loads(CONFIGURACION.read_text(encoding="utf-8"))["ambulancias"]

    def test_carga_correctamente_las_cinco_ambulancias(self) -> None:
        ambulancias = cargar_ambulancias(CONFIGURACION, self.bases)

        self.assertEqual(5, len(ambulancias))
        self.assertEqual(["A1", "A2", "A3", "A4", "A5"], [a.id for a in ambulancias])
        self.assertEqual(
            ["Clase C SAME 1", "Clase C SAME 2", "Clase C SAME RESERVA",
             "Clase C Medicar 1", "Clase C Medicar 2"],
            [a.nombre for a in ambulancias],
        )
        self.assertEqual(["SAME", "SAME", "SAME", "GUARDIA-5", "GUARDIA-5"],
                         [a.base_id for a in ambulancias])
        self.assertEqual([False, False, True, False, False],
                         [a.reserva for a in ambulancias])
        self.assertEqual("-60.5610963,-33.8909003", ambulancias[0].nodo_id)
        self.assertTrue(all(a.disponible for a in ambulancias))
        self.assertEqual("Clase C SAME RESERVA", ambulancias[2].etiqueta)

    def test_rechaza_base_inexistente(self) -> None:
        configuracion = self.configuracion_valida()
        configuracion[0]["base_id"] = "BASE-INEXISTENTE"

        with self.assertRaisesRegex(ValueError, "base inexistente"):
            cargar_ambulancias(self.guardar_configuracion(configuracion), self.bases)

    def test_rechaza_id_duplicado(self) -> None:
        configuracion = self.configuracion_valida()
        configuracion[1]["id"] = configuracion[0]["id"]

        with self.assertRaisesRegex(ValueError, "ID de ambulancia duplicado"):
            cargar_ambulancias(self.guardar_configuracion(configuracion), self.bases)

    def test_permite_varias_ambulancias_en_la_misma_base(self) -> None:
        ambulancias = cargar_ambulancias(CONFIGURACION, self.bases)
        por_base: dict[str, int] = {}
        for ambulancia in ambulancias:
            por_base[ambulancia.base_id] = por_base.get(ambulancia.base_id, 0) + 1

        self.assertEqual({"SAME": 3, "GUARDIA-5": 2}, por_base)

    def test_rechaza_reserva_no_booleana(self) -> None:
        configuracion = self.configuracion_valida()
        configuracion[0]["reserva"] = "sí"

        with self.assertRaisesRegex(ValueError, "reserva debe ser booleano"):
            cargar_ambulancias(self.guardar_configuracion(configuracion), self.bases)

    def test_rechaza_nombre_vacio(self) -> None:
        configuracion = self.configuracion_valida()
        configuracion[0]["nombre"] = "   "

        with self.assertRaisesRegex(ValueError, "nombre debe ser"):
            cargar_ambulancias(self.guardar_configuracion(configuracion), self.bases)

    def test_rechaza_complejidad_invalida(self) -> None:
        configuracion = self.configuracion_valida()
        configuracion[0]["complejidad"] = 0

        with self.assertRaisesRegex(ValueError, "complejidad"):
            cargar_ambulancias(self.guardar_configuracion(configuracion), self.bases)

    def test_rechaza_capacidad_invalida(self) -> None:
        configuracion = self.configuracion_valida()
        configuracion[0]["capacidad_pacientes"] = 0

        with self.assertRaisesRegex(ValueError, "capacidad_pacientes"):
            cargar_ambulancias(self.guardar_configuracion(configuracion), self.bases)


if __name__ == "__main__":
    unittest.main()
