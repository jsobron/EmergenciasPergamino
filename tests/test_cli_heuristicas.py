import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from ambulancias_pergamino.cli import (
    listar_alternativas_reducidas,
    listar_candidatos,
    resumir_heuristicas,
)


RAIZ = Path(__file__).resolve().parents[1]
ENTRADA = RAIZ / "data/pergamino.json"
AMBULANCIAS = RAIZ / "config/ambulancias.json"
EMERGENCIAS = RAIZ / "config/emergencias.json"
ESTABLECIMIENTOS = RAIZ / "config/establecimientos.json"


class CliHeuristicasTest(unittest.TestCase):
    def ejecutar(self, funcion, *argumentos):
        salida = io.StringIO()
        with redirect_stdout(salida):
            funcion(*argumentos)
        return salida.getvalue()

    def test_resumen_informa_parametros_reduccion_y_orden(self) -> None:
        texto = self.ejecutar(
            resumir_heuristicas,
            ENTRADA, AMBULANCIAS, EMERGENCIAS, ESTABLECIMIENTOS,
        )
        self.assertIn("Nivel de candidatos: 1", texto)
        self.assertIn("Ambulancias por emergencia (k): 3", texto)
        self.assertIn("Establecimientos por emergencia (h): 2", texto)
        self.assertIn("Alternativas originales: 120", texto)
        self.assertIn("Alternativas factibles: 120", texto)
        self.assertIn("Alternativas no factibles excluidas: 0", texto)
        self.assertIn("Alternativas tras filtrar ambulancias: 60", texto)
        self.assertIn("Alternativas tras filtrar establecimientos: 30", texto)
        self.assertIn("Alternativas reducidas: 30", texto)
        self.assertIn("Reducción: 75.0%", texto)
        posiciones = [
            texto.index(f"{indice}. {emergencia}")
            for indice, emergencia in enumerate(
                ["E2", "E1", "E3", "E4", "E5"], 1
            )
        ]
        self.assertEqual(sorted(posiciones), posiciones)

    def test_resumen_permite_elegir_otro_nivel(self) -> None:
        texto = self.ejecutar(
            resumir_heuristicas,
            ENTRADA, AMBULANCIAS, EMERGENCIAS, ESTABLECIMIENTOS, 2,
        )
        self.assertIn("Nivel de candidatos: 2", texto)
        self.assertIn("Ambulancias por emergencia (k): 4", texto)
        self.assertIn("Establecimientos por emergencia (h): 3", texto)
        self.assertIn("Alternativas reducidas: 60", texto)

    def test_listar_candidatos_muestra_conservados_excluidos_y_motivos(self) -> None:
        texto = self.ejecutar(
            listar_candidatos,
            "E1", ENTRADA, AMBULANCIAS, EMERGENCIAS, ESTABLECIMIENTOS,
        )
        self.assertIn("Emergencia E1:", texto)
        self.assertIn("Ambulancias conservadas (3):", texto)
        self.assertIn("A1: 2667 m", texto)
        self.assertIn("A2: 3241 m", texto)
        self.assertIn("A3: 3385 m", texto)
        self.assertIn("Ambulancias excluidas (3):", texto)
        self.assertIn("fuera_de_las_k_mas_cercanas", texto)
        self.assertIn("Establecimientos conservados (2):", texto)
        self.assertIn("GUARDIA-2: criterio 3675 m", texto)
        self.assertIn("GUARDIA-3: criterio 4141 m", texto)
        self.assertIn("Establecimientos excluidos (2):", texto)
        self.assertIn("fuera_de_los_h_mas_convenientes", texto)

    def test_listar_candidatos_sin_filtro_recorre_todas_las_emergencias(self) -> None:
        texto = self.ejecutar(
            listar_candidatos,
            None, ENTRADA, AMBULANCIAS, EMERGENCIAS, ESTABLECIMIENTOS,
        )
        for emergencia_id in ("E1", "E2", "E3", "E4", "E5"):
            self.assertIn(f"Emergencia {emergencia_id}:", texto)

    def test_listar_reducidas_de_e1_tiene_seis_alternativas(self) -> None:
        texto = self.ejecutar(
            listar_alternativas_reducidas,
            "E1", ENTRADA, AMBULANCIAS, EMERGENCIAS, ESTABLECIMIENTOS,
        )
        self.assertIn("Alternativas reducidas para E1: 6", texto)
        lineas = [
            linea for linea in texto.splitlines()
            if len(linea) > 1 and linea[0] == "A" and linea[1].isdigit()
        ]
        self.assertEqual(6, len(lineas))
        self.assertIn("GUARDIA-2", texto)
        self.assertIn("GUARDIA-3", texto)
        self.assertNotIn("GUARDIA-1", texto)
        self.assertNotIn("GUARDIA-4", texto)

    def test_listar_reducidas_sin_filtro_informa_cada_emergencia(self) -> None:
        texto = self.ejecutar(
            listar_alternativas_reducidas,
            None, ENTRADA, AMBULANCIAS, EMERGENCIAS, ESTABLECIMIENTOS,
        )
        for emergencia_id in ("E1", "E2", "E3", "E4", "E5"):
            self.assertIn(
                f"Alternativas reducidas para {emergencia_id}: 6", texto
            )

    def test_rechaza_emergencia_inexistente(self) -> None:
        with self.assertRaisesRegex(ValueError, "Emergencia inexistente"):
            listar_candidatos(
                "E99", ENTRADA, AMBULANCIAS, EMERGENCIAS, ESTABLECIMIENTOS
            )
        with self.assertRaisesRegex(ValueError, "Emergencia inexistente"):
            listar_alternativas_reducidas(
                "E99", ENTRADA, AMBULANCIAS, EMERGENCIAS, ESTABLECIMIENTOS
            )

    def test_rechaza_nivel_inexistente(self) -> None:
        with self.assertRaisesRegex(ValueError, "Nivel de candidatos inexistente"):
            resumir_heuristicas(
                ENTRADA, AMBULANCIAS, EMERGENCIAS, ESTABLECIMIENTOS, 99
            )


if __name__ == "__main__":
    unittest.main()
