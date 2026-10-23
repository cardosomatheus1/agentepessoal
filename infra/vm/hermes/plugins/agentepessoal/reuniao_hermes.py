"""`reuniao` no Hermes (migração, fase 5): o briefing antes da reunião e a pergunta do pós-reunião, "por cima" do cron
do próprio Hermes (no A0 viravam tarefas planejadas do agendador dele, que o Hermes não tem). Mesmo nome, mesmos
parâmetros e o mesmo registro (/a0/usr/auxiliar/<login>.json pelo helper do plugin auxiliar: os textos do briefing e do
pós, os horários, a nota da reunião no Segundo Cérebro); só o agendamento muda: um agendamento único do Hermes
(cron.jobs.create_job, o mesmo que o cronjob_manage usa), com o id guardado como "hermes:<id>".
No ensaio o registro é só leitura: agendar/cancelar/pos_registrado devolvem o aviso do ensaio (as reuniões seguem com o A0)."""
import importlib.util
import inspect
import json
import sys
from pathlib import Path

PLUGINS = Path("/a0/usr/plugins")
PREFIXO = "hermes:"


def aux():
    nome, caminho = "auxiliar_helper", PLUGINS / "auxiliar" / "helpers" / "auxiliar.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = mtime
        sys.modules[nome] = m
    return sys.modules[nome]


def _cron():
    from cron import jobs  # o cron do próprio Hermes (este código roda dentro do gateway dele)
    return jobs


def _remover(r: dict, cron) -> None:
    for chave in ("tarefa_briefing", "tarefa_pos"):
        uid = str(r.pop(chave, "") or "")
        if uid.startswith(PREFIXO):
            try:
                cron.remove_job(uid[len(PREFIXO):])
            except Exception:
                pass


def agendar(login: str, evento_id: str, titulo: str, inicio: str, fim: str = "", participantes: str = "",
            local: str = "", cron=None) -> str:
    a = aux()
    cron = cron or _cron()
    ini, fim_dt = a._data(inicio), a._data(fim)
    if not evento_id.strip() or not titulo.strip() or ini is None:
        return "Diga `evento_id`, `titulo` e `inicio` (ISO com hora)."
    fim_dt = fim_dt if fim_dt and fim_dt > ini else ini + a.dt.timedelta(hours=1)
    agora_dt = a.agora()
    if fim_dt < agora_dt:
        return "Essa reunião já terminou."
    d = a.carregar(login)
    r = next((x for x in d["reunioes"] if x["evento_id"] == evento_id.strip()), None)
    if r and r.get("inicio_ts") == ini.timestamp() and r.get("fim_ts") == fim_dt.timestamp():
        return f"«{titulo}» já estava agendada (briefing e pós-reunião)."
    if r:
        _remover(r, cron)
    else:
        r = {"evento_id": evento_id.strip()}
    r.update({"titulo": titulo.strip()[:120], "inicio_ts": ini.timestamp(), "fim_ts": fim_dt.timestamp(),
              "inicio_txt": ini.astimezone(a._tz()).strftime("%d/%m %H:%M"), "participantes": participantes.strip()[:500],
              "local": local.strip()[:300], "pos_perguntado": 0, "pos_registrado": False})
    quando_briefing = max(ini - a.ANTES_DA_REUNIAO, agora_dt + a.dt.timedelta(minutes=1))
    feito = []
    if quando_briefing < ini - a.dt.timedelta(minutes=5):
        job = cron.create_job(prompt=a.BRIEFING_SISTEMA + "\n\n" + a._prompt_briefing(r), schedule=quando_briefing.isoformat(),
                              name=f"📅 Briefing: {r['titulo']}"[:80], deliver="local", repeat=1)
        r["tarefa_briefing"] = PREFIXO + str(job["id"])
        feito.append(f"briefing às {quando_briefing.astimezone(a._tz()).strftime('%d/%m %H:%M')}")
    quando_pos = fim_dt + a.DEPOIS_DA_REUNIAO
    job = cron.create_job(prompt="Você só faz uma pergunta curta.\n\n" + a._prompt_pos(r), schedule=quando_pos.isoformat(),
                          name=f"📝 Pós-reunião: {r['titulo']}"[:80], deliver="local", repeat=1)
    r["tarefa_pos"] = PREFIXO + str(job["id"])
    feito.append(f"pergunta do pós às {quando_pos.astimezone(a._tz()).strftime('%H:%M')}")
    with a._exclusivo(login):  # relê: aplica só esta reunião ao estado atual
        atual = a.carregar(login)
        atual["reunioes"] = [x for x in atual["reunioes"] if x["evento_id"] != r["evento_id"]] + [r]
        a.salvar(login, atual)
    return f"«{r['titulo']}»: " + " e ".join(feito) + "."


def cancelar(login: str, evento_id: str, cron=None) -> str:
    a = aux()
    cron = cron or _cron()
    d = a.carregar(login)
    r = next((x for x in d["reunioes"] if x["evento_id"] == evento_id.strip()), None)
    if not r:
        return "Essa reunião não estava agendada."
    _remover(r, cron)
    with a._exclusivo(login):
        atual = a.carregar(login)
        atual["reunioes"] = [x for x in atual["reunioes"] if x["evento_id"] != r["evento_id"]]
        a.salvar(login, atual)
    return f"«{r['titulo']}» cancelada: briefing e pós-reunião removidos."


def esquema() -> dict:
    ponte = sys.modules["agentepessoal_ponte_a0"]
    props = {k: {"type": "string"} for k in ("acao", "evento_id", "titulo", "inicio", "fim", "participantes", "local",
                                             "resumo")}
    props["decisoes"] = {}
    return {"name": "reuniao", "description": ponte.manual("auxiliar", "reuniao"),
            "parameters": {"type": "object", "properties": props, "additionalProperties": False}}


async def executar(args: dict, session_id=None, task_id=None, **kw) -> str:
    ponte = sys.modules["agentepessoal_ponte_a0"]
    args = dict(args or {})
    login = ponte.login_da_sessao(str(session_id or task_id or ""))
    acao = str(args.get("acao") or "agendar").lower()
    try:
        if acao == "agendar":
            return agendar(login, *(str(args.get(k) or "") for k in ("evento_id", "titulo", "inicio", "fim",
                                                                     "participantes", "local")))
        if acao == "cancelar":
            return cancelar(login, str(args.get("evento_id") or ""))
    except Exception as exc:
        if ponte.somente_leitura(exc):
            return ponte.ERRO_SO_LEITURA
        raise
    # listar e pos_registrado não agendam nada: a mesma ferramenta do A0, pela ponte
    classe = ponte.carregar("auxiliar", "reuniao")
    return await ponte.executar(classe, "reuniao", args, session_id or task_id)


def registrar(ctx) -> None:
    ctx.register_tool(name="reuniao", toolset="agentepessoal", schema=esquema(), handler=executar, is_async=True)
