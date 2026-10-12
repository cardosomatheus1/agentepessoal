"""The phone bridge (host) and plugins/cofre (container) write the same vault files: they must share one lock and
never take an unreadable file as empty. Run from the repository root: python3 infra/vm/tests/test_cofre_ponte.py
(temporary folder only; boto3 needed for the import, no AWS call)."""

import importlib.util
import shutil
import sys
import tempfile
import threading
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]


def _carregar(nome: str, arquivo: Path):
    spec = importlib.util.spec_from_file_location(nome, arquivo)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main() -> int:
    ponte = _carregar("ponte_teste", RAIZ / "infra" / "vm" / "ponte_whatsapp.py")
    cofre = _carregar("cofre_teste", RAIZ / "infra" / "vm" / "plugins" / "cofre" / "helpers" / "cofre.py")
    tmp = Path(tempfile.mkdtemp(prefix="cofre-ponte-"))
    falhas = []
    try:
        ponte.COFRE = cofre.PASTA = tmp / "segredos"
        log = []
        ponte.log = log.append
        login = "teste_ponte"

        # 1. both writers at once: the lock is the same file, so nothing is lost
        def pela_ponte():
            for i in range(20):
                ponte.DESCREVER.pop(login, None)
                ponte.comando_cofre(login, f"/senha PONTE_{i} valor{i}")

        def pelo_agente():
            for i in range(20):
                cofre.salvar(login, f"AGENTE_{i}", f"valor{i}")

        fios = [threading.Thread(target=pela_ponte), threading.Thread(target=pelo_agente)]
        [f.start() for f in fios]
        [f.join() for f in fios]
        nomes = cofre.carregar(login)
        if len(nomes) != 40:
            falhas.append(f"gravações simultâneas: esperava 40 senhas, ficaram {len(nomes)}")

        # 2. the description answered after /senha goes to the shared descriptions file
        ponte.comando_cofre(login, "/senha GMAIL_SENHA abc123")
        r = ponte.comando_cofre(login, "Google · teste@exemplo.com")
        if not r.startswith("📝 Anotado") or cofre.descricoes(login).get("GMAIL_SENHA") != "Google · teste@exemplo.com":
            falhas.append(f"descrição pela ponte: {r!r}")

        # 3. unreadable vault: the bridge refuses and leaves the file alone
        arq = cofre._arquivo(login)
        arq.write_text('{"GMAIL_SENHA": "ab', encoding="utf-8")
        r = ponte.comando_cofre(login, "/senha NOVA_SENHA xyz")
        if "Não consegui ler o cofre" not in r or arq.read_text(encoding="utf-8") != '{"GMAIL_SENHA": "ab':
            falhas.append(f"cofre ilegível: a ponte devia recusar sem gravar: {r!r}")
        r = ponte.comando_cofre(login, "/senhas")
        if "Não consegui ler o cofre" not in r:
            falhas.append(f"listar cofre ilegível: {r!r}")
        if list((tmp / "segredos").glob(".*.tmp")):
            falhas.append("arquivo temporário largado")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for f in falhas:
        print("FALHA", f)
    print("TESTES", 4 - min(len(falhas), 4), 4)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
