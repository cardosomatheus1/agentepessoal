"""Tests of the Tarefas board (temporary folders only; never the live register). Run with implantar.py or locally."""

import datetime as dt
import importlib.util
import json
import os
import tempfile
import time
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
LOGIN = "teste_quadro"


class Falha(AssertionError):
    pass


def ok(cond, msg):
    if not cond:
        raise Falha(msg)


def eq(a, b, msg):
    if a != b:
        raise Falha(f"{msg}: esperado {b!r}, veio {a!r}")


def _modulo():
    tmp = Path(tempfile.mkdtemp(prefix="quadro-teste-"))
    # next to this plugin in the repository; in the VM's staging copy (alone in its folder), the installed plugins
    os.environ["QUADRO_PLUGINS"] = str(RAIZ.parent if (RAIZ.parent / "fios_soltos").exists() else Path("/a0/usr/plugins"))
    os.environ["QUADRO_TAREFAS"] = str(tmp / "tasks.json")
    os.environ["QUADRO_OBJETIVOS"] = str(tmp / "goals")
    spec = importlib.util.spec_from_file_location("quadro_teste", RAIZ / "helpers" / "quadro.py")
    q = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(q)
    q.fios().PASTA = tmp / "fios"
    return q, tmp


class Suite:
    def __init__(self):
        self.resultados = []

    def t_colunas_do_quadro(self):
        # 22/10 (Claude Duet's Tasks tab): Ativas, A conferir, Próximas, Resolvidas, Agendadas
        q, tmp = _modulo()
        f = q.fios()
        f.mesclar(LOGIN, [{"titulo": "Responder a Diana", "dono": "agente", "prioridade": "baixa"},
                          {"titulo": "Assinar o contrato", "dono": "você", "prioridade": "alta", "prazo": "2026-10-24"},
                          {"titulo": "Cobrar o fornecedor"}, {"titulo": "Montar o painel de vendas"},
                          {"titulo": "Pagar o boleto"}])
        ids = {x["titulo"]: x["id"] for x in f.carregar(LOGIN)["fios"]}
        f.adiar(LOGIN, ids["Cobrar o fornecedor"], 3)
        eq(f.para_conferir(LOGIN, [ids["Montar o painel de vendas"]], "painel pronto na pasta Agente"), 1, "agente diz que fez")
        f.concluir(LOGIN, ids["Pagar o boleto"], "teste")
        b = q.montar(LOGIN)
        eq([c["titulo"] for c in b["ativas"]], ["Assinar o contrato", "Responder a Diana"], "ativas, a urgente primeiro")
        eq([c["titulo"] for c in b["conferir"]], ["Montar o painel de vendas"], "a conferir")
        eq(b["conferir"][0]["nota"], "painel pronto na pasta Agente", "com o que ele fez")
        eq([c["titulo"] for c in b["proximas"]], ["Cobrar o fornecedor"], "adiada vai para próximas")
        eq([c["titulo"] for c in b["resolvidas"]], ["Pagar o boleto"], "resolvidas")
        amanha3 = time.time() + 4 * 86400
        eq([c["titulo"] for c in q.montar(LOGIN, amanha3)["proximas"]], [], "adiada que venceu volta às ativas")

    def t_agendadas_e_quando(self):
        q, tmp = _modulo()
        eq(q.quando({"minute": "45", "hour": "7", "day": "*", "weekday": "*"}), "todo dia 07:45", "todo dia")
        eq(q.quando({"minute": "52", "hour": "8", "day": "*", "weekday": "1"}), "seg 08:52", "segunda")
        eq(q.quando({"minute": "0", "hour": "9", "day": "*", "weekday": "1-5"}), "seg a sex 09:00", "dias úteis")
        eq(q.quando({"minute": "7", "hour": "9", "day": "1", "weekday": "*"}), "dia 1 09:07", "mensal")
        eq(q.quando({"minute": "40", "hour": "8,13,18", "day": "*", "weekday": "*"}), "todo dia 08:40, 13:40, 18:40", "várias")
        (tmp / "tasks.json").write_text(json.dumps({"tasks": [
            {"name": "📰 Resumo do dia", "state": "idle", "schedule": {"minute": "45", "hour": "7"},
             "last_run": "2026-10-22T10:45:00Z", "last_result": "Bom dia!\nNada que precise de você."},
            {"name": "Velha", "state": "disabled", "schedule": {"minute": "0", "hour": "1"}},
            {"name": "Avulsa", "state": "idle"}]}), encoding="utf-8")
        a = q.agendadas()
        eq([x["nome"] for x in a], ["📰 Resumo do dia"], "só as ligadas e com horário")
        eq((a[0]["quando"], a[0]["ultima"]), ("todo dia 07:45", "22/10 07:45"), "quando e última (Bahia)")
        ok("\n" not in a[0]["resultado"], "resultado numa linha")
        (tmp / "tasks.json").write_text("{quebrado", encoding="utf-8")
        eq(q.agendadas(), [], "arquivo ilegível: lista vazia, nunca erro")

    def t_fazer_pra_mim_texto(self):
        q, _ = _modulo()
        t = q.texto_fazer({"id": "ab12", "titulo": "Cobrar a Diana", "proximo_passo": "rascunhar a cobrança"})
        ok("ab12" in t and "rascunhar a cobrança" in t and "eu confiro e fecho" in t and "aprovação" in t, t)

    def t_api_so_le_e_usa_os_fios(self):
        api = (RAIZ / "api" / "quadro.py").read_text(encoding="utf-8")
        ok("f.concluir(" in api and "f.reabrir(" in api and "_nova_conversa(" in api, "ações pelo registro de fios")
        for proibido in ("open(", "write_text", "json.dump"):
            ok(proibido not in api, f"a API não escreve arquivos por conta própria ({proibido})")

    async def rodar(self, so: str = "") -> dict:
        for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
            try:
                getattr(self, nome)()
                self.resultados.append({"teste": nome, "ok": True})
            except Exception as exc:
                self.resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                        "onde": traceback.format_exc()[-600:]})
        passou = sum(1 for r in self.resultados if r["ok"])
        return {"passou": passou, "total": len(self.resultados), "resultados": self.resultados}
