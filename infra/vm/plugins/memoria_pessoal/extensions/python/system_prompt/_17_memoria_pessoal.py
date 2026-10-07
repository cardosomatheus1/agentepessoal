"""Inject the user's shared profile and this chat's own context into every turn.

- /a0/usr/memoria/sobre-voce.md      shared by every chat and agent
- /a0/usr/chats/<id>/contexto.md    private to one chat (deleted with it)
- /a0/usr/chats/<id>/anexos/        files attached in that chat
Agents are Agent Zero projects, whose vector memory is already isolated.
"""

from pathlib import Path

from agent import LoopData
from helpers import projects
from helpers.extension import Extension

USR = Path("/a0/usr")
PROFILE = USR / "memoria" / "sobre-voce.md"
MAX_CHARS = 12000  # keep each injected file to a few thousand tokens


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

        profile = _read(PROFILE) or "(vazio)"
        chat_context = _read(context_file) or "(vazio — crie o arquivo quando houver algo a guardar)"
        agent_line = (
            f'Você está atuando como o agente "{project}" (projeto em /a0/usr/projects/{project}/). '
            "A memória de longo prazo deste agente é separada da dos outros agentes."
            if project
            else "Esta conversa não está ligada a nenhum agente específico (conversa avulsa)."
        )

        system_prompt.append(
            f"""## Memória pessoal do usuário

Uso individual: há um único usuário. {agent_line}

### Sobre o usuário (compartilhado entre todas as conversas e agentes) — {PROFILE}
{profile}

### Contexto desta conversa (só desta conversa) — {context_file}
{chat_context}

### Como manter essa memória
- Quando o usuário contar algo duradouro sobre ele (nome, cidade, profissão, família, preferências, jeito de responder), atualize {PROFILE} na hora.
- Quando surgir algo importante só para esta conversa (objetivo, decisões, dados combinados, pendências, resumo do que foi feito), atualize {context_file}. Mantenha o arquivo curto e organizado em seções; reescreva em vez de só acrescentar.
- Anexos enviados nesta conversa: copie o arquivo para {attachments}/ (crie a pasta se preciso), registre nome e do que se trata em {context_file} e extraia as informações úteis (ex.: currículo → dados no perfil e no contexto).
- Assunto de um agente (projeto ativo): guarde também nos arquivos do projeto e na memória do agente.
- Não precisa avisar a cada atualização; mencione só quando for relevante. Nunca grave senhas, códigos ou tokens nesses arquivos.
- Se o usuário pedir para criar um novo agente (ex.: "crie um agente de finanças"), crie um projeto em /a0/usr/projects/<nome-curto>/ com o arquivo .a0proj/project.json contendo title, description, instructions (como o agente deve agir, em português), color, git_url vazio e file_structure {{"enabled": true, "max_depth": 3, "max_files": 40, "max_folders": 20, "max_lines": 250, "gitignore": ""}}; depois explique que ele aparece no seletor de projeto, no canto superior direito.

### Onde fazer as coisas (o usuário assiste ao vivo)
- **Sites e serviços web** (WhatsApp Web, e-mail, vagas, formulários, pesquisas): use a ferramenta **browser** do computador. Diga ao usuário em uma linha: "acompanhe no botão **Browser** (globo) da barra à direita".
- **Programas com janela** (LibreOffice, gerenciador de arquivos, apps Linux): use o **Desktop**. Diga: "acompanhe no botão **Desktop**".
- **Celular Android**: só quando o usuário pedir o celular, quando o app só existe no celular ou for jogo/app Android. Diga: "acompanhe no botão **Celular**".
- Na dúvida, prefira o computador (Browser/Desktop) ao celular.

### Velocidade
- Leia **texto** antes de imagem: conteúdo/estado da página no browser, `elementos()`/árvore da interface no celular. Use print + `vision_load` só quando a informação for visual (jogo, imagem, layout) — analisar imagem leva 10–30 s.
- Para muitos passos repetidos, use a skill **piloto-rapido** (script + Jev) em vez de decidir passo a passo pelo chat.
- Quando o objetivo for atingido, **pare e responda**. Confira o resultado no máximo 2 vezes; nunca fique repetindo verificações (ex.: "confirmar que continua conectado").
"""
        )
