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
                # 21/10, de novo: o agente chamou upload_file só com seletor; sem ref, a ferramenta acha sozinha o
                # "Anexar arquivo" (que abre um menu) e depois o "Navegar neste computador" do menu
                menu = """<input type="file" id="onedrive" style="display:none" multiple>
                  <input type="file" id="onedrive2" style="display:none" multiple>
                  <button aria-label="Arquivo">Arquivo</button>
                  <button aria-label="Anexar arquivo" id="anx">Anexe um arquivo a este item.</button>
                  <div id="m" role="menu" style="display:none">
                    <div role="menuitem">Carregar e compartilhar</div>
                    <div role="menuitem" id="pc">Navegar neste computador</div></div>
                  <div id="anexos"></div>
                  <script>
                    document.getElementById('anx').onclick = () => { document.getElementById('m').style.display = 'block'; };
                    document.getElementById('pc').onclick = () => {
                      const i = document.createElement('input'); i.type = 'file';
                      i.onchange = () => { document.getElementById('anexos').textContent = 'anexo: ' + i.files[0].name; };
                      i.click();
                    };
                  </script>"""
                await pg.set_content(menu)
                eq(await c.pelo_gatilho_da_pagina(pg, [str(arq)]), "Anexar arquivo Anexe um arquivo a este item. → "
                   "Navegar neste computador", "abriu o menu e usou o item do computador")
                await pg.wait_for_timeout(200)
                eq(await pg.inner_text("#anexos"), "anexo: revisado.xlsx", "virou anexo")
                eq(await pg.evaluate("document.getElementById('onedrive').files.length + "
                                     "document.getElementById('onedrive2').files.length"), 0, "nada no OneDrive")
                await pg.set_content('<input type="file" id="f" style="display:none"><p>sem botão</p>')
                eq(await c.pelo_gatilho_da_pagina(pg, [str(arq)]), "", "sem botão de anexar: devolve vazio (vai ao campo)")
                await b.close()

    async def t_chamadas_reais_que_falharam_no_registro(self):
        """21/10: as chamadas exatas do agente que mais falharam em 4 dias de registro."""
        c = _correcoes()
        # relatório da 1ª noite (21/10): as chamadas exatas
        args = {"action": "click", "browser_id": 17, "ref": "button 22"}
        ok(c.argumentos_de_ref(args) and args["ref"] == "22", f"ref 'button 22' vira 22: {args}")
        args = {"action": "click", "browser_id": 17, "ref": "editable 64"}
        ok(c.argumentos_de_ref(args) and args["ref"] == "64", "ref 'editable 64' vira 64")
        args = {"action": "drag", "ref": "[link 3]", "target_ref": "input text 9"}
        ok(c.argumentos_de_ref(args) and (args["ref"], args["target_ref"]) == ("3", "9"), f"com colchetes e alvo: {args}")
        ok(not c.argumentos_de_ref({"action": "click", "ref": "22"}), "ref certa fica")
        ok(not c.argumentos_de_ref({"action": "click", "ref": 22}), "ref número fica")
        args = {"action": "key_chord", "browser_id": 45, "key": "Enter"}
        ok(c.argumentos_de_ref(args) and args["keys"] == ["Enter"] and "key" not in args, f"key_chord com key: {args}")
        args = {"action": "key_chord", "browser_id": 37, "text": "Control+a"}
        ok(c.argumentos_de_ref(args) and args["keys"] == ["Control", "a"], "key_chord com text")
        ok(not c.argumentos_de_ref({"action": "key_chord", "keys": ["Escape"]}), "keys certo fica")
        # teclas em maiúsculas
        args = {"action": "keyboard", "key": "ENTER"}
        ok(c.argumentos_de_teclas(args) and args["key"] == "Enter", "ENTER → Enter")
        args = {"action": "key_chord", "keys": ["CONTROL", "a"]}
        ok(c.argumentos_de_teclas(args) and args["keys"] == ["Control", "a"], "CONTROL → Control")
        eq(c.tecla("ARROWDOWN"), "ArrowDown", "seta")
        eq(c.tecla("ctrl+A"), "Control+a", "combinação")
        eq(c.tecla("a"), "a", "letra fica")
        ok(not c.argumentos_de_teclas({"action": "keyboard", "key": "Enter"}), "certa não muda")
        # 21/10: keys como texto ("Control+a", "Backspace") era apertado letra por letra
        args = {"action": "key_chord", "keys": "Control+a"}
        ok(c.argumentos_de_teclas(args) and args["keys"] == ["Control", "a"], f"keys em texto vira lista: {args}")
        args = {"action": "key_chord", "keys": "Backspace"}
        ok(c.argumentos_de_teclas(args) and args["keys"] == ["Backspace"], "uma tecla só, também")
        # scroll sem ref
        args = {"action": "scroll", "browser_id": 3}
        ok(c.argumentos_de_rolagem(args) and args["action"] == "wheel" and args["delta_y"] == 700, "rola para baixo")
        args = {"action": "scroll", "direction": "up", "amount": 300}
        ok(c.argumentos_de_rolagem(args) and args["delta_y"] == -300, "rola para cima")
        ok(not c.argumentos_de_rolagem({"action": "scroll", "ref": "5"}), "com ref fica")
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return
        exe = os.environ.get("CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
        if not Path(exe).exists():
            exe = "/a0/tmp/playwright/chromium-1228/chrome-linux/chrome"
        if not Path(exe).exists():
            return
        html = """<button aria-label="Next" id="n" style="margin-top:900px" onclick="this.textContent='clicado'">→</button>
          <input id="i" value="velho"><div id="e" contenteditable="true" style="width:300px;height:30px"></div>
          <div id="lista" style="width:200px;height:30px;border:1px solid" onclick="document.getElementById('ops').style.display='block'">Escolha</div>
          <ul id="ops" style="display:none"><li onclick="document.getElementById('lista').textContent=this.textContent">Bahia</li>
            <li onclick="document.getElementById('lista').textContent=this.textContent">Sergipe</li></ul>"""
        async with async_playwright() as p:
            b = await p.chromium.launch(executable_path=exe, headless=True)
            pg = await b.new_page()
            await pg.set_content(html)

            async def chamar(metodo, bid, *a, **k):
                if metodo == "a0_ponto_do_seletor":
                    return await pg.evaluate(c.PONTO_DO_SELETOR_JS, a[0])
                if metodo == "mouse":
                    return await pg.mouse.click(a[1], a[2])
                if metodo == "key_chord":
                    return await pg.keyboard.press("+".join(a[0]))
                if metodo == "keyboard":
                    return await pg.keyboard.type(k.get("text", ""))

            # 55 cliques: click com selector "button[aria-label='Next']" e sem ref
            args = {"action": "click", "browser_id": 1, "selector": "button[aria-label='Next']"}
            eq(await c.resolver_seletor(args, chamar), "", "achou")
            ok("selector" not in args and args["x"] > 0, f"virou clique por coordenada: {args}")
            await pg.mouse.click(args["x"], args["y"])
            eq(await pg.inner_text("#n"), "clicado", "e o clique pegou o botão (estava fora da tela)")
            args = {"action": "click", "selector": "text=Escolha"}
            await c.resolver_seletor(args, chamar)
            ok("x" in args, "text= também")
            args = {"action": "type", "selector": "#i", "text": "novo"}
            await c.resolver_seletor(args, chamar)
            eq(args["action"], "keyboard", "type por seletor: clica no campo e digita pelo teclado")
            await pg.keyboard.type(args["text"])
            eq(await pg.input_value("#i"), "novo", "substituiu o que havia")
            nota = await c.resolver_seletor({"action": "click", "selector": "#nao-existe"}, chamar)
            ok("não achou" in nota, "seletor sem elemento: diz o que fazer")

            # 17 select_option em lista feita pelo site; 3 type em <div>
            class Core:
                async def select_option(self, browser_id, ref, value="", values=None):
                    raise RuntimeError('Browser page content cannot select helper-backed reference "1".')

                async def type(self, browser_id, reference_id, text):
                    raise RuntimeError("Browser DOM helper cannot type into <div>.")

                def _resolve_browser_id(self, b):
                    return b

                def _page(self, b):
                    return pg

                async def _point_for(self, page, ref):
                    return await page.evaluate("(id) => { const r = document.getElementById(id).getBoundingClientRect();"
                                               " return {x: r.x + r.width / 2, y: r.y + r.height / 2}; }", ref)

                async def _settle(self, page, short=False):
                    pass

                def _maybe_promote(self, b):
                    pass

                async def _state(self, b):
                    return {}

            c._lista_do_site(Core)
            r = await Core().select_option(1, "lista", value="Sergipe")
            eq(r["action"]["opcao"], "sergipe", "abriu a lista e clicou na opção")
            eq(await pg.inner_text("#lista"), "Sergipe", "a lista ficou com a opção")
            r = await Core().type(1, "e", "Olá Bruno")
            eq(await pg.inner_text("#e"), "Olá Bruno", "digitou na caixa feita pelo site")
            ok(r["conferido"].startswith("✓"), f"e conferiu: {r['conferido']}")

            # 21/10, Direct do Instagram: a caixa do site acrescenta o texto a cada `type`; dois `type` mandariam duplicado
            class Acrescenta(Core):
                _a0_original_type = None  # a classe nova guarda o próprio original (não o herdado de Core)

                async def type(self, browser_id, reference_id, text):
                    await pg.click("#e")
                    await pg.keyboard.press("End")
                    await pg.keyboard.type(text)
                    return {"ok": True}
            c._lista_do_site(Acrescenta)
            await Acrescenta().type(1, "e", "Segue o link")
            await Acrescenta().type(1, "e", "Segue o link")
            eq(await pg.inner_text("#e"), "Segue o link", "digitar de novo substitui o que a caixa tinha, sem duplicar")

            # 21/10, 2ª vez: a caixa do Direct é uma ref "helper-backed" (num frame), sem ponto; o clique da ferramenta chega
            class SemPonto(Acrescenta):
                _a0_original_type = None

                async def _point_for(self, page, ref):
                    raise RuntimeError('Page.evaluate: BrowserPageContentActionError: Browser page content cannot resolve '
                                       'point for helper-backed reference "44".')

                async def scroll(self, browser_id, ref):  # A0: scrollIntoView + focus, sem clique
                    await pg.focus("#e")
                    return {}
            c._lista_do_site(SemPonto)
            await SemPonto().type(1, "44", "Segue o link")
            eq(await pg.inner_text("#e"), "Segue o link", "ref sem ponto: foca pela ferramenta, limpa e não duplica")
            await b.close()

    async def t_print_com_o_numero_de_cada_ref(self):
        c = _correcoes()
        js = next((p for p in (Path("/a0/plugins/_browser/assets/browser-page-content.js"),
                               Path(os.environ.get("A0SRC", "/nao-existe")) / "plugins/_browser/assets/browser-page-content.js")
                   if p.exists()), None)
        if js is None:
            return
        fonte = c.script_rapido(js.read_text(encoding="utf-8"))
        ok(c.ROTULOS_MARCA in fonte and c.VALOR_MARCA in fonte, "a API da página ganha os rótulos (e mantém o valor lido)")
        eq(c.com_rotulos(fonte), fonte, "não duplica")
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return
        exe = os.environ.get("CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
        if not Path(exe).exists():
            exe = "/a0/tmp/playwright/chromium-1228/chrome-linux/chrome"
        if not Path(exe).exists():
            return
        html = """<h1>Cadastro</h1><div><label for="n">Nome</label><input id="n"><button>Salvar</button>
          <a href="#x">Ajuda</a></div><div style="margin-top:3000px"><button>Lá embaixo</button></div>"""
        async with async_playwright() as p:
            b = await p.chromium.launch(executable_path=exe, headless=True)
            pg = await b.new_page()
            await pg.set_content(html)
            # como no servidor: o ajudante de DOM antes do script de leitura (a leitura passa por ele)
            ajudante = c.helper_rapido((js.parent / "browser-dom-helper.js").read_text(encoding="utf-8"))
            ok(ajudante and c.ELEMENTO_MARCA in ajudante, "o ajudante expõe o elemento vivo")
            await pg.add_script_tag(content=ajudante)
            await pg.add_script_tag(content=fonte)
            api = "globalThis.__spaceBrowserPageContent__"
            await pg.evaluate(f"() => {api}.capture(null)")
            ok(await pg.evaluate("() => Boolean(globalThis.__spaceBrowserDomHelper__?.a0Elemento)"), "ajudante carregado")
            await pg.fill("#n", "Matheus")
            ref = "1"  # [input text 1] Nome
            eq(await pg.evaluate(f"(r) => {api}.a0ValorDe(r)", ref), {"valor": "Matheus"},
               "a conferência do digitado acha o campo vivo pelo ajudante")

            class Core:
                def _resolve_browser_id(self, b):
                    return b

                def _page(self, b):
                    return pg

                async def content(self, b, payload):
                    return await pg.evaluate(f"() => {api}.capture(null)")

                async def screenshot_file(self, browser_id=None, *, quality=80, full_page=False, path=""):
                    # o que estava na tela na hora do print
                    return {"na_tela": await pg.evaluate(
                        "() => [...(document.getElementById('__a0_rotulos__')?.children || [])].map(e => e.textContent)")}

            c._print_rotulado(Core)
            r = await Core().screenshot_file(1)
            ok(r["na_tela"], f"o print saiu com números: {r}")
            ok("refs" in r.get("rotulos", ""), "e o resultado explica os números")
            leitura = json_texto = str(await pg.evaluate(f"() => {api}.capture(null)"))
            for numero in r["na_tela"]:
                ok(f" {numero}]" in json_texto, f"o número {numero} existe na leitura que o agente recebe: {leitura[:400]}")
            eq(len(r["na_tela"]), 3, f"só os elementos visíveis ganham número (o 'Lá embaixo' fica de fora): {r}")
            eq(await pg.evaluate("() => document.getElementById('__a0_rotulos__')"), None, "os números somem depois do print")
            r = await Core().screenshot_file(1, full_page=True)
            eq(r["na_tela"], [], "página inteira: sem números")
            # 21/10: a 1ª versão ficou presa no servidor rodando; reinstalar embrulha o original, não o embrulho antigo
            setattr(Core, c.MARK_PRINT, True)
            c._print_rotulado(Core)
            eq(getattr(Core, c.MARK_PRINT), c.VERSAO_PRINT, "marca com a versão")
            r = await Core().screenshot_file(1)
            ok(r["na_tela"] and "rotulos" in r, f"reinstalado continua funcionando: {r}")
            await b.close()

    async def t_pagina_grande_inteira_em_arquivo(self):
        import tempfile
        import types

        stubs = {"agent": types.ModuleType("agent"), "helpers": types.ModuleType("helpers"),
                 "helpers.extension": types.ModuleType("helpers.extension")}
        stubs["agent"].LoopData = type("LoopData", (), {"__init__": lambda s: setattr(s, "extras_temporary", {})})
        stubs["helpers.extension"].Extension = type("Extension", (), {"__init__": lambda s, agent=None: setattr(s, "agent", agent)})
        antes = {k: sys.modules.get(k) for k in stubs}
        sys.modules.update(stubs)
        try:
            spec = importlib.util.spec_from_file_location(
                "navegador_rapido_limitar_teste", RAIZ / "extensions" / "python" / "message_loop_prompts_after" / "_21_limitar_pagina.py")
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
        finally:
            for k, v in antes.items():
                sys.modules.pop(k, None) if v is None else sys.modules.__setitem__(k, v)
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            pagina = "\n".join(f"linha {i}: " + "x" * 60 for i in range(1, 2001))
            curto = m.cortar(pagina, "ctxA1", pasta)
            ok(len(curto) < 21_000, "o passo leva só o começo")
            arquivos = list(pasta.glob("*.txt"))
            eq(len(arquivos), 1, "a página inteira foi guardada")
            eq(arquivos[0].read_text(encoding="utf-8"), pagina, "inteira, sem corte")
            ok(f"caminho {arquivos[0]}" in curto and "`ler`" in curto, f"diz onde está e com que ferramenta: {curto[-400:]}")
            ultima = curto.split("[page text cut")[0].rstrip().splitlines()[-1]
            proxima = int(curto.split(" and inicio ")[1].split(" ")[0])
            eq(pagina.splitlines()[proxima - 1], f"linha {proxima}: " + "x" * 60, "inicio aponta a linha certa")
            ok(ultima.startswith(f"linha {proxima - 1}:"), "o início continua logo depois do corte")
            m.cortar(pagina, "ctxA1", pasta)
            eq(len(list(pasta.glob("*.txt"))), 1, "a mesma página não é gravada de novo")
            for n in range(m.GUARDAR + 3):
                m.cortar(pagina + f"\nvariação {n}", "ctxA1", pasta)
            eq(len(list(pasta.glob("*.txt"))), m.GUARDAR, "guarda só as últimas")
            eq(m.cortar("curta", "ctx", pasta), "curta", "página curta fica igual")
            ok("whole page" not in m.cortar(pagina, "ctx", pasta / "arquivo.txt" / "nao"), "sem pasta: corta sem prometer arquivo")
            ld = stubs["agent"].LoopData()
            ld.extras_temporary["browser_context"] = pagina
            ag = types.SimpleNamespace(context=types.SimpleNamespace(id="ctxB2"))
            m.PASTA = pasta
            await m.LimitarPagina(ag).execute(loop_data=ld)
            ok("ctxB2-" in ld.extras_temporary["browser_context"], "o gancho grava com o id da conversa")

    async def t_navegador_que_caiu_reinicia(self):
        c = _correcoes()
        import types

        chamadas = []

        class Core:
            async def _discard_stale_context(self, m):
                chamadas.append("reiniciou")

        class BrowserRuntime:
            def __init__(self):
                self.caiu = True
                self._core = Core()

            async def call_for(self, context_id, method, *a, **k):
                if method == "a0_reiniciar":
                    return await getattr(self._core, method)()
                if self.caiu:
                    self.caiu = False
                    raise RuntimeError("BrowserContext.new_page: Connection closed while reading from the driver")
                return {"ok": method}

        mod = types.SimpleNamespace(BrowserRuntime=BrowserRuntime, _BrowserRuntimeCore=Core)
        c._reinicio_se_cair(mod)
        eq(await BrowserRuntime().call_for("x", "open", "https://a"), {"ok": "open"}, "open: reiniciou e repetiu")
        eq(chamadas, ["reiniciou"], "reiniciou uma vez")
        try:
            await BrowserRuntime().call_for("x", "click", 1, "5")
            ok(False, "clique depois de cair deveria avisar")
        except RuntimeError as exc:
            ok("reiniciado" in str(exc) and "Abra a página" in str(exc), f"clique: diz para reabrir: {exc}")

    async def t_janelas_do_site_respondidas_e_avisadas(self):
        c = _correcoes()

        class Core:
            pass

        args = {"action": "dialog", "accept": True}
        ok(c.argumentos_de_dialogo(args, "ctx", Core) and args == {"action": "state"}, "dialog arma e vira state")
        eq(getattr(Core, c.ARMADO)["ctx"]["accept"], True, "armado para OK")
        getattr(Core, c.ARMADO).clear()
        ok(not c.argumentos_de_dialogo({"action": "click"}, "ctx", Core), "outra ação não muda")
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return
        exe = os.environ.get("CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
        if not Path(exe).exists():
            exe = "/a0/tmp/playwright/chromium-1228/chrome-linux/chrome"
        if not Path(exe).exists():
            return
        import asyncio
        async with async_playwright() as p:
            b = await p.chromium.launch(executable_path=exe, headless=True)
            pg = await b.new_page()
            pg.on("dialog", lambda d: asyncio.ensure_future(c.responder_dialogo(Core, "ctx", d)))
            await pg.set_content('<div id="r"></div>'
                                 '<button id="x" onclick="document.getElementById(\'r\').textContent = '
                                 'confirm(\'Excluir o rascunho?\') ? \'excluido\' : \'mantido\'">Excluir</button>'
                                 '<button id="a" onclick="alert(\'Salvo!\')">Salvar</button>')
            await pg.click("#x")
            await pg.wait_for_timeout(200)
            eq(await pg.inner_text("#r"), "mantido", "sem armar: Cancelar (seguro)")
            c.argumentos_de_dialogo({"action": "dialog", "accept": True}, "ctx", Core)
            await pg.click("#x")
            await pg.wait_for_timeout(200)
            eq(await pg.inner_text("#r"), "excluido", "armado: OK")
            await pg.click("#a")
            await pg.wait_for_timeout(200)
            await b.close()
        texto = c.aviso_dialogos(getattr(Core, c.DIALOGOS).pop("ctx"))
        ok("Excluir o rascunho?" in texto and "Cancelar (padrão seguro)" in texto and '"accept": true' in texto,
           f"o agente fica sabendo o que o site perguntou e como confirmar: {texto}")
        ok("OK (como você deixou armado)" in texto and "Salvo!" in texto and "OK (era só um aviso)" in texto,
           "confirmação armada e aviso também aparecem")

    async def t_erros_da_pagina_e_chamadas_que_falharam(self):
        c = _correcoes()

        class Core:
            context_id = "ctx9"

            async def _ensure_content_helper(self, page):
                return None

        c._ouvintes(Core)
        sem = {"action": "erros"}
        ok("Nenhum erro" in c.argumentos_de_erros(sem, "ctx9", Core) and sem["action"] == "state", "sem erros: diz")
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
            await pg.route("https://api.exemplo.test/**", lambda r: r.fulfill(status=422, body='{"erro":"cnpj"}'))
            await pg.goto("https://api.exemplo.test/pagina")  # documento 422 também conta
            await Core()._ensure_content_helper(pg)
            await pg.evaluate("""() => { console.error('Falha ao salvar o formulário');
                fetch('https://api.exemplo.test/salvar', {method: 'POST'});
                setTimeout(() => { throw new Error('quebrou'); }, 0); }""")
            await pg.wait_for_timeout(500)
            await b.close()
        args = {"action": "erros"}
        texto = c.argumentos_de_erros(args, "ctx9", Core)
        for trecho in ("Falha ao salvar o formulário", "HTTP 422", "POST https://api.exemplo.test/salvar", "quebrou"):
            ok(trecho in texto, f"mostra {trecho!r}: {texto}")
        ok("Nenhum erro" in c.argumentos_de_erros({"action": "erros"}, "ctx9", Core), "mostra uma vez e limpa")

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
        # 21/10: o print com números não apareceu no servidor rodando, porque a troca do script só olhava as marcas antigas
        script = f"navegadorRapidoHidden {c.ROTULO_MARCA} {c.VALOR_MARCA}\n" + c.VALOR_FIM

        def montar(fonte):
            async def _ensure_content_helper(self, page):
                return fonte
            return _ensure_content_helper

        Core._ensure_content_helper = montar(script)
        c._atualizar_script_vivo(Core)
        novo = Core._ensure_content_helper.__closure__[0].cell_contents
        ok(c.ROTULOS_MARCA in novo, "o script vivo ganha os números do print")
        c._atualizar_script_vivo(Core)
        eq(Core._ensure_content_helper.__closure__[0].cell_contents, novo, "trocar de novo não duplica")

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
