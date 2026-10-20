"""Tests of the vault's safe writes (temporary folder only; never the live vault, no values printed).
Run with implantar.py (staging copy) or inside the container."""

import importlib.util
import shutil
import stat
import sys
import tempfile
import threading
import traceback
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
LOGIN = "teste_cofre"


class Falha(AssertionError):
    pass


def ok(cond, msg):
    if not cond:
        raise Falha(msg)


def eq(a, b, msg):
    if a != b:
        raise Falha(f"{msg}: esperado {b!r}, veio {a!r}")


def _carregar(nome: str, arquivo: Path):
    spec = importlib.util.spec_from_file_location(nome, arquivo)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Suite:
    def __init__(self):
        self.c = _carregar("cofre_teste", RAIZ / "helpers" / "cofre.py")
        self.resultados = []

    def _pasta_nova(self):
        if getattr(self, "_tmp", None):
            shutil.rmtree(self._tmp, ignore_errors=True)
        self._tmp = Path(tempfile.mkdtemp(prefix="cofre-teste-"))
        self.c.PASTA = self._tmp / "segredos"
        self.c._ultimo_bom.clear()

    def t_salvar_descrever_apagar(self):
        c = self.c
        c.salvar(LOGIN, "GMAIL_SENHA", "valor-1")
        c.salvar(LOGIN, "TAVILY_API_KEY", "valor-2")
        c.descrever(LOGIN, "GMAIL_SENHA", "Google · teste@exemplo.com")
        eq(sorted(c.carregar(LOGIN)), ["GMAIL_SENHA", "TAVILY_API_KEY"], "as duas guardadas")
        eq(c.lista(LOGIN)[0], ("GMAIL_SENHA", "Google · teste@exemplo.com"), "com a descrição")
        c.apagar(LOGIN, "GMAIL_SENHA")
        eq(sorted(c.carregar(LOGIN)), ["TAVILY_API_KEY"], "apagada")
        eq(c.descricoes(LOGIN), {}, "a descrição vai junto")
        modo = stat.S_IMODE(c._arquivo(LOGIN).stat().st_mode)
        eq(modo, 0o600, "arquivo do cofre só para o dono")
        eq(stat.S_IMODE(c.PASTA.stat().st_mode), 0o700, "pasta só para o dono")
        ok(not list(c.PASTA.glob(".*.tmp")), "nenhum temporário largado")
        try:
            c.descrever(LOGIN, "NAO_EXISTE", "x")
            raise Falha("descrever segredo inexistente devia recusar")
        except ValueError:
            pass

    def t_arquivo_ilegivel_nunca_vira_vazio(self):
        c = self.c
        c.salvar(LOGIN, "GMAIL_SENHA", "valor-1")
        eq(c.carregar(LOGIN), {"GMAIL_SENHA": "valor-1"}, "lido uma vez (fica como última cópia boa)")
        arq = c._arquivo(LOGIN)
        arq.write_text('{"GMAIL_SENHA": "val', encoding="utf-8")  # cut in the middle of a write
        try:
            c.salvar(LOGIN, "OUTRA", "valor-2")
            raise Falha("gravar por cima de um cofre ilegível devia dar erro")
        except c.CofreIlegivel:
            pass
        eq(arq.read_text(encoding="utf-8"), '{"GMAIL_SENHA": "val', "o arquivo não foi sobrescrito")
        eq(c.carregar(LOGIN), {"GMAIL_SENHA": "valor-1"},
           "para usar e mascarar, vale a última cópia boa (o valor continua mascarado nas saídas)")

    def t_gravacoes_simultaneas_nao_se_apagam(self):
        c = self.c
        erros = []

        def gravar(prefixo):
            try:
                for i in range(15):
                    c.salvar(LOGIN, f"{prefixo}_{i}", f"v{i}")
            except Exception as exc:  # pragma: no cover
                erros.append(repr(exc))

        fios = [threading.Thread(target=gravar, args=(p,)) for p in ("A", "B", "C")]
        [f.start() for f in fios]
        [f.join() for f in fios]
        eq(erros, [], "sem erro")
        eq(len(c.carregar(LOGIN)), 45, "as 45 senhas ficaram (nenhuma gravação apagou a outra)")

    def t_livro_so_com_o_nome(self):
        # 12/10 review §6: the ledger records which secret was handed to which tool — the name, never the value
        lc = _carregar("cofre_livro_teste", RAIZ / "helpers" / "livro_cofre.py")
        central = RAIZ.parent / "central" / "helpers" / "livro.py"
        if not central.exists():
            central = Path("/a0/usr/plugins/central/helpers/livro.py")
        livro = _carregar("central_livro_teste", central)
        livro.PASTA, livro.BANCO = self._tmp / "central", self._tmp / "central" / "agente.db"
        ultimos = {}
        feitos = lc.registrar_usos(livro, "pessoa_cofre", "browser", ["FEQ", "GMAIL_SENHA"], ultimos, "ctx1", agora=1000.0)
        eq(feitos, ["FEQ", "GMAIL_SENHA"], "os dois nomes registrados")
        eq(lc.registrar_usos(livro, "pessoa_cofre", "browser", ["FEQ"], ultimos, "ctx1", agora=1300.0), [],
           "o mesmo nome na mesma conversa em 10 min não repete")
        eq(lc.registrar_usos(livro, "pessoa_cofre", "browser", ["FEQ"], ultimos, "ctx1", agora=1000.0 + lc.INTERVALO), ["FEQ"],
           "depois de 10 min registra de novo")
        linhas = livro.do_periodo("pessoa_cofre", 0)
        eq(sorted(r["alvo"] for r in linhas), ["cofre:FEQ", "cofre:FEQ", "cofre:GMAIL_SENHA"], "alvo = nome no cofre")
        ok(all(not r["conteudo_previa"] and not r["conteudo_hash"] and r["verbo"] == "segredo" for r in linhas),
           "nada do valor no livro")
        eq(lc.registrar_usos(None, "pessoa_cofre", "browser", ["X"], {}, agora=1.0), [], "sem livro instalado: nada, sem erro")
        eq(lc.registrar_usos(livro, "teste_cofre", "browser", ["X"], {}, agora=1.0), [], "login de teste não vai ao livro")

    def t_bloco_do_prompt_curto_sem_regras_repetidas(self):
        # 20/10 (prompt enxuto): captcha and "never ask in the chat" live in prompt_enxuto; long descriptions are cut
        stubs = {"agent": types.ModuleType("agent"), "helpers.extension": types.ModuleType("helpers.extension")}
        stubs["agent"].LoopData = type("LoopData", (), {})
        stubs["helpers.extension"].Extension = type("Extension", (), {})
        antes = {k: sys.modules.get(k) for k in stubs}
        sys.modules.update(stubs)
        try:
            ext = _carregar("cofre_prompt_teste", RAIZ / "extensions" / "python" / "system_prompt" / "_14_cofre.py")
        finally:
            for k, v in antes.items():
                sys.modules.pop(k, None) if v is None else sys.modules.__setitem__(k, v)
        falso = types.SimpleNamespace(dono=lambda ctx: LOGIN, carregar=lambda d: {"GMAIL": 1, "IG": 1},
                                      lista=lambda d: [("GMAIL", "Google · " + "conta muito comprida " * 10), ("IG", "")])
        ext.cofre = lambda: falso
        obj = ext.CofrePrompt.__new__(ext.CofrePrompt)
        obj.agent = types.SimpleNamespace(context=None)
        saida = []
        corrotina = obj.execute(system_prompt=saida)
        try:
            corrotina.send(None)
        except StopIteration:
            pass
        texto = saida[0]
        ok("§§secret(NOME)" in texto and "NÃO é falha" in texto and "/senha NOME valor" in texto, "como usar o cofre fica")
        ok("- IG: (sem descrição)" in texto and "cofre_descrever" in texto, "lista e como descrever")
        linha = next(l for l in texto.splitlines() if l.startswith("- GMAIL:"))
        ok(len(linha) <= len("- GMAIL: ") + ext.DESCRICAO_MAX and linha.endswith("…"), f"descrição longa cortada: {linha}")
        ok("captcha" not in texto.lower() and "nunca contorne" not in texto, "captcha só nas regras de sempre")
        ok(len(texto) < 1600, f"bloco curto ({len(texto)} caracteres sem a lista longa)")

    async def rodar(self, so=""):
        try:
            for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
                self._pasta_nova()
                try:
                    getattr(self, nome)()
                    self.resultados.append({"teste": nome, "ok": True})
                except Exception as exc:
                    self.resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                            "onde": traceback.format_exc().splitlines()[-3:]})
        finally:
            shutil.rmtree(getattr(self, "_tmp", ""), ignore_errors=True)
        return {"passou": sum(r["ok"] for r in self.resultados), "total": len(self.resultados),
                "resultados": self.resultados}


if __name__ == "__main__":
    import asyncio

    r = asyncio.run(Suite().rodar(sys.argv[1] if len(sys.argv) > 1 else ""))
    for x in r["resultados"]:
        print("ok   " if x["ok"] else "FALHA", x["teste"], x.get("erro", ""), *(x.get("onde") or []) if not x["ok"] else "")
    print("TESTES", r["passou"], r["total"])
