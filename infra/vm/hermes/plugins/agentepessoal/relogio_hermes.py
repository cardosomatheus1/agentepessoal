"""O relógio (migração, fase 2): as tarefas de fundo sem modelo que no A0 rodam no `job_loop` (de minuto em minuto)
rodam aqui numa thread do gateway do Hermes, chamando os MESMOS arquivos (/a0/usr/plugins/<plugin>/extensions/python/
job_loop/*.py) pela ponte_a0: publicar o post na hora, nota do dia do Segundo Cérebro, painel vivo, lembrete de contas,
conferência do livro, reenvio do que a ponte não entregou.

Só liga com AGENTEPESSOAL_RELOGIO=1: até a virada quem roda essas tarefas é o A0 (rodar as duas publicaria o post duas
vezes). No dia de sombra (fase 7) liga sobre a CÓPIA dos dados, com o ensaio (nada ao celular nem à Meta).

Fora daqui, de propósito (ver docs/MIGRACAO_HERMES.md):
- do próprio A0, sem par no Hermes (N): limpeza (abas, conversas, /tmp, time travel), agenda_confiavel (rodadas do
  agendador do A0; o cron do Hermes tem as dele), aprendizado (skills do A0; o curador do Hermes cuida das dele),
  whatsapp _55/_56 (andamento e retomada de conversas do A0; no Hermes a ponte acompanha os eventos do run);
- que entregam numa conversa do A0 ou usam o MCP dele, e voltam adaptados na fase 6: prospeccao _46_crm_raiz (MCP
  Google), whatsapp _57_email_do_agente (e-mail vira pedido numa conversa), conversas_externas _48 (resposta da loja
  vira mensagem na conversa), login_usuarios _20 (pausa as rotinas do convidado no agendador do A0).
"""
import asyncio
import importlib.util
import inspect
import logging
import os
import sys
import threading
import time
from pathlib import Path

PLUGINS = Path("/a0/usr/plugins")
TRAVA = Path("/opt/data/agentepessoal/relogio.lock")  # um relógio por container (o plugin carrega em mais de um processo)
INTERVALO = 60
TAREFAS = (
    ("conteudo", "_46_publicar_conteudo.py"),
    ("central", "_45_conferencia.py"),
    ("painel", "_47_painel.py"),
    ("whatsapp", "_58_reenviar_saida.py"),
    ("auxiliar", "_58_lembrete_contas.py"),
    ("cerebro", "_58_cerebro.py"),
    ("cerebro", "_63_cerebro_trabalho.py"),
)
log = logging.getLogger("agentepessoal.relogio")
_estado = {"thread": None, "voltas": 0, "ultima": 0.0, "erros": {}}
_parar = threading.Event()


def ligado() -> bool:
    return os.environ.get("AGENTEPESSOAL_RELOGIO") == "1"


def _classe(plugin: str, arquivo: str):
    """A extensão do job_loop (o mesmo arquivo do A0), carregada de novo quando o arquivo muda (uma implantação)."""
    ponte = sys.modules["agentepessoal_ponte_a0"]
    ponte.instalar_modulos()
    caminho = PLUGINS / plugin / "extensions" / "python" / "job_loop" / arquivo
    nome = f"hermes_relogio_{plugin}_{arquivo[:-3]}"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = mtime
        sys.modules[nome] = m
    base = sys.modules["helpers.extension"].Extension
    for valor in vars(sys.modules[nome]).values():
        if inspect.isclass(valor) and issubclass(valor, base) and valor is not base:
            return valor
    raise LookupError(f"{caminho}: nenhuma extensão")


async def volta(tarefas=TAREFAS) -> dict:
    """Uma passada por todas as tarefas; uma que falha não impede as outras. Devolve {tarefa: "ok" | erro}."""
    feito = {}
    for plugin, arquivo in tarefas:
        chave = f"{plugin}/{arquivo}"
        try:
            classe = _classe(plugin, arquivo)
            obj = classe.__new__(classe)
            obj.agent, obj.kwargs = None, {}
            await obj.execute()
            feito[chave] = "ok"
        except Exception as exc:
            feito[chave] = f"{type(exc).__name__}: {exc}"[:300]
    return feito


def _laco() -> None:
    laco = asyncio.new_event_loop()
    asyncio.set_event_loop(laco)
    while not _parar.is_set():
        inicio = time.time()
        try:
            feito = laco.run_until_complete(volta())
            erros = {k: v for k, v in feito.items() if v != "ok"}
            for k, v in erros.items():
                if _estado["erros"].get(k) != v:  # o mesmo erro não enche o log a cada minuto
                    log.warning("relógio: %s: %s", k, v)
            _estado["erros"] = erros
            _estado["voltas"] += 1
            _estado["ultima"] = time.time()
        except Exception as exc:
            log.warning("relógio: volta falhou: %s: %s", type(exc).__name__, exc)
        _parar.wait(max(1.0, INTERVALO - (time.time() - inicio)))


def iniciar() -> bool:
    """Liga a thread (uma só por processo). False quando está desligado por configuração."""
    if not ligado():
        log.warning("relógio: desligado (AGENTEPESSOAL_RELOGIO != 1): as tarefas de fundo seguem com o A0")
        return False
    if _estado["thread"] is not None and _estado["thread"].is_alive():
        return True
    import fcntl

    try:  # o processo que pega a trava fica com ela até morrer; os outros (trabalhadores do cron, CLI) não ligam
        TRAVA.parent.mkdir(parents=True, exist_ok=True)
        arquivo = open(TRAVA, "a")
        fcntl.flock(arquivo, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log.warning("relógio: outro processo deste Hermes já roda o relógio")
        return False
    _estado["trava"] = arquivo
    _parar.clear()
    t = threading.Thread(target=_laco, name="agentepessoal-relogio", daemon=True)
    _estado["thread"] = t
    t.start()
    log.warning("relógio: ligado (%d tarefas a cada %d s)", len(TAREFAS), INTERVALO)
    return True


def registrar(ctx) -> None:
    iniciar()
