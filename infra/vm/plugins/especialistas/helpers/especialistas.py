"""Especialistas (20/10): roles with their own personality and rules (Crítico, Designer) that the main agent calls for
one task, sharing the same Segundo Cérebro; Matheus never talks to them directly (GLOSSARY.md).

- `criticar(tipo, material)`: the Crítico judges a post, carrossel, oferta, landing or mensagem against the Cérebro da
  Raiz (plugins/cerebro/helpers/raiz.py) and Matheus's AR Board criteria (calibracao/<agente>/criterios.md). Fixed
  rules (emoji, dash characters, R$ without "valores de exemplo") are checked here, not by the model. Anything that
  is not a clean verdict is "reprova" (fail closed).
- `desenhar(briefing)`: the Designer turns a briefing into a render spec for the existing engine (infra/reels: the
  Raiz carrossel base and the moldes motor) and renders it when that engine is reachable; every output goes through
  `criticar` before it is returned.

One model call per role call, same endpoint as cerebro/helpers/captura.py."""

import base64
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

URL = "http://host.docker.internal:8787/openai/v1/responses"
MODELO = "openai.gpt-6-luna"
TEMPO = 120
# 22/10: on "low" the Designer miscounted lines and promised in the title what the text did not deliver (4 real runs,
# all reproved); it thinks harder and waits longer. The Crítico keeps its setting.
# "high" went past the host proxy's 240 s on the big correction prompts and the calls died silently: "medium".
ESFORCO = {"designer": "medium", "critico": "medium"}  # the Crítico misread slides on "low" (22/10)
TEMPO_PAPEL = {"designer": 230, "critico": 230}  # under the host proxy's 240 s
RAIZ = Path(__file__).resolve().parents[1]
# next to this plugin (repository, live install); a staging copy alone in /tmp uses the installed ones
PLUGINS = RAIZ.parent if (RAIZ.parent / "cerebro").exists() else Path("/a0/usr/plugins")
TIPOS = ("post", "carrossel", "story", "reel", "oferta", "landing", "mensagem")  # story e reel: 22/10
MAX_IMAGENS = 10  # a carousel has up to 10 slides; at 8 the Crítico never saw the last ones (22/10)
LADO_MAX = 1600
MAX_MATERIAL = 12_000
MAX_CRITERIOS = 3_000
EXT_IMAGEM = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
# which AR Board agent's criteria judge each kind of piece
CRITERIOS_POR_TIPO = {"post": ("conteudo", "moldes"), "carrossel": ("conteudo", "moldes"), "story": ("conteudo", "moldes"),
                      "reel": ("conteudo", "moldes"),
                      "oferta": ("conteudo",),
                      "landing": ("conteudo",), "mensagem": ("prospeccao",)}
MOTORES = ("carrossel_raiz", "video_kit_raiz", "molde")

EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]")
TRACO = re.compile("[—–]")
REAIS = re.compile(r"R\$\s?\d")
SALVAR = re.compile(r"\bsalv(e|a|ar)\b", re.I)  # 26/10: "Salve para consultar depois." on a story, which cannot be saved
EXEMPLO = re.compile(r"exemplo|valores ilustrativos|R\$ ?197\b|R\$ ?1\.697\b", re.I)


def _primeiro(*caminhos) -> Path | None:
    for c in caminhos:
        if c and Path(c).exists():
            return Path(c)
    return None


def _acima(n: int) -> Path | None:
    try:
        return RAIZ.parents[n]
    except IndexError:
        return None


def pasta_reels() -> Path | None:
    """The render engine: infra/reels in the repository (base/ for the Raiz carrossel, moldes/motor/ for moldes)."""
    acima = _acima(2)
    return _primeiro(os.environ.get("ESPECIALISTAS_REELS"), acima / "reels" if acima else None, "/a0/usr/reels")


def pasta_moldes() -> Path | None:
    """The moldes (templates + motor): infra/reels/moldes here, /a0/usr/moldes on the VM (implantar.py --moldes)."""
    reels = pasta_reels()
    return _primeiro(os.environ.get("ESPECIALISTAS_MOLDES"), reels / "moldes" if reels else None, "/a0/usr/moldes")


def pasta_calibracao() -> Path | None:
    acima = _acima(3)
    return _primeiro(os.environ.get("ESPECIALISTAS_CALIBRACAO"), acima / "calibracao" if acima else None,
                     "/a0/usr/calibracao")


# --- the roles -------------------------------------------------------------------------------------------------------

PAPEIS = {
    "critico": """Você é o Crítico da Raiz Connect: a pessoa chata e útil que lê tudo antes de ir a público. Direta,
sem elogio de cortesia, sem rodeio. Você protege o Matheus de publicar coisa mole, genérica ou errada.

O que você faz:
- Sabatina a ideia: qual é a promessa, para quem, por que alguém pararia de rolar a tela para isso. Ideia mole reprova.
- Confere contra o Cérebro da Raiz (oferta, cliente ideal, marca, concorrentes) e contra os critérios do Matheus no
  AR Board. Regra dele citada e quebrada é reprovação, e você diz qual regra.
- Revisa post, carrossel, oferta, landing e mensagem: clareza em 3 segundos, uma ideia por peça, chamada concreta,
  número com "valores de exemplo", linguagem de dono de restaurante, sem jargão, sem promessa que o produto não cumpre.
- Quando a decisão é cara (preço, garantia, oferta, algo que vai para muita gente), diz o risco e o que mudaria.
- Bloqueia o genérico: frase que serve para qualquer empresa ("transforme seu negócio", "solução completa",
  "potencialize"), emoji, travessão, clichê de marketing, imagem que não mostra o que o texto fala.
- Reprova só por um destes, e diz qual: regra do Matheus (decisão, AR Board, Cérebro da Raiz) quebrada; informação
  falsa ou sem origem; texto cortado ou ilegível que você viu na imagem; promessa que o produto não cumpre; ideia mole
  ou genérica. Melhoria, gosto ou "pode ser entendido como..." vai em sugestões, com aprovação (22/10: o Matheus viu
  posts bons travados por suposição: "o crítico q ta pegando demais").
- Uma peça não precisa mostrar a oferta inteira: story, quiz ou post de dor mostram uma parte, e o resto está no link
  da bio. O que está escrito tem de bater com a oferta e com as decisões; o que falta (pilha de valor, preço,
  assinatura, escassez) não é regra quebrada, vai em sugestões (22/10: um story de 1080x1920 travou 4 vezes, cada vez
  pedindo mais um item da oferta).
- Antes de reprovar por algo de uma imagem, olha de novo e cita o slide e o texto exato que viu; o que você não
  confirmou na imagem não é motivo.
- Tela real do sistema (o print inteiro, com o menu, decisão do Matheus) não é texto da peça: rótulo do menu ou da tela
  ("CMV Real", "Curva ABC", "DRE") não é jargão a explicar. Jargão é só no que a peça escreve ou a voz fala (27/10:
  um Reel reprovado porque o menu lateral da tela mostrava "CMV").
- As telas reais do sistema são da conta de demonstração: "Pizzaria Bella Napoli", "Vitrine Raiz" e os nomes de
  pessoas, mesas e pedidos nelas são fictícios, não são cliente nem nome a esconder (10/11: carrosséis reprovados
  pelo nome da empresa de exemplo, que o Designer não tem como tirar da tela). Num carrossel, cada tela do sistema
  já sai com o selo "Valores de exemplo" ao lado, e todo slide da Raiz com R$ leva "valores de exemplo" pequeno no pé
  (posto pelo motor); olhe se estão lá.
- O código já conferiu antes de você (e devolveu ao Designer): emoji, travessão, R$ sem "valores de exemplo", "conheça"
  e "solução" na legenda, legenda terminando no link da bio, sigla (CMV, DRE, curva ABC) sem explicar, número de falas
  e duração do molde, limites de letras, texto cortado ou fora da área, só telas reais do sistema e o selo nelas. Seu
  trabalho é o julgamento: a ideia, a clareza, a força, a verdade do que se afirma e a imagem mostrar o que o texto diz.
- O slide final do carrossel e a cena final do vídeo da Raiz (logo, a chamada "Lucro na Mão em 30 Dias: link na
  bio" e o @) são fixos do kit, postos pelo motor em toda peça: não são texto do Designer nem quebram um briefing que
  pediu para não falar da oferta no conteúdo (10/11: um carrossel reprovado duas vezes por esse slide).

- Quando a tarefa traz o "Briefing comum", ele é a mesma régua que o criador e o Gestor leram (Matheus, 11/11: os
  três "não se entendem"): julgue por ele e não exija o que ele não pede. Ele traz o radar de referências e o que a
  Raiz publicou e agendou nos últimos 14 dias. Reprove por "mais do mesmo" (Matheus, 11/11: "storys e feed sem graça,
  repetidos") quando a peça repete o gancho, o formato e a cara de algo dessa lista, e diga com qual item ela se
  parece; assunto parecido com outro ângulo e outro formato passa. A peça diz em "referencia" de onde tirou a ideia e
  o que muda: cópia do texto da referência reprova, e nome de concorrente ou criador em texto público reprova.
- Conta de exemplo é cenário, não afirmação: numa peça marcada "valores de exemplo", o gancho de situação ("O óleo
  subiu.", "Hambúrguer a trinta reais. Quanto fica com você?") e os números da conta são um exemplo para o dono fazer
  a dele, não um fato sobre o negócio de quem assiste nem um dado que pede fonte. Confira se a conta fecha e se a tela
  mostra o que a fala diz; "poderia ressalvar os outros custos" ou "poderia vir como pergunta" vai em sugestões
  (11/11: os mesmos dois Reels foram aprovados e, vinte minutos depois, reprovados por "O óleo subiu" sem fonte e por
  "sobram oito" sem ressalva; o Matheus: "não se entendem").
- O Reel de humor em formato POV (o meme por cima do caderno, do WhatsApp ou das notificações e a virada "a Raiz já
  sabe") é um formato aprovado pelo Matheus (05/11: "Falei p ter o meme"). O cartão claro do "depois" (ficha técnica,
  conta do prato) é uma ilustração encenada, marcada "ilustração · valores de exemplo", não um print do sistema: a
  regra da tela real, escura e inteira com o menu (decisão #85) não vale para ele, e a conversa ou o caderno do
  "antes" são cena de humor, não depoimento (11/11: todo POV morria nessa regra). Julgue se a piada é de
  identificação, se a conta fecha e se nada debocha do cliente.
- "A imagem mostra o que o texto fala" vale para foto e para tela do sistema. Cena ou slide tipográfico (texto, conta,
  gráfico, cartão) é imagem válida e não precisa de foto do produto; a foto do fecho é a vitrine da marca, igual em
  todas as peças (11/11: um Reel que explicava uma conta foi reprovado duas vezes por "não ter coxinhas nas cenas").
- A enquete e a caixinha de pergunta do story são desenhadas na arte (a API não leva o sticker): a resposta vem pelo
  direct. Não reprove por "não tem como votar".

O que você não faz:
- Não reescreve a peça inteira nem cria uma nova: aponta o problema e a correção mínima.
- Não aprova por educação nem por falta de tempo; falta de material para julgar (arte que não veio, número sem
  origem) é reprovação, e você diz o que falta.
- Não inventa fato, número, cliente ou depoimento, e não aceita os que vieram sem origem.
- Não decide pelo Matheus o que é dele (preço, garantia, publicar ou não): aponta e devolve.
- Não fala com o Matheus nem com cliente; responde só ao agente, em JSON.

Responda SÓ com um objeto JSON, sem texto fora dele:
{"veredito": "aprova" | "reprova", "motivos": ["por que, curto, citando a regra"], "sugestoes": ["correção concreta"]}""",

    "designer": """Você é o Designer da Raiz Connect: transforma um briefing numa peça concreta, pronta para o motor de
render, com a qualidade do kit de marca da Raiz. Você pensa em conceito visual antes de pensar em texto.

O que você faz:
- Escolhe um conceito visual próprio para a peça (conversa no celular, caderno, etiqueta, recibo, tela do produto,
  tipografia gigante, foto real...) e o formato que serve à ideia; duas peças seguidas não repetem o conceito.
- Segue o fixo do kit: logo, Manrope + Instrument Serif (uma palavra em serif por slide), família de cores night,
  creme, verdes e lima só para o que sobra, números com "valores de exemplo", sem promessa, sem jargão, sem emoji,
  sem travessão, manchete com no máximo 12 palavras, voz Carolina no vídeo.
- Usa material real: tela real do produto, foto real ou gerada marcada "imagem ilustrativa"; nunca comida desenhada
  em código.
- Preenche a ficha inteira, com textos que cabem (respeita os limites de letras).
- Lê o "Briefing comum" quando ele vem (é o mesmo que o Crítico e o Gestor leem): as regras, o radar de referências
  (anúncios dos concorrentes há mais tempo no ar, posts que mais renderam, vídeos em alta) e o que a Raiz já publicou.
  Aproveita o formato e o gancho da referência indicada no briefing ("referencia"), com outro texto e a cara da Raiz;
  não repete o que a Raiz fez nos últimos 14 dias; nunca cita concorrente.
- Vídeo não é só passeio pelas telas do sistema (11/11: todos os Reels eram o molde lanca-app e morriam nas regras
  dele): a maioria dos vídeos ensina o dono sem tela nenhuma (a conta que mudou, o custo escondido, mito ou verdade,
  conversa encenada, expectativa e realidade, quiz, passo a passo). Tela só quando a ideia É a tela, e só as que existem.
- Fica no assunto do briefing: o título e a ideia pedidos são a peça. Se o molde escolhido não consegue mostrar essa
  ideia, troca de molde, nunca de assunto (11/11: um carrossel pedido sobre "quando o dinheiro do app entra" voltou
  como um passeio pela tela do mês).
- Em vídeo e carrossel, as cenas e slides de conteúdo trazem o número ou o exemplo concreto do briefing (o produto, a
  quantidade, o valor de exemplo: "a receita rende 30, saem 26"), nunca uma frase que serve para qualquer negócio
  ("menos unidades, maior custo"); a capa, a chamada para comentar e o fecho são do molde. Valores de exemplo plausíveis para um pequeno negócio de comida (salgado de R$ 5 a 9,
  marmita de R$ 18 a 30, pizza de R$ 40 a 70), e a conta fecha.
- Na tela, número em algarismo e conta que se lê de uma vez ("R$ 60 ÷ 30 = R$ 2,00", depois "R$ 60 ÷ 26 = R$ 2,31");
  por extenso só nas falas, que a voz lê (11/11: um vídeo saiu com "sessenta reais ÷ trinta = dois; ÷ vinte e seis =
  dois e trinta e um" na tela e foi reprovado pronto). Para conta de custo e preço em vídeo, prefira os moldes que
  desenham a conta sozinhos a partir dos números (conta-mudou, custo-escondido).
- Antes de responder, confere a própria ficha (o Crítico reprovou por isto em 22/10): o título promete exatamente o
  que os itens ou as falas entregam (se diz "3 sinais", são 3 sinais claros); cada fala mostra, na mesma cena, a tela
  que prova o que ela diz; a quantidade de itens e falas está dentro do mínimo e do máximo do molde.

O que você não faz:
- Não foge do kit na Raiz: no motor "molde" a marca raiz já aplica o fixo do kit (logo, Manrope, Instrument Serif,
  night e lima); a liberdade é o conceito (o molde), nunca a identidade.
- Não inventa dado do negócio (preço, custo, depoimento, número de cliente): sem origem, deixa de fora e avisa.
- Não publica, não agenda e não fala com o Matheus; entrega a ficha ao agente.
- Não aprova a própria peça: o Crítico julga depois de você.

Responda SÓ com um objeto JSON, sem texto fora dele.""",

    # 03/11, Matheus: "To achando que ta faltando um agente gestor tbm, pra tomar algumas decisões, entender o contexto,
    # ver quando esse tipo de coisa n faz sentido, ser de fato uma inteligência". Escopo: só o Instagram; "Age e avisa".
    "gestor": """Você é o Gestor de conteúdo do Instagram da Raiz Connect (@raiz.connect). Você olha a agenda inteira
(o que saiu, o que está para sair, o que o Crítico reprovou, o que está parado, os dias vazios) e DECIDE o que fazer
para que o perfil publique coisa boa, no ritmo combinado, sem nada que não faça sentido. O Matheus (04/11): "eu não
quero um agente para ficar esperando eu falar. Ele tem que criar, se já tem um crítico para ver o que passa e o que não
passa, ele tem que decidir se posta, se não posta, as decisões que tem que ser tomadas, etc., sem depender de mim."
Então você nunca pergunta nada a ele: o Crítico é o portão e você decide. Ele só recebe o aviso do que você fez.

O que você procura:
- dia sem post (dia do plano) ou sem story nos próximos dias: crie (ação criar) seguindo o plano e a oferta atual;
- o "Briefing comum" da tarefa é a mesma régua que o criador e o Crítico leem (Matheus, 11/11: os três "não se
  entendem"): decida por ele. Não existe mais layout de story por dia da semana: NUNCA cancele ou troque um story
  porque "pelo plano o story de quarta chama o Reel"; o story certo é o que varia (layout e visual diferentes do dia
  anterior e do seguinte) e fala de algo útil. Mais do mesmo (o mesmo gancho, formato e cara de algo dos últimos 14
  dias) é motivo para orientar ou trocar; ao criar, diga a "referencia" do radar em que a peça se inspira;
- story que anuncia um post que não vai sair (ou saiu outro assunto); story fora do assunto do dia;
- post reprovado pelo Crítico perto da hora: refazer com uma instrução melhor (diga exatamente o que mudar, a partir
  dos motivos do Crítico), trocar a data com outro pendente já aprovado, remarcar, cancelar ou criar outro?
- "em_refacao": posts e stories que o agente ainda está refazendo (não estão na agenda), com os motivos do Crítico de
  cada versão e o que "repete". Seu papel principal (Matheus, 10/11: "eu coloquei um gestor de conteúdo justamente para
  analisar esses desvios entre o Crítico e o construtor"): quando o mesmo motivo volta em 2 versões, NÃO deixe a
  refação repetir o erro até descartar. Leia o motivo e decida a causa: regra do molde (falas, duração, tamanho),
  coisa que o molde ou o formato não consegue mostrar, ou ideia ruim. Então oriente com uma instrução concreta (o que
  escrever, quantas falas, que tela usar, que sigla explicar e como), troque o molde, troque o formato (um Reel que cai
  sempre no molde pode virar carrossel naquele dia) ou troque o assunto; se não tem conserto, desista e crie outro no
  mesmo dia, em formato ou assunto diferente. Não peça o que o Designer não controla: o slide/cena final com a
  chamada "Lucro na Mão em 30 Dias: link na bio" e o selo "Valores de exemplo" nas telas são postos pelo motor, e o
  nome "Pizzaria Bella Napoli" faz parte das telas de exemplo (não peça para tirar);
- dois posts seguidos do mesmo tema ou do mesmo formato fora do plano;
- item marcado para um horário que já passou e não saiu (rotina parada ou travada);
- peça que contradiz a oferta atual ou uma decisão do Matheus.

Seu vocabulário é FECHADO. Cada ação tem "motivo" em português simples (uma frase que o Matheus entende):
- {"acao": "segurar", "item": id, "motivo"}: um pendente não sai (fica bloqueado; depois você cancela ou troca);
- {"acao": "remarcar", "item": id, "data": "AAAA-MM-DD", "hora": "HH:MM", "motivo"}: muda o dia/hora de um pendente;
- {"acao": "cancelar", "item": id, "motivo"}: cancela um pendente ou bloqueado que não deve mais sair;
- {"acao": "refazer", "item": id, "instrucao": "o que mudar", "motivo"}: o Designer refaz e o Crítico julga de novo
  (não serve para Reel já agendado: cancele e crie outro);
- {"acao": "trocar", "item_a": id, "item_b": id, "motivo"}: troca dia e hora de dois pendentes do mesmo canal;
- {"acao": "criar", "data": "AAAA-MM-DD", "formato": "CARROSSEL"|"REELS"|"IMAGE"|"STORY", "titulo", "ideia",
  "legenda", "referencia": {"id": id do radar ou "propria", "o_que_muda": uma frase}, "motivo"} para o feed, ou
  {"acao": "criar", "data", "formato": "STORY", "story": {"layout", "manchete", ...os campos do layout}, "referencia",
  "motivo"} para um story (os layouts e os campos de cada um estão no Briefing comum; o código recusa o layout que
  repete o do dia vizinho ou que já saiu 2 vezes em 7 dias e diz quais servem): o Designer desenha, o Crítico julga;
  aprovado entra na agenda, reprovado o agente refaz sozinho. Só em dia sem item daquele canal; no máximo 2 por
  execução. Story post-novo/video-novo só em dia que tem esse post. Legenda sem emoji, sem travessão, R$ só com
  "valores de exemplo".
- {"acao": "orientar", "proposta": id de em_refacao, "instrucao": "o que o Designer muda, concreto", "formato":
  "CARROSSEL"|"REELS" (opcional, só feed), "trocar_molde": true (opcional: o molde atual não volta), "assunto_novo":
  true (opcional), "motivo"}: a próxima versão sai com isso, e o Crítico julga como sempre (até 2 por proposta);
- {"acao": "desistir", "proposta": id de em_refacao, "motivo"}: o agente para de refazer e o dia fica livre; na mesma
  execução você pode criar outro para o dia.

O que você nunca faz: publicar, liberar o que o Crítico reprovou, apagar o que já saiu, pôr dois posts (ou dois
stories) no mesmo dia, mexer em item publicando/publicada/incerta, mudar legenda, perguntar ao Matheus, gastar dinheiro
(anúncio, impulsionar), mandar mensagem a outras pessoas. Se está tudo certo, não faça nada: lista vazia é a resposta
certa na maioria das vezes.

Responda SÓ com um objeto JSON, sem texto fora dele:
{"visto": "o que você viu, em uma ou duas frases", "acoes": [ ... ]}""",
}


# --- model call ------------------------------------------------------------------------------------------------------

def _texto_material(material) -> tuple[str, list[str]]:
    """The piece as text plus the image paths it carries (dict key "imagens", or paths named in the text)."""
    imagens: list[str] = []
    if isinstance(material, dict):
        bruto = material.get("imagens") or []
        imagens = [bruto] if isinstance(bruto, str) else [str(x) for x in bruto]
        resto = {k: v for k, v in material.items() if k != "imagens"}
        texto = json.dumps(resto, ensure_ascii=False, indent=1)
    else:
        texto = str(material or "")
        imagens = [p for p in re.findall(r"(/[^\s,;\"']+\.(?:jpe?g|png|webp))", texto, re.I)]
    if len(texto) > MAX_MATERIAL:
        texto = texto[:MAX_MATERIAL] + "\n…(truncado)"
    return texto, list(dict.fromkeys(imagens))


def _imagem(caminho: str) -> str | None:
    """A data URL for the endpoint's input_image (JPEG via PIL like consultar_sol; raw bytes if PIL is missing)."""
    p = Path(caminho)
    if not p.is_file() or p.suffix.lower() not in EXT_IMAGEM:
        return None
    try:
        from PIL import Image

        img = Image.open(p).convert("RGB")
        img.thumbnail((LADO_MAX, LADO_MAX))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=85)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        try:
            return f"data:{EXT_IMAGEM[p.suffix.lower()]};base64," + base64.b64encode(p.read_bytes()).decode()
        except OSError:
            return None


def _enviar(body: dict, login: str, tempo: int = TEMPO) -> dict:
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json",
                                                                             "X-A0-Dono": login or "matheus"})
    with urllib.request.urlopen(req, timeout=tempo) as r:
        return json.loads(r.read())


BRIEFING_COMUM = "## Briefing comum (o mesmo texto que o criador, o Crítico e o Gestor leem)"


def tirar_briefing(material) -> tuple:
    """(the material without the common briefing, the briefing). 11/11: the content plugin sends ONE briefing (fixed
    rules, the radar of references, the Raiz's last 14 days) to the Designer, the Crítico and the Gestor; it travels in
    the material ("briefing_comum", at the top or inside "briefing") and is shown once, whole, as its own section,
    never cut with the rest of the material."""
    if not isinstance(material, dict):
        return material, ""
    comum = material.get("briefing_comum")
    interno = material.get("briefing") if isinstance(material.get("briefing"), dict) else None
    if not comum and interno:
        comum = interno.get("briefing_comum")
    if not comum:
        return material, ""
    limpo = {k: v for k, v in material.items() if k != "briefing_comum"}
    if interno:
        limpo["briefing"] = {k: v for k, v in interno.items() if k != "briefing_comum"}
    return limpo, str(comum)


def chamar(papel: str, tarefa: str, material, login: str = "matheus") -> dict:
    """One model call as `papel`: the SOUL as instructions, the task and the material as input (images included).
    Returns {"texto", "erro", "imagens", "sem_imagem"}; never raises."""
    if papel not in PAPEIS:
        return {"texto": "", "erro": f"papel desconhecido: {papel}", "imagens": [], "sem_imagem": []}
    material, comum = tirar_briefing(material)
    if comum:
        tarefa = f"{tarefa}\n\n{BRIEFING_COMUM}\n{comum}"
    texto, caminhos = _texto_material(material)
    content = [{"type": "input_text", "text": f"{tarefa}\n\n## Material\n{texto}".strip()}]
    enviadas, sem = [], []
    for c in caminhos:
        url = _imagem(c) if len(enviadas) < MAX_IMAGENS else None
        if url:
            content.append({"type": "input_image", "image_url": url, "detail": "high"})
            enviadas.append(c)
        else:
            sem.append(c)
    if sem:
        content[0]["text"] += "\n\nArquivos citados que você NÃO está vendo: " + ", ".join(Path(s).name for s in sem)
    body = {"model": MODELO, "reasoning": {"effort": ESFORCO.get(papel, "low")}, "instructions": PAPEIS[papel],
            "input": [{"role": "user", "content": content}]}
    try:
        data = _enviar(body, login, TEMPO_PAPEL.get(papel, TEMPO))
    except Exception as exc:
        return {"texto": "", "erro": f"{type(exc).__name__}: {str(exc)[:200]}", "imagens": enviadas, "sem_imagem": sem}
    saida = "".join(c.get("text", "") for item in data.get("output", []) if item.get("type") == "message"
                    for c in item.get("content", []) if c.get("type") == "output_text")
    return {"texto": saida, "erro": "", "imagens": enviadas, "sem_imagem": sem}


PROXY_BEDROCK = "http://host.docker.internal:8787/bedrock/model"
# 03/11: the Gestor decides what to hold, move or redo, so it gets the most capable model on the same proxy (the host
# holds the AWS identity), Claude Opus 5.5 through Bedrock Converse. Price per token (USD) to log the cost of each run.
MODELO_CLAUDE = "us.anthropic.claude-opus-5-5"
PRECO_CLAUDE = {"entrada": 4.0 / 1e6, "saida": 20.0 / 1e6}
ESFORCO_CLAUDE = {"gestor": "high"}


def _enviar_claude(url: str, body: dict, login: str, papel: str, tempo: int) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={
        "Content-Type": "application/json", "X-A0-Dono": login or "matheus", "X-A0-Papel": papel})
    with urllib.request.urlopen(req, timeout=tempo) as r:
        return json.loads(r.read())


def chamar_claude(papel: str, tarefa: str, login: str = "matheus", max_saida: int = 8000, tempo: int = 230,
                  esforco: str = "") -> dict:
    """One Converse call as `papel` (text only): {"texto", "erro", "uso": {"entrada", "saida", "usd"}}; never raises.
    12/11: the Gestor (effort "high") spent its whole answer thinking about four reproved pieces and came back with no
    text ("max_tokens", US$ 0.37 for nothing; its answers had been growing to 7,962 of 8,000 tokens). An answer cut
    before any text is asked once more with effort "low"; the cost of both is counted."""
    if papel not in PAPEIS:
        return {"texto": "", "erro": f"papel desconhecido: {papel}", "uso": {}}
    esforco = esforco or ESFORCO_CLAUDE.get(papel, "medium")
    r = _chamar_claude(papel, tarefa, login, max_saida, tempo, esforco)
    if not r["texto"] and "max_tokens" in r["erro"] and esforco != "low":
        r2 = _chamar_claude(papel, tarefa, login, max_saida, tempo, "low")
        u1, u2 = r.get("uso") or {}, r2.get("uso") or {}
        r2["uso"] = {**u2, **{k: (u1.get(k) or 0) + (u2.get(k) or 0) for k in ("entrada", "saida", "cache_lido", "usd")}}
        if isinstance(r2["uso"].get("usd"), float):
            r2["uso"]["usd"] = round(r2["uso"]["usd"], 4)
        return r2
    return r


def _chamar_claude(papel: str, tarefa: str, login: str, max_saida: int, tempo: int, esforco: str) -> dict:
    body = {"system": [{"text": PAPEIS[papel]}], "messages": [{"role": "user", "content": [{"text": tarefa}]}],
            "inferenceConfig": {"maxTokens": int(max_saida)},
            "additionalModelRequestFields": {"output_config": {"effort": esforco}}}
    try:
        data = _enviar_claude(f"{PROXY_BEDROCK}/{MODELO_CLAUDE}/converse", body, login, papel, tempo)
    except Exception as exc:
        return {"texto": "", "erro": f"{type(exc).__name__}: {str(exc)[:200]}", "uso": {}}
    u = data.get("usage") or {}
    # the host proxy adds cache points: most of the prompt comes as cache write/read, not inputTokens (03/11: "4")
    entrada, saida = int(u.get("inputTokens") or 0), int(u.get("outputTokens") or 0)
    grava, le = int(u.get("cacheWriteInputTokens") or 0), int(u.get("cacheReadInputTokens") or 0)
    p = PRECO_CLAUDE
    uso = {"entrada": entrada + grava + le, "saida": saida, "cache_lido": le, "modelo": MODELO_CLAUDE,
           "usd": round(entrada * p["entrada"] + grava * p["entrada"] * 1.25 + le * p["entrada"] * 0.1
                        + saida * p["saida"], 4)}
    texto = "".join(c.get("text", "") for c in ((data.get("output") or {}).get("message") or {}).get("content") or []
                    if isinstance(c, dict))
    return {"texto": texto, "erro": "" if texto else f"sem texto na resposta ({data.get('stopReason')})", "uso": uso}


def _json(saida: str):
    """The answer's JSON object. 12/11: besides the whole answer between the first "{" and the last "}", the first
    object that decodes on its own (a ficha followed by a note with braces, or two objects, used to come out
    "ilegível")."""
    saida = saida or ""
    achado = re.search(r"\{.*\}", saida, re.S)
    if not achado:
        return None
    try:
        d = json.loads(achado.group(0))
        return d if isinstance(d, dict) else None
    except ValueError:
        pass
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", saida):
        try:
            d, _fim = dec.raw_decode(saida, m.start())
        except ValueError:
            continue
        if isinstance(d, dict) and len(d) > 1:
            return d
    return None


def _lista_textos(v) -> list[str] | None:
    if v is None:
        return []
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        return None
    return [x.strip() for x in v if x.strip()]


def interpretar_critica(saida: str) -> dict:
    """The Crítico's answer, strictly: a JSON object with veredito aprova|reprova and lists of texts. Anything else is
    "reprova" with motivo "resposta ilegível" (fail closed)."""
    ilegivel = {"veredito": "reprova", "motivos": ["resposta ilegível"], "sugestoes": []}
    d = _json(saida)
    if d is None:
        return ilegivel
    veredito = d.get("veredito")
    motivos, sugestoes = _lista_textos(d.get("motivos")), _lista_textos(d.get("sugestoes"))
    if not isinstance(veredito, str) or veredito.strip().lower() not in ("aprova", "reprova") \
            or motivos is None or sugestoes is None:
        return ilegivel
    veredito = veredito.strip().lower()
    if veredito == "reprova" and not motivos:
        motivos = ["reprovado sem motivo dado"]
    return {"veredito": veredito, "motivos": motivos, "sugestoes": sugestoes}


# --- what the Crítico reads ------------------------------------------------------------------------------------------

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


# 22/10: at 6000 letters each Raiz file got a fair share and the offer was cut after ~1000; the Crítico reproved the
# offer post for numbers that are in the offer (5 implementações, 10 produtos, the value stack). The whole Cérebro da
# Raiz is ~18k letters: read it all.
CONTEXTO = 24000


def contexto_raiz(limite: int = CONTEXTO) -> tuple[str, str]:
    """(text, note) from the Cérebro da Raiz (cerebro/helpers/raiz.py `contexto`); empty text plus a clear note when
    it is not installed or fails, so the caller can still judge by the fixed rules."""
    cerebro = PLUGINS / "cerebro" / "helpers"
    try:
        # the cerebro tool's own loader when it is already in memory (same module, same pasta.RAIZ)
        mods = sys.modules.get("cerebro_modulos")
        if mods is None or Path(getattr(mods, "RAIZ", "")).resolve() != cerebro.parent.resolve():
            mods = _carregar("especialistas_cerebro_modulos", cerebro / "modulos.py") \
                if (cerebro / "modulos.py").exists() else None
        if mods is not None and "raiz" in getattr(mods, "CAMINHOS", {}):
            raiz = mods.m("raiz")
        elif (cerebro / "raiz.py").exists():
            raiz = _carregar("cerebro_raiz", cerebro / "raiz.py")
        else:
            return "", "Cérebro da Raiz indisponível (cerebro/helpers/raiz.py não está instalado)"
        texto = str(raiz.contexto(limite=limite) or "").strip()
    except Exception as exc:
        return "", f"Cérebro da Raiz indisponível ({type(exc).__name__}: {str(exc)[:120]})"
    return (texto, "") if texto else ("", "Cérebro da Raiz vazio")


def decisoes_raiz(limite: int = 9000) -> str:
    """Matheus's decisions and preferences for the Raiz (posts, videos, prospecção) from the Segundo Cérebro: they come
    after the AR Board criteria were written and win over them (21/10: the Crítico blocked the iFood video citing a
    week-1 criterion that his later "nexo" decision had replaced). "" when the Pasta is not there."""
    cerebro = PLUGINS / "cerebro" / "helpers"
    try:
        mods = sys.modules.get("cerebro_modulos")
        if mods is None or "briefing" not in getattr(mods, "CAMINHOS", {}):
            mods = _carregar("especialistas_cerebro_modulos", cerebro / "modulos.py")
        return str(mods.m("briefing").para_revisor(mods, "raiz", limite=limite) or "")
    except Exception:
        return ""


def criterios(tipo: str) -> str:
    """Matheus's AR Board criteria for this kind of piece, when they exist (calibracao/<agente>/criterios.md)."""
    pasta = pasta_calibracao()
    if pasta is None:
        return ""
    partes = []
    for agente in CRITERIOS_POR_TIPO.get(tipo, ()):
        arq = pasta / agente / "criterios.md"
        try:
            texto = arq.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if texto:
            partes.append(f"### {agente}\n" + (texto[:MAX_CRITERIOS] + "\n…(truncado)" if len(texto) > MAX_CRITERIOS
                                               else texto))
    return "\n\n".join(partes)


def regras_fixas(tipo: str, material) -> list[str]:
    """Rules checked by code, not by the model: they reprove whatever the model says. Only the piece's own text: the
    post a story calls (post_do_dia) is context, its caption may say "salva" or carry the offer's price."""
    if isinstance(material, dict):
        # 11/11: the common briefing and the declared reference are context too: the radar quotes third parties (their
        # emoji, their "salve") and the rules name the forbidden words; five good stories were reproved by them
        material, _ = tirar_briefing(material)
        material = {k: v for k, v in material.items() if k not in ("post_do_dia", "referencia")}
        if isinstance(material.get("briefing"), dict):
            material["briefing"] = {k: v for k, v in material["briefing"].items() if k != "referencia"}
    texto, _ = _texto_material(material)
    motivos = []
    if EMOJI.search(texto):
        motivos.append("tem emoji (regra fixa: sem emoji em nada público)")
    if TRACO.search(texto):
        motivos.append("tem travessão (regra fixa do AR Board: sem — nem –)")
    if tipo in ("post", "carrossel", "story", "reel") and REAIS.search(texto) and not EXEMPLO.search(texto):
        motivos.append('número em R$ sem "valores de exemplo"')
    if tipo == "story" and SALVAR.search(texto):
        motivos.append('pede para salvar, e story não se salva no Instagram (use "tira um print" ou "responde aqui")')
    return motivos


def criticar(tipo: str, material, *, login: str = "matheus") -> dict:
    """The Crítico's verdict on a piece: {"veredito": "aprova"|"reprova", "motivos": [...], "sugestoes": [...]} plus
    "avisos" (what it judged without). `material`: text, or a dict (fields of the piece; "imagens": paths)."""
    tipo = str(tipo or "").strip().lower()
    if tipo not in TIPOS:
        return {"veredito": "reprova", "motivos": [f"tipo desconhecido: {tipo or '(vazio)'} (use {', '.join(TIPOS)})"],
                "sugestoes": [], "avisos": []}
    if not material or (isinstance(material, str) and not material.strip()):
        return {"veredito": "reprova", "motivos": ["nada para julgar (material vazio)"], "sugestoes": [], "avisos": []}
    ctx, nota = contexto_raiz()
    crit = criterios(tipo)
    avisos = [nota] if nota else []
    if not crit:
        avisos.append(f"sem critérios do AR Board para {tipo}")
    tarefa = (f"Julgue esta peça do tipo **{tipo}** antes de ela ir a público.\n\n"
              f"## Cérebro da Raiz\n{ctx or '(indisponível: ' + nota + '; julgue pelas regras fixas e diga se faltou contexto)'}"
              f"\n\n## Critérios do Matheus (AR Board)\n{crit or '(nenhum registrado para este tipo)'}")
    dec = decisoes_raiz()
    if dec:
        tarefa += f"\n\n## Decisões do Matheus\n{dec}"
    if isinstance(material, dict) and material.get("narracao"):
        tarefa += ("\n\n## Vídeo\nAs imagens são quadros do vídeo (a ordem e o segundo de cada uma estão em \"quadros\") e "
                   "\"narracao\" é a fala com os tempos. Confira: a tela mostra o que a narração diz naquele momento; nenhum "
                   "texto cortado, sobretudo no último quadro (a chamada); o que a legenda afirma aparece no vídeo. Julgue "
                   "pelo que vê e ouve aqui, não exija prova que não caberia num vídeo. Tela do sistema: ela entra inteira, com "
                   "o menu, e depois a câmera aproxima um ponto dela (decisão #85: vídeo com zoom e movimento); um quadro "
                   "aproximado não é tela recortada nem quebra a decisão #85 (27/10: um Reel aprovado pelo Matheus foi "
                   "travado na publicação por isso).")
    if isinstance(material, dict) and material.get("post_do_dia"):
        tarefa += ("\n\n## Story que chama o post do dia\n\"post_do_dia\" é o post do feed que este story manda ver. A manchete "
                   "tem de falar do mesmo assunto dele: story que promete um assunto e leva a um post de outro é informação "
                   "falsa (reprova, citando os dois). A imagem do story é a capa ou a tela desse post.")
    r = chamar("critico", tarefa, material, login=login)
    if r["erro"]:
        veredito = {"veredito": "reprova", "motivos": [f"o crítico não respondeu ({r['erro']})"], "sugestoes": []}
    else:
        veredito = interpretar_critica(r["texto"])
    fixas = regras_fixas(tipo, material)
    if fixas:
        veredito = {"veredito": "reprova", "motivos": fixas + [m for m in veredito["motivos"] if m not in fixas],
                    "sugestoes": veredito["sugestoes"]}
    if r.get("sem_imagem"):
        avisos.append("imagens não vistas: " + ", ".join(Path(s).name for s in r["sem_imagem"]))
    veredito["avisos"] = avisos
    return veredito


# --- the Designer ----------------------------------------------------------------------------------------------------

KIT = """Motor de render: sempre "motor": "molde" (é o único que roda aqui; o carrossel e o vídeo "do kit" feitos à mão
são só da sessão de operador, nunca escolha).
- "molde": o que o agente renderiza sozinho, para a Raiz e para outras marcas (22/10). Para a Raiz, "_marca": "raiz"
  na ficha aplica o fixo do kit; o conceito muda de peça para peça (o molde de um post dos últimos 14 dias não
  volta: a lista de moldes abaixo já vem sem eles). Campos:
  "molde" (id do catálogo), "formato" (carrossel|reel|story, um dos formatos do molde), "ficha" (os campos do esquema
  do molde, com "_marca" e "_origem" para dado real; Reel narrado leva "falas", lidas pela voz Carolina).
  Tela do sistema: só as telas reais, escuras e inteiras de /a0/usr/plugins/conteudo/story/telas/ (no molde
  lanca-app/demonstracao, a câmera dá zoom no "destaque" da tela); toda peça com tela diz "valores de exemplo" na
  própria peça (campo nota do molde que tem nota; no carrossel o motor já põe o selo ao lado de cada tela), nunca só
  na legenda, e cada fala mostra a tela que prova o que ela diz.
  Termo técnico (CMV, ficha técnica, DRE) vem explicado em palavras simples na primeira vez.
Sempre: "marca" ("raiz" ou a pasta da outra marca), "formato" (carrossel|reel|story), "conceito", "legenda" (sem
emoji, terminando no passo concreto da chamada)."""


# The catalog was made for every kind of small business; most moldes speak to the CONSUMER of a shop (menu, combo, real
# customer's words, opening hours, a product photo of the shop's own). The Raiz speaks to the owner and has no shop
# photos nor real customers to quote: offered those, the Designer filled a "pergunta de cliente" with an invented
# comment and a "produto da semana" with a tour of a screen (11/11, the simulation: 0 of 4 feed posts passed). For the
# Raiz the Designer is offered only the moldes that fit a brand that teaches owners.
MOLDES_DA_RAIZ = {
    "carrossel": ("mito", "quiz", "time", "frases", "passo-a-passo", "faca-nao-faca", "pergunta-cliente", "antes-depois"),
    "reel": ("conta-mudou", "custo-escondido", "mito", "quiz", "chat", "expectativa", "frases", "passo-a-passo",
             "faca-nao-faca", "explica", "glossario", "sabia-que", "lista-cinco", "piramide", "comparativo", "funil",
             "pergunta-cliente", "time", "lanca-app", "demonstracao", "oferta-completa"),
}


def moldes_da_marca(catalogo: dict, marca: str, formato: str) -> dict:
    """The catalog cut to what fits the brand and the slot's format (the whole catalog for any other brand)."""
    servem = MOLDES_DA_RAIZ.get(formato) if str(marca or "raiz").lower() == "raiz" else None
    corte = {i: m for i, m in catalogo.items() if i in servem} if servem else {}
    return corte or catalogo


def catalogo_moldes() -> dict:
    moldes = pasta_moldes()
    arq = moldes / "catalogo.json" if moldes else None
    try:
        return {m["id"]: m for m in json.loads(arq.read_text(encoding="utf-8"))["moldes"]} if arq else {}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def _regra_curta(regra: dict) -> str:
    """One esquema field as the Designer needs it: type, limits, optional, and the sub-fields of a list."""
    partes = [str(regra.get("tipo", "texto"))]
    if "min" in regra:
        partes.append(f"min {regra['min']}")
    if "max" in regra:
        partes.append(f"max {regra['max']}")
    if regra.get("obrigatorio") is False:
        partes.append("opcional")
    if regra.get("real"):
        partes.append("real")
    item = regra.get("item")
    if isinstance(item, dict) and "tipo" in item and not isinstance(item["tipo"], dict):  # a list of plain values
        partes.append("cada um " + _regra_curta(item))
    elif isinstance(item, dict) and item and all(isinstance(v, dict) for v in item.values()):
        partes.append("cada um {" + ", ".join(f"{k}: {_regra_curta(v)}" for k, v in item.items()) + "}")
    return " ".join(partes)


def _campos_do_molde(molde: str) -> str:
    """The molde's real fields, from its esquema.json (what validar.py checks). 08/11: the catalog's hand-written
    "ficha" had drifted in 25 of the 65 moldes (demonstracao had no "falas"), the Designer filled the wrong fields and
    Sunday's Reel failed every redo. Empty when there is no esquema (the catalog's summary is used instead)."""
    moldes = pasta_moldes()
    try:
        campos = json.loads((moldes / molde / "esquema.json").read_text(encoding="utf-8")).get("campos") or {}
    except (OSError, ValueError, TypeError, AttributeError):
        return ""
    # 10/11: the narrated moldes count their falas from the screens ("telas + 7 falas") and want 55 to 65 s; that rule
    # lives only in the field's "dica", which the short form dropped: 9 of Sunday's Reels came back with 10 falas
    return "{" + "; ".join(f"{k}: {_regra_curta(v)}" + (f" (regra: {v['dica']})" if k == "falas" and v.get("dica") else "")
                           for k, v in campos.items() if isinstance(v, dict)) + "}"


FALAS_POR_TELA = re.compile(r"telas \+ (\d+) falas")


def _falas_do_molde(molde: str, ficha: dict) -> list[str]:
    """10/11: lanca-app and demonstracao refuse a ficha whose falas are not "telas + N" only inside the render (after
    the voice is made), with a message the Designer kept getting wrong: checked here, before the render, from the
    esquema's own rule, so the correction round fixes it with the exact count."""
    moldes = pasta_moldes()
    try:
        regra = json.loads((moldes / molde / "esquema.json").read_text(encoding="utf-8"))["campos"]["falas"]
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return []
    achado = FALAS_POR_TELA.search(str(regra.get("dica") or ""))
    telas, falas = ficha.get("telas"), ficha.get("falas")
    if not achado or not isinstance(telas, list) or not isinstance(falas, list) or not telas:
        return []
    certo = len(telas) + int(achado.group(1))
    if len(falas) == certo:
        return []
    return [f"falas: são {certo} ({len(telas)} telas + {achado.group(1)}: {regra.get('dica')}); vieram {len(falas)}. "
            f"Uma fala por cena, na ordem das cenas; a voz Carolina lê umas 2,5 palavras por segundo"]


def _validar_ficha(molde: str, ficha: dict) -> list[str]:
    """The moldes motor's own validator (moldes/motor/validar.py) against the molde's esquema.json."""
    moldes = pasta_moldes()
    pasta = moldes / molde if moldes else None
    if not pasta or not (pasta / "esquema.json").exists():
        return [f"molde {molde} não existe no motor"]
    try:
        validar = _carregar("especialistas_validar_molde", moldes / "motor" / "validar.py").validar
        return list(validar(json.loads((pasta / "esquema.json").read_text(encoding="utf-8")), ficha))
    except Exception as exc:
        return [f"não consegui validar a ficha ({type(exc).__name__})"]


def _pode_renderizar() -> str:
    """Empty when the moldes motor can run here (render.py plus Playwright or patchright); otherwise what is missing."""
    moldes = pasta_moldes()
    if moldes is None or not (moldes / "motor" / "render.py").exists():
        return "o motor de render (moldes) não está nesta máquina"
    if importlib.util.find_spec("playwright") is None and importlib.util.find_spec("patchright") is None:
        return "falta o Playwright/Chromium para renderizar"
    return ""


VOZ_CREDENCIAIS = "http://host.docker.internal:8788/voz"  # credenciais_meta.py on the host: only Nova Sonic and Polly


def ambiente_render(pasta: Path) -> dict:
    """The environment render.py runs with: the narration's short-lived credentials come from the host
    (credential_process, profile "voz" in a config file of its own) and the voice cache stays under /a0/usr."""
    config = pasta / "aws-voz.config"
    config.write_text("[profile voz]\nregion = us-east-1\ncredential_process = python3 -c \"import urllib.request; "
                      f"print(urllib.request.urlopen('{VOZ_CREDENCIAIS}', timeout=20).read().decode())\"\n",
                      encoding="utf-8")
    # 27/10: in the Hermes the Bedrock endpoint points at our HTTP/1 proxy and fake keys are set; the voice (Nova
    # Sonic, an HTTP/2 stream) inherited them and every Reel since 23/10 failed ("não leu a fala certa")
    fora = {"AWS_ENDPOINT_URL", "AWS_ENDPOINT_URL_BEDROCK_RUNTIME", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN"}
    return {**{k: v for k, v in os.environ.items() if k not in fora}, "AWS_CONFIG_FILE": str(config),
            "AWS_PROFILE": "voz", "AWS_REGION": "us-east-1", "AWS_SDK_LOAD_CONFIG": "1",
            "MOLDES_CACHE": os.environ.get("MOLDES_CACHE", "/a0/usr/conteudo/cache-moldes"),
            # 12/11: not the Hermes's scratch volume, where Chromium hung or crashed the page (a 15-minute render)
            "TMPDIR": "/tmp"}


def _pasta_saida() -> Path:
    base = Path(os.environ.get("ESPECIALISTAS_SAIDA", "/a0/usr/workdir/especialistas"))
    try:
        destino = base / time.strftime("%Y%m%d-%H%M%S")
        destino.mkdir(parents=True, exist_ok=True)
        return destino
    except OSError:
        return Path(tempfile.mkdtemp(prefix="especialistas_"))


RENDER_CURTO = 240  # s: a preview or a carousel (they take under 30 s)
RENDER_VIDEO = 900  # s: the finished video


def renderizar_molde(molde: str, formato: str, ficha: dict, previa: bool = False, saida: Path | None = None,
                     timeout: int | None = None, processos: int = 0) -> tuple[list[str], str]:
    """Runs moldes/motor/render.py; returns (files, problem). Exit 2 = ficha refused, 3 = the check found problems.
    previa: the check, the contact sheet and the narration only (narracao.m4a), never the video (that comes after the
    Crítico approves the preview). 12/11: a preview hung in the browser for the whole 15 minutes the finished video
    gets; previews and carousels take under 30 s, so they get RENDER_CURTO."""
    if timeout is None:
        timeout = RENDER_CURTO if previa or formato == "carrossel" else RENDER_VIDEO
    moldes = pasta_moldes()
    saida = saida or _pasta_saida()
    saida.mkdir(parents=True, exist_ok=True)
    arq_ficha = saida / "ficha.json"
    arq_ficha.write_text(json.dumps(ficha, ensure_ascii=False, indent=1), encoding="utf-8")
    cmd = [sys.executable, str(moldes / "motor" / "render.py"), molde, str(arq_ficha),
           "--formato", formato, "--saida", str(saida)] + (["--previa"] if previa else []) + (
              ["--processos", str(processos)] if processos else [])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(moldes),
                           env=ambiente_render(saida))
    except Exception as exc:
        return [], f"o render não rodou ({type(exc).__name__})"
    arquivos = sorted((str(p) for p in saida.rglob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".mp4", ".m4a")
                       and (previa or p.name != "prev.jpg")),  # the contact sheet is not a slide
                      key=lambda a: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", a)])  # slide2 before slide10
    if r.returncode == 2:
        return [], "o molde recusou a ficha: " + (r.stderr or r.stdout).strip()[-300:]
    if r.returncode == 3:
        return arquivos, "a conferência do render achou problemas: " + (r.stdout or "").strip()[-300:]
    if r.returncode != 0:  # the exception's own line, not the traceback's tail (27/10: the failing fala was cut off)
        linhas = [x for x in (r.stderr or "").strip().splitlines() if x.strip()]
        erro = next((x for x in reversed(linhas) if re.match(r"\w+(Error|Exception)\b", x)), linhas[-1] if linhas else "")
        return [], f"o render falhou (código {r.returncode}): " + erro.strip()[:400]
    return arquivos, ""


# Jargon the Crítico reproved three times in a row on 22/10: a term goes with its plain explanation (the brief's rule)
PERTO = 120
JARGAO = {"CMV": re.compile(r"custo d[aoe]s? (mercadoria|ingrediente|insumo|produto|que (você )?vend)|o quanto (do que|da venda)"
                            r"|quanto do faturamento|custo da comida", re.I),
          # 10/11: the Crítico reproved Sunday's and Wednesday's Reels for "DRE" and "Curva ABC" said without a word of
          # explanation, after the CMV was fixed: the same rule ("termo técnico explicado na primeira vez") for them
          "DRE": re.compile(r"quanto entrou|o que (sobrou|sobra)|resumo d[oe] (mês|resultado|dinheiro)|resultado do mês"
                            r"|entrou e (quanto )?saiu|demonstrativo", re.I),
          "curva ABC": re.compile(r"onde (vai|está|fica|se concentra) (a maior parte|o grosso|o maior)|o que mais pesa"
                                  r"|maiores gastos|(gastos?|custos?) que mais pesam|concentra(m)? (o|os|a|as) (gasto|custo)", re.I)}
JARGAO_CASO = {"DRE": 0, "CMV": 0, "curva ABC": re.I}  # DRE/CMV only as the acronym; curva ABC in any case
JARGAO_EXEMPLO = {"CMV": "CMV, o custo dos ingredientes do que você vendeu",
                  "DRE": "a DRE, o resumo do mês: quanto entrou, quanto saiu e o que sobrou",
                  "curva ABC": "a curva ABC mostra onde vai a maior parte do dinheiro gasto"}


def _jargao(texto: str) -> list[str]:
    """The explanation must come with the first time the term appears (22/10: explained only on the last slide, the
    Crítico still reproved), within PERTO letters of it."""
    erros = []
    for termo, explica in JARGAO.items():
        primeira = re.search(rf"\b{termo}\b", texto, JARGAO_CASO.get(termo, 0))
        if primeira and not explica.search(texto[max(0, primeira.start() - PERTO):primeira.end() + PERTO]):
            erros.append(f"ficha: {termo} aparece sem explicação em palavras simples logo na primeira vez (ex.: "
                         f"\"{JARGAO_EXEMPLO[termo]}\")")
    return erros


LEGENDA_GENERICA = re.compile(r"\b(conheça|saiba mais|solução|soluções)\b", re.I)


def _legenda_generica(spec: dict) -> list[str]:
    """10/11, real: the Wednesday carousel reproved for a caption ending "Conheça a solução para sua operação." The
    rule was only in the Designer's prompt (end on the concrete step, never "saiba mais"/"conheça"); now the
    correction round fixes it before the Crítico. 11/11: the caption also ends on the same call as the final slide
    (the link in the bio), which the motor puts on every Raiz piece."""
    legenda = str(spec.get("legenda") or "")
    erros = []
    achado = LEGENDA_GENERICA.search(legenda)
    if achado:
        erros.append(f"ficha: a legenda usa \"{achado.group(0)}\" (genérico, a marca não usa): termine no passo concreto, "
                     "ex.: \"Toque no link da bio e veja o Lucro na Mão em 30 Dias.\"")
    if legenda.strip() and not re.search(r"link (da|na) bio", legenda, re.I):
        erros.append("ficha: a legenda não termina na chamada do slide final (toque no link da bio)")
    return erros


def _telas_desconhecidas(ficha) -> list[str]:
    """11/11, real: the calculator (a public page, light, no menu) saved in the screens folder went into a carousel as
    a "tela do sistema" and the Crítico reproved it three times. Only the known screens (TELAS) may be used."""
    achados = set(re.findall(r"/story/telas/([^\s\"']+)", json.dumps(ficha, ensure_ascii=False)))
    return [f"ficha: {n} não é tela do sistema (use só: {', '.join(sorted(TELAS))})" for n in sorted(achados) if n not in TELAS]


def _texto_dito(ficha: dict) -> dict:
    """What the piece writes or says, for the jargon check: a screen's file and its menu label are not text of the piece
    (the Crítico's rule, 27/10)."""
    def limpar(v):
        if isinstance(v, dict):
            fora = {"imagem", "_origem"} | ({"nome"} if "imagem" in v else set())  # a screen: its file and menu label
            return {k: limpar(x) for k, x in v.items() if k not in fora}
        if isinstance(v, list):
            return [limpar(x) for x in v]
        return "" if isinstance(v, str) and re.search(r"\.(jpe?g|png|webp)$", v, re.I) else v
    return limpar(ficha)


def _conferir_spec(spec: dict) -> list[str]:
    """Deterministic checks on the Designer's spec; each problem goes to "falta"."""
    problemas = []
    motor, marca = spec.get("motor"), str(spec.get("marca") or "raiz").strip().lower()
    if motor not in MOTORES:
        return [f"motor desconhecido: {motor!r} (use {', '.join(MOTORES)})"]
    if motor == "carrossel_raiz":
        slides = spec.get("slides")
        if not isinstance(slides, list) or not 2 <= len(slides) <= 10:
            problemas.append("carrossel precisa de 2 a 10 slides")
        else:
            for i, s in enumerate(slides, 1):
                manchete = str((s or {}).get("manchete") or "") if isinstance(s, dict) else ""
                if not manchete.strip():
                    problemas.append(f"slide {i} sem manchete")
                elif len(manchete.split()) > 12:
                    problemas.append(f"slide {i}: manchete com {len(manchete.split())} palavras (máx. 12)")
    if motor == "molde":
        if not isinstance(spec.get("ficha"), dict):
            problemas.append("molde sem ficha")
        else:
            if marca == "raiz" and str(spec["ficha"].get("_marca") or "raiz") != "raiz":
                problemas.append("peça da Raiz com outra marca na ficha (_marca): o kit só vale com a marca raiz")
            if marca == "raiz":
                problemas += _jargao(json.dumps(_texto_dito(spec["ficha"]), ensure_ascii=False))
                problemas += _legenda_generica(spec)
                problemas += _telas_desconhecidas(spec["ficha"])
            pedido = spec.get("_formato_pedido")
            if pedido and str(spec.get("formato") or "").lower() != pedido:
                problemas.append(f"ficha: formato {spec.get('formato')!r}, mas a vaga da semana é {pedido!r}: use um molde "
                                 f"que faça {pedido}")
            problemas += [f"ficha: {e}" for e in _validar_ficha(str(spec.get("molde") or ""), spec["ficha"])]
            problemas += [f"ficha: {e}" for e in _falas_do_molde(str(spec.get("molde") or ""), spec["ficha"])]
    return problemas


CORRECOES = 3
REVISOES = 2


FORMATO_DO_BRIEFING = {"CARROSSEL": "carrossel", "REELS": "reel", "STORY": "story"}


def _spec(r: dict, pedido: str = "") -> dict:
    """The Designer's JSON; a ficha with a "molde" is the moldes motor even when "motor" was left out (22/10). The
    format the week asked for travels with the spec: a Reel delivered for a carousel slot is a ficha error."""
    spec = (_json(r["texto"]) if not r["erro"] else None) or {}
    if not isinstance(spec, dict):
        return {}
    if spec.get("molde") and not spec.get("motor"):
        spec["motor"] = "molde"
    if spec and pedido:
        spec["_formato_pedido"] = pedido
        # 11/11: the slot's format is imposed, not discovered later. A molde that makes the slot's format comes out in
        # it whatever the ficha says ("formato": "reel" on a carousel slot killed Friday's carousel three times)
        if pedido in (catalogo_moldes().get(str(spec.get("molde") or "")) or {}).get("formatos", []):
            spec["formato"] = pedido
            if isinstance(spec.get("ficha"), dict) and spec["ficha"].get("_formato"):
                spec["ficha"]["_formato"] = pedido
    return _padroes_da_raiz(spec)


# The closing slide/scene of most moldes is a "produto" (or "oferta"): a real photo of what the post sells plus its
# name. The Raiz sells one thing and has one picture for it; the Designer left the field out and the correction came
# back unreadable, twice in a row (11/11, the carousel of 24/11: "ficha: produto: falta"). For the Raiz the field has a
# default: what is missing is filled, what the Designer wrote stays.
VITRINE_DA_RAIZ = {"foto": "fotos/raiz_calculadora.jpg", "nome": "Lucro na Mão em 30 Dias",
                   "detalhe": "Veja quanto sobra em cada produto", "convite": "toque no link da bio"}


def _padroes_da_raiz(spec: dict) -> dict:
    ficha = spec.get("ficha") if isinstance(spec, dict) else None
    if not isinstance(ficha, dict) or str(spec.get("marca") or ficha.get("_marca") or "raiz").lower() != "raiz":
        return spec
    moldes = pasta_moldes()
    try:
        campos = json.loads((moldes / str(spec.get("molde") or "") / "esquema.json").read_text(encoding="utf-8"))["campos"]
    except Exception:
        return spec
    for nome, regra in campos.items():
        if not isinstance(regra, dict) or regra.get("obrigatorio") is False:
            continue
        sub = regra.get("campos") if regra.get("tipo") == "objeto" and isinstance(regra.get("campos"), dict) else None
        if sub and {"foto", "nome"} <= set(sub):  # the vitrine object (produto, oferta)
            atual = ficha.get(nome) if isinstance(ficha.get(nome), dict) else {}
            ficha[nome] = {**{k: v for k, v in VITRINE_DA_RAIZ.items() if k in sub}, **{k: v for k, v in atual.items() if v}}
            # in a video the motor puts no "Valores de exemplo" seal next to a screen: the closing picture is the photo
            if str(spec.get("formato") or "").lower() == "reel" and "/telas/" in str(ficha[nome].get("foto") or ""):
                ficha[nome]["foto"] = VITRINE_DA_RAIZ["foto"]
        elif regra.get("tipo") == "foto" and "produto" in nome and not ficha.get(nome):
            ficha[nome] = VITRINE_DA_RAIZ["foto"]
    # A number of the Raiz's teaching pieces is an example sum (the piece says "valores de exemplo"), not a client's
    # datum: the origin the moldes ask for every "real" field is "dono" (as in the Raiz's own example fichas). 11/11:
    # "conta[1].valor: dado real sem origem" killed the same carousel a third time.
    try:
        sem_origem = {m.group(1).split("[")[0].split(".")[0] for m in (
            re.match(r"(.+?): dado real sem origem", e) for e in _validar_ficha(str(spec.get("molde") or ""), ficha)) if m}
    except Exception:
        sem_origem = set()
    if sem_origem:
        origem = ficha.get("_origem") if isinstance(ficha.get("_origem"), dict) else {}
        ficha["_origem"] = {**{k: "dono" for k in sem_origem}, **origem}
    return spec


def _chamada_da_marca() -> str:
    """The Raiz's final scene shows the brand's call to action; the last line of a narrated video says the same."""
    try:
        chamada = json.loads((pasta_moldes() / "marcas" / "raiz" / "marca.json").read_text(encoding="utf-8")).get("chamada")
    except Exception:
        return ""
    return (f"A cena final da Raiz mostra a chamada \"{chamada}\" (a oferta Lucro na Mão em 30 Dias: em 30 dias o dono vê "
            "quanto sobra em cada produto). A última fala de um vídeo narrado liga a ideia da peça a essa oferta e diz a "
            "chamada; a legenda termina com o mesmo passo concreto (toque no link da bio), nunca \"saiba mais\" ou "
            "\"conheça\".\n\n") if chamada else ""


# what each screen shows (22/10: a line said "99Food" over the kitchen screen, which shows iFood and table orders only)
TELAS = {
    "cozinha-kds.jpg": "cozinha (KDS): pedido da mesa ao lado de dois pedidos com o selo iFood, com o tempo de cada um; não mostra 99Food",
    "mapa-de-mesas.jpg": "mapa de mesas do salão: cada mesa livre ou ocupada, com tempo e valor da conta",
    "cmv-real.jpg": "CMV do mês (o custo dos ingredientes do que você vendeu: quanto do faturamento virou custo), a meta e "
                    "quanto escapou entre a ficha técnica e o estoque",
    "visao-executiva.jpg": "visão executiva: quanto sobrou no mês, receita, custo dos ingredientes, despesas, ponto de empate, "
                           "caixa e contas vencidas",
    "dashboard-restaurante.jpg": "dashboard do restaurante: faturamento do dia, ticket médio, pedidos, itens mais vendidos, formas de pagamento",
    "dre.jpg": "DRE (o resumo do mês: quanto entrou, quanto saiu e o que sobrou): receita, custos, despesas e resultado",
    "curva-abc-custos.jpg": "curva ABC de custos (onde vai a maior parte do dinheiro gasto), por conta",
    "engenharia-de-cardapio.jpg": "engenharia de cardápio: cada prato por quanto vende e quanto sobra (campeão, oportunidade, revisar)",
}


# 12/11, the simulation: the Designer wrote "fotos/pizza_cozinha.jpg" (no such photo) and, before that, a description
# of the scene in the photo field: it was never told which photos exist. The bank's food photos go with the task.
FORA_DO_BANCO_DA_RAIZ = ("atelie", "oficina", "salao", "inauguracao_oficina", "inauguracao_salao", "lanca-produto_fds",
                         "lanca-produto_linho")


def fotos_do_banco() -> str:
    """The photos a Raiz piece may use (moldes/midia/fotos/indice.json, the food ones), by path, with what each shows."""
    moldes = pasta_moldes()
    try:
        indice = json.loads((moldes / "midia" / "fotos" / "indice.json").read_text(encoding="utf-8")) if moldes else {}
    except (OSError, ValueError):
        return ""
    linhas = [f"- fotos/{nome}: {str((info or {}).get('mostra') or '')[:70]}" for nome, info in sorted(indice.items())
              if not nome.startswith(FORA_DO_BANCO_DA_RAIZ) and isinstance(info, dict)]
    if not linhas:
        return ""
    return ("## Fotos que existem (campo de foto ou filmagem: só estes caminhos ou uma tela da lista; outra foto não "
            "existe e o molde recusa)\n" + "\n".join(linhas) + "\n\n")


def telas_do_sistema(formato: str = "") -> str:
    """The real screens of the system the Designer may use (dark, whole, with the menu: decision #85), by path."""
    pasta = PLUGINS / "conteudo" / "story" / "telas"
    # 11/11: a public page (the calculator, light, no menu) was saved in that folder on the VM and offered as a "tela
    # do sistema"; the Crítico reproved it as a cut screen without the menu three times and Wednesday lost its post.
    # Only the known screens of the system (TELAS) are offered; any other file there is not.
    nomes = sorted(p.name for p in pasta.glob("*.jpg") if p.name in TELAS) if pasta.exists() else []
    if not nomes:
        return ""
    return ("## Telas reais do sistema (1440x900, tema escuro, inteiras com o menu; a empresa de exemplo \"Pizzaria Bella "
            "Napoli\" é fictícia e fica na tela: não prometa esconder o nome; valores de exemplo). A fala só afirma o que a "
            "tela mostra; sigla da tela (CMV, DRE, curva ABC) dita ou escrita vem explicada em palavras simples na hora:\n"
            + "\n".join(f"- /a0/usr/plugins/conteudo/story/telas/{n}: {TELAS[n]}" for n in nomes)
            + "\n" + (
                # 22/10: told "use lanca-app to show the system", a carousel slot kept coming back as a video
                "Num carrossel, a tela entra no campo de foto de um molde de carrossel (ex.: passo-a-passo, mito, "
                "faca-nao-faca, pergunta-cliente), com o caminho acima; nunca use molde de vídeo. O motor põe o selo "
                "\"Valores de exemplo\" ao lado de cada tela e \"valores de exemplo\" pequeno no pé de todo slide que "
                "mostra R$ (12/11): não repita isso no texto dos slides; na legenda, uma vez."
                if formato == "carrossel" else
                "Um vídeo não precisa mostrar o sistema: a maioria ensina o dono sem tela nenhuma (conta-mudou, "
                "custo-escondido, mito, quiz, chat, expectativa, frases, passo-a-passo, explica). Só quando a ideia É a "
                "tela use o molde lanca-app com \"aparelho\": \"computador\" (a câmera dá zoom no \"destaque\" de cada "
                "tela, em % da tela; demonstracao é moldura de celular), e só com as telas desta lista: não existe tela de "
                "comanda, de divisão de conta, de cardápio digital nem de estoque.")
            + " Campo \"real\" pede \"_origem\" com \"sistema\" (tela) ou \"dono\".\n\n")


def _moldes_que_servem(formato: str, evitar=()) -> str:
    """The catalog's moldes for the slot's format (minus the ones ruled out), for a ficha that named a molde that does
    not exist (10/11: the Gestor said "um molde de cena ou humor", the Designer wrote "molde": "cena" three times and
    the correction never told it which moldes exist)."""
    cat = {i: m for i, m in catalogo_moldes().items() if not formato or formato in m.get("formatos", [])}
    cat = moldes_da_marca(cat, "raiz", formato)
    sobra = {i: m for i, m in cat.items() if i not in set(evitar or [])} or cat
    return "\n".join(f"- {i}: {m.get('situacao', '')} Ficha: {_campos_do_molde(i) or json.dumps(m.get('ficha', {}), ensure_ascii=False)}"
                     for i, m in sobra.items())


def _tarefa_correcao(spec: dict, falta: list, evitar=()) -> str:
    """The second try: the template's schema, an example ficha (the Raiz's when there is one) and what failed."""
    pasta = pasta_moldes() / str(spec.get("molde") or "") if pasta_moldes() else None
    esquema = exemplo = ""
    pedido = str(spec.get("_formato_pedido") or "")
    nao_faz = bool(pedido) and pedido not in (catalogo_moldes().get(str(spec.get("molde") or "")) or {}).get("formatos", [pedido])
    if pasta is not None and (nao_faz or not (pasta / "esquema.json").exists()):
        lista = _moldes_que_servem(pedido, evitar)
        return (f"A ficha abaixo usa o molde {spec.get('molde')!r}, que "
                + (f"não faz {pedido} (a vaga é de {pedido})" if nao_faz and (pasta / "esquema.json").exists() else "não existe")
                + ". Escolha UM molde desta lista (use o id "
                f"exatamente como está), refaça a ficha com os campos dele e devolva a ficha inteira (com \"motor\": "
                f"\"molde\"), sem trocar o assunto do briefing.\n\n## Erros\n" + "\n".join(f"- {f}" for f in falta)
                + f"\n\n## Moldes que servem\n{lista}\n\n## Sua ficha\n{json.dumps(spec, ensure_ascii=False)[:6000]}\n\n"
                + telas_do_sistema(spec.get("_formato_pedido", "")) + fotos_do_banco() + "Responda só com o JSON.")
    if pasta and (pasta / "esquema.json").exists():
        esquema = (pasta / "esquema.json").read_text(encoding="utf-8")[:6000]
        exemplos = sorted((pasta / "exemplos").glob("*.json"))
        raiz = [e for e in exemplos if '"_marca": "raiz"' in e.read_text(encoding="utf-8")]
        if raiz or exemplos:
            exemplo = (raiz or exemplos)[0].read_text(encoding="utf-8")[:4000]
    return (f"A ficha abaixo não passou nas regras do molde {spec.get('molde')}. Corrija TODOS os erros, respeitando "
            f"os limites de letras do esquema (deixe cada texto uns 10% abaixo do máximo: contar letras é fácil de errar), e devolva a ficha inteira (mesmo formato, com \"motor\": \"molde\"). "
            f"Se este molde não serve para a ideia, troque por outro do catálogo.\n\n## Erros\n"
            + "\n".join(f"- {f}" for f in falta)
            + f"\n\n## Sua ficha\n{json.dumps(spec, ensure_ascii=False)[:6000]}\n\n## Esquema do molde\n{esquema}\n\n"
            + (f"## Exemplo de ficha que passa\n{exemplo}\n\n" if exemplo else "") + telas_do_sistema(spec.get("_formato_pedido", ""))
            + fotos_do_banco()
            + "Responda só com o JSON.")


def desenhar(briefing, *, login: str = "matheus") -> dict:
    """A briefing (text or dict) turned into {"spec", "arquivos", "critica", "falta", "render"}: the spec for the
    engine, the rendered files when the engine runs here, the Crítico's verdict (always) and what is still missing."""
    if not briefing or (isinstance(briefing, str) and not briefing.strip()):
        spec, arquivos, falta, render = {}, [], ["briefing vazio"], ""
        return {"spec": spec, "arquivos": arquivos, "falta": falta, "render": render,
                "critica": {"veredito": "reprova", "motivos": ["nada para julgar (briefing vazio)"], "sugestoes": [],
                            "avisos": []}}
    ctx, nota = contexto_raiz()
    catalogo = catalogo_moldes()
    pedido = FORMATO_DO_BRIEFING.get(str(briefing.get("formato") or "").upper(), "") if isinstance(briefing, dict) else ""
    if pedido:  # 22/10: shown the whole catalog it kept answering a carousel slot with a video template
        catalogo = {i: m for i, m in catalogo.items() if pedido in m.get("formatos", [])}
        marca = str(briefing.get("marca") or "raiz") if isinstance(briefing, dict) else "raiz"
        catalogo = moldes_da_marca(catalogo, marca, pedido)
    evitar = set(briefing.get("evitar_moldes") or []) if isinstance(briefing, dict) else set()
    if evitar and any(i not in evitar for i in catalogo):  # 08/11: the neighbouring posts' moldes are not offered
        catalogo = {i: m for i, m in catalogo.items() if i not in evitar}
    linhas_cat = "\n".join(f"- {i} ({', '.join(m.get('formatos', []))}): {m.get('situacao', '')} Ficha: "
                           f"{_campos_do_molde(i) or json.dumps(m.get('ficha', {}), ensure_ascii=False)}"
                           for i, m in catalogo.items())
    tarefa = (f"Transforme o briefing numa ficha para o motor de render.\n\n{KIT}\n\n"
              f"## Cérebro da Raiz\n{ctx or '(indisponível: ' + nota + ')'}\n\n"
              + (f"## Catálogo de moldes\n{linhas_cat}\n\n" if linhas_cat else "")
              + telas_do_sistema(pedido) + fotos_do_banco() + _chamada_da_marca()
              + (f"A vaga é de {pedido}: use só um molde da lista acima, com \"formato\": \"{pedido}\".\n" if pedido else "")
              + "Responda só com o JSON da ficha, com \"motor\".")
    material = {"briefing": briefing} if isinstance(briefing, str) else briefing
    r = chamar("designer", tarefa, material, login=login)
    out = _volta(briefing, material, _spec(r, pedido), r, login)
    # 22/10: the Designer redoes the piece once with the Crítico's reasons before it goes to Matheus
    for _ in range(REVISOES):
        spec = out["spec"]
        if out["critica"]["veredito"] != "reprova" or spec.get("motor") != "molde":
            break
        vistas = (out.get("previa") or [a for a in out["arquivos"] if Path(a).suffix.lower() in EXT_IMAGEM])[:MAX_IMAGENS]
        r = chamar("designer", _tarefa_revisao(spec, out["critica"]), {**material, "imagens": vistas}, login=login)
        novo = _spec(r, pedido)
        if not novo:
            out["falta"] = out["falta"] + [f"o designer não respondeu à revisão ({r['erro'] or 'resposta ilegível'})"]
            break
        anteriores = out.get("revisoes", []) + [out["critica"]["motivos"]]
        out = _volta(briefing, material, novo, r, login)
        out["revisoes"] = anteriores
    return out


def julgar_ficha(briefing, spec: dict, *, login: str = "matheus") -> dict:
    """A ficha written outside the Designer (27/10: the operator, after the Designer put the falas out of order three
    times) checked, rendered and judged exactly as a Designer's: same checks, same render, same Crítico; nothing is
    rewritten (a ficha error comes back in "falta")."""
    spec = dict(spec or {})
    if spec.get("molde") and not spec.get("motor"):
        spec["motor"] = "molde"
    pedido = FORMATO_DO_BRIEFING.get(str(briefing.get("formato") or "").upper(), "") if isinstance(briefing, dict) else ""
    if pedido:
        spec["_formato_pedido"] = pedido
    material = {"briefing": briefing} if isinstance(briefing, str) else briefing
    return _volta(briefing, material, spec, {"erro": "", "texto": ""}, login, correcoes=0)  # no Designer to correct it


def revisar(briefing, spec: dict, critica: dict, imagens=None, *, login: str = "matheus") -> dict:
    """One more Designer round on a piece already in the agenda, with the Crítico's reasons (22/10, Matheus: "Se o
    crítico rejeita, automáticamente deveria ser refeito ... durante a etapa de criação"): the advance check, a day
    before the post, calls this when it reproves. Same answer as desenhar()."""
    material = {"briefing": briefing} if isinstance(briefing, str) else dict(briefing or {})
    r = chamar("designer", _tarefa_revisao(spec, critica), {**material, "imagens": list(imagens or [])[:MAX_IMAGENS]},
               login=login)
    novo = _spec(r, spec.get("_formato_pedido", ""))
    if not novo:
        return {"spec": spec, "arquivos": [], "render": "",
                "falta": [f"o designer não respondeu à revisão ({r['erro'] or 'resposta ilegível'})"],
                "critica": {"veredito": "reprova", "motivos": list(critica.get("motivos") or []), "sugestoes": []}}
    return _volta(briefing, material, novo, r, login)


def _evitar(material) -> list:
    return list(material.get("evitar_moldes") or []) if isinstance(material, dict) else []


def _guardar_ilegivel(r: dict) -> None:
    """The raw answer that did not parse, kept for the operator (12/11: "resposta ilegível" with nothing to look at)."""
    try:
        pasta = Path(os.environ.get("ESPECIALISTAS_SAIDA", "/a0/usr/workdir/especialistas")) / "ilegiveis"
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / f"{time.strftime('%Y%m%d-%H%M%S')}.txt").write_text(f"erro: {r.get('erro')}\n\n{r.get('texto')}", encoding="utf-8")
    except OSError:
        pass


def _corrigir(spec: dict, falta: list, material, login: str) -> tuple[dict, dict]:
    """One correction of the ficha by the Designer: (the answer, the new spec or {}). 12/11, the simulation: three
    pieces of one week died on "o designer não respondeu à correção (resposta ilegível)" after a single try, and the
    same correction, asked again, came back fine. An unreadable answer is kept and asked once more."""
    r2 = {}
    for _ in range(2):
        r2 = chamar("designer", _tarefa_correcao(spec, falta, _evitar(material)), material, login=login)
        novo = _spec(r2, spec.get("_formato_pedido", ""))
        if novo:
            return r2, novo
        _guardar_ilegivel(r2)
    return r2, {}


def _volta(briefing, material: dict, spec: dict, r: dict, login: str, correcoes: int | None = None) -> dict:
    """One round: check the ficha (with up to CORRECOES fixes against the template's schema), render it, judge it."""
    falta, arquivos, render = [], [], ""
    previa, narracao, folha = [], "", ""
    if r["erro"]:
        falta.append(f"o designer não respondeu ({r['erro']})")
    elif not spec:
        falta.append("o designer não devolveu uma ficha legível")
    else:
        falta += _conferir_spec(spec)
        # 22/10, real runs: fichas over the template's limits, "_origem" missing, telas without a file, a video
        # shorter than the template allows (refused only when rendering). The Designer gets the template's exact
        # schema, an example and the errors; CORRECOES tries in all, for the ficha and the render together.
        tentativas = CORRECOES if correcoes is None else correcoes
        while True:
            while tentativas and spec.get("motor") == "molde" and any(f.startswith("ficha:") for f in falta):
                tentativas -= 1
                r2, novo = _corrigir(spec, falta, material, login)
                if not novo:
                    falta.append(f"o designer não respondeu à correção ({r2['erro'] or 'resposta ilegível'})")
                    tentativas = 0
                    break
                spec, falta = novo, _conferir_spec(novo)
            arquivos, render, previa, narracao, folha, falta = _renderizar(spec, falta)
            # 11/11: the render's own check (cut text, text outside the Instagram area) goes back to the Designer
            # too, not to the Crítico as a reason to reprove
            recusa = [f for f in falta if f.startswith(("o molde recusou a ficha", "a conferência do render achou problemas"))]
            if not (recusa and tentativas):
                break
            tentativas -= 1
            r2, novo = _corrigir(spec, recusa, material, login)
            if not novo:
                falta.append(f"o designer não respondeu à correção ({r2['erro'] or 'resposta ilegível'})")
                break
            spec, falta = novo, _conferir_spec(novo)
    formato = str(spec.get("formato") or "").lower()
    imagens = _quadros_para_o_critico(previa, folha) if previa else [a for a in arquivos if Path(a).suffix.lower() in EXT_IMAGEM]
    julgar = {"briefing": briefing, "ficha": spec or r["texto"] or "(vazia)", "problemas": falta, "imagens": imagens}
    if previa:  # 22/10: he read the zoomed frames as a cropped screen and asked for frames he was not sent
        julgar["quadros_da_previa"] = _legendas_dos_quadros(imagens, folha)
        julgar["como_ver_a_previa"] = (
            "Cada imagem está descrita em \"quadros_da_previa\". Tela cortada de verdade é a tela marcada INTEIRA sem o "
            "menu ou com borda fora do quadro: isso continua reprovando. O quadro marcado ZOOM é a câmera aproximando "
            "o destaque da mesma tela, que você vê inteira na imagem indicada: não reprove o zoom como recorte. " + 
            "É a prévia de um vídeo narrado: a primeira imagem é a folha com um quadro de cada cena, as outras são cenas "
            "inteiras, sempre a do fim entre elas. Em cada tela do sistema, a tela entra inteira (tema escuro, com o menu) "
            "e depois a câmera aproxima o destaque, como o Matheus pediu (decisão #85: vídeo com zoom e movimento); o "
            "quadro do zoom não é recorte. A narração são as \"falas\" da ficha, uma por cena, na ordem das cenas. Esta "
            "revisão decide: aprovada, o vídeo é feito e publicado sem passar pelo Matheus (decisão dele, 04/11); "
            "não reprove por falta da aprovação dele.")
    tipo = ("carrossel" if formato == "carrossel" or spec.get("motor") == "carrossel_raiz"
            else "reel" if formato == "reel" else "post")
    if spec.get("motor") == "molde" and not arquivos and not previa and falta:
        # 12/11: with no art the Crítico could only say "a arte não veio" and that became the reason the Gestor and
        # the next redo read; the real reason is what failed before the render
        critica = {"veredito": "reprova", "motivos": [f"sem arte para julgar: {uma}" for uma in falta[:3]], "sugestoes": []}
    else:
        critica = criticar(tipo, julgar, login=login)
    if not spec and critica["veredito"] == "aprova":  # nothing to approve: fail closed
        critica = {**critica, "veredito": "reprova", "motivos": ["sem ficha do designer"] + critica["motivos"]}
    out = {"spec": spec, "arquivos": arquivos, "critica": critica, "falta": falta, "render": render}
    if previa:
        out.update(previa=previa, folha=folha, narracao=narracao, video_pendente=not falta)
    return out


INTEIRA = re.compile(r"(p\d+)-inteira\.(jpe?g|png)$", re.I)


def _espalhar(lista: list, n: int) -> list:
    if n <= 0:
        return []
    if len(lista) <= n:
        return list(lista)
    if n == 1:
        return [lista[-1]]
    passo = (len(lista) - 1) / (n - 1)
    return [lista[round(i * passo)] for i in range(n)]


def _quadros_para_o_critico(previa: list, folha: str) -> list:
    """What fits in the Crítico's MAX_IMAGENS: the contact sheet (every scene), then frames spread over the video
    with the last one always in. 10/11: a screen shown whole and then zoomed (pNN-inteira.jpg + pNN.jpg) goes as a
    pair, so the Crítico sees the whole screen with the menu next to its zoom (up to 3 pairs; the rest in the sheet)."""
    vagas = MAX_IMAGENS - (1 if folha else 0)
    nomes = {Path(a).name: a for a in previa}
    pares = [(a, nomes[f"{INTEIRA.search(Path(a).name).group(1)}.{INTEIRA.search(Path(a).name).group(2)}"])
             for a in previa if INTEIRA.search(Path(a).name)
             and f"{INTEIRA.search(Path(a).name).group(1)}.{INTEIRA.search(Path(a).name).group(2)}" in nomes]
    if len(previa) <= vagas:
        escolhidos = list(previa)
    elif not pares:
        escolhidos = _espalhar(previa, vagas)
    else:
        usados = _espalhar(pares, min(len(pares), max(0, (vagas - 3) // 2)))
        dentro = {x for par in usados for x in par}
        resto = [a for a in previa if a not in {x for par in pares for x in par}]
        ultimo = [resto[-1]] if resto else []
        outros = _espalhar(resto[:-1], vagas - len(dentro) - len(ultimo))
        escolhidos = [a for a in previa if a in dentro or a in outros or a in ultimo]
    return ([folha] if folha else []) + escolhidos


def _legendas_dos_quadros(imagens: list, folha: str) -> list[str]:
    """What each image the Crítico gets is, in order: the sheet, a scene, a whole screen, or the intended zoom on it."""
    saida, inteiras = [], {}
    for k, a in enumerate(imagens, 1):
        nome = Path(a).name
        achado = INTEIRA.search(nome)
        cena = re.match(r"p(\d+)", nome)
        if folha and a == folha:
            saida.append(f"imagem {k}: folha de contato (um quadro de cada cena; numa tela do sistema, a inteira e o zoom)")
        elif achado:
            inteiras[achado.group(1)] = k
            saida.append(f"imagem {k}: cena {int(cena.group(1))}, a tela do sistema INTEIRA, com o menu, antes da câmera "
                         "aproximar (é aqui que se confere tela inteira e tela cortada)")
        elif cena and f"p{cena.group(1)}" in inteiras:
            saida.append(f"imagem {k}: cena {int(cena.group(1))}, ZOOM intencional da câmera no destaque da mesma tela "
                         f"mostrada inteira na imagem {inteiras[f'p{cena.group(1)}']} (decisão #85: zoom e movimento): "
                         "não é recorte nem tela cortada")
        else:
            saida.append(f"imagem {k}: cena {int(cena.group(1))}" if cena else f"imagem {k}: {nome}")
    return saida


def _renderizar(spec: dict, falta: list) -> tuple:
    """(arquivos, render, previa, narracao, folha, falta) for the spec's motor; nothing renders while falta has items."""
    falta, arquivos, render = list(falta), [], ""
    previa, narracao, folha = [], "", ""
    motor = spec.get("motor")
    if motor == "carrossel_raiz":
        render = (f"no repositório (sessão de operador): criar infra/reels/{spec.get('pasta') or 'c_<nome>'}/index.html "
                  "sobre base/raiz-carrossel.css/js com o conceito desta ficha, depois "
                  f"python3 base/carrossel.py {spec.get('pasta') or 'c_<nome>'} e base/validar_carrossel.py")
        falta.append("render do carrossel da Raiz: cada peça tem HTML próprio (conceito livre do kit); "
                     "o plugin entrega a ficha, não os slides")
    elif motor == "video_kit_raiz":
        render = "no repositório erp-saas: projeto marketing/<nome>/ do kit de motion (skill motion-graphics)"
        falta.append("render do vídeo da Raiz: o kit de motion mora no repositório erp-saas, fora do alcance do agente")
    elif motor == "molde" and not falta:
        if (str(spec.get("marca") or "raiz").lower() == "raiz" and spec.get("molde") == "lanca-app"
                and isinstance(spec.get("ficha"), dict) and "selo" not in spec["ficha"]):
            spec["ficha"]["selo"] = ""  # 27/10: the Raiz launches nothing; the molde's "Lançamento" badge was reproved
        sem = _pode_renderizar()
        formato = str(spec.get("formato") or "carrossel")
        render = f"moldes/motor/render.py {spec.get('molde')} <ficha.json> --formato {formato}"
        if sem:
            falta.append(sem)
        elif formato == "carrossel":
            arquivos, problema = renderizar_molde(str(spec["molde"]), formato, spec["ficha"])
            if problema:
                falta.append(problema)
        else:  # a video: only the preview and the narration now; the video after the Crítico approves the preview
            feitos, problema = renderizar_molde(str(spec["molde"]), formato, spec["ficha"], previa=True)
            previa = [a for a in feitos if Path(a).suffix.lower() in EXT_IMAGEM and Path(a).name != "prev.jpg"]
            narracao = next((a for a in feitos if a.endswith(".m4a")), "")
            folha = next((a for a in feitos if Path(a).name == "prev.jpg"), "")
            if problema:
                falta.append(problema)
            elif not previa:
                falta.append("a prévia do vídeo não saiu")
    return arquivos, render, previa, narracao, folha, falta


def _tarefa_revisao(spec: dict, critica: dict) -> str:
    """The Crítico reproved: the same piece redone with his reasons (concept or template may change)."""
    return ("O Crítico reprovou a peça abaixo. Refaça a ficha resolvendo cada motivo (pode trocar o conceito ou o molde "
            "se o problema for esse) e devolva a ficha inteira em JSON, com \"motor\".\n\n## Motivos do Crítico\n"
            + "\n".join(f"- {m}" for m in critica.get("motivos") or [])
            + ("\n\n## Sugestões dele\n" + "\n".join(f"- {m}" for m in critica.get("sugestoes") or [])
               if critica.get("sugestoes") else "")
            + f"\n\n## Sua ficha\n{json.dumps(spec, ensure_ascii=False)[:6000]}\n\n{KIT}\n\n" + telas_do_sistema(spec.get("_formato_pedido", "")) + fotos_do_banco()
            + "Responda só com o JSON.")
