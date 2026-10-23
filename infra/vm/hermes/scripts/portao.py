"""Portão das rotinas no Hermes (migração, fase 5): o mesmo portão do A0 (/a0/usr/plugins/rotinas/helpers/portao.py:
ids dos e-mails e eventos novos pelo conector Google e um arquivo, comparados com a última rodada), como "script" do
cron do Hermes, cujo contrato é o mesmo de onde a ideia veio: se a ÚLTIMA linha impressa for {"wakeAgent": false}, a
rodada é pulada sem chamar o modelo; senão o que foi impresso entra no pedido da rodada (o que mudou).
Uso (o subir.sh cria um embrulho por rotina com portão): python3 portao.py <uuid da rotina no A0>.
Fonte com erro = roda (nunca "nada mudou"); o 1º da manhã roda inteiro; o estado novo só vale quando a rodada termina
bem (rotinas_hermes.py confirma). Fora do ar ou no ensaio (estado só leitura), a rodada roda inteira."""
import asyncio
import importlib.util
import json
import sys
from pathlib import Path

PLUGINS = Path("/a0/usr/plugins")
GOOGLE = "http://hermes-mcp:8765/mcp"


def portao():
    spec = importlib.util.spec_from_file_location("portao_a0", PLUGINS / "rotinas" / "helpers" / "portao.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


async def chamar(ferramenta: str, argumentos: dict) -> tuple:
    """Uma ferramenta do conector Google (o mesmo hermes-mcp que o Hermes usa), pelo cliente MCP do próprio Hermes."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    try:
        async with streamablehttp_client(GOOGLE) as (leitura, escrita, _):
            async with ClientSession(leitura, escrita) as s:
                await s.initialize()
                r = await s.call_tool(ferramenta, argumentos)
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    texto = "\n".join(str(getattr(c, "text", "") or "") for c in (getattr(r, "content", None) or []))
    return not getattr(r, "isError", False), texto


def main(uuid: str) -> None:
    P = portao()
    cfg = P.config(uuid)
    if not cfg:
        return  # sem portão: nada impresso, a rodada roda como sempre
    decisao = asyncio.run(P.avaliar(uuid, cfg, chamar))
    if decisao["rodar"]:
        try:
            P.preparar(uuid, decisao)
        except OSError:
            pass  # ensaio (só leitura): roda sem guardar o estado novo
        print(P.contexto(decisao))
        return
    try:
        P.registrar_pulo(uuid, decisao)
        P.descartar(uuid)
    except OSError:
        print("(portão: nada mudou, mas o estado não pôde ser gravado; a rodada roda)")
        return
    print(json.dumps({"wakeAgent": False, "motivo": P.PULO}))


if __name__ == "__main__":
    try:
        main(sys.argv[1] if len(sys.argv) > 1 else "")
    except Exception as exc:  # o portão nunca impede uma rodada
        print(f"(portão falhou, a rodada roda inteira: {type(exc).__name__}: {str(exc)[:200]})")
