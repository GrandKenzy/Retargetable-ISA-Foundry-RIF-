from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import unittest

from rif.cli import main


ROOT = Path(__file__).resolve().parents[1]
HELP = ROOT / "help"


class HelpTests(unittest.TestCase):
    def test_help_files_exist(self):
        required = [
            "resources/system/home/que_es_rif.md",
            "resources/system/home/version_actual.md",
            "resources/system/home/como_se_usa.md",
            "resources/use/instrucciones/instrucciones.md",
            "resources/use/instrucciones/flujos_on_switch.md",
            "resources/use/instrucciones/tablas_y_secciones.md",
            "resources/use/plugins/basics.md",
            "resources/use/plugins/crear_y_usar.md",
            "resources/use/plugins/estructura.md",
            "resources/use/plugins/importar.md",
            "resources/use/empaquetadores/packer.md",
            "resources/use/empaquetadores/linker.md",
            "resources/use/cli/cli.md",
            "resources/use/cli/compilar.md",
            "resources/system/futuros/mir.md",
            "resources/system/futuros/optimizadores.md",
            "resources/system/futuros/soporte.md",
            "resources/system/futuros/mejoras_del_linker.md",
            "resources/system/futuros/compiladores.md",
            "resources/system/futuros/total_vscode_support.md",
        ]

        self.assertTrue((HELP / "index.html").exists())
        for item in required:
            self.assertTrue((HELP / item).exists(), item)

    def test_cli_help_lists_topics(self):
        output = StringIO()
        with redirect_stdout(output):
            code = main(["help"])

        self.assertEqual(code, 0)
        self.assertIn("que_es_rif", output.getvalue())
        self.assertIn("compilar", output.getvalue())

    def test_cli_help_reads_topic(self):
        output = StringIO()
        with redirect_stdout(output):
            code = main(["help", "version_actual"])

        self.assertEqual(code, 0)
        self.assertIn("A 0.0 Beta", output.getvalue())


if __name__ == "__main__":
    unittest.main()
