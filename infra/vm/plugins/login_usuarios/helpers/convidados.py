"""Guests: friends of the owner with their own Telegram chat and only personal use (15/10: Ilia, Matheus's friend).

A guest's phone chats live in the guest's own project (convidado-<login>), so:
- memory is the project's own (Agent Zero isolates memory per project), never Matheus's;
- the project's tool policy (Agent Zero `_tool_access`, sparse config in .a0proj) blocks every tool but FERRAMENTAS,
  so the guest's agent does not even see prospecção, conteúdo, the shell, the editor or the scheduler;
- `bloqueio()` repeats the same rule at run time (tool_execute_before), refuses any tool in a guest chat that left
  the project, and refuses local paths outside the guest's own folders (no reading Matheus's files through
  document_query, whatsapp_enviar or the browser).
Spending: every model call carries the chat owner in X-A0-Dono (`com_dono`), the host proxy logs it in uso.jsonl and
the phone bridge stops passing a guest's messages once the guest's day passes `teto_dia_usd` (ponte_whatsapp.py).
"""

import copy
import json
import re
from pathlib import Path

CONVIDADOS = {
    "ilia": {"nome": "Ilia", "teto_dia_usd": 5.0, "idioma": None},  # idioma: Whisper language, None = detect (he speaks Russian)
    "will": {"nome": "Will", "teto_dia_usd": 5.0, "idioma": None},  # 15/10, friend of Matheus: same rules as Ilia
}

# What a guest's agent may use: conversation, research, the browser (own profile), files the guest sent, own
# memory/notes/vault. Nothing of the Raiz, of Matheus's accounts, no shell, no file editor, no scheduled tasks.
FERRAMENTAS = (
    "response", "call_subordinate", "wait", "notify_user",  # no "parallel": its chats have no project
    "search_engine", "pesquisar", "browser", "document_query", "vision_load", "analisar_imagens",
    "assistir_video", "videos_em_alta",
    "memory_save", "memory_load", "memory_delete", "memory_forget",  # project memory: the guest's own
    "lembrar", "ficha", "cofre_descrever",  # per person
    "conversa_externa",  # 15/10: talk to stores/clinics on the guest's OWN WhatsApp (plugin conversas_externas)
    "whatsapp_enviar",  # always to the chat's owner, and only the guest's own files (see caminho_proibido)
)

LEEM_ARQUIVO = {"document_query", "vision_load", "analisar_imagens", "whatsapp_enviar", "browser", "assistir_video"}

PROJETOS = Path("/a0/usr/projects")
CELULAR = Path("/a0/usr/whatsapp")  # the bridge saves each person's attachments in <login>/
CABECALHO = "X-A0-Dono"
_LOGIN = re.compile(r"^[a-z0-9_-]{1,32}$")
# a local path starts a word (not the "/home" inside https://site/home); relative ones are never a guest's file
_INICIO = r"(?:^|(?<=[\s\"'(=,\[]))"
_CAMINHO = re.compile(_INICIO + r"(?:file://)?(/(?:a0|opt|root|etc|home|var|proc|sys|tmp|usr|srv|mnt|run|dev)(?:/[^\s\"'<>|`]*)?)",
                      re.M)
# the agent's own UI/API, the host's model proxy and phone bridge, the cloud metadata: never from a guest's chat
_REDE_INTERNA = re.compile(r"(?i)(localhost|host\.docker\.internal|\b127\.\d|\b0\.0\.0\.0|\b169\.254\.|\b10\.\d+\.\d+\.\d|"
                           r"\b172\.(1[6-9]|2\d|3[01])\.|\b192\.168\.|\[::1?\]|\bagent-zero\b|\bmetadata\.google)")
_RELATIVO = re.compile(_INICIO + r"((?:~/|\.{1,2}/|a0/|usr/)[^\s\"'<>|`]*)", re.M)


def convidado(login: str | None) -> dict | None:
    return CONVIDADOS.get(str(login or "").strip().lower())


def projeto(login: str) -> str:
    return f"convidado-{str(login).strip().lower()}"


def raizes(login: str) -> tuple[Path, ...]:
    login = str(login).strip().lower()
    return (PROJETOS / projeto(login), CELULAR / login)


def instrucoes(login: str) -> str:
    nome = (convidado(login) or {}).get("nome") or login.title()
    return (f"Você está conversando com {nome}, amigo do Matheus (dono deste agente), pelo Telegram. Trate {nome} "
            f"como a pessoa que você atende nesta conversa: chame pelo nome, curto e direto, na língua em que {nome} escrever "
            f"(se pediu uma língua, sempre nela).\n"
            f"Pedido que depende de lugar (loja, rota, serviço perto): use os lugares que {nome} disse; se faltar onde ele está, "
            f"mora ou trabalha, pergunte antes de pesquisar. Dê opções no caminho ou perto desses pontos, com a distância, e o "
            f"link do Google Maps de cada uma. Nunca troque a cidade dele por outra maior só porque achou mais resultado lá.\n"
            f"Uso só pessoal: conversar, pesquisar, ler arquivos e fotos que {nome} mandar, navegar, guardar notas e "
            f"lembrar coisas dele. Você NÃO tem aqui as ferramentas do Matheus (Raiz Connect, prospecção, posts, "
            f"Instagram, e-mail, agenda, contas, terminal, tarefas agendadas) e não fala dos dados, clientes, "
            f"conversas ou negócios do Matheus. Se {nome} pedir algo disso, diga com educação que este acesso é só "
            f"para uso pessoal dele.\nCada conversa dele tem um limite de uso por dia; se acabar, o próprio celular avisa.")


def politica(ids: list[str]) -> dict:
    """Agent Zero _tool_access sparse policy: everything blocked except these tool ids."""
    return {"mode": "custom", "default": "block", "mcp_default": "block", "allowed": sorted(set(ids)), "blocked": []}


def ids_ferramentas(nomes=FERRAMENTAS, pastas_plugins=(Path("/a0/usr/plugins"), Path("/a0/plugins")),
                    pasta_nucleo=Path("/a0/tools")) -> list[str]:
    """Canonical ids as Agent Zero's tool_policy writes them: plugin:<plugin>:<name> for a plugin tool (user plugins
    win over bundled ones, same as Agent Zero's search order), local:<name> otherwise."""
    ids = []
    for nome in nomes:
        achou = ""
        for raiz in pastas_plugins:
            for arq in sorted(Path(raiz).glob(f"*/tools/{nome}.py")):
                achou = f"plugin:{arq.parents[1].name}:{nome}"
                break
            if achou:
                break
        if not achou and (Path(pasta_nucleo) / f"{nome}.py").exists():
            achou = f"local:{nome}"
        ids.append(achou or f"local:{nome}")
    return ids


def preparar(login: str, projects, ids: list[str] | None = None) -> str:
    """Create or refresh the guest's project (idempotent): owner, instructions and tool policy. Returns its name."""
    login = str(login).strip().lower()
    if not convidado(login) or not _LOGIN.match(login):
        raise ValueError(f"{login!r} não é convidado")
    nome = projeto(login)
    pasta = Path(projects.get_project_folder(nome))
    if not (pasta / ".a0proj" / "project.json").exists():
        projects.create_project(nome, {
            "title": f"{(convidado(login) or {}).get('nome') or login.title()} (convidado)", "description": "Uso pessoal pelo Telegram",
            "instructions": instrucoes(login), "color": "", "git_url": "",
            "file_structure": {"enabled": False, "max_depth": 1, "max_files": 0, "max_folders": 0, "max_lines": 0,
                               "gitignore": ""}})
    else:
        dados = projects.load_basic_project_data(nome)
        if dados.get("instructions") != instrucoes(login):
            dados["instructions"] = instrucoes(login)
            projects.save_project_header(nome, dados)
    meta = pasta / ".a0proj"
    (meta / "dono.txt").write_text(login, encoding="utf-8")
    conf = meta / "plugins" / "_tool_access" / "config.json"
    conf.parent.mkdir(parents=True, exist_ok=True)
    novo = json.dumps(politica(ids if ids is not None else ids_ferramentas()), ensure_ascii=False, indent=1)
    if not conf.exists() or conf.read_text(encoding="utf-8") != novo:
        tmp = conf.with_suffix(".tmp")
        tmp.write_text(novo, encoding="utf-8")
        tmp.replace(conf)
    return nome


def _textos(valor):
    if isinstance(valor, str):
        yield valor
    elif isinstance(valor, dict):
        for v in valor.values():
            yield from _textos(v)
    elif isinstance(valor, (list, tuple)):
        for v in valor:
            yield from _textos(v)


def caminho_proibido(login: str, args) -> str:
    """The first local path in the tool's arguments that is outside the guest's own folders ("" when none)."""
    permitidas = [str(r.resolve()) if r.exists() else str(r) for r in raizes(login)]
    for texto in _textos(args):
        relativo = _RELATIVO.search(texto)
        if relativo:
            return relativo.group(1)
        for m in _CAMINHO.finditer(texto):
            bruto = m.group(1).rstrip(".,;:)]}")
            try:
                real = str(Path(bruto).resolve())
            except Exception:
                return bruto
            if not any(real == r or real.startswith(r + "/") for r in permitidas):
                return bruto
    return ""


def bloqueio(login: str | None, ferramenta: str, args, projeto_ativo: str | None) -> str:
    """Why this tool call is refused in a guest's chat ("" = allowed; non-guests are never refused here)."""
    if not convidado(login):
        return ""
    login = str(login).strip().lower()
    if projeto_ativo != projeto(login):
        return (f"Esta conversa é de um convidado ({login}) e está fora do projeto dele; nenhuma ferramenta roda aqui. "
                "Responda só com texto.")
    if ferramenta not in FERRAMENTAS:
        return (f"A ferramenta '{ferramenta}' não está disponível para convidados (uso só pessoal). Não tente de novo "
                "nem por outro caminho; diga à pessoa, com educação, que isso não está liberado para ela.")
    if ferramenta in LEEM_ARQUIVO and any(_REDE_INTERNA.search(t) for t in _textos(args)):
        return ("Endereços internos da máquina (localhost, host.docker.internal, rede privada) não podem ser abertos "
                "aqui. Use só sites públicos.")
    proibido = caminho_proibido(login, args) if ferramenta in LEEM_ARQUIVO else ""
    if proibido:
        return (f"O caminho {proibido} está fora dos arquivos desta pessoa e não pode ser usado aqui. Use só arquivos "
                "que ela mandou nesta conversa ou que você criou para ela.")
    return ""


def com_dono(modelo, dono: str | None):
    """A copy of the model wrapper whose calls carry the chat owner in X-A0-Dono (for spending per person).
    The original object may be shared between chats, so it is never changed; on any surprise the original is kept."""
    dono = str(dono or "").strip().lower()
    if not modelo or not _LOGIN.match(dono):
        return modelo
    try:
        kwargs = dict(getattr(modelo, "kwargs", None) or {})
        cab = dict(kwargs.get("extra_headers") or {})
        cab[CABECALHO] = dono
        kwargs["extra_headers"] = cab
        novo = copy.copy(modelo)
        try:
            object.__setattr__(novo, "kwargs", kwargs)
        except Exception:
            novo.kwargs = kwargs
        return novo if getattr(novo, "kwargs", None) is kwargs else modelo
    except Exception:
        return modelo
