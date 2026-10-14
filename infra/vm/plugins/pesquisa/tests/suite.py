"""Tests of the research plugin that need no network (the ledger record). Run with implantar.py (staging copy),
inside the container, or from the repository root: python3 infra/vm/plugins/pesquisa/tests/suite.py"""

import importlib.util
import shutil
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


def eq(a, b, msg):
    if a != b:
        raise Falha(f"{msg}: esperado {b!r}, veio {a!r}")


def _carregar(nome: str, arquivo: Path):
    spec = importlib.util.spec_from_file_location(nome, arquivo)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Suite:
    def __init__(self):
        self.resultados = []

    def t_pesquisa_no_livro(self):
        # 12/10 review §6: the research's result file is recorded in the ledger
        lp = _carregar("pesquisa_livro_teste", RAIZ / "helpers" / "livro_pesquisa.py")
        central = RAIZ.parent / "central" / "helpers" / "livro.py"
        if not central.exists():
            central = Path("/a0/usr/plugins/central/helpers/livro.py")
        livro = _carregar("central_livro_pesquisa_teste", central)
        tmp = Path(tempfile.mkdtemp(prefix="pesquisa-livro-"))
        try:
            livro.PASTA, livro.BANCO = tmp, tmp / "agente.db"
            arquivo = "/a0/usr/workdir/pesquisas/20261012-150000/sintese.md"
            ok(lp.registrar(livro, "pessoa_pesquisa", "Qual lava e seca 127 V\n compensa?", arquivo, 9, "ctx9"), "registrado")
            r = livro.do_periodo("pessoa_pesquisa", 0)[0]
            eq((r["verbo"], r["alvo"], r["fase"]), ("pesquisa", f"arquivo:{arquivo}", "executada"), "pesquisa com o arquivo")
            eq(r["conteudo_previa"], "Qual lava e seca 127 V compensa?", "a pergunta, numa linha")
            ok("9 fontes" in r["resultado"], "quantas fontes")
            eq(lp.registrar(None, "pessoa_pesquisa", "x", arquivo, 1), "", "sem livro: nada, sem erro")
            eq(lp.registrar(livro, "teste_pesquisa", "x", arquivo, 1), "", "login de teste não vai ao livro")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # ------------------------------------------------------------------ blocked page -> archived copy (14/10)

    @staticmethod
    def _recuperar(respostas: dict, jina: bool = True):
        """The recovery helper with a fake network: `respostas` maps a URL prefix to (status, body, final URL)."""
        rp = _carregar("pesquisa_recuperar_teste", RAIZ / "helpers" / "recuperar_pagina.py")
        rp.JINA = jina
        rp.pedidos = []

        def falso(url, timeout, headers=None, retries_on_429=0):
            rp.pedidos.append((url, dict(headers or {})))
            for prefixo, resposta in respostas.items():
                if url.startswith(prefixo):
                    return resposta
            return 0, b"", url
        rp._fetch = falso
        return rp

    def t_copia_conferida_antes_de_valer(self):
        rp = self._recuperar({})
        conteudo = b"<html><head><title>Fogao 5 bocas: teste</title></head><body>" + b"texto de verdade " * 400 + b"</body></html>"
        eq(rp.validate(conteudo, "wayback", "https://loja.com.br/p/1"), None, "página de verdade vale")
        ok(str(rp.validate(b"<html>pouco</html>", "wayback", "https://loja.com.br/p/1")).startswith("body_too_small"),
           "corpo pequeno é página de erro, não cópia")
        cf = b"<html><head><title>Just a moment...</title></head><body>" + b"x" * 5000 + b"</body></html>"
        ok("interstitial" in str(rp.validate(cf, "wayback", "https://loja.com.br/p/1")), "'just a moment' não é a página")
        volta = (b'<html><head><title>ok</title><meta http-equiv="refresh" content="0;url=https://loja.com.br/p/1"></head>'
                 + b" " * 4000 + b"</html>")
        eq(rp.validate(volta, "archive_today", "https://loja.com.br/p/1"), "redirect_stub_to_origin",
           "redirecionamento falso de volta ao site bloqueado")
        ok(rp.bloqueada(403, b"") and rp.bloqueada(429, b""), "erro >= 400 é bloqueio")
        ok(rp.bloqueada(200, cf), "200 com 'Just a moment...' também é bloqueio")
        ok(not rp.bloqueada(200, conteudo), "página normal não é bloqueio")

    def t_copia_do_wayback_com_a_data(self):
        pagina = b"<html><head><title>Reclame Aqui</title></head><body>" + b"reclamacao " * 600 + b"</body></html>"
        rp = self._recuperar({
            "https://archive.org/wayback/available": (200, b'{"archived_snapshots": {"closest": {"available": true, '
                                                           b'"url": "http://web.archive.org/web/20261009071414/https://www.reclameaqui.com.br/x", '
                                                           b'"timestamp": "20261009071414"}}}', ""),
            "https://web.archive.org/web/20261009071414id_/": (200, pagina, "https://web.archive.org/web/20261009071414id_/https://www.reclameaqui.com.br/x"),
        })
        r = rp.recover("https://www.reclameaqui.com.br/x")
        ok(r is not None, "achou a cópia")
        eq((r["route"], r["label"]), ("wayback", "cópia arquivada de 09/10/2026"), "rota e rótulo com a data")
        ok(any("id_/" in u for u, _ in rp.pedidos), "a cópia é lida crua, sem a barra do Wayback")

    def t_redirecionamento_falso_nao_vale(self):
        pagina = b"<html><head><title>Inicio</title></head><body>" + b"home " * 900 + b"</body></html>"
        rp = self._recuperar({
            "https://archive.org/wayback/available": (200, b'{"archived_snapshots": {}}', ""),
            # the site had redirected the article to its home page: that snapshot is not the article
            "https://web.archive.org/web/2id_/": (200, pagina, "https://web.archive.org/web/20260101000000id_/https://loja.com.br/"),
            # archive.ph sends to some other host
            "https://archive.ph/": (200, pagina, "https://outro-site.com/"),
            "https://archive.md/": (200, b"<html><head><title>Just a moment...</title></head>" + b"x" * 5000, "https://archive.md/x"),
        }, jina=False)
        eq(rp.recover("https://loja.com.br/artigo/1"), None, "cópia de outra página ou de outro site não vale")
        data = (b'<html><head><title>Artigo</title></head><body><time itemprop="pubdate" datetime="2026-08-06T10:00:00Z">'
                b"6 ago</time>" + b"artigo " * 900 + b"</body></html>")
        rp2 = self._recuperar({"https://archive.li/": (200, data, "https://archive.li/AbCd")}, jina=False)
        r = rp2.recover("https://loja.com.br/artigo/1")
        eq((r["route"], r["label"]), ("archive_today:archive.li", "cópia arquivada de 06/08/2026"),
           "archive.today: a data vem da própria cópia")

    def t_jina_sem_chave_e_desligavel(self):
        import os

        md = b"Title: Precos de fogao\n\nURL Source: https://loja.com.br/p\n\nMarkdown Content:\n" + b"preco " * 200
        rp = self._recuperar({"https://r.jina.ai/": (200, md, "https://r.jina.ai/https://loja.com.br/p")})
        antes = os.environ.pop("JINA_API_KEY", None)
        try:
            r = rp.recover("https://loja.com.br/p")
            eq(r["route"], "jina_reader", "Jina Reader sem chave")
            ok(r["label"].startswith("cópia lida pelo Jina Reader em "), "rótulo diz que é cópia e de quando")
            ok(not rp.pedidos[-1][1].get("Authorization"), "sem chave, sem cabeçalho de autorização")
        finally:
            if antes is not None:
                os.environ["JINA_API_KEY"] = antes
        rp_off = self._recuperar({"https://r.jina.ai/": (200, md, "")}, jina=False)
        eq(rp_off.recover("https://loja.com.br/p"), None, "desligado, não usa o Jina")
        eq(rp.recover("https://loja.com.br/p", prazo=0), None, "prazo esgotado: nenhuma rota começa")
        eq(rp.recover("ftp://x"), None, "endereço que não é http")

    async def t_pagina_bloqueada_entra_como_copia(self):
        """_ler_pagina in the tool: a 403 becomes the archived copy, with its label; a normal page stays as it was."""
        import types

        faltando = {}
        for nome in ("aiohttp", "bs4", "helpers", "helpers.tool"):
            try:
                __import__(nome)
            except Exception:
                m = types.ModuleType(nome)
                if nome == "aiohttp":
                    m.ClientSession, m.ClientTimeout = object, lambda **k: None
                if nome == "bs4":
                    m.BeautifulSoup = object
                if nome == "helpers.tool":
                    m.Response, m.Tool = object, object
                faltando[nome] = m
        antes = {n: sys.modules.get(n) for n in faltando}
        sys.modules.update(faltando)
        try:
            pq = _carregar("pesquisa_tool_teste", RAIZ / "tools" / "pesquisar.py")
        finally:
            for n, m in antes.items():
                if m is None:
                    sys.modules.pop(n, None)
                else:
                    sys.modules[n] = m
        pq._texto_html = lambda h: "TEXTO:" + h[:60]
        copia_body = b"<html><head><title>Fogao</title></head><body>" + b"preco " * 900 + b"</body></html>"
        chamadas = []

        class Recuperar:
            bloqueada = staticmethod(_carregar("pesquisa_recuperar_t2", RAIZ / "helpers" / "recuperar_pagina.py").bloqueada)

            @staticmethod
            def recover(url):
                chamadas.append(url)
                return {"body": copia_body, "label": "cópia arquivada de 09/10/2026",
                        "source_url": "https://web.archive.org/web/20261009071414id_/" + url}
        pq._modulo_local = lambda nome, arquivo: Recuperar

        class Resp:
            def __init__(self, status, corpo):
                self.status, self.corpo, self.headers = status, corpo, {"Content-Type": "text/html"}

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def text(self, errors="ignore"):
                return self.corpo

        class Sessao:
            def get(self, url, **k):
                return Resp(403, "<title>Forbidden</title>") if "bloqueado" in url else Resp(200, "<title>Ok</title>conteudo")

        texto, copia = await pq._ler_pagina(Sessao(), "https://bloqueado.com.br/p")
        eq(copia, {"rotulo": "cópia arquivada de 09/10/2026",
                   "url": "https://web.archive.org/web/20261009071414id_/https://bloqueado.com.br/p"}, "403 vira cópia marcada")
        ok(texto.startswith("TEXTO:<html><head><title>Fogao"), "o texto é o da cópia")
        texto, copia = await pq._ler_pagina(Sessao(), "https://normal.com.br/p")
        eq((copia, chamadas), ({}, ["https://bloqueado.com.br/p"]), "página normal: lida como antes, sem procurar cópia")
        ok("cópia arquivada de <data>" in pq.PROMPT_SINTESE, "a síntese manda dizer a data da cópia")

    async def rodar(self, so=""):
        for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
            try:
                r = getattr(self, nome)()
                if hasattr(r, "__await__"):
                    await r
                self.resultados.append({"teste": nome, "ok": True})
            except Exception as exc:
                self.resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                        "onde": traceback.format_exc().splitlines()[-3:]})
        return {"passou": sum(r["ok"] for r in self.resultados), "total": len(self.resultados),
                "resultados": self.resultados}


if __name__ == "__main__":
    import asyncio

    r = asyncio.run(Suite().rodar(sys.argv[1] if len(sys.argv) > 1 else ""))
    for x in r["resultados"]:
        print("ok   " if x["ok"] else "FALHA", x["teste"], x.get("erro", ""), *(x.get("onde") or []) if not x["ok"] else "")
    print("TESTES", r["passou"], r["total"])
