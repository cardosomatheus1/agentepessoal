"""🖥️ "Resolver aqui" no Hermes (o navegador_visual do A0, 14/10, Matheus: "quero conseguir resolver pelo Telegram,
sem nada extra"): quando o agente precisa que o Matheus faça algo no navegador (login com 2FA, captcha, "segure o
botão", uma escolha), a ferramenta `resolver_aqui` manda a ele no Telegram o print da aba e o botão "🖥️ Resolver aqui",
que abre a página Navegador do portal NESSA aba, por um link assinado (o mesmo esquema do A0: segredo da ponte, 30 min,
só o dono). Lá um toque é um clique; "✅ Terminei" avisa esta conversa (o portal abre um pedido na mesma sessão) e o
agente confere a página. Só o dono (e os logins de teste, que não têm celular); convidados nunca (o navegador é o dele).
O agente nunca resolve captcha sozinho: este botão é justamente para o Matheus resolver."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

PLUGINS = Path("/a0/usr/plugins")
URL_AGENTE = Path("/a0/usr/agente/url.txt")  # o link público do portal (report_url.py)
PRINTS = Path("/a0/usr/whatsapp/matheus/navegador")  # a ponte só manda arquivos de /a0/usr
DONO = "matheus"

ESQUEMA = {
    "name": "resolver_aqui",
    "description": (
        "Manda ao Matheus, no Telegram, o print da aba do navegador e o botão \"🖥️ Resolver aqui\", que abre essa aba "
        "no celular dele para ELE fazer o que só ele pode: login com código/2FA, captcha, \"segure o botão\", uma "
        "escolha da conta dele. Use quando travar nisso (nunca tente resolver captcha você mesmo). `pedido`: o que ele "
        "deve fazer, curto e na língua dele (ex.: \"Entre na sua conta do iFood; o código chega no seu e-mail\"). "
        "`aba`: o id da aba ou um pedaço do endereço (vazio = a aba que está na frente). Depois de mandar, termine a "
        "sua resposta dizendo que está esperando; quando ele apertar \"✅ Terminei\", esta conversa recebe o aviso e você "
        "lê a página de novo (browser_snapshot) e segue. O botão abre a página Navegador do portal, no navegador do "
        "Telegram com o nome do bot (Luffy): é esta ferramenta, a sua, mostrando o seu navegador; nunca diga a ele que "
        "parece golpe."),
    "parameters": {"type": "object", "properties": {"pedido": {"type": "string"}, "aba": {"type": "string"}},
                   "required": ["pedido"], "additionalProperties": False},
}


def _tela():
    nome, caminho = "agentepessoal_tela_a0", PLUGINS / "navegador_visual" / "helpers" / "tela.py"
    antigo, mtime = sys.modules.get(nome), caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = mtime
        sys.modules[nome] = m
    return sys.modules[nome]


def _ponte():
    nome, caminho = "whatsapp_ponte", PLUGINS / "whatsapp" / "helpers" / "ponte.py"
    antigo, mtime = sys.modules.get(nome), caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = mtime
        sys.modules[nome] = m
    return sys.modules[nome]


def pode(login: str, convidado_instancia: str) -> bool:
    """Só o dono do navegador (e os logins de teste do operador, que não têm celular); nunca um convidado."""
    return not convidado_instancia and (login == DONO or login.startswith("teste_"))


def escolher_aba(abas: list, pedida: str) -> dict | None:
    pedida = str(pedida or "").strip()
    if pedida:
        for a in abas:
            if a.get("id") == pedida or pedida in str(a.get("currentUrl") or ""):
                return a
        return None
    return abas[0] if abas else None


def link(base: str, sessao: str, login: str, aba_id: str, segredo: str, tela=None) -> str:
    """O link do botão: a página Navegador do portal nessa aba, com a assinatura do A0 (o portal confere). O token é
    sessão.login.expira.assinatura: uma sessão com ponto quebraria o token, então fica sem link."""
    t = tela or _tela()
    base = str(base or "").strip().rstrip("/")
    if not base.startswith("https://") or not segredo or not sessao or "." in sessao or "." in login:
        return ""
    token = t.assinar(sessao, login, segredo)
    return f"{base}/navegador?t={urllib.parse.quote(token)}&aba={urllib.parse.quote(aba_id)}"


async def executar(args: dict, sessao: str, navegador=None, ponte=None, tela=None, base_url: str | None = None) -> str:
    pa = sys.modules["agentepessoal_ponte_a0"]
    login = pa.login_da_sessao(sessao)
    if not pode(login, pa.convidado_da_instancia()):
        return "NÃO FEITO: o \"Resolver aqui\" é só do Matheus (o navegador é o dele)."
    pedido = " ".join(str(args.get("pedido") or "").split())[:600]
    if not pedido:
        return "NÃO FEITO: diga em `pedido` o que ele deve fazer na tela."
    rt = navegador or pa.NavegadorCDP(os.environ.get("BROWSER_CDP_URL", ""))
    abas = (await rt.call("list")).get("browsers") or []
    aba = escolher_aba(abas, str(args.get("aba") or ""))
    if aba is None:
        return f"NÃO FEITO: não achei essa aba. Abas abertas: {[(a['id'], a.get('currentUrl', '')[:60]) for a in abas][:8]}"
    t = tela or _tela()
    base = base_url if base_url is not None else (URL_AGENTE.read_text().strip() if URL_AGENTE.exists() else "")
    url = link(base, sessao, login, aba["id"], t.segredo(), t)
    if not url:
        return "NÃO FEITO: o link do portal não está pronto (endereço público ou segredo da ponte ausente). Diga ao operador."
    foto = await rt.call("screenshot", aba["id"], quality=60)
    arquivo = ""
    if foto.get("image"):
        import base64

        PRINTS.mkdir(parents=True, exist_ok=True)
        caminho = PRINTS / f"resolver-{time.strftime('%Y%m%d-%H%M%S')}.jpg"
        caminho.write_bytes(base64.b64decode(foto["image"]))
        arquivo = str(caminho)
    p = ponte or _ponte()
    texto = f"🖥️ *Preciso de você no navegador*\n\n{pedido}\n\nToque em \"Resolver aqui\", faça na tela e aperte ✅ Terminei."
    erro = await asyncio.to_thread(p.enviar, login, texto, arquivo, aba.get("currentUrl", "")[:200], None, "urgente",
                                   True, "", {"titulo": "🖥️ Resolver aqui", "url": url})
    if erro:
        return f"NÃO FEITO: a mensagem não chegou ao celular ({str(erro)[:150]})."
    return ("Mandei a ele o print e o botão \"🖥️ Resolver aqui\" (vale 30 min). Termine agora a sua resposta dizendo, em "
            "uma linha, o que ele precisa fazer e que você espera. Quando ele apertar \"✅ Terminei\", esta conversa "
            "recebe o aviso: leia a página de novo (browser_snapshot), confira e siga. Não tente resolver você mesmo.")


def registrar(ctx) -> None:
    async def manipular(args, session_id=None, task_id=None, **kwargs):
        return await executar(args or {}, str(session_id or task_id or ""))

    ctx.register_tool(name="resolver_aqui", toolset="agentepessoal", schema=ESQUEMA, handler=manipular, is_async=True)
