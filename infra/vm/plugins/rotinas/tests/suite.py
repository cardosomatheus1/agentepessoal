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
FIM = RAIZ / "extensions" / "python" / "_functions" / "agent" / "Agent" / "monologue" / "end" / "_10_portao_fim.py"


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
        for m in ("rotinas_portao", "rotinas_helper"):  # the tests changed their folders and sources
            sys.modules.pop(m, None)
        return {"passou": sum(r["ok"] for r in self.resultados), "total": len(self.resultados), "resultados": self.resultados}


if __name__ == "__main__":
    r = asyncio.run(Suite().rodar(sys.argv[1] if len(sys.argv) > 1 else ""))
    for x in r["resultados"]:
        print("ok   " if x["ok"] else "FALHA", x["teste"], x.get("erro", ""), *(x.get("onde") or []) if not x["ok"] else "")
    print("TESTES", r["passou"], r["total"])
