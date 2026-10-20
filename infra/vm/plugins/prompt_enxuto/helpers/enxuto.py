"""Shorter prompt for every model call (20/10): the tool list goes with one line per tool, and each tool's full
description (its manual) comes once per chat, right after the tool's first result.

Measured on 20/10 in Matheus's phone chat: 52 tools = 23.2k tokens of descriptions in every call, ~60% of the fixed part
of the prompt. The model needs the detail of a tool only when it uses it.

Text mode (20/10, the Sonnet preset: `a0_api_mode: chat`): no native tool list goes; Agent Zero writes every tool's
prompt into the system prompt ("## available tools", one "### <tool>" per prompt file). `encurtar_texto` does the same
there: one short line per tool, the whole prompt file becomes the manual (MANUAIS_TEXTO: the text-mode wording, with
its `tool_name`/`tool_args` examples).

Switch: the file DESLIGADO exists = everything here is off (full descriptions again, no manual), no deploy needed."""

import copy
import os
import re
from pathlib import Path

DESLIGADO = Path("/a0/usr/plugins/prompt_enxuto/desligado")
MARCA = "📘 Manual da ferramenta `{nome}`"

# full descriptions seen in this process, by tool name (filled by the first model call after a start or deploy)
MANUAIS: dict[str, str] = {}
# the same in text mode (the tool's prompt file as Agent Zero writes it into the system prompt)
MANUAIS_TEXTO: dict[str, str] = {}

# how Agent Zero names the tools of a prompt file (helpers/responses_tools.py; used only when it cannot be imported)
_DECLARACAO = re.compile(r"^\s*-\s+`([A-Za-z0-9_-]{1,64})`:\s+(args?\b.*)$", re.IGNORECASE | re.MULTILINE)
_EXEMPLO = re.compile(r"""["']tool_name["']\s*:\s*["']([A-Za-z0-9_-]{1,64})["']""")
_TITULO = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", re.MULTILINE)
_NOME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def ligado() -> bool:
    try:
        return not DESLIGADO.exists()
    except OSError:
        return True


def encurtar(ferramentas: list, curtas: dict, min_ganho: int, manuais: dict | None = None) -> list:
    """A copy of the Responses tool list with the short descriptions; the full ones are kept in `manuais`.
    Only the description changes (name and parameters stay), and only when it saves at least `min_ganho` characters."""
    manuais = MANUAIS if manuais is None else manuais
    saida = []
    for f in ferramentas or []:
        if not isinstance(f, dict):
            saida.append(f)
            continue
        nome, descricao = str(f.get("name") or ""), str(f.get("description") or "")
        curta = curtas.get(nome)
        if not curta or len(descricao) - len(curta) < min_ganho:
            saida.append(f)
            continue
        manuais[nome] = descricao
        nova = copy.copy(f)
        nova["description"] = curta
        saida.append(nova)
    return saida


def _texto(conteudo) -> str:
    if isinstance(conteudo, str):
        return conteudo
    try:
        return str(conteudo)
    except Exception:
        return ""


def no_historico(saida_historico, trecho: str) -> bool:
    """`trecho` is in what the model still sees of the history (a summarized part no longer counts)."""
    for m in saida_historico or []:
        conteudo = m.get("content") if isinstance(m, dict) else getattr(m, "content", "")
        if trecho in _texto(conteudo):
            return True
    return False


def manual(nome: str, manuais: dict | None = None, texto_modo: bool = False) -> str:
    """The history message with a tool's manual, or "" when there is none. `texto_modo`: the chat's model gets the tools
    as text (the manual in that wording first)."""
    if manuais is None:
        primeiro, segundo = (MANUAIS_TEXTO, MANUAIS) if texto_modo else (MANUAIS, MANUAIS_TEXTO)
        texto = primeiro.get(nome) or segundo.get(nome, "")
    else:
        texto = manuais.get(nome, "")
    if not texto:
        return ""
    return (f"{MARCA.format(nome=nome)} (vem uma vez por conversa; siga-o nesta e nas próximas chamadas dela; "
            f"as regras que valem sempre continuam valendo):\n\n{texto}")


# ---------------------------------------------------------------- text mode (tools written into the system prompt)

def modo_texto(agent) -> bool:
    """This agent's chat model gets the tools as text in the system prompt (any API mode but Responses), the same test
    Agent Zero makes before each call (agent.call_chat_model_turn). Unknown = False: nothing changes."""
    try:
        from helpers.litellm_transport import TransportMode

        kwargs = getattr(agent.get_chat_model(), "kwargs", None)
        if not isinstance(kwargs, dict):
            return False
        return TransportMode.from_value(kwargs.get("a0_api_mode")) is not TransportMode.RESPONSES
    except Exception:
        return False


def nomes_da_parte(parte: str, reserva: str) -> list[str]:
    """The tool names of one prompt file, the way Agent Zero reads them (declarations, else the first `tool_name` of an
    example, else the first heading, else the file name)."""
    try:
        from helpers.responses_tools import _tool_names_from_prompt

        return list(_tool_names_from_prompt(parte, fallback=reserva))
    except Exception:
        pass
    declarados = list(dict.fromkeys(_DECLARACAO.findall(parte or "")))
    if declarados:
        return [d[0] if isinstance(d, tuple) else d for d in declarados]
    for m in _EXEMPLO.finditer(parte or ""):
        return [m.group(1)]
    for m in _TITULO.finditer(parte or ""):
        nome = (m.group(1).split(None, 1) or [""])[0].strip("`'\" :")
        if _NOME.fullmatch(nome):
            return [nome]
    return [reserva] if reserva else []


def linha_texto(nome: str, curta: str) -> str:
    return f"### {nome}\n{curta}"


def encurtar_texto(secao: str, partes: list[tuple[str, str]], curtas: dict, min_ganho: int,
                   manuais: dict | None = None) -> str:
    """`secao` (the "## available tools" text) with one short line per tool instead of each prompt file.

    `partes`: [(file name, prompt)] as Agent Zero read them (the vision block too, as ("vision_load", prompt)). A prompt
    is replaced only where it appears exactly once in `secao` (one that changed since, or that another plugin
    rewrote, stays whole), only when every tool it declares has a short line and the gain is at least `min_ganho`.
    Its whole text is kept as the manual of each of its tools."""
    manuais = MANUAIS_TEXTO if manuais is None else manuais
    saida, guardar = secao, {}
    for arquivo, parte in partes:
        if not parte or len(parte) < min_ganho or saida.count(parte) != 1:
            continue
        nome_arquivo = os.path.basename(arquivo or "")
        reserva = nome_arquivo[len("agent.system.tool."):-len(".md")] if nome_arquivo.startswith("agent.system.tool.") \
            else nome_arquivo
        nomes = nomes_da_parte(parte, reserva)
        linhas = [linha_texto(n, curtas[n]) for n in nomes if curtas.get(n)]
        curto = "\n".join(linhas)
        if not nomes or len(linhas) != len(nomes) or len(parte) - len(curto) < min_ganho:
            continue
        saida = saida.replace(parte, curto, 1)
        for n in nomes:
            guardar[n] = parte
    manuais.update(guardar)
    return saida


def partes_das_ferramentas(agent) -> list[tuple[str, str]]:
    """The prompt files of the tools section, as Agent Zero's system_prompt/_11_tools_prompt.build_prompt reads and
    filters them, and the vision block it appends (as "vision_load"). Any failure raises (the caller leaves the prompt
    as it was)."""
    from helpers import files, subagents, tool_policy

    kwargs_por_arquivo = agent.get_data("_tool_prompt_kwargs") or {}
    partes = []
    for caminho in files.get_unique_filenames_in_dirs(subagents.get_paths(agent, "prompts"), "agent.system.tool.*.md"):
        arquivo = os.path.basename(caminho)
        try:
            partes.append((arquivo, agent.read_prompt(arquivo, **kwargs_por_arquivo.get(arquivo, {}))))
        except Exception:
            continue  # Agent Zero skips it too
    filtradas = tool_policy.filter_tool_prompts(agent, partes)
    if len(filtradas) != len(partes):  # cannot pair them with their files: leave the section alone
        raise ValueError("política de ferramentas mudou a lista")
    partes = [(a, f) for (a, _), f in zip(partes, filtradas) if f]
    try:
        from plugins._model_config.helpers.model_config import get_chat_model_config, get_vision_model_config

        if get_vision_model_config(agent) or get_chat_model_config(agent).get("vision", False):
            partes.append(("vision_load", agent.read_prompt("agent.system.tools_vision.md")))
    except Exception:
        pass
    return partes
