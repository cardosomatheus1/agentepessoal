"""As rotinas no Hermes (migração, fase 5): as 23 tarefas agendadas do A0 viram agendamentos do cron do Hermes
(`infra/operador/rotinas_hermes.py` cria, pausados até a virada), com o mesmo pedido e o mesmo horário. Aqui fica o
que o A0 fazia em volta de cada rodada e o cron do Hermes não faz:

- `pre_llm_call` (1º turno da sessão do cron): o bloco de tarefa agendada do A0 (LER → ENTENDER → AGIR, checkpoint,
  SEM NOVIDADE, PRECISA DE VOCÊ), com o checkpoint num arquivo por rotina (cada rodada do cron é uma sessão nova);
- também no 1º turno: as correções que o Matheus aprovou para a rotina (autoavaliação → "Aplicar");
- o portão (pular a rodada quando nada mudou) é o "script" do cron do Hermes (scripts/portao.py, contrato wakeAgent);
- `post_llm_call` (fim da rodada): confirma o estado do portão, roda a autoavaliação (uma linha; melhoria vira
  proposta com Aplicar/Não no celular, no máximo 1 por semana) e a resposta final vai ao celular do dono como no A0
  (whatsapp/extensions/.../_50_enviar_resposta.py): "SEM NOVIDADE" fica quieto; "PRECISA DE VOCÊ" ou bloqueio vai como
  urgente (chega no horário de silêncio); o resto como progresso, com o nome da rotina (a ponte junta os avisos da
  noite dentro do 📰 Resumo do dia pelo nome, como no A0). No ensaio, nada vai ao celular: fica em ensaio_celular.jsonl.

O mapa job do Hermes → rotina do A0 fica em /opt/data/agentepessoal/rotinas.json (escrito pelo operador)."""
import importlib.util
import json
import logging
import re
import sys
import threading
from pathlib import Path

PLUGINS = Path("/a0/usr/plugins")
DADOS = Path("/opt/data/agentepessoal")
MAPA = DADOS / "rotinas.json"          # {job_id: {"a0": uuid, "nome": nome}}
CHECKPOINTS = DADOS / "rotinas"         # <a0 uuid ou job>/contexto.md
JOBS = Path("/opt/data/cron/jobs.json")  # o cron do próprio Hermes (para o nome, se o mapa não tiver)
CRON = re.compile(r"^cron_([A-Za-z0-9]+)_\d{8}_\d{6}$")
LIMITE_CELULAR = 3500
# 29/10: o 🔎 Radar respondia SEM NOVIDADE com o Google pedindo login de novo em quase toda chamada (26-28/10): o Matheus
# não sabia que o Gmail e a Agenda não estavam sendo lidos. Conector que pede login numa rodada vira aviso a ele.
SEM_LOGIN = re.compile(r"ACTION REQUIRED: \w+ Authentication|Authentication (Needed|required)", re.I)
FONTES = {"google": "Gmail, Agenda e Drive"}
AVISOS_LOGIN = DADOS / "avisos_conector.json"  # {"<login>|<conector>": "AAAA-MM-DD"}: no máximo 1 aviso por dia
_sem_login: dict = {}  # sessão -> conectores que pediram login nesta rodada
CHECKPOINT_MAX = 16000  # caracteres: o checkpoint só cresce (a rodada acrescenta no fim); o começo antigo é cortado
log = logging.getLogger("agentepessoal.rotinas")
_trava = threading.Lock()
_avisadas: set = set()

TAREFA = """## Esta conversa é uma rotina agendada: {nome}
Cada rodada segue LER → ENTENDER → AGIR, qualquer que seja a tarefa:
1. LER: o que mudou desde a última rodada (o seu checkpoint `{checkpoint}` e as fontes da tarefa), lendo o conteúdo de verdade — a mensagem, o e-mail, a página —, não só status e títulos.
2. ENTENDER: qual é o objetivo do usuário com esta tarefa e o que o que mudou significa para ele: alguém (uma pessoa, uma sessão, um sistema) está esperando algo que você pode dar? algo de uma fonte precisa chegar a outra? algo travou ou precisa da decisão dele? Quando houver decisão com contexto a tomar (coordenar, priorizar, interpretar o que outros escreveram), chame `consultar_sol` com o texto relevante copiado e peça ações concretas.
3. AGIR: faça o que essa leitura pede, dentro do que a tarefa e as regras do usuário autorizam — repasse, instrua, corrija, avise. "Observei e não fiz nada" só vale quando o passo 2 concluiu que nada era preciso.
Registre no checkpoint o que viu e o que fez, para não repetir ação na próxima rodada (cada rodada começa numa conversa nova: o checkpoint é a sua memória desta rotina). Registrar é ACRESCENTAR no fim, com `terminal`: `cat >> {checkpoint} <<'FIM_CHECKPOINT_7F3'` + as linhas novas (data e hora no começo) + `FIM_CHECKPOINT_7F3`. Não releia nem reescreva o arquivo inteiro: na mesma rodada, uma 2ª leitura volta `unchanged` sem o conteúdo (também dentro de `execute_code`), e reescrever de memória perde anotações. O começo antigo é cortado sozinho quando o arquivo cresce.

Sua resposta final de cada rodada chega sozinha no celular do usuário (Telegram/WhatsApp): seja curto e comece pelo que importa. Se a rodada gerou um arquivo para ele, mande o arquivo com `whatsapp_enviar` em vez de citar o caminho da pasta (ele não acessa a máquina).
- Se a tarefa disser para ficar em silêncio quando não houver novidade e esta rodada não tiver nada novo, comece a resposta final com `SEM NOVIDADE` (ela não é enviada).
- Se a rodada precisa do usuário agora — uma decisão ou aprovação que só ele dá, ou um bloqueio que só ele resolve (login, código, captcha, conta bloqueada) —, comece a resposta final com `PRECISA DE VOCÊ:`: chega na hora mesmo no horário de silêncio dele. Falha que se resolve sozinha ou na próxima rodada não é urgência: conte no texto normal.
- Termine cada rodada com a resposta final; não fique esperando a próxima rodada dentro desta."""


def _modulo(nome: str, caminho: Path):
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = mtime
        sys.modules[nome] = m
    return sys.modules[nome]


def ponte_celular():
    return _modulo("whatsapp_ponte", PLUGINS / "whatsapp" / "helpers" / "ponte.py")


def _rotinas_a0():
    return _modulo("rotinas_helper", PLUGINS / "rotinas" / "helpers" / "rotinas.py")


def _portao():
    return _modulo("rotinas_portao", PLUGINS / "rotinas" / "helpers" / "portao.py")


def _autoavaliacao():
    return _modulo("rotinas_autoavaliacao", PLUGINS / "rotinas" / "helpers" / "autoavaliacao.py")


def correcoes(a0: str) -> str:
    """As correções que o Matheus aprovou para esta rotina (o "Aplicar" da autoavaliação), como no A0."""
    if not a0:
        return ""
    try:
        lista = _rotinas_a0().correcoes_agendada(a0)
    except Exception as exc:
        log.warning("rotinas: correções de %s não lidas: %s: %s", a0, type(exc).__name__, exc)
        return ""
    return ("## Correções do Matheus para esta rotina (valem acima dos passos)\n" + "\n".join(f"- {c}" for c in lista)
            if lista else "")


def _avaliar(r: dict, texto: str, pedido: str) -> None:
    try:
        res = _autoavaliacao().autoavaliar(r["a0"], r["nome"], texto, pedido=pedido[:3000])
        log.warning("rotinas: autoavaliação de %s: %s", r["nome"], res.get("motivo"))
    except Exception as exc:  # nunca visível a ele; a próxima rodada avalia de novo
        log.warning("rotinas: autoavaliação de %s falhou: %s: %s", r["nome"], type(exc).__name__, exc)


def job_da_sessao(sessao: str) -> str:
    m = CRON.match(str(sessao or ""))
    return m.group(1) if m else ""


def rotina(job: str) -> dict:
    """{"a0": uuid do A0 (ou ""), "nome": nome} desta rotina do Hermes."""
    try:
        mapa = json.loads(MAPA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        mapa = {}
    item = mapa.get(job) if isinstance(mapa, dict) else None
    if isinstance(item, dict) and item.get("nome"):
        return {"a0": str(item.get("a0") or ""), "nome": str(item["nome"])}
    try:
        jobs = json.loads(JOBS.read_text(encoding="utf-8"))
        lista = jobs.get("jobs", jobs) if isinstance(jobs, dict) else jobs
        for j in lista or []:
            if isinstance(j, dict) and j.get("id") == job:
                return {"a0": "", "nome": str(j.get("name") or job)}
    except (OSError, ValueError):
        pass
    return {"a0": "", "nome": job}


def aparar(arq: Path) -> None:
    """Checkpoint maior que CHECKPOINT_MAX: fica a 1ª linha (o cabeçalho) e as anotações mais novas, inteiras. Roda no
    começo da rodada, antes de o agente ler (nada escreve nele ao mesmo tempo); troca o arquivo inteiro de uma vez."""
    texto = arq.read_text(encoding="utf-8", errors="replace")
    if len(texto) <= CHECKPOINT_MAX:
        return
    cabeca = texto.split("\n", 1)[0] if texto.startswith("#") else ""
    fim = texto[-(CHECKPOINT_MAX - len(cabeca) - 100):]
    fim = fim.split("\n", 1)[1] if "\n" in fim else fim
    novo = (f"{cabeca}\n\n" if cabeca else "") + "(anotações mais antigas cortadas para o arquivo não crescer sem fim)\n" + fim
    tmp = arq.with_suffix(".md.tmp")
    tmp.write_text(novo, encoding="utf-8")
    tmp.replace(arq)


def contexto(session_id="", task_id="", is_first_turn=False, **kw):
    """Gancho `pre_llm_call`: o bloco de tarefa agendada no 1º turno de uma rodada do cron."""
    job = job_da_sessao(session_id or task_id)
    if not job or not is_first_turn:
        return None
    r = rotina(job)
    pasta = CHECKPOINTS / (r["a0"] or job)
    arq = pasta / "contexto.md"
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        if not arq.exists():  # 27/10: a 1ª rodada lia um arquivo que não existia ("File not found") e perdia passos
            arq.write_text(f"# Checkpoint da rotina {r['nome']}\n\n(primeira rodada: nada registrado ainda)\n",
                           encoding="utf-8")
        else:
            aparar(arq)
    except OSError:
        pass
    texto = TAREFA.format(nome=r["nome"], checkpoint=arq)
    extra = correcoes(r["a0"])
    return {"context": texto + (f"\n\n{extra}" if extra else "")}


def fonte_sem_login(tool_name: str, texto: str, kw=None) -> str:
    """Dentro do gancho `transform_tool_result` (cofre_hermes.DEPOIS): anota o conector (mcp__<conector>__...) que
    respondeu pedindo login, na sessão da rodada. Não muda o texto."""
    nome = str(tool_name or "")
    sessao = str((kw or {}).get("session_id") or (kw or {}).get("task_id") or "")
    if nome.startswith("mcp__") and job_da_sessao(sessao) and SEM_LOGIN.search(str(texto or "")[:3000]):
        with _trava:
            _sem_login.setdefault(sessao, set()).add(nome.split("__")[1])
    return texto


def aviso_sem_login(conectores) -> str:
    nomes = ", ".join(f"{c.capitalize()} ({FONTES[c]})" if c in FONTES else c.capitalize() for c in sorted(conectores))
    return (f"o conector {nomes} do agente desconectou e pede login de novo: nesta rodada nada dele foi lido. Para "
            "religar é preciso entrar de novo nessa conta pelo computador (o operador tem o passo a passo).")


def _avisar_hoje(login: str, conectores, agora: float | None = None) -> bool:
    """True (e anota) quando ainda não houve aviso hoje deste login para algum desses conectores."""
    import time
    hoje = time.strftime("%Y-%m-%d", time.localtime(agora))
    try:
        feitos = json.loads(AVISOS_LOGIN.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        feitos = {}
    novos = [c for c in conectores if feitos.get(f"{login}|{c}") != hoje]
    if not novos:
        return False
    feitos.update({f"{login}|{c}": hoje for c in novos})
    try:
        tmp = AVISOS_LOGIN.with_suffix(".tmp")
        tmp.write_text(json.dumps(feitos, ensure_ascii=False), encoding="utf-8")
        tmp.replace(AVISOS_LOGIN)
    except OSError:
        pass
    return True


def mensagem(nome: str, texto: str) -> str:
    texto = texto.strip()
    if len(texto) > LIMITE_CELULAR:
        texto = texto[:LIMITE_CELULAR].rsplit(" ", 1)[0] + "…"
    return f"*{nome}*\n\n{texto}"


def entregar(session_id="", assistant_response="", **kw):
    """Gancho `post_llm_call`: a resposta final de uma rodada do cron vai ao celular do dono (regras do A0)."""
    job = job_da_sessao(session_id)
    if not job or not isinstance(assistant_response, str) or not assistant_response.strip():
        return None
    with _trava:  # uma entrega por sessão (o gancho não dispara de novo, mas uma repetição nunca vira 2 mensagens)
        if session_id in _avisadas:
            return None
        _avisadas.add(session_id)
    p = ponte_celular()
    texto = assistant_response.strip()
    r = rotina(job)
    if r["a0"]:
        try:  # a rodada terminou: o que o portão viu passa a valer (uma rodada que falha veria a mudança de novo)
            _portao().confirmar(r["a0"])
        except Exception:
            pass
        user = kw.get("user_message")
        threading.Thread(target=_avaliar, args=(r, texto, user if isinstance(user, str) else ""), daemon=True,
                         name="rotinas-autoavaliacao").start()
    with _trava:
        sem_login = _sem_login.pop(session_id, set())
    login = sys.modules["agentepessoal_ponte_a0"].login_da_sessao(session_id)
    if texto.upper().startswith(p.SILENCIO):
        if not sem_login or not _avisar_hoje(login, sem_login):
            log.warning("rotinas: %s sem novidade (não enviada)", session_id)
            return None
        texto = "PRECISA DE VOCÊ: " + aviso_sem_login(sem_login)
    elif sem_login:
        texto += "\n\n⚠️ Também: " + aviso_sem_login(sem_login)
    tipo = "urgente" if (p.urgente(texto) or p.pede_tela(texto)) else "progresso"
    # `rotina` = o NOME, como o A0 (_50_enviar_resposta): a ponte põe os avisos da noite dentro do 📰 Resumo do dia
    erro = p.enviar(login, mensagem(r["nome"], texto), "", "", None, tipo, False, r["nome"], None, reenviar=True)
    log.warning("rotinas: resultado de %s (%s) para %s: %s", r["nome"], session_id, login, erro or "ok")
    return None


def registrar_fontes(cofre) -> None:
    if fonte_sem_login not in cofre.DEPOIS:
        cofre.DEPOIS.append(fonte_sem_login)


def registrar(ctx) -> None:
    ctx.register_hook("pre_llm_call", contexto)
    ctx.register_hook("post_llm_call", entregar)
