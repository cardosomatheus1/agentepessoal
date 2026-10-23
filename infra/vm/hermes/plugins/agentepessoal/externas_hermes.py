"""Conversas externas pelo WhatsApp Web da própria pessoa (decisão 3 do Matheus: continuam) no Hermes (virada, fase 8).

As MESMAS regras e o mesmo código do A0 (conversas_externas/helpers/externas.py e navegador.py, a ferramenta
`conversa_externa` e o vigia do job_loop _48_vigiar_conversas.py); só três pontos mudam:
- o navegador: o do Hermes desta instância, por CDP (BROWSER_CDP_URL). No principal é o do Matheus (perfil `shared`);
  cada convidado tem o próprio Hermes (hermes/convidado.sh) com o navegador no perfil dele (pessoa_<login>), então a aba
  do WhatsApp Web é sempre da pessoa certa (no A0 era o navegador_por_pessoa);
- quem esta instância vigia: o convidado só a dele; o principal, todas menos as dos convidados;
- "manter acordada a VM" enquanto uma loja pode responder: uma marca em /opt/data/agentepessoal/acordado que o
  watchdog.sh do host lê (no A0 era gravar o arquivo da conversa).
O que o A0 entregava na conversa (resposta de uma loja, mensagem não lida para responder) vai pela ponte (/conversa)."""
from __future__ import annotations

import importlib.util
import os
import sys
import time
from pathlib import Path

PLUGINS = Path("/a0/usr/plugins")
RAIZ = PLUGINS / "conversas_externas"
ACORDADO = Path("/opt/data/agentepessoal/acordado")
CONVIDADOS = PLUGINS / "login_usuarios" / "helpers" / "convidados.py"


def _modulo(nome: str, caminho: Path):
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._mtime = mtime
        sys.modules[nome] = m
    return sys.modules[nome]


def _convidados():
    return _modulo("login_usuarios_convidados", CONVIDADOS)


def meus_logins(todos: list, instancia: str) -> list:
    """Quem esta instância atende: o convidado dela, ou (no principal) todos menos os convidados."""
    if instancia:
        return [l for l in todos if l == instancia]
    c = _convidados()
    return [l for l in todos if not c.convidado(l)]


def _navegador_cdp():
    ponte = sys.modules["agentepessoal_ponte_a0"]
    base = os.environ.get("BROWSER_CDP_URL", "")
    if not base:
        raise RuntimeError("este Hermes não tem navegador (BROWSER_CDP_URL)")
    return ponte.NavegadorCDP(base)


def instalar():
    """Carrega (ou recarrega, depois de uma implantação) os helpers do A0 com os três pontos do Hermes. Idempotente."""
    ponte = sys.modules["agentepessoal_ponte_a0"]
    ponte.instalar_modulos()
    ex = _modulo("conversas_externas_helper", RAIZ / "helpers" / "externas.py")
    nav = _modulo("conversas_externas_navegador", RAIZ / "helpers" / "navegador.py")
    instancia = ponte.convidado_da_instancia()
    if not getattr(ex, "_hermes", False):
        original = ex.logins
        ex.logins = lambda: meus_logins(original(), instancia)
        ex._hermes = True
    if not getattr(nav, "_hermes", False):
        SemWhatsApp = nav.SemWhatsApp

        async def _runtime(ex_, login, nome):
            if instancia and login != instancia:
                raise SemWhatsApp("a aba do WhatsApp não é desta pessoa")
            if not instancia and _convidados().convidado(login):
                raise SemWhatsApp("o WhatsApp de um convidado só abre no navegador dele")
            return _navegador_cdp()

        def manter_acordado(ex_, login):
            ACORDADO.parent.mkdir(parents=True, exist_ok=True)
            ACORDADO.touch()

        nav._runtime, nav.manter_acordado, nav._hermes = _runtime, manter_acordado, True
    # o receber.py do A0 com a entrega no Hermes (o vigia e o aprender entregam por ele)
    sys.modules.get("agentepessoal_botoes") or _carregar_botoes()
    sys.modules["agentepessoal_botoes"].receber()
    _modulo("whatsapp_ponte", PLUGINS / "whatsapp" / "helpers" / "ponte.py")  # a ferramenta procura por este nome
    return ex, nav


def _carregar_botoes():
    aqui = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("agentepessoal_botoes", aqui / "botoes_hermes.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


async def passo() -> None:
    """Uma passada do vigia do A0 (_48_vigiar_conversas._passo) com os pontos do Hermes."""
    instalar()
    vigia = _modulo("hermes_vigia_conversas", RAIZ / "extensions" / "python" / "job_loop" / "_48_vigiar_conversas.py")
    await vigia._passo()


_ULTIMO = {"em": 0.0}


async def passo_do_relogio() -> None:
    """No relógio (a cada minuto), como o A0: no máximo uma passada por minuto."""
    if time.time() - _ULTIMO["em"] < 60:
        return
    _ULTIMO["em"] = time.time()
    await passo()
