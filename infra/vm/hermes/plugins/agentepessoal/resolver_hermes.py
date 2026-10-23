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
        "`aba`: o id da aba ou um pedaço do endereço (vazio = a aba desta conversa, onde o browser_navigate abriu). Depois de mandar, termine a "
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


def _registro_abas() -> Path:
    """browser_own_tabs.json do Hermes (patch abas_por_sessao): dono (a conversa, ou cron:<job>) -> a aba dele."""
    try:
        from hermes_constants import get_hermes_home
        return Path(get_hermes_home()) / "browser_own_tabs.json"
    except Exception:
        return Path(os.environ.get("HERMES_HOME", "/opt/data")) / "browser_own_tabs.json"


def _dono(sessao: str) -> str:
    """O dono da aba como o Hermes grava (browser_tool_session._tab_owner): toda execução de uma rotina usa a do job."""
    partes = str(sessao or "default").split(":")
    return f"cron:{partes[1]}" if len(partes) >= 3 and partes[0] == "cron" and partes[1] else str(sessao or "default")


def aba_da_conversa(sessao: str, registro: Path | None = None) -> list:
    """Os ids das abas desta conversa (a própria e, se ela estava ocupada, a segunda "<dono>#..."), a mais recente
    primeiro."""
    try:
        dados = json.loads((registro or _registro_abas()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    dono = _dono(sessao)
    minhas = [v for k, v in (dados.items() if isinstance(dados, dict) else [])
              if isinstance(v, dict) and v.get("target_id") and (k == dono or k.startswith(dono + "#"))]
    return [v["target_id"] for v in sorted(minhas, key=lambda v: v.get("used") or 0, reverse=True)]


def escolher_aba(abas: list, pedida: str, da_conversa: list | None = None) -> dict | None:
    """A aba pedida (id ou pedaço do endereço) ou, sem pedido, a aba DESTA conversa (cada conversa e rotina tem a sua);
    nunca "a primeira da lista", que pode ser a de outra conversa."""
    pedida = str(pedida or "").strip()
    if pedida:
        for a in abas:
            if a.get("id") == pedida or pedida in str(a.get("currentUrl") or ""):
                return a
        return None
    for alvo in da_conversa or []:
        for a in abas:
            if a.get("id") == alvo:
                return a
    return None


def link(base: str, sessao: str, login: str, aba_id: str, segredo: str, tela=None) -> str:
    """O link do botão: a página Navegador do portal nessa aba, com a assinatura do A0 (o portal confere). O token é
    sessão.login.expira.assinatura: uma sessão com ponto quebraria o token, então fica sem link."""
    t = tela or _tela()
    base = str(base or "").strip().rstrip("/")
    if not base.startswith("https://") or not segredo or not sessao or "." in sessao or "." in login:
        return ""
    token = t.assinar(sessao, login, segredo)
    return f"{base}/navegador?t={urllib.parse.quote(token)}&aba={urllib.parse.quote(aba_id)}"


async def executar(args: dict, sessao: str, navegador=None, ponte=None, tela=None, base_url: str | None = None,
                   registro: Path | None = None) -> str:
    pa = sys.modules["agentepessoal_ponte_a0"]
    login = pa.login_da_sessao(sessao)
    if not pode(login, pa.convidado_da_instancia()):
        return "NÃO FEITO: o \"Resolver aqui\" é só do Matheus (o navegador é o dele)."
    pedido = " ".join(str(args.get("pedido") or "").split())[:600]
    if not pedido:
        return "NÃO FEITO: diga em `pedido` o que ele deve fazer na tela."
    rt = navegador or pa.NavegadorCDP(os.environ.get("BROWSER_CDP_URL", ""))
    abas = (await rt.call("list")).get("browsers") or []
    aba = escolher_aba(abas, str(args.get("aba") or ""), aba_da_conversa(sessao, registro))
    if aba is None and not str(args.get("aba") or "").strip():
        return ("NÃO FEITO: esta conversa ainda não tem aba no navegador. Abra a página com browser_navigate (ela abre na "
                "aba desta conversa) e chame de novo, ou diga em `aba` o id ou um pedaço do endereço.")
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
