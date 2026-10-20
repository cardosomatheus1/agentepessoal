"""`conector`: list a connector's tools (google, github) and activate the ones that are not in the chat's tool list
(helpers/sob_demanda.py). Activating only puts the tool in the list: the call itself goes the normal way (owner check,
approvals reviewer)."""

import importlib.util
import json
import sys
from pathlib import Path

from helpers.tool import Response, Tool

_RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
_spec = importlib.util.spec_from_file_location("conectores_carregar", _RAIZ / "helpers" / "carregar.py")
carregar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(carregar)
DONOS = _RAIZ / "donos.json"


def donos() -> dict:
    try:
        return json.loads(DONOS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def dono_da_conversa(context) -> str:
    sep = sys.modules.get("login_usuarios_separacao")
    return sep.dono_contexto(context) if sep else (context.get_data("dono") or "matheus")


def catalogo_mcp(agent) -> list:
    from helpers.mcp_handler import MCPConfig

    return MCPConfig.get_for_agent(agent).get_tools()


def _lista(valor) -> list[str]:
    if isinstance(valor, str):
        valor = valor.replace(";", ",").split(",")
    return [str(v).strip() for v in (valor or []) if str(v).strip()]


class Conector(Tool):
    async def execute(self, acao: str = "listar", conector: str = "", ferramentas=None, ferramenta: str = "",
                      busca: str = "", **kwargs) -> Response:
        def r(texto: str) -> Response:
            return Response(message=texto, break_loop=False)

        s = carregar.modulo("sob_demanda")
        acao = str(acao or "listar").strip().lower()
        conector = str(conector or "").strip().lower()
        nomes = _lista(ferramentas) + _lista(ferramenta)
        if not conector and nomes:
            conector = s.servidor_e_nome(nomes[0])[0] or (nomes[0].split("_", 1)[0] if "_" in nomes[0] else "")
        cat = s.catalogo(catalogo_mcp(self.agent))
        servidores = sorted({s.servidor_e_nome(n)[0] for n in cat} - {""})
        eu = dono_da_conversa(self.agent.context)
        meus = [x for x in servidores if donos().get(x) in (None, "", eu)]
        if conector not in meus:
            if conector in servidores:
                return r(f"O conector `{conector}` está ligado à conta de outra pessoa: não pode ser usado nesta conversa.")
            return r(f"Conectores desta conversa: {', '.join(meus) or 'nenhum'}. Diga qual em `conector`.")
        ativas = s.ativas(self.agent.context)

        if acao in ("listar", "lista", "list"):
            return r(s.listar(cat, conector, ativas, False, str(busca or "")))

        if acao in ("descrever", "describe", "manual"):
            if not nomes:
                return r("Diga qual em `ferramenta` (ex.: \"create_doc\").")
            textos = [s.descrever(cat, s.nome_completo(conector, n)) or f"`{n}` não existe no conector `{conector}`."
                      for n in nomes[:3]]
            return r("\n\n".join(textos))

        if acao in ("ativar", "activate", "usar"):
            if not nomes and conector == "github":
                nomes = list(s.GITHUB_CODIGO)
            if not nomes:
                return r("Diga quais em `ferramentas` (veja com acao \"listar\").")
            completos = [s.nome_completo(conector, n) for n in nomes]
            existem = [n for n in completos if n in cat]
            faltam = [n for n in completos if n not in cat]
            novas = s.ativar(self.agent.context, existem)
            ja = [n for n in existem if n not in novas]
            partes = []
            if novas:
                partes.append(f"Ativadas nesta conversa: {', '.join(novas)}. Elas entram na sua lista de ferramentas a "
                              "partir da próxima chamada: chame-as normalmente (as regras e aprovações valem igual).")
            if ja:
                partes.append(f"Já estavam na lista: {', '.join(ja)}.")
            if faltam:
                partes.append(f"Não existem no conector `{conector}`: {', '.join(faltam)} (veja com acao \"listar\").")
            return r(" ".join(partes))

        return r("`acao`: listar | ativar | descrever.")
