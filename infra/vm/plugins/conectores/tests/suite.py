"""Tests of conectores (no model, no MCP server: Agent Zero's modules are stubbed while the files load).
Run with implantar.py (staging copy), inside the container, or from the repository root:
python3 infra/operador/rodar_suites_locais.py conectores

`ferramentas_mcp_20out.json.gz`: the google (workspace-mcp) and github tools as the VM's MCP servers gave them on
20/10 (name, description, input schema; the owner's address replaced by dono@example.com)."""

import asyncio
import copy
import gzip
import importlib.util
import json
import shutil
import sys
import tempfile
import traceback
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
EXT = RAIZ / "extensions" / "python"
FIXTURE = RAIZ / "tests" / "ferramentas_mcp_20out.json.gz"
# measured on 20/10 (the VM, a chat of Matheus's): the 52 local tools after prompt_enxuto took 21,439 characters
LOCAIS_MEDIDO = 21439
CONECTOR_MEDIDO = 1433  # the new `conector` tool, as Agent Zero turns its prompt into a native tool (VM, 20/10)
META = 40000

# connector tools run in Matheus's chats in the 14 days to 20/10 (chat logs), with the number of runs
USADAS_14_DIAS = {
    "google.search_gmail_messages": 133, "google.get_events": 74, "google.get_gmail_message_content": 34,
    "google.search_drive_files": 10, "google.get_gmail_messages_content_batch": 9, "google.create_drive_file": 9,
    "google.get_gmail_thread_content": 6, "google.list_drive_items": 6, "google.import_to_google_doc": 4,
    "google.read_sheet_values": 3, "google.get_doc_as_markdown": 2, "google.get_doc_content": 2,
    "google.create_spreadsheet": 2, "google.get_drive_shareable_link": 2, "google.get_drive_file_content": 1,
    "google.get_spreadsheet_info": 1, "google.update_drive_file": 1, "google.create_drive_folder": 1,
    "google.modify_sheet_values": 1, "google.format_sheet_range": 1, "google.resize_sheet_dimensions": 1,
    "github.get_file_contents": 18, "github.search_repositories": 8, "github.list_commits": 6,
    "github.pull_request_read": 5, "github.get_me": 3, "github.get_commit": 2, "github.search_code": 1,
    "github.list_branches": 1,
}
# used once or twice and too big to go in every call: on demand (`conector` ativar, or called by name)
RARAS_SOB_DEMANDA = {"google.get_doc_content", "google.update_drive_file", "google.format_sheet_range",
                     "google.resize_sheet_dimensions"}


class Falha(AssertionError):
    pass


def ok(cond, msg):
    if not cond:
        raise Falha(msg)


def eq(a, b, msg):
    if a != b:
        raise Falha(f"{msg}: esperado {b!r}, veio {a!r}")


class Response:
    def __init__(self, message="", break_loop=False, **k):
        self.message, self.break_loop = message, break_loop


def _stubs() -> dict:
    agent = types.ModuleType("agent")
    agent.LoopData = type("LoopData", (), {})
    helpers = types.ModuleType("helpers")
    ext = types.ModuleType("helpers.extension")
    ext.Extension = type("Extension", (), {"__init__": lambda self, agent=None, **k: setattr(self, "agent", agent)})
    tool = types.ModuleType("helpers.tool")
    tool.Response = Response
    tool.Tool = type("Tool", (), {"__init__": lambda self, agent=None, **k: setattr(self, "agent", agent)})
    errors = types.ModuleType("helpers.errors")
    errors.RepairableException = type("RepairableException", (Exception,), {})
    return {"agent": agent, "helpers": helpers, "helpers.extension": ext, "helpers.tool": tool, "helpers.errors": errors}


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


def _nativo(original: str) -> str:
    return original.replace(".", "_")[:52] + "_abcd1234"  # like Agent Zero's _native_tool_name for "server.tool"


class Contexto:
    def __init__(self, dono="matheus"):
        self.data = {"dono": dono}

    def get_data(self, k):
        return self.data.get(k)

    def set_data(self, k, v):
        self.data[k] = v


class Mensagem:
    def __init__(self, texto):
        self.content = {"user_message": texto}


class Agente:
    def __init__(self, dono="matheus", texto="", mapa=None):
        self.context = Contexto(dono)
        self.data = {"responses_tool_name_map": mapa or {}}
        self.last_user_message = Mensagem(texto) if texto else None

    def get_data(self, k):
        return self.data.get(k)


def _tam(ferramentas) -> int:
    return len(json.dumps(ferramentas, ensure_ascii=False))


class Suite:
    def __init__(self):
        self.resultados = []
        self.tmp = Path(tempfile.mkdtemp(prefix="conectores-teste-"))
        self.carregar = _carregar("conectores_carregar", RAIZ / "helpers" / "carregar.py")
        self.s = self.carregar.modulo("sob_demanda")
        self.s.DESLIGADO = self.tmp / "desligado"
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as f:
            self.mcp = json.load(f)  # {"google.x": {"description", "input_schema"}}

    def _desligar(self, sim: bool):
        if sim:
            self.s.DESLIGADO.write_text("")
        else:
            self.s.DESLIGADO.unlink(missing_ok=True)

    def _lista_real(self, locais=3):
        """The native list as Agent Zero builds it: local tools first, then every MCP tool; and its name map."""
        ferramentas = [{"type": "function", "name": f"local_{i}", "strict": False, "description": "x" * 50,
                        "parameters": {"type": "object", "properties": {}}} for i in range(locais)]
        mapa = {f"local_{i}": f"local_{i}" for i in range(locais)}
        for original, t in self.mcp.items():
            nativo = _nativo(original)
            mapa[nativo] = original
            esquema = dict(t["input_schema"])
            esquema.setdefault("additionalProperties", True)
            ferramentas.append({"type": "function", "name": nativo, "strict": False,
                                "description": t["description"] or original, "parameters": esquema})
        return ferramentas, mapa

    def _ext(self):
        m = _carregar("conectores_lista_teste", EXT / "chat_model_call_before" / "_40_ferramentas_do_conector.py")
        m.carregar = self.carregar
        m.donos = lambda: {"google": "matheus", "github": "matheus"}
        return m

    def _rodar_ext(self, agente, ferramentas):
        dados = {"a0_responses_function_tools": ferramentas, "messages": []}
        _rodar(self._ext().FerramentasDoConector(agent=agente).execute(call_data=dados))
        return dados["a0_responses_function_tools"]

    @staticmethod
    def _originais(ferramentas, mapa):
        return [mapa.get(f["name"], f["name"]) for f in ferramentas]

    # ------------------------------------------------------------------ what goes in the list

    def t_sempre_existe_e_cobre_o_uso_real(self):
        s = self.s
        for servidor, nomes in list(s.SEMPRE.items()) + [("github", s.GITHUB_CODIGO)]:
            for n in nomes:
                ok(f"{servidor}.{n}" in self.mcp, f"{servidor}.{n} não existe no servidor (nome mudou?)")
        for original in USADAS_14_DIAS:
            servidor, nome = s.servidor_e_nome(original)
            na = nome in s.SEMPRE.get(servidor, ()) or (servidor == "github" and nome in s.GITHUB_CODIGO)
            ok(na or original in RARAS_SOB_DEMANDA, f"{original} foi usada e não está nem sempre nem nas raras")
        for essencial in ("search_gmail_messages", "get_gmail_message_content", "get_events", "search_drive_files",
                          "get_drive_file_content", "create_drive_file", "get_doc_as_markdown", "import_to_google_doc",
                          "read_sheet_values", "create_spreadsheet", "start_google_auth"):
            ok(essencial in s.SEMPRE["google"], f"essencial fora: {essencial}")

    def t_lista_do_matheus_abaixo_da_meta(self):
        s = self.s
        ferramentas, mapa = self._lista_real(0)
        antes = _tam(ferramentas)
        ok(antes > 150000, f"a lista cheia dos conectores media ~155 mil caracteres (deu {antes})")
        depois = _tam(s.filtrar(ferramentas, mapa, set(), False))
        ok(LOCAIS_MEDIDO + depois + CONECTOR_MEDIDO < META,
           f"conversa comum: {LOCAIS_MEDIDO} locais + {depois} dos conectores + `conector` passa de {META}")
        codigo = _tam(s.filtrar(ferramentas, mapa, set(), True))
        ok(codigo - depois < 8000, f"o GitHub de código acrescenta até ~8 mil (deu {codigo - depois})")
        print(f"conectores: lista dos conectores {antes} -> {depois} caracteres ({codigo} com GitHub de código)")

    def t_filtrar_mantem_locais_e_tira_o_raro(self):
        s = self.s
        ferramentas, mapa = self._lista_real()
        intacta = copy.deepcopy(ferramentas)
        nova = s.filtrar(ferramentas, mapa, set(), False)
        eq(ferramentas, intacta, "a lista original não é alterada")
        nomes = self._originais(nova, mapa)
        eq(nomes[:3], ["local_0", "local_1", "local_2"], "ferramentas locais primeiro, iguais")
        ok(nova[0] is ferramentas[0], "ferramenta local vai como veio")
        eq(sorted(n for n in nomes if n.startswith("google.")), sorted(f"google.{n}" for n in s.SEMPRE["google"]),
           "do Google, só as de sempre")
        ok(not any(n.startswith("github.") for n in nomes), "GitHub fora de conversa de código")
        ordem = [n for n in self._originais(ferramentas, mapa) if n in nomes]
        eq(nomes, ordem, "a ordem é a de sempre (cache)")
        # active and code
        nova = s.filtrar(ferramentas, mapa, {"google.batch_update_doc", "github.list_issues"}, True)
        nomes = set(self._originais(nova, mapa))
        ok({"google.batch_update_doc", "github.list_issues"} <= nomes, "ativadas entram")
        ok({f"github.{n}" for n in s.GITHUB_CODIGO} <= nomes, "conversa de código: GitHub básico")
        # another person's connector: nothing of it
        nova = s.filtrar(ferramentas, mapa, {"google.batch_update_doc"}, True, de_outros={"google", "github"})
        eq(self._originais(nova, mapa), ["local_0", "local_1", "local_2"], "conector de outra pessoa não vai")
        # an MCP server not handled here goes as it comes; no name map = nothing changes
        outra = {"type": "function", "name": "slack_post_x", "description": "d" * 900, "parameters": {}}
        nova = s.filtrar([outra], {"slack_post_x": "slack.post"}, set(), False)
        ok(nova[0] is outra, "outro servidor MCP fica como está")
        eq(s.filtrar(ferramentas, {}, set(), False), ferramentas, "sem mapa de nomes: lista igual")

    def t_esquema_compacto_tem_os_mesmos_parametros(self):
        s = self.s
        for original, t in self.mcp.items():
            esquema = t["input_schema"]
            curto = s.compactar_esquema(esquema)
            props, curtas = esquema.get("properties", {}), curto.get("properties", {})
            obrig = set(esquema.get("required") or [])
            esperadas = {k for k in props if not (k == "user_google_email" and k not in obrig)}
            eq(set(curtas), esperadas, f"{original}: parâmetros")
            eq(curto.get("required"), esquema.get("required"), f"{original}: obrigatórios")
            for k in esperadas:
                for campo in ("type", "enum", "anyOf", "items"):
                    if campo in props[k] and campo != "anyOf":
                        eq(json.dumps(s.compactar_esquema(props[k][campo]) if campo == "items" else props[k][campo]),
                           json.dumps(curtas[k][campo]), f"{original}.{k}.{campo}")
                if props[k].get("default") is not None:
                    eq(curtas[k].get("default"), props[k]["default"], f"{original}.{k}: padrão")
                ok(len(str(curtas[k].get("description", ""))) <= s.MAX_PARAMETRO, f"{original}.{k}: descrição curta")
        ok("dono@example.com" not in json.dumps(s.compactar_esquema(self.mcp["google.get_events"]["input_schema"])),
           "o e-mail do dono não vai em toda chamada")
        f = {"name": "x", "description": "Primeira frase. Segunda frase longa.", "parameters": {"type": "object"}}
        eq(s.compactar(f)["description"], "Primeira frase.", "descrição: primeira frase")

    def t_fala_de_codigo(self):
        s = self.s
        for sim in ("olha o PR 12 do aibusiness", "o que mudou no repositório?", "faz um commit", "abre o GitHub",
                    "tem bug no código do app", "roda o Claude Code", "script em Python"):
            ok(s.fala_de_codigo(sim), f"devia ser código: {sim}")
        for nao in ("manda o código de verificação", "paga o boleto com o código de barras", "cliente de Curitiba, pr",
                    "resume meus e-mails", "agenda de amanhã", "prospecção de hoje"):
            ok(not s.fala_de_codigo(nao), f"não é código: {nao}")

    # ------------------------------------------------------------------ the extension

    def t_extensao_filtra_e_lembra_o_codigo(self):
        s = self.s
        ferramentas, mapa = self._lista_real()
        a = Agente(texto="resume meus e-mails de hoje", mapa=mapa)
        nomes = self._originais(self._rodar_ext(a, ferramentas), mapa)
        ok("google.search_gmail_messages" in nomes and "google.batch_update_doc" not in nomes, "comum: Google básico")
        ok(not any(n.startswith("github.") for n in nomes), "sem código: sem GitHub")
        a.last_user_message = Mensagem("e o último commit do agentepessoal?")
        nomes = self._originais(self._rodar_ext(a, ferramentas), mapa)
        ok("github.list_commits" in nomes, "falou de código: GitHub entra")
        a.last_user_message = Mensagem("ok, obrigado")
        nomes = self._originais(self._rodar_ext(a, ferramentas), mapa)
        ok("github.list_commits" in nomes, "e fica na conversa (lista estável para o cache)")
        eq(sorted(a.context.data[s.CHAVE_ATIVAS]), sorted(f"github.{n}" for n in s.GITHUB_CODIGO), "guardado no contexto")

    def t_extensao_convidado_desligada_e_erro(self):
        ferramentas, mapa = self._lista_real()
        convidado = Agente(dono="will", texto="olha o repositório", mapa=mapa)
        nomes = self._originais(self._rodar_ext(convidado, ferramentas), mapa)
        eq(nomes, ["local_0", "local_1", "local_2"], "convidado: nenhum conector do Matheus na lista")
        self._desligar(True)
        try:
            eq(len(self._rodar_ext(Agente(mapa=mapa), ferramentas)), len(ferramentas), "desligado: lista inteira")
        finally:
            self._desligar(False)
        eq(len(self._rodar_ext(Agente(mapa={}), ferramentas)), len(ferramentas), "sem mapa de nomes: lista inteira")
        quebrado = Agente(mapa=mapa)
        quebrado.context = None  # anything unexpected
        eq(len(self._rodar_ext(quebrado, ferramentas)), len(ferramentas), "erro: lista inteira, a chamada segue")

    def t_ferramenta_chamada_pelo_nome_fica_ativa(self):
        m = _carregar("conectores_ativo_teste", EXT / "tool_execute_before" / "_05_conector_ativo.py")
        m.carregar = self.carregar
        a = Agente()
        for nome in ("google.create_doc", "google.search_gmail_messages", "slack.post", "prospeccao", "google.create_doc"):
            _rodar(m.ConectorAtivo(agent=a).execute(tool_args={}, tool_name=nome))
        eq(a.context.data.get(self.s.CHAVE_ATIVAS), ["google.create_doc"], "só a rara do conector, uma vez")

    # ------------------------------------------------------------------ the `conector` tool

    def _ferramenta(self, dono="matheus"):
        m = _carregar("conectores_tool_teste", RAIZ / "tools" / "conector.py")
        m.carregar = self.carregar
        m.donos = lambda: {"google": "matheus", "github": "matheus"}
        m.catalogo_mcp = lambda agent: [{n: dict(t)} for n, t in self.mcp.items()]
        a = Agente(dono=dono)
        return m.Conector(agent=a), a

    def t_conector_lista_ativa_e_descreve(self):
        s = self.s
        t, a = self._ferramenta()
        txt = _rodar(t.execute(acao="listar", conector="google")).message
        eq(sum(1 for l in txt.splitlines() if l[:2] in ("✓ ", "· ")), sum(1 for n in self.mcp if n.startswith("google.")),
           "listar mostra todas as do Google")
        ok("✓ search_gmail_messages" in txt and "· batch_update_doc" in txt, "marca as que já estão na lista")
        ok("batch_update_doc" in _rodar(t.execute(acao="listar", conector="google", busca="batch")).message, "busca")
        txt = _rodar(t.execute(acao="ativar", conector="google", ferramentas=["create_doc", "google.modify_doc_text",
                                                                            "nao_existe"])).message
        eq(a.context.data[s.CHAVE_ATIVAS], ["google.create_doc", "google.modify_doc_text"], "ativadas no contexto")
        ok("Ativadas" in txt and "nao_existe" in txt, txt)
        txt = _rodar(t.execute(acao="ativar", ferramentas="google_create_doc")).message
        ok("Já estavam" in txt, "nome nativo/repetido: já estava")
        _rodar(t.execute(acao="ativar", conector="github"))
        ok(set(f"github.{n}" for n in s.GITHUB_CODIGO) <= set(a.context.data[s.CHAVE_ATIVAS]), "GitHub básico")
        txt = _rodar(t.execute(acao="descrever", conector="google", ferramenta="batch_update_doc")).message
        ok(self.mcp["google.batch_update_doc"]["description"] in txt and "operations" in txt, "descrever: completo")
        ok("google.batch_update_doc" not in a.context.data[s.CHAVE_ATIVAS], "descrever não ativa")

    def t_conector_de_outra_pessoa_recusado(self):
        t, a = self._ferramenta(dono="will")
        for acao in ("listar", "ativar"):
            txt = _rodar(t.execute(acao=acao, conector="google", ferramentas=["create_doc"])).message
            ok("outra pessoa" in txt, f"{acao}: recusado ({txt})")
        ok(not a.context.data.get(self.s.CHAVE_ATIVAS), "nada ativado")

    def t_prompt_da_ferramenta_tem_o_esquema(self):
        texto = (RAIZ / "prompts" / "agent.system.tool.conector.md").read_text(encoding="utf-8")
        esquema = json.loads(texto.split("Input schema for tool_args:", 1)[1].split("\n", 1)[0])
        eq(esquema["properties"]["acao"]["enum"], ["listar", "ativar", "descrever"], "ações")
        ok(len(texto) < 1100, f"a descrição vai em toda chamada: curta ({len(texto)})")

    # ------------------------------------------------------------------ system prompt

    def t_instrucoes_avisam_do_sob_demanda(self):
        m = _carregar("conectores_prompt_teste", EXT / "system_prompt" / "_15_conectores.py")
        m.DONOS = self.tmp / "donos.json"
        m.DONOS.write_text(json.dumps({"google": "matheus", "github": "matheus"}))
        orig = m._sob_demanda
        m._sob_demanda = lambda: self.s.ligado()

        def texto(dono):
            saida = []
            _rodar(m.ConectoresPrompt(agent=Agente(dono=dono)).execute(system_prompt=saida))
            return saida[0]

        ok("`conector`" in texto("matheus"), "Matheus: avisa que as outras vêm pelo `conector`")
        ok("`conector`" not in texto("will") and "Não use nesta conversa" in texto("will"), "convidado: só a recusa")
        self._desligar(True)
        try:
            ok("`conector`" not in texto("matheus"), "desligado: sem o aviso")
        finally:
            self._desligar(False)
        m._sob_demanda = orig
        ok(m._sob_demanda() in (True, False), "o interruptor real carrega sem erro")

    async def rodar(self, filtro: str = ""):
        separacao = sys.modules.pop("login_usuarios_separacao", None)  # another suite may have loaded the real one
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
            if separacao is not None:
                sys.modules["login_usuarios_separacao"] = separacao
        passou = sum(1 for r in self.resultados if r["ok"])
        return {"total": len(self.resultados), "passou": passou, "resultados": self.resultados}


if __name__ == "__main__":
    r = asyncio.run(Suite().rodar(sys.argv[1] if len(sys.argv) > 1 else ""))
    for x in r["resultados"]:
        print(("✓ " if x["ok"] else "✗ ") + x["teste"] + ("" if x["ok"] else f": {x['erro']}"))
    print(f"{r['passou']}/{r['total']}")
    sys.exit(0 if r["passou"] == r["total"] else 1)
