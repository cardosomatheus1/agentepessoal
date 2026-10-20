"""Which connector tools (MCP: google, github) go in the native tool list of each model call (20/10).

Measured on 20/10 in one of Matheus's chats: 139 native tools, 176k characters in every call; 59 were Google's
(122k; `batch_update_doc` alone 25.6k) and 28 GitHub's (33k). In the 14 days before, his chats used 30 of those 87.

- Always in the list: the ones he uses and the basics (Gmail search/read, Calendar read, Drive/Docs/Sheets read and
  basic create), with a shorter schema (first sentence of each description, no repeated e-mail field).
- GitHub (the core set) only in chats that talk about code, or on demand.
- Every other connector tool stays callable: the `conector` tool lists them and activates them for the chat (they
  join the list from the next call); a connector tool that runs anyway (by its name) is kept active as well.
- A connector tied to another person (donos.json) does not go in the list at all (it was already refused on use).

Text mode (the Sonnet preset, `a0_api_mode: chat`): no native list goes; Agent Zero writes every MCP tool into the
system prompt ("#### MCP tool `google.x`", 165 thousand characters measured on 20/10). `enxugar_mcp_texto` applies the
same choice there: the same tools stay, with the same shorter description and schema; the others leave the prompt.

Nothing here makes a tool uncallable: the MCP server and Agent Zero still have all of them; only what the model
sees per call changes. Switch: the file DESLIGADO exists = the full list as before, no deploy needed."""

import copy
import json
import re
from pathlib import Path

DESLIGADO = Path("/a0/usr/plugins/conectores/sob_demanda_desligado")
CHAVE_ATIVAS = "conectores_ativas"  # context data (saved with the chat): ["google.create_doc", ...]
ENXUTOS = ("google", "github")  # connectors filtered here; any other MCP server goes as it comes

SEMPRE: dict[str, tuple[str, ...]] = {
    "google": (
        "start_google_auth",  # the login link when the authorization expires
        # Gmail: search and read (read-only server)
        "search_gmail_messages", "get_gmail_message_content", "get_gmail_messages_content_batch",
        "get_gmail_thread_content",
        # Calendar: read
        "get_events",
        # Drive: find, read, create file/folder, link
        "search_drive_files", "list_drive_items", "get_drive_file_content", "create_drive_file", "create_drive_folder",
        "get_drive_shareable_link",
        # Docs: read, create from text/Markdown
        "get_doc_as_markdown", "import_to_google_doc",
        # Sheets: read, create, write values
        "get_spreadsheet_info", "read_sheet_values", "create_spreadsheet", "modify_sheet_values",
    ),
    "github": (),
}
# GitHub in a chat about code: the tools used in the 14 days measured (read-only server)
GITHUB_CODIGO = ("get_me", "search_repositories", "get_file_contents", "search_code", "list_commits", "get_commit",
                 "list_branches", "pull_request_read")

CODIGO = re.compile(
    r"\b(github|git|reposit[óo]rios?|repos?|commits?|pull requests?|branch(es)?|merge|"
    r"aibusiness|ia business|revenue-os|agentepessoal|agent zero|claude code|python|typescript|javascript|"
    r"programa(r|ção|cao)|c[óo]digo[- ]fonte|c[óo]digo d[oae] (projeto|app|aplicativo|site|sistema|agente|reposit\w*|plugin))\b",
    re.IGNORECASE)
SIGLA_PR = re.compile(r"\bPRs?\b")  # uppercase only: "pr" is also the state (Paraná)

MAX_DESCRICAO, MAX_PARAMETRO = 300, 120


def ligado() -> bool:
    try:
        return not DESLIGADO.exists()
    except OSError:
        return True


def fala_de_codigo(texto: str) -> bool:
    return bool(CODIGO.search(texto or "") or SIGLA_PR.search(texto or ""))


def _frase(texto: str, teto: int) -> str:
    """The first sentence, at most `teto` characters."""
    texto = " ".join(str(texto or "").split())
    m = re.match(r"(.+?[.!?])(\s|$)", texto)
    texto = m.group(1) if m else texto
    return texto if len(texto) <= teto else texto[:teto - 1].rstrip() + "…"


def compactar_esquema(esquema, raiz: bool = True):
    """Same parameters, types, enums, defaults and required fields; only shorter: first sentence of each
    description, no "title", no `"default": null`, and no `user_google_email` unless required (single-user server:
    it defaults to the owner's address)."""
    if isinstance(esquema, list):
        return [compactar_esquema(x, False) for x in esquema]
    if not isinstance(esquema, dict):
        return esquema
    saida = {}
    obrigatorios = set(esquema.get("required") or [])
    for chave, valor in esquema.items():
        if chave == "title" and isinstance(valor, str):
            continue
        if chave == "default" and valor is None:
            continue
        if chave == "description" and isinstance(valor, str):
            saida[chave] = _frase(valor, MAX_PARAMETRO)
        elif chave == "properties" and isinstance(valor, dict):
            saida[chave] = {k: compactar_esquema(v, False) for k, v in valor.items()
                            if not (k == "user_google_email" and k not in obrigatorios)}
        else:
            saida[chave] = compactar_esquema(valor, False)
    return saida


def compactar(ferramenta: dict) -> dict:
    nova = copy.copy(ferramenta)
    nova["description"] = _frase(ferramenta.get("description") or ferramenta.get("name") or "", MAX_DESCRICAO)
    if isinstance(ferramenta.get("parameters"), dict):
        nova["parameters"] = compactar_esquema(ferramenta["parameters"])
    return nova


def servidor_e_nome(original: str) -> tuple[str, str]:
    servidor, ponto, nome = str(original or "").partition(".")
    return (servidor, nome) if ponto and servidor and nome else ("", "")


def na_lista(original: str, ativas, codigo: bool) -> bool:
    servidor, nome = servidor_e_nome(original)
    if original in ativas or nome in SEMPRE.get(servidor, ()):
        return True
    return servidor == "github" and codigo and nome in GITHUB_CODIGO


def filtrar(ferramentas: list, mapa: dict, ativas, codigo: bool, de_outros=()) -> list:
    """A new tool list: local tools as they come; connector tools of `ENXUTOS` only if always/active/code (shorter);
    tools of connectors in `de_outros` (another person's) out. `mapa`: native name -> original ("google.x")."""
    saida = []
    for f in ferramentas or []:
        if not isinstance(f, dict):
            saida.append(f)
            continue
        original = (mapa or {}).get(str(f.get("name") or ""), "")
        servidor, _ = servidor_e_nome(original)
        if servidor and servidor in de_outros:
            continue
        if servidor not in ENXUTOS:
            saida.append(f)
        elif na_lista(original, ativas, codigo):
            saida.append(compactar(f))
    return saida


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


def lembrar_codigo(agent) -> None:
    """The person's last message talks about code: GitHub's core set joins this chat's tools (and stays: stable list)."""
    if fala_de_codigo(texto_da_mensagem(getattr(agent, "last_user_message", None))):
        ativar(agent.context, [f"github.{n}" for n in GITHUB_CODIGO])


def _esquema_texto(esquema) -> str:
    return json.dumps(esquema) if esquema else ""  # as helpers/mcp_handler.get_tools_prompt writes it


def enxugar_mcp_texto(secao: str, cat: dict, render, ativas_agora, de_outros=(), render_servidor=None,
                      servidores: dict | None = None) -> str:
    """`secao` (Agent Zero's MCP text section) with only the connector tools this chat gets, shorter.

    `cat`: {"google.x": {"description", "input_schema"}}; `render(qualified_name, description, input_schema)`: the
    "#### MCP tool" block exactly as Agent Zero renders it. Only blocks found exactly in `secao` are touched (a tool
    the policy or the server left out is never added): kept ones get the first sentence and the compact schema,
    the others go (with the separator before them). Connectors of `de_outros` (another person's) go entirely,
    their server heading too (`render_servidor(name, description)`, `servidores`: {name: description}); when no MCP
    tool remains at all, "" (the section goes)."""
    saida, tirou = secao, False
    for original, ferramenta in cat.items():
        servidor, _ = servidor_e_nome(original)
        if servidor not in ENXUTOS and servidor not in de_outros:
            continue
        bloco = render(original, ferramenta.get("description"), _esquema_texto(ferramenta.get("input_schema")))
        if not bloco or saida.count(bloco) != 1:
            continue
        if servidor in de_outros or not na_lista(original, ativas_agora, False):
            saida = saida.replace("\n\n" + bloco, "", 1) if ("\n\n" + bloco) in saida else saida.replace(bloco, "", 1)
            tirou = True
            continue
        curta = compactar({"name": original, "description": ferramenta.get("description") or "",
                           "parameters": ferramenta.get("input_schema")})
        esquema = curta.get("parameters")
        saida = saida.replace(bloco, render(original, curta["description"],
                                            json.dumps(esquema, ensure_ascii=False, separators=(",", ":")) if esquema else ""), 1)
    if render_servidor and servidores:
        for servidor in de_outros:
            if servidor in servidores and f"#### MCP tool `{servidor}." not in saida:
                cabeca = render_servidor(servidor, servidores[servidor])
                if cabeca and saida.count(cabeca) == 1:
                    saida = saida.replace(cabeca + "\n", "", 1) if (cabeca + "\n") in saida else saida.replace(cabeca, "", 1)
    if tirou and "#### MCP tool `" not in saida:
        return ""
    return saida


def ativas(contexto) -> list[str]:
    try:
        valor = contexto.get_data(CHAVE_ATIVAS)
    except Exception:
        return []
    return [str(x) for x in valor] if isinstance(valor, list) else []


def ativar(contexto, originais) -> list[str]:
    """Add tools ("google.create_doc") to this chat's active ones; returns the ones that were new."""
    atuais = ativas(contexto)
    novas = [o for o in dict.fromkeys(originais) if servidor_e_nome(o)[0] in ENXUTOS and o not in atuais]
    if novas:
        contexto.set_data(CHAVE_ATIVAS, sorted(atuais + novas))
    return novas


def texto_da_mensagem(mensagem) -> str:
    """The text of a history message (the person's last message), whatever its shape."""
    if mensagem is None:
        return ""
    conteudo = getattr(mensagem, "content", mensagem)
    if isinstance(conteudo, str):
        return conteudo
    try:
        return json.dumps(conteudo, ensure_ascii=False, default=str)
    except Exception:
        return str(conteudo)


# ---------------------------------------------------------------- the `conector` tool

def catalogo(entradas) -> dict[str, dict]:
    """MCPConfig.get_tools() ([{"google.x": {...}}, ...]) as {"google.x": {...}}."""
    saida = {}
    for e in entradas or []:
        if isinstance(e, dict):
            for nome, ferramenta in e.items():
                if isinstance(ferramenta, dict):
                    saida[str(nome)] = ferramenta
    return saida


def nome_completo(conector: str, nome: str) -> str:
    nome = str(nome or "").strip().strip("`")
    if servidor_e_nome(nome)[0]:
        return nome
    if nome.startswith(f"{conector}_"):
        nome = nome[len(conector) + 1:]
    return f"{conector}.{nome}" if conector and nome else nome


def listar(cat: dict, conector: str, ativas_agora, codigo: bool, busca: str = "") -> str:
    nomes = sorted(n for n in cat if servidor_e_nome(n)[0] == conector)
    if busca:
        b = busca.lower()
        nomes = [n for n in nomes if b in n.lower() or b in str(cat[n].get("description") or "").lower()]
    if not nomes:
        return f"Nenhuma ferramenta do conector `{conector}`" + (f" com «{busca}»." if busca else ".")
    linhas = [f"Ferramentas do conector `{conector}` ({len(nomes)}); ✓ = já na sua lista nesta conversa. Para usar uma "
              "sem ✓: `conector` acao \"ativar\" com `ferramentas` (ela entra na lista na próxima chamada); detalhe de "
              "uma: acao \"descrever\"."]
    for n in nomes:
        marca = "✓" if na_lista(n, ativas_agora, codigo) else "·"
        linhas.append(f"{marca} {servidor_e_nome(n)[1]} — {_frase(cat[n].get('description') or '', 110)}")
    return "\n".join(linhas)


def descrever(cat: dict, original: str) -> str:
    f = cat.get(original)
    if not f:
        return ""
    esquema = json.dumps(f.get("input_schema") or {}, ensure_ascii=False)
    return f"`{original}`\n{f.get('description') or ''}\n\nParâmetros (esquema completo):\n{esquema}"
