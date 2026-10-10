"""In-process tests of plugins/auxiliar (run by api/testar.py inside the agent, so the real scheduler is used
without a second writer of tasks.json). Only "teste_*" logins are touched; phone messages of those logins
are recorded in /a0/usr/testes/celular.jsonl (whatsapp/helpers/ponte.py) instead of being sent; everything
created is removed at the end."""

import asyncio
import datetime as dt
import importlib.util
import json
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

LOGIN = "teste_aux"
OUTRO = "teste_outro"
CAIXA = Path("/a0/usr/testes/celular.jsonl")
RAIZ = Path(__file__).resolve().parents[1]


def _carregar(nome: str, caminho: Path):
    """Same rule as the plugin's loaders: reuse the loaded module unless the file changed (a deploy)."""
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


class Falha(AssertionError):
    pass


def eq(obtido, esperado, o_que: str):
    if obtido != esperado:
        raise Falha(f"{o_que}: esperado {esperado!r}, veio {obtido!r}")


def ok(cond, o_que: str):
    if not cond:
        raise Falha(o_que)


def caixa(desde: float) -> list[dict]:
    if not CAIXA.exists():
        return []
    return [m for m in (json.loads(l) for l in CAIXA.read_text(encoding="utf-8").splitlines() if l.strip())
            if m["em"] >= desde]


class Suite:
    def __init__(self):
        self.a = _carregar("auxiliar_helper", RAIZ / "helpers" / "auxiliar.py")
        self.resultados: list[dict] = []
        self.tarefas_criadas: list[str] = []

    def limpar(self):
        for login in (LOGIN, OUTRO):
            (self.a.PASTA / f"{login}.json").unlink(missing_ok=True)
            (self.a.PASTA / "estilo" / f"{login}.md").unlink(missing_ok=True)
        for pasta in Path("/a0/usr/chats").glob("teste_aux_chat*"):
            shutil.rmtree(pasta, ignore_errors=True)

    async def rodar(self, so: str = "") -> dict:
        self.limpar()
        testes = [(n, getattr(self, n)) for n in sorted(dir(self)) if n.startswith("t_") and (not so or so in n)]
        for nome, f in testes:
            self.limpar()  # every test starts from an empty record
            inicio = time.time()
            try:
                r = f()
                if asyncio.iscoroutine(r):
                    await r
                self.resultados.append({"teste": nome, "ok": True, "s": round(time.time() - inicio, 2)})
            except Exception as exc:
                self.resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                        "onde": traceback.format_exc().splitlines()[-3:], "s": round(time.time() - inicio, 2)})
        await self._limpar_tarefas()
        self.limpar()
        passou = sum(r["ok"] for r in self.resultados)
        return {"passou": passou, "total": len(self.resultados), "resultados": self.resultados}

    async def _limpar_tarefas(self):
        from agent import AgentContext
        from helpers.task_scheduler import TaskScheduler

        agendador = TaskScheduler.get()
        for t in list(agendador.get_tasks()):
            if "TESTE_AUX" in t.name or t.uuid in self.tarefas_criadas:
                await agendador.remove_task_by_uuid(t.uuid)
                if AgentContext.get(t.uuid):
                    AgentContext.remove(t.uuid)

    # ------------------------------------------------------------------ bills
    def t_contas_valores(self):
        a = self.a
        casos = {"1.234,56": "1234.56", "129,9": "129.90", "R$ 89,90": "89.90", "1234.5": "1234.50", "0,01": "0.01",
                 "": "", "abc": "", "R$1.000.000,00": "1000000.00"}
        for entrada, esperado in casos.items():
            eq(a._valor(entrada), esperado, f"valor {entrada!r}")
        c, _ = a.salvar_conta(LOGIN, "Conta X", "2030-01-10", "1.234,56")
        eq(a._dinheiro(c), "R$ 1.234,56", "formato BRL")
        c, _ = a.salvar_conta(LOGIN, "AWS", "2030-01-10", "12.5", moeda="usd")
        eq(a._dinheiro(c), "US$ 12,50", "formato USD")
        eq(c["moeda"], "USD", "moeda maiúscula")

    def t_contas_validacao_e_dedupe(self):
        a = self.a
        c, erro = a.salvar_conta(LOGIN, "", "2030-01-10")
        ok(c is None and erro, "sem descrição recusa")
        c, erro = a.salvar_conta(LOGIN, "Luz", "amanhã")
        ok(c is None and erro, "data inválida recusa")
        c1, _ = a.salvar_conta(LOGIN, "Fatura Vivo", "2030-02-15", "129,90", fonte="e-mail 1")
        c2, _ = a.salvar_conta(LOGIN, "fatura vivo", "2030-02-15", "", fonte="e-mail 2")
        eq(c1["id"], c2["id"], "mesma conta não duplica")
        eq(c2["valor"], "129.90", "valor vazio não apaga o conhecido")
        c3, _ = a.salvar_conta(LOGIN, "Fatura Vivo", "2030-03-15", "129,90")
        ok(c3["id"] != c1["id"], "mês seguinte é outra conta")
        c4, _ = a.salvar_conta(LOGIN, "Fatura Vivo", "2030-02-15T10:00:00-03:00")
        eq(c4["id"], c1["id"], "data com hora vira a mesma data")

    def t_contas_lembretes_etapas(self):
        a = self.a
        hoje = a.agora().date()
        esperado = {}
        for dias, etapa in ((10, None), (4, None), (3, "d3"), (2, "d3"), (1, "d1"), (0, "d0"), (-1, None)):
            c, _ = a.salvar_conta(LOGIN, f"Conta D{dias}", (hoje + dt.timedelta(days=dias)).isoformat(), "10")
            esperado[c["id"]] = etapa
        vistos = {c["id"]: e for c, e in a.lembretes_de_contas(LOGIN)}
        eq(vistos, {k: v for k, v in esperado.items() if v}, "etapas de lembrete")
        eq(a.lembretes_de_contas(LOGIN), [], "segunda passada no mesmo dia não repete")

    def t_contas_adiar_e_fechar(self):
        a = self.a
        hoje = a.agora().date()
        c, _ = a.salvar_conta(LOGIN, "Internet", (hoje + dt.timedelta(days=1)).isoformat(), "99")
        eq([e for _, e in a.lembretes_de_contas(LOGIN)], ["d1"], "véspera")
        a.adiar_conta(LOGIN, c["id"])
        eq(a.lembretes_de_contas(LOGIN), [], "adiada não volta hoje")
        d = a.carregar(LOGIN)
        d["contas"][0]["lembrar_em"] = hoje.isoformat()  # simulate the next day
        a.salvar(LOGIN, d)
        eq([e[:7] for _, e in a.lembretes_de_contas(LOGIN)], ["adiado-"], "adiada volta no dia seguinte")
        ok(a.fechar_conta(LOGIN, c["id"]), "fecha")
        ok(not a.fechar_conta(LOGIN, c["id"]), "não fecha duas vezes")
        eq(a.contas_abertas(LOGIN), [], "paga sai da lista")
        eq(a.adiar_conta(LOGIN, c["id"]), None, "não adia conta fechada")

    def t_contas_texto(self):
        a = self.a
        hoje = a.agora().date()
        for dias, trecho in ((0, "vence hoje"), (1, "vence amanhã"), (5, "vence em 5 dias"), (-2, "venceu")):
            c, _ = a.salvar_conta(LOGIN, f"T{dias}", (hoje + dt.timedelta(days=dias)).isoformat())
            ok(trecho in a.linha_conta(c), f"{trecho} em {a.linha_conta(c)!r}")
        m = a.mensagem_conta(c, "d1")
        ok(m.startswith("💳 *Conta vence amanhã*"), "título da mensagem")
        for b in a.botoes_conta(LOGIN, c["id"]):
            ok(len(b["id"].encode()) <= 64, "callback do Telegram cabe em 64 bytes")

    def t_contas_isoladas_por_pessoa(self):
        a = self.a
        a.salvar_conta(LOGIN, "Só minha", "2030-01-01")
        eq(a.contas_abertas(OUTRO, 99999), [], "outra pessoa não vê")

    # ------------------------------------------------------------------ drafts
    def t_rascunho_chave(self):
        a = self.a
        base = a._chave("Ana <ana@x.com>", "Orçamento")
        for para, assunto in (("ana@x.com", "Re: Orçamento"), ("ANA@X.COM", "RES: Orçamento"),
                              ("Ana Souza <ana@x.com>", "Fwd: RE: orçamento"), ("ana@x.com", "  Orçamento ")):
            eq(a._chave(para, assunto), base, f"mesma conversa: {para} / {assunto}")
        ok(a._chave("bob@x.com", "Orçamento") != base, "outro destinatário")
        ok(a._chave("ana@x.com", "Contrato") != base, "outro assunto")

    def t_rascunho_ciclo(self):
        a = self.a
        r1 = a.novo_rascunho(LOGIN, "Ana <ana@x.com>", "Orçamento", "Oi, Ana!\n\nPode ser terça.\n\nAbraço,\nMatheus", "Quer o dia")
        eq(a.ja_tratado(LOGIN, "ana@x.com", "Re: Orçamento")["id"], r1["id"], "tratado")
        r2 = a.novo_rascunho(LOGIN, "ana@x.com", "Re: Orçamento", "Oi, Ana! Terça às 9h.", "Quer o dia")
        eq(a.obter_rascunho(LOGIN, r1["id"])["estado"], "substituido", "versão anterior substituída")
        eq(a.ja_tratado(LOGIN, "ana@x.com", "Orçamento")["id"], r2["id"], "a nova é a vigente")
        a.marcar_rascunho(LOGIN, r2["id"], "descartado")
        eq(a.ja_tratado(LOGIN, "ana@x.com", "Orçamento")["estado"], "descartado", "dispensado continua tratado")
        d = a.carregar(LOGIN)
        for r in d["rascunhos"]:
            r["criado"] -= 8 * 86400
        a.salvar(LOGIN, d)
        eq(a.ja_tratado(LOGIN, "ana@x.com", "Orçamento"), None, "depois de 7 dias pode rascunhar de novo")

    def t_rascunho_mensagem(self):
        a = self.a
        r = a.novo_rascunho(LOGIN, "Ana <ana@x.com>", "Orçamento", "Oi, Ana!", "Quer saber o dia")
        m = a.mensagem_rascunho(r)
        ok(m.startswith("✉️ *Resposta pronta — Orçamento*"), "título")
        ok("O que pediram: Quer saber o dia" in m and m.endswith("Oi, Ana!"), "pedido e texto")
        ids = [b["id"] for b in a.botoes_rascunho(LOGIN, r["id"])]
        eq([i.rsplit(":", 1)[1] for i in ids], ["usar", "ajustar", "deixa"], "botões")
        ok(all(len(i.encode()) <= 64 for i in ids), "callback cabe em 64 bytes")

    def t_mensagens_dele_filtra(self):
        a = self.a
        pasta = Path("/a0/usr/chats/teste_aux_chat1")
        pasta.mkdir(parents=True, exist_ok=True)
        logs = [{"type": "user", "content": t} for t in (
            "Qro afastar ou da zoom com o dedo", "✅ Faz pra mim (fio solto 1): x", "/nova", "💡 algo",
            "N funcionou ainda\n\n(leitura automática das abreviações desta mensagem: \"n\" = não.)", "x" * 700)]
        logs.append({"type": "response", "content": "resposta do agente"})
        (pasta / "chat.json").write_text(json.dumps({"data": {"whatsapp_de": LOGIN}, "log": {"logs": logs}}), encoding="utf-8")
        outra = Path("/a0/usr/chats/teste_aux_chat2")
        outra.mkdir(parents=True, exist_ok=True)
        (outra / "chat.json").write_text(json.dumps({"data": {}, "log": {"logs": [{"type": "user", "content": "prompt de tarefa"}]}}), encoding="utf-8")
        eq(a.mensagens_dele(LOGIN), ["Qro afastar ou da zoom com o dedo", "N funcionou ainda"], "só o que ele digitou")

    def t_estilo(self):
        a = self.a
        eq(a.estilo(LOGIN), "", "sem perfil")
        a.salvar_estilo(LOGIN, "E-mail: curto.\n" * 1000)
        ok(len(a.estilo(LOGIN)) <= 6000, "perfil limitado")

    # ------------------------------------------------------------------ meetings (real scheduler)
    def _tarefas(self, titulo: str):
        from helpers.task_scheduler import TaskScheduler

        return [t for t in TaskScheduler.get().get_tasks() if titulo in t.name]

    async def t_reuniao_agenda_e_reagenda(self):
        from agent import AgentContext

        a = self.a
        ini = a.agora().replace(microsecond=0) + dt.timedelta(days=1)
        r = await a.agendar_reuniao(LOGIN, "ev-teste-1", "TESTE_AUX Alinhamento", ini.isoformat(),
                                    (ini + dt.timedelta(minutes=45)).isoformat(), "joao@x.com", "Meet")
        ok("briefing" in r and "pós" in r, f"resposta: {r}")
        ts = self._tarefas("TESTE_AUX Alinhamento")
        eq(sorted(t.name.split(":")[0] for t in ts), ["📅 Briefing", "📝 Pós-reunião"], "duas tarefas")
        planos = {t.name.split(":")[0]: t.plan.todo[0] for t in ts}
        eq(planos["📅 Briefing"], ini - dt.timedelta(minutes=30), "briefing 30 min antes")
        eq(planos["📝 Pós-reunião"], ini + dt.timedelta(minutes=55), "pós 10 min depois do fim")
        for t in ts:
            ctx = AgentContext.get(t.uuid)
            ok(ctx is not None and ctx.get_data("dono") == LOGIN, "contexto da tarefa já tem o dono certo")
        ok("já estava" in await a.agendar_reuniao(LOGIN, "ev-teste-1", "TESTE_AUX Alinhamento", ini.isoformat(),
                                                   (ini + dt.timedelta(minutes=45)).isoformat()), "repetido não duplica")
        eq(len(self._tarefas("TESTE_AUX Alinhamento")), 2, "continua com 2")
        antigos = {t.uuid for t in ts}
        novo = ini + dt.timedelta(hours=2)
        await a.agendar_reuniao(LOGIN, "ev-teste-1", "TESTE_AUX Alinhamento", novo.isoformat(),
                                (novo + dt.timedelta(minutes=30)).isoformat())
        ts2 = self._tarefas("TESTE_AUX Alinhamento")
        eq(len(ts2), 2, "reagendada continua com 2")
        ok(not antigos & {t.uuid for t in ts2}, "tarefas antigas removidas")
        ok(all(AgentContext.get(u) is None for u in antigos), "contextos antigos removidos")
        eq({t.name.split(":")[0]: t.plan.todo[0] for t in ts2}["📅 Briefing"], novo - dt.timedelta(minutes=30), "novo horário")
        r = await a.cancelar_reuniao(LOGIN, "ev-teste-1")
        ok("cancelada" in r, r)
        eq(self._tarefas("TESTE_AUX Alinhamento"), [], "cancelada remove as tarefas")
        eq(a.carregar(LOGIN)["reunioes"], [], "e o registro")
        ok("não estava" in await a.cancelar_reuniao(LOGIN, "ev-teste-1"), "cancelar de novo é inofensivo")

    async def t_reuniao_casos_de_borda(self):
        a = self.a
        agora = a.agora().replace(microsecond=0)
        ok("já terminou" in await a.agendar_reuniao(LOGIN, "ev-p", "TESTE_AUX Passada", (agora - dt.timedelta(hours=2)).isoformat(),
                                                      (agora - dt.timedelta(hours=1)).isoformat()), "passada")
        ok("Diga" in await a.agendar_reuniao(LOGIN, "", "TESTE_AUX Sem id", agora.isoformat()), "sem id")
        ok("Diga" in await a.agendar_reuniao(LOGIN, "ev-x", "TESTE_AUX Data ruim", "semana que vem"), "data inválida")
        # starts in 4 min: too late for a briefing, still gets the follow-up
        ini = agora + dt.timedelta(minutes=4)
        r = await a.agendar_reuniao(LOGIN, "ev-4", "TESTE_AUX Em 4 min", ini.isoformat(), (ini + dt.timedelta(minutes=20)).isoformat())
        eq([t.name.split(":")[0] for t in self._tarefas("TESTE_AUX Em 4 min")], ["📝 Pós-reunião"], f"só o pós ({r})")
        # starts in 20 min: briefing right away (1 min from now)
        ini = agora + dt.timedelta(minutes=20)
        await a.agendar_reuniao(LOGIN, "ev-20", "TESTE_AUX Em 20 min", ini.isoformat())
        b = [t for t in self._tarefas("TESTE_AUX Em 20 min") if t.name.startswith("📅")]
        eq(len(b), 1, "briefing em cima da hora")
        ok(abs((b[0].plan.todo[0] - (agora + dt.timedelta(minutes=1))).total_seconds()) < 90, "sai em ~1 min")
        await self._limpar_tarefas()  # before it fires
        # no end time: 1 h meeting; end before start: 1 h meeting
        ini = agora + dt.timedelta(days=2)
        await a.agendar_reuniao(LOGIN, "ev-f", "TESTE_AUX Sem fim", ini.isoformat(), (ini - dt.timedelta(hours=1)).isoformat())
        pos = [t for t in self._tarefas("TESTE_AUX Sem fim") if t.name.startswith("📝")][0]
        eq(pos.plan.todo[0], ini + dt.timedelta(minutes=70), "fim inválido vira 1 h")
        await self._limpar_tarefas()

    def t_reuniao_pos_pendente(self):
        a = self.a
        d = a.carregar(LOGIN)
        fim = time.time() - 30 * 60
        d["reunioes"] = [{"evento_id": "ev-pos", "titulo": "TESTE_AUX Pós", "inicio_ts": fim - 3600, "fim_ts": fim,
                          "inicio_txt": "10/10 09:00", "pos_registrado": False}]
        a.salvar(LOGIN, d)
        eq([r["evento_id"] for r in a.pos_pendentes(LOGIN)], ["ev-pos"], "pendente depois da pergunta")
        ok(a.registrar_pos(LOGIN, "ev-pos"), "registra")
        eq(a.pos_pendentes(LOGIN), [], "registrado sai")

    # ------------------------------------------------------------------ phone buttons (receber.py)
    def _receber(self):
        return _carregar("receber_testes", Path("/a0/usr/plugins/whatsapp/api/receber.py"))

    async def t_botoes_rascunho(self):
        a, rc = self.a, self._receber()
        r = a.novo_rascunho(LOGIN, "Ana <ana@x.com>", "Orçamento", "Oi, Ana!\n\nTerça às 9h.\n\nAbraço,\nMatheus")
        desde = time.time()
        eq((await rc._botao_rascunho(OUTRO, f"rd:{LOGIN}:{r['id']}:usar"))["ok"], False, "botão de outra pessoa é recusado")
        await rc._botao_rascunho(LOGIN, f"rd:{LOGIN}:{r['id']}:usar")
        msgs = caixa(desde)
        eq(len(msgs), 2, "aviso + bloco para copiar")
        ok(msgs[1]["texto"].startswith("```") and "Terça às 9h." in msgs[1]["texto"], "texto em bloco copiável")
        eq(a.obter_rascunho(LOGIN, r["id"])["estado"], "usado", "marcado como usado")
        r2 = a.novo_rascunho(LOGIN, "bob@x.com", "Contrato", "Oi, Bob!")
        desde = time.time()
        await rc._botao_rascunho(LOGIN, f"rd:{LOGIN}:{r2['id']}:deixa")
        eq(a.obter_rascunho(LOGIN, r2["id"])["estado"], "descartado", "deixa")
        await rc._botao_rascunho(LOGIN, f"rd:{LOGIN}:{r2['id']}:deixa")
        ok("já foi" in caixa(desde)[-1]["texto"], "segundo toque avisa que já foi tratado")
        await rc._botao_rascunho(LOGIN, f"rd:{LOGIN}:inexistente:usar")
        ok("já foi" in caixa(desde)[-1]["texto"], "rascunho inexistente")

    async def t_botoes_conta(self):
        a, rc = self.a, self._receber()
        c, _ = a.salvar_conta(LOGIN, "Água", (a.agora().date() + dt.timedelta(days=1)).isoformat(), "55,10")
        desde = time.time()
        eq((await rc._botao_conta(OUTRO, f"ct:{LOGIN}:{c['id']}:paga"))["ok"], False, "de outra pessoa")
        await rc._botao_conta(LOGIN, f"ct:{LOGIN}:{c['id']}:amanha")
        ok("amanhã" in caixa(desde)[-1]["texto"], "confirma o adiamento")
        ok(a.carregar(LOGIN)["contas"][0].get("lembrar_em"), "guarda o dia")
        await rc._botao_conta(LOGIN, f"ct:{LOGIN}:{c['id']}:paga")
        eq(a.carregar(LOGIN)["contas"][0]["estado"], "paga", "paga")
        await rc._botao_conta(LOGIN, f"ct:{LOGIN}:{c['id']}:paga")
        ok("já foi fechada" in caixa(desde)[-1]["texto"], "segundo toque")
        c2, _ = a.salvar_conta(LOGIN, "Não é minha", "2030-01-01")
        await rc._botao_conta(LOGIN, f"ct:{LOGIN}:{c2['id']}:ignorar")
        eq([x["estado"] for x in a.carregar(LOGIN)["contas"] if x["id"] == c2["id"]], ["ignorada"], "ignorar")

    # ------------------------------------------------------------------ voice
    def t_voz_pronuncia(self):
        a = self.a
        eq(a.pronuncia("O IA Business e as IAs"), "O I.A. Business e as I.As.", "sigla falada")
        eq(a.pronuncia("MEIA hora, IARA"), "MEIA hora, IARA", "não mexe dentro de palavras")

    def t_voz_so_quando_vale(self):
        a = self.a
        ok(not a.vale_audio("*Bom dia!* Nada que precise de você hoje. 👍"), "nada a dizer: sem áudio")
        ok(not a.vale_audio("*Bom dia!* Reunião às 15h."), "muito curto: sem áudio")
        ok(a.vale_audio("*Bom dia! Sábado, 10/10*\n*Precisa de você:* aprovar o orçamento da instalação que a Carla mandou ontem; "
                        "ela espera resposta até segunda.\n*Hoje:* 15h reunião com o João sobre o contrato do NEXOS."), "resumo real: com áudio")

    def t_voz_texto_falavel(self):
        a = self.a
        t = a._falavel("*Bom dia!* 📰 Resumo\n- item https://x.com/a?b=1\n\n\n- `código` [link]")
        for proibido in ("*", "📰", "http", "`", "[", "\n\n"):
            ok(proibido not in t, f"{proibido!r} removido: {t!r}")

    def t_voz_roteiro_e_audio(self):
        a = self.a
        resumo = ("*Bom dia! Resumo de 10/10*\n*Precisa de você:* a análise do NEXOS na Meta (ads_read e pages_messaging) "
                  "segue sem decisão.\n*Andamento:* ROS-F4-007 concluída; ROS-F5-006 em validação cega, ciclo 1.\n"
                  "*Contas:* Fatura Vivo R$ 129,90 vence 15/10.\n*Hoje:* 15:00 reunião com João (Meet).")
        falado = a.roteiro_falado(resumo)
        palavras = len(falado.split())
        ok(falado.startswith("Bom dia, Matheus"), f"abertura: {falado[:40]!r}")
        ok(45 <= palavras <= 125, f"curto e objetivo: {palavras} palavras")
        for proibido in ("ROS-", "R$", "*", "http", "ads_read", "15/10"):
            ok(proibido not in falado, f"{proibido!r} não pode ser lido em voz: {falado!r}")
        destino = Path("/a0/usr/testes/voz_teste.ogg")
        erro = a.audio(falado, destino)
        eq(erro, "", "áudio gerado")
        eq(a.ULTIMA_VOZ.get("motor"), "generative", "voz generativa (natural), nunca a neural")
        eq(a.ULTIMA_VOZ.get("voz"), "Camila", "voz Camila")
        info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,sample_rate:format=duration",
                                          "-of", "json", str(destino)], capture_output=True, text=True).stdout)
        eq(info["streams"][0]["codec_name"], "opus", "nota de voz do Telegram é OGG/Opus")
        duracao = float(info["format"]["duration"])
        ok(15 <= duracao <= 60, f"duração {duracao:.0f}s")
        ok(1.9 <= palavras / duracao <= 3.4, f"ritmo natural: {palavras / duracao * 60:.0f} palavras/min")
        self.resultados.append({"teste": "t_voz_roteiro_e_audio·medidas", "ok": True,
                                "info": {"palavras": palavras, "duracao_s": round(duracao, 1),
                                         "ppm": round(palavras / duracao * 60), "texto": falado}})
