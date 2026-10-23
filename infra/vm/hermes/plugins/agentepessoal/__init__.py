"""Plugin `agentepessoal` do Hermes (migração de 23/10, docs/MIGRACAO_HERMES.md): registra as ferramentas dos nossos
plugins do Agent Zero, rodando os mesmos arquivos de /a0/usr/plugins pela ponte_a0. Uma ferramenta que não carrega
(arquivo ausente, erro de import) é pulada e registrada no log, sem derrubar as outras."""
import importlib.util
import logging
import sys
from pathlib import Path

_aqui = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("agentepessoal_ponte_a0", _aqui / "ponte_a0.py")
ponte = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = ponte  # dataclasses look their module up in sys.modules
_spec.loader.exec_module(ponte)
_spec_c = importlib.util.spec_from_file_location("agentepessoal_cofre", _aqui / "cofre_hermes.py")
cofre = importlib.util.module_from_spec(_spec_c)
sys.modules[_spec_c.name] = cofre
_spec_c.loader.exec_module(cofre)
log = logging.getLogger("agentepessoal")

# (plugin, ferramenta). "Hermes primeiro" (23/10): só entra o que é nosso de verdade (dados, Raiz, Segundo Cérebro).
# Fora, de propósito:
#  - o que o Hermes já faz bem: pesquisa/pesquisar (= web_search); conectores/conector e prompt_enxuto/ferramentas_extras
#    (MCP e lista de ferramentas próprios);
#  - o que grava no agendador ou nas conversas do Agent Zero (chamado daqui, criaria tarefa que o A0 executa):
#    agenda_confiavel/tarefa_limite, rotinas/me_mostre e salvar_rotina, whatsapp/criar_gatilho, objetivo_vivo/passos,
#    painel/painel_vivo, canais/canal. Voltam na fase 5 por cima do cron do Hermes (ou ficam no cron dele);
#  - o que espera resposta pela ponte do celular: whatsapp/perguntar e pedir_codigo (fase 6);
#  - celular_rapido/celular: põe a imagem da tela no histórico do A0 (precisa de adaptação).
FERRAMENTAS = (
    ("agent_delegates", "delegar"), ("agent_delegates", "text_delegate"),
    ("analisar_imagens", "analisar_imagens"), ("auxiliar", "contas"), ("auxiliar", "rascunho"), ("auxiliar", "reuniao"),
    ("central", "livro"), ("cerebro", "cerebro"), ("cofre", "cofre_descrever"),
    ("concorrentes", "concorrentes"), ("consultar_sol", "consultar_sol"), ("conteudo", "conteudo"),
    ("conversas_externas", "conversa_externa"), ("especialistas", "especialista"), ("fios_soltos", "fios"),
    ("iniciativa", "iniciativa"), ("ler_arquivo", "ler"), ("login_usuarios", "terminal_isolado"),
    ("memoria_pessoal", "decisao"), ("memoria_pessoal", "ficha"), ("memoria_pessoal", "lembrar"),
    ("prospeccao", "prospeccao"), ("radar", "monitor"), ("video", "assistir_video"),
    ("video", "videos_em_alta"), ("whatsapp", "whatsapp_enviar"), ("whatsapp", "whatsapp_guardar_token"),
)


def _manipulador(classe, nome):
    async def manipular(args, session_id=None, task_id=None, **kwargs):
        return await ponte.executar(classe, nome, args, session_id or task_id)
    return manipular


def register(ctx):
    cofre.registrar(ctx)  # antes das ferramentas: sem ele, nenhuma recebe senha (o §§secret segue como texto)
    feitas, puladas = [], []
    for plugin, nome in FERRAMENTAS:
        try:
            classe = ponte.carregar(plugin, nome)
            ctx.register_tool(name=nome, toolset="agentepessoal", schema=ponte.esquema(plugin, nome, classe),
                              handler=_manipulador(classe, nome), is_async=True)
            feitas.append(nome)
        except Exception as exc:  # one broken tool never takes the others down
            puladas.append(f"{plugin}/{nome}: {type(exc).__name__}: {exc}"[:300])
    log.warning("agentepessoal: %d ferramentas registradas; puladas: %s", len(feitas), puladas or "nenhuma")
