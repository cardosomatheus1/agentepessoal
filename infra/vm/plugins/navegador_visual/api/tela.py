"""The live view of one chat's browser tab, opened from Telegram ("🖥️ Resolver aqui"); see helpers/tela.py.

GET ?t=<signed link>  → the page (works inside Telegram: a tap on the picture is a click on the page).
POST {"t", "acao", …}  → quadro (picture of the tab), conteudo (its text and filled fields), elementos (with refs), anexar (a file from ANEXOS), toque, arrastar, rolar, texto, tecla, recarregar, pronto.
No app login: the signed link is the key, and it opens only the tab of the chat it names, for its owner, for 30 min.
"""

import importlib.util
import json
import sys
from pathlib import Path

from helpers.api import ApiHandler, Request, Response

from plugins._browser.helpers.runtime import get_runtime


def _tela():
    caminho = Path(__file__).resolve().parents[1] / "helpers" / "tela.py"
    nome = "navegador_visual_tela"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


PAGINA = Path(__file__).resolve().parents[1] / "helpers" / "tela.html"
ESCOLHER = r"""(() => { const alvo = __TEXTO__;
  const todos = [];
  const varrer = (raiz) => {
    if (!raiz) return;
    raiz.querySelectorAll('select').forEach(s => todos.push(s));
    raiz.querySelectorAll('*').forEach(el => { if (el.shadowRoot) varrer(el.shadowRoot); });
    raiz.querySelectorAll('iframe').forEach(f => { try { varrer(f.contentDocument); } catch (e) {} });
  };
  varrer(document);
  for (const s of todos) {
    const o = [...s.options].find(o => o.text.trim() === alvo);
    if (!o) continue;
    Object.getOwnPropertyDescriptor(s.ownerDocument.defaultView.HTMLSelectElement.prototype, 'value').set.call(s, o.value);
    s.dispatchEvent(new Event('input', {bubbles: true}));
    s.dispatchEvent(new Event('change', {bubbles: true}));
    return 'escolhido: ' + o.text;
  }
  return 'opção não encontrada em ' + todos.length + ' listas: ' + todos.map(s => [...s.options].map(o => o.text).join('/')).join(' | ');
})()"""
ANEXOS = Path("/a0/usr/navegador_visual/anexos")  # what "anexar" may attach (put there by the operator)
TAMANHO = """(() => [innerWidth, innerHeight])()"""
# 16/10: the operator taking over a task reads the page as text (a picture cuts long fields, e.g. app credentials):
# the visible text plus the value of each filled field, nothing the screenshot of the same tab would not show
CONTEUDO = r"""(() => {
  const campos = [...document.querySelectorAll('input, textarea')].filter(c => c.type !== 'password' && c.value)
    .map(c => ({rotulo: (c.labels && c.labels[0] ? c.labels[0].innerText : '') || c.name || c.id || c.placeholder || '',
                valor: c.value}));
  return JSON.stringify({texto: (document.body.innerText || '').slice(0, 20000), campos: campos.slice(0, 50)});
})()"""
PRONTO = ("(Ele resolveu o que você pediu na tela do navegador, pelo botão do Telegram. Recarregue a sua aba ou abra o "
          "endereço de novo, confira e siga com a tarefa.)")


async def _na_pagina(runtime, bid, op: str, valor: str) -> str:
    """Runs on the browser's own thread (where its Playwright page lives) and works across every frame."""
    sessao = getattr(runtime, "_runtime", runtime)
    nucleo = sessao._core

    async def fazer():
        marca = nucleo.request_context_id.set(str(getattr(runtime, "context_id", "") or sessao.context_id))
        try:
            return await _fazer()
        finally:
            nucleo.request_context_id.reset(marca)

    async def _fazer():
        pagina = nucleo._page(nucleo._resolve_browser_id(bid))
        for quadro in pagina.frames:
            if op == "arquivo":
                campo = await quadro.query_selector('input[type="file"]')
                if campo:
                    await campo.set_input_files(valor)
                    return f"arquivo posto em {quadro.url[:80]}"
            else:
                for lista in await quadro.query_selector_all("select"):
                    try:
                        await lista.select_option(label=valor)
                        return f"escolhido {valor!r} em {quadro.url[:80]}"
                    except Exception:
                        continue
        if op == "escolher":  # a list the site draws itself: open it first (toque), then click the option by its text
            for quadro in pagina.frames:
                opcao = quadro.get_by_text(valor, exact=True)
                for i in range(await opcao.count()):
                    if await opcao.nth(i).is_visible():
                        await opcao.nth(i).click()
                        return f"cliquei na opção {valor!r}"
        return "não achei o campo em nenhum quadro da página"

    futuro = sessao._worker.event_loop_thread.run_coroutine(fazer())
    import asyncio
    return await asyncio.wrap_future(futuro)


def _erro(msg: str, status: int = 403) -> Response:
    return Response(f'{{"erro": "{msg}"}}', status=status, mimetype="application/json")


class Tela(ApiHandler):
    @classmethod
    def requires_auth(cls) -> bool:
        return False  # the signed link is the key (helpers/tela.py)

    @classmethod
    def requires_csrf(cls) -> bool:
        return False

    @classmethod
    def requires_api_key(cls) -> bool:
        return False

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET", "POST"]

    async def process(self, input: dict, request: Request) -> dict | Response:
        t = _tela()
        token = str(input.get("t") or request.args.get("t") or "")
        dados = t.conferir(token, t.segredo())
        if dados is None:
            return Response("<h3 style='font-family:sans-serif;padding:24px'>Este link expirou. Peça de novo ao agente.</h3>",
                            status=403, mimetype="text/html")
        from agent import AgentContext

        ctx = AgentContext.get(dados["contexto"])
        if ctx is None or str(ctx.get_data("dono") or "") != dados["usuario"]:
            return _erro("conversa não encontrada")
        if request.method == "GET":
            return Response(PAGINA.read_text(encoding="utf-8").replace("__TOKEN__", token), mimetype="text/html")
        acao = str(input.get("acao") or "")
        if acao == "pronto":
            from agent import UserMessage
            from helpers import message_queue as mq

            mq.log_user_message(ctx, "✅ Resolvi na tela (botão do Telegram)", [], None, source=" (Telegram)")
            ctx.communicate(UserMessage(message=PRONTO, attachments=[]))
            return {"ok": True}
        import time as _t

        ctx.set_data("navegador_em_uso_ate", _t.time() + 20 * 60)  # the cleanup (limpeza) leaves this tab alone
        abrir_nova = acao == "abrir" and str(input.get("url") or "").startswith("https://")
        runtime = await get_runtime(dados["contexto"], create=abrir_nova)
        if runtime is None:
            return _erro("esta conversa não tem navegador aberto", 404)
        lista = await runtime.call("list")
        bid = (lista or {}).get("last_interacted_browser_id")
        if bid is None and (lista or {}).get("browsers"):
            bid = lista["browsers"][-1].get("id")
        if bid is None and abrir_nova:  # the tab was closed (e.g. by the cleanup): the operator opens a new one
            await runtime.call("open", str(input.get("url")))
            return {"ok": True, "nova_aba": True}
        if bid is None:
            return _erro("esta conversa não tem aba aberta", 404)
        if acao == "elementos":  # the page as the agent's browser tool sees it, with the reference of each element
            r = await runtime.call("content", bid)
            return {"elementos": str((r or {}).get("content") or r)[:30000]}
        if acao == "campo":  # fill/choose/tick/click one element by its reference (from "elementos"): exact, unlike typing
            metodo, ref, valor = str(input.get("metodo") or ""), input.get("ref"), input.get("valor")
            if metodo == "type":
                r = await runtime.call("type", bid, ref, str(valor or "")[:2000])
            elif metodo == "select_option":
                r = await runtime.call("select_option", bid, ref, value=str(valor or ""))
            elif metodo == "set_checked":
                r = await runtime.call("set_checked", bid, ref, checked=bool(valor))
            elif metodo == "click":
                r = await runtime.call("click", bid, ref)
            elif metodo == "escolher":  # a <select> by the visible text of an option (sites that ignore select_option)
                r = await runtime.call("evaluate", bid, ESCOLHER.replace("__TEXTO__", json.dumps(str(valor or ""))))
            else:
                return _erro("método não permitido", 400)
            return {"ok": True, "resultado": str(r)[:500]}
        if acao == "anexar":  # attach a file to a file field (e.g. a logo); only from the operator's attachments folder
            caminho = Path(str(input.get("arquivo") or "")).resolve()
            if ANEXOS not in caminho.parents or not caminho.is_file():
                return _erro("arquivo fora da pasta de anexos", 400)
            r = await runtime.call("upload_file", bid, input.get("ref"), path=str(caminho))
            return {"ok": True, "resultado": str(r)[:500]}
        if acao == "pagina":  # straight on the page (all frames, cross-origin too) when the reference tools can't reach
            op, valor = str(input.get("op") or ""), str(input.get("valor") or "")
            if op not in ("arquivo", "escolher"):
                return _erro("operação não permitida", 400)
            if op == "arquivo":
                caminho = Path(valor).resolve()
                if ANEXOS not in caminho.parents or not caminho.is_file():
                    return _erro("arquivo fora da pasta de anexos", 400)
            return {"ok": True, "resultado": await _na_pagina(runtime, bid, op, valor)}
        if acao == "conteudo":
            r = await runtime.call("evaluate", bid, CONTEUDO)
            valor = (r or {}).get("result", (r or {}).get("value")) if isinstance(r, dict) else r
            return {"conteudo": valor}
        if acao == "quadro":
            foto = await runtime.call("screenshot", bid, quality=int(input.get("qualidade") or 60))
            estado = foto.get("state") or {}
            return {"imagem": foto.get("image"), "url": estado.get("url", ""), "titulo": estado.get("title", "")}
        largura, altura = ((await runtime.call("evaluate", bid, TAMANHO)) or {}).get("result") or [0, 0]
        if not largura or not altura:
            return _erro("não consegui medir a página", 500)

        def ponto(p):
            return max(0.0, min(1.0, float(p[0]))) * largura, max(0.0, min(1.0, float(p[1]))) * altura

        if acao == "toque":
            x, y = ponto((input.get("fx"), input.get("fy")))
            await runtime.call("mouse", bid, "click", x, y)
        elif acao == "arrastar":
            pontos = [ponto(p) for p in (input.get("pontos") or [])][:200]
            if len(pontos) < 2:
                return _erro("arraste curto", 400)
            await runtime.call("mouse", bid, "move", *pontos[0])
            await runtime.call("mouse", bid, "down", *pontos[0])
            for x, y in pontos[1:]:
                await runtime.call("mouse", bid, "move", x, y)
            await runtime.call("mouse", bid, "up", *pontos[-1])
        elif acao == "rolar":
            await runtime.call("wheel", bid, largura / 2, altura / 2, 0, float(input.get("dy") or 0) * altura)
        elif acao == "texto":
            await runtime.call("keyboard", bid, text=str(input.get("texto") or "")[:500])
        elif acao == "tecla":
            tecla = str(input.get("tecla") or "")
            if tecla not in ("Enter", "Backspace", "Tab", "Escape"):
                return _erro("tecla não permitida", 400)
            await runtime.call("keyboard", bid, key=tecla)
        elif acao == "recarregar":
            await runtime.call("reload", bid)
        elif acao == "abrir":  # the operator (or the person) taking over a task needs to change page
            url = str(input.get("url") or "")
            if not url.startswith("https://"):
                return _erro("só endereço https", 400)
            await runtime.call("navigate", bid, url)
        else:
            return _erro("ação desconhecida", 400)
        return {"ok": True}
