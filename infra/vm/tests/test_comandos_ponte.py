"""/decisoes and /livro of the phone bridge, read from the real helpers' files (temporary folder; no network).
Run from the repository root: python3 infra/vm/tests/test_comandos_ponte.py (boto3 needed for the import)."""

import importlib.util
import json
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


class _Resposta:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps({"texto": "⚙️ *Fazendo agora*\nNada rodando."}).encode()


def _resposta_painel(req, timeout=0):
    return _Resposta()


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
        # 12/10 review §6: the secret's name (never the value) and the research's file are in the ledger too
        l.registrar("executada", "matheus", "cofre", "browser", "segredo", "cofre:FEQ", "", resultado="senha FEQ entregue")
        l.registrar("executada", "matheus", "pesquisa", "pesquisar", "pesquisa",
                    "arquivo:/a0/usr/workdir/pesquisas/20261012-152000/sintese.md", "Qual lava e seca compensa?")
        r = p.texto_livro("matheus")
        if not ("🔑 senha usada: 1" in r and "senha usada FEQ" in r and "🔎 pesquisa 20261012-152000 «Qual lava e seca" in r
                and "/a0/usr/workdir" not in r):
            falhas.append(f"senha usada (só o nome) e pesquisa no /livro: {r!r}")
        # /painel (12/10 review §7 item 11): the ledger in one line, the health check only for the owner
        r = p.linha_livro("matheus")
        if not ("💬 DM: 1" in r and "(falhou)" in r and "🔑 senha usada: 1" in r and "/livro" in r):
            falhas.append(f"livro numa linha: {r!r}")
        if "nada registrado" not in p.linha_livro("ninguem"):
            falhas.append("livro vazio para quem não tem ações")
        import time

        p.SAUDE = tmp / "saude.json"
        if "ainda não conferida" not in p.linha_saude():
            falhas.append("saúde sem conferência")
        agora = time.time()
        p.SAUDE.write_text(json.dumps({"em": time.strftime("%FT%TZ", time.gmtime(agora - 3600)), "problemas": []}))
        r = p.linha_saude(agora)
        if not ("tudo certo" in r and "atrasada" not in r):
            falhas.append(f"saúde em dia: {r!r}")
        p.SAUDE.write_text(json.dumps({"em": time.strftime("%FT%TZ", time.gmtime(agora - 30 * 3600)),
                                       "problemas": ["disco 91% cheio", "backup atrasado"]}))
        r = p.linha_saude(agora)
        if not ("atrasada" in r and "2 problema(s)" in r and "• disco 91% cheio" in r):
            falhas.append(f"saúde atrasada e com problemas: {r!r}")
        p.chave = lambda: "x"
        p.urllib.request.urlopen = _resposta_painel
        p.gasto = lambda: (1.5, 20.0)
        p.cfg = lambda: {}
        r = p.texto_painel("matheus")
        if not (r.index("Fazendo agora") < r.index("Livro de hoje") < r.index("Saúde") < r.index("Gasto")):
            falhas.append(f"painel na ordem: {r!r}")
        if "Saúde" in p.texto_painel("outra"):
            falhas.append("a saúde da VM só aparece para o dono")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for f in falhas:
        print("FALHA", f)
    print("TESTES", 12 - len(falhas), 12)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
