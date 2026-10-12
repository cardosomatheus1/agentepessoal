"""Tests of the approvals rules (no model calls). Run with implantar.py (staging copy) or inside the container."""
import importlib.util
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


class Falha(Exception):
    pass


def ok(cond, msg):
    if not cond:
        raise Falha(msg)


class Suite:
    def __init__(self):
        spec = importlib.util.spec_from_file_location("aprovacoes_revisor_teste", RAIZ / "helpers" / "revisor.py")
        self.rv = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.rv)
        self.resultados = []

    def t_instagram_sem_perguntar(self):
        rv, cfg = self.rv, {}
        msg = {"categoria": "mensagem_terceiros", "resumo": "Enviar no Instagram para @annasaude.marmitas: «Oi, pessoal»"}
        ok(rv.livre_instagram(msg, "browser", {"action": "press", "key": "Enter"}, "enviar a resposta aprovada no Direct", cfg),
           "mensagem no Direct do Instagram passa sem perguntar")
        com = {"categoria": "publicar", "resumo": "Publicar comentário no post"}
        ok(rv.livre_instagram(com, "browser", {"action": "click"}, "publicar o comentário aprovado no Instagram", cfg),
           "comentário no Instagram passa")
        unsend = {"categoria": "apagar", "resumo": "Cancelar o envio da mensagem duplicada"}
        ok(rv.livre_instagram(unsend, "browser", {"action": "click"}, "Unsend na conversa do Direct do Instagram", cfg),
           "cancelar envio de mensagem no Instagram passa")
        ok(not rv.livre_instagram({"categoria": "apagar", "resumo": "Apagar a conta"}, "browser", {"action": "click"},
                                  "apagar a conta do instagram", cfg), "apagar conta do Instagram continua perguntando")
        ok(not rv.livre_instagram({"categoria": "mensagem_terceiros", "resumo": "Enviar e-mail ao cliente"}, "browser",
                                  {"action": "click"}, "enviar o e-mail no Gmail", cfg), "e-mail fora do Instagram continua perguntando")
        ok(not rv.livre_instagram({"categoria": "pagamento", "resumo": "Pagar anúncio no Instagram"}, "browser",
                                  {"action": "click"}, "pagar impulsionamento no Instagram", cfg), "pagamento nunca passa por aqui")
        ok(not rv.livre_instagram(msg, "code_execution_tool", {}, "instagram", cfg), "só ações de navegador")
        ok(not rv.livre_instagram(msg, "browser", {"action": "press"}, "Direct do Instagram", {"instagram_sem_perguntar": False}),
           "desligável na configuração")
        ok(rv.veredito({"pagamento": "nunca"}, {"categoria": "pagamento", "sempre_permitida": True}) == "nunca",
           "regra nunca continua acima de tudo")

    async def rodar(self, so=""):
        for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
            try:
                getattr(self, nome)()
                self.resultados.append({"teste": nome, "ok": True})
            except Exception as exc:
                self.resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                        "onde": traceback.format_exc().splitlines()[-3:]})
        return {"passou": sum(r["ok"] for r in self.resultados), "total": len(self.resultados), "resultados": self.resultados}
