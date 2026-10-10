"""Tool `rascunho`: a reply drafted in the person's style, delivered to the phone with buttons (never sent by the agent)."""

import importlib.util
import sys
from pathlib import Path

from helpers.tool import Response, Tool


def _carregar(nome: str, caminho: Path):
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


def aux():
    raiz = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
    return _carregar("auxiliar_helper", raiz / "helpers" / "auxiliar.py")


def ponte():
    if "whatsapp_ponte" in sys.modules:
        return sys.modules["whatsapp_ponte"]
    return _carregar("whatsapp_ponte", Path("/a0/usr/plugins/whatsapp/helpers/ponte.py"))


def dono(context) -> str:
    sep = sys.modules.get("login_usuarios_separacao")
    return (sep.dono_contexto(context) if sep else (context.get_data("dono") or "matheus")) or "matheus"


class Rascunho(Tool):
    async def execute(self, acao: str = "criar", para: str = "", assunto: str = "", texto: str = "", pedido: str = "",
                      referencia: str = "", perfil: str = "", nova_versao=False, **kwargs) -> Response:
        a = aux()
        login = dono(self.agent.context)
        acao = str(acao or "criar").lower()
        if acao == "estilo_salvar":
            if len(perfil.strip()) < 200:
                return Response(message="O `perfil` precisa descrever o estilo (saudação, despedida, tom, tamanho, "
                                        "vocabulário, exemplos curtos).", break_loop=False)
            a.salvar_estilo(login, perfil)
            return Response(message="Perfil de estilo salvo; os próximos rascunhos seguem ele.", break_loop=False)
        if acao == "amostras":
            msgs = a.mensagens_dele(login)
            return Response(message=f"{len(msgs)} mensagens que ele digitou no celular (do mais antigo ao mais novo):\n"
                                    + "\n".join(f"- {m}" for m in msgs) if msgs else "(nenhuma mensagem dele no celular ainda)",
                            break_loop=False)
        if acao == "estilo":
            return Response(message=a.estilo(login) or "(ainda sem perfil de estilo)", break_loop=False)
        if acao == "listar":
            pend = [r for r in a.carregar(login)["rascunhos"] if r["estado"] == "pendente"]
            return Response(message="\n".join(f"- [{r['id']}] {r['para']} — {r['assunto']}" for r in pend) or "(nenhum)",
                            break_loop=False)
        if acao != "criar":
            return Response(message="acao: criar | listar | amostras | estilo | estilo_salvar", break_loop=False)
        if not (para.strip() and assunto.strip() and texto.strip()):
            return Response(message="Diga `para`, `assunto` e `texto` (o rascunho pronto).", break_loop=False)
        if "/a0/" in texto:
            return Response(message="Tire caminhos de pasta do rascunho.", break_loop=False)
        anterior = a.ja_tratado(login, para, assunto)
        if anterior and not str(nova_versao).lower() in ("true", "1", "sim"):
            situacao = {"pendente": "está esperando ele decidir", "usado": "ele já usou", "descartado": "ele dispensou"}
            return Response(message=f"Esse e-mail já tem rascunho [{anterior['id']}] ({situacao.get(anterior['estado'], anterior['estado'])}); "
                                    "não mande de novo. Use nova_versao: true só quando ele pedir ajuste.", break_loop=False)
        r = a.novo_rascunho(login, para, assunto, texto, pedido, referencia)
        erro = ponte().enviar(login, a.mensagem_rascunho(r), botoes=a.botoes_rascunho(login, r["id"]), tipo="progresso")
        if erro:
            return Response(message=f"Rascunho {r['id']} salvo, mas não chegou ao celular: {erro}", break_loop=False)
        return Response(message=f"Rascunho {r['id']} enviado ao celular com os botões Usar / Ajustar / Deixa. "
                                "Nada foi enviado ao destinatário.", break_loop=False)
