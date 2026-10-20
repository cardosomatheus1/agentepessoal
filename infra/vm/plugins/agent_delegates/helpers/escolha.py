"""Who does a task (20/10): Agent Zero orchestrates; Hermes and OpenClaw run in a separate box with their full tools
(terminal, files, internet, browser) but nothing of Matheus's. So the split is by what the task touches, then by
strength:
- stays with Agent Zero: anything with his accounts, vault, logged-in browser, messages to people, payments, the Raiz
  prospecting flow, his Google/agenda; and short things (delegating costs a box and minutes);
- Hermes: code and data work (scripts, spreadsheets, PDFs, conversions, charts, files to produce), terminal-heavy jobs;
- OpenClaw: research and reading on the open web (many pages, comparisons, collecting facts from sites), long
  autonomous multi-step work, a second independent take on something Hermes or the agent did.
The agent may name the engine itself; `motor="auto"` uses this choice. Deterministic and explainable, on purpose."""

import re
import unicodedata


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


# what never leaves Agent Zero (it needs his accounts, or it acts on people or money)
_SO_A0 = [
    (r"\b(senha|fazer login|logar|entrar na (minha |sua |)conta|cofre|2fa|codigo de verificacao)\b", "usa conta ou senha"),
    (r"\b(gmail|meu e-?mail|minha agenda|google agenda|calendar|meu drive|google drive|whatsapp|telegram|instagram da raiz|"
     r"@raiz\.connect)\b", "mexe nas contas dele"),
    (r"\b(envi(e|ar|a) (uma |um |a |o )?(mensagem|e-?mail|dm|whats)|mand(e|ar|a) (uma |um )?(mensagem|e-?mail|whats)|responda? (ao|a) "
     r"(cliente|lead))\b", "manda mensagem a alguém"),
    (r"\b(pagar|pague|fazer (o )?pagamento|comprar|compre|efetuar compra|assinar plano|cartao de credito)\b",
     "envolve dinheiro"),
    (r"\bprospec", "fluxo da prospecção (só no A0, com revisor e cotas)"),
]
_HERMES = r"\b(codigo|script|python|programa|planilha|excel|xlsx|csv|pdf|docx|converter|conversao|grafico|dados|" \
          r"tabela|terminal|instal|automatiz|extrair de arquivo|ocr|imagem|redimension|ffmpeg|video|audio|json|api|" \
          r"teste|bug|refator|compilar|calcul)"
_OPENCLAW = r"\b(pesquis|pesquisar na web|levant|compar(ar|e|acao)|concorrent|mercado|preco(s)? de|sites?|paginas?|" \
            r"noticia|artigo|fontes|ler (o|a|os|as) |resum(ir|o) (de |do |da )?(site|pagina|artigo)|segunda opiniao|" \
            r"revis(ar|ao) (critica|independente)|critic|auditar|verificar fatos|checar)"


def so_no_a0(tarefa: str) -> str:
    """Why this task must stay with Agent Zero ('' when it may be delegated)."""
    t = _norm(tarefa)
    for padrao, motivo in _SO_A0:
        if re.search(padrao, t):
            return motivo
    return ""


def escolher_motor(tarefa: str) -> tuple:
    """('hermes'|'openclaw', why) for a task that may be delegated."""
    t = _norm(tarefa)
    h = len(re.findall(_HERMES, t))
    o = len(re.findall(_OPENCLAW, t))
    if o > h:
        return "openclaw", "pesquisa/leitura na web ou segunda opinião"
    if h > o:
        return "hermes", "código, dados ou arquivos"
    return "hermes", "tarefa geral com terminal e arquivos (padrão)"
