"""Tests of resumo_seguro (no model calls). Run with implantar.py (staging copy), inside the container, or from the
repository root: python3 infra/vm/plugins/resumo_seguro/tests/suite.py"""

import importlib.util
import inspect
import json
import math
import re
import sys
import traceback
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
EXT = RAIZ / "extensions" / "python" / "_functions" / "agent" / "Agent" / "call_utility_model" / "end" / "_50_ancoras.py"
PROMPT_A0 = Path("/a0/prompts/fw.topic_summary.sys.md")
SISTEMA = (PROMPT_A0.read_text(encoding="utf-8").rstrip("\n") if PROMPT_A0.exists()
           else "# AI role\nYou are AI summarization assistant")
CTX = "ctxTESTE1"
SAIDA = f"/a0/usr/chats/{CTX}/saidas/0007-browser.txt"


class Falha(AssertionError):
    pass


def ok(cond, msg):
    if not cond:
        raise Falha(msg)


def _carregar(nome: str, arquivo: Path):
    try:
        import helpers.extension  # noqa: F401  (inside the container)
    except Exception:
        sys.modules.setdefault("helpers", types.ModuleType("helpers"))
        ext = types.ModuleType("helpers.extension")
        ext.Extension = type("Extension", (), {})
        sys.modules["helpers.extension"] = ext
    spec = importlib.util.spec_from_file_location(nome, arquivo)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


_UNSET = object()


async def _extensible(func, extensoes, agent, **kwargs):
    """What helpers.extension.extensible does around an async method: call it, then the end extensions."""
    data = {"args": (agent,), "kwargs": kwargs, "result": _UNSET, "exception": None}
    try:
        data["result"] = await func(**kwargs)
    except Exception as exc:
        data["exception"] = exc
    for cls in extensoes:
        obj = cls.__new__(cls)  # real Extension takes agent=, the CI stub takes nothing
        obj.agent = agent
        r = obj.execute(data=data)
        if inspect.isawaitable(r):
            await r
    if isinstance(data["exception"], BaseException):
        raise data["exception"]
    return None if data["result"] is _UNSET else data["result"]


class AgenteFalso:
    def __init__(self, extensao, respostas):
        self.context = types.SimpleNamespace(id=CTX)
        self.number = 0
        self.extensoes = [extensao]
        self.respostas = list(respostas)
        self.chamadas = []

    def read_prompt(self, file, **kw):
        if file == "fw.topic_summary.sys.md":
            return SISTEMA
        if file == "fw.topic_summary.msg.md":
            return "# Message history to summarize:\n" + str(kw.get("content"))
        raise FileNotFoundError(file)

    def parse_prompt(self, file, **kw):
        return {"messages_summary": kw["summary"]}  # fw.msg_summary.md is a JSON template

    async def _modelo(self, system, message, callback=None, background=False):
        self.chamadas.append((system, message))
        r = self.respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    async def call_utility_model(self, system, message, callback=None, background=False):
        return await _extensible(self._modelo, self.extensoes, self, system=system, message=message,
                                 callback=callback, background=background)


def _txt(m):
    c = m["content"]
    return ("ai" if m["ai"] else "user") + ": " + (c if isinstance(c, str) else json.dumps(c, ensure_ascii=False, separators=(",", ":")))


class TopicoFalso:
    """The message list of a history topic and Topic.compress_attention of helpers/history.py, line by line."""

    def __init__(self, agent, mensagens):
        self.agent, self.messages = agent, mensagens

    async def compress_attention(self, ratio=0.0):
        middle = len(self.messages) - 2
        if middle < 2:
            return False
        cnt = middle - math.floor(middle * ratio)
        txt = [_txt(m) for m in self.messages[1: cnt + 1]]
        summary = await self.agent.call_utility_model(
            system=self.agent.read_prompt("fw.topic_summary.sys.md"),
            message=self.agent.read_prompt("fw.topic_summary.msg.md", content=txt))
        self.messages[1: cnt + 1] = [{"ai": False, "content": self.agent.parse_prompt("fw.msg_summary.md", summary=summary)}]
        return True


def _historia():
    return [
        {"ai": False, "content": {"user_message": "Roda a prospecção de hoje"}},
        {"ai": True, "content": '{"tool_name":"acao","tool_args":{"acao":"executar","acao_id":"3f2a1b"}}'},
        {"ai": False, "content": {"tool_name": "browser", "tool_result": "perfil @zen.marmitas, 1.234 seguidores. "
                                  f"[… Resultado completo (40.000 caracteres) em {SAIDA}. Se precisar, leia …]"}},
        {"ai": False, "content": {"user_intervention": "Não manda pro \"@doce.lar\" ainda, só amanhã às 9h"}},
        {"ai": True, "content": "Rotina laMIuaPt agendada; link https://raizconnect.com.br/materiais/precificacao/calculadora"},
        {"ai": True, "content": "Feito."},
    ]


def _history_real():
    """helpers/history.py of Agent Zero: the real one in the container; outside, the source (AGENT_ZERO_SRC or
    /home/user/src/agent-zero) loaded with its heavy imports stubbed (only tokens are counted, by length)."""
    try:
        from helpers import history
        if hasattr(history, "Topic"):
            return history
    except Exception:
        pass
    import os
    fonte = Path(os.environ.get("AGENT_ZERO_SRC", "/home/user/src/agent-zero")) / "helpers" / "history.py"
    if not fonte.exists():
        return None
    mod = types.ModuleType
    helpers, lc, lcm = mod("helpers"), mod("langchain_core"), mod("langchain_core.messages")
    tokens, mc = mod("helpers.tokens"), mod("plugins._model_config.helpers.model_config")
    tokens.approximate_tokens = lambda texto: len(texto) // 4
    for nome in ("messages", "settings", "call_llm"):
        setattr(helpers, nome, mod(f"helpers.{nome}"))
    helpers.tokens = tokens
    for nome in ("BaseMessage", "HumanMessage", "SystemMessage", "AIMessage"):
        setattr(lcm, nome, type(nome, (), {}))
    mc.get_chat_model_config = lambda agent=None: {}
    stubs = {"helpers": helpers, "helpers.tokens": tokens, "langchain_core": lc, "langchain_core.messages": lcm,
             "plugins": mod("plugins"), "plugins._model_config": mod("plugins._model_config"),
             "plugins._model_config.helpers": mod("plugins._model_config.helpers"),
             "plugins._model_config.helpers.model_config": mc}
    antes = {k: sys.modules.get(k) for k in stubs}
    sys.modules.update(stubs)
    try:
        return _carregar("resumo_seguro_history_a0", fonte)
    finally:
        for k, v in antes.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


class Suite:
    def __init__(self):
        self.rs = _carregar("resumo_seguro_ancoras_teste", RAIZ / "helpers" / "ancoras.py")
        self.ext = _carregar("resumo_seguro_ext_teste", EXT).Ancoras
        self.resultados = []

    # ---- anchors -------------------------------------------------------------------------------------------
    def t_extrai_ancoras(self):
        texto = (
            "ai: abri https://instagram.com/zen.marmitas/ e mandei a DM ao @zen.marmitas (acao_id 3f2a1b).\n"
            'ai: {"tool_name":"acao","tool_args":{"acao_id":"9c8d7e"}}\n'
            "user: a ação 4b5c6d deu certo? manda pra fulano@gmail.com\n"
            f"user: resultado em {SAIDA}. Outro: /a0/usr/prospeccao/matheus.json\n"
            'ai: {"uuid":"nW924Nkj"} e rotina laMIuaPt; tarefa agendada; id 123e4567-e89b-12d3-a456-426614174000\n'
            "ai: @property no código; https://api.telegram.org/bot1/x?token=SEGREDO e https://x.io/a?code=1\n"
        )
        a = self.rs.ancoras(texto, CTX)
        ok(a[0] == SAIDA, f"o arquivo de saidas vem primeiro: {a}")
        for esperado in ("acao_id=3f2a1b", "acao_id=9c8d7e", "acao_id=4b5c6d", "uuid=nW924Nkj", "uuid=laMIuaPt",
                         "uuid=123e4567-e89b-12d3-a456-426614174000", "@zen.marmitas",
                         "https://instagram.com/zen.marmitas/", "/a0/usr/prospeccao/matheus.json"):
            ok(esperado in a, f"falta {esperado}: {a}")
        ok(not any("gmail" in x for x in a), "e-mail não vira @")
        ok("uuid=agendada" not in a and "@property" not in a, f"palavra comum não vira âncora: {a}")
        ok(not any("SEGREDO" in x or "code=" in x for x in a), "URL com token/código fica de fora")
        ok(a.index("acao_id=9c8d7e") < a.index("@zen.marmitas") < a.index("https://instagram.com/zen.marmitas/"),
           f"ordem: ids, @, links: {a}")

    def t_ancoras_em_json_escapado(self):
        # a summary of a summary: the block went through json.dumps once more
        interno = json.dumps({"messages_summary": "falamos do lead\n@doce.lar e do acao_id\":\"abc123\" em\n" + SAIDA},
                             ensure_ascii=False)
        a = self.rs.ancoras("user: " + interno, CTX)
        ok("@doce.lar" in a and SAIDA in a and "acao_id=abc123" in a, f"âncoras dentro de JSON escapado: {a}")

    def t_rodape_nao_vira_ancora(self):
        b = self.rs.bloco(f"ai: veja {SAIDA} e @zen.marmitas " + "x" * 3000, "resumo", CTX)
        a = self.rs.ancoras(b, CTX)
        ok(f"/a0/usr/chats/{CTX}/chat.json" not in a and f"/a0/usr/chats/{CTX}/saidas/" not in a, f"rodapé: {a}")

    # ---- the person's words --------------------------------------------------------------------------------
    def t_falas_literais(self):
        msgs = [_txt(m) for m in _historia()]
        entrada = self.rs.entrada_texto("# Message history to summarize:\n" + str(msgs))
        ok(entrada.startswith("user: {\"user_message\""), f"desfaz a lista do Agent Zero: {entrada[:60]}")
        f = self.rs.falas(entrada)
        ok(f == ["Roda a prospecção de hoje", 'Não manda pro "@doce.lar" ainda, só amanhã às 9h'], f"falas: {f}")
        longa = "palavra " * 100
        f2 = self.rs.falas(_txt({"ai": False, "content": {"user_message": longa}}))
        ok(len(f2[0]) == self.rs.FALA_MAX and f2[0].endswith("…"), "fala longa é cortada com …")

    def t_falas_sobrevivem_ao_resumo_do_resumo(self):
        texto = "\n".join(_txt(m) for m in _historia()) + " " + "y" * 3000
        primeiro = "Prospecção rodada." + "\n\n" + self.rs.bloco(texto, "Prospecção rodada.", CTX)
        de_novo = _txt({"ai": False, "content": {"messages_summary": primeiro}}) + "\nai: outra coisa " + "z" * 3000
        f = self.rs.falas(de_novo)
        ok('Não manda pro "@doce.lar" ainda, só amanhã às 9h' in f, f"a fala do bloco anterior continua: {f}")
        b = self.rs.bloco(de_novo, "Resumo novo.", CTX)
        ok("@doce.lar" in b and SAIDA in b and "acao_id=3f2a1b" in b, f"e as âncoras também: {b}")

    # ---- size ----------------------------------------------------------------------------------------------
    def t_teto_de_tamanho(self):
        muitos = " ".join(f"@lead_{i:03d} acao_id={i:06x}a /a0/usr/chats/{CTX}/saidas/{i:04d}-x.txt" for i in range(300))
        falas = "\n".join(_txt({"ai": False, "content": {"user_message": "fala " + "k" * 400}}) for _ in range(5))
        b = self.rs.bloco(muitos + "\n" + falas, "resumo curto", CTX)
        ok(0 < len(b) <= self.rs.LIMITE, f"no máximo {self.rs.LIMITE}: {len(b)}")
        ok(f"/a0/usr/chats/{CTX}/saidas/0299-x.txt" in b, "fica o arquivo mais recente")
        ok("@lead_299" in b and "acao_id=" in b and "» fala k" in b, f"300 arquivos não tiram o @, o id e as falas: {b}")
        ok(b.rstrip().endswith("chat.json."), "o rodapé nunca é cortado")
        pequeno = f"ai: veja {SAIDA} @zen.marmitas " + "w" * 700
        b2 = self.rs.bloco(pequeno, "r" * 100, CTX)
        ok(len(b2) <= (len(pequeno) - 100) // 2, f"teto proporcional ao que o resumo economizou: {len(b2)}")
        ok(self.rs.bloco(f"ai: {SAIDA}", "resumo", CTX) == "", "texto curto demais: sem bloco")
        ok(self.rs.bloco("ai: nada para guardar " + "q" * 5000, "resumo", CTX) == "", "nada a guardar: sem bloco")

    def t_resumo_fica_menor_que_o_original(self):
        texto = "\n".join(_txt(m) for m in _historia()) + "\n" + "ai: detalhe " * 200
        resumo = "O agente executou a prospecção e agendou a rotina."
        data = {"result": resumo, "exception": None}
        self.rs.depois_do_resumo(data, "# Message history to summarize:\n" + texto, CTX)
        ok(data["result"].startswith(resumo) and self.rs.CABECALHO in data["result"], "bloco anexado ao resumo")
        ok(len(data["result"]) < len(texto), "o resumo com o bloco continua menor que o texto resumido")

    def t_mesmo_texto_mesmo_bloco(self):
        # cache_prompt: a summary must not change by itself between turns (no clock, no random order)
        texto = "\n".join(_txt(m) for m in _historia()) + " " + "y" * 3000
        b1, b2 = self.rs.bloco(texto, "r", CTX), self.rs.bloco(texto, "r", CTX)
        ok(b1 == b2, "determinístico")
        ok(not re.search(r"\b\d{1,2}:\d{2}\b|\b20\d\d-\d\d-\d\d\b", b1.replace("9h", "")), "sem hora nem data no bloco")

    def t_ancora_que_o_resumo_ja_tem_nao_repete(self):
        texto = f"ai: @zen.marmitas e {SAIDA} " + "x" * 3000
        b = self.rs.bloco(texto, "Falamos com @zen.marmitas.", CTX)
        ok("@zen.marmitas" not in b.split("Âncoras:", 1)[-1] and SAIDA in b, f"não repete o que o resumo diz: {b}")

    # ---- failure -------------------------------------------------------------------------------------------
    def t_resumo_que_falha_nao_muda_nada(self):
        erro = RuntimeError("proxy fora")
        data = {"result": None, "exception": erro}
        self.rs.depois_do_resumo(data, "user: oi", CTX)
        ok(data["exception"] is erro and data["result"] is None, "erro do modelo continua erro")
        for vazio in ("", "   \n", None):
            data = {"result": vazio, "exception": None}
            self.rs.depois_do_resumo(data, "user: oi", CTX)
            ok(isinstance(data["exception"], self.rs.ResumoVazio), f"resumo vazio vira erro: {vazio!r}")

    # ---- the hook, with a fake history ---------------------------------------------------------------------
    async def t_gancho_com_historico_falso(self):
        resumo = "O agente executou a prospecção."
        agente = AgenteFalso(self.ext, [resumo])
        topico = TopicoFalso(agente, _historia() + [{"ai": True, "content": "detalhe " * 300}, {"ai": True, "content": "fim"}])
        ok(await topico.compress_attention(), "resumiu")
        conteudo = topico.messages[1]["content"]["messages_summary"]
        ok(conteudo.startswith(resumo), "o resumo do modelo fica igual, no começo")
        for esperado in (SAIDA, "@zen.marmitas", "acao_id=3f2a1b", "uuid=laMIuaPt",
                         '» Não manda pro "@doce.lar" ainda, só amanhã às 9h', f"/a0/usr/chats/{CTX}/chat.json"):
            ok(esperado in conteudo, f"falta {esperado} no resumo: {conteudo}")
        ok(len(topico.messages) == 3, "o resto do tópico como estava")

    async def t_gancho_quando_o_resumo_falha(self):
        for resposta, erro in ((RuntimeError("Bedrock 503"), "RuntimeError"), ("", "ResumoVazio"), ("  ", "ResumoVazio")):
            agente = AgenteFalso(self.ext, [resposta])
            antes = _historia()
            topico = TopicoFalso(agente, [dict(m) for m in antes])
            try:
                await topico.compress_attention()
                ok(False, "deveria dar erro")
            except Falha:
                raise
            except Exception as exc:
                ok(type(exc).__name__ == erro, f"erro esperado {erro}, veio {type(exc).__name__}")
            ok(topico.messages == antes, "histórico intacto")

    async def t_outras_chamadas_nao_mudam(self):
        agente = AgenteFalso(self.ext, ["resposta da memória", ""])
        r = await agente.call_utility_model(system="Extract facts", message=f"user: {SAIDA} @zen.marmitas " + "x" * 3000)
        ok(r == "resposta da memória", "chamada que não é resumo fica igual")
        ok(await agente.call_utility_model(system="Extract facts", message="x") == "", "nem resposta vazia vira erro")

    async def t_historico_real_do_agent_zero(self):
        """The real Topic/Bulk of Agent Zero's helpers/history.py, with the fake agent (skipped in CI, where there
        is no Agent Zero: t_gancho_com_historico_falso covers the same flow)."""
        h = _history_real()
        if h is None:
            return
        agente = AgenteFalso(self.ext, ["Resumo do tópico.", "Resumo do bloco.", RuntimeError("caiu")])
        dono = types.SimpleNamespace(agent=agente)
        t = h.Topic(history=dono)
        for m in _historia() + [{"ai": True, "content": "detalhe " * 300}, {"ai": True, "content": "fim"}]:
            t.add_message(m["ai"], m["content"])
        ok(await t.compress_attention(0), "o Topic real resumiu")
        texto = t.output_text()
        ok(SAIDA in texto and "@zen.marmitas" in texto and "doce.lar" in texto, f"Topic real guarda: {texto[:600]}")
        b = h.Bulk(history=dono)
        t2 = h.Topic(history=dono)
        for m in _historia():
            t2.add_message(m["ai"], m["content"])
        t2.add_message(True, "detalhe " * 300)
        b.records = [t2]
        await b.summarize()
        ok(b.summary.startswith("Resumo do bloco.") and "» Roda a prospecção de hoje" in b.summary, f"Bulk real: {b.summary}")
        t3 = h.Topic(history=dono)
        for m in _historia():
            t3.add_message(m["ai"], m["content"])
        antes = t3.output_text()
        try:
            await t3.compress_attention(0)
            ok(False, "deveria dar erro")
        except RuntimeError:
            pass
        ok(t3.output_text() == antes, "Topic real intacto quando o resumo falha")

    def t_bloco_do_registro(self):
        itens = [types.SimpleNamespace(type="user", content="manda pro @zen.marmitas"),
                 types.SimpleNamespace(type="tool", content=f"resultado em {SAIDA}"),
                 types.SimpleNamespace(type="response", content="feito, acao_id 3f2a1b")]
        b = self.rs.bloco_do_registro(itens, CTX)
        ok("@zen.marmitas" in b and SAIDA in b and "acao_id=3f2a1b" in b and f"/a0/usr/chats/{CTX}/chat.json" in b,
           f"âncoras da conversa antiga: {b}")
        ok("Últimas falas" not in b, "as falas já vão no _herdado")
        ok(self.rs.bloco_do_registro([], CTX) == "", "registro vazio")

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
    import asyncio
    r = asyncio.run(Suite().rodar(sys.argv[1] if len(sys.argv) > 1 else ""))
    for x in r["resultados"]:
        if not x["ok"]:
            print("✗", x["teste"], x["erro"])
    print(f"{r['passou']}/{r['total']}")
