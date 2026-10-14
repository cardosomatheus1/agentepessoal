"""What may enter the person's memory (ficha and reviewer decisions): facts and their own words, never orders hidden in
text. Memory goes into every turn's prompt, so a poisoned entry would act in every conversation from then on.

Ported from Hermes (tools/threat_patterns.py, MIT): classic injection, role hijack, hiding things from the user,
exfiltration, secrets and invisible unicode; plus Portuguese wordings, orders/permissions disguised as facts and text
that came from third parties (a lead's DM, an e-mail: aprovacoes marks tool output with "⟦DADO EXTERNO").
Patterns anchor on attack vocabulary, not on bossy everyday Portuguese ("sempre responder curto" is a preference)."""

import re
import unicodedata

_F = r"(?:[\w'’]+\s+){0,6}"  # bounded filler between key words (unbounded repeats backtrack badly)
# imperative or infinitive only: "envie"/"enviar" is an order, "envia" (he sends) is a fact
_VERBO_EFEITO = (r"(?:envi(?:e|ar)|mand(?:e|ar)|encaminh(?:e|ar)|pag(?:ue|ar)|transf(?:ira|erir)|aprov(?:e|ar)|"
                 r"apag(?:ue|ar)|exclu(?:a|ir)|delet(?:e|ar)|compartilh(?:e|ar)|public(?:ar|que)|post(?:e|ar)|"
                 r"execut(?:e|ar)|rod(?:e|ar)|instal(?:e|ar)|baix(?:e|ar)|cli(?:que|car)|acess(?:e|ar))")

# (regex, reason shown to the agent); every scope gets INJECAO, the ficha also gets ORDENS and TERCEIROS
INJECAO = [
    (rf"\b(ignor[ae]r?|desconsider[ae]r?|esque[cç][ae]r?|ignore|disregard|forget)\s+{_F}(instru[cç](ões|oes|ão)|regras|"
     rf"orienta[cç](ões|oes)|instructions|rules|guidelines)", "manda ignorar instruções"),
    (r"system\s+prompt|prompt\s+(do|de)\s+sistema|instru[cç](ões|oes)\s+do\s+sistema|developer\s+message",
     "fala do prompt do sistema"),
    (rf"\b(voc[eê]|vc)\s+{_F}agora\s+(é|e|será|sera|vai\s+ser)\s+(um|uma|o|a)\b|you\s+are\s+{_F}now\s+(a|an|the)\b|"
     rf"\bfinja\s+{_F}(ser|que)\b|\bpretend\s+{_F}(to\s+be|you\s+are)\b|\baja\s+como\s+se\b",
     "tenta trocar quem o agente é"),
    (rf"\ba\s+partir\s+de\s+agora\s+{_F}(voc[eê]|vc|o\s+agente)\s+(deve|vai|tem\s+que|precisa)\b",
     "dá ordem ao agente"),
    (rf"\b(n[aã]o|nunca|never|do\s+not)\s+{_F}(cont[ae]r?|diga|dizer|avis[ae]r?|mostr[ae]r?|fal[ae]r?|tell)\s+{_F}"
     rf"(usu[aá]rio|matheus|dono|user)\b|\bsem\s+(avisar|contar|dizer)\s+(ao|a|o|pro|para\s+o)\s+(usu[aá]rio|matheus|dono)",
     "manda esconder algo da pessoa"),
    (r"<!--|<\s*div\s+style\s*=\s*[\"'][^>]{0,500}display\s*:\s*none", "tem conteúdo escondido (HTML)"),
    (r"\b(envi[ae]r?|mand[ae]r?|encaminh[ae]r?|post[ae]r?|transmit[ae]r?|send|post|upload)\b[^\n]{0,300}"
     r"\b(para|pra|to|at)\s+https?://", "manda enviar dados para um endereço"),
    (r"\b(curl|wget)\s+[^\n]{0,300}\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|SENHA)", "tenta vazar segredo"),
    (r"(authorized_keys|~/\.ssh|\$HOME/\.ssh|\.env\b|/a0/usr/.{0,40}(cofre|\.chave))", "mexe em credencial ou chave"),
    (r"(senha|password|token|api[_ -]?key|chave(\s+de\s+api)?|secret)\s*[:=]\s*[\"']?(?=\S*[\d!@#$%&*])"
     r"[A-Za-z0-9+/=_\-.!@#$%&*]{8,}",
     "parece um segredo (senha, token ou chave)"),
    (r"\b(AKIA|ASIA)[A-Z0-9]{16}\b|\b(sk|ghp|gho|xox[bp])[-_][A-Za-z0-9_\-]{16,}|"
     r"\b(?=[A-Za-z0-9+/=_]*\d)(?=[A-Za-z0-9+/=_]*[A-Za-z])[A-Za-z0-9+/=_]{40,}",
     "parece um segredo (senha, token ou chave)"),
]

ORDENS = [
    (rf"^\W*(sempre|nunca|n[aã]o)\s+{_VERBO_EFEITO}\b", "é uma ordem, não um fato sobre a pessoa"),
    (rf"\b(pode|deve|podem|pode-se)\s+{_F}{_VERBO_EFEITO}\s+{_F}sem\s+(perguntar|pedir|aprova[cç][aã]o|confirma[cç][aã]o|"
     rf"ok|autoriza[cç][aã]o)", "é uma permissão, não um fato sobre a pessoa"),
    (r"\b(aprova[cç][aã]o|confirma[cç][aã]o|autoriza[cç][aã]o)\s+(autom[aá]tica|dispensada|n[aã]o\s+(é|e)\s+(necess[aá]ria|"
     r"precisa))|\bn[aã]o\s+precisa\s+(de\s+)?(aprova[cç][aã]o|confirma[cç][aã]o|perguntar|pedir\s+ok|autoriza[cç][aã]o)",
     "é uma permissão, não um fato sobre a pessoa"),
]

TERCEIROS = [
    (r"⟦\s*DADO\s+EXTERNO", "veio de uma página, DM, e-mail ou busca (dado de terceiros)"),
    (r"\b(o|a)\s+(lead|cliente|empresa|perfil|remetente)\s+(disse|pediu|falou|escreveu|mandou|respondeu)\b|"
     r"@[\w.]{2,}\s+(disse|pediu|falou|escreveu|mandou|respondeu)\b",
     "é fala de terceiros (lead, cliente, remetente), não da pessoa"),
    (r"\b(segundo|conforme|de\s+acordo\s+com)\s+(o|a|um|uma)\s+(e-?mail|dm|direct|mensagem\s+d[eoa])",
     "veio de um e-mail ou DM (dado de terceiros)"),
    (r"^\s*(de|from|para|to|assunto|subject|enviado\s+em|sent)\s*:\s", "parece um e-mail colado (dado de terceiros)"),
]

# zero-width, word joiner, invisible operators, BOM, bidi embeddings/overrides/isolates (Hermes INVISIBLE_CHARS)
INVISIVEIS = frozenset("​‌‍⁠⁢⁣⁤﻿‪‫‬‭‮⁦⁧⁨⁩")

_COMPILADOS = {nome: [(re.compile(p, re.I | re.M), motivo) for p, motivo in lista]
               for nome, lista in (("injecao", INJECAO), ("ordens", ORDENS), ("terceiros", TERCEIROS))}


def ameaca(texto: str, ficha: bool = True) -> str:
    """Why `texto` must not be stored ("" when it may). ficha=True also refuses orders/permissions and third-party text
    (the profile holds facts about the person); ficha=False (a reviewer decision, which IS a rule) checks only
    injection, secrets and hidden characters."""
    texto = str(texto or "")[:20000]
    achados = sorted(set(texto) & INVISIVEIS)
    if achados:
        return f"tem caractere invisível (U+{ord(achados[0]):04X}), usado para esconder instruções"
    normal = unicodedata.normalize("NFKC", texto)
    grupos = ("injecao", "ordens", "terceiros") if ficha else ("injecao",)
    for grupo in grupos:
        for padrao, motivo in _COMPILADOS[grupo]:
            if padrao.search(normal):
                return motivo
    return ""
