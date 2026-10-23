"""Aprovações antes de ação de risco no Hermes (migração, fase 2), com o mesmo revisor e as mesmas regras do A0
(/a0/usr/plugins/aprovacoes: helpers/revisor.py e default_config.yaml).

"Hermes primeiro": os comandos de terminal perigosos ficam com as aprovações do próprio Hermes (approvals.mode smart).
O que é nosso de verdade e entra aqui, num gancho `pre_tool_call`:
- cliques/teclas/JS no navegador e conectores MCP que escrevem: o revisor (Luna) só CLASSIFICA a ação (ferramenta,
  argumentos e o rótulo do elemento clicado, nunca o conteúdo da página); a regra dele decide: permitir (segue), nunca
  (bloqueio) ou perguntar (`{"action": "approve"}`: o portão de aprovação do Hermes, que pelo API server vira o evento
  `approval.request` do run; a ponte põe os botões no celular e devolve a escolha em /v1/runs/<id>/approval);
- as liberações do Matheus: mensagem no Instagram (avisada no celular), app da Meta da Raiz, homologação da 99, janela
  da prospecção, "Nesta tarefa" (escolha `session`) e "Sempre permitir" (escolha `always`, que também entra na lista
  que o revisor lê, como no A0);
- a trava contra vazamento (cartão, CPF, token, valor do cofre) no que sai para outras pessoas, acima de qualquer regra;
- numa rodada do cron (ninguém para responder; o `cron_mode: approve` aprovaria sozinho) o "perguntar" não roda: o
  Matheus é avisado e a rotina diz PRECISA DE VOCÊ (as liberações acima continuam valendo).

O Hermes não tem a "intenção declarada" do A0: o rótulo do elemento vem da última leitura da página (`post_tool_call`
do browser_snapshot guarda ref → rótulo por sessão) e a página atual do último browser_navigate.
"""
import hashlib
import importlib.util
import json
import logging
import re
import sys
import threading
import time
from pathlib import Path

import yaml

PLUGINS = Path("/a0/usr/plugins")
DADOS = Path("/opt/data/agentepessoal")
SEMPRE = DADOS / "aprovacoes_sempre.txt"  # "Sempre permitir" dado pelo Hermes (o do A0 fica no config dele)
log = logging.getLogger("agentepessoal.aprovacoes")

# ferramenta do Hermes -> ação do `browser` do A0 (o revisor e as liberações falam essa língua)
NAVEGADOR = {"browser_click": "click", "browser_press": "press", "browser_type": "type", "browser_console": "evaluate",
             "browser_cdp": "evaluate", "browser_exec": "evaluate", "browser_dialog": "dialog"}
LEITURA = frozenset({"browser_navigate", "browser_snapshot", "browser_scroll", "browser_back", "browser_get_images",
                     "browser_vision"})
# Hermes primeiro: comando de terminal e código ficam com as aprovações do próprio Hermes (approvals.mode smart)
DO_HERMES = frozenset({"terminal", "execute_code", "process_manage"})
SEM_ENDERECO = frozenset({"browser_console", "browser_cdp", "browser_exec", "browser_get_images", "browser_vision"})
REF = re.compile(r'^\s*-\s*([\w-]+)(?:\s+"((?:[^"\\]|\\.)*)")?[^\n]*?\[ref=@?(e\d+)\]', re.M)
URL = re.compile(r'"(?:url|currentUrl|final_url)"\s*:\s*"(https?://[^"]+)"')

_trava = threading.Lock()
_paginas: dict[str, dict] = {}     # sessão -> {"url": ..., "refs": {"e12": 'button "Enviar"'}}
_pendentes: dict[str, dict] = {}   # rule_key -> {"sessao", "categoria", "resumo"}
_tarefa: dict[str, dict] = {}      # sessão -> {categoria: quando} ("Nesta tarefa" = escolha session)
_rotina_avisada: dict[str, set] = {}  # rodada do cron -> categorias já avisadas ao Matheus
ROTINA = re.compile(r"^cron_[A-Za-z0-9]+_\d{8}_\d{6}$")  # a sessão de uma rodada do cron (igual a acesso_hermes.ROTINA)


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


def revisor():
    return _modulo("agentepessoal_revisor", PLUGINS / "aprovacoes" / "helpers" / "revisor.py")


def config() -> dict:
    """As regras do A0 (default_config.yaml do plugin; o A0 não tem config salvo por cima) + o "sempre" do Hermes."""
    try:
        cfg = yaml.safe_load((PLUGINS / "aprovacoes" / "default_config.yaml").read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        log.warning("aprovacoes: config do A0 não lida (%s): toda ação de risco pergunta", exc)
        cfg = {}
    try:
        extra = SEMPRE.read_text(encoding="utf-8")
    except OSError:
        extra = ""
    cfg["sempre_permitir"] = "\n".join(t for t in (str(cfg.get("sempre_permitir") or "").strip(), extra.strip()) if t)
    return cfg


def _sessao(kw: dict) -> str:
    return str(kw.get("session_id") or kw.get("task_id") or "")


def ver_pagina(tool_name="", args=None, result=None, **kw):
    """Gancho `post_tool_call`: guarda a página atual e os rótulos dos elementos da última leitura."""
    if not str(tool_name).startswith("browser_") or not isinstance(result, str):
        return None
    sessao = _sessao(kw)
    with _trava:
        pagina = _paginas.setdefault(sessao, {"url": "", "refs": {}})
        if tool_name == "browser_navigate" and isinstance(args, dict) and args.get("url"):
            pagina["url"] = str(args["url"])
        texto = result
        try:  # as ferramentas browser_* devolvem JSON ({"success", "url", "snapshot": "<texto>"}): o texto vem dentro
            dados = json.loads(result)
        except ValueError:
            dados = None
        if isinstance(dados, dict):
            texto = str(dados.get("snapshot") or "")
            if tool_name not in SEM_ENDERECO and isinstance(dados.get("url"), str) and dados["url"].startswith("http"):
                pagina["url"] = dados["url"]
        # 23/10 (prospecção, executar das 11:38): o resultado de um JS/CDP ou da lista de imagens traz endereços de
        # QUALQUER coisa da página (um link do Facebook no post): ele virava "a página atual", o revisor leu "comentário
        # no Facebook" e o comentário pré-aprovado no Instagram foi barrado. Só a navegação diz onde o navegador está.
        achou = [] if tool_name in SEM_ENDERECO else URL.findall(result)
        if achou:
            pagina["url"] = achou[-1]
        refs = {ref: (f'{papel} "{rotulo}"' if rotulo else papel) for papel, rotulo, ref in REF.findall(texto)}
        if refs:
            pagina["refs"] = refs
        if tool_name == "browser_type" and isinstance(args, dict):  # Enter depois disso envia o que foi digitado
            pagina["digitado"] = pagina.get("refs", {}).get(str(args.get("ref") or "").lstrip("@"), "um campo")
    return None


def alvo(sessao: str, ref: str) -> tuple:
    """(rótulo do elemento `ref` na última leitura da página, página atual) desta sessão; ("", "") se não se sabe."""
    with _trava:
        pagina = dict(_paginas.get(sessao) or {})
    return (pagina.get("refs") or {}).get(str(ref or "").lstrip("@"), ""), pagina.get("url", "")


def intencao(tool_name: str, args: dict, sessao: str) -> str:
    with _trava:
        pagina = dict(_paginas.get(sessao) or {})
    ref = str(args.get("ref") or "").lstrip("@")
    alvo = (pagina.get("refs") or {}).get(ref, "")
    partes = [f"{NAVEGADOR.get(tool_name, tool_name)}"]
    if alvo:
        partes.append(f"no elemento {alvo}")
    if args.get("key"):
        partes.append(f"tecla {args['key']}")
        if str(args["key"]).lower() in ("enter", "return", "control+enter", "meta+enter") and pagina.get("digitado"):
            partes.append(f"(envia o que foi digitado em {pagina['digitado']})")
    if pagina.get("url"):
        partes.append(f"na página {pagina['url']}")
    return " ".join(partes)


def _como_a0(tool_name: str, args: dict) -> tuple:
    if tool_name in NAVEGADOR:
        a = dict(args)
        a["action"] = NAVEGADOR[tool_name]
        return "browser", a
    return tool_name, dict(args)


def _avisar(login: str, texto: str) -> None:
    try:
        ponte = _modulo("whatsapp_ponte", PLUGINS / "whatsapp" / "helpers" / "ponte.py")
        erro = ponte.enviar(login, texto, "", "", None, "progresso")
        if erro:
            log.warning("aprovacoes: aviso não saiu: %s", erro)
    except Exception as exc:
        log.warning("aprovacoes: aviso não saiu: %s: %s", type(exc).__name__, exc)


def checar(tool_name="", args=None, **kw):
    """Gancho `pre_tool_call`."""
    if tool_name in LEITURA or tool_name in DO_HERMES:
        return None
    args = args if isinstance(args, dict) else {}
    sessao = _sessao(kw)
    rv = revisor()
    ponte = sys.modules["agentepessoal_ponte_a0"]
    login = ponte.login_da_sessao(sessao)
    nome_a0, args_a0 = _como_a0(tool_name, args)
    quer = intencao(tool_name, args, sessao) if tool_name.startswith("browser_") else ""
    cofre = rv.valores_do_cofre(login)
    if rv.digitando_para_alguem(nome_a0, args_a0, quer):
        motivos = rv.vazamento(args_a0, cofre)
        if motivos:
            return _barrar(motivos)
    if not rv.precisa_revisao(nome_a0, args_a0, quer):
        return None
    cfg = config()
    try:
        analise = rv.classificar(nome_a0, args_a0, quer, str(cfg.get("sempre_permitir") or ""))
        decisao = rv.veredito(cfg.get("regras") or {}, analise)
    except Exception as exc:  # revisor fora: ele decide
        analise = {"categoria": "contas_reais", "sempre_permitida": False,
                   "resumo": f"{tool_name} (o revisor falhou: {str(exc)[:80]})"}
        decisao = "perguntar"
    if analise["categoria"] in rv.SAIDA:
        motivos = rv.vazamento({"args": args_a0, "intencao": quer}, cofre)
        if motivos:
            return _barrar(motivos)
    pagina = (_paginas.get(sessao) or {}).get("url", "")
    if decisao != "permitir" and rv.livre_erp(analise, nome_a0, args_a0, quer, cfg, pagina):
        _avisar(login, f"📣 *ERP Raiz (sem pedir ok)*\n\n{analise['resumo']}")
        return None
    if decisao == "nunca":
        return {"action": "block", "message": (
            f"[Aprovações] Bloqueado pela regra do Matheus ({analise['categoria']}: nunca): «{analise['resumo']}». "
            "Não foi executado. Não tente de novo nem por outro caminho; diga a ele em uma linha.")}
    if decisao == "permitir":
        return None
    conversa = ponte.conversa(sessao)
    if rv.liberacao_vale(analise, nome_a0, conversa.get_data("_aprovacoes_liberadas") or {}, pagina, time.time()):
        return None  # a janela da prospecção: ele já aprovou essa ação (só no Instagram, minutos)
    with _trava:
        tarefa = dict(_tarefa.get(sessao) or {})
    if analise["categoria"] in tarefa and time.time() - tarefa[analise["categoria"]] < rv.TAREFA_MAX:
        return None  # "Nesta tarefa"
    if rv.livre_instagram(analise, nome_a0, args_a0, quer, cfg):
        _avisar(login, f"📣 *Instagram (sem pedir ok)*\n\n{analise['resumo']}")
        return None
    if rv.livre_meta_raiz(analise, nome_a0, args_a0, quer, cfg):
        _avisar(login, f"📣 *Meta da Raiz (sem pedir ok)*\n\n{analise['resumo']}")
        return None
    if rv.livre_99food(analise, nome_a0, args_a0, quer, cfg, pagina):
        _avisar(login, f"📣 *99Food (sem pedir ok)*\n\n{analise['resumo']}")
        return None
    if ROTINA.match(sessao):
        return _rotina_sem_ok(login, sessao, analise)
    chave = "ap-" + hashlib.sha256(f"{tool_name}|{json.dumps(args, sort_keys=True, default=str)}".encode()).hexdigest()[:16]
    with _trava:
        _pendentes[chave] = {"sessao": sessao, "categoria": analise["categoria"], "resumo": analise["resumo"],
                             "em": time.time()}
        for velha in [k for k, v in _pendentes.items() if time.time() - v["em"] > 86400]:
            _pendentes.pop(velha, None)
    return {"action": "approve", "rule_key": chave,
            "message": f"{analise['resumo'] or tool_name} ({analise['categoria'].replace('_', ' ')})"}


def _rotina_sem_ok(login: str, sessao: str, analise: dict) -> dict:
    """Rotina (cron) com uma ação que pede o ok do Matheus. O cron do Hermes, com `approvals.cron_mode: approve` (para
    o código das rotinas rodar como no A0), aprovaria sozinho o portão do plugin: o "perguntar" das regras viraria
    "permitir" sem ninguém ver (ex.: um Direct lido na prospecção pedindo um e-mail). No A0 a rotina perguntava; aqui
    não há quem responda: a ação não roda, ele é avisado (uma vez por categoria na rodada) e a rotina segue com o resto
    e diz na resposta final. O que já é livre (Instagram, Meta da Raiz, 99, janela da prospecção) passou antes."""
    resumo = analise.get("resumo") or "uma ação"
    categoria = str(analise.get("categoria") or "")
    with _trava:
        avisadas = _rotina_avisada.setdefault(sessao, set())
        novo = categoria not in avisadas
        avisadas.add(categoria)
    if novo:
        _avisar(login, f"🔒 *Rotina pediu seu ok e não fez*\n\n{resumo} ({categoria.replace('_', ' ')}). "
                       "Se quiser, peça na conversa que eu faço.")
    return {"action": "block", "message": (
        f"[Aprovações] Rotina sem ninguém para aprovar: «{resumo}» ({categoria.replace('_', ' ')}) pede o ok do "
        "Matheus e NÃO foi executado (ele foi avisado). Não tente de novo nem por outro caminho; siga com o resto da "
        "rotina e, na resposta final, diga em uma linha: PRECISA DE VOCÊ: <isso>.")}


def _barrar(motivos: list) -> dict:
    return {"action": "block", "message": (
        f"[Aprovações] Bloqueado: o texto que sairia para outra pessoa leva {', '.join(motivos)}. Nada foi enviado. "
        "Tire isso do texto (nunca mande senha, token, cartão ou CPF a terceiros) ou pergunte ao Matheus.")}


def resposta(pattern_key="", choice="", **kw):
    """Gancho `post_approval_response`: "Nesta tarefa" (session) libera a categoria até o fim da conversa; "Sempre
    permitir" (always) entra na lista que o revisor lê (o Hermes guarda só esta ação exata)."""
    chave = str(pattern_key or "").removeprefix("plugin_rule:")
    with _trava:
        pend = _pendentes.pop(chave, None) if choice in ("once", "session", "always", "deny") else _pendentes.get(chave)
        if not pend:
            return None
        if choice == "session":
            _tarefa.setdefault(pend["sessao"], {})[pend["categoria"]] = time.time()
    if choice == "always":
        try:
            DADOS.mkdir(parents=True, exist_ok=True)
            with SEMPRE.open("a", encoding="utf-8") as f:
                f.write(f"{pend['categoria']}: {pend['resumo']}\n")
        except OSError as exc:
            log.warning("aprovacoes: 'sempre permitir' não gravou: %s", exc)
    return None


def registrar(ctx) -> None:
    ctx.register_hook("post_tool_call", ver_pagina)
    ctx.register_hook("pre_tool_call", checar)
    ctx.register_hook("post_approval_response", resposta)
