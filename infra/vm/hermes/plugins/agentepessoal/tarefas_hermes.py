"""Tarefas longas com plano em disco e retomada sozinha (Matheus, 23/10: "Pode fazer e testar").

Um pedido longo (muitos passos, muito tempo, vários módulos ou sites; do celular ou de uma rotina) vira uma pasta da
pessoa: /a0/usr/tarefas/<login>/<id>/plano.json (o pedido palavra por palavra, os passos, o estado de cada um,
horários, tentativas) e resultado.md (o resultado de cada passo, acrescentado quando ele fica feito). Gravação atômica
(arquivo temporário + os.replace) sob trava de arquivo, como os helpers dos plugins.

- Ferramentas: tarefa_iniciar, tarefa_passo, tarefa_status, tarefa_concluir. Cada pessoa só vê as dela (o login vem
  da sessão; o convidado tem o /a0/usr dele, no Hermes dele: nunca vê as do Matheus).
- Estado de passo só muda pela tabela TRANSICOES; "feito" é final (passo feito nunca se refaz).
- Ação de fora (mandar mensagem, criar conta, postar, pagar, e-mail): antes, "vou fazer X" no passo (`acao`); depois,
  "feito" com `prova`. Numa retomada, uma ação marcada e não confirmada tem de ser CONFERIDA no próprio sistema antes
  de refazer (23/10: o Hermes se recusou a refazer um cadastro com medo de duplicar; agora ele sabe o que já fez).
- Passo que precisa do Matheus (captcha, código, decisão): esperando_matheus; a pergunta vai uma vez ao celular dele e
  os passos que não dependem dele seguem.
- O vigia (relógio, um por container: o do Matheus e o de cada convidado, cada um nos dados dele): tarefa aberta, com
  passo pendente pronto e sem nada rodando na sessão dela (Hermes reiniciado, VM caída, limite de uso, tempo esgotado,
  run parado) ganha um pedido NA SESSÃO dela pela ponte ("retome a tarefa <id> do próximo passo pendente"), com espera
  crescente (BACKOFF) e no máximo MAX_RETOMADAS sem progresso; aí avisa a pessoa uma vez.
- Sessão "viva": ganchos do Hermes (pre_llm_call no início do turno, pre_api_request e as ferramentas no meio,
  on_session_end no fim) gravam um batimento por sessão com o processo (pid + início); processo morto (o container
  reiniciou), turno terminado ou sem sinal há muito = parada.
- Entrega só no fim: tarefa_concluir compila o resumo e manda UMA mensagem com o resultado.md inteiro anexado (pela
  ponte, ao celular da pessoa; teste_* vai à caixa dos testes). Se a ponte falhar, o vigia entrega depois.
"""
from __future__ import annotations

import asyncio
import contextlib
import fcntl
import importlib.util
import json
import logging
import os
import re
import secrets
import sys
import time
from pathlib import Path

RAIZ = Path("/a0/usr/tarefas")
VIVAS = Path("/opt/data/agentepessoal/tarefas_vivas")
PLUGINS = Path("/a0/usr/plugins")
log = logging.getLogger("agentepessoal.tarefas")

ESTADOS = ("falta", "fazendo", "feito", "esperando_matheus", "falhou")
TRANSICOES = {
    "falta": {"fazendo", "feito", "esperando_matheus", "falhou"},
    "fazendo": {"fazendo", "feito", "esperando_matheus", "falhou", "falta"},
    "esperando_matheus": {"falta", "fazendo", "feito", "falhou", "esperando_matheus"},
    "falhou": {"falta", "fazendo", "feito", "esperando_matheus"},
    "feito": set(),  # feito é feito: nunca se refaz (precisa de mais? um passo novo)
}
MAX_TENTATIVAS = 3          # vezes que um passo pode começar (cada "fazendo"); depois o vigia não o retoma
ESPERA_OCIOSA = 120         # s parada antes da primeira retomada (o Hermes subindo, a ponte notando o run sumido)
BACKOFF = (120, 300, 900, 1800, 3600, 7200)  # s entre retomadas sem progresso (limite de uso pode durar horas)
MAX_RETOMADAS = len(BACKOFF)
SEM_SINAL = 20 * 60         # turno sem batimento (fora de ferramenta) há mais que isso = parado
FERRAMENTA_MAX = 7 * 3600   # uma ferramenta (ou o ok pelo celular dentro dela) pode demorar até isso
ESPERA_SUBIDA = 90         # s depois que o plugin carregou: o API server do Hermes ainda está subindo (23/10, ao vivo:
                           # a 1ª retomada depois da queda da VM saiu antes dele ouvir e se perdeu)
_CARREGADO = time.time()
ENTREGA_MAX = 6             # tentativas do vigia de entregar o resultado quando a ponte falhou
RESULTADO_PASSO_MAX = 60000
STATUS_RESULTADO_MAX = 9000
ROTINA = re.compile(r"^cron_[A-Za-z0-9]+_\d{8}_\d{6}$")
_LOGIN = re.compile(r"^[a-z0-9_-]{1,32}$")
_ID = re.compile(r"^\d{4}-\d{4}-[0-9a-f]{4}$")

AVISO_RETOMAR = (
    "[Aviso automático do vigia de tarefas: a tarefa longa {id} («{titulo}») parou no meio ({motivo}) e não terminou. "
    "Retome a tarefa {id} do próximo passo pendente: chame tarefa_status com id \"{id}\" e siga o plano. Não refaça "
    "passo feito; ação de fora marcada e não confirmada: confira no próprio sistema antes de refazer. Não escreva à "
    "pessoa no meio; no fim, tarefa_concluir (ele recebe uma mensagem só, com o arquivo). Se parar sem terminar, "
    "responda só: ok]")
AVISO_ENTREGAR = (
    "[Aviso automático do vigia de tarefas: todos os passos da tarefa {id} («{titulo}») estão resolvidos, mas ela não "
    "foi entregue. Chame tarefa_status com id \"{id}\", escreva o resumo e chame tarefa_concluir. Depois responda só: ok]")


# ------------------------------------------------------------------ disco
def _limpo_login(login: str) -> str:
    login = str(login or "").strip().lower()
    if not _LOGIN.match(login):
        raise ValueError("login inválido")
    return login


def pasta(login: str, tid: str, raiz: Path | None = None) -> Path:
    if not _ID.match(str(tid or "")):
        raise ValueError(f"id de tarefa inválido: {tid!r}")
    return (raiz or RAIZ) / _limpo_login(login) / tid


@contextlib.contextmanager
def trava(p: Path):
    p.mkdir(parents=True, exist_ok=True)
    with open(p / ".trava", "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _gravar_atomico(arq: Path, texto: str) -> None:
    tmp = arq.with_name(f".{arq.name}.{os.getpid()}.{secrets.token_hex(3)}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(texto)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, arq)


def ler(p: Path) -> dict:
    return json.loads((p / "plano.json").read_text(encoding="utf-8"))


def gravar(p: Path, plano: dict) -> None:
    _gravar_atomico(p / "plano.json", json.dumps(plano, ensure_ascii=False, indent=1))


def _hora(t: float | None) -> str:
    return time.strftime("%d/%m %H:%M", time.localtime(t)) if t else ""


def _diario(plano: dict, texto: str, agora: float) -> None:
    plano.setdefault("diario", []).append({"em": agora, "o_que": texto[:300]})
    plano["diario"] = plano["diario"][-200:]


def novo_id(agora: float) -> str:
    return time.strftime("%m%d-%H%M", time.localtime(agora)) + "-" + secrets.token_hex(2)


def _passos_de(lista, inicio: int = 1, sequencial: bool = True) -> list:
    """Passos novos: texto ("Pesquisar X") ou {"titulo", "depende_de": [n]}; sem depende_de, depende do anterior."""
    passos = []
    for i, item in enumerate(lista or [], start=inicio):
        if isinstance(item, dict):
            titulo = str(item.get("titulo") or item.get("passo") or "").strip()
            dep = item.get("depende_de")
        else:
            titulo, dep = str(item or "").strip(), None
        if not titulo:
            continue
        if dep is None:
            dep = [i - 1] if sequencial and i > 1 else []
        dep = sorted({int(d) for d in (dep if isinstance(dep, list) else [dep]) if str(d).strip().lstrip("-").isdigit()
                      and 0 < int(d) < i})
        passos.append({"n": i, "titulo": titulo[:300], "estado": "falta", "depende_de": dep, "tentativas": 0,
                       "inicio": None, "fim": None})
    return passos


def sessao_alvo(login: str, sessao: str, mapa: dict | None = None) -> str:
    """Onde a retomada entra: a própria conversa da pessoa (tg-/tgp<n>-<login>) ou, numa rotina/sessão sem dono, a
    conversa principal dela (a do mapa da ponte; senão tg-<login>)."""
    sessao = str(sessao or "")
    conversa = re.compile(rf"^(tg|tgp\d+)-{re.escape(login)}(-\d{{14}})?$")
    if conversa.match(sessao):
        return sessao
    if mapa is None:
        try:
            ponte = sys.modules.get("agentepessoal_ponte_a0")
            mapa = json.loads(ponte.SESSOES.read_text(encoding="utf-8")) if ponte is not None else {}
        except (OSError, ValueError, AttributeError):
            mapa = {}
    atual = str((mapa or {}).get(f"atual:tg-{login}") or "")
    return atual if conversa.match(atual) else f"tg-{login}"


def criar(login: str, titulo: str, pedido: str, passos: list, sessao: str, raiz: Path | None = None,
          agora: float | None = None, mapa: dict | None = None) -> dict:
    agora = agora or time.time()
    login = _limpo_login(login)
    lista = _passos_de(passos)
    if len(lista) < 2:
        raise ValueError("uma tarefa longa tem pelo menos 2 passos")
    if len(lista) > 60:
        raise ValueError("passos demais (máximo 60): junte os parecidos")
    tid = novo_id(agora)
    while (raiz or RAIZ).joinpath(login, tid).exists():
        tid = novo_id(agora)
    p = pasta(login, tid, raiz)
    plano = {
        "id": tid, "login": login, "titulo": str(titulo or "").strip()[:200] or lista[0]["titulo"],
        "pedido": str(pedido or ""), "origem": "rotina" if ROTINA.match(sessao or "") else "conversa",
        "sessao": sessao, "sessao_atual": sessao, "sessao_alvo": sessao_alvo(login, sessao, mapa),
        "criada_em": agora, "atualizada_em": agora, "estado": "aberta", "passos": lista,
        "retomadas": [], "sem_progresso": 0, "travada_em": None, "entrega": None,
    }
    with trava(p):
        _diario(plano, "criada", agora)
        gravar(p, plano)
        _gravar_atomico(p / "resultado.md", f"# {plano['titulo']}\n\nPedido (como veio): {plano['pedido']}\n\n"
                                            f"Começada em {_hora(agora)} · tarefa {tid}\n")
    _mostrar(plano)
    return plano


# ------------------------------------------------------------------ situação
def _passo(plano: dict, n) -> dict:
    try:
        n = int(n)
    except (TypeError, ValueError):
        raise ValueError("diga o número do passo") from None
    for p in plano["passos"]:
        if p["n"] == n:
            return p
    raise ValueError(f"a tarefa não tem o passo {n} (tem 1 a {len(plano['passos'])})")


def terminal(p: dict) -> bool:
    return p["estado"] in ("feito", "falhou")


def pronto(plano: dict, p: dict) -> bool:
    """O vigia pode retomar por este passo: pendente, com tentativa sobrando, e o que ele espera já resolvido."""
    if p["estado"] not in ("falta", "fazendo") or p.get("tentativas", 0) >= MAX_TENTATIVAS:
        return False
    por_n = {x["n"]: x for x in plano["passos"]}
    return all(terminal(por_n[d]) for d in p.get("depende_de") or [] if d in por_n)


def situacao(plano: dict, pausada: bool = False) -> str:
    """concluida | pausada | travada | pronta (há passo para fazer) | entregar (tudo resolvido, falta o resumo) |
    esperando (só o que depende do Matheus) | sem_saida (passos esgotaram as tentativas)."""
    if plano.get("estado") in ("concluida", "cancelada"):
        return "concluida"
    if pausada:
        return "pausada"
    if plano.get("travada_em"):
        return "travada"
    if any(pronto(plano, p) for p in plano["passos"]):
        return "pronta"
    if all(terminal(p) for p in plano["passos"]):
        return "entregar"
    if any(p["estado"] == "esperando_matheus" for p in plano["passos"]):
        return "esperando"
    return "sem_saida"


def proximo(plano: dict) -> dict | None:
    for p in plano["passos"]:
        if pronto(plano, p):
            return p
    return None


# ------------------------------------------------------------------ envio ao celular
def _ponte_whatsapp():
    nome, caminho = "whatsapp_ponte", PLUGINS / "whatsapp" / "helpers" / "ponte.py"
    antigo, mtime = sys.modules.get(nome), caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = mtime
        sys.modules[nome] = m
    return sys.modules[nome]


def enviar(login: str, texto: str, arquivo: str = "", legenda: str = "") -> str:
    """'' quando foi; senão o motivo. Pela ponte do celular (teste_*: a caixa dos testes, nada sai)."""
    return _ponte_whatsapp().enviar(login, texto, arquivo, legenda, None, "resposta", True)


def andamento(login: str, texto: str, fim: bool = False) -> str:
    """A mensagem única de andamento da pessoa no Telegram (a ponte edita a aberta; `fim` fecha). Nunca impede a
    tarefa: '' quando foi, senão o motivo (24/10, Matheus: "Precisa aparecer no telegram" — uma tarefa aberta por
    fora do celular, pelo operador ou pela rotina, não mostrava nada)."""
    try:
        return _ponte_whatsapp().andamento(login, texto, fim) or ""
    except Exception as exc:  # noqa: BLE001
        log.warning("tarefas: andamento não foi: %s: %s", type(exc).__name__, exc)
        return str(exc)[:200]


def texto_andamento(plano: dict) -> str:
    total = len(plano["passos"])
    feitos = sum(1 for x in plano["passos"] if x["estado"] == "feito")
    atual = next((x for x in plano["passos"] if x["estado"] == "fazendo"), None) or proximo(plano)
    linhas = [f"🔄 {plano['titulo']}", f"{feitos}/{total} passos feitos"]
    if atual:
        linhas.append(f"Agora: passo {atual['n']}/{total} — {atual['titulo']}")
    falhos = sum(1 for x in plano["passos"] if x["estado"] == "falhou")
    esperando = [x for x in plano["passos"] if x["estado"] == "esperando_matheus"]
    if falhos:
        linhas.append(f"{falhos} não deu (vai no relatório)")
    if esperando:
        linhas.append("Esperando você no passo " + ", ".join(str(x["n"]) for x in esperando))
    linhas.append("No fim chega uma mensagem só com o resumo e o arquivo completo.")
    return "\n".join(linhas)


def _mostrar(plano: dict) -> None:
    if plano.get("estado") == "aberta":
        andamento(plano["login"], texto_andamento(plano))


# ------------------------------------------------------------------ mudanças (as ferramentas)
def _pausada(p: Path) -> bool:
    return (p / "pausada").exists()


def mudar_passo(login: str, tid: str, n, estado: str, resultado: str = "", acao: str = "", prova: str = "",
                pergunta: str = "", erro: str = "", conferido: str = "", novos_passos: list | None = None,
                sessao: str = "", raiz: Path | None = None, agora: float | None = None, enviar_fn=None) -> str:
    agora = agora or time.time()
    p = pasta(login, tid, raiz)
    if not (p / "plano.json").exists():
        return f"NÃO FEITO: não achei a tarefa {tid} desta pessoa (veja tarefa_status sem id)."
    avisar = None
    with trava(p):
        plano = ler(p)
        if plano.get("estado") != "aberta":
            return f"NÃO FEITO: a tarefa {tid} já está {plano.get('estado')}."
        extra = []
        if novos_passos:
            novos = _passos_de(novos_passos, inicio=len(plano["passos"]) + 1)
            plano["passos"].extend(novos)
            extra.append(f"Passos novos: {', '.join(str(x['n']) for x in novos)}.")
            _diario(plano, f"passos novos {[x['n'] for x in novos]}", agora)
        if n in (None, "", 0, "0") and novos_passos:
            estado = ""
        if estado:
            if estado not in ESTADOS:
                return f"NÃO FEITO: estado deve ser um de {', '.join(ESTADOS)}."
            try:
                passo = _passo(plano, n)
            except ValueError as exc:
                return f"NÃO FEITO: {exc}"
            antes = passo["estado"]
            if estado not in TRANSICOES[antes]:
                return (f"NÃO FEITO: o passo {passo['n']} está {antes} e não pode ir para {estado}"
                        + (" (passo feito não se refaz; se precisa de mais, acrescente um passo novo em novos_passos)."
                           if antes == "feito" else "."))
            ac = passo.get("acao") or {}
            if estado == "fazendo":
                if ac.get("estado") == "vou_fazer" and acao and not conferido.strip():
                    return (f"NÃO FEITO: numa tentativa anterior deste passo você marcou a ação de fora «{ac['descricao']}» "
                            f"({_hora(ac.get('em'))}) e ela não foi confirmada. Antes de refazer, confira no próprio "
                            "sistema se ela já aconteceu (ex.: a conta já existe, a mensagem já está lá). Já aconteceu: "
                            "marque o passo feito com a prova. Não aconteceu: chame de novo com `conferido` dizendo o "
                            "que você viu.")
                passo["tentativas"] = int(passo.get("tentativas") or 0) + 1
                passo["inicio"] = passo.get("inicio") or agora
                if passo["tentativas"] > MAX_TENTATIVAS:
                    extra.append(f"Atenção: esta é a tentativa {passo['tentativas']} deste passo; se não der agora, "
                                 "marque falhou com o motivo e siga com os outros.")
                if acao.strip():
                    passo["acao"] = {"descricao": acao.strip()[:500], "estado": "vou_fazer", "em": agora,
                                     **({"conferido": conferido.strip()[:500]} if conferido.strip() else {})}
            if estado == "feito":
                if ac.get("estado") == "vou_fazer" and not prova.strip():
                    return (f"NÃO FEITO: este passo tem a ação de fora «{ac['descricao']}». Diga em `prova` como você "
                            "conferiu que ela aconteceu (id, link, o que leu de volta no sistema).")
                if ac and prova.strip():
                    ac.update({"estado": "feita", "prova": prova.strip()[:1000], "feita_em": agora})
                elif acao.strip() and prova.strip():
                    passo["acao"] = {"descricao": acao.strip()[:500], "estado": "feita", "em": agora,
                                     "prova": prova.strip()[:1000], "feita_em": agora}
                passo["fim"] = agora
                texto = str(resultado or "").strip() or "(sem texto)"
                if len(texto) > RESULTADO_PASSO_MAX:
                    texto = texto[:RESULTADO_PASSO_MAX] + "\n[…cortado]"
                prova_md = f"\n\nProva: {passo['acao']['prova']}" if (passo.get("acao") or {}).get("prova") else ""
                atual = (p / "resultado.md").read_text(encoding="utf-8") if (p / "resultado.md").exists() else ""
                _gravar_atomico(p / "resultado.md", atual.rstrip("\n") + f"\n\n## Passo {passo['n']} — {passo['titulo']}\n"
                                f"_feito em {_hora(agora)}_\n\n{texto}{prova_md}\n")
            if estado == "falhou":
                passo["erro"] = (erro or resultado or "sem motivo").strip()[:1000]
                passo["fim"] = agora
                atual = (p / "resultado.md").read_text(encoding="utf-8") if (p / "resultado.md").exists() else ""
                _gravar_atomico(p / "resultado.md", atual.rstrip("\n") + f"\n\n## Passo {passo['n']} — {passo['titulo']}\n"
                                f"_não deu ({_hora(agora)})_: {passo['erro']}\n")
            if estado == "esperando_matheus":
                pergunta = " ".join(str(pergunta or "").split())[:900]
                passo["esperando_desde"] = passo.get("esperando_desde") if antes == "esperando_matheus" else agora
                if pergunta and pergunta != passo.get("pergunta"):
                    passo["pergunta"] = pergunta
                    avisar = (f"❓ *{plano['titulo']}* — preciso de você no passo {passo['n']} ({passo['titulo']}):\n\n"
                              f"{pergunta}\n\nOs outros passos seguem enquanto isso.")
            elif antes == "esperando_matheus":
                passo.pop("esperando_desde", None)
            if estado in ("feito", "falhou", "esperando_matheus"):
                plano["sem_progresso"] = 0  # o passo andou: as retomadas voltam a ter fôlego
            passo["estado"] = estado
            _diario(plano, f"passo {passo['n']}: {antes} -> {estado}", agora)
        plano["atualizada_em"] = agora
        plano["travada_em"] = None
        if sessao:
            plano["sessao_atual"] = sessao
        (p / "pausada").unlink(missing_ok=True)  # mexeu na tarefa: ela voltou a andar
        gravar(p, plano)
    if estado or novos_passos:
        _mostrar(plano)
    if avisar:
        erro_envio = (enviar_fn or enviar)(plano["login"], avisar)
        with trava(p):
            plano = ler(p)
            passo = _passo(plano, n)
            passo["avisado_em"] = agora if not erro_envio else None
            gravar(p, plano)
        if erro_envio:
            extra.append(f"A pergunta NÃO chegou ao celular ({str(erro_envio)[:120]}): diga a ele na sua resposta.")
        else:
            extra.append("Mandei a pergunta a ele (uma vez). Siga com os passos que não dependem disto; não repita a "
                         "pergunta na resposta. Quando ele responder, mude este passo e siga.")
    prox = proximo(plano)
    sit = situacao(plano)
    fim = {"pronta": f"Próximo: passo {prox['n']} ({prox['titulo']})." if prox else "",
           "entregar": "Todos os passos resolvidos: escreva o resumo e chame tarefa_concluir.",
           "esperando": "Só falta o que depende do Matheus: termine a resposta com «ok» e espere ele.",
           "sem_saida": "Passos esgotaram as tentativas: marque falhou (com o motivo) ou conclua parcial."}.get(sit, "")
    return " ".join(x for x in ["Anotado.", *extra, fim] if x)


def status(login: str, tid: str = "", raiz: Path | None = None) -> str:
    login = _limpo_login(login)
    base = (raiz or RAIZ) / login
    if not tid:
        linhas = []
        for arq in sorted(base.glob("*/plano.json"), reverse=True)[:40]:
            try:
                plano = json.loads(arq.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            sit = situacao(plano, _pausada(arq.parent))
            if sit == "concluida" and len(linhas) >= 5:
                continue
            feitos = sum(1 for x in plano["passos"] if x["estado"] == "feito")
            linhas.append(f"- {plano['id']} «{plano['titulo']}»: {sit}, {feitos}/{len(plano['passos'])} feitos "
                          f"(atualizada {_hora(plano.get('atualizada_em'))})")
        return "Tarefas longas desta pessoa:\n" + "\n".join(linhas) if linhas else "Nenhuma tarefa longa desta pessoa."
    p = pasta(login, tid, raiz)
    if not (p / "plano.json").exists():
        return f"Não achei a tarefa {tid} desta pessoa (tarefa_status sem id lista as dela)."
    plano = ler(p)
    sit = situacao(plano, _pausada(p))
    linhas = [f"Tarefa {plano['id']} «{plano['titulo']}» — {sit} (origem: {plano.get('origem')}; pasta {p})",
              f"Pedido (como veio): {plano['pedido']}", "Passos:"]
    for x in plano["passos"]:
        info = x["estado"] + (f", tentativa {x['tentativas']}" if x.get("tentativas") and x["estado"] != "feito" else "")
        dep = f" (depois de {', '.join(map(str, x['depende_de']))})" if x.get("depende_de") else ""
        linha = f" {x['n']}. [{info}] {x['titulo']}{dep}"
        if x.get("fim") and x["estado"] == "feito":
            linha += f" — {_hora(x['fim'])}"
        ac = x.get("acao") or {}
        if ac.get("estado") == "vou_fazer":
            linha += (f"\n    ⚠️ ação de fora «{ac['descricao']}» marcada em {_hora(ac.get('em'))} e NÃO confirmada: "
                      "confira no próprio sistema se já aconteceu ANTES de refazer (aconteceu: marque feito com a prova).")
        elif ac.get("estado") == "feita":
            linha += f"\n    ação de fora feita: «{ac['descricao']}» (prova: {ac.get('prova', '')[:200]})"
        if x["estado"] == "esperando_matheus":
            linha += f"\n    esperando o Matheus: {x.get('pergunta') or '(sem pergunta registrada)'}"
        if x["estado"] == "falhou":
            linha += f"\n    não deu: {x.get('erro', '')[:300]}"
        linhas.append(linha)
    prox = proximo(plano)
    if sit == "pausada":
        linhas.append("Pausada pelo /parar da pessoa: só retome se ela pediu (\"continua\").")
    if sit == "travada":
        linhas.append("Travada: o vigia desistiu de retomar sozinho; siga só se a pessoa pediu.")
    linhas.append({"pronta": f"Próximo passo: {prox['n']} ({prox['titulo']})." if prox else "",
                   "entregar": "Todos os passos resolvidos: escreva o resumo e chame tarefa_concluir.",
                   "esperando": "Só falta o que depende do Matheus.",
                   "sem_saida": "Os passos pendentes esgotaram as tentativas: marque falhou ou conclua parcial.",
                   "concluida": f"Concluída{' e entregue' if (plano.get('entrega') or {}).get('estado') == 'entregue' else ''}.",
                   }.get(sit, ""))
    resultado = (p / "resultado.md").read_text(encoding="utf-8") if (p / "resultado.md").exists() else ""
    if len(resultado) > STATUS_RESULTADO_MAX:
        resultado = (f"[o começo está em {p / 'resultado.md'}; leia com read_file se precisar]\n…"
                     + resultado[-STATUS_RESULTADO_MAX:])
    linhas.append("\nResultados até aqui (resultado.md):\n" + resultado)
    return "\n".join(x for x in linhas if x != "")


def _nome_arquivo(plano: dict) -> str:
    import unicodedata

    sem_acento = unicodedata.normalize("NFKD", plano["titulo"].lower()).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", sem_acento).strip("-")[:40].strip("-")
    return f"{slug or 'tarefa'}-{plano['id']}.md"


def entregar(p: Path, enviar_fn=None, agora: float | None = None) -> str:
    """Manda o resumo e o arquivo final (uma vez). '' quando foi; senão o motivo (fica pendente para o vigia)."""
    agora = agora or time.time()
    with trava(p):
        plano = ler(p)
        ent = plano.get("entrega") or {}
        if ent.get("estado") == "entregue":
            return ""
        ent["tentativas"] = int(ent.get("tentativas") or 0) + 1
        ent["ultima"] = agora
        plano["entrega"] = ent
        gravar(p, plano)
    arquivo = p / ent["arquivo"]
    resumo = ent.get("resumo") or ""
    feitos = sum(1 for x in plano["passos"] if x["estado"] == "feito")
    cab = f"✅ *{plano['titulo']}*" + ("" if feitos == len(plano["passos"]) else f" ({feitos}/{len(plano['passos'])} passos)")
    corpo = f"{cab}\n\n{resumo}".strip()
    if len(corpo) <= 1000:  # cabe como legenda: uma mensagem só, com o arquivo
        erro = (enviar_fn or enviar)(plano["login"], "", str(arquivo), corpo)
    else:
        erro = (enviar_fn or enviar)(plano["login"], corpo, str(arquivo), "Resultado completo")
    with trava(p):
        plano = ler(p)
        plano["entrega"]["estado"] = "entregue" if not erro else "pendente"
        plano["entrega"]["erro"] = str(erro or "")[:300]
        if not erro:
            plano["entrega"]["entregue_em"] = agora
        _diario(plano, "entregue" if not erro else f"entrega falhou: {str(erro)[:120]}", agora)
        gravar(p, plano)
    return str(erro or "")


def concluir(login: str, tid: str, resumo: str, parcial: bool = False, sessao: str = "", raiz: Path | None = None,
             agora: float | None = None, enviar_fn=None) -> str:
    agora = agora or time.time()
    p = pasta(login, tid, raiz)
    if not (p / "plano.json").exists():
        return f"NÃO FEITO: não achei a tarefa {tid} desta pessoa."
    resumo = str(resumo or "").strip()
    if not resumo:
        return "NÃO FEITO: escreva em `resumo` o resultado em poucas linhas (o que ele precisa saber/decidir)."
    with trava(p):
        plano = ler(p)
        if plano.get("estado") == "concluida":
            ja = (plano.get("entrega") or {}).get("estado") == "entregue"
            return ("Já estava concluída e entregue. Responda só: ok" if ja else
                    "Já estava concluída; a entrega está pendente e o vigia tenta de novo. Responda só: ok")
        abertos = [x for x in plano["passos"] if not terminal(x)]
        if abertos and not parcial:
            return ("NÃO FEITO: ainda há passos abertos: " + ", ".join(f"{x['n']} ({x['estado']})" for x in abertos)
                    + ". Faça-os (ou marque falhou com o motivo). Só conclua parcial (parcial=true) se a pessoa pediu "
                    "ou se o que falta depende dela e o resto já vale a entrega.")
        corpo = (p / "resultado.md").read_text(encoding="utf-8") if (p / "resultado.md").exists() else ""
        cab, *secoes = corpo.split("\n## Passo ")
        num = lambda x: int(re.match(r"\d+", x).group()) if re.match(r"\d+", x) else 0  # noqa: E731
        secoes = sorted(secoes, key=num)  # na ordem dos passos (um independente pode ter terminado antes)
        final = cab.rstrip("\n") + f"\n\n## Resumo\n{resumo}\n" + "".join(
            f"\n## Passo {x.rstrip(chr(10))}\n" for x in secoes)
        if abertos:
            final += "\n\n## Ficou faltando\n" + "\n".join(
                f"- Passo {x['n']} — {x['titulo']}: {x['estado']}" + (f" ({x.get('pergunta')})" if x.get("pergunta") else "")
                for x in abertos) + "\n"
        _gravar_atomico(p / "resultado.md", final)
        nome = _nome_arquivo(plano)
        _gravar_atomico(p / nome, final)
        plano.update({"estado": "concluida", "concluida_em": agora, "atualizada_em": agora,
                      "entrega": {"estado": "pendente", "arquivo": nome, "resumo": resumo[:3500], "tentativas": 0}})
        if sessao:
            plano["sessao_atual"] = sessao
        _diario(plano, "concluída" + (" (parcial)" if abertos else ""), agora)
        gravar(p, plano)
    andamento(plano["login"], f"✅ {plano['titulo']}: terminado, mandando o resultado.", fim=True)
    erro = entregar(p, enviar_fn, agora)
    if erro:
        return (f"Concluída, mas a entrega ao celular falhou agora ({erro[:120]}); o vigia tenta de novo sozinho. "
                "Responda só: ok")
    return "Entregue ao celular dele: o resumo e o arquivo com o resultado completo, numa mensagem. Responda só: ok"


# ------------------------------------------------------------------ sessões vivas (ganchos)
def _inicio_processo(pid: int) -> str:
    try:
        dados = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return ""
    return dados.rsplit(")", 1)[-1].split()[19] if ")" in dados else ""


_EU = {"pid": os.getpid(), "inicio": _inicio_processo(os.getpid())}


def _arq_viva(sessao: str, vivas: Path | None = None) -> Path:
    return (vivas or VIVAS) / (re.sub(r"[^A-Za-z0-9_.-]", "_", sessao)[:120] + ".json")


def marcar(sessao: str, vivas: Path | None = None, agora: float | None = None, **campos) -> None:
    if not sessao:
        return
    agora = agora or time.time()
    arq = _arq_viva(sessao, vivas)
    try:
        dados = json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dados = {}
    if _EU["pid"] != os.getpid():  # fork
        _EU.update(pid=os.getpid(), inicio=_inicio_processo(os.getpid()))
    dados.update({"pid": _EU["pid"], "inicio_proc": _EU["inicio"], "batimento": agora, **campos})
    try:
        arq.parent.mkdir(parents=True, exist_ok=True)
        _gravar_atomico(arq, json.dumps(dados))
    except OSError as exc:
        log.warning("tarefas: batimento de %s não gravou: %s", sessao, exc)


def viva(sessao: str, vivas: Path | None = None, agora: float | None = None, inicio_fn=None) -> tuple[bool, str]:
    """(rodando agora?, por que parou). O turno conta como rodando enquanto o processo dele existe, o turno não
    terminou e há sinal recente (uma ferramenta, ou o ok pelo celular dentro dela, pode demorar até FERRAMENTA_MAX)."""
    agora = agora or time.time()
    try:
        d = json.loads(_arq_viva(sessao, vivas).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False, "nada rodando"
    if d.get("fim") and d.get("fim", 0) >= d.get("turno_desde", 0):
        return False, "o pedido terminou sem fechar a tarefa"
    if (inicio_fn or _inicio_processo)(int(d.get("pid") or 0)) != str(d.get("inicio_proc") or "-"):
        return False, "o agente reiniciou no meio"
    limite = FERRAMENTA_MAX if d.get("ferramenta") else SEM_SINAL
    if agora - float(d.get("batimento") or 0) > limite:
        return False, "ficou sem sinal (travado ou limite de uso)"
    return True, ""


def _sessao_kw(kw: dict) -> str:
    return str(kw.get("session_id") or kw.get("task_id") or "")


def gancho_inicio(**kw):
    """pre_llm_call: o turno começou. Também devolve, se houver, o lembrete das tarefas abertas da pessoa."""
    sessao = _sessao_kw(kw)
    marcar(sessao, turno_desde=time.time(), fim=None, ferramenta=None)
    try:
        return lembrete(sessao)
    except Exception as exc:  # o turno segue sem o lembrete
        log.warning("tarefas: lembrete falhou: %s: %s", type(exc).__name__, exc)
        return None


def gancho_api(**kw):
    marcar(_sessao_kw(kw), ferramenta=None)


def gancho_ferramenta(tool_name="", **kw):
    marcar(_sessao_kw(kw), ferramenta=str(tool_name or "?"))


def gancho_ferramenta_fim(**kw):
    marcar(_sessao_kw(kw), ferramenta=None)


def gancho_fim(**kw):
    marcar(_sessao_kw(kw), fim=time.time(), ferramenta=None)


def _login(sessao: str) -> str:
    return sys.modules["agentepessoal_ponte_a0"].login_da_sessao(sessao)


def lembrete(sessao: str, raiz: Path | None = None) -> dict | None:
    """Numa conversa (não rotina), as tarefas abertas da pessoa em uma linha cada: quem responde a uma pergunta de
    tarefa, ou diz "continua", cai no lugar certo."""
    if not sessao or ROTINA.match(sessao):
        return None
    login = _login(sessao)
    base = (raiz or RAIZ) / login
    if not base.is_dir():
        return None
    linhas = []
    for arq in sorted(base.glob("*/plano.json"), reverse=True)[:30]:
        try:
            plano = json.loads(arq.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        sit = situacao(plano, _pausada(arq.parent))
        if sit == "concluida":
            continue
        feitos = sum(1 for x in plano["passos"] if x["estado"] == "feito")
        esp = [x for x in plano["passos"] if x["estado"] == "esperando_matheus"]
        linha = f"- {plano['id']} «{plano['titulo']}»: {sit}, {feitos}/{len(plano['passos'])} feitos"
        if esp:
            linha += "; esperando a pessoa: " + "; ".join(f"passo {x['n']}: {x.get('pergunta') or x['titulo']}" for x in esp)[:400]
        linhas.append(linha)
        if len(linhas) >= 4:
            break
    if not linhas:
        return None
    return {"context": "## Tarefas longas abertas desta pessoa (plano em disco)\n" + "\n".join(linhas) +
            "\nSe a mensagem responde a uma delas ou pede para continuar: tarefa_status com o id e siga o plano "
            "(tarefa_passo para mudar o passo)."}


# ------------------------------------------------------------------ o vigia (relógio)
def _conversa(login: str, texto: str, sessao: str) -> dict:
    return sys.modules["agentepessoal_botoes"].conversa(login, texto, sessao=sessao)


def passo_do_relogio(raiz: Path | None = None, vivas: Path | None = None, agora: float | None = None,
                     conversa_fn=None, enviar_fn=None, inicio_fn=None) -> list:
    """Uma volta do vigia sobre todas as tarefas deste container. Devolve o que fez [(id, ação)] (para os testes)."""
    agora = agora or time.time()
    raiz = raiz or RAIZ
    feito = []
    if not raiz.is_dir() or time.time() - _CARREGADO < ESPERA_SUBIDA:
        return feito
    for arq in sorted(raiz.glob("*/*/plano.json")):
        p = arq.parent
        try:
            feito.extend(_vigiar(p, agora, vivas, conversa_fn or _conversa, enviar_fn, inicio_fn))
        except Exception as exc:  # uma tarefa torta não para as outras
            log.warning("tarefas: vigia em %s: %s: %s", p, type(exc).__name__, exc)
            feito.append((p.name, f"erro: {type(exc).__name__}: {exc}"[:200]))
    _limpar_vivas(vivas, time.time())  # pelo relógio de verdade (o mtime dos arquivos é dele)
    return feito


def _limpar_vivas(vivas: Path | None, agora: float) -> None:
    base = vivas or VIVAS
    if not base.is_dir():
        return
    for arq in base.glob("*.json"):
        try:
            if agora - arq.stat().st_mtime > 3 * 86400:
                arq.unlink()
        except OSError:
            pass


def _vigiar(p: Path, agora: float, vivas, conversa_fn, enviar_fn, inicio_fn) -> list:
    plano = ler(p)
    login = plano["login"]
    if p.parent.name != login:
        return []  # nunca agir por uma pasta que não é da pessoa do plano
    ent = plano.get("entrega") or {}
    if plano.get("estado") == "concluida":
        if ent.get("estado") == "pendente" and int(ent.get("tentativas") or 0) < ENTREGA_MAX and \
                agora - float(ent.get("ultima") or 0) >= BACKOFF[min(int(ent.get("tentativas") or 0), len(BACKOFF) - 1)]:
            erro = entregar(p, enviar_fn, agora)
            return [(plano["id"], "entregue" if not erro else f"entrega falhou: {erro[:80]}")]
        return []
    if plano.get("estado") != "aberta":
        return []
    sit = situacao(plano, _pausada(p))
    if sit in ("pausada", "travada", "esperando", "concluida"):
        return []
    sessoes = [s for s in dict.fromkeys([plano.get("sessao"), plano.get("sessao_atual"), plano.get("sessao_alvo")]) if s]
    motivos = []
    for s in sessoes:
        rodando, motivo = viva(s, vivas, agora, inicio_fn)
        if rodando:
            return []  # algo roda numa sessão dela: espera
        motivos.append(motivo)
    retomadas = plano.get("retomadas") or []
    ultima = max([float(plano.get("atualizada_em") or 0)] + [float(r.get("em") or 0) for r in retomadas[-1:]])
    n = int(plano.get("sem_progresso") or 0)
    if sit == "sem_saida" or n >= MAX_RETOMADAS:
        if agora - ultima < ESPERA_OCIOSA:
            return []
        return [(plano["id"], _travar(p, agora, enviar_fn, "sem_saida" if sit == "sem_saida" else "retomadas"))]
    espera = ESPERA_OCIOSA if n == 0 else BACKOFF[min(n, len(BACKOFF) - 1)]
    if agora - ultima < espera:
        return []
    motivo = next((m for m in motivos if "reiniciou" in m), None) or next((m for m in motivos if m != "nada rodando"), "")
    motivo = motivo or "o pedido parou"
    texto = (AVISO_ENTREGAR if sit == "entregar" else AVISO_RETOMAR).format(id=plano["id"], titulo=plano["titulo"],
                                                                           motivo=motivo)
    with trava(p):
        plano = ler(p)
        plano.setdefault("retomadas", []).append({"em": agora, "motivo": motivo, "sessao": plano.get("sessao_alvo")})
        plano["retomadas"] = plano["retomadas"][-50:]
        plano["sem_progresso"] = int(plano.get("sem_progresso") or 0) + 1
        _diario(plano, f"retomada {plano['sem_progresso']} ({motivo})", agora)
        gravar(p, plano)
    try:
        r = conversa_fn(login, texto, plano.get("sessao_alvo") or f"tg-{login}")
        ok = bool(r.get("ok")) if isinstance(r, dict) else bool(r)
    except Exception as exc:
        ok, r = False, f"{type(exc).__name__}: {exc}"
    if not ok:
        log.warning("tarefas: retomada de %s não saiu: %s", plano["id"], str(r)[:200])
        return [(plano["id"], f"retomada não saiu: {str(r)[:80]}")]
    return [(plano["id"], f"retomada {plano['sem_progresso']}: {motivo}")]


def _travar(p: Path, agora: float, enviar_fn, porque: str) -> str:
    with trava(p):
        plano = ler(p)
        if plano.get("travada_em"):
            return "já travada"
        plano["travada_em"] = agora
        _diario(plano, f"travada ({porque})", agora)
        gravar(p, plano)
    pend = [x for x in plano["passos"] if not terminal(x)]
    onde = f"passo {pend[0]['n']} ({pend[0]['titulo']})" if pend else "a entrega"
    texto = (f"⚠️ *{plano['titulo']}* parou em {onde} e não consegui retomar sozinho "
             f"({int(plano.get('sem_progresso') or 0)} tentativas). O que já fiz está guardado. Diga \"continua\" para "
             "eu tentar de novo, ou me diga o que mudar.")
    erro = (enviar_fn or enviar)(plano["login"], texto)
    return "travada e avisada" if not erro else f"travada; aviso falhou: {erro[:80]}"


def pausar(login: str, raiz: Path | None = None, agora: float | None = None) -> list:
    """O /parar da pessoa: as tarefas abertas dela ficam pausadas (o vigia não retoma). Devolve os títulos."""
    agora = agora or time.time()
    base = (raiz or RAIZ) / _limpo_login(login)
    titulos = []
    for arq in sorted(base.glob("*/plano.json")):
        try:
            plano = json.loads(arq.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if plano.get("estado") == "aberta" and not _pausada(arq.parent):
            (arq.parent / "pausada").write_text(str(agora))
            titulos.append(plano["titulo"])
    return titulos


# ------------------------------------------------------------------ ferramentas
_ITEM = {"anyOf": [{"type": "string"}, {"type": "object", "properties": {
    "titulo": {"type": "string"}, "depende_de": {"type": "array", "items": {"type": "integer"}}}}]}
ESQUEMAS = {
    "tarefa_iniciar": {
        "name": "tarefa_iniciar",
        "description": (
            "Abre uma TAREFA LONGA com o plano gravado em disco, para ela sobreviver a reinício do agente, queda da "
            "máquina, limite de uso ou tempo esgotado: se o trabalho parar no meio, o vigia retoma SOZINHO do próximo "
            "passo pendente, sem a pessoa pedir. Use ANTES de começar quando o pedido tem muitos passos (4 ou mais), "
            "vai levar mais de uns 10 minutos ou passa por vários módulos/sites — ex.: testar o Raiz Connect de ponta a "
            "ponta como cliente novo, uma pesquisa grande com relatório, cadastros em vários portais. Pedido rápido: "
            "não use. Depois: em cada passo, tarefa_passo(estado=fazendo) ao começar e tarefa_passo(estado=feito, "
            "resultado=...) ao terminar (o resultado vai para o arquivo final); no fim, tarefa_concluir. Não mande "
            "mensagens à pessoa no meio: ela recebe UMA mensagem no fim, com o arquivo completo. `pedido`: o que a "
            "pessoa pediu, palavra por palavra. `passos`: a lista em ordem; cada um é um texto curto ou "
            "{\"titulo\", \"depende_de\": [números]} (sem depende_de, depende do anterior; [] = independente)."),
        "parameters": {"type": "object", "properties": {
            "titulo": {"type": "string"}, "pedido": {"type": "string"},
            "passos": {"type": "array", "items": _ITEM}}, "required": ["titulo", "pedido", "passos"]},
    },
    "tarefa_passo": {
        "name": "tarefa_passo",
        "description": (
            "Atualiza um passo da tarefa longa. estado: fazendo (ao começar), feito (com `resultado`: o que achou ou "
            "fez, completo, vai para o arquivo final), esperando_matheus (precisa dele: captcha/Resolver aqui, código, "
            "decisão; `pergunta` vai UMA vez ao celular dele, a não ser que o resolver_aqui já tenha mandado; siga com "
            "os passos que não dependem disto), falhou (`erro`: por que não deu, depois de tentar caminhos), falta "
            "(voltar a pendente, ex.: ele respondeu). Passo feito não se refaz. AÇÃO DE FORA (mandar mensagem/e-mail/"
            "DM, criar conta, postar, pagar, enviar formulário): ao começar o passo, `acao`=\"vou fazer X\"; depois, "
            "feito com `prova` (id, link, o que leu de volta no sistema). Se a tarefa mostra uma ação marcada e não "
            "confirmada, CONFIRA no sistema antes de refazer e diga o que viu em `conferido`. `novos_passos`: "
            "acrescenta passos no fim."),
        "parameters": {"type": "object", "properties": {
            "id": {"type": "string"}, "passo": {"type": "integer"},
            "estado": {"type": "string", "enum": list(ESTADOS)},
            "resultado": {"type": "string"}, "acao": {"type": "string"}, "prova": {"type": "string"},
            "conferido": {"type": "string"}, "pergunta": {"type": "string"}, "erro": {"type": "string"},
            "novos_passos": {"type": "array", "items": _ITEM}}, "required": ["id"]},
    },
    "tarefa_status": {
        "name": "tarefa_status",
        "description": (
            "O plano de uma tarefa longa (com `id`): o pedido como veio, cada passo e o estado dele, ações de fora "
            "marcadas/confirmadas, o próximo passo e os resultados até aqui. Sem `id`: as tarefas longas desta pessoa. "
            "Use ao retomar (o vigia manda \"retome a tarefa <id>\"), quando a pessoa diz \"continua\" ou responde a "
            "uma pergunta de tarefa."),
        "parameters": {"type": "object", "properties": {"id": {"type": "string"}}},
    },
    "tarefa_concluir": {
        "name": "tarefa_concluir",
        "description": (
            "Fecha a tarefa longa e entrega: `resumo` (poucas linhas: o principal, o que ele precisa decidir/fazer) + o "
            "arquivo com o resultado completo de todos os passos, numa mensagem só ao celular da pessoa. Só quando "
            "todos os passos estão feitos ou falharam (parcial=true só se ele pediu ou se o que falta depende dele). "
            "Depois responda só: ok (a entrega já foi)."),
        "parameters": {"type": "object", "properties": {
            "id": {"type": "string"}, "resumo": {"type": "string"}, "parcial": {"type": "boolean"}},
            "required": ["id", "resumo"]},
    },
}


def _texto(x) -> str:
    return "" if x is None else str(x)


async def executar(nome: str, args: dict, sessao: str) -> str:
    login = _login(sessao)
    try:
        if nome == "tarefa_iniciar":
            passos = args.get("passos")
            if isinstance(passos, str):
                passos = [x.strip(" -•\t") for x in passos.splitlines() if x.strip(" -•\t")]
            plano = await asyncio.to_thread(criar, login, _texto(args.get("titulo")), _texto(args.get("pedido")),
                                            passos or [], sessao)
            return (f"Tarefa {plano['id']} aberta com {len(plano['passos'])} passos (plano em disco; se parar no meio "
                    "eu retomo sozinho). Comece pelo passo 1: tarefa_passo(id, passo=1, estado=fazendo). Lembre: "
                    "resultado completo em cada feito; nada de mensagens no meio; no fim tarefa_concluir.")
        if nome == "tarefa_passo":
            return await asyncio.to_thread(
                mudar_passo, login, _texto(args.get("id")).strip(), args.get("passo"), _texto(args.get("estado")),
                _texto(args.get("resultado")), _texto(args.get("acao")), _texto(args.get("prova")),
                _texto(args.get("pergunta")), _texto(args.get("erro")), _texto(args.get("conferido")),
                args.get("novos_passos") or None, sessao)
        if nome == "tarefa_status":
            return await asyncio.to_thread(status, login, _texto(args.get("id")).strip())
        if nome == "tarefa_concluir":
            return await asyncio.to_thread(concluir, login, _texto(args.get("id")).strip(), _texto(args.get("resumo")),
                                           bool(args.get("parcial")), sessao)
    except ValueError as exc:
        return f"NÃO FEITO: {exc}"
    return f"NÃO FEITO: ferramenta desconhecida {nome}"


def registrar(ctx) -> None:
    for nome, esquema in ESQUEMAS.items():
        async def manipulador(args, session_id=None, task_id=None, _nome=nome, **kwargs):
            return await executar(_nome, args or {}, str(session_id or task_id or ""))
        ctx.register_tool(name=nome, toolset="agentepessoal", schema=esquema, handler=manipulador, is_async=True)
    ctx.register_hook("pre_llm_call", gancho_inicio)
    ctx.register_hook("pre_api_request", gancho_api)
    ctx.register_hook("pre_tool_call", gancho_ferramenta)
    ctx.register_hook("post_tool_call", gancho_ferramenta_fim)
    ctx.register_hook("on_session_end", gancho_fim)
