"""Tests of conversas_externas with no WhatsApp and no agent: temporary state folder, a fake browser runtime for the
send/read flow, and (when Playwright is available) the WhatsApp Web scripts run on a page shaped like WhatsApp Web.
Run with implantar.py or: python3 infra/vm/plugins/conversas_externas/tests/suite.py"""

import asyncio
import datetime as dt
import importlib.util
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


class Falha(AssertionError):
    pass


def ok(cond, msg):
    if not cond:
        raise Falha(msg)


def _carregar(nome, arquivo):
    spec = importlib.util.spec_from_file_location(nome, RAIZ / "helpers" / arquivo)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _ex():
    os.environ["CONVERSAS_EXTERNAS_PASTA"] = tempfile.mkdtemp(prefix="externas-")
    return _carregar("externas_teste", "externas.py")


def _ts(e, hora: int, dias: int = 0) -> float:
    base = dt.datetime(2026, 10, 15, hora, 0, tzinfo=e.FUSO) + dt.timedelta(days=dias)
    return base.timestamp()


class RtFalso:
    """Fake browser runtime: one tab; the scripts answer like WhatsApp Web would."""

    def __init__(self, e, invalido=False, nao_aparece=False):
        self.e, self.chamadas, self.url, self.enviado = e, [], "", False
        self.invalido, self.nao_aparece = invalido, nao_aparece

    async def call(self, metodo, *args, **kw):
        self.chamadas.append((metodo, args, kw))
        if metodo == "list":
            return {"browsers": [{"id": 1, "currentUrl": self.url or "https://web.whatsapp.com/"}]}
        if metodo == "navigate":
            self.url = args[1]
            return {}
        if metodo == "evaluate":
            s = args[1]
            if s == self.e.SCRIPT_ESTADO:
                return {"result": json.dumps({"logado": True, "conversa_aberta": not self.invalido, "invalido": self.invalido})}
            if s == self.e.SCRIPT_ENVIAR:
                self.enviado = True
                return {"result": "clicado"}
            if s == self.e.SCRIPT_MENSAGENS:
                msgs = [{"id": "false_1@c.us_A", "de": "eles", "texto": "Bom dia", "hora": ""}]
                if self.enviado and not self.nao_aparece:
                    msgs.append({"id": "true_1@c.us_B", "de": "eu", "texto": "Olá! Sou o assistente do Ilia. Vocês têm soquete 32 mm?", "hora": ""})
                return {"result": json.dumps({"mensagens": msgs})}
        return {}


class Suite:
    def __init__(self):
        self.resultados = []

    def t_telefone(self):
        e = _ex()
        ok(e.telefone("(71) 99735-6521") == "5571997356521", "celular com DDD ganha o 55")
        ok(e.telefone("+55 71 3622-4109") == "557136224109", "fixo com +55")
        ok(e.telefone("+7 916 123-45-67") == "79161234567", "número de fora do Brasil fica como veio")
        for ruim in ("123", "", "abc"):
            try:
                e.telefone(ruim)
                ok(False, f"telefone inválido aceito: {ruim!r}")
            except e.Recusa:
                pass

    def t_pergunta_e_informa(self):
        # Matheus 15/10: the agent asks and informs; committing the person needs the person's own yes
        e = _ex()
        ok("assistente" in e.validar("Oi, tem soquete 32?", primeira=True, nome_dono="Ilia"), "1ª mensagem diz que é assistente")
        ok(e.validar("Olá! Sou o assistente do Ilia. Vocês têm soquete 32 mm encaixe 1/2?", True, nome_dono="Ilia") == "",
           "pergunta com apresentação passa")
        ok(e.validar("Vocês fazem agendamento para amanhã à tarde?", False) == "", "perguntar se agendam não compromete")
        for compromete in ("Pode marcar às 15h", "Confirmo o horário", "Vou querer, pode separar", "Fechado, segue o pix"):
            ok("compromete" in e.validar(compromete, False), f"compromisso sem o sim da pessoa: {compromete}")
            ok(e.validar(compromete, False, confirmado="Ilia: sim, pode marcar às 15h") == "", f"com o sim dele passa: {compromete}")
        for dado in ("O CPF dele é 123.456.789-09", "email ilia@exemplo.com", "nascido em 1990, RG 123"):
            ok("da pessoa" in e.validar(dado, False), f"dado pessoal sem o sim dele: {dado}")
        ok("longa" in e.validar("x" * 800, False), "mensagem longa demais")

    def t_limites_protegem_o_numero(self):
        e = _ex()
        t = _ts(e, 10)
        for i in range(e.NOVAS_POR_DIA):
            e.abrir("ilia", f"Loja {i}", f"71 9{i}735-652{i}", "soquete", ts=t)
        try:
            e.abrir("ilia", "Loja 9", "71 98888-7777", "soquete", ts=t)
            ok(False, "passou do limite de contatos novos do dia")
        except e.Recusa as exc:
            ok("limite" in str(exc), str(exc))
        c = e.abrir("ilia", "Loja 0", "71 90735-6520", "outra coisa", ts=t)
        ok(c["objetivo"] == "soquete", "mesmo número aberto: a mesma conversa")
        ok(e.abrir("ilia", "Loja Z", "71 97777-1111", "x", ts=_ts(e, 10, dias=1)), "no dia seguinte, abre de novo")
        try:
            e.pode_enviar("ilia", c["id"], "Olá! Sou o assistente do Ilia. Tem?", ts=_ts(e, 22))
            ok(False, "mandou fora do horário comercial")
        except e.Recusa as exc:
            ok("horário" in str(exc), str(exc))
        ok(e.pode_enviar("ilia", c["id"], "Olá! Sou o assistente do Ilia. Tem?", ts=_ts(e, 10))["id"] == c["id"], "no horário vai")
        for i in range(e.MENSAGENS_POR_DIA):
            e.registrar_envio("ilia", c["id"], f"msg {i}", ts=_ts(e, 10))
        try:
            e.pode_enviar("ilia", c["id"], "mais uma?", ts=_ts(e, 11))
            ok(False, "passou do limite de mensagens do dia")
        except e.Recusa:
            pass
        e.encerrar("ilia", c["id"], "achou a peça")
        try:
            e.pode_enviar("ilia", c["id"], "oi?", ts=_ts(e, 10, dias=1))
            ok(False, "mandou em conversa encerrada")
        except e.Recusa as exc:
            ok("encerrada" in str(exc), str(exc))

    def t_so_resposta_nova_acorda_o_agente(self):
        e = _ex()
        t = _ts(e, 10)
        c = e.abrir("ilia", "Master Parafusos", "71 3622-4109", "soquete 32 mm", ts=t)
        e.registrar_envio("ilia", c["id"], "Olá! Sou o assistente do Ilia. Têm soquete 32?", ts=t)
        velhas = [{"id": "false_x_1", "de": "eles", "texto": "promoção de ontem"}, {"id": "true_x_2", "de": "eu", "texto": "Olá!"}]
        ok(e.registrar_lidas("ilia", c["id"], velhas, ts=t) == [], "a 1ª leitura só marca o histórico (não é novidade)")
        novas = e.registrar_lidas("ilia", c["id"], velhas + [{"id": "false_x_3", "de": "eles", "texto": "Temos sim, R$ 35"}], ts=t + 300)
        ok([n["texto"] for n in novas] == ["Temos sim, R$ 35"], f"só a resposta nova: {novas}")
        ok(e.registrar_lidas("ilia", c["id"], velhas + [{"id": "false_x_3", "de": "eles", "texto": "Temos sim, R$ 35"}], ts=t + 600) == [],
           "a mesma resposta não acorda o agente duas vezes")
        cc = e._conversa(e.carregar("ilia"), c["id"])
        aviso = e.aviso_ao_agente(cc, novas, "Ilia")
        ok("Temos sim, R$ 35" in aviso and "esperar_dono" in aviso and "soquete 32 mm" in aviso, "o agente recebe a fala e o que fazer")

    def t_vigia_no_ritmo_certo(self):
        e = _ex()
        t = _ts(e, 10)
        a = e.abrir("ilia", "A", "71 91111-1111", "x", ts=t)
        e.abrir("ilia", "Sem envio", "71 92222-2222", "x", ts=t)
        e.registrar_envio("ilia", a["id"], "Olá! Sou o assistente do Ilia.", ts=t)
        checar, _ = e.devidas("ilia", ts=t + 60)
        ok([c["id"] for c in checar] == [a["id"]], "só conversa com mensagem enviada é vigiada")
        e.registrar_lidas("ilia", a["id"], [], ts=t + 60)
        ok(e.devidas("ilia", ts=t + 120)[0] == [], "acabou de ler: espera o intervalo")
        ok(len(e.devidas("ilia", ts=t + 60 + 4 * 60)[0]) == 1, "conversa recente: de 4 em 4 min")
        e.registrar_lidas("ilia", a["id"], [], ts=t + 5 * 3600)
        ok(e.devidas("ilia", ts=t + 5 * 3600 + 5 * 60)[0] == [], "parada há horas: não lê de 4 em 4 min")
        ok(len(e.devidas("ilia", ts=t + 5 * 3600 + 15 * 60)[0]) == 1, "...e sim de 15 em 15")
        checar, fechadas = e.devidas("ilia", ts=t + 73 * 3600)
        ok(not checar and [c["id"] for c in fechadas] == [a["id"]], "3 dias sem nada: encerra e avisa")
        ok("3 dias" in e.aviso_silencio(fechadas[0]), "aviso de encerramento")

    def t_enviar_confere_que_saiu(self):
        e = _ex()
        n = _carregar("navegador_teste", "navegador.py")
        rt = RtFalso(e)

        async def rt_falso(*a):
            return rt
        n._runtime = rt_falso
        n.asyncio = type("A", (), {"sleep": staticmethod(lambda s: asyncio.sleep(0)), "Lock": asyncio.Lock})
        texto = "Olá! Sou o assistente do Ilia. Vocês têm soquete 32 mm?"
        lidas = asyncio.run(n.enviar(e, "ilia", "Ilia", "557136224109", texto))
        nav = [c for c in rt.chamadas if c[0] == "navigate"][0][1][1]
        ok(nav.startswith("https://web.whatsapp.com/send?phone=557136224109&text=Ol%C3%A1"), f"abre a conversa com o texto: {nav}")
        ok(any(m["de"] == "eu" for m in lidas), "confere que a mensagem apareceu")
        rt2 = RtFalso(e, nao_aparece=True)

        async def rt_falso2(*a):
            return rt2
        n._runtime = rt_falso2
        try:
            asyncio.run(n.enviar(e, "ilia", "Ilia", "557136224109", texto))
            ok(False, "disse que enviou sem ver a mensagem na conversa")
        except n.SemWhatsApp as exc:
            ok("confira" in str(exc), str(exc))
        rt3 = RtFalso(e, invalido=True)

        async def rt_falso3(*a):
            return rt3
        n._runtime = rt_falso3
        try:
            asyncio.run(n.ler(e, "ilia", "Ilia", "5571000000000"))
            ok(False, "número sem WhatsApp passou")
        except n.SemWhatsApp as exc:
            ok("não tem WhatsApp" in str(exc), str(exc))

    def t_scripts_numa_pagina_como_o_whatsapp(self):
        if os.environ.get("ESTAGIO"):
            return  # no Playwright browser inside the agent's staging run; runs in the local suites and CI
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return
        e = _ex()
        html = """<html><body><div id="side"><div id="pane-side"></div></div><div id="main">
          <div data-id="false_557136224109@c.us_AAA"><div class="copyable-text" data-pre-plain-text="[10:31, 15/10/2026] Loja: ">
            <span class="selectable-text">Temos sim, R$ 35</span></div></div>
          <div data-id="true_557136224109@c.us_BBB"><div class="copyable-text" data-pre-plain-text="[10:30, 15/10/2026] Eu: ">
            <span class="selectable-text">Olá! Sou o assistente do Ilia</span></div></div>
          <footer><div contenteditable="true">oi</div><button aria-label="Enviar" onclick="window.foi=1"><span data-icon="send"></span></button></footer>
        </div></body></html>"""
        with sync_playwright() as p:
            b = None
            for kw in ({}, *({"executable_path": str(x)} for x in sorted(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux*/chrome")))):
                try:
                    b = p.chromium.launch(**kw)
                    break
                except Exception:
                    continue
            if b is None:
                return  # no browser here
            pg = b.new_page()
            pg.set_content(html)
            est = json.loads(pg.evaluate(e.SCRIPT_ESTADO))
            ok(est["logado"] and est["conversa_aberta"] and not est["invalido"], f"estado: {est}")
            msgs = json.loads(pg.evaluate(e.SCRIPT_MENSAGENS))["mensagens"]
            ok([(m["de"], m["texto"]) for m in msgs] == [("eles", "Temos sim, R$ 35"), ("eu", "Olá! Sou o assistente do Ilia")],
               f"mensagens: {msgs}")
            ok(msgs[0]["hora"].startswith("10:31"), f"hora: {msgs[0]}")
            ok(pg.evaluate(e.SCRIPT_ENVIAR) == "clicado" and pg.evaluate("window.foi") == 1, "clica em enviar")
            # as the real login page showed on 15/10
            pg.set_content('<div>Scan to log in</div><div role="button" onmousedown="window.desceu=1" onclick="window.foi2=1">'
                           '<span>Link with phone number instead.</span></div>')
            est = json.loads(pg.evaluate(e.SCRIPT_ESTADO))
            ok(est["qr"] and not est["pede_numero"] and not est["logado"], f"tela do QR: {est}")
            ok(pg.evaluate(e.SCRIPT_ENTRAR_COM_NUMERO) == "clicado" and pg.evaluate("window.desceu") == 1
               and pg.evaluate("window.foi2") == 1, "clica no 'Link with phone number' com o mouse inteiro")
            pg.set_content('<div>Enter phone number</div><input type="text" aria-label="Type your phone number to log in to WhatsApp" '
                           'value="+55 71 90000-0000"><div role="button" onclick="window.foi3=1"><div>Next</div></div>')
            ok(json.loads(pg.evaluate(e.SCRIPT_ESTADO))["pede_numero"], "tela do número")
            ok(pg.evaluate(e.SCRIPT_CAMPO_TELEFONE) == "foco", "acha o campo do número")
            ok(pg.evaluate(e.SCRIPT_VALOR_TELEFONE) == "+55 71 90000-0000", "lê o número digitado")
            ok(pg.evaluate(e.SCRIPT_AVANCAR) == "clicado" and pg.evaluate("window.foi3") == 1, "clica em Next")
            pg.set_content('<div id="pane-side">'
                           '<div role="listitem" onclick="window.abriu=\'Ana\'"><span title="Ana">Ana</span><span aria-label="2 unread messages">2</span></div>'
                           '<div role="listitem"><span title="Bruno">Bruno</span></div>'
                           '<div role="listitem"><span title="Loja \'X\'">Loja</span><span aria-label="1 mensagem não lida">1</span></div>'
                           '</div><div id="main"><header><span title="Ana">Ana</span></header><footer><div contenteditable="true"></div></footer></div>')
            ok(json.loads(pg.evaluate(e.SCRIPT_NAO_LIDAS))["chats"] == [{"titulo": "Ana", "nao_lidas": 2}, {"titulo": "Loja 'X'", "nao_lidas": 1}],
               "acha as conversas com mensagem não lida")
            ok(pg.evaluate(e.script_abrir_titulo("Ana")) == "clicado" and pg.evaluate("window.abriu") == "Ana", "abre pelo nome")
            ok(pg.evaluate(e.script_abrir_titulo("Loja 'X'")) == "clicado", "nome com aspas")
            ok(pg.evaluate(e.script_abrir_titulo("Carla")) == "não achei", "nome que não está na lista")
            ok(pg.evaluate(e.SCRIPT_TITULO_ABERTO) == "Ana" and pg.evaluate(e.SCRIPT_CAIXA) == "foco", "conversa aberta e caixa vazia")
            conv = json.loads(pg.evaluate(e.SCRIPT_CONVERSAS))["chats"]
            ok([(c["titulo"], c["nao_lidas"]) for c in conv] == [("Ana", 2), ("Bruno", 0), ("Loja 'X'", 1)], f"todas as conversas: {conv}")
            pg.set_content('<div id="main"><div id="rol" style="height:100px;overflow-y:auto">'
                           '<div style="height:1000px"><div data-id="false_55@c.us_1">a</div></div></div></div>')
            pg.evaluate("document.getElementById('rol').scrollTop = 500")
            ok(pg.evaluate(e.SCRIPT_ROLAR_CIMA) == 1 and pg.evaluate("document.getElementById('rol').scrollTop") == 0,
               "rola a conversa até o começo")
            pg.set_content('<div data-link-code="ABCD,1234"></div>')
            ok(json.loads(pg.evaluate(e.SCRIPT_ESTADO))["codigo"] == "ABCD1234", "lê o código de 8 letras")
            pg.set_content('<div>Enter code on phone</div><div>K7QP-2XRT</div>')
            ok(json.loads(pg.evaluate(e.SCRIPT_ESTADO))["codigo"] == "K7QP2XRT", "lê o código escrito na tela")
            b.close()

    def t_responder_por_mim_questionario(self):
        # 16/10, Matheus (Will): not built yet; the agent suggests the approve-first start, asks, and the answers go to him
        e = _ex()
        try:
            e.salvar_preferencias("will", {"quem": "só clientes", "aprovar": "aprovar antes"})
            ok(False, "salvou sem todas as respostas")
        except e.Recusa as exc:
            ok("assuntos" in str(exc) and "tom" in str(exc) and "Pergunte" in str(exc), f"diz o que falta perguntar: {exc}")
        resp = {"quem": "só clientes, família fora", "aprovar": "aprovar cada uma no começo", "assuntos": "preço e horário; nunca desconto",
                "tom": "informal,   sem emoji", "horario": "8h às 20h", "nao_sabe": "me pergunta no Telegram"}
        reg = e.salvar_preferencias("will", json.dumps(resp))
        ok(reg["tom"] == "informal, sem emoji" and e.carregar("will")["responder_por_mim"]["quem"] == resp["quem"], "guardado")
        ok("will" in e.logins() and e.carregar("will")["conversas"] == [], "não mexe nas conversas")
        txt = e.texto_preferencias("Will", reg)
        ok(txt.startswith("📝 Will") and all(f"• {k}:" in txt for k, _ in e.QUESTIONARIO), f"aviso ao Matheus completo: {txt}")
        prompt = (RAIZ / "prompts" / "agent.system.tool.conversa_externa.md").read_text(encoding="utf-8")
        ok("UMA pergunta por mensagem" in prompt and "✅ Enviar" in prompt and "sem o ✅ dela" in prompt,
           "regra: começa aprovando e faz o questionário")
        ok(all(k in prompt for k, _ in e.QUESTIONARIO), "prompt e ferramenta pedem as mesmas respostas")

    def t_responder_fluxo(self):
        # 16/10, Matheus: "então construa" — unread chat -> draft -> the person approves -> sent; changes teach
        e = _ex()
        ok(not e.varrer_agora("will", _ts(e, 10)), "desligado: não olha nada")
        e.ligar_responder("will", True, ["Mãe", " Grupo da família "], False)
        ok(e.varrer_agora("will", _ts(e, 10)) and not e.varrer_agora("will", _ts(e, 10) + 60), "a cada 3 min")
        ok(e.varrer_agora("will", _ts(e, 10) + 200) and not e.varrer_agora("will", _ts(e, 23)), "só no horário")
        ok(e.jid_de([{"id": "false_5571999990000@c.us_ABC"}]) == ("5571999990000@c.us", "5571999990000"), "telefone do id")
        ok(e.jid_de([{"id": "false_1203630@g.us_X_557199@c.us"}])[0].endswith("@g.us"), "grupo")
        ok(e.jid_de([{"id": "true_98765@lid_X"}]) == ("98765@lid", ""), "lid: sem telefone (abre pelo nome)")
        ana = [{"id": "true_5571988887777@c.us_A1", "de": "eu", "texto": "Oi Ana"},
               {"id": "false_5571988887777@c.us_B1", "de": "eles", "texto": "Oi Will, amanhã você pode às 15h?"}]
        ok(e.novo_pedido("will", "Mãe", ana) is None, "excluída fica de fora")
        grupo = [{"id": "false_1203@g.us_C1_5571@c.us", "de": "eles", "texto": "bom dia"}]
        ok(e.novo_pedido("will", "Pelada", grupo) is None, "grupo fica de fora")
        ok(e.novo_pedido("will", "Ana", ana[:1]) is None, "a última é minha: nada a responder")
        p = e.novo_pedido("will", "Ana", ana, _ts(e, 10))
        ok(p and p["telefone"] == "5571988887777" and [m["texto"] for m in p["recebidas"]] == ["Oi Will, amanhã você pode às 15h?"],
           f"pedido: {p}")
        mais = ana + [{"id": "false_5571988887777@c.us_B2", "de": "eles", "texto": "?"}]
        ok(e.novo_pedido("will", "Ana", mais, _ts(e, 10)) is None, "já tem sugestão aberta para a Ana: não repete")
        aviso = e.aviso_pedido(p, "Will", {"tom": "informal"}, [])
        ok(f'pedido "{p["id"]}"' in aviso and "Will: Oi Ana" in aviso and "nada sai sem ele" in aviso and "tom: informal" in aviso, aviso)
        for ruim in ("", "x" * (e.TAMANHO_MAX + 1)):
            try:
                e.sugerir("will", p["id"], ruim)
                ok(False, "sugestão inválida aceita")
            except e.Recusa:
                pass
        e.sugerir("will", p["id"], "Opa, posso sim! 15h fechado.")
        e.sugerir("will", p["id"], "Posso sim, Ana. Te vejo 15h")
        texto, botoes = e.cartao("will", e.pedido("will", p["id"]))
        ok("Ana" in texto and "Te vejo 15h" in texto and [b["titulo"] for b in botoes] == ["✅ Enviar", "✏️ Mudar", "🙈 Ignorar"]
           and all(b["id"].startswith(f"rp:will:{p['id']}:") and len(b["id"]) <= 64 for b in botoes), f"cartão: {texto} {botoes}")
        e.decidir("will", p["id"], "enviado")
        ex = e.carregar("will")["exemplos_resposta"]
        ok(ex[-1]["sugerida"] == "Opa, posso sim! 15h fechado." and ex[-1]["enviada"] == "Posso sim, Ana. Te vejo 15h", "aprende com a mudança")
        try:
            e.decidir("will", p["id"], "enviado")
            ok(False, "enviou duas vezes")
        except e.Recusa:
            pass
        ok(e.novo_pedido("will", "Ana", mais, _ts(e, 11))["recebidas"][-1]["texto"] == "?", "depois de resolvida, a nova vem")
        ok("ele mandou «Posso sim, Ana. Te vejo 15h»" in e.aviso_pedido(p, "Will", {}, ex), "a correção vai no próximo pedido")
        ok("will" in e.logins() and e.ligar_responder("will", False)["ativo"] is False, "desliga")
        lidas = [{"id": "R1", "de": "eles", "texto": "a"}, {"id": "R2", "de": "eles", "texto": "e o preço?"}, {"id": "M", "de": "eu", "texto": "ok"}]
        ok(e.chegaram_depois({"recebidas": [{"id": "R1"}]}, lidas) == ["e o preço?"], "avisa o que chegou enquanto ele aprovava")
        vigia = (RAIZ / "extensions" / "python" / "job_loop" / "_48_vigiar_conversas.py").read_text(encoding="utf-8")
        ok("ex.PEDIDOS_ABERTOS}" in vigia and "abertos)" in vigia, "conversa com sugestão pendente não é reaberta (marcaria lida)")

    def t_responder_navegador(self):
        e = _ex()
        n = _carregar("navegador_teste_resp", "navegador.py")
        n.asyncio = type("A", (), {"sleep": staticmethod(lambda s: asyncio.sleep(0)), "Lock": asyncio.Lock})

        class Rt(RtFalso):
            def __init__(self, e, ja_respondi=False):
                super().__init__(e)
                self.ja, self.digitado = ja_respondi, []

            async def call(self, metodo, *args, **kw):
                if metodo == "keyboard" and kw.get("text"):
                    self.digitado.append(kw["text"])
                if metodo == "evaluate" and args[1] == self.e.SCRIPT_CAIXA:
                    return {"result": "foco"}
                if metodo == "evaluate" and args[1] == self.e.SCRIPT_MENSAGENS:
                    msgs = [{"id": "false_557199@c.us_R1", "de": "eles", "texto": "Pode às 15h?"}]
                    if self.ja:
                        msgs.append({"id": "true_557199@c.us_M0", "de": "eu", "texto": "pode sim"})
                    if self.enviado:
                        msgs.append({"id": "true_557199@c.us_M1", "de": "eu", "texto": "Posso sim, Ana. Te vejo 15h"})
                    return {"result": json.dumps({"mensagens": msgs})}
                return await super().call(metodo, *args, **kw)

        p = {"id": "a1", "titulo": "Ana", "telefone": "557199", "recebidas": [{"id": "false_557199@c.us_R1", "texto": "Pode às 15h?"}]}
        rt = Rt(e)

        async def rt1(*a):
            return rt
        n._runtime = rt1
        asyncio.run(n.responder(e, "will", "Will", p, "Posso sim, Ana.\nTe vejo 15h"))
        ok(rt.digitado == ["Posso sim, Ana.", "Te vejo 15h"] and any(c[0] == "key_chord" for c in rt.chamadas),
           f"digita as linhas com Shift+Enter: {rt.digitado}")
        nav = [c for c in rt.chamadas if c[0] == "navigate"][0][1][1]
        ok(nav == "https://web.whatsapp.com/send?phone=557199", f"abre a conversa sem texto pronto: {nav}")
        rt2 = Rt(e, ja_respondi=True)

        async def rt2f(*a):
            return rt2
        n._runtime = rt2f
        try:
            asyncio.run(n.responder(e, "will", "Will", p, "Posso sim"))
            ok(False, "mandou depois de ele já ter respondido")
        except n.SemWhatsApp as exc:
            ok("já respondeu" in str(exc) and not rt2.digitado, str(exc))

    def t_aprender_jeito_dele(self):
        # 16/10, Matheus: "opção 3, lendo as conversas no WhatsApp, sem exportar"
        e = _ex()
        conv = [{"id": "false_5571911112222@c.us_1", "de": "eles", "texto": "Oi Will, quanto fica a diária?"},
                {"id": "false_5571911112222@c.us_2", "de": "eles", "texto": "pra sábado"},
                {"id": "true_5571911112222@c.us_3", "de": "eu", "texto": "opa! diária é 250 kkk"},
                {"id": "true_5571911112222@c.us_4", "de": "eu", "texto": "sábado tenho livre"},
                {"id": "false_5571911112222@c.us_5", "de": "eles", "texto": "[imagem]"},
                {"id": "false_5571911112222@c.us_6", "de": "eles", "texto": "e o endereço da obra?"},
                {"id": "true_5571911112222@c.us_7", "de": "eu", "texto": "te mando no zap mais tarde"}]
        ok(e.pares(conv) == [("Oi Will, quanto fica a diária? / pra sábado", "opa! diária é 250 kkk / sábado tenho livre"),
                             ("e o endereço da obra?", "te mando no zap mais tarde")], f"pares: {e.pares(conv)}")
        ok(e.guardar_coleta("will", "Carlos", conv) == 2 and e.guardar_coleta("will", "Carlos", conv) == 0, "não duplica")
        grupo = [{"id": "false_1203@g.us_9_557199@c.us", "de": "eles", "texto": "bora?"}, {"id": "true_1203@g.us_8", "de": "eu", "texto": "bora"}]
        ok(e.guardar_coleta("will", "Pelada", grupo) == 0, "grupo não ensina")
        e.guardar_pares("will", [{"contato": "Ana", "recebida": "qual o valor da diaria no domingo?", "resposta": "domingo é 300 viu"},
                                 {"contato": "Ana", "recebida": "bom dia tudo bem", "resposta": "bom diaa"}])
        par = e.parecidas("will", "quanto é a diária de vocês?", "Carlos", 3)
        ok(par and "250" in par[0]["resposta"], f"acha a resposta parecida, mesma pessoa primeiro: {par}")
        ok(any("300" in x["resposta"] for x in par), "e a de outra pessoa sobre o mesmo assunto")
        ok(e.parecidas("will", "xyz qwe", "Ninguém") == [], "nada parecido: nada")
        est = e.estatisticas("will")
        ok(est["respostas"] == 4 and est["risadas"].get("kkk") == 1 and est["comeca_maiuscula_pct"] == 0, f"números: {est}")
        aviso = e.aviso_aprendizado("will", "Will", 3)
        ok("[Aprendizado pronto]" in aviso and "propor_perfil" in aviso and "propor_fatos" in aviso and "250" in aviso, aviso)
        try:
            e.aprovar("will", "perfil")
            ok(False, "aprovou sem proposta")
        except e.Recusa:
            pass
        e.propor("will", "perfil", "- tudo minúsculo\n- risada é kkk\n- frases curtas, sem ponto final")
        e.propor("will", "fatos", "- diária 250 (sábado), 300 (domingo)\n- endereço da obra: manda depois")
        ok(e.contexto_aprendido("will", {"recebidas": [{"texto": "diária?"}], "titulo": "Carlos"})["perfil"] == "",
           "proposta pendente ainda não vale")
        txt, bot = e.cartao_proposta("will", "fatos", e.carregar_aprendizado("will")["fatos"]["pendente"])
        ok("• diária 250" in txt and [b["id"] for b in bot] == ["rpa:will:fatos:aprovar", "rpa:will:fatos:mudar"], f"{txt} {bot}")
        e.aprovar("will", "perfil")
        e.aprovar("will", "fatos")
        ctx = e.contexto_aprendido("will", {"recebidas": [{"texto": "quanto a diária?"}], "titulo": "Carlos"})
        ok("risada é kkk" in ctx["perfil"] and ctx["fatos"][0].startswith("diária 250") and ctx["parecidas"], f"contexto: {ctx}")
        p = {"id": "x1", "titulo": "Carlos", "contexto": [{"de": "eles", "texto": "quanto a diária?"}], "recebidas": []}
        aviso = e.aviso_pedido(p, "Will", {}, [], ctx)
        ok("siga à risca" in aviso and "não invente" in aviso and "Carlos: «Oi Will, quanto fica" in aviso, aviso)
        # what he approves joins the base, ahead of plain history
        e.ligar_responder("will", True)
        ped = e.novo_pedido("will", "Bia", [{"id": "false_557100@c.us_Z", "de": "eles", "texto": "tem diária livre sexta?"}], _ts(e, 10))
        e.sugerir("will", ped["id"], "Tenho sim.")
        e.sugerir("will", ped["id"], "tenho sim sexta livre")
        e.decidir("will", ped["id"], "enviado")
        ok(any(x["origem"] == "corrigida" and x["resposta"] == "tenho sim sexta livre" for x in e.carregar_aprendizado("will")["pares"]),
           "a resposta aprovada vira exemplo (corrigida)")
        e.esquecer("will")
        ok(e.carregar_aprendizado("will")["pares"] == [] and e.carregar("will")["responder"]["ativo"], "esquecer apaga só o aprendido")
        ok("will" in e.logins() and len(e.logins()) == 1, "o arquivo do aprendizado não vira um login")

    def t_aprender_le_historico(self):
        e = _ex()
        n = _carregar("navegador_teste_apr", "navegador.py")
        n.asyncio = type("A", (), {"sleep": staticmethod(lambda s: asyncio.sleep(0)), "Lock": asyncio.Lock})

        class Rt(RtFalso):
            def __init__(self, e):
                super().__init__(e)
                self.aberto, self.rolagens = "", 0

            async def call(self, metodo, *args, **kw):
                if metodo == "evaluate":
                    s = args[1]
                    if s == self.e.SCRIPT_CONVERSAS:
                        return {"result": json.dumps({"chats": [{"titulo": "Carlos", "nao_lidas": 0}, {"titulo": "Ana", "nao_lidas": 2},
                                                                 {"titulo": "Mãe", "nao_lidas": 0}]})}
                    if "alvo_titulo" in s:
                        self.aberto = json.loads(s.split("const alvo_titulo = ")[1].split(";")[0])
                        return {"result": "clicado"}
                    if s == self.e.SCRIPT_TITULO_ABERTO:
                        return {"result": self.aberto}
                    if s == self.e.SCRIPT_ROLAR_CIMA:
                        self.rolagens += 1
                        return {"result": min(self.rolagens, 3) * 10}
                    if s == self.e.SCRIPT_HISTORICO:
                        return {"result": json.dumps({"mensagens": [{"id": "false_55@c.us_1", "de": "eles", "texto": "oi"},
                                                                    {"id": "true_55@c.us_2", "de": "eu", "texto": "fala"}]})}
                return await super().call(metodo, *args, **kw)

        rt = Rt(e)

        async def rtf(*a):
            return rt
        n._runtime = rtf
        lidas = asyncio.run(n.aprender(e, "will", "Will", ["mãe"]))
        ok([t for t, _ in lidas] == ["Carlos"], f"pula a não lida (marcaria lida) e a excluída: {lidas}")
        ok(rt.rolagens == 4, f"rola até parar de carregar: {rt.rolagens}")

    def t_convidado_pode_usar(self):
        arq = next((x for x in (RAIZ.parent / "login_usuarios" / "helpers" / "convidados.py",
                                Path("/a0/usr/plugins/login_usuarios/helpers/convidados.py")) if x.exists()), None)
        if arq is None:
            return  # staging copy outside the plugins folder and no live plugin: nothing to compare
        conv = arq.read_text(encoding="utf-8")
        ok('"conversa_externa"' in conv, "o Ilia (convidado) tem a ferramenta")

    async def rodar(self, so=""):
        for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
            try:
                await asyncio.to_thread(getattr(self, nome))  # own thread: tests may run their own event loop
                self.resultados.append({"teste": nome, "ok": True})
            except Exception as exc:
                self.resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                        "onde": traceback.format_exc().splitlines()[-3:]})
        return {"passou": sum(r["ok"] for r in self.resultados), "total": len(self.resultados),
                "resultados": self.resultados}


if __name__ == "__main__":
    r = asyncio.run(Suite().rodar(sys.argv[1] if len(sys.argv) > 1 else ""))
    for x in r["resultados"]:
        print("ok   " if x["ok"] else "FALHA", x["teste"], x.get("erro", ""), *(x.get("onde") or []) if not x["ok"] else "")
    print("TESTES", r["passou"], r["total"])
