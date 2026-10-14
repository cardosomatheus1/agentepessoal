"""The live view of one chat's browser tab, opened from Telegram ("🖥️ Resolver aqui"); see helpers/tela.py.

GET ?t=<signed link>  → the page (works inside Telegram: a tap on the picture is a click on the page).
POST {"t", "acao", …}  → quadro (picture of the tab), toque, arrastar, rolar, texto, tecla, recarregar, pronto.
No app login: the signed link is the key, and it opens only the tab of the chat it names, for its owner, for 30 min.
"""

import importlib.util
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
TAMANHO = """(() => [innerWidth, innerHeight])()"""
PRONTO = ("(Ele resolveu o que você pediu na tela do navegador, pelo botão do Telegram. Recarregue a sua aba ou abra o "
          "endereço de novo, confira e siga com a tarefa.)")


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
        runtime = await get_runtime(dados["contexto"], create=False)
        if runtime is None:
            return _erro("esta conversa não tem navegador aberto", 404)
        lista = await runtime.call("list")
        bid = (lista or {}).get("last_interacted_browser_id")
        if bid is None and (lista or {}).get("browsers"):
            bid = lista["browsers"][-1].get("id")
        if bid is None:
            return _erro("esta conversa não tem aba aberta", 404)
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
        else:
            return _erro("ação desconhecida", 400)
        return {"ok": True}
