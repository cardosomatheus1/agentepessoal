"""Tests of the "Resolver aqui" signed links (no network, no browser). Run with implantar.py or inside the container."""

import importlib.util
import tempfile
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _tela():
    spec = importlib.util.spec_from_file_location("tela_teste", RAIZ / "helpers" / "tela.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def ok(cond, msg):
    if not cond:
        raise AssertionError(msg)


class Suite:
    def t_link_assinado_abre_so_a_conversa_dele(self):
        t = _tela()
        tok = t.assinar("S2keHNv0", "matheus", "segredo", agora=1000)
        d = t.conferir(tok, "segredo", agora=1000 + 60)
        ok(d == {"contexto": "S2keHNv0", "usuario": "matheus", "expira": 1000 + t.VALIDADE_S}, d)
        ok(t.conferir(tok, "outro-segredo", agora=1060) is None, "outra chave não abre")
        ok(t.conferir(tok.replace("S2keHNv0", "q3fotwxU", 1), "segredo", agora=1060) is None, "trocar a conversa não abre")
        ok(t.conferir(tok.replace("matheus", "fernanda", 1), "segredo", agora=1060) is None, "trocar a pessoa não abre")
        ok(t.conferir(tok, "segredo", agora=1000 + t.VALIDADE_S + 1) is None, "expira em 30 min")
        ok(t.conferir("lixo", "segredo") is None and t.conferir("", "segredo") is None, "token torto não abre")
        ok(t.conferir(tok, "", agora=1060) is None, "sem segredo na máquina nada abre")

    def t_link_completo_so_com_endereco_e_segredo(self):
        t = _tela()
        with tempfile.TemporaryDirectory() as d:
            chave = Path(d) / ".chave"
            ok(t.link("https://agente.exemplo.com/", "abc", "matheus", chave) == "", "sem segredo, sem link")
            chave.write_text("s3gr3do\n")
            l = t.link("https://agente.exemplo.com/", "abc", "matheus", chave)
            ok(l.startswith("https://agente.exemplo.com/api/plugins/navegador_visual/tela?t=abc.matheus."), l)
            ok(t.conferir(l.split("?t=")[1], "s3gr3do") is not None, "o link gerado confere")
            ok(t.link("starting", "abc", "matheus", chave) == "", "endereço ainda subindo: sem link")

    def t_pagina_e_api_existem(self):
        pagina = (RAIZ / "helpers" / "tela.html").read_text(encoding="utf-8")
        ok("__TOKEN__" in pagina and "telegram-web-app.js" in pagina and '"pronto"' in pagina, "página do Telegram")
        api = (RAIZ / "api" / "tela.py").read_text(encoding="utf-8")
        ok("conferir(token" in api and 'get_data("dono")' in api, "a API confere o link e o dono da conversa")
        ok('("Enter", "Backspace", "Tab", "Escape")' in api, "só teclas de edição")
        ok('acao == "abrir"' in api and 'url.startswith("https://")' in api, "abrir endereço só https")
        ok('acao == "abas"' in api and 'runtime.call("open"' in api and 'input.get("nova")' in api, "abre aba nova e lista as abas da conversa")
        ok('"aba não encontrada nesta conversa"' in api and 'str(pedida) not in ids' in api, "aba escolhida só entre as da própria conversa")
        # 16/10: page text for the operator, behind the same signed link; never password fields
        ok('acao == "conteudo"' in api and "c.type !== 'password'" in api
           and api.index("conferir(token") < api.index('acao == "conteudo"'), "texto da página só com o link e sem senha")
        ok('acao == "anexar"' in api and "ANEXOS not in caminho.parents" in api, "anexar só da pasta de anexos do operador")
        ok('acao == "campo"' in api and 'método não permitido' in api, "campo: só type, select_option, set_checked e click")
        ok('acao == "pagina"' in api and "operação não permitida" in api and api.count("ANEXOS not in caminho.parents") == 2,
           "pagina: só arquivo (da pasta de anexos), escolher e raiz_api")
        ok('pagina.url.startswith("https://raizconnect.com.br/")' in api and '"/auth/" in pedido["caminho"]' in api,
           "raiz_api: só na Raiz, só /api/v1/ e nunca rotas de autenticação")

    async def rodar(self, so=""):
        resultados = []
        for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
            try:
                getattr(self, nome)()
                resultados.append({"teste": nome, "ok": True})
            except Exception as exc:
                resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                   "onde": traceback.format_exc().splitlines()[-3:]})
        return {"passou": sum(r["ok"] for r in resultados), "total": len(resultados), "resultados": resultados}


if __name__ == "__main__":
    import asyncio
    import sys

    r = asyncio.run(Suite().rodar(sys.argv[1] if len(sys.argv) > 1 else ""))
    for x in r["resultados"]:
        print("ok   " if x["ok"] else "FALHA", x["teste"], x.get("erro", ""))
    print("TESTES", r["passou"], r["total"])
