"""Tool `iniciativa`: the context for deciding on an unprompted message, sending it, and learning."""

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


def _ini():
    raiz = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
    return _carregar("iniciativa_helper", raiz / "helpers" / "iniciativa.py")


def _ponte():
    if "whatsapp_ponte" in sys.modules:
        return sys.modules["whatsapp_ponte"]
    caminho = Path("/a0/usr/plugins/whatsapp/helpers/ponte.py")
    return _carregar("whatsapp_ponte", caminho) if caminho.exists() else None


def dono(context) -> str:
    sep = sys.modules.get("login_usuarios_separacao")
    return (sep.dono_contexto(context) if sep else (context.get_data("dono") or "matheus")) or "matheus"


class Iniciativa(Tool):
    async def execute(self, acao: str = "contexto", titulo: str = "", texto: str = "", tipo: str = "ideia",
                      aprendizado: str = "", candidatos: list | None = None, arquivo: str = "",
                      **kwargs) -> Response:
        ini = _ini()
        login = dono(self.agent.context)
        acao = str(acao or "contexto").lower()
        if acao == "contexto":
            return Response(message=ini.contexto(login, ignorar=self.agent.context.id), break_loop=False)
        if acao == "candidatos":
            return Response(message=ini.avaliar(login, candidatos or []), break_loop=False)
        if acao == "aprender":
            ini.aprender(login, aprendizado or texto)
            return Response(message="Anotado nos aprendizados.", break_loop=False)
        if acao == "enviar":
            if not titulo.strip() or not texto.strip():
                return Response(message="Diga `titulo` e `texto`.", break_loop=False)
            ok, motivo = ini.pode_enviar(login)
            if not ok:
                return Response(message=f"Não enviado: {motivo}. Responda SEM NOVIDADE.", break_loop=False)
            ponte = _ponte()
            if ponte is None:
                return Response(message="Ponte do celular indisponível.", break_loop=False)
            anexo = ""
            if arquivo:
                anexo, erro = ini.para_celular(arquivo)
                if erro:
                    return Response(message=f"Não enviado: {erro}. Corrija o `arquivo` (precisa estar em /a0/usr).",
                                    break_loop=False)
            iid = ini.registrar(login, titulo.strip(), texto.strip(), str(tipo or "ideia").lower())
            if anexo:  # the file first, so the message with the buttons stays last
                erro = ponte.enviar(login, arquivo=anexo, legenda=f"💡 {titulo.strip()}", tipo="progresso")
                if erro:
                    return Response(message=f"Falhou ao enviar o arquivo: {erro}", break_loop=False)
            erro = ponte.enviar(login, ini.mensagem(titulo, texto), botoes=ini.botoes(login, iid), tipo="progresso")
            if erro:
                return Response(message=f"Falhou ao enviar: {erro}", break_loop=False)
            return Response(message=f"Iniciativa {iid} enviada ao celular com botões. Responda SEM NOVIDADE.", break_loop=False)
        return Response(message="acao: contexto | candidatos | enviar | aprender", break_loop=False)
