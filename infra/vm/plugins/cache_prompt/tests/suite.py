"""Tests of cache_prompt (no model calls, no Agent Zero needed: its modules are stubbed while the files load).
Run with implantar.py (staging copy), inside the container, or from the repository root:
python3 infra/operador/rodar_suites_locais.py cache_prompt"""

import asyncio
import importlib.util
import json
import sys
import traceback
import types
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
EXT = RAIZ / "extensions" / "python" / "message_loop_prompts_after" / "_98_extras_no_historico.py"
TIRAR = RAIZ / "extensions" / "python" / "_functions" / "agent" / "Agent" / "prepare_prompt" / "end" / "_50_tirar_extras_vazio.py"


class Falha(AssertionError):
    pass


def ok(cond, msg):
    if not cond:
        raise Falha(msg)


def eq(a, b, msg):
    if a != b:
        raise Falha(f"{msg}: esperado {b!r}, veio {a!r}")


class LoopData:
    def __init__(self):
        self.extras_persistent, self.extras_temporary = {}, {}
        self.history_output = []
        self.params_temporary, self.params_persistent = {}, {}


def _stubs() -> dict:
    agent = types.ModuleType("agent")
    agent.LoopData = LoopData
    helpers = types.ModuleType("helpers")
    dj = types.ModuleType("helpers.dirty_json")
    dj.stringify = lambda v, separators=None: json.dumps(v, ensure_ascii=False, separators=separators)
    helpers.dirty_json = dj
    ext = types.ModuleType("helpers.extension")
    ext.Extension = type("Extension", (), {"__init__": lambda self, agent=None, **k: setattr(self, "agent", agent)})
    return {"agent": agent, "helpers": helpers, "helpers.dirty_json": dj, "helpers.extension": ext}


def _carregar(nome: str, arquivo: Path):
    stubs = _stubs()
    antes = {k: sys.modules.get(k) for k in stubs}
    sys.modules.update(stubs)
    try:
        spec = importlib.util.spec_from_file_location(nome, arquivo)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        for k, v in antes.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


class Msg:
    def __init__(self, content):
        self.id, self.content, self.summary = str(uuid.uuid4()), content, ""


class Historico:
    def __init__(self):
        self.msgs = []

    def all_messages(self):
        return list(self.msgs)

    def output(self):
        return [{"ai": False, "content": m.summary or m.content, "id": m.id} for m in self.msgs]


class Agente:
    def __init__(self):
        self.context = types.SimpleNamespace(id="ctxTESTE")
        self.data, self.history = {}, Historico()

    def get_data(self, k):
        return self.data.get(k)

    def set_data(self, k, v):
        self.data[k] = v

    def read_prompt(self, arquivo, **kw):
        return "[EXTRAS]\n" + kw["extras"]

    def hist_add_message(self, ai, content):
        m = Msg(content)
        self.history.msgs.append(m)
        return m


class Suite:
    def __init__(self):
        self.m = _carregar("cache_prompt_extras_teste", EXT)
        self.m.SWITCH = Path("/nao/existe/conversas.txt")  # no switch file = on everywhere
        self.resultados = []

    def _passo(self, agente, persistentes=None, temporarios=None):
        ld = LoopData()
        ld.extras_persistent.update(persistentes or {})
        ld.extras_temporary.update(temporarios or {})
        ld.history_output = agente.history.output()
        obj = self.m.ExtrasNoHistorico(agent=agente)
        _rodar(obj.execute(loop_data=ld))
        ok(not ld.extras_persistent and not ld.extras_temporary, "o bloco do fim fica vazio")
        return ld

    def t_so_o_que_mudou_entra_no_historico(self):
        a = Agente()
        self._passo(a, {"fios": "F1", "contexto_conversa": "C1"})
        eq(len(a.history.msgs), 1, "primeiro passo grava um bloco")
        ok('"fios":"F1"' in a.history.msgs[0].content and "C1" in a.history.msgs[0].content, a.history.msgs[0].content)
        self._passo(a, {"fios": "F1", "contexto_conversa": "C1"})
        eq(len(a.history.msgs), 1, "nada mudou: nada novo no histórico (o começo do prompt continua igual)")
        self._passo(a, {"fios": "F2", "contexto_conversa": "C1"})
        eq(len(a.history.msgs), 2, "mudou um: um bloco novo")
        ok("F2" in a.history.msgs[1].content and "C1" not in a.history.msgs[1].content, "só a chave que mudou vai")

    def t_chave_que_falta_num_passo_nao_volta_repetida(self):
        # memories are recalled every 3 steps: the key is missing in between and used to come back as "changed"
        a = Agente()
        self._passo(a, {"memories": "M1"}, {"current_datetime": "10:00"})
        self._passo(a, {}, {"current_datetime": "10:00"})
        self._passo(a, {"memories": "M1"}, {"current_datetime": "10:00"})
        eq(len(a.history.msgs), 1, "a mesma memória não é gravada de novo depois de um passo sem ela")

    def t_bloco_resumido_e_gravado_de_novo(self):
        a = Agente()
        self._passo(a, {"contexto_conversa": "objetivo: X"})
        self._passo(a, {"contexto_conversa": "objetivo: X"})
        eq(len(a.history.msgs), 1, "igual: não repete")
        a.history.msgs[0].summary = "resumo da conversa"  # history compression replaced it
        self._passo(a, {"contexto_conversa": "objetivo: X"})
        eq(len(a.history.msgs), 2, "o bloco que o resumo levou volta ao histórico")
        ok("objetivo: X" in a.history.msgs[1].content, "com o valor atual")
        a.history.msgs = a.history.msgs[1:]  # a whole topic summarized: its messages leave the output
        a.history.msgs.insert(0, Msg("resumo do tópico"))
        self._passo(a, {"contexto_conversa": "objetivo: X"})
        eq(len(a.history.msgs), 2, "ainda visível: não repete")

    def t_objetivo_vivo_volta_ao_fim_quando_fica_longe(self):
        a = Agente()
        self._passo(a, {"objetivo_vivo": "Pedido: X", "fios": "F1"})
        for i in range(self.m.REPETIR["objetivo_vivo"]):
            a.history.msgs.append(Msg(f"passo {i}"))
            self._passo(a, {"objetivo_vivo": "Pedido: X", "fios": "F1"})
        eq(len(a.history.msgs), 1 + self.m.REPETIR["objetivo_vivo"], "até N mensagens atrás: não repete")
        a.history.msgs.append(Msg("mais um passo"))
        self._passo(a, {"objetivo_vivo": "Pedido: X", "fios": "F1"})
        ultimo = a.history.msgs[-1].content
        ok("Pedido: X" in ultimo and "F1" not in ultimo, f"longe demais: só o objetivo volta ao fim: {ultimo}")
        antes = [m.content for m in a.history.msgs[:-1]]
        self._passo(a, {"objetivo_vivo": "Pedido: X", "fios": "F1"})
        eq([m.content for m in a.history.msgs[:-1]], antes, "só acrescenta no fim (o começo do prompt não muda)")
        eq(len(a.history.msgs), len(antes) + 1, "e logo depois não repete de novo")
        eq(self.m.longe({"x": "id"}, [{"id": "id"}] + [{"id": str(i)} for i in range(50)]), set(),
           "chave fora de REPETIR nunca repete por distância")

    def t_desligado_por_conversa(self):
        tmp = Path(__import__("tempfile").mkdtemp(prefix="cache-teste-"))
        try:
            (tmp / "conversas.txt").write_text("outra\n")
            self.m.SWITCH = tmp / "conversas.txt"
            a = Agente()
            ld = LoopData()
            ld.extras_persistent["fios"] = "F1"
            _rodar(self.m.ExtrasNoHistorico(agent=a).execute(loop_data=ld))
            eq(len(a.history.msgs), 0, "conversa fora da lista: nada muda")
            ok(ld.extras_persistent == {"fios": "F1"}, "e o bloco segue no fim, como no Agent Zero")
        finally:
            self.m.SWITCH = Path("/nao/existe/conversas.txt")
            __import__("shutil").rmtree(tmp, ignore_errors=True)

    def t_bloco_vazio_do_fim_sai(self):
        t = _carregar("cache_prompt_tirar_teste", TIRAR)
        eq(t._strip("[EXTRAS]\n{}"), None, "bloco vazio sozinho sai")
        eq(t._strip("ola\n[EXTRAS]\n{}"), "ola", "bloco vazio no fim sai")
        eq(t._strip("ola"), "ola", "texto sem bloco fica")

    async def rodar(self, filtro: str = ""):
        for nome in sorted(n for n in dir(self) if n.startswith("t_") and filtro in n):
            try:
                getattr(self, nome)()
                self.resultados.append({"teste": nome, "ok": True})
            except Exception as exc:
                self.resultados.append({"teste": nome, "ok": False, "erro": f"{exc}\n{traceback.format_exc()[-600:]}"})
        passou = sum(1 for r in self.resultados if r["ok"])
        return {"total": len(self.resultados), "passou": passou, "resultados": self.resultados}


def _rodar(corrotina):
    """Run a coroutine that never really awaits, also from inside the suite runner's event loop."""
    try:
        corrotina.send(None)
    except StopIteration as fim:
        return fim.value
    raise Falha("a extensão esperou algo (não devia)")


if __name__ == "__main__":
    r = asyncio.run(Suite().rodar(sys.argv[1] if len(sys.argv) > 1 else ""))
    for x in r["resultados"]:
        print(("✓ " if x["ok"] else "✗ ") + x["teste"] + ("" if x["ok"] else f": {x['erro']}"))
    print(f"{r['passou']}/{r['total']}")
    sys.exit(0 if r["passou"] == r["total"] else 1)
