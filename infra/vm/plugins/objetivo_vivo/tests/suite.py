"""Tests of objetivo_vivo (no model calls; Agent Zero's modules are stubbed while the files load). Run with implantar.py
(staging copy), inside the container, or from the repository root: python3 infra/operador/rodar_suites_locais.py objetivo_vivo"""

import asyncio
import enum
import importlib.util
import inspect
import json
import sys
import tempfile
import traceback
import types
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PLUGINS = RAIZ.parent if (RAIZ.parent / "cache_prompt").is_dir() else Path("/a0/usr/plugins")  # staging copy: the live ones
EXT = RAIZ / "extensions" / "python"
HOOK = EXT / "_functions" / "agent" / "Agent" / "hist_add_user_message" / "end" / "_30_objetivo_vivo.py"
EXTRA = EXT / "message_loop_prompts_after" / "_30_objetivo_vivo.py"
CACHE = PLUGINS / "cache_prompt" / "extensions" / "python" / "message_loop_prompts_after" / "_98_extras_no_historico.py"
WHATS = PLUGINS / "whatsapp" / "extensions" / "python" / "system_prompt" / "_60_conversa_whatsapp.py"


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


class Tipo(enum.Enum):
    USER = "user"
    TASK = "task"
    BACKGROUND = "background"


def _stubs() -> dict:
    agent = types.ModuleType("agent")
    agent.LoopData, agent.AgentContextType = LoopData, Tipo
    helpers = types.ModuleType("helpers")
    ext = types.ModuleType("helpers.extension")
    ext.Extension = type("Extension", (), {"__init__": lambda self, agent=None, **k: setattr(self, "agent", agent)})
    tool = types.ModuleType("helpers.tool")
    tool.Response = type("Response", (), {"__init__": lambda self, message="", break_loop=False, **k:
                                          (setattr(self, "message", message), setattr(self, "break_loop", break_loop))})
    tool.Tool = type("Tool", (), {})
    dj = types.ModuleType("helpers.dirty_json")
    dj.stringify = lambda v, separators=None: json.dumps(v, ensure_ascii=False, separators=separators)
    helpers.extension, helpers.tool, helpers.dirty_json = ext, tool, dj
    return {"agent": agent, "helpers": helpers, "helpers.extension": ext, "helpers.tool": tool, "helpers.dirty_json": dj}


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
    def __init__(self, content, id=""):
        self.id, self.content, self.summary = id or str(uuid.uuid4()), content, ""


class Historico:
    def __init__(self):
        self.msgs = []

    def all_messages(self):
        return list(self.msgs)

    def output(self):
        return [{"ai": False, "content": m.summary or m.content, "id": m.id} for m in self.msgs]


class Contexto:
    def __init__(self, id="ctxOBJ", tipo=Tipo.USER, **dados):
        self.id, self.type, self.data = id, tipo, dict(dados)

    def get_data(self, k):
        return self.data.get(k)

    def set_data(self, k, v):
        self.data[k] = v


class Agente:
    def __init__(self, ctx=None, number=0):
        self.context, self.number = ctx or Contexto(dono="matheus"), number
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
        self.o = _carregar("objetivo_vivo_objetivo_teste", RAIZ / "helpers" / "objetivo.py")
        self.tmp = Path(tempfile.mkdtemp(prefix="objetivo-teste-"))
        self.o.TAREFAS = self.tmp / "tasks.json"
        self.o.TAREFAS.write_text(json.dumps({"tasks": [{"uuid": "ROTINA01", "context_id": "ctxROTINA"}]}))
        self.resultados = []

    def _modulos(self):
        """The extensions and the tool, each pointed at this suite's helper (and the fake scheduler file)."""
        sys.modules["objetivo_vivo_objetivo"] = self.o
        self.o._mtime = (RAIZ / "helpers" / "objetivo.py").stat().st_mtime
        return (_carregar("ov_hook", HOOK).ObjetivoNaMensagem, _carregar("ov_extra", EXTRA).ObjetivoVivo,
                _carregar("ov_tool", RAIZ / "tools" / "passos.py"))

    def _mensagem(self, hook, agente, texto, intervencao=False):
        msg = Msg({"user_intervention" if intervencao else "user_message": texto})
        agente.history.msgs.append(msg)
        data = {"args": (agente, types.SimpleNamespace(message=texto)), "kwargs": {"intervention": intervencao},
                "result": msg, "exception": None}
        hook(agent=agente).execute(data=data)
        return msg

    async def _passo(self, extra, cache, agente):
        ld = LoopData()
        ld.history_output = agente.history.output()
        await extra(agent=agente).execute(loop_data=ld)
        bloco = ld.extras_persistent.get("objetivo_vivo", "")
        if cache is not None:
            await cache(agent=agente).execute(loop_data=ld)
        return bloco

    # ---- reading his message ---------------------------------------------------------------------------------
    def t_pedido_estado_e_confirmacao(self):
        t = self.o.tipo
        for texto in ("Monta a planilha dos leads e manda pro meu e-mail", "n manda pro @doce.lar ainda",
                      "continua e manda pro fulano também", "pesquisa o preço da Contabo", "faz o relatório"):
            eq(t(texto), "pedido", texto)
        for texto in ("continua", "Continua?", "e aí?", "E aí, conseguiu?", "oq ta fazendo?", "O que está fazendo?",
                      "??", "kd", "terminou?", "status", "🎤 e aí", "e ai como ta"):
            eq(t(texto), "estado", texto)
        for texto in ("pode", "Sim", "ok", "pode sim, continua"[:8], "beleza", "👍", "n"):
            ok(t(texto) in {"confirmacao", "estado"}, f"{texto}: {t(texto)}")
        for texto in ("✅ Faz pra mim", "[Conversa externa com Loja X] chegou: «temos sim»", "## Task:\nRadar"):
            eq(t(texto), "maquina", texto)
        eq(t("e aí?\n\n(Ele respondeu citando a sua mensagem: «Quer que eu mande?»)"), "estado", "citação do celular")
        eq(self.o.texto_dele("[Pedido feito pelo celular enquanto a conversa principal está ocupada com: “x”.]\n"
                             "Últimas...\n\nPedido:\nAgenda a reunião"), "Agenda a reunião", "conversa paralela")
        eq(self.o.texto_dele("[Reiniciei no meio do pedido anterior desta conversa: «x». Antes confira]\n\nfaz y"),
           "faz y", "pedido cortado por reinício")

    def t_mensagem_nova_atualiza_o_objetivo(self):
        o = self.o
        e = o.nova_mensagem({}, "Monta a planilha dos 30 leads", "m1", agora=1)
        eq((e["pedido"], e["msg_id"], e["passos"]), ("Monta a planilha dos 30 leads", "m1", []), "pedido novo")
        e = o.com_passos(e, ["[x] achar os leads", "[ ] montar a planilha", "[ ] mandar o e-mail"])
        for texto in ("e aí?", "continua", "pode", "✅ Faz pra mim"):
            ok(o.nova_mensagem(e, texto, "m9") == e, f"'{texto}' não troca o objetivo nem os passos")
        e2 = o.nova_mensagem(e, "e põe o telefone de cada um também", "m2", agora=2)
        eq(e2["pedido"], "e põe o telefone de cada um também", "pedido novo troca")
        eq(e2["anterior"], "Monta a planilha dos 30 leads", "o anterior fica, porque tinha passos abertos")
        eq(e2["passos"], [], "passos do pedido anterior saem")
        e3 = o.nova_mensagem(o.com_passos(e2, ["[x] tudo"]), "outra coisa: vê a agenda", "m3", agora=3)
        eq(e3["anterior"], "", "pedido anterior terminado não volta")
        longo = "palavra " * 200
        ok(len(o.nova_mensagem({}, longo)["pedido"]) <= o.PEDIDO_MAX, "pedido literal, mas curto")

    def t_passos(self):
        o = self.o
        p = o.ler_passos(["[x] abrir o site", "[ ] baixar o relatório", "✅ logar", "- mandar", "",
                          {"passo": "conferir", "feito": True}])
        eq([(x["texto"], x["feito"]) for x in p],
           [("abrir o site", True), ("baixar o relatório", False), ("logar", True), ("mandar", False),
            ("conferir", True)], "lê os formatos")
        e = o.com_passos({"pedido": "x"}, ["[ ] a", "[ ] b", "[ ] c"])
        e = o.com_passos(e, feitos=[1, 3])
        eq([x["feito"] for x in e["passos"]], [True, False, True], "marca por número")
        e = o.com_passos(e, feitos=["B"])
        ok(all(x["feito"] for x in e["passos"]), "e por texto")
        eq(len(o.ler_passos([f"[ ] {i}" for i in range(40)])), o.PASSOS_MAX, "teto de passos")

    # ---- the block ---------------------------------------------------------------------------------------------
    def t_bloco_curto_estavel_e_com_a_regra(self):
        o = self.o
        e = o.com_passos(o.nova_mensagem({}, "Monta a planilha dos 30 leads", "m1", agora=1),
                         ["[x] achar os leads", "[ ] montar a planilha"])
        b = o.bloco(e, "matheus", pelo_celular=False)
        for esperado in ("«Monta a planilha dos 30 leads»", "1. [x] achar os leads", "2. [ ] montar a planilha",
                         "(1 de 2 feitos)", "Termine o pedido inteiro", "do Matheus decidir", "dinheiro",
                         "envio a terceiros", "apagar", "captcha", "credencial", "\"e aí?\""):
            ok(esperado in b, f"falta {esperado!r}: {b}")
        ok(b == o.bloco(dict(e), "matheus"), "mesmo estado, mesmo texto (cache)")
        ok(len(b) < 1200, f"curto: {len(b)}")
        ok(not any(c.isdigit() and ":" in b[i:i + 3] for i, c in enumerate(b)), "sem hora")
        ok("da pessoa decidir" in o.bloco(e, "ilia"), "convidado: 'da pessoa'")
        ok(o.bloco({}, "matheus") == "", "sem pedido, sem bloco")
        celular = o.bloco(e, "matheus", pelo_celular=True)
        ok("\"e aí?\"" not in celular, "no celular a regra do 'e aí?' já está no _60_conversa_whatsapp")
        if WHATS.exists():
            regras = WHATS.read_text(encoding="utf-8")
            ok("pedido de estado" in regras and "e aí?" in regras, "a regra que o bloco não repete no celular existe lá")

    def t_so_conversa_de_pessoa(self):
        o = self.o
        ok(o.conversa_de_pessoa(Agente()), "conversa do app do Matheus")
        ok(o.conversa_de_pessoa(Agente(Contexto(dono="ilia", whatsapp_de="ilia"))), "convidado no celular")
        ok(not o.conversa_de_pessoa(Agente(Contexto(id="ctxROTINA"))), "rotina (tasks.json)")
        ok(not o.conversa_de_pessoa(Agente(Contexto(tipo=Tipo.TASK))), "contexto de tarefa")
        ok(not o.conversa_de_pessoa(Agente(Contexto(gatilhos_de="x"))), "conversa de gatilho")
        ok(not o.conversa_de_pessoa(Agente(number=1)), "ajudante")

    # ---- the whole flow, with cache_prompt -------------------------------------------------------------------
    async def t_fluxo_com_o_cache_prompt(self):
        hook, extra, _ = self._modulos()
        cache = _carregar("ov_cache", CACHE).ExtrasNoHistorico if CACHE.exists() else None
        a = Agente()
        m = self._mensagem(hook, a, "Monta a planilha dos 30 leads e manda pro meu e-mail")
        estado = a.context.get_data("objetivo_vivo")
        eq(estado["msg_id"], m.id, "guarda a mensagem do pedido (o resumo_seguro não resume dali em diante)")
        b = await self._passo(extra, cache, a)
        ok("«Monta a planilha dos 30 leads e manda pro meu e-mail»" in b, b)
        if cache is None:
            return
        ok("objetivo_vivo" in a.history.msgs[-1].content, "entra no fim do histórico")
        n = len(a.history.msgs)
        await self._passo(extra, cache, a)
        eq(len(a.history.msgs), n, "igual: não entra de novo (começo do prompt estável)")
        self._mensagem(hook, a, "e aí?", intervencao=True)
        await self._passo(extra, cache, a)
        eq(len(a.history.msgs), n + 1, "'e aí?' não troca o objetivo: só a mensagem dele entrou")
        self._mensagem(hook, a, "Agora vê a agenda de amanhã")
        await self._passo(extra, cache, a)
        ok("«Agora vê a agenda de amanhã»" in a.history.msgs[-1].content, "pedido novo: bloco novo no fim")

    async def t_rotina_sem_bloco(self):
        hook, extra, ferramenta = self._modulos()
        a = Agente(Contexto(id="ctxROTINA"))
        self._mensagem(hook, a, "## Task:\nRadar")
        self._mensagem(hook, a, "Faz o radar")
        ok(a.context.get_data("objetivo_vivo") is None, "rotina não guarda objetivo")
        eq(await self._passo(extra, None, a), "", "nem põe bloco")
        ok("rotina" in ferramenta.executar(a, ["[ ] a"]), "a ferramenta diz que aqui não há objetivo")

    async def t_ferramenta_passos(self):
        hook, extra, f = self._modulos()
        a = Agente(Contexto(dono="matheus", whatsapp_de="matheus"))
        ok("Ainda não há pedido" in f.executar(a, ["[ ] a"]), "sem pedido")
        self._mensagem(hook, a, "Baixa o relatório do Meta e me manda")
        r = f.executar(a, ["[x] abrir o Meta", "[ ] baixar o relatório", "[ ] mandar no celular"])
        ok("Falta(m) 2" in r and "sem parar" in r, r)
        ok("2. [ ] baixar o relatório" in await self._passo(extra, None, a), "o bloco mostra os passos")
        r = f.executar(a, None, [2, 3])
        ok("Todos os passos feitos" in r, r)
        ok("(3 de 3 feitos)" in await self._passo(extra, None, a), "marcados")
        ok("Pedido atual" in f.executar(a), "sem argumentos: mostra o objetivo")
        ok("Nenhum passo válido" in f.executar(a, ["", "  "]), "lista vazia é recusada")
        prompt = (RAIZ / "prompts" / "agent.system.tool.passos.md").read_text(encoding="utf-8")
        esquema = json.loads(prompt.split("Input schema for tool_args:", 1)[1].split("\n", 1)[0])
        ok(set(esquema["properties"]) == {"passos", "feitos"}, "esquema com os argumentos da ferramenta")
        ok(len(prompt) < 1200, f"descrição curta (ela vai em toda chamada): {len(prompt)}")

    async def t_juiz_do_pronto(self):
        """21/10: o agente disse que o rascunho ia para o Matheus e o campo Para estava vazio."""
        j = _carregar("objetivo_vivo_juiz_teste", RAIZ / "helpers" / "juiz.py")
        Item = lambda tipo, cabeca="", conteudo="", args=None: types.SimpleNamespace(  # noqa: E731
            type=tipo, heading=cabeca, content=conteudo, kvps={"tool_args": args} if args else {})
        log = [Item("user", conteudo="pedido antigo"), Item("tool", "browser", "velho"),
               Item("user", conteudo="manda o e-mail com a planilha"),
               Item("agent", "pensando"),
               Item("tool", "A0: Using browser", '{"currentUrl": "outlook"}', {"action": "click", "ref": 8}),
               Item("tool", "A0: Using browser", "rascunho aberto", {"action": "type", "text": "NCM"}),
               Item("tool", "A0: Using browser", "Não foi possível anexar", {"action": "upload_file"}),
               Item("warning", "Possível loop", "repetiu")]
        p = j.provas(log)
        eq(len(p), 4, "só os passos depois da última mensagem dele, sem pensamento")
        ok(p[0].startswith("[tool]") and '"click"' in p[0] and "velho" not in " ".join(p), f"provas: {p}")
        estado = {"pedido": "manda o e-mail com a planilha", "msg_id": "m1"}
        ok(j.deve_julgar(estado, p, None), "pedido com 3 passos: julga")
        ok(not j.deve_julgar(estado, p[:2] + ["[warning] x"], None), "menos de 3 passos de ferramenta: não julga")
        ok(not j.deve_julgar({"pedido": ""}, p, None), "sem pedido: não julga")
        ok(not j.deve_julgar(estado, p, {"msg_id": "m1", "vezes": 2}), "já barrou 2 vezes este pedido: deixa sair")
        ok(j.deve_julgar(estado, p, {"msg_id": "m0", "vezes": 2}), "pedido novo: conta de novo")
        eq(j.contar(estado, {"msg_id": "m1", "vezes": 1}), {"msg_id": "m1", "vezes": 2}, "conta por pedido")
        eq(j.veredito('ok: {"pronto": false, "falta": "o Para está vazio"}'), {"pronto": False, "falta": "o Para está vazio"},
           "lê o JSON no meio do texto")
        eq(j.veredito("não sei"), None, "sem JSON: deixa sair")
        eq(j.veredito('{"pronto": "talvez"}'), None, "pronto que não é sim/não: deixa sair")
        ok("PEDIDO DA PESSOA" in j.entrada("x", p, "Enviado.") and "Enviado." in j.entrada("x", p, "Enviado."),
           "a entrada tem pedido, provas e resposta")

        # o gancho, com o modelo simulado
        stubs_err = types.ModuleType("helpers.errors")

        class RepairableException(Exception):
            pass

        stubs_err.RepairableException = RepairableException
        sys.modules["helpers.errors"] = stubs_err
        try:
            ext = _carregar("objetivo_vivo_juiz_ext_teste", EXT / "tool_execute_before" / "_40_juiz_do_pronto.py")
        finally:
            sys.modules.pop("helpers.errors", None)
        ext.carregar.objetivo().TAREFAS = self.o.TAREFAS

        def agente(resposta_do_juiz, number=0):
            a = Agente(Contexto(dono="matheus", objetivo_vivo=estado), number=number)
            a.context.log = types.SimpleNamespace(logs=log)
            a.chamadas = 0

            async def call_utility_model(system="", message="", **k):
                a.chamadas += 1
                if isinstance(resposta_do_juiz, Exception):
                    raise resposta_do_juiz
                return resposta_do_juiz
            a.call_utility_model = call_utility_model
            return a

        a = agente('{"pronto": false, "falta": "o campo Para do rascunho está vazio"}')
        for vez in (1, 2):
            try:
                await ext.JuizDoPronto(a).execute(tool_args={"text": "Enviado para o Matheus."}, tool_name="response")
                ok(False, "deveria barrar a resposta")
            except RepairableException as exc:
                ok("NÃO foi enviada" in str(exc) and "Para do rascunho" in str(exc), f"recado: {exc}")
        eq(a.context.get_data(j.CHAVE), {"msg_id": "m1", "vezes": 2}, "contou duas")
        await ext.JuizDoPronto(a).execute(tool_args={"text": "Enviado."}, tool_name="response")
        eq(a.chamadas, 2, "na 3ª vez nem chama o juiz: a resposta sai")
        a = agente('{"pronto": true, "falta": ""}')
        await ext.JuizDoPronto(a).execute(tool_args={"text": "Enviado, conferido em Itens Enviados."}, tool_name="response")
        eq(a.chamadas, 1, "pronto: sai")
        a = agente(RuntimeError("modelo fora do ar"))
        await ext.JuizDoPronto(a).execute(tool_args={"text": "x"}, tool_name="response")
        eq(a.chamadas, 1, "juiz falhou: a resposta sai")
        a = agente('{"pronto": false, "falta": "x"}', number=1)
        await ext.JuizDoPronto(a).execute(tool_args={"text": "x"}, tool_name="response")
        eq(a.chamadas, 0, "ajudante: não julga")
        a = agente('{"pronto": false, "falta": "x"}')
        await ext.JuizDoPronto(a).execute(tool_args={"action": "click"}, tool_name="browser")
        eq(a.chamadas, 0, "outra ferramenta: não julga")

    async def rodar(self, so: str = "") -> dict:
        for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
            try:
                r = getattr(self, nome)()
                if inspect.isawaitable(r):
                    await r
                self.resultados.append({"teste": nome, "ok": True})
            except Exception as exc:
                self.resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                        "onde": traceback.format_exc()[-600:]})
        passou = sum(1 for r in self.resultados if r["ok"])
        return {"passou": passou, "total": len(self.resultados), "resultados": self.resultados}


if __name__ == "__main__":
    r = asyncio.run(Suite().rodar(sys.argv[1] if len(sys.argv) > 1 else ""))
    for x in r["resultados"]:
        if not x["ok"]:
            print("✗", x["teste"], x["erro"], x["onde"])
    print(f"{r['passou']}/{r['total']}")
