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

    def test_carga_correctamente_las_seis_ambulancias(self) -> None:
        ambulancias = cargar_ambulancias(CONFIGURACION, self.bases)

        self.assertEqual(6, len(ambulancias))
        self.assertEqual(["A1", "A2", "A3", "A4", "A5", "A6"], [a.id for a in ambulancias])
        self.assertEqual("-60.5777033,-33.8912338", ambulancias[0].nodo_id)
        self.assertTrue(all(a.disponible for a in ambulancias))

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

    def test_rechaza_dos_ambulancias_en_la_misma_base(self) -> None:
        configuracion = self.configuracion_valida()
        configuracion[1]["base_id"] = configuracion[0]["base_id"]

        with self.assertRaisesRegex(ValueError, "más de una ambulancia"):
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
