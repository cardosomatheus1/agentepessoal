"""O que cada conversa pode usar no Hermes (migração, fase 2), num gancho `pre_tool_call` (bloqueio determinístico; o
Hermes trata erro ou demora dele como bloqueio):

- Convidados (ilia, will; decisão 1 do Matheus, 23/10): só as ferramentas de uso pessoal, como no A0
  (login_usuarios/helpers/convidados.py). Nunca o `terminal`, o `execute_code` ou os arquivos do Hermes (leem
  /a0/usr/segredos e os dados de todos): o computador deles é o `terminal_isolado` (caixa própria). Nem a memória, a
  busca nas conversas, as skills, o cron ou o navegador do Matheus. Caminho local fora das pastas deles é recusado.
- Ensaio até a virada (AGENTEPESSOAL_ENSAIO=1): o navegador só lê (abrir, ler a página, rolar, voltar, ver imagens;
  e o clique que só abre uma conversa da caixa do Direct). Clicar no resto, digitar, teclar, rodar JS ou CDP ficam
  bloqueados: com o perfil logado do Instagram, um clique pode seguir,
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
# notas e cofre dele, o computador isolado dele, conversas com lojas no WhatsApp dele).
CONVIDADO_PODE = frozenset({
    "web_search", "web_extract", "vision_analyze", "video_analyze", "clarify", "todo_list", "text_to_speech",
    "lembrar", "ficha", "cofre_descrever", "analisar_imagens", "assistir_video", "videos_em_alta", "whatsapp_enviar",
    "terminal_isolado", "ler", "conversa_externa",
})
# Virada (fase 8): no Hermes PRÓPRIO do convidado (hermes/convidado.sh: memória, conversas, cron e navegador só dele)
# voltam o navegador (perfil dele), a memória e a busca nas conversas (as dele), os subagentes e as rotinas (até 5, no
# máximo de hora em hora, como no A0: convidados.TAREFAS_MAX).
CONVIDADO_NA_INSTANCIA = frozenset({"memory", "session_search", "delegate_task", "cronjob_manage"})
INTERVALO = re.compile(r"^(?:every\s+)?(\d+)\s*(m|min|mins|minutes?|h|hr|hrs|hours?|d|days?)$")
# Ferramentas que leem um caminho local: só as pastas do convidado (convidados.caminho_proibido).
LEEM_CAMINHO = frozenset({"whatsapp_enviar", "analisar_imagens", "assistir_video", "ler", "vision_analyze", "video_analyze"})

NAVEGADOR_SO_LE = frozenset({"browser_navigate", "browser_snapshot", "browser_scroll", "browser_back",
                             "browser_get_images", "browser_vision"})
CDP = re.compile(r"(?i)\bcdp\b|devtools|remote-debugging|:922[23]\b|navegador-hermes|hermes-navegador|playwright|puppeteer|"
                 r"chrome-remote-interface|websocket|\bws://|agent-browser")
CODIGO = frozenset({"terminal", "execute_code", "process_manage"})
# Ensaio: o único clique que passa é o de ABRIR uma conversa (ou uma aba da caixa) no Direct do Instagram, pelo rótulo
# que a última leitura da página deu ao elemento (a lista não tem links: cada conversa é um botão). Nada com cara de
# ação (enviar, seguir, curtir, apagar…), nada fora do /direct.
DIRECT = re.compile(r"^https://(www\.)?instagram\.com/direct/")
ABRIR_CONVERSA = re.compile(r'^(button|link|tab|listitem|gridcell|row) "(user-profile-picture |'
                            r'(Primary|General|Requests|Principal|Geral|Solicita[çc][õo]es|Mensagens)\b)')
ACAO = re.compile(r"(?i)\b(send|enviar|envie|follow|seguir|like|curtir|delete|apagar|excluir|unsend|cancelar envio|"
                  r"block|bloquear|report|denunciar|restrict|restringir|accept|aceitar|decline|recusar|call|ligar|"
                  r"video|chamada|new message|nova mensagem|reply|responder|react|reagir|share|compartilhar)\b")


# Rotinas (cron, ninguém para aprovar; approvals.cron_mode approve como no A0): o código e os scripts rodam, menos o
# que apaga/move/trunca dados vivos fora das pastas de trabalho, mexe no cofre, nas chaves ou no Docker, ou fala com a
# ponte/proxy/navegador por fora das ferramentas.
ROTINA = re.compile(r"^cron_[A-Za-z0-9]+_\d{8}_\d{6}$")
ROTINA_PROIBIDO = re.compile(
    r"(?i)(\b(rm|rmdir|shred|truncate|mv|unlink)\b[^;&|\n]*\s/(a0/usr|opt/data)(?!/(workdir|tmp|cache|scratch|agentepessoal/rotinas)\b)"
    r"|\b(rm|rmdir|shred|unlink)\b[^;&|\n]*\s/(a0/usr|opt/data)/?(\s|$|['\"])"
    r"|shutil\.rmtree|os\.(remove|unlink|rmdir)\s*\(\s*['\"]/(a0/usr|opt/data)(?!/(workdir|tmp|cache|scratch))"
    r"|/a0/usr/segredos|segredos/|API_SERVER_KEY|whatsapp/\.chave|\bdocker\b|:8789\b|:8787\b|:8642\b|:922[23]\b)")


def checar_rotina(tool_name: str, args: dict, sessao: str):
    if not ROTINA.match(sessao or "") or tool_name not in CODIGO:
        return None
    texto = json.dumps(args, ensure_ascii=False, default=str)
    if ROTINA_PROIBIDO.search(texto):
        return _bloqueio("Rotina: este comando mexe em dados vivos, no cofre, em chaves, no Docker ou nos serviços do "
                         "agente por fora das ferramentas. Use as ferramentas do agente (ou workdir/tmp para arquivos "
                         "seus); o que precisar do Matheus, diga na resposta final com PRECISA DE VOCÊ.")
    return None


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
        propria = ponte.convidado_da_instancia() == login
        if propria and (tool_name.startswith("browser_") or tool_name in CONVIDADO_NA_INSTANCIA):
            if tool_name == "cronjob_manage":
                motivo = rotina_de_convidado(c, args)
                return _bloqueio(motivo) if motivo else None
            return None
        if tool_name not in CONVIDADO_PODE:
            return _bloqueio(f"«{tool_name}» não está disponível nesta conversa (uso pessoal de convidado). "
                             "Faça com as ferramentas que você tem ou diga com educação que não dá.")
        if tool_name in LEEM_CAMINHO:
            proibido = c.caminho_proibido(login, args)
            if proibido:
                return _bloqueio(f"O caminho {proibido} não é desta pessoa: só os arquivos que ela mandou.")
    bloqueio_rotina = checar_rotina(tool_name, args, str(session_id or task_id or ""))
    if bloqueio_rotina:
        return bloqueio_rotina
    if ensaio():
        if tool_name == "browser_click" and abre_conversa(str(session_id or task_id or ""), args):
            return None
        if tool_name.startswith("browser_") and tool_name not in NAVEGADOR_SO_LE:
            return _bloqueio("Ensaio do Hermes: até a virada o navegador só lê (abrir, ler a página, rolar, voltar). "
                             "Clicar, digitar e teclar continuam com o agente de hoje; não tente de outro jeito. "
                             "Diga ao operador o que ia fazer.")
        if tool_name in CODIGO and CDP.search(json.dumps(args, ensure_ascii=False, default=str)):
            return _bloqueio("Ensaio do Hermes: o terminal e o código não falam com o navegador por fora. Use as "
                             "ferramentas browser_* (no ensaio, só leitura).")
    return None


def _jobs_do_cron() -> list:
    from cron import jobs  # o cron do próprio Hermes (no do convidado, todos são dele)

    return jobs.list_jobs(include_disabled=True)


def rotina_de_convidado(c, args: dict, jobs=None) -> str:
    """Por que esta chamada do cronjob_manage é recusada a um convidado ("" = pode). As regras do A0
    (convidados.regra_agenda): até TAREFAS_MAX rotinas, no máximo de hora em hora; e nada de código (script, monitor
    por script, sem agente), que rodaria fora das ferramentas dele."""
    acao = str(args.get("action") or "").strip().lower()
    if acao not in ("create", "update", "list", "pause", "resume", "remove", "run"):
        return f"A ação '{acao}' das rotinas não está disponível aqui."
    if args.get("script") or args.get("no_agent") or (args.get("monitor") and not str(args["monitor"]).startswith("http")):
        return "Rotinas de convidado não rodam código (script/monitor por script): só um pedido em texto."
    if acao == "create":
        lista = jobs if jobs is not None else _jobs_do_cron()
        if len(lista) >= c.TAREFAS_MAX:
            return (f"Esta pessoa já tem {len(lista)} rotinas (o máximo é {c.TAREFAS_MAX}). Pergunte qual apagar "
                    "(action remove) antes de criar outra.")
    agenda = str(args.get("schedule") or "").strip().lower()
    if acao in ("create", "update") and agenda:
        campos = agenda.split()
        m = INTERVALO.match(agenda)
        if len(campos) == 5 and not agenda.startswith(("every", "in ")):
            if not re.fullmatch(r"\d{1,2}", campos[0]):
                return ("Rotinas de convidado rodam no máximo de hora em hora: use um minuto fixo no cron (ex.: "
                        "\"0 9 * * *\"), não \"*\" nem \"*/n\".")
        elif m and m.group(2).startswith("m") and int(m.group(1)) < 60:
            return "Rotinas de convidado rodam no máximo de hora em hora (every 1h ou mais)."
    return ""


def abre_conversa(sessao: str, args: dict) -> bool:
    """O clique só abre uma conversa (ou aba) da caixa do Direct: elemento conhecido, rótulo de conversa, sem ação."""
    aprov = sys.modules.get("agentepessoal_aprovacoes")
    if aprov is None:
        return False
    rotulo, url = aprov.alvo(sessao, str(args.get("ref") or ""))
    return bool(rotulo and DIRECT.match(url or "") and ABRIR_CONVERSA.match(rotulo) and not ACAO.search(rotulo))


def registrar(ctx) -> None:
    ctx.register_hook("pre_tool_call", checar)
