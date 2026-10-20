"""Inject the speaker's profile and this chat's own context into every turn.

- /a0/usr/memoria/usuarios/<login>.md  one profile per person (shared by all their chats/agents);
                                      the speaker comes from the login (login_usuarios plugin)
- /a0/usr/chats/<id>/contexto.md    private to one chat (deleted with it)
- /a0/usr/chats/<id>/anexos/        files attached in that chat
- /a0/usr/memoria/decisoes/<login>.json  the person's decisions in force (helpers/decisoes.py), so the agent follows
                                      them instead of asking again
Agents are Agent Zero projects, whose vector memory is already isolated.

20/10 (prompt enxuto): this chat's contexto.md and attachment list left the system prompt (they change during the chat
and broke the provider cache of every later call); they go at the end, as the `contexto_conversa` extra (no_turno).
"Velocidade" (stop when done, check at most twice) lives in prompt_enxuto's "Regras que valem sempre".
"""

import importlib.util
import sys
from pathlib import Path

from agent import LoopData
from helpers import projects
from helpers.extension import Extension

USR = Path("/a0/usr")
PROFILES = USR / "memoria" / "usuarios"
DONO = "matheus"  # whose profile applies when nobody is logged in (API, scheduled tasks)
USUARIOS = USR / "usuarios.json"
MAX_CHARS = 12000  # keep each injected file to a few thousand tokens


def _helper(arquivo: str):
    """A helper of this plugin, reloaded when the file changes."""
    nome = f"memoria_pessoal_{arquivo}"
    caminho = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists()) / "helpers" / f"{arquivo}.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


def decisoes():
    return _helper("decisoes")


def ficha(quem: str, modulo=None) -> tuple[str, bool]:
    """(the speaker's profile for the prompt, kept by the `ficha` tool?). Old free-text file: as it is."""
    try:
        return (modulo or _helper("ficha")).texto_para_prompt(quem)
    except Exception as exc:  # the turn must go on without the block
        return f"(ficha indisponível: {type(exc).__name__})", True


def bloco_decisoes(quem: str, nome: str, modulo=None) -> str:
    try:
        lista = (modulo or decisoes()).texto_para_prompt(quem)
    except Exception as exc:  # the turn must go on without the block
        lista = f"(registro de decisões indisponível: {type(exc).__name__})"
    return f"""### Decisões de {nome} em vigor — valem até {nome} mudar; não pergunte de novo
{lista or "(nenhuma registrada ainda)"}
- Antes de perguntar algo a {nome} ou de pedir o ok de {nome}, confira esta lista: se o assunto já está decidido, siga a decisão e só conte o que fez. Pergunte só o que ela não cobre.
- Quando {nome} decidir algo que vale para as próximas vezes (permitir ou proibir algo, um jeito de trabalhar, uma preferência), registre na hora com a ferramenta `decisao` (acao "registrar", com as palavras de {nome} em `citacao`) e termine a resposta com "Anotado: …". Se {nome} mudar de ideia, registre de novo com o mesmo `tema` (a antiga é substituída) ou use acao "revogar".
- Depois da conversa, um revisor relê as mensagens de {nome} e manda avisos curtos ao celular ("Anotado: …", "Anotado na rotina …", "Anotado sobre você: …", "Quer que eu salve '…' como rotina?", "Você disse «…». Hoje vale a decisão #N … Troco por «…»?"). Quando {nome} responder a um deles: «desfaz a N» → `decisao` acao "revogar" id N; «troca a N» → `decisao` acao "registrar" no tema da decisão N com o texto e as palavras que o aviso trouxe; «tira da ficha: …» → `ficha` acao "remove"; «tira da rotina X» → `salvar_rotina` acao "corrigir" na rotina X dizendo que a correção do aviso deixou de valer; "sim" para salvar rotina → `salvar_rotina` acao "salvar" com os passos que funcionaram."""


def no_turno(loop_data, chave: str, fazer) -> None:
    """A block that changes during a chat (this chat's contexto.md, its attachments) goes at the end of the prompt, not in
    the system prompt, whose start must stay the same between calls (provider cache): it is computed once per message
    of the person and cache_prompt writes it into the history only when it changed. Without a real LoopData (old
    callers), nothing is added."""
    memo = getattr(loop_data, "params_persistent", None)
    extras = getattr(loop_data, "extras_persistent", None)
    if not isinstance(memo, dict) or not isinstance(extras, dict):
        return
    turno = memo.setdefault("_no_turno", {})
    if chave not in turno:
        turno[chave] = fazer()
    if turno[chave]:
        extras[chave] = turno[chave]


def _read(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n…(truncado; leia o arquivo completo se precisar)"
    return text


class MemoriaPessoal(Extension):
    async def execute(self, system_prompt: list[str] = [], loop_data: LoopData = LoopData(), **kwargs):
        if not self.agent or self.agent.number != 0:  # subordinates get context from their task
            return

        ctx_id = self.agent.context.id
        chat_dir = USR / "chats" / ctx_id
        context_file = chat_dir / "contexto.md"
        attachments = chat_dir / "anexos"
        project = projects.get_context_project_name(self.agent.context) or ""

        quem = (self.agent.context.get_data("usuario") or DONO).strip().lower()
        nome = self.agent.context.get_data("usuario_nome") or quem.title()
        PROFILE = PROFILES / f"{quem}.md"
        try:
            import json

            todos = [u.get("nome") or k.title() for k, u in json.loads(USUARIOS.read_text()).get("usuarios", {}).items()]
        except Exception:
            todos = [nome]
        profile, ficha_nova = ficha(quem)
        profile = profile or "(vazio)"
        chat_context = _read(context_file) or "(vazio — crie o arquivo quando houver algo a guardar)"
        try:
            files = sorted(p for p in attachments.iterdir() if p.is_file())
        except OSError:
            files = []
        anexos = "\n".join(f"- {p.name} ({p.stat().st_size / 1024**2:.1f} MB)" for p in files[:40]) or "(nenhum)"
        agent_line = (
            f'Você está atuando como o agente "{project}" (projeto em /a0/usr/projects/{project}/). '
            "A memória de longo prazo deste agente é separada da dos outros agentes."
            if project
            else "Esta conversa não está ligada a nenhum agente específico (conversa avulsa)."
        )

        regra_ficha = (
            f"- Quando {nome} contar algo duradouro sobre si (nome, cidade, profissão, família, preferências, jeito de "
            "responder, contexto do negócio), grave na hora com a ferramenta `ficha` (acao \"add\"; corrigir: \"patch\"; "
            "deixou de valer: \"remove\") — só a ficha de quem está falando, só fatos (ordens e permissões vão na "
            "`decisao`). Nunca edite o arquivo da ficha direto. Ficha cheia: junte ou tire entradas e tente de novo."
            if ficha_nova else
            f"- Quando {nome} contar algo duradouro sobre si (nome, cidade, profissão, família, preferências, jeito de "
            f"responder), atualize {PROFILE} na hora — só a ficha de quem está falando.")
        system_prompt.append(
            f"""## Memória pessoal do usuário

Pessoas que usam este agente: {", ".join(todos)} (cada uma com a sua ficha). **Quem está falando nesta conversa: {nome}.** Trate essa pessoa pelo nome dela e não misture informações pessoais de uma com a outra. {agent_line}

### Sobre {nome} (ficha desta pessoa, compartilhada entre as conversas e agentes dela) — {PROFILE}
{profile}

{bloco_decisoes(quem, nome)}

### Como manter essa memória
{regra_ficha}
- Quando {nome} citar algo de uma conversa antiga que não está aqui ("aquilo que falamos sobre…"), procure com a ferramenta `lembrar` antes de dizer que não sabe ou de perguntar de novo.
- O contexto desta conversa ({context_file}) e a lista de anexos dela chegam nas mensagens, no bloco `contexto_conversa`, na versão atual (atualizado a cada mensagem dele, quando muda): não leia o arquivo de novo (nem com text_editor nem com cat). Quando surgir algo importante só para esta conversa (objetivo, combinados, dados, pendências, o que já está comprovado e o que falta), reescreva o arquivo inteiro de uma vez, curto e em seções; decisão que vale também fora daqui vai para a ferramenta `decisao`.
- Arquivos que o usuário manda: pelo **+ → Attach files** desta conversa os grandes (até 5 GB) ficam em {attachments}/ e os pequenos chegam como anexo; pela página de controle ("Enviar arquivos") em /a0/usr/workdir/entrada/; pelo botão Files, na pasta que ele escolher. Anexo recebido: copie para {attachments}/, registre nome e assunto em {context_file} e extraia o que for útil (ex.: currículo → ficha e contexto).
- Assunto de um agente (projeto ativo): guarde também nos arquivos do projeto e na memória do agente. Não avise a cada atualização. Nunca grave senhas, códigos ou tokens nesses arquivos.
- Pedido para criar um novo agente (ex.: "crie um agente de finanças"): crie o projeto /a0/usr/projects/<nome-curto>/ com .a0proj/project.json (title, description, instructions em português, color, git_url vazio, file_structure {{"enabled": true, "max_depth": 3, "max_files": 40, "max_folders": 20, "max_lines": 250, "gitignore": ""}}) e .a0proj/dono.txt contendo só `{quem}` (cada pessoa só vê os próprios agentes); depois diga que ele aparece no seletor de projeto, no canto superior direito.

### Onde fazer as coisas (o usuário assiste ao vivo)
- Sites e serviços web: ferramenta **browser** ("acompanhe no botão **Browser**"). Programas com janela: **Desktop** ("acompanhe no botão **Desktop**"). Celular Android: só quando ele pedir, o app só existir no celular ou for jogo, com a ferramenta **`celular`**, que já devolve o texto da tela (não tire print + `vision_load` à parte). Na dúvida, o computador.
- Leia **texto** antes de imagem. Muitos passos repetidos: skill **piloto-rapido** (script + Jev) em vez de decidir passo a passo.
"""
        )
        no_turno(loop_data, "contexto_conversa", lambda: f"""### Contexto desta conversa (só desta conversa) — {context_file}
{chat_context}

### Anexos desta conversa — {attachments}/
{anexos}""")
