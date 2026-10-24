"""O que o A0 punha em todo turno sobre quem está falando (memoria_pessoal/_17_memoria_pessoal.py), no Hermes
(migração, fase 5), no 1º turno de cada sessão e depois de cada resumo dela (gancho `pre_llm_call`): a ficha "Sobre você" e as decisões em vigor
da pessoa, pelos mesmos helpers (só leitura). "Hermes primeiro": a memória curta e o perfil do Hermes seguem dele; isto
é o que é nosso (o Segundo Cérebro é a fonte das decisões) e evita perguntar de novo o que ele já decidiu.
Convidados: só a ficha e as decisões deles mesmos, nunca as do Matheus."""
import importlib.util
import logging
import sys
from pathlib import Path

PLUGINS = Path("/a0/usr/plugins")
log = logging.getLogger("agentepessoal.contexto")


def _helper(arquivo: str):
    nome = f"memoria_pessoal_{arquivo}"
    caminho = PLUGINS / "memoria_pessoal" / "helpers" / f"{arquivo}.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = mtime
        sys.modules[nome] = m
    return sys.modules[nome]


def bloco(login: str) -> str:
    partes = []
    try:
        texto, _ = _helper("ficha").texto_para_prompt(login)
        if texto.strip():
            partes.append(f"## Sobre quem fala com você ({login})\n{texto.strip()}")
    except Exception as exc:  # o turno segue sem o bloco
        log.warning("contexto: ficha de %s indisponível: %s: %s", login, type(exc).__name__, exc)
    try:
        lista = _helper("decisoes").texto_para_prompt(login)
        if lista.strip():
            partes.append("## Decisões em vigor (siga sem perguntar de novo; mudou? a pessoa diz)\n" + lista.strip())
    except Exception as exc:
        log.warning("contexto: decisões de %s indisponíveis: %s: %s", login, type(exc).__name__, exc)
    return "\n\n".join(partes)


MARCAS = ("## Sobre quem fala com você", "## Decisões em vigor")


def ja_tem(conversation_history) -> bool:
    """A conversa ainda leva o bloco? Uma sessão longa (tg-matheus) é resumida de tempos em tempos e o bloco do 1º turno
    some com o resumo (24/10: as decisões tinham saído da conversa desde 23/10); aí ele volta no turno seguinte."""
    for m in conversation_history or []:
        if isinstance(m, dict):
            for chave in ("api_content", "content"):
                v = m.get(chave)
                if isinstance(v, str) and any(x in v for x in MARCAS):
                    return True
    return False


def contexto(session_id="", task_id="", is_first_turn=False, conversation_history=None, **kw):
    """Gancho `pre_llm_call`: no 1º turno e de novo quando o resumo da conversa o levou embora."""
    if not is_first_turn and (conversation_history is None or ja_tem(conversation_history)):
        return None
    login = sys.modules["agentepessoal_ponte_a0"].login_da_sessao(str(session_id or task_id or ""))
    texto = bloco(login)
    return {"context": texto} if texto else None


def registrar(ctx) -> None:
    ctx.register_hook("pre_llm_call", contexto)
