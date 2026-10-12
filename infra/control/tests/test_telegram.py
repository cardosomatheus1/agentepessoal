"""Telegram link codes of the control function: one use, 15 minutes, the chats already linked are told.
No network and no AWS: the settings store and the Telegram API are replaced. Run from the repository root:
python3 infra/control/tests/test_telegram.py"""

import importlib.util
import json
import sys
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]


class Loja:
    """Stand-in for the SSM SecureString the control function keeps its settings in."""

    def __init__(self, cfg):
        self.cfg = json.loads(json.dumps(cfg))

    def config(self, fresca=False):
        return json.loads(json.dumps(self.cfg))

    def gravar(self, cfg):
        self.cfg = json.loads(json.dumps(cfg))


def carregar(loja: Loja, enviados: list):
    wa = types.ModuleType("whatsapp")
    wa.config, wa.gravar, wa.save_config = loja.config, loja.gravar, lambda u: loja.config()
    wa._text = lambda corpo, codigo=200: {"statusCode": codigo, "body": corpo}
    wa.QUEUE_URL = "fila"
    wa.sqs = types.SimpleNamespace(send_message=lambda **kw: enviados.append(("fila", json.loads(kw["MessageBody"]))))
    sys.modules["whatsapp"] = wa
    spec = importlib.util.spec_from_file_location("telegram_teste", RAIZ / "infra" / "control" / "telegram.py")
    t = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(t)
    t.api = lambda metodo, dados: enviados.append((metodo, dados)) or {"ok": True}
    return t


def start(t, chat, texto, segredo="s3gredo", nome="Ana"):
    corpo = json.dumps({"message": {"chat": {"id": chat}, "text": texto, "from": {"first_name": nome}}}).encode()
    return t.receive(corpo, {"x-telegram-bot-api-secret-token": segredo}, lambda: "running", None, None)


def main() -> int:
    falhas = []

    def ok(cond, msg):
        if not cond:
            falhas.append(msg)

    loja, enviados = Loja({"tg_bot": "agente_bot", "tg_segredo": "s3gredo", "tg_token": "x",
                           "tg_codigos": {"antigo123": "matheus"}, "tg_chats": {"111": "matheus"}}), []
    t = carregar(loja, enviados)
    agora = 1_800_000_000.0

    start(t, "999", "/start antigo123")
    ok("999" not in loja.cfg["tg_chats"], "código antigo (permanente) não vale mais")
    ok(any("privado" in d.get("text", "") for m, d in enviados if m == "sendMessage"), "chat estranho ouve que é privado")

    url = t.novo_link("matheus", agora)
    codigo = url.rsplit("=", 1)[1]
    ok(url.startswith("https://t.me/agente_bot?start=") and len(codigo) >= 16, f"link novo: {url}")
    ok(loja.cfg["tg_codigos"][codigo]["ate"] == agora + 15 * 60, "vale 15 minutos")
    ok("antigo123" not in loja.cfg["tg_codigos"], "gerar link limpa os códigos velhos")

    login, antigos = t.vincular(loja.config(), "222", codigo, "Ana, @ana", agora + 60)
    ok(login == "matheus" and loja.cfg["tg_chats"].get("222") == "matheus", "código bom liga o chat")
    ok(codigo not in loja.cfg["tg_codigos"], "e é gasto na mesma gravação")
    ok(antigos == ["111"], "devolve os chats que já estavam ligados")
    aviso = [d for m, d in enviados if m == "sendMessage" and d.get("chat_id") == "111"]
    ok(aviso and "Outro chat" in aviso[-1]["text"] and "Ana, @ana" in aviso[-1]["text"], f"o chat antigo é avisado: {aviso}")
    ok(t.vincular(loja.config(), "333", codigo, "Golpe", agora + 61) == ("", []), "o mesmo código não vale 2 vezes")
    ok("333" not in loja.cfg["tg_chats"], "nem liga o segundo chat")

    velho = t.novo_link("matheus", agora).rsplit("=", 1)[1]
    ok(t.vincular(loja.config(), "444", velho, "x", agora + 15 * 60 + 1) == ("", []), "passou de 15 min, não vale")
    a = t.novo_link("matheus", agora).rsplit("=", 1)[1]
    b = t.novo_link("matheus", agora + 5).rsplit("=", 1)[1]
    ok(a not in loja.cfg["tg_codigos"] and b in loja.cfg["tg_codigos"], "link novo derruba o anterior não usado")
    f = t.novo_link("fernanda", agora + 6).rsplit("=", 1)[1]
    ok(b in loja.cfg["tg_codigos"] and f in loja.cfg["tg_codigos"], "o de outra pessoa continua valendo")

    r = start(t, "555", f"/start {f}", segredo="errado")
    ok(r["statusCode"] == 403 and "555" not in loja.cfg["tg_chats"], "webhook sem o segredo do Telegram é recusado")
    # receive() uses the real clock: codes made at `agora` (2027) are still good today
    start(t, "555", f"/start {f}", nome="Fê")
    ok(loja.cfg["tg_chats"].get("555") == "fernanda", "pelo webhook, /start com código bom liga")
    ok(any(d.get("chat_id") == "555" and "Pronto, fernanda" in d.get("text", "") for m, d in enviados if m == "sendMessage"),
       "e confirma no chat novo")

    ok(t.desligar("matheus") == 2 and set(loja.cfg["tg_chats"]) == {"555"}, "desconectar tira todos os chats do login")
    s = t.status()
    ok(s["tg_chats_por_login"] == {"fernanda": 1} and "tg_links" not in s, f"status sem link permanente: {s}")

    for f_ in falhas:
        print("FALHA", f_)
    print("telegram:", "ok" if not falhas else f"{len(falhas)} falha(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
