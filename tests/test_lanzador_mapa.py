import unittest
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]
LANZADOR = RAIZ / "abrir-mapa.ps1"


class LanzadorMapaTest(unittest.TestCase):
    def test_regenera_siempre_el_html_antes_de_abrirlo(self) -> None:
        script = LANZADOR.read_text(encoding="utf-8-sig")

        self.assertIn("& $python -m ambulancias_pergamino exportar-mapa", script)
        self.assertNotIn("if (-not (Test-Path -LiteralPath $mapa))", script)
        self.assertLess(
            script.index("& $python -m ambulancias_pergamino exportar-mapa"),
            script.index("function Test-MapaServer"),
        )

    def test_servidor_local_usa_el_python_detectado(self) -> None:
        script = LANZADOR.read_text(encoding="utf-8-sig")

        self.assertIn("-FilePath $python", script)
        self.assertIn("@('-m', 'http.server'", script)


if __name__ == "__main__":
    unittest.main()
