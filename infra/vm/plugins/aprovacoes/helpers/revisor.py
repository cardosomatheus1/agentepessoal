"""Independent review of risky actions, and the approvals waiting on the user.

A model only *classifies* the action into a category (it sees the tool, its arguments and the
agent's stated intent — never the page content, which may carry injected instructions). What
happens next comes from the user's rules, deterministically: permitir / perguntar / nunca. If
the reviewer fails, the action waits for the user.
"""

import json
import re
import time
import urllib.request
import uuid

URL = "http://host.docker.internal:8787/openai/v1/responses"
MODELO = "openai.gpt-6-luna"

CATEGORIAS = {
    "pagamento": "pagar, cadastrar cartão ou forma de pagamento, assinar plano pago, transferir dinheiro",
    "compra": "finalizar compra, pedido, reserva ou contratação com cobrança",
    "termos": "aceitar termos de uso, políticas, contratos ou declarações em nome do usuário",
    "enviar_analise": "enviar algo para análise, revisão ou aprovação de terceiros (ex.: revisão de app da Meta, candidatura, formulário oficial)",
    "mensagem_terceiros": "mandar mensagem, e-mail, comentário, convite ou ligação para outras pessoas",
    "publicar": "publicar post, anúncio, página, campanha ativa ou conteúdo público",
    "apagar": "apagar ou desativar arquivos, contas, dados, campanhas, repositórios (irreversível ou difícil de desfazer)",
    "contas_reais": "alterar configurações de contas reais (banco, anúncios, governo, empresa)",
    "senha_seguranca": "MUDAR a segurança da conta: trocar senha, ativar/desativar 2FA, trocar e-mail ou telefone de "
                       "recuperação (digitar a senha atual para entrar ou confirmar a identidade NÃO é esta categoria)",
    "chaves_acesso": "gerar, copiar ou revogar tokens, chaves de API ou credenciais de aplicativos",
    "producao": "mexer em sistemas em produção: deploy, banco de dados, servidores, DNS",
}

# Cheap pre-filter: only actions that may change something outside the agent get reviewed.
ACOES_BROWSER = {"click", "dblclick", "press", "press_key", "key", "submit", "select", "select_option",
                 "check", "uncheck", "evaluate", "js", "execute_js", "tap"}
PALAVRAS = re.compile(
    r"envi|submet|confirm|aceit|concord|compr|pag(ar|amento|ue)|cart[aã]o|assin|publi|post|exclu|apag|delet|"
    r"remov|desativ|cancel|transfer|finaliz|conclu|revis[aã]o|an[aá]lise|solicit|contrat|reserv|instal|"
    r"send|submit|confirm|accept|agree|buy|pay|purchase|checkout|order|publish|delete|remove|deactivat|"
    r"cancel|transfer|request|review|deploy|merge|push|invite|share|approve|launch|activat|ativ",
    re.I,
)
DESTRUTIVO = re.compile(
    r"\brm\s+-|\brmdir\b|\bshred\b|\bmkfs|\bdd\s+if=|\bdrop\s+(table|database)|\btruncate\b|\bdelete\s+from\b|"
    r"\bgit\s+push\b|--force\b|\baws\s+\S+\s+(delete|remove|terminate|rm)\b|\bcurl\b[^\n]*-X\s*(POST|PUT|DELETE|PATCH)|"
    r"\bnpm\s+publish\b|\btwine\s+upload\b|\bkubectl\s+delete\b|\bterraform\s+(apply|destroy)\b|\bshutdown\b|\breboot\b",
    re.I,
)

PENDENTES: dict[str, dict] = {}  # context id -> approval waiting for the user
LEITURA = "/a0/usr/aprovacoes/somente_leitura.json"  # chat ids where nothing may change
ATIVIDADE = "/a0/usr/aprovacoes/atividade"  # <login>.jsonl: every reviewed action and its outcome


def somente_leitura() -> set:
    try:
        with open(LEITURA, encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def marcar_somente_leitura(ctx_id: str) -> None:
    import os

    ids = somente_leitura() | {ctx_id}
    os.makedirs(os.path.dirname(LEITURA), exist_ok=True)
    with open(LEITURA, "w", encoding="utf-8") as f:
        json.dump(sorted(ids), f)


def registrar_atividade(context, tool: str, analise: dict, decisao: str) -> None:
    """Activity log of consequential actions (what /atividade on WhatsApp shows)."""
    import os
    import sys

    try:
        sep = sys.modules.get("login_usuarios_separacao")
        dono = sep.dono_contexto(context) if sep else (context.get_data("dono") or "matheus")
        os.makedirs(ATIVIDADE, exist_ok=True)
        linha = {"em": time.time(), "conversa": context.name or context.id, "ferramenta": tool,
                 "categoria": analise.get("categoria"), "decisao": decisao, "resumo": analise.get("resumo")}
        with open(f"{ATIVIDADE}/{dono}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(linha, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _texto(v) -> str:
    try:
        return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    except Exception:
        return str(v)


def precisa_revisao(tool: str, args: dict, intencao: str) -> bool:
    nome = (tool or "").lower()
    if nome in ("response", "wait", "goal", "whatsapp_enviar", "consultar_sol", "analisar_imagens",
                "memory_load", "memory_save", "search_engine", "vision_load", "call_subordinate"):
        return False
    if nome == "browser":
        acao = str(args.get("action") or "").lower()
        if acao not in ACOES_BROWSER:
            return False
        return bool(PALAVRAS.search(intencao + " " + _texto(args)))
    if nome in ("code_execution_tool", "code_execution", "terminal"):
        return bool(DESTRUTIVO.search(_texto(args)))
    if "." in nome or "__" in nome or nome.startswith("mcp"):  # MCP connectors (Agent Zero: server.tool): anything that writes
        acao = nome.split(".", 1)[-1]
        return bool(re.search(r"send|create|update|delete|post|write|remove|reply|insert|modify|draft|share|move|"
                              r"trash|import|upload|copy|rename|manage|set_|add_|patch", acao))
    return False


def classificar(tool: str, args: dict, intencao: str, sempre: str) -> dict:
    lista = "\n".join(f"- {k}: {v}" for k, v in CATEGORIAS.items())
    pedido = f"""Classifique a AÇÃO que um agente de IA vai executar agora em nome do usuário.

Categorias:
{lista}
- nenhuma: não muda nada fora do agente, ou é passo intermediário sem efeito (abrir menu, navegar, preencher campo sem enviar, ler).

Ações que o usuário já mandou "sempre permitir" (se a ação for claramente uma destas, responda sempre_permitida=true):
{sempre.strip() or "(nenhuma)"}

AÇÃO
Ferramenta: {tool}
Argumentos: {_texto(args)[:1500]}
Intenção declarada pelo agente: {intencao[:2000]}

Responda só JSON: {{"categoria": "<uma das categorias ou nenhuma>", "sempre_permitida": false, "resumo": "<o que vai acontecer, em uma frase curta em português, do ponto de vista do usuário>"}}"""
    body = {"model": MODELO, "reasoning": {"effort": "low"}, "input": [{"role": "user", "content": pedido}]}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    texto = "".join(c.get("text", "") for item in data.get("output", []) if item.get("type") == "message"
                    for c in item.get("content", []) if c.get("type") == "output_text")
    achado = re.search(r"\{.*\}", texto, re.S)
    resultado = json.loads(achado.group(0)) if achado else {}
    categoria = str(resultado.get("categoria") or "").strip().lower()
    return {
        "categoria": categoria if categoria in CATEGORIAS else "nenhuma",
        "sempre_permitida": bool(resultado.get("sempre_permitida")),
        "resumo": str(resultado.get("resumo") or "").strip()[:300],
    }


def veredito(regras: dict, analise: dict) -> str:
    categoria = analise["categoria"]
    if categoria == "nenhuma":
        return "permitir"
    regra = str((regras or {}).get(categoria) or "perguntar").lower()
    if regra == "nunca":
        return "nunca"  # "always allow" never overrides a hard rule
    if regra == "permitir" or analise.get("sempre_permitida"):
        return "permitir"
    return "perguntar"


def abrir(ctx_id: str, analise: dict, tool: str) -> dict:
    pendente = {"id": uuid.uuid4().hex[:8], "contexto": ctx_id, "categoria": analise["categoria"],
                "resumo": analise["resumo"] or f"usar {tool}", "decisao": None, "criado": time.time()}
    PENDENTES[ctx_id] = pendente
    return pendente


def decidir(ctx_id: str, decisao: str, pid: str = "") -> bool:
    pendente = PENDENTES.get(ctx_id)
    if not pendente or pendente["decisao"] or (pid and pid != pendente["id"]):
        return False
    if decisao not in ("aprovar", "sempre", "recusar"):
        return False
    pendente["decisao"] = decisao
    return True


RESPOSTAS = {
    "aprovar": {"aprovar", "aprovo", "aprovado", "sim", "pode", "ok", "pode fazer", "autorizo", "✅"},
    "sempre": {"sempre", "sempre permitir", "pode sempre"},
    "recusar": {"recusar", "recuso", "não", "nao", "negar", "não pode", "nao pode", "❌"},
}


def resposta_digitada(texto: str) -> str:
    t = (texto or "").strip().lower().rstrip(".!")
    for decisao, opcoes in RESPOSTAS.items():
        if t in opcoes:
            return decisao
    return ""
