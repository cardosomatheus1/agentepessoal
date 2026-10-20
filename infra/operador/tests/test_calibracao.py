"""implantar.py --calibracao (20/10): only the AR Board criteria go to the VM, never the judged cases."""

import importlib.util
import sys
import tempfile
import types
from pathlib import Path

sys.modules["boto3"] = types.SimpleNamespace(client=lambda *a, **k: types.SimpleNamespace())
spec = importlib.util.spec_from_file_location("implantar_teste", Path(__file__).resolve().parents[1] / "implantar.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_so_criterios():
    with tempfile.TemporaryDirectory() as d:
        raiz = Path(d)
        for agente in ("prospeccao", "conteudo"):
            (raiz / "calibracao" / agente).mkdir(parents=True)
            (raiz / "calibracao" / agente / "criterios.md").write_text("# x\n")
            (raiz / "calibracao" / agente / "casos.jsonl").write_text("{}\n")
        (raiz / "calibracao" / ".quadro").mkdir()
        (raiz / "calibracao" / ".quadro" / "rodada.json").write_text("{}")
        assert m.arquivos_calibracao(raiz) == ["calibracao/conteudo/criterios.md", "calibracao/prospeccao/criterios.md"]


def test_repositorio_tem_os_da_prospeccao():
    assert "calibracao/prospeccao/criterios.md" in m.arquivos_calibracao()


if __name__ == "__main__":
    test_so_criterios()
    test_repositorio_tem_os_da_prospeccao()
    print("calibracao: ok")
