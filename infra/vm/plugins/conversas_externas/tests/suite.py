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
            pg.set_content('<div><span>Entrar com número de telefone</span></div><input type="text" aria-label="Número de telefone">'
                           '<div data-link-code="ABCD,1234"></div>')
            ok(pg.evaluate(e.SCRIPT_ENTRAR_COM_NUMERO) == "clicado", "acha 'Entrar com número de telefone'")
            ok(pg.evaluate(e.SCRIPT_CAMPO_TELEFONE) == "foco", "acha o campo do número")
            ok(json.loads(pg.evaluate(e.SCRIPT_ESTADO))["codigo"] == "ABCD1234", "lê o código de 8 letras")
            b.close()

    def t_convidado_pode_usar(self):
        conv = (RAIZ.parent / "login_usuarios" / "helpers" / "convidados.py").read_text(encoding="utf-8")
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
