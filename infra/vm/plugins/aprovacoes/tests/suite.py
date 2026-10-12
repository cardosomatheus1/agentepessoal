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
        ok(rv.livre_instagram(msg, "browser", {"action": "press", "key": "Enter"}, "enviar a resposta no Direct do Instagram", cfg),
           "mensagem no Instagram passa sem perguntar")
        ok(not rv.livre_instagram({"categoria": "publicar", "resumo": "Publicar no Instagram"}, "browser", {"action": "click"},
                                  "publicar no Instagram", cfg), "publicar (pode ser anúncio/impulsionar) continua perguntando")
        ok(not rv.livre_instagram({"categoria": "apagar", "resumo": "Cancelar o envio da mensagem no Instagram"}, "browser",
                                  {"action": "click"}, "Unsend no Direct do Instagram", cfg),
           "cancelar envio/apagar continua perguntando (CLAUDE.md: destrutivo só com ordem dele)")
        ok(not rv.livre_instagram({"categoria": "mensagem_terceiros", "resumo": "Enviar e-mail ao cliente"}, "browser",
                                  {"action": "click"}, "vou seguir e enviar o e-mail no Gmail", cfg),
           "palavra comum ('seguir') fora do Instagram não libera")
        ok(not rv.livre_instagram({"categoria": "mensagem_terceiros", "resumo": "Responder comentário no YouTube"}, "browser",
                                  {"action": "click"}, "curtir e comentar no YouTube", cfg), "curtir/comentar em outro site não libera")
        ok(not rv.livre_instagram({"categoria": "pagamento", "resumo": "Pagar anúncio no Instagram"}, "browser",
                                  {"action": "click"}, "pagar impulsionamento no Instagram", cfg), "pagamento nunca passa por aqui")
        ok(not rv.livre_instagram(msg, "code_execution_tool", {}, "instagram", cfg), "só ações de navegador")
        ok(not rv.livre_instagram(msg, "browser", {"action": "press"}, "Direct do Instagram", {"instagram_sem_perguntar": False}),
           "desligável na configuração")
        ok(rv.veredito({"pagamento": "nunca"}, {"categoria": "pagamento", "sempre_permitida": True}) == "nunca",
           "regra nunca continua acima de tudo")

    def t_teclas_de_edicao_nao_param_a_rodada(self):
        rv = self.rv
        for tecla in ("Control+A", "Backspace", "Delete"):
            ok(not rv.precisa_revisao("browser", {"action": "press", "key": tecla}, "apagar o rascunho do campo antes de digitar"),
               f"{tecla} para esvaziar o campo não passa pelo revisor")
        ok(rv.precisa_revisao("browser", {"action": "press", "key": "Enter"}, "enviar a mensagem no Direct"),
           "Enter (envia) continua passando pelo revisor")
        ok(rv.precisa_revisao("browser", {"action": "click", "ref": 3}, "apagar a conversa"), "clique de apagar continua revisado")

    def t_meta_da_raiz_sem_perguntar(self):
        rv, cfg = self.rv, {}
        livre = lambda cat, resumo, intencao="": rv.livre_meta_raiz({"categoria": cat, "resumo": resumo}, "browser",  # noqa: E731
                                                                    {"action": "click", "ref": 4}, intencao, cfg)
        ok(livre("chaves_acesso", "No Meta Graph API, trocar o token de acesso por um token de longa duração e conferir sua expiração."),
           "estender o token de leitura passa (12/10: perguntou duas vezes)")
        ok(livre("contas_reais", "No Facebook, autorizar o app Raiz Prospecção a ler a Página e a @raiz.connect",
                 "dialog de permissão em facebook.com/v26.0/dialog/oauth com instagram_basic"), "autorizar a leitura passa")
        ok(livre("chaves_acesso", "Gerar token de acesso no Explorador da Graph API com instagram_basic e pages_read_engagement"),
           "gerar o token no Explorador passa")
        ok(livre("chaves_acesso", "No site aberto no navegador, gerar um token de usuário de longa duração."),
           "estender pelo nome que o classificador deu em 12/10 também passa")
        ok(not livre("chaves_acesso", "Gerar token no app Barber Dock (2229462691177967)"), "Barber Dock nunca por aqui")
        ok(not livre("contas_reais", "Alterar a conta de anúncios act_1384895845137880 no Gerenciador da Meta"), "conta de anúncio, não")
        ok(not livre("contas_reais", "Autorizar business_management no app da Meta"), "gerenciar o portfólio da empresa, não")
        ok(not livre("chaves_acesso", "Revogar o token de acesso do app da Meta"), "revogar, não")
        ok(not livre("chaves_acesso", "Gerar token do WhatsApp Business no app da Meta"), "WhatsApp Business, não")
        ok(not livre("pagamento", "Adicionar cartão no Meta for Developers"), "pagamento nunca")
        ok(not livre("chaves_acesso", "Gerar chave de API no Google Cloud"), "fora da Meta, não")
        ok(not rv.livre_meta_raiz({"categoria": "chaves_acesso", "resumo": "token de acesso no Graph API"}, "browser", {},
                                  "", {"instagram_sem_perguntar": False}), "desligável na configuração")

    async def rodar(self, so=""):
        for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
            try:
                getattr(self, nome)()
                self.resultados.append({"teste": nome, "ok": True})
            except Exception as exc:
                self.resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                        "onde": traceback.format_exc().splitlines()[-3:]})
        return {"passou": sum(r["ok"] for r in self.resultados), "total": len(self.resultados), "resultados": self.resultados}
