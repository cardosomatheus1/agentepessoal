"""Tests of controle_agente that need no running agent. Run with implantar.py (staging copy) or from the repository
root: python3 infra/vm/plugins/controle_agente/tests/suite.py"""

import importlib.util
import sys
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


def _carregar(nome: str, arquivo: Path):
    spec = importlib.util.spec_from_file_location(nome, arquivo)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _extensao(nome: str, arquivo: Path):
    """Load an extension file; outside the container helpers.extension is a stand-in."""
    try:
        import helpers.extension  # noqa: F401  (inside the container)
    except Exception:
        sys.modules.setdefault("helpers", types.ModuleType("helpers"))
        ext = types.ModuleType("helpers.extension")

        class Extension:
            def __init__(self, agent=None, **kwargs):
                self.agent = agent
                self.kwargs = kwargs

        ext.Extension = Extension
        sys.modules["helpers.extension"] = ext
    return _carregar(nome, arquivo)


def _nova(cls, agent):
    """An extension instance for `agent`, whatever stand-in of helpers.extension another suite loaded first."""
    obj = cls.__new__(cls)
    obj.agent, obj.kwargs = agent, {}
    return obj


def _sincrono(coro):
    """Run an extension's execute() that never really waits (the suite itself already runs in an event loop)."""
    try:
        coro.send(None)
    except StopIteration as fim:
        return fim.value
    raise Falha("a extensão esperou algo de verdade")


EXT = RAIZ / "extensions" / "python"


class LogFalso:
    def __init__(self):
        self.guid, self.updates, self.itens = "log", [], []

    def log(self, **kw):
        self.itens.append(kw)
        self.updates.append(len(self.itens))


class Mensagem:
    def __init__(self, content):
        self.content, self.summary = content, ""


class HistoricoFalso:
    """Agent Zero's history: the current topic and older topics (a summarized topic shows only its summary)."""

    def __init__(self):
        self.current = types.SimpleNamespace(messages=[], summary="")
        self.topics = []

    def adicionar(self, content):
        m = Mensagem(content)
        self.current.messages.append(m)
        return m


def _agente(numero=0, nome_chat="conversa"):
    ctx = types.SimpleNamespace(id=f"ctx{numero}", name=nome_chat, log=LogFalso(), paused=False)
    return types.SimpleNamespace(number=numero, agent_name=f"A{numero}", context=ctx, data={},
                                 loop_data=types.SimpleNamespace(current_tool=None), history=HistoricoFalso())


def _familia_falsa():
    """familia.raiz() without Agent Zero: a helper's chat points at its parent's chat."""
    m = types.ModuleType("controle_agente_familia_v2")
    m.raiz = lambda ctx: getattr(ctx, "pai", None) or ctx
    sys.modules["controle_agente_familia_v2"] = m


class Suite:
    def __init__(self):
        self.resultados = []
        _familia_falsa()
        self.antes = _extensao("controle_contar_passo_teste", EXT / "tool_execute_before" / "_12_contar_passo.py")
        self.depois = _extensao("controle_guardas_teste", EXT / "tool_execute_after" / "_12_guardas.py")
        self.zerar = _extensao("controle_zerar_guardas_teste",
                               EXT / "_functions" / "agent" / "Agent" / "monologue" / "start" / "_15_zerar_guardas.py")
        base = EXT / "_functions" / "agent" / "Agent" / "hist_add_tool_result"
        self.hist_ini = _extensao("controle_resultado_repetido_teste", base / "start" / "_10_resultado_repetido.py")
        self.hist_fim = _extensao("controle_lembrar_resultado_teste", base / "end" / "_10_lembrar_resultado.py")
        self.g = self.depois.guardas

    def _passo(self, agent, tool, mensagem, args=None):
        """One step as Agent Zero runs it: tool_execute_before, the tool, tool_execute_after, then the history."""
        agent.data["_detector_loop_args"] = dict(args or {})
        _sincrono(_nova(self.antes.ContarPasso, agent).execute(tool_args=args or {}, tool_name=tool))
        resp = types.SimpleNamespace(message=mensagem, break_loop=False)
        _sincrono(_nova(self.depois.Guardas, agent).execute(response=resp, tool_name=tool))
        return resp

    def _historico(self, agent, tool, texto, item=None):
        """hist_add_tool_result with its start/end hooks; returns what went into the history."""
        agent.loop_data.current_tool = types.SimpleNamespace(name=tool)
        kw = {"id": "x"}
        if item is not None:
            kw["_responses_output_item"] = item
        data = {"args": (agent, tool, texto), "kwargs": kw, "result": None, "exception": None}
        _nova(self.hist_ini.ResultadoRepetido, agent).execute(data=data)
        final = data["kwargs"].get("tool_result", data["args"][2])
        data["result"] = agent.history.adicionar({"tool_name": tool, "tool_result": final})
        _nova(self.hist_fim.LembrarResultado, agent).execute(data=data)
        agent.loop_data.current_tool = None
        return final

    def t_falhou_reconhece_erros_das_ferramentas(self):
        g = self.g
        for erro in ("Error: no document provided", "Browser click failed: timeout", "ERROR: connection refused",
                     "error reading /tmp/x: file not found", "A2A chat error: boom", "Task not found: abc",
                     "Tool 'xyz' not found or could not be initialized.", "Task failed to update: abc",
                     g.CABECALHO + " dado⟧\nError: busca falhou"):
            ok(g.falhou("ferramenta", erro), f"é erro: {erro!r}")
        for bom in ('{"currentUrl": "https://x"}', "resultado: 3 linhas\nerror: só no meio do texto",
                    "Achei 5 perfis.", "", "Error: x"):
            ok(not g.falhou("response" if bom == "Error: x" else "browser", bom), f"não é erro: {bom!r}")

    def t_mesma_ferramenta_falhando_com_argumentos_diferentes(self):
        # the loop detector only catches the same arguments with the same result; a new selector each time slipped by
        a = _agente(0)
        r1 = self._passo(a, "browser", "Browser click failed: seletor #a", {"sel": "#a"})
        r2 = self._passo(a, "browser", "Browser click failed: seletor #b", {"sel": "#b"})
        self._passo(a, "search_engine", "Achei 3 resultados.")  # another tool in between does not reset it
        r3 = self._passo(a, "browser", "Browser click failed: seletor #c", {"sel": "#c"})
        ok("falhou" not in r1.message[30:] and "falhou" not in r2.message[30:], "1ª e 2ª falha: sem aviso")
        ok("falhou 3 vezes seguidas" in r3.message and "mude de abordagem" in r3.message, f"3ª: avisa: {r3.message!r}")
        ok(not r3.break_loop and not a.context.paused, "só avisa: a tarefa continua")
        ok([i["heading"] for i in a.context.log.itens] == ["Ferramenta falhando"], "o chat mostra uma vez")
        r4 = self._passo(a, "browser", "Browser click failed: seletor #d", {"sel": "#d"})
        ok("falhou 4 vezes seguidas" in r4.message, "continua avisando enquanto falhar")
        ok(len(a.context.log.itens) == 1, "sem encher o chat")
        self._passo(a, "browser", '{"currentUrl": "https://x"}')
        r6 = self._passo(a, "browser", "Browser click failed: seletor #e", {"sel": "#e"})
        ok("falhou" not in r6.message[30:], "um acerto da ferramenta zera a conta")
        b = _agente(0)
        for _ in range(3):
            r = self._passo(b, "browser", "Browser click failed: igual\n\n⚠️ ATENÇÃO: você já fez exatamente esta ação")
        ok(r.message.count("⚠️") == 1, "se o detector de loop já avisou (mesmos argumentos), não avisa de novo")

    def t_teto_de_passos_do_ajudante(self):
        # 11/10: a phone question went A0 → A7 with 175 steps and no answer
        g = self.g
        ok(g.teto(0) == 0 and g.teto(0, ["🎯 Prospecção — executar"]) == 0, "o agente principal (A0) não tem teto")
        ok(g.teto(1) == 40 and g.teto(2, ["conversa"]) == 40, "ajudante: 40")
        ok(g.teto(1, ["🎯 Prospecção — buscar"]) == g.TETO_PROSPECCAO > 100, "ajudante de rodada da prospecção: teto alto")
        a = _agente(1)
        _nova(self.zerar.ZerarGuardas, a).execute(data={})
        for passo in range(1, 32):
            r = self._passo(a, "search_engine", f"resultado {passo}")
            ok(r.message == f"resultado {passo}" and not r.break_loop, f"passo {passo}: nada")
        r = self._passo(a, "search_engine", "resultado 32")
        ok("Passo 32 de no máximo 40" in r.message and not r.break_loop, f"80%: avisa para fechar: {r.message!r}")
        for passo in range(33, 40):
            r = self._passo(a, "search_engine", f"resultado {passo}")
            ok(not r.break_loop and "⏳" not in r.message, f"passo {passo}: segue sem repetir o aviso")
        r = self._passo(a, "search_engine", "resultado 40")
        ok(r.break_loop and "parado no teto de 40 passos" in r.message and "resultado 40" in r.message,
           f"no teto, para e devolve o que tem a quem chamou: {r.message!r}")
        ok(any(i["heading"] == "Ajudante parado no teto de passos" for i in a.context.log.itens), "o chat mostra")
        _nova(self.zerar.ZerarGuardas, a).execute(data={})
        ok(not self._passo(a, "search_engine", "nova tarefa").break_loop, "tarefa nova (novo monólogo) começa do zero")
        principal = _agente(0)
        for _ in range(60):
            r = self._passo(principal, "search_engine", "x")
        ok(not r.break_loop and "⏳" not in r.message, "o A0 nunca é parado por passos")
        rodada = _agente(0, "🎯 Prospecção — executar")
        ajudante = _agente(1)
        ajudante.context.pai = rodada.context
        for _ in range(45):
            r = self._passo(ajudante, "browser", '{"ok": 1}')
        ok(not r.break_loop, "ajudante da rodada da prospecção passa de 40")

    def t_resultado_repetido_vira_referencia_no_historico(self):
        g = self.g
        a = _agente(0)
        _nova(self.zerar.ZerarGuardas, a).execute(data={})
        pagina = "Perfil @zen.marmitas\n" + "linha da página\n" * 60
        self._passo(a, "browser", pagina, {"action": "content"})
        h1 = self._historico(a, "browser", pagina)
        ok(h1 == pagina, "a primeira vez entra inteira")
        self._passo(a, "search_engine", "outra coisa")
        self._historico(a, "search_engine", "outra coisa")
        self._passo(a, "browser", pagina, {"action": "content"})
        antes = [m.content for m in a.history.current.messages]
        item = {"type": "function_call_output", "call_id": "c3", "output": pagina}
        h3 = self._historico(a, "browser", pagina + "\n\n⚠️ ATENÇÃO: você já fez exatamente esta ação", item)
        ok(h3.startswith("[igual ao resultado do passo 1 (2 passos atrás)") and "browser" in h3,
           f"repetido vira referência ao passo: {h3[:120]!r}")
        ok(h3.endswith("⚠️ ATENÇÃO: você já fez exatamente esta ação"), "o aviso do detector continua visível")
        ok(item["output"] == h3, "o resultado nativo (modelos Responses) leva o mesmo texto")
        ok([m.content for m in a.history.current.messages][:len(antes)] == antes,
           "itens anteriores do histórico intactos: o começo do prompt não muda (cache)")
        curto = "ok, salvo."
        self._historico(a, "text_editor", curto)
        ok(self._historico(a, "text_editor", curto) == curto, "resultado curto (< 512) não é trocado")
        erro = "Error: " + "x" * 600
        self._historico(a, "browser", erro)
        ok(self._historico(a, "browser", erro) == erro, "erro repetido não é trocado")
        b = _agente(0)
        self._historico(b, "browser", pagina)
        b.history.current.messages[0].summary = "resumido"
        ok(self._historico(b, "browser", pagina) == pagina, "se o original foi resumido, o repetido entra inteiro")
        ok(self._historico(b, "browser", pagina).startswith("[igual ao resultado"), "e passa a ser a nova referência")
        c = _agente(0)
        self._historico(c, "browser", pagina)
        c.history.topics, c.history.current = [c.history.current], types.SimpleNamespace(messages=[], summary="")
        c.history.topics[0].summary = "tópico resumido"
        ok(self._historico(c, "browser", pagina) == pagina, "tópico antigo resumido também não serve de referência")
        d = _agente(0)
        self._historico(d, "browser", pagina)
        _nova(self.zerar.ZerarGuardas, d).execute(data={})
        ok(self._historico(d, "browser", pagina) == pagina, "tarefa nova: o passo N de antes não vale")
        e = _agente(0)
        self._historico(e, "browser", pagina)
        data = {"args": (e, "call_subordinate", pagina), "kwargs": {}, "result": None, "exception": None}
        _nova(self.hist_ini.ResultadoRepetido, e).execute(data=data)  # no tool running: an answer handed up
        ok(data["args"][2] == pagina, "fora de um passo de ferramenta não mexe")


    def t_clique_em_referencia_que_sumiu(self):
        c = _carregar("controle_clique_teste", RAIZ / "helpers" / "clique.py")
        erro = ('Browser click failed: Page.evaluate: BrowserPageContentReferenceError: Browser page content could not find '
                'reference "button 21".')
        ok(c.dica("browser", erro), "o clique que falhou ganha a saída")
        ok(c.dica("browser", 'BrowserDomHelperSelectorError: Browser DOM helper could not resolve selector "x"'), "seletor também")
        ok(not c.dica("browser", "clicked"), "clique que deu certo: nada")
        ok(not c.dica("code_execution_tool", erro), "só no navegador")
        ok(not c.dica("browser", erro + c.DICA), "não repete a dica")
        ext = (RAIZ / "extensions" / "python" / "tool_execute_after" / "_11_clique_que_sumiu.py").read_text(encoding="utf-8")
        ok("clique.dica(" in ext, "a extensão usa a regra")

    def t_delegacoes_seguidas_sem_falar_com_a_pessoa(self):
        # 18/10: ~33 helper calls in 4 h with no answer or notify_user; Matheus repeated "Continua…?" four times
        g = self.g
        a0 = _agente(0)
        for i in range(1, 3):
            r = self._passo(a0, "call_subordinate", f"resultado {i}", {"message": "parte", "reset": "true"})
            ok("Delegação nº" not in r.message, f"{i}ª delegação ainda sem aviso")
        r = self._passo(a0, "call_subordinate", "resultado 3", {"message": "parte"})
        ok("⚠️ Delegação nº 3 seguida" in r.message and "notify_user" in r.message, "3ª delegação seguida avisa")
        ok(r.message.startswith("resultado 3"), "o resultado do ajudante continua inteiro")
        ok(any(i.get("heading") == "Delegações sem falar com a pessoa" for i in a0.context.log.itens), "registra no log")
        ok(not r.break_loop, "só avisa: a tarefa continua")
        r = self._passo(a0, "code_execution_tool", "ok", {"code": "ls"})
        ok("Delegação nº" not in r.message, "ferramenta comum não recebe o aviso")
        r = self._passo(a0, "parallel", "resultado 4", {"tool_calls": [{"tool_name": "call_subordinate", "tool_args": {}}]})
        ok("Delegação nº 4" in r.message, "parallel com ajudante conta")
        self._passo(a0, "notify_user", "enviado", {"message": "estado"})
        r = self._passo(a0, "call_subordinate", "resultado 5", {"message": "parte"})
        ok("Delegação nº" not in r.message and a0.data["_guardas_delegacoes"] == 1, "notify_user zera a contagem")
        r = self._passo(a0, "parallel", "x", {"tool_calls": [{"tool_name": "search_engine", "tool_args": {}}]})
        ok(a0.data["_guardas_delegacoes"] == 1, "parallel sem ajudante não conta")
        a1 = _agente(1)
        for i in range(4):
            r = self._passo(a1, "call_subordinate", "r", {"message": "x"})
        ok("Delegação nº" not in r.message and "_guardas_delegacoes" not in a1.data, "ajudante (A1) não é contado")
        ok(g.Delegacoes("lixo").n == 0 and g.Delegacoes(None).registrar("response", {}) == 0, "valor torto vira zero")
        ok(g.separar("x" + g.aviso_delegacoes(3))[1].startswith("\n\n⚠️ Delegação nº 3"), "aviso fica visível após stub")
        zerar = (EXT / "_functions" / "agent" / "Agent" / "monologue" / "start" / "_15_zerar_guardas.py").read_text(encoding="utf-8")
        ok("_guardas_delegacoes" in zerar, "nova tarefa (monólogo) zera a contagem")

    def t_rodada_agendada_recebe_aviso_para_fechar(self):
        # 20/10: rounds that found nothing ran up to 120 steps; the main agent of a round gets a nudge, never a stop
        g, m = self.g, self.depois
        antes = m.tarefas_da_rodada
        try:
            m.tarefas_da_rodada = lambda agent: ["🔎 Radar e fios soltos"]
            a0 = _agente(0, "🔎 Radar (Gmail e Agenda)")
            _nova(self.zerar.ZerarGuardas, a0).execute(data={})
            for passo in range(1, 30):
                r = self._passo(a0, "code_execution_tool", "ok")
                ok("⏳ Rodada" not in r.message, f"passo {passo}: nada")
            r = self._passo(a0, "code_execution_tool", "ok")
            ok("⏳ Rodada agendada no passo 30" in r.message and not r.break_loop, f"passo 30 avisa: {r.message!r}")
            for _ in range(9):
                r = self._passo(a0, "code_execution_tool", "ok")
            ok("⏳" not in r.message, "não repete a cada passo")
            r = self._passo(a0, "code_execution_tool", "ok")
            ok("passo 40" in r.message and not r.break_loop, "repete a cada 10, sem parar a rodada")
            m.tarefas_da_rodada = lambda agent: ["🎯 Prospecção — executar"]
            p = _agente(0, "🎯 Prospecção — executar")
            for _ in range(119):
                r = self._passo(p, "browser", "ok")
                ok("⏳ Rodada" not in r.message, "prospecção navega muito de propósito")
            ok("⏳ Rodada agendada no passo 120" in self._passo(p, "browser", "ok").message, "prospecção: aviso no 120")
            m.tarefas_da_rodada = lambda agent: []
            c = _agente(0)
            for _ in range(60):
                r = self._passo(c, "search_engine", "x")
            ok("⏳" not in r.message and not r.break_loop, "conversa com a pessoa: nada")
            eq(g.aviso_rodada(29, ["x"]), "", "antes do limite, nada")
        finally:
            m.tarefas_da_rodada = antes

    def t_regras_de_sempre_num_lugar_so(self):
        # 20/10 (prompt enxuto): the goal-mode list and "stop at the 2nd repeat" live in prompt_enxuto; here only a pointer
        texto = (EXT / "system_prompt" / "_18_sem_loops.py").read_text(encoding="utf-8")
        regras = texto.split('REGRAS = """', 1)[1].split('"""', 1)[0]
        ok("Regras que valem sempre" in regras, "aponta para as regras de sempre")
        for repetida in ("aceitar termos legais", "pagamento ou forma de pagamento", "pela 2ª vez sem avanço"):
            ok(repetida not in regras, f"não repete «{repetida}»")
        for fica in ("analisar_imagens", "nunca coloque `browser`", "reset: true", "consultar_sol", "blocked"):
            ok(fica in regras, f"o que é só daqui fica: «{fica}»")

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


if __name__ == "__main__":
    import asyncio
    r = asyncio.run(Suite().rodar())
    print(f"{r['passou']}/{r['total']}")
