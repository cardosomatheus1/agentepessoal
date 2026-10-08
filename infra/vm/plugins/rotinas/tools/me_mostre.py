"""Record the user doing a task once in the agent's browser, to turn it into a routine.

iniciar: every 3 s, while the screen changes, saves a screenshot and the page address/title of
the chat's browser to chats/<id>/demonstracao/. parar: stops and returns the timeline and the
image paths, for the agent to study (analisar_imagens) and draft the routine (salvar_rotina).
Stops by itself after 20 min.
"""

import asyncio
import base64
import hashlib
import json
import time
from pathlib import Path

from helpers.tool import Response, Tool

GRAVACOES: dict[str, dict] = {}
LIMITE = 20 * 60


async def _gravar(ctx_id: str, pasta: Path, estado: dict) -> None:
    from plugins._browser.helpers.runtime import get_runtime

    ultimo = ""
    fim = time.time() + LIMITE
    while not estado["parar"] and time.time() < fim:
        try:
            rt = await get_runtime(ctx_id, create=False)
            if rt is not None:
                shot = await rt.call("screenshot", None, quality=60)
                img = base64.b64decode(shot["image"])
                marca = hashlib.sha1(img).hexdigest()
                if marca != ultimo:
                    ultimo = marca
                    n = len(estado["passos"]) + 1
                    arquivo = pasta / f"{n:03d}.jpg"
                    arquivo.write_bytes(img)
                    st = shot.get("state") or {}
                    passo = {"n": n, "s": round(time.time() - estado["inicio"]), "url": st.get("url", ""),
                             "titulo": st.get("title", ""), "imagem": str(arquivo)}
                    estado["passos"].append(passo)
                    with (pasta / "passos.jsonl").open("a", encoding="utf-8") as f:
                        f.write(json.dumps(passo, ensure_ascii=False) + "\n")
        except Exception as exc:
            estado["erro"] = str(exc)[:200]
        await asyncio.sleep(3)


class MeMostre(Tool):
    async def execute(self, acao: str = "iniciar", **kwargs) -> Response:
        ctx = self.agent.context
        acao = (acao or "iniciar").lower()
        if acao == "iniciar":
            antigo = GRAVACOES.get(ctx.id)
            if antigo and not antigo["tarefa"].done():
                return Response(message="Já estou gravando. Quando o usuário disser que terminou, use acao=parar.", break_loop=False)
            pasta = Path("/a0/usr/chats") / ctx.id / "demonstracao" / time.strftime("%Y%m%d-%H%M%S")
            pasta.mkdir(parents=True, exist_ok=True)
            estado = {"parar": False, "passos": [], "inicio": time.time(), "pasta": str(pasta), "erro": ""}
            estado["tarefa"] = asyncio.get_running_loop().create_task(_gravar(ctx.id, pasta, estado))
            GRAVACOES[ctx.id] = estado
            return Response(message=(
                "Gravando o navegador desta conversa (até 20 min). Diga ao usuário: abra o **Navegador** (globo, botão "
                "Ferramentas no celular), faça a tarefa uma vez do jeito certo e me avise com \"pronto\". Se o navegador "
                "ainda não estiver aberto, abra antes a página inicial da tarefa."), break_loop=False)
        estado = GRAVACOES.pop(ctx.id, None)
        if not estado:
            return Response(message="Não havia gravação em andamento.", break_loop=False)
        estado["parar"] = True
        try:
            await asyncio.wait_for(estado["tarefa"], timeout=10)
        except Exception:
            pass
        passos = estado["passos"]
        linhas = [f"{p['n']:03d} +{p['s']}s {p['titulo'][:60]} — {p['url'][:120]}" for p in passos]
        return Response(message=(
            f"Gravação parada: {len(passos)} telas em {estado['pasta']}" + (f" (aviso: {estado['erro']})" if estado["erro"] else "")
            + ".\nLinha do tempo:\n" + "\n".join(linhas[:80])
            + "\n\nAgora: estude as telas com analisar_imagens (passe a pasta), descreva os passos com as decisões que o "
              "usuário tomou, pergunte só o que não deu para entender, e salve com salvar_rotina."), break_loop=False)
