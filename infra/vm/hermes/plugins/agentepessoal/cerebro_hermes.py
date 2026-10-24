"""O Segundo Cérebro nas conversas do Hermes (24/10, Matheus: "Me diz pra que serve segundo cérebro então? Ou não tá
preenchendo ele ou não tá buscando informações").

No A0 isto eram duas extensões do plugin `cerebro` que a migração não trouxe: `monologue_end/_62_cerebro_captura.py`
(a anotação automática depois de cada mensagem dele) e `system_prompt/_27_cerebro.py` (as regras, os Assuntos abertos
com onde pararam e as notas ligadas ao que ele acabou de escrever, em todo turno). No Hermes só a ficha e as decisões
entravam, e só no 1º turno da sessão (tg-matheus é uma sessão só, resumida várias vezes: depois do resumo, nada).

- Escrever (`post_llm_call`, uma vez por turno): a mensagem dele e a resposta do agente (o relato do que foi feito)
  viram um arquivo na fila do Segundo Cérebro (/a0/usr/segundo_cerebro/entrada), a mesma do operador; o relógio lê com
  a anotação automática (cerebro/helpers/trabalho.py + captura.py: decisão e pendência nova só com as palavras dele; o
  relato move o onde parou dos Assuntos e fecha pendências feitas) e manda o "📌 Anotei …". Aviso do vigia de tarefas e
  mensagem do operador não são palavras dele: vão como relato.
- Ler (`pre_llm_call`, todo turno): o que da Pasta ainda não está na conversa (depois de um resumo, tudo de novo): as
  regras, os Assuntos abertos com onde pararam (o que mudou desde a última vez), as pendências dele, as notas ligadas
  ao que ele acabou de escrever e o assunto de cada tarefa longa aberta. A Pasta é só do dono; teste_* (o login de
  teste) usa as decisões e pendências dele mesmo, nunca as do Matheus.
- Tarefas longas: cada passo que termina (feito, não deu, esperando ele) move sozinho o onde parou do assunto ligado à
  tarefa (tarefas_hermes chama `passo_da_tarefa`), sem depender de o modelo lembrar.
Nada disto roda no Hermes de um convidado além da leitura das coisas dele (lá a fila não é lida)."""
from __future__ import annotations

import importlib.util
import json
import logging
import os
import re
import secrets
import sys
import time
from pathlib import Path

PLUGINS = Path("/a0/usr/plugins")
ENTRADA = Path("/a0/usr/segundo_cerebro/entrada")
DONO = "matheus"
RELATO_MAX = 6000
DELE_MAX = 4000
BLOCO_MAX = 7000
ASSUNTOS_PAINEL = 8
MARCA = "## Segundo Cérebro (como funciona)"
NAO_DELE = ("[Aviso automático", "(Operador)", "[Operador]")
log = logging.getLogger("agentepessoal.cerebro")

REGRAS_DONO = MARCA + """
A Pasta do Matheus (/a0/usr/segundo_cerebro/pasta) é a fonte do que ele decidiu, do que está em andamento (Assuntos,
com onde parou) e do que ele tem de fazer (Pendências).
- Ler: antes de responder sobre algo já conversado ou feito (qual conta foi usada, se um problema já foi resolvido,
  onde parou, o que ele decidiu), use o bloco «Do Segundo Cérebro» que vem com as mensagens; faltou detalhe →
  `cerebro` acao=consultar texto=<palavras>. Não pergunte a ele o que está lá; o que não está, diga que não está.
- Escrever: depois de cada resposta sua, a anotação automática lê a mensagem dele e o que você fez e registra sozinha
  decisões, pendências e o onde parou dos assuntos (ele recebe «📌 Anotei …»). Cada passo de tarefa longa
  (tarefa_passo) atualiza sozinho o assunto ligado à tarefa: ponha no `resultado` os fatos que valem depois (conta,
  e-mail, id, o que foi resolvido). Fato que muda o rumo e não cabe num passo: `cerebro` acao=assunto ref=<id>
  onde_parou=… na hora.
- Ele corrigiu uma anotação («não era isso», «tira») → `cerebro` acao=desfazer."""

REGRAS_OUTRO = MARCA + """
O que esta pessoa decidiu e o que ela tem de fazer ficam registrados (decisões e pendências dela). Depois de cada
resposta sua, a anotação automática registra sozinha as decisões e pendências novas que ela disser. Antes de perguntar
algo que ela já disse, use o bloco «Do Segundo Cérebro» que vem com as mensagens (ou `decisao` listar)."""


# ------------------------------------------------------------------ helpers do cerebro (os mesmos arquivos do A0)
def mods():
    """cerebro/helpers/modulos.py: pasta, assuntos, decisoes, fios, briefing… (recarregados quando mudam)."""
    caminho = PLUGINS / "cerebro" / "helpers" / "modulos.py"
    antigo = sys.modules.get("cerebro_modulos")
    mtime = caminho.stat().st_mtime
    if antigo is None or (getattr(antigo, "_mtime", None) not in (None, mtime)):
        spec = importlib.util.spec_from_file_location("cerebro_modulos", caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = mtime
        sys.modules["cerebro_modulos"] = m
    return sys.modules["cerebro_modulos"]


def _ponte():
    return sys.modules["agentepessoal_ponte_a0"]


def _convidado() -> str:
    try:
        return _ponte().convidado_da_instancia()
    except Exception:
        return ""


def login_da_conversa(sessao: str) -> str:
    """O login quando a sessão é uma conversa de alguém pelo celular (tg-<login>, tgp<n>-<login>, tg-<login>-<n>);
    "" para rotina, subagente, teste do operador pela API (sessões sem dono caem no Matheus: nunca anotar isso)."""
    sessao = str(sessao or "")
    if not sessao.startswith(("tg-", "tgp")):
        return ""
    try:
        login = _ponte().login_da_sessao(sessao)
    except Exception:
        return ""
    if re.fullmatch(rf"(tg|tgp\d+)-{re.escape(login)}(-\d+)?", sessao):
        return login
    return ""


def com_pasta(login: str) -> bool:
    try:
        return bool(mods().m("pasta").ativa(login))
    except Exception:
        return False


def _curto(t, n: int) -> str:
    t = re.sub(r"\s+", " ", str(t or "")).strip()
    return t if len(t) <= n else t[: n - 1] + "…"


# ------------------------------------------------------------------ escrever: a fila da anotação automática
def pode_anotar(login: str) -> bool:
    """O dono (Pasta) e os logins de teste (decisões e pendências deles). No Hermes de um convidado, ninguém: lá o
    relógio não lê a fila."""
    if not login or _convidado():
        return False
    return login == DONO or login.startswith("teste_")


def _texto(x) -> str:
    if isinstance(x, str):
        return x
    if isinstance(x, list):  # conteúdo multimodal: só o texto
        return "\n".join(str(c.get("text") or "") for c in x if isinstance(c, dict))
    return "" if x is None else str(x)


def entrada_do_turno(sessao: str, login: str, user_message, assistant_response) -> dict | None:
    """O arquivo da fila para este turno, ou None quando não há o que anotar."""
    dele = _texto(user_message).strip()
    relato = _texto(assistant_response).strip()
    de_fora = dele.startswith(NAO_DELE)
    if de_fora:  # vigia de tarefas, operador: não são palavras dele; contam como relato (fatos que movem os assuntos)
        relato = (dele + "\n\n" + relato).strip()
        dele = ""
    if not dele and not de_fora and len(relato) < 200:
        return None
    return {"sessao": sessao, "login": login, "dele": [dele[:DELE_MAX]] if dele else [],
            "relato": relato[-RELATO_MAX:], "origem": f"conversa {sessao}", "em": time.time()}


def enfileirar(dados: dict, entrada: Path | None = None) -> Path:
    entrada = entrada or ENTRADA
    entrada.mkdir(parents=True, exist_ok=True)
    nome = f"{time.strftime('%Y%m%dT%H%M%S')}-{re.sub(r'[^A-Za-z0-9_-]', '', dados['sessao'])[:40]}-{secrets.token_hex(2)}.json"
    tmp = entrada / f".{nome}.tmp"
    tmp.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, entrada / nome)
    return entrada / nome


def anotar(session_id="", user_message=None, assistant_response=None, **kw):
    """Gancho `post_llm_call` (uma vez por turno, depois da resposta): o turno vai à fila do Segundo Cérebro."""
    try:
        sessao = str(session_id or "")
        login = login_da_conversa(sessao)
        if not pode_anotar(login):
            return None
        dados = entrada_do_turno(sessao, login, user_message, assistant_response)
        if dados:
            enfileirar(dados)
    except Exception as exc:  # nunca atrapalha a conversa; o próximo turno tenta de novo
        log.warning("cerebro: turno não foi para a fila: %s: %s", type(exc).__name__, exc)
    return None


# ------------------------------------------------------------------ ler: o que da Pasta ainda não está na conversa
def ja_na_conversa(conversation_history) -> str:
    """O texto que esta conversa já mandou ao modelo (mensagens dele com o que foi injetado nelas e os resumos)."""
    partes = []
    for m in conversation_history or []:
        if not isinstance(m, dict):
            continue
        for chave in ("api_content", "content"):
            v = m.get(chave)
            if isinstance(v, str) and v:
                partes.append(v)
            elif isinstance(v, list):
                partes.append(_texto(v))
    return "\n".join(partes)


def _novas(linhas: list, ja: str) -> list:
    return [x for x in linhas if x and x not in ja]


def _tarefas_abertas(login: str) -> list:
    t = sys.modules.get("agentepessoal_tarefas")
    if t is None:
        return []
    base = t.RAIZ / login
    vivas = []
    for arq in sorted(base.glob("*/plano.json"), reverse=True)[:30] if base.is_dir() else []:
        try:
            plano = json.loads(arq.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if plano.get("estado") == "aberta":
            vivas.append(plano)
    return vivas


def _relevantes_outro(m, login: str, texto: str, limite: int = 5) -> list:
    """Sem Pasta (teste_*): as decisões e pendências DESTA pessoa ligadas ao que ela escreveu (palavras em comum)."""
    p = m.m("pasta")
    termos = [t for t in p._termos(texto)[0] if len(t) > 2]
    if not termos:
        return []
    precisa = max(1, (len(termos) + 2) // 3)
    linhas = []
    for d in m.m("decisoes").ativas(login):
        alvo = p.slug(" ".join([str(d.get("tema")), str(d.get("valor")), str(d.get("citacao") or "")]), 10 ** 5)
        if sum(p._tem(t, alvo) for t in termos) >= precisa:
            linhas.append(f"- decisão #{d.get('id')} {d.get('tema')}: {_curto(d.get('valor'), 240)}")
    for f in m.m("fios").abertos(login, 40):
        alvo = p.slug(" ".join([str(f.get("titulo")), str(f.get("detalhe") or "")]), 10 ** 5)
        if sum(p._tem(t, alvo) for t in termos) >= precisa:
            linhas.append(f"- pendência {f.get('id')}: {_curto(f.get('titulo'), 160)}")
    return linhas[:limite]


def bloco(login: str, texto: str, ja: str) -> str:
    """O que vai com a mensagem: só o que a conversa ainda não tem."""
    m = mods()
    dono = com_pasta(login)
    partes = []
    if MARCA not in ja:
        partes.append(REGRAS_DONO if dono else REGRAS_OUTRO)
    if dono:
        a = m.m("assuntos")
        linhas = _novas(["- " + a.linha(x) for x in a.abertos(ASSUNTOS_PAINEL)], ja)
        if linhas:
            partes.append("Assuntos em andamento (onde pararam agora):\n" + "\n".join(linhas))
        for plano in _tarefas_abertas(login):
            ref = str(plano.get("assunto") or "")
            achado = a.achar(a.todos(), ref) if ref else None
            if not achado:
                continue
            hist = [h.get("nota") for h in (achado.get("historico") or [])[-5:] if h.get("nota")]
            linhas = _novas([f"- {_curto(h, 300)}" for h in hist], ja)
            if linhas:
                partes.append(f"Tarefa longa {plano['id']} «{_curto(plano.get('titulo'), 80)}» — assunto [{achado['id']}], "
                              "o que já se sabe (mais novo por último):\n" + "\n".join(linhas))
        try:
            rel = m.m("briefing").relevantes(m, texto, limite=5)
        except Exception:
            rel = ""
        abertos = tuple(f"- [[Assuntos/{x['id']}-" for x in a.abertos(ASSUNTOS_PAINEL))  # já vão no painel acima
        linhas = _novas([x for x in rel.splitlines()[1:] if not x.startswith(abertos)], ja)
        if linhas:
            partes.append(rel.splitlines()[0] + "\n" + "\n".join(linhas))
    else:
        linhas = _novas(_relevantes_outro(m, login, texto), ja)
        if linhas:
            partes.append("Registrado antes, ligado ao que a pessoa acabou de escrever:\n" + "\n".join(linhas))
    if MARCA not in ja:
        fios = m.m("fios")
        pend = _novas([f"- {fios.linha_curta(f)}" for f in fios.abertos(login, 8)], ja)
        if pend:
            partes.append("Pendências dele(a) em aberto:\n" + "\n".join(pend))
    if not partes:
        return ""
    texto_bloco = "## Do Segundo Cérebro (o que ainda não estava nesta conversa)\n" + "\n\n".join(partes)
    return texto_bloco if len(texto_bloco) <= BLOCO_MAX else texto_bloco[:BLOCO_MAX] + "\n…(cortado: `cerebro` consultar)"


def contexto(session_id="", task_id="", user_message=None, conversation_history=None, **kw):
    """Gancho `pre_llm_call` (todo turno)."""
    try:
        sessao = str(session_id or task_id or "")
        login = login_da_conversa(sessao)
        if not login:
            return None
        texto = bloco(login, _texto(user_message), ja_na_conversa(conversation_history))
        return {"context": texto} if texto else None
    except Exception as exc:  # o turno segue sem o bloco
        log.warning("cerebro: bloco do turno falhou: %s: %s", type(exc).__name__, exc)
        return None


# ------------------------------------------------------------------ tarefas longas -> o assunto ligado
def assunto_da_tarefa(plano: dict, ref: str = "") -> str:
    """O id do assunto ligado a uma tarefa nova: o `ref` dado (se existe) ou um assunto aberto com o título da tarefa
    (o mesmo título reaproveita o que já existe). "" sem Pasta (teste_*, convidado)."""
    if not com_pasta(plano.get("login", "")):
        return ""
    a = mods().m("assuntos")
    texto = f"Tarefa longa {plano['id']} aberta com {len(plano.get('passos') or [])} passos."
    if ref:
        achado = a.achar(a.todos(), str(ref).strip())
        if achado:
            a.atualizar(achado["id"], onde_parou=texto, por=f"tarefa {plano['id']}")
            return achado["id"]
    area = mods().m("fios").area_de(plano.get("titulo", ""), plano.get("pedido", ""))[0]
    novo = a.registrar(plano.get("titulo") or plano["id"], onde_parou=texto, area=area, origem=f"tarefa {plano['id']}",
                       por=f"tarefa {plano['id']}")
    return novo["id"]


ROTULO = {"feito": "feito", "falhou": "não deu", "esperando_matheus": "esperando ele"}


def onde_parou(plano: dict, passo: dict) -> str:
    feitos = sum(1 for x in plano["passos"] if x["estado"] == "feito")
    o_que = passo.get("_resumo") or passo.get("erro") or passo.get("pergunta") or ""
    prox = next((x for x in plano["passos"] if x["estado"] in ("falta", "fazendo")), None)
    return (f"Tarefa {plano['id']}: {feitos}/{len(plano['passos'])} passos feitos. Passo {passo['n']} ({_curto(passo['titulo'], 60)}) "
            f"{ROTULO.get(passo['estado'], passo['estado'])}: {_curto(o_que, 330)}"
            + (f" Próximo: passo {prox['n']} ({_curto(prox['titulo'], 60)})." if prox else ""))


def passo_da_tarefa(plano: dict, passo: dict) -> str:
    """Um passo terminou (feito, não deu, esperando ele): o onde parou do assunto ligado muda (fica no histórico)."""
    ref = str(plano.get("assunto") or "")
    if not ref or not com_pasta(plano.get("login", "")):
        return ""
    texto = onde_parou(plano, passo)
    mods().m("assuntos").atualizar(ref, onde_parou=texto, por=f"tarefa {plano['id']}")
    return texto


def tarefa_concluida(plano: dict, resumo: str) -> str:
    ref = str(plano.get("assunto") or "")
    if not ref or not com_pasta(plano.get("login", "")):
        return ""
    feitos = sum(1 for x in plano["passos"] if x["estado"] == "feito")
    texto = f"Tarefa {plano['id']} entregue ({feitos}/{len(plano['passos'])} passos feitos): {_curto(resumo, 400)}"
    mods().m("assuntos").atualizar(ref, onde_parou=texto, por=f"tarefa {plano['id']}")
    return texto


def registrar(ctx) -> None:
    ctx.register_hook("pre_llm_call", contexto)
    ctx.register_hook("post_llm_call", anotar)
