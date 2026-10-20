"""Tests of prompt_enxuto (no model calls; Agent Zero's modules are stubbed while the files load).
Run with implantar.py (staging copy), inside the container, or from the repository root:
python3 infra/operador/rodar_suites_locais.py prompt_enxuto"""

import asyncio
import copy
import importlib.util
import json
import re
import shutil
import sys
import tempfile
import traceback
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PLUGINS = RAIZ.parent
EXT = RAIZ / "extensions" / "python"


class Falha(AssertionError):
    pass


def ok(cond, msg):
    if not cond:
        raise Falha(msg)


def eq(a, b, msg):
    if a != b:
        raise Falha(f"{msg}: esperado {b!r}, veio {a!r}")


def _stubs() -> dict:
    agent = types.ModuleType("agent")
    agent.LoopData = type("LoopData", (), {})
    helpers = types.ModuleType("helpers")
    ext = types.ModuleType("helpers.extension")
    ext.Extension = type("Extension", (), {"__init__": lambda self, agent=None, **k: setattr(self, "agent", agent)})
    return {"agent": agent, "helpers": helpers, "helpers.extension": ext}


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


def _rodar(corrotina):
    """Run a coroutine that never really awaits, also from inside the suite runner's event loop."""
    try:
        corrotina.send(None)
    except StopIteration as fim:
        return fim.value
    raise Falha("a extensão esperou algo (não devia)")


def _ferramenta(nome, descricao, parametros=None):
    return {"type": "function", "name": nome, "strict": False, "description": descricao,
            "parameters": parametros or {"type": "object", "properties": {}, "additionalProperties": True}}


class Historico:
    def __init__(self):
        self.msgs = []  # [{"content", "summary"}]

    def output(self):
        return [{"ai": False, "content": m.get("summary") or m["content"]} for m in self.msgs]


class Agente:
    def __init__(self):
        self.history = Historico()

    def hist_add_message(self, ai, content):
        self.history.msgs.append({"content": content})


class Suite:
    def __init__(self):
        self.resultados = []
        self.tmp = Path(tempfile.mkdtemp(prefix="enxuto-teste-"))
        self.carregar = _carregar("prompt_enxuto_carregar", RAIZ / "helpers" / "carregar.py")
        self.e = self.carregar.modulo("enxuto")
        self.i = self.carregar.modulo("indice")
        self.e.DESLIGADO = self.tmp / "desligado"

    def _desligar(self, sim: bool):
        if sim:
            self.e.DESLIGADO.write_text("")
        else:
            self.e.DESLIGADO.unlink(missing_ok=True)

    # ------------------------------------------------------------------ tool list

    def t_lista_curta_mantem_nome_e_parametros(self):
        e, i = self.e, self.i
        longa = "### prospeccao\n" + "regra importante. " * 200
        schema = {"type": "object", "properties": {"acao": {"type": "string"}}, "additionalProperties": True}
        original = [_ferramenta("prospeccao", longa, schema), _ferramenta("desconhecida", "x" * 3000),
                    _ferramenta("wait", "pausa curta")]
        intacta = copy.deepcopy(original)
        manuais = {}
        nova = e.encurtar(original, i.CURTAS, i.MIN_GANHO, manuais)
        eq(original, intacta, "a lista original não é alterada (pode ser compartilhada)")
        eq([f["name"] for f in nova], ["prospeccao", "desconhecida", "wait"], "mesmas ferramentas, mesma ordem")
        eq(nova[0]["description"], i.CURTAS["prospeccao"], "descrição curta")
        eq(nova[0]["parameters"], schema, "parâmetros iguais")
        eq(manuais, {"prospeccao": longa}, "o texto inteiro vira o manual")
        eq(nova[1]["description"], "x" * 3000, "ferramenta fora do índice fica inteira")
        eq(nova[2]["description"], "pausa curta", "descrição que já é curta fica como está")

    def t_extensao_troca_a_lista_e_respeita_o_interruptor(self):
        m = _carregar("enxuto_lista_teste", EXT / "chat_model_call_before" / "_50_ferramentas_curtas.py")
        m.carregar = self.carregar
        longa = "### celular\n" + "detalhe. " * 300
        dados = {"a0_responses_function_tools": [_ferramenta("celular", longa)]}
        _rodar(m.FerramentasCurtas(agent=None).execute(call_data=dados))
        eq(dados["a0_responses_function_tools"][0]["description"], self.i.CURTAS["celular"], "lista curta na chamada")
        self._desligar(True)
        try:
            dados = {"a0_responses_function_tools": [_ferramenta("celular", longa)]}
            _rodar(m.FerramentasCurtas(agent=None).execute(call_data=dados))
            eq(dados["a0_responses_function_tools"][0]["description"], longa, "desligado: tudo como antes")
        finally:
            self._desligar(False)
        dados = {"messages": []}
        _rodar(m.FerramentasCurtas(agent=None).execute(call_data=dados))
        eq(dados, {"messages": []}, "chamada sem lista de ferramentas (utilitária) não muda")

    def t_indice_curto_e_com_as_acoes_de_cada_ferramenta(self):
        i = self.i
        for nome, curta in i.CURTAS.items():
            ok(len(curta) <= 420, f"{nome}: a linha curta passou de 420 caracteres ({len(curta)})")
        total = sum(len(c) for c in i.CURTAS.values()) // 4
        ok(total < 6500, f"o índice inteiro deve caber em ~6 mil tokens (deu ~{total})")
        # every action a plugin tool declares in its JSON schema is named in its short line
        for md in PLUGINS.glob("*/prompts/agent.system.tool.*.md"):
            texto = md.read_text(encoding="utf-8")
            nome = md.name[len("agent.system.tool."):-3]
            if nome not in i.CURTAS:
                continue
            m = re.search(r"Input schema for tool_args:\s*(\{.*\})", texto)
            if not m:
                continue
            try:
                enum = json.loads(m.group(1)).get("properties", {}).get("acao", {}).get("enum", [])
            except ValueError:
                continue
            faltam = [a for a in enum if a not in i.CURTAS[nome]]
            ok(not faltam, f"{nome}: ações sem menção na linha curta: {faltam}")
        ok("response" in i.SEM_MANUAL, "a resposta final nunca leva manual (vai para a pessoa como está)")

    def t_regras_de_seguranca_ficam_em_toda_chamada(self):
        m = _carregar("enxuto_regras_teste", EXT / "system_prompt" / "_12_regras_base.py")
        m.carregar = self.carregar
        saida = []
        _rodar(m.RegrasBase(agent=None).execute(system_prompt=saida))
        texto = saida[0]
        for palavra in ("pagar", "meio de pagamento", "termos legais", "terceiros", "apagar", "Captcha", "nunca resolva",
                        "§§secret(NOME)", "pedir_codigo", "nunca ordem", "laço de verificação", "manual completo"):
            ok(palavra in texto, f"regra sem «{palavra}»")
        self._desligar(True)
        try:
            saida = []
            _rodar(m.RegrasBase(agent=None).execute(system_prompt=saida))
            ok("manual completo" not in saida[0] and "Captcha" in saida[0], "desligado: sem a linha do manual, regras ficam")
        finally:
            self._desligar(False)

    # ------------------------------------------------------------------ manual on first use

    def _manual_ext(self):
        m = _carregar("enxuto_manual_teste", EXT / "_functions" / "agent" / "Agent" / "hist_add_tool_result" / "end"
                      / "_50_manual_na_primeira.py")
        m.carregar = self.carregar
        return m

    def t_manual_entra_uma_vez_e_volta_se_resumido(self):
        m, e = self._manual_ext(), self.e
        e.MANUAIS["celular"] = "Ações: ver, tocar... (texto completo)"
        a = Agente()
        a.history.msgs.append({"content": {"tool_name": "celular", "tool_result": "tela"}})

        def usou():
            m.ManualNaPrimeira(agent=a).execute(data={"args": (a, "celular", "tela"), "kwargs": {}, "exception": None})

        usou()
        eq(len(a.history.msgs), 2, "primeiro uso: o manual entra logo depois do resultado")
        ok("📘 Manual da ferramenta `celular`" in a.history.msgs[1]["content"]
           and "texto completo" in a.history.msgs[1]["content"], a.history.msgs[1])
        usou()
        eq(len(a.history.msgs), 2, "segundo uso: não repete")
        a.history.msgs[1]["summary"] = "resumo"
        usou()
        eq(len(a.history.msgs), 3, "o resumo levou o manual: ele volta")
        m.ManualNaPrimeira(agent=a).execute(data={"args": (a,), "kwargs": {"tool_name": "response"}, "exception": None})
        e.MANUAIS["response"] = "nunca"
        m.ManualNaPrimeira(agent=a).execute(data={"args": (a, "response", "oi"), "kwargs": {}, "exception": None})
        eq(len(a.history.msgs), 3, "resposta final nunca leva manual")
        m.ManualNaPrimeira(agent=a).execute(data={"args": (a, "sem_manual", "x"), "kwargs": {}, "exception": None})
        eq(len(a.history.msgs), 3, "ferramenta sem manual guardado: nada")

    def t_manual_desligado_ou_com_erro_nao_entra(self):
        m, e = self._manual_ext(), self.e
        e.MANUAIS["fios"] = "manual dos fios"
        a = Agente()
        self._desligar(True)
        try:
            m.ManualNaPrimeira(agent=a).execute(data={"args": (a, "fios", "ok"), "kwargs": {}, "exception": None})
            eq(len(a.history.msgs), 0, "desligado: nada")
        finally:
            self._desligar(False)
        m.ManualNaPrimeira(agent=a).execute(data={"args": (a, "fios", "ok"), "kwargs": {}, "exception": RuntimeError()})
        eq(len(a.history.msgs), 0, "a gravação do resultado falhou: nada")

    def t_manuais_sobrevivem_a_recarga(self):
        self.e.MANUAIS["livro"] = "manual do livro"
        self.e._mtime = -1  # as if the file changed (a deploy)
        novo = self.carregar.modulo("enxuto")
        ok(novo is not self.e and novo.MANUAIS.get("livro") == "manual do livro", "recarregar não perde os manuais")
        self.e = novo
        self.e.DESLIGADO = self.tmp / "desligado"

    async def rodar(self, filtro: str = ""):
        try:
            for nome in sorted(n for n in dir(self) if n.startswith("t_") and filtro in n):
                try:
                    getattr(self, nome)()
                    self.resultados.append({"teste": nome, "ok": True})
                except Exception as exc:
                    self.resultados.append({"teste": nome, "ok": False,
                                            "erro": f"{exc}\n{traceback.format_exc()[-600:]}"})
        finally:
            shutil.rmtree(self.tmp, ignore_errors=True)
        passou = sum(1 for r in self.resultados if r["ok"])
        return {"total": len(self.resultados), "passou": passou, "resultados": self.resultados}


if __name__ == "__main__":
    r = asyncio.run(Suite().rodar(sys.argv[1] if len(sys.argv) > 1 else ""))
    for x in r["resultados"]:
        print(("✓ " if x["ok"] else "✗ ") + x["teste"] + ("" if x["ok"] else f": {x['erro']}"))
    print(f"{r['passou']}/{r['total']}")
    sys.exit(0 if r["passou"] == r["total"] else 1)
