"""In-process tests of plugins/prospeccao (POST /plugins/prospeccao/testar). Only "teste_*" logins; their phone
messages are recorded to /a0/usr/testes/celular.jsonl. The clock is simulated by replacing the helper's agora()."""

import asyncio
import datetime as dt
import importlib.util
import json
import re
import sys
import time
import traceback
from pathlib import Path

LOGIN, OUTRO = "teste_pro", "teste_pro2"
RAIZ = Path(__file__).resolve().parents[1]
CAIXA = Path("/a0/usr/testes/celular.jsonl")


def _carregar(nome: str, caminho: Path):
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


def eq(a, b, o):
    if a != b:
        raise Falha(f"{o}: esperado {b!r}, veio {a!r}")


def ok(c, o):
    if not c:
        raise Falha(o)


def caixa(desde):
    if not CAIXA.exists():
        return []
    return [m for m in (json.loads(l) for l in CAIXA.read_text(encoding="utf-8").splitlines() if l.strip())
            if m["em"] >= desde and m["usuario"] in (LOGIN, OUTRO)]


TEXTOS = [
    "Oi, {n}! Vi o bolo de pote de ninho com morango de vocês, que capricho na camada. Vocês sabem quanto sobra em cada pote depois da embalagem? Faço essa conta de graça se me mandar a receita. — Matheus, da Raiz Connect",
    "Oi, {n}! Acompanhei o cardápio fit da semana, gostei da opção de escondidinho de mandioca. Com a carne subindo, muita marmitaria vende com margem menor sem perceber. Calculo de graça o lucro de 1 marmita. Topa? — Matheus, da Raiz Connect",
    "Oi, {n}! Que lindo o kit de salgados para festa com coxinha de costela. Vocês já sabem quanto lucram por cento de salgado depois do óleo e das embalagens? Se quiser, faço essa conta sem custo. — Matheus, da Raiz Connect",
    "Oi, {n}! Vi que vocês abriram encomendas de congelados para o mês, a lasanha de berinjela parece ótima. Me manda a receita e o preço que eu calculo quanto sobra em cada uma, de graça. — Matheus, da Raiz Connect",
]

DM_A = ("Oi, Ana! Vi a marmita de frango com batata-doce de vocês — capricho no tempero. Vocês sabem quanto sobra de "
        "verdade em cada marmita depois de embalagem e taxa do iFood? Me manda a receita que eu faço a conta. — Matheus, da Raiz Connect")


class Suite:
    def __init__(self):
        self.p = _carregar("prospeccao_helper", RAIZ / "helpers" / "prospeccao.py")
        self.resultados = []
        self.relogio = None

    def limpar(self):
        for l in (LOGIN, OUTRO):
            (self.p.PASTA / f"{l}.json").unlink(missing_ok=True)

    def em(self, ts):  # simulated clock
        self.relogio = ts
        self.p.agora = lambda: self.relogio

    def hora(self, h, dias=0):
        base = dt.datetime.now(self.p._tz()).replace(hour=h, minute=0, second=0, microsecond=0) + dt.timedelta(days=dias)
        return base.timestamp()

    async def rodar(self, so=""):
        original = self.p.agora
        for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
            self.limpar()
            self.p.agora = original
            inicio = time.time()
            try:
                r = getattr(self, nome)()
                if asyncio.iscoroutine(r):
                    await r
                self.resultados.append({"teste": nome, "ok": True, "s": round(time.time() - inicio, 2)})
            except Exception as exc:
                self.resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                        "onde": traceback.format_exc().splitlines()[-3:]})
        self.p.agora = original
        self.limpar()
        return {"passou": sum(r["ok"] for r in self.resultados), "total": len(self.resultados), "resultados": self.resultados}

    def _dia(self, dias_atras=0):
        return (dt.datetime.fromtimestamp(self.p.agora(), self.p._tz()).date() - dt.timedelta(days=dias_atras)).isoformat()

    def _lead(self, handle="marmitasdaana", **extra):
        base = {"canal": "instagram", "handle": handle, "nome": "Marmitas da Ana", "segmento": "marmitaria",
                "cidade": "Salvador", "motivo": "marmitas fit por encomenda, cardápio semanal com preços",
                "seguidores": "3.2k", "ultimo_post": self._dia(2), "canais": ["encomenda", "whatsapp"],
                "sinais": ["kits"], "cardapio": True, "post_recente": "marmita de frango com batata-doce"}
        r = self.p.registrar(LOGIN, [{**base, **extra}])
        return r["criados"][0]["id"] if r["criados"] else None

    def _executar(self, lid, tipo, texto="", variante=""):
        """Propose, approve and execute one action (clock inside business hours, spaced)."""
        out = self.p.propor(LOGIN, [{"lead_id": lid, "tipo": tipo, "texto": texto, "variante": variante}])
        ok(out["propostas"], f"proposta de {tipo} aceita: {out['recusadas']}")
        aid = out["propostas"][0]["id"]
        self.p.decidir(LOGIN, aid, "aprovar")
        d = self.p.carregar(LOGIN)
        d["config"]["executar_em_teste"] = True
        d["config"]["conta_instagram"] = "raizconnect"
        self.p.salvar(LOGIN, d)
        a, motivo = self.p.proxima(LOGIN, "raizconnect")
        ok(a and a["id"] == aid, f"próxima é a aprovada ({motivo})")
        self.p.resultado(LOGIN, aid, True, "feito")
        return aid

    # ------------------------------------------------------------------ leads
    def t_registro_dedupe_e_validacao(self):
        p = self.p
        lid = self._lead("marmitasdaana")
        for variante in ("@MarmitasDaAna", "https://www.instagram.com/marmitasdaana/?hl=pt", "instagram.com/marmitasdaana"):
            r = p.registrar(LOGIN, [{"canal": "instagram", "handle": variante, "nome": "x", "segmento": "x", "cidade": "x", "motivo": "x"}])
            eq(r["repetidos"][0]["id"], lid, f"mesmo perfil: {variante}")
        r = p.registrar(LOGIN, [{"canal": "instagram", "handle": "outro", "nome": "Outro"}])
        ok(r["recusados"] and "faltam" in r["recusados"][0]["motivo"], "sem cidade/segmento/motivo é recusado")
        r = p.registrar(LOGIN, [{"canal": "tiktok", "handle": "y", "nome": "y", "segmento": "y", "cidade": "y", "motivo": "y"}])
        ok(r["recusados"], "canal fora do playbook")
        eq(len(p.carregar(LOGIN)["leads"]), 1, "um lead só")
        eq(p.carregar(OUTRO)["leads"], [], "isolado por pessoa")

    # ------------------------------------------------------------------ lead score
    def t_nota_rubrica(self):
        p = self.p
        self.em(self.hora(11))
        r = p.registrar(LOGIN, [{"canal": "instagram", "handle": "topo", "nome": "Topo", "segmento": "Marmitaria fit",
                                 "cidade": "Salvador - BA", "motivo": "m", "seguidores": "3,2 mil", "ultimo_post": self._dia(3),
                                 "canais": ["ifood", "encomenda", "whatsapp", "telepatia"], "sinais": ["reajuste", "kits", "inventado"],
                                 "cardapio": True, "link_pedido": True}])
        eq(r["criados"][0]["nota"], 95, f"25+15+15+10+10+10+10 (desconhecidos não contam): {p.carregar(LOGIN)['leads'][0]['avaliacao']}")
        eq(r["criados"][0]["faixa"], "quente", "95 é quente")
        lead = p.carregar(LOGIN)["leads"][0]
        eq(lead["avaliacao"]["partes"]["canais"], 10, "3 canais = 9 +1")
        eq(lead["evidencias"]["ultimo_post"], self._dia(3), "evidência guardada")
        r = p.registrar(LOGIN, [{"canal": "instagram", "handle": "medio", "nome": "Médio", "segmento": "confeitaria",
                                 "cidade": "Campinas", "motivo": "m", "seguidores": "18,9 mil", "ultimo_post": self._dia(12)}])
        ok(r["recusados"] and "nota 54" in r["recusados"][0]["motivo"], f"54 fica abaixo de 55: {r}")
        eq(p._numero("18,9 mil"), 18900, "18,9 mil")
        eq(p._numero("2.194"), 2194, "2.194")
        eq(p._numero("33.3k"), 33300, "33.3k")
        eq(p._numero(816), 816, "número")

    def t_nota_exclusoes_e_cortes(self):
        p = self.p
        self.em(self.hora(11))
        boa = {"canal": "instagram", "nome": "X", "segmento": "marmitaria", "cidade": "Salvador", "motivo": "m",
               "seguidores": "2000", "ultimo_post": self._dia(1)}
        casos = [({"ultimo_post": self._dia(40)}, "parado"), ({"seguidores": "120"}, "pequeno"),
                 ({"seguidores": "80 mil"}, "grande"), ({"cidade": "Recife"}, "região"), ({"exclusoes": ["franquia"]}, "franquia"),
                 ({"exclusoes": ["curso"]}, "parceiro"), ({"segmento": "pet shop"}, "segmento"), ({"ultimo_post": ""}, "último post"),
                 ({"ultimo_post": "ontem"}, "último post")]
        for i, (mudar, chave) in enumerate(casos):
            r = p.registrar(LOGIN, [{**boa, "handle": f"fora{i}", **mudar}])
            ok(not r["criados"] and r["recusados"] and chave in r["recusados"][0]["motivo"], f"{chave}: {r}")
        d = p.carregar(LOGIN)
        eq(d["leads"], [], "nenhum virou lead")
        eq(len(d["rejeitados"]), len(casos), "todos anotados como examinados (não voltam por 60 dias)")
        ok("fora0" in p.resumo_contexto(LOGIN), "contexto mostra os recusados pela nota")

    def t_ordem_por_nota(self):
        p = self.p
        self.em(self.hora(11))
        fraco = self._lead("fraco", segmento="padaria", seguidores="400", sinais=["kits"], canais=["loja", "delivery", "whatsapp"],
                           ultimo_post=self._dia(20))  # 15+8+6+10+10+5+5 = 59
        forte = self._lead("forte", link_pedido=True, sinais=["reajuste", "insumo", "kits"])
        notas = {l["handle"]: l["nota"] for l in p.carregar(LOGIN)["leads"]}
        ok(notas["forte"] > notas["fraco"] >= p.NOTA_MINIMA, f"notas {notas}")
        eq([l["id"] for l in p.devidos(LOGIN)["aquecer"]], [forte, fraco], "maior nota primeiro na fila")
        ok("nota " in p.resumo_contexto(LOGIN), "contexto mostra a nota")

    # ------------------------------------------------------------------ pre-approved (reviewer)
    def _revisor(self, reprovar=(), erro=False, lixo=False):
        chamadas = []

        def fake(pedido):
            ids = re.findall(r"## Item (\w+) — ", pedido)
            chamadas.append({"ids": ids, "pedido": pedido})
            if erro:
                raise TimeoutError("sem rede")
            if lixo:
                return "não sei"
            return json.dumps({"itens": [{"id": i, "aprovado": i not in reprovar, "motivo": "ok" if i not in reprovar else "cita post que não existe"}
                                         for i in ids]})
        self.p.revisor = fake
        return chamadas

    def _aquecido(self, handle):
        lid = self._lead(handle)
        d = self.p.carregar(LOGIN)
        l = self.p._lead(d, lid)
        l["etapa"], l["atualizado"] = "aquecido", l["atualizado"] - 3 * 86400
        self.p.salvar(LOGIN, d)
        return lid

    def t_auto_aprova_com_revisor(self):
        p = self.p
        self.em(self.hora(10))
        p.definir_auto(LOGIN, True)
        chamadas = self._revisor()
        try:
            a1, a2, a3 = self._lead("um"), self._lead("dois"), self._aquecido("tres")
            p.mudar_etapa(LOGIN, a2, "respondeu", "quero saber mais")
            out = p.propor(LOGIN, [{"lead_id": a1, "tipo": "aquecer", "texto": "Que capricho nessa marmita de frango! Sai mais no almoço ou no jantar?",
                                    "base": "post de ontem: marmita de frango"},
                                   {"lead_id": a3, "tipo": "dm_abertura", "texto": DM_A},
                                   {"lead_id": a2, "tipo": "resposta", "texto": "Oi! Que bom que gostou. Me manda a receita de uma marmita e o preço que eu faço a conta. — Matheus"}])
            eq(sorted(a["tipo"] for a in out["automaticas"]), ["aquecer", "dm_abertura"], f"pré-aprovadas: {out}")
            eq([a["tipo"] for a in out["propostas"]], ["resposta"], "resposta continua com o Matheus")
            eq(len(chamadas), 1, "uma chamada ao revisor para o lote")
            eq(len(chamadas[0]["ids"]), 2, "resposta não vai ao revisor automático")
            ok("post de ontem: marmita de frango" in chamadas[0]["pedido"] and "Playbook de prospecção" in chamadas[0]["pedido"],
               "revisor recebe o que o agente viu e o playbook")
            d = p.carregar(LOGIN)
            auto = [a for a in d["acoes"] if a.get("auto")]
            ok(all(a["estado"] == "aprovada" and a.get("decidida") for a in auto), "aprovadas e com hora")
            d["config"].update({"executar_em_teste": True, "conta_instagram": "raizconnect"})
            p.salvar(LOGIN, d)
            a, motivo = p.proxima(LOGIN, "raizconnect")
            ok(a and a.get("auto"), f"execução pega a pré-aprovada ({motivo})")

            class Ctx:
                dados = {}
                def set_data(self, k, v): self.dados[k] = v
                def get_data(self, k): return self.dados.get(k)
            c = Ctx()
            p.liberar(c, a)
            ok("pré-aprovada" in c.get_data("_aprovacoes_liberadas")["motivo"], "revisor de aprovações vê que é pré-aprovada")
            # follow/like without text: no reviewer call needed
            chamadas.clear()
            out = p.propor(LOGIN, [{"lead_id": self._lead("quatro"), "tipo": "aquecer", "texto": ""}])
            eq(len(out["automaticas"]), 1, "seguir e curtir sem texto passa direto")
            eq(chamadas, [], "sem texto, sem revisor")
        finally:
            p.revisor = None

    def t_auto_revisor_reprova_ou_falha(self):
        p = self.p
        self.em(self.hora(10))
        p.definir_auto(LOGIN, True)
        try:
            a, b = self._aquecido("aa1"), self._aquecido("bb1")
            # first, a reviewer that rejects one item
            self._revisor(reprovar=())
            prim = p.propor(LOGIN, [{"lead_id": a, "tipo": "dm_abertura", "texto": DM_A}])
            ok(prim["automaticas"], "a primeira passa")
            texto_b = TEXTOS[1].format(n="Bia")
            ids_antes = {x["id"] for x in p.carregar(LOGIN)["acoes"]}
            self.p.revisor = lambda pedido: json.dumps({"itens": [{"id": i, "aprovado": False, "motivo": "cita escondidinho que não aparece no perfil"}
                                                                  for i in re.findall(r"## Item (\w+) — ", pedido)]})
            out = p.propor(LOGIN, [{"lead_id": b, "tipo": "dm_abertura", "texto": texto_b}])
            eq(out["automaticas"], [], "reprovada não sai sozinha")
            eq(len(out["propostas"]), 1, "vai ao Matheus")
            nova = next(x for x in p.carregar(LOGIN)["acoes"] if x["id"] not in ids_antes)
            eq(nova["estado"], "proposta", "fica esperando o ✅")
            ok("escondidinho" in nova["revisao"], "com o motivo do revisor")
            for modo in ({"erro": True}, {"lixo": True}):
                p.decidir(LOGIN, nova["id"], "pular")
                self._revisor(**modo)
                out = p.propor(LOGIN, [{"lead_id": b, "tipo": "dm_abertura", "texto": texto_b + " "}])
                eq(out["automaticas"], [], f"revisor {modo}: falha fechada")
                ok(out["propostas"] and out["propostas"][0]["revisao"], f"motivo registrado ({modo})")
                nova = out["propostas"][0]
        finally:
            p.revisor = None

    def t_auto_respeita_limites_e_desligado(self):
        p = self.p
        self.em(self.hora(10))
        p.definir_auto(LOGIN, True)
        chamadas = self._revisor()
        try:
            lids = [self._lead(f"lim{i}") for i in range(10)]
            out = p.propor(LOGIN, [{"lead_id": l, "tipo": "aquecer", "texto": ""} for l in lids])
            eq(len(out["automaticas"]), p.LIMITE_PILOTO["aquecer"], "só até o limite do dia (piloto)")
            eq(len(out["recusadas"]), 10 - p.LIMITE_PILOTO["aquecer"], "o resto é recusado pelo limite")
            ok(all("limite" in r["motivo"] for r in out["recusadas"]), "motivo é o limite")
            d = p.carregar(LOGIN)
            d["config"].update({"executar_em_teste": True, "conta_instagram": "raizconnect"})
            p.salvar(LOGIN, d)
            feitas = 0
            for _ in range(12):
                a, _m = p.proxima(LOGIN, "raizconnect")
                if not a:
                    break
                p.resultado(LOGIN, a["id"], True, "ok")
                feitas += 1
                self.em(self.relogio + p.INTERVALO + 1)
            eq(feitas, p.LIMITE_PILOTO["aquecer"], "execução também para no limite")
            p.definir_auto(LOGIN, False)
            chamadas.clear()
            self.em(self.relogio + 86400)
            out = p.propor(LOGIN, [{"lead_id": self._lead("manual1"), "tipo": "aquecer", "texto": "Esse bolo de pote ficou lindo! Qual sabor sai mais?"}])
            ok("automaticas" not in out and out["propostas"], "desligado: tudo vai ao Matheus")
            eq(chamadas, [], "desligado: revisor nem é chamado")
        finally:
            p.revisor = None

    # ------------------------------------------------------------------ end-of-day summary
    def t_resumo_hoje(self):
        p = self.p
        self.em(self.hora(10))
        eq(p.resumo_hoje(LOGIN), "", "dia vazio: nada a mandar")
        a = self._lead("resumo1")
        self._executar(a, "aquecer", "Que capricho nessa marmita! Vocês entregam no fim de semana também?")
        b = self._aquecido("resumo2")
        self.em(self.relogio + p.INTERVALO + 1)
        self._executar(b, "dm_abertura", DM_A)
        p.mudar_etapa(LOGIN, b, "respondeu", "quanto custa?")
        p.registrar(LOGIN, [{"canal": "instagram", "handle": "parado", "nome": "P", "segmento": "marmitaria", "cidade": "Salvador",
                             "motivo": "m", "seguidores": "900", "ultimo_post": self._dia(90)}])
        txt = p.resumo_hoje(LOGIN)
        ok("Responderam" in txt and "@resumo2" in txt, f"respostas primeiro: {txt}")
        ok(txt.index("Responderam") < txt.index("Feito hoje"), "respostas antes do resto")
        ok("1 aquecidos" in txt and "1 primeiras mensagens" in txt, f"contagem do dia: {txt}")
        ok(txt.count("•") >= 3, "uma linha por perfil")
        ok("Oi, Ana!" in txt, "mostra a DM que saiu")
        ok("@resumo1 — seguiu e curtiu; comentou «Que capricho" in txt, f"cada aquecimento com o comentário: {txt}")
        ok("@resumo2 — primeira mensagem: «Oi, Ana!" in txt, "cada mensagem com o texto")
        ok("leads novos" in txt and "nota " in txt and "1 perfis examinados e descartados" in txt, f"novos com nota e descartados: {txt}")
        ok(len(txt) < 1500, "curto")
        self.em(self.relogio + 86400)
        eq(p.resumo_hoje(LOGIN), "", "no dia seguinte, sem novidade não manda nada")

    def t_resposta_em_comentario_avisa_uma_vez(self):
        p = self.p
        self.em(self.hora(10))
        lid = self._aquecido("comentou1")
        dm = p.propor(LOGIN, [{"lead_id": lid, "tipo": "dm_abertura", "texto": DM_A}])["propostas"][0]
        r1 = p.mudar_etapa(LOGIN, lid, "respondeu", "Obrigada! O mais pedido é o frango com batata-doce", "comentario")
        ok(r1["novidade"], "primeira vez é novidade")
        r2 = p.mudar_etapa(LOGIN, lid, "respondeu", "Obrigada! O mais pedido é o frango com batata-doce", "comentario")
        ok(not r2["novidade"], "a rodada seguinte relendo a mesma resposta não avisa de novo")
        eq(sum(1 for h in p._lead(p.carregar(LOGIN), lid)["historico"] if h["tipo"] == "etapa:respondeu"), 1, "registrada uma vez")
        eq(next(a for a in p.carregar(LOGIN)["acoes"] if a["id"] == dm["id"])["estado"], "cancelada",
           "a DM fria cancela: quem respondeu recebe resposta pessoal")
        ok(p.propor(LOGIN, [{"lead_id": lid, "tipo": "resposta", "texto": "Oi! Vi sua resposta lá no post: frango com batata-doce é campeão mesmo. Quer que eu calcule quanto sobra em cada uma? — Matheus"}])["propostas"],
           "resposta pessoal pode ser proposta")
        ok(p.mudar_etapa(LOGIN, lid, "respondeu", "E vocês fazem o cálculo como?", "direct")["novidade"], "mensagem nova é novidade")
        txt = p.resumo_hoje(LOGIN)
        ok("no Direct: «E vocês fazem o cálculo como?»" in txt, f"relatório mostra a última resposta e onde: {txt}")

    def t_execucao_exige_conferir_respostas(self):
        p = self.p
        self.em(self.hora(10))
        lid = self._lead("conf1")
        aid = p.propor(LOGIN, [{"lead_id": lid, "tipo": "aquecer", "texto": ""}])["propostas"][0]["id"]
        p.decidir(LOGIN, aid, "aprovar")
        d = p.carregar(LOGIN)
        d["config"].update({"executar_em_teste": True, "conta_instagram": "raizconnect", "exigir_conferencia": True})
        p.salvar(LOGIN, d)
        a, motivo = p.proxima(LOGIN, "raizconnect")
        ok(not a and "confira as respostas" in motivo, f"sem conferência não executa: {motivo}")
        ok(p.conferido(LOGIN, "nenhuma", "ok"), "conferência vazia é recusada")
        eq(p.conferido(LOGIN, "nenhuma conversa nova", "Notificações · Hoje · emporiodacau começou a seguir você · 2 h"), "", "conferência real")
        a, motivo = p.proxima(LOGIN, "raizconnect")
        ok(a and a["id"] == aid, f"com conferência executa ({motivo})")
        p.resultado(LOGIN, aid, True, "ok")
        self.em(self.relogio + p.CONFERENCIA_VALE + 60)
        a2 = self._lead("conf2")
        aid2 = p.propor(LOGIN, [{"lead_id": a2, "tipo": "aquecer", "texto": ""}])["propostas"][0]["id"]
        p.decidir(LOGIN, aid2, "aprovar")
        a, motivo = p.proxima(LOGIN, "raizconnect")
        ok(not a and "confira" in motivo, "conferência vencida: confere de novo na rodada seguinte")

    def t_metricas_por_faixa(self):
        p = self.p
        self.em(self.hora(10))
        lid = self._aquecido("faixa1")
        self._executar(lid, "dm_abertura", DM_A)
        m = p.metricas(LOGIN, 7)
        ok(m["por_faixa"] and list(m["por_faixa"].values())[0]["abordados"] == 1, f"por faixa: {m['por_faixa']}")

    # ------------------------------------------------------------------ texts
    def t_textos_barrados(self):
        p = self.p
        d = p.carregar(LOGIN)
        casos = {
            "dm_abertura": [(DM_A.replace("Me manda", "Veja raizconnect.com.br e me manda"), "link"),
                            (DM_A + " Promoção imperdível!", "palavra"), (DM_A.replace("Matheus", "Equipe"), "assine"),
                            ("Oi! Tudo bem?", "curta"), (DM_A * 5, "longa")],
            "aquecer": [("Que lindo! Conheçam a Raiz Connect", "Raiz"), ("Lindo! www.site.com.br", "link")],
        }
        for tipo, lista in casos.items():
            for texto, chave in lista:
                motivo = p.validar_texto(tipo, texto, d, "x")
                ok(motivo, f"{tipo} deveria barrar ({chave}): {texto[:50]}")
        eq(p.validar_texto("aquecer", "", d, "x"), "", "aquecer sem comentário é válido")
        eq(p.validar_texto("dm_abertura", DM_A, d, "x"), "", "abertura boa passa")
        eq(p.validar_texto("resposta", "Fiz a conta: o CMV dessa marmita deu 41%, ou seja, sobra R$ 3,10 por unidade. — Matheus", d, "x"),
           "", "resposta pode usar CMV (quem pediu o cálculo)")

    def t_mesmo_texto_para_duas_pessoas_e_barrado(self):
        p = self.p
        a, b = self._lead("aaa"), self._lead("bbb")
        for lid in (a, b):
            d = p.carregar(LOGIN)
            next(l for l in d["leads"] if l["id"] == lid)["etapa"] = "aquecido"
            next(l for l in d["leads"] if l["id"] == lid)["atualizado"] -= 3 * 86400
            p.salvar(LOGIN, d)
        ok(p.propor(LOGIN, [{"lead_id": a, "tipo": "dm_abertura", "texto": DM_A}])["propostas"], "primeira passa")
        r = p.propor(LOGIN, [{"lead_id": b, "tipo": "dm_abertura", "texto": DM_A}])
        ok(r["recusadas"] and "igual" in r["recusadas"][0]["motivo"], f"igual para outra pessoa: {r}")
        quase = DM_A.replace("Ana", "Bia")
        r = p.propor(LOGIN, [{"lead_id": b, "tipo": "dm_abertura", "texto": quase}])
        ok(r["recusadas"], "trocar só o nome também é massa")

    # ------------------------------------------------------------------ sequence
    def t_sequencia_e_tempos(self):
        p = self.p
        t0 = self.hora(10)
        self.em(t0)
        lid = self._lead()
        r = p.propor(LOGIN, [{"lead_id": lid, "tipo": "dm_abertura", "texto": DM_A}])
        ok(r["recusadas"] and "aquecimento" in r["recusadas"][0]["motivo"], "DM antes de aquecer é barrada")
        self._executar(lid, "aquecer", "Que capricho nessa marmita! Vocês entregam no fim de semana também?")
        eq(p._lead(p.carregar(LOGIN), lid)["etapa"], "aquecido", "aquecido")
        eq([l["id"] for l in p.devidos(LOGIN)["dm_abertura"]], [], "abertura ainda não é devida (2 dias)")
        self.em(t0 + 2 * 86400 + 60)
        eq([l["id"] for l in p.devidos(LOGIN)["dm_abertura"]], [lid], "dia 2: abertura devida")
        self._executar(lid, "dm_abertura", DM_A)
        lead = p._lead(p.carregar(LOGIN), lid)
        eq(lead["etapa"], "abordado", "abordado")
        ok(lead.get("variante") in ("A", "B"), "variante registrada no lead")
        r = p.propor(LOGIN, [{"lead_id": lid, "tipo": "dm_lembrete", "texto": "Oi, Ana! Só pra não deixar passar: o cálculo continua de pé, é só mandar a receita de um 🙂"}])
        ok(r["recusadas"] and "cedo" in r["recusadas"][0]["motivo"], "lembrete antes de 3 dias é barrado")
        self.em(self.relogio + 3 * 86400 + 60)
        self._executar(lid, "dm_lembrete", "Oi, Ana! Só pra não deixar passar: o cálculo continua de pé, é só mandar a receita de um 🙂")
        eq(p._lead(p.carregar(LOGIN), lid)["etapa"], "lembrado", "lembrado")
        r = p.propor(LOGIN, [{"lead_id": lid, "tipo": "dm_lembrete", "texto": "Oi, Ana! Passando de novo para lembrar do cálculo gratuito da sua marmita, combinado?"}])
        ok(r["recusadas"], "terceira mensagem sem resposta é barrada")
        self.em(self.relogio + 5 * 86400 + 60)
        eq(p.fechar_vencidos(LOGIN), 1, "fecha como sem_resposta")
        eq(p._lead(p.carregar(LOGIN), lid)["etapa"], "sem_resposta", "sem_resposta")
        r = p.propor(LOGIN, [{"lead_id": lid, "tipo": "resposta", "texto": "Oi, Ana! Voltando aqui sobre o cálculo da marmita de vocês. — Matheus"}])
        ok(r["recusadas"], "encerrado não recebe mais nada")

    def t_resposta_e_descarte(self):
        p = self.p
        lid = self._lead()
        r = p.propor(LOGIN, [{"lead_id": lid, "tipo": "resposta", "texto": "Oi, Ana! Obrigado pela resposta, fico à disposição. — Matheus"}])
        ok(r["recusadas"], "resposta só para quem escreveu")
        p.mudar_etapa(LOGIN, lid, "descartado", "disse que não tem interesse")
        r = p.propor(LOGIN, [{"lead_id": lid, "tipo": "resposta", "texto": "Tranquilo, Ana! Obrigado pelo retorno e sucesso com as marmitas. — Matheus"}])
        ok(r["propostas"], f"agradecer uma vez a quem disse não: {r['recusadas']}")
        r = p.propor(LOGIN, [{"lead_id": lid, "tipo": "aquecer", "texto": ""}])
        ok(r["recusadas"], "descartado não volta a ser aquecido")

    def t_responder_cancela_abordagens_pendentes(self):
        p = self.p
        lid = self._lead()
        aid = p.propor(LOGIN, [{"lead_id": lid, "tipo": "aquecer", "texto": ""}])["propostas"][0]["id"]
        p.decidir(LOGIN, aid, "aprovar")
        p.mudar_etapa(LOGIN, lid, "respondeu", "perguntou como funciona")
        eq(next(a for a in p.carregar(LOGIN)["acoes"] if a["id"] == aid)["estado"], "cancelada", "abordagem pendente cancelada")

    def t_variantes_alternam(self):
        p = self.p
        vs = []
        for i in range(4):
            lid = self._lead(f"lead{i}")
            d = p.carregar(LOGIN)
            l = p._lead(d, lid)
            l["etapa"], l["atualizado"] = "aquecido", l["atualizado"] - 3 * 86400
            p.salvar(LOGIN, d)
            vs.append(p.propor(LOGIN, [{"lead_id": lid, "tipo": "dm_abertura", "texto": TEXTOS[i].format(n=f"Pessoa {i}")}])["propostas"][0]["variante"])
        eq(vs, ["A", "B", "A", "B"], "A/B alternando")

    # ------------------------------------------------------------------ limits, hours, pause
    def t_cotas_do_piloto(self):
        p = self.p
        ids = [self._lead(f"c{i}") for i in range(10)]
        r = p.propor(LOGIN, [{"lead_id": i, "tipo": "aquecer", "texto": ""} for i in ids])
        eq(len(r["propostas"]), p.LIMITE_PILOTO["aquecer"], "piloto: 8 aquecer por dia")
        ok(all("limite" in x["motivo"] for x in r["recusadas"]), "o resto por limite")
        d = p.carregar(LOGIN)
        d["config"]["inicio"] = p.agora() - 8 * 86400
        p.salvar(LOGIN, d)
        eq(p.limites(p.carregar(LOGIN))["aquecer"], p.LIMITE_DIA["aquecer"], "depois de 7 dias, limite cheio")

    def t_propostas_pendentes_contam_na_cota(self):
        p = self.p
        r1 = p.propor(LOGIN, [{"lead_id": self._lead(f"q{i}"), "tipo": "aquecer", "texto": ""} for i in range(5)])
        r2 = p.propor(LOGIN, [{"lead_id": self._lead(f"r{i}"), "tipo": "aquecer", "texto": ""} for i in range(5)])
        eq(len(r1["propostas"]) + len(r2["propostas"]), p.LIMITE_PILOTO["aquecer"], "duas rodadas no mesmo dia não passam da cota")

    def t_execucao_horario_espacamento_bloqueio(self):
        p = self.p
        self.em(self.hora(10))
        ids = []
        for i in range(3):
            lid = self._lead(f"e{i}")
            aid = p.propor(LOGIN, [{"lead_id": lid, "tipo": "aquecer", "texto": ""}])["propostas"][0]["id"]
            p.decidir(LOGIN, aid, "aprovar")
            ids.append(aid)
        d = p.carregar(LOGIN)
        d["config"]["conta_instagram"] = "raizconnect"
        p.salvar(LOGIN, d)
        a, motivo = p.proxima(LOGIN, "raizconnect")
        ok(a is None and "teste" in motivo, "login de teste não executa por padrão")
        d = p.carregar(LOGIN)
        d["config"]["executar_em_teste"] = True
        p.salvar(LOGIN, d)
        a, motivo = p.proxima(LOGIN, "cardosomatheus1")
        ok(a is None and "pessoal" in motivo, f"conta pessoal ativa é recusada ({motivo})")
        a, motivo = p.proxima(LOGIN, "")
        ok(a is None and "conta_ativa" in motivo, "sem dizer a conta ativa, nada")
        a, motivo = p.proxima(LOGIN, "outraconta")
        ok(a is None and "@raizconnect" in motivo, "outra conta qualquer é recusada")
        eq(p.definir_conta(LOGIN, "@cardosomatheus1"), "conta inválida para prospecção", "a pessoal nunca vira a conta da prospecção")
        self.em(self.hora(7))
        a, motivo = p.proxima(LOGIN, "raizconnect")
        ok(a is None and "horário" in motivo, f"7h: fora do horário ({motivo})")
        self.em(self.hora(20, 0) + 60)
        ok(p.proxima(LOGIN, "raizconnect")[0] is None, "20h01: fora")
        self.em(self.hora(10))
        a, _ = p.proxima(LOGIN, "raizconnect")
        eq(a["id"], ids[0], "a mais antiga aprovada primeiro")
        p.resultado(LOGIN, a["id"], True, "ok")
        a, motivo = p.proxima(LOGIN, "raizconnect")
        ok(a is None and "espaçamento" in motivo, "3 min entre ações")
        self.em(self.relogio + 181)
        a, _ = p.proxima(LOGIN, "raizconnect")
        eq(a["id"], ids[1], "segunda depois de 3 min")
        p.resultado(LOGIN, a["id"], False, "Tente novamente mais tarde", bloqueio=True)
        self.em(self.relogio + 600)
        a, motivo = p.proxima(LOGIN, "raizconnect")
        ok(a is None and "pausado" in motivo, "bloqueio pausa tudo")
        self.em(self.relogio + 48 * 3600)
        if p.HORARIO[0] <= p._hora_local() < p.HORARIO[1]:
            ok(p.proxima(LOGIN, "raizconnect")[0], "volta depois de 48 h")
        eq(p._lead(p.carregar(LOGIN), p.carregar(LOGIN)["acoes"][1]["lead_id"])["etapa"], "novo", "falha não avança a etapa")

    def t_aprovacao_expira_e_nao_decide_duas_vezes(self):
        p = self.p
        lid = self._lead()
        aid = p.propor(LOGIN, [{"lead_id": lid, "tipo": "aquecer", "texto": ""}])["propostas"][0]["id"]
        self.em(p.agora() + 25 * 3600)
        eq(p.decidir(LOGIN, aid, "aprovar")["estado"], "expirada", "depois de 24 h expira")
        eq(p.decidir(LOGIN, aid, "aprovar"), None, "não decide de novo")

    def t_edicao_volta_para_aprovacao(self):
        p = self.p
        lid = self._lead()
        aid = p.propor(LOGIN, [{"lead_id": lid, "tipo": "aquecer", "texto": "Que lindo esse prato!"}])["propostas"][0]["id"]
        p.decidir(LOGIN, aid, "aprovar")
        a, motivo = p.editar(LOGIN, aid, "Ficou lindo! Esse sai mais no iFood ou na encomenda?")
        eq(a["estado"], "proposta", f"editada volta para aprovação ({motivo})")
        a, motivo = p.editar(LOGIN, aid, "Conheça a Raiz Connect!")
        ok(a is None and motivo, "edição também passa pelas regras")

    # ------------------------------------------------------------------ phone and buttons
    async def t_botoes(self):
        p = self.p
        rc = _carregar("receber_testes_pro", Path("/a0/usr/plugins/whatsapp/api/receber.py"))
        a1, a2, a3 = (p.propor(LOGIN, [{"lead_id": self._lead(h), "tipo": "aquecer", "texto": ""}])["propostas"][0]["id"]
                      for h in ("b1", "b2", "b3"))
        pid = p.guardar_pacote(LOGIN, [a1, a2])
        eq((await rc._botao_prospeccao(OUTRO, f"pa:{LOGIN}:{a3}:aprovar"))["ok"], False, "botão de outra pessoa")
        desde = time.time()
        await rc._botao_prospeccao(LOGIN, f"pa:{LOGIN}:{pid}:todas")
        estados = {a["id"]: a["estado"] for a in p.carregar(LOGIN)["acoes"]}
        eq((estados[a1], estados[a2], estados[a3]), ("aprovada", "aprovada", "proposta"), "aprovar todas do pacote")
        ok("2 aprovadas" in caixa(desde)[-1]["texto"], "confirma quantas")
        await rc._botao_prospeccao(LOGIN, f"pa:{LOGIN}:{a3}:pular")
        eq(next(a for a in p.carregar(LOGIN)["acoes"] if a["id"] == a3)["estado"], "pulada", "pular")
        await rc._botao_prospeccao(LOGIN, f"pa:{LOGIN}:{a3}:aprovar")
        ok("já foi decidida" in caixa(desde)[-1]["texto"], "segundo toque")
        for b in p.botoes_acao(LOGIN, a1) + [{"id": f"pa:{LOGIN}:{pid}:todas"}]:
            ok(len(b["id"].encode()) <= 64, "callback cabe em 64 bytes")

    def t_mensagem_no_celular(self):
        p = self.p
        lid = self._lead(seguidores="3.2k")
        a = p.propor(LOGIN, [{"lead_id": lid, "tipo": "aquecer", "texto": "Que capricho! Vocês entregam no fim de semana?"}])["propostas"][0]
        m = p.mensagem_acao(a, p._lead(p.carregar(LOGIN), lid))
        for trecho in ("🔥 Aquecer", "Marmitas da Ana", "@marmitasdaana", "Salvador", "3.2k", "Por quê:", "comentar", "instagram.com/marmitasdaana"):
            ok(trecho in m, f"mensagem mostra {trecho!r}")

    def t_liberacao_para_o_revisor(self):
        p = self.p

        class Ctx:
            dados = {}

            def set_data(self, k, v):
                self.dados[k] = v

            def get_data(self, k):
                return self.dados.get(k)

        c = Ctx()
        p.liberar(c, {"id": "abc", "tipo": "dm_abertura"})
        lib = c.get_data("_aprovacoes_liberadas")
        eq(sorted(lib["categorias"]), ["mensagem_terceiros", "publicar"], "só essas categorias")
        ok(0 < lib["ate"] - p.agora() <= p.LIBERACAO, "janela de minutos")
        p.encerrar_liberacao(c)
        eq(c.get_data("_aprovacoes_liberadas"), None, "fecha depois do resultado")

    def t_rejeitados(self):
        p = self.p
        lid = self._lead("jaelead")
        eq(p.rejeitar(LOGIN, [{"handle": "@RedeGrande", "motivo": "franquia"}, {"handle": "jaelead", "motivo": "x"}]), 1,
           "rejeita só quem não é lead")
        ctx = p.resumo_contexto(LOGIN)
        ok("redegrande" in ctx and "rejeitados" in ctx, "contexto mostra os rejeitados")
        d = p.carregar(LOGIN)
        d["rejeitados"]["redegrande"]["em"] -= 61 * 86400
        p.salvar(LOGIN, d)
        p.rejeitar(LOGIN, [])
        ok("redegrande" not in p.carregar(LOGIN)["rejeitados"], "depois de 60 dias pode ser reexaminado")

    def t_metricas(self):
        p = self.p
        self.em(self.hora(10))
        for i, (var, resp) in enumerate((("A", True), ("A", False), ("B", True), ("B", True))):
            lid = self._lead(f"m{i}")
            d = p.carregar(LOGIN)
            l = p._lead(d, lid)
            l["etapa"], l["atualizado"] = "aquecido", l["atualizado"] - 3 * 86400
            p.salvar(LOGIN, d)
            self.em(self.relogio + 200)
            self._executar(lid, "dm_abertura", TEXTOS[i].format(n=f"Pessoa {i}"), var)
            if resp:
                p.mudar_etapa(LOGIN, lid, "respondeu" if i != 3 else "lead", "")
        m = p.metricas(LOGIN, 7)
        eq(m["geral"]["abordados"], 4, "4 abordados")
        eq(m["geral"]["responderam"], 3, "3 responderam")
        eq(m["geral"]["leads"], 1, "1 lead")
        eq(m["por_variante"]["A"]["taxa_resposta"], 50.0, "A: 50%")
        eq(m["por_variante"]["B"]["taxa_resposta"], 100.0, "B: 100%")
