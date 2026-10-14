"""The "🖥️ Resolver aqui" button: on Telegram it opens a page inside the app (web_app), on WhatsApp the link goes in
the text. Run from the repository root: python3 infra/vm/tests/test_botao_app.py (boto3 for the import; no AWS)."""

import importlib.util
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("ponte_app_teste", RAIZ / "infra" / "vm" / "ponte_whatsapp.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

falhas = []


def ok(cond, msg):
    if not cond:
        falhas.append(msg)


app = {"titulo": "🖥️ Resolver aqui", "url": "https://agente.exemplo.com/api/plugins/navegador_visual/tela?t=x"}
botoes = [{"id": "ap:1", "titulo": "Aprovar"}]
ok(p.teclado(None, app) == {"inline_keyboard": [[{"text": "🖥️ Resolver aqui", "web_app": {"url": app["url"]}}]]},
   f"só o botão do app: {p.teclado(None, app)}")
t = p.teclado(botoes, app)
ok(t and len(t["inline_keyboard"]) == 2 and t["inline_keyboard"][0][0]["callback_data"] == "ap:1", f"botões e app: {t}")
ok(p.teclado(None, {"titulo": "x", "url": "http://inseguro"}) is None, "web_app só com https")
ok(p.teclado(None, None) is None, "sem botões, sem teclado")
ok(p.texto_com_app("Resolva o captcha.", app).endswith(f"🖥️ Resolver aqui: {app['url']}"), "WhatsApp leva o link no texto")
ok(p.texto_com_app("Oi", None) == "Oi", "sem app o texto não muda")

enviados = []
p.tg = lambda metodo, dados: enviados.append(dados) or {}
p.tg_texto("123", "Resolva o captcha na Redesim.", None, app)
ok(enviados and enviados[-1].get("reply_markup", {}).get("inline_keyboard", [[{}]])[0][0].get("web_app"), f"Telegram: {enviados[-1:]}")
enviados.clear()
p.tg_texto("123", "x" * (p.TG_LIMITE + 10), None, app)
ok(len(enviados) == 2 and "reply_markup" not in enviados[0] and "reply_markup" in enviados[1], "botão só na última parte")

print("\n".join("FALHOU: " + f for f in falhas) or "botao_app: ok")
sys.exit(1 if falhas else 0)
