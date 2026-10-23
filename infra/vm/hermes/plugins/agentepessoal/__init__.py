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
log = logging.getLogger("agentepessoal")

# (plugin, ferramenta). Fora por enquanto, de propósito (fases seguintes do plano):
#  conectores/conector e prompt_enxuto/ferramentas_extras: o Hermes tem MCP e lista de ferramentas próprios;
#  whatsapp/perguntar e whatsapp/pedir_codigo: esperam a resposta pela ponte do celular (fase 6);
#  celular_rapido/celular: põe a imagem da tela no histórico do A0 (precisa de adaptação).
FERRAMENTAS = (
    ("agenda_confiavel", "tarefa_limite"), ("agent_delegates", "delegar"), ("agent_delegates", "text_delegate"),
    ("analisar_imagens", "analisar_imagens"), ("auxiliar", "contas"), ("auxiliar", "rascunho"), ("auxiliar", "reuniao"),
    ("canais", "canal"), ("central", "livro"), ("cerebro", "cerebro"), ("cofre", "cofre_descrever"),
    ("concorrentes", "concorrentes"), ("consultar_sol", "consultar_sol"), ("conteudo", "conteudo"),
    ("conversas_externas", "conversa_externa"), ("especialistas", "especialista"), ("fios_soltos", "fios"),
    ("iniciativa", "iniciativa"), ("ler_arquivo", "ler"), ("login_usuarios", "terminal_isolado"),
    ("memoria_pessoal", "decisao"), ("memoria_pessoal", "ficha"), ("memoria_pessoal", "lembrar"),
    ("objetivo_vivo", "passos"), ("painel", "painel_vivo"), ("pesquisa", "pesquisar"), ("prospeccao", "prospeccao"),
    ("radar", "monitor"), ("rotinas", "me_mostre"), ("rotinas", "salvar_rotina"), ("video", "assistir_video"),
    ("video", "videos_em_alta"), ("whatsapp", "criar_gatilho"), ("whatsapp", "whatsapp_enviar"),
    ("whatsapp", "whatsapp_guardar_token"),
)


def _manipulador(classe, nome):
    async def manipular(args, session_id=None, task_id=None, **kwargs):
        return await ponte.executar(classe, nome, args, session_id or task_id)
    return manipular


def register(ctx):
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
