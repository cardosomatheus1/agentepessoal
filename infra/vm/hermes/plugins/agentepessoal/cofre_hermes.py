"""O cofre de cada pessoa no Hermes (migração, fase 2): os mesmos arquivos e helpers do Agent Zero
(/a0/usr/plugins/cofre/helpers), ligados nos pontos do Hermes:

- middleware `tool_execution` (roda depois das aprovações, que só veem o nome): nas ferramentas que agem num site ou
  sistema, `§§secret(NOME)` vira o valor do dono da conversa; nas outras (texto para gente ou para guardar) vira só o
  NOME. O resultado volta mascarado e o uso entra no livro (só os nomes).
- gancho `transform_tool_result`: mascara de novo (segunda trava; o Hermes ignora erro de gancho e seguiria sem máscara).
- middleware `llm_request`: nenhum valor do cofre chega ao modelo, nem uma senha colada na conversa.
- gancho `pre_llm_call`: os nomes que a pessoa tem no cofre (nunca os valores), na 1ª mensagem e quando a lista muda.
"""
import importlib.util
import json
import logging
import sys
import threading
from pathlib import Path

PLUGINS = Path("/a0/usr/plugins")
log = logging.getLogger("agentepessoal.cofre")

# Ferramentas do Hermes que digitam ou executam: só elas recebem o valor real (no A0: browser, code_execution_tool,
# terminal, input...). Conector MCP fica fora: um que manda e-mail levaria o valor a terceiros.
ACAO = frozenset({"terminal", "execute_code", "browser_type", "browser_exec", "browser_cdp", "browser_press",
                  "computer_use", "terminal_isolado"})
AVISO_USO = ("\n\n✅ Cofre: o valor real de {nomes} foi usado nesta ação. Campos de senha e o texto digitado aparecem "
             "vazios ou como §§secret(...) para você por segurança — isso é normal. Siga em frente (ex.: clique em "
             "Avançar/Entrar); só conclua que falhou se o site disser que a senha está errada.")

_trava = threading.Lock()
_livro_ultimos: dict[str, dict] = {}   # sessão -> {nome: quando entrou no livro}
_nomes_avisados: dict[str, tuple] = {}  # sessão -> nomes já ditos ao modelo nesta conversa


def _modulo(nome: str, caminho: Path):
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        sys.modules[nome] = modulo
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
    return sys.modules[nome]


def cofre():
    return _modulo("cofre_helper", PLUGINS / "cofre" / "helpers" / "cofre.py")


def _livro_cofre():
    return _modulo("cofre_livro", PLUGINS / "cofre" / "helpers" / "livro_cofre.py")


def _login(kw: dict) -> str:
    """Só a sessão que a ponte ligou a uma pessoa tem cofre: sessão sem dono (subtarefa, sessão nova) não recebe senha
    de ninguém, em vez de cair no cofre do Matheus (revisão OpenCode, 23/10)."""
    ponte = sys.modules["agentepessoal_ponte_a0"]
    return ponte.login_mapeado(str(kw.get("session_id") or kw.get("task_id") or ""))


def _dados(kw: dict) -> dict:
    login = _login(kw)
    if not login:
        return {}
    try:
        return cofre().carregar(login)
    except Exception as exc:  # cofre ilegível: nada é trocado (o placeholder segue) e o log diz por quê
        log.warning("cofre: não lido: %s: %s", type(exc).__name__, exc)
        return {}


def _esconder(valor, kw: dict):
    """Máscara de todos os cofres, o do dono da sessão primeiro (para o modelo ver os nomes que ele usa)."""
    return mascarar(mascarar(valor, _dados(kw)), _todos())


def _todos() -> dict:
    """Os valores de todas as pessoas, só para mascarar (esconder a mais nunca vaza; a menos, sim)."""
    c = cofre()
    tudo: dict = {}
    for arq in sorted(Path(c.PASTA).glob("*.json")):
        if arq.name.endswith(".descricoes.json"):
            continue
        try:
            for nome, valor in c.carregar(arq.stem).items():
                tudo[nome if tudo.get(nome, valor) == valor else f"{nome}_{arq.stem}"] = valor
        except Exception as exc:
            log.warning("cofre: %s não lido para a máscara: %s", arq.name, type(exc).__name__)
    return tudo


def _so_nomes(valor, c):
    if isinstance(valor, str):
        return c.PADRAO.sub(lambda m: m.group(1), valor)
    if isinstance(valor, dict):
        return {k: _so_nomes(v, c) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_so_nomes(v, c) for v in valor]
    return valor


NIVEIS_ESCAPE = 3  # JSON dentro de JSON (ex.: uma ferramenta lê um .json e o resultado volta como JSON): 2 níveis


def _formas(valor: str) -> set:
    """O valor como está e como aparece dentro de JSON, até NIVEIS_ESCAPE níveis (as ferramentas do Hermes devolvem
    JSON: uma senha com `"`, `\\`, quebra de linha ou acento volta escapada e passaria pela troca exata; revisões
    OpenCode de 23/10)."""
    formas, nivel = {valor}, {valor}
    for _ in range(NIVEIS_ESCAPE):
        nivel = {json.dumps(f, ensure_ascii=a)[1:-1] for f in nivel for a in (True, False)}
        formas |= nivel
    return formas


def mascarar(valor, dados: dict):
    """Cada valor do cofre (≥ 4 caracteres) volta a ser §§secret(NOME), em texto, dict ou lista."""
    if not dados:
        return valor
    if isinstance(valor, str):
        trocas = sorted(((f, n) for n, v in dados.items() if isinstance(v, str) and len(v) >= 4 for f in _formas(v)),
                        key=lambda t: -len(t[0]))
        for forma, nome in trocas:
            valor = valor.replace(forma, f"§§secret({nome})")
        return valor
    if isinstance(valor, dict):
        return {k: mascarar(v, dados) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return type(valor)(mascarar(v, dados) for v in valor)
    return valor


def _registrar(login: str, ferramenta: str, usados: list, sessao: str) -> None:
    try:
        lc = _livro_cofre()
        with _trava:
            ultimos = _livro_ultimos.setdefault(sessao, {})
        lc.registrar_usos(lc.livro(), login, ferramenta, usados, ultimos, sessao)
    except Exception as exc:  # o livro nunca impede a ferramenta
        log.warning("cofre: uso não registrado no livro: %s: %s", type(exc).__name__, exc)


def executar(tool_name="", args=None, next_call=None, **kw):
    """Middleware `tool_execution`."""
    if not isinstance(args, dict) or "§§secret(" not in json.dumps(args, ensure_ascii=False, default=str):
        return _esconder(next_call(args), kw)
    c = cofre()
    if tool_name not in ACAO:
        return _esconder(next_call(_so_nomes(args, c)), kw)
    if not _login(kw):
        return json.dumps({"error": "Esta conversa não está ligada a uma pessoa, então não há cofre para usar aqui. "
                                    "Peça a senha pelo canal da pessoa (Telegram/WhatsApp) ou rode a tarefa na conversa dela."},
                          ensure_ascii=False)
    dados = _dados(kw)
    bruto = json.dumps(args, ensure_ascii=False, default=str)
    pedidos = sorted(set(c.PADRAO.findall(bruto)))
    faltando = [n for n in pedidos if n not in dados]
    if faltando:
        return json.dumps({"error": (
            f"{', '.join(faltando)} não está no cofre do usuário. Nomes disponíveis: {', '.join(sorted(dados)) or 'nenhum'}. "
            f"Use um desses ou peça para ele mandar no Telegram/WhatsApp `/senha {faltando[0]} valor`.")},
            ensure_ascii=False)
    _registrar(_login(kw), tool_name, pedidos, str(kw.get("session_id") or kw.get("task_id") or ""))
    # o do dono primeiro, depois o de todos: juntar os dois num dict perderia o valor de outra pessoa com o mesmo nome
    resultado = _esconder(next_call(c.trocar(args, dados)), kw)
    if isinstance(resultado, str) and pedidos:
        resultado += AVISO_USO.format(nomes=", ".join(f"{n} ({len(dados[n])} caracteres)" for n in pedidos))
    return resultado


DEPOIS: list = []  # (tool_name, texto) -> texto, depois da máscara (dicas_hermes): no Hermes só o 1º gancho vale


def resultado_mascarado(tool_name="", args=None, result=None, **kw):
    """Gancho `transform_tool_result`: devolve o texto só quando algo mudou (máscara e, depois, as dicas)."""
    if not isinstance(result, str):
        return None
    novo = _esconder(result, kw)
    for f in DEPOIS:
        try:
            novo = f(tool_name, novo)
        except Exception as exc:  # uma dica nunca derruba a máscara
            log.warning("dica falhou: %s: %s", type(exc).__name__, exc)
    return novo if novo != result else None


def pedido_mascarado(request=None, **kw):
    """Middleware `llm_request`: tira do pedido ao modelo qualquer valor do cofre (mensagens e prompt)."""
    if not isinstance(request, dict):
        return None
    novo = {k: (_esconder(v, kw) if k in ("messages", "system", "input", "instructions") else v)
            for k, v in request.items()}
    if novo == request:
        return None
    return {"request": novo, "source": "agentepessoal", "reason": "cofre: valor mascarado"}


def contexto_nomes(session_id="", task_id="", is_first_turn=False, **kw):
    """Gancho `pre_llm_call`: os nomes do cofre, quando a conversa começa ou a lista muda."""
    try:
        login = _login({"session_id": session_id, "task_id": task_id})
        if not login:
            return None
        itens = cofre().lista(login)
    except Exception as exc:
        log.warning("cofre: lista não lida: %s: %s", type(exc).__name__, exc)
        return None
    chave = str(session_id or task_id or "")
    assinatura = tuple(n for n, _ in itens)
    with _trava:
        if not is_first_turn and _nomes_avisados.get(chave) == assinatura:
            return None
        _nomes_avisados[chave] = assinatura
    if not itens:
        return {"context": "Cofre: esta pessoa ainda não tem senha guardada."}
    curto = lambda t: (" ".join(str(t or "").split())[:59] + "…") if len(" ".join(str(t or "").split())) > 60 \
        else " ".join(str(t or "").split())
    linhas = "\n".join(f"- {n}: {curto(para) or '(sem descrição)'}" for n, para in itens)
    return {"context": ("Senhas que você TEM no cofre desta pessoa (use `§§secret(NOME)`; guardar no cofre já autoriza "
                        f"usar no login, sem perguntar):\n{linhas}")}


def registrar(ctx) -> None:
    ctx.register_middleware("tool_execution", executar)
    ctx.register_middleware("llm_request", pedido_mascarado)
    ctx.register_hook("transform_tool_result", resultado_mascarado)
    ctx.register_hook("pre_llm_call", contexto_nomes)
