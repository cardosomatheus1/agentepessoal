"""/decisoes and /livro of the phone bridge, read from the real helpers' files (temporary folder; no network).
Run from the repository root: python3 infra/vm/tests/test_comandos_ponte.py (boto3 needed for the import)."""

import importlib.util
import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]


def _carregar(nome: str, arquivo: Path):
    spec = importlib.util.spec_from_file_location(nome, arquivo)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main() -> int:
    p = _carregar("ponte_teste", RAIZ / "infra" / "vm" / "ponte_whatsapp.py")
    d = _carregar("decisoes_teste", RAIZ / "infra" / "vm" / "plugins" / "memoria_pessoal" / "helpers" / "decisoes.py")
    l = _carregar("livro_teste", RAIZ / "infra" / "vm" / "plugins" / "central" / "helpers" / "livro.py")
    tmp = Path(tempfile.mkdtemp(prefix="comandos-ponte-"))
    falhas = []
    try:
        d.PASTA = p.DECISOES = tmp / "decisoes"
        l.PASTA, l.BANCO = tmp / "central", tmp / "central" / "agente.db"
        p.LIVRO = l.BANCO
        if "Nenhuma decisão registrada" not in p.texto_decisoes("matheus"):
            falhas.append("sem registro")
        d.registrar("matheus", "pagamentos", "Nada de pagamento ou meio de pagamento", tipo="proibicao")
        d.registrar("matheus", "avisos", "Menos avisos e mais claros", tipo="preferencia")
        r = p.texto_decisoes("matheus")
        if not (r.index("🚫 #1") < r.index("💬 #2") and "revoga" in r):
            falhas.append(f"decisões em ordem, com o jeito de mudar: {r!r}")
        if "vazio" not in p.texto_livro("matheus"):
            falhas.append("livro vazio")
        l.registrar("executada", "matheus", "prospeccao", "instagram", "dm", "instagram:@zen.marmitas", "Oi, pessoal da Zen!")
        l.registrar("falhou", "matheus", "prospeccao", "instagram", "dm", "instagram:@anna", "Oi", resultado="script falhou")
        l.registrar("executada", "outra", "prospeccao", "instagram", "dm", "instagram:@x", "de outra pessoa")
        r = p.texto_livro("matheus")
        if not ("@zen.marmitas" in r and "falhou: script falhou" in r and "@x" not in r):
            falhas.append(f"livro do dia só da pessoa: {r!r}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for f in falhas:
        print("FALHA", f)
    print("TESTES", 4 - len(falhas), 4)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
