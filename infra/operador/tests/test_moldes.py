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


def test_previa_narrada_tem_a_credencial_da_voz():
    # OpenCode 22/10: without the /voz credentials the narrated preview always failed and nothing was ever deployed
    c = m.comando_moldes("abc123", "tmp/x.tgz", "agora")
    partes = c.split(" && ")
    i_cfg = next(i for i, p in enumerate(partes) if "aws-voz.config" in p and p.startswith("printf"))
    i_exec = next(i for i, p in enumerate(partes) if p.startswith("docker exec -e MOLDES_CACHE"))
    assert i_cfg < i_exec and "credencial_voz.py" in partes[i_cfg]
    assert "AWS_PROFILE=voz" in partes[i_exec] and "AWS_CONFIG_FILE=/a0/usr/moldes.novo/aws-voz.config" in partes[i_exec]
    raiz = Path(__file__).resolve().parents[3] / m.MOLDES
    assert (raiz / "motor" / "credencial_voz.py").exists()
    assert (raiz / "lanca-app" / "exemplos" / "raiz-sistema-computador.json").exists(), "a ficha da prévia existe"


def test_npm_ci_so_quando_o_lock_mudou():
    c = m.comando_moldes("abc123", "tmp/x.tgz", "agora")
    assert "cmp -s" in c and "npm ci" in c.split("else", 1)[1], "reaproveita node_modules quando o lock é o mesmo"


def test_guarda_a_anterior():
    c = m.comando_moldes("abc123", "tmp/x.tgz", "agora")
    assert f"mv {m.MOLDES_VM} {m.MOLDES_VM}.anterior" in c and "abc123" in c


def test_no_hermes_depois_da_virada():
    c = m.comando_moldes("abc123", "tmp/x.tgz", "agora", "hermes")
    assert "agent-zero" not in c and "/opt/venv-a0" not in c, "com o A0 parado, nada roda nele"
    assert "-u 10000 -e HOME=/opt/data hermes sh -c '/opt/hermes/.venv/bin/python3 /a0/usr/moldes.novo/motor/test_validar.py" in c
    assert "docker exec -u 10000 -e HOME=/opt/data -w /a0/usr/moldes.novo/motor hermes npm ci" in c
    assert "AWS_PROFILE=voz" in c and "render.py lanca-app" in c, "a mesma prévia narrada, como no A0"


def test_segundo_cerebro_no_portal():
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import segundo_cerebro as sc
    antes = sc.ALVO_VM
    sc.ALVO_VM = sc.ALVO_HERMES
    try:
        linha = sc._lado_vm("/x", "sondar", "a" * 40)
    finally:
        sc.ALVO_VM = antes
    assert "--container portal" in linha and "--portal-dir /opt/hermes/portal" in linha and "--login-path /entrar" in linha


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f(); print("ok", nome)
