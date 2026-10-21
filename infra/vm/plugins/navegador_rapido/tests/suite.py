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

    async def t_campo_sem_label_ganha_o_rotulo_visual(self):
        c = _correcoes()
        js = next((p for p in (Path("/a0/plugins/_browser/assets/browser-page-content.js"),
                               Path(os.environ.get("A0SRC", "/nao-existe")) / "plugins/_browser/assets/browser-page-content.js")
                   if p.exists()), None)
        if js is None:
            return
        fonte = c.script_rapido(js.read_text(encoding="utf-8"))
        ok(fonte is not None and c.ROTULO_MARCA in fonte, "o script da captura recebe o rótulo visual")
        eq(c.com_rotulo_visual(fonte), fonte, "aplicar de novo não duplica")
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return
        exe = os.environ.get("CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
        if not Path(exe).exists():
            exe = "/a0/tmp/playwright/chromium-1228/chrome-linux/chrome"
        if not Path(exe).exists():
            return
        # como na Keeta: o nome do campo fica numa caixa acima, sem <label for>
        pagina = """<form>
          <div class="g"><div class="l"><span>*</span> Company Website</div><div class="c"><input type="text"></div></div>
          <div class="g"><div class="l"><span>*</span> Address</div><div class="c"><input type="text"></div></div>
          <div class="g"><label for="e">Email</label><input id="e" type="text"></div>
          <span id="t">Telefone</span><input aria-labelledby="t" type="text">
        </form>"""
        async with async_playwright() as p:
            b = await p.chromium.launch(executable_path=exe, headless=True)
            pg = await b.new_page()
            await pg.set_content(pagina)
            await pg.add_script_tag(content=fonte)
            texto = await pg.evaluate("async () => JSON.stringify(await globalThis.__spaceBrowserPageContent__.capture())")
            await b.close()
        for nome in ("Company Website", "Address", "Email", "Telefone"):
            ok(nome in texto, f"o campo aparece com o nome {nome!r}")

    async def t_digitou_e_conferiu_o_campo(self):
        c = _correcoes()
        ok(c.conferir_digitado("Rua A, 1", {"valor": "Rua A, 1"}).startswith("✓"), "igual: conferido")
        ok(c.conferir_digitado("71991564477", {"valor": "(71) 99156-4477"}).startswith("✓"), "máscara do site: conferido")
        ok(c.conferir_digitado("Rua do Rouxinol", {"valor": "https://x"}).startswith("⚠️"), "outro conteúdo: avisa")
        ok("NÃO ficou" in c.conferir_digitado("Rua A", {"valor": ""}), "campo vazio depois de digitar: avisa")
        eq(c.conferir_digitado("x", {"valor": None, "senha": True}), "", "senha não é lida")
        eq(c.conferir_digitado("x", None), "", "sem leitura: nada")
        js = next((p for p in (Path("/a0/plugins/_browser/assets/browser-page-content.js"),
                               Path(os.environ.get("A0SRC", "/nao-existe")) / "plugins/_browser/assets/browser-page-content.js")
                   if p.exists()), None)
        if js is None:
            return
        fonte = c.script_rapido(js.read_text(encoding="utf-8"))
        ok(c.VALOR_MARCA in fonte, "a API da página ganha a leitura do valor")
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return
        exe = os.environ.get("CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
        if not Path(exe).exists():
            exe = "/a0/tmp/playwright/chromium-1228/chrome-linux/chrome"
        if not Path(exe).exists():
            return
        async with async_playwright() as p:
            b = await p.chromium.launch(executable_path=exe, headless=True)
            pg = await b.new_page()
            # um site que reformata o que se digita (máscara de telefone)
            html = r"""<label for="t">Telefone</label><input id="t" type="text"
              oninput="this.value=this.value.replace(/(\d{2})(\d{5})(\d{4})/,'($1) $2-$3')">"""
            await pg.set_content(html)
            await pg.add_script_tag(content=fonte)
            api = "globalThis.__spaceBrowserPageContent__"
            await pg.evaluate(f"async () => {{ await {api}.capture(); }}")
            ref = "1"
            await pg.evaluate(f"(r) => {api}.type(r, '71991564477')", ref)
            lido = await pg.evaluate(f"(r) => {api}.a0ValorDe(r)", ref)
            await b.close()
        ok(isinstance(lido, dict) and "valor" in lido, f"leu o campo: {lido}")
        eq(lido, {"valor": "(71) 99156-4477"}, "leu o que o site deixou no campo")
        ok(c.conferir_digitado("71991564477", lido).startswith("✓"), "e a conferência entende a máscara")

    async def t_upload_pela_janela_de_arquivos_do_botao(self):
        c = _correcoes()
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return
        exe = os.environ.get("CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
        if not Path(exe).exists():
            exe = "/a0/tmp/playwright/chromium-1228/chrome-linux/chrome"
        if not Path(exe).exists():
            return
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            arq = Path(tmp) / "revisado.xlsx"
            arq.write_bytes(b"PK\x03\x04x")
            # como o Outlook: um campo escondido que manda para o OneDrive e um botão que cria, na hora, o campo do anexo
            html = """<input type="file" id="onedrive" style="display:none">
              <button id="b" style="position:absolute;left:40px;top:40px;width:200px;height:40px">Navegar neste computador</button>
              <div id="anexos"></div>
              <script>
                document.getElementById('b').onclick = () => {
                  const i = document.createElement('input'); i.type = 'file';
                  i.onchange = () => { document.getElementById('anexos').textContent = 'anexo: ' + i.files[0].name; };
                  i.click();
                };
              </script>"""
            async with async_playwright() as p:
                b = await p.chromium.launch(executable_path=exe, headless=True)
                pg = await b.new_page()
                await pg.set_content(html)
                ok(await c.pelo_seletor_de_arquivos(pg, {"x": 140, "y": 60}, [str(arq)]), "a janela de arquivos abriu")
                await pg.wait_for_timeout(200)
                eq(await pg.inner_text("#anexos"), "anexo: revisado.xlsx", "o arquivo foi para o anexo, não para o OneDrive")
                eq(await pg.evaluate("document.getElementById('onedrive').files.length"), 0, "o campo do OneDrive ficou vazio")
                ok(not await c.pelo_seletor_de_arquivos(pg, {"x": 5, "y": 300}, [str(arq)], espera_ms=800),
                   "clique que não abre janela: devolve False, sem travar")
                await b.close()

    def t_reaplica_correcao_nova_no_servidor_ja_rodando(self):
        c = _correcoes()

        class Core:
            def upload_file(self):
                return "original"

        original_upload = Core.upload_file

        def antigo(self):  # o embrulho da versão anterior, que guardava o original no fechamento
            return original_upload(self)

        Core.upload_file = antigo
        eq(c._original(Core, "upload_file", "original_upload")(None), "original", "acha o original dentro do embrulho")
        eq(Core._a0_original_upload_file(None), "original", "e guarda na classe para as próximas versões")

    async def t_espera_pelo_que_importa(self):
        c = _correcoes()
        args = {"action": "wait", "text": "Pedido enviado", "timeout": 5}
        ok(c.argumentos_de_espera(args) and args["action"] == "evaluate", "wait vira evaluate")
        ok("text" not in args and "timeout" not in args, "os argumentos da espera saem")
        ok(not c.argumentos_de_espera({"action": "click"}), "outra ação não muda")
        sem = {"action": "wait"}
        c.argumentos_de_espera(sem)
        ok('"load": true' in sem["script"], "sem condição: espera a página carregar")
        longo = {"action": "wait", "url": "x", "timeout": 999}
        c.argumentos_de_espera(longo)
        ok('"ms": 60000' in longo["script"], "teto de 60 s")
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return
        exe = os.environ.get("CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
        if not Path(exe).exists():
            exe = "/a0/tmp/playwright/chromium-1228/chrome-linux/chrome"
        if not Path(exe).exists():
            return
        async with async_playwright() as p:
            b = await p.chromium.launch(executable_path=exe, headless=True)
            pg = await b.new_page()
            await pg.set_content('<div id="s">Enviando...</div><script>setTimeout(() => {'
                                 'document.getElementById("s").textContent = "Pedido   enviado com sucesso"}, 800)</script>')
            r = await pg.evaluate(args["script"])
            ok(r["ok"] and 0.5 <= r["esperou_s"] <= 3, f"esperou o texto aparecer: {r}")
            sumiu = {"action": "wait", "text_gone": "Enviando", "timeout": 2}
            c.argumentos_de_espera(sumiu)
            ok((await pg.evaluate(sumiu["script"]))["ok"], "texto que sumiu")
            nunca = {"action": "wait", "selector": "#nao-existe", "timeout": 1}
            c.argumentos_de_espera(nunca)
            r = await pg.evaluate(nunca["script"])
            ok(not r["ok"] and "releia" in r["aviso"], f"não aconteceu: diz o próximo passo {r}")
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
