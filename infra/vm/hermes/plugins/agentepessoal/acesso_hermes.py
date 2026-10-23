"""O que cada conversa pode usar no Hermes (migração, fase 2), num gancho `pre_tool_call` (bloqueio determinístico; o
Hermes trata erro ou demora dele como bloqueio):

- Convidados (ilia, will; decisão 1 do Matheus, 23/10): só as ferramentas de uso pessoal, como no A0
  (login_usuarios/helpers/convidados.py). Nunca o `terminal`, o `execute_code` ou os arquivos do Hermes (leem
  /a0/usr/segredos e os dados de todos): o computador deles é o `terminal_isolado` (caixa própria). Nem a memória, a
  busca nas conversas, as skills, o cron ou o navegador do Matheus. Caminho local fora das pastas deles é recusado.
- Ensaio até a virada (AGENTEPESSOAL_ENSAIO=1): o navegador só lê (abrir, ler a página, rolar, voltar, ver imagens).
  Clicar, digitar, teclar, rodar JS ou CDP ficam bloqueados: com o perfil logado do Instagram, um clique pode seguir,
  curtir ou mandar um Direct. E o terminal/código não fala com o navegador por fora (CDP, devtools, Playwright).
"""
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

PLUGINS = Path("/a0/usr/plugins")

# Hermes + nossas: o equivalente de convidados.FERRAMENTAS (conversa, pesquisa, imagens/vídeo, arquivos que ele mandou,
# notas e cofre dele, o computador isolado dele). Rotinas e navegador dos convidados voltam com os perfis próprios deles.
CONVIDADO_PODE = frozenset({
    "web_search", "web_extract", "vision_analyze", "video_analyze", "clarify", "todo_list", "text_to_speech",
    "lembrar", "ficha", "cofre_descrever", "analisar_imagens", "assistir_video", "videos_em_alta", "whatsapp_enviar",
    "terminal_isolado", "ler",
})
# Ferramentas que leem um caminho local: só as pastas do convidado (convidados.caminho_proibido).
LEEM_CAMINHO = frozenset({"whatsapp_enviar", "analisar_imagens", "assistir_video", "ler", "vision_analyze", "video_analyze"})

NAVEGADOR_SO_LE = frozenset({"browser_navigate", "browser_snapshot", "browser_scroll", "browser_back",
                             "browser_get_images", "browser_vision"})
CDP = re.compile(r"(?i)\bcdp\b|devtools|remote-debugging|:9222\b|navegador-hermes|playwright|puppeteer|"
                 r"chrome-remote-interface|websocket|\bws://|agent-browser")
CODIGO = frozenset({"terminal", "execute_code", "process_manage"})


def ensaio() -> bool:
    return os.environ.get("AGENTEPESSOAL_ENSAIO") == "1"


def _convidados():
    nome, caminho = "agentepessoal_convidados", PLUGINS / "login_usuarios" / "helpers" / "convidados.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = mtime
        sys.modules[nome] = m
    return sys.modules[nome]


def _bloqueio(texto: str) -> dict:
    return {"action": "block", "message": texto}


def checar(tool_name="", args=None, session_id="", task_id="", **kw):
    """Gancho `pre_tool_call`: None = segue; {"action": "block"} = não roda."""
    args = args if isinstance(args, dict) else {}
    ponte = sys.modules["agentepessoal_ponte_a0"]
    login = ponte.login_da_sessao(str(session_id or task_id or ""))
    c = _convidados()
    if c.convidado(login):
        if tool_name not in CONVIDADO_PODE:
            return _bloqueio(f"«{tool_name}» não está disponível nesta conversa (uso pessoal de convidado). "
                             "Faça com as ferramentas que você tem ou diga com educação que não dá.")
        if tool_name in LEEM_CAMINHO:
            proibido = c.caminho_proibido(login, args)
            if proibido:
                return _bloqueio(f"O caminho {proibido} não é desta pessoa: só os arquivos que ela mandou.")
    if ensaio():
        if tool_name.startswith("browser_") and tool_name not in NAVEGADOR_SO_LE:
            return _bloqueio("Ensaio do Hermes: até a virada o navegador só lê (abrir, ler a página, rolar, voltar). "
                             "Clicar, digitar e teclar continuam com o agente de hoje; não tente de outro jeito. "
                             "Diga ao operador o que ia fazer.")
        if tool_name in CODIGO and CDP.search(json.dumps(args, ensure_ascii=False, default=str)):
            return _bloqueio("Ensaio do Hermes: o terminal e o código não falam com o navegador por fora. Use as "
                             "ferramentas browser_* (no ensaio, só leitura).")
    return None


def registrar(ctx) -> None:
    ctx.register_hook("pre_tool_call", checar)
