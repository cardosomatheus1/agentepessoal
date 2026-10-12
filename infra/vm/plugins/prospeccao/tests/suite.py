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
            (self.p.PASTA / f"{l}_fontes.json").unlink(missing_ok=True)

    def _fontes(self):
        f = _carregar("prospeccao_fontes_teste", RAIZ / "helpers" / "fontes.py")
        f.PAUSA_BUSCA = f.PAUSA_GUIAPJ = 0
        return f

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
                                   {"lead_id": a2, "tipo": "resposta", "texto": "Oi, pessoal da Dois! Que bom que gostou. A calculadora grátis mostra quanto sobra em cada marmita: raizconnect.com.br/materiais/precificacao/calculadora — Matheus"}])
            eq(sorted(a["tipo"] for a in out["automaticas"]), ["aquecer", "dm_abertura", "resposta"], f"pré-aprovadas: {out}")
            eq(out["propostas"], [], "resposta também sai pelo revisor (11/10)")
            eq(len(chamadas), 1, "uma chamada ao revisor para o lote")
            eq(len(chamadas[0]["ids"]), 3, "resposta vai ao revisor com o lote")
            ok("O QUE A PESSOA DISSE: quero saber mais" in chamadas[0]["pedido"], "revisor vê o que a pessoa disse")
            ok("post de ontem: marmita de frango" in chamadas[0]["pedido"] and "Playbook de prospecção" in chamadas[0]["pedido"],
               "revisor recebe o que o agente viu e o playbook")
            d = p.carregar(LOGIN)
            auto = [a for a in d["acoes"] if a.get("auto")]
            ok(all(a["estado"] == "aprovada" and a.get("decidida") for a in auto), "aprovadas e com hora")
            d["config"].update({"executar_em_teste": True, "conta_instagram": "raizconnect"})
            p.salvar(LOGIN, d)
            a, motivo = p.proxima(LOGIN, "raizconnect")
            ok(a and a.get("auto"), f"execução pega a pré-aprovada ({motivo})")
            eq(a["tipo"], "resposta", "resposta sai antes das outras pré-aprovadas")

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
            a, b, c = self._aquecido("aa1"), self._aquecido("bb1"), self._aquecido("cc1")
            self._revisor(reprovar=())
            prim = p.propor(LOGIN, [{"lead_id": a, "tipo": "dm_abertura", "texto": DM_A}])
            ok(prim["automaticas"], "a primeira passa")
            reprova = lambda pedido: json.dumps({"itens": [{"id": i, "aprovado": False, "motivo": "cita escondidinho que não aparece no perfil"}
                                                           for i in re.findall(r"## Item (\w+) — ", pedido)]})
            # sem aprovação (padrão, pedido do Matheus 12/10): reprovada volta ao agente para reescrever, não vai ao celular
            self.p.revisor = reprova
            for n in range(p.VERSOES_REVISOR):
                out = p.propor(LOGIN, [{"lead_id": b, "tipo": "dm_abertura", "texto": TEXTOS[1].format(n="Bia") + " " * n}])
                eq((out["automaticas"], out["propostas"]), ([], []), f"versão {n}: não sai e não vai ao Matheus")
                ok(out["recusadas"] and "escondidinho" in out["recusadas"][0]["motivo"], f"motivo do revisor volta ao agente: {out['recusadas']}")
                if n < p.VERSOES_REVISOR - 1:
                    ok(out["recusadas"][0]["motivo"].startswith("REESCREVA"), "manda reescrever")
            ok("amanhã" in out["recusadas"][0]["motivo"], f"última versão avisa que acabou: {out['recusadas']}")
            out = p.propor(LOGIN, [{"lead_id": b, "tipo": "dm_abertura", "texto": TEXTOS[2].format(n="Bia")}])
            ok(out["recusadas"] and "amanhã" in out["recusadas"][0]["motivo"] and not self.p.carregar(LOGIN)["acoes"][-1]["texto"].startswith(TEXTOS[2][:10]),
               f"depois de {p.VERSOES_REVISOR} versões, nem vai ao revisor: {out['recusadas']}")
            ok(all(x["estado"] == "pulada" for x in p.carregar(LOGIN)["acoes"] if x["lead_id"] == b), "reprovadas ficam como puladas")
            # revisor fora do ar: nada sai sozinho e nada vai ao celular
            for n, modo in enumerate(({"erro": True}, {"lixo": True}, {"erro": True}, {"lixo": True})):
                self._revisor(**modo)
                out = p.propor(LOGIN, [{"lead_id": c, "tipo": "dm_abertura", "texto": TEXTOS[3].format(n="Cida") + " " * n}])
                eq((out["automaticas"], out["propostas"]), ([], []), f"revisor {modo}: falha fechada, sem celular")
                ok(out["recusadas"] and "fora do ar" in out["recusadas"][0]["motivo"], f"diz que o revisor está fora, não que reprovou: {out['recusadas']}")
            eq(p._versoes_reprovadas(p.carregar(LOGIN), c, "dm_abertura"), 0, "revisor fora do ar não gasta as versões do dia")
            # quem desligar o "sem aprovação" volta ao fluxo antigo (vai ao ✅)
            d = p.carregar(LOGIN)
            d["config"]["sem_aprovacao"] = False
            p.salvar(LOGIN, d)
            self.p.revisor = reprova
            d2 = self._aquecido("dd1")
            out = p.propor(LOGIN, [{"lead_id": d2, "tipo": "dm_abertura", "texto": TEXTOS[0].format(n="Dani")}])
            eq(len(out["propostas"]), 1, "com sem_aprovacao desligado, reprovada vai ao Matheus")
            eq(out["propostas"][0]["estado"], "proposta", "fica esperando o ✅")
        finally:
            p.revisor = None

    def t_auto_respeita_limites_e_desligado(self):
        p = self.p
        self.em(self.hora(10))
        p.definir_auto(LOGIN, True)
        chamadas = self._revisor()
        try:
            n = p.LIMITE_PILOTO["aquecer"] + 2
            lids = [self._lead(f"lim{i}") for i in range(n)]
            out = p.propor(LOGIN, [{"lead_id": l, "tipo": "aquecer", "texto": ""} for l in lids])
            eq(len(out["automaticas"]), p.LIMITE_PILOTO["aquecer"], "só até o limite do dia (piloto)")
            eq(len(out["recusadas"]), n - p.LIMITE_PILOTO["aquecer"], "o resto é recusado pelo limite")
            ok(all("limite" in r["motivo"] for r in out["recusadas"]), "motivo é o limite")
            d = p.carregar(LOGIN)
            d["config"].update({"executar_em_teste": True, "conta_instagram": "raizconnect"})
            p.salvar(LOGIN, d)
            feitas = 0
            for _ in range(n + 2):
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
        ok("2 entraram hoje" in txt and "estoque " in txt and "prontos para aquecer" in txt and "1 descartados hoje" in txt,
           f"leads: novos de hoje separados do estoque e dos descartados: {txt}")
        # a visit that failed: one readable line per profile, first sentence of why
        c = self._lead("resumo3")
        self.em(self.relogio + p.INTERVALO + 1)
        aid = p.propor(LOGIN, [{"lead_id": c, "tipo": "aquecer", "texto": ""}])["propostas"][0]["id"]
        p.decidir(LOGIN, aid, "aprovar")
        p.proxima(LOGIN, "raizconnect")
        p.resultado(LOGIN, aid, False, "Perfil parado há 90 dias. Não segui nem curti; o último post é de julho.")
        txt = p.resumo_hoje(LOGIN)
        ok("Não saíram" in txt and "@resumo3 (🔥 Aquecer) — Perfil parado há 90 dias." in txt and "julho" not in txt,
           f"falha legível, uma linha por perfil: {txt}")
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

    def t_etapa_e_proposta_aceitam_o_arroba(self):
        p = self.p
        self.em(self.hora(10))
        lid = self._aquecido("arroba1")
        r = p.mudar_etapa(LOGIN, "@arroba1", "respondeu", "oieeee….entra sim!!!", "comentario")
        ok(r and r["id"] == lid and r["novidade"], f"etapa pelo @ (11/10: zen.marmitas recusado): {r and r['id']}")
        ok(p.mudar_etapa(LOGIN, "https://www.instagram.com/arroba1/", "lead", "mandou a receita"), "etapa pela URL do perfil")
        prop = p.propor(LOGIN, [{"lead_id": "arroba1", "tipo": "resposta",
                                 "texto": "Oi! Que bom que o rondelli entra. Quer que eu calcule quanto sobra em cada kit? — Matheus"}])
        ok(prop["propostas"] and prop["propostas"][0]["lead_id"] == lid, f"proposta pelo @ guarda o id interno: {prop}")
        eq(p.mudar_etapa(LOGIN, "@naoexiste", "respondeu", "x"), None, "@ desconhecido continua recusado")

    def t_fontes_leem_o_catalogo_de_cnpj(self):
        f = self._fontes()
        card = """<article class=\"panel result-card advanced-result-row\"><div class=\"advanced-result-summary\"><div class=\"advanced-result-content\"><div class=\"advanced-result-line advanced-result-line-top\"><h3 class=\"result-card-title\">COZINHA DE CHEF</h3><span class=\"advanced-result-legal-name\" title=\"CCLAY COMERCIO DE REFEICAO LTDA\">CCLAY COMERCIO DE REFEICAO LTDA</span><span class=\"pill neutral\">09.205.662/0001-72</span><span class=\"pill light\">SALVADOR/BA</span><span class=\"pill\">Ativa</span><span class=\"pill\">Matriz</span></div><div class=\"advanced-result-line advanced-result-line-middle\"><span class=\"advanced-line-item\"><strong>Tel:</strong> <!-- -->(71) 99922-3577</span><span class=\"advanced-line-item\" title=\"x@gmail.com\"><strong>E-mail:</strong> <!-- -->cozinhadechef@gmail.com</span></div><div class=\"advanced-result-line advanced-result-line-bottom\"><span class=\"advanced-line-item\"><strong>Bairro:</strong> <!-- -->PITUBA</span><span class=\"advanced-line-item\"><strong>Abertura:</strong> <!-- -->12/11/2007</span><span class=\"advanced-line-item\"><strong>CNAE:</strong> <!-- -->5620104</span></div></div></div></article>"""
        e = f.ler_listagem(card + card.replace("COZINHA DE CHEF", "BAR DO ZE").replace("09.205.662", "09.205.663"))
        eq(len(e), 2, "dois cartões")
        eq((e[0]["nome"], e[0]["cnpj"], e[0]["cidade"], e[0]["telefone"], e[0]["cnae"], e[0]["situacao"]),
           ("COZINHA DE CHEF", "09.205.662/0001-72", "Salvador", "(71) 99922-3577", "5620104", "Ativa"), f"campos: {e[0]}")
        eq(f._nome_busca("COZINHA DE CHEF"), "Cozinha de Chef", "nome sem caixa alta para a busca")

    def t_fontes_so_aceitam_instagram_que_bate(self):
        f = self._fontes()
        empresa = {"nome": "COZINHA DE CHEF", "cidade": "Salvador", "telefone": "(71) 99922-3577"}
        bom = {"url": "https://www.instagram.com/cozinhadechef", "title": "Cozinha de Chef (@cozinhadechef) · Salvador, BA",
               "content": "11K seguidores - Seu almoço delivery. Quentinhas frescas ou Congelados 71 99922.3577. Follow."}
        outro = {"url": "https://www.instagram.com/peumesquita", "title": "Peu Mesquita (@peumesquita)",
                 "content": "Compartilho o meu mundo da cozinha. Salvador, Bahia Chef Executivo"}
        post = {"url": "https://www.instagram.com/p/C2lU3e2r1og/", "title": "Cozinha de Chef", "content": "71 99922-3577"}
        f._buscar = lambda q: [post, outro, bom]
        ig = f.achar_instagram(empresa)
        eq((ig["handle"], ig["confianca"], ig["seguidores"]), ("cozinhadechef", "telefone", "11K"), f"perfil certo pelo telefone: {ig}")
        ok("Quentinhas" in ig["bio"] and "Follow" not in ig["bio"], f"bio do resultado: {ig['bio']}")
        f._buscar = lambda q: [post, outro]
        eq(f.achar_instagram(empresa), None, "perfil de outra pessoa ou post solto não vale")
        f._buscar = lambda q: [{**bom, "content": "Seu almoço delivery em Salvador"}]
        eq(f.achar_instagram({**empresa, "telefone": ""})["confianca"], "nome", "sem telefone, vale nome + cidade")
        def falha(q):
            raise OSError("fora do ar")
        f._buscar = falha
        try:
            f.achar_instagram(empresa)
            ok(False, "buscador fora do ar tinha de avisar")
        except RuntimeError:
            pass

    def t_fontes_viram_lead_com_conferencia_na_visita(self):
        p, f = self.p, self._fontes()
        self.em(self.hora(10))
        cozinha = {"nome": "COZINHA DE CHEF", "razao": "CCLAY", "cnpj": "09.205.662/0001-72", "cidade": "Salvador", "uf": "BA",
                   "situacao": "Ativa", "telefone": "(71) 99922-3577", "abertura": "12/11/2007", "cnae": "5620104", "fonte": "GuiaPJ"}
        d = f.carregar(LOGIN)
        for e in (cozinha, {**cozinha, "nome": "BAR DO TONHAO", "cnpj": "1"}, {**cozinha, "nome": "11.568.582 SONIA MARIA", "cnpj": "2"},
                  {**cozinha, "nome": "PADARIA DO JOAO", "cnpj": "3", "telefone": "(71) 91111-2222"}):
            d["empresas"][f._chave(e)] = {**e, "estado": "fila"}
        f.salvar(LOGIN, d)
        f.importar(LOGIN, [{"nome": "Doce Lar", "cidade": "Salvador", "uf": "BA", "segmento": "Confeitaria",
                            "instagram": "@docelar.ssa", "evidencia": "Grok: bolos sob encomenda", "fonte": "Planilha SDR Grok"},
                           {"nome": "Doce Lar", "cidade": "Salvador"}])
        consultas = []
        def buscar(q):
            consultas.append(q)
            if "Cozinha de Chef" in q:
                return [{"url": "https://www.instagram.com/cozinhadechef/", "title": "Cozinha de Chef (@cozinhadechef)",
                         "content": "2.194 seguidores - Quentinhas e congelados por encomenda 71 99922-3577"}]
            return []
        f._buscar = buscar
        out = f.enriquecer(LOGIN, p, 10)
        handles = {c["handle"] for c in out["criados"]}
        eq(handles, {"cozinhadechef", "docelar.ssa"}, f"leads criados: {out}")
        eq(out["pulados"], 2, "bar e MEI com nome de pessoa pulados sem gastar busca")
        eq(out["sem_instagram"], 1, "padaria sem perfil achado")
        ok(not any("docelar" in q for q in consultas), f"quem já veio com @ não gasta busca: {consultas}")
        d = p.carregar(LOGIN)
        lead = next(l for l in d["leads"] if l["handle"] == "cozinhadechef")
        ok(lead["conferir_atividade"] and lead["nota"] >= p.NOTA_MINIMA, f"lead com nota e conferência pendente: {lead['nota']}")
        ok("CNPJ 09.205.662/0001-72" in lead["motivo"] and "aberta em 2007" in lead["motivo"], f"motivo com a origem: {lead['motivo']}")
        doce = next(l for l in d["leads"] if l["handle"] == "docelar.ssa")
        eq(doce["avaliacao"]["partes"]["porte"], 12, "tamanho desconhecido conta como mediano até a visita")
        eq(f.importar(LOGIN, [{"nome": "Doce Lar", "cidade": "Salvador"}])["importadas"], 0, "lista importada sem repetir")
        out2 = f.enriquecer(LOGIN, p, 10)
        eq(out2["criados"], [], "segunda passada não cria de novo")
        aid = p.propor(LOGIN, [{"lead_id": lead["id"], "tipo": "aquecer", "texto": ""}])["propostas"][0]["id"]
        ok(aid, "aquecer sem comentário pode ser proposto")

    def t_estoque_de_leads_e_teto_de_buscas(self):
        p, f = self.p, self._fontes()
        self.em(self.hora(10))
        eq(p.estoque(LOGIN), {"prontos": 0, "alvo": 100, "faltam": 100}, "estoque vazio: faltam 100")
        a, b = self._lead("est1"), self._lead("est2")
        self._aquecido("est3")
        e = p.estoque(LOGIN)
        eq((e["prontos"], e["faltam"]), (2, 98), "só leads novos contam no estoque (aquecido não)")
        aid = p.propor(LOGIN, [{"lead_id": a, "tipo": "aquecer", "texto": ""}])["propostas"][0]["id"]
        p.decidir(LOGIN, aid, "aprovar")
        d = p.carregar(LOGIN)
        d["config"].update({"executar_em_teste": True, "conta_instagram": "raizconnect", "estoque_alvo": 3})
        p.salvar(LOGIN, d)
        x, _ = p.proxima(LOGIN, "raizconnect")
        p.resultado(LOGIN, x["id"], False, "perfil parado")
        eq(p.estoque(LOGIN), {"prontos": 1, "alvo": 3, "faltam": 2}, "visita que falhou sai do estoque; alvo configurável")
        ok("Estoque de leads prontos para aquecer: 1 de 3 — FALTAM 2" in p.resumo_contexto(LOGIN), "contexto mostra o estoque e quanto falta")
        ok("estoque 1/3" in p.resumo_hoje(LOGIN), "resumo do dia mostra o estoque")
        # daily cap of paid search calls
        d = f.carregar(LOGIN)
        for i in range(4):
            e = {"nome": f"MARMITARIA TESTE {i}", "cidade": "Salvador", "uf": "BA", "situacao": "Ativa", "cnae": "5620104",
                 "fonte": "GuiaPJ", "cnpj": f"9{i}"}
            d["empresas"][f._chave(e)] = {**e, "estado": "fila"}
        d["buscas_dia"] = 3
        f.salvar(LOGIN, d)
        chamadas = []
        f._buscar = lambda q: chamadas.append(q) or []
        out = f.enriquecer(LOGIN, p, 10)
        ok(len(chamadas) <= 4 and "limite diário de 3 buscas" in out.get("erro_busca", ""), f"para no teto de buscas do dia: {len(chamadas)} {out}")
        n = len(chamadas)
        out = f.enriquecer(LOGIN, p, 10)
        eq(len(chamadas), n, "no mesmo dia, não busca mais nada")
        d = f.carregar(LOGIN)
        d["buscas"]["dia"] = "2000-01-01"  # as if the count were from another day
        f.salvar(LOGIN, d)
        out = f.enriquecer(LOGIN, p, 10)
        ok(len(chamadas) > n, "no dia seguinte o teto zera")

    def t_resposta_apagada_libera_uma_nova(self):
        p = self.p
        self.em(self.hora(10))
        lid = self._aquecido("apagada1")
        p.mudar_etapa(LOGIN, lid, "respondeu", "oieeee….entra sim!!!", "comentario")
        d = p.carregar(LOGIN)
        for estado, desloc in (("falhou", 60), ("falhou", 120), ("executada", 600)):
            d["acoes"].append({"id": f"x{desloc}", "lead_id": lid, "tipo": "resposta", "texto": "Oi!", "estado": estado,
                               "executada_em": p.agora() + desloc, "criada": p.agora()})
        p.salvar(LOGIN, d)
        self.em(p.agora() + 700)
        resp = "Oi, pessoal! Que bom que o rondelli entra no kit da semana. Quer testar a calculadora grátis? — Matheus, da Raiz Connect"
        r = p.propor(LOGIN, [{"lead_id": lid, "tipo": "resposta", "texto": resp}])
        ok(not r["propostas"] and "já respondemos" in r["recusadas"][0]["motivo"], f"enviada conta como respondida: {r['recusadas']}")
        eq(p.marcar_apagada(LOGIN, "x60", "x"), None, "só mensagem executada vira apagada")
        ok(p.marcar_apagada(LOGIN, "x600", "apagada no Instagram por engano")["estado"] == "apagada", "marca apagada")
        r = p.propor(LOGIN, [{"lead_id": lid, "tipo": "resposta", "texto": resp}])
        ok(r["propostas"], f"apagada + falhas antigas não travam uma nova: {r['recusadas']}")

    def t_estados_so_mudam_pela_regra_e_ficam_no_diario(self):
        p = self.p
        self.em(self.hora(10))
        (p.PASTA / f"{LOGIN}_eventos.jsonl").unlink(missing_ok=True)
        lid = self._lead("diario1")
        aid = p.propor(LOGIN, [{"lead_id": lid, "tipo": "aquecer", "texto": ""}])["propostas"][0]["id"]
        p.decidir(LOGIN, aid, "aprovar")
        d = p.carregar(LOGIN)
        a = next(x for x in d["acoes"] if x["id"] == aid)
        try:
            p._mudar(d, a, "apagada")
            ok(False, "aprovada → apagada tinha de ser recusado")
        except p.TransicaoInvalida:
            pass
        p._mudar(d, a, "executada", "teste", executada_em=p.agora())
        try:
            p._mudar(d, a, "proposta")
            ok(False, "executada não volta a proposta")
        except p.TransicaoInvalida:
            pass
        p.salvar(LOGIN, d)
        evs = [(e["de"], e["para"]) for e in p.eventos(LOGIN) if e["acao"] == aid]
        eq(evs[:3], [("-", "proposta"), ("proposta", "aprovada"), ("aprovada", "executada")], f"diário: {evs}")
        ok("_eventos" not in p.carregar(LOGIN), "o diário não fica dentro do registro")
        (p.PASTA / f"{LOGIN}_eventos.jsonl").unlink(missing_ok=True)

    def t_revisor_que_contradiz_o_texto_revisa_de_novo(self):
        p = self.p
        self.em(self.hora(10))
        lid = self._aquecido("revisor1")
        p.mudar_etapa(LOGIN, lid, "respondeu", "oieeee entra sim", "comentario")
        chamadas = []
        def revisor(pedido):
            chamadas.append(pedido)
            ids = re.findall(r"## Item (\w+)", pedido)
            if len(chamadas) == 1:
                return json.dumps({"itens": [{"id": i, "aprovado": False, "motivo": "A resposta não se apresenta como Matheus e não inclui o link da calculadora."} for i in ids]})
            ok("CONFERIDO POR REGRA" in pedido, "a 2ª revisão recebe o fato conferido")
            return json.dumps({"itens": [{"id": i, "aprovado": True, "motivo": "ok"} for i in ids]})
        antigo = p.revisor
        p.revisor = revisor
        try:
            d = p.carregar(LOGIN); d["config"]["auto"] = True; p.salvar(LOGIN, d)
            texto = ("Oi, pessoal! Que bom que entra. Aqui é o Matheus, da Raiz Connect. A calculadora grátis mostra quanto sobra: "
                     "raizconnect.com.br/materiais/precificacao/calculadora, e dá pra começar sem cadastro.")
            out = p.propor(LOGIN, [{"lead_id": lid, "tipo": "resposta", "texto": texto}])  # auto on: reviewer runs
        finally:
            p.revisor = antigo
        eq(len(chamadas), 2, "revisou duas vezes")
        ok(out["automaticas"] and not out["propostas"], f"aprovada na 2ª revisão: {out}")

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

    def t_links_das_iscas(self):
        p = self.p
        d = p.carregar(LOGIN)
        lembrete = ("Oi, Ana! Passando só pra deixar uma coisa útil: fizemos uma calculadora grátis que mostra quanto sobra "
                    "em cada marmita depois de insumo, embalagem e taxa do iFood: {link} — se preferir, me manda a receita 🙂")
        eq(p.validar_texto("dm_lembrete", lembrete.format(link=p.LINK_CALCULADORA), d, "x"), "", "calculadora no lembrete")
        eq(p.validar_texto("resposta", lembrete.format(link="raizconnect.com.br/materiais/quanto-sobra-no-delivery"), d, "x"), "",
           "simulador de delivery na resposta, sem https")
        for ruim in ("https://raizconnect.com.br/materiais/raio-x-do-lucro", "https://raizconnect.com.br/#/register",
                     "https://raizconnect.com.br/materiais/precificacao", "bit.ly/calc",
                     p.LINK_CALCULADORA + " e www.outro.com.br"):
            ok(p.validar_texto("dm_lembrete", lembrete.format(link=ruim), d, "x"), f"link fora da lista barrado: {ruim}")
        ok("primeira mensagem" in p.validar_texto("dm_abertura", DM_A.replace("Me manda", p.LINK_CALCULADORA + " Me manda"), d, "x"),
           "nem a calculadora na primeira mensagem")

    def t_quem_interagiu_vai_primeiro(self):
        p = self.p
        self.em(self.hora(10))
        forte = self._aquecido("forte1")
        d = p.carregar(LOGIN)
        p._lead(d, forte)["nota"] = 95
        p.salvar(LOGIN, d)
        fraco = self._aquecido("fraco1")
        eq([l["id"] for l in p.devidos(LOGIN)["dm_abertura"]][0], forte, "sem interação: maior nota primeiro")
        eq(p.conferido(LOGIN, "nenhuma conversa nova", "fraco1 começou a seguir você · 1 h; outra notificação", ["@fraco1", "desconhecido"]), "", "ok")
        eq([l["id"] for l in p.devidos(LOGIN)["dm_abertura"]][0], fraco, "quem seguiu de volta passa na frente")

    def t_busca_rapida_filtra_conhecidos(self):
        p = self.p
        self._lead("jaconhecido")
        p.rejeitar(LOGIN, [{"handle": "jarejeitado", "motivo": "x"}])
        ok("marmita salvador" in p.montar_busca(["marmita salvador", ""]) and "topsearch" in p.montar_busca(["x"]), "script com os termos")
        achados = json.dumps([{"handle": "JaConhecido"}, {"handle": "jarejeitado"}, {"handle": "cardosomatheus1"},
                              {"handle": "nova.marmita"}, {"handle": "nova.marmita"}, {"handle": "outra_fit"}])
        eq(p.novos_handles(LOGIN, achados), ["nova.marmita", "outra_fit"], "só os novos, sem repetir, sem a conta pessoal")
        eq(len(p.novos_handles(LOGIN, [{"handle": f"h{i}"} for i in range(40)])), 30, "no máximo 30 na fila")
        ok(p.montar_script([f"h{i}" for i in range(9)]).count("\"h") == 5, "5 perfis por script (limite de 30 s)")

    def t_api_oficial_business_discovery(self):
        p = self.p
        self.em(self.hora(11))
        cofre = {}
        class C:
            def carregar(self, login): return dict(cofre)
            def salvar(self, login, n, v): cofre[n] = v
            def descrever(self, *a): pass
        agora = int(p.agora())
        def iso(ts): return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000")
        def graph(caminho, params):
            if caminho == "me/accounts":
                return {"data": [{"name": "Outra", "access_token": "EAAoutra", "instagram_business_account": {"id": "9", "username": "outra"}},
                                 {"name": "Raiz Connect", "access_token": "EAApagina", "instagram_business_account": {"id": "178", "username": "raizconnect"}}]}
            if caminho == "debug_token":
                return {"data": {"expires_at": 0}}
            h = params["fields"].split("username(")[1].split(")")[0]
            if h == "pessoal1":
                return {"error": {"code": 110, "message": "Invalid user id"}}
            return {"business_discovery": {"username": h, "name": "Marmitas da Bia", "followers_count": 2300,
                    "biography": "Marmitas fit congeladas | Salvador-BA | Peça no iFood e pelo WhatsApp", "website": "https://wa.me/55719",
                    "media": {"data": [{"timestamp": iso(agora - 3 * 86400), "caption": "Kit 10 marmitas", "permalink": "https://www.instagram.com/p/ABC/"},
                                       {"timestamp": iso(agora - 200 * 86400), "caption": "antigo", "permalink": "https://www.instagram.com/p/OLD/"}]}}}
        orig_c, orig_g = p._cofre, p._graph
        p._cofre, p._graph = (lambda: C()), graph
        try:
            d = p.carregar(LOGIN); d["config"]["conta_instagram"] = "raizconnect"; p.salvar(LOGIN, d)
            eq(p.descobrir_perfis(LOGIN, ["x"])[0]["erro"][:13], "API da Meta n", "sem token: avisa")
            res = p.guardar_token_meta(LOGIN, "EAAusuario")
            ok(res["ok"] and res["pagina"] == "Raiz Connect" and res["expira"] == "nunca", f"pega a Página da conta certa: {res}")
            eq(cofre, {"META_IG_TOKEN": "EAApagina", "META_IG_USER_ID": "178"}, "token da Página e id no cofre")
            ok("EAA" not in json.dumps(res), "o resumo não mostra o token")
            perfis = p.descobrir_perfis(LOGIN, ["@boa.api", "pessoal1"])
            eq(perfis[1]["erro"], "conta pessoal ou inexistente", "conta não comercial")
            out = p.avaliar_perfis(LOGIN, perfis)
            eq([c["handle"] for c in out["criados"]], ["boa.api"], f"avaliada pela API e registrada: {out}")
            lead = next(l for l in p.carregar(LOGIN)["leads"] if l["handle"] == "boa.api")
            eq(lead["evidencias"]["ultimo_post"], dt.datetime.fromtimestamp(agora - 3 * 86400, p._tz()).date().isoformat(), "data do post mais novo")
        finally:
            p._cofre, p._graph = orig_c, orig_g

    def t_ler_direct_pela_api(self):
        p = self.p
        self.em(self.hora(10))
        lid = self._aquecido("cliente.dm")
        self._executar(lid, "dm_abertura", DM_A)
        outro = self._lead("so.aquecido")
        dados = {"principal": {"erro": "", "threads": [
                    {"usuarios": ["cliente.dm"], "itens": [{"de_mim": False, "tipo": "text", "texto": "Opa! Quanto custa?", "ts": 1},
                                                          {"de_mim": True, "tipo": "text", "texto": "Oi, Ana!", "ts": 0}]},
                    {"usuarios": ["desconhecido"], "itens": [{"de_mim": False, "tipo": "text", "texto": "oi", "ts": 1}]}]},
                 "pedidos": {"erro": "", "threads": [
                    {"usuarios": ["so.aquecido"], "itens": [{"de_mim": True, "tipo": "text", "texto": "nossa msg", "ts": 1}]}]}}
        out = p.processar_direct(LOGIN, json.dumps(dados))
        eq([n["handle"] for n in out["novas"]], ["cliente.dm"], f"só o lead que respondeu por último: {out}")
        eq(out["conversas"], 3, "conta todas as conversas lidas")
        lead = p._lead(p.carregar(LOGIN), lid)
        eq(lead["etapa"], "respondeu", "virou respondeu")
        eq(p._lead(p.carregar(LOGIN), outro)["etapa"], "novo", "quem não respondeu não muda")
        eq(p.processar_direct(LOGIN, json.dumps(dados))["novas"], [], "a mesma resposta não avisa duas vezes")

    def t_avaliacao_rapida_de_perfis(self):
        p = self.p
        self.em(self.hora(11))
        agora = int(p.agora())
        def perfil(h, **k):
            base = {"handle": h, "nome": "Marmitas da Bia", "seguidores": 2300, "privado": False, "categoria": "Restaurante",
                    "bio": "Marmitas fit congeladas | Salvador-BA | Peça no iFood e pelo WhatsApp", "link": "https://wa.me/5571999999999",
                    "posts": [{"fixado": True, "ts": agora - 300 * 86400, "codigo": "FIX", "legenda": "post antigo fixado"},
                              {"fixado": False, "ts": agora - 2 * 86400, "codigo": "ABC", "legenda": "Kit 10 marmitas com preço novo R$ 189"}]}
            base.update(k); return base
        dados = [perfil("boa"),
                 perfil("parada", posts=[{"fixado": False, "ts": agora - 60 * 86400, "codigo": "X", "legenda": "x"}]),
                 perfil("privada", privado=True),
                 perfil("enorme", seguidores=120000),
                 perfil("semcidade", bio="Marmitas fit congeladas, peça pelo WhatsApp"),
                 {"handle": "sumiu", "erro": "perfil não encontrado"}]
        ok("\"boa\"" in p.montar_script(["@boa", "parada"]) and "web_profile_info" in p.montar_script(["boa"]), "script com os @")
        out = p.avaliar_perfis(LOGIN, json.dumps(dados))
        eq([c["handle"] for c in out["criados"]], ["boa"], f"só a boa entra: {out}")
        ok(out["criados"][0]["nota"] >= p.NOTA_MINIMA, "com nota")
        lead = p.carregar(LOGIN)["leads"][0]
        eq(lead["evidencias"]["ultimo_post"], (dt.datetime.fromtimestamp(agora - 2 * 86400, p._tz()).date()).isoformat(),
           "último post = o primeiro NÃO fixado")
        ok("ifood" in lead["evidencias"]["canais"] and "whatsapp" in lead["evidencias"]["canais"], "canais lidos da bio")
        ok("kits" in lead["evidencias"]["sinais"], "sinais lidos das legendas")
        recusados = {r["handle"]: r["motivo"] for r in out["recusados"]}
        ok("parado" in recusados.get("parada", ""), f"parada recusada: {recusados}")
        ok("privado" in recusados.get("privada", ""), "privada recusada")
        ok("grande" in recusados.get("enorme", ""), "enorme recusada")
        eq([c["item"]["handle"] for c in out["conferir"]], ["semcidade"], "sem cidade vai para conferir")
        eq(out["conferir"][0]["falta"], ["cidade"], "diz o que falta")
        eq([e["handle"] for e in out["erros"]], ["sumiu"], "erro do script aparece")
        rej = p.carregar(LOGIN)["rejeitados"]
        ok({"parada", "privada", "enorme"} <= set(rej), "recusados anotados (não voltam por 60 dias)")
        eq(p.avaliar_perfis(LOGIN, json.dumps([perfil("boa")]))["recusados"][0]["motivo"], "já conhecido", "repetido não duplica")
        eq(p.api_pausada(LOGIN), "", "sem 429, sem pausa")
        p.avaliar_perfis(LOGIN, json.dumps([{"handle": "x1", "erro": "http 429"}]))
        ok(p.api_pausada(LOGIN), "429 pausa os scripts de perfil")
        self.em(self.relogio + 16 * 60)
        eq(p.api_pausada(LOGIN), "", "a pausa acaba em 15 min")

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

    def t_repor_aquecer_e_dias_de_calendario(self):
        p = self.p
        self.em(self.hora(10))
        self._revisor()  # never the real model in the suite
        p.definir_auto(LOGIN, True)
        d = p.carregar(LOGIN)
        d["config"].update({"executar_em_teste": True, "conta_instagram": "raizconnect"})
        p.salvar(LOGIN, d)
        a1, a2 = self._lead("repor1", seguidores="4k"), self._lead("repor2")
        a, motivo = p.proxima(LOGIN, "raizconnect")
        ok(a and a["tipo"] == "aquecer" and not a["texto"], f"vaga livre é reposta com o melhor novo, sem texto ({motivo})")
        p.resultado(LOGIN, a["id"], True, "seguiu e curtiu")
        self.em(self.relogio + 4 * 60)
        b, motivo = p.proxima(LOGIN, "raizconnect")
        ok(b and b["tipo"] == "aquecer" and b["lead_id"] != a["lead_id"], f"depois de uma ação, repõe o próximo ({motivo})")
        p.resultado(LOGIN, b["id"], False, "parado há 90 dias")
        self.em(self.relogio + 4 * 60)
        c, motivo = p.proxima(LOGIN, "raizconnect")
        ok(not c and "nenhuma" in motivo, f"fila vazia: nada a repor ({motivo})")
        d = p.carregar(LOGIN)
        x = next(y for y in d["acoes"] if y["id"] == a["id"])
        x["executada_em"] = p.agora()  # as if an action had just happened
        p.salvar(LOGIN, d)
        c, motivo = p.proxima(LOGIN, "raizconnect")
        ok(not c and "nenhuma" in motivo, f"sem nada a fazer, encerra mesmo logo depois de uma ação, não manda esperar ({motivo})")
        self.em(self.relogio + 4 * 60)
        ok(p.aviso_sem_acao(motivo).startswith("NADA AGORA"), "fila vazia encerra a rodada")
        self._lead("repor_espera1"), self._lead("repor_espera2")
        c, motivo = p.proxima(LOGIN, "raizconnect")
        ok(c and c["tipo"] == "aquecer", f"lead novo na fila: repõe ({motivo})")
        p.resultado(LOGIN, c["id"], True, "seguiu e curtiu")
        c, motivo = p.proxima(LOGIN, "raizconnect")
        ok(not c and motivo.startswith("espaçamento"), f"logo depois de uma ação: espaçamento ({motivo})")
        ok(p.aviso_sem_acao(motivo).startswith("ESPERE"), "espaçamento manda esperar, não encerrar a rodada")
        self.em(self.relogio + 4 * 60)
        c, motivo = p.proxima(LOGIN, "raizconnect")
        ok(c and c["tipo"] == "aquecer", f"depois da espera, repõe o seguinte ({motivo})")
        p.resultado(LOGIN, c["id"], True, "seguiu e curtiu")
        d = p.carregar(LOGIN)
        hoje = sum(1 for x in d["acoes"] if x["tipo"] == "aquecer" and x["estado"] in ("aprovada", "executada"))
        d["config"]["auto"] = False
        p.salvar(LOGIN, d)
        self._lead("repor3")
        c, _ = p.proxima(LOGIN, "raizconnect")
        ok(not c, "sem pré-aprovação (auto desligado), não repõe sozinho")
        eq(hoje, 3, "3 feitas; a que falhou não ocupa vaga")
        # calendar days: warmed at 19h, the first DM is due 2 days later from the morning
        self.em(self.hora(19))
        lid = self._lead("calendario")
        d = p.carregar(LOGIN)
        lead = p._lead(d, lid)
        lead.update({"etapa": "aquecido", "atualizado": self.hora(19)})
        p.salvar(LOGIN, d)
        self.em(self.hora(9, dias=1))
        ok(lid not in [l["id"] for l in p.devidos(LOGIN)["dm_abertura"]], "dia seguinte: ainda não")
        self.em(self.hora(9, dias=2))
        ok(lid in [l["id"] for l in p.devidos(LOGIN)["dm_abertura"]], "2 dias de calendário depois, às 9h: devida")
        p.revisor = None

    def t_comentario_na_visita_e_atrasado(self):
        p = self.p
        self.em(self.hora(10))
        chamadas = self._revisor(reprovar=())
        p.definir_auto(LOGIN, True)
        d = p.carregar(LOGIN)
        d["config"].update({"executar_em_teste": True, "conta_instagram": "raizconnect"})
        p.salvar(LOGIN, d)
        l1, l2 = self._lead("coment1"), self._lead("coment2")
        a, motivo = p.proxima(LOGIN, "raizconnect")
        ok(a and a["tipo"] == "aquecer" and not a["texto"], f"aquecer sem texto ({motivo})")
        r, m = p.comentar(LOGIN, a["id"], "Que capricho nessa marmita! www.loja.com.br", "post de ontem")
        ok(not r and "sem link" in m, f"link barrado antes do revisor: {m}")
        r, m = p.comentar(LOGIN, a["id"], "Que capricho nessa marmita de frango! Sai mais no almoço ou no jantar?", "post de ontem: marmita de frango")
        ok(r, f"comentário na visita aprovado: {m}")
        ok(len(chamadas) == 1 and "post de ontem: marmita de frango" in chamadas[0]["pedido"], "revisor recebe o post visto")
        r, m = p.comentar(LOGIN, a["id"], "Outro comentário qualquer sobre o post de vocês?", "post")
        ok(not r and "já tem" in m, f"nunca dois comentários no mesmo aquecimento: {m}")
        ok(p.comentado(LOGIN, a["id"], True, "apareceu na lista"), "comentário publicado registrado")
        p.resultado(LOGIN, a["id"], True, "seguiu, curtiu e comentou")
        d = p.carregar(LOGIN)
        x = next(y for y in d["acoes"] if y["id"] == a["id"])
        eq((x["comentario"]["estado"], x["estado"]), ("publicado", "executada"), "comentário publicado e aquecimento feito")
        # catch-up: a warm-up done earlier with no comment
        self.em(self.relogio + 4 * 60)
        b, _ = p.proxima(LOGIN, "raizconnect")
        p.resultado(LOGIN, b["id"], True, "seguiu e curtiu")
        eq([s["acao_id"] for s in p.sem_comentario(LOGIN)], [b["id"]], "lista os aquecimentos sem comentário")
        r, m = p.comentar(LOGIN, b["id"], "Esse bolo de pote de ninho ficou lindo! Vocês fazem por encomenda pra festa?", "post de 09/10")
        ok(not r and m.startswith("espaçamento"), f"comentário atrasado respeita os 3 minutos: {m}")
        self.em(self.relogio + 4 * 60)
        self._revisor(reprovar=(b["id"],))
        r, m = p.comentar(LOGIN, b["id"], "Esse bolo de pote de ninho ficou lindo! Vocês fazem por encomenda pra festa?", "post de 09/10")
        ok(not r and m.startswith("REESCREVA") and "3 tentativa" in m, f"revisor reprovou: manda reescrever com o motivo: {m}")
        ok(not p.comentado(LOGIN, b["id"], True, "x"), "sem aprovação, 'comentado' não registra nada")
        self._revisor()
        r, m = p.comentar(LOGIN, b["id"], "Esse bolo de pote de ninho ficou lindo! Sai mais por encomenda ou na pronta entrega?", "post de 09/10")
        ok(r, f"nova tentativa aprovada: {m}")
        p.comentado(LOGIN, b["id"], True, "apareceu")
        eq(p.sem_comentario(LOGIN), [], "nada mais sem comentário")
        # the reviewer keeps saying no: at most TENTATIVAS_COMENTARIO versions, then the warm-up stays without comment
        self.em(self.relogio + 4 * 60)
        self._lead("coment3")
        c, _ = p.proxima(LOGIN, "raizconnect")
        self._revisor(reprovar=(c["id"],))
        for n in range(p.TENTATIVAS_COMENTARIO):
            r, m = p.comentar(LOGIN, c["id"], f"Versão {n} de um comentário sobre o kit de marmitas da semana?", "post")
            ok(not r, f"tentativa {n} reprovada")
        ok("última versão" in m, f"a última tentativa avisa que acabou: {m}")
        r, m = p.comentar(LOGIN, c["id"], "Mais uma versão de um comentário sobre o kit de marmitas?", "post")
        ok(not r and "versões reprovadas" in m, f"depois do limite, não tenta mais: {m}")
        p.resultado(LOGIN, c["id"], True, "seguiu e curtiu, sem comentário")
        self._revisor()
        self._lead("coment4")  # something to do, so the spacing is what holds it
        self.em(self.relogio + 30)
        c, motivo = p.proxima(LOGIN, "raizconnect")
        ok(not c and motivo.startswith("espaçamento"), f"comentário atrasado conta no espaçamento ({motivo})")
        self.em(self.hora(10, dias=5))
        d = p.carregar(LOGIN)
        d["acoes"] = [y for y in d["acoes"] if y["id"] != b["id"]]
        p.salvar(LOGIN, d)
        r, m = p.comentar(LOGIN, a["id"], "Mais um?", "x")
        ok(not r, "fora da janela de 3 dias / já comentado: recusa")
        p.revisor = None

    def t_direct_script_e_comentario_relido(self):
        p = self.p
        self.em(self.hora(10))
        s = p.script_digitar('Oi, pessoal da "Ana"! 😊 raizconnect.com.br/materiais/precificacao/calculadora')
        ok("CAMPO NÃO ESTÁ VAZIO" in s and "insertText" in s and "await espera" in s,
           "script recusa campo com rascunho, insere uma vez e espera o texto aparecer (editor do Instagram é assíncrono)")
        ok(json.dumps('Oi, pessoal da "Ana"! 😊 raizconnect.com.br/materiais/precificacao/calculadora', ensure_ascii=False) in s,
           "texto exato, com aspas escapadas")
        ok(set(p.TIPOS_DIRECT) == {"dm_abertura", "dm_lembrete", "resposta", "parceiro"}, "todo envio no Direct usa o script")
        lid = self._lead("relida")
        n1 = p.mudar_etapa(LOGIN, lid, "respondeu", "Respondeu ao comentário da Raiz com orientação sobre aquecer marmitas: pode ir ao micro-ondas.", "comentario")
        ok(n1["novidade"], "primeira leitura avisa")
        n2 = p.mudar_etapa(LOGIN, lid, "respondeu", "Respondeu ao comentário: pode aquecer direto no micro-ondas; ou descongelar na geladeira.", "comentario")
        ok(not n2["novidade"], "a mesma resposta no comentário, descrita de outro jeito e sem citação, não avisa de novo")
        d = p.carregar(LOGIN)
        d["acoes"].append({"id": "r1", "lead_id": lid, "tipo": "resposta", "texto": "x", "estado": "executada",
                           "criada": p.agora(), "executada_em": p.agora() + 1})
        p.salvar(LOGIN, d)
        self.em(self.relogio + 3600)
        n3 = p.mudar_etapa(LOGIN, lid, "respondeu", "Respondeu de novo no comentário: obrigada, vou olhar a calculadora!", "comentario")
        ok(n3["novidade"], "depois da nossa resposta, uma fala nova avisa")

    def t_resposta_uma_por_fala(self):
        p = self.p
        self.em(self.hora(10))
        self._revisor()  # never the real model in the suite
        lid = self._lead("fala1")
        p.mudar_etapa(LOGIN, lid, "respondeu", "entra sim!", "comentario")
        r = p.propor(LOGIN, [{"lead_id": lid, "tipo": "resposta", "texto": "Oi, pessoal da Fala! Que bom. A calculadora grátis: raizconnect.com.br/materiais/precificacao/calculadora — Matheus"}])
        ok(r["propostas"] or r.get("automaticas"), f"primeira resposta passa: {r}")
        d = p.carregar(LOGIN)
        a = next(x for x in d["acoes"] if x["lead_id"] == lid and x["tipo"] == "resposta")
        a.update({"estado": "executada", "executada_em": p.agora()})
        p.salvar(LOGIN, d)
        self.em(self.hora(11))
        r = p.propor(LOGIN, [{"lead_id": lid, "tipo": "resposta", "texto": "Oi de novo, pessoal da Fala! Conseguiram ver a calculadora? — Matheus"}])
        ok(r["recusadas"] and "já respondemos" in r["recusadas"][0]["motivo"], f"segunda resposta à mesma fala é barrada: {r}")
        self.em(self.hora(12))
        p.mudar_etapa(LOGIN, lid, "lead", "vou testar, obrigada!", "direct")
        r = p.propor(LOGIN, [{"lead_id": lid, "tipo": "resposta", "texto": "Imagina, pessoal da Fala! Qualquer dúvida no uso, me chama 🙂 — Matheus"}])
        ok(not r["recusadas"], f"fala nova libera nova resposta: {r}")
        d = p.carregar(LOGIN)
        a = [x for x in d["acoes"] if x["lead_id"] == lid and x["tipo"] == "resposta"][-1]
        a.update({"estado": "falhou", "executada_em": p.agora()})
        p.salvar(LOGIN, d)
        r = p.propor(LOGIN, [{"lead_id": lid, "tipo": "resposta", "texto": "Oi, pessoal da Fala! Tentando de novo por aqui 🙂 — Matheus"}])
        ok(r["recusadas"] and "já falhou" in r["recusadas"][0]["motivo"], f"resposta que falhou não vira ciclo: {r}")
        n1 = p.mudar_etapa(LOGIN, lid, "lead", "Respondeu no Direct: «vou testar, obrigada!»", "direct")
        eq(n1["novidade"], False, "a mesma fala descrita com outras palavras não avisa de novo")
        p.revisor = None

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
        ids = [self._lead(f"c{i}") for i in range(p.LIMITE_PILOTO["aquecer"] + 2)]
        r = p.propor(LOGIN, [{"lead_id": i, "tipo": "aquecer", "texto": ""} for i in ids])
        eq(p.LIMITE_PILOTO["aquecer"], 15, "piloto: 15 aquecer por dia (Matheus, 12/10)")
        eq(len(r["propostas"]), p.LIMITE_PILOTO["aquecer"], "piloto: só até o limite")
        ok(all("limite" in x["motivo"] for x in r["recusadas"]), "o resto por limite")
        d = p.carregar(LOGIN)
        d["config"]["inicio"] = p.agora() - 8 * 86400
        p.salvar(LOGIN, d)
        eq(p.limites(p.carregar(LOGIN))["aquecer"], p.LIMITE_DIA["aquecer"], "depois de 7 dias, limite cheio")

    def t_propostas_pendentes_contam_na_cota(self):
        p = self.p
        m = p.LIMITE_PILOTO["aquecer"] // 2 + 2
        r1 = p.propor(LOGIN, [{"lead_id": self._lead(f"q{i}"), "tipo": "aquecer", "texto": ""} for i in range(m)])
        r2 = p.propor(LOGIN, [{"lead_id": self._lead(f"r{i}"), "tipo": "aquecer", "texto": ""} for i in range(m)])
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
