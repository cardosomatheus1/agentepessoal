"""Tests of prompt_enxuto (no model calls; Agent Zero's modules are stubbed while the files load).
Run with implantar.py (staging copy), inside the container, or from the repository root:
python3 infra/operador/rodar_suites_locais.py prompt_enxuto"""

import asyncio
import copy
import gzip
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
# the repository's plugins; in implantar.py's staging copy (/tmp/estagio-prompt_enxuto) the VM's installed ones
PLUGINS = RAIZ.parent if (RAIZ.parent / "conectores").is_dir() else Path("/a0/usr/plugins")
EXT = RAIZ / "extensions" / "python"
# Agent Zero's own tool prompts (rendered outside the agent, e3051fb = the VM's version) and its tools/MCP templates
FIXTURE = RAIZ / "tests" / "prompts_agent_zero_20out.json.gz"
# measured on the VM on 20/10 (a request of Matheus's chat to Sonnet, text mode): 281,509 characters of system prompt,
# 77,296 in "## available tools" and 164,823 in the MCP section; the rest (instructions, rules, decisions, the
# "Sobre" sheet, memory, vault, skills…) was 39,390
RESTO_MEDIDO = 39390
META_TEXTO = 80000


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


class Modelo:
    def __init__(self, modo):
        self.kwargs = {"a0_api_mode": modo}


class _Transporte:
    """helpers.litellm_transport.TransportMode, as Agent Zero has it (any value but responses* = chat)."""
    RESPONSES, CHAT = "responses", "chat"

    @classmethod
    def from_value(cls, valor):
        return cls.RESPONSES if str(valor or "").lower().strip() in {"response", "responses", "responses_api"} else cls.CHAT


def com_transporte(funcao):
    """Run `funcao` with Agent Zero's transport module importable (outside the container it is not)."""
    modulo = types.ModuleType("helpers.litellm_transport")
    modulo.TransportMode = _Transporte
    antes = {k: sys.modules.get(k) for k in ("helpers", "helpers.litellm_transport")}
    if antes["helpers"] is None:
        sys.modules["helpers"] = types.ModuleType("helpers")
    sys.modules["helpers.litellm_transport"] = modulo
    try:
        return funcao()
    finally:
        for k, v in antes.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def partes_reais() -> list[tuple[str, str]]:
    """The tool prompts of a chat of Matheus's, in Agent Zero's order: its own (fixture) and this repository's
    plugins, sorted by file name, plus the vision block at the end."""
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as f:
        dados = json.load(f)
    proprias = [tuple(x) for x in dados["ferramentas"]]
    visao = [x for x in proprias if x[0] == "vision_load"]
    arquivos = {a: p for a, p in proprias if a != "vision_load"}
    for md in PLUGINS.glob("*/prompts/agent.system.tool.*.md"):
        arquivos[md.name] = md.read_text(encoding="utf-8").rstrip("\n")
    return sorted(arquivos.items()) + visao, dados


def secao_texto(partes, dados) -> str:
    """The tools section as Agent Zero's system_prompt/_11_tools_prompt.build_prompt writes it."""
    comuns = [p for a, p in partes if a != "vision_load"]
    visao = [p for a, p in partes if a == "vision_load"]
    texto = dados["agent.system.tools.md"].replace("{{tools}}", "\n\n".join(comuns)).rstrip("\n")
    return texto + ("\n\n" + visao[0] if visao else "")


class Historico:
    def __init__(self):
        self.msgs = []  # [{"content", "summary"}]

    def output(self):
        return [{"ai": False, "content": m.get("summary") or m["content"]} for m in self.msgs]


class Agente:
    def __init__(self, modo="responses"):
        self.history = Historico()
        self.modo = modo

    def get_chat_model(self):
        return Modelo(self.modo)

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

    # ------------------------------------------------------------------ tools on demand (21/10)

    def _sd(self):
        sd = self.carregar.modulo("sob_demanda")
        sd.DESLIGADO = self.tmp / "sem_sob_demanda"
        return sd

    def _lista_mista(self):
        eventos = {"type": "object", "properties": {"time_min": {"type": "string"}, "time_max": {"type": "string"}},
                   "required": ["time_min"]}
        return [_ferramenta("response", "Resposta final."), _ferramenta("browser", "Navegador."),
                _ferramenta("google_get_events_82f4960e", "Lists events from the user's calendar. Supports ranges.",
                            eventos),
                _ferramenta("assistir_video", "Assiste um vídeo inteiro e descreve com os tempos. `url`."),
                _ferramenta("ferramentas_extras", "As ferramentas fora desta lista.")]

    def t_sob_demanda_separa_nucleo_e_catalogo_estavel(self):
        sd = self._sd()
        original = self._lista_mista()
        intacta = copy.deepcopy(original)
        lista, ocultas = sd.separar(original)
        eq(original, intacta, "a lista original não é alterada")
        eq([f["name"] for f in lista], ["response", "browser", "ferramentas_extras"], "só o núcleo e a ponte na lista")
        eq(sorted(ocultas), ["assistir_video", "google_get_events_82f4960e"], "o resto fica atrás da ponte")
        final = sd.com_ponte(lista, ocultas)
        ponte = final[-1]["description"]
        ok("google_get_events_82f4960e(time_min)" in ponte, f"catálogo com nome e obrigatórios: {ponte}")
        ok("assistir_video()" in ponte and ponte.index("assistir_video") < ponte.index("google_"),
           "ferramentas soltas antes dos conectores")
        eq(sd.com_ponte(*sd.separar(self._lista_mista())), final, "mesma lista a cada chamada (cache do prompt)")
        sem_ponte = [f for f in self._lista_mista() if f["name"] != "ferramentas_extras"]
        eq(sd.separar(sem_ponte), (sem_ponte, {}), "sem a ponte na lista nada se esconde (ficaria inalcançável)")
        for nome in ("response", "pedir_codigo", "whatsapp_guardar_token", "decisao", "prospeccao", "tarefa_limite"):
            ok(sd.visivel(nome), f"{nome} fica sempre na lista (resposta final, fluxos de segurança, rotinas)")

    def t_sob_demanda_acha_pelo_nome_aproximado_e_por_palavras(self):
        sd = self._sd()
        _, ocultas = sd.separar(self._lista_mista())
        for pedido in ("google_get_events_82f4960e", "google_get_events", "google.get_events", "Google-Get-Events",
                       "google_get_event"):
            eq(sd.resolver(ocultas, pedido), "google_get_events_82f4960e", f"resolver {pedido!r}")
        eq(sd.resolver(ocultas, "apagar_tudo"), "", "nome sem parecida não vira outra ferramenta")
        eq(sd.buscar(ocultas, "calendar events")[0], "google_get_events_82f4960e", "busca por palavras da descrição")
        eq(sd.buscar(ocultas, "vídeo")[0], "assistir_video", "busca em português")
        eq(sd.buscar(ocultas, ""), [], "busca vazia")
        sem_obrig = {"parameters": {"type": "object", "properties": {"time_min": {}, "time_max": {}, "calendar_id": {},
                                                                     "max_results": {}}}, "description": "Eventos."}
        ok(sd.linha("google_get_events_x", sem_obrig).startswith("- google_get_events_x(time_min?, time_max?, calendar_id?)"),
           "sem obrigatório: os primeiros opcionais com '?' (o modelo não chuta o nome)")
        eq(sd.args_validos(ocultas["google_get_events_82f4960e"], {}), "faltam os argumentos obrigatórios: time_min",
           "obrigatório que falta é dito pelo nome")
        eq(sd.args_validos(ocultas["google_get_events_82f4960e"], {"time_min": "x"}), "", "argumentos completos")
        ok(sd.args_validos(ocultas["assistir_video"], "url") != "", "args que não é objeto é recusado")

    def t_sob_demanda_extensao_guarda_as_ocultas_e_respeita_o_interruptor(self):
        sd = self._sd()
        m = _carregar("enxuto_lista_teste2", EXT / "chat_model_call_before" / "_50_ferramentas_curtas.py")
        m.carregar = self.carregar
        ativas = []
        agente = types.SimpleNamespace(dados={"responses_tool_name_map": {"google_get_events_82f4960e": "google.get_events"}},
                                       context=types.SimpleNamespace(get_data=lambda k: ativas if k == "conectores_ativas" else None))
        agente.set_data = lambda k, v: agente.dados.__setitem__(k, v)
        agente.get_data = lambda k: agente.dados.get(k)
        dados = {"a0_responses_function_tools": self._lista_mista()}
        _rodar(m.FerramentasCurtas(agent=agente).execute(call_data=dados))
        eq([f["name"] for f in dados["a0_responses_function_tools"]], ["response", "browser", "ferramentas_extras"],
           "lista do modelo só com o núcleo")
        eq(sorted(agente.dados[sd.CHAVE]), ["assistir_video", "google_get_events_82f4960e"], "ocultas guardadas no agente")
        ativas.append("google.get_events")  # the conectores plugin activated it in this chat
        dados = {"a0_responses_function_tools": self._lista_mista()}
        _rodar(m.FerramentasCurtas(agent=agente).execute(call_data=dados))
        ok("google_get_events_82f4960e" in [f["name"] for f in dados["a0_responses_function_tools"]],
           "ferramenta de conector ativada na conversa fica na lista (senão ativa e continua sem ver: loop do Gmail)")
        eq(sorted(agente.dados[sd.CHAVE]), ["assistir_video"], "e sai do catálogo")
        sd.DESLIGADO.write_text("")
        try:
            dados = {"a0_responses_function_tools": self._lista_mista()}
            _rodar(m.FerramentasCurtas(agent=agente).execute(call_data=dados))
            eq(len(dados["a0_responses_function_tools"]), 5, "interruptor: todas as ferramentas na lista de novo")
        finally:
            sd.DESLIGADO.unlink(missing_ok=True)

    def _ponte(self, ferramentas: dict, chamadas: list):
        """The bridge tool loaded with Agent Zero's modules stubbed; `ferramentas` = {original name: callable(args)}."""
        class Response:
            def __init__(self, message, break_loop, additional=None):
                self.message, self.break_loop, self.additional = message, break_loop, additional

        class Tool:
            def __init__(self, agent=None, name="", method=None, args=None, message="", loop_data=None, **k):
                self.agent, self.name, self.args, self.message, self.loop_data = agent, name, args, message, loop_data

        class Unknown(Tool):
            pass

        async def call_extensions_async(ponto, agente, **kw):
            chamadas.append((ponto, kw.get("tool_name")))

        stubs = {"agent": types.ModuleType("agent"), "helpers": types.ModuleType("helpers"), "helpers.tool": types.ModuleType("helpers.tool"),
                 "helpers.extension": types.ModuleType("helpers.extension"),
                 "helpers.responses_tools": types.ModuleType("helpers.responses_tools"),
                 "helpers.mcp_handler": types.ModuleType("helpers.mcp_handler")}
        stubs["helpers.tool"].Response, stubs["helpers.tool"].Tool = Response, Tool
        stubs["helpers.extension"].call_extensions_async = call_extensions_async
        stubs["helpers.responses_tools"].original_tool_name = lambda n, mapa: (mapa or {}).get(n, n)

        class _MCP:
            @staticmethod
            def get_instance():
                return types.SimpleNamespace(get_tool=lambda agente, nome: None)

        stubs["helpers.mcp_handler"].MCPConfig = _MCP
        antes = {k: sys.modules.get(k) for k in stubs}
        sys.modules.update(stubs)

        def get_tool(name, method, args, message, loop_data):
            if name not in ferramentas:
                return Unknown(name=name)
            t = Tool(name=name)

            async def execute(**a):
                return Response(ferramentas[name](a), False, {"_responses_output_item": {"x": 1}})
            t.execute = execute
            return t

        sd = self._sd()
        _, ocultas = sd.separar(self._lista_mista())
        class Agente:
            DATA_NAME_RESPONSES_TOOL_NAME_MAP = "responses_tool_name_map"

            def __init__(self):
                self.dados = {sd.CHAVE: ocultas,
                              "responses_tool_name_map": {"google_get_events_82f4960e": "google.get_events"}}
                self.get_tool = get_tool

            def get_data(self, k):
                return self.dados.get(k)

        agente = Agente()
        spec = importlib.util.spec_from_file_location("ferramentas_extras_teste", RAIZ / "tools" / "ferramentas_extras.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._carregar = lambda: self.carregar
        ponte = m.FerramentasExtras(agent=agente, name="ferramentas_extras", args={}, message="", loop_data=None)
        return ponte, antes

    def _soltar(self, antes):
        for k, v in antes.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    def t_ponte_usar_roda_a_ferramenta_com_as_conferencias(self):
        chamadas = []
        ponte, antes = self._ponte({"google.get_events": lambda a: f"3 eventos desde {a['time_min']}"}, chamadas)
        try:
            r = _rodar(ponte.execute(acao="usar", nome="google_get_events", args={"time_min": "2026-10-22"}))
            eq(r.message, "[google.get_events] 3 eventos desde 2026-10-22", "roda pelo nome original do conector")
            eq(r.break_loop, False, "a tarefa continua")
            eq(r.additional, None, "o item nativo da ferramenta de dentro não vaza (o da ponte é o que vale)")
            eq(chamadas, [("tool_execute_before", "google.get_events"), ("tool_execute_after", "google.get_events")],
               "as conferências veem a ferramenta real")
            r = _rodar(ponte.execute(acao="usar", nome="google_get_events", args='{"time_min": "x"}'))
            ok(r.message.endswith("desde x"), "args em texto JSON também serve")
            chamadas.clear()
            r = _rodar(ponte.execute(acao="usar", nome="google_get_events", args={}))
            ok("time_min" in r.message and "Parâmetros" in r.message, f"falta argumento: diz qual e mostra a ficha: {r.message}")
            eq(chamadas, [], "sem argumento obrigatório não roda")
            r = _rodar(ponte.execute(acao="usar", nome="apagar_tudo", args={}))
            ok("não existe" in r.message, "nome desconhecido não roda outra coisa")
            r = _rodar(ponte.execute(acao="usar", nome="assistir_video", args={"url": "u"}))
            ok("não carregou" in r.message, "ferramenta que não carrega: avisa em vez de quebrar")
            # inside Agent Zero's `parallel` tool: a fresh worker agent, the catalog comes from the parent chat
            pai = ponte.agent
            trabalhador = type(pai)()
            trabalhador.dados = {}
            trabalhador.context = types.SimpleNamespace(get_data=lambda k: "PAI" if k == "_parallel_parent_context_id" else None)
            sys.modules["agent"] = types.SimpleNamespace(AgentContext=types.SimpleNamespace(
                get=lambda cid: types.SimpleNamespace(agent0=pai) if cid == "PAI" else None))
            ponte.agent = trabalhador
            chamadas.clear()
            r = _rodar(ponte.execute(acao="usar", nome="google_get_events", args={"time_min": "x"}))
            eq(r.message, "[google.get_events] 3 eventos desde x", "no trabalhador da `parallel`: catálogo e nomes do pai")
        finally:
            self._soltar(antes)

    def t_ponte_buscar_mostra_manual_e_parametros(self):
        self.e.MANUAIS["assistir_video"] = "### assistir_video\nManual inteiro com as regras."
        ponte, antes = self._ponte({}, [])
        try:
            r = _rodar(ponte.execute(acao="buscar", texto="vídeo"))
            ok("Manual inteiro com as regras." in r.message, "a busca traz o manual completo")
            ok("Parâmetros (JSON Schema)" in r.message, "e os parâmetros")
            r = _rodar(ponte.execute(acao="buscar", texto="zzzz"))
            ok("assistir_video" in r.message and "google_get_events_82f4960e" in r.message,
               "busca sem resultado lista as disponíveis")
        finally:
            self._soltar(antes)
            self.e.MANUAIS.pop("assistir_video", None)

    def t_pasta_de_trabalho_uma_linha_fixa(self):
        projeto = {"nome": ""}
        cfg = {"workdir_show": True, "workdir_path": "/a0/usr/workdir"}
        stubs = {"agent": types.ModuleType("agent"), "helpers": types.ModuleType("helpers"),
                 "helpers.extension": types.ModuleType("helpers.extension"),
                 "helpers.projects": types.ModuleType("helpers.projects"),
                 "helpers.settings": types.ModuleType("helpers.settings")}
        stubs["agent"].LoopData = type("LoopData", (), {})
        stubs["helpers.extension"].Extension = type(
            "Extension", (), {"__init__": lambda self, agent=None, **k: setattr(self, "agent", agent)})
        stubs["helpers.projects"].get_context_project_name = lambda ctx: projeto["nome"]
        stubs["helpers.settings"].get_settings_for_prompt = lambda: cfg
        stubs["helpers"].projects, stubs["helpers"].settings = stubs["helpers.projects"], stubs["helpers.settings"]
        antes = {k: sys.modules.get(k) for k in stubs}
        sys.modules.update(stubs)
        try:
            arq = EXT / "message_loop_prompts_after" / "_75_include_workdir_extras.py"
            spec = importlib.util.spec_from_file_location("enxuto_workdir_teste", arq)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            agente = types.SimpleNamespace(context=types.SimpleNamespace(id="c"))

            def passo():
                ld = types.SimpleNamespace(extras_temporary={})
                _rodar(m.IncludeWorkdirExtras(agent=agente).execute(loop_data=ld))
                return ld.extras_temporary
            um, dois = passo(), passo()
            eq(um, dois, "a mesma linha a cada passo (o cache_prompt manda uma vez só)")
            texto = um["project_file_structure"]
            ok("/a0/usr/workdir" in texto and "ls" in texto and len(texto) < 300, f"uma linha com a pasta: {texto}")
            cfg["workdir_show"] = False
            eq(passo(), {}, "com workdir_show desligado nas configurações: nada, como no Agent Zero")
            projeto["nome"] = "raiz"
            chamado = []

            async def nucleo(self, ld):
                chamado.append(True)
            m.IncludeWorkdirExtras._nucleo = nucleo
            passo()
            eq(chamado, [True], "dentro de um projeto, o comportamento do Agent Zero fica")
        finally:
            for k, v in antes.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
        for raiz in (Path("/a0"), Path("/home/user/src/agent-zero")):
            nucleo = raiz / "extensions" / "python" / "message_loop_prompts_after" / "_75_include_workdir_extras.py"
            if nucleo.exists():
                import hashlib
                eq(hashlib.md5(nucleo.read_bytes()).hexdigest(), "ca5fb21762e53e5130fd46a4c0784496",
                   "o arquivo do núcleo que este substitui mudou: revise a substituição")
                break

    def t_indice_curto_e_com_as_acoes_de_cada_ferramenta(self):
        i = self.i
        for nome, curta in i.CURTAS.items():
            teto = 1000 if nome == "prospeccao" else 420  # the rounds' tool: every action and the core rules stay listed
            ok(len(curta) <= teto, f"{nome}: a linha curta passou de {teto} caracteres ({len(curta)})")
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
                        "§§secret(NOME)", "pedir_codigo", "nunca ordem", "laço de verificação", "manual completo",
                        "Insista até terminar", "3 caminhos", "por ferramenta", "leia de volta", "sem \"corrigir\"",
                        "não é resposta"):
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

    # ------------------------------------------------------------------ text mode (tools written into the system prompt)

    def t_texto_uma_linha_por_ferramenta_e_manual_guardado(self):
        e, i = self.e, self.i
        partes, dados = partes_reais()
        secao = secao_texto(partes, dados)
        ok(len(secao) > 70000, f"a seção de ferramentas cheia media ~77 mil caracteres na VM (deu {len(secao)})")
        manuais = {}
        nova = e.encurtar_texto(secao, partes, i.CURTAS, i.MIN_GANHO, manuais)
        ok(len(nova) < 16000, f"seção de ferramentas curta até ~16 mil (deu {len(nova)})")
        ok(nova.startswith(dados["agent.system.tools.md"].split("{{tools}}")[0]), "o cabeçalho de Agent Zero fica")
        for nome in ("prospeccao", "code_execution_tool", "salvar_rotina", "call_subordinate", "parallel",
                     "conversa_externa", "memory_load", "memory_forget", "vision_load", "response"):
            ok(e.linha_texto(nome, i.CURTAS[nome]) in nova, f"{nome}: a linha curta do índice")
            ok(nome in manuais, f"{nome}: o texto inteiro vira o manual")
        ok(manuais["prospeccao"] == dict(partes)["agent.system.tool.prospeccao.md"], "manual = o prompt inteiro")
        ok("Input schema for tool_args" not in nova.split("### conector", 1)[0], "nada do texto inteiro antes do conector")
        conector = dict(partes)["agent.system.tool.conector.md"]
        ok(conector in nova and "conector" not in manuais, "ferramenta fora do índice fica inteira")
        eq(e.encurtar_texto(secao, partes, i.CURTAS, i.MIN_GANHO, {}), nova, "montada duas vezes: igual (cache)")
        # a prompt that is not in the section exactly (changed since) stays whole; the others still change
        mexido = secao.replace("### celular", "### celular ", 1)
        outra = e.encurtar_texto(mexido, partes, i.CURTAS, i.MIN_GANHO, {})
        ok("### celular \n" in outra and e.linha_texto("prospeccao", i.CURTAS["prospeccao"]) in outra, "só a mexida fica")
        eq(e.encurtar_texto("## skills", partes, i.CURTAS, i.MIN_GANHO, {}), "## skills", "texto sem ferramentas: igual")
        print(f"prompt_enxuto: seção de ferramentas do prompt de texto {len(secao)} -> {len(nova)} caracteres")

    def _ext_texto(self):
        m = _carregar("enxuto_texto_teste", EXT / "message_loop_prompts_after" / "_20_ferramentas_curtas_texto.py")
        m.carregar = self.carregar
        return m

    def _rodar_texto(self, agente, sistema, partes):
        dados = types.SimpleNamespace(system=list(sistema))
        original = self.e.partes_das_ferramentas
        self.e.partes_das_ferramentas = lambda agent: partes
        try:
            com_transporte(lambda: _rodar(self._ext_texto().FerramentasCurtasTexto(agent=agente).execute(loop_data=dados)))
        finally:
            self.e.partes_das_ferramentas = original
        return dados.system

    def t_texto_extensao_so_no_modo_texto(self):
        partes, dados = partes_reais()
        secao = secao_texto(partes, dados)
        sistema = ["# Agent Zero System Manual", secao, "## Regras que valem sempre", "## Sobre Matheus"]
        texto = self._rodar_texto(Agente("chat"), sistema, partes)
        ok(len(texto[1]) < 16000 and texto[0] == sistema[0] and texto[2:] == sistema[2:], "modo texto: só a seção muda")
        eq(self._rodar_texto(Agente("chat"), sistema, partes), texto, "duas chamadas: sistema idêntico (cache)")
        eq(self._rodar_texto(Agente("responses"), sistema, partes), sistema, "modo nativo: o texto fica (a lista é que encurta)")
        self._desligar(True)
        try:
            eq(self._rodar_texto(Agente("chat"), sistema, partes), sistema, "desligado: tudo como antes")
        finally:
            self._desligar(False)
        quebrado = Agente("chat")
        quebrado.get_chat_model = None  # anything unexpected: not text mode, nothing changes
        eq(self._rodar_texto(quebrado, sistema, partes), sistema, "erro: tudo como antes")

    def t_texto_manual_na_primeira_no_formato_de_texto(self):
        m, e = self._manual_ext(), self.e
        e.MANUAIS["ficha"] = "manual nativo da ficha"
        e.MANUAIS_TEXTO["ficha"] = "### ficha\nmanual de texto com {\"tool_name\": \"ficha\"}"
        for modo, esperado in (("chat", "manual de texto"), ("responses", "manual nativo")):
            a = Agente(modo)
            com_transporte(lambda: m.ManualNaPrimeira(agent=a).execute(
                data={"args": (a, "ficha", "ok"), "kwargs": {}, "exception": None}))
            eq(len(a.history.msgs), 1, f"{modo}: o manual entra no primeiro uso")
            ok(esperado in a.history.msgs[0]["content"], f"{modo}: {a.history.msgs[0]['content'][:80]}")
            com_transporte(lambda: m.ManualNaPrimeira(agent=a).execute(
                data={"args": (a, "ficha", "ok"), "kwargs": {}, "exception": None}))
            eq(len(a.history.msgs), 1, f"{modo}: não repete")
        e.MANUAIS_TEXTO["so_texto"] = "só no texto"
        eq(e.manual("so_texto", texto_modo=False).endswith("só no texto"), True, "sem o nativo, serve o de texto")

    def t_texto_meta_conversa_do_matheus_no_sonnet(self):
        """The whole system prompt of a common chat of Matheus's in text mode: below 80 thousand characters, with the
        rules, decisions and sheet (the measured rest) untouched."""
        e, i = self.e, self.i
        partes, dados = partes_reais()
        secao = secao_texto(partes, dados)
        conectores = _carregar("conectores_suite_para_meta", PLUGINS / "conectores" / "tests" / "suite.py")
        ok(hasattr(conectores, "secao_mcp_texto"), "o conectores com o modo texto tem de ser implantado antes")
        s = conectores.Suite()
        try:
            mcp = conectores.secao_mcp_texto(s.mcp)
            antes = RESTO_MEDIDO + len(secao) + len(mcp)
            ferramentas = e.encurtar_texto(secao, partes, i.CURTAS, i.MIN_GANHO, {})
            comum = s.s.enxugar_mcp_texto(mcp, s.mcp, conectores.render_ferramenta, set())
            codigo = s.s.enxugar_mcp_texto(mcp, s.mcp, conectores.render_ferramenta,
                                           {f"github.{n}" for n in s.s.GITHUB_CODIGO})
        finally:
            shutil.rmtree(s.tmp, ignore_errors=True)
        depois = RESTO_MEDIDO + len(ferramentas) + len(comum)
        ok(antes > 270000, f"antes: ~281 mil como na VM (deu {antes})")
        ok(depois < META_TEXTO, f"conversa comum no Sonnet: {depois} caracteres (meta {META_TEXTO})")
        com_codigo = RESTO_MEDIDO + len(ferramentas) + len(codigo)
        ok(com_codigo < META_TEXTO, f"conversa de código: {com_codigo} (meta {META_TEXTO})")
        print(f"prompt_enxuto: sistema no modo texto {antes} -> {depois} caracteres (código {com_codigo})")

    # ------------------------------------------------------------------ <invoke> do modelo vira JSON (20/10)

    def t_invoke_xml_vira_chamada_json(self):
        x = self.carregar.modulo("xml_ferramenta")
        # visto no log de 20/10 (texto antes, parâmetros com JSON e texto, e um ``` solto)
        bruto = ('Vou abrir o seletor.\n<invoke name="browser">\n<parameter name="action">evaluate</parameter>\n'
                 '<parameter name="browser_id">13</parameter>\n<parameter name="script">Array.from(document.querySelectorAll'
                 '("select")).map(e=>e.tagName)</parameter>\n</invoke>\n```')
        d = json.loads(x.converter(bruto))
        eq((d["tool_name"], d["tool_args"]), ("browser", {"action": "evaluate", "browser_id": 13,
                                                          "script": 'Array.from(document.querySelectorAll("select")).map(e=>e.tagName)'}),
           "nome e parâmetros, número como número")
        eq(d["thoughts"], ["Vou abrir o seletor."], "o texto antes vira o pensamento")
        ok(x.converter('<invoke name="browser">\n</invoke>\n<invoke name="browser">\n</invoke>') is None,
           "20/10: <invoke> sem parâmetros não vira chamada vazia (o navegador rodava sem nada e entrava em loop)")
        aninhado = json.loads(x.converter('<function_calls><invoke name="response"><parameter name="text">Pronto: '
                                          '3 itens</parameter><parameter name="opcoes">{"a": [1, 2]}</parameter></invoke></function_calls>'))
        eq(aninhado["tool_args"], {"text": "Pronto: 3 itens", "opcoes": {"a": [1, 2]}}, "objeto JSON e texto")
        # 20/10 21h: valid JSON then a stray empty <invoke>: leave it to Agent Zero's JSON parser (no conversion)
        ok(x.converter('{"thoughts": ["preencher"], "headline": "Preenchendo", "tool_name": "browser", "tool_args": '
                       '{"action": "type", "ref": 61, "text": "Food"}}\n</invoke>\n<invoke name="browser">\n</invoke>') is None,
           "JSON válido antes do <invoke> vazio: a chamada JSON vale")
        ok(x.converter('<invoke name="browser">\n</invoke>\nWait, I must output valid JSON only.\n\n{"thoughts": ["ler"], '
                       '"headline": "Lendo", "tool_name": "browser", "tool_args": {"action": "content", "browser_id": 23}}') is None,
           "<invoke> vazio e depois o JSON válido: a chamada JSON vale")
        cortado = json.loads(x.converter('<invoke name="browser"><parameter name="action">click</parameter><parameter name="ref">22'))
        eq(cortado["tool_args"], {"action": "click", "ref": 22}, "resposta cortada no meio ainda vale")
        eq(x.converter('{"tool_name": "response", "tool_args": {"text": "oi"}}'), None, "JSON não mexe")
        eq(x.converter("texto comum, sem ferramenta"), None, "texto comum não mexe")

    def t_extensao_xml_so_troca_quando_precisa(self):
        m = _carregar("enxuto_xml_teste", EXT / "message_loop_result" / "_05_xml_para_json.py")
        et = types.ModuleType("helpers.extract_tools")
        et.extract_tool_request = lambda t: {"ok": 1} if t.startswith("{") else None
        antes = sys.modules.get("helpers.extract_tools")
        sys.modules["helpers.extract_tools"] = et
        sys.modules.setdefault("helpers", types.ModuleType("helpers")).extract_tools = et
        try:
            llm = types.SimpleNamespace(response='<invoke name="browser"><parameter name="action">list</parameter></invoke>',
                                        function_calls=None)
            m.XmlParaJson(agent=None).execute(result_data={"llm_result": llm})
            eq(json.loads(llm.response)["tool_args"], {"action": "list"}, "XML virou JSON")
            nativa = types.SimpleNamespace(response='<invoke name="x"></invoke>', function_calls=[1])
            m.XmlParaJson(agent=None).execute(result_data={"llm_result": nativa})
            eq(nativa.response, '<invoke name="x"></invoke>', "chamada nativa: não mexe")
            json_ok = types.SimpleNamespace(response='{"tool_name": "a", "tool_args": {"q": "<invoke>"}}', function_calls=None)
            m.XmlParaJson(agent=None).execute(result_data={"llm_result": json_ok})
            ok(json_ok.response.startswith('{"tool_name": "a"'), "JSON válido com a palavra invoke: não mexe")
        finally:
            if antes is None:
                sys.modules.pop("helpers.extract_tools", None)
            else:
                sys.modules["helpers.extract_tools"] = antes

    # ------------------------------------------------------------------ Sonnet nativo no Bedrock (20/10)

    def t_nativo_bedrock_sem_marcas_so_quando_o_proxy_cacheia(self):
        n = self.carregar.modulo("nativo")

        def modelo(modo="responses", nome="bedrock/converse/us.anthropic.claude-sonnet-5-5",
                   base="http://host.docker.internal:8787/bedrock"):
            return types.SimpleNamespace(model_name=nome, kwargs={"a0_api_mode": modo, "api_base": base})

        ok(n.sem_marcas_do_a0(modelo()), "Responses + Bedrock + proxy: sem as marcas do A0")
        ok(n.sem_marcas_do_a0(modelo(base="http://host.docker.internal:8787/bedrock/")), "barra no fim também")
        ok(not n.sem_marcas_do_a0(modelo("chat")), "modo texto: as marcas do A0 ficam")
        ok(not n.sem_marcas_do_a0(modelo(base="")), "Bedrock direto (sem o proxy, que é quem põe o cache): ficam")
        ok(not n.sem_marcas_do_a0(modelo(nome="anthropic/claude-x", base="https://api.anthropic.com")), "outro provedor")
        ok(not n.sem_marcas_do_a0(modelo(nome="openai/gpt-6-luna", base="http://host.docker.internal:8787/openai/v1")),
           "GPT pelo proxy: não mexe")
        ok(not n.sem_marcas_do_a0(None) and not n.sem_marcas_do_a0(types.SimpleNamespace(kwargs=None)),
           "modelo estranho: não mexe")

    def t_nativo_bedrock_extensao(self):
        m = _carregar("enxuto_nativo_teste", EXT / "chat_model_call_before" / "_05_nativo_bedrock.py")
        m.carregar = self.carregar
        sonnet = types.SimpleNamespace(model_name="bedrock/converse/us.anthropic.claude-sonnet-5-5",
                                       kwargs={"a0_api_mode": "responses",
                                               "api_base": "http://host.docker.internal:8787/bedrock"})
        dados = {"model": sonnet, "explicit_caching": True, "a0_responses_function_tools": [_ferramenta("response", "x")]}
        _rodar(m.NativoBedrock(agent=None).execute(call_data=dados))
        eq(dados["explicit_caching"], False, "chamada nativa ao Sonnet pelo proxy: sem as marcas (senão perde as ferramentas)")
        self._desligar(True)
        try:
            dados = {"model": sonnet, "explicit_caching": True, "a0_responses_function_tools": [_ferramenta("response", "x")]}
            _rodar(m.NativoBedrock(agent=None).execute(call_data=dados))
            eq(dados["explicit_caching"], False, "com o interruptor desligado também (as ferramentas precisam chegar)")
        finally:
            self._desligar(False)
        dados = {"model": sonnet, "explicit_caching": True, "a0_responses_function_tools": []}
        _rodar(m.NativoBedrock(agent=None).execute(call_data=dados))
        eq(dados["explicit_caching"], True, "sem lista de ferramentas: não mexe")
        texto = types.SimpleNamespace(model_name=sonnet.model_name, kwargs={**sonnet.kwargs, "a0_api_mode": "chat"})
        dados = {"model": texto, "explicit_caching": True, "a0_responses_function_tools": [_ferramenta("response", "x")]}
        _rodar(m.NativoBedrock(agent=None).execute(call_data=dados))
        eq(dados["explicit_caching"], True, "modo texto: não mexe")

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
