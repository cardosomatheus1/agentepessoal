"""Tests of the Especialistas (Crítico and Designer) with the model call mocked: no network, no Agent Zero, no render
engine. Run with implantar.py (staging copy) or anywhere: python3 tests/suite.py"""

import asyncio
import importlib.util
import json
import struct
import sys
import tempfile
import traceback
import types
import zlib
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


class Falha(AssertionError):
    pass


def eq(a, b, msg):
    if a != b:
        raise Falha(f"{msg}: esperado {b!r}, veio {a!r}")


def ok(cond, msg):
    if not cond:
        raise Falha(msg)


_n = [0]


def _carregar(nome: str, arquivo: Path, stubs: dict | None = None):
    antes = {k: sys.modules.get(k) for k in (stubs or {})}
    sys.modules.update(stubs or {})
    try:
        _n[0] += 1
        spec = importlib.util.spec_from_file_location(f"{nome}_{_n[0]}", arquivo)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        for k, v in antes.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _png(caminho: Path):
    """A valid 1x1 PNG without PIL."""
    def bloco(tipo, dados):
        return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)
    caminho.write_bytes(b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
                        + bloco(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + bloco(b"IEND", b""))


def _resposta(texto: str) -> dict:
    return {"output": [{"type": "message", "content": [{"type": "output_text", "text": texto}]}]}


APROVA = json.dumps({"veredito": "aprova", "motivos": [], "sugestoes": ["nada"]})


class Suite:
    def __init__(self):
        self.resultados = []
        self.tmp = Path(tempfile.mkdtemp(prefix="teste_especialistas_"))

    def _e(self, com_raiz: str | None = None, criterios: dict | None = None, reels: Path | None = None):
        """A fresh helper with a fake plugins folder (cerebro/helpers/raiz.py only when com_raiz) and calibracao."""
        m = _carregar("especialistas_teste", RAIZ / "helpers" / "especialistas.py")
        base = Path(tempfile.mkdtemp(dir=self.tmp))
        (base / "plugins" / "cerebro" / "helpers").mkdir(parents=True)
        if com_raiz is not None:
            (base / "plugins" / "cerebro" / "helpers" / "raiz.py").write_text(
                f"def contexto(nomes=None, limite=6000):\n    return {com_raiz!r}[:limite]\n", encoding="utf-8")
        m.PLUGINS = base / "plugins"
        for agente, texto in (criterios or {}).items():
            (base / "calibracao" / agente).mkdir(parents=True)
            (base / "calibracao" / agente / "criterios.md").write_text(texto, encoding="utf-8")
        m.pasta_calibracao = lambda: (base / "calibracao") if criterios else None
        m.pasta_reels = lambda: reels
        m.pasta_moldes = lambda: (reels / "moldes") if reels else None  # never the VM's real /a0/usr/moldes
        return m

    # --- the roles

    def t_souls_tem_personalidade_regras_e_o_que_nao_faz(self):
        m = self._e()
        eq(sorted(m.PAPEIS), ["critico", "designer", "gestor"], "os três papéis")
        for papel, soul in ((p, s) for p, s in m.PAPEIS.items() if p != "gestor"):
            ok("O que você faz:" in soul, f"{papel}: seção do que faz")
            ok("O que você não faz:" in soul, f"{papel}: seção do que não faz")
            nao_faz = soul.split("O que você não faz:")[1].split("\n\n")[0]
            ok(nao_faz.count("\n- ") >= 3, f"{papel}: pelo menos 3 coisas que não faz")
            ok("Não fala com o Matheus" in soul or "não fala com o Matheus" in soul, f"{papel}: não fala com o Matheus")
        c = m.PAPEIS["critico"]
        for termo in ("veredito", "motivos", "sugestoes", "genérico", "Cérebro da Raiz", "AR Board", "decisão é cara"):
            ok(termo in c, f"crítico cita {termo!r}")
        # 22/10: the agent renders the Raiz with the moldes; the identity stays the kit's (marca raiz)
        ok("Não foge do kit na Raiz" in m.PAPEIS["designer"], "designer sabe que a Raiz usa molde só com o kit")

    def t_gestor_vocabulario_fechado_e_opus(self):
        # 03/11, Matheus: "ta faltando um agente gestor tbm ... ser de fato uma inteligência"
        m = self._e()
        g = m.PAPEIS["gestor"]
        for termo in ('"segurar"', '"remarcar"', '"cancelar"', '"refazer"', '"trocar"', '"criar"', "FECHADO",
                      '"orientar"', '"desistir"', "em_refacao", "desvios entre o Crítico e o construtor",
                      "nunca faz: publicar", "liberar o que o Crítico reprovou", "apagar o que já saiu", "lista vazia",
                      "perguntar ao Matheus", "sem depender de mim"):
            ok(termo in g, f"gestor cita {termo!r}")
        # 04/11, Matheus: "eu não quero um agente para ficar esperando eu falar": the Gestor has no question to ask
        ok("pedir_ao_matheus" not in g, "o gestor não tem como perguntar")
        ok("decisão #39" not in m.PAPEIS["critico"] and "sem passar pelo Matheus" in Path(m.__file__).read_text(encoding="utf-8"),
           "o Crítico sabe que a prévia aprovada vira vídeo e sai")
        enviados = []

        def enviar(url, body, login, papel, tempo):
            enviados.append((url, body, login, papel, tempo))
            return {"output": {"message": {"content": [{"reasoningContent": {}}, {"text": '{"visto": "ok", "acoes": []}'}]}},
                    "usage": {"inputTokens": 4, "cacheWriteInputTokens": 20000, "cacheReadInputTokens": 1000,
                              "outputTokens": 1500}, "stopReason": "end_turn"}
        m._enviar_claude = enviar
        r = m.chamar_claude("gestor", "Decida.", login="teste_ana")
        url, body, login, papel, tempo = enviados[0]
        ok(url.endswith("/bedrock/model/us.anthropic.claude-opus-5-5/converse") and tempo < 240, url)
        eq(body["system"][0]["text"], g, "o papel vai como system")
        eq(body["additionalModelRequestFields"]["output_config"]["effort"], "high", "pensa com cuidado")
        eq((login, papel), ("teste_ana", "gestor"), "dono e papel nos cabeçalhos (uso por dono)")
        eq(r["texto"], '{"visto": "ok", "acoes": []}', "só o texto")
        eq(r["uso"]["entrada"], 21004, "a entrada conta o cache que o proxy põe")
        eq(r["uso"]["usd"], round(4 * 4 / 1e6 + 20000 * 5 / 1e6 + 1000 * 0.4 / 1e6 + 1500 * 20 / 1e6, 4), "custo da execução")

        # 12/11: the whole answer went to thinking (max_tokens, no text): asked once more with effort "low"
        enviados.clear()

        def corta(url, body, login, papel, tempo):
            enviados.append(body["additionalModelRequestFields"]["output_config"]["effort"])
            if len(enviados) == 1:
                return {"output": {"message": {"content": [{"reasoningContent": {}}]}}, "stopReason": "max_tokens",
                        "usage": {"inputTokens": 10, "outputTokens": 8000}}
            return {"output": {"message": {"content": [{"text": '{"acoes": []}'}]}}, "stopReason": "end_turn",
                    "usage": {"inputTokens": 10, "outputTokens": 900}}
        m._enviar_claude = corta
        r = m.chamar_claude("gestor", "Decida.")
        eq(enviados, ["high", "low"], "cortado sem texto: mais uma vez, pensando menos")
        ok(r["texto"] == '{"acoes": []}' and r["uso"]["saida"] == 8900 and r["erro"] == "", r)
        enviados.clear()

        def corta_no_meio(url, body, login, papel, tempo):
            enviados.append(body["additionalModelRequestFields"]["output_config"]["effort"])
            if len(enviados) == 1:
                return {"output": {"message": {"content": [{"text": '{"visto": "a agenda', }]}}, "stopReason": "max_tokens",
                        "usage": {"inputTokens": 10, "outputTokens": 8000}}
            return {"output": {"message": {"content": [{"text": '{"acoes": []}'}]}}, "stopReason": "end_turn",
                    "usage": {"inputTokens": 10, "outputTokens": 900}}
        m._enviar_claude = corta_no_meio
        r = m.chamar_claude("gestor", "Decida.")
        ok(enviados == ["high", "low"] and r["texto"] == '{"acoes": []}', f"JSON cortado no meio também: {enviados} {r}")

        def cai(*a):
            raise OSError("sem rede")
        m._enviar_claude = cai
        ok(m.chamar_claude("gestor", "x")["erro"].startswith("OSError"), "rede fora: erro, sem levantar")
        ok(m.chamar_claude("bruxo", "x")["erro"].startswith("papel desconhecido"), "papel inventado")

    # --- strict parsing, fail closed

    def t_critica_so_vale_json_limpo(self):
        m = self._e()
        i = m.interpretar_critica
        eq(i(APROVA), {"veredito": "aprova", "motivos": [], "sugestoes": ["nada"]}, "aprova limpo")
        eq(i('Aqui: {"veredito": "Reprova ", "motivos": "manchete genérica"}')["motivos"], ["manchete genérica"],
           "JSON no meio do texto, motivo único em texto")
        eq(i('{"veredito": "reprova", "motivos": []}')["motivos"], ["reprovado sem motivo dado"], "reprova sem motivo")
        ilegivel = {"veredito": "reprova", "motivos": ["resposta ilegível"], "sugestoes": []}
        for ruim in ("", "Aprovo sim!", "{nao é json}", '["aprova"]', '{"veredito": "talvez"}',
                     '{"veredito": "aprova", "motivos": 3}', '{"veredito": "aprova", "sugestoes": [1, 2]}',
                     '{"veredito": true}', None):
            eq(i(ruim), ilegivel, f"ilegível: {ruim!r}")

    def t_chamar_monta_um_pedido_com_soul_texto_e_imagem(self):
        m = self._e()
        img = self.tmp / "slide1.png"
        _png(img)
        enviados = []
        m._enviar = lambda body, login, tempo=0: enviados.append((body, login, tempo)) or _resposta("oi")
        r = m.chamar("critico", "Julgue.", {"legenda": "Lucro na mão",
                                            "imagens": [str(img), "/nao/existe/slide2.png"]}, login="teste_ana")
        eq(len(enviados), 1, "uma chamada só")
        body, login, tempo = enviados[0]
        ok(body["reasoning"]["effort"] == "medium" and tempo == 230, "o Crítico lê com mais cuidado (22/10: lia slide errado)")
        c = m.PAPEIS["critico"]
        ok("Reprova só por um destes" in c and "sugestões, com aprovação" in c and "cita o slide e o texto exato" in c,
           "reprova por regra, não por suposição")
        ok("não precisa mostrar a oferta inteira" in c and "o que falta" in c,
           "peça curta não é reprovada por não trazer a oferta inteira (22/10: story travado 4 vezes)")
        m.chamar("designer", "Desenhe.", "x")
        ok(enviados[1][0]["reasoning"]["effort"] == "medium" and enviados[1][2] < 240,
           "o Designer pensa mais, dentro dos 240 s do proxy (22/10: no alto as correções morriam caladas)")
        ok("não mostra 99Food" in m.TELAS["cozinha-kds.jpg"], "o Designer sabe o que cada tela mostra")
        eq(login, "teste_ana", "o dono vai no cabeçalho")
        eq(body["model"], "openai.gpt-6-luna", "modelo")
        eq(body["instructions"], m.PAPEIS["critico"], "o SOUL vai como instruções")
        conteudo = body["input"][0]["content"]
        ok("Julgue." in conteudo[0]["text"] and "Lucro na mão" in conteudo[0]["text"], "tarefa e material no texto")
        ok("slide2.png" in conteudo[0]["text"], "avisa a imagem que não viu")
        eq([c["type"] for c in conteudo], ["input_text", "input_image"], "a imagem vai como input_image")
        ok(conteudo[1]["image_url"].startswith("data:image/"), "imagem em data URL")
        eq((r["texto"], r["erro"], r["imagens"]), ("oi", "", [str(img)]), "resultado")
        eq(m.chamar("bruxo", "x", "y")["erro"], "papel desconhecido: bruxo", "papel inventado")

    def t_rede_fora_reprova(self):
        m = self._e(com_raiz="Raiz")

        def cai(body, login, tempo=0):
            raise OSError("sem rede")
        m._enviar = cai
        r = m.chamar("critico", "x", "y")
        ok(r["erro"].startswith("OSError") and r["texto"] == "", "chamar não levanta")
        c = m.criticar("post", "Calculadora grátis na bio")
        eq(c["veredito"], "reprova", "sem resposta, reprova")
        ok("não respondeu" in c["motivos"][0], c["motivos"])

    # --- what the Crítico reads

    def t_criticar_usa_o_cerebro_da_raiz_e_os_criterios(self):
        m = self._e(com_raiz="OFERTA: Lucro na Mão em 30 Dias", criterios={"conteudo": "Regra 7: sem promessa.",
                                                                            "prospeccao": "Regra P: curto."})
        tarefas = []
        m.chamar = lambda papel, tarefa, material, login="matheus": tarefas.append((papel, tarefa, material)) or \
            {"texto": APROVA, "erro": "", "imagens": [], "sem_imagem": []}
        c = m.criticar("post", "Acerte o preço do cardápio em 30 dias. Calculadora grátis na bio.")
        eq(c["veredito"], "aprova", "aprovado")
        eq(c["avisos"], [], "nada faltou")
        papel, tarefa, _ = tarefas[0]
        eq(papel, "critico", "papel")
        ok("Lucro na Mão em 30 Dias" in tarefa, "contexto da Raiz na tarefa")
        ok("Regra 7" in tarefa and "Regra P" not in tarefa, "só os critérios do tipo (post = conteúdo)")
        m.criticar("mensagem", "Oi, tudo bem?")
        ok("Regra P" in tarefas[1][1] and "Regra 7" not in tarefas[1][1], "mensagem usa os critérios da prospecção")

    def t_criticar_le_as_decisoes_do_matheus(self):
        # 21/10: his later decisions win over the AR Board criteria (the iFood video was blocked by a week-1 criterion)
        m = self._e(com_raiz="Raiz", criterios={"conteudo": "Regra antiga: CTA da calculadora."})
        tarefas = []
        m.chamar = lambda papel, tarefa, material, login="matheus": tarefas.append(tarefa) or \
            {"texto": APROVA, "erro": "", "imagens": [], "sem_imagem": []}
        m.decisoes_raiz = lambda limite=4000: "Decisões… (valem ACIMA dos critérios)\n- #39 [preferencia] marketing.x: áudio antes"
        m.criticar("post", "Experimente grátis por 15 dias.")
        ok("## Decisões do Matheus" in tarefas[0] and "áudio antes" in tarefas[0], "as decisões vão na tarefa")
        ok(tarefas[0].index("Critérios do Matheus") < tarefas[0].index("## Decisões do Matheus"), "depois dos critérios")
        m.decisoes_raiz = lambda limite=4000: ""
        m.criticar("post", "Experimente grátis por 15 dias.")
        ok("## Decisões do Matheus" not in tarefas[1], "sem Pasta: como antes")
        m.criticar("post", {"formato": "REELS", "legenda": "x", "narracao": "[0.6s] Pediu pelo iFood?",
                            "quadros": "ordem das imagens: 1 = segundo 0.2"})
        ok("## Vídeo" in tarefas[2] and "naquele momento" in tarefas[2] and "texto cortado" in tarefas[2],
           "Reel com quadros e narração: o Crítico confere tela x fala e letra cortada")
        ok("## Vídeo" not in tarefas[1], "post sem vídeo: sem essa parte")

    def t_criticar_funciona_sem_cerebro_e_sem_criterios(self):
        m = self._e()
        tarefas = []
        m.chamar = lambda papel, tarefa, material, login="matheus": tarefas.append(tarefa) or \
            {"texto": APROVA, "erro": "", "imagens": [], "sem_imagem": []}
        c = m.criticar("landing", "Acerte o preço do cardápio.")
        eq(c["veredito"], "aprova", "ainda julga")
        ok(any("Cérebro da Raiz indisponível" in a for a in c["avisos"]), c["avisos"])
        ok(any("sem critérios" in a for a in c["avisos"]), c["avisos"])
        ok("indisponível" in tarefas[0], "o modelo sabe que faltou contexto")
        # a raiz.py that breaks is also tolerated
        q = self._e(com_raiz="x")
        (q.PLUGINS / "cerebro" / "helpers" / "raiz.py").write_text("def contexto(**k):\n    raise RuntimeError('quebrou')\n")
        texto, nota = q.contexto_raiz()
        eq(texto, "", "sem texto")
        ok("RuntimeError" in nota, nota)

    def t_critico_do_video_sabe_do_zoom(self):
        # 27/10: the publish gate read a zoomed frame of an approved Reel as a cropped screen (decision #85)
        m = self._e(com_raiz="Raiz")
        chamadas = []
        m.chamar = lambda *a, **k: chamadas.append(a) or {"texto": APROVA, "erro": "", "imagens": [], "sem_imagem": []}
        m.criticar("reel", {"narracao": [{"t": 0, "fala": "Oi"}], "imagens": []})
        ok("não é tela recortada" in chamadas[-1][1] and "#85" in chamadas[-1][1], chamadas[-1][1][-500:])

    def t_regras_fixas_reprovam_mesmo_com_o_modelo_aprovando(self):
        m = self._e(com_raiz="Raiz")
        chamadas = []
        m.chamar = lambda *a, **k: chamadas.append(a) or {"texto": APROVA, "erro": "", "imagens": [], "sem_imagem": []}
        eq(m.criticar("post", "Seu lucro vai subir \U0001F680")["veredito"], "reprova", "emoji")
        eq(m.criticar("mensagem", "Oi — tudo bem?")["veredito"], "reprova", "travessão")
        c = m.criticar("carrossel", {"slides": ["Custo do prato: R$ 12,40"]})
        eq(c["veredito"], "reprova", "R$ sem valores de exemplo")
        ok('valores de exemplo' in c["motivos"][0], c["motivos"])
        eq(m.criticar("carrossel", {"slides": ["Custo do prato: R$ 12,40", "valores de exemplo"]})["veredito"],
           "aprova", "com valores de exemplo passa")
        eq(m.criticar("oferta", "Programa por R$ 197/mês")["veredito"], "aprova", "oferta com preço real passa")
        # 26/10: "Salve para consultar depois." on a story (a story cannot be saved); fine on a feed post
        c = m.criticar("story", {"legenda": "3 pontos do caixa", "chamada": "Salve para consultar depois."})
        ok(c["veredito"] == "reprova" and "story não se salva" in c["motivos"][0], c)
        eq(m.criticar("post", {"legenda": "Salve para consultar depois."})["veredito"], "aprova", "no feed salvar existe")
        # a story that calls the day's post: the Crítico is told to compare both subjects
        m.criticar("story", {"legenda": "Estoque na hora certa", "post_do_dia": {"tipo": "REELS", "titulo": "iFood"}})
        ok("Story que chama o post do dia" in chamadas[-1][1] and "mesmo assunto" in chamadas[-1][1], chamadas[-1][1][-400:])
        c = m.criticar("story", {"legenda": "3 sinais do CMV", "chamada": "Arrasta no perfil",
                                 "post_do_dia": {"tipo": "CARROSSEL", "titulo": "CMV", "legenda": "Salva pra fazer hoje. R$ 12"}})
        eq(c["veredito"], "aprova", "a legenda do post chamado é contexto, não texto do story")
        m.criticar("story", {"legenda": "Dica"})
        ok("Story que chama o post do dia" not in chamadas[-1][1], "só quando chama")
        eq(m.criticar("reel", {"falas": ["O prato custa R$ 12,40"]})["veredito"], "reprova", "reel também (22/10)")
        # 11/11: the common briefing (it quotes competitors' ads, emoji and all, and names the forbidden words) and the
        # declared reference are context, never the piece: five good stories were reproved for "emoji" and "salve"
        comum = "Regras: nunca \"salve\" em story. Radar: A1 «ANOTA AÍ \U0001F4DD — custo R$ 12»"
        ref = {"id": "A1", "gancho": "Salve este post \U0001F680", "o_que_muda": "vira enquete"}
        c = m.criticar("story", {"legenda": "Mesmo preço no app?", "briefing_comum": comum, "referencia": ref})
        eq(c["veredito"], "aprova", f"o briefing comum e a referência não são texto da peça: {c}")
        c = m.criticar("carrossel", {"briefing": {"titulo": "x", "briefing_comum": comum, "referencia": ref}, "ficha": {"slides": ["ok"]}})
        eq(c["veredito"], "aprova", f"nem dentro do briefing do Designer: {c}")
        c = m.criticar("story", {"legenda": "Salve para depois", "briefing_comum": comum})
        eq(c["veredito"], "reprova", "a peça continua conferida")
        limpo, tirado = m.tirar_briefing({"briefing": {"titulo": "x", "briefing_comum": comum}, "ficha": {}})
        ok(tirado == comum and "briefing_comum" not in limpo["briefing"] and limpo["briefing"]["titulo"] == "x", limpo)

    def t_critico_conta_de_exemplo_e_cenario(self):
        # 11/11: the same two Reels were approved and, twenty minutes later, reproved for "O óleo subiu" without a
        # source and "sobram oito" without a caveat. A sum marked "valores de exemplo" is a scenario, not a claim
        m = self._e()
        papel = m.PAPEIS["critico"]
        ok("Conta de exemplo é cenário, não afirmação" in papel and "vai em sugestões" in papel
           and "mesma régua que o criador e o Gestor" in papel, "o Crítico sabe ler a conta de exemplo e o briefing comum")

    def t_critico_le_o_cerebro_inteiro(self):
        # 22/10: the offer was cut at 6000 letters and he reproved numbers that were in it
        m = self._e(com_raiz="x" * 15000 + " 5 implementações por semana")
        tarefas = []
        m.chamar = lambda papel, tarefa, material, login="matheus": tarefas.append(tarefa) or \
            {"texto": APROVA, "erro": "", "imagens": [], "sem_imagem": []}
        m.criticar("carrossel", {"slides": ["5 implementações por semana"]})
        ok("5 implementações por semana" in tarefas[0], "o fim da oferta chega ao Crítico")

    def t_tipo_ou_material_ruim_reprova_sem_chamar(self):
        m = self._e()
        chamadas = []
        m.chamar = lambda *a, **k: chamadas.append(a) or {"texto": APROVA, "erro": "", "imagens": [], "sem_imagem": []}
        eq(m.criticar("tweet", "x")["veredito"], "reprova", "tipo desconhecido")
        eq(m.criticar("post", "   ")["veredito"], "reprova", "vazio")
        eq(chamadas, [], "nada chamado")

    # --- the Designer

    def _designer(self, m, ficha_texto: str, critica: str = APROVA):
        chamadas = []

        def chamar(papel, tarefa, material, login="matheus"):
            chamadas.append((papel, tarefa, material))
            return {"texto": ficha_texto if papel == "designer" else critica, "erro": "", "imagens": [], "sem_imagem": []}
        m.chamar = chamar
        return chamadas

    def t_designer_entrega_ficha_do_kit_e_sempre_a_critica(self):
        m = self._e(com_raiz="Marca: night, creme, lima")
        spec = {"marca": "raiz", "motor": "carrossel_raiz", "formato": "carrossel", "pasta": "c_prato",
                "conceito": "recibo", "slides": [{"manchete": "Seu prato campeão paga a conta?", "destaque": "conta"},
                                                 {"manchete": "Custo R$ 12,40 (valores de exemplo)", "destaque": "custo"}],
                "legenda": "Calculadora grátis na bio"}
        chamadas = self._designer(m, json.dumps(spec))
        d = m.desenhar("Carrossel sobre prato mais vendido no prejuízo")
        for chave in ("spec", "arquivos", "critica"):
            ok(chave in d, f"chave {chave}")
        eq(d["spec"]["motor"], "carrossel_raiz", "ficha do kit")
        eq(d["arquivos"], [], "carrossel da Raiz não renderiza no plugin")
        ok("base/carrossel.py c_prato" in d["render"], d["render"])
        ok(any("HTML próprio" in f for f in d["falta"]), d["falta"])
        eq([c[0] for c in chamadas], ["designer", "critico"], "o designer e depois o crítico")
        ok("Marca: night" in chamadas[0][1], "o designer lê o Cérebro da Raiz")
        ok("c_prato" in json.dumps(chamadas[1][2], ensure_ascii=False), "o crítico vê a ficha")
        eq(d["critica"]["veredito"], "aprova", "crítica anexada")

    def t_ficha_pronta_vai_ao_critico_sem_o_designer(self):
        # 27/10: the operator writes the ficha (the Designer put the falas out of order three times): checked,
        # rendered and judged as it is; an error comes back, never a rewrite
        m = self._e()
        chamadas = []
        m.chamar = lambda papel, tarefa, material, **k: chamadas.append(papel) or {"texto": APROVA, "erro": "", "imagens": [], "sem_imagem": []}
        m._validar_ficha = lambda molde, ficha: [] if ficha.get("pergunta") else ["pergunta: falta"]
        renders = []
        m._renderizar = lambda spec, falta: renders.append(spec) or ([], "", [], "", "", list(falta))
        d = m.julgar_ficha({"formato": "CARROSSEL", "marca": "raiz"}, {"marca": "raiz", "molde": "frases", "formato": "carrossel",
                                                                     "ficha": {"_marca": "raiz", "pergunta": "Quanto sobra?"}})
        eq(chamadas, ["critico"], "só o Crítico, nenhum Designer")
        ok(renders[0]["motor"] == "molde" and renders[0]["_formato_pedido"] == "carrossel"
           and renders[0]["ficha"]["pergunta"] == "Quanto sobra?", renders[0])
        eq(d["critica"]["veredito"], "aprova", "julgada como a do Designer")
        chamadas.clear()
        d = m.julgar_ficha({"formato": "CARROSSEL"}, {"molde": "frases", "formato": "carrossel", "ficha": {"_marca": "raiz"}})
        # 12/11: nothing rendered, so the Crítico is not asked: the reason is the ficha's own error
        ok(chamadas == [] and any("pergunta: falta" in f for f in d["falta"])
           and any("sem arte para julgar" in x for x in d["critica"]["motivos"]), f"erro volta, sem correção: {chamadas} {d['falta']}")

    def t_designer_ilegivel_ou_fora_do_ar_reprova(self):
        m = self._e()
        self._designer(m, "não sei fazer isso")
        d = m.desenhar("Um carrossel")
        eq(d["spec"], {}, "sem ficha")
        eq(d["critica"]["veredito"], "reprova", "nada para aprovar: reprova mesmo com o crítico aprovando")
        ok("o designer não devolveu uma ficha legível" in d["falta"], d["falta"])
        q = self._e()
        q._enviar = lambda body, login, tempo=0: (_ for _ in ()).throw(OSError("fora"))
        d = q.desenhar("Um carrossel")
        eq(d["critica"]["veredito"], "reprova", "fora do ar")
        ok(any("não respondeu" in f for f in d["falta"]), d["falta"])
        eq(q.desenhar("  ")["critica"]["veredito"], "reprova", "briefing vazio")

    def t_designer_confere_a_ficha(self):
        m = self._e()
        longa = " ".join(["palavra"] * 13)
        self._designer(m, json.dumps({"marca": "raiz", "motor": "carrossel_raiz", "formato": "carrossel",
                                      "slides": [{"manchete": longa}]}))
        d = m.desenhar("x")
        ok("carrossel precisa de 2 a 10 slides" in d["falta"], d["falta"])
        self._designer(m, json.dumps({"marca": "raiz", "motor": "carrossel_raiz", "slides": [{"manchete": longa},
                                                                                           {"manchete": "ok"}]}))
        ok(any("13 palavras" in f for f in m.desenhar("x")["falta"]), "manchete longa")
        self._designer(m, json.dumps({"marca": "raiz", "motor": "molde", "molde": "frases",
                                      "ficha": {"_marca": "doces-da-lu"}}))
        d = m.desenhar("x")
        ok(any("outra marca na ficha" in f for f in d["falta"]) and d["arquivos"] == [], d["falta"])
        self._designer(m, json.dumps({"motor": "photoshop"}))
        ok(any("motor desconhecido" in f for f in m.desenhar("x")["falta"]), "motor inventado")

    def _reels(self) -> Path:
        reels = Path(tempfile.mkdtemp(dir=self.tmp))
        (reels / "moldes" / "frases").mkdir(parents=True)
        (reels / "moldes" / "motor").mkdir(parents=True)
        (reels / "moldes" / "frases" / "esquema.json").write_text(json.dumps(
            {"formatos": ["carrossel"], "campos": {"pergunta": {"tipo": "texto", "max": 20}}}))
        (reels / "moldes" / "motor" / "validar.py").write_text(
            "def validar(esquema, ficha):\n    return [f'{k}: longo' for k, v in ficha.items()\n"
            "            if k in esquema['campos'] and len(v) > esquema['campos'][k]['max']]\n")
        (reels / "moldes" / "motor" / "render.py").write_text("")
        (reels / "moldes" / "catalogo.json").write_text(json.dumps(
            {"moldes": [{"id": "frases", "formatos": ["carrossel"], "situacao": "Frases", "ficha": {"pergunta": "até 20"}}]}))
        return reels

    def t_valores_de_exemplo_nao_se_repete_no_texto(self):
        # 12/11: four "(valores de exemplo)" in the four steps of a Reel; the motor puts the note on screen
        m = self._e()
        ok(m._exemplo_repetido({"passos": ["Taxa R$ 7 (valores de exemplo)", "Longe R$ 12 (valores de exemplo)"]}),
           "duas vezes no texto: volta ao Designer")
        eq(m._exemplo_repetido({"passos": ["Taxa R$ 7", "Longe R$ 12"], "nota": "valores de exemplo"}), [], "no campo nota, ok")
        eq(m._exemplo_repetido({"pista": "Valores de exemplo: R$ 7"}), [], "uma vez, ok")
        ok(any("escrito 2 vezes" in f for f in m._conferir_spec({"motor": "molde", "marca": "raiz", "molde": "x", "ficha": {
            "_marca": "raiz", "itens": [{"a": "R$ 3. Valores de exemplo."}, {"a": "R$ 6. Valores de exemplo."}]}})),
           "a conferência da ficha da Raiz cobra")

    def t_designer_sabe_quais_fotos_existem(self):
        # 12/11, the simulation: "fotos/pizza_cozinha.jpg" (no such photo) and a description in the photo field
        reels = self._reels()
        (reels / "moldes" / "midia" / "fotos").mkdir(parents=True)
        (reels / "moldes" / "midia" / "fotos" / "indice.json").write_text(json.dumps(
            {"cantina_marmita.jpg": {"mostra": "marmita de frango"}, "oficina_pneu.jpg": {"mostra": "pneu"}}))
        m = self._e(reels=reels)
        f = m.fotos_do_banco()
        ok("fotos/cantina_marmita.jpg: marmita de frango" in f and "oficina" not in f, f)
        tarefas = []
        m.chamar = lambda papel, tarefa, material, login="matheus": tarefas.append(tarefa) or {
            "texto": "", "erro": "fora", "imagens": [], "sem_imagem": []}
        m.desenhar("Carrossel da Raiz")
        ok("fotos/cantina_marmita.jpg" in tarefas[0], "a lista vai na tarefa do Designer")
        ok("fotos/cantina_marmita.jpg" in m._tarefa_correcao({"molde": "frases", "ficha": {}}, ["ficha: foto: x"]),
           "e na correção")

    def t_designer_renderiza_molde_de_outra_marca_e_mostra_ao_critico(self):
        reels = self._reels()
        m = self._e(reels=reels)
        img = self.tmp / "slide_molde.png"
        _png(img)
        m._pode_renderizar = lambda: ""
        renders = []
        m.renderizar_molde = lambda molde, formato, ficha: renders.append((molde, formato, ficha)) or \
            ([str(img), str(self.tmp / "video.mp4")], "")
        chamadas = self._designer(m, json.dumps({"marca": "doces-da-lu", "motor": "molde", "molde": "frases",
                                                 "formato": "carrossel", "ficha": {"pergunta": "O que mais ouve?"}}))
        d = m.desenhar("Carrossel de frases para a Doces da Lu")
        eq(renders, [("frases", "carrossel", {"pergunta": "O que mais ouve?"})], "renderizou com a ficha")
        eq(d["arquivos"], [str(img), str(self.tmp / "video.mp4")], "arquivos devolvidos")
        eq(chamadas[1][2]["imagens"], [str(img)], "o crítico recebe as imagens renderizadas")
        ok("frases" in chamadas[0][1] and "Catálogo de moldes" in chamadas[0][1], "o designer vê o catálogo")
        # a ficha the molde's validator refuses is not rendered
        self._designer(m, json.dumps({"marca": "doces-da-lu", "motor": "molde", "molde": "frases",
                                      "ficha": {"pergunta": "x" * 30}}))
        d = m.desenhar("x")
        ok("ficha: pergunta: longo" in d["falta"] and len(renders) == 1, d["falta"])
        # without the engine here: the spec plus what is missing
        sem = self._e(reels=None)
        self._designer(sem, json.dumps({"marca": "doces-da-lu", "motor": "molde", "molde": "frases", "ficha": {}}))
        ok(any("não existe no motor" in f for f in sem.desenhar("x")["falta"]), "sem motor")

    def t_designer_corrige_a_ficha_com_o_esquema(self):
        # 22/10, first real run: no "motor", texts over the limits; one correction round with the schema fixes it
        reels = self._reels()
        m = self._e(reels=reels)
        m._pode_renderizar = lambda: ""
        m.renderizar_molde = lambda molde, formato, ficha: ([], "")
        respostas = [json.dumps({"marca": "raiz", "molde": "frases", "formato": "carrossel",
                                 "ficha": {"_marca": "raiz", "pergunta": "x" * 30}}),
                     json.dumps({"marca": "raiz", "molde": "frases", "formato": "carrossel",
                                 "ficha": {"_marca": "raiz", "pergunta": "Quanto sobra?"}})]
        chamadas = []

        def chamar(papel, tarefa, material, login="matheus"):
            chamadas.append((papel, tarefa))
            texto = respostas.pop(0) if papel == "designer" else APROVA
            return {"texto": texto, "erro": "", "imagens": [], "sem_imagem": []}
        m.chamar = chamar
        d = m.desenhar("Carrossel da Raiz")
        eq(d["spec"]["motor"], "molde", "sem motor, mas com molde: é o motor de moldes")
        eq(d["falta"], [], "a correção passou")
        eq(d["spec"]["ficha"]["pergunta"], "Quanto sobra?", "ficha corrigida")
        segunda = chamadas[1][1]
        ok(chamadas[1][0] == "designer" and "pergunta: longo" in segunda and "Esquema do molde" in segunda
           and '"max": 20' in segunda, segunda[:300])
        # it gives up after CORRECOES tries and says what is still wrong
        respostas[:] = [json.dumps({"molde": "frases", "ficha": {"pergunta": "x" * 30}})] * (m.CORRECOES + 1)
        chamadas.clear()
        m.REVISOES = 0  # this checks the corrections only (the review round after a reproval has its own tests)
        d = m.desenhar("Carrossel da Raiz")
        ok(sum(p == "designer" for p, _ in chamadas) == m.CORRECOES + 1 and "ficha: pergunta: longo" in d["falta"], d["falta"])

    def t_correcao_ilegivel_pergunta_de_novo_e_sem_arte_nao_chama_o_critico(self):
        # 12/11, the simulation: three pieces died on "o designer não respondeu à correção (resposta ilegível)" after one
        # try (the same correction, asked again, came back fine), and the Crítico, with no art, said "a arte não veio"
        import os
        m = self._e()
        eq(m._json('{"molde": "frases", "ficha": {"a": 1}}\nObs.: troquei {x} por {y}.'), {"molde": "frases", "ficha": {"a": 1}},
           "a ficha seguida de uma nota com chaves")
        reels = self._reels()
        m = self._e(reels=reels)
        m._pode_renderizar = lambda: ""
        m.renderizar_molde = lambda molde, formato, ficha: (["s1.jpg"], "")
        respostas = [json.dumps({"marca": "raiz", "molde": "frases", "formato": "carrossel",
                                 "ficha": {"_marca": "raiz", "pergunta": "x" * 30}}), "Desculpe, não consegui.",
                     json.dumps({"marca": "raiz", "molde": "frases", "formato": "carrossel",
                                 "ficha": {"_marca": "raiz", "pergunta": "Quanto sobra?"}})]
        chamadas = []

        def chamar(papel, tarefa, material, login="matheus"):
            chamadas.append(papel)
            return {"texto": respostas.pop(0) if papel == "designer" else APROVA, "erro": "", "imagens": [], "sem_imagem": []}
        m.chamar = chamar
        os.environ["ESPECIALISTAS_SAIDA"] = str(Path(tempfile.mkdtemp(dir=self.tmp)))
        try:
            d = m.desenhar("Carrossel da Raiz")
            guardada = list((Path(os.environ["ESPECIALISTAS_SAIDA"]) / "ilegiveis").glob("*.txt"))
        finally:
            os.environ.pop("ESPECIALISTAS_SAIDA", None)
        eq(d["falta"], [], f"a correção ilegível foi pedida de novo e passou: {d['falta']}")
        ok(guardada and "Desculpe" in guardada[0].read_text(), "a resposta ilegível fica guardada para o operador")
        # nothing rendered: the reason is what failed, and the Crítico is not asked to judge an empty piece
        m.renderizar_molde = lambda molde, formato, ficha: ([], "o molde recusou a ficha: imagem: é o caminho de uma imagem")
        respostas[:] = [json.dumps({"marca": "raiz", "molde": "frases", "formato": "carrossel",
                                    "ficha": {"_marca": "raiz", "pergunta": "Quanto sobra?"}})] * (m.CORRECOES + 1)
        chamadas.clear()
        m.REVISOES = 0
        d = m.desenhar("Carrossel da Raiz")
        ok("critico" not in chamadas, f"sem arte, o Crítico não é chamado: {chamadas}")
        ok(d["critica"]["veredito"] == "reprova" and any("sem arte para julgar" in x and "caminho de uma imagem" in x
                                                         for x in d["critica"]["motivos"]), d["critica"])

    def t_jargao_e_recusa_do_molde_entram_na_correcao(self):
        m = self._e()
        ok(m._jargao("Seu CMV está alto") and "CMV" in m._jargao("Seu CMV está alto")[0], "CMV sozinho")
        eq(m._jargao("CMV, o custo dos ingredientes do que você vendeu"), [], "CMV explicado")
        ok(m._jargao("Seu CMV está alto. " + "x" * 200 + " CMV é o custo dos ingredientes"), "explicado só lá no fim não vale")
        # the template refuses only when rendering (a video too short): the Designer fixes it like a ficha error
        reels = self._reels()
        m = self._e(reels=reels)
        m._pode_renderizar = lambda: ""
        renders = []

        def render(molde, formato, ficha):
            renders.append(ficha["pergunta"])
            return ([], "o molde recusou a ficha: MOLDE RECUSOU: duração 41.9 s") if len(renders) == 1 else (["s1.jpg"], "")
        m.renderizar_molde = render
        fichas = [{"marca": "raiz", "motor": "molde", "molde": "frases", "formato": "carrossel",
                   "ficha": {"_marca": "raiz", "pergunta": p}} for p in ("Curta?", "Maior agora")]
        chamadas = []

        def chamar(papel, tarefa, material, login="matheus"):
            chamadas.append((papel, tarefa))
            return {"texto": json.dumps(fichas.pop(0)) if papel == "designer" else APROVA, "erro": "", "imagens": [],
                    "sem_imagem": []}
        m.chamar = chamar
        d = m.desenhar("Carrossel da Raiz")
        eq(renders, ["Curta?", "Maior agora"], "renderizou de novo com a ficha corrigida")
        ok("duração 41.9 s" in chamadas[1][1] and d["falta"] == [] and d["arquivos"] == ["s1.jpg"], (chamadas[1][1][:200], d))

    def t_formato_da_vaga_vale(self):
        # 4º teste real (22/10): a carousel slot came back as a Reel
        reels = self._reels()
        esq = reels / "moldes" / "frases" / "esquema.json"
        esq.write_text(json.dumps({"formatos": ["carrossel", "reel"], "campos": {"pergunta": {"tipo": "texto", "max": 20}}}))
        m = self._e(reels=reels)
        m._pode_renderizar = lambda: ""
        m.renderizar_molde = lambda molde, formato, ficha, previa=False: (["s1.jpg"], "")
        fichas = [{"marca": "raiz", "motor": "molde", "molde": "frases", "formato": f, "ficha": {"_marca": "raiz", "pergunta": "Oi"}}
                  for f in ("reel", "carrossel")]
        chamadas = []

        def chamar(papel, tarefa, material, login="matheus"):
            chamadas.append((papel, tarefa))
            return {"texto": json.dumps(fichas.pop(0)) if papel == "designer" else APROVA, "erro": "", "imagens": [],
                    "sem_imagem": []}
        m.chamar = chamar
        (reels / "moldes" / "catalogo.json").write_text(json.dumps({"moldes": [
            {"id": "frases", "formatos": ["carrossel", "reel"], "situacao": "Frases", "ficha": {}},
            {"id": "so-video", "formatos": ["reel"], "situacao": "Só vídeo", "ficha": {}}]}))
        d = m.desenhar({"formato": "CARROSSEL", "titulo": "x", "ideia": "y"})
        ok("so-video" not in chamadas[0][1] and "- frases" in chamadas[0][1], "só os moldes que fazem carrossel")
        m.PLUGINS = Path(tempfile.mkdtemp(dir=self.tmp))
        (m.PLUGINS / "conteudo" / "story" / "telas").mkdir(parents=True)
        (m.PLUGINS / "conteudo" / "story" / "telas" / "cmv-real.jpg").write_bytes(b"x")
        ok("lanca-app" not in m.telas_do_sistema("carrossel") and "campo de foto" in m.telas_do_sistema("carrossel"),
           "no carrossel a tela vai num molde de carrossel")
        ok("lanca-app" in m.telas_do_sistema("reel"), "no vídeo, o tour com zoom")
        # 11/11: the slot's format is imposed at once (the molde makes carousels): no correction round is spent on it
        eq([papel for papel, _ in chamadas], ["designer", "critico"], "o formato da vaga é imposto, sem rodada de correção")
        eq((d["spec"]["formato"], d["falta"]), ("carrossel", []), "sai como carrossel")
        # a molde that cannot make the slot's format: the correction names the moldes that can
        fichas[:] = [{"marca": "raiz", "motor": "molde", "molde": "so-video", "formato": "reel", "ficha": {"_marca": "raiz"}},
                     {"marca": "raiz", "motor": "molde", "molde": "frases", "formato": "carrossel", "ficha": {"_marca": "raiz", "pergunta": "Oi"}}]
        (reels / "moldes" / "so-video").mkdir(exist_ok=True)
        (reels / "moldes" / "so-video" / "esquema.json").write_text(json.dumps({"formatos": ["reel"], "campos": {}}))
        chamadas.clear()
        d = m.desenhar({"formato": "CARROSSEL", "titulo": "x", "ideia": "y"})
        ok("não faz carrossel" in chamadas[1][1] and "- frases" in chamadas[1][1] and "sem trocar o assunto" in chamadas[1][1],
           chamadas[1][1][:300])
        eq((d["spec"]["molde"], d["spec"]["formato"], d["falta"]), ("frases", "carrossel", []), "corrigido para um molde de carrossel")
        # for the Raiz only the moldes that fit a brand that teaches owners are offered
        cat = {i: {"formatos": ["carrossel"]} for i in ("mito", "combo", "cardapio", "time")}
        eq(sorted(m.moldes_da_marca(cat, "raiz", "carrossel")), ["mito", "time"], "molde de cardápio e combo não é da Raiz")
        eq(sorted(m.moldes_da_marca(cat, "doces-da-lu", "carrossel")), sorted(cat), "outra marca vê o catálogo inteiro")
        eq(sorted(m.moldes_da_marca({"so-teste": {}}, "raiz", "carrossel")), ["so-teste"], "sem nenhum que sirva, o catálogo fica")
        # 11/11: "ficha: produto: falta" killed a carousel twice (the Designer left the closing field out and the
        # correction came back unreadable). For the Raiz the vitrine has a default; what the Designer wrote stays
        (reels / "moldes" / "frases" / "esquema.json").write_text(json.dumps({"formatos": ["carrossel"], "campos": {
            "pergunta": {"tipo": "texto", "max": 20},
            "produto": {"tipo": "objeto", "campos": {"foto": {"tipo": "foto"}, "nome": {"tipo": "texto"}, "detalhe": {"tipo": "texto", "obrigatorio": False}}}}}))
        sem = m._spec({"erro": "", "texto": json.dumps({"marca": "raiz", "molde": "frases", "ficha": {"_marca": "raiz", "pergunta": "Oi"}})}, "carrossel")
        eq(sem["ficha"]["produto"], {"foto": "fotos/raiz_calculadora.jpg", "nome": "Lucro na Mão em 30 Dias",
                                     "detalhe": "Veja quanto sobra em cada produto"}, "a vitrine da Raiz entra quando falta")
        com = m._spec({"erro": "", "texto": json.dumps({"marca": "raiz", "molde": "frases", "ficha": {
            "_marca": "raiz", "pergunta": "Oi", "produto": {"nome": "Raiz Connect"}}})}, "carrossel")
        eq((com["ficha"]["produto"]["nome"], com["ficha"]["produto"]["foto"]), ("Raiz Connect", "fotos/raiz_calculadora.jpg"),
           "o que o Designer escreveu fica; só o que falta é preenchido")
        # an example sum of the Raiz gets the origin the molde asks for ("conta[1].valor: dado real sem origem", 11/11)
        m._validar_ficha = lambda molde, ficha: [] if (ficha.get("_origem") or {}).get("conta") else ["conta[1].valor: dado real sem origem (_origem: dono ou sistema)"]
        conta = m._spec({"erro": "", "texto": json.dumps({"marca": "raiz", "molde": "frases", "ficha": {
            "_marca": "raiz", "pergunta": "Oi", "conta": [{"valor": 5}, {"valor": 6}], "_origem": {"produto": "sistema"}}})}, "carrossel")
        eq(conta["ficha"]["_origem"], {"conta": "dono", "produto": "sistema"}, "a origem que falta é preenchida; a que veio fica")
        ok("Cena ou slide tipográfico" in m.PAPEIS["critico"], "o Crítico não exige foto do produto em cena de texto")
        outra = m._spec({"erro": "", "texto": json.dumps({"marca": "doces-da-lu", "molde": "frases", "ficha": {"_marca": "doces-da-lu", "pergunta": "Oi"}})}, "carrossel")
        ok("produto" not in outra["ficha"], "outra marca não ganha a vitrine da Raiz")
        ok("POV" in m.PAPEIS["critico"] and "decisão #85) não vale para ele" in m.PAPEIS["critico"], "o POV de humor tem a exceção escrita")
        ok("troca de molde, nunca de assunto" in m.PAPEIS["designer"] and "o exemplo concreto do briefing" in m.PAPEIS["designer"],
           "o Designer fica no assunto e é concreto")

    def t_moldes_dos_posts_vizinhos_nao_sao_oferecidos(self):
        # 08/11, Matheus: "Estao td igual os post": three carousels in a row from passo-a-passo
        reels = self._reels()
        m = self._e(reels=reels)
        chamadas = []
        m.chamar = lambda papel, tarefa, material, login="matheus": chamadas.append(tarefa) or {
            "texto": "nada", "erro": "", "imagens": [], "sem_imagem": []}
        (reels / "moldes" / "catalogo.json").write_text(json.dumps({"moldes": [
            {"id": "passo-a-passo", "formatos": ["carrossel"], "situacao": "Passos", "ficha": {}},
            {"id": "mito", "formatos": ["carrossel"], "situacao": "Mito", "ficha": {}}]}))
        m.desenhar({"formato": "CARROSSEL", "titulo": "x", "ideia": "y", "evitar_moldes": ["passo-a-passo"]})
        ok("- passo-a-passo" not in chamadas[0] and "- mito" in chamadas[0], "o molde dos vizinhos sai do catálogo")
        chamadas.clear()
        m.desenhar({"formato": "CARROSSEL", "titulo": "x", "ideia": "y", "evitar_moldes": ["passo-a-passo", "mito"]})
        ok("- passo-a-passo" in chamadas[0] and "- mito" in chamadas[0], "sem nenhum sobrando, o catálogo fica inteiro")

    def t_designer_ve_os_campos_reais_do_molde(self):
        # 08/11: the catalog said demonstracao had problema/resultado/telas and no falas; the esquema wants falas too.
        # The Designer is shown the esquema's own fields, not the catalog's hand-written summary.
        reels = self._reels()
        m = self._e(reels=reels)
        (reels / "moldes" / "demo").mkdir(parents=True, exist_ok=True)
        (reels / "moldes" / "demo" / "esquema.json").write_text(json.dumps({"formatos": ["reel"], "campos": {
            "problema": {"tipo": "texto", "min": 10, "max": 60},
            "nota": {"tipo": "texto", "max": 40, "obrigatorio": False},
            "falas": {"tipo": "lista", "min": 5, "max": 8, "item": {"texto": {"tipo": "texto", "max": 90}}}}}))
        (reels / "moldes" / "catalogo.json").write_text(json.dumps({"moldes": [
            {"id": "demo", "formatos": ["reel"], "situacao": "Demo", "ficha": {"problema": "...", "cenas": "..."}},
            {"id": "sem-esquema", "formatos": ["reel"], "situacao": "X", "ficha": {"so_no_catalogo": "..."}}]}))
        chamadas = []
        m.chamar = lambda papel, tarefa, material, login="matheus": chamadas.append(tarefa) or {
            "texto": "nada", "erro": "", "imagens": [], "sem_imagem": []}
        m.desenhar({"formato": "REELS", "titulo": "x", "ideia": "y"})
        linha = next(l for l in chamadas[0].splitlines() if l.startswith("- demo"))
        ok("falas: lista min 5 max 8 cada um {texto: texto max 90}" in linha and "nota: texto max 40 opcional" in linha
           and "cenas" not in linha, linha)
        ok("so_no_catalogo" in chamadas[0], "molde sem esquema: fica o resumo do catálogo")

    def t_reel_narrado_falas_e_siglas_antes_do_render(self):
        # 10/11, casos reais: 9 Reels de domingo 08/11 e de quarta 11/11 caíram com "falas: são 12 (... uma por tela (5)
        # ...); vieram 10" (a regra "telas + 7 falas" só estava na dica, que o Designer não via) e com "fala 4 diz 'No CMV
        # do mês', fala 5 'Na Curva ABC' e fala 6 'A DRE reúne'" sem explicação. Agora o Designer vê a regra e o código
        # confere as duas coisas antes do render, para a rodada de correção resolver.
        reels = self._reels()
        real = next((r / "reels" / "moldes" / "lanca-app" / "esquema.json" for r in RAIZ.parents
                     if (r / "reels" / "moldes" / "lanca-app" / "esquema.json").exists()), None)
        esquema = json.loads(real.read_text(encoding="utf-8")) if real else {"formatos": ["reel"], "campos": {
            "telas": {"tipo": "lista", "min": 3, "max": 5, "item": {"imagem": {"tipo": "foto"}}},
            "falas": {"tipo": "lista", "min": 10, "max": 12, "item": {"tipo": "texto", "max": 170},
                      "dica": "telas + 7 falas: dores, pergunta, revelação, uma por tela, benefícios, como começar, "
                              "oferta ou para quem, chamada; 55 a 65 s no total"}}}  # the staging copy has no moldes
        (reels / "moldes" / "lanca-app").mkdir(parents=True)
        (reels / "moldes" / "lanca-app" / "esquema.json").write_text(json.dumps(esquema, ensure_ascii=False), encoding="utf-8")
        (reels / "moldes" / "motor" / "validar.py").write_text("def validar(esquema, ficha):\n    return []\n")
        m = self._e(reels=reels)
        campos = m._campos_do_molde("lanca-app")
        ok("falas: lista min 10 max 12" in campos and "telas + 7 falas" in campos and "55 a 65 s" in campos, campos)
        telas = [{"imagem": f"/a0/usr/plugins/conteudo/story/telas/{n}.jpg", "nome": nome, "legenda": "veja aqui"}
                 for n, nome in (("cmv-real", "CMV"), ("curva-abc-custos", "Curva ABC"), ("dre", "DRE"),
                                 ("cozinha-kds", "Cozinha"), ("visao-executiva", "Visão"))]
        spec = {"marca": "raiz", "motor": "molde", "molde": "lanca-app", "formato": "reel",
                "ficha": {"_marca": "raiz", "telas": telas, "falas": ["Fala simples."] * 10}}
        falta = m._conferir_spec(spec)
        ok(any("falas: são 12 (5 telas + 7" in f and "vieram 10" in f for f in falta), falta)
        ok(not any("CMV" in f or "DRE" in f or "curva ABC" in f for f in falta),
           f"o rótulo e o arquivo da tela não são texto da peça: {falta}")
        spec["ficha"]["falas"] = ["Fala simples."] * 9 + ["No CMV do mês você vê a meta.", "Na Curva ABC, as contas.",
                                                          "A DRE reúne tudo."]
        falta = m._conferir_spec(spec)
        ok(not any(f.startswith("ficha: falas: são") for f in falta), falta)
        ok(sum(f.startswith("ficha: CMV") or f.startswith("ficha: curva ABC") or f.startswith("ficha: DRE") for f in falta) == 3,
           falta)
        ok(any("o resumo do mês" in f for f in falta), "o erro já diz como explicar a DRE")
        spec["ficha"]["falas"][9:] = ["No CMV, o custo dos ingredientes do que você vendeu, você vê a meta.",
                                      "Na curva ABC, onde vai a maior parte do dinheiro gasto.",
                                      "A DRE é o resumo do mês: quanto entrou, quanto saiu e o que sobrou."]
        eq([f for f in m._conferir_spec(spec) if not f.startswith("ficha: falas")], [], "siglas explicadas passam")
        # a molde without the telas rule is not touched
        eq(m._falas_do_molde("frases", {"telas": [1], "falas": [1]}), [], "molde sem a regra")

    def t_tela_do_sistema_nome_ficticio_e_selo(self):
        # 10/11, casos reais: "Slide 6 mostra 'Pizzaria Bella Napoli', mas a ficha exige ocultar o nome" e "A legenda
        # dizer que os números são valores de exemplo não cumpre a regra" (8 carrosséis caíram nisso de 06 a 10/11)
        m = self._e()
        ok("Pizzaria Bella Napoli" in m.PAPEIS["critico"] and "fictícios" in m.PAPEIS["critico"]
           and "selo \"Valores de exemplo\"" in m.PAPEIS["critico"], "o Crítico sabe que o nome é da conta de exemplo")
        m.PLUGINS = Path(tempfile.mkdtemp(dir=self.tmp))
        (m.PLUGINS / "conteudo" / "story" / "telas").mkdir(parents=True)
        for n in ("dre.jpg", "curva-abc-custos.jpg", "cmv-real.jpg"):
            (m.PLUGINS / "conteudo" / "story" / "telas" / n).write_bytes(b"x")
        t = m.telas_do_sistema("carrossel")
        ok("Pizzaria Bella Napoli" in t and "não prometa esconder" in t and "pequeno no pé de todo slide" in t
           and "selo" in t, t)
        ok("o resumo do mês" in t and "maior parte do dinheiro" in t and "custo dos ingredientes" in t,
           "a descrição da tela já traz a sigla explicada")
        ok("ou no texto do slide/legenda" not in m.KIT and "nunca só" in m.KIT, "o kit não oferece mais a legenda")
        # 11/11, caso real: "calculadora-quanto-sobra.jpg" (página pública, clara, sem menu) apareceu na pasta das telas
        # e foi oferecida como tela do sistema; o Crítico reprovou "a tela da calculadora está cortada e não mostra o menu"
        (m.PLUGINS / "conteudo" / "story" / "telas" / "calculadora-quanto-sobra.jpg").write_bytes(b"x")
        ok("calculadora" not in m.telas_do_sistema("carrossel") and "dre.jpg" in m.telas_do_sistema("carrossel"),
           "só as telas do sistema conhecidas são oferecidas")
        # 10/11, caso real: "o slide 5 traz 'Lucro na Mão em 30 Dias: link na bio', embora a instrução diga para não
        # citar essa oferta" (o slide final é do motor) e o gestor pedindo para tirar o que o Designer não controla
        ok("fixos do kit" in m.PAPEIS["critico"] and "Lucro na Mão em 30 Dias: link na" in m.PAPEIS["critico"], "slide final")
        ok("Não peça o que o Designer não controla" in m.PAPEIS["gestor"], "o gestor não pede o impossível")

    def t_designer_refaz_com_os_motivos_do_critico(self):
        # 22/10: the agent makes the posts by itself, so a reproved piece is redone once before it reaches Matheus
        reels = self._reels()
        m = self._e(reels=reels)
        m._pode_renderizar = lambda: ""
        m.renderizar_molde = lambda molde, formato, ficha: ([], "")
        fichas = [{"marca": "raiz", "motor": "molde", "molde": "frases", "formato": "carrossel",
                   "ficha": {"_marca": "raiz", "pergunta": "Margem baixa?"}},
                  {"marca": "raiz", "motor": "molde", "molde": "frases", "formato": "carrossel",
                   "ficha": {"_marca": "raiz", "pergunta": "Custo alto?"}}]
        vereditos = [json.dumps({"veredito": "reprova", "motivos": ["CMV sem explicação"], "sugestoes": ["explique"]}), APROVA]
        chamadas = []

        def chamar(papel, tarefa, material, login="matheus"):
            chamadas.append((papel, tarefa))
            texto = json.dumps(fichas.pop(0)) if papel == "designer" else vereditos.pop(0)
            return {"texto": texto, "erro": "", "imagens": [], "sem_imagem": []}
        m.chamar = chamar
        d = m.desenhar("Carrossel da Raiz")
        eq([p for p, _ in chamadas], ["designer", "critico", "designer", "critico"], "uma revisão")
        ok("CMV sem explicação" in chamadas[2][1] and "explique" in chamadas[2][1], "o Designer recebe os motivos")
        eq(d["critica"]["veredito"], "aprova", "a versão revisada é a que vale")
        eq(d["spec"]["ficha"]["pergunta"], "Custo alto?", "ficha nova")
        eq(d["revisoes"], [["CMV sem explicação"]], "fica registrado o que foi corrigido")
        # a revision call that fails is said, never silent
        fichas[:] = [{"marca": "raiz", "motor": "molde", "molde": "frases", "formato": "carrossel",
                      "ficha": {"_marca": "raiz", "pergunta": "Margem baixa?"}}]
        vereditos[:] = [json.dumps({"veredito": "reprova", "motivos": ["fraco"], "sugestoes": []})]
        m.chamar = lambda papel, tarefa, material, login="matheus": (
            {"texto": json.dumps(fichas.pop(0)), "erro": "", "imagens": [], "sem_imagem": []} if papel == "designer" and fichas
            else {"texto": "", "erro": "TimeoutError", "imagens": [], "sem_imagem": []} if papel == "designer"
            else {"texto": vereditos.pop(0) if vereditos else APROVA, "erro": "", "imagens": [], "sem_imagem": []})
        d = m.desenhar("Carrossel da Raiz")
        ok(any("não respondeu à revisão (TimeoutError)" in f for f in d["falta"]), d["falta"])

    def t_revisar_peca_ja_na_agenda(self):
        # 22/10, Matheus: "Se o crítico rejeita, automáticamente deveria ser refeito": the advance check redoes a piece
        # of the agenda with the Crítico's reasons, the art it saw and the same render and judgment as desenhar()
        m = self._e(reels=self._reels())
        m._pode_renderizar = lambda: ""
        m.renderizar_molde = lambda molde, formato, ficha: ([], "")
        antiga = {"marca": "raiz", "motor": "molde", "molde": "frases", "formato": "carrossel", "_formato_pedido": "carrossel",
                  "ficha": {"_marca": "raiz", "pergunta": "Margem baixa?"}}
        chamadas = []

        def chamar(papel, tarefa, material, login="matheus"):
            chamadas.append((papel, tarefa, material))
            if papel == "designer":
                return {"texto": json.dumps(dict(antiga, ficha={"_marca": "raiz", "pergunta": "Custo alto?"})), "erro": "",
                        "imagens": [], "sem_imagem": []}
            return {"texto": APROVA, "erro": "", "imagens": [], "sem_imagem": []}
        m.chamar = chamar
        d = m.revisar({"formato": "CARROSSEL", "titulo": "Margem"}, antiga, {"motivos": ["slide 2 cortado"]}, ["/x/1.jpg"])
        eq([p for p, _, _ in chamadas], ["designer", "critico"], "uma volta do Designer e o Crítico de novo")
        ok("slide 2 cortado" in chamadas[0][1] and chamadas[0][2]["imagens"] == ["/x/1.jpg"], "motivos e arte que ele viu")
        eq((d["critica"]["veredito"], d["spec"]["ficha"]["pergunta"], d["spec"]["_formato_pedido"]),
           ("aprova", "Custo alto?", "carrossel"), "a ficha nova, na mesma vaga")
        m.chamar = lambda *a, **k: {"texto": "", "erro": "TimeoutError", "imagens": [], "sem_imagem": []}
        d = m.revisar("x", antiga, {"motivos": ["fraco"]})
        ok(d["critica"]["veredito"] == "reprova" and "TimeoutError" in d["falta"][0], "Designer fora: continua reprovada")

    def t_molde_inexistente_a_correcao_mostra_os_que_existem(self):
        # 10/11, caso real: o gestor orientou "use um molde de cena ou humor" e o Designer escreveu "molde": "cena";
        # a correção não dizia quais moldes existem e o Reel de quarta caiu em "ficha: molde cena não existe no motor"
        reels = self._reels()
        (reels / "moldes" / "conta-mudou").mkdir(parents=True)
        (reels / "moldes" / "conta-mudou" / "esquema.json").write_text(json.dumps({"formatos": ["reel"], "campos": {
            "pergunta": {"tipo": "texto", "max": 20}}}))
        (reels / "moldes" / "catalogo.json").write_text(json.dumps({"moldes": [
            {"id": "conta-mudou", "formatos": ["reel"], "situacao": "Conta que mudou", "ficha": {}},
            {"id": "lanca-app", "formatos": ["reel"], "situacao": "Tour de telas", "ficha": {}},
            {"id": "frases", "formatos": ["carrossel"], "situacao": "Frases", "ficha": {}}]}))
        m = self._e(reels=reels)
        m._pode_renderizar = lambda: ""
        m.renderizar_molde = lambda molde, formato, ficha, previa=False: (["p01.jpg"], "")
        fichas = [{"marca": "raiz", "motor": "molde", "molde": "cena", "formato": "reel", "ficha": {"_marca": "raiz"}},
                  {"marca": "raiz", "motor": "molde", "molde": "conta-mudou", "formato": "reel",
                   "ficha": {"_marca": "raiz", "pergunta": "Quanto sobra?"}}]
        chamadas = []

        def chamar(papel, tarefa, material, login="matheus"):
            chamadas.append((papel, tarefa))
            return {"texto": json.dumps(fichas.pop(0)) if papel == "designer" else APROVA, "erro": "", "imagens": [],
                    "sem_imagem": []}
        m.chamar = chamar
        d = m.desenhar({"formato": "REELS", "titulo": "x", "ideia": "y", "evitar_moldes": ["lanca-app"]})
        correcao = chamadas[1][1]
        ok("não existe" in correcao and "- conta-mudou" in correcao and "- lanca-app" not in correcao
           and "- frases" not in correcao, correcao[:500])
        eq((d["spec"]["molde"], [f for f in d["falta"] if "não existe" in f]), ("conta-mudou", []), "corrigido com um molde real")

    def t_legenda_generica_entra_na_correcao(self):
        # 10/11, caso real: carrossel de quarta 11/11 reprovado só por "A legenda termina com 'Conheça a solução para
        # sua operação.' Isso quebra a regra de voz da marca"
        m = self._e()
        spec = {"marca": "raiz", "motor": "molde", "molde": "frases", "formato": "carrossel", "ficha": {"_marca": "raiz"},
                "legenda": "Responder a mesma pergunta o dia todo cansa. Conheça a solução para sua operação."}
        m._validar_ficha = lambda molde, ficha: []
        ok(any("legenda usa \"Conheça\"" in f for f in m._conferir_spec(spec)), m._conferir_spec(spec))
        spec["legenda"] = "Responder a mesma pergunta o dia todo cansa. Toque no link da bio e veja o cardápio."
        eq([f for f in m._conferir_spec(spec) if "legenda" in f], [], "legenda com o passo concreto passa")

    def t_regras_duras_voltam_ao_designer(self):
        # 11/11, casos reais: "a tela da calculadora está cortada e não mostra o menu" (calculadora não é tela do
        # sistema), texto cortado no slide (o render já via), legenda sem a chamada do slide final
        m = self._e()
        m._validar_ficha = lambda molde, ficha: []
        base = {"marca": "raiz", "motor": "molde", "molde": "frases", "formato": "carrossel",
                "legenda": "Qual time é você? Comenta aqui. Toque no link da bio e veja o Lucro na Mão em 30 Dias."}
        spec = dict(base, ficha={"_marca": "raiz", "foto": "/a0/usr/plugins/conteudo/story/telas/calculadora-quanto-sobra.jpg"})
        ok(any("calculadora-quanto-sobra.jpg não é tela do sistema" in f for f in m._conferir_spec(spec)), m._conferir_spec(spec))
        spec = dict(base, ficha={"_marca": "raiz", "foto": "/a0/usr/plugins/conteudo/story/telas/cozinha-kds.jpg"})
        eq(m._conferir_spec(spec), [], "tela conhecida e legenda com a chamada passam")
        spec = dict(spec, legenda="Qual time é você? Comenta aqui.")
        ok(any("link da bio" in f for f in m._conferir_spec(spec)), "legenda sem a chamada do slide final")
        # the render's own check goes back to the Designer, not to the Crítico
        reels = self._reels()
        m = self._e(reels=reels)
        m._pode_renderizar = lambda: ""
        renders = []

        def render(molde, formato, ficha):
            renders.append(ficha["pergunta"])
            return (["s1.jpg"], "a conferência do render achou problemas: slide 2: texto cortado") if len(renders) == 1 \
                else (["s1.jpg"], "")
        m.renderizar_molde = render
        fichas = [{"marca": "raiz", "motor": "molde", "molde": "frases", "formato": "carrossel",
                   "ficha": {"_marca": "raiz", "pergunta": q}} for q in ("Longa", "Curta")]
        chamadas = []

        def chamar(papel, tarefa, material, login="matheus"):
            chamadas.append((papel, tarefa))
            return {"texto": json.dumps(fichas.pop(0)) if papel == "designer" else APROVA, "erro": "", "imagens": [],
                    "sem_imagem": []}
        m.chamar = chamar
        d = m.desenhar("Carrossel da Raiz")
        ok(renders == ["Longa", "Curta"] and "texto cortado" in chamadas[1][1] and d["falta"] == [], (renders, d["falta"]))

    def t_previa_mostra_tela_inteira_antes_do_zoom(self):
        # 10/11, caso real: o Reel de quarta 11/11 (lanca-app, 5 telas) reprovado por "Regra do Matheus #85: nas cenas
        # das telas, o sistema não aparece inteiro com o menu visível ... na tela da cozinha, as laterais estão
        # cortadas". O Crítico só recebia o quadro do zoom. Agora cada tela vai inteira e no zoom, cada imagem descrita.
        reels = self._reels()
        m = self._e(reels=reels)
        m._pode_renderizar = lambda: ""
        nomes = []
        for i in range(1, 13):
            if 4 <= i <= 8:
                nomes.append(f"p{i:02d}-inteira.jpg")
            nomes.append(f"p{i:02d}.jpg")
        arquivos = [self.tmp / "z" / n for n in nomes]
        arquivos[0].parent.mkdir(exist_ok=True)
        for a in arquivos:
            _png(a)
        folha = self.tmp / "z" / "prev.jpg"
        _png(folha)
        m.renderizar_molde = lambda molde, formato, ficha, previa=False: (
            [str(a) for a in arquivos] + [str(folha), str(self.tmp / "z" / "narracao.m4a")], "")
        chamadas = self._designer(m, json.dumps({"marca": "raiz", "motor": "molde", "molde": "frases", "formato": "reel",
                                                 "ficha": {"_marca": "raiz", "pergunta": "Quanto sobra?"}}))
        m.desenhar("Reel da Raiz")
        julgar = chamadas[1][2]
        imgs = [Path(x).name for x in julgar["imagens"]]
        ok(len(imgs) <= m.MAX_IMAGENS and imgs[0] == "prev.jpg" and imgs[-1] == "p12.jpg", imgs)
        pares = [n for n in imgs if n.endswith("-inteira.jpg")]
        ok(len(pares) == 3 and all(imgs[imgs.index(n) + 1] == n.replace("-inteira", "") for n in pares),
           f"cada tela vai inteira logo antes do zoom dela: {imgs}")
        legendas = julgar["quadros_da_previa"]
        eq(len(legendas), len(imgs), "uma descrição por imagem")
        k = imgs.index(pares[0])
        ok("INTEIRA" in legendas[k] and "tela cortada" in legendas[k]
           and f"mostrada inteira na imagem {k + 1}" in legendas[k + 1] and "não é recorte" in legendas[k + 1], legendas)
        ok("Tela cortada de verdade" in julgar["como_ver_a_previa"] and "continua reprovando" in julgar["como_ver_a_previa"],
           "o critério de tela cortada de verdade continua")
        # without whole frames (other moldes), the old spread
        onze = [f"p{i:02d}.jpg" for i in range(1, 12)]
        eq(m._quadros_para_o_critico(onze, "prev.jpg")[-1], "p11.jpg", "sem pares, como antes")

    def t_video_da_raiz_sai_so_previa_e_narracao(self):
        # decision #39: a narrated video goes to Matheus as audio first; the video is made only after he approves
        reels = self._reels()
        esq = reels / "moldes" / "frases" / "esquema.json"
        esq.write_text(json.dumps({"formatos": ["carrossel", "reel"], "campos": {"pergunta": {"tipo": "texto", "max": 20}}}))
        m = self._e(reels=reels)
        m._pode_renderizar = lambda: ""
        quadros = [self.tmp / f"p{i:02d}.jpg" for i in (1, 2)]
        for q in quadros:
            _png(q)
        chamadas_render = []

        def render(molde, formato, ficha, previa=False):
            chamadas_render.append((formato, previa))
            return [str(quadros[0]), str(quadros[1]), str(self.tmp / "prev.jpg"), str(self.tmp / "narracao.m4a")], ""
        m.renderizar_molde = render
        chamadas = self._designer(m, json.dumps({"marca": "raiz", "motor": "molde", "molde": "frases", "formato": "reel",
                                                 "ficha": {"_marca": "raiz", "pergunta": "Quanto sobra?"}}))
        d = m.desenhar("Reel da Raiz")
        eq(chamadas_render, [("reel", True)], "vídeo: só a prévia")
        eq(d["arquivos"], [], "nenhum vídeo ainda")
        eq(d["previa"], [str(q) for q in quadros], "prévia sem a folha de contato")
        ok(d["narracao"].endswith("narracao.m4a") and d["video_pendente"], d)
        eq(chamadas[1][2]["imagens"], [str(self.tmp / "prev.jpg")] + [str(q) for q in quadros], "o Crítico julga a prévia")
        ok("zoom" in chamadas[1][2]["como_ver_a_previa"], "ele sabe que o zoom não é recorte")
        ok(m.MAX_IMAGENS >= 10, "um carrossel de até 10 slides chega inteiro ao Crítico (22/10: o 9º ficava de fora)")
        onze = [f"p{i:02d}.jpg" for i in range(1, 12)]
        vistos = m._quadros_para_o_critico(onze, "prev.jpg")
        ok(len(vistos) == m.MAX_IMAGENS and vistos[0] == "prev.jpg" and vistos[-1] == "p11.jpg" and vistos[1] == "p01.jpg",
           f"cabe no limite, com a folha e a última cena: {vistos}")
        ok("carrossel_raiz" not in m.KIT and '"motor": "molde"' in m.KIT, "o Designer só vê o motor que roda aqui")
        # 27/10: the Raiz launches nothing: lanca-app goes without its "Lançamento" badge unless the ficha names one
        fichas = []
        m._validar_ficha = lambda molde, ficha: []
        m.renderizar_molde = lambda molde, formato, ficha, previa=False: fichas.append(dict(ficha)) or (
            [str(quadros[0]), str(self.tmp / "narracao.m4a")], "")
        for ficha in ({"_marca": "raiz"}, {"_marca": "raiz", "selo": "Novo painel"}):
            m._renderizar({"marca": "raiz", "motor": "molde", "molde": "lanca-app", "formato": "reel", "ficha": ficha}, [])
        m._renderizar({"marca": "nexos", "motor": "molde", "molde": "lanca-app", "formato": "reel", "ficha": {}}, [])
        eq([f.get("selo", "(padrão)") for f in fichas], ["", "Novo painel", "(padrão)"], "selo vazio só na Raiz sem selo")
        ok("rótulo do menu" in m.PAPEIS["critico"], "o menu da tela real não é jargão da peça")

    def t_renderizar_molde_chama_o_motor(self):
        import os
        reels = self._reels()
        m = self._e(reels=reels)
        saida = Path(tempfile.mkdtemp(dir=self.tmp))
        os.environ["ESPECIALISTAS_SAIDA"] = str(saida)
        cmds = []

        envs = []

        def run(cmd, **kw):
            cmds.append(cmd)
            envs.append(kw.get("env") or {})
            destino = Path(cmd[cmd.index("--saida") + 1])
            for nome in ("slide1.jpg", "slide10.jpg", "slide2.jpg", "prev.jpg"):
                (destino / nome).write_bytes(b"x")
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")
        m.subprocess = types.SimpleNamespace(run=run)
        try:
            arquivos, problema = m.renderizar_molde("frases", "carrossel", {"pergunta": "Oi"})
        finally:
            os.environ.pop("ESPECIALISTAS_SAIDA", None)
        eq(problema, "", "sem problema")
        eq([Path(a).name for a in arquivos], ["slide1.jpg", "slide2.jpg", "slide10.jpg"], "slides na ordem, sem a folha")
        ok(envs[0]["AWS_PROFILE"] == "voz" and "/voz" in Path(envs[0]["AWS_CONFIG_FILE"]).read_text(),
           "a voz usa só a credencial curta do host")
        # 27/10: the Hermes's Bedrock endpoint (our proxy) and its fake keys never reach the voice
        os.environ.update(AWS_ENDPOINT_URL_BEDROCK_RUNTIME="http://host.docker.internal:8787/hermes/bedrock",
                          AWS_ACCESS_KEY_ID="falsa", AWS_SECRET_ACCESS_KEY="falsa")
        try:
            env = m.ambiente_render(saida)
        finally:
            for k in ("AWS_ENDPOINT_URL_BEDROCK_RUNTIME", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
                os.environ.pop(k, None)
        ok(not {"AWS_ENDPOINT_URL_BEDROCK_RUNTIME", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"} & set(env)
           and env["AWS_PROFILE"] == "voz", "a voz não herda o endpoint do proxy nem as chaves falsas")
        eq(env["TMPDIR"], "/tmp", "12/11: o render (Chromium) não usa o TMPDIR de rascunho do Hermes, onde travava")
        ok(cmds[0][1].endswith("moldes/motor/render.py") and cmds[0][2] == "frases", cmds[0])
        ficha = Path(cmds[0][3])
        eq(json.loads(ficha.read_text()), {"pergunta": "Oi"}, "a ficha vai em arquivo")
        m.subprocess = types.SimpleNamespace(run=lambda cmd, **kw: types.SimpleNamespace(returncode=2, stdout="",
                                                                                         stderr="prazo vencido"))
        arquivos, problema = m.renderizar_molde("frases", "carrossel", {})
        ok(arquivos == [] and "recusou a ficha" in problema and "prazo vencido" in problema, problema)
        fala = "Na cozinha, aparecem identificados com o selo iFood, ao lado de um pedido de mesa, com o tempo de cada um."
        rastro = ("Traceback (most recent call last):\n" + "  File \"render.py\", line 9, in x\n" * 40
                  + f"RuntimeError: a voz carolina não leu a fala certa depois de 3 tentativas: {fala!r} (ouvido: {fala * 2!r})\n")
        m.subprocess = types.SimpleNamespace(run=lambda cmd, **kw: types.SimpleNamespace(returncode=1, stdout="", stderr=rastro))
        arquivos, problema = m.renderizar_molde("frases", "carrossel", {})
        ok(f"RuntimeError: a voz carolina não leu a fala certa depois de 3 tentativas: {fala!r}" in problema,
           f"o erro sai do começo, com a fala que falhou (27/10: o fim do rastro cortava a fala): {problema}")
        # 12/11: a preview hung for the 15 minutes of the finished video; a carousel or a preview gets the short limit
        tempos = []
        m.subprocess = types.SimpleNamespace(run=lambda cmd, **kw: tempos.append(kw.get("timeout")) or run(cmd, **kw))
        os.environ["ESPECIALISTAS_SAIDA"] = str(saida)
        try:
            m.renderizar_molde("frases", "carrossel", {})
            m.renderizar_molde("frases", "reel", {}, previa=True)
            m.renderizar_molde("frases", "reel", {})
        finally:
            os.environ.pop("ESPECIALISTAS_SAIDA", None)
        eq(tempos, [m.RENDER_CURTO, m.RENDER_CURTO, m.RENDER_VIDEO], "limite do render: curto na prévia e no carrossel")
        ok(m.RENDER_CURTO <= 300, "a prévia não espera mais de 5 minutos")

    # --- the tool

    def _ferramenta(self):
        stubs = {"helpers": types.ModuleType("helpers"), "helpers.tool": types.ModuleType("helpers.tool")}
        stubs["helpers.tool"].Tool = type("Tool", (), {"__init__": lambda s: None})
        stubs["helpers.tool"].Response = type("Response", (), {"__init__": lambda s, **kw: s.__dict__.update(kw)})
        return _carregar("especialistas_ferramenta_teste", RAIZ / "tools" / "especialista.py", stubs)

    async def t_ferramenta_liga_acao_ao_papel(self):
        f = self._ferramenta()
        feitos = []
        falso = types.SimpleNamespace(
            criticar=lambda tipo, material, login="matheus": feitos.append(("criticar", tipo, material)) or
            {"veredito": "reprova", "motivos": ["manchete genérica"], "sugestoes": ["diga o número"],
             "avisos": ["sem critérios do AR Board para landing"]},
            desenhar=lambda briefing, login="matheus": feitos.append(("desenhar", briefing)) or
            {"spec": {"motor": "carrossel_raiz"}, "arquivos": [], "falta": ["render no repositório"], "render": "cmd",
             "critica": {"veredito": "aprova", "motivos": [], "sugestoes": []}})
        f.esp = lambda: falso
        e = f.Especialista()
        r = await e.execute(acao="criticar", tipo="landing", material='{"titulo": "Preço certo", "imagens": []}')
        eq(feitos[0], ("criticar", "landing", {"titulo": "Preço certo", "imagens": []}), "JSON vira dict")
        ok(r.message.startswith("REPROVADO") and "manchete genérica" in r.message and "diga o número" in r.message,
           r.message)
        ok("Julgado sem" in r.message, "avisa o que faltou")
        r = await e.execute(acao="desenhar", briefing="Carrossel do prato campeão")
        eq(feitos[1], ("desenhar", "Carrossel do prato campeão"), "briefing")
        ok("carrossel_raiz" in r.message and "APROVADO" in r.message and "render no repositório" in r.message, r.message)
        r = await e.execute(acao="desenhar", papel="critico", briefing="x")
        ok("é do papel designer" in r.message, r.message)
        r = await e.execute(acao="publicar")
        ok("acao desconhecida" in r.message, r.message)
        r = await e.execute(acao="criticar", tipo="post")
        ok("Mande o `material`" in r.message, r.message)
        eq(len(feitos), 2, "nada chamado nos erros")

        def quebra(*a, **k):
            raise RuntimeError("x")
        f.esp = lambda: types.SimpleNamespace(criticar=quebra)
        r = await e.execute(acao="criticar", material="x")
        ok("Não publique sem crítica" in r.message, r.message)

    def t_manual_e_indice(self):
        manual = (RAIZ / "prompts" / "agent.system.tool.especialista.md").read_text(encoding="utf-8")
        for termo in ("Antes de publicar", "O Matheus não fala com eles", "criticar", "desenhar", "Reprovado não sai",
                      "Input schema for tool_args"):
            ok(termo in manual, f"manual cita {termo!r}")
        indice = RAIZ.parent / "prompt_enxuto" / "helpers" / "indice.py"
        if indice.exists():
            i = _carregar("especialistas_indice_teste", indice)
            ok("especialista" in i.CURTAS, "o índice curto tem a ferramenta")
            ok(len(i.CURTAS["especialista"]) <= 420, "linha curta até 420")

    async def rodar(self, so=""):
        for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
            try:
                feito = getattr(self, nome)()
                if asyncio.iscoroutine(feito):
                    await feito
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
