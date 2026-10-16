"""Tool `conversa_externa`: talk to a store, clinic or other business on the person's own WhatsApp, and keep the
conversation going (helpers/externas.py has the rules, helpers/navegador.py drives WhatsApp Web)."""

import importlib.util
import json
import sys
from pathlib import Path

from helpers.tool import Response, Tool

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())


def _carregar(nome: str, arquivo: str):
    caminho = RAIZ / "helpers" / arquivo
    antigo, mtime = sys.modules.get(nome), caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = mtime
        sys.modules[nome] = m
    return sys.modules[nome]


def ex():
    return _carregar("conversas_externas_helper", "externas.py")


def nav():
    return _carregar("conversas_externas_navegador", "navegador.py")


def dono_e_nome(context) -> tuple[str, str]:
    sep = sys.modules.get("login_usuarios_separacao")
    login = (sep.dono_contexto(context) if sep else str(context.get_data("dono") or "matheus")).lower()
    conv = sys.modules.get("login_usuarios_convidados")
    nome = ((conv.convidado(login) or {}).get("nome") if conv else "") or login.title()
    return login, nome


def avisar_matheus(texto: str) -> str:
    """Tell the owner on his phone (the WhatsApp plugin's bridge); returns the note for the agent."""
    p = sys.modules.get("whatsapp_ponte")
    try:
        erro = p.enviar("matheus", texto, tipo="progresso", reenviar=True) if p else "ponte indisponível"
    except Exception as exc:
        erro = str(exc)
    return " e o Matheus foi avisado" if not erro else f" (o aviso ao Matheus falhou: {str(erro)[:100]})"


class ConversaExterna(Tool):
    async def execute(self, acao: str = "listar", conversa: str = "", nome: str = "", telefone: str = "",
                      objetivo: str = "", texto: str = "", confirmado: str = "", motivo: str = "", **kwargs) -> Response:
        e, n = ex(), nav()
        login, dono = dono_e_nome(self.agent.context)
        r = lambda m: Response(message=m, break_loop=False)
        acao = str(acao or "listar").lower()
        try:
            if acao == "listar":
                d = e.carregar(login)
                abertas = [{"conversa": c["id"], "com": c["nome"], "telefone": c["telefone"], "estado": c["estado"],
                            "objetivo": c["objetivo"], "ultimas": e.resumo(c, 3)}
                           for c in d["conversas"] if c["estado"] in e.ABERTAS]
                return r(json.dumps(abertas, ensure_ascii=False) if abertas else "Nenhuma conversa externa aberta.")
            if acao == "estado":
                est = await n.estado(e, login, dono)
                return r(f"WhatsApp de {dono}: " + ("conectado." if est.get("logado") else
                         f"NÃO conectado. Chame acao \"conectar\" com o telefone de {dono}. (tela: {json.dumps(est)[:200]})"))
            if acao == "conectar":
                if not telefone:
                    return r(f"Preciso do número de WhatsApp de {dono} (com DDD). Pergunte a ele.")
                res = await n.conectar(e, login, dono, telefone)
                if res.get("logado"):
                    with e.transacao(login) as d:
                        d["numero"] = e.telefone(telefone)
                    return r(f"O WhatsApp de {dono} já está conectado.")
                with e.transacao(login) as d:
                    d["numero"] = e.telefone(telefone)
                return r(f"CÓDIGO: {res['codigo']}. Mande a {dono}, na língua dele, em mensagem própria e curta: no celular, abrir "
                         "o WhatsApp > Configurações (ou ⋮) > Aparelhos conectados > Conectar aparelho > \"Conectar com número de "
                         f"telefone\" e digitar o código {res['codigo']} (vale poucos minutos). Depois confira com acao \"estado\".")
            if acao == "abrir":
                c = e.abrir(login, nome, telefone, objetivo)
                return r(f"Conversa {c['id']} com {c['nome']} ({c['telefone']}) pronta. Agora mande a primeira mensagem com "
                         f"acao \"enviar\", conversa \"{c['id']}\": curta, na língua da loja (português no Brasil), dizendo que é "
                         f"o assistente de {dono} e perguntando o que ele quer saber.")
            if acao == "enviar":
                c = e.pode_enviar(login, conversa, texto, confirmado, dono)
                lidas = await n.enviar(e, login, dono, c["telefone"], texto)
                e.registrar_envio(login, c["id"], texto, confirmado)
                e.registrar_lidas(login, c["id"], lidas)
                return r(f"Enviado para {c['nome']}. Vou vigiar a conversa e te chamo quando responderem; não precisa "
                         "verificar. Diga a {dono} em uma linha o que perguntou.".replace("{dono}", dono))
            if acao == "ler":
                c = next(x for x in e.carregar(login)["conversas"] if x["id"] == conversa or x["telefone"] == conversa)
                res = await n.ler(e, login, dono, c["telefone"])
                novas = e.registrar_lidas(login, c["id"], res.get("mensagens") or [])
                return r(json.dumps({"novas": novas, "ultimas": e.resumo(e._conversa(e.carregar(login), c["id"]), 8),
                                     **({"texto_da_tela": res["texto_da_tela"]} if res.get("texto_da_tela") else {})},
                                    ensure_ascii=False))
            if acao == "esperar_dono":
                c = e.esperar_dono(login, conversa, texto or motivo)
                return r(f"Ok: a conversa com {c['nome']} espera a decisão de {dono}. Pergunte a ele (na língua dele) e, "
                         f"quando ele responder, siga com acao \"enviar\" e `confirmado` = as palavras dele.")
            if acao == "encerrar":
                c = e.encerrar(login, conversa, motivo or "concluída")
                return r(f"Conversa com {c['nome']} encerrada ({c['motivo']}). Não vigio mais.")
            if acao == "responder_por_mim":
                reg = e.salvar_preferencias(login, kwargs.get("respostas") or {})
                avisado = avisar_matheus(e.texto_preferencias(dono, reg)) if login != "matheus" else ""
                return r(f"Preferências de {dono} guardadas{avisado}. Diga a ele, na língua dele, que o Matheus vai montar "
                         "isso com essas respostas e que você avisa quando estiver pronto. Não prometa data e não comece a "
                         "responder ninguém por ele.")
            return r("acao desconhecida: use listar, estado, conectar, abrir, enviar, ler, esperar_dono, encerrar ou "
                     "responder_por_mim")
        except StopIteration:
            return r(f"conversa {conversa} não encontrada (veja acao \"listar\")")
        except (e.Recusa, n.SemWhatsApp) as exc:
            return r(f"NÃO FEITO: {exc}")
