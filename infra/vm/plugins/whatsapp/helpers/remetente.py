"""Proof that an e-mail to the agent really came from the owner.

12/10 review: anything short of an explicit "fail" in Authentication-Results was taken as the owner, but Locaweb's MX
adds that header to only some messages (none to Gmail), and a forger can write one of his own in the message. Two
proofs are accepted now, both made of data a forger cannot write:

1. Sent through the owner's own Locaweb account. Locaweb's submission server writes "(Authenticated sender: <login>)
   ... with ESMTPSA" in the third Received header from the top. Checked on real mail (12/10): for mail from outside, the
   top three Received are always Locaweb's (mailbox ← relay ← MX), so anything a sender forges sits fourth or lower;
   and the second must have come from the third's server over Locaweb's internal network (10.x), so a shorter chain
   cannot bring a forged header up to third place. The login must be the From address. Mail sent from an AWS machine
   (the agent itself) never counts: otherwise a page could get the agent to e-mail itself an "order from the owner".
2. A valid DKIM signature (rsa-sha256) by the From domain itself, verified here with the public key from DNS (Gmail
   signs all mail; Locaweb does not sign the owner's).

Authentication-Results is still read, but only the ones above the third Received (written by Locaweb), and only to
drop explicit failures."""

import base64
import hashlib
import re
import time

LOCAWEB = re.compile(r"(^|\.)(locaweb\.com\.br|email-ssl\.com\.br|correio\.biz)$", re.I)
INTERNO = re.compile(r"\[10\.\d{1,3}\.\d{1,3}\.\d{1,3}\]")
# the b= value (and only it) is emptied before verifying; same expression as the reference library (dkimpy)
FWS = rb"(?:(?:\s*\r?\n)?\s+)?"
SEM_B = re.compile(rb"([;\s]b" + FWS + rb"=)(?:" + FWS + rb"[a-zA-Z0-9+/=])*(?:\r?\n\Z)?")


def campos(bruto: bytes) -> tuple[list[tuple[bytes, bytes]], bytes]:
    """Raw header fields in order, as (name, value with its folding and final CRLF), and the raw body."""
    bruto = re.sub(rb"\r?\n", b"\r\n", bruto)
    fim = bruto.find(b"\r\n\r\n")
    cabeca, corpo = (bruto[:fim + 2], bruto[fim + 4:]) if fim >= 0 else (bruto + b"\r\n", b"")
    saida: list[list[bytes]] = []
    for linha in cabeca.split(b"\r\n")[:-1]:
        if linha[:1] in (b" ", b"\t") and saida:
            saida[-1][1] += linha + b"\r\n"
        elif b":" in linha:
            nome, valor = linha.split(b":", 1)
            saida.append([nome, valor + b"\r\n"])
    return [(n, v) for n, v in saida], corpo


def _nome(n: bytes) -> bytes:
    return n.strip().lower()


def _texto(v: bytes) -> str:
    return " ".join(v.decode("utf-8", "replace").split())


def recebidos(cab: list) -> list[str]:
    return [_texto(v) for n, v in cab if _nome(n) == b"received"]


def autent_locaweb(bruto: bytes) -> str:
    """Authentication-Results written by Locaweb: only those above the third Received (the MX's)."""
    vistos, saida = 0, []
    for n, v in campos(bruto)[0]:
        if _nome(n) == b"received":
            vistos += 1
            if vistos >= 3:
                break
        elif _nome(n) == b"authentication-results":
            saida.append(_texto(v))
    return "; ".join(saida).lower()


def cadeia_locaweb(rec: list[str]) -> bool:
    """The top three Received are Locaweb's: the second came from the third's server over the internal network."""
    if len(rec) < 3:
        return False
    por3 = re.search(r"\bby\s+([\w.-]+)", rec[2], re.I)
    de2 = re.match(r"from\s+([\w.-]+)\s+\(([^()]*)\)", rec[1], re.I)
    return bool(por3 and de2 and LOCAWEB.search(por3.group(1)) and INTERNO.search(de2.group(2))
                and de2.group(1).lower() == por3.group(1).lower())


def pela_conta(rec: list[str], remetente: str) -> bool:
    """Sent by logging into the From address's own Locaweb account (not from an AWS machine)."""
    if not cadeia_locaweb(rec):
        return False
    m = re.search(r"\(Authenticated sender:\s*([^\s)]+)\)\s*by\s+([\w.-]+)", rec[2], re.I)
    origem = rec[2].split(" by ", 1)[0]
    return bool(m and m.group(1).lower() == remetente.lower() and LOCAWEB.search(m.group(2))
                and re.search(r"\bwith\s+ESMTPSA\b", rec[2], re.I) and "amazonaws.com" not in origem.lower())


def _tags(valor: bytes) -> dict:
    tags = {}
    for parte in valor.split(b";"):
        if b"=" in parte:
            k, v = parte.split(b"=", 1)
            tags[k.strip().decode("ascii", "replace")] = re.sub(rb"\s+", b"", v)
    return tags


def _cab_relaxed(nome: bytes, valor: bytes) -> bytes:
    return _nome(nome).rstrip() + b":" + re.sub(rb"[\t ]+", b" ", re.sub(rb"\r?\n", b"", valor)).strip() + b"\r\n"


def _corpo_canonico(corpo: bytes, relaxed: bool) -> bytes:
    if relaxed:
        corpo = re.sub(rb"[\t ]+", b" ", re.sub(rb"[\t ]+\r\n", b"\r\n", corpo))
    corpo = re.sub(rb"(?:\r\n)*\Z", b"\r\n", corpo, count=1)
    return b"" if relaxed and corpo == b"\r\n" else corpo


def chave_dns(seletor: str, dominio: str) -> str:
    """The DKIM key record (TXT at <selector>._domainkey.<domain>)."""
    if not re.fullmatch(r"[a-z0-9._-]{1,200}", f"{seletor}.{dominio}", re.I):
        return ""
    import dns.resolver

    resposta = dns.resolver.resolve(f"{seletor}._domainkey.{dominio}", "TXT", lifetime=10)
    registros = [b"".join(r.strings).decode("ascii", "replace") for r in resposta]
    return next((r for r in registros if "p=" in r), "")


def dkim_valido(bruto: bytes, dominio: str, consultar=None, agora: float | None = None) -> bool:
    """A DKIM signature by the From domain (or a subdomain of it) checks out: rsa-sha256, body and headers."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    cab, corpo = campos(bruto)
    for nome, valor in cab:
        if _nome(nome) != b"dkim-signature":
            continue
        try:
            t = _tags(valor)
            d = t.get("d", b"").decode().lower()
            assinados = [h.lower() for h in t.get("h", b"").decode().split(":") if h]
            if (t.get("v") != b"1" or t.get("a") != b"rsa-sha256" or not d or "from" not in assinados
                    or not (d == dominio or d.endswith("." + dominio))):
                continue
            if t.get("x") and int(t["x"]) < (agora or time.time()):
                continue
            c = t.get("c", b"simple/simple").decode().lower().split("/")
            c_cab, c_corpo = c[0], (c[1] if len(c) > 1 else "simple")
            if c_cab not in ("simple", "relaxed") or c_corpo not in ("simple", "relaxed"):
                continue
            canon = _corpo_canonico(corpo, c_corpo == "relaxed")
            if t.get("l"):
                canon = canon[:int(t["l"])]
            if base64.b64encode(hashlib.sha256(canon).digest()) != t.get("bh"):
                continue
            dados, usados = b"", {}
            for h in assinados:  # repeated names take the instances from the bottom up
                instancias = [(n, v) for n, v in cab if _nome(n) == h.encode()]
                k = usados.get(h, 0)
                usados[h] = k + 1
                if k < len(instancias):
                    n, v = instancias[len(instancias) - 1 - k]
                    dados += _cab_relaxed(n, v) if c_cab == "relaxed" else n + b":" + v
            sem_b = SEM_B.sub(rb"\1", valor)
            dados += (_cab_relaxed(nome, sem_b) if c_cab == "relaxed" else nome + b":" + sem_b).rstrip()
            registro = _tags((consultar or chave_dns)(t["s"].decode(), d).encode())
            if registro.get("k", b"rsa") != b"rsa" or not registro.get("p"):
                continue
            chave = serialization.load_der_public_key(base64.b64decode(registro["p"]))
            if not isinstance(chave, rsa.RSAPublicKey) or chave.key_size < 1024:
                continue
            chave.verify(base64.b64decode(t["b"]), dados, padding.PKCS1v15(), hashes.SHA256())
            return True
        except Exception:
            continue
    return False


def confirmado(bruto: bytes, remetente: str, consultar=None) -> bool:
    """The From address is proven (see the module docstring). A second From header never passes (DKIM covers only one)."""
    cab, _ = campos(bruto)
    dominio = remetente.rsplit("@", 1)[-1].lower() if "@" in (remetente or "") else ""
    if not dominio or sum(_nome(n) == b"from" for n, _ in cab) != 1:
        return False
    return pela_conta(recebidos(cab), remetente) or dkim_valido(bruto, dominio, consultar)
