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
        eq(sorted(m.PAPEIS), ["critico", "designer"], "os dois papéis")
        for papel, soul in m.PAPEIS.items():
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
        d = m.desenhar("Carrossel da Raiz")
        ok(sum(p == "designer" for p, _ in chamadas) == m.CORRECOES + 1 and "ficha: pergunta: longo" in d["falta"], d["falta"])

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
        ok("a vaga da semana é 'carrossel'" in chamadas[1][1], chamadas[1][1][:200])
        eq((d["spec"]["formato"], d["falta"]), ("carrossel", []), "corrigido para carrossel")

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
        ok(cmds[0][1].endswith("moldes/motor/render.py") and cmds[0][2] == "frases", cmds[0])
        ficha = Path(cmds[0][3])
        eq(json.loads(ficha.read_text()), {"pergunta": "Oi"}, "a ficha vai em arquivo")
        m.subprocess = types.SimpleNamespace(run=lambda cmd, **kw: types.SimpleNamespace(returncode=2, stdout="",
                                                                                         stderr="prazo vencido"))
        arquivos, problema = m.renderizar_molde("frases", "carrossel", {})
        ok(arquivos == [] and "recusou a ficha" in problema and "prazo vencido" in problema, problema)
        rastro = ("Traceback (most recent call last):\n" + "  File \"render.py\", line 9, in x\n" * 40
                  + "RuntimeError: a voz carolina não leu a fala certa depois de 3 tentativas: 'Oi' (ouvido: 'erro')\n")
        m.subprocess = types.SimpleNamespace(run=lambda cmd, **kw: types.SimpleNamespace(returncode=1, stdout="", stderr=rastro))
        arquivos, problema = m.renderizar_molde("frases", "carrossel", {})
        ok(problema.endswith("RuntimeError: a voz carolina não leu a fala certa depois de 3 tentativas: 'Oi' (ouvido: 'erro')"),
           f"o erro sai inteiro, não o fim do rastro: {problema}")

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
