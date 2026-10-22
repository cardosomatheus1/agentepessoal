"""implantar.py --moldes (22/10): the templates swap only after the tests and a real preview pass on the VM, inside the
agent container, and npm ci runs only when package-lock.json changed."""

import importlib.util
import sys
import types
from pathlib import Path

sys.modules["boto3"] = types.SimpleNamespace(client=lambda *a, **k: types.SimpleNamespace())
spec = importlib.util.spec_from_file_location("implantar_teste_moldes", Path(__file__).resolve().parents[1] / "implantar.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_troca_so_depois_dos_testes():
    c = m.comando_moldes("abc123", "tmp/x.tgz", "2026-10-22T12:00:00Z")
    partes = c.split(" && ")
    i_ok = next(i for i, p in enumerate(partes) if "echo TESTES_OK" in p)
    i_troca = next(i for i, p in enumerate(partes) if p.startswith(f"mv {m.MOLDES_VM}.novo {m.MOLDES_VM}"))
    i_teste = next(i for i, p in enumerate(partes) if "test_validar.py" in p)
    assert i_teste < i_ok < i_troca, "testa, confirma e só então troca"
    assert " || " not in " ".join(partes[i_teste:i_troca]).replace("|| true)", ""), "nenhuma falha é engolida antes da troca"
    assert "render.py lanca-app" in c and "--previa" in c and "docker exec" in c, "prévia de verdade dentro do container"


def test_npm_ci_so_quando_o_lock_mudou():
    c = m.comando_moldes("abc123", "tmp/x.tgz", "agora")
    assert "cmp -s" in c and "npm ci" in c.split("else", 1)[1], "reaproveita node_modules quando o lock é o mesmo"


def test_guarda_a_anterior():
    c = m.comando_moldes("abc123", "tmp/x.tgz", "agora")
    assert f"mv {m.MOLDES_VM} {m.MOLDES_VM}.anterior" in c and "abc123" in c


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f(); print("ok", nome)
