"""Tests of helpers/compressao.py (summarize less often and deeper, never the task in progress) and of the
structured summary prompt. Mixed into tests/suite.py.

Two history implementations: a small fake that follows Agent Zero's helpers/history.py (Message/Topic/Bulk/History,
always available, e.g. in CI) and the real helpers/history.py when its source is around (in the container, or
AGENT_ZERO_SRC / /home/user/src/agent-zero), with its heavy imports stubbed. t_prova_quantas_compressoes compares,
on a long fake conversation, how many compressions Agent Zero's own History.compress does and how many this one does."""

import hashlib
import importlib.util
import json
import math
import os
import sys
import tempfile
import types
from contextlib import contextmanager
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CTX = "ctxCOMP1"
LIMITE = 50_000  # tokens: ctx_length 200.000 x ctx_history 0,25, as on the VM
_LIM = {"v": LIMITE}  # the limit in use (the proof also tries a bigger ctx_history)
NUCLEO = {  # core files the plugin overrides, as they were when the overrides were written (20/10)
    "extensions/python/message_loop_end/_10_organize_history.py": "38f8222cdfd7b81216f251a0f9ccffe6",
    "extensions/python/message_loop_prompts_before/_90_organize_history_wait.py": "67051c4aeceb3093a7663fd30e81e80b",
    "helpers/history.py": "c2358e98f675712e8b811e39e2625c00",
    # the override rests on these: plugin paths before the core ones, and "first file name wins"
    "helpers/extension.py": "fab6d68b7b232120a371d5618a4d6c15",
    "helpers/subagents.py": "165482f3dfa1cc48bd1ab83622dbcd85",
}


class Falha(AssertionError):
    pass


def ok(cond, msg):
    if not cond:
        raise Falha(msg)


def _fonte_a0() -> Path | None:
    for raiz in (Path("/a0"), Path(os.environ.get("AGENT_ZERO_SRC", "/home/user/src/agent-zero"))):
        if (raiz / "helpers" / "history.py").exists():
            return raiz
    return None


def _tok(texto: str) -> int:
    return len(texto) // 4


# ---- fake helpers/history.py (same shapes and the same compress as Agent Zero's) -------------------------------

def _historia_falsa():
    m = types.ModuleType("historia_falsa")

    def _str(c):
        return c if isinstance(c, str) else json.dumps(c, ensure_ascii=False, separators=(",", ":"))

    def output_text(msgs, ai_label="ai", human_label="human"):
        return "\n".join(f"{ai_label if o['ai'] else human_label}: {_str(o['content'])}" for o in msgs)

    class Message:
        def __init__(self, ai, content, id="", n=[0]):
            n[0] += 1
            self.ai, self.content, self.id, self.summary = ai, content, id or f"m{n[0]}", ""
            self.tokens = _tok(output_text(self.output()))

        def get_tokens(self):
            return self.tokens

        def set_summary(self, s):
            self.summary = s
            self.tokens = _tok(output_text(self.output()))

        def output(self):
            return [{"ai": self.ai, "content": self.summary or self.content, "id": self.id}]

    class Topic:
        def __init__(self, history):
            self.history, self.summary, self.messages = history, "", []

        def get_tokens(self):
            return _tok(self.summary) if self.summary else sum(x.get_tokens() for x in self.messages)

        def output(self):
            return [{"ai": False, "content": self.summary}] if self.summary else [o for x in self.messages for o in x.output()]

        async def compress(self):
            return await self.compress_attention()

        async def compress_attention(self, ratio=0.65):
            middle = len(self.messages) - 2
            if middle < 2:
                return False
            cnt = middle - math.floor(middle * ratio)
            if cnt < 1:
                return False
            txt = [output_text(x.output()) for x in self.messages[1:cnt + 1]]
            ag = self.history.agent
            s = await ag.call_utility_model(system=ag.read_prompt("fw.topic_summary.sys.md"),
                                            message=ag.read_prompt("fw.topic_summary.msg.md", content=txt))
            self.messages[1:cnt + 1] = [Message(False, {"messages_summary": s})]
            return True

    class Bulk:
        def __init__(self, history):
            self.history, self.summary, self.records = history, "", []

        def get_tokens(self):
            return _tok(self.summary) if self.summary else sum(r.get_tokens() for r in self.records)

        def output(self):
            return [{"ai": False, "content": self.summary}] if self.summary else [o for r in self.records for o in r.output()]

        async def summarize(self):
            ag = self.history.agent
            self.summary = await ag.call_utility_model(system=ag.read_prompt("fw.topic_summary.sys.md"),
                                                       message=ag.read_prompt("fw.topic_summary.msg.md",
                                                                              content=output_text(self.output())))

    class History:
        def __init__(self, agent):
            self.agent, self.bulks, self.topics = agent, [], []
            self.current = Topic(self)
            self.compress_calls = 0

        def _get_ctx_size_for_history(self):
            return _LIM["v"]

        def get_tokens(self):
            return sum(r.get_tokens() for r in self.bulks + self.topics + [self.current])

        def is_over_limit(self):
            return self.get_tokens() > _LIM["v"]

        def new_topic(self):
            if self.current.messages:
                self.topics.append(self.current)
                self.current = Topic(self)

        def add_message(self, ai, content, id=""):
            msg = Message(ai, content, id)
            self.current.messages.append(msg)
            return msg

        def output(self):
            return [o for r in self.bulks + self.topics + [self.current] for o in r.output()]

        async def compress(self):  # a reduced Agent Zero History.compress: current topic first when it is big
            self.compress_calls += 1
            if self.get_tokens() <= _LIM["v"]:
                return False
            alvo, mudou = _LIM["v"] * 0.8, False
            while self.get_tokens() > alvo:
                if self.current.get_tokens() > 0.5 * alvo and await self.current.compress_attention():
                    mudou = True
                    continue
                if self.topics:
                    b = Bulk(self)
                    b.records = self.topics[:3]
                    await b.summarize()
                    self.bulks.append(b)
                    self.topics[:3] = []
                    mudou = True
                    continue
                if len(self.bulks) > 1:
                    self.bulks.pop(0)
                    mudou = True
                    continue
                break
            return mudou

    m.Message, m.Topic, m.Bulk, m.History, m.output_text = Message, Topic, Bulk, History, output_text
    return m


# ---- the real helpers/history.py with its imports stubbed ---------------------------------------------------------

@contextmanager
def _stubs_a0():
    mod = types.ModuleType
    helpers, lc, lcm = mod("helpers"), mod("langchain_core"), mod("langchain_core.messages")
    tokens, mc, msgs = mod("helpers.tokens"), mod("plugins._model_config.helpers.model_config"), mod("helpers.messages")
    agente = mod("agent")
    agente.Agent = type("Agent", (), {})
    tokens.approximate_tokens = _tok
    msgs.truncate_dict_by_ratio = lambda agent, c, a, b: (c[: int(a)] if isinstance(c, str) else
                                                          {k: (v[: int(a)] if isinstance(v, str) else v) for k, v in c.items()})
    for nome in ("settings", "call_llm"):
        setattr(helpers, nome, mod(f"helpers.{nome}"))
    helpers.tokens, helpers.messages = tokens, msgs
    for nome in ("BaseMessage", "HumanMessage", "SystemMessage", "AIMessage"):
        setattr(lcm, nome, type(nome, (), {}))
    mc.get_chat_model_config = lambda agent=None: {"ctx_length": 200_000, "ctx_history": _LIM["v"] / 200_000}
    stubs = {"helpers": helpers, "helpers.tokens": tokens, "helpers.messages": msgs, "langchain_core": lc,
             "langchain_core.messages": lcm, "plugins": mod("plugins"), "plugins._model_config": mod("plugins._model_config"),
             "plugins._model_config.helpers": mod("plugins._model_config.helpers"),
             "plugins._model_config.helpers.model_config": mc, "agent": agente}
    antes = {k: sys.modules.get(k) for k in stubs}
    sys.modules.update(stubs)
    try:
        yield
    finally:
        for k, v in antes.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _historia_real():
    raiz = _fonte_a0()
    if raiz is None:
        return None
    with _stubs_a0():
        spec = importlib.util.spec_from_file_location("resumo_seguro_history_real", raiz / "helpers" / "history.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
    return m


# ---- fake agent and conversation ------------------------------------------------------------------------------

class Agente:
    def __init__(self, h, respostas=None, sistema="# AI role\nresumo"):
        self.number = 0
        self.context = types.SimpleNamespace(id=CTX, data={})
        self.context.get_data = self.context.data.get
        self.history = h.History(agent=self)
        self.sistema, self.respostas, self.chamadas = sistema, list(respostas or []), []

    def read_prompt(self, file, **kw):
        if file == "fw.topic_summary.sys.md":
            return self.sistema
        if file == "fw.topic_summary.msg.md":
            return "# Message history to summarize:\n" + str(kw.get("content"))
        raise FileNotFoundError(file)

    def parse_prompt(self, file, **kw):
        return {"messages_summary": kw["summary"]}

    async def call_utility_model(self, system, message, **kw):
        self.chamadas.append((system, message))
        if self.respostas:
            r = self.respostas.pop(0)
            if isinstance(r, Exception):
                raise r
            if callable(r):
                return r(message)
            return r
        return "## Objetivo atual\n«resumo de teste»\n## Feito\n1. coisas\n## Pendente\n—\n## Próximos passos\n—\n" \
               "## Decisões e preferências ditas nesta conversa\n—"

    def pedido(self, texto, mid=None, intervencao=False):
        self.history.new_topic()
        chave = "user_intervention" if intervencao else "user_message"
        msg = self.history.add_message(False, {chave: texto}, id=mid or "")
        return msg

    def passo(self, i, tamanho, ferramenta="code_execution_tool"):
        self.history.add_message(True, json.dumps({"thoughts": [f"passo {i} marca<{i}> " + "pensando " * 60],
                                                   "tool_name": ferramenta, "tool_args": {"n": i}}))
        corpo = (f"resultado {i} @lead_{i:03d} acao_id={i:06x}ab " + "linha de saída " * (tamanho // 15))[:tamanho]
        self.history.add_message(False, {"tool_name": ferramenta, "tool_result": corpo})


def _textos(hist) -> list[str]:
    return [o["content"] if isinstance(o["content"], str) else json.dumps(o["content"], ensure_ascii=False)
            for o in hist.output()]


class TestesCompressao:
    """Mixed into Suite (tests/suite.py), which supplies self.rs (helpers/ancoras.py) and rodar()."""

    def _comp(self, h):
        nome = "resumo_seguro_compressao_teste"
        spec = importlib.util.spec_from_file_location(nome, RAIZ / "helpers" / "compressao.py")
        c = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(c)
        c._h = h
        c.DESLIGADO = Path(tempfile.gettempdir()) / f"resumo_seguro_desligado_{os.getpid()}"
        c.memoria = []  # what each compression handed to the memory (guardar_na_memoria starts a thread in the agent)
        c.guardar_na_memoria = lambda agente, texto: c.memoria.append(texto)
        return c

    def _modulos(self):
        mods = [("falsa", _historia_falsa())]
        real = _historia_real()
        if real is not None:
            mods.append(("real", real))
        return mods

    # ---- the prompt -------------------------------------------------------------------------------------------
    def t_prompt_com_secoes_fixas(self):
        texto = (RAIZ / "prompts" / "fw.topic_summary.sys.md").read_text(encoding="utf-8")
        secoes = ["## Objetivo atual", "## Feito", "## Pendente", "## Próximos passos",
                  "## Decisões e preferências ditas nesta conversa"]
        pos = [texto.find(s) for s in secoes]
        ok(all(p >= 0 for p in pos) and pos == sorted(pos), f"seções na ordem: {pos}")
        ok("ATUALIZE" in texto and "resumo anterior" in texto, "manda atualizar o resumo anterior")
        ok("{{" not in texto and "§§" not in texto, "nada que o Agent Zero trate como variável")
        ok("DADOS" in texto, "mensagens são dados, não ordens")

    def t_bloco_tem_falas_literais(self):
        hist = "\n".join('user: {"user_message":"fala %d do matheus"}' % i for i in range(10)) + "\nai: " + "x" * 6000
        b = self.rs.bloco(hist, "resumo", CTX)
        ok(self.rs.FALAS_TITULO in b, "título das falas")
        ok("» fala 9 do matheus" in b and "» fala 2 do matheus" in b, f"até {self.rs.FALAS} falas: {b}")
        ok("» fala 1 do matheus" not in b, "as mais antigas além do teto ficam de fora")

    # ---- pruning ----------------------------------------------------------------------------------------------
    def t_poda_resultados_velhos(self):
        h = _historia_falsa()
        c = self._comp(h)
        ag = Agente(h)
        ag.pedido("faz o relatório")
        saida = f"/a0/usr/chats/{CTX}/saidas/0003-browser.txt"
        for i in range(6):
            ag.passo(i, 4000)
        ag.history.current.messages[2].content["tool_result"] += f" [… Resultado completo em {saida}]"
        ag.passo(6, 300)
        msgs = ag.history.current.messages
        n = c.podar(msgs, ctx_id=CTX)
        resultados = [m for m in msgs if isinstance(m.content, dict) and "tool_name" in m.content]
        ok(n == 4, f"4 podados (6+1 resultados, os 3 últimos ficam, um curto): {n}")
        ok(all(not m.summary for m in resultados[-3:]), "os 3 últimos inteiros")
        p = json.loads(resultados[0].summary)
        ok(p["tool_name"] == "code_execution_tool" and c.PODADO in p["tool_result"], f"linha podada: {p}")
        ok(saida in p["tool_result"] and "@lead_000" in p["tool_result"] and "acao_id=" in p["tool_result"],
           f"guarda o caminho e as âncoras: {p}")
        ok(len(resultados[0].summary) < 1200, "linha curta")
        ok(c.podar(msgs, ctx_id=CTX) == 0, "podar de novo não muda nada")

    # ---- compression ------------------------------------------------------------------------------------------
    async def _cenario(self, h, c, com_pedido=True):
        ag = Agente(h)
        for t in range(8):  # 8 old requests, each with some work
            ag.pedido(f"pedido antigo {t}")
            for i in range(12):  # short results (not pruned): only a summary makes room
                ag.passo(t * 100 + i, 1400)
        m = ag.pedido("Monta a planilha dos 30 leads e manda pro meu e-mail", mid="pedido-atual")
        if com_pedido:
            ag.context.data["objetivo_vivo"] = {"msg_id": m.id}
        for i in range(5):
            ag.passo(1000 + i, 3000)
        ag.pedido("e aí?", intervencao=True)
        for i in range(3):
            ag.passo(2000 + i, 3000)
        return ag

    async def t_tarefa_em_andamento_fica_inteira(self):
        for nome, h in self._modulos():
            c = self._comp(h)
            with _stubs_a0():
                ag = await self._cenario(h, c)
                hist = ag.history
                ok(hist.get_tokens() > LIMITE, f"{nome}: cenário passa do limite ({hist.get_tokens()})")
                ok(await c.comprimir(ag), f"{nome}: comprimiu")
            textos = _textos(hist)
            ok(len(ag.chamadas) == 1, f"{nome}: uma chamada de resumo: {len(ag.chamadas)}")
            ok(len(hist.bulks) == 1 and hist.bulks[0].summary.startswith(c.CABECA), f"{nome}: um resumo só")
            ok(hist.get_tokens() <= LIMITE * c.ALVO + 1500, f"{nome}: fundo, perto de 45%: {hist.get_tokens()}")
            ok(any("Monta a planilha" in t for t in textos) and any('"e aí?"' in t for t in textos),
               f"{nome}: o pedido atual e o 'e aí?' inteiros")
            ok(not any("pedido antigo 0" in t for t in textos[1:]), f"{nome}: o começo foi para o resumo")
            atual = next(i for i, t in enumerate(textos) if "Monta a planilha" in t)
            ok(all(c.PODADO not in t for t in textos[-3 * 2:]), f"{nome}: os últimos resultados inteiros")
            ok(sum(f"marca<{i}>" in t for t in textos[atual:] for i in range(1000, 1005)) == 5,
               f"{nome}: nenhum passo da tarefa resumido")
            entrada = ag.chamadas[0][1]
            ok("pedido antigo 0" in entrada and "Monta a planilha" not in entrada,
               f"{nome}: o resumo recebe só o que veio antes da tarefa")

    async def t_memoria_antes_do_resumo(self):
        h = _historia_falsa()
        c = self._comp(h)
        with _stubs_a0():
            ag = await self._cenario(h, c)
            await c.comprimir(ag)
        ok(len(c.memoria) == 1, f"uma ida à memória por resumo: {len(c.memoria)}")
        ok("pedido antigo 0" in c.memoria[0] and "Monta a planilha" not in c.memoria[0],
           "a memória recebe o que vai ser resumido, não a tarefa que fica inteira")
        ok(len(c.memoria[0]) <= c.FLUSH_MAX, "dentro do teto")
        h = _historia_falsa()
        c = self._comp(h)
        with _stubs_a0():
            ag = await self._cenario(h, c)
            ag.respostas = [RuntimeError("modelo fora")]
            try:
                await c.comprimir(ag)
            except Exception:
                pass
        ok(c.memoria == [], "resumo que falha não leva nada à memória (nada saiu do histórico)")

    async def t_memorizar_salva_com_os_filtros_do_agent_zero(self):
        h = _historia_falsa()
        c = self._comp(h)
        salvas, apagadas = [], []
        cfg = {"memory_memorize_enabled": True, "memory_memorize_replace_threshold": 0.9}

        class Db:
            async def delete_documents_by_query(self, query, threshold, filter):
                apagadas.append((query, threshold, filter))
                return []

            async def insert_text(self, text, metadata):
                salvas.append((text, metadata))

        class Memory:
            class Area:
                FRAGMENTS = types.SimpleNamespace(value="fragments")

            @staticmethod
            async def get(agente):
                return Db()

        mods = {n: types.ModuleType(n) for n in ("helpers", "helpers.plugins", "helpers.dirty_json", "plugins",
                                                  "plugins._memory", "plugins._memory.helpers",
                                                  "plugins._memory.helpers.memory", "plugins._memory.helpers.memory_quality")}
        mods["helpers.plugins"].get_plugin_config = lambda nome, agente: cfg
        mods["helpers.dirty_json"].DirtyJson = types.SimpleNamespace(parse_string=json.loads)
        mods["plugins._memory.helpers.memory"].Memory = Memory
        mods["plugins._memory.helpers.memory_quality"].filter_auto_memory_fragments = \
            lambda ms: [m for m in ms if "efêmero" not in m]
        mods["helpers"].plugins, mods["helpers"].dirty_json = mods["helpers.plugins"], mods["helpers.dirty_json"]
        antes = {k: sys.modules.get(k) for k in mods}
        sys.modules.update(mods)
        try:
            ag = Agente(h, respostas=['["Matheus prefere planilha no Drive", "status efêmero da tela"]'])
            ag.read_prompt = lambda f, **k: "extraia fatos duráveis" if f == "memory.memories_sum.sys.md" else ""
            n = await c.memorizar(ag, "user: guarda a planilha no Drive")
            ok(n == 1 and salvas == [("Matheus prefere planilha no Drive", {"area": "fragments"})],
               f"salva o fato durável, o filtro do Agent Zero tira o resto: {salvas}")
            ok(apagadas and apagadas[0][1] == 0.9, "quase-igual antigo é trocado (limiar da configuração)")
            ok(ag.chamadas[0] == ("extraia fatos duráveis", "user: guarda a planilha no Drive"),
               "mesmo prompt de extração do Agent Zero")
            cfg["memory_memorize_enabled"] = False
            ok(await c.memorizar(ag, "x") == 0 and len(ag.chamadas) == 1, "memória desligada: nem chama o modelo")
            cfg["memory_memorize_enabled"] = True
            ag.respostas = ["isso não é json"]
            ok(await c.memorizar(ag, "x") == 0, "resposta que não é JSON: nada salvo, sem erro")
        finally:
            for k, v in antes.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

    async def t_sem_pedido_guarda_desde_a_ultima_mensagem(self):
        for nome, h in self._modulos():
            c = self._comp(h)
            with _stubs_a0():
                ag = await self._cenario(h, c, com_pedido=False)
                await c.comprimir(ag)
            textos = _textos(ag.history)
            ok(any('"e aí?"' in t for t in textos), f"{nome}: a última mensagem fica")
            ok(sum(f"marca<{i}>" in t for t in textos for i in range(2000, 2003)) == 3,
               f"{nome}: e o que veio depois dela, inteiro")

    async def t_segundo_resumo_atualiza_o_primeiro(self):
        h = _historia_falsa()
        c = self._comp(h)
        ag = await self._cenario(h, c)
        await c.comprimir(ag)
        primeiro = ag.history.bulks[0]
        for t in range(6):
            ag.pedido(f"pedido novo {t}")
            for i in range(12):
                ag.passo(3000 + t * 100 + i, 1400)
        ag.context.data["objetivo_vivo"] = {"msg_id": ag.history.current.messages[0].id}
        ok(await c.comprimir(ag), "comprimiu de novo")
        entrada = ag.chamadas[-1][1]
        ok(entrada.startswith("# Resumo anterior (atualize"), f"pede para atualizar: {entrada[:80]}")
        ok(primeiro.summary in entrada, "com o resumo anterior inteiro")
        ok("pedido novo 0" in entrada and "pedido antigo 0" not in entrada.split("# Mensagens novas", 1)[1],
           "e só as mensagens novas, sem resumir o que já foi resumido")
        ok(len(ag.history.bulks) == 1 and ag.history.bulks[0].records[0] is primeiro,
           "continua um resumo só; o anterior fica guardado dentro dele")

    async def t_tarefa_gigante_usa_o_corte_do_agent_zero(self):
        h = _historia_falsa()
        c = self._comp(h)
        ag = Agente(h)
        ag.pedido("antigo")
        ag.passo(0, 2000)
        m = ag.pedido("tarefa enorme", mid="grande")
        ag.context.data["objetivo_vivo"] = {"msg_id": m.id}
        for i in range(130):
            ag.passo(i, 1400)  # short results: pruning does not help
        ok(ag.history.get_tokens() > LIMITE, "uma tarefa só passa do limite")
        ok(await c.comprimir(ag), "comprimiu")
        textos = _textos(ag.history)
        ok(ag.history.get_tokens() <= LIMITE, f"o contexto fica no limite: {ag.history.get_tokens()}")
        ok(any('"tarefa enorme"' in t for t in textos) and "marca<129>" in textos[-2],
           "o corte é dentro da tarefa: o pedido e os últimos passos ficam")
        ok(any("messages_summary" in t for t in textos), "o meio da tarefa é que foi resumido (só neste caso)")

    async def t_topico_atual_vazio_nao_leva_a_tarefa(self):
        """Seen on the VM (helper chats): the current topic is empty and the task is the last old topic."""
        h = _historia_falsa()
        c = self._comp(h)
        ag = Agente(h)
        ag.pedido("antigo")
        ag.passo(0, 1400)
        m = ag.pedido("a tarefa", mid="t1")
        ag.context.data["objetivo_vivo"] = {"msg_id": m.id}
        for i in range(120):
            ag.passo(10 + i, 1400)
        ag.history.new_topic()  # empty current topic
        ok(not ag.history.current.messages and ag.history.get_tokens() > LIMITE, "cenário")
        await c.comprimir(ag)
        textos = _textos(ag.history)
        ok(any('"a tarefa"' in t for t in textos), "a mensagem da tarefa não vai para o resumo")
        ok(ag.history.get_tokens() <= LIMITE, "e cabe no limite (corte do Agent Zero dentro do tópico)")

    async def t_resumo_que_falha_nao_perde_nada(self):
        h = _historia_falsa()
        c = self._comp(h)
        ag = await self._cenario(h, c)
        ag.respostas = [RuntimeError("Bedrock 503")]
        antes = len(ag.history.topics)
        try:
            await c.comprimir(ag)
            ok(ag.history.get_tokens() <= LIMITE, "sem erro só se a poda bastou")
        except RuntimeError:
            pass
        ok(len(ag.history.topics) == antes and not ag.history.bulks, "nenhuma mensagem trocada por resumo")
        ag.respostas = ["   "]
        try:
            await c.comprimir(ag)
        except Exception as exc:
            ok(type(exc).__name__ == "ResumoVazio" or ag.history.get_tokens() <= LIMITE, f"resumo vazio: {exc}")
        ok(not ag.history.bulks, "resumo vazio não apaga nada")

    async def t_mensagem_que_chega_durante_o_resumo_fica(self):
        h = _historia_falsa()
        c = self._comp(h)
        ag = await self._cenario(h, c)

        def no_meio(_msg):
            ag.pedido("NOVA no meio do resumo", intervencao=True)
            return "## Objetivo atual\nx"

        ag.respostas = [no_meio]
        await c.comprimir(ag)
        ok(any("NOVA no meio do resumo" in t for t in _textos(ag.history)), "a mensagem nova continua no histórico")
        ok(any('"e aí?"' in t for t in _textos(ag.history)), "e o tópico que virou antigo durante o resumo também")

    async def t_desligado_volta_ao_agent_zero(self):
        h = _historia_falsa()
        c = self._comp(h)
        ag = await self._cenario(h, c)
        c.DESLIGADO.write_text("")
        try:
            await c.comprimir(ag)
        finally:
            c.DESLIGADO.unlink()
        ok(ag.history.compress_calls == 1, "com o arquivo, só a compressão do Agent Zero")

    async def t_abaixo_do_limite_nao_mexe(self):
        h = _historia_falsa()
        c = self._comp(h)
        ag = Agente(h)
        ag.pedido("oi")
        ag.passo(1, 3000)
        ok(not await c.comprimir(ag) and not ag.chamadas, "nada a fazer")

    def t_nucleo_do_agent_zero_igual(self):
        """The two core extensions are replaced by copies here: if Agent Zero changes them (or history.py), the
        copies must be checked again before deploying."""
        raiz = _fonte_a0()
        if raiz is None:
            return
        for rel, md5 in NUCLEO.items():
            atual = hashlib.md5((raiz / rel).read_bytes()).hexdigest()
            ok(atual == md5, f"{rel} mudou no Agent Zero ({atual}): confira as cópias em resumo_seguro/extensions")

    def t_extensoes_com_o_nome_do_nucleo(self):
        for rel in list(NUCLEO)[:2]:
            ok((RAIZ / rel).exists(), f"falta {rel} (substitui o do núcleo pelo mesmo nome)")
            texto = (RAIZ / rel).read_text(encoding="utf-8")
            ok("compress_history" in texto and "helpers.history import" not in texto.split("def compress_history")[0]
               .replace("from helpers.history import clear_responses_provider_state", ""), f"{rel} usa a nossa")

    # ---- the proof ---------------------------------------------------------------------------------------------
    async def _simular(self, h, comprimir, n_pedidos=6, passos=45, limite=LIMITE):
        """A long chat: n requests, each with `passos` tool steps and an "e aí?" in the middle; Agent Zero runs the
        compression after every step (message_loop_end) while over the limit."""
        _LIM["v"] = limite
        try:
            return await self._simular_com(h, comprimir, n_pedidos, passos, limite)
        finally:
            _LIM["v"] = LIMITE

    async def _simular_com(self, h, comprimir, n_pedidos, passos, limite):
        ag = Agente(h)
        tamanhos = [1200, 4000, 6500, 2500, 8000, 1800]
        eventos = regravado = mexeu_na_tarefa = 0
        for p in range(n_pedidos):
            m = ag.pedido(f"Pedido {p}: faz a tarefa {p} inteira", mid=f"pedido-{p}")
            ag.context.data["objetivo_vivo"] = {"msg_id": m.id}
            for i in range(passos):
                if i == passos // 2:
                    ag.pedido("e aí?", intervencao=True)
                ag.passo(p * 100 + i, tamanhos[(p + i) % len(tamanhos)])
                if ag.history.get_tokens() > limite:
                    marcas = [f"marca<{p * 100 + j}>" for j in range(i + 1)]
                    antes = sum(any(mk in t for t in _textos(ag.history)) for mk in marcas)
                    passes = 0
                    while ag.history.get_tokens() > limite and passes < 64:
                        passes += 1
                        if not await comprimir(ag):
                            break
                    eventos += 1
                    regravado += ag.history.get_tokens()
                    depois = sum(any(mk in t for t in _textos(ag.history)) for mk in marcas)
                    if depois < antes:
                        mexeu_na_tarefa += 1
        return {"compressoes": eventos, "chamadas_de_resumo": len(ag.chamadas), "tokens_regravados": regravado,
                "resumiram_a_tarefa_em_andamento": mexeu_na_tarefa, "tokens_no_fim": ag.history.get_tokens()}

    async def t_prova_quantas_compressoes(self):
        """Printed for the report. Agent Zero's own compression vs this one, on fake chats of several shapes (requests
        x tool steps each, an "e aí?" in the middle of each), at the VM limit (50 mil tokens) and with ctx_history 0,4."""
        nome, h = self._modulos()[-1]  # the real Agent Zero history when available
        c = self._comp(h)
        soma = {"a0": {}, "nosso": {}}
        for limite in (LIMITE, 80_000):
            for n, passos in ((1, 150), (6, 45), (20, 8)):
                with _stubs_a0():
                    antes = await self._simular(h, lambda ag: ag.history.compress(), n, passos, limite)
                    depois = await self._simular(h, c.comprimir, n, passos, limite)
                print(f"resumo_seguro: prova ({nome}, limite {limite}, {n}x{passos}) Agent Zero {antes} -> nosso {depois}")
                ok(depois["tokens_no_fim"] <= limite, f"nunca passa do limite: {depois}")
                ok(depois["chamadas_de_resumo"] <= antes["chamadas_de_resumo"], f"não chama mais o resumo: {antes} {depois}")
                if passos < 100:  # a single 150-step task bigger than the limit is the one case it must summarize
                    ok(depois["resumiram_a_tarefa_em_andamento"] == 0, f"nunca resume a tarefa em andamento: {depois}")
                for k, v in antes.items():
                    soma["a0"][k] = soma["a0"].get(k, 0) + v
                for k, v in depois.items():
                    soma["nosso"][k] = soma["nosso"].get(k, 0) + v
        print(f"resumo_seguro: prova, somando tudo: {soma}")
        ok(soma["nosso"]["resumiram_a_tarefa_em_andamento"] * 3 <= soma["a0"]["resumiram_a_tarefa_em_andamento"],
           f"bem menos resumos da tarefa em andamento: {soma}")
