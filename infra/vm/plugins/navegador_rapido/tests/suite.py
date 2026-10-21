"""Tests of the browser fixes that run without Agent Zero. The page script runs in a real Chromium when Playwright is
installed (locally and on the VM); in CI, without it, that test only checks the script is well formed.
Run: python3 infra/vm/plugins/navegador_rapido/tests/suite.py"""

import asyncio
import importlib.util
import os
import sys
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


def _correcoes():
    spec = importlib.util.spec_from_file_location("navegador_rapido_correcoes_teste", RAIZ / "helpers" / "correcoes.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _ver_tela():
    spec = importlib.util.spec_from_file_location("navegador_rapido_ver_tela_teste", RAIZ / "helpers" / "ver_tela.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# 21/10, 99Food login: one password field per login tab, only the e-mail tab's is visible
PAGINA = """<form><input id=a type=password style="display:none"><input id=b type=password>
<input id=c type=text><button id=d style="visibility:hidden">Entrar</button><button id=e>Entrar</button></form>
<div class=x>um</div><div class=x>dois</div>"""


class _Pagina:
    def __init__(self, devolve=None, erro=None):
        self.devolve, self.erro, self.chamadas = devolve, erro, []

    async def evaluate(self, script, arg=None, isolated_context=False):
        self.chamadas.append(arg)
        if self.erro:
            raise self.erro
        return self.devolve


class Suite:
    def __init__(self):
        self.resultados = []

    async def t_alvo_visivel_na_pagina(self):
        c = _correcoes()
        ok(c.ALVO_VISIVEL.startswith("(sel) =>") and c.ALVO in c.ALVO_VISIVEL, "o script recebe o seletor")
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return
        exe = os.environ.get("CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
        if not Path(exe).exists():
            return
        async with async_playwright() as p:
            b = await p.chromium.launch(executable_path=exe, headless=True)
            pg = await b.new_page()
            await pg.set_content(PAGINA)
            novo = await pg.evaluate(c.ALVO_VISIVEL, "input[type=password]")
            eq(novo, '[data-a0-alvo="1"]', "o primeiro campo de senha está escondido: troca pelo visível")
            eq(await pg.evaluate(f"document.querySelector('{novo}').id"), "b", "marcou o campo que aparece")
            eq(await pg.evaluate(c.ALVO_VISIVEL, "button"), '[data-a0-alvo="1"]', "botão escondido antes do visível")
            eq(await pg.evaluate("document.querySelectorAll('[data-a0-alvo]').length"), 1, "só um marcado de cada vez")
            eq(await pg.evaluate("document.querySelector('[data-a0-alvo]').id"), "e", "o botão visível")
            eq(await pg.evaluate(c.ALVO_VISIVEL, "input[type=text]"), "", "um só: deixa como está")
            eq(await pg.evaluate(c.ALVO_VISIVEL, "#b, #c"), "", "o primeiro já é o visível: deixa como está")
            eq(await pg.evaluate(c.ALVO_VISIVEL, "div.x"), "", "seletor de leitura (não é campo) fica como está")
            eq(await pg.evaluate(c.ALVO_VISIVEL, "[[["), "", "seletor inválido não quebra")
            await b.close()

    async def t_envio_de_arquivo_por_campo_escondido(self):
        c = _correcoes()
        campos = [{"accept": "image/*"}, {"accept": ".pdf,.xlsx"}, {"accept": ""}]
        eq(c.escolher_input(campos, ["/a/planilha.xlsx"]), 2, "o último campo que aceita (sem accept aceita tudo)")
        eq(c.escolher_input(campos[:2], ["/a/planilha.xlsx"]), 1, "o que aceita .xlsx")
        eq(c.escolher_input(campos[:2], ["/a/foto.jpg"]), 0, "imagem vai no image/*")
        eq(c.escolher_input(campos[:1], ["/a/planilha.xlsx"]), None, "nenhum aceita: não força")
        eq(c.escolher_input([], ["/a/x.xlsx"]), None, "sem campo de arquivo")
        args = {"action": "upload_file", "selector": "input[type=file]", "path": "/a/x.xlsx"}
        ok(c.argumentos_de_upload(args) and args["ref"] == c.ARQUIVO, "só seletor: vai direto ao campo de arquivo")
        args = {"action": "upload_file", "ref": "8", "path": "/a/x.xlsx"}
        ok(not c.argumentos_de_upload(args) and args["ref"] == "8", "ref dada fica (o fallback cuida se falhar)")
        ok(not c.argumentos_de_upload({"action": "click", "selector": "x"}), "outra ação não muda")
        ok(not c.argumentos_de_upload(None), "sem argumentos não quebra")
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return
        exe = os.environ.get("CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
        if not Path(exe).exists():
            return
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            arq = Path(tmp) / "76437182_CL.xlsx"
            arq.write_bytes(b"PK\x03\x04teste")
            async with async_playwright() as p:
                b = await p.chromium.launch(executable_path=exe, headless=True)
                pg = await b.new_page()
                # como no claude.ai: o campo de arquivo existe, mas escondido, e o botão é que aparece
                await pg.set_content('<button>Anexar</button><input type="file" id="f" style="display:none" multiple>')
                eq(await c.enviar_pelo_campo(pg, [str(arq)]), 0, "achou o campo escondido")
                eq(await pg.evaluate("document.getElementById('f').files[0].name"), "76437182_CL.xlsx",
                   "o arquivo entrou no campo escondido")
                await b.close()

    async def t_content_usa_o_alvo_visivel(self):
        c = _correcoes()
        recebidos = []

        class Core:
            async def content(self, browser_id=None, payload=None):
                recebidos.append(payload)
                return {"ok": True}

            async def ensure_started(self):
                pass

            def _resolve_browser_id(self, bid):
                return bid

            def _page(self, bid):
                return self.pagina

        c._alvo_visivel(Core)
        ok(getattr(Core, c.MARK_ALVO), "marca que já aplicou")
        core = Core()
        core.pagina = _Pagina(devolve='[data-a0-alvo="1"]')
        eq(await core.content(1, {"selector": "input[type=password]"}), {"ok": True}, "devolve o original")
        eq(recebidos[-1], {"selector": '[data-a0-alvo="1"]'}, "lê o campo visível")
        eq(core.pagina.chamadas, ["input[type=password]"], "perguntou à página pelo seletor pedido")
        core.pagina = _Pagina(devolve="")
        await core.content(1, {"selector": "main"})
        eq(recebidos[-1], {"selector": "main"}, "sem troca, segue o seletor pedido")
        await core.content(1, None)
        eq(recebidos[-1], None, "sem seletor não pergunta nada")
        eq(core.pagina.chamadas, ["main"], "nenhuma pergunta extra sem seletor")
        core.pagina = _Pagina(erro=RuntimeError("página fechou"))
        await core.content(1, {"selector": "input"})
        eq(recebidos[-1], {"selector": "input"}, "erro na conferência não bloqueia a leitura")

    def t_print_so_depois_de_acao_que_age(self):
        v = _ver_tela()
        eq(v.acao_que_age("browser", {"action": "click", "ref": 3}), "click", "clique mostra a tela")
        eq(v.acao_que_age("browser", {"action": "Type-Submit"}), "type_submit", "nome normalizado")
        for acao in ("content", "screenshot", "list", "state", "detail", "close"):
            eq(v.acao_que_age("browser", {"action": acao}), "", f"{acao} só lê: sem print")
        eq(v.acao_que_age("code_execution_tool", {"action": "click"}), "", "outra ferramenta não")
        eq(v.acao_que_age("browser", None), "", "sem argumentos não")

    def t_print_vira_imagem_com_orientacao(self):
        import tempfile

        from PIL import Image

        v = _ver_tela()
        with tempfile.TemporaryDirectory() as d:
            arq = Path(d) / "browser-1.jpg"
            Image.new("RGB", (1280, 720), "white").save(arq, "JPEG")
            eq(v.caminho_do_print({"browser_snapshot": {"path": str(arq)}}), str(arq), "acha o print do passo")
            eq(v.caminho_do_print({"browser_snapshot": {"path": str(arq) + "x"}}), "", "arquivo que não existe")
            eq(v.caminho_do_print({}), "", "passo sem print")
            eq(v.caminho_do_print(None), "", "sem log")
            m = v.mensagem(str(arq), "type")
            eq(m["preview"], v.MARCA, "marcado como print automático")
            texto, imagem = m["raw_content"][0]["text"], m["raw_content"][1]
            ok("`type`" in texto and "1280x720" in texto, "diz a ação e o tamanho (coordenadas do clique)")
            ok("coordenadas" in texto and "evaluate" in texto, "ensina a clicar pela posição e não por evaluate")
            ok(imagem["image_url"]["url"].startswith("data:image/jpeg;base64,"), "a imagem vai junto")
            eq(v.mensagem(str(Path(d) / "nada.jpg"), "click"), None, "arquivo sumiu: nada")

    def t_licoes_no_prompt(self):
        v = _ver_tela()
        for trecho in ("tool_args", "print", "coordenadas", "wheel", "evaluate", "três jeitos"):
            ok(trecho in v.LICOES, f"lição sobre {trecho}")
        ext = (RAIZ / "extensions" / "python" / "system_prompt" / "_16_licoes_navegador.py").read_text(encoding="utf-8")
        ok("system_prompt.append(ver_tela.LICOES)" in ext, "a extensão põe as lições no prompt")

    def t_so_o_ultimo_print_fica(self):
        v = _ver_tela()

        class Msg:
            def __init__(self, content):
                self.content, self.summary = content, ""

            def set_summary(self, s):
                self.summary = s

        prints = [Msg({"raw_content": [], "preview": v.MARCA}) for _ in range(2)]
        outra = Msg({"raw_content": [], "preview": "<Image attachments loaded by path>"})
        texto = Msg("resultado da ferramenta")
        eq(v.apagar_antigos(prints + [outra, texto]), 2, "os prints automáticos anteriores saem")
        ok(all(p.summary for p in prints), "viram uma linha de texto")
        ok(not outra.summary and not texto.summary, "imagem pedida pelo agente e texto ficam")
        eq(v.apagar_antigos(prints), 0, "não apaga de novo")

    async def t_download_fica_com_o_nome_real_e_o_agente_sabe(self):
        import tempfile
        spec = importlib.util.spec_from_file_location("navegador_rapido_downloads_teste", RAIZ / "helpers" / "downloads.py")
        d = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(d)
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            reg = pasta / "baixados.jsonl"

            class Download:
                suggested_filename = "76437182_CL.xlsx"
                url = "https://outlook.office.com/anexo"

                async def save_as(self, caminho):
                    Path(caminho).write_bytes(b"x" * 2048)

            primeiro = await d.salvar(Download(), pasta, reg)
            eq(primeiro, pasta / "76437182_CL.xlsx", "salvo com o nome real")
            eq((await d.salvar(Download(), pasta, reg)).name, "76437182_CL (2).xlsx", "não sobrescreve o anterior")
            eq(d.nome_seguro("../../etc/passwd", pasta).parent, pasta, "nome com caminho não sai da pasta")
            texto = d.aviso(d.a_avisar(reg))
            ok("76437182_CL.xlsx (2 KB)" in texto and "76437182_CL (2).xlsx" in texto, f"o agente fica sabendo: {texto}")
            eq(d.a_avisar(reg), [], "avisa uma vez só")

            class Quebrado:
                suggested_filename = "a.pdf"

                async def save_as(self, caminho):
                    raise RuntimeError("canceled")

            eq(await d.salvar(Quebrado(), pasta, reg), None, "falha no download não derruba o navegador")

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
    r = asyncio.run(Suite().rodar(sys.argv[1] if len(sys.argv) > 1 else ""))
    for x in r["resultados"]:
        print("ok   " if x["ok"] else "FALHA", x["teste"], x.get("erro", ""), *(x.get("onde") or []) if not x["ok"] else "")
    print("TESTES", r["passou"], r["total"])
