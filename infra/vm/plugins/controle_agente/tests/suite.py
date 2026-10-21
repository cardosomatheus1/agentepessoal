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

    def t_detector_de_laco_com_os_limites_do_hermes(self):
        det = _extensao("controle_detector_laco_teste", EXT / "tool_execute_after" / "_10_detector_loop.py")
        laco = det.laco

        def agente(numero=0, tarefa=False):
            a = _agente(numero)
            a.get_data, a.set_data = a.data.get, a.data.__setitem__
            texto = "## Task\nrodada" if tarefa else "faz isso pra mim"
            a.last_user_message = types.SimpleNamespace(content={"user_message": texto})
            return a

        def passo(a, tool, args, msg="mesmo resultado"):
            a.data["_detector_loop_args"] = dict(args)
            r = types.SimpleNamespace(message=msg, break_loop=False)
            _sincrono(_nova(det.DetectorLoop, a).execute(response=r, tool_name=tool))
            return r

        ok(laco.consulta("browser", {"action": "content"}) and laco.consulta("code_execution_tool", {"runtime": "output"}),
           "ler a página e a saída do comando são consultas")
        ok(not laco.consulta("browser", {"action": "click"}), "clicar é ação")
        # conversa com a pessoa: ação repetida avisa na 2ª e só pausa na 8ª
        a = agente()
        clique = {"action": "click", "ref": 5}
        rs = [passo(a, "browser", clique) for _ in range(7)]
        ok("⚠️" in rs[1].message and not a.context.paused, "2ª: avisa, segue")
        ok(not a.context.paused, "até a 7ª a conversa não pausa")
        passo(a, "browser", clique)
        ok(a.context.paused, "8ª: pausa")
        # rodada agendada (ninguém olhando): pausa na 5ª
        b = agente(tarefa=True)
        for _ in range(5):
            passo(b, "browser", clique)
        ok(b.context.paused, "rodada: pausa na 5ª")
        # reler a página esperando carregar: sem aviso até a 5ª e nunca pausa na conversa
        c = agente()
        leituras = [passo(c, "browser", {"action": "content"}) for _ in range(14)]
        ok("⚠️" not in leituras[3].message and "⚠️" in leituras[4].message, "consulta: avisa só na 5ª")
        ok(not c.context.paused, "consulta na conversa nunca pausa")
        # ciclo A,B,A,B
        d = agente()
        passo(d, "browser", {"action": "click", "ref": 1}, "a")
        passo(d, "browser", {"action": "click", "ref": 2}, "b")
        passo(d, "browser", {"action": "click", "ref": 1}, "a2")
        passo(d, "browser", {"action": "click", "ref": 2}, "b2")
        passo(d, "browser", {"action": "click", "ref": 1}, "a2")
        r = passo(d, "browser", {"action": "click", "ref": 2}, "b2")
        ok("🔁" in r.message or "⚠️" in r.message, f"vaivém é avisado: {r.message!r}")
        ok(laco.ciclo(["x", "a", "b", "a", "b"]) and not laco.ciclo(["a", "a", "a", "a"]), "ciclo só com passos diferentes")

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


    def t_argumentos_embrulhados_duas_vezes(self):
        a = _carregar("controle_argumentos_teste", RAIZ / "helpers" / "argumentos.py")
        # 21/10, 99Food: every click went in like this and the browser only reported its state
        args = {"tool_name": "browser", "tool_args": {"action": "click", "browser_id": 37, "x": 137, "y": 148}}
        mesmo = args
        ok(a.desembrulhar("browser", args), "desembrulha")
        ok(args is mesmo and args == {"action": "click", "browser_id": 37, "x": 137, "y": 148},
           "no mesmo dicionário que chega à ferramenta")
        tres = {"tool_args": {"tool_name": "browser", "tool_args": {"action": "type", "ref": 2, "text": "x"}}}
        ok(a.desembrulhar("browser", tres) and tres == {"action": "type", "ref": 2, "text": "x"}, "duas camadas")
        normal = {"action": "content", "browser_id": 37}
        ok(not a.desembrulhar("browser", normal) and normal == {"action": "content", "browser_id": 37}, "normal fica")
        outro = {"tool_name": "code_execution_tool", "tool_args": {"code": "1"}}
        ok(not a.desembrulhar("browser", outro), "nome de outra ferramenta dentro: não mexe")
        mistura = {"tool_name": "browser", "tool_args": {"action": "click"}, "ref": 3}
        ok(not a.desembrulhar("browser", mistura), "argumento de verdade junto: não mexe")
        ok(not a.desembrulhar("browser", None), "sem argumentos")
        ext = (RAIZ / "extensions" / "python" / "tool_execute_before" / "_05_desembrulhar.py").read_text(encoding="utf-8")
        ok("argumentos.desembrulhar(" in ext, "a extensão usa a regra")
        rolar = {"action": "wheel", "browser_id": 37, "x": 340, "y": 560, "deltaY": 200}
        ok(a.nomes_do_navegador("browser", rolar) and rolar == {"action": "wheel", "browser_id": 37, "x": 340, "y": 560,
                                                                "delta_y": 200}, "deltaY vira delta_y (rolava 0 px)")
        ambos = {"deltaY": 1, "delta_y": 2}
        ok(not a.nomes_do_navegador("browser", ambos) and ambos == {"deltaY": 1, "delta_y": 2}, "não sobrescreve")
        outra = {"deltaY": 1}
        ok(not a.nomes_do_navegador("code_execution_tool", outra) and outra == {"deltaY": 1}, "só no navegador")
        ok("nomes_do_navegador(" in ext, "a extensão troca os nomes")

    def t_argumento_desconhecido_nao_executa(self):
        # Hermes Agent's validation, ported: what the tool does not take is an error, not silently dropped
        a = _carregar("controle_argumentos_teste2", RAIZ / "helpers" / "argumentos.py")

        class Navegador:
            async def execute(self, action: str = "", ref=None, delta_y: float = 0.0, **kwargs):
                modo = kwargs.get("clipboard_action") or kwargs.get("operation")
                return modo

        nomes = a.aceitos(Navegador.execute)
        eq(nomes, {"action", "ref", "delta_y", "clipboard_action", "operation"}, "assinatura + o que o corpo lê")
        erro = a.conferir("browser", {"action": "scroll", "ref": 3, "direction": "down"}, nomes)
        ok("NÃO foi executada" in erro and "'direction'" in erro and "delta_y" in erro, "erro com os nomes aceitos")
        ok("você quis dizer 'delta_y'" in a.conferir("browser", {"deltay": 1}, nomes), "sugere o nome parecido")
        eq(a.conferir("browser", {"action": "click", "ref": 2, "thoughts": ["x"]}, nomes), "", "chamada certa passa")

        class Repassa:
            async def execute(self, **kwargs):
                return await outro(**kwargs)  # noqa: F821

        class LeArgs:
            async def execute(self, **kwargs):
                a = self.args
                return a

        class SoKwargs:
            async def execute(self, **kwargs):
                return self.args.get("code"), self.args["runtime"]

        eq(a.aceitos(Repassa.execute), None, "repassa kwargs: não dá para saber, não bloqueia")
        eq(a.aceitos(LeArgs.execute), None, "self.args usado de outro jeito: não bloqueia")
        eq(a.aceitos(SoKwargs.execute), {"code", "runtime"}, "nomes lidos de self.args contam")
        eq(a.conferir("x", {"qualquer": 1}, None), "", "sem lista: passa (como o Hermes, falha aberto)")
        ext = (RAIZ / "extensions" / "python" / "tool_execute_before" / "_05_desembrulhar.py").read_text(encoding="utf-8")
        ok("RepairableException(erro)" in ext and "argumentos.conferir(" in ext, "a extensão barra a chamada")

    def t_ferramenta_vai_ao_modelo_com_os_parametros(self):
        # 21/10: in native mode the browser went to the model with an empty schema, so it guessed names
        a = _carregar("controle_argumentos_teste3", RAIZ / "helpers" / "argumentos.py")
        fonte = (
            "from helpers.tool import Tool\n"
            "class Navegador(Tool):\n"
            "    async def execute(self, action: str = '', ref: int | str | None = None, x: float = 0.0,\n"
            "                      selectors: list[str] | None = None, **kwargs):\n"
            "        return kwargs.get('operation')\n")
        e = a.esquema(fonte)
        eq(e["additionalProperties"], False, "só os parâmetros de verdade")
        eq(e["properties"]["action"], {"type": "string"}, "tipo simples vai")
        eq(e["properties"]["x"], {"type": "number"}, "número")
        eq(e["properties"]["ref"], {}, "união: sem tipo, aceita qualquer")
        ok("operation" in e["properties"], "o que o corpo lê também vai")
        eq(a.esquema("class T:\n    async def execute(self, **kwargs):\n        return run(**kwargs)\n"), None,
           "não dá para saber: fica o do Agent Zero")
        eq(a.esquema("isto não é python ("), None, "arquivo quebrado: nada")
        ext = (RAIZ / "extensions" / "python" / "agent_init" / "_25_esquema_das_ferramentas.py").read_text(encoding="utf-8")
        ok("base.get(\"properties\")" in ext and "argumentos.esquema(" in ext, "só troca o esquema vazio")

    def t_clique_em_referencia_que_sumiu(self):
        c = _carregar("controle_clique_teste", RAIZ / "helpers" / "clique.py")
        erro = ('Browser click failed: Page.evaluate: BrowserPageContentReferenceError: Browser page content could not find '
                'reference "button 21".')
        ok(c.dica("browser", erro), "o clique que falhou ganha a saída")
        d = c.dica("browser", 'Browser click failed: click could not resolve selector "button[aria-label=\'Next\']" to a browser ref')
        ok("não mudou" in d and "mudou depois" not in d, f"seletor: dica certa, não 'a página mudou': {d}")
        ok(not c.dica("browser", "clicked"), "clique que deu certo: nada")
        ok(not c.dica("code_execution_tool", erro), "só no navegador")
        ok(not c.dica("browser", erro + c.DICA), "não repete a dica")
        ext = (RAIZ / "extensions" / "python" / "tool_execute_after" / "_11_clique_que_sumiu.py").read_text(encoding="utf-8")
        ok("clique.dica(" in ext, "a extensão usa a regra")
        # catálogo de erros do OpenClaw (toAIFriendlyError): cada falha vira o próximo passo
        casos = {
            "Browser click failed: strict mode violation: locator('input') resolved to 3 elements": "mais de um",
            "Browser click failed: <div class=\"cookie\">…</div> intercepts pointer events": "por cima",
            "Browser type failed: Element is not an <input>, <textarea> or [contenteditable] element": "não aceita texto",
            "Browser click failed: element is not enabled": "desativado",
            "Browser type failed: Cannot type text into input[type=number]": "formato",
            "Browser upload_file failed: Browser ref '8' does not resolve to a file input": "upload_file",
            "Browser click failed: Timeout 30000ms exceeded.": "Esperou",
            "Browser select failed: Browser page content cannot select options on <div>.": "não é um <select>",
            'Browser click failed: cannot resolve point for helper-backed reference "12".': "iframe",
        }
        for erro, trecho in casos.items():
            d = c.dica("browser", erro)
            ok(trecho in d, f"{erro[:50]}… → {d!r}")
        ok(not c.dica("browser", "Browser click ok"), "sem falha: nada")
        ok(not c.dica("browser", "Browser click failed: x" + c.OUTROS[0][1]), "não repete dica nenhuma")

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
