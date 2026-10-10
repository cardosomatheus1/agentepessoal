"""Tool `fios`: read the panorama and keep the person's register of loose ends."""

import importlib.util
import json
import sys
from pathlib import Path

from helpers.tool import Response, Tool


def _fios():
    nome = "fios_soltos_helper"
    caminho = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists()) / "helpers" / "fios.py"
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


def _ponte():
    """The phone bridge of plugins/whatsapp (Telegram/WhatsApp), loaded by path."""
    if "whatsapp_ponte" in sys.modules:
        return sys.modules["whatsapp_ponte"]
    caminho = Path("/a0/usr/plugins/whatsapp/helpers/ponte.py")
    if not caminho.exists():
        return None
    spec = importlib.util.spec_from_file_location("whatsapp_ponte", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    modulo._mtime = caminho.stat().st_mtime
    sys.modules["whatsapp_ponte"] = modulo
    return modulo


def dono(context) -> str:
    sep = sys.modules.get("login_usuarios_separacao")
    return (sep.dono_contexto(context) if sep else (context.get_data("dono") or "matheus")) or "matheus"


def _lista(valor):
    if isinstance(valor, str):
        try:
            valor = json.loads(valor)
        except Exception:
            return [v.strip() for v in valor.split(",") if v.strip()]
    return valor if isinstance(valor, list) else ([valor] if valor else [])


class Fios(Tool):
    async def execute(self, acao: str = "listar", fios: list | str | None = None, resolvidos: list | str | None = None,
                      id: str = "", ate: str = "", horas: int = 72, **kwargs) -> Response:
        f = _fios()
        login = dono(self.agent.context)
        acao = str(acao or "listar").lower()
        if acao == "coletar":
            return Response(message=f.coletar(login, int(horas or 72), ignorar=self.agent.context.id), break_loop=False)
        if acao in ("salvar", "atualizar", "criar"):
            criados, atualizados, fechados = f.mesclar(login, _lista(fios), _lista(resolvidos))
            return Response(message=f"Registro salvo: {criados} novo(s), {atualizados} atualizado(s), {fechados} resolvido(s).",
                            break_loop=False)
        if acao in ("resolver", "fechar"):
            ids = _lista(resolvidos) or _lista(id)
            _, _, fechados = f.mesclar(login, [], ids)
            return Response(message=f"{fechados} fio(s) marcado(s) como resolvido(s).", break_loop=False)
        if acao == "avisar":
            ponte = _ponte()
            if ponte is None:
                return Response(message="Ponte do celular indisponível: escreva os itens na resposta final.", break_loop=False)
            enviados, falhas = [], []
            for fid in _lista(id) + _lista(fios):
                fid = str(fid.get("id") if isinstance(fid, dict) else fid)
                fio = f.obter(login, fid)
                if not fio:
                    falhas.append(f"{fid}: não existe no registro")
                    continue
                urgente = str(fio.get("prioridade", "")).lower() == "alta" and bool(kwargs.get("urgente") or fio.get("urgente"))
                erro = ponte.enviar(login, f.mensagem(fio, urgente), botoes=f.botoes(login, fid),
                                    tipo="urgente" if urgente else "progresso")
                (falhas if erro else enviados).append(f"{fid}: {erro}" if erro else fid)
            texto = f"Enviados ao celular com botões: {', '.join(enviados) or 'nenhum'}."
            if falhas:
                texto += " Falhas: " + "; ".join(falhas) + " — esses vão por escrito na resposta final."
            return Response(message=texto, break_loop=False)
        if acao == "adiar":
            if not id or not ate:
                return Response(message="Diga o `id` e a data `ate` (AAAA-MM-DD).", break_loop=False)
            f.mesclar(login, [{"id": id, "estado": "adiado", "adiar_ate": ate}])
            return Response(message=f"Fio {id} adiado até {ate}.", break_loop=False)
        lista = f.abertos(login, 30)
        if not lista:
            return Response(message="Nenhum fio solto em aberto.", break_loop=False)
        return Response(message="\n".join("- " + f.linha(x) for x in lista), break_loop=False)
