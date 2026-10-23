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


def _sub(nome: str, arquivo: str):
    spec = importlib.util.spec_from_file_location(nome, _aqui / arquivo)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


cofre = _sub("agentepessoal_cofre", "cofre_hermes.py")
uso = _sub("agentepessoal_uso", "uso_hermes.py")
acesso = _sub("agentepessoal_acesso", "acesso_hermes.py")
aprovacoes = _sub("agentepessoal_aprovacoes", "aprovacoes_hermes.py")
relogio = _sub("agentepessoal_relogio", "relogio_hermes.py")
rotinas = _sub("agentepessoal_rotinas", "rotinas_hermes.py")
contexto = _sub("agentepessoal_contexto", "contexto_hermes.py")
reuniao = _sub("agentepessoal_reuniao", "reuniao_hermes.py")
audio = _sub("agentepessoal_audio", "audio_hermes.py")
email = _sub("agentepessoal_email", "email_hermes.py")  # tarefa do relógio (sem registro próprio)
botoes = _sub("agentepessoal_botoes", "botoes_hermes.py")  # botões/comandos do celular (a ponte roda o arquivo)
externas = _sub("agentepessoal_externas", "externas_hermes.py")  # conversas externas (ferramenta + vigia do relógio)
mcp = _sub("agentepessoal_mcp", "mcp_hermes.py")  # conector Google para código sem modelo (CRM da prospecção)
limite = _sub("agentepessoal_limite", "limite_hermes.py")  # limite do dia do convidado (relógio do Hermes dele)
resolver = _sub("agentepessoal_resolver", "resolver_hermes.py")  # "🖥️ Resolver aqui" (o navegador_visual do A0)
subagentes = _sub("agentepessoal_subagentes", "subagentes_hermes.py")  # resultado dos subagentes volta ao celular
log = logging.getLogger("agentepessoal")

# (plugin, ferramenta). "Hermes primeiro" (23/10): só entra o que é nosso de verdade (dados, Raiz, Segundo Cérebro).
# Fora, de propósito:
#  - o que o Hermes já faz bem: pesquisa/pesquisar (= web_search); conectores/conector e prompt_enxuto/ferramentas_extras
#    (MCP e lista de ferramentas próprios);
#  - o que grava no agendador ou nas conversas do Agent Zero (chamado daqui, criaria tarefa que o A0 executa):
#    agenda_confiavel/tarefa_limite, rotinas/me_mostre e salvar_rotina, whatsapp/criar_gatilho, objetivo_vivo/passos,
#    painel/painel_vivo, canais/canal, auxiliar/reuniao (briefing e pós-reunião agendados). Voltam na fase 5 por cima do
#    cron do Hermes (ou ficam no cron dele); conversas_externas/conversa_externa (abre conversa no A0) volta na fase 6;
#  - agent_delegates/delegar e text_delegate (o Hermes tem delegate_task; o `listar/parar` daqui pararia tarefas que o
#    A0 delegou na mesma caixa) e whatsapp/whatsapp_guardar_token (usa o navegador do A0): voltam na fase 6 (OpenClaw);
#  - o que espera resposta pela ponte do celular: whatsapp/perguntar e pedir_codigo (fase 6);
#  - celular_rapido/celular: põe a imagem da tela no histórico do A0 (precisa de adaptação).
# Na virada (fase 8) voltaram, adaptados: conversa_externa (externas_hermes.py), celular (a tela vira um arquivo para o
# vision_analyze, ponte_a0.guardar_imagem), delegar (só o OpenClaw: para o resto o Hermes tem delegate_task) e
# me_mostre (grava o navegador do Hermes; a pessoa mexe nele pela página Navegador do portal).
FERRAMENTAS = (
    ("analisar_imagens", "analisar_imagens"), ("auxiliar", "contas"), ("auxiliar", "rascunho"),
    ("central", "livro"), ("cerebro", "cerebro"), ("cofre", "cofre_descrever"),
    ("concorrentes", "concorrentes"), ("consultar_sol", "consultar_sol"), ("conteudo", "conteudo"),
    ("especialistas", "especialista"), ("fios_soltos", "fios"),
    ("iniciativa", "iniciativa"), ("ler_arquivo", "ler"), ("login_usuarios", "terminal_isolado"),
    ("memoria_pessoal", "decisao"), ("memoria_pessoal", "ficha"), ("memoria_pessoal", "lembrar"),
    ("prospeccao", "prospeccao"), ("radar", "monitor"), ("video", "assistir_video"),
    ("video", "videos_em_alta"), ("whatsapp", "whatsapp_enviar"),
    ("conversas_externas", "conversa_externa"), ("celular_rapido", "celular"), ("agent_delegates", "delegar"),
    ("rotinas", "me_mostre"),
)

# O que muda numa ferramenta do A0 ao rodar aqui: preparo antes (helpers com os pontos do Hermes), argumentos fixos e
# uma nota no manual / na resposta.
PREPAROS = {"conversa_externa": lambda: externas.instalar()}
FIXOS = {"delegar": {"motor": "openclaw"}}  # decisão 5 do Matheus: delegar é para o OpenClaw; o Hermes tem delegate_task
NOTAS_MANUAL = {
    "delegar": "No agente novo: subtarefas e trabalho em paralelo são com `delegate_task`; `delegar` manda a tarefa só "
               "ao OpenClaw (motor é sempre openclaw).",
    "celular": "A imagem da tela, quando vem, fica num arquivo (o caminho vem na resposta): veja com vision_analyze.",
    "me_mostre": "No agente novo o navegador fica na página Navegador do portal (o mesmo link do agente, /navegador): é "
                 "lá que a pessoa faz a tarefa enquanto você grava.",
}


def _url_portal() -> str:
    try:
        return Path("/a0/usr/agente/url.txt").read_text().strip().rstrip("/")
    except OSError:
        return ""


def _nota_resposta(nome: str, texto: str) -> str:
    if nome == "me_mostre" and "Navegador" in texto:
        url = _url_portal()
        return texto + (f"\nNo agente novo o navegador é a página {url}/navegador (mesmo login do agente)." if url else
                        "\nNo agente novo o navegador é a página Navegador do portal do agente (mesmo login).")
    return texto


def _manipulador(plugin, nome):
    async def manipular(args, session_id=None, task_id=None, **kwargs):
        if nome in PREPAROS:
            PREPAROS[nome]()
        classe = ponte.carregar(plugin, nome)  # de novo se o arquivo mudou (implantação do plugin)
        texto = await ponte.executar(classe, nome, {**(args or {}), **FIXOS.get(nome, {})}, session_id or task_id)
        return _nota_resposta(nome, texto)
    return manipular


def _esquema(plugin, nome, classe) -> dict:
    esquema = ponte.esquema(plugin, nome, classe)
    if nome in NOTAS_MANUAL:
        esquema["description"] = NOTAS_MANUAL[nome] + "\n\n" + esquema["description"]
    if nome in FIXOS:
        for campo in FIXOS[nome]:
            esquema["parameters"].get("properties", {}).pop(campo, None)
    return esquema


def register(ctx):
    cofre.registrar(ctx)  # antes das ferramentas: sem ele, nenhuma recebe senha (o §§secret segue como texto)
    uso.registrar(ctx)    # dono/sessão/rotina de cada chamada de modelo, para o uso.jsonl do proxy
    acesso.registrar(ctx)  # convidados só com o uso pessoal; ensaio: navegador só lê
    aprovacoes.registrar(ctx)  # revisor + regras do Matheus antes de ação de risco
    relogio.registrar(ctx)  # tarefas de fundo sem modelo (só com AGENTEPESSOAL_RELOGIO=1: até a virada, o A0 roda)
    rotinas.registrar(ctx)  # rodada do cron: bloco de tarefa agendada e o resultado ao celular (regras do A0)
    contexto.registrar(ctx)  # ficha e decisões em vigor de quem fala, no 1º turno
    audio.registrar(ctx)  # áudio do celular transcrito antes do modelo (faster-whisper, como no A0)
    resolver.registrar(ctx)  # "🖥️ Resolver aqui": print + botão para o Matheus fazer na aba (só o dono)
    subagentes.registrar(ctx)  # subagentes em segundo plano: quando terminam, a sessão acorda e a resposta vai ao celular
    try:  # `reuniao` por cima do cron do Hermes (briefing e pós-reunião)
        reuniao.registrar(ctx)
        feitas_extra = ["reuniao"]
    except Exception as exc:
        feitas_extra = []
        log.warning("agentepessoal: reuniao pulada: %s: %s", type(exc).__name__, exc)
    feitas, puladas = [], []
    for plugin, nome in FERRAMENTAS:
        try:
            classe = ponte.carregar(plugin, nome)
            ctx.register_tool(name=nome, toolset="agentepessoal", schema=_esquema(plugin, nome, classe),
                              handler=_manipulador(plugin, nome), is_async=True)
            feitas.append(nome)
        except Exception as exc:  # one broken tool never takes the others down
            puladas.append(f"{plugin}/{nome}: {type(exc).__name__}: {exc}"[:300])
    log.warning("agentepessoal: %d ferramentas registradas; puladas: %s", len(feitas) + len(feitas_extra),
                puladas or "nenhuma")
