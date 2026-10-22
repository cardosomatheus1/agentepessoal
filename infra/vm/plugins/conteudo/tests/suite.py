"""Tests of conteudo (daily posts on @raiz.connect) that need no running agent and never touch Meta: a fake API stands
in for the Graph API. Run with implantar.py or: python3 infra/vm/plugins/conteudo/tests/suite.py"""

import datetime as dt
import json
import importlib.util
import os
import tempfile
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


class Falha(AssertionError):
    pass


def ok(cond, msg):
    if not cond:
        raise Falha(msg)


def _modulo():
    os.environ["CONTEUDO_PASTA"] = tempfile.mkdtemp(prefix="conteudo_teste_")
    spec = importlib.util.spec_from_file_location("conteudo_teste", RAIZ / "helpers" / "conteudo.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.especialistas = lambda: None  # the real Crítico calls a model; tests that want one pass a fake
    return m


def _ts(c, data: str, hora: str) -> float:
    return dt.datetime.fromisoformat(f"{data}T{hora}:00").replace(tzinfo=c._tz()).timestamp()


class ApiFalsa:
    def __init__(self, falhar_em: str = "", status: str = "FINISHED"):
        self.ig, self.chamadas, self.falhar_em, self.status, self.n = "IG1", [], falhar_em, status, 0

    def url(self, chave):
        return f"https://s3/{chave}?assinado"

    def post(self, caminho, params):
        self.chamadas.append(("POST", caminho, dict(params)))
        if self.falhar_em and self.falhar_em in caminho:
            if self.falhar_em == "media_publish":
                raise TimeoutError("caiu a conexão")
            return {"error": {"message": "permissão negada"}}
        self.n += 1
        return {"id": f"C{self.n}"}

    def get(self, caminho, params):
        self.chamadas.append(("GET", caminho, dict(params)))
        if params.get("fields") == "status_code":
            return {"status_code": self.status}
        return {"permalink": f"https://instagram.com/p/{caminho}"}


ITEM = {"id": "seg-pov", "data": "2026-10-14", "hora": "11:45", "tipo": "REELS", "arquivos": ["conteudo/semana1/pov.mp4"],
        "legenda": "POV: você vende salgado e chega mensagem às 23h. Marca quem já passou por isso."}
CARR = {"id": "ter-frases", "data": "2026-10-15", "hora": "11:45", "tipo": "CARROSSEL",
        "arquivos": [f"conteudo/semana1/frases/{i}.jpg" for i in range(1, 10)], "legenda": "Qual você mais ouve? Comenta o número."}

FOTO = {"id": "s3-foto", "data": "2026-10-17", "hora": "11:45", "tipo": "IMAGE", "arquivos": ["conteudo/semana3/ifood/foto.jpg"],
        "legenda": "Pedidos do iFood na Raiz Connect. Mais clareza para acompanhar os pedidos."}


class Suite:
    def __init__(self):
        self.resultados = []

    def t_critico_ve_o_video_quadros_e_narracao(self):
        # 21/10 (Matheus: "pode fazer o do Crítico ver o vídeo"): a Reel goes to the Crítico with frames and narration
        import shutil
        import subprocess
        if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
            return  # the VM and CI have ffmpeg; a machine without it cannot make the test video
        c = _modulo()
        origem = Path(tempfile.mkdtemp()) / "v.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=4:size=320x568:rate=10",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=4", "-shortest", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", str(origem)], check=True)
        baixados, ouvidos = [], []
        c._OUVIR = lambda caminho: ouvidos.append(caminho) or "[0.6s] Pediu pelo iFood?\n[3.0s] Experimente grátis."
        reel = dict(ITEM, id="reel-critico")
        m = c.material_do_video(reel, [], baixar=lambda chave, destino: baixados.append(chave) or shutil.copy(origem, destino))
        ok(baixados == ["conteudo/semana1/pov.mp4"], "baixa o vídeo do S3 uma vez")
        ok(len(m["imagens"]) == 6 and all(Path(i).exists() for i in m["imagens"]), f"6 quadros: {m['imagens']}")
        ok("instante de transição" in m["quadros"], "o Crítico sabe que a troca de cena tem folga (22/10)")
        ok(m["quadros"].startswith("ordem das imagens: 1 = segundo 0.2") and "6 = segundo 3.4" in m["quadros"],
           f"a ordem e o segundo de cada quadro (o último perto do fim, onde fica a chamada): {m['quadros']}")
        ok(m["narracao"].startswith("[0.6s] Pediu pelo iFood?") and ouvidos[0].endswith("narracao.mp3"),
           "a narração vem transcrita do áudio do vídeo")
        m2 = c.material_do_video(reel, ["/capa.jpg"], baixar=lambda *a: 1 / 0)
        ok(m2["imagens"][0] == "/capa.jpg" and m2["quadros"].startswith("ordem das imagens: 1 = capa"),
           "a capa vem primeiro; o vídeo já baixado não baixa de novo")
        c._OUVIR = lambda caminho: 1 / 0
        (c.PASTA / "cache" / "reel-critico" / "narracao.mp3").unlink()
        ok(c.material_do_video(reel, [])["narracao"].startswith("(narração não transcrita"),
           "transcrição que falha vira aviso, não erro")
        com_roteiro = c.material_do_video(dict(reel, roteiro="Pediu pelo iFood? Chegou no Raiz Connect!"), [])
        ok(com_roteiro["narracao"] == "Pediu pelo iFood? Chegou no Raiz Connect!", "roteiro do post vale sem transcrever")
        tipo, mat = c.material_do_post(dict(ITEM, id="reel-sem-arquivo"))
        ok("video" in mat and "não pôde ser aberto" in mat["video"], "vídeo que não baixa: o Crítico é avisado")

    def t_legenda_sem_emoji(self):
        c = _modulo()
        ok(c.validar_legenda("Marca quem já passou por isso.") == "", "texto puro passa")
        for ruim in ("Marca quem já passou 😅", "Comenta 👇", "Feito com carinho ❤️", "ok ✨"):
            ok("emoji" in c.validar_legenda(ruim), f"emoji recusado: {ruim!r}")
        ok("caracteres" in c.validar_legenda("a" * 2201), "limite de tamanho")
        ok("hashtags" in c.validar_legenda(" ".join(f"#t{i}" for i in range(31))), "limite de hashtags")
        ok(c.validar_legenda("Preço: R$ 9,50 (100%) e ação.") == "", "acentos, R$ e % não são emoji")

    def t_story_do_kit_regras_e_desenho(self):
        spec = importlib.util.spec_from_file_location("story_teste", RAIZ / "helpers" / "story.py")
        st = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(st)
        ok(st.validar({"layout": "dica", "manchete": "Confere o insumo que mais subiu."}) == "", "dica simples passa")
        ok("layout" in st.validar({"layout": "carrossel", "manchete": "x"}), "layout desconhecido")
        ok("emoji" in st.validar({"layout": "dica", "manchete": "Confere 😅"}), "sem emoji")
        ok("travessão" in st.validar({"layout": "dica", "manchete": "Confere — agora"}), "sem travessão")
        ok("valores de exemplo" in st.validar({"layout": "dica", "manchete": "Bolo a R$ 80"}), "R$ só com valores de exemplo")
        ok("tela real" in st.validar({"layout": "bastidor", "manchete": "Bastidor"}), "bastidor pede tela real")
        ok("não encontrado" in st.validar({"layout": "post-novo", "manchete": "x", "imagem": "/nao/existe.jpg"}), "imagem existe")
        ok("desconhecidos" in st.validar({"layout": "dica", "manchete": "x", "script": "alert(1)"}), "campo estranho fora")
        ok("emoji" in st.validar({"layout": "oferta", "preco": "R$ 197 😅"}), "o preço também passa pelas regras")
        ok(st.validar({"layout": "oferta"}) == "", "oferta sem preço (os detalhes ficam no link da bio)")
        ok("você não paga" not in (RAIZ / "story" / "story.html").read_text(encoding="utf-8"),
           "garantia do story padrão com as palavras aprovadas: a gente não cobra (decisão #22)")
        ok((RAIZ / "story" / "telas" / "curva-abc-custos.jpg").exists(), "há tela real para o bastidor")
        # 22/10, Matheus: "usaria tema escuro e n usaria esse formato de tela ... pq menu some": tela escura e inteira
        from PIL import Image, ImageStat
        for tela in sorted((RAIZ / "story" / "telas").iterdir()):
            with Image.open(tela) as im:
                ok(ImageStat.Stat(im.convert("L")).mean[0] < 70, f"{tela.name}: tela no tema escuro")
                ok(abs(im.size[0] / im.size[1] - 1.6) < 0.01, f"{tela.name}: tela inteira (16:10, com o menu)")
        mau = {"layout": "dica", "manchete": "</script><script>fetch('file:///etc/passwd')</script>"}
        pagina = st.injetar((RAIZ / "story" / "story.html").read_text(encoding="utf-8"), mau)
        ok(pagina.count("</script>") == (RAIZ / "story" / "story.html").read_text(encoding="utf-8").count("</script>") + 1
           and "\\u003c/script\\u003e" in pagina, "texto com </script> não fecha a tag")
        if not st._chrome():
            return  # without a browser the drawing is checked on the VM
        import importlib.util as iu
        from PIL import Image
        ok(iu.find_spec("playwright") or iu.find_spec("patchright"), "há playwright ou patchright para desenhar")
        saida = Path(tempfile.mkdtemp()) / "dica.jpg"
        st.renderizar({"layout": "bastidor", "manchete": "Pra onde vai o seu dinheiro?", "destaque": "seu dinheiro",
                       "tela": str(RAIZ / "story" / "telas" / "curva-abc-custos.jpg"),
                       "pergunta": "Responde aqui no direct: <b>qual</b> é o maior custo?"}, str(saida))
        with Image.open(saida) as im:
            ok(im.size == (1080, 1920) and im.format == "JPEG", f"story 1080x1920 em JPEG: {im.size} {im.format}")

    def t_story_um_por_dia_ao_lado_do_post(self):
        # 22/10, Matheus: "story sim todo dia": o story tem a vaga dele, ao lado do post do feed
        c = _modulo()
        story = {"id": "qui-story", "data": "2026-10-14", "hora": "09:00", "tipo": "STORY",
                 "arquivos": ["conteudo/stories/bastidor.jpg"], "legenda": "bastidor: a tela do estoque"}
        agora = _ts(c, "2026-10-13", "10:00")
        r = c.agendar([ITEM, story], agora)
        ok(r["ok"], f"post e story no mesmo dia: {r}")
        r = c.agendar([dict(story, id="outro-story")], agora)
        ok(not r["ok"] and "story" in r["erro"] and "um por dia" in r["erro"], "dois stories no mesmo dia, não")
        ok(not c.agendar([dict(story, id="s2", data="2026-10-15", arquivos=["conteudo/a.jpg", "conteudo/b.jpg"])], agora)["ok"],
           "story é um arquivo só")
        ok(c.agendar([dict(story, id="s3", data="2026-10-16", legenda="")], agora)["ok"], "story não precisa de legenda")
        eq = lambda a, b, m: ok(a == b, f"{m}: veio {a!r}")
        eq(c.devido(_ts(c, "2026-10-14", "09:05"))["id"], "qui-story", "às 9h sai o story")
        api = ApiFalsa()
        r = c.rodar(api, lambda t: None, _ts(c, "2026-10-14", "09:05"))
        eq(r["estado"], "publicada", "story publicado")
        criar = [x for x in api.chamadas if x[0] == "POST" and x[1] == "IG1/media"][0][2]
        eq((criar.get("media_type"), criar.get("image_url"), "caption" in criar),
           ("STORIES", "https://s3/conteudo/stories/bastidor.jpg?assinado", False), "STORIES com a imagem e sem legenda")
        eq(c.devido(_ts(c, "2026-10-14", "11:46"))["id"], "seg-pov", "o story não tira a vaga do post do dia")
        c.agendar([{"id": "s-video", "data": "2026-10-17", "hora": "09:00", "tipo": "STORY", "arquivos": ["conteudo/s/v.mp4"]}], agora)
        api2 = ApiFalsa()
        c.rodar(api2, lambda t: None, _ts(c, "2026-10-17", "09:01"))
        criar = [x for x in api2.chamadas if x[0] == "POST" and x[1] == "IG1/media"][0][2]
        ok(criar.get("video_url", "").startswith("https://s3/conteudo/s/v.mp4"), "story em vídeo vai como video_url")
        # replanejar e adiar respeitam as duas vagas: post e story no mesmo dia não é choque
        c.AUTOR["quem"] = "operador: teste"
        try:
            c.agendar([dict(CARR, id="feed-18", data="2026-10-18")], agora)
            r = c.replanejar([{"id": "feed-18", "data": "2026-10-16"}], agora)  # o dia 16 já tem story (s3)
            ok(r["ok"], f"post vai para dia que só tem story: {r}")
            r = c.replanejar([{"id": "s3", "data": "2026-10-14"}], agora)
            ok(not r["ok"] and "dois stories" in r["erro"], f"dois stories no mesmo dia, não: {r}")
            ok("2026-10-17" in c.adiar_a_partir("2026-10-16", 1, agora)["erro"], "story não cai em dia com story publicado")
            r = c.adiar_a_partir("2026-10-16", 2, agora)
            ok(r["ok"] and set(r["movidos"].values()) == {"2026-10-18"}, f"post e story vão juntos para o mesmo dia: {r}")
        finally:
            c.AUTOR["quem"] = "agente"

    def t_agendar_um_por_dia_e_tudo_ou_nada(self):
        c = _modulo()
        agora = _ts(c, "2026-10-13", "10:00")
        r = c.agendar([ITEM, CARR], agora)
        ok(r["ok"] and r["agendados"] == ["seg-pov", "ter-frases"], r)
        r = c.agendar([dict(ITEM, id="outro")], agora)
        ok(not r["ok"] and "um por dia" in r["erro"], "segundo post no mesmo dia é recusado")
        r = c.agendar([dict(CARR, id="x", data="2026-10-20"), dict(ITEM, id="y", data="2026-10-21", legenda="oi 😅")], agora)
        ok(not r["ok"] and "emoji" in r["erro"], "um item ruim recusa o lote")
        ok(len(c.carregar()["itens"]) == 2, "nada do lote recusado entrou")
        ok(not c.agendar([dict(ITEM, id="z", data="2026-10-12")], agora)["ok"], "data no passado")
        ok(not c.agendar([dict(ITEM, id="w", data="2026-10-22", arquivos=["outro/x.mp4"])], agora)["ok"], "só arquivos de conteudo/")
        ok(not c.agendar([dict(CARR, id="v", data="2026-10-23", arquivos=["conteudo/a.png", "conteudo/b.png"])], agora)["ok"],
           "carrossel só com .jpg")

    def t_devido_so_na_hora(self):
        c = _modulo()
        c.agendar([ITEM], _ts(c, "2026-10-13", "10:00"))
        ok(c.devido(_ts(c, "2026-10-14", "11:44")) is None, "antes da hora: nada")
        ok(c.devido(_ts(c, "2026-10-14", "11:46"))["id"] == "seg-pov", "na hora: o post do dia")
        ok(c.devido(_ts(c, "2026-10-15", "11:46")) is None, "outro dia: nada")

    def t_publica_reel_uma_vez(self):
        c = _modulo()
        c.agendar([ITEM], _ts(c, "2026-10-13", "10:00"))
        api, avisos = ApiFalsa(), []
        r = c.rodar(api, avisos.append, _ts(c, "2026-10-14", "11:50"), dormir=lambda s: None)
        ok(r["estado"] == "publicada" and r["media_id"] == "C2", r)
        cria = api.chamadas[0]
        ok(cria[1] == "IG1/media" and cria[2]["media_type"] == "REELS" and cria[2]["video_url"].startswith("https://s3/conteudo/"),
           "cria o Reel com o link do S3")
        ok(cria[2]["caption"] == ITEM["legenda"], "legenda exata")
        ok(("POST", "IG1/media_publish", {"creation_id": "C1"}) in api.chamadas, "publica o contêiner pronto")
        ok(not avisos, "deu certo: não incomoda o Matheus")
        ok(c.rodar(api, avisos.append, _ts(c, "2026-10-14", "12:30"), dormir=lambda s: None) is None, "não publica duas vezes")
        ok(c.carregar()["itens"][0]["permalink"].startswith("https://instagram.com/p/"), "guarda o link do post")

    def t_reel_sai_com_capa(self):
        # 14/10: "Raiz invisível" went out with a black cover (first frame); a Reel now always names its cover
        c = _modulo()
        agora = _ts(c, "2026-10-13", "10:00")
        ok(c.agendar([dict(ITEM, capa="conteudo/semana2/capa.png")], agora)["ok"] is False, "capa tem de ser .jpg do S3")
        ok(c.agendar([dict(CARR, capa="conteudo/semana1/capa.jpg")], agora)["ok"] is False, "carrossel não tem capa")
        c.agendar([dict(ITEM, capa="conteudo/semana2/capa-pov.jpg"), dict(ITEM, id="sem-capa", data="2026-10-15")], agora)
        api = ApiFalsa()
        c.rodar(api, lambda t: None, _ts(c, "2026-10-14", "11:50"), dormir=lambda s: None)
        ok(api.chamadas[0][2].get("cover_url") == "https://s3/conteudo/semana2/capa-pov.jpg?assinado", f"capa pela imagem: {api.chamadas[0]}")
        api = ApiFalsa()
        c.rodar(api, lambda t: None, _ts(c, "2026-10-15", "11:50"), dormir=lambda s: None)
        ok(api.chamadas[0][2].get("thumb_offset") == str(c.CAPA_MS) and "cover_url" not in api.chamadas[0][2],
           f"sem imagem, a capa é um quadro depois da abertura: {api.chamadas[0]}")
        c.AUTOR["quem"] = "operador: capa"
        c.agendar([dict(ITEM, id="depois", data="2026-10-20")], agora)
        ok(c.replanejar([{"id": "depois", "capa": "conteudo/semana2/capa-depois.jpg"}], agora)["ok"], "o operador põe capa num Reel já agendado")
        ok(next(i for i in c.carregar()["itens"] if i["id"] == "depois")["capa"] == "conteudo/semana2/capa-depois.jpg", "capa gravada")

    def t_publica_carrossel(self):
        c = _modulo()
        c.agendar([CARR], _ts(c, "2026-10-13", "10:00"))
        api = ApiFalsa()
        r = c.rodar(api, lambda t: None, _ts(c, "2026-10-15", "12:00"), dormir=lambda s: None)
        filhos = [x for x in api.chamadas if x[0] == "POST" and x[2].get("is_carousel_item") == "true"]
        ok(len(filhos) == 9, "uma imagem por tela")
        mae = next(x for x in api.chamadas if x[2].get("media_type") == "CAROUSEL")
        ok(mae[2]["children"] == ",".join(f"C{i}" for i in range(1, 10)), "o carrossel junta as telas na ordem")
        ok(r["estado"] == "publicada", r)

    def t_falha_antes_de_publicar_avisa_e_para(self):
        c = _modulo()
        c.agendar([ITEM], _ts(c, "2026-10-13", "10:00"))
        avisos = []
        r = c.rodar(ApiFalsa(falhar_em="IG1/media"), avisos.append, _ts(c, "2026-10-14", "11:50"), dormir=lambda s: None)
        ok(r["estado"] == "falhou" and "permissão negada" in r["erro"], r)
        ok(avisos and avisos[0].startswith("pendente:") and "Nada foi publicado" in avisos[0], "avisa com pendente:")
        ok(c.devido(_ts(c, "2026-10-14", "12:30")) is None, "não tenta de novo sozinho")

    def t_tentar_de_novo_so_pelo_operador(self):
        c = _modulo()
        c.agendar([ITEM], _ts(c, "2026-10-13", "10:00"))
        c.rodar(ApiFalsa(falhar_em="IG1/media"), lambda t: None, _ts(c, "2026-10-14", "11:50"), dormir=lambda s: None)
        ok(not c.tentar_de_novo("seg-pov")["ok"], "o agente sozinho não manda tentar de novo")
        c.AUTOR["quem"] = "operador: link do S3 pelo proxy"
        r = c.tentar_de_novo("seg-pov")
        ok(r["ok"], r)
        it = c.carregar()["itens"][0]
        ok(it["estado"] == "pendente" and "erro" not in it and "permissão negada" in it["erro_anterior"], it)
        ok(c.devido(_ts(c, "2026-10-14", "12:30"))["id"] == "seg-pov", "volta a ser o post do dia")
        r = c.rodar(ApiFalsa(), lambda t: None, _ts(c, "2026-10-14", "12:31"), dormir=lambda s: None)
        ok(r["estado"] == "publicada", r)
        ok(not c.tentar_de_novo("seg-pov")["ok"], "publicada não volta para a fila")
        ok(not c.tentar_de_novo("nao-existe")["ok"], "id desconhecido")

    def t_cancelar_libera_o_dia(self):
        # 14/10: the old brigadeiro Reel gives its day to the kit version
        c = _modulo()
        c.agendar([ITEM], _ts(c, "2026-10-13", "10:00"))
        ok(not c.cancelar("seg-pov")["ok"], "o agente sozinho não cancela")
        c.AUTOR["quem"] = "operador: troca pelo vídeo do kit"
        r = c.cancelar("seg-pov", "versão nova")
        ok(r["ok"] and c.carregar()["itens"][0]["estado"] == "cancelada", r)
        ok(c.devido(_ts(c, "2026-10-14", "11:50")) is None, "cancelado não é publicado")
        novo = {**ITEM, "id": "seg-pov-v2"}
        ok(c.agendar([novo], _ts(c, "2026-10-13", "11:00"))["ok"], "o dia ficou livre para o novo post")
        ok(not c.cancelar("seg-pov")["ok"], "cancelado não cancela de novo")
        c.rodar(ApiFalsa(), lambda t: None, _ts(c, "2026-10-14", "11:50"), dormir=lambda s: None)
        ok(not c.cancelar("seg-pov-v2")["ok"], "publicado não se cancela")

    def t_adiar_a_partir_de_um_dia(self):
        c = _modulo()
        agora = _ts(c, "2026-10-13", "21:30")
        c.agendar([ITEM, CARR, dict(ITEM, id="qui", data="2026-10-16")], agora)
        ok(not c.adiar_a_partir("2026-10-14", 1, agora)["ok"], "o agente sozinho não remarca")
        c.AUTOR["quem"] = "operador: video novo no dia 14"
        r = c.adiar_a_partir("2026-10-14", 1, agora)
        ok(r["ok"] and r["movidos"] == {"seg-pov": "2026-10-15", "ter-frases": "2026-10-16", "qui": "2026-10-17"}, r)
        itens = {i["id"]: i for i in c.carregar()["itens"]}
        ok(itens["seg-pov"]["hora"] == "11:45" and all(i["estado"] == "pendente" for i in itens.values()), "hora e estado mantidos")
        novo = dict(ITEM, id="video-novo", arquivos=["conteudo/semana2/raiz-invisivel-9x16.mp4"])
        ok(c.agendar([novo], agora)["ok"], "o dia liberado aceita o post novo")
        ok(c.devido(_ts(c, "2026-10-14", "11:46"))["id"] == "video-novo", "no dia 14 sai o novo")
        diario = [json.loads(l) for l in (c.PASTA / "diario.jsonl").read_text().splitlines()]
        ok(any(e.get("remarcado") and e["item"] == "seg-pov" and e["para_data"] == "2026-10-15" and e["quem"].startswith("operador")
               for e in diario), "o diário registra a remarcação e quem fez")
        ok(not c.adiar_a_partir("2026-10-01", 1, agora)["ok"], "data no passado")

    def t_adiar_nao_cai_em_dia_ocupado(self):
        c = _modulo()
        agora = _ts(c, "2026-10-13", "10:00")
        c.agendar([ITEM, CARR], agora)
        d = c.carregar()
        d["itens"][1]["estado"] = "publicada"  # o do dia 15 já saiu (ex.: publicado à mão)
        c._gravar(d)
        c.AUTOR["quem"] = "operador: teste"
        r = c.adiar_a_partir("2026-10-14", 1, agora)
        ok(not r["ok"] and "2026-10-15" in r["erro"], f"não empurra um post para cima de outro: {r}")
        ok(c.carregar()["itens"][0]["data"] == "2026-10-14", "recusado: nada se mexeu")
        r = c.adiar_a_partir("2026-10-14", 2, agora)
        ok(r["ok"] and r["movidos"] == {"seg-pov": "2026-10-16"}, "só os pendentes se movem, e cabem dois dias depois")

    def t_replanejar_troca_dias_e_legendas(self):
        # 14/10: the week is redone around the new offer: days swap and captions change, all or nothing
        c = _modulo()
        agora = _ts(c, "2026-10-14", "16:00")
        c.agendar([dict(ITEM, id="a", data="2026-10-15"), dict(CARR, id="b", data="2026-10-16"),
                   dict(ITEM, id="pub", data="2026-10-17")], agora)
        d = c.carregar()
        d["itens"][2]["estado"] = "publicada"
        c._gravar(d)
        ok(not c.replanejar([{"id": "a", "data": "2026-10-16"}], agora)["ok"], "o agente sozinho não replaneja")
        c.AUTOR["quem"] = "operador: semana nova da oferta"
        r = c.replanejar([{"id": "a", "data": "2026-10-16"}], agora)
        ok(not r["ok"] and "2026-10-16" in r["erro"], f"não deixa dois posts no mesmo dia: {r}")
        r = c.replanejar([{"id": "a", "data": "2026-10-16", "legenda": "Nova legenda da oferta."},
                          {"id": "b", "data": "2026-10-15"}], agora)
        ok(r["ok"] and r["agenda"] == {"a": "2026-10-16", "b": "2026-10-15"}, f"troca os dois dias de uma vez: {r}")
        itens = {i["id"]: i for i in c.carregar()["itens"]}
        ok(itens["a"]["legenda"] == "Nova legenda da oferta." and itens["b"]["legenda"] == CARR["legenda"], "só a legenda pedida muda")
        ok(not c.replanejar([{"id": "pub", "data": "2026-10-20"}], agora)["ok"], "post já publicado não muda")
        r = c.replanejar([{"id": "a", "legenda": "Com emoji 🍰"}, {"id": "b", "data": "2026-10-20"}], agora)
        ok(not r["ok"] and c.carregar()["itens"][1]["data"] == "2026-10-15", f"legenda ruim recusa tudo, nada se mexe: {r}")
        ok(not c.replanejar([{"id": "b", "data": "2026-10-10"}], agora)["ok"], "data no passado")
        diario = [json.loads(l) for l in (c.PASTA / "diario.jsonl").read_text().splitlines()]
        ok(any(e.get("replanejado") and e["item"] == "a" and e["legenda_mudou"] for e in diario), "o diário registra")

    def t_link_do_arquivo_pelo_proxy(self):
        """13/10: the container has no AWS credentials; the link comes from the host proxy."""
        import io
        import json
        import urllib.error
        import urllib.request
        c = _modulo()
        api, pedidos, orig = c.Api("tok", "IG1"), [], urllib.request.urlopen

        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def falso(req, timeout=None):
            pedidos.append((req.full_url, json.loads(req.data)))
            if "falta" in json.loads(req.data)["chave"]:
                raise urllib.error.HTTPError(req.full_url, 400, "x", {}, io.BytesIO(json.dumps({"error": "arquivo não encontrado"}).encode()))
            return Resp(b'{"url": "https://s3/assinado"}')
        urllib.request.urlopen = falso
        try:
            ok(api.url("conteudo/semana1/pov.mp4") == "https://s3/assinado", "devolve o link do proxy")
            ok(pedidos[0] == ("http://host.docker.internal:8787/arquivos/conteudo", {"chave": "conteudo/semana1/pov.mp4"}), pedidos)
            try:
                api.url("conteudo/falta.mp4")
                ok(False, "arquivo que não existe deve dar erro")
            except RuntimeError as exc:
                ok("não encontrado" in str(exc), str(exc))
        finally:
            urllib.request.urlopen = orig

    def t_video_recusado_pela_meta(self):
        c = _modulo()
        c.agendar([ITEM], _ts(c, "2026-10-13", "10:00"))
        api = ApiFalsa(status="ERROR")
        r = c.rodar(api, lambda t: None, _ts(c, "2026-10-14", "11:50"), dormir=lambda s: None)
        ok(r["estado"] == "falhou" and "recusou" in r["erro"], r)
        ok(not any(x[1].endswith("media_publish") for x in api.chamadas), "nada publicado")

    def t_publicacao_sem_confirmacao_fica_incerta(self):
        c = _modulo()
        c.agendar([ITEM], _ts(c, "2026-10-13", "10:00"))
        avisos = []
        r = c.rodar(ApiFalsa(falhar_em="media_publish"), avisos.append, _ts(c, "2026-10-14", "11:50"), dormir=lambda s: None)
        ok(r["estado"] == "incerta", r)
        ok("Confira o perfil" in avisos[0], "pede para conferir antes de repetir")
        ok(c.devido(_ts(c, "2026-10-14", "13:00")) is None, "incerta nunca é repetida sozinha")
        try:
            c._mudar(c.carregar()["itens"][0], "pendente")
            ok(False, "incerta → pendente é proibido")
        except c.TransicaoInvalida:
            pass

    def t_diario_registra_quem(self):
        c = _modulo()
        c.AUTOR["quem"] = "operador: teste"
        c.agendar([ITEM], _ts(c, "2026-10-13", "10:00"))
        linhas = (c.PASTA / "diario.jsonl").read_text(encoding="utf-8").strip().splitlines()
        ok(linhas and '"operador: teste"' in linhas[-1], "o diário guarda quem mudou")

    def t_agenda_mostra_os_dias_vazios(self):
        # 14/10: the weekly routine must see the days with no post before they happen (the plan: 1 a day)
        c = _modulo()
        c.agendar([ITEM, CARR], _ts(c, "2026-10-13", "10:00"))
        r = c.agenda_proxima(4, _ts(c, "2026-10-14", "08:00"))
        ok([d["data"] for d in r["dias"]] == ["2026-10-14", "2026-10-15", "2026-10-16", "2026-10-17"], "4 dias a partir de hoje")
        ok(r["dias"][0]["itens"][0]["id"] == "seg-pov" and r["dias"][1]["itens"][0]["id"] == "ter-frases", "cada post no seu dia")
        ok(r["vazios"] == ["2026-10-16", "2026-10-17"], f"os dias sem post aparecem: {r['vazios']}")

    def t_desempenho_soma_a_semana(self):
        # 14/10: the weekly numbers come from the Graph API; old posts stay out, a post without metrics does not break it
        c = _modulo()

        class ApiLeitura(ApiFalsa):
            def get(self, caminho, params):
                self.chamadas.append(("GET", caminho, dict(params)))
                if caminho == "IG1/media":
                    return {"data": [
                        {"id": "M1", "media_product_type": "REELS", "timestamp": "2026-10-14T14:45:54+0000", "permalink": "p1"},
                        {"id": "M2", "media_product_type": "FEED", "timestamp": "2026-10-12T14:45:54+0000", "permalink": "p2"},
                        {"id": "M3", "media_product_type": "REELS", "timestamp": "2026-09-01T14:45:54+0000", "permalink": "p3"}]}
                if caminho == "M1/insights":
                    return {"data": [{"name": n, "values": [{"value": v}]} for n, v in
                                     (("reach", 120), ("saved", 4), ("likes", 9), ("comments", 2), ("shares", 1), ("views", 300))]}
                if caminho == "M2/insights":
                    return {"error": {"message": "métrica indisponível"}}
                if caminho == "IG1":
                    return {"followers_count": 86}
                return {}
        api = ApiLeitura()
        r = c.desempenho(api, 7, _ts(c, "2026-10-15", "09:00"))
        ok(r["ok"] and [p["media_id"] for p in r["posts"]] == ["M1", "M2"], f"só os posts da semana: {r}")
        ok(r["total"]["reach"] == 120 and r["total"]["saved"] == 4 and r["seguidores"] == 86, "soma e seguidores")
        ok(r["posts"][1].get("erro") and r["posts"][1]["reach"] == 0, "post sem métricas não derruba o relatório")
        ok(not any(m == "POST" for m, _, _ in api.chamadas), "desempenho só lê")

    def t_ferramenta_so_muda_pela_semana(self):
        # 20/10: the tool proposes and approves the week (semana.py) and releases a blocked post on his word; it never
        # schedules, changes or publishes a post by itself
        tool = (RAIZ / "tools" / "conteudo.py").read_text(encoding="utf-8")
        ok("agenda_proxima" in tool and "desempenho" in tool, "a ferramenta usa o helper")
        for proibido in ("agendar(", "replanejar(", "c.rodar(", "tentar_de_novo(", "adiar_a_partir(", "cancelar(",
                         "trocar_formato("):
            ok(proibido not in tool, f"a ferramenta não muda a agenda ({proibido})")
        for acao in ("propor_semana", "aprovar_semana", '"semana"', "liberar_post"):
            ok(acao in tool, f"a ferramenta oferece {acao}")
        prompt = (RAIZ / "prompts" / "agent.system.tool.conteudo.md").read_text(encoding="utf-8")
        ok(all(a in prompt for a in ("propor_semana", "aprovar_semana", "liberar_post")), "o agente sabe usar as ações novas")

    # ------------------------------------------------------------------ the week (helpers/semana.py) and the gate

    def _semana(self, esp="falso", reprovar=(3,), quebrar=(), video_pendente=False):
        """semana.py over a fresh conteudo, with a fake Designer/Crítico (or none) and local art files on disk."""
        c = _modulo()
        spec = importlib.util.spec_from_file_location("semana_teste", RAIZ / "helpers" / "semana.py")
        s = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(s)
        s._C["fixo"] = c
        arte = Path(tempfile.mkdtemp(prefix="conteudo_arte_"))
        chamadas = []

        class Esp:
            def desenhar(self, briefing):
                n = len(chamadas) + 1
                chamadas.append(briefing)
                if n in quebrar:
                    raise RuntimeError("motor de render fora")
                if briefing["formato"] == "REELS" and video_pendente:  # the moldes: preview and narration only
                    for nome in (f"p{n}-1.jpg", f"narracao{n}.m4a"):
                        (arte / nome).write_bytes(b"\xff\xd8\xff previa")
                    return {"spec": {"motor": "molde", "molde": "lanca-app", "formato": "reel",
                                     "ficha": {"_marca": "raiz", "falas": ["Oi"]}},
                            "arquivos": [], "falta": [], "render": "ok", "video_pendente": True,
                            "previa": [str(arte / f"p{n}-1.jpg")], "narracao": str(arte / f"narracao{n}.m4a"),
                            "critica": {"veredito": "aprova", "motivos": [], "sugestoes": []}}
                if briefing["formato"] == "REELS":
                    nomes = [f"r{n}.mp4", f"r{n}-capa.jpg"]
                elif briefing["formato"] == "IMAGE":
                    nomes = [f"f{n}.jpg"]
                else:
                    nomes = [f"c{n}-{k}.jpg" for k in (1, 2, 3)]
                for nome in nomes:
                    (arte / nome).write_bytes(b"\xff\xd8\xff arte")
                veredito = {"veredito": "reprova", "motivos": ["gancho fraco", "fala com o consumidor"], "sugestoes": []} \
                    if n in reprovar else {"veredito": "aprova", "motivos": [], "sugestoes": []}
                return {"spec": {"motor": "carrossel_raiz"}, "arquivos": [str(arte / x) for x in nomes], "critica": veredito,
                        "falta": [], "render": "ok"}

            def criticar(self, tipo, material):
                return {"veredito": "aprova", "motivos": []}
        c.especialistas = (lambda: Esp()) if esp == "falso" else (lambda: None)

        class StoryFalso:  # helpers/story.py draws with a browser; here a file is enough
            CAMPOS = ("layout", "manchete", "destaque", "texto", "chamada", "tela", "pergunta", "itens", "imagem")
            PASTA = RAIZ / "story"
            validar = staticmethod(lambda campos: "" if campos.get("layout") else "layout")

            @staticmethod
            def renderizar(campos, saida):
                if campos.get("layout") == "quebra":
                    raise ValueError("layout deve ser um de: dica, ...")
                Path(saida).parent.mkdir(parents=True, exist_ok=True)
                Path(saida).write_bytes(b"\xff\xd8\xff story")
                return saida
        s._S["fixo"] = StoryFalso
        return c, s, chamadas

    @staticmethod
    def _feed():
        formatos = ["CARROSSEL", "REELS", "CARROSSEL", "REELS"]
        return [{"titulo": f"Post {n}", "formato": f, "ideia": f"gancho {n}",
                 "legenda": f"Quanto custa de verdade a sua marmita? Post {n}, com valores de exemplo."}
                for n, f in enumerate(formatos, start=1)]

    @staticmethod
    def _stories():
        layouts = ["post-novo", "video-novo", "bastidor", "post-novo", "oferta", "video-novo", "dica"]
        return [{"layout": l, "manchete": f"Story {n}"} for n, l in enumerate(layouts, start=1)]

    def t_semana_propoe_4_no_feed_e_7_stories(self):
        # 22/10, Matheus: "4 por semana, 2 carrosseis e 2 videos e story sim todo dia"
        c, s, chamadas = self._semana()
        enviados = []
        agora = _ts(c, "2026-10-26", "07:50")  # a Monday
        r = s.propor(self._feed(), agora, enviar=lambda login, texto, botoes: enviados.append((login, texto, botoes)) or "",
                     stories=self._stories())
        ok(r["ok"] and r["semana"] == "s20261026-1" and r["enviada"], r)
        ok(len(chamadas) == 4 and all(b["marca"] == "raiz" and "emoji" in b["regras"] for b in chamadas),
           "só o feed vai ao Designer, com as regras da Raiz")
        ps = s.carregar("s20261026-1")["propostas"]
        feed = [(p["data"], p["tipo"], p["hora"]) for p in ps[:4]]
        ok(feed == [("2026-10-27", "CARROSSEL", "11:45"), ("2026-10-28", "REELS", "11:45"),
                    ("2026-10-30", "CARROSSEL", "11:45"), ("2026-11-01", "REELS", "11:45")], f"ter/sex carrossel, qua/dom vídeo: {feed}")
        st = ps[4:]
        ok([p["data"] for p in st] == [f"2026-10-{d}" for d in range(27, 32)] + ["2026-11-01", "2026-11-02"]
           and all(p["tipo"] == "STORY" and p["hora"] == "09:00" and p["arquivos"] for p in st), "um story por dia às 9h")
        ok(ps[2]["critica"]["veredito"] == "reprova" and all(p["critica"]["veredito"] == "aprova" for p in st),
           "a crítica vem junto de cada um, stories incluídos")
        ok(ps[1]["capa"].endswith("r2-capa.jpg"), "a imagem junto do vídeo vira a capa do Reel")
        ok(len(enviados) == 1, "uma mensagem só")
        login, texto, botoes = enviados[0]
        ok("4 no feed e 7 stories" in texto and "\n11. " in texto and "Story 09:00" in texto and "Crítico reprovou" in texto, texto)
        ok([b["id"] for b in botoes] == ["cs:matheus:s20261026-1:todas", "cs:matheus:s20261026-1:algumas",
                                         "cs:matheus:s20261026-1:refazer"] and botoes[0]["titulo"] == "✅ Aprovar 10 de 11", botoes)
        ok(all(len(b["id"].encode()) <= 64 for b in botoes), "cabe no callback do Telegram")
        ok(c.carregar()["itens"] == [], "propor não agenda nada")
        ok(not s.propor(self._feed()[:3], agora, enviar=lambda *a: "", stories=self._stories())["ok"], "menos de 4 no feed é recusado")
        tres = [dict(p, formato="CARROSSEL") for p in self._feed()]
        erro = s.propor(tres, agora, enviar=lambda *a: "", stories=self._stories())["erro"]
        ok("4 vaga(s) no feed" in erro and "ter 27/10 Carrossel" in erro and "qua 28/10 Reel" in erro, f"a mistura segue as vagas: {erro}")
        ok(not s.propor(self._feed(), agora, enviar=lambda *a: "", stories=self._stories()[:5])["ok"], "7 stories")

    def t_semana_sem_critico_nao_aprova_sozinha(self):
        c, s, _ = self._semana(esp=None)
        enviados = []
        feed = [dict(p, arquivos=["conteudo/semanas/x/a.jpg"]) for p in self._feed()]
        r = s.propor(feed, _ts(c, "2026-10-26", "07:50"), enviar=lambda l, t, b: enviados.append((t, b)) or "",
                     stories=self._stories())
        ok(r["ok"] and all(p["critico"] == "sem revisão" for p in r["propostas"]), r)
        texto, botoes = enviados[0]
        ok(texto.count("sem revisão do Crítico") == 11 and "não está instalado" in texto, texto)
        ok(c.carregar()["itens"] == [] and s.carregar(r["semana"])["estado"] == "proposta", "nada aprovado sozinho")
        # a Designer that breaks on one, and a story that cannot be drawn: they cannot be scheduled and say why
        c, s, _ = self._semana(quebrar=(4,))
        st = self._stories()
        st[0] = {"layout": "quebra", "manchete": "x"}
        r = s.propor(self._feed(), _ts(c, "2026-10-26", "07:50"), enviar=lambda *a: "", stories=st)
        ps = s.carregar(r["semana"])["propostas"]
        ok(ps[3]["problema"].startswith("o Designer não entregou") and "render fora" in ps[3]["problema"], ps[3])
        ok(ps[4]["problema"].startswith("o story não foi desenhado") and not ps[4]["tipo"], ps[4])

    def t_semana_aprovar_todas_escreve_a_agenda(self):
        c, s, _ = self._semana()
        agora = _ts(c, "2026-10-26", "07:50")
        s.propor(self._feed(), agora, enviar=lambda *a: "", stories=self._stories())
        subidos = []
        r = s.botao("matheus", "cs:matheus:s20261026-1:todas", subir=lambda local, chave: subidos.append((local, chave)))
        ok("Agendados" in r["mensagem"] and "Não agendei" not in r["mensagem"], r)
        itens = {i["id"]: i for i in c.carregar()["itens"]}
        ok(len(itens) == 10 and "s20261026-1-3" not in itens, f"a reprovada fica de fora do 'todas': {sorted(itens)}")
        for i in itens.values():
            ok(c._validar_item(i) == "" and i["estado"] == "pendente", f"formato da agenda: {i}")
            ok(all(a.startswith("conteudo/semanas/s20261026-1/") for a in i["arquivos"]), i["arquivos"])
            ok("liberado" not in i and i["origem"]["semana"] == "s20261026-1", i)
        ok(sum(1 for i in itens.values() if i["tipo"] == "STORY" and i["hora"] == "09:00") == 7, "os 7 stories na agenda")
        reel = itens["s20261026-1-2"]
        ok(reel["tipo"] == "REELS" and reel["capa"].endswith("r2-capa.jpg"), reel)
        ok(len(subidos) == sum(len(i["arquivos"]) + (1 if i.get("capa") else 0) for i in itens.values()), "cada arquivo subiu")
        ok((c.PASTA / "cache" / "s20261026-1-1" / "c1-1.jpg").exists(), "cópia local para o Crítico da publicação")
        # the daily publish: the story at 9h, the carousel at 11:45, the same day (the gate's Crítico approves)
        aprova = type("C", (), {"criticar": lambda self, t, m: {"veredito": "aprova"}})()
        api = ApiFalsa()
        pub = c.rodar(api, lambda t: None, _ts(c, "2026-10-27", "09:05"), dormir=lambda x: None, critico=aprova)
        ok(pub["estado"] == "publicada" and any(x[2].get("media_type") == "STORIES" for x in api.chamadas), pub)
        api = ApiFalsa()
        pub = c.rodar(api, lambda t: None, _ts(c, "2026-10-27", "11:50"), dormir=lambda x: None, critico=aprova)
        ok(pub["estado"] == "publicada" and any(x[2].get("media_type") == "CAROUSEL" for x in api.chamadas), "o carrossel do dia")
        de_novo = s.botao("matheus", "cs:matheus:s20261026-1:todas", subir=lambda *a: None)["mensagem"]
        ok(de_novo.startswith("Nada para agendar") and "Ainda esperando você: 3" in de_novo, f"aprovar de novo não duplica: {de_novo}")
        ok(len(c.carregar()["itens"]) == 10, "nada duplicado")
        ok(s.botao("outra", "cs:matheus:s20261026-1:todas") == {}, "botão de outra pessoa não vale")

    # ---- 22/10, Matheus: "Se o crítico rejeita, automáticamente deveria ser refeito, e não logo antes de postar,
    # durante a etapa de criação"

    def t_semana_story_reprovado_e_refeito_na_criacao(self):
        c, s, _ = self._semana()
        pedidos, julgados = [], []

        class Esp:
            def desenhar(self, briefing):
                return {"spec": {"motor": "carrossel_raiz"}, "arquivos": [], "falta": ["sem arte"], "render": "",
                        "critica": {"veredito": "aprova", "motivos": [], "sugestoes": []}}

            def criticar(self, tipo, material):
                julgados.append(material["legenda"])
                if tipo == "story" and material["legenda"] == "Story 5":
                    return {"veredito": "reprova", "motivos": ["diz você não paga"]}
                return {"veredito": "aprova", "motivos": []}

            def chamar(self, papel, tarefa, material):
                pedidos.append((papel, tarefa, material))
                return {"texto": json.dumps({"layout": "oferta", "manchete": "Story 5 refeito", "senha": "x"}), "erro": ""}
        c.especialistas = lambda: Esp()
        r = s.propor(self._feed(), _ts(c, "2026-10-26", "07:50"), enviar=lambda *a: "", stories=self._stories())
        p5 = next(p for p in s.carregar(r["semana"])["propostas"] if p["legenda"].startswith("Story 5"))
        ok(len(pedidos) == 1 and pedidos[0][0] == "designer" and "diz você não paga" in pedidos[0][1], "o Designer refaz com o motivo")
        ok(p5["critica"]["veredito"] == "aprova" and p5["spec"]["story"] == {"layout": "oferta", "manchete": "Story 5 refeito"},
           f"a versão refeita é a que vai ao Matheus, só com campos do story: {p5}")
        ok(p5["arquivos"][0].endswith("story-9-r1.jpg") and Path(p5["arquivos"][0]).exists(), p5["arquivos"])
        # the Designer gives nothing usable: stays reproved after the tries, never approved by itself
        c2, s2, _ = self._semana()
        Esp.chamar = lambda self, papel, tarefa, material: {"texto": "não sei", "erro": ""}
        Esp.criticar = lambda self, tipo, material: {"veredito": "reprova" if tipo == "story" else "aprova", "motivos": ["fraco"]}
        c2.especialistas = lambda: Esp()
        r = s2.propor(self._feed(), _ts(c2, "2026-10-26", "07:50"), enviar=lambda *a: "", stories=self._stories())
        ok(all(p["critico"] == "reprova" for p in r["propostas"] if p["tipo"] == "STORY"), r["propostas"])
        # a redone story never points at a file outside the system's screens
        for fora in ({"layout": "bastidor", "manchete": "x", "tela": "/etc/passwd"}, {"layout": "dica", "imagem": "/root/a.jpg"}):
            Esp.chamar = lambda self, papel, tarefa, material, f=fora: {"texto": json.dumps(f), "erro": ""}
            ok(s2._refazer_story(Esp(), {"layout": "dica"}, {"motivos": ["x"]}, Path(tempfile.mkdtemp()) / "s.jpg") is None, fora)

    def _arquivo_falso(self):
        return {"url": lambda chave: "https://s3/" + chave,
                "baixar": lambda link, caminho: Path(caminho).write_bytes(b"\xff\xd8 " + link.encode())}

    def t_conferencia_antecipada_aprova_e_vale_na_hora(self):
        c = _modulo()
        story = {"id": "st", "data": "2026-10-15", "hora": "09:00", "tipo": "STORY", "arquivos": ["conteudo/st/a.jpg"],
                 "legenda": "qua: dica"}
        longe = dict(ITEM, id="longe", data="2026-10-18", tipo="CARROSSEL", arquivos=["conteudo/l/1.jpg", "conteudo/l/2.jpg"])
        ok(c.agendar([CARR, story, longe], _ts(c, "2026-10-13", "10:00"))["ok"], "agenda")
        julgados = []

        class Critico:
            veredito = "aprova"

            def criticar(self, tipo, material):
                julgados.append((tipo, list(material["imagens"])))
                return {"veredito": self.veredito, "motivos": [] if self.veredito == "aprova" else ["fraco"]}
        crit, arq = Critico(), self._arquivo_falso()
        agora = _ts(c, "2026-10-14", "10:00")
        r1 = c.conferir_antes(agora, crit, **arq)
        r2 = c.conferir_antes(agora, crit, **arq)
        ok((r1["id"], r2["id"]) == ("st", "ter-frases") and c.conferir_antes(agora, crit, **arq) is None,
           f"um por vez, o mais próximo primeiro, e só o que ainda não foi julgado: {r1} {r2}")
        ok(len(julgados) == 2 and len(julgados[1][1]) == 9, "o Crítico vê as 9 imagens baixadas para o cache")
        itens = {i["id"]: i for i in c.carregar()["itens"]}
        ok("conferido" not in itens["longe"], "fora das 36 h ainda não é julgado")
        ok(itens["ter-frases"]["conferido"]["veredito"] == "aprova" and itens["ter-frases"]["conferido"]["impressao"]
           == c.impressao(itens["ter-frases"]), itens["ter-frases"].get("conferido"))
        # at the hour the earlier approval of the same files is the gate: no last-minute surprise
        class Quebra:
            def criticar(self, tipo, material):
                raise AssertionError("não devia julgar de novo")
        pub = c.rodar(ApiFalsa(), lambda t: None, _ts(c, "2026-10-15", "09:05"), dormir=lambda x: None, critico=Quebra())
        ok(pub["estado"] == "publicada" and pub["portao"] == "o Crítico aprovou na conferência antecipada", pub)
        # a file changed after the check: the approval no longer fits, the gate judges again
        (c.PASTA / "cache" / "ter-frases" / "3.jpg").write_bytes(b"\xff\xd8 outra arte")
        crit.veredito = "reprova"
        pub = c.rodar(ApiFalsa(), lambda t: None, _ts(c, "2026-10-15", "11:50"), dormir=lambda x: None, critico=crit)
        ok(pub["estado"] == "bloqueada", f"arte trocada depois da aprovação é julgada de novo: {pub}")
        ok(any('"conferido": "aprova"' in l for l in (c.PASTA / "diario.jsonl").read_text(encoding="utf-8").splitlines()),
           "fica no diário")

    def t_conferencia_reprova_refaz_ou_avisa_cedo(self):
        c = _modulo()
        ok(c.agendar([CARR], _ts(c, "2026-10-13", "10:00"))["ok"], "agenda")
        vereditos = ["reprova", "aprova"]

        class Critico:
            def criticar(self, tipo, material):
                v = vereditos.pop(0) if vereditos else "reprova"
                return {"veredito": v, "motivos": [] if v == "aprova" else ["slide 3 cortado"]}
        refeitos, avisos = [], []

        def refazer(item, critica):
            refeitos.append(critica["motivos"])
            n = len(refeitos)
            novos = [f"conteudo/r{n}/{k}.jpg" for k in (1, 2)]
            return c.refeito(item["id"], novos, "refeito pelo Designer")
        arq, agora = self._arquivo_falso(), _ts(c, "2026-10-14", "10:00")
        r = c.conferir_antes(agora, Critico(), refazer, lambda t, b=None: avisos.append((t, b)), **arq)
        it = c.carregar()["itens"][0]
        ok(r["refeito"] and refeitos == [["slide 3 cortado"]] and it["arquivos"] == ["conteudo/r1/1.jpg", "conteudo/r1/2.jpg"]
           and it["refeitas"] == 1 and "conferido" not in it and not avisos, f"reprovado: refeito sozinho, sem avisar: {r} {it}")
        r = c.conferir_antes(agora, Critico(), refazer, avisos.append, **arq)
        ok(r["veredito"] == "aprova" and c.carregar()["itens"][0]["conferido"]["veredito"] == "aprova", "a versão nova é julgada")
        # cannot be redone (made outside the weekly routine): Matheus hears it a day early, once, with the button
        c2 = _modulo()
        c2.agendar([CARR], _ts(c2, "2026-10-13", "10:00"))
        nao = lambda item, critica: {"ok": False, "erro": "foi feito fora da rotina da semana"}
        r = c2.conferir_antes(agora, Critico(), nao, lambda t, b=None: avisos.append((t, b)), **arq)
        ok(not r["refeito"] and len(avisos) == 1, r)
        texto, botoes = avisos[0]
        ok(texto.startswith("pendente:") and "sai 2026-10-15 às 11:45" in texto and "fora da rotina" in texto
           and "slide 3 cortado" in texto and botoes[0]["id"] == "cs:matheus:ter-frases:liberar", texto)
        ok(c2.conferir_antes(agora, Critico(), nao, avisos.append, **arq) is None and len(avisos) == 1, "avisa uma vez só")
        ok(c2.carregar()["itens"][0]["estado"] == "pendente", "continua pendente: o portão da hora ainda decide")
        # always reproved: at most REFAZER_MAX redos, then the notice
        c3 = _modulo()
        c3.agendar([CARR], _ts(c3, "2026-10-13", "10:00"))
        vereditos[:] = []
        sempre = lambda item, critica: c3.refeito(item["id"], [f"conteudo/x{item.get('refeitas', 0)}/{k}.jpg" for k in (1, 2)], "x")
        avisos.clear()
        rs = [c3.conferir_antes(agora, Critico(), sempre, lambda t, b=None: avisos.append(t), **arq) for _ in range(4)]
        ok([x and x.get("refeito") for x in rs[:3]] == [True, True, False] and rs[3] is None and len(avisos) == 1
           and "já refiz 2 vezes" in avisos[0], f"{rs} {avisos}")
        # the Crítico down is not a reproval: nothing redone, nothing said, judged again next pass
        c5 = _modulo()
        c5.agendar([CARR], _ts(c5, "2026-10-13", "10:00"))
        class Fora:
            def criticar(self, tipo, material):
                raise TimeoutError("proxy")
        refeitos.clear(); avisos.clear()
        r = c5.conferir_antes(agora, Fora(), refazer, avisos.append, **arq)
        ok(r["veredito"] == "erro" and not refeitos and not avisos and "conferido" not in c5.carregar()["itens"][0], r)
        # released by Matheus: not judged ahead
        c4 = _modulo()
        c4.agendar([dict(CARR, liberado={"por": "matheus"})], _ts(c4, "2026-10-13", "10:00"))
        ok(c4.conferir_antes(agora, Critico(), nao, avisos.append, **arq) is None, "liberado não passa pela conferência")

    def t_semana_refaz_item_da_agenda(self):
        c, s, _ = self._semana()
        agora = _ts(c, "2026-10-26", "07:50")
        s.propor(self._feed(), agora, enviar=lambda *a: "", stories=self._stories())
        s.botao("matheus", "cs:matheus:s20261026-1:todas", subir=lambda *a: None)
        itens = {i["id"]: i for i in c.carregar()["itens"]}
        st = next(i for i in itens.values() if i["tipo"] == "STORY")

        class Esp:
            def chamar(self, papel, tarefa, material):
                return {"texto": json.dumps({"layout": "dica", "manchete": "Confere a nota"}), "erro": ""}

            def criticar(self, tipo, material):
                return {"veredito": "aprova", "motivos": []}
        c.especialistas = lambda: Esp()
        subidos = []
        r = s.refazer_item(st, {"motivos": ["layout errado"]}, subir=lambda local, chave: subidos.append(chave))
        novo = next(i for i in c.carregar()["itens"] if i["id"] == st["id"])
        ok(r["ok"] and novo["arquivos"] == subidos and subidos[0].startswith("conteudo/semanas/s20261026-1/")
           and (c.PASTA / "cache" / st["id"] / subidos[0].rsplit("/", 1)[-1]).exists(), f"story refeito na agenda: {r} {novo}")
        p = next(x for x in s.carregar("s20261026-1")["propostas"] if x["id"] == st["id"])
        ok(p["refeita"] == 1 and p["spec"]["story"]["manchete"] == "Confere a nota", "a semana guarda a versão nova")
        reel = next(i for i in itens.values() if i["tipo"] == "REELS")
        ok("decisão #39" in s.refazer_item(reel, {"motivos": ["x"]})["erro"], "Reel não é refeito sem o ok dele no áudio")
        ok("fora da rotina" in s.refazer_item(dict(CARR), {"motivos": ["x"]})["erro"], "post feito à mão: não sabe refazer")
        Esp.criticar = lambda self, tipo, material: {"veredito": "reprova", "motivos": ["ainda fraco"]}
        r = s.refazer_item(novo, {"motivos": ["x"]}, subir=lambda *a: None)
        ok(not r["ok"] and "também foi reprovada: ainda fraco" in r["erro"], r)

    def t_semana_video_so_depois_da_aprovacao(self):
        # 22/10, Matheus: "Leve" (the agent makes the Reels too); decision #39: the narration is approved before the video
        c, s, _ = self._semana(video_pendente=True)
        agora = _ts(c, "2026-10-26", "07:50")
        enviados, lancados = [], []
        s._enviar_ponte = lambda login, texto, botoes: enviados.append(texto) or ""
        s.iniciar_video = lambda sid, n: lancados.append((sid, n))
        s._subir_pelo_proxy = lambda local, chave: None
        s.propor(self._feed(), agora, enviar=lambda l, t, b: enviados.append(t) or "", stories=self._stories())
        ps = s.carregar("s20261026-1")["propostas"]
        reel = ps[1]
        ok(reel["tipo"] == "REELS" and reel["arquivos"] == [] and reel["video"]["estado"] == "aguardando_aprovacao"
           and not reel["problema"], reel)
        ok("Ouça a narração" in enviados[0] and "mostra a 2" in enviados[0], "a mensagem pede para ouvir antes")
        ok(next(p for p in s.ver("s20261026-1")["propostas"] if p["n"] == 2)["narracao"].endswith("narracao2.m4a"),
           "\"mostra a 2\" tem o áudio")
        ok(not s.concluir_video("s20261026-1", 2, video="/x.mp4")["ok"], "sem aprovação não há vídeo para concluir")
        r = s.aprovar("s20261026-1", None, agora=agora, subir=lambda *a: None)
        ok(r["gerando_video"] == [2, 4] and lancados == [("s20261026-1", 2), ("s20261026-1", 4)], r)
        ok("Gerando o vídeo de 2, 4" in r["texto"], r["texto"])
        ok(sorted(i["id"] for i in c.carregar()["itens"] if i["tipo"] == "REELS") == [], "nenhum Reel na agenda ainda")
        # the background render: the approved ficha goes to the moldes, and the video goes into the agenda by itself
        spec = importlib.util.spec_from_file_location("video_fila_teste", RAIZ / "helpers" / "video_fila.py")
        vf = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(vf)
        pedidos = []

        class Motor:
            def renderizar_molde(self, molde, formato, ficha, previa=False, saida=None, timeout=0, processos=0):
                pedidos.append((molde, formato, ficha, previa, processos))
                Path(saida).mkdir(parents=True, exist_ok=True)
                (Path(saida) / "video.mp4").write_bytes(b"video")
                return [str(Path(saida) / "video.mp4")], ""
        s.c().AUTOR["quem"] = "teste"
        r = vf.gerar("s20261026-1", 2, semana=s, esp=Motor())
        ok(r["ok"] and pedidos == [("lanca-app", "reel", {"_marca": "raiz", "falas": ["Oi"]}, False, 2)], (r, pedidos))
        item = next(i for i in c.carregar()["itens"] if i["id"] == "s20261026-1-2")
        ok(item["tipo"] == "REELS" and item["arquivos"][0].endswith("video.mp4") and c._validar_item(item) == "", item)
        ok("ficou pronto" in enviados[-1] and "qua 28/10" in enviados[-1], enviados[-1])
        # a failed render is kept and told, never scheduled
        r = vf.gerar("s20261026-1", 4, semana=s, esp=type("M", (), {"renderizar_molde": lambda self, *a, **k: ([], "o render falhou (código 1)")})())
        p4 = s.carregar("s20261026-1")["propostas"][3]
        ok(not r["ok"] and p4["estado"] == "erro" and "render falhou" in p4["erro"] and "não entrou na agenda" in enviados[-1], p4)
        ok(not vf.gerar("s20261026-1", 2, semana=s, esp=Motor())["ok"], "um vídeo já agendado não é refeito")

    def t_semana_aprovacao_parcial(self):
        c, s, _ = self._semana()
        agora = _ts(c, "2026-10-26", "07:50")
        s.propor(self._feed(), agora, enviar=lambda *a: "", stories=self._stories())
        r = s.botao("matheus", "cs:matheus:s20261026-1:algumas")
        ok("aprovar_semana" in r["conversa"] and "s20261026-1" in r["conversa"] and "Não aprove nenhum outro" in r["conversa"], r)
        r = s.aprovar("s20261026-1", "2 e 3", quem="matheus (pela conversa)", agora=agora, subir=lambda *a: None)
        ok(r["ok"] and r["agendados"] == [2, 3], r)
        itens = {i["id"]: i for i in c.carregar()["itens"]}
        ok(sorted(itens) == ["s20261026-1-2", "s20261026-1-3"], sorted(itens))
        lib = itens["s20261026-1-3"]["liberado"]
        ok(lib["por"] == "matheus (pela conversa)" and "gancho fraco" in lib["critica"], f"a decisão dele fica registrada: {lib}")
        ok("liberado" not in itens["s20261026-1-2"], "só a reprovada leva a liberação")
        semana = s.carregar("s20261026-1")
        ok(semana["estado"] == "parcial" and [p["estado"] for p in semana["propostas"]].count("proposta") == 9, semana["estado"])
        ok("Ainda esperando você: 1, 4, 5, 6, 7, 8, 9, 10, 11" in r["texto"], r["texto"])
        diario = [json.loads(l) for l in (c.PASTA / "diario.jsonl").read_text(encoding="utf-8").splitlines()]
        ok(any(e.get("item") == "s20261026-1-3" and e.get("para") == "pendente" and e["quem"].startswith("matheus") for e in diario),
           "o diário diz quem aprovou")
        # the gate does not block what he already decided, even if the Crítico still reproves
        reprova = type("C", (), {"criticar": lambda self, t, m: {"veredito": "reprova", "motivos": ["gancho fraco"]}})()
        pub = c.rodar(ApiFalsa(), lambda t: None, _ts(c, "2026-10-30", "11:50"), dormir=lambda x: None, critico=reprova)
        ok(pub["estado"] == "publicada" and pub["portao"].startswith("liberado por matheus"), pub)
        # one that fails to upload is not scheduled, the others go
        def sobe(local, chave):
            if "/r4" in chave:
                raise RuntimeError("proxy fora do ar")
        r = s.aprovar("s20261026-1", [4, 5], agora=agora, subir=sobe)
        ok(r["agendados"] == [5] and r["recusados"][0]["n"] == 4 and "não subiu" in r["recusados"][0]["motivo"], r)
        # redo: the old message's buttons stop working; the new version proposes only for the free days
        ok("propor_semana" in s.botao("matheus", "cs:matheus:s20261026-1:refazer")["conversa"], "refazer pede o que mudar")
        ok("já foi decidida" in s.botao("matheus", "cs:matheus:s20261026-1:todas")["mensagem"], "semana refeita não aprova")
        # 28 (Reel) and 30 (carrossel) já estão na agenda, e o story do 27: a semana nova só preenche as vagas livres
        erro = s.propor(self._feed(), agora, enviar=lambda *a: "", stories=self._stories())["erro"]
        ok("2 vaga(s) no feed" in erro, f"não empurra post para a semana seguinte: {erro}")
        r2 = s.propor(self._feed()[:2], agora, enviar=lambda *a: "", stories=self._stories()[:6])
        ok(r2["ok"] and r2["semana"] == "s20261026-2", r2)
        feed = [(p["data"], p["tipo"]) for p in r2["propostas"] if p["tipo"] != "STORY"]
        ok(feed == [("2026-10-27", "CARROSSEL"), ("2026-11-01", "REELS")], f"só as vagas livres: {feed}")
        ok([p["data"] for p in r2["propostas"] if p["tipo"] == "STORY"][0] == "2026-10-28", "stories só nos dias sem story")
        ok(not s.aprovar("s20261026-1", None, agora=agora, subir=lambda *a: None)["ok"], "versão velha recusa")

    def t_portao_bloqueia_reprova(self):
        c = _modulo()
        c.agendar([ITEM], _ts(c, "2026-10-13", "10:00"))
        api, avisos = ApiFalsa(), []
        vistos = []

        class Critico:
            def criticar(self, tipo, material):
                vistos.append((tipo, material))
                return {"veredito": "reprova", "motivos": ["tem emoji\nna capa", "fala com o consumidor"], "sugestoes": []}
        r = c.rodar(api, lambda t, b=None: avisos.append((t, b)), _ts(c, "2026-10-14", "11:50"), dormir=lambda x: None,
                    critico=Critico())
        ok(r["estado"] == "bloqueada" and api.chamadas == [], f"reprovado não chega à Meta: {r} {api.chamadas}")
        ok(vistos[0][0] == "post" and vistos[0][1]["legenda"] == ITEM["legenda"], "o Crítico vê a legenda")
        texto, botoes = avisos[0]
        ok(texto.startswith("pendente:") and "tem emoji na capa; fala com o consumidor" in texto and "\n" not in texto,
           f"avisa com os motivos numa linha: {texto}")
        ok(botoes == [{"id": "cs:matheus:seg-pov:liberar", "titulo": "🔓 Publicar mesmo assim"}], botoes)
        it = c.carregar()["itens"][0]
        ok(it["estado"] == "bloqueada" and "reprovou" in it["bloqueio"], "fica na agenda como bloqueada")
        ok(c.devido(_ts(c, "2026-10-14", "12:30")) is None and c.rodar(api, lambda t: None, _ts(c, "2026-10-14", "12:30"),
                                                                        critico=Critico()) is None, "não tenta de novo sozinho")
        ok(c.agenda_proxima(1, _ts(c, "2026-10-14", "13:00"))["dias"][0]["itens"][0]["estado"] == "bloqueada", "a agenda mostra")
        ok(not c.agendar([dict(ITEM, id="outro")], _ts(c, "2026-10-14", "13:00"))["ok"], "o dia continua ocupado")
        # without especialistas the post goes as before
        c2 = _modulo()
        c2.agendar([ITEM], _ts(c2, "2026-10-13", "10:00"))
        ok(c2.rodar(ApiFalsa(), lambda t: None, _ts(c2, "2026-10-14", "11:50"), dormir=lambda x: None)["portao"]
           == "sem Crítico instalado", "sem o plugin, publica como antes")

    def t_portao_falha_fechado(self):
        class Quebra:
            def criticar(self, tipo, material):
                raise TimeoutError("modelo não respondeu")

        class Estranho:
            def criticar(self, tipo, material):
                return {"veredito": "talvez"}

        def nao_carrega():
            raise SyntaxError("arquivo pela metade")
        for nome, critico in (("exceção", Quebra()), ("sem veredito", Estranho()), ("não carrega", "carregador")):
            c = _modulo()
            if critico == "carregador":
                c.especialistas, critico = nao_carrega, c._PADRAO
            c.agendar([FOTO], _ts(c, "2026-10-13", "10:00"))
            api, avisos = ApiFalsa(), []
            r = c.rodar(api, avisos.append, _ts(c, "2026-10-17", "11:50"), dormir=lambda x: None, critico=critico)
            ok(r["estado"] == "bloqueada" and api.chamadas == [], f"{nome}: nunca publica com o portão em erro: {r}")
            ok(avisos and avisos[0].startswith("pendente:") and "libera o post s3-foto" in avisos[0], f"{nome}: {avisos}")

    def t_liberar_pelo_matheus(self):
        c = _modulo()
        c.agendar([ITEM], _ts(c, "2026-10-13", "10:00"))
        quebra = type("C", (), {"criticar": lambda self, t, m: (_ for _ in ()).throw(TimeoutError("fora"))})()
        c.rodar(ApiFalsa(), lambda t: None, _ts(c, "2026-10-14", "11:50"), dormir=lambda x: None, critico=quebra)
        ok(not c.liberar("seg-pov", "")["ok"], "sem motivo não libera")
        spec = importlib.util.spec_from_file_location("semana_teste_lib", RAIZ / "helpers" / "semana.py")
        s = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(s)
        s._C["fixo"] = c
        ok(s.botao("outra", "cs:matheus:seg-pov:liberar") == {}, "botão de outra pessoa não vale")
        r = s.botao("matheus", "cs:matheus:seg-pov:liberar")
        ok(r["mensagem"].startswith("🔓 Liberado"), r)
        it = c.carregar()["itens"][0]
        ok(it["estado"] == "pendente" and it["liberado"]["por"] == "matheus (botão)" and "falhou" in it["liberado"]["bloqueio"], it)
        diario = [json.loads(l) for l in (c.PASTA / "diario.jsonl").read_text(encoding="utf-8").splitlines()]
        ok(any(e.get("para") == "pendente" and e.get("de") == "bloqueada" and e["quem"].startswith("matheus") for e in diario),
           "o diário registra a liberação e quem")
        api = ApiFalsa()
        pub = c.rodar(api, lambda t: None, _ts(c, "2026-10-14", "12:10"), dormir=lambda x: None, critico=quebra)
        ok(pub["estado"] == "publicada", f"liberado sai no mesmo dia, sem perguntar ao Crítico de novo: {pub}")
        ok(not c.liberar("seg-pov", "de novo")["ok"], "publicado não se libera")
        ok(c.AUTOR["quem"] == "agente", "liberar devolve o autor")

    def t_arquivos_do_post_do_dia(self):
        c = _modulo()
        c.agendar([CARR], _ts(c, "2026-10-13", "10:00"))
        links, baixados = [], []
        def url(chave):
            links.append(chave); return f"https://s3/{chave}?assinado"
        def baixar(link, caminho):
            baixados.append(link); Path(caminho).write_bytes(b"jpg")
        r = c.baixar_post("2026-10-15", url, baixar)
        ok(r["ok"] and r["tipo"] == "CARROSSEL" and len(r["arquivos"]) == 9 and r["legenda"] == CARR["legenda"], r)
        ok(all(Path(a).exists() and "/cache/ter-frases/" in a for a in r["arquivos"]), "arquivos baixados no disco do agente")
        ok(links == CARR["arquivos"], "pelo link assinado de cada arquivo do S3")
        c.baixar_post("2026-10-15", url, baixar)
        ok(len(baixados) == 9, "já baixado não baixa de novo")
        ok(not c.baixar_post("2026-10-16", url, baixar)["ok"], "dia sem post: diz que não tem")
        ok(c.carregar()["itens"][0]["estado"] == "pendente", "só leitura: não muda o post")
        fonte = (RAIZ / "tools" / "conteudo.py").read_text(encoding="utf-8")
        ok('acao == "arquivos"' in fonte and "baixar_post" in fonte, "a ferramenta oferece a ação")

    def t_foto_unica_valida(self):
        c = _modulo()
        agora = _ts(c, "2026-10-13", "10:00")
        ok(c._validar_item(FOTO) == "", "uma .jpg do S3 é foto válida")
        ok(c._validar_item(dict(FOTO, arquivos=["conteudo/s3/a.JPEG"])) == "", ".jpeg também")
        ruins = {"mp4": dict(FOTO, arquivos=["conteudo/s3/a.mp4"]), "png": dict(FOTO, arquivos=["conteudo/s3/a.png"]),
                 "duas": dict(FOTO, arquivos=["conteudo/s3/a.jpg", "conteudo/s3/b.jpg"]), "nenhuma": dict(FOTO, arquivos=[]),
                 "fora do S3": dict(FOTO, arquivos=["/tmp/a.jpg"]), "capa": dict(FOTO, capa="conteudo/s3/capa.jpg"),
                 "capa_ms": dict(FOTO, capa_ms=1500), "emoji": dict(FOTO, legenda="Pedidos 🍔"),
                 "minúsculo": dict(FOTO, tipo="image"), "desconhecido": dict(FOTO, tipo="FOTO")}
        for nome, it in ruins.items():
            ok(c._validar_item(it) != "", f"foto inválida passou: {nome}")
            ok(c.agendar([it], agora)["ok"] is False, f"agendar recusa: {nome}")
        ok(c.carregar()["itens"] == [], "nada inválido entrou")
        ok(c.agendar([FOTO], agora)["ok"], "foto válida agenda")
        it = c.carregar()["itens"][0]
        ok(it["tipo"] == "IMAGE" and it["arquivos"] == FOTO["arquivos"] and "capa" not in it, it)
        ok(c.agenda_proxima(7, _ts(c, "2026-10-17", "09:00"))["dias"][0]["itens"][0]["tipo"] == "IMAGE", "a agenda mostra o tipo")

    def t_publica_foto_unica_uma_vez(self):
        c = _modulo()
        c.agendar([FOTO], _ts(c, "2026-10-13", "10:00"))
        api, avisos = ApiFalsa(), []
        r = c.rodar(api, avisos.append, _ts(c, "2026-10-17", "11:45"), dormir=lambda s: None)
        ok(r["estado"] == "publicada" and r["media_id"] == "C2", r)
        criar = [x for x in api.chamadas if x[0] == "POST" and x[1] == "IG1/media"]
        ok(len(criar) == 1, f"um único contêiner: {criar}")
        ok(criar[0][2] == {"image_url": "https://s3/conteudo/semana3/ifood/foto.jpg?assinado", "caption": FOTO["legenda"]},
           f"só image_url + caption (sem media_type, is_carousel_item, children, share_to_feed, vídeo): {criar[0][2]}")
        ok(("GET", "C1", {"fields": "status_code"}) in api.chamadas, "espera a Meta processar antes de publicar")
        pubs = [x for x in api.chamadas if x[1] == "IG1/media_publish"]
        ok(pubs == [("POST", "IG1/media_publish", {"creation_id": "C1"})], f"publica uma vez o contêiner: {pubs}")
        ok(not avisos, "deu certo: sem aviso")
        ok(c.rodar(api, avisos.append, _ts(c, "2026-10-17", "12:30"), dormir=lambda s: None) is None, "não publica de novo")
        ok(len([x for x in api.chamadas if x[1] == "IG1/media_publish"]) == 1, "sem publicação duplicada")

    def t_foto_unica_falhas(self):
        casos = {"criar": (ApiFalsa(falhar_em="IG1/media"), "falhou", "permissão negada"),
                 "processar": (ApiFalsa(status="ERROR"), "falhou", "recusou"),
                 "publicar": (ApiFalsa(falhar_em="media_publish"), "incerta", "caiu a conexão")}
        for nome, (api, estado, msg) in casos.items():
            c = _modulo()
            c.agendar([FOTO], _ts(c, "2026-10-13", "10:00"))
            avisos = []
            r = c.rodar(api, avisos.append, _ts(c, "2026-10-17", "11:50"), dormir=lambda s: None)
            ok(r["estado"] == estado and msg in r["erro"], f"{nome}: {r}")
            ok(avisos and avisos[0].startswith("pendente:"), f"{nome}: avisa")
            ok(c.devido(_ts(c, "2026-10-17", "13:00")) is None, f"{nome}: não repete sozinho")
            pubs = [x for x in api.chamadas if x[1] == "IG1/media_publish"]
            ok(len(pubs) == (1 if nome == "publicar" else 0), f"{nome}: publicação chamada {len(pubs)}x")

    def t_tipo_desconhecido_nao_vira_carrossel(self):
        c = _modulo()
        api = ApiFalsa()
        for tipo in ("FOTO", "IMAGEM", "", None, "image"):
            try:
                c.preparar(dict(FOTO, tipo=tipo), api, dormir=lambda s: None)
                ok(False, f"tipo {tipo!r} foi aceito")
            except ValueError:
                pass
        ok(api.chamadas == [], f"nada foi criado na Meta: {api.chamadas}")
        # a corrupted calendar entry with an unknown type fails before Meta and never goes out as a carousel
        c.agendar([FOTO], _ts(c, "2026-10-13", "10:00"))
        d = c.carregar(); d["itens"][0]["tipo"] = "FOTO"; c._gravar(d)
        r = c.rodar(api, lambda t: None, _ts(c, "2026-10-17", "11:50"), dormir=lambda s: None)
        ok(r["estado"] == "falhou" and "tipo desconhecido" in r["erro"] and api.chamadas == [], r)

    def t_reel_e_carrossel_sem_mudanca(self):
        c = _modulo()
        agora = _ts(c, "2026-10-13", "10:00")
        c.agendar([dict(ITEM, capa="conteudo/semana2/capa-pov.jpg"), CARR], agora)
        api = ApiFalsa()
        c.rodar(api, lambda t: None, _ts(c, "2026-10-14", "11:50"), dormir=lambda s: None)
        ok(api.chamadas[0][2] == {"media_type": "REELS", "video_url": "https://s3/conteudo/semana1/pov.mp4?assinado",
                                  "caption": ITEM["legenda"], "share_to_feed": "true",
                                  "cover_url": "https://s3/conteudo/semana2/capa-pov.jpg?assinado"}, api.chamadas[0])
        api = ApiFalsa()
        c.rodar(api, lambda t: None, _ts(c, "2026-10-15", "11:50"), dormir=lambda s: None)
        criar = [x[2] for x in api.chamadas if x[0] == "POST" and x[1] == "IG1/media"]
        ok(criar[:9] == [{"image_url": f"https://s3/conteudo/semana1/frases/{i}.jpg?assinado", "is_carousel_item": "true"}
                         for i in range(1, 10)], "telas do carrossel iguais a antes")
        ok(criar[9] == {"media_type": "CAROUSEL", "children": ",".join(f"C{i}" for i in range(1, 10)),
                        "caption": CARR["legenda"]}, criar[9])
        for n, bom in ((1, False), (2, True), (10, True), (11, False)):
            it = dict(CARR, arquivos=[f"conteudo/x/{i}.jpg" for i in range(n)])
            ok((c._validar_item(it) == "") is bom, f"carrossel de {n}")
        ok(c._validar_item(dict(CARR, arquivos=["conteudo/x/1.jpg", "conteudo/x/2.png"])) != "", "carrossel só .jpg")
        ok(c._validar_item(dict(ITEM, arquivos=["conteudo/x/a.jpg"])) != "", "Reel só .mp4")
        ok(c._validar_item(dict(ITEM, arquivos=["conteudo/x/a.mp4", "conteudo/x/b.mp4"])) != "", "Reel um arquivo")

    def t_trocar_formato_reel_para_foto(self):
        c = _modulo()
        agora = _ts(c, "2026-10-17", "09:00")
        reel = dict(ITEM, id="s3-ifood", data="2026-10-17", capa="conteudo/s3/capa.jpg", capa_ms=800)
        outro = dict(ITEM, id="amanha", data="2026-10-18", capa="conteudo/s3/capa2.jpg")
        c.agendar([reel, outro], agora)
        antes = c.carregar()
        bruto = c._arq().read_bytes()
        foto = ["conteudo/s3/feed.jpg"]
        ok(not c.trocar_formato("s3-ifood", "IMAGE", foto, agora=agora)["ok"], "só o operador")
        c.AUTOR["quem"] = "operador: foto"
        for tipo, arqs in (("IMAGE", ["conteudo/s3/feed.png"]), ("IMAGE", foto * 2), ("FOTO", foto), ("IMAGE", ["conteudo/a.mp4"])):
            ok(not c.trocar_formato("s3-ifood", tipo, arqs, agora=agora)["ok"], f"recusa {tipo} {arqs}")
        ok(not c.trocar_formato("s3-ifood", "IMAGE", foto, capa="conteudo/s3/c.jpg", agora=agora)["ok"], "foto sem capa")
        ok(c._arq().read_bytes() == bruto, "recusa não grava nada")
        r = c.trocar_formato("s3-ifood", "IMAGE", foto, agora=agora)
        ok(r["ok"] and Path(r["backup"]).read_bytes() == bruto, f"cópia exata antes de gravar: {r}")
        depois = c.carregar()
        novo, velho = depois["itens"][0], antes["itens"][0]
        ok(novo == {**{k: v for k, v in velho.items() if k not in ("capa", "capa_ms")}, "tipo": "IMAGE", "arquivos": foto},
           f"só tipo/arquivos mudam e a capa sai: {novo}")
        ok(list(novo) == [k for k in velho if k not in ("capa", "capa_ms")], "ordem dos campos mantida")
        ok(depois["itens"][1] == antes["itens"][1], "o outro post fica idêntico")
        ev = json.loads((c.PASTA / "diario.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        ok(ev["formato_trocado"] and ev["para_formato"]["tipo"] == "IMAGE" and ev["quem"] == "operador: foto", ev)
        ok(c.devido(_ts(c, "2026-10-17", "11:45"))["tipo"] == "IMAGE", "a rotina vê a foto na hora")
        bruto, linhas = c._arq().read_bytes(), (c.PASTA / "diario.jsonl").read_text(encoding="utf-8")
        r2 = c.trocar_formato("s3-ifood", "IMAGE", foto, agora=agora)
        ok(r2["ok"] and r2.get("sem_mudanca") and c._arq().read_bytes() == bruto
           and (c.PASTA / "diario.jsonl").read_text(encoding="utf-8") == linhas, f"repetir não grava nem registra: {r2}")
        api = ApiFalsa()
        c.rodar(api, lambda t: None, _ts(c, "2026-10-17", "11:45"), dormir=lambda s: None)
        ok(api.chamadas[0][2] == {"image_url": "https://s3/conteudo/s3/feed.jpg?assinado", "caption": ITEM["legenda"]}, api.chamadas[0])
        ok(not c.trocar_formato("s3-ifood", "REELS", ["conteudo/a.mp4"], agora=agora)["ok"], "publicado não muda")

    def t_arquivos_da_foto_do_dia(self):
        c = _modulo()
        c.agendar([FOTO], _ts(c, "2026-10-13", "10:00"))
        links = []
        def url(chave):
            links.append(chave); return f"https://s3/{chave}?assinado"
        r = c.baixar_post("2026-10-17", url, lambda link, caminho: Path(caminho).write_bytes(b"\xff\xd8\xff"))
        ok(r["ok"] and r["tipo"] == "IMAGE" and len(r["arquivos"]) == 1 and r["arquivos"][0].endswith("/cache/s3-foto/foto.jpg"), r)
        ok(links == FOTO["arquivos"] and r["legenda"] == FOTO["legenda"], "a foto pelo link do S3, com a legenda")

    def t_rotina_recarrega_o_helper(self):
        import sys
        import types
        falso = types.ModuleType("helpers.extension")
        falso.Extension = type("Extension", (), {})
        guardados = {k: sys.modules.get(k) for k in ("helpers", "helpers.extension")}
        sys.modules.setdefault("helpers", types.ModuleType("helpers"))
        sys.modules["helpers.extension"] = falso
        try:
            import shutil
            _modulo()  # fresh CONTEUDO_PASTA
            copia = Path(tempfile.mkdtemp(prefix="conteudo_ext_"))  # a copy: the real helper's mtime is never touched
            shutil.copytree(RAIZ / "helpers", copia / "helpers")
            (copia / "extensions" / "python" / "job_loop").mkdir(parents=True)
            arq = copia / "extensions" / "python" / "job_loop" / "_46_publicar_conteudo.py"
            shutil.copy(RAIZ / "extensions" / "python" / "job_loop" / "_46_publicar_conteudo.py", arq)
            spec = importlib.util.spec_from_file_location("ext_teste", arq)
            ext = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(ext)
            m1 = ext._helper()
            ok("IMAGE" in m1.TIPOS and ext._helper() is m1, "carrega uma vez e reaproveita")
            prova = json.loads((m1.PASTA / "rotina.json").read_text(encoding="utf-8"))
            import hashlib
            ok(prova["pid"] == os.getpid() and prova["helper_sha256"] == hashlib.sha256(ext._CAMINHO.read_bytes()).hexdigest()
               and "IMAGE" in prova["tipos"], prova)
            st = ext._CAMINHO.stat()
            os.utime(ext._CAMINHO, ns=(st.st_atime_ns, st.st_mtime_ns + 1000))
            ok(ext._helper() is not m1, "helper novo no disco: a rotina relê")
        finally:
            for k, v in guardados.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

    def t_extensao_usa_o_helper(self):
        ext = (RAIZ / "extensions" / "python" / "job_loop" / "_46_publicar_conteudo.py").read_text(encoding="utf-8")
        ok("conteudo.rodar(" in ext and "run_in_executor" in ext, "a rotina publica fora do laço principal")
        ok("conferir_antes(refazer=_semana().refazer_item" in ext and "CONFERIR_CADA" in ext,
           "a conferência antecipada roda na rotina, com o refazer do agente")
        ok('tipo="urgente"' in ext, "falha chega na hora (é um pendente:)")

    async def rodar(self, so: str = "") -> dict:
        for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
            try:
                getattr(self, nome)()
                self.resultados.append({"teste": nome, "ok": True})
            except Exception as exc:
                self.resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                        "onde": traceback.format_exc()[-600:]})
        passou = sum(1 for r in self.resultados if r["ok"])
        return {"passou": passou, "total": len(self.resultados), "resultados": self.resultados}


if __name__ == "__main__":
    import asyncio
    r = asyncio.run(Suite().rodar())
    print(f"{r['passou']}/{r['total']}")
    for x in r["resultados"]:
        if not x["ok"]:
            print(x["teste"], x["erro"])
