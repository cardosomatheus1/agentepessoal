"""Tests of the competitor watch with a fake network and a temporary folder (never /a0/usr/concorrentes). Run with
implantar.py or: python3 infra/vm/plugins/concorrentes/tests/suite.py"""

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import traceback
import types
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


def rss(*itens) -> bytes:
    corpo = "".join(f"<item><title>{t}</title><link>{l}</link><pubDate>{d}</pubDate><description><![CDATA[{r}]]></description></item>"
                    for t, l, d, r in itens)
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>Blog</title>{corpo}</channel></rss>'.encode()


AGORA = 1_791_000_000.0  # 2026-10-03
HOJE = "Fri, 02 Oct 2026 10:00:00 GMT"


class Rede:
    """Fake network: url -> (status, body, content type); anything else is a connection failure."""

    def __init__(self, paginas: dict):
        self.paginas, self.pedidos = dict(paginas), []

    def __call__(self, url, timeout=20):
        self.pedidos.append(url)
        return self.paginas.get(url, (0, b"", ""))


class Suite:
    def __init__(self):
        self.resultados = []

    def _modulo(self):
        self.tmp = tempfile.mkdtemp(prefix="concorrentes_teste_")
        os.environ["CONCORRENTES_PASTA"] = self.tmp
        m = _carregar("concorrentes_teste", RAIZ / "helpers" / "concorrentes.py")
        os.environ.pop("CONCORRENTES_PASTA", None)
        return m

    def _so(self, c, fontes):
        """A list with one competitor, written through the helper (as the agent would)."""
        c.PASTA.mkdir(parents=True, exist_ok=True)
        c._gravar("lista.json", {"concorrentes": [], "removidos": []})
        c.adicionar("Doce Sistema", "teste", fontes)

    def t_le_rss_atom_e_json(self):
        fd = _carregar("concorrentes_feed_teste", RAIZ / "helpers" / "feed.py")
        r = fd.parse_feed(rss(("Novo plano", "https://x.com/a", HOJE, "<b>mais</b> barato")))
        eq((r["format"], r["entries"][0]["title"], r["entries"][0]["summary"]), ("rss", "Novo plano", "mais barato"), "RSS")
        atom = (b'<feed xmlns="http://www.w3.org/2005/Atom"><title>A</title><entry><title>Lancamento</title>'
                b'<link rel="alternate" href="https://x.com/b"/><updated>2026-10-01T12:00:00Z</updated></entry></feed>')
        r = fd.parse_feed(atom)
        eq((r["format"], r["entries"][0]["link"]), ("atom", "https://x.com/b"), "Atom")
        js = json.dumps({"version": "https://jsonfeed.org/version/1.1", "items": [{"title": "J", "url": "https://x.com/c",
                                                                                  "date_published": "2026-10-01T00:00:00Z"}]}).encode()
        r = fd.parse_feed(js, "application/feed+json")
        eq((r["format"], r["entries"][0]["link"]), ("jsonfeed", "https://x.com/c"), "JSON Feed")
        pagina = b'<html><head><link rel="alternate" type="application/rss+xml" href="/feed.xml"></head></html>'
        eq(fd.discover("https://x.com/blog/", pagina), ["https://x.com/feed.xml"], "acha o feed anunciado na página")
        eq(fd.discover("https://x.com/", b"<html></html>", common_paths=False), [], "sem anúncio e sem caminhos comuns")

    def t_acha_o_feed_ou_os_posts(self):
        c = self._modulo()
        try:
            rede = Rede({
                "https://x.com/blog": (200, b'<html><head><link rel="alternate" type="application/rss+xml" href="/rss"></head></html>', "text/html"),
                "https://x.com/rss": (200, rss(("Post", "https://x.com/p1", HOJE, "")), "application/rss+xml"),
                "https://y.com/blog": (200, b'<html><a href="/blog/como-precificar-brigadeiro">Como precificar brigadeiro para vender</a>'
                                            b'<a href="https://outro.com/x">Link de fora do site com titulo longo</a><a href="/s">Sair</a></html>', "text/html"),
                "https://z.com/": (200, b"<html><body>site</body></html>", "text/html"),
            })
            r = c.ler_fonte({"tipo": "blog", "url": "https://x.com/blog"}, rede)
            eq((r["modo"], r["itens"][0]["link"], r["feed"]), ("feed", "https://x.com/p1", "https://x.com/rss"), "feed da página")
            r = c.ler_fonte({"tipo": "blog", "url": "https://y.com/blog"}, rede)
            eq((r["modo"], [i["link"] for i in r["itens"]]), ("links", ["https://y.com/blog/como-precificar-brigadeiro"]),
               "blog sem feed: os links dos posts do próprio site")
            r = c.ler_fonte({"tipo": "site", "url": "https://z.com/"}, rede)
            ok(r["ok"] and r["itens"] == [] and "https://z.com/feed" not in rede.pedidos,
               "site sem feed: no ar, nada a listar, sem chutar caminhos")
            r = c.ler_fonte({"tipo": "blog", "url": "https://fora.com/"}, rede)
            ok(not r["ok"] and r["erro"] == "sem resposta", "sem resposta é falha")
        finally:
            shutil.rmtree(self.tmp, ignore_errors=True)

    def t_so_o_que_e_novo_agrupado_por_fato(self):
        c = self._modulo()
        try:
            self._so(c, [{"tipo": "blog", "url": "https://x.com/rss"}, {"tipo": "imprensa", "url": "\"Doce Sistema\""}])
            gn = c.imprensa('"Doce Sistema"')
            rede = Rede({"https://x.com/rss": (200, rss(("Post antigo", "https://x.com/p0", HOJE, "")), "application/rss+xml"),
                         gn: (200, rss(), "application/rss+xml")})
            r1 = c.coletar(rede, AGORA)
            eq((r1["fatos"], len(r1["primeira_leitura"])), ([], 2), "1ª rodada: base, nada é novo")
            rede.paginas["https://x.com/rss"] = (200, rss(
                ("Doce Sistema lança novo plano para confeitarias", "https://x.com/p1", HOJE, ""),
                ("Post antigo", "https://x.com/p0", HOJE, ""),
                ("Post de 2025 que reapareceu", "https://x.com/velho", "Mon, 01 Sep 2025 10:00:00 GMT", "")), "application/rss+xml")
            rede.paginas[gn] = (200, rss(
                ("Doce Sistema lança novo plano para confeitarias - Jornal A", "https://news/a", HOJE, ""),
                ("Novo plano: Doce Sistema lança para confeitarias - Portal B", "https://news/b", HOJE, ""),
                ("Doce Sistema recebe aporte de R$ 5 milhões", "https://news/c", HOJE, "")), "application/rss+xml")
            r2 = c.coletar(rede, AGORA + 86400)
            eq(len(r2["fatos"]), 2, "o lançamento (blog + 2 jornais) é um fato; o aporte é outro")
            lanc = next(f for f in r2["fatos"] if len(f["fontes"]) == 3)
            eq((lanc["titulo"], lanc["categoria"]), ("Doce Sistema lança novo plano para confeitarias", "preço"),
               "o título vem da própria empresa")
            ok(any(f["categoria"] == "investimento" for f in r2["fatos"]), "aporte vira investimento")
            ok(all("velho" not in x["link"] for f in r2["fatos"] for x in f["fontes"]), "item de mais de 30 dias nunca é novo")
            r3 = c.coletar(rede, AGORA + 2 * 86400)
            eq(r3["fatos"], [], "3ª rodada igual: nada novo")
            ok("Nada novo" in c.texto(r3), "texto diz que não há novidade nas fontes lidas")
            eq(c.ultima()["em"], AGORA + 2 * 86400, "a última rodada fica guardada")
        finally:
            shutil.rmtree(self.tmp, ignore_errors=True)

    def t_fonte_que_falhou_e_sem_cobertura(self):
        c = self._modulo()
        try:
            self._so(c, [{"tipo": "rss", "url": "https://x.com/rss"}])
            rede = Rede({"https://x.com/rss": (200, rss(("A", "https://x.com/a", HOJE, "")), "application/rss+xml")})
            c.coletar(rede, AGORA)
            rede.paginas["https://x.com/rss"] = (503, b"", "")
            r = c.coletar(rede, AGORA + 3600)
            eq((r["fatos"], r["sem_cobertura"][0]["erro"], r["fontes_lidas"]), ([], "HTTP 503", 0), "falhou: sem cobertura")
            t = c.texto(r)
            ok("Sem cobertura" in t and "não quer dizer que não houve novidade" in t, f"nunca 'sem notícia': {t}")
            rede.paginas["https://x.com/rss"] = (200, rss(("B saiu enquanto a fonte estava fora", "https://x.com/b", HOJE, ""),
                                                          ("A", "https://x.com/a", HOJE, "")), "application/rss+xml")
            r = c.coletar(rede, AGORA + 7200)
            eq([f["titulo"] for f in r["fatos"]], ["B saiu enquanto a fonte estava fora"],
               "o que saiu durante a falha aparece na volta (a base não andou)")
        finally:
            shutil.rmtree(self.tmp, ignore_errors=True)

    def t_precos_mudaram(self):
        c = self._modulo()
        try:
            self._so(c, [{"tipo": "precos", "url": "https://x.com/planos"}])
            pagina = lambda *v: (200, ("<html><script>var p='R$ 1,00'</script>" + "".join(f"<p>Plano R$ {x}</p>" for x in v)  # noqa: E731
                                       + "</html>").encode(), "text/html")
            rede = Rede({"https://x.com/planos": pagina("19,90", "199,90")})
            c.coletar(rede, AGORA)
            eq(c.coletar(rede, AGORA + 60)["fatos"], [], "mesmos preços: nada")
            rede.paginas["https://x.com/planos"] = pagina("24,90", "199,90")
            f = c.coletar(rede, AGORA + 120)["fatos"]
            eq(len(f), 1, "um fato")
            ok("saiu R$19,90" in f[0]["titulo"] and "entrou R$24,90" in f[0]["titulo"], f"o que saiu e o que entrou: {f[0]['titulo']}")
            ok("R$1,00" not in f[0]["titulo"], "texto de script não conta")
        finally:
            shutil.rmtree(self.tmp, ignore_errors=True)

    def t_lista_editavel_pela_ferramenta(self):
        c = self._modulo()
        try:
            d = c.carregar()
            ok(len(d["concorrentes"]) >= 5 and all(x["pesquisa"] and x["fontes"] for x in d["concorrentes"]),
               "a lista inicial tem concorrentes reais, com fontes e as URLs da pesquisa")
            ok(not (c.PASTA / "lista.json").exists(), "ler não grava nada")
            novo = c.adicionar("Confeitaria Pro", "app", [{"tipo": "site", "url": "https://cpro.com.br"},
                                                         {"tipo": "imprensa", "url": "\"Confeitaria Pro\""}])
            eq(novo["id"], "confeitaria_pro", "id pelo nome")
            ok(novo["fontes"][1]["url"].startswith("https://news.google.com/rss/search?"), "termo de imprensa vira busca em RSS")
            for ruim, msg in (([{"tipo": "tv", "url": "https://x.com"}], "tipo inexistente"),
                              ([{"tipo": "site", "url": "javascript:alert(1)"}], "endereço inválido"), ([], "sem fonte")):
                try:
                    c.adicionar("Outro", "", ruim)
                    raise Falha(f"aceitou {msg}")
                except ValueError:
                    pass
            try:
                c.adicionar("Confeitaria Pro", "", [{"tipo": "site", "url": "https://x.com"}])
                raise Falha("aceitou repetido")
            except ValueError:
                pass
            c.mudar_fonte("confeitaria_pro", {"tipo": "precos", "url": "https://cpro.com.br/planos"})
            c.mudar_fonte("confeitaria_pro", {"url": "https://cpro.com.br"}, tirar=True)
            eq([f["tipo"] for f in c._achar(c.carregar(), "confeitaria_pro")["fontes"]], ["imprensa", "precos"], "fontes mudadas")
            c.remover("confeitaria_pro", "não é concorrente")
            d = c.carregar()
            ok(all(x["id"] != "confeitaria_pro" for x in d["concorrentes"]) and d["removidos"][-1]["motivo"] == "não é concorrente",
               "removido fica guardado")
            linhas = (c.PASTA / "diario.jsonl").read_text(encoding="utf-8").splitlines()
            eq([json.loads(l)["acao"] for l in linhas], ["adicionar", "fonte", "tirar_fonte", "remover"], "tudo no diário")
            # the tool's actions (Agent Zero's Tool replaced by a stand-in outside the container)
            antes = {n: sys.modules.get(n) for n in ("helpers", "helpers.tool")}
            if antes["helpers.tool"] is None:
                sys.modules["helpers"] = types.ModuleType("helpers")
                sys.modules["helpers.tool"] = types.SimpleNamespace(Response=object, Tool=object)
            try:
                tool = _carregar("concorrentes_tool_teste", RAIZ / "tools" / "concorrentes.py")
            finally:
                for n, m in antes.items():
                    if m is None:
                        sys.modules.pop(n, None)
            ok("saipos" in tool.executar(c, "lista", {}), "lista pela ferramenta")
            ok(tool.executar(c, "adicionar", {"nome": "Nova", "fontes": '[{"tipo": "site", "url": "https://nova.com"}]'})
               .startswith("Adicionado: nova"), "adicionar pela ferramenta (fontes como texto JSON)")
            ok(tool.executar(c, "ultima", {}) == "Ainda não houve coleta.", "sem coleta ainda")
        finally:
            shutil.rmtree(self.tmp, ignore_errors=True)

    async def rodar(self, so=""):
        for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
            try:
                getattr(self, nome)()
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
