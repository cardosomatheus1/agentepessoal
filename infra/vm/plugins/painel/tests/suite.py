"""Tests of the live panel with temporary folders (never /a0/usr/painel, /a0/usr/prospeccao or /a0/usr/conteudo) and
fake readers. The real read functions of prospeccao and conteudo are called on temporary copies of their data. Run
with implantar.py or: python3 infra/vm/plugins/painel/tests/suite.py"""

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
# the staging copy on the VM runs alone in /tmp: the other plugins are then the live ones
PLUGINS = RAIZ.parent if (RAIZ.parent / "prospeccao").exists() else Path("/a0/usr/plugins")


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


AGORA = 1_791_000_000.0


class Suite:
    def __init__(self):
        self.resultados = []

    def _painel(self):
        self.tmp = tempfile.mkdtemp(prefix="painel_teste_")
        os.environ["PAINEL_PASTA"], os.environ["PAINEL_PLUGINS"] = self.tmp, str(PLUGINS)
        try:
            return _carregar("painel_teste", RAIZ / "helpers" / "painel.py")
        finally:
            os.environ.pop("PAINEL_PASTA", None)
            os.environ.pop("PAINEL_PLUGINS", None)

    @staticmethod
    def _leitores(**falhar):
        chamadas = []

        def leitor(nome, valor):
            def ler(login):
                chamadas.append(nome)
                if falhar.get(nome):
                    raise RuntimeError(f"{nome} fora do ar")
                return valor
            return ler
        return {"funil": leitor("funil", {"proposto": 2, "lead": 1, "demo": 0, "teste": 0}),
                "agenda": leitor("agenda", {"dias": [], "vazios": []}),
                "desempenho": leitor("desempenho", {"ok": True, "posts": [], "total": {}})}, chamadas

    def t_guarda_cada_fonte_com_a_hora(self):
        p = self._painel()
        try:
            leitores, chamadas = self._leitores()
            p.atualizar("matheus", leitores, AGORA)
            d = p.ler("matheus")
            eq(sorted(d["fontes"]), ["agenda", "desempenho", "funil"], "o Matheus tem as três fontes")
            eq(d["fontes"]["funil"]["valor"]["proposto"], 2, "o valor lido")
            eq(d["fontes"]["funil"]["lido_as"], p.hora(AGORA), "a hora de cada leitura, pronta para mostrar")
            ok(d["fontes"]["funil"]["lido_as"] and not d["fontes"]["funil"]["desatualizado"], "lido e em dia")
            p.atualizar("teste_painel", leitores, AGORA)
            eq(sorted(p.ler("teste_painel")["fontes"]), ["funil"], "outro login: só a prospecção dele (a agenda é da @raiz.connect)")
            eq(p.ler("ninguem"), None, "sem painel ainda")
        finally:
            shutil.rmtree(self.tmp, ignore_errors=True)

    def t_fonte_que_falha_fica_com_o_ultimo_bom(self):
        p = self._painel()
        try:
            bons, _ = self._leitores()
            p.atualizar("matheus", bons, AGORA)
            ruins, _ = self._leitores(desempenho=True, funil=True)
            p.atualizar("matheus", ruins, AGORA + 4 * 3600)
            d = p.ler("matheus")
            f = d["fontes"]["funil"]
            eq(f["valor"]["proposto"], 2, "o último valor bom continua")
            ok(f["desatualizado"] and "fora do ar" in f["erro"], "marcado desatualizado, com o erro")
            eq((f["lido_as"], f["falhou_as"]), (p.hora(AGORA), p.hora(AGORA + 4 * 3600)), "a hora da leitura boa e a da falha")
            ok(not d["fontes"]["agenda"]["desatualizado"], "a fonte que leu fica em dia")
            eq(p.devidas(json.loads(Path(p._arq("matheus")).read_text()), "matheus", AGORA + 4 * 3600 + 60), [],
               "falhou agora: não insiste no mesmo minuto")
            p.atualizar("matheus", bons, AGORA + 4 * 3600 + p.NOVA_TENTATIVA)
            ok(not p.ler("matheus")["fontes"]["desempenho"]["desatualizado"], "voltou: em dia de novo")
        finally:
            shutil.rmtree(self.tmp, ignore_errors=True)

    async def t_job_leve_so_le_o_que_venceu(self):
        p = self._painel()
        try:
            leitores, chamadas = self._leitores()
            p.atualizar("matheus", leitores, AGORA)
            chamadas.clear()
            p.atualizar("matheus", leitores, AGORA + 60)
            eq(chamadas, [], "1 min depois: nada vence")
            p.atualizar("matheus", leitores, AGORA + 11 * 60)
            eq(sorted(chamadas), ["agenda", "funil"], "10 min: funil e agenda; desempenho (Meta) só a cada 3 h")
            antes = Path(p._arq("matheus")).stat().st_mtime_ns
            p.atualizar("matheus", leitores, AGORA + 12 * 60)
            eq(Path(p._arq("matheus")).stat().st_mtime_ns, antes, "nada vencido: o arquivo nem é regravado")
            # the job extension: one pass at a time, in a thread
            stub = {"helpers": types.ModuleType("helpers"), "helpers.extension": types.ModuleType("helpers.extension")}
            stub["helpers.extension"].Extension = type("Extension", (), {"__init__": lambda s, agent=None, **k: setattr(s, "agent", agent)})
            antes_mods = {n: sys.modules.get(n) for n in stub}
            sys.modules.update(stub)
            try:
                job = _carregar("painel_job_teste", RAIZ / "extensions/python/job_loop/_47_painel.py")
            finally:
                for n, m in antes_mods.items():
                    sys.modules.pop(n, None) if m is None else sys.modules.__setitem__(n, m)
            passos = []
            falso = types.SimpleNamespace(ESTADO={"rodando": False}, passo=lambda: (passos.append(1), time.sleep(0.2)))
            job.painel = lambda: falso
            import asyncio

            await job.AtualizarPainel(None).execute()
            await job.AtualizarPainel(None).execute()
            await asyncio.sleep(0.4)
            eq((passos, falso.ESTADO["rodando"]), ([1], False), "uma passada por vez, e a trava se solta no fim")
        finally:
            shutil.rmtree(self.tmp, ignore_errors=True)

    def t_le_pelas_funcoes_da_prospeccao_e_do_conteudo(self):
        p = self._painel()
        dados = tempfile.mkdtemp(prefix="painel_fontes_")
        try:
            pr = p._modulo("painel_prospeccao", PLUGINS / "prospeccao" / "helpers" / "prospeccao.py")
            pr.PASTA = Path(dados)
            lead = lambda i, etapa: {"id": f"l{i}", "handle": f"loja{i}", "etapa": etapa, "canal": "instagram",  # noqa: E731
                                     "historico": [], "criado": AGORA, "atualizado": AGORA}
            (Path(dados) / "teste_painel.json").write_text(json.dumps({
                "leads": [lead(1, "lead"), lead(2, "lead"), lead(3, "demo"), lead(4, "teste"), lead(5, "aquecido")],
                "acoes": [{"id": "a1", "lead_id": "l5", "tipo": "dm_abertura", "estado": "proposta", "criada": AGORA},
                          {"id": "a2", "lead_id": "l5", "tipo": "aquecer", "estado": "executada", "criada": AGORA}],
                "config": {}, "bloqueio_ate": 0}), encoding="utf-8")
            f = p.ler_funil("teste_painel")
            eq({k: f[k] for k in ("proposto", "lead", "demo", "teste")}, {"proposto": 1, "lead": 2, "demo": 1, "teste": 1},
               "proposto, lead, demo e teste pela prospecção")
            ok(f["resumo"].startswith("Funil"), f"a linha do funil do /painel: {f['resumo']!r}")
            os.environ["CONTEUDO_PASTA"] = dados
            try:
                c = p._conteudo()
            finally:
                os.environ.pop("CONTEUDO_PASTA", None)
            c.PASTA = Path(dados)
            a = p.ler_agenda("matheus")
            eq((len(a["dias"]), len(a["vazios"])), (7, 7), "agenda: 7 dias, todos vazios sem posts")
            c.api_do_cofre = lambda login="matheus": None
            try:
                p.ler_desempenho("matheus")
                raise Falha("sem token deveria falhar (e o painel marcar desatualizado)")
            except RuntimeError as exc:
                ok("token" in str(exc), "sem token: falha com o motivo")
            c.api_do_cofre = lambda login="matheus": object()
            c.desempenho = lambda api, dias: {"ok": False, "erro": "permissão negada"}
            try:
                p.ler_desempenho("matheus")
                raise Falha("erro da Meta deveria falhar")
            except RuntimeError as exc:
                ok("permissão" in str(exc), "erro da Meta não vira painel vazio")
        finally:
            shutil.rmtree(self.tmp, ignore_errors=True)
            shutil.rmtree(dados, ignore_errors=True)
            sys.modules.pop("painel_prospeccao", None)
            sys.modules.pop("painel_conteudo", None)

    async def t_ninguem_edita_pelo_painel(self):
        p = self._painel()
        try:
            leitores, _ = self._leitores()
            p.atualizar("matheus", leitores, AGORA)
            arq = Path(p._arq("matheus"))
            antes = arq.read_bytes()
            stub = {"helpers": types.ModuleType("helpers"), "helpers.api": types.ModuleType("helpers.api")}
            stub["helpers.api"].ApiHandler, stub["helpers.api"].Request, stub["helpers.api"].Response = object, object, object
            antes_mods = {n: sys.modules.get(n) for n in [*stub, "painel_helper"]}
            sys.modules.update(stub)
            try:
                api = _carregar("painel_api_teste", RAIZ / "api" / "painel.py")
                api.painel = lambda: p
                r = await api.Painel().process({"acao": "apagar", "fontes": {}, "funil": {"lead": 99}}, None)
            finally:
                for n, m in antes_mods.items():
                    sys.modules.pop(n, None) if m is None else sys.modules.__setitem__(n, m)
            eq(r["painel"]["fontes"]["funil"]["valor"]["lead"], 1, "a API só devolve o que está salvo")
            eq(arq.read_bytes(), antes, "o que vem no pedido não muda nada")
            pagina = (RAIZ / "webui" / "main.html").read_text(encoding="utf-8")
            ok("<button" not in pagina and "<input" not in pagina and "<select" not in pagina, "a página não tem botão nem campo")
            ok(set(__import__("re").findall(r"sendJsonData\('([^']+)'", pagina)) == {"/plugins/painel/painel"},
               "a página só chama a leitura do painel")
        finally:
            shutil.rmtree(self.tmp, ignore_errors=True)

    async def rodar(self, so=""):
        for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
            try:
                r = getattr(self, nome)()
                if hasattr(r, "__await__"):
                    await r
                self.resultados.append({"teste": nome, "ok": True})
            except Exception as exc:
                self.resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                        "onde": traceback.format_exc().splitlines()[-3:]})
        return {"passou": sum(r["ok"] for r in self.resultados), "total": len(self.resultados),
                "resultados": self.resultados}


if __name__ == "__main__":
    import asyncio

    r = asyncio.run(Suite().rodar(sys.argv[1] if len(sys.argv) > 1 else ""))
    for x in r["resultados"]:
        print("ok   " if x["ok"] else "FALHA", x["teste"], x.get("erro", ""), *(x.get("onde") or []) if not x["ok"] else "")
    print("TESTES", r["passou"], r["total"])
