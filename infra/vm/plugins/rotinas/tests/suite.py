"""Tests of the routines plugin (no model calls): the wake gate of scheduled routines and salvar_rotina's
corrections. Run with implantar.py (staging copy), rodar_suites_locais.py or inside the container."""
import asyncio
import importlib.util
import inspect
import json
import shutil
import sys
import tempfile
import traceback
import types
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parents[1]
FUSO = ZoneInfo("America/Bahia")
INICIO = RAIZ / "extensions" / "python" / "_functions" / "agent" / "Agent" / "monologue" / "start" / "_10_portao.py"
ENXUTA = RAIZ / "extensions" / "python" / "_functions" / "agent" / "Agent" / "monologue" / "start" / "_20_rodada_enxuta.py"
FIM = RAIZ / "extensions" / "python" / "_functions" / "agent" / "Agent" / "monologue" / "end" / "_10_portao_fim.py"
CORRECOES = RAIZ / "extensions" / "python" / "_functions" / "agent" / "Agent" / "monologue" / "start" / "_30_correcoes_agendada.py"
AUTOAVALIAR = RAIZ / "extensions" / "python" / "_functions" / "agent" / "Agent" / "monologue" / "end" / "_20_autoavaliar.py"


class Falha(Exception):
    pass


def ok(cond, msg):
    if not cond:
        raise Falha(msg)


def eq(a, b, msg):
    if a != b:
        raise Falha(f"{msg}: esperado {b!r}, veio {a!r}")


def _carregar(nome: str, arquivo: Path):
    """Extensions and tools import Agent Zero modules (heavy): stand-ins only while they load."""
    ext = types.ModuleType("helpers.extension")
    ext.Extension = type("Extension", (), {"__init__": lambda s, agent=None, **kw: setattr(s, "agent", agent)})
    tool = types.ModuleType("helpers.tool")
    tool.Tool = type("Tool", (), {})
    tool.Response = type("Response", (), {"__init__": lambda s, **kw: s.__dict__.update(kw)})
    antes = {k: sys.modules.get(k) for k in ("helpers", "helpers.extension", "helpers.tool")}
    sys.modules.setdefault("helpers", types.ModuleType("helpers"))
    sys.modules["helpers.extension"], sys.modules["helpers.tool"] = ext, tool
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


def _sincrono(corrotina):
    """Run an extension's execute() that never really waits (the suite already runs inside an event loop)."""
    try:
        corrotina.send(None)
    except StopIteration as fim:
        return fim.value
    raise Falha("a extensão esperou algo de verdade")


def _quando(dia: int, hora: int) -> datetime:
    return datetime(2026, 10, dia, hora, 0, tzinfo=FUSO)


class FonteFalsa:
    """A source whose answer the test sets: a dict of items, or an exception."""

    def __init__(self):
        self.resposta = {"a": "primeiro"}
        self.chamadas = 0

    async def __call__(self, f, chamar, agora):
        self.chamadas += 1
        if isinstance(self.resposta, BaseException):
            raise self.resposta
        return dict(self.resposta)


# ---- stand-ins for the agent, its chat and history ----

class Msg:
    def __init__(self, texto):
        self.id = f"m{id(self)}"
        self.content = {"system_message": ["sp"], "user_message": texto, "attachments": []}
        self.tokens = 1

    def calculate_tokens(self):
        return len(json.dumps(self.content)) // 4


class Ctx:
    def __init__(self, cid):
        self.id, self.dados, self.logs = cid, {}, []
        self.log = types.SimpleNamespace(log=lambda **kw: self.logs.append(kw))

    def get_data(self, k):
        return self.dados.get(k)

    def set_data(self, k, v):
        self.dados[k] = v


class Agente:
    def __init__(self, ctx, numero=0):
        self.context, self.number = ctx, numero
        self.history = types.SimpleNamespace(current=types.SimpleNamespace(messages=[]))
        self.last_user_message = None

    def tarefa(self, texto="## Task:\nfaça a rodada"):
        m = Msg(texto)
        self.history.current.messages.append(m)
        self.last_user_message = m
        return m


class Suite:
    def __init__(self):
        self.resultados = []

    # ---------- wake gate ----------

    def _portao(self):
        """The gate helper exactly as the extension loads it, writing to a temporary folder."""
        self.ini = _carregar("rotinas_portao_inicio_teste", INICIO)
        self.fim = _carregar("rotinas_portao_fim_teste", FIM)
        P = self.ini.portao()
        pasta = Path(tempfile.mkdtemp(prefix="portao-teste-"))
        self._tmp.append(pasta)
        P.PASTA = pasta
        self.fonte = FonteFalsa()
        P.FONTES = {**P.FONTES, "falsa": self.fonte}
        return P

    CFG = {"fontes": [{"nome": "teste", "tipo": "falsa"}]}

    async def _rodada(self, P, agora, uuid="T1", ok_fim=True):
        """One scheduled round through the gate: decide, then the round 'ends' (well or not)."""
        d = await P.avaliar(uuid, self.CFG, None, agora)
        if d["rodar"]:
            P.preparar(uuid, d)
            P.confirmar(uuid) if ok_fim else P.descartar(uuid)
        else:
            P.registrar_pulo(uuid, d)
        return d

    async def t_portao_igual_pula(self):
        P = self._portao()
        eq((await self._rodada(P, _quando(14, 8)))["motivo"], "primeira", "sem estado, a primeira roda inteira")
        d = await self._rodada(P, _quando(14, 13))
        ok(not d["rodar"], f"mesma fonte no mesmo dia: pula ({d['motivo']})")
        eq(d["motivo"], "igual", "motivo")
        d = await self._rodada(P, _quando(14, 18))
        ok(not d["rodar"], "pular não esquece que já rodou hoje")

    async def t_portao_diferente_roda_so_com_o_que_mudou(self):
        P = self._portao()
        self.fonte.resposta = {"a": "primeiro", "b": "segundo"}
        await self._rodada(P, _quando(14, 8))
        self.fonte.resposta = {"a": "primeiro", "b": "segundo mudado", "c": "terceiro"}
        d = await self._rodada(P, _quando(14, 13))
        ok(d["rodar"], "fonte diferente: roda")
        eq(d["motivo"], "mudou", "motivo")
        eq(d["mudancas"]["teste"], {"novos": ["c | terceiro"], "mudou": ["segundo mudado"], "saiu": []}, "só o que mudou")
        texto = P.contexto(d)
        ok("c | terceiro" in texto and "segundo mudado" in texto and "primeiro" not in texto,
           f"o contexto leva só o que mudou: {texto}")
        ok(not (await self._rodada(P, _quando(14, 18)))["rodar"], "depois de rodar, a mesma fonte volta a pular")

    async def t_portao_fonte_com_erro_roda(self):
        P = self._portao()
        await self._rodada(P, _quando(14, 8))
        self.fonte.resposta = RuntimeError("conector fora")
        d = await self._rodada(P, _quando(14, 13))
        ok(d["rodar"], "fonte com erro nunca vira 'sem mudança'")
        eq(d["motivo"], "erro", "motivo")
        ok("conector fora" in P.contexto(d), "o motivo vai para a rodada")
        self.fonte.resposta = {"a": "primeiro"}
        ok(not (await self._rodada(P, _quando(14, 18)))["rodar"],
           "o que a fonte mostrava antes do erro continua valendo para comparar")
        # a source type that does not exist, or that hangs, is an error too
        lidas = await P.ler_fontes({"fontes": [{"nome": "x", "tipo": "nao_existe"}]}, None, _quando(14, 9))
        ok("erro" in lidas["x"], "tipo desconhecido = erro")

        async def trava(f, chamar, agora):
            await asyncio.sleep(5)
        P.FONTES["trava"], espera = trava, P.ESPERA
        P.ESPERA = 0.05
        try:
            lidas = await P.ler_fontes({"fontes": [{"nome": "y", "tipo": "trava"}]}, None, _quando(14, 9))
        finally:
            P.ESPERA = espera
        ok("erro" in lidas["y"], "fonte que não responde a tempo = erro")

    async def t_portao_rodada_diaria_forcada(self):
        P = self._portao()
        await self._rodada(P, _quando(14, 8))
        ok(not (await self._rodada(P, _quando(14, 18)))["rodar"], "mesmo dia, nada mudou: pula")
        d = await self._rodada(P, _quando(15, 8))
        ok(d["rodar"], "primeira rodada do dia seguinte roda mesmo sem mudança")
        eq(d["motivo"], "diaria", "motivo")
        ok("Rodada completa do dia" in P.contexto(d), "a rodada sabe que é a completa do dia")
        ok(not (await self._rodada(P, _quando(15, 13)))["rodar"], "e depois dela o dia volta a pular")

    async def t_portao_rodada_que_falhou_ve_a_mudanca_de_novo(self):
        # Hermes keeps the new hash at detection: a round that failed would never see that change again
        P = self._portao()
        await self._rodada(P, _quando(14, 8))
        self.fonte.resposta = {"a": "primeiro", "n": "novo"}
        ok((await self._rodada(P, _quando(14, 13), ok_fim=False))["rodar"], "mudou: roda (e falha)")
        d = await self._rodada(P, _quando(14, 18))
        ok(d["rodar"] and d["motivo"] == "mudou", f"a próxima vê a mesma mudança: {d['motivo']}")
        ok(not P._arq("T1", ".pendente").exists(), "nada pendente largado")

    async def t_portao_so_novos_ignora_o_que_saiu(self):
        # e-mails leaving the "newer_than:2d" window are not news; a calendar event that left is
        P = self._portao()
        cfg = {"fontes": [{"nome": "mail", "tipo": "falsa", "so_novos": True}]}
        self.fonte.resposta = {"x": "", "y": ""}
        d = P.decidir(cfg, await P.ler_fontes(cfg, None, _quando(14, 8)), None, _quando(14, 8))
        estado = d["estado"]
        self.fonte.resposta = {"y": ""}
        d = P.decidir(cfg, await P.ler_fontes(cfg, None, _quando(14, 13)), estado, _quando(14, 13))
        ok(not d["rodar"], "só saiu: pula")
        d = P.decidir(self.CFG | {"fontes": [{"nome": "mail", "tipo": "falsa"}]},
                      await P.ler_fontes(cfg, None, _quando(14, 13)), estado, _quando(14, 13))
        ok(d["rodar"] and d["mudancas"]["mail"]["saiu"] == ["x"], "sem so_novos, sair é mudança")

    async def t_portao_fontes_google_e_arquivo(self):
        P = self._portao()
        gmail = ("Found 2 messages matching 'q':\n\n📧 MESSAGES:\n  1. Message ID: 19a1\n     Subject: Boleto\n"
                 "     From: Banco <b@x>\n     Date: x\n     Web Link: u\n\n  2. Message ID: 19a2\n     Web Link: u\n")
        agenda = ("Successfully retrieved 1 events from calendar 'primary' for e:\n"
                  '- "Dentista" (Starts: 2026-10-15T09:00:00-03:00, Ends: 2026-10-15T10:00:00-03:00)')
        respostas = {"search_gmail_messages": (True, gmail), "get_events": (True, agenda)}
        pedidos = []

        async def chamar(ferramenta, args):
            pedidos.append((ferramenta, args))
            return respostas[ferramenta]
        eq(await P.fonte_gmail({"busca": "in:inbox"}, chamar, _quando(14, 8)),
           {"19a1": "Assunto: Boleto | De: Banco <b@x>", "19a2": ""}, "ids e cabeçalhos do Gmail")
        eq(list(await P.fonte_agenda({"dias": 8}, chamar, _quando(14, 8))),
           ['- "Dentista" (Starts: 2026-10-15T09:00:00-03:00, Ends: 2026-10-15T10:00:00-03:00)'], "eventos")
        eq((pedidos[-1][1]["time_min"], pedidos[-1][1]["time_max"]), ("2026-10-14", "2026-10-22"), "janela fixa no dia")
        respostas["search_gmail_messages"] = (True, "No messages found for query: 'q'")
        eq(await P.fonte_gmail({"busca": "q"}, chamar, _quando(14, 8)), {}, "caixa vazia é resposta válida")
        for errado in ((False, "auth"), (True, "Please authorize: https://accounts.google.com/...")):
            respostas["search_gmail_messages"] = respostas["get_events"] = errado
            for fonte in (P.fonte_gmail, P.fonte_agenda):
                try:
                    await fonte({"busca": "q"}, chamar, _quando(14, 8))
                    raise Falha(f"{fonte.__name__}: {errado} devia ser erro, não 'nada novo'")
                except P.FonteComErro:
                    pass
        arq = P.PASTA / "fios.json"
        arq.write_text(json.dumps({"fios": [{"id": "f1", "titulo": "Boleto", "estado": "aberto"},
                                            {"id": "f2", "titulo": "Velho", "estado": "resolvido"}]}), encoding="utf-8")
        eq(await P.fonte_arquivo({"caminho": str(arq), "lista": "fios", "campos": ["titulo", "estado"],
                                  "so_estados": ["aberto"]}, None, None), {"f1": "Boleto | aberto"}, "itens do JSON")
        try:
            await P.fonte_arquivo({"caminho": str(P.PASTA / "nao_tem.json")}, None, None)
            raise Falha("arquivo que sumiu devia ser erro")
        except P.FonteComErro:
            pass

    def t_portao_config_real(self):
        P = self._portao()
        dados = json.loads(P.CONFIG.read_text(encoding="utf-8"))
        ok("HL76nfIg" in dados and P.config("HL76nfIg"), "radar com portão")
        ok("2FIQTI0o" in dados, "iniciativa com portão")
        ok("H8kWmYP1" not in dados, "Nexos sem portão: não há fonte barata confiável da página da Meta")
        for uuid, cfg in dados.items():
            for f in cfg["fontes"]:
                ok(f["tipo"] in ("gmail", "agenda", "arquivo"), f"{uuid}: tipo {f['tipo']}")
        rotinas = RAIZ.parents[1] / "rotinas"
        if rotinas.exists():  # in the repository (not in the staging copy on the VM)
            for uuid in dados:
                ok((rotinas / f"{uuid}.json").exists(), f"{uuid} é uma rotina versionada")
        ok(P.config("nao-existe") is None, "rotina sem portão roda como antes")

    async def t_portao_gancho_pula_sem_chamar_modelo(self):
        P = self._portao()
        ini, fim = self.ini, self.fim
        tarefa = types.SimpleNamespace(uuid="T1", name="Radar teste")
        rodando = {"ctx1": tarefa}
        ini.tarefa_rodando = lambda cid: rodando.get(cid)
        P.config = lambda uuid: self.CFG if uuid == "T1" else None
        ag = Agente(Ctx("ctx1"))

        async def monologo(agente, ok_fim=True):
            data = {"args": (agente,), "kwargs": {}, "result": "NAO_RODOU", "exception": None}
            data["result"] = ini._UNSET = object()
            await ini.Portao(agente).execute(data=data)
            pulou = data["result"] is not ini._UNSET
            if not pulou:
                data["result"] = "resposta do modelo"
                if not ok_fim:
                    data["exception"] = RuntimeError("modelo caiu")
            await fim.PortaoFim(agente).execute(data=data)
            return pulou, data["result"]

        m = ag.tarefa()
        pulou, _ = await monologo(ag)
        ok(not pulou, "primeira rodada roda")
        ok("Primeira rodada com portão" in m.content["user_message"] and m.content["user_message"].startswith("## Task"),
           f"o contexto vai no fim da mensagem da tarefa: {m.content['user_message'][:80]}")
        ok(P.carregar_estado("T1"), "rodou bem: estado gravado")

        m = ag.tarefa()
        pulou, res = await monologo(ag)
        ok(pulou and res.startswith("SEM NOVIDADE"), f"nada mudou: pula sem chamar o modelo ({res})")
        ok(m not in ag.history.current.messages, "a mensagem da rodada pulada sai do histórico")
        ok(any("pulada" in str(x.get("content")) for x in ag.context.logs), "a conversa mostra que foi pulada")
        pulou, _ = await monologo(ag)
        ok(not pulou, "a mesma rodada não é avaliada duas vezes")

        self.fonte.resposta = {"a": "primeiro", "z": "e-mail novo"}
        m = ag.tarefa()
        pulou, _ = await monologo(ag, ok_fim=False)
        ok(not pulou and "z | e-mail novo" in m.content["user_message"], "mudou: roda com o que mudou")
        m = ag.tarefa()
        pulou, _ = await monologo(ag)
        ok(not pulou, "a rodada anterior falhou: esta vê a mesma mudança")

        sub = Agente(ag.context, numero=1)
        sub.tarefa("## Task:\nsubordinado")
        self.fonte.chamadas = 0
        await monologo(sub)
        eq(self.fonte.chamadas, 0, "subordinado na mesma conversa não passa pelo portão")
        outra = Agente(Ctx("ctx2"))
        outra.tarefa("oi, tudo bem?")
        await monologo(outra)
        eq(self.fonte.chamadas, 0, "conversa sem rotina rodando não passa pelo portão")
        ag.tarefa("uma mensagem do usuário no meio")
        await monologo(ag)
        eq(self.fonte.chamadas, 0, "mensagem que não é da rodada não passa pelo portão")

        def quebra(cid):
            raise RuntimeError("agendador indisponível")
        ini.tarefa_rodando = quebra
        ag.tarefa()
        pulou, _ = await monologo(ag)
        ok(not pulou, "portão com defeito deixa a rodada rodar")

    # ---------- salvar_rotina ----------

    def _ferramenta(self):
        F = _carregar("rotinas_salvar_teste", RAIZ / "tools" / "salvar_rotina.py")
        T = F.rotinas()  # the helper exactly as the tool loads it
        pasta = Path(tempfile.mkdtemp(prefix="rotinas-teste-"))
        self._tmp.append(pasta)
        T.SKILLS = pasta
        eu = types.SimpleNamespace(agent=types.SimpleNamespace(context=types.SimpleNamespace(get_data=lambda k: "teste_rot")))

        async def chamar(**kw):
            return (await F.SalvarRotina.execute(eu, **kw)).message
        return T, chamar

    async def _rotina(self, chamar):
        return await chamar(acao="salvar", nome="Conferir exames", descricao="Ver exames novos",
                            passos=["Abrir o portal", "Entrar", "Baixar os PDFs"])

    async def t_corrigir_recusa_correcao_repetida(self):
        T, chamar = self._ferramenta()
        await self._rotina(chamar)
        ok("gravada" in await chamar(acao="corrigir", nome="Conferir exames", correcao="Use sempre a conta raiz."),
           "primeira correção grava")
        r = await chamar(acao="corrigir", nome="Conferir exames", correcao="  use SEMPRE a  conta Raíz ")
        ok("já está" in r, f"igual depois de normalizar: recusada ({r})")
        texto = (T.SKILLS / "conferir-exames" / "SKILL.md").read_text(encoding="utf-8")
        eq(len(T.correcoes(texto)), 1, "só uma linha gravada")
        ok("gravada" in await chamar(acao="corrigir", nome="Conferir exames", correcao="Use a conta pessoal só aos sábados"),
           "correção diferente grava")
        await self._rotina(chamar)
        eq(len(T.correcoes((T.SKILLS / "conferir-exames" / "SKILL.md").read_text(encoding="utf-8"))), 2,
           "salvar de novo mantém as correções")

    async def t_ajustar_so_com_rotina_relida(self):
        T, chamar = self._ferramenta()
        await self._rotina(chamar)
        arq = T.SKILLS / "conferir-exames" / "SKILL.md"
        r = await chamar(acao="ajustar", nome="Conferir exames", trecho="2. Entrar", novo="2. Entrar com o cofre")
        ok("não foi relida" in r and "2. Entrar\n" in arq.read_text(encoding="utf-8"), f"sem versao: recusa ({r})")
        lido = await chamar(acao="ler", nome="Conferir exames")
        versao = lido.split("\n")[0].split(": ")[1]
        ok("## Passos" in lido and versao == T.hash_de(arq.read_text(encoding="utf-8")), "ler devolve a rotina e a versao")
        r = await chamar(acao="ajustar", nome="Conferir exames", versao="000000000000", trecho="2. Entrar", novo="x")
        ok("não foi relida" in r, "versao errada: recusa")
        for trecho, esperado in (("não existe aqui", "não está"), ("PDFs", "")):
            r = await chamar(acao="ajustar", nome="Conferir exames", versao=versao, trecho=trecho, novo="y")
            if esperado:
                ok(esperado in r, f"trecho ausente: recusa ({r})")
        ok("aparece" not in r, "trecho único troca")
        await chamar(acao="corrigir", nome="Conferir exames", correcao="Baixe também o laudo")
        r = await chamar(acao="ajustar", nome="Conferir exames", versao=versao, trecho="2. Entrar", novo="z")
        ok("não foi relida" in r, "a rotina mudou depois da leitura (a versao velha não vale)")
        versao = (await chamar(acao="ler", nome="Conferir exames")).split("\n")[0].split(": ")[1]
        r = await chamar(acao="ajustar", nome="Conferir exames", versao=versao, trecho="2. Entrar", novo="2. Entrar com o cofre")
        ok("ajustada" in r and "2. Entrar com o cofre" in arq.read_text(encoding="utf-8"), f"relida: troca ({r})")
        arq.write_text(arq.read_text(encoding="utf-8") + "\nEntrar\n", encoding="utf-8")
        versao = (await chamar(acao="ler", nome="Conferir exames")).split("\n")[0].split(": ")[1]
        r = await chamar(acao="ajustar", nome="Conferir exames", versao=versao, trecho="Entrar", novo="x")
        ok("aparece" in r, f"trecho repetido: pede um maior ({r})")

    async def t_oito_correcoes_pedem_passos_limpos(self):
        T, chamar = self._ferramenta()
        await self._rotina(chamar)
        for i in range(1, T.LIMITE):
            r = await chamar(acao="corrigir", nome="Conferir exames", correcao=f"Correção número {i} sobre o passo {i}")
            ok("reescreva" not in r, f"com {i} correções ainda não pede ({r})")
        r = await chamar(acao="corrigir", nome="Conferir exames", correcao="Mais uma, a oitava")
        ok(f"acumula {T.LIMITE}" in r and "reescreva os passos" in r, f"na 8ª pede os passos limpos ({r})")
        r = await chamar(acao="salvar", nome="Conferir exames", descricao="Ver exames novos", passos=["Limpo"], consolidar=True)
        ok("Nada foi gravado" in r, "consolidar sem reler é recusado")
        versao = (await chamar(acao="ler", nome="Conferir exames")).split("\n")[0].split(": ")[1]
        r = await chamar(acao="salvar", nome="Conferir exames", descricao="Ver exames novos", passos=["Limpo, já corrigido"],
                         consolidar="true", versao=versao)
        texto = (T.SKILLS / "conferir-exames" / "SKILL.md").read_text(encoding="utf-8")
        ok("incorporadas" in r and T.SECAO not in texto and "Limpo, já corrigido" in texto, f"consolidada ({r})")
        guardadas = list((T.SKILLS / "conferir-exames" / ".versoes").glob("SKILL-*.md"))
        ok(len(guardadas) == 1 and "a oitava" in guardadas[0].read_text(encoding="utf-8"), "a versão anterior ficou guardada")
        r = await chamar(acao="corrigir", nome="Conferir exames", correcao="Nova depois de limpar")
        ok("reescreva" not in r, "depois de consolidar a contagem recomeça")

    async def t_helper_publico_para_o_revisor(self):
        # the end-of-chat reviewer (memory front) imports helpers/rotinas.py: names and answers are a contract
        T, chamar = self._ferramenta()
        R = _carregar("rotinas_helper_direto", RAIZ / "helpers" / "rotinas.py")
        R.SKILLS = T.SKILLS
        eq(R.listar(), [], "sem rotinas")
        eq(R.ler("Conferir exames"), None, "ler o que não existe")
        eq(R.corrigir("Conferir exames", "x")["motivo"], "nao_existe", "corrigir o que não existe")
        await self._rotina(chamar)
        (T.SKILLS / "outra-skill").mkdir()
        (T.SKILLS / "outra-skill" / "SKILL.md").write_text('---\nname: outra-skill\ndescription: "x"\ntags: ["prospeccao"]\n---\n',
                                                         encoding="utf-8")
        eq(R.corrigir("Conferir exames", "Use a conta raiz", por="revisor"),
           {"ok": True, "motivo": "gravada", "n_correcoes": 1, "pede_reescrita": False}, "corrigir")
        eq(R.corrigir("conferir exames", "use a conta RAIZ.", por="revisor")["motivo"], "repetida", "duplicata pelo revisor")
        eq(R.corrigir("Conferir exames", "   ")["motivo"], "vazia", "correção vazia")
        lista = R.listar()
        eq(lista, [{"nome": "conferir-exames", "descricao": "Ver exames novos", "gatilhos": [], "n_correcoes": 1}],
           "listar só as rotinas, com o número de correções")
        lido = R.ler("Conferir exames")
        ok(set(lido) == {"texto", "hash"} and lido["hash"] == R.hash_de(lido["texto"]), "ler devolve texto e hash")
        import re as _re
        ok(_re.search(r"- \d{2}/\d{2}/\d{4} \(por revisor\): Use a conta raiz", lido["texto"]), "a correção leva data e autor")
        await chamar(acao="corrigir", nome="Conferir exames", correcao="Baixe também o laudo")
        ok("(por teste_rot): Baixe" in R.ler("Conferir exames")["texto"], "pela ferramenta, o autor é o login da conversa")
        eq(R.ajustar("Conferir exames", "2. Entrar", "2. Entrar pelo cofre", lido["hash"], por="revisor")["motivo"],
           "nao_relida", "hash velho (a ferramenta gravou depois da leitura): recusa")
        lido = R.ler("Conferir exames")
        r = R.ajustar("Conferir exames", "2. Entrar", "2. Entrar pelo cofre", lido["hash"], por="revisor")
        ok(r["ok"] and r["motivo"] == "ajustada" and r["hash"] == R.ler("Conferir exames")["hash"] and r["n_correcoes"] == 2,
           f"ajustar com o hash lido: {r}")
        eq(R.ajustar("Conferir exames", "nada disso", "y", r["hash"])["motivo"], "nao_achou", "trecho ausente")
        diario = (T.SKILLS / "conferir-exames" / ".versoes" / "diario.jsonl").read_text(encoding="utf-8").splitlines()
        eq([json.loads(l)["acao"] for l in diario], ["salvar", "corrigir", "corrigir", "ajustar"], "diário das mudanças")
        eq(json.loads(diario[-1])["por"], "revisor", "o diário guarda quem mudou")
        for i in range(R.LIMITE - 2):
            r = R.corrigir("Conferir exames", f"regra {i}", por="revisor")
        ok(r["pede_reescrita"] and r["n_correcoes"] == R.LIMITE, f"na {R.LIMITE}ª pede reescrita: {r}")
        ok(not list(T.SKILLS.rglob("*.tmp")), "nenhum temporário largado")
        old = "- 01/10/2026: correção do formato antigo"
        arq = T.SKILLS / "conferir-exames" / "SKILL.md"
        arq.write_text(arq.read_text(encoding="utf-8") + old + "\n", encoding="utf-8")
        eq(R.corrigir("Conferir exames", "Correção do formato antigo")["motivo"], "repetida",
           "correção no formato antigo (sem autor) também conta")

    # ---------- 20/10: a round starts with only the previous round ----------

    def t_rodada_comeca_so_com_a_anterior(self):
        ext = _carregar("rotinas_rodada_enxuta_teste", ENXUTA)
        R = ext.rodada()

        class Topico:
            def __init__(self, tokens):
                self.tokens = tokens

            def get_tokens(self):
                return self.tokens

        def hist(*tokens, blocos=(5000,)):
            return types.SimpleNamespace(topics=[Topico(t) for t in tokens], bulks=[Topico(b) for b in blocos],
                                         current=types.SimpleNamespace(messages=["## Task"]))

        h = hist(9000, 20000, 4000)
        eq(R.enxugar(h), 3, "dois tópicos antigos e o resumo saem")
        eq([t.tokens for t in h.topics], [4000], "a rodada anterior pequena fica")
        eq(h.bulks, [], "resumos antigos saem")
        eq(h.current.messages, ["## Task"], "a rodada atual não é tocada")
        h = hist(9000, 30000)
        eq(R.enxugar(h), 3, "rodada anterior grande também sai")
        eq(h.topics, [], "nada antigo fica")
        h = hist(3000, 4000, blocos=())
        eq(R.enxugar(h), 0, "histórico pequeno: nada muda")
        eq(len(h.topics), 2, "intacto")

        # the extension: only the main agent, only a scheduled round, once per round, never a round the gate skipped
        ctx = Ctx("rot1")
        a = Agente(ctx)
        a.history = hist(9000, 20000, 4000)
        a.last_user_message = Msg("## Task:\nrodada")
        tarefa = types.SimpleNamespace(name="Prospecção — executar")
        ext.tarefa_rodando = lambda cid: tarefa if cid == "rot1" else None
        _sincrono(ext.RodadaEnxuta(agent=a).execute(data={"result": object()}))
        eq(len(a.history.topics), 1, "rodada agendada: começa enxuta")
        ok(any("saíram do histórico" in str(l.get("content")) for l in ctx.logs), "fica registrado no log")
        a.history = hist(9000, 20000)
        _sincrono(ext.RodadaEnxuta(agent=a).execute(data={"result": object()}))
        eq(len(a.history.topics), 2, "a mesma rodada não é enxugada de novo")
        a.last_user_message = Msg("## Task:\noutra rodada")
        _sincrono(ext.RodadaEnxuta(agent=a).execute(data={"result": "SEM NOVIDADE (portão: nada mudou)"}))
        eq(len(a.history.topics), 2, "rodada pulada pelo portão: nada muda")
        b = Agente(Ctx("conversa"))
        b.history = hist(9000, 20000)
        b.last_user_message = Msg("## Task:\nalgo")
        _sincrono(ext.RodadaEnxuta(agent=b).execute(data={"result": object()}))
        eq(len(b.history.topics), 2, "conversa sem tarefa rodando: nada muda")
        c = Agente(ctx, numero=1)
        c.history = hist(9000, 20000)
        c.last_user_message = Msg("## Task:\nterceira")
        _sincrono(ext.RodadaEnxuta(agent=c).execute(data={"result": object()}))
        eq(len(c.history.topics), 2, "ajudante (A1): nada muda")
        a.last_user_message = Msg("oi, tudo bem?")
        a.history = hist(9000, 20000)
        _sincrono(ext.RodadaEnxuta(agent=a).execute(data={"result": object()}))
        eq(len(a.history.topics), 2, "mensagem da pessoa (não é rodada): nada muda")

    # ---------- self-assessment of scheduled routines ----------

    def _auto(self):
        """autoavaliacao.py and rotinas.py on temporary folders; a fake phone and a fake model."""
        A = _carregar("rotinas_autoavaliacao_teste", RAIZ / "helpers" / "autoavaliacao.py")
        R = _carregar("rotinas_helper_auto_teste", RAIZ / "helpers" / "rotinas.py")
        pasta = Path(tempfile.mkdtemp(prefix="autoavaliacao-teste-"))
        self._tmp.append(pasta)
        A.PASTA, R.SKILLS, R.AGENDADAS = pasta / "log", pasta / "skills", pasta / "agendadas"
        self.enviadas, self.pedidos, self.modelo = [], [], ""

        def enviar(login, texto, botoes):
            self.enviadas.append({"login": login, "texto": texto, "botoes": botoes})
            return self.falha_envio
        self.falha_envio = ""

        def modelo(pedido):
            self.pedidos.append(pedido)
            if isinstance(self.modelo, BaseException):
                raise self.modelo
            return self.modelo

        def avaliar(resultado="Resumo: 3 e-mails importantes.", erro=None, agora=None, uuid="R1"):
            return A.autoavaliar(uuid, "📰 Resumo do dia", resultado, pedido="Monte o resumo da manhã.", erro=erro,
                                 chamar_modelo=modelo, enviar=enviar, R=R, agora=agora)
        return A, R, avaliar

    @staticmethod
    def _json(nota=4, linha="Bom: trouxe só o que importa.", melhoria="", infra=False):
        return "ok, aqui: " + json.dumps({"nota": nota, "linha": linha, "falha_infra": infra, "melhoria": melhoria})

    def t_autoavaliacao_resposta_ruim_nao_propoe(self):
        A, R, avaliar = self._auto()
        for saida in ("não sei", "{nota: 4}", self._json(nota=9, melhoria="x"), self._json(linha="", melhoria="x"),
                      '["lista"]', RuntimeError("modelo caiu")):
            self.modelo = saida
            r = avaliar()
            eq(r["motivo"], "sem_avaliacao", f"resposta ruim do modelo ({saida!r})")
        eq(self.enviadas, [], "nada vai ao celular")
        av = [e for e in A.eventos("R1") if e["tipo"] == "avaliacao"]
        eq(len(av), 6, "cada rodada fica no registro, sem nota")
        ok(all(e["nota"] is None for e in av) and "modelo caiu" in av[-1]["linha"], "o motivo fica registrado")
        self.modelo = self._json()
        r = avaliar()
        eq((r["motivo"], r["avaliacao"]["nota"]), ("avaliada", 4), "resposta boa sem melhoria: só avalia")
        eq(A.eventos("R1")[-1]["linha"], "Bom: trouxe só o que importa.", "a linha fica no registro")
        eq(self.enviadas, [], "sem melhoria, sem mensagem")

    def t_autoavaliacao_falha_de_infra_nao_propoe(self):
        A, R, avaliar = self._auto()
        self.modelo = self._json(melhoria="Mude tudo")
        eq(avaliar(erro=TimeoutError("sem rede"))["motivo"], "infra", "rodada com erro")
        eq(avaliar(resultado="CONSULTA LIMITADA (429): tente depois")["motivo"], "infra", "limite de consulta")
        eq(avaliar(resultado="")["motivo"], "infra", "rodada sem resposta")
        eq(self.pedidos, [], "falha de infra: nem chama o modelo")
        eq(avaliar(resultado="SEM NOVIDADE")["motivo"], "sem_novidade", "sem novidade: registra sem modelo")
        eq(self.pedidos, [], "sem novidade não chama o modelo")
        self.modelo = self._json(nota=1, infra=True, melhoria="Tente de novo com outra conta")
        eq(avaliar(resultado="A busca não trouxe nada hoje.")["motivo"], "infra", "o modelo viu falha de infra")
        eq(self.enviadas, [], "nenhuma proposta por falha de infra")
        ok(all("melhoria" not in e for e in A.eventos("R1")), "melhoria de rodada com falha de infra é descartada")

    def t_autoavaliacao_uma_proposta_por_semana_sem_repetir(self):
        A, R, avaliar = self._auto()
        t0, dia = 1_800_000_000, 86400
        self.modelo = self._json(melhoria="Junte os e-mails do mesmo remetente numa linha só")
        r = avaliar(agora=t0)
        eq(r["motivo"], "proposta", "primeira melhoria vira proposta")
        eq(len(self.enviadas), 1, "UMA mensagem")
        m = self.enviadas[0]
        eq(m["login"], "matheus", "vai ao Matheus")
        ok("Junte os e-mails" in m["texto"] and "Resumo do dia" in m["texto"] and "ok" in m["texto"], m["texto"])
        eq([b["titulo"] for b in m["botoes"]], ["✅ Aplicar", "❌ Não"], "botões Aplicar / Não")
        ok(all(len(b["id"].encode()) <= 64 for b in m["botoes"]), "id cabe no botão do Telegram (64 bytes)")
        eq(A.ler_botao(m["botoes"][0]["id"]), ("matheus", "R1", r["proposta"], "aplicar"), "o botão diz qual proposta")
        eq(avaliar(agora=t0 + 3600)["motivo"], "repetida", "a mesma melhoria pendente não volta")
        self.modelo = self._json(melhoria="Comece pelo que vence hoje")
        eq(avaliar(agora=t0 + 3 * dia)["motivo"], "limite", "outra melhoria antes de 7 dias: espera")
        eq(len(self.enviadas), 1, "nada mais foi ao celular")
        self.modelo = self._json(melhoria="  junte os E-MAILS do mesmo remetente, numa linha só. ")
        eq(avaliar(agora=t0 + 8 * dia)["motivo"], "repetida", "a mesma (normalizada) não volta nem depois de 7 dias")
        self.modelo = self._json(melhoria="Comece pelo que vence hoje")
        eq(avaliar(agora=t0 + 8 * dia)["motivo"], "proposta", "depois de 7 dias, uma nova pode ir")
        eq(len(self.enviadas), 2, "segunda proposta enviada")
        ok(avaliar(uuid="R2", agora=t0 + 8 * dia)["motivo"] == "proposta", "o limite é por rotina")
        # a proposal that never reached the phone does not hold the next one back
        self.falha_envio = "ponte fora do ar"
        self.modelo = self._json(melhoria="Diga a hora de cada reunião")
        eq(avaliar(uuid="R3", agora=t0)["motivo"], "envio_falhou", "envio falhou")
        self.falha_envio = ""
        self.modelo = self._json(melhoria="Ponha as contas no topo")
        eq(avaliar(uuid="R3", agora=t0 + 60)["motivo"], "proposta", "a que não chegou não conta no limite")

    def t_autoavaliacao_aplicar_passa_pela_correcao(self):
        A, R, avaliar = self._auto()
        rotinas_git = {p.name: p.read_bytes() for p in (RAIZ.parents[1] / "rotinas").glob("*.json")}
        self.modelo = self._json(melhoria="Junte os e-mails do mesmo remetente numa linha só")
        pid = avaliar()["proposta"]
        aplicar, nao = (b["id"] for b in self.enviadas[0]["botoes"])
        ok("Não reconheci" in A.responder("outra_pessoa", aplicar, R=R), "botão de outro login não vale")
        eq(R.correcoes_agendada("R1"), [], "nada aplicado sem o ok dele")
        r = A.responder("matheus", aplicar, R=R)
        ok(r.startswith("✅ Aplicado"), r)
        eq(R.correcoes_agendada("R1"), ["Junte os e-mails do mesmo remetente numa linha só"],
           "a mudança entra pelas correções da rotina")
        texto = R.arquivo_agendada("R1").read_text(encoding="utf-8")
        ok(f"(por matheus, aprovou a sugestão {pid})" in texto and "Resumo do dia" in texto, texto)
        diario = (R.arquivo_agendada("R1").parent / ".versoes" / "diario.jsonl").read_text(encoding="utf-8")
        ok('"acao": "corrigir"' in diario and "aprovou" in diario, "o diário das rotinas registra a correção")
        resp = [e for e in A.eventos("R1") if e["tipo"] == "resposta"]
        eq((resp[0]["decisao"], resp[0]["ok_de"]), ("aplicada", "matheus"), "o ok dele fica registrado")
        ok("já foi respondida" in A.responder("matheus", nao, R=R), "segunda resposta não muda nada")
        eq(len(R.correcoes_agendada("R1")), 1, "aplicada uma vez só")
        self.modelo = self._json(melhoria="junte os e-mails do mesmo remetente numa linha só!")
        eq(avaliar(uuid="R1")["motivo"], "ja_vale", "o que já vale não é proposto de novo")
        # never the routine itself: the versioned JSONs are untouched and the helper never writes the scheduler
        eq({p.name: p.read_bytes() for p in (RAIZ.parents[1] / "rotinas").glob("*.json")}, rotinas_git,
           "as rotinas do git ficam iguais")
        fonte = (RAIZ / "helpers" / "autoavaliacao.py").read_text(encoding="utf-8").split('"""', 2)[2]  # code, no docstring
        for proibido in ("tasks.json", "update_task", "TaskScheduler", "salvar(", "ajustar("):
            ok(proibido not in fonte, f"a autoavaliação não mexe na rotina direto ({proibido})")
        escritos = {p.relative_to(A.PASTA.parent).parts[0] for p in A.PASTA.parent.rglob("*") if p.is_file()}
        ok(escritos <= {"log", "agendadas", "skills"}, f"só grava no registro e nas correções: {escritos}")

    def t_autoavaliacao_nao_registra_recusa(self):
        A, R, avaliar = self._auto()
        self.modelo = self._json(melhoria="Mande também o clima")
        avaliar(agora=1_800_000_000)
        nao = self.enviadas[0]["botoes"][1]["id"]
        ok("fica como está" in A.responder("matheus", nao, R=R), "Não: responde curto")
        eq(R.correcoes_agendada("R1"), [], "Não: nada muda na rotina")
        p = A.propostas("R1")[0]
        eq((p["estado"], p["resposta"]["por"]), ("recusada", "matheus"), "a recusa fica registrada")
        eq(avaliar(agora=1_800_000_000 + 30 * 86400)["motivo"], "repetida", "recusada não volta")
        ok("Não achei" in A.responder("matheus", "rta:matheus:R1.ffffffff:aplicar", R=R), "proposta que não existe")
        ok("Não reconheci" in A.responder("matheus", "rta:matheus:lixo", R=R), "botão malformado")

    def t_autoavaliacao_registro_pequeno(self):
        A, R, avaliar = self._auto()
        A.MAX_AVALIACOES = 5
        self.modelo = self._json(melhoria="Mande também o clima")
        avaliar(agora=1_800_000_000)
        self.modelo = self._json()
        for i in range(12):
            avaliar(agora=1_800_000_100 + i)
        ev = A.eventos("R1")
        eq(sum(e["tipo"] == "avaliacao" for e in ev), 5, "só as últimas avaliações ficam")
        eq(len(A.propostas("R1")), 1, "a proposta nunca sai do registro")

    def t_autoavaliacao_ganchos(self):
        ini = _carregar("rotinas_correcoes_inicio_teste", CORRECOES)
        fim = _carregar("rotinas_autoavaliar_fim_teste", AUTOAVALIAR)
        R = _carregar("rotinas_helper_gancho_teste", RAIZ / "helpers" / "rotinas.py")
        pasta = Path(tempfile.mkdtemp(prefix="ganchos-teste-"))
        self._tmp.append(pasta)
        R.SKILLS, R.AGENDADAS = pasta / "skills", pasta / "agendadas"
        ini.rotinas = lambda: R
        tarefa = types.SimpleNamespace(uuid="R1", name="📰 Resumo do dia", prompt="Monte o resumo da manhã.")
        ini.tarefa_rodando = lambda cid: tarefa if cid == "c1" else None
        chamadas = []
        fim.iniciar = lambda marca, resultado, erro: chamadas.append((marca, resultado, erro))

        def rodada(agente, resultado="resposta", erro=None, pulada=False):
            data = {"result": "SEM NOVIDADE (portão: nada mudou)" if pulada else object(), "exception": None}
            _sincrono(ini.CorrecoesAgendada(agent=agente).execute(data=data))
            if not pulada:
                data["result"] = resultado
                data["exception"] = erro
            _sincrono(fim.Autoavaliar(agent=agente).execute(data=data))

        ag = Agente(Ctx("c1"))
        m = ag.tarefa()
        rodada(ag)
        eq(m.content["user_message"], "## Task:\nfaça a rodada", "sem correções: a mensagem fica igual")
        eq(len(chamadas), 1, "a rodada terminada é avaliada")
        eq((chamadas[0][0]["uuid"], chamadas[0][1]), ("R1", "resposta"), "com o resultado da rodada")
        ok("resumo da manhã" in chamadas[0][0]["pedido"], "e o que a rotina pede")
        R.corrigir_agendada("R1", tarefa.name, "Comece pelo que vence hoje", por="matheus")
        m = ag.tarefa()
        rodada(ag, erro=RuntimeError("caiu"))
        ok(m.content["user_message"].startswith("## Task") and "- Comece pelo que vence hoje" in m.content["user_message"]
           and "valem acima dos passos" in m.content["user_message"], "a correção aprovada entra no fim da tarefa")
        ok(isinstance(chamadas[-1][2], RuntimeError), "rodada com erro: a avaliação recebe o erro (infra)")
        n = len(chamadas)
        ag.tarefa()
        rodada(ag, pulada=True)
        eq(len(chamadas), n, "rodada pulada pelo portão não é avaliada")
        _sincrono(fim.Autoavaliar(agent=ag).execute(data={"result": "outra", "exception": None}))
        eq(len(chamadas), n, "fim sem rodada marcada (mensagem dele no chat): nada")
        sub = Agente(ag.context, numero=1)
        sub.tarefa("## Task:\nsubordinado")
        rodada(sub)
        eq(len(chamadas), n, "subordinado não é avaliado")
        outra = Agente(Ctx("c2"))
        outra.tarefa()
        rodada(outra)
        eq(len(chamadas), n, "conversa sem rotina rodando não é avaliada")
        receber = RAIZ.parent / "whatsapp" / "api" / "receber.py"  # in the repository (a staging copy is alone)
        if receber.exists():
            texto = receber.read_text(encoding="utf-8")
            ok('botao.startswith("rta:")' in texto and ".responder, usuario, botao" in texto,
               "o botão do celular chega ao responder da autoavaliação")

    async def rodar(self, so=""):
        self._tmp = []
        for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
            try:
                r = getattr(self, nome)()
                if inspect.isawaitable(r):
                    await r
                self.resultados.append({"teste": nome, "ok": True})
            except Exception as exc:
                self.resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                        "onde": traceback.format_exc().splitlines()[-3:]})
        for pasta in self._tmp:
            shutil.rmtree(pasta, ignore_errors=True)
        for m in ("rotinas_portao", "rotinas_helper", "rotinas_autoavaliacao"):  # the tests changed their folders and sources
            sys.modules.pop(m, None)
        return {"passou": sum(r["ok"] for r in self.resultados), "total": len(self.resultados), "resultados": self.resultados}


if __name__ == "__main__":
    r = asyncio.run(Suite().rodar(sys.argv[1] if len(sys.argv) > 1 else ""))
    for x in r["resultados"]:
        print("ok   " if x["ok"] else "FALHA", x["teste"], x.get("erro", ""), *(x.get("onde") or []) if not x["ok"] else "")
    print("TESTES", r["passou"], r["total"])
