"""Tests of conteudo (daily posts on @raiz.connect) that need no running agent and never touch Meta: a fake API stands
in for the Graph API. Run with implantar.py or: python3 infra/vm/plugins/conteudo/tests/suite.py"""

import datetime as dt
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


class Suite:
    def __init__(self):
        self.resultados = []

    def t_legenda_sem_emoji(self):
        c = _modulo()
        ok(c.validar_legenda("Marca quem já passou por isso.") == "", "texto puro passa")
        for ruim in ("Marca quem já passou 😅", "Comenta 👇", "Feito com carinho ❤️", "ok ✨"):
            ok("emoji" in c.validar_legenda(ruim), f"emoji recusado: {ruim!r}")
        ok("caracteres" in c.validar_legenda("a" * 2201), "limite de tamanho")
        ok("hashtags" in c.validar_legenda(" ".join(f"#t{i}" for i in range(31))), "limite de hashtags")
        ok(c.validar_legenda("Preço: R$ 9,50 (100%) e ação.") == "", "acentos, R$ e % não são emoji")

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

    def t_extensao_usa_o_helper(self):
        ext = (RAIZ / "extensions" / "python" / "job_loop" / "_46_publicar_conteudo.py").read_text(encoding="utf-8")
        ok("conteudo.rodar(" in ext and "run_in_executor" in ext, "a rotina publica fora do laço principal")
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
