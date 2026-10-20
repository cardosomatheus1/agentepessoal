"""Tests of consultar_sol with the model calls mocked: no network, no Agent Zero. Run with implantar.py (staging copy)
or anywhere: python3 tests/suite.py"""

import asyncio
import importlib.util
import sys
import tempfile
import traceback
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


class Falha(AssertionError):
    pass


def eq(a, b, msg):
    if a != b:
        raise Falha(f"{msg}: esperado {b!r}, veio {a!r}")


def ok(cond, msg):
    if not cond:
        raise Falha(msg)


def _ferramenta():
    resposta = type("Response", (), {"__init__": lambda self, message="", break_loop=False: setattr(self, "message", message)})
    stub = {"helpers": types.ModuleType("helpers"), "helpers.tool": types.SimpleNamespace(Tool=object, Response=resposta)}
    antes = {k: sys.modules.get(k) for k in stub}
    sys.modules.update(stub)
    try:
        spec = importlib.util.spec_from_file_location("consultar_sol_teste", RAIZ / "tools" / "consultar_sol.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        for k, v in antes.items():
            sys.modules.pop(k, None) if v is None else sys.modules.__setitem__(k, v)


def _agente(modelo: str, ctx: str = "c1"):
    return types.SimpleNamespace(get_chat_model=lambda: types.SimpleNamespace(model_name=modelo),
                                 context=types.SimpleNamespace(id=ctx), history=types.SimpleNamespace(output=lambda: []))


class Suite:
    def __init__(self):
        self.resultados = []

    def t_haiku_pede_ao_sonnet_luna_ao_sol(self):
        # 20/10 (Matheus): Haiku gets the same help Luna gets from Sol, from Sonnet
        m = _ferramenta()
        eq(m.conselheiro(_agente("bedrock/converse/us.anthropic.claude-haiku-5-5")), "Sonnet", "Haiku → Sonnet")
        eq(m.conselheiro(_agente("openai.gpt-6-luna")), "Sol", "Luna → Sol")
        eq(m.conselheiro(types.SimpleNamespace(get_chat_model=lambda: 1 / 0)), "Sol", "modelo ilegível: como antes")

    def t_sonnet_recebe_o_caso_e_as_imagens(self):
        m = _ferramenta()
        pedidos = []

        def completar(**kw):
            pedidos.append(kw)
            msg = types.SimpleNamespace(content="1. **Recomendação:** siga.")
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])
        r = m._perguntar_sonnet("## Pergunta do agente\nposso?", ["QUJD"], completar=completar)
        eq(r, "1. **Recomendação:** siga.", "resposta do Sonnet")
        kw = pedidos[0]
        eq(kw["model"], "bedrock/converse/us.anthropic.claude-sonnet-5-5", "modelo")
        ok(kw["api_base"].endswith(":8787/bedrock"), "pelo proxy da VM (cache e cabeçalhos)")
        eq(kw["messages"][0], {"role": "system", "content": m.INSTRUCOES}, "as mesmas instruções do Sol")
        partes = kw["messages"][1]["content"]
        ok(partes[0]["text"].startswith("## Pergunta") and partes[1]["image_url"]["url"].endswith("QUJD"), partes)

    def t_erro_do_sonnet_volta_como_texto(self):
        m = _ferramenta()
        m.time = types.SimpleNamespace(sleep=lambda s: None, strftime=m.time.strftime)  # this module only, never the real time
        r = m._perguntar_sonnet("x", [], completar=lambda **kw: 1 / 0)
        ok(r.startswith("(erro ao consultar o Sonnet"), r)

    async def t_ferramenta_usa_o_conselheiro_da_conversa(self):
        m = _ferramenta()
        usados = []
        m._perguntar_sonnet = lambda t, i: usados.append("Sonnet") or "siga"
        m._perguntar = lambda t, i: usados.append("Sol") or "siga"
        with tempfile.TemporaryDirectory() as d:
            m.Path = lambda *a: Path(d).joinpath(*[str(x).lstrip("/") for x in a]) if a and str(a[0]).startswith("/a0") else Path(*a)
            for modelo, quem in (("converse/us.anthropic.claude-haiku-5-5", "Sonnet"), ("openai.gpt-6-luna", "Sol")):
                t = object.__new__(m.ConsultarSol)
                t.agent = _agente(modelo)
                async def progresso(texto):
                    pass
                t.set_progress = progresso
                r = await t.execute(pergunta="posso?", contexto="caso")
                ok(r.message.startswith(f"Conselho do {quem}"), r.message)
        eq(usados, ["Sonnet", "Sol"], "cada conversa pergunta ao seu conselheiro")

    async def rodar(self, so=""):
        for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
            try:
                feito = getattr(self, nome)()
                if asyncio.iscoroutine(feito):
                    await feito
                self.resultados.append({"teste": nome, "ok": True})
            except Exception as exc:
                self.resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                        "onde": traceback.format_exc().splitlines()[-3:]})
        return {"passou": sum(r["ok"] for r in self.resultados), "total": len(self.resultados),
                "resultados": self.resultados}


if __name__ == "__main__":
    r = asyncio.run(Suite().rodar(sys.argv[1] if len(sys.argv) > 1 else ""))
    for x in r["resultados"]:
        print("ok   " if x["ok"] else "FALHA", x["teste"], x.get("erro", ""), *(x.get("onde") or []) if not x["ok"] else "")
    print("TESTES", r["passou"], r["total"])
